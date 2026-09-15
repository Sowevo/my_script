"""使用本地HTTP服务器验证下载行为，不访问外网或用户下载目录。"""

from contextlib import redirect_stdout, redirect_stderr
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
from pathlib import Path
import pickle
import socket
import sys
from tempfile import TemporaryDirectory
from threading import Thread, Lock
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import pbf_download as downloader
import parse_osm


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix='rail-download-test-')
        self.directory = Path(self.temp.name)
        self.body = bytes(range(256)) * 12288
        self.etag = '"version-1"'
        self.mode = 'range'
        self.partial_sent = False
        self.requests = []
        self.active = 0
        self.peak = 0
        self.lock = Lock()
        test = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path == '/redirect':
                    self.send_response(302)
                    self.send_header('Location', '/file')
                    self.end_headers()
                    return
                if self.path == '/missing':
                    self.send_error(404)
                    return
                requested = self.headers.get('Range')
                probe = requested == 'bytes=0-0'
                with test.lock:
                    test.requests.append(requested)
                    if test.mode == 'interrupt' and not probe:
                        if test.partial_sent:
                            self.send_error(503)
                            return
                        test.partial_sent = True
                ranged = bool(requested) and test.mode != 'stream'
                start, end = 0, len(test.body) - 1
                if ranged:
                    first, last = requested.removeprefix('bytes=').split('-')
                    start, end = int(first), int(last)
                self.send_response(206 if ranged else 200)
                self.send_header('Content-Length', str(end - start + 1))
                if test.etag:
                    self.send_header('ETag', test.etag)
                if ranged:
                    reported_start = start + 1 if test.mode == 'bad-range' and not probe else start
                    self.send_header('Content-Range', f'bytes {reported_start}-{end}/{len(test.body)}')
                self.end_headers()
                with test.lock:
                    test.active += 1
                    test.peak = max(test.peak, test.active)
                try:
                    stop = min(start + 65536, end + 1) if test.mode == 'interrupt' and not probe else end + 1
                    for offset in range(start, stop, 16384):
                        self.wfile.write(test.body[offset:min(offset + 16384, stop)])
                        time.sleep(.002)
                    if stop != end + 1:
                        self.connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                finally:
                    with test.lock:
                        test.active -= 1

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/redirect'
        self.download_dir = patch.object(downloader, 'get_download_dir', return_value=self.directory)
        self.download_dir.start()
        self.stdout = redirect_stdout(io.StringIO())
        self.stderr = redirect_stderr(io.StringIO())
        self.stdout.__enter__()
        self.stderr.__enter__()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.download_dir.stop()
        self.stdout.__exit__(None, None, None)
        self.stderr.__exit__(None, None, None)
        self.temp.cleanup()

    def test_parallel_redirect_and_completed_file_reuse(self):
        target = downloader.download_pbf(self.url)
        self.assertEqual(target.read_bytes(), self.body)
        self.assertGreater(self.peak, 1)
        self.assertLessEqual(self.peak, 16)
        before = len(self.requests)
        self.assertEqual(downloader.download_pbf(self.url), target)
        self.assertEqual(self.requests[before:], ['bytes=0-0'])
        self.assertFalse(list(target.parent.glob('*.partial')))

    def test_interrupted_download_resumes_from_saved_offset(self):
        self.mode = 'interrupt'
        with self.assertRaises(RuntimeError):
            downloader.download_pbf(self.url)
        parts = list(self.directory.glob('rail/*/part-*.partial'))
        self.assertTrue(parts)
        self.assertTrue(any(p.stat().st_size > 0 for p in parts))
        self.assertFalse(list(self.directory.glob('rail/*/source.osm.pbf')))
        # 多线程下最先传输的分段不一定从0开始。
        interrupted_range = next(r for r in self.requests if r and r != 'bytes=0-0')
        resumed_start = int(interrupted_range.split('=')[1].split('-')[0]) + 65536
        before = len(self.requests)
        self.mode = 'range'
        target = downloader.download_pbf(self.url)
        self.assertEqual(target.read_bytes(), self.body)
        resumed = self.requests[before:]
        self.assertTrue(any(r and r.startswith(f'bytes={resumed_start}-') for r in resumed), resumed)

    def test_changed_remote_version_replaces_completed_file(self):
        target = downloader.download_pbf(self.url)
        self.body = b'X' * len(self.body)
        self.etag = '"version-2"'
        downloader.download_pbf(self.url)
        self.assertEqual(target.read_bytes(), self.body)

    def test_changed_remote_version_discards_partial_segments(self):
        self.mode = 'interrupt'
        with self.assertRaises(RuntimeError):
            downloader.download_pbf(self.url)
        self.mode = 'range'
        self.etag = '"version-2"'
        self.body = b'Y' * len(self.body)
        self.assertEqual(downloader.download_pbf(self.url).read_bytes(), self.body)

    def test_no_range_support_uses_single_stream(self):
        self.mode = 'stream'
        self.assertEqual(downloader.download_pbf(self.url).read_bytes(), self.body)
        self.assertIn(None, self.requests)

    def test_missing_validator_does_not_reuse_stale_file(self):
        self.etag = None
        target = downloader.download_pbf(self.url)
        self.body = b'Z' * len(self.body)
        downloader.download_pbf(self.url)
        self.assertEqual(target.read_bytes(), self.body)

    def test_invalid_range_does_not_replace_existing_file(self):
        target = downloader.download_pbf(self.url)
        original = target.read_bytes()
        self.etag = '"version-2"'
        self.mode = 'bad-range'
        with self.assertRaises(ValueError):
            downloader.download_pbf(self.url)
        self.assertEqual(target.read_bytes(), original)

    def test_failed_download_does_not_start_index_generation(self):
        with patch.object(parse_osm, 'build_and_save_index') as build:
            with self.assertRaises(OSError):
                parse_osm.prepare_index(self.url.replace('/redirect', '/missing'))
            build.assert_not_called()

    def test_download_to_real_pbf_indexes(self):
        import osmium
        fixture = self.directory / 'fixture.osm.pbf'
        with osmium.SimpleWriter(str(fixture)) as writer:
            for i in range(1, 5):
                writer.add_node(osmium.osm.mutable.Node(id=i, location=(120+i/100, 30)))
            for wid, nodes, tags in [(10, [1, 2], {'railway': 'rail'}),
                                     (11, [2, 3], {'railway': 'subway'}),
                                     (12, [3, 4], {'railway': 'light_rail'}),
                                     (13, [1, 4], {'highway': 'primary'})]:
                writer.add_way(osmium.osm.mutable.Way(id=wid, nodes=nodes, tags=tags))
        self.body = fixture.read_bytes()
        data = self.directory / 'indexes'
        paths = {'DATA_DIR': data}
        for constant, filename in [('NODE_TO_WAYS_PATH', 'node_to_ways.pkl'),
                                   ('WAY_TO_NODES_PATH', 'way_to_nodes.pkl'),
                                   ('NODE_COORDS_PATH', 'node_coords.pkl'),
                                   ('WAY_TO_META_PATH', 'way_to_meta.pkl')]:
            paths[constant] = data / filename
        with patch.multiple(parse_osm, **paths):
            parse_osm.prepare_index(self.url)
        with (data / 'way_to_nodes.pkl').open('rb') as f:
            self.assertEqual(pickle.load(f), {10: [1, 2], 11: [2, 3], 12: [3, 4]})
        with (data / 'node_to_ways.pkl').open('rb') as f:
            self.assertEqual(pickle.load(f)[2], {10, 11})
        with (data / 'node_coords.pkl').open('rb') as f:
            self.assertEqual(len(pickle.load(f)), 4)


if __name__ == '__main__':
    unittest.main()

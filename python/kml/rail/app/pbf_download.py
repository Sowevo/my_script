"""PBF下载：系统下载目录、HTTP重定向、分段并发及可验证的断点续传。"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
import fcntl
import hashlib
import http.client
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from threading import Event
from urllib.error import URLError
from urllib.request import Request, urlopen

from tqdm import tqdm

MAX_CONNECTIONS = 16
MIN_PART_SIZE = 1024 * 1024
BUFFER_SIZE = 256 * 1024
TIMEOUT = 30


def get_download_dir():
    """优先查询系统下载目录，无法查询时回退到用户主目录下的Downloads。"""
    command = None
    if sys.platform == 'darwin':
        command = ['/usr/bin/osascript', '-e', 'POSIX path of (path to downloads folder)']
    elif sys.platform.startswith('linux') and shutil.which('xdg-user-dir'):
        command = ['xdg-user-dir', 'DOWNLOAD']
    if command:
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=10)
            directory = Path(result.stdout.strip())
            if directory.is_absolute():
                return directory
        except (OSError, subprocess.SubprocessError):
            pass
    return Path.home() / 'Downloads'


def _open(url, headers=None):
    request = Request(url, headers={
        'User-Agent': 'RailExplorer/1.0', 'Accept-Encoding': 'identity', **(headers or {})
    })
    response = urlopen(request, timeout=TIMEOUT)
    if response.headers.get('Content-Encoding', 'identity') != 'identity':
        response.close()
        raise ValueError('服务器返回了额外压缩的数据，无法验证分段位置')
    return response


def _content_range(response):
    match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
    if not match:
        raise ValueError('服务器返回了无效的Content-Range，停止下载')
    return tuple(map(int, match.groups()))


def _validator(response):
    etag = response.headers.get('ETag')
    if etag and not etag.startswith('W/'):
        return ['ETag', etag]
    modified = response.headers.get('Last-Modified')
    return ['Last-Modified', modified] if modified else None


def _probe(url):
    # GET探测兼容不支持HEAD的服务器；urllib自动跟随重定向。
    with _open(url, {'Range': 'bytes=0-0'}) as response:
        ranged = response.status == 206
        if ranged:
            start, end, size = _content_range(response)
            if (start, end) != (0, 0) or size < 1 or len(response.read(2)) != 1:
                raise ValueError('服务器返回了不正确的分段探测结果')
        elif response.status == 200:
            length = response.headers.get('Content-Length')
            size = int(length) if length else None
        else:
            raise ValueError(f'不支持的HTTP状态：{response.status}')
        return {'version': 1, 'url': url, 'size': size, 'ranged': ranged, 'validator': _validator(response)}


@contextmanager
def _download_lock(directory):
    with (directory / '.download.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('同一链接已有下载任务正在运行') from None
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _save_state(path, state):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state), encoding='utf-8')
    temporary.replace(path)


def _download_part(url, path, start, end, info, progress, stop):
    """每段只追加已验证范围的数据，失败重试时从实际文件长度继续。"""
    for attempt in range(3):
        if stop.is_set():
            return
        offset = path.stat().st_size if path.exists() else 0
        if offset == end - start + 1:
            return
        headers = {'Range': f'bytes={start + offset}-{end}'}
        if info['validator']:
            headers['If-Range'] = info['validator'][1]
        try:
            with _open(url, headers) as response:
                if response.status != 206:
                    raise ValueError('服务器不再接受分段请求或远端文件已变化，请重新运行下载')
                if _content_range(response) != (start + offset, end, info['size']):
                    raise ValueError('服务器返回的分段范围不一致，停止下载')
                if info['validator']:
                    key, value = info['validator']
                    actual = response.headers.get(key)
                    if actual is not None and actual != value:
                        raise ValueError('远端文件版本已变化，请重新运行下载')
                remaining = end - start + 1 - offset
                with path.open('ab') as output:
                    while remaining and not stop.is_set():
                        chunk = response.read(min(BUFFER_SIZE, remaining))
                        if not chunk:
                            raise OSError('分段下载提前结束')
                        output.write(chunk)
                        remaining -= len(chunk)
                        progress.update(len(chunk))
                if not remaining and response.read(1):
                    path.unlink()
                    raise ValueError('服务器返回了超出请求范围的数据')
            return
        except (OSError, URLError, http.client.HTTPException) as error:
            if attempt == 2:
                raise RuntimeError('下载失败，进度已保留；用同一链接重试即可续传') from error
            if stop.wait(attempt + 1):
                return


def _download_ranges(url, directory, info):
    size = info['size']
    count = min(MAX_CONNECTIONS, max(1, size // MIN_PART_SIZE))
    part_size = (size + count - 1) // count
    parts = []
    for index, start in enumerate(range(0, size, part_size)):
        end = min(start + part_size, size) - 1
        path = directory / f'part-{index:02d}.partial'
        if path.exists() and path.stat().st_size > end - start + 1:
            path.unlink()
        parts.append((path, start, end))
    initial = sum(path.stat().st_size for path, _, _ in parts if path.exists())
    stop = Event()
    with tqdm(total=size, initial=initial, desc='下载PBF', unit='B', unit_scale=True) as progress:
        with ThreadPoolExecutor(max_workers=count) as pool:
            futures = [pool.submit(_download_part, url, path, start, end, info, progress, stop)
                       for path, start, end in parts]
            try:
                for future in as_completed(futures):
                    future.result()
            except BaseException:
                stop.set()
                for future in futures:
                    future.cancel()
                raise
    merged = directory / 'source.osm.pbf.partial'
    with merged.open('wb') as output:
        for path, start, end in parts:
            if path.stat().st_size != end - start + 1:
                raise ValueError('分段大小校验失败')
            with path.open('rb') as part:
                shutil.copyfileobj(part, output, BUFFER_SIZE)
    return merged


def _download_stream(url, directory, info):
    print('服务器不支持分段下载，改用单连接完整下载。')
    target = directory / 'source.osm.pbf.partial'
    with _open(url) as response:
        if response.status != 200:
            raise ValueError(f'不支持的HTTP状态：{response.status}')
        if info['validator'] and _validator(response) != info['validator']:
            raise ValueError('远端文件版本已变化，请重新运行下载')
        length = response.headers.get('Content-Length')
        size = int(length) if length else None
        received = 0
        with target.open('wb') as output, tqdm(total=size, desc='下载PBF', unit='B', unit_scale=True) as progress:
            while chunk := response.read(BUFFER_SIZE):
                output.write(chunk)
                received += len(chunk)
                progress.update(len(chunk))
        if received == 0 or (size is not None and received != size):
            raise ValueError('下载文件为空或长度不完整，请重试')
    return target


def download_pbf(url):
    directory = get_download_dir() / 'rail' / hashlib.sha256(url.encode('utf-8')).hexdigest()[:16]
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / 'source.osm.pbf'
    print(f'下载文件：{destination}', flush=True)
    with _download_lock(directory):
        info = _probe(url)
        state_path = directory / 'download.json'
        try:
            saved = json.loads(state_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            saved = {}
        reusable = bool(info['validator']) and saved.get('source') == info
        if reusable and saved.get('complete') and destination.is_file():
            if destination.stat().st_size == saved.get('downloaded_size'):
                print('远端版本未变化，复用已下载文件。')
                return destination
        if not reusable:
            for part in directory.glob('*.partial'):
                part.unlink()
        if not info['validator']:
            print('服务器未提供文件版本标识；本次重新下载，避免混用旧数据。')
        _save_state(state_path, {'source': info, 'complete': False})
        downloaded = (_download_ranges(url, directory, info) if info['ranged']
                      else _download_stream(url, directory, info))
        downloaded.replace(destination)
        _save_state(state_path, {'source': info, 'complete': True, 'downloaded_size': destination.stat().st_size})
        for part in directory.glob('*.partial'):
            part.unlink()
    return destination

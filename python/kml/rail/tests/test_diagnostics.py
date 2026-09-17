"""验证前端操作摘要、数据请求、错误堆栈与轮转日志。"""
import json
import logging
from pathlib import Path
import sys
import tempfile
import unittest
from flask import Flask, jsonify, request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from diagnostics import configure_logging, record_diagnostic


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.app = Flask('diagnostic-test-' + self.id())
        self.path = configure_logging(self.app, self.directory.name)

        @self.app.post('/diagnostics')
        def diagnostic():
            record_diagnostic('client_operation', **request.json)
            return jsonify(ok=True)

        @self.app.post('/track-data')
        def track_data():
            return jsonify(error='当前索引中没有指定轨道。'), 404

        @self.app.get('/broken')
        def broken():
            raise RuntimeError('diagnostic failure')

    def tearDown(self):
        for handler in list(self.app.logger.handlers):
            if isinstance(handler, logging.FileHandler):
                handler.close()
                self.app.logger.removeHandler(handler)
        self.directory.cleanup()

    def records(self):
        return [json.loads(line) for line in self.path.read_text().splitlines()]

    def test_data_error_logs_ids_version_not_credentials(self):
        response = self.app.test_client().post('/track-data',
            json={'way_ids':[1,2], 'dataset_version':'v1', 'password':'never-log'},
            headers={'Authorization':'never-log', 'Cookie':'never-log'})
        record = self.records()[-1]
        self.assertEqual(record['request_id'], response.headers['X-Request-ID'])
        self.assertEqual(record['body']['way_ids'], [1,2])
        self.assertEqual(record['body']['dataset_version'], 'v1')
        self.assertEqual(record['status'], 404)
        self.assertNotIn('never-log', self.path.read_text())
        self.assertNotIn('Set-Cookie', response.headers)

    def test_client_projection_and_summary_are_recorded_without_session(self):
        body = {'page_id':'page-1', 'operation':'startPreview', 'revision':3,
                'before':{'current_way':1, 'way_count':1},
                'after':{'current_way':1, 'way_count':1},
                'details':[{'event':'start_projection', 'way_id':1, 'distance_m':900}],
                'error':'请在已选轨道上点击起点（距离不超过 150 米）。'}
        response = self.app.test_client().post('/diagnostics', json=body)
        record = self.records()[-1]['diagnostics'][0]
        self.assertEqual(record['page_id'], 'page-1')
        self.assertEqual(record['before'], record['after'])
        self.assertGreater(record['details'][0]['distance_m'], 150)
        self.assertIn('150', record['error'])
        self.assertNotIn('Set-Cookie', response.headers)

    def test_unexpected_error_has_traceback_and_correlated_id(self):
        response = self.app.test_client().get('/broken')
        record = next(r for r in self.records() if r.get('event') == 'unhandled_exception')
        self.assertEqual(record['request_id'], response.headers['X-Request-ID'])
        self.assertIn('RuntimeError: diagnostic failure', record['exception'])

    def test_rotation_limits_file_growth(self):
        handler = next(h for h in self.app.logger.handlers if isinstance(h, logging.FileHandler))
        self.assertEqual(handler.maxBytes, 5 * 1024 * 1024)
        self.assertEqual(handler.backupCount, 3)
        handler.maxBytes = 250
        for i in range(20):
            self.app.logger.info('x' * 100)
        self.assertTrue(Path(str(self.path) + '.1').exists())
        self.assertLessEqual(len(list(Path(self.directory.name).glob('rail.log*'))), 4)

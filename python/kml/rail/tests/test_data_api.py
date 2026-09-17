"""隔离索引验证：后端只读数据、版本检查、不使用行程会话。"""
import importlib.util
import json
import logging
import os
from pathlib import Path
import pickle
import sys
import tempfile
import unittest
from unittest.mock import patch

APP_DIR = Path(__file__).resolve().parents[1] / 'app'
sys.path.insert(0, str(APP_DIR))


class DataApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        fixtures = {
            'way_to_nodes': {1:[10,11], 2:[11,12]},
            'node_to_ways': {10:{1}, 11:{1,2}, 12:{2}},
            'node_coords': {10:(35,139), 11:(35,139.001), 12:(35,139.002)},
            'way_to_meta': {1:{'name':'测试', 'tags':{'name':'测试','railway':'rail'}}, 2:{'tags':{}}},
        }
        for name, value in fixtures.items():
            with open(Path(cls.directory.name) / (name + '.pkl'), 'wb') as stream:
                pickle.dump(value, stream)
        spec = importlib.util.spec_from_file_location('rail_data_test_app', APP_DIR / 'app.py')
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        with patch.dict(os.environ, {'RAIL_DATA_DIR':cls.directory.name}):
            spec.loader.exec_module(cls.module)
        cls.client = cls.module.app.test_client()
        cls.version = cls.module.DATASET_VERSION

    @classmethod
    def tearDownClass(cls):
        for handler in list(cls.module.app.logger.handlers):
            if isinstance(handler, logging.FileHandler):
                handler.close()
                cls.module.app.logger.removeHandler(handler)
        sys.modules.pop(cls.module.__name__, None)
        cls.directory.cleanup()

    def post(self, ids, version=None):
        return self.client.post('/track-data', json={
            'way_ids':ids, 'dataset_version':version or self.version})

    def test_track_data_returns_only_requested_way_with_adjacency(self):
        response = self.post([1])
        self.assertEqual(response.status_code, 200)
        data = response.json
        self.assertEqual(set(data['ways']), {'1'})
        self.assertEqual(data['ways']['1']['nodes'], [10,11])
        self.assertEqual(data['node_ways']['11'], [1,2])
        self.assertEqual(set(data['coords']), {'10','11'})
        self.assertEqual(data['ways']['1']['meta']['tags']['name'], '测试')
        self.assertNotIn('Set-Cookie', response.headers)

    def test_invalid_and_missing_ids(self):
        for ids in ([], [True], ['1'], [1] * 1001):
            self.assertEqual(self.post(ids).status_code, 400)
        self.assertEqual(self.post([999]).status_code, 404)
        self.assertEqual(self.post([999]).json['missing'], [999])

    def test_dataset_version_required_on_all_index_queries(self):
        self.assertEqual(self.post([1], 'old').status_code, 409)
        for url in ('/elements/way/1','/nearby?lat=35&lon=139','/stations/map?bbox=35,139,36,140&zoom=16'):
            self.assertEqual(self.client.get(url).status_code, 409)
        self.assertEqual(self.client.get('/dataset').json['dataset_version'], self.version)
        self.assertEqual(self.client.get('/elements/way/1?dataset_version=' + self.version).status_code, 200)

    def test_page_renders_and_legacy_calculation_routes_are_absent(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'journey_engine.js', response.data)
        self.assertNotIn(b'empty_revision', response.data)
        for method, url in [('get','/ways/1'),('post','/journey/clear'),('post','/journey/start'),
                            ('post','/journey/cut'),('post','/journey/undo-way')]:
            self.assertEqual(getattr(self.client, method)(url).status_code, 404)
        self.assertIsNone(self.module.app.secret_key)

    def test_diagnostics_whitelist_and_request_id(self):
        response = self.client.post('/diagnostics', json={
            'operation':'advance', 'page_id':'page-a', 'before':{'way_count':1},
            'after':{'way_count':2}, 'password':'not-written'})
        self.assertEqual(response.status_code, 200)
        records = [json.loads(line) for line in (Path(self.directory.name)/'logs/rail.log').read_text().splitlines()]
        record = records[-1]
        self.assertEqual(record['request_id'], response.headers['X-Request-ID'])
        self.assertEqual(record['diagnostics'][0]['operation'], 'advance')
        self.assertNotIn('not-written', json.dumps(record))
        self.assertEqual(self.client.post('/diagnostics', json={'details':'x'*65000}).status_code, 400)

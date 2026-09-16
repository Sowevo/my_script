"""验证本地关联优先级、换乘站分组及附近站兜底。"""
from pathlib import Path
import sys
import unittest
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from stations import StationIndex
from station_index import assign_stop_areas

class StationTests(unittest.TestCase):
    def setUp(self):
        self.features = {
            ('n', 1): {'name': '关联站', 'rail': True, 'coords': (35.004, 139)},
            ('n', 2): {'name': '线路站', 'rail': True, 'coords': (35.002, 139)},
            ('n', 3): {'name': '附近站', 'rail': True, 'coords': (35, 139)},
            ('n', 4): {'name': '远站', 'rail': True, 'coords': (36, 139)},
        }
        self.index = StationIndex({'features': self.features,
                                  'routes': {10: {'ways': [100], 'stops': [('n', 2)]}}},
                                 {100: [1, 8], 101: [8, 9]})

    def test_associations_beat_closer_unrelated_station(self):
        result = self.index.query((35, 139), [100])
        self.assertEqual([s['name'] for s in result], ['线路站', '关联站', '附近站'])
        self.assertEqual([s['source'] for s in result], ['线路停靠站', '轨道停车点', '附近车站'])

    def test_fallback_when_no_association(self):
        result = self.index.query((35, 139), [101])
        self.assertEqual(result[0]['name'], '附近站')
        self.assertTrue(all(s['source'] == '附近车站' for s in result))
        self.assertEqual(self.index.query((0, 0), [100]), [])

    def test_parent_group_does_not_merge_distinct_stop_areas(self):
        relations = {
            20: {'id':20, 'tags':{'public_transport':'stop_area','name':'单轨站'}, 'members':[{'type':'n','ref':1}]},
            21: {'id':21, 'tags':{'public_transport':'stop_area','name':'JR站'}, 'members':[{'type':'n','ref':2}]},
            22: {'id':22, 'tags':{'public_transport':'stop_area_group','name':'换乘站'},
                 'members':[{'type':'r','ref':20},{'type':'r','ref':21}]},
        }
        assign_stop_areas(self.features, relations)
        self.assertEqual(self.features[('n',1)]['stop_area'], 20)
        self.assertEqual(self.features[('n',2)]['stop_area'], 21)
        self.assertEqual(self.features[('n',1)]['name'], '单轨站')
        self.assertEqual(self.features[('n',2)]['name'], 'JR站')
        self.assertTrue(all('group' not in f for f in self.features.values()))
        self.assertNotIn('group', self.features[('n',3)])

    def test_pbf_builder_resolves_unnamed_stop_and_platform_geometry(self):
        from station_index import build_station_index
        xml = """<osm version="0.6">
          <node id="1" lat="35" lon="139"><tag k="public_transport" v="stop_position"/></node>
          <node id="2" lat="35.001" lon="139"/>
          <node id="3" lat="35.002" lon="139"/>
          <way id="9"><nd ref="2"/><nd ref="3"/><tag k="railway" v="platform"/></way>
        </osm>"""
        relations = {
            10: {'id':10, 'tags':{'type':'route','route':'train'}, 'members':[
                {'type':'n','ref':1,'role':'stop'}, {'type':'w','ref':9,'role':'platform'},
                {'type':'w','ref':100,'role':''}]},
            20: {'id':20, 'tags':{'public_transport':'stop_area','name':'测试站'}, 'members':[
                {'type':'n','ref':1,'role':'stop'}, {'type':'w','ref':9,'role':'platform'}]},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'station.osm'
            path.write_text(xml)
            data = build_station_index(path, directory, {100:[1,2]}, relations)
            self.assertEqual(data['features'][('n',1)]['name'], '测试站')
            self.assertEqual(data['features'][('w',9)]['stop_area'], 20)
            self.assertAlmostEqual(data['features'][('w',9)]['coords'][0], 35.0015)
            self.assertTrue((Path(directory) / 'stations.pkl').is_file())

    def test_unnamed_platform_outline_is_kept_without_becoming_station_name(self):
        from station_index import build_station_index
        from station_map import StationMap
        xml = '''<osm version="0.6">
          <node id="1" lat="35" lon="139"/>
          <node id="2" lat="35.001" lon="139"/>
          <node id="3" lat="35" lon="139.001"/>
          <way id="9"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="1"/>
            <tag k="railway" v="platform"/><tag k="ref" v="1"/></way>
          <way id="10"><nd ref="1"/><nd ref="2"/><tag k="railway" v="platform"/></way>
        </osm>'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'platform.osm'
            path.write_text(xml)
            data = build_station_index(path, directory, {}, {})
            self.assertEqual(data['features'][('w',9)]['name'], '')
            self.assertNotIn(('w',10), data['features'])
            station = StationMap(data['features']).query(34.99,138.99,35.01,139.01)['stations'][0]
            self.assertEqual(station['name'], '1 号站台')
            self.assertEqual(len(station['polygons'][0]), 4)
            self.assertEqual(StationIndex(data, {}).query((35,139), []), [])
            data['features'][('w',9)]['ref'] = ''
            self.assertEqual(StationMap(data['features']).stations['way/9']['name'], '未命名站台')

    def test_later_stop_does_not_override_endpoint_station(self):
        self.index.ways[101] = [3, 8]
        result = self.index.query((35, 139), [100, 101])
        self.assertEqual(result[0]['name'], '线路站')
        self.assertEqual(next(s for s in result if s['name'] == '附近站')['source'], '附近车站')

    def test_building_contains_stop_but_does_not_rename_outside_stop(self):
        from station_index import assign_building_names
        features = {
            ('w', 128195825): {'name':'浜松町駅', 'rail':True, 'coords':(1,1),
                'building_polygon':[(0,0),(0,2),(2,2),(2,0),(0,0)]},
            ('w', 210374585): {'name':'單軌電車濱松町', 'rail':True, 'coords':(1,4),
                'building_polygon':[(0,3),(0,5),(2,5),(2,3),(0,3)]},
            ('n',1): {'name':'', 'rail':True, 'coords':(1,1)},
            ('n',2): {'name':'モノレール浜松町', 'rail':True, 'coords':(1,4), 'stop_area':9251545},
            ('n',3): {'name':'其他站', 'rail':True, 'coords':(3,3)},
        }
        assign_building_names(features)
        self.assertEqual(features[('n',1)]['name'], '浜松町駅')
        self.assertEqual(features[('n',2)]['name'], 'モノレール浜松町')
        self.assertEqual(features[('n',3)]['name'], '其他站')
        self.assertEqual(features[('n',1)]['station_building'], 128195825)

    def test_same_name_different_stop_areas_are_not_deduplicated(self):
        self.features[('n',1)].update(name='同名站', stop_area=20)
        self.features[('n',2)].update(name='同名站', stop_area=21)
        stations = [s for s in self.index.query((35,139), [100]) if s['name'] == '同名站']
        self.assertEqual({s['stop_area'] for s in stations}, {20,21})

    def test_ambiguous_stop_area_keeps_original_name(self):
        relations = {i: {'id':i, 'tags':{'public_transport':'stop_area', 'name':str(i)},
                        'members':[{'type':'n','ref':1}]} for i in (20,21)}
        assign_stop_areas(self.features, relations)
        self.assertEqual(self.features[('n',1)]['name'], '关联站')
        self.assertNotIn('stop_area', self.features[('n',1)])

    def test_local_name_precedes_translations(self):
        from station_index import name
        self.assertEqual(name({'name':'羽田空港第3ターミナル', 'name:zh':'羽田机场3号航站楼',
                               'name:ja':'日文别名', 'name:en':'Haneda Airport T3'}), '羽田空港第3ターミナル')
        self.assertEqual(name({'name:zh':'中文备用', 'name:ja':'日文备用'}), '中文备用')
        self.assertEqual(name({'name:en':'Fallback'}), 'Fallback')
        self.assertEqual(name({}), '')

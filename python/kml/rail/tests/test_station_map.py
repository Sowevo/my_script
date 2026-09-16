"""验证车站地图去重、代表点、建筑范围及视野过滤。"""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from station_map import StationMap, StationLines


class StationLinesTests(unittest.TestCase):
    def test_master_merges_directions_and_ignores_infrastructure(self):
        features = {('n', 1): {'station_node': True}}
        member = {'type': 'n', 'ref': 1, 'role': 'stop'}
        relations = {
            1: {'tags': {'type':'route', 'route':'train', 'name':'线路（上り）', 'ref':'JY', 'operator':'JR'}, 'members':[member]},
            2: {'tags': {'type':'route', 'route':'train', 'name':'线路（下り）', 'ref':'JY', 'operator':'JR'}, 'members':[member]},
            3: {'tags': {'type':'route_master', 'route_master':'train', 'name':'山手線', 'ref':'JY', 'operator':'JR'},
                'members':[{'type':'r','ref':1}, {'type':'r','ref':2}]},
            4: {'tags': {'type':'route', 'route':'railway', 'name':'底层铁路线'}, 'members':[member]},
        }
        lines = StationLines(features, relations)
        self.assertEqual(lines.get([('n',1)]), [{'name':'山手線','operator':'JR'}])
        self.assertEqual(lines.get([('n',2)]), [])

    def test_same_ref_different_operators_are_distinct(self):
        features = {('n',1): {'station_node':True}}
        relations = {i: {'tags': {'type':'route','route':'train','name':f'线路{i}','ref':'1','operator':str(i)},
                         'members':[{'type':'n','ref':1,'role':'stop'}]} for i in (1,2)}
        self.assertEqual(len(StationLines(features,relations).get([('n',1)])),2)

class StationMapTests(unittest.TestCase):
    def test_only_stations_and_dedup_with_lines(self):
        features = {
            ('n',1): {'name':'本站','coords':(35,139),'rail':True,'station_node':True,'stop_area':10},
            ('w',2): {'name':'本站','coords':(35.1,139),'rail':True,'station_node':True,'stop_area':10},
            ('n',3): {'name':'本站','coords':(35,139),'rail':True,'stop_position':True,'stop_area':10},
            ('n',4): {'name':'公交','coords':(35,139),'rail':True,'station_node':True,'bus_only':True},
            ('n',5): {'name':'本站','coords':(35.01,139),'rail':True,'station_node':True,'stop_area':11},
            ('w',6): {'name':'独立站','coords':(35.02,139),'rail':True,'station_node':True},
        }
        relations = {1: {'tags':{'type':'route','route':'train','name':'线路'},
                        'members':[{'type':'n','ref':3,'role':'stop'}]}}
        catalog = StationMap(features,relations)
        self.assertEqual(set(catalog.stations), {'relation/10','relation/11','way/6'})
        self.assertEqual(catalog.stations['relation/10']['lat'],35)
        self.assertEqual(catalog.stations['relation/10']['lines'],[{'name':'线路','operator':''}])
        self.assertTrue(catalog.query(34,138,36,140,limit=1)['truncated'])
        self.assertEqual(catalog.query(0,0,1,1)['stations'],[])
        self.assertEqual(len(catalog.query(34.999,138.999,35.001,139.001)['stations']),1)

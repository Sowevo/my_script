"""验证车站地图去重、代表点、建筑范围及视野过滤。"""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from station_map import StationMap

class StationMapTests(unittest.TestCase):
    def setUp(self):
        self.features = {
            ('n',1): {'name':'单轨站','coords':(35,139),'stop_area':10,'station_node':True,'station_building':20},
            ('n',2): {'name':'单轨站','coords':(35.001,139),'stop_area':10,'stop_position':True,'station_building':20},
            ('n',3): {'name':'JR站','coords':(35.002,139),'stop_area':11,'stop_position':True,'station_building':21},
            ('w',20): {'name':'单轨建筑','coords':(35,139),'building_polygon':[(35,139),(35,139.001),(35.001,139.001),(35,139)]},
            ('w',21): {'name':'JR建筑','coords':(35.002,139),'building_polygon':[(35.002,139),(35.002,139.001),(35.003,139),(35.002,139)]},
            ('n',4): {'name':'独立站','coords':(36,140),'station_node':True},
            ('n',5): {'name':'无关联停车点','coords':(35,139),'stop_position':True},
        }
        self.catalog = StationMap(self.features)

    def test_stop_area_unique_and_distinct_stations_retained(self):
        self.assertEqual(set(self.catalog.stations), {'relation/10','relation/11','node/4'})
        station = self.catalog.stations['relation/10']
        self.assertEqual(station['lat'],35)
        self.assertTrue(station['has_building'])
        self.assertEqual(len(station['polygons']),1)

    def test_viewport_filter_limit_and_small_response(self):
        result=self.catalog.query(34.99,138.99,35.01,139.01)
        self.assertEqual(len(result['stations']),2)
        self.assertFalse(result['truncated'])
        self.assertTrue(result['stations'][0]['polygons'])
        self.assertTrue(self.catalog.query(34.99,138.99,35.01,139.01,limit=1)['truncated'])
        self.assertEqual(self.catalog.query(0,0,1,1)['stations'],[])

    def test_unrelated_station_building_and_node_do_not_duplicate(self):
        self.features[('n',4)]['station_building']=30
        self.features[('w',30)]={'name':'独立站建筑','coords':(36,140),'building_polygon':[(36,140),(36,140.001),(36.001,140),(36,140)]}
        result=StationMap(self.features)
        self.assertIn('way/30',result.stations)
        self.assertNotIn('node/4',result.stations)
        self.assertEqual(result.stations['way/30']['name'],'独立站')

    def test_unassociated_building_does_not_override_stop_area(self):
        self.features[('w',30)]={'name':'单轨站','coords':(35.0005,139),'building_polygon':[(35,139),(35,139.001),(35.001,139),(35,139)]}
        catalog=StationMap(self.features)
        self.assertIn('way/30', catalog.stations)
        self.assertEqual(len(catalog.stations['relation/10']['polygons']), 1)

    def test_outline_in_view_even_when_station_coordinate_is_outside(self):
        result=self.catalog.query(35.0007,139.0007,35.0009,139.0009)
        self.assertEqual([s['id'] for s in result['stations']], ['relation/10'])
        self.assertEqual(self.catalog.query(35.99,139.99,36.01,140.01)['stations'], [])

    def test_stop_area_platform_has_priority_over_building(self):
        self.features[('w',50)]={'name':'独立站台', 'coords':(36,140), 'stop_area':12,
            'station_polygon':[(36,140),(36,140.001),(36.001,140),(36,140)], 'area_kind':'站台范围'}
        self.features[('w',51)]={'name':'单轨站台', 'coords':(35,139), 'stop_area':10,
            'station_polygon':[(35,139),(35,139.001),(35.001,139),(35,139)], 'area_kind':'站台范围'}
        catalog=StationMap(self.features)
        fallback=catalog.query(35.99,139.99,36.01,140.01)['stations'][0]
        self.assertEqual(fallback['outline_kind'],'站台范围')
        self.assertTrue(fallback['polygons'])
        self.assertFalse(catalog.stations['relation/12']['has_building'])
        self.assertEqual(catalog.stations['relation/10']['outline_kind'],'站台范围')
        self.assertEqual(len(catalog.stations['relation/10']['polygons']),1)

    def test_station_area_has_priority_over_platform(self):
        self.features[('w',50)]={'name':'单轨站', 'coords':(35,139), 'stop_area':10,
            'station_polygon':[(35,139),(35,139.001),(35.001,139),(35,139)], 'area_kind':'站台范围'}
        self.features[('w',51)]={'name':'单轨站', 'coords':(35,139), 'stop_area':10,
            'station_polygon':[(35,139),(35,139.002),(35.002,139),(35,139)], 'area_kind':'车站范围'}
        station=StationMap(self.features).stations['relation/10']
        self.assertEqual(station['outline_kind'],'车站范围')
        self.assertEqual(station['polygons'],[self.features[('w',51)]['station_polygon']])

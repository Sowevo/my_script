"""验证连接方向、端点接续和站场分支推荐。"""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from recommendation import recommend_way


class RecommendationTests(unittest.TestCase):
    def setUp(self):
        self.coords = {1:(0,0), 2:(0,.001), 3:(0,.002), 4:(0,.003),
                       5:(0,.004), 6:(.0001,.0025), 7:(.001,.004)}
        self.ways = {10:[1,2], 20:[2,3,4], 30:[4,5], 40:[3,6], 50:[4,7]}
        self.meta = {wid:{'tags':{'name':'线路'}} for wid in self.ways}
        self.meta[40]['tags']['service'] = 'yard'
        self.path = [{'way_id':10}, {'way_id':20}]

    def recommend(self, choices):
        return recommend_way(self.path, choices, self.ways, self.coords, self.meta)

    def test_endpoint_main_beats_midway_yard(self):
        self.assertEqual(self.recommend([40,30]),30)

    def test_reversing_all_node_orders_keeps_recommendation(self):
        for wid in self.ways:
            self.ways[wid].reverse()
        self.assertEqual(self.recommend([40,30]),30)

    def test_local_turn_breaks_same_name_tie(self):
        self.assertEqual(self.recommend([50,30]),30)

    def test_main_beats_yard_at_same_exit(self):
        self.meta[30]['tags']['service']='yard'
        self.assertEqual(self.recommend([30,50]),50)

    def test_no_recommendation_for_entry_side_or_backtracking(self):
        self.ways[30]=[2,1]
        self.ways[40]=[4,3]
        self.assertIsNone(self.recommend([30,40]))

    def test_ambiguous_entry_or_first_way_has_no_star(self):
        self.path=[{'way_id':20}]
        self.assertIsNone(self.recommend([30]))
        self.path=[{'way_id':40},{'way_id':20}]
        self.assertIsNone(self.recommend([30]))

    def test_missing_coordinates_and_equal_branches_have_no_star(self):
        self.ways[50]=[4,5]
        self.assertIsNone(self.recommend([30,50]))
        del self.coords[4]
        self.assertIsNone(self.recommend([30]))

if __name__ == '__main__':
    unittest.main()

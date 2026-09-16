"""截断方向、停车点吸附、部分轨道继续及统一撤销。"""
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from journey import JourneyExplorer
from journey_cut import JourneyCut, revision


class CutTests(unittest.TestCase):
    def setUp(self):
        self.ways = {1:[1,2,3], 2:[3,4,5], 3:[5,6], 4:[7,6], 8:[8,9]}
        self.coords = {i:(35, 139 + i * .001) for i in range(1,10)}
        neighbors = defaultdict(set)
        for wid, nodes in self.ways.items():
            for node in nodes:
                neighbors[node].add(wid)
        self.explorer = JourneyExplorer(self.ways, neighbors, {})
        self.cut = JourneyCut(self.ways, self.coords, {})
        self.legs, _ = self.explorer.advance([], 1, max_steps=2)

    def candidate(self, legs, longitude):
        return self.cut.preview(legs, [35,longitude])['candidates'][0]

    def test_last_way_cut_and_undo_preserves_prior_ways(self):
        before = deepcopy(self.legs)
        candidate = self.candidate(self.legs,139.0045)
        result = self.cut.apply(self.legs,candidate)
        self.assertEqual(len(result[0]['path']),2)
        self.assertAlmostEqual(self.cut.item_coords(result[0]['path'][-1])[-1][1],139.0045)
        self.assertEqual(self.cut.undo_preview(result)['kind'],'cut')
        self.assertEqual(self.explorer.undo_way(result)[0],before)
        self.assertEqual(self.legs,before)
        self.assertNotEqual(revision(result),revision(before))

    def test_continue_remainder_then_undo_way_then_undo_cut(self):
        cut = self.cut.apply(self.legs,self.candidate(self.legs,139.0045))
        self.assertEqual(self.explorer.choices(cut[-1])[0],[2])
        continued,_ = self.explorer.forward_way(cut,2)
        remainder = continued[-1]['path'][-1]
        self.assertEqual(remainder['way_id'],2)
        self.assertAlmostEqual(self.cut.item_coords(remainder)[0][1],139.0045)
        self.assertEqual(self.cut.item_coords(remainder)[-1],list(self.coords[5]))
        self.assertEqual(self.cut.undo_preview(continued)['kind'],'way')
        self.assertEqual(self.explorer.undo_way(continued)[0],cut)
        self.assertEqual(self.explorer.undo_way(cut)[0],self.legs)

    def test_transfer_and_nested_cuts_restore_in_order(self):
        cut1 = self.cut.apply(self.legs,self.candidate(self.legs,139.0045))
        cut2 = self.cut.apply(cut1,self.candidate(cut1,139.0035))
        self.assertEqual(self.explorer.undo_way(cut2)[0],cut1)
        transferred,_ = self.explorer.advance(cut2,8,transfer=True,max_steps=1)
        self.assertEqual(self.explorer.undo_way(transferred)[0],cut2)

    def test_reverse_direction_and_single_way_direction_choice(self):
        legs,_ = self.explorer.advance([],4,max_steps=2)
        candidate = self.candidate(legs,139.0055)
        self.assertGreater(candidate['span'][0],candidate['span'][1])
        cut = self.cut.apply(legs,candidate)
        self.assertAlmostEqual(self.cut.item_coords(cut[-1]['path'][-1])[-1][1],139.0055)
        one,_ = self.explorer.advance([],1,max_steps=1)
        with self.assertRaisesRegex(ValueError,'尚未确定行进方向'):
            self.cut.preview(one,[35,139.0025])

    def test_stop_snap_only_to_stop_on_selected_way_and_within_25m(self):
        self.cut = JourneyCut(self.ways,self.coords,{('n',4):{'stop_position':True},
                                                   ('n',8):{'stop_position':True}})
        candidate = self.candidate(self.legs,139.0041)
        self.assertTrue(candidate['snapped'])
        self.assertEqual(candidate['point'],list(self.coords[4]))
        self.assertFalse(self.candidate(self.legs,139.0045)['snapped'])

    def test_far_click_empty_journey_and_noop_are_rejected(self):
        with self.assertRaises(ValueError):self.cut.preview(self.legs,[36,139])
        with self.assertRaises(ValueError):self.cut.preview([],[35,139])
        with self.assertRaises(ValueError):self.cut.preview(self.legs,list(self.coords[6]))

    def test_earlier_way_does_not_participate_in_projection(self):
        with self.assertRaisesRegex(ValueError,'最后一条轨道'):
            self.cut.preview(self.legs,[35,139.001])
        candidate=self.candidate(self.legs,139.0045)
        self.assertEqual(candidate['path_index'],1)
        self.assertEqual(candidate['way_id'],2)

    def test_one_way_keep_middle_from_confirmed_start_and_direction(self):
        started=[{'name':'测试','start_way':1,'current_way':1,'directed':True,
                  'path':[{'way_id':1,'type':'manual','span':[.5,2]}]}]
        result=self.cut.apply(started,self.candidate(started,139.0025))
        coords=self.cut.item_coords(result[0]['path'][0])
        self.assertAlmostEqual(coords[0][1],139.0015)
        self.assertAlmostEqual(coords[-1][1],139.0025)
        self.assertEqual(self.explorer.undo_way(result)[0],started)
        reverse=[{'name':'测试','start_way':1,'current_way':1,'directed':True,
                  'path':[{'way_id':1,'type':'manual','span':[1.5,0]}]}]
        result=self.cut.apply(reverse,self.candidate(reverse,139.0015))
        self.assertGreater(result[0]['path'][0]['span'][0],result[0]['path'][0]['span'][1])
        self.assertEqual(self.explorer.undo_way(result)[0],reverse)

    def test_point_start_offers_two_halves_and_endpoint_only_one(self):
        whole=self.cut.start_preview(2)
        self.assertIsNone(whole['point'])
        self.assertEqual([d['span'] for d in whole['directions']],[[2,0],[0,2]])
        self.assertEqual(whole['directions'][0]['coords'],whole['directions'][1]['coords'][::-1])
        preview=self.cut.start_preview(2,[35,139.0045])
        self.assertEqual(len(preview['directions']),2)
        for direction in preview['directions']:
            self.assertAlmostEqual(direction['coords'][0][1],139.0045)
        self.assertEqual(len(self.cut.start_preview(2,list(self.coords[3]))['directions']),1)
        with self.assertRaises(ValueError):self.cut.start_preview(2,[36,139])

    def test_directed_start_only_continues_from_chosen_end(self):
        preview=self.cut.start_preview(2,[35,139.0045])
        for direction, expected in zip(preview['directions'],([1],[3])):
            leg={'name':'测试','start_way':2,'current_way':2,'directed':True,
                 'path':[{'way_id':2,'type':'manual','span':direction['span']}]}
            self.assertEqual(self.explorer.choices(leg)[0],expected)
            continued,_=self.explorer.forward_way([leg],expected[0])
            first_end=self.cut.item_coords(leg['path'][0])[-1]
            next_start=self.cut.item_coords(continued[0]['path'][-1])[0]
            self.assertEqual(first_end,next_start)
            self.assertEqual(self.explorer.undo_way([leg])[0],[])


if __name__ == '__main__':unittest.main()

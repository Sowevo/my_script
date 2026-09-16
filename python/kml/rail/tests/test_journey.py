"""验证换乘隔离、旧线路状态不再限制探索和无效操作不损坏行程。"""

from collections import defaultdict
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from journey import JourneyExplorer


class JourneyTests(unittest.TestCase):
    def setUp(self):
        ways = {1:[1,2], 2:[2,3], 3:[3,4], 4:[3,5], 8:[8,9], 9:[9,10]}
        nodes = defaultdict(set)
        for wid, points in ways.items():
            for point in points:
                nodes[point].add(wid)
        meta = {wid:{'tags':{'name':f'轨道{wid}'}} for wid in ways}
        self.explorer = JourneyExplorer(ways, nodes, meta)

    def test_transfer_preserves_previous_leg_and_allows_disconnected_way(self):
        legs, _ = self.explorer.advance([], 1)
        previous = list(legs[0]['path'])
        updated, result = self.explorer.advance(legs, 8, transfer=True, transfer_label='换乘站')
        self.assertEqual(updated[0]['path'], previous)
        self.assertEqual([x['way_id'] for x in updated[1]['path']], [8,9])
        self.assertEqual(updated[1]['transfer_label'], '换乘站')
        self.assertEqual(result['current_way'], 9)
        self.assertEqual(len(legs), 1)

    def test_new_leg_can_reuse_previous_track(self):
        legs, _ = self.explorer.advance([], 1)
        updated, _ = self.explorer.advance(legs, 1, transfer=True)
        self.assertEqual(updated[0]['path'], updated[1]['path'])

    def test_disconnected_continuation_is_rejected_without_mutation(self):
        legs, _ = self.explorer.advance([], 1)
        with self.assertRaises(ValueError):
            self.explorer.advance(legs, 8)
        self.assertEqual(len(legs), 1)
        self.assertEqual(legs[0]['current_way'], 2)

    def test_old_relation_state_does_not_force_member_order(self):
        legs, _ = self.explorer.advance([], 1)
        legs[0].update(relation_id=10, route_cursor=1)
        choices, _ = self.explorer.choices(legs[0])
        self.assertEqual(choices, [3, 4])

    def test_undo_removes_one_auto_way_without_advancing(self):
        legs, _ = self.explorer.advance([], 1)
        updated, result = self.explorer.undo_way(legs)
        self.assertEqual([x['way_id'] for x in updated[0]['path']], [1])
        self.assertEqual(result['current_way'], 1)
        self.assertEqual(result['choices'], [2])
        self.assertEqual(len(legs[0]['path']), 2)

    def test_undo_across_transfer_and_empty_journey(self):
        legs, _ = self.explorer.advance([], 1)
        legs, _ = self.explorer.advance(legs, 8, transfer=True)
        legs, _ = self.explorer.undo_way(legs)
        self.assertEqual(legs[-1]['current_way'], 8)
        legs, result = self.explorer.undo_way(legs)
        self.assertEqual(len(legs), 1)
        self.assertEqual(result['current_way'], 2)
        legs, _ = self.explorer.undo_way(legs)
        legs, result = self.explorer.undo_way(legs)
        self.assertEqual(legs, [])
        self.assertIsNone(result['current_way'])
        self.assertEqual(self.explorer.undo_way([])[0], [])

    def test_reset_and_invalid_start(self):
        legs, _ = self.explorer.advance([], 1)
        updated, _ = self.explorer.advance(legs, 8, reset=True)
        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0]['start_way'], 8)
        with self.assertRaises(ValueError):
            self.explorer.advance(legs, 999, transfer=True)
        with self.assertRaises(ValueError):
            self.explorer.advance([], 8, transfer=True)


class ForwardTests(unittest.TestCase):
    def setUp(self):
        ways = {1:[1,2], 2:[2,3], 3:[3,4], 4:[4,5], 5:[4,6]}
        nodes = defaultdict(set)
        for wid, ids in ways.items():
            for nid in ids:
                nodes[nid].add(wid)
        self.explorer = JourneyExplorer(ways, nodes, {})

    def test_forward_adds_only_one_even_with_more_unique_tracks(self):
        legs, _ = self.explorer.advance([], 1, max_steps=1)
        updated, result = self.explorer.forward_way(legs)
        self.assertEqual([x['way_id'] for x in updated[0]['path']], [1,2])
        self.assertEqual(result['choices'], [3])
        self.assertEqual(len(legs[0]['path']), 1)
        restored, _ = self.explorer.undo_way(updated)
        self.assertEqual(restored, legs)

    def test_explicit_branch_adds_exactly_one_and_rejects_invalid_choice(self):
        legs, _ = self.explorer.advance([], 1)
        self.assertEqual(legs[0]['current_way'], 3)
        updated, result = self.explorer.forward_way(legs, 4)
        self.assertEqual(result['path'], [4])
        self.assertEqual(result['current_way'], 4)
        self.assertEqual(len(updated[0]['path']), len(legs[0]['path']) + 1)
        self.assertEqual(legs[0]['current_way'], 3)
        with self.assertRaises(ValueError):
            self.explorer.forward_way(legs, 1)
        with self.assertRaises(ValueError):
            self.explorer.forward_way(legs, 999)

    def test_empty_branch_and_dead_end_are_rejected(self):
        with self.assertRaises(ValueError):
            self.explorer.forward_way([])
        legs, _ = self.explorer.advance([], 1)
        self.assertEqual(legs[0]['current_way'], 3)
        with self.assertRaises(ValueError):
            self.explorer.forward_way(legs)
        final = [{'current_way':5, 'path':[{'way_id':wid} for wid in (1,2,3,4,5)]}]
        with self.assertRaises(ValueError):
            self.explorer.forward_way(final)

    def test_loop_closure_stops_even_with_an_unused_exit(self):
        ways={1:[1,2],2:[2,3],3:[3,1],4:[1,4]}
        nodes=defaultdict(set)
        for wid,ids in ways.items():
            for node in ids:nodes[node].add(wid)
        explorer=JourneyExplorer(ways,nodes,{})
        for directed in (False,True):
            item={'way_id':1,'type':'manual'}
            if directed:item['span']=[0,1]
            legs=[{'name':'环线','start_way':1,'current_way':1,'directed':directed,'path':[item]}]
            self.assertFalse(explorer.loop_closed(legs[0]))
            result,info=explorer.advance(legs,2)
            self.assertEqual([i['way_id'] for i in result[0]['path']],[1,2,3])
            self.assertEqual(info['choices'],[])
            self.assertIn('接回',info['stop_reason'])
            restored,_=explorer.undo_way(result)
            self.assertFalse(explorer.loop_closed(restored[0]))
            self.assertIn(3,explorer.choices(restored[0])[0])

    def test_closure_uses_only_travelled_part_of_start_way(self):
        ways={1:[1,2,3],2:[3,4],3:[4,1],4:[1,5]}
        nodes=defaultdict(set)
        for wid,ids in ways.items():
            for node in ids:nodes[node].add(wid)
        explorer=JourneyExplorer(ways,nodes,{})
        leg={'current_way':3,'directed':True,'path':[
            {'way_id':1,'span':[1.5,2]}, {'way_id':2,'span':[0,1]}, {'way_id':3,'span':[0,1]}]}
        self.assertFalse(explorer.loop_closed(leg))
        self.assertEqual(explorer.choices(leg)[0],[4])


if __name__ == '__main__':
    unittest.main()

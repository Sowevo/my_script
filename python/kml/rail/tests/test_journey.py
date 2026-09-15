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


if __name__ == '__main__':
    unittest.main()

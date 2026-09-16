"""分段行程：换乘保留前段，每段独立记录轨道。"""

from copy import deepcopy
import math

PASSENGER_ROUTES = {'train', 'subway', 'light_rail', 'monorail', 'tram'}


class JourneyExplorer:
    def __init__(self, ways, node_to_ways, metadata):
        self.ways = ways
        self.node_to_ways = node_to_ways
        self.metadata = metadata

    def connected(self, wid):
        neighbors = set()
        for node in self.ways[wid]:
            neighbors.update(self.node_to_ways.get(node, ()))
        neighbors.discard(wid)
        return neighbors

    def choices(self, leg):
        current = leg['current_way']
        last = leg['path'][-1]
        if self.loop_closed(leg):
            return [], '前进端已接回本段走过的轨迹，本段结束。'
        if 'span' in last:
            start, end = last['span']
            terminal = len(self.ways[current]) - 1 if end > start else 0
            if abs(end - terminal) > 1e-9:
                return [current], '可继续当前轨道剩余部分，或开始下一段。'
        visited = {item['way_id'] for item in leg['path']}
        neighbors = self.connected(current)
        if 'span' in last:
            if leg.get('directed'):
                node = self.ways[current][round(last['span'][1])]
                neighbors = {wid for wid in self.node_to_ways.get(node, ())
                             if node in (self.ways[wid][0], self.ways[wid][-1])}
            else:
                low, high = sorted(last['span'])
                nodes = self.ways[current][math.ceil(low):math.floor(high) + 1]
                neighbors = {wid for node in nodes for wid in self.node_to_ways.get(node, ())}
        choices = sorted(neighbors - visited)
        return choices, '' if choices else '本段没有更多相连轨道，可搜索轨道开始下一段。'

    def loop_closed(self, leg):
        path = leg['path']
        item = path[-1]
        nodes = self.ways[item['way_id']]
        span = item.get('span')
        if span is None:
            if len(path) < 2:
                return nodes[0] == nodes[-1] and len(nodes) > 2
            previous = path[-2]
            previous_nodes = self.ways[previous['way_id']]
            if 'span' in previous:
                position = previous['span'][1]
                if not float(position).is_integer():
                    return False
                shared = {previous_nodes[int(position)]} & {nodes[0], nodes[-1]}
            else:
                shared = set(previous_nodes) & {nodes[0], nodes[-1]}
            if not shared:
                return False
            if len(shared) == 2:
                return True
            span = [0, len(nodes) - 1] if nodes[0] in shared else [len(nodes) - 1, 0]
        start, end = span
        if not float(end).is_integer():
            return False
        exit_node = nodes[int(end)]
        for earlier in path[:-1]:
            old_nodes = self.ways[earlier['way_id']]
            low, high = sorted(earlier.get('span', [0, len(old_nodes) - 1]))
            if exit_node in old_nodes[math.ceil(low):math.floor(high) + 1]:
                return True
        # 一条闭合 way 或同 way 内回到已走过的节点，也只走到闭合为止。
        low, high = sorted((start, end))
        indices = range(math.ceil(low), math.floor(high) + 1)
        return any(i != int(end) and nodes[i] == exit_node for i in indices)

    def advance(self, legs, wid, *, reset=False, transfer=False,
                transfer_label='', max_steps=20):
        if wid not in self.ways:
            raise ValueError('当前地图中没有这个轨道ID。')
        if reset and transfer:
            raise ValueError('不能同时重新开始和添加换乘。')
        updated = deepcopy(legs)
        if transfer and not updated:
            raise ValueError('请先开始第一段行程，再添加换乘。')
        if reset:
            updated = []
        new_leg = transfer or not updated
        if new_leg:
            tags = self.metadata.get(wid, {}).get('tags', {})
            leg = {'name': tags.get('name') or '未命名轨道', 'start_way': wid,
                   'current_way': wid, 'path': [],
                   'transfer_label': transfer_label if transfer else ''}
            updated.append(leg)
        else:
            leg = updated[-1]
            allowed, _ = self.choices(leg)
            if wid not in allowed:
                raise ValueError('请选择当前可选轨道；不相连的轨道请通过添加换乘进入。')
        travelled = []
        for step in range(max_steps):
            last = leg['path'][-1] if leg['path'] else None
            item = {'way_id': wid, 'type': 'manual' if step == 0 else 'auto'}
            if last and last['way_id'] == wid and 'span' in last:
                start, end = last['span']
                terminal = len(self.ways[wid]) - 1 if end > start else 0
                item['span'] = [end, terminal]
            elif last and leg.get('directed'):
                node = self.ways[last['way_id']][round(last['span'][1])]
                end = len(self.ways[wid]) - 1
                item['span'] = [0, end] if self.ways[wid][0] == node else [end, 0]
            leg['current_way'] = wid
            leg['path'].append(item)
            travelled.append(wid)
            choices, stop_reason = self.choices(leg)
            if len(choices) != 1 or step == max_steps - 1:
                break
            wid = choices[0]
        return updated, {'current_way': leg['current_way'], 'choices': choices,
                         'path': travelled, 'visited_path': travelled, 'stop_reason': stop_reason}

    def forward_way(self, legs, wid=None):
        if not legs:
            raise ValueError('请先选择起始轨道。')
        choices, _ = self.choices(legs[-1])
        if wid is None:
            if len(choices) != 1:
                raise ValueError('仅有一条可选相连轨道时才能前进一条。')
            wid = choices[0]
        elif wid not in choices:
            raise ValueError('请选择当前可选的相连轨道。')
        return self.advance(legs, wid, max_steps=1)

    def undo_way(self, legs):
        updated = deepcopy(legs)
        if updated:
            last = updated[-1]['path'].pop()
            if 'trim_restore' in last:
                updated[-1] = last['trim_restore']['leg']
            elif 'cut_restore' in last:
                updated[-1]['path'].extend(last['cut_restore'])
            if not updated[-1]['path']:
                updated.pop()
        if updated:
            leg = updated[-1]
            leg['current_way'] = leg['path'][-1]['way_id']
            choices, reason = self.choices(leg)
        else:
            choices, reason = [], ''
        return updated, {'current_way': updated[-1]['current_way'] if updated else None,
                         'choices': choices, 'path': [], 'visited_path': [],
                         'stop_reason': reason}

"""分段行程：换乘保留前段，每段独立记录轨道。"""

from copy import deepcopy

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
        visited = {item['way_id'] for item in leg['path']}
        choices = sorted(self.connected(current) - visited)
        return choices, '' if choices else '本段没有更多相连轨道，可搜索轨道开始下一段。'

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
            leg['current_way'] = wid
            leg['path'].append({'way_id': wid, 'type': 'manual' if step == 0 else 'auto'})
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
            updated[-1]['path'].pop()
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

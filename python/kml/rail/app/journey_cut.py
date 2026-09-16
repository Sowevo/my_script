"""按当前行程方向截断轨道；区间使用原始 way 的节点序号及小数位置。"""

from copy import deepcopy
import hashlib
import json
import math

from stations import distance


def revision(legs):
    return hashlib.sha256(json.dumps(legs, sort_keys=True).encode()).hexdigest()


def interpolate(points, position):
    index = min(int(position), len(points) - 2)
    fraction = position - index
    return [points[index][axis] + fraction * (points[index + 1][axis] - points[index][axis])
            for axis in (0, 1)]


def slice_coords(points, start, end):
    if len(points) < 2 or abs(start - end) < 1e-9:
        return []
    low, high = sorted((start, end))
    result = [interpolate(points, low)]
    result.extend(points[i] for i in range(math.floor(low) + 1, math.ceil(high)))
    result.append(interpolate(points, high))
    return result if start < end else result[::-1]


class JourneyCut:
    MAX_DISTANCE = 150
    SNAP_DISTANCE = 25

    def __init__(self, ways, coords, features):
        self.ways, self.coords = ways, coords
        self.stops = {key[1] for key, feature in features.items()
                      if key[0] == 'n' and feature.get('stop_position')}

    def raw_coords(self, item):
        return [self.coords[n] for n in self.ways[item['way_id']] if n in self.coords]

    def item_coords(self, item):
        points = self.raw_coords(item)
        return slice_coords(points, *item['span']) if 'span' in item else points

    def start_preview(self, wid, point=None):
        if wid not in self.ways:
            raise ValueError('请选择有效的起始轨道。')
        points = self.raw_coords({'way_id': wid})
        if len(points) < 2 or len(points) != len(self.ways[wid]):
            raise ValueError('这条轨道缺少完整坐标，无法选择起点。')
        if point is None:
            end = len(points) - 1
            return {'point': None, 'snapped': False, 'directions': [
                {'id': 0, 'span': [end, 0], 'coords': points[::-1]},
                {'id': 1, 'span': [0, end], 'coords': points}]}
        cosine = math.cos(math.radians(point[0]))
        projections = []
        for i, (a, b) in enumerate(zip(points, points[1:])):
            dx, dy = (b[1] - a[1]) * cosine, b[0] - a[0]
            length = dx * dx + dy * dy
            if not length:
                continue
            fraction = max(0, min(1, ((point[1] - a[1]) * cosine * dx + (point[0] - a[0]) * dy) / length))
            position = i + fraction
            projections.append((distance(point, interpolate(points, position)), position))
        if not projections or min(projections)[0] > self.MAX_DISTANCE:
            raise ValueError('请在已选轨道上点击起点（距离不超过 150 米）。')
        _, position = min(projections)
        stops = [(distance(interpolate(points, position), self.coords[n]), i)
                 for i, n in enumerate(self.ways[wid]) if n in self.stops]
        snapped = bool(stops and min(stops)[0] <= self.SNAP_DISTANCE)
        if snapped:
            position = min(stops)[1]
        directions = [{'id': i, 'span': [position, end], 'coords': slice_coords(points, position, end)}
                      for i, end in enumerate((0, len(points) - 1)) if abs(position - end) > 1e-9]
        return {'point': interpolate(points, position), 'directions': directions, 'snapped': snapped}

    def directions(self, path, index):
        item = path[index]
        if 'span' in item:
            return [item['span']]
        nodes = self.ways[item['way_id']]
        end = len(nodes) - 1
        # 优先根据已走过的前一条确定进入端；单条或环路方向不明时交由用户选择。
        if index:
            previous = path[index - 1]
            previous_points = self.item_coords(previous)
            if 'span' in previous:
                shared = {n for n in (nodes[0], nodes[-1])
                          if self.coords.get(n) and distance(self.coords[n], previous_points[-1]) < .1}
            else:
                shared = {nodes[0], nodes[-1]} & set(self.ways[previous['way_id']])
            if len(shared) == 1 and nodes[0] != nodes[-1]:
                return [[0, end]] if nodes[0] in shared else [[end, 0]]
        if index + 1 < len(path):
            shared = {nodes[0], nodes[-1]} & set(self.ways[path[index + 1]['way_id']])
            if len(shared) == 1 and nodes[0] != nodes[-1]:
                return [[end, 0]] if nodes[0] in shared else [[0, end]]
        return [[0, end], [end, 0]]

    def preview(self, legs, point):
        if not legs:
            raise ValueError('请先选择轨道。')
        path = legs[-1]['path']
        index = len(path) - 1
        item = path[index]
        points = self.raw_coords(item)
        if len(points) < 2 or len(points) != len(self.ways[item['way_id']]):
            raise ValueError('最后一条轨道缺少完整坐标。')
        spans = self.directions(path, index)
        if len(spans) != 1:
            raise ValueError('尚未确定行进方向，请先用“从此开始本段”选择起点和方向。')
        start, end = spans[0]
        low, high = sorted((start, end))
        cosine = math.cos(math.radians(point[0]))
        projections = []
        for segment in range(math.floor(low), min(math.ceil(high), len(points) - 1)):
            a, b = points[segment:segment + 2]
            dx, dy = (b[1] - a[1]) * cosine, b[0] - a[0]
            length = dx * dx + dy * dy
            if not length:
                continue
            t = ((point[1] - a[1]) * cosine * dx + (point[0] - a[0]) * dy) / length
            position = max(low, min(high, segment + max(0, min(1, t))))
            projections.append((distance(point, interpolate(points, position)), position))
        if not projections or min(projections)[0] > self.MAX_DISTANCE:
            raise ValueError('点击位置距最后一条轨道超过 150 米；若要结束在更早的轨道，请先退回。')
        metres, position = min(projections)
        stops = [(distance(interpolate(points, position), self.coords[n]), i)
                 for i, n in enumerate(self.ways[item['way_id']])
                 if n in self.stops and low <= i <= high]
        snapped = bool(stops and min(stops)[0] <= self.SNAP_DISTANCE)
        if snapped:
            position = min(stops)[1]
        if abs(position - start) < 1e-9:
            raise ValueError('终点落在这条轨道的起点，请用“退回一步”移除整条轨道。')
        if abs(position - end) < 1e-9:
            raise ValueError('此处已经是本段终点。')
        return {'revision': revision(legs), 'candidates': [{
            'id': 0, 'path_index': index, 'way_id': item['way_id'], 'side': 'end',
            'span': [start, position], 'point': interpolate(points, position),
            'removed': [slice_coords(points, position, end)],
            'snapped': snapped, 'distance': round(metres, 1)}]}

    def apply(self, legs, candidate):
        updated = deepcopy(legs)
        leg = updated[-1]
        index = candidate['path_index']
        original = deepcopy(leg)
        item = leg['path'][index]
        item['span'] = candidate['span']
        side = candidate.get('side', 'end')
        leg['path'] = leg['path'][index:] if side == 'start' else leg['path'][:index + 1]
        leg['start_way'] = leg['path'][0]['way_id']
        leg['current_way'] = leg['path'][-1]['way_id']
        # 撤销标记放在操作结束处；后来添加的轨道先逐条退回，再恢复整个修剪操作。
        leg['path'][-1]['trim_restore'] = {'leg': original, 'side': side,
                                         'index': index, 'span': candidate['span']}
        return updated

    def undo_preview(self, legs):
        if not legs:
            return {'kind': 'way', 'coords': []}
        item = legs[-1]['path'][-1]
        if 'trim_restore' in item:
            saved = item['trim_restore']
            original = saved['leg']['path']
            if saved['side'] == 'restart':
                return {'kind': 'cut', 'side': 'start',
                        'coords': [self.item_coords(i) for i in original]}
            index = saved['index']
            target = original[index]
            spans = self.directions(original, index)
            span = saved['span']
            forward = span[1] > span[0]
            start, end = next((s for s in spans if (s[1] > s[0]) == forward), spans[0])
            if saved['side'] == 'start':
                lines = [self.item_coords(i) for i in original[:index]]
                lines.append(slice_coords(self.raw_coords(target), start, span[0]))
            else:
                lines = [slice_coords(self.raw_coords(target), span[1], end)]
                lines.extend(self.item_coords(i) for i in original[index + 1:])
            return {'kind': 'cut', 'side': saved['side'], 'coords': [line for line in lines if len(line) >= 2]}
        if 'cut_restore' not in item:
            return {'kind': 'way', 'coords': [self.item_coords(item)]}
        original = item['cut_restore']
        end = original[0].get('span', self.directions(original, 0)[0])[1]
        # 截断前单条轨道没有方向时，沿已确认的截断方向恢复剩余区间。
        if 'span' not in original[0]:
            end = len(self.ways[item['way_id']]) - 1 if item['span'][1] > item['span'][0] else 0
        lines = [slice_coords(self.raw_coords(item), item['span'][1], end)]
        lines.extend(self.item_coords(i) for i in original[1:])
        return {'kind': 'cut', 'coords': [line for line in lines if len(line) >= 2]}

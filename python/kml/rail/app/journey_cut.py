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
        cosine = math.cos(math.radians(point[0]))
        projections = []
        for index, item in enumerate(path):
            points = self.raw_coords(item)
            if len(points) < 2 or len(points) != len(self.ways[item['way_id']]):
                continue
            low, high = sorted(self.directions(path, index)[0])
            for segment in range(math.floor(low), min(math.ceil(high), len(points) - 1)):
                a, b = points[segment:segment + 2]
                dx, dy = (b[1] - a[1]) * cosine, b[0] - a[0]
                length = dx * dx + dy * dy
                if not length:
                    continue
                t = ((point[1] - a[1]) * cosine * dx + (point[0] - a[0]) * dy) / length
                position = max(low, min(high, segment + max(0, min(1, t))))
                projections.append((distance(point, interpolate(points, position)), index, position))
        if not projections or min(projections)[0] > self.MAX_DISTANCE:
            raise ValueError('点击位置距本段已选轨道超过 150 米，请靠近本段轨迹选择终点。')
        # 等距时选择较早的经过位置，连接点优先落在前一条的末端。
        metres, index, position = min(projections)
        item = path[index]
        points = self.raw_coords(item)
        spans = self.directions(path, index)
        if len(spans) != 1:
            raise ValueError('尚未确定行进方向，请先用“从此开始本段”选择起点和方向。')
        start, end = spans[0]
        low, high = sorted((start, end))
        stops = [(distance(interpolate(points, position), self.coords[n]), i)
                 for i, n in enumerate(self.ways[item['way_id']])
                 if n in self.stops and low <= i <= high]
        snapped = bool(stops and min(stops)[0] <= self.SNAP_DISTANCE)
        if snapped:
            position = min(stops)[1]
        if abs(position - start) < 1e-9 and index:
            previous_points = self.raw_coords(path[index - 1])
            previous_spans = self.directions(path, index - 1)
            if (len(previous_spans) == 1 and
                    distance(interpolate(previous_points, previous_spans[0][1]),
                             interpolate(points, position)) < .1):
                index -= 1
                item, points = path[index], previous_points
                start, end = previous_spans[0]
                position = end
        if abs(position - start) < 1e-9:
            raise ValueError('终点落在本段起点，请用“退回一条轨道”缩短行程。')
        if abs(position - end) < 1e-9 and index == len(path) - 1:
            raise ValueError('此处已经是本段终点。')
        return {'revision': revision(legs), 'candidates': [{
            'id': 0, 'path_index': index, 'way_id': item['way_id'], 'side': 'end',
            'span': [start, position], 'point': interpolate(points, position),
            'removed': [line for line in [slice_coords(points, position, end)] +
                        [self.item_coords(i) for i in path[index + 1:]] if len(line) >= 2],
            'snapped': snapped, 'distance': round(metres, 1)}]}

    def apply(self, legs, candidate):
        updated = deepcopy(legs)
        leg = updated[-1]
        index = candidate['path_index']
        item = leg['path'][index]
        item['span'] = candidate['span']
        side = candidate.get('side', 'end')
        leg['path'] = leg['path'][index:] if side == 'start' else leg['path'][:index + 1]
        leg['start_way'] = leg['path'][0]['way_id']
        leg['current_way'] = leg['path'][-1]['way_id']
        return updated

    def undo_preview(self, legs):
        if not legs:
            return {'kind': 'way', 'coords': []}
        item = legs[-1]['path'][-1]
        return {'kind': 'way', 'coords': [self.item_coords(item)]}

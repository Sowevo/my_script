"""根据共享节点和连接处方向推荐接续轨道，不改变可选轨道集合。"""

import math


def _outward(nodes, index, step, coords):
    """从连接点沿轨道取约30米的方向；缺失坐标时不跨越缺口。"""
    origin = coords.get(nodes[index])
    if origin is None:
        return None
    scale = 111195
    longitude_scale = scale * math.cos(math.radians(origin[0]))
    previous = origin
    remaining = 30.0
    vector = None
    for i in range(index + step, len(nodes) if step > 0 else -1, step):
        point = coords.get(nodes[i])
        if point is None:
            break
        dx = (point[1] - previous[1]) * longitude_scale
        dy = (point[0] - previous[0]) * scale
        length = math.hypot(dx, dy)
        fraction = min(1, remaining / length) if length else 1
        end = (previous[0] + (point[0] - previous[0]) * fraction,
               previous[1] + (point[1] - previous[1]) * fraction)
        vector = ((end[1] - origin[1]) * longitude_scale,
                  (end[0] - origin[0]) * scale)
        remaining -= length
        if remaining <= 0:
            break
        previous = point
    if vector and math.hypot(*vector) > 0:
        return vector
    return None


def recommend_way(path, choices, ways, coords, metadata):
    if len(path) < 2:
        return None
    nodes = ways.get(path[-1]['way_id'], [])
    previous = set(ways.get(path[-2]['way_id'], []))
    entries = [i for i, node in enumerate(nodes) if node in previous]
    # 中途进入、闭环或多个共享节点时，方向不明确，暂不标星。
    if len(nodes) < 2 or len(entries) != 1 or entries[0] not in (0, len(nodes) - 1):
        return None
    entry = entries[0]
    direction = 1 if entry == 0 else -1
    exit_index = len(nodes) - 1 if direction == 1 else 0
    tags = metadata.get(path[-1]['way_id'], {}).get('tags', {})
    service_tracks = {'yard', 'siding', 'spur', 'crossover'}
    ranked = []
    for wid in choices:
        candidate = ways.get(wid, [])
        # 多个共享节点可能意味着重叠轨道，无法确定唯一接续点。
        if len(set(candidate) & set(nodes)) != 1:
            continue
        candidate_tags = metadata.get(wid, {}).get('tags', {})
        scores = []
        for i, node in enumerate(nodes):
            if (i - entry) * direction <= 0:
                continue
            backward = _outward(nodes, i, -direction, coords)
            if backward is None:
                continue
            incoming = (-backward[0], -backward[1])
            for j, candidate_node in enumerate(candidate):
                if candidate_node != node:
                    continue
                for step in (-1, 1):
                    outgoing = _outward(candidate, j, step, coords)
                    if outgoing is None:
                        continue
                    cosine = sum(a*b for a, b in zip(incoming, outgoing)) / (
                        math.hypot(*incoming) * math.hypot(*outgoing))
                    if cosine <= 0:
                        continue
                    angle = math.acos(max(-1, min(1, cosine)))
                    leaves_main = (tags.get('service') not in service_tracks
                                   and candidate_tags.get('service') in service_tracks)
                    same_name = bool(tags.get('name')) and tags['name'] == candidate_tags.get('name')
                    scores.append((i != exit_index, leaves_main, not same_name, angle))
        if scores:
            ranked.append((min(scores), wid))
    ranked.sort()
    if not ranked:
        return None
    if len(ranked) > 1:
        first, second = ranked[0][0], ranked[1][0]
        if first[:3] == second[:3] and abs(first[3] - second[3]) < 1e-6:
            return None
    return ranked[0][1]

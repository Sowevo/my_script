"""地图车站目录：stop_area 去重，按可视范围返回车站点。"""

import math
import re

from station_index import RAIL_MODES, name


class StationLines:
    """只依据站点/站台成员关联运行线路，不按附近轨道猜测。"""

    def __init__(self, features, relations):
        self.members = {}
        self.lines = {}
        masters = {}
        for rid, relation in relations.items():
            tags = relation['tags']
            if tags.get('type') == 'route_master' and tags.get('route_master') in RAIL_MODES:
                for member in relation['members']:
                    if member['type'] == 'r':
                        masters.setdefault(member['ref'], []).append((rid, tags))
        for rid, relation in relations.items():
            tags = relation['tags']
            if tags.get('type') != 'route' or tags.get('route') not in RAIL_MODES:
                continue
            parents = masters.get(rid, [])
            source = {**tags, **parents[0][1]} if len(parents) == 1 else tags
            label = name(source)
            # 仅去掉明确的方向/端点括注，保留名称里的其他限定信息。
            label = re.sub(r'\s*[（(][^()（）]*(?:→|↔|=>|内回り|外回り|上り|下り)[^()（）]*[）)]', '', label).strip()
            operator = source.get('operator', '')
            ref = source.get('ref', '')
            if not label:
                label = ref
            if not label:
                continue
            identity = (tags['route'], operator or source.get('network', ''), ref or label)
            # 同运营方、同模式、同编号的方向和运行种别合并，优先总关系名称。
            if identity not in self.lines or len(parents) == 1:
                self.lines[identity] = {'name': label, 'operator': operator}
            for member in relation['members']:
                key = (member['type'], member['ref'])
                if key in features and (member.get('role', '').split('_')[0] in {'stop', 'platform'}
                                        or features[key].get('station_node')
                                        or features[key].get('stop_position')):
                    self.members.setdefault(key, set()).add(identity)

    def get(self, keys):
        ids = {identity for key in keys for identity in self.members.get(key, ())}
        return sorted((self.lines[identity] for identity in ids),
                      key=lambda line: (line['operator'], line['name']))


class StationMap:
    """仅显示明确标记的车站；同一 stop_area 一个点，其他车站独立显示。"""
    CELL = 0.05

    def __init__(self, features, relations=None):
        self.stations = {}
        self.cells = {}
        lines = StationLines(features, relations or {})
        groups = {}
        members = {}
        for key, feature in features.items():
            area = feature.get('stop_area')
            identity = f'relation/{area}' if area else f"{ {'n':'node', 'w':'way', 'r':'relation'}[key[0]]}/{key[1]}"
            members.setdefault(identity, []).append(key)
            if feature.get('station_node') and feature.get('rail') and not feature.get('bus_only'):
                groups.setdefault(identity, []).append((key, feature))
        for identity, candidates in groups.items():
            # 优先使用车站节点，其次使用车站 way 的代表坐标。
            key, feature = min(candidates, key=lambda item: (item[0][0] != 'n', item[0]))
            lat, lon = feature['coords']
            station = {'id': identity, 'name': feature['name'] or '未命名车站',
                       'lat': lat, 'lon': lon, 'lines': lines.get(members[identity])}
            self.stations[identity] = station
            self.cells.setdefault((math.floor(lat / self.CELL), math.floor(lon / self.CELL)), []).append(station)

    def query(self, south, west, north, east, limit=500):
        found = []
        for lat_cell in range(math.floor(south / self.CELL), math.floor(north / self.CELL) + 1):
            for lon_cell in range(math.floor(west / self.CELL), math.floor(east / self.CELL) + 1):
                found.extend(s for s in self.cells.get((lat_cell, lon_cell), ())
                             if south <= s['lat'] <= north and west <= s['lon'] <= east)
        lat, lon = (south + north) / 2, (west + east) / 2
        found.sort(key=lambda s: ((s['lat'] - lat)**2 + ((s['lon'] - lon)*math.cos(math.radians(lat)))**2, s['id']))
        return {'stations': found[:limit], 'truncated': len(found) > limit}

"""地图车站目录：stop_area 去重，按可视范围返回建筑轮廓。"""

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
    CELL = 0.05

    def __init__(self, features, relations=None):
        self.stations = {}
        self.cells = {}
        lines = StationLines(features, relations or {})
        feature_keys = {id(feature): key for key, feature in features.items()}
        areas = {}
        for key, feature in features.items():
            if feature.get('stop_area'):
                areas.setdefault(feature['stop_area'], []).append((key, feature))
        represented_buildings = set()
        for area_id, members in areas.items():
            station_nodes = [f for key, f in members if key[0] == 'n' and f.get('station_node')]
            stops = [f for key, f in members if key[0] == 'n' and f.get('stop_position')]
            points = station_nodes or stops or [f for _, f in members]
            building_ids = {f['station_building'] for _, f in members if f.get('station_building')}
            building_ids.update(key[1] for key, f in members if key[0] == 'w' and f.get('building_polygon'))
            represented_buildings.update(building_ids)
            area_features = [(key, f) for key, f in members if f.get('station_polygon')]
            station_areas = [(key, f) for key, f in area_features if f['area_kind'] == '车站范围']
            selected = station_areas or area_features
            polygons = [f['station_polygon'] for _, f in selected]
            outline_kind = '车站范围' if station_areas else '站台范围'
            if not polygons:
                polygons = [features[('w', bid)]['building_polygon'] for bid in sorted(building_ids)
                            if features.get(('w', bid), {}).get('building_polygon')]
                outline_kind = '车站建筑'
            self.add(f'relation/{area_id}', points[0]['name'], points, '车站', polygons, outline_kind)
            station_lines = lines.get(key for key, _ in members)
            labels = []
            for key, feature in selected:
                direct = lines.get([key]) if feature['area_kind'] == '站台范围' else []
                labels.append({'lines': direct or station_lines,
                               'scope': 'platform' if direct else 'station'})
            self.stations[f'relation/{area_id}']['polygon_labels'] = labels or [
                {'lines': station_lines, 'scope': 'station'} for _ in polygons]
        standalone = {}
        for key, feature in features.items():
            if feature.get('stop_area'):
                continue
            if feature.get('station_polygon'):
                identity = f'way/{key[1]}'
                platform = feature['area_kind'] == '站台范围'
                fallback = (f"{feature['ref']} 号站台" if feature.get('ref') else '未命名站台') if platform else '未命名车站'
                self.add(identity, feature['name'] or fallback, [feature],
                         '站台' if platform else '车站', [feature['station_polygon']], feature['area_kind'])
                self.stations[identity]['polygon_labels'] = [
                    {'lines': lines.get([key]), 'scope': 'platform' if platform else 'station'}]
                continue
            building_id = key[1] if feature.get('building_polygon') else feature.get('station_building')
            if building_id in represented_buildings:
                continue
            if feature.get('station_node'):
                identity = f'way/{building_id}' if building_id else f'node/{key[1]}'
                standalone.setdefault(identity, []).append(feature)
            elif feature.get('building_polygon'):
                standalone.setdefault(f'way/{key[1]}', []).append(feature)
        for identity, members in standalone.items():
            points = [f for f in members if f.get('station_node')] or members
            polygons = [f['building_polygon'] for f in members if f.get('building_polygon')]
            self.add(identity, points[0]['name'], points, '车站' if points[0].get('station_node') else '车站建筑', polygons)
            station_lines = lines.get(feature_keys[id(f)] for f in members)
            self.stations[identity]['polygon_labels'] = [
                {'lines': station_lines, 'scope': 'station'} for _ in polygons]

        # 建筑跨越视野边缘时，即使站点代表坐标在视野外也应返回轮廓。
        for station in self.stations.values():
            points = [point for polygon in station['polygons'] for point in polygon]
            if not points:
                continue
            south, north = min(p[0] for p in points), max(p[0] for p in points)
            west, east = min(p[1] for p in points), max(p[1] for p in points)
            station['bounds'] = (south, west, north, east)
            for lat in range(math.floor(south / self.CELL), math.floor(north / self.CELL) + 1):
                for lon in range(math.floor(west / self.CELL), math.floor(east / self.CELL) + 1):
                    self.cells.setdefault((lat, lon), []).append(station)

    def add(self, identity, name, points, kind, polygons, outline_kind='车站建筑'):
        lat, lon = (sum(f['coords'][axis] for f in points) / len(points) for axis in (0, 1))
        station = {'id': identity, 'name': name, 'lat': lat, 'lon': lon,
                   'kind': kind, 'has_building': bool(polygons) and outline_kind == '车站建筑',
                   'polygons': polygons, 'outline_kind': outline_kind}
        self.stations[identity] = station

    def query(self, south, west, north, east, limit=500):
        found = {}
        for lat_cell in range(math.floor(south / self.CELL), math.floor(north / self.CELL) + 1):
            for lon_cell in range(math.floor(west / self.CELL), math.floor(east / self.CELL) + 1):
                for station in self.cells.get((lat_cell, lon_cell), ()):
                    a, b, c, d = station['bounds']
                    if a <= north and c >= south and b <= east and d >= west:
                        found[station['id']] = station
        # 达到上限时优先显示视野中心附近的车站。
        lat, lon = (south + north) / 2, (west + east) / 2
        found = sorted(found.values(), key=lambda s: ((s['lat'] - lat) ** 2 + ((s['lon'] - lon) * math.cos(math.radians(lat))) ** 2, s['id']))
        return {'stations': [{key: station[key] for key in ('id', 'name', 'polygons', 'outline_kind', 'polygon_labels')}
                             for station in found[:limit]], 'truncated': len(found) > limit}

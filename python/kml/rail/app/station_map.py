"""地图车站目录：stop_area 去重，按可视范围返回建筑轮廓。"""

import math


class StationMap:
    CELL = 0.05

    def __init__(self, features):
        self.stations = {}
        self.cells = {}
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
            area_features = [f for _, f in members if f.get('station_polygon')]
            station_areas = [f for f in area_features if f['area_kind'] == '车站范围']
            polygons = [f['station_polygon'] for f in (station_areas or area_features)]
            outline_kind = '车站范围' if station_areas else '站台范围'
            if not polygons:
                polygons = [features[('w', bid)]['building_polygon'] for bid in sorted(building_ids)
                            if features.get(('w', bid), {}).get('building_polygon')]
                outline_kind = '车站建筑'
            self.add(f'relation/{area_id}', points[0]['name'], points, '车站', polygons, outline_kind)
        standalone = {}
        for key, feature in features.items():
            if feature.get('stop_area'):
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
        return {'stations': [{key: station[key] for key in ('id', 'name', 'polygons', 'outline_kind')}
                             for station in found[:limit]], 'truncated': len(found) > limit}

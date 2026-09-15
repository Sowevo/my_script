"""查询本地轨道几何及所属OSM关系，不依赖在线服务。"""

import math
from journey import PASSENGER_ROUTES


class NearbyIndex:
    def __init__(self, ways, coords, metadata, relations):
        self.ways, self.coords = ways, coords
        self.metadata, self.relations = metadata, relations
        self.bounds = []
        for wid, nodes in ways.items():
            points = [coords[n] for n in nodes if n in coords]
            if points:
                lat, lon = zip(*points)
                self.bounds.append((wid, min(lat), max(lat), min(lon), max(lon)))
        self.parents = {}
        for rid, relation in relations.items():
            for member in relation['members']:
                self.parents.setdefault((member['type'], member['ref']), set()).add(rid)

    def parent_relations(self, way_ids):
        found = set()
        pending = [('w', wid) for wid in way_ids]
        while pending:
            for rid in self.parents.get(pending.pop(), ()):
                if rid not in found:
                    found.add(rid)
                    pending.append(('r', rid))
        return sorted(found)

    def distance(self, wid, lat, lon):
        scale = 111195
        longitude_scale = scale * math.cos(math.radians(lat))
        best = float('inf')
        previous = None
        for node in self.ways[wid]:
            point = self.coords.get(node)
            if point is None:
                previous = None
                continue
            current = (((point[1] - lon + 180) % 360 - 180) * longitude_scale,
                       (point[0] - lat) * scale)
            best = min(best, math.hypot(*current))
            if previous is not None:
                x, y = previous
                dx, dy = current[0] - x, current[1] - y
                length = dx * dx + dy * dy
                t = max(0, min(1, -(x * dx + y * dy) / length)) if length else 0
                best = min(best, math.hypot(x + t * dx, y + t * dy))
            previous = current
        return best

    def summary(self, kind, element_id):
        meta = self.metadata[element_id] if kind == 'way' else self.relations[element_id]
        tags = meta.get('tags', {})
        return {'type': kind, 'id': element_id, 'name': tags.get('name', '未命名'),
                'display_name': tags.get('name:zh') or tags.get('name:ja') or tags.get('name', '未命名'),
                'followable': tags.get('type') == 'route' and tags.get('route') in PASSENGER_ROUTES,
                'railway': tags.get('railway', ''), 'relation_type': tags.get('type', ''),
                'route': tags.get('route', ''), 'ref': tags.get('ref', ''),
                'from': tags.get('from', ''), 'to': tags.get('to', ''),
                'roundtrip': tags.get('roundtrip') == 'yes'}

    def memberships(self, kind, element_id):
        member_type = 'w' if kind == 'way' else 'r'
        result = []
        for rid in self.parents.get((member_type, element_id), ()):
            if kind == 'relation' and rid == element_id:
                continue
            roles = list(dict.fromkeys(member['role'] for member in self.relations[rid]['members']
                                       if member['type'] == member_type and member['ref'] == element_id))
            result.append({**self.summary('relation', rid), 'roles': roles})
        return sorted(result, key=lambda item: (item['relation_type'] != 'route', item['id']))

    def query(self, lat, lon, radius, limit=50):
        dy = radius / 111195
        dx = dy / max(math.cos(math.radians(lat)), 1e-6)
        hits = []
        for wid, south, north, west, east in self.bounds:
            if south > lat + dy or north < lat - dy:
                continue
            if not any(west <= lon + shift + dx and east >= lon + shift - dx
                       for shift in (-360, 0, 360)):
                continue
            distance = self.distance(wid, lat, lon)
            if distance <= radius:
                hits.append((distance, wid))
        hits.sort()
        # 关系按所有命中轨道收集，不受轨道列表数量上限影响。
        relations = self.parent_relations(wid for _, wid in hits)
        return {'ways': [{**self.summary('way', wid), 'distance': round(distance, 1)}
                         for distance, wid in hits[:limit]],
                'relations': [self.summary('relation', rid) for rid in relations],
                'total': len(hits), 'radius': radius}

    def detail(self, kind, element_id):
        result = self.summary(kind, element_id)
        meta = self.metadata[element_id] if kind == 'way' else self.relations[element_id]
        way_ids = []
        if kind == 'way':
            way_ids.append(element_id)
        else:
            visited = set()
            pending = [element_id]
            while pending:
                rid = pending.pop()
                if rid in visited or rid not in self.relations:
                    continue
                visited.add(rid)
                for member in self.relations[rid]['members']:
                    if member['type'] == 'w' and member['ref'] in self.ways:
                        way_ids.append(member['ref'])
                    elif member['type'] == 'r':
                        pending.append(member['ref'])
        way_ids = list(dict.fromkeys(way_ids))
        geometry = []
        for wid in way_ids:
            line = []
            for node in self.ways[wid]:
                if node in self.coords:
                    line.append(self.coords[node])
                else:
                    if len(line) > 1:
                        geometry.append(line)
                    line = []
            if len(line) > 1:
                geometry.append(line)
        result.update(tags=meta.get('tags', {}), geometry=geometry,
                      memberships=self.memberships(kind, element_id),
                      members=[{**member, 'available':
                                (member['type'] == 'w' and member['ref'] in self.ways) or
                                (member['type'] == 'r' and member['ref'] in self.relations)}
                               for member in meta.get('members', [])],
                      ways=[self.summary('way', wid) for wid in way_ids])
        return result

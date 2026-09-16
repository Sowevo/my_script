"""收录停车点、车站、站台及 stop_area / route 关联。"""

from pathlib import Path
import pickle
import os
import math
import osmium

RAIL_MODES = {"train", "subway", "light_rail", "monorail", "tram"}


def name(tags):
    return tags.get("name") or tags.get("name:zh") or tags.get("name:ja") or tags.get("name:en", "")


def is_rail(tags):
    return (tags.get('building') == 'train_station'
            or tags.get("railway") in {"station", "halt", "stop", "tram_stop", "platform"}
            or any(tags.get(mode) == "yes" for mode in RAIL_MODES))


def inside(point, polygon):
    lat, lon = point
    result = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if (a[0] > lat) != (b[0] > lat):
            crossing = (b[1] - a[1]) * (lat - a[0]) / (b[0] - a[0]) + a[1]
            if lon < crossing:
                result = not result
    return result


def assign_building_names(features):
    # 只将落在车站建筑内部的停车点/站台关联到建筑，不按“最近建筑”猜测。
    cells = {}
    for key, building in features.items():
        polygon = building.get('building_polygon', [])
        if not polygon or not building['name']:
            continue
        south, north = min(p[0] for p in polygon), max(p[0] for p in polygon)
        west, east = min(p[1] for p in polygon), max(p[1] for p in polygon)
        for lat in range(math.floor(south * 100), math.floor(north * 100) + 1):
            for lon in range(math.floor(west * 100), math.floor(east * 100) + 1):
                cells.setdefault((lat, lon), []).append((key, building))
    for feature in features.values():
        if not feature['rail'] or 'coords' not in feature or feature.get('building_polygon'):
            continue
        point = feature['coords']
        matches = [(key, building) for key, building in cells.get(
            (math.floor(point[0] * 100), math.floor(point[1] * 100)), [])
                   if inside(point, building['building_polygon'])]
        if len(matches) == 1:
            key, building = matches[0]
            if not feature['name']:
                feature['name'] = building['name']
            feature['station_building'] = key[1]


def assign_stop_areas(features, relations):
    memberships = {}
    for rid, relation in relations.items():
        if relation['tags'].get('public_transport') != 'stop_area':
            continue
        for member in relation['members']:
            key = (member['type'], member['ref'])
            if key in features:
                memberships.setdefault(key, set()).add(rid)
    for key, area_ids in memberships.items():
        # 多个站点关系共用一个成员时不随意选一个，也不提升到换乘组。
        if len(area_ids) != 1:
            continue
        rid = next(iter(area_ids))
        feature = features[key]
        feature['stop_area'] = rid
        station_name = name(relations[rid]['tags'])
        if station_name:
            feature['name'] = station_name


class Features(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.features = {}
        self.way_nodes = {}
        self.buildings = set()
        self.station_areas = {}

    def node(self, node):
        if node.location.valid():
            tags = dict(node.tags)
            self.features[("n", node.id)] = {"name": name(tags), "rail": is_rail(tags),
                                            "coords": (node.location.lat, node.location.lon),
                                            'station_node': tags.get('railway') in {'station', 'halt', 'tram_stop'} or tags.get('public_transport') == 'station',
                                            'stop_position': tags.get('public_transport') == 'stop_position' or tags.get('railway') == 'stop'}

    def way(self, way):
        tags = dict(way.tags)
        self.features[("w", way.id)] = {"name": name(tags), "rail": is_rail(tags)}
        self.way_nodes[way.id] = [node.ref for node in way.nodes]
        if tags.get('building') == 'train_station':
            self.buildings.add(way.id)
        elif tags.get('railway') in {'station', 'halt'} or tags.get('public_transport') == 'station':
            self.station_areas[way.id] = '车站范围'
        elif tags.get('railway') == 'platform' or tags.get('public_transport') == 'platform':
            self.station_areas[way.id] = '站台范围'


class Coordinates(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.coords = {}

    def node(self, node):
        if node.location.valid():
            self.coords[node.id] = (node.location.lat, node.location.lon)


def build_station_index(pbf_path, data_dir, rail_ways, relations):
    handler = Features()
    tag_filter = osmium.filter.TagFilter(
        ('building', 'train_station'),
        *(("railway", value) for value in ("station", "halt", "stop", "tram_stop", "platform")),
        *(("public_transport", value) for value in ("station", "stop_position", "platform")))
    print("收集本地车站、停车点和站台...", flush=True)
    with osmium.io.Reader(str(pbf_path), osmium.osm.NODE | osmium.osm.WAY) as reader:
        osmium.apply(reader, tag_filter, handler)
    routes, areas = {}, []
    for relation in relations.values():
        tags, members = relation["tags"], relation["members"]
        if tags.get("public_transport") == "stop_area":
            areas.append((tags, [(m["type"], m["ref"]) for m in members]))
        if tags.get("type") == "route" and tags.get("route") in RAIL_MODES:
            ways = [m["ref"] for m in members if m["type"] == "w" and m["ref"] in rail_ways]
            if ways:
                stops = [(m["type"], m["ref"]) for m in members
                         if m["role"].split("_")[0] in {"stop", "platform"}]
                routes[relation["id"]] = {"ways": ways, "stops": stops}
    referenced = {key for route in routes.values() for key in route["stops"]}
    referenced.update(key for _, members in areas for key in members)
    needed = {nid for nodes in handler.way_nodes.values() for nid in nodes}
    needed.update(ref for kind, ref in referenced if kind == "n" and (kind, ref) not in handler.features)
    print(f"补充 {len(needed)} 个站点几何节点...", flush=True)
    coords = Coordinates()
    if needed:
        with osmium.io.Reader(str(pbf_path), osmium.osm.NODE) as reader:
            osmium.apply(reader, osmium.filter.IdFilter(needed), coords)
    for kind, ref in referenced:
        if kind == "n" and (kind, ref) not in handler.features and ref in coords.coords:
            handler.features[(kind, ref)] = {"name": "", "rail": False, "coords": coords.coords[ref]}
    for wid, nodes in handler.way_nodes.items():
        points = [coords.coords[n] for n in nodes if n in coords.coords]
        if points:
            handler.features[("w", wid)]["coords"] = tuple(sum(p[i] for p in points) / len(points) for i in (0, 1))
            if wid in handler.buildings and len(points) == len(nodes) and len(points) >= 4 and nodes[0] == nodes[-1]:
                handler.features[("w", wid)]['building_polygon'] = points
            if wid in handler.station_areas and len(points) == len(nodes) and len(points) >= 4 and nodes[0] == nodes[-1]:
                handler.features[("w", wid)]['station_polygon'] = points
                handler.features[("w", wid)]['area_kind'] = handler.station_areas[wid]
    for route in routes.values():
        for key in route["stops"]:
            if key in handler.features:
                handler.features[key]["rail"] = True
    for tags, members in areas:
        features = [handler.features[key] for key in members if key in handler.features]
        if not any(f["rail"] for f in features):
            continue
        for feature in features:
            feature["rail"] = True
    assign_stop_areas(handler.features, relations)
    assign_building_names(handler.features)
    features = {key: value for key, value in handler.features.items()
                if value["rail"] and value["name"] and "coords" in value}
    data = {"features": features, "routes": routes}
    path = Path(data_dir) / "stations.pkl"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".pkl.tmp")
    with temporary.open("wb") as output:
        pickle.dump(data, output)
    os.replace(temporary, path)
    print(f"站点索引已保存：{len(features)} 个站点要素、{len(routes)} 条运行线路。", flush=True)
    return data

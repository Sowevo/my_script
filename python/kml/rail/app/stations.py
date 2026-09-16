"""从本地 PBF 站点索引查询轨道关联车站，不发送在线请求。"""

import math


def distance(a, b):
    lat1, lat2 = map(math.radians, (a[0], b[0]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2)
    return 6371000 * 2 * math.asin(min(1, math.sqrt(h)))


class StationIndex:
    def __init__(self, data, ways):
        self.features = data["features"]
        self.routes = data["routes"]
        self.ways = ways
        self.way_routes = {}
        for rid, route in self.routes.items():
            for wid in route["ways"]:
                self.way_routes.setdefault(wid, set()).add(rid)

    def query(self, point, way_ids, radius=1500):
        # 端点命名不能被行程中途经过的停车点抢占。
        endpoint_way = way_ids[0] if way_ids else None
        nodes = set(self.ways.get(endpoint_way, ()))
        related = {key for rid in self.way_routes.get(endpoint_way, ())
                   for key in self.routes[rid]["stops"]}
        candidates = {}
        for key, feature in self.features.items():
            if not feature["name"] or not feature.get("rail"):
                continue
            metres = distance(point, feature["coords"])
            if metres > radius:
                continue
            direct = key[0] == "n" and key[1] in nodes
            priority = 0 if direct else 1 if key in related else 2
            source = ("轨道停车点", "线路停靠站", "附近车站")[priority]
            candidate = {"name": feature["name"], "distance": round(metres), "source": source,
                         "stop_area": feature.get('stop_area')}
            # 直接停车点与线路停靠站都有关联，优先选择更靠近端点的一站。
            rank = (0 if priority < 2 else 1, metres, priority)
            identity = ('stop_area', feature['stop_area']) if feature.get('stop_area') else ('name', feature['name'])
            if identity not in candidates or rank < candidates[identity][0]:
                candidates[identity] = (rank, candidate)
        return [item for _, item in sorted(candidates.values(), key=lambda entry: entry[0])[:5]]

from flask import Flask, request, jsonify, render_template
import pickle
import os
import math
import hashlib
import json
from nearby import NearbyIndex
from geocoding import Geocoder
from stations import StationIndex
from station_map import StationMap
from urllib.error import HTTPError, URLError
from diagnostics import configure_logging, record_diagnostic

DATA_DIR = os.environ.get('RAIL_DATA_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'))
NODE_TO_WAYS_PATH = os.path.join(DATA_DIR, 'node_to_ways.pkl')
WAY_TO_NODES_PATH = os.path.join(DATA_DIR, 'way_to_nodes.pkl')
NODE_COORDS_PATH = os.path.join(DATA_DIR, 'node_coords.pkl')
WAY_TO_META_PATH = os.path.join(DATA_DIR, 'way_to_meta.pkl')

# 加载索引
with open(NODE_TO_WAYS_PATH, 'rb') as f:
    node_to_ways = pickle.load(f)
with open(WAY_TO_NODES_PATH, 'rb') as f:
    way_to_nodes = pickle.load(f)
with open(NODE_COORDS_PATH, 'rb') as f:
    node_coords = pickle.load(f)
with open(WAY_TO_META_PATH, 'rb') as f:
    way_to_meta = pickle.load(f)

# 索引只保留轨道节点，使用其实际覆盖范围初始化地图。
map_bounds = None
if node_coords:
    map_bounds = [
        [min(p[0] for p in node_coords.values()), min(p[1] for p in node_coords.values())],
        [max(p[0] for p in node_coords.values()), max(p[1] for p in node_coords.values())],
    ]

app = Flask(__name__)
log_path = configure_logging(app, os.path.join(DATA_DIR, 'logs'))


relations_path = os.path.join(DATA_DIR, 'relations.pkl')
relations_available = os.path.isfile(relations_path)
relations = {}
if relations_available:
    with open(relations_path, 'rb') as f:
        relations = pickle.load(f)
nearby_index = NearbyIndex(way_to_nodes, node_coords, way_to_meta, relations)
geocoder = Geocoder()


station_index = None
station_map = None
station_path = os.path.join(DATA_DIR, 'stations.pkl')
if os.path.isfile(station_path):
    with open(station_path, 'rb') as station_file:
        station_index = StationIndex(pickle.load(station_file), way_to_nodes)
        station_map = StationMap(station_index.features, relations)

app.logger.info('startup', extra={'event_data': {
    'event': 'startup', 'data_dir': DATA_DIR, 'log_path': str(log_path),
    'way_count': len(way_to_nodes), 'node_count': len(node_coords),
    'relation_count': len(relations), 'map_bounds': map_bounds,
    'index_files': {name: {'bytes': os.path.getsize(os.path.join(DATA_DIR, name)),
                           'modified': os.path.getmtime(os.path.join(DATA_DIR, name))}
                    for name in os.listdir(DATA_DIR) if name.endswith('.pkl')}
}})


# 绑定已加载索引的版本；重建任一索引都会使旧页面的计算请求失效。
index_signature = [(name, os.stat(os.path.join(DATA_DIR, name)).st_size,
                    os.stat(os.path.join(DATA_DIR, name)).st_mtime_ns)
                   for name in sorted(os.listdir(DATA_DIR)) if name.endswith('.pkl')]
DATASET_VERSION = hashlib.sha256(json.dumps(index_signature).encode()).hexdigest()


@app.before_request
def check_dataset():
    indexed = request.path.startswith(('/track-data', '/elements/', '/nearby', '/stations/'))
    if not indexed:
        return
    payload = request.get_json(silent=True) if request.is_json else None
    supplied = payload.get('dataset_version') if isinstance(payload, dict) else request.args.get('dataset_version')
    if supplied != DATASET_VERSION:
        return jsonify(error='数据源已切换或页面版本过旧，请先导出已有轨迹，再清空行程或刷新页面。',
                       code='dataset_changed', dataset_version=DATASET_VERSION), 409


@app.get('/dataset')
def dataset():
    return jsonify(dataset_version=DATASET_VERSION, map_bounds=map_bounds)


@app.route('/')
def index():
    return render_template('index.html', map_bounds=map_bounds, dataset_version=DATASET_VERSION)

@app.post('/track-data')
def track_data():
    payload = request.get_json(silent=True)
    ids = payload.get('way_ids') if isinstance(payload, dict) else None
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 1000 or
            any(isinstance(wid, bool) or not isinstance(wid, int) for wid in ids)):
        return jsonify(error='请提供 1 至 1000 个轨道 ID。'), 400
    missing = [wid for wid in ids if wid not in way_to_nodes]
    if missing:
        return jsonify(error='当前索引中没有指定轨道。', missing=missing), 404
    nodes = {node for wid in ids for node in way_to_nodes[wid]}
    return jsonify(
        dataset_version=DATASET_VERSION,
        ways={wid: {'nodes': way_to_nodes[wid], 'meta': way_to_meta.get(wid, {})} for wid in ids},
        coords={node: node_coords[node] for node in nodes if node in node_coords},
        node_ways={node: sorted(node_to_ways.get(node, ())) for node in nodes},
        stops=[node for node in nodes if station_index and
               station_index.features.get(('n', node), {}).get('stop_position')])


@app.post('/diagnostics')
def client_diagnostics():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or len(request.data) > 64000:
        return jsonify(error='无效的诊断记录。'), 400
    allowed = ('page_id', 'operation', 'dataset_version', 'revision', 'parameters',
               'before', 'after', 'result', 'error', 'details')
    record_diagnostic('client_operation', **{k: payload[k] for k in allowed if k in payload})
    return jsonify(ok=True)


@app.get('/stations/map')
def visible_stations():
    try:
        south, west, north, east = map(float, request.args['bbox'].split(','))
        zoom = float(request.args['zoom'])
        if (not all(map(math.isfinite, (south, west, north, east, zoom)))
                or not -90 <= south <= north <= 90 or not -180 <= west <= east <= 180
                or north - south > 5 or east - west > 5):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        return jsonify(error='无效的地图范围。'), 400
    if zoom < 16:
        return jsonify(stations=[], truncated=False)
    if station_map is None:
        return jsonify(error='请先生成本地站点索引。'), 503
    return jsonify(station_map.query(south, west, north, east))


@app.post('/stations/nearby')
def endpoint_stations():
    body = request.get_json(silent=True)
    try:
        endpoints = body['endpoints']
        if not isinstance(endpoints, list) or not 2 <= len(endpoints) <= 100:
            raise ValueError
        validated = []
        for endpoint in endpoints:
            point = tuple(map(float, endpoint['point']))
            ids = endpoint['way_ids']
            if (len(point) != 2 or not all(map(math.isfinite, point))
                    or not -90 <= point[0] <= 90 or not -180 <= point[1] <= 180
                    or not isinstance(ids, list) or not ids or len(ids) != 1
                    or any(not isinstance(wid, int) or wid not in way_to_nodes for wid in ids)):
                raise ValueError
            validated.append((point, ids))
    except (KeyError, TypeError, ValueError):
        return jsonify(error='请提供有效的轨迹端点及已选轨道。'), 400
    if station_index is None:
        return jsonify(error='尚未生成本地站点索引，请重新解析 PBF 或手动填写站名。'), 503
    return jsonify(stations=[station_index.query(point, ids) for point, ids in validated])


@app.route('/nearby')
def nearby_elements():
    try:
        lat = float(request.args['lat'])
        lon = float(request.args['lon'])
        radius = float(request.args.get('radius', 250))
        if not (math.isfinite(lat) and math.isfinite(lon) and math.isfinite(radius)
                and -90 <= lat <= 90 and -180 <= lon <= 180 and 10 <= radius <= 500):
            raise ValueError
    except (KeyError, ValueError, TypeError):
        return jsonify(error='请提供有效经纬度及10至500米的查询半径。'), 400
    result = nearby_index.query(lat, lon, radius)
    result['relations_available'] = relations_available
    return jsonify(result)


@app.route('/geocode')
def geocode():
    query = request.args.get('q', '').strip()
    if not query or len(query) > 200:
        return jsonify(error='请输入1至200个字符的地点名称或地址。'), 400
    try:
        return jsonify(results=geocoder.search(query))
    except HTTPError as error:
        app.logger.warning('地名服务返回HTTP %s', error.code)
        if error.code in (403, 429):
            return jsonify(error='在线地名服务暂时限制请求，请稍后重试。'), 503
        return jsonify(error='在线地名服务暂时不可用，请稍后重试。'), 502
    except (URLError, OSError) as error:
        app.logger.warning('地名服务请求失败：%r', error)
        reason = getattr(error, 'reason', error)
        if isinstance(reason, TimeoutError):
            return jsonify(error='在线地名服务响应超时，重试后仍未成功，请稍后再试。'), 504
        return jsonify(error='暂时无法连接在线地名服务，重试后仍未成功，请稍后再试。'), 502
    except (ValueError, KeyError, TypeError) as error:
        app.logger.warning('地名服务响应格式异常：%r', error)
        return jsonify(error='在线地名服务返回了异常数据，请稍后重试。'), 502


@app.route('/elements/<kind>/<int:element_id>')
def element_detail(kind, element_id):
    source = way_to_meta if kind == 'way' else relations if kind == 'relation' else {}
    if element_id not in source:
        return jsonify(error='当前索引中没有这个要素。'), 404
    detail = nearby_index.detail(kind, element_id)
    return jsonify(detail)


if __name__ == '__main__':
    app.run(debug=True, port=5050)

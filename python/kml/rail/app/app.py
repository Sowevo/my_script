from flask import Flask, request, jsonify, render_template, session
import pickle
import folium
import os
import math
from nearby import NearbyIndex
from geocoding import Geocoder
from journey import JourneyExplorer
from recommendation import recommend_way
from urllib.error import HTTPError, URLError

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
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
app.secret_key = 'a_very_secret_key_123456'  # 用于session


relations_path = os.path.join(DATA_DIR, 'relations.pkl')
relations_available = os.path.isfile(relations_path)
relations = {}
if relations_available:
    with open(relations_path, 'rb') as f:
        relations = pickle.load(f)
nearby_index = NearbyIndex(way_to_nodes, node_coords, way_to_meta, relations)
geocoder = Geocoder()
journey_explorer = JourneyExplorer(way_to_nodes, node_to_ways, way_to_meta)


# 递归查找轨道
MAX_DEPTH = 1000

def find_connected_ways(start_way_id, max_depth=MAX_DEPTH):
    visited_ways = set()
    result = []
    def dfs(way_id, depth):
        if depth > max_depth or way_id in visited_ways:
            return
        visited_ways.add(way_id)
        result.append(way_id)
        nodes = way_to_nodes.get(way_id, [])
        for n in nodes:
            for next_way in node_to_ways.get(n, set()):
                if next_way != way_id:
                    dfs(next_way, depth+1)
    dfs(start_way_id, 1)
    return result

def find_next_choices(start_way_id, max_depth=20, total_path=None):
    """
    从start_way_id出发，沿唯一轨道自动前进，直到出现多个可选way或无新way。
    返回：当前way_id、可选的相连way列表（不含当前way）、经过的way链路、visited_path
    """
    if total_path is None:
        total_path = []  # int列表
    visited_ways = set()
    path = []
    current_way = start_way_id
    for _ in range(max_depth):
        visited_ways.add(current_way)
        path.append(current_way)
        nodes = way_to_nodes.get(current_way, [])
        neighbor_ways = set()
        for n in nodes:
            neighbor_ways.update(node_to_ways.get(n, set()))
        neighbor_ways.discard(current_way)  # 排除当前way
        neighbor_ways -= visited_ways
        neighbor_ways -= set(total_path)  # 排除全局累计链路中出现过的way，避免往回走
        if len(neighbor_ways) == 1:
            current_way = list(neighbor_ways)[0]
        else:
            return {
                'current_way': current_way,
                'choices': list(neighbor_ways),
                'path': path,
                'visited_path': path
            }
    return {
        'current_way': current_way,
        'choices': list(neighbor_ways),
        'path': path,
        'visited_path': path
    }

@app.route('/')
def index():
    return render_template('index.html', map_bounds=map_bounds)

def load_legs():
    if isinstance(session.get('legs'), list):
        return session['legs']
    # 兼容此前浏览器保存的单段轨道链路。
    old_path = [item for item in session.get('total_path', [])
                if isinstance(item, dict) and item.get('way_id') in way_to_nodes]
    if not old_path:
        return []
    first = old_path[0]['way_id']
    return [{'name': way_to_meta.get(first, {}).get('name') or '未命名轨道',
             'start_way': first, 'current_way': old_path[-1]['way_id'],
             'path': old_path, 'relation_id': None, 'transfer_label': ''}]


def journey_response(legs, result):
    def way_coords(wid):
        return [node_coords[n] for n in way_to_nodes.get(wid, []) if n in node_coords]

    result['legs'] = [dict(leg, colour_candidates=[
        way_to_meta.get(leg['start_way'], {}).get('tags', {}).get('colour')])
        for leg in legs]
    result['total_path'] = [item for leg in legs for item in leg['path']]
    result['active_path'] = legs[-1]['path'] if legs else []
    result['choice_coords'] = [
        {'id': wid, 'coords': way_coords(wid), 'meta': way_to_meta.get(wid, {})}
        for wid in result['choices']]
    result['path_coords'] = [
        {'id': wid, 'coords': way_coords(wid), 'meta': way_to_meta.get(wid, {})}
        for wid in result['path']]
    result['total_path_coords'] = [
        {'id': item['way_id'], 'coords': way_coords(item['way_id']),
         'meta': way_to_meta.get(item['way_id'], {}), 'type': item['type'], 'leg': index}
        for index, leg in enumerate(legs) for item in leg['path']]
    recommended = recommend_way(
        legs[-1]['path'] if legs else [], result['choices'],
        way_to_nodes, node_coords, way_to_meta)
    for choice in result['choice_coords']:
        if choice['id'] == recommended:
            choice['recommend'] = True
    return jsonify(result)


@app.route('/ways/<int:way_id>')
def get_ways(way_id):
    if way_id not in way_to_nodes:
        return jsonify(error='当前地图中没有这个轨道ID。'), 404
    try:
        label = request.args.get('transfer_label', '').strip()
        if len(label) > 100:
            raise ValueError('换乘备注不能超过100个字符。')
        legs, result = journey_explorer.advance(
            load_legs(), way_id, reset=request.args.get('reset') == '1',
            transfer=request.args.get('transfer') == '1',
            transfer_label=label)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    session['legs'] = legs
    session.pop('total_path', None)
    return journey_response(legs, result)


@app.post('/journey/undo-way')
def undo_way():
    legs, result = journey_explorer.undo_way(load_legs())
    session['legs'] = legs
    session.pop('total_path', None)
    return journey_response(legs, result)


@app.route('/journey')
def get_journey():
    legs = load_legs()
    choices, reason = journey_explorer.choices(legs[-1]) if legs else ([], '')
    return journey_response(legs, {'current_way': legs[-1]['current_way'] if legs else None,
                                  'choices': choices, 'path': [], 'visited_path': [],
                                  'stop_reason': reason})


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
    if kind == 'way':
        selected = {item['way_id'] for leg in load_legs() for item in leg['path']}
        touching = journey_explorer.connected(element_id) | {element_id}
        detail['connected_to_journey'] = bool(selected & touching)
    return jsonify(detail)


@app.route('/map/<int:way_id>')
def get_map(way_id):
    legs = load_legs()
    session_path = legs[-1]['path'] if legs else []
    int_path = [x['way_id'] for x in session_path if isinstance(x, dict) and 'way_id' in x]
    result = find_next_choices(way_id, total_path=int_path)
    highlight = request.args.get('highlight', type=int)
    all_coords = []
    for wid in result['path']:
        nodes = way_to_nodes.get(wid, [])
        coords = [node_coords[n] for n in nodes if n in node_coords]
        all_coords.extend(coords)
    if highlight:
        nodes = way_to_nodes.get(highlight, [])
        coords = [node_coords[n] for n in nodes if n in node_coords]
        all_coords.extend(coords)
    center = [(map_bounds[0][i] + map_bounds[1][i]) / 2 for i in range(2)] if map_bounds else [0, 0]
    if all_coords:
        center = all_coords[0]
    m = folium.Map(location=center, zoom_start=8)
    # 蓝色链路
    for wid in result['path']:
        nodes = way_to_nodes.get(wid, [])
        coords = [node_coords[n] for n in nodes if n in node_coords]
        if len(coords) >= 2:
            folium.PolyLine(coords, color='blue', tooltip=f"{wid}").add_to(m)
    # 仅高亮悬停轨道
    if highlight:
        nodes = way_to_nodes.get(highlight, [])
        coords = [node_coords[n] for n in nodes if n in node_coords]
        if len(coords) >= 2:
            folium.PolyLine(coords, color='red', tooltip=f'可选:{highlight}').add_to(m)
    # 自动缩放
    if all_coords:
        m.fit_bounds(all_coords)
    return m._repr_html_()

if __name__ == '__main__':
    app.run(debug=True, port=5050)

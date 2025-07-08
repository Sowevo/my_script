from flask import Flask, request, jsonify, render_template, session
import pickle
import folium
import os
import math

DATA_DIR = 'data'
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

app = Flask(__name__)
app.secret_key = 'a_very_secret_key_123456'  # 用于session

# 递归查找轨道
MAX_DEPTH = 20

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
    return render_template('index.html')

@app.route('/ways/<int:way_id>')
def get_ways(way_id):
    if request.args.get('reset') == '1':
        session['total_path'] = []
    if 'total_path' not in session or not isinstance(session['total_path'], list):
        session['total_path'] = []
    else:
        session['total_path'] = [x for x in session['total_path'] if isinstance(x, dict) and 'way_id' in x]
    total_path = session['total_path']
    int_path = [x['way_id'] for x in total_path]
    result = find_next_choices(way_id, total_path=int_path)
    visited_path = result['visited_path']
    new_path = []
    if not total_path:
        new_path.append({'way_id': visited_path[0], 'type': 'manual'})
        start = 1
    else:
        start = 0
    for i in range(start, len(visited_path)):
        if i == len(visited_path)-1 and result['choices']:
            new_path.append({'way_id': visited_path[i], 'type': 'manual'})
        else:
            new_path.append({'way_id': visited_path[i], 'type': 'auto'})
    for item in new_path:
        if not any(x['way_id']==item['way_id'] for x in total_path):
            total_path.append(item)
    session['total_path'] = total_path
    result['total_path'] = total_path
    # 新增：返回轨道坐标数据
    def way_coords(wid):
        nodes = way_to_nodes.get(wid, [])
        return [node_coords[n] for n in nodes if n in node_coords]
    result['path_coords'] = [
        {'id': wid, 'coords': way_coords(wid), 'meta': way_to_meta.get(wid, {})}
        for wid in result['path']
    ]
    result['choice_coords'] = [
        {'id': wid, 'coords': way_coords(wid), 'meta': way_to_meta.get(wid, {})}
        for wid in result['choices']
    ]
    result['total_path_coords'] = [
        {'id': x['way_id'], 'coords': way_coords(x['way_id']), 'meta': way_to_meta.get(x['way_id'], {}), 'type': x['type']}
        for x in total_path
    ]
    # === 推荐逻辑 ===
    def dist(p1, p2):
        return math.hypot(p1[0]-p2[0], p1[1]-p2[1])
    def point_line_dist(p, a, b):
        # p到ab直线距离
        if a == b:
            return dist(p, a)
        x0, y0 = p
        x1, y1 = a
        x2, y2 = b
        num = abs((y2-y1)*x0 - (x2-x1)*y0 + x2*y1 - y2*x1)
        den = math.hypot(y2-y1, x2-x1)
        return num/den if den else 0
    if len(result['total_path_coords']) >= 2 and result['choice_coords']:
        prev2 = result['total_path_coords'][-2]
        prev1 = result['total_path_coords'][-1]
        a = prev2['coords'][-1] if prev2['coords'] else None
        b = prev1['coords'][-1] if prev1['coords'] else None
        prev1_name = prev1['meta'].get('tags', {}).get('name')
        # 1. 排除往回走
        filtered = []
        for c in result['choice_coords']:
            if not c['coords']: continue
            c_end = c['coords'][-1]
            if dist(c_end, a) < dist(c_end, b):
                continue
            filtered.append(c)
        # 2. name相同优先（都为空不算）
        name_matched = []
        if prev1_name:
            for c in filtered:
                cname = c['meta'].get('tags', {}).get('name')
                if cname and cname == prev1_name:
                    name_matched.append(c)
        # 3. 终点更靠近直线
        candidates = name_matched if name_matched else filtered
        best_idx = -1
        best_score = float('inf')
        for idx, c in enumerate(result['choice_coords']):
            if c not in candidates: continue
            c_end = c['coords'][-1]
            score = point_line_dist(c_end, a, b)
            if score < best_score:
                best_score = score
                best_idx = idx
        if best_idx >= 0:
            result['choice_coords'][best_idx]['recommend'] = True
    return jsonify(result)

@app.route('/map/<int:way_id>')
def get_map(way_id):
    session_path = session.get('total_path', [])
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
    center = [35, 104]
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
    app.run(debug=True) 
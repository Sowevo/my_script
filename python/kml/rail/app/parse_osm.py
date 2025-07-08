import osmium
import pickle
from tqdm import tqdm
import os

PBF_PATH = '/Users/sowevo/Downloads/china-latest.osm.pbf'
DATA_DIR = 'data'
NODE_TO_WAYS_PATH = os.path.join(DATA_DIR, 'node_to_ways.pkl')
WAY_TO_NODES_PATH = os.path.join(DATA_DIR, 'way_to_nodes.pkl')
NODE_COORDS_PATH = os.path.join(DATA_DIR, 'node_coords.pkl')
WAY_TO_META_PATH = os.path.join(DATA_DIR, 'way_to_meta.pkl')

class RailWayHandler(osmium.SimpleHandler):
    def __init__(self, pbar=None):
        super().__init__()
        self.node_to_ways = {}
        self.way_to_nodes = {}
        self.rail_node_ids = set()
        self.way_to_meta = {}
        self.way_count = 0
        self.pbar = pbar
    def way(self, w):
        if 'railway' in w.tags and w.tags['railway'] in ['rail', 'subway', 'light_rail']:
            node_ids = [n.ref for n in w.nodes]
            self.way_to_nodes[w.id] = node_ids
            for n in node_ids:
                self.node_to_ways.setdefault(n, set()).add(w.id)
                self.rail_node_ids.add(n)
            meta = {
                'id': w.id,
                'name': w.tags.get('name'),
                'ref': w.tags.get('ref'),
                'operator': w.tags.get('operator'),
                'tags': dict(w.tags),
                'nodes': node_ids
            }
            self.way_to_meta[w.id] = meta
            self.way_count += 1
        if self.pbar:
            self.pbar.update(1)

class RailNodeHandler(osmium.SimpleHandler):
    def __init__(self, rail_node_ids, pbar=None):
        super().__init__()
        self.rail_node_ids = rail_node_ids
        self.node_coords = {}
        self.node_count = 0
        self.pbar = pbar
    def node(self, n):
        if n.id in self.rail_node_ids:
            self.node_coords[n.id] = (n.location.lat, n.location.lon)
            self.node_count += 1
            if self.pbar:
                self.pbar.update(1)

def count_entities(pbf_path):
    class Counter(osmium.SimpleHandler):
        def __init__(self):
            super().__init__()
            self.way_count = 0
            self.node_count = 0
        def way(self, w):
            self.way_count += 1
        def node(self, n):
            self.node_count += 1
    counter = Counter()
    counter.apply_file(pbf_path, locations=False)
    return counter.way_count, counter.node_count

def build_and_save_index(pbf_path):
    os.makedirs(DATA_DIR, exist_ok=True)
    print('第一遍：收集way和相关node id...')
    total_way_count, total_node_count = count_entities(pbf_path)
    way_pbar = tqdm(total=total_way_count, desc='Way处理', unit='way')
    way_handler = RailWayHandler(pbar=way_pbar)
    way_handler.apply_file(pbf_path, locations=False)
    way_pbar.close()
    print(f'共找到铁路/地铁/轻轨way: {way_handler.way_count} 条，相关node: {len(way_handler.rail_node_ids)} 个')
    print('第二遍：收集相关node的坐标...')
    node_pbar = tqdm(total=len(way_handler.rail_node_ids), desc='Node处理', unit='node')
    node_handler = RailNodeHandler(way_handler.rail_node_ids, pbar=node_pbar)
    node_handler.apply_file(pbf_path, locations=True)
    node_pbar.close()
    print(f'共找到相关node坐标: {node_handler.node_count} 个')
    with open(NODE_TO_WAYS_PATH, 'wb') as f:
        pickle.dump(way_handler.node_to_ways, f)
    with open(WAY_TO_NODES_PATH, 'wb') as f:
        pickle.dump(way_handler.way_to_nodes, f)
    with open(NODE_COORDS_PATH, 'wb') as f:
        pickle.dump(node_handler.node_coords, f)
    with open(WAY_TO_META_PATH, 'wb') as f:
        pickle.dump(way_handler.way_to_meta, f)
    print('索引已保存')

if __name__ == '__main__':
    build_and_save_index(PBF_PATH) 
import osmium
import pickle
from tqdm import tqdm
import os
import argparse
import time
from pathlib import Path
from http.client import HTTPException
from urllib.parse import urlsplit
from pbf_download import download_pbf

DATA_DIR = Path(__file__).resolve().parent / 'data'
RAILWAY_TYPES = ('rail', 'subway', 'light_rail', 'monorail')
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
        if w.tags.get('railway') in RAILWAY_TYPES:
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
        if self.pbar is not None:
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
            if self.pbar is not None:
                self.pbar.update(1)


class RailRelationHandler(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.relations = {}

    def relation(self, relation):
        self.relations[relation.id] = {
            'id': relation.id, 'tags': dict(relation.tags),
            'members': [{'type': member.type, 'ref': member.ref, 'role': member.role}
                        for member in relation.members],
        }

    def related_to(self, way_ids):
        # 保留直接包含轨道的关系及其父关系，支持 route_master 和循环引用。
        parents = {}
        selected = set()
        for rid, relation in self.relations.items():
            for member in relation['members']:
                if member['type'] == 'w' and member['ref'] in way_ids:
                    selected.add(rid)
                elif member['type'] == 'r':
                    parents.setdefault(member['ref'], set()).add(rid)
        pending = list(selected)
        while pending:
            for rid in parents.get(pending.pop(), ()):
                if rid not in selected:
                    selected.add(rid)
                    pending.append(rid)
        return {rid: self.relations[rid] for rid in selected}

def build_and_save_index(pbf_path):
    started = time.monotonic()
    os.makedirs(DATA_DIR, exist_ok=True)
    print('第一遍：收集way和相关node id...')
    # 在底层只读取way并过滤轨道，避免为进度统计额外扫描整个文件。
    rail_filter = osmium.filter.TagFilter(
        *(('railway', railway_type) for railway_type in RAILWAY_TYPES)
    )
    with tqdm(desc='轨道处理', unit='way') as way_pbar:
        way_handler = RailWayHandler(pbar=way_pbar)
        with osmium.io.Reader(pbf_path, osmium.osm.WAY) as reader:
            osmium.apply(reader, rail_filter, way_handler)
    print(f'共找到铁路/地铁/轻轨/单轨way: {way_handler.way_count} 条，相关node: {len(way_handler.rail_node_ids)} 个')
    print('第二遍：收集相关node的坐标...')
    # 节点自带坐标，无需为全部OSM节点建立位置缓存；仅匹配节点进入Python。
    with tqdm(total=len(way_handler.rail_node_ids), desc='Node处理', unit='node') as node_pbar:
        node_handler = RailNodeHandler(way_handler.rail_node_ids, pbar=node_pbar)
        with osmium.io.Reader(pbf_path, osmium.osm.NODE) as reader:
            osmium.apply(reader, osmium.filter.IdFilter(way_handler.rail_node_ids), node_handler)
    print(f'共找到相关node坐标: {node_handler.node_count} 个')
    print('读取轨道所属的OSM关系...')
    relation_handler = RailRelationHandler()
    with osmium.io.Reader(pbf_path, osmium.osm.RELATION) as reader:
        osmium.apply(reader, relation_handler)
    relations = relation_handler.related_to(way_handler.way_to_nodes)
    print(f'共找到相关关系: {len(relations)} 个')
    with open(NODE_TO_WAYS_PATH, 'wb') as f:
        pickle.dump(way_handler.node_to_ways, f)
    with open(WAY_TO_NODES_PATH, 'wb') as f:
        pickle.dump(way_handler.way_to_nodes, f)
    with open(NODE_COORDS_PATH, 'wb') as f:
        pickle.dump(node_handler.node_coords, f)
    with open(WAY_TO_META_PATH, 'wb') as f:
        pickle.dump(way_handler.way_to_meta, f)
    with open(Path(DATA_DIR) / 'relations.pkl', 'wb') as f:
        pickle.dump(relations, f)
    print(f'索引已保存，耗时 {time.monotonic() - started:.1f} 秒')


def prepare_index(source):
    if urlsplit(source).scheme.lower() in ('http', 'https'):
        pbf_path = download_pbf(source)
        build_and_save_index(str(pbf_path))
    else:
        pbf_path = Path(source).expanduser()
        if not pbf_path.is_file():
            raise FileNotFoundError(f'本地文件不存在：{pbf_path}；也可以直接传入 HTTP/HTTPS 下载链接')
        build_and_save_index(str(pbf_path))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='从本地OSM PBF文件或下载链接生成轨道索引')
    parser.add_argument('source', help='必填：本地PBF路径或HTTP/HTTPS下载链接')
    args = parser.parse_args()
    try:
        prepare_index(args.source)
    except (OSError, ValueError, RuntimeError, HTTPException) as error:
        parser.exit(1, f'生成索引失败：{error}\n')
    except KeyboardInterrupt:
        parser.exit(130, '已中断；下载进度会保留，用同一链接重试即可续传。\n')

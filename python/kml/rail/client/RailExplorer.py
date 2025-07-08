import osmium as osm
from collections import defaultdict
"""
======================================================
RailMapper - 铁路轨道网络探索工具
======================================================

RailMapper 是一个交互式工具，用于从OSM PBF文件中提取和分析铁路轨道网络。它可以：
1. 探索相连的铁路轨道路径
2. 显示轨道详细信息
3. 搜索特定名称的轨道
4. 可视化铁路网络连接关系

主要功能：
----------------------
1. 轨道路径探索
   - 从指定轨道ID开始
   - 递归探索相连轨道
   - 分支点提供交互选择
   - 自动检测单一连接路径

2. 轨道搜索
   - 按名称关键词搜索
   - 显示匹配轨道列表
   - 快速选择或输入ID

3. 轨道详情查看
   - 显示轨道元数据
   - 列出连接的轨道
   - 提供起始点选项

使用方法：
----------------------
1. 主菜单选项：
   [轨道ID] - 直接输入轨道ID开始探索
   [s] - 按名称搜索轨道
   [d] - 查询轨道详细信息
   [q] - 退出程序

2. 路径探索中的导航：
   [1-9] - 选择分支轨道编号
   [b] - 返回上一级轨道
   [e] - 结束当前路径探索
   [q] - 退出程序

3. 通用命令：
   [回车] - 返回上级菜单
   [q] - 退出当前操作

技术特性：
----------------------
- 基于Osmium库高效解析大型PBF文件
- 构建节点轨道索引实现快速查询
- 递归深度控制防止无限循环
- 智能轨道连接检测算法
- 用户友好交互界面

使用示例：
----------------------
1. 探索京哈铁路网络：
   > 输入起始轨道ID: 123456789
   > 按照提示选择分支路线

2. 搜索"京沪"线路：
   > 输入"s"
   > 搜索关键词: "京沪"
   > 从结果列表选择轨道

3. 查询轨道详情：
   > 输入"d"
   > 输入轨道ID: 987654321
   > 查看详情并决定是否作为起点

数据准备：
----------------------
- 下载OSM PBF格式地图文件
- 安装Python依赖: pip install osmium
"""

class RailwayGraph:
    def __init__(self, pbf_file):
        self.node_ways = defaultdict(set)  # 节点ID → 连接的轨道Way IDs
        self.way_data = {}  # Way ID → {id, nodes, tags}
        print("正在加载铁路网络数据...")
        self._load_railway_data(pbf_file)
        print(f"数据加载完成! 共找到 {len(self.way_data)} 条铁路轨道")

    def _load_railway_data(self, pbf_file):
        """从PBF文件加载铁路轨道数据"""

        class RailwayHandler(osm.SimpleHandler):
            def __init__(self, graph):
                super().__init__()
                self.graph = graph

            def way(self, w):
                if w.tags.get('railway') in ['rail', 'subway', 'light_rail']:
                    way_id = w.id
                    nodes = [n.ref for n in w.nodes]
                    self.graph.way_data[way_id] = {
                        'id': way_id,
                        'nodes': nodes,
                        'tags': dict(w.tags)
                    }
                    for node_id in nodes:
                        self.graph.node_ways[node_id].add(way_id)

        handler = RailwayHandler(self)
        handler.apply_file(pbf_file)

    def get_connected_railways(self, start_way_id, max_level=100):
        """提取相连的铁路轨道（含分支处理）"""
        visited = set()  # 已访问的Way ID
        result = []  # 最终结果序列

        def traverse(way_id, level):
            if level > max_level or way_id in visited:
                return

            way = self.way_data.get(way_id)
            if not way:
                print(f"警告: 轨道 {way_id} 不存在于数据中!")
                return

            visited.add(way_id)
            result.append(way)
            print(f"\n层级 {level}: 轨道 {way_id} " +
                  f"({way['tags'].get('name', '未命名轨道')})")

            # 收集通过节点连接的其他轨道
            branches = {}
            for node_id in way['nodes']:
                for connected_way_id in self.node_ways[node_id]:
                    # 排除自身和已访问轨道
                    if connected_way_id != way_id and connected_way_id not in visited:
                        connected_way = self.way_data[connected_way_id]
                        branches[connected_way_id] = connected_way

            # 处理分支
            if branches:
                if len(branches) == 1:
                    # 只有一个分支自动选择
                    next_way_id = next(iter(branches))
                    way_name = branches[next_way_id]['tags'].get('name', '未命名')
                    print(f"自动选择唯一分支: {next_way_id} ({way_name})")
                    traverse(next_way_id, level + 1)
                else:
                    # 多个分支需用户选择
                    print("\n发现多条分支轨道:")
                    for idx, (wid, way) in enumerate(branches.items(), 1):
                        name = way['tags'].get('name', '未命名轨道')
                        nodes_count = len(way['nodes'])
                        print(f"  {idx}> Way {wid}: {name} (含{nodes_count}节点)")
                        log_list(result,wid)
                    print("  b> 返回上一级")
                    print("  e> 结束当前路径探索")

                    choice = input("请选择操作: ").lower()

                    if choice == 'b' and level > 1:
                        print("返回上一级轨道...")
                        return  # 返回上一级
                    elif choice == 'e':
                        print("结束当前路径探索")
                        return
                    elif choice.isdigit():
                        choice_idx = int(choice)
                        if 1 <= choice_idx <= len(branches):
                            selected_id = list(branches.keys())[choice_idx - 1]
                            traverse(selected_id, level + 1)
                        else:
                            print("无效选择，返回上一级")
                            return
                    else:
                        print("无效输入，返回上一级")
                        return
            else:
                print("此轨道无未访问分支")

        traverse(start_way_id, 1)
        return result


# 主程序循环
def main():
    pbf_path = "/Users/sowevo/Downloads/china-latest.osm.pbf"  # 替换为你的PBF文件路径

    try:
        graph = RailwayGraph(pbf_path)
    except Exception as e:
        print(f"加载OSM文件失败: {e}")
        return

    while True:
        print("\n" + "=" * 50)
        print("铁路轨道提取工具 (输入 'q' 退出程序)")
        print("=" * 50)

        # 获取用户输入
        start_input = input("请输入起始轨道ID (输入 's' 搜索轨道，'f' 查找轨道): ").strip().lower()

        if start_input == 'q':
            print("退出程序...")
            break

        if start_input == 's':
            search_term = input("请输入轨道名称关键词: ").strip().lower()
            found = []

            # 搜索轨道名称包含关键词的轨道
            for way_id, way in graph.way_data.items():
                if search_term in way['tags'].get('name', '').lower():
                    found.append(way)
                    if len(found) >= 20:  # 限制结果数量
                        break

            if found:
                print("\n找到以下匹配的轨道:")
                for i, way in enumerate(found, 1):
                    name = way['tags'].get('name', '未命名')
                    print(f"{i}. Way {way['id']}: {name}")

                # 显示更多结果信息
                if len(found) > 20:
                    print(f"(省略了 {len(found) - 20} 条结果)")

                # 灵活的输入处理
                choice = input("\n请选择轨道编号或输入轨道ID (按回车返回): ").strip()

                if choice == "":
                    print("返回主菜单...")
                elif choice.isdigit():
                    choice_num = int(choice)

                    # 如果输入数字在搜索结果索引范围内
                    if 1 <= choice_num <= len(found):
                        start_way_id = found[choice_num - 1]['id']
                        print(f"选择轨道: {start_way_id}")
                        railways = graph.get_connected_railways(start_way_id)
                        print_results(railways)

                    # 如果输入的数字可能是轨道ID
                    elif choice_num in graph.way_data:
                        start_way_id = choice_num
                        print(f"直接选择轨道ID: {start_way_id}")
                        railways = graph.get_connected_railways(start_way_id)
                        print_results(railways)

                    else:
                        print(f"错误: {choice_num} 既不是有效的搜索结果索引，也不是存在的轨道ID")
                else:
                    print("无效输入，请输入数字或轨道ID")
            else:
                print("未找到匹配的轨道")
            continue

        if start_input == 'f':
            while True:
                way_id_str = input("\n请输入轨道ID进行查询 (或按回车返回): ").strip()
                if way_id_str == "":
                    print("返回主菜单...")
                    break

                try:
                    way_id = int(way_id_str)
                except ValueError:
                    print("请输入有效的数字轨道ID")
                    continue

                if way_id in graph.way_data:
                    way = graph.way_data[way_id]
                    print(f"\n轨道 {way_id} 详细信息:")
                    print(f"名称: {way['tags'].get('name', '未命名')}")
                    print(f"类型: {way['tags'].get('railway', '未指定')}")
                    print(f"节点数: {len(way['nodes'])}")

                    # 检查连接点
                    connections = set()
                    for node_id in way['nodes']:
                        for w_id in graph.node_ways[node_id]:
                            if w_id != way_id:
                                connections.add(w_id)

                    if connections:
                        print(f"\n此轨道连接到以下轨道:")
                        for i, conn_id in enumerate(connections, 1):
                            name = graph.way_data[conn_id]['tags'].get('name', '未命名')
                            print(f"{i}. Way {conn_id}: {name}")
                    else:
                        print("此轨道无直接连接的其他轨道")

                    # 询问是否使用此轨道
                    use = input("\n是否使用此轨道作为起点? (y/n): ").lower()
                    if use == 'y':
                        railways = graph.get_connected_railways(way_id)
                        print_results(railways)
                        break
                else:
                    print(f"轨道 {way_id} 不存在!")
            continue

        # 直接输入轨道ID
        try:
            start_way_id = int(start_input)
        except ValueError:
            print("错误: 请输入有效的轨道ID数字")
            continue

        if start_way_id in graph.way_data:
            railways = graph.get_connected_railways(start_way_id)
            print_results(railways)
        else:
            print(f"错误: 轨道 {start_way_id} 不存在!")

            # 随机展示几个轨道ID帮助用户
            import random
            sample = random.sample(list(graph.way_data.keys()), min(5, len(graph.way_data)))
            print("\n随机可用轨道示例:")
            for way_id in sample:
                name = graph.way_data[way_id]['tags'].get('name', '未命名')
                print(f" - Way {way_id}: {name}")


# 打印提取结果
def print_results(railways):
    if not railways:
        print("未提取到任何轨道")
        return

    print("\n" + "=" * 50)
    print("======= 提取结果 =======")
    for idx, way in enumerate(railways, 1):
        name = way['tags'].get('name', '未命名轨道')
        nodes = way['nodes']
        ref = way['tags'].get('ref', '')
        print(f"{idx}. Way {way['id']}: {name} {ref} (含{len(nodes)}节点)")

    print(f"\n共提取 {len(railways)} 条相连轨道")
    log_list(railways)
    print("=" * 50)

def log_list(result_list=None,last_way_id=None):
    ## 记录当前进度
    for e in result_list:
        print(f"way({e['id']});", end="")
    if last_way_id:
        print(f"way({last_way_id});", end="")
    print()

if __name__ == "__main__":
    main()
# 铁路/地铁/轻轨 OSM 轨道递归提取与可视化系统

## 功能简介
- 基于 OSM PBF 文件，递归提取铁路/地铁/轻轨轨道的 way 列表。
- 支持自动/手动推进轨道链路，智能推荐分支。
- 可视化轨道链路、分支、全局累计链路，支持地图交互。
- 支持一键复制全局累计链路为 Overpass Turbo 查询格式。
- 前端采用 Leaflet+Bootstrap5，交互美观流畅。

## 依赖环境
- Python 3.8+
- Flask
- osmium
- tqdm
- folium
- Bootstrap 5 (前端CDN)
- Leaflet.js (前端CDN)

## 安装与运行
1. 安装依赖：
   ```bash
   pip install flask osmium tqdm folium
   ```
2. 下载 OSM PBF 数据（如 china-latest.osm.pbf），放到本地。
3. 生成索引（首次运行较慢，需数分钟~十几分钟，视机器性能和数据量）：
   ```bash
   python3 parse_osm.py
   ```
4. 启动服务：
   ```bash
   python3 app.py
   ```
5. 浏览器访问 [http://127.0.0.1:5000/](http://127.0.0.1:5000/)

## 数据准备
- 推荐使用 [Geofabrik](https://download.geofabrik.de/) 下载中国或其他区域的最新 OSM PBF 文件。
- 默认路径为 `/Users/sowevo/Downloads/china-latest.osm.pbf`，可在 `parse_osm.py` 中修改。
- 生成的索引文件会保存在 `data/` 目录。

## 主要用法
- 输入起始 way_id，点击“重新开始”即可递归提取轨道链路。
- 可选相连轨道支持智能推荐，推荐项高亮。
- 地图支持轨道高亮、自动缩放、全局累计链路可视化。
- 点击“全局累计链路:”可一键复制 Overpass Turbo 查询格式，并自动打开 [overpass-turbo.eu](https://overpass-turbo.eu/#)。

## 界面说明
- 左侧为操作区：way_id输入、可选轨道、全局累计链路。
- 右侧为地图区，支持轨道高亮、缩放、全览。
- 支持响应式布局，适配不同屏幕。

## 常见问题
- **PBF 解析慢/内存高**：建议裁剪区域或用更大内存机器。
- **轨道不显示**：请确保 `node_coords.pkl` 文件不为空，且已用“两遍法”生成。
- **复制/粘贴问题**：如浏览器限制剪贴板访问，请手动复制。

## 目录结构
```
├── app.py              # Flask后端主程序
├── parse_osm.py        # OSM PBF解析与索引生成
├── templates/
│   └── index.html      # 前端页面
├── data/               # 索引数据目录
│   ├── node_to_ways.pkl
│   ├── way_to_nodes.pkl
│   ├── node_coords.pkl
│   └── way_to_meta.pkl
└── README.md           # 项目说明
```

## 联系与反馈
如有问题或建议，欢迎 issue 或联系作者。 
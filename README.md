# 我的脚本与配置备份

## [shell](./shell): 一些脚本

- 各类常用 shell 脚本，按用途分类：
  - mac/：macOS 相关初始化、网络配置、壁纸下载等脚本
    - mac_init.sh：Mac 初始化脚本
    - set_ethernet.sh：公司环境下快速切换网卡配置
    - bing.wallpapers.sh：下载 Bing 壁纸并设置为桌面
  - media_processing/：媒体文件处理相关脚本
    - exiftool_import.sh：批量导入图片元数据
    - find_hardlink.sh：查找硬链接
    - subtitle_rename.sh：字幕文件批量重命名
    - rsync/：常用 rsync 拉取/推送命令（照片、视频、系统镜像）
  - other/：杂项脚本
    - aliyunpan_upload.sh：阿里云盘上传
    - auto-generate-docker-tls-ca.sh：自动生成 Docker TLS 证书
    - CloudflareSpeedTest.sh：Cloudflare 节点测速
    - find_video.sh：查找视频文件
    - install_docker_compose.sh：一键安装 Docker Compose
    - mysql.backup.sh / mysql.sync.sh：开发环境 MySQL 备份与同步
    - ssr_url.sh：SSR 链接处理
  - openwrt/：OpenWrt 相关脚本与文档
    - openwrt.md：OpenWrt 相关说明
  - snippet.md：常用 shell 片段收集

## [postfix-templates](./postfix-templates)

- IDEA 自定义代码补全模板，需配合 Custom Postfix Templates 插件使用
- nancalnumberutils.postfixTemplates：自定义模板示例

## [docker-compose](./docker-compose): 一些 docker-compose 配置

- 各类服务的 Docker Compose 配置，便于一键部署
  - media_server/、photo_server/、openwrt/ 等：常用服务编排
  - deprecated/：已弃用的历史配置
    - prometheus/、immich/、nas-tools/、photoprism/、docker-registry/、homeassistant/、icloudpd/：历史服务编排及相关配置

## [m3u](./m3u)

- 各地 IPTV 的 m3u 播放列表配置
- update.sh：自动更新脚本

## [python](./python) 一些 python 脚本

- 各类实用 Python 脚本工具
  - 115_csv_rename.py：115 网盘导出 CSV 文件重命名
  - DaTiKa.py / DaTiKa.json：答题卡相关处理
  - gycq.py：共有产权房监控提醒（可用于青龙面板）
  - iCloudDupPhotoClean.py：iCloud 照片去重
  - mp3_tag.py：MP3 标签处理
  - notion.py：Notion 相关脚本
  - qb.py / qbittorrent_torrent_statistics.py：qBittorrent 相关脚本
  - kml/：地理信息相关脚本
    - flight/：航班轨迹、KML 处理
    - rail/：铁路轨迹、OSM 解析、Web 可视化（含 app/、client/ 子目录）

## [userscript](./userscript)

- 浏览器用户脚本
  - YuanbaoFontSize.user.js：网页字体大小自定义脚本


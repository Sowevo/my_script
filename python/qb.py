import qbittorrentapi

conn_info = dict(
    host="https://qbittorrent.com",
    port=8080,
    username="admin",
    password="adminadmin"
)
# 获取所有的种子
qb = qbittorrentapi.Client(**conn_info)

torrents = qb.torrents.info()
# 尝试判断辅种
file_sizes = {}

for torrent in torrents:
    file_size = torrent.size
    if file_size in file_sizes:
        file_sizes[file_size].append(torrent)
    else:
        file_sizes[file_size] = [torrent]
for torrent in torrents:
    for tracker in torrent.trackers:
        if "sharkpt" in tracker.url or "leaguehd" in tracker.url:
            x = file_sizes.get(torrent.size)
            if len(x) > 1:
                print("不完全删除\t" + torrent.name)
                qb.torrents.delete(torrent_hashes=torrent.hash, delete_files=False)
            else:
                # 没有辅种的,手动处理
                print("完全删除\t" + torrent.name)

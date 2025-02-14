import math
from datetime import datetime
import requests
import hashlib
import pandas as pd
import os
"""
qBittorrent 种子统计与分类工具

功能描述：
1. 登录 qBittorrent Web UI，获取当前所有种子的详细信息。
2. 对种子进行去重处理，避免统计重复的辅种。
3. 根据种子的保存路径（save_path）的最后一级目录，自动生成分类标签。
4. 将种子的总大小、添加时间、完成时间等字段转换为更易读的格式。
5. 将统计结果导出为 Excel 文件，包含以下字段：
   - 种子名称
   - 哈希值
   - 保存路径
   - 分类标签
   - 总大小（可读格式，如 GB、MB）
   - 进度
   - 状态
   - 分享率
   - 添加时间（可读格式）
   - 完成时间（可读格式）

使用方法：
1. 修改脚本中的 `host`、`username` 和 `password` 变量，配置 qBittorrent Web UI 的地址和登录信息。
2. 运行脚本，生成的 Excel 文件将保存为 `qBittorrent种子统计.xlsx`。

依赖库：
- requests：用于与 qBittorrent Web UI 进行 HTTP 通信。
- pandas：用于生成和导出 Excel 文件。
- hashlib：用于生成种子的唯一标识符。
- os：用于路径处理。
- datetime：用于时间戳转换。

# pip install requests pandas openpyxl

"""


def login_qbittorrent(host, username, password):
    session = requests.Session()
    login_url = f"{host}/api/v2/auth/login"
    try:
        response = session.post(login_url, data={'username': username, 'password': password})
        if response.text == 'Ok.':
            print("登录成功")
            return session
        else:
            print(f"登录失败: {response.text}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"登录请求失败: {e}")
        return None


def get_torrents_list(session, host):
    torrents_url = f"{host}/api/v2/torrents/info"
    try:
        response = session.get(torrents_url)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"获取种子列表失败: {e}")
        return None


def get_torrent_files(session, host, hash):
    files_url = f"{host}/api/v2/torrents/files?hash={hash}"
    try:
        response = session.get(files_url)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"获取种子 {hash} 文件失败: {e}")
        return None


def normalize_path(path):
    path = os.path.normpath(path).replace('\\', '/')
    return path.rstrip('/')


def generate_identifier(save_path, file_list):
    sorted_files = sorted(file_list, key=lambda x: x['name'])
    identifier_str = normalize_path(save_path)
    for f in sorted_files:
        identifier_str += f"{f['name']}:{f['size']}#"
    return hashlib.md5(identifier_str.encode()).hexdigest()


def convert_timestamp(timestamp):
    """将Unix时间戳转换为可读的日期时间格式"""
    if timestamp == 0:
        return "N/A"
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')


def convert_size(size_bytes):
    """将字节大小转换为更易读的格式"""
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"


def get_category_from_path(save_path):
    """从 save_path 中提取最后一级目录作为分类标签"""
    normalized_path = normalize_path(save_path)
    parts = normalized_path.split('/')
    if len(parts) > 1:
        return parts[-1]  # 返回最后一级目录
    return "未分类"  # 如果没有子目录，则返回“未分类”


def main():
    host = 'http://10.0.0.53:8080'  # 替换为你的qBittorrent地址
    username = 'username'  # 替换为你的用户名
    password = 'password'  # 替换为你的密码

    # 登录并获取会话
    session = login_qbittorrent(host, username, password)
    if not session:
        return

    # 获取所有种子列表
    torrents = get_torrents_list(session, host)
    if not torrents:
        return

    unique_identifiers = set()
    deduped_torrents = []

    # 处理每个种子
    for torrent in torrents:
        hash = torrent['hash']
        save_path = normalize_path(torrent['save_path'])

        # 获取文件列表
        files_data = get_torrent_files(session, host, hash)
        if not files_data:
            continue

        # 生成文件标识符
        file_list = [{'name': f['name'], 'size': f['size']} for f in files_data]
        identifier = generate_identifier(save_path, file_list)

        # 去重处理
        if identifier not in unique_identifiers:
            unique_identifiers.add(identifier)
            # 提取分类标签
            category = get_category_from_path(save_path)
            # 收集种子信息
            torrent_info = {
                '种子名称': torrent.get('name', 'N/A'),
                '哈希值': hash,
                '保存路径': save_path,
                '总大小(字节)': torrent.get('size', 0),
                '总大小': convert_size(torrent.get('size', 0)),  # 转换为可读大小
                '进度': torrent.get('progress', 0) * 100,
                '状态': torrent.get('state', 'N/A'),
                '分享率': torrent.get('ratio', 0),
                '分类标签': category,  # 添加分类标签
                '添加时间': convert_timestamp(torrent.get('added_on', 0)),  # 转换为可读时间
                '完成时间': convert_timestamp(torrent.get('completion_on', 0))  # 转换为可读时间
            }
            deduped_torrents.append(torrent_info)
        else:
            print(f"发现辅种: {torrent.get('name', 'N/A')}")

    # 创建DataFrame并导出Excel
    if deduped_torrents:
        df = pd.DataFrame(deduped_torrents)
        df.to_excel('qBittorrent种子统计.xlsx', index=False)
        print(f"导出成功！原始种子数: {len(torrents)}，去重后数量: {len(deduped_torrents)}")
    else:
        print("没有找到需要导出的种子")


if __name__ == '__main__':
    main()

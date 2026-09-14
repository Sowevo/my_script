"""
将 Flightradar24（FR24）的航班飞行轨迹转换为 KML，供「世界迷雾」导入。

数据来源：
    Flightradar24，地址：https://www.flightradar24.com/
    搜索航班号，进入对应日期的航班详情，链接中 # 后面的 ID 就是本脚本的入参。
    在线获取失败时，在开发者工具 Network 中搜索 flight-playback.json，
    复制 Response 中的完整 JSON 保存为文件，也可作为入参。

运行示例（在项目根目录下，使用已有的 .venv 环境）：
    .venv/bin/python "python/kml/flight/fr242kml.py" 419ad5da
    .venv/bin/python "python/kml/flight/fr242kml.py" "/Users/sowevo/Downloads/419ad5da.json"
    .venv/bin/python "python/kml/flight/fr242kml.py" 419ad5da -o "/你的路径/输出目录"

输出规则：
    文件名为「航班号_YYYYMMDD.kml」，例如 CZ647_20260911.kml，日期取轨迹开始的北京时间。
    缺少航班号时，使用 ID 或原 JSON 文件名加日期。
    传入 ID：默认输出到 /Users/sowevo/Downloads/；传入 JSON：默认输出到文件旁。
    -o / --output_path 可指定已存在的输出目录，同名 KML 会被覆盖。
    转换时会补充中间轨迹点，并打印轨迹点数、北京时间和输出文件的完整路径。
    完成后将生成的 KML 导入「世界迷雾」即可。
"""
import argparse
import json
import os.path
import re
import shlex
import sys
from datetime import datetime, timedelta, timezone

import requests
from geopy.distance import geodesic
import xml.etree.ElementTree as ET


def parse_flight(data):
    """从完整接口响应中提取轨迹和航班号，供在线和本地读取共用。"""
    try:
        flight = data['result']['response']['data']['flight']
        track = flight['track']
    except (KeyError, TypeError) as exc:
        raise ValueError("JSON 中未找到航班轨迹，请保存完整的 flight-playback 接口响应。") from exc
    if not isinstance(track, list) or not track:
        raise ValueError("接口响应中没有有效的航班轨迹数据。")
    identification = flight.get('identification') or {}
    number = identification.get('number') or {}
    flight_number = number.get('default')
    return track, flight_number


def fetch_flight_playback(_fr24id):
    """
    从flightradar24获取航班轨迹信息并返回
    :return:
    """
    url = "https://api.flightradar24.com/common/v1/flight-playback.json?flightId=" + _fr24id

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/117.0.0.0 Safari/537.36'
    }

    print(f"正在读取链接：{url}", flush=True)
    try:
        response = requests.request("GET", url, headers=headers, timeout=30)
        if response.status_code != 200:
            raise ValueError(f"接口返回 HTTP {response.status_code}，可能是访问限制或服务异常。")
        try:
            data = response.json()
        except ValueError as exc:
            raise ValueError("接口返回的内容不是有效 JSON，可能是 Cloudflare 验证页。") from exc
        return parse_flight(data)
    except (requests.RequestException, ValueError) as exc:
        command = shlex.join([sys.executable, os.path.abspath(__file__), _fr24id + '.json'])
        raise ValueError(
            f"在线获取失败：{exc}\n"
            "请尝试在浏览器中手动获取 JSON：\n"
            "1. 打开 https://www.flightradar24.com/ ，搜索实际航班号，进入对应日期的航班详情。\n"
            "   如需登录或验证，请先完成。\n"
            "2. 打开开发者工具 → Network（网络），搜索 flight-playback.json，刷新页面或打开航班回放。\n"
            f"3. 复制该请求 Response（响应）中的完整 JSON，保存为 {_fr24id}.json。\n"
            f"然后运行：\n{command}"
        ) from exc


def generate_kml(_data, file_name='fr24.kml'):
    # 创建一个SimpleKML对象
    # 创建根元素
    kml = ET.Element('kml')
    kml.set('xmlns', 'http://www.opengis.net/kml/2.2')
    document = ET.SubElement(kml, 'Document')

    placemark = ET.SubElement(document, 'Placemark')
    name = ET.SubElement(placemark, 'name')
    name.text = 'https://sowevo.com'

    # 添加扩展数据
    extended_data = ET.SubElement(placemark, 'ExtendedData')
    data_name = ET.SubElement(extended_data, 'Data', {'name': 'name'})
    data_value = ET.SubElement(data_name, 'value')
    data_value.text = 'https://sowevo.com'

    # 添加LineString
    linestring = ET.SubElement(placemark, 'LineString')
    coordinates = ET.SubElement(linestring, 'coordinates')

    # 将数据列表中的每个位置添加到LineString中
    coord_str_list = [f"{point['longitude']},{point['latitude']}" for point in _data]
    coordinates.text = " ".join(coord_str_list)

    # 将根元素写入文件
    tree = ET.ElementTree(kml)
    # 将KML文件保存到磁盘
    tree.write(file_name)


def insert_intermediate_points(track_data, max_distance_km=1):
    _new_track = []
    prev_point = None

    for point in track_data:
        if prev_point is not None:
            # 计算当前点与前一个点之间的距离
            distance_km = geodesic((prev_point['latitude'], prev_point['longitude']),
                                   (point['latitude'], point['longitude'])).kilometers
            if distance_km > max_distance_km:
                # 如果距离大于1公里，添加平分点
                num_intermediate_points = int(distance_km / max_distance_km)
                for i in range(1, num_intermediate_points):
                    fraction = i / (num_intermediate_points + 1)
                    intermediate_lat = prev_point['latitude'] + fraction * (point['latitude'] - prev_point['latitude'])
                    intermediate_lon = prev_point['longitude'] + fraction * (
                            point['longitude'] - prev_point['longitude'])
                    intermediate_timestamp = prev_point['timestamp'] + fraction * (
                            point['timestamp'] - prev_point['timestamp'])
                    intermediate_feet = prev_point['altitude']['feet'] + fraction * (
                            point['altitude']['feet'] - prev_point['altitude']['feet'])
                    intermediate_meters = prev_point['altitude']['meters'] + fraction * (
                            point['altitude']['meters'] - prev_point['altitude']['meters'])
                    _new_track.append({
                        'latitude': intermediate_lat,
                        'longitude': intermediate_lon,
                        'altitude': {
                            'feet': intermediate_feet,
                            'meters': intermediate_meters,
                        },
                        'speed': point['speed'],
                        'verticalSpeed': point['verticalSpeed'],
                        'heading': point['heading'],
                        'squawk': point['squawk'],
                        'timestamp': intermediate_timestamp,
                        'ems': point['ems'],
                        'intermediate_points': True,
                    })
        point['intermediate_points'] = False
        _new_track.append(point)
        prev_point = point

    return _new_track


def main(fr24id, output_path=None):
    if fr24id.lower().endswith('.json'):
        input_file = os.path.abspath(fr24id)
        print(f"正在读取文件：{input_file}", flush=True)
        with open(input_file, 'r', encoding='utf-8-sig') as f:
            try:
                track, flight_number = parse_flight(json.load(f))
            except json.JSONDecodeError as exc:
                raise ValueError("文件不是有效 JSON，请保存接口的完整 JSON 响应，不要保存 HTML 页面。") from exc
        file_name = os.path.splitext(os.path.basename(input_file))[0]
        if output_path is None:
            output_path = os.path.dirname(input_file)
    else:
        track, flight_number = fetch_flight_playback(fr24id)
        file_name = fr24id
        if output_path is None:
            output_path = '/Users/sowevo/Downloads/'
    print(f"读取并解析成功，共 {len(track)} 个轨迹点，正在补充中间点……", flush=True)
    new_track = insert_intermediate_points(track)
    print(f"轨迹处理完成，共 {len(new_track)} 个轨迹点，正在生成 KML……", flush=True)
    start_time = datetime.fromtimestamp(min(point['timestamp'] for point in track),
                                        tz=timezone(timedelta(hours=8)))
    print(f"轨迹开始时间（北京时间）：{start_time:%Y-%m-%d %H:%M:%S}", flush=True)
    if isinstance(flight_number, str) and flight_number.strip():
        file_name = re.sub(r'[^A-Za-z0-9_-]', '_', flight_number.strip())
    else:
        print("未找到航班号，文件名使用 ID 或原 JSON 文件名加日期。", flush=True)
    file_name += start_time.strftime('_%Y%m%d')
    output_file = os.path.abspath(os.path.join(output_path, file_name + '.kml'))
    generate_kml(new_track, output_file)
    print(f"KML 文件已输出到：{output_file}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("fr24id", help="Flightradar24 航班 ID（如 419ad5da），或保存的 JSON 文件路径（如 419ad5da.json）", nargs='?', default=argparse.SUPPRESS)
    parser.add_argument("-o", "--output_path", default=None, help="已存在的 KML 输出目录；默认：JSON 文件旁 / ID 模式 /Users/sowevo/Downloads/")
    args = vars(parser.parse_args())

    if 'fr24id' not in args:
        print("错误：请提供 Flightradar24 航班 ID 或 JSON 文件路径。")
        parser.print_help()
        exit()

    try:
        main(args['fr24id'], args['output_path'])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"错误：{exc}", file=sys.stderr, flush=True)
        sys.exit(1)

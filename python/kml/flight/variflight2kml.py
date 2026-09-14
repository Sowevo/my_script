"""
将飞常准（VariFlight）的航班飞行轨迹转换为 KML，供「世界迷雾」导入。

数据来源：
    飞常准，登录地址：https://flightadsb.variflight.com
    登录后输入航班号查询，选择指定日期后点击按钮
    即可下载 JSON 数据，该 JSON 文件就是本脚本的入参。

运行示例（在项目根目录下，使用已有的 .venv 环境）：
    .venv/bin/python "python/kml/flight/variflight2kml.py" "/Users/sowevo/Downloads/Variflight_CZ647_20260911.json"
    .venv/bin/python "python/kml/flight/variflight2kml.py" "/你的路径/航迹.json" -o "/你的路径/输出目录"

输出规则：
    默认在输入 JSON 旁生成「航班号_YYYYMMDD.kml」，例如 CZ647_20260911.kml。
    日期是首个轨迹点的北京时间日期，不是计划起飞日期；缺少时间时只用航班号。
    -o / --output_path 可指定已存在的输出目录，同名 KML 会被覆盖。
    转换时会补充中间轨迹点，并打印解析结果、轨迹点数和输出文件的完整路径。
    完成后将生成的 KML 导入「世界迷雾」即可。
"""
import argparse
import os.path
from datetime import datetime, timedelta, timezone

from geopy.distance import geodesic
import xml.etree.ElementTree as ET


def fetch_json(input_json):
    # 读取JSON文件
    with open(input_json, 'r') as f:
        data = f.read()
    # 将JSON数据转换为Python字典
    track = eval(data)
    return track


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
                    _new_track.append({
                        'latitude': intermediate_lat,
                        'longitude': intermediate_lon,
                    })
        _new_track.append(point)
        prev_point = point

    return _new_track


def main(input_json, output_path=None):
    if output_path is None:
        output_path = os.path.dirname(os.path.abspath(input_json))
    print(f"正在读取：{os.path.abspath(input_json)}", flush=True)
    track = fetch_json(input_json)
    print(f"读取并解析成功，共 {len(track)} 个轨迹点，正在补充中间点……", flush=True)
    new_track = insert_intermediate_points(track)
    print(f"轨迹处理完成，共 {len(new_track)} 个轨迹点，正在生成 KML……", flush=True)
    first_point = track[0]
    file_name = str(first_point['fnum'])
    start_time = None
    if first_point.get('updatetime') is not None:
        start_time = datetime.fromtimestamp(float(first_point['updatetime']), tz=timezone.utc)
    elif first_point.get('UTC Time'):
        start_time = datetime.strptime(first_point['UTC Time'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
    if start_time is not None:
        start_time = start_time.astimezone(timezone(timedelta(hours=8)))
        file_name += start_time.strftime('_%Y%m%d')
        print(f"轨迹开始时间（北京时间）：{start_time:%Y-%m-%d %H:%M:%S}", flush=True)
    else:
        print("未找到轨迹开始时间，文件名仅使用航班号。", flush=True)
    output_file = os.path.abspath(os.path.join(output_path, file_name + '.kml'))
    generate_kml(new_track, output_file)
    print(f"KML 文件已输出到：{output_file}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input_json",
                        help="从飞常准获取并保存的本地航迹 .json 文件路径",
                        nargs='?', default=argparse.SUPPRESS)
    parser.add_argument("-o", "--output_path", default=None, help="KML 文件的输出目录，默认与输入 JSON 文件相同")
    args = vars(parser.parse_args())

    if 'input_json' not in args:
        print("错误：请使用参数“input_json”来自 variflight 飞行数据文件路径")
        parser.print_help()
        exit()

    # 判断input_json是否存在
    if not os.path.exists(args['input_json']):
        print("错误：{0}文件不存在。".format(args['input_json']))
        exit()
    # 判断是否为json文件
    if not args['input_json'].endswith('.json'):
        print("错误：{0}不是JSON文件。".format(args['input_json']))
        exit()

    main(args['input_json'], args['output_path'])

"""
从https://flightadsb.variflight.com获取的数据生成KML文件用于导入世界迷雾
"""
import argparse
import os.path

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


def main(input_json, output_path='.'):
    track = fetch_json(input_json)
    new_track = insert_intermediate_points(track)
    generate_kml(new_track, os.path.join(output_path, str(new_track[0]['fnum']) + '.kml'))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='用于将从 variflight 获取的飞行数据文件转换成 KML 文件的脚本。')
    parser.add_argument("input_json",
                        help="来自 variflight 飞行数据文件路径,  请在https://flightadsb.variflight.com搜索航班号后获取",
                        nargs='?', default=argparse.SUPPRESS)
    parser.add_argument("-o", "--output_path", default=".", help="KML 文件的输出路径")
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

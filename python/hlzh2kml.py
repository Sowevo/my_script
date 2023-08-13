"""
从航旅纵横抓包的数据生成KML文件用于导入世界迷雾
"""

import datetime
import xml.etree.ElementTree as ET
from math import radians, sin, cos, sqrt, atan2
from python.coord_utils import gcj02_to_wgs84


def distance(lat1, lon1, lat2, lon2):
    R = 6371  # 地球平均半径，单位为千米
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    distance_meters = R * c * 1000  # 距离单位转换为米
    return distance_meters


def read_data():
    """
    从文件中读取数据并返回
    :return:
    """
    _data = []
    # 打开文本文件并逐行读取数据
    with open('hlzh.txt', 'r') as f:
        for line in f:
            # 分割每一行数据，获取经纬度和时间戳
            line_data = line.strip().split('|')
            longitude, latitude = float(line_data[1]), float(line_data[3])
            longitude, latitude = gcj02_to_wgs84(longitude, latitude)
            timestamp = datetime.datetime.strptime(line_data[8].strip('"'), '%Y-%m-%d %H:%M:%S%f')

            # 存储经纬度和时间戳到数据列表中
            _data.append({'longitude': longitude, 'latitude': latitude, 'timestamp': timestamp})
    return _data


def fix_data(_data):
    _fix_data = []
    last_lat, last_lon, last_time = None, None, None
    for point in _data:
        longitude = point['longitude']
        latitude = point['latitude']
        timestamp = point['timestamp']
        if last_lat is not None and last_lon is not None:
            # 距离
            dist = distance(last_lat, last_lon, latitude, longitude)
            # 如果距离大于1公里，则添加平分点
            if dist > 1000:
                num_points = int(dist // 1000)  # 将线段分割成多少个子线段
                dlon = (longitude - last_lon) / num_points
                dlat = (latitude - last_lat) / num_points
                dt = (timestamp - last_time) / num_points  # 时间戳按照坐标平分点的个数进行切分
                for i in range(1, num_points):
                    # 计算平分点的经纬度坐标
                    sub_longitude = last_lon + dlon * i
                    sub_latitude = last_lat + dlat * i
                    sub_timestamp = last_time + dt * i
                    _fix_data.append({'longitude': sub_longitude, 'latitude': sub_latitude, 'timestamp': sub_timestamp})
            _fix_data.append({'longitude': longitude, 'latitude': latitude, 'timestamp': timestamp})
        last_lat, last_lon, last_time = latitude, longitude, timestamp
    return _fix_data


def generate_kml(_data):
    # 创建一个SimpleKML对象
    # 创建根元素
    kml = ET.Element('kml')
    kml.set('xmlns', 'http://www.opengis.net/kml/2.2')
    document = ET.SubElement(kml, 'Document')

    # 添加名称为'https://fog.vicc.wang'的Placemark
    placemark = ET.SubElement(document, 'Placemark')
    name = ET.SubElement(placemark, 'name')
    name.text = 'https://fog.vicc.wang'

    # 添加扩展数据
    extended_data = ET.SubElement(placemark, 'ExtendedData')
    data_name = ET.SubElement(extended_data, 'Data', {'name': 'name'})
    data_value = ET.SubElement(data_name, 'value')
    data_value.text = 'https://fog.vicc.wang'

    # 添加LineString
    linestring = ET.SubElement(placemark, 'LineString')
    coordinates = ET.SubElement(linestring, 'coordinates')

    # 将数据列表中的每个位置添加到LineString中
    coord_str_list = [f"{point['longitude']},{point['latitude']}" for point in data]
    coordinates.text = " ".join(coord_str_list)

    # 将根元素写入文件
    tree = ET.ElementTree(kml)
    # 将KML文件保存到磁盘
    tree.write('hlzh.kml')


def calculate_data(_data):
    last_lat, last_lon, last_time = None, None, None
    for point in _data:
        longitude = point['longitude']
        latitude = point['latitude']
        timestamp = point['timestamp']
        # print(longitude,latitude,timestamp)
        if last_lat is not None and last_lon is not None:
            # 计算距离和时间差
            dist = distance(last_lat, last_lon, latitude, longitude)
            time_delta = (timestamp - last_time).total_seconds()
            # 计算速度
            speed = dist / time_delta * 3.6  # 单位：公里/小时
            # 输出结果
            print(f"距离差：{dist:.2f} 米，时间差：{time_delta:.2f} 秒，速度：{speed:.2f} 公里/小时")
        last_lat, last_lon, last_time = latitude, longitude, timestamp


data = read_data()
print(data)
data = fix_data(data)
print(data)
generate_kml(data)

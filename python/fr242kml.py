"""
从flightradar24获取数据生成KML文件用于导入世界迷雾
"""
import requests
from geopy.distance import geodesic
import xml.etree.ElementTree as ET


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

    response = requests.request("GET", url, headers=headers)
    data = response.json()
    # print(data['result']['response']['data']['flight']['track'])
    return data['result']['response']['data']['flight']['track']


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


fr24id = '32529fa9'
track = fetch_flight_playback(fr24id)
new_track = insert_intermediate_points(track)
generate_kml(new_track, fr24id + '.kml')

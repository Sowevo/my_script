from bs4 import BeautifulSoup
import requests
import requests_cache
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from retrying import retry
import re
import sqlite3
import json
from tqdm import tqdm
from datetime import datetime, timedelta
import hashlib


class Station:
    def __init__(self, name, url):
        self.name = name
        self.url = url

    def __eq__(self, other):
        return isinstance(other, Station) and self.url == other.url

    def __hash__(self):
        return hash(self.url)


class Schedule:
    def __init__(self, name, url):
        self.name = name
        self.url = url

    def __eq__(self, other):
        return isinstance(other, Station) and self.url == other.url

    def __hash__(self):
        return hash(self.url)


class ScheduleStation:
    def __init__(self, schedule_id, name, cn_name, number, series, direction, stop_name, _date, time, stop_info_url):
        self.id = hashlib.md5((str(schedule_id) + stop_name + _date).encode()).hexdigest()
        self.schedule_id = schedule_id
        self.name = name
        self.cn_name = cn_name
        self.number = number
        self.series = series
        self.direction = direction
        self.stop_name = stop_name
        self.date = _date
        self.time = time
        self.stop_info_url = stop_info_url

    def to_dict(self):
        return {
            'id': self.id,
            'schedule_id': self.schedule_id,
            'name': self.name,
            'cn_name': self.cn_name,
            'number': self.number,
            'series': self.series,
            'direction': self.direction,
            'stop_name': self.stop_name,
            'date': self.date,
            'time': self.time,
            'stop_info_url': self.stop_info_url
        }


# 启用缓存,缓存有效期为24小时
requests_cache.install_cache('requests_cache', expire_after=60 * 60 * 24)
headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) '
                         'Chrome/119.0.0.0 Safari/537.36'}
base_url = 'https://www.jorudan.co.jp'
name_map = {
    'あさま': {'cn_name': '浅间', 'series': ''},
    'かがやき': {'cn_name': '光辉', 'series': ''},
    'こだま': {'cn_name': '回声', 'series': ''},
    'こまち': {'cn_name': '小町', 'series': ''},
    'さくら': {'cn_name': '樱', 'series': ''},
    'たにがわ': {'cn_name': '谷川', 'series': ''},
    'つばさ': {'cn_name': '翼', 'series': ''},
    'つばめ': {'cn_name': '燕', 'series': ''},
    'つるぎ': {'cn_name': '剑', 'series': ''},
    'とき': {'cn_name': '朱鹭', 'series': ''},
    'なすの': {'cn_name': '那须野', 'series': ''},
    'のぞみ': {'cn_name': '希望', 'series': ''},
    'はくたか': {'cn_name': '白鹰', 'series': ''},
    'はやて': {'cn_name': '疾风', 'series': ''},
    'はやぶさ': {'cn_name': '隼', 'series': ''},
    'ひかり': {'cn_name': '光', 'series': ''},
    'みずほ': {'cn_name': '瑞穗', 'series': ''},
    'やまびこ': {'cn_name': '山彦', 'series': ''}
}


@retry(stop_max_attempt_number=10, wait_fixed=1000)
def get_stations():
    """
    获取所有新干线站点列表
    """
    url = base_url + '/time/shinkansen.html'
    r = requests.get(url, headers=headers, )
    soup = BeautifulSoup(r.text, "html.parser")
    div_elements = soup.find_all('div', class_='section_none')
    _stations = set()
    for div in div_elements:
        a_elements = div.find_all('a')
        for a in a_elements:
            _stations.add(Station(a.text, a['href']))
    return sorted(list(_stations), key=lambda x: x.name)


@retry(stop_max_attempt_number=10, wait_fixed=1000)
def get_schedules(_station, _date, reverse_direction=True):
    """
    获取一个站点下的班次列表
    """
    url = base_url + _station.url + _date.strftime("?Ddd=%d&Dym=%Y%m")
    r = requests.get(url, headers=headers, )
    soup = BeautifulSoup(r.text, "html.parser")
    table_elements = soup.find_all('table', class_='timetable2')
    _schedules = set()
    for div in table_elements:
        a_elements = div.find_all('a')
        for a in a_elements:
            href = clean_params(a['href'])
            name = a.select_one('span').text
            _schedules.add(Schedule(name, href))
    if reverse_direction:
        bk = soup.find_all('a', class_='tab')
        if len(bk) > 1:
            print("多个反向班次!!!" + _station.url)
        for a in bk:
            href = a['href']
            name = _station.name
            reverse_schedules = get_schedules(Station(name, href), _date, False)
            _schedules.update(reverse_schedules)

    return sorted(list(_schedules), key=lambda x: x.name)


@retry(stop_max_attempt_number=10, wait_fixed=1000)
def get_schedule_stations(_schedule, _date):
    """
    获取一个班次下的所有站点信息
    """
    # 解析URL
    parsed_url = urlparse(_schedule.url)
    # 获取查询参数字典
    params = parse_qs(parsed_url.query)
    _schedule_infos = []
    url = base_url + _schedule.url + _date.strftime("&Ddd=%d&Dym=%Y%m")
    r = requests.get(url, headers=headers, )
    soup = BeautifulSoup(r.text, "html.parser")
    title = soup.find('h1', class_='time').text
    name, cn_name, number, series, direction = parse_title(title)

    # 查找所有class为"js_rosenEki"的元素
    eki_elements = soup.find_all("tr", class_="js_rosenEki")
    for eki in eki_elements:
        stop_name = eki.find("td", class_="eki").text.strip()
        time = eki.find("td", class_="time").text.strip().replace(" 発", "").replace(" 着", "")
        info_url = eki.find("a", class_="noprint")["href"]

        _schedule_infos.append(
            ScheduleStation(int(params['lid'][0]), name, cn_name, number, series, direction, stop_name,
                            _date.strftime("%Y-%m-%d"), time, base_url + info_url))
    return _schedule_infos


def clean_params(url):
    # 解析URL
    parsed_url = urlparse(url)
    # 获取查询参数字典
    params = parse_qs(parsed_url.query)
    # 只保留'lid'参数
    if 'lid' in params:
        new_params = {'lid': params['lid']}
    else:
        new_params = {}
    # 重新构建URL
    new_query = urlencode(new_params, doseq=True)
    new_url = urlunparse(
        (parsed_url.scheme, parsed_url.netloc, parsed_url.path, parsed_url.params, new_query, parsed_url.fragment))
    return new_url


def parse_title(text):
    """
    从标题中解析出车次部分信息
    """
    # 使用正则表达式来匹配信息，允许车型信息可选，并排除括号
    pattern = r'^(.*?)\d+号(?:\((.*?)\))? *\((.*?)行\)の運行表$'
    match = re.match(pattern, text)

    if match:
        name = match.group(1)
        series = match.group(2) if match.group(2) else None
        direction = match.group(3)
        number = re.search(r'\d+', text).group()
    else:
        name = None
        series = None
        direction = None
        number = None
    cn_name = name_map[name]['cn_name'] if name in name_map else name
    return name, cn_name, number, series, direction


# Function to create SQLite table
def create_schedule_table():
    conn = sqlite3.connect('schedule_info.sqlite')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS schedule_info (
            id TEXT PRIMARY KEY,
            schedule_id TEXT,
            name TEXT,
            cn_name TEXT,
            number TEXT,
            series TEXT,
            direction TEXT,
            stop_name TEXT,
            date TEXT,
            time TEXT,
            stop_info_url TEXT
        )
    ''')

    conn.commit()
    conn.close()


# Function to insert data into SQLite table
def insert_schedule_data(schedule_info):
    conn = sqlite3.connect('schedule_info.sqlite')
    cursor = conn.cursor()

    for _info in schedule_info:
        cursor.execute('''
            REPLACE INTO schedule_info (id, schedule_id, name,cn_name, number, series, direction,stop_name, date, time, stop_info_url) VALUES (:id, :schedule_id, :name,:cn_name, :number, :series, :direction,:stop_name, :date, :time, :stop_info_url)
        ''', _info.to_dict())

    conn.commit()
    conn.close()


if __name__ == '__main__':
    # 获取当前日期
    today = datetime.now()
    # 计算未来三天的日期
    future_dates = [today + timedelta(days=i) for i in range(3)]

    # 创建 SQLite 表
    create_schedule_table()
    # 获取所有的站点列表
    stations = get_stations()


    # stations = [Station('東京', '/time/timetable/新横浜/新幹線のぞみ/名古屋/')]

    for date in future_dates:
        schedules_set = set()
        schedule_infos = []
        tqdm_stations = tqdm(stations, desc="加载[" + date.strftime('%Y%m%d') + "]站点信息...", ncols=150)
        for station in tqdm_stations:
            schedules = get_schedules(station, date)
            schedules_set.update(schedules)
        all_schedules = sorted(schedules_set, key=lambda x: x.name)
        tqdm_schedules = tqdm(all_schedules, desc="加载[" + date.strftime('%Y%m%d') + "]班次信息...", ncols=150)
        for schedule in tqdm_schedules:
            infos = get_schedule_stations(schedule, date)
            # 将 schedule_infos 写入 SQLite 文件
            insert_schedule_data(infos)
            for info in infos:
                schedule_infos.append(info)
        # 按天写入json文件
        with open('schedule_info_' + date.strftime('%Y%m%d') + '.json', 'w', encoding='utf-8') as json_file:
            json.dump([schedule.to_dict() for schedule in schedule_infos], json_file, ensure_ascii=False, indent=4)


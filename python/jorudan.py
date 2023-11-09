from bs4 import BeautifulSoup
import requests
import requests_cache
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from retrying import retry
import re
import sqlite3
import json
from tqdm import tqdm

# 启用缓存,缓存有效期为24小时
requests_cache.install_cache('requests_cache', expire_after=60 * 60 * 24)
headers = {'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:22.0) Gecko/20100101 Firefox/22.0'}
base_url = 'https://www.jorudan.co.jp'


@retry(stop_max_attempt_number=10, wait_fixed=1000)
def get_station_url():
    url = base_url + '/time/shinkansen.html'
    r = requests.get(url, headers=headers, )
    soup = BeautifulSoup(r.text, "html.parser")
    div_elements = soup.find_all('div', class_='section_none')
    _station_urls = set()
    for div in div_elements:
        a_elements = div.find_all('a')
        for a in a_elements:
            _station_urls.add(a['href'])
    return sorted(list(_station_urls))


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


@retry(stop_max_attempt_number=10, wait_fixed=1000)
def get_schedule_url(_station_url):
    url = base_url + _station_url
    r = requests.get(url, headers=headers, )
    soup = BeautifulSoup(r.text, "html.parser")
    table_elements = soup.find_all('table', class_='timetable2')
    _station_urls = set()
    for div in table_elements:
        a_elements = div.find_all('a')
        for a in a_elements:
            href = clean_params(a['href'])
            _station_urls.add(href)
    return sorted(list(_station_urls))


@retry(stop_max_attempt_number=10, wait_fixed=1000)
def get_schedule_info(_schedule_url):
    # 解析URL
    parsed_url = urlparse(_schedule_url)
    # 获取查询参数字典
    params = parse_qs(parsed_url.query)
    station_info = []
    url = base_url + _schedule_url
    r = requests.get(url, headers=headers, )
    soup = BeautifulSoup(r.text, "html.parser")
    name = soup.find('h1', class_='time').text
    info = extract_information(name)

    # 查找所有class为"js_rosenEki"的元素
    eki_elements = soup.find_all("tr", class_="js_rosenEki")
    for eki in eki_elements:
        name = eki.find("td", class_="eki").text.strip()
        time = eki.find("td", class_="time").text.strip().replace(" 発", "").replace(" 着", "")
        info_url = eki.find("a", class_="noprint")["href"]

        station_info.append({
            'Id': int(params['lid'][0]),
            'Name': info['Name'],
            'Number': info['Number'],
            'Series': info['Series'],
            'Direction': info['Direction'],
            "StopName": name,
            "Time": time,
            "StopInfoURL": base_url + info_url
        })
    return station_info


def extract_information(text):
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
    return {
        'Name': name,
        'Number': number,
        'Series': series,
        'Direction': direction
    }


# Function to create SQLite table
def create_schedule_table():
    conn = sqlite3.connect('schedule_info.sqlite')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS schedule_info (
            Id TEXT,
            Name TEXT,
            Number TEXT,
            Series TEXT,
            Direction TEXT,
            StopName TEXT,
            Time TEXT,
            StopInfoURL TEXT
        )
    ''')

    conn.commit()
    conn.close()


# Function to insert data into SQLite table
def insert_schedule_data(schedule_info):
    conn = sqlite3.connect('schedule_info.sqlite')
    cursor = conn.cursor()

    for info in schedule_info:
        cursor.execute('''
            INSERT INTO schedule_info VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            info['Id'], info['Name'], info['Number'], info['Series'], info['Direction'], info['StopName'], info['Time'],
            info['StopInfoURL']))

    conn.commit()
    conn.close()


if __name__ == '__main__':
    # 创建 SQLite 表
    create_schedule_table()
    station_urls = get_station_url()
    schedule_urls_set = set()
    for station_url in tqdm(station_urls, desc="加载站点信息...", ncols=100):
        urls = get_schedule_url(station_url)
        schedule_urls_set.update(urls)
    schedule_urls = sorted(schedule_urls_set)
    schedule_infos = []
    for schedule_url in tqdm(schedule_urls, desc="加载班次信息...", ncols=100):
        infos = get_schedule_info(schedule_url)
        # 将 schedule_infos 写入 SQLite 文件
        insert_schedule_data(infos)
        for info in get_schedule_info(schedule_url):
            schedule_infos.append(info)

    # 将 schedule_infos 写入 JSON 文件
    with open('schedule_infos.json', 'w', encoding='utf-8') as json_file:
        json.dump(schedule_infos, json_file, ensure_ascii=False, indent=4)

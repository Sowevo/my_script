from bs4 import BeautifulSoup
import requests
import requests_cache
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from retrying import retry
import re

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
        time = eki.find("td", class_="time").text.strip().replace(" 発", "")
        info_url = eki.find("a", class_="noprint")["href"]

        station_info.append({
            'Id': params['lid'][0],
            'Name': info['Name'],
            'Number': info['Number'],
            'Series': info['Series'],
            'Direction': info['Direction'],
            "StopName": name,
            "Time": time,
            "StopInfoURL": base_url+info_url
        })
    return station_info


def extract_information(text):
    # 使用正则表达式来匹配信息，允许车型信息可选，并排除括号
    pattern = r'^(.*?)\d+号(?:\((.*?)系\))? *\((.*?)行\)の運行表$'
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


if __name__ == '__main__':
    station_urls = get_station_url()
    schedule_urls_set = set()
    for station_url in station_urls:
        urls = get_schedule_url(station_url)
        schedule_urls_set.update(urls)
    schedule_urls = sorted(schedule_urls_set)
    schedule_infos = []
    for schedule_url in schedule_urls:
        schedule_infos.extend(get_schedule_info(schedule_url))
    for schedule_info in schedule_infos:
        print(schedule_info)

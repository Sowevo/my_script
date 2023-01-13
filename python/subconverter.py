# 方便进行subconverter参数拼接的脚本
import yaml
import base64
import requests
from urllib.parse import urlencode


def get_short_url(url):
    payload = {'longUrl': base64.b64encode(url.encode("utf-8"))}
    response = requests.request("POST", 'https://v1.mk/short', data=payload)
    return response.json()['ShortUrl']


def get_config():
    with open("subconverter.yaml", "r") as stream:
        data = yaml.safe_load(stream)
        return data


def get_param(service_subconverter, subconverter):
    # 定义一个参数字典,先加入全局参数,再加入个性化参数,重复的覆盖
    param = {}
    _param_str = ""
    for key, value in subconverter.items():
        param[key] = value
    for key, value in service_subconverter.items():
        param[key] = value
    return param


def get_url(_service, _config, _type):
    extend_url = _config['extend_url']
    subconverter_url = _config['subconverter_url']
    subconverter = _config['subconverter']
    service_subconverter = _service['subconverter']
    name = _service['name']
    site = _service['site']
    param = get_param(service_subconverter, subconverter)
    if _type == 'CLASH':
        param['target'] = 'clashr'
    elif _type == 'HOME':
        param['target'] = 'clashr'
        param['url'] = param['url'] + '|' + extend_url
    elif _type == 'SURGE':
        param['target'] = 'surge'
        param['ver'] = '4'
        param['url'] = param['url'] + '|' + extend_url
    param['filename'] = name + '_' + _type + '.yaml'
    url = subconverter_url + '?' + urlencode(param)
    short_url = get_short_url(url)
    return '|[' + name + '](' + site + ')|' + _type + '|[' + short_url + '](' + url + ')|'


config = get_config()
services = config['services']
print('| 机场  | 类型 | 链接  |')
print('| :----: | :----: | :----: |')
for service in services:
    clash_url = get_url(service, config, 'CLASH')
    home_url = get_url(service, config, 'HOME')
    surge_url = get_url(service, config, 'SURGE')
    print(clash_url)
    print(home_url)
    print(surge_url)

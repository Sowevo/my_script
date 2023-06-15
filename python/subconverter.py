import yaml
import base64
import requests
from urllib.parse import urlencode
from retrying import retry


@retry(stop_max_attempt_number=10, wait_fixed=1000)
def get_short_url(url):
    payload = {'longUrl': base64.b64encode(url.encode("utf-8"))}
    response = requests.request("POST", 'https://v1.mk/short', data=payload)
    try:
        url = response.json()['ShortUrl']
        return url
    except Exception:
        raise Exception("<!--获取短连接失败-->")


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
        param['url'] = param['url'] + '|tag:HO,' + extend_url
        param['rename'] = param['rename'] + '`!!GROUP=HO!!^@[HO]'
    elif _type == 'SURGE':
        param['target'] = 'surge'
        param['ver'] = '4'
        param['url'] = param['url'] + '|tag:HO,' + extend_url
        param['rename'] = param['rename'] + '`!!GROUP=HO!!^@[HO]'
    param['filename'] = name + '_' + _type + '.yaml'
    url = subconverter_url + '?' + urlencode(param)
    short_url = get_short_url(url)
    return '|[' + name + '](' + site + ')|' + _type + '|[' + short_url + '](' + url + ')|'


config = get_config()
services = config['services']
# 补充tag信息
for service in services:
    if hasattr(service, 'short_name'):
        short_name = service['short_name']
    else:
        short_name = service['name'][0: 2]
    service['subconverter']['url'] = 'tag:' + short_name + ',' + service['subconverter']['url']
    service['subconverter']['rename'] = '!!GROUP='+short_name+'!!^@['+short_name+']'

mix_urls = []
mix_renames = []
param = {}
# 找出来需要混合的!
for service in services:
    if service['mix']:
        mix_urls.append(service['subconverter']['url'])
        mix_renames.append(service['subconverter']['rename'])
        for key, value in service['subconverter'].items():
            param[key] = value
if len(mix_urls):
    mix_service = {'name': '混合', 'site': 'https://baidu.com'}
    param.update({'url': '|'.join(mix_urls), 'rename': '`'.join(mix_renames)})
    mix_service['subconverter'] = param
    services.append(mix_service)

print('| 机场  | 类型 | 链接  |')
print('| :----: | :----: | :----: |')
for service in services:
    clash_url = get_url(service, config, 'CLASH')
    print(clash_url)
    home_url = get_url(service, config, 'HOME')
    print(home_url)
    surge_url = get_url(service, config, 'SURGE')
    print(surge_url)
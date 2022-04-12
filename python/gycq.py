from bs4 import BeautifulSoup
import os
import json
import hmac
import time
import base64
import hashlib
import requests
import urllib.parse

# 从环境变量中获取钉钉消息的配置
# 可以直接修改为自己的
if "DD_BOT_TOKEN" in os.environ and os.environ["DD_BOT_TOKEN"] \
        and "DD_BOT_SECRET" in os.environ and os.environ["DD_BOT_SECRET"]:
    DD_BOT_TOKEN = os.environ["DD_BOT_TOKEN"]
    DD_BOT_SECRET = os.environ["DD_BOT_SECRET"]


def query():
    # 准备数据
    base_url = 'http://gycq.zjw.beijing.gov.cn'
    home_url = base_url + '/enroll/home.jsp'
    data_url = base_url + '/enroll/dyn/enroll/viewEnrollHomePager.json'
    headers = {'Content-Type': 'application/json'}
    data = json.dumps({"currPage": 1, "pageJSMethod": "goToPage"})

    # 请求
    session = requests.session()
    session.get(home_url)
    response = session.post(url=data_url, data=data, headers=headers)

    # 解析
    encode_json = json.loads(response.text)
    date = encode_json['data']
    return date


def parse(date):
    soup = BeautifulSoup(date, 'html.parser')

    proj_infos = soup.find_all(class_="ProjInfo")

    msg = ''
    for proj_info in proj_infos:
        link = proj_info.find('a', {'class': "F14"}, 'href')['href']
        ths = proj_info.select('tbody > tr > th')
        for index, th in enumerate(ths):

            if index == 0:
                msg = msg + '# **' + th.text + '** '
                msg = msg + '[' + th.next_sibling.text + '](' + link + ')\n\n'
            elif index == 5:
                map_link = 'https://amap.com/search?query=' + th.next_sibling.text + '&city=110000'
                msg = msg + '**' + th.text + '** '
                msg = msg + '[' + th.next_sibling.text + '](' + map_link + ')\n\n'
            else:
                msg = msg + '**' + th.text + '** '
                msg = msg + th.next_sibling.text + '\n\n'

        msg = msg + '***\n\n'
    title = '共有产权住房项目提醒'
    dingding_bot(title, msg)


def dingding_bot(title, content):
    timestamp = str(round(time.time() * 1000))  # 时间戳
    secret_enc = DD_BOT_SECRET.encode('utf-8')
    string_to_sign = '{}\n{}'.format(timestamp, DD_BOT_SECRET)
    string_to_sign_enc = string_to_sign.encode('utf-8')
    hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))  # 签名
    print('开始使用 钉钉机器人 推送消息...', end='')
    url = f'https://oapi.dingtalk.com/robot/send?access_token={DD_BOT_TOKEN}&timestamp={timestamp}&sign={sign}'
    headers = {'Content-Type': 'application/json;charset=utf-8'}
    data = {
        'msgtype': 'markdown',
        'markdown': {
            "title": f'{title}',
            'text': f'{content}'
        }
    }
    response = requests.post(url=url, data=json.dumps(data), headers=headers, timeout=15).json()
    if not response['errcode']:
        print('推送成功！')
    else:
        print('推送失败！')


def main():
    date = query()
    parse(date)


if __name__ == '__main__':
    main()

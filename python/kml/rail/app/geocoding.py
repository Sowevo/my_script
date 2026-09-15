"""在线地名定位：手动提交查询，缓存结果并限制公共服务请求频率。"""

from collections import OrderedDict
import json
import logging
import math
import os
import threading
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)


class Geocoder:
    def __init__(self):
        self.endpoint = os.environ.get('RAIL_GEOCODER_URL', 'https://nominatim.openstreetmap.org/search')
        self.cache = OrderedDict()
        self.lock = threading.Lock()
        self.last_request = None

    def search(self, query):
        # 查询只在用户提交时发生，不做逐字自动补全。单进程串行请求不超过每秒一次。
        with self.lock:
            now = time.monotonic()
            cached = self.cache.get(query)
            if cached and now - cached[0] < 86400:
                self.cache.move_to_end(query)
                return cached[1]
            params = urlencode({'q': query, 'format': 'jsonv2', 'limit': 5,
                                'accept-language': 'zh-CN,zh,ja,en'})
            request = Request(self.endpoint + '?' + params, headers={
                'User-Agent': 'RailExplorer/1.0 (local interactive railway map)',
                'Accept': 'application/json',
            })
            for attempt in range(2):
                if self.last_request is not None:
                    time.sleep(max(0, 1.05 - (time.monotonic() - self.last_request)))
                self.last_request = time.monotonic()
                try:
                    with urlopen(request, timeout=12) as response:
                        payload = json.load(response)
                    break
                except HTTPError:
                    # 服务拒绝或限流时不立即重试。
                    raise
                except (URLError, OSError) as error:
                    logger.warning('地名服务连接失败（第%d次）：%r', attempt + 1, error)
                    if attempt:
                        raise
            if not isinstance(payload, list):
                raise ValueError('Invalid geocoder response')
            results = []
            for item in payload[:5]:
                lat, lon = float(item['lat']), float(item['lon'])
                if not (math.isfinite(lat) and math.isfinite(lon)
                        and -90 <= lat <= 90 and -180 <= lon <= 180):
                    continue
                bounds = None
                raw = item.get('boundingbox', [])
                if len(raw) == 4:
                    south, north, west, east = map(float, raw)
                    if -90 <= south <= north <= 90 and -180 <= west <= east <= 180:
                        bounds = [[south, west], [north, east]]
                results.append({'name': str(item.get('display_name', query)),
                                'lat': lat, 'lon': lon, 'bounds': bounds})
            self.cache[query] = (time.monotonic(), results)
            self.cache.move_to_end(query)
            while len(self.cache) > 256:
                self.cache.popitem(last=False)
            return results

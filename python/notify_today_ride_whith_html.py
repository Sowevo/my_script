#!/usr/bin/env python3
"""
NIU 骑行统计脚本
================

功能简介
--------
* 自动登录 NIU 账号获取访问 token，并选取默认车辆（或自定义 SN）。
* 支持按 “日/周/月” 三种周期汇总骑行总里程、总次数、平均速度及单次最长行程。
* 支持指定参考日期（`--target-date`）和周起始日（`--week-start`），方便回溯历史周期。
* 自动分页读取行程数据，直到覆盖所需日期范围，避免遗漏月初或大量骑行记录。
* 自动缓存 token，优先使用 refresh_token 刷新，减少重复登录。
* 生成 Bark 推送，包含官方图标、`niu://` 跳转、可自定义分组/提示音/图片，推送内容精简为四字字段。

快速使用
--------
python3 notify_today_ride.py -b <BarkKey> -a <NIU账号> -p <明文密码>

常用示例
--------
1. 获取当天数据:
   python3 notify_today_ride.py -b xxx -a you@niu.com -p password

2. 获取本周数据 (周一为一周起点):
   python3 notify_today_ride.py -b xxx -a you@niu.com -p password --period week --week-start 1

3. 获取指定日期所在月的统计:
   python3 notify_today_ride.py -b xxx -a you@niu.com -p password --period month --target-date 20251116

参数说明
--------
-b/--bark-key     Bark 推送 key，可用环境变量 BARK_KEY
-a/--niu-account  NIU 账号，可用环境变量 NIU_ACCOUNT
-p/--niu-password NIU 明文密码，可用环境变量 NIU_PASSWORD
NIU_TOKEN_CACHE   token 缓存文件路径 (默认 ./niu_token_cache.bin)
可选参数详见 `python3 notify_today_ride.py --help`

作者：Codex（使用本脚本发生的玄学问题都算 Codex 的）
"""
import argparse
import base64
import datetime as dt
import hashlib
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

BARK_ENDPOINT = os.environ.get("BARK_ENDPOINT", "https://api.day.app/push")
BARK_ICON_URL = os.environ.get(
    "BARK_ICON_URL",
    "https://is1-ssl.mzstatic.com/image/thumb/Purple211/v4/36/ad/88/36ad8879-edd0-3b27-7069-e70e58ea8b65/AppIcon-1x_U007emarketing-0-5-0-sRGB-85-220-0.png/96x96ia-75.webp",
)
BARK_OPEN_URL = os.environ.get("BARK_OPEN_URL", "niu://")
NIU_SN = os.environ.get("NIU_SN", "")
TRACK_PAGE_SIZE = int(os.environ.get("TRACK_PAGE_SIZE", "50"))
TARGET_TZ = "Asia/Shanghai"
TARGET_DATE = os.environ.get("TARGET_DATE", "")
NIU_APP_ID = "niu_ktdrr960"
NIU_SCOPE = "base"
NIU_USER_AGENT = (
    "manager/5.7.4 (android; OPPO R9s 9);lang=zh-CN;clientIdentifier=Domestic;"
    "timezone=Asia/Shanghai;model=OPPO_OPPO R9s;deviceName=OPPO R9s;ostype=android"
)
PERIOD = os.environ.get("PERIOD", "day").lower()
WEEK_START = int(os.environ.get("WEEK_START", "1"))
BARK_GROUP = os.environ.get("BARK_GROUP", "niu-rides")
BARK_SOUND = os.environ.get("BARK_SOUND", "shake")
TOKEN_CACHE_PATH = Path(os.environ.get("NIU_TOKEN_CACHE", os.path.abspath("niu_token_cache.bin")))
ACCOUNT_API_BASE = "https://account.niu.com"
DATA_API_BASE = "https://app-api.niu.com"
MAPBOX_ACCESS_TOKEN = os.environ.get("MAPBOX_ACCESS_TOKEN", "")
MAPBOX_STYLE = os.environ.get("MAPBOX_STYLE", "mapbox://styles/mapbox/streets-v12")


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def hash_password(password: str) -> str:
    """NIU 登录接口需要 32 位 MD5。"""
    return hashlib.md5(password.encode("utf-8")).hexdigest()


def normalize_account(account: str) -> str:
    """归一化账号（去空格并小写）以供缓存键使用。"""
    return account.strip().lower()


def ensure_dependencies() -> None:
    """命令行参数或环境变量的合法性检查。"""
    if PERIOD not in {"day", "week", "month"}:
        sys.exit("PERIOD 仅支持 day/week/month")
    if WEEK_START < 1 or WEEK_START > 7:
        sys.exit("WEEK_START 必须在 1-7 之间")
    if TRACK_PAGE_SIZE <= 0:
        sys.exit("TRACK_PAGE_SIZE 必须为正整数")


def current_date_str() -> str:
    tz = ZoneInfo(TARGET_TZ) if ZoneInfo else None
    now = dt.datetime.now(tz)
    return now.strftime("%Y%m%d")


def target_date() -> str:
    return TARGET_DATE or current_date_str()


def compute_period_bounds(date_str: str) -> Tuple[str, str]:
    """根据参考日期和周期(day/week/month)计算统计区间。"""
    base = dt.datetime.strptime(date_str, "%Y%m%d").date()
    start = base
    end = base
    if PERIOD == "week":
        desired = (WEEK_START - 1) % 7
        delta = (base.weekday() - desired) % 7
        start = base - dt.timedelta(days=delta)
        end = start + dt.timedelta(days=6)
    elif PERIOD == "month":
        start = base.replace(day=1)
        if start.month == 12:
            next_month = dt.date(start.year + 1, 1, 1)
        else:
            next_month = dt.date(start.year, start.month + 1, 1)
        end = next_month - dt.timedelta(days=1)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


PI = math.pi
EE = 0.00669342162296594323
EARTH_A = 6378245.0


def _transform_lat(x: float, y: float) -> float:
    ret = (
        -100.0
        + 2.0 * x
        + 3.0 * y
        + 0.2 * y * y
        + 0.1 * x * y
        + 0.2 * math.sqrt(abs(x))
    )
    ret += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * PI) + 40.0 * math.sin(y / 3.0 * PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * PI) + 320.0 * math.sin(y * PI / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lng(x: float, y: float) -> float:
    ret = (
        300.0
        + x
        + 2.0 * y
        + 0.1 * x * x
        + 0.1 * x * y
        + 0.1 * math.sqrt(abs(x))
    )
    ret += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * PI) + 40.0 * math.sin(x / 3.0 * PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * PI) + 300.0 * math.sin(x / 30.0 * PI)) * 2.0 / 3.0
    return ret


def _out_of_china(lng: float, lat: float) -> bool:
    """简单判断是否在国界外，国界外无需偏移。"""
    return not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271)


def gcj02_to_wgs84(lng: float, lat: float) -> Tuple[float, float]:
    """将 GCJ-02(火星) 坐标反算成 WGS84，方便在 OSM/Leaflet 上正确展示。"""
    if _out_of_china(lng, lat):
        return lng, lat
    dlat = _transform_lat(lng - 105.0, lat - 35.0)
    dlng = _transform_lng(lng - 105.0, lat - 35.0)
    rad_lat = lat / 180.0 * PI
    magic = math.sin(rad_lat)
    magic = 1 - EE * magic * magic
    sqrt_magic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((EARTH_A * (1 - EE)) / (magic * sqrt_magic) * PI)
    dlng = (dlng * 180.0) / (EARTH_A / sqrt_magic * math.cos(rad_lat) * PI)
    mg_lat = lat + dlat
    mg_lng = lng + dlng
    return lng - (mg_lng - lng), lat - (mg_lat - lat)


def http_json(url: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """POST 请求并解析 JSON 响应，异常时报出详细信息。"""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    req.add_header("Accept", "*/*")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"请求 {url} 失败: {e.code} {raw}") from e
    except urllib.error.URLError as e:  # pragma: no cover
        raise RuntimeError(f"请求 {url} 失败: {e}") from e
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"解析 {url} 响应失败: {raw}") from e


def login(account: str, password_md5: str) -> str:
    """登录 NIU 账户并返回完整 token 信息。"""
    payload = {
        "account": account,
        "password": password_md5,
        "scope": NIU_SCOPE,
        "grant_type": "password",
        "app_id": NIU_APP_ID,
    }
    headers = {"User-Agent": NIU_USER_AGENT}
    resp = http_json(f"{ACCOUNT_API_BASE}/v3/api/oauth2/token", payload, headers)
    token_info = resp.get("data", {}).get("token", {})
    if not token_info.get("access_token"):
        raise RuntimeError(f"登录失败: {resp}")
    return token_info


def refresh_access_token(refresh_token: str) -> Dict[str, Any]:
    """使用 refresh_token 换取新的令牌。"""
    if not refresh_token:
        raise RuntimeError("缺少 refresh_token")
    payload = {
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
        "scope": NIU_SCOPE,
        "app_id": NIU_APP_ID,
    }
    headers = {"User-Agent": NIU_USER_AGENT}
    resp = http_json(f"{ACCOUNT_API_BASE}/v3/api/oauth2/token", payload, headers)
    token_info = resp.get("data", {}).get("token", {})
    if not token_info.get("access_token"):
        raise RuntimeError(f"刷新 token 失败: {resp}")
    return token_info


def load_token_cache(path: Path) -> Dict[str, Any]:
    """读取 token 缓存文件。"""
    try:
        with path.open("r", encoding="utf-8") as fh:
            encoded = fh.read()
            if not encoded:
                return {}
            raw = base64.b64decode(encoded.encode("utf-8")).decode("utf-8")
            return json.loads(raw)
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, ValueError, base64.binascii.Error):
        return {}


def save_token_cache(path: Path, data: Dict[str, Any]) -> None:
    """写入 token 缓存文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(data, ensure_ascii=False)
    encoded = base64.b64encode(raw.encode("utf-8")).decode("utf-8")
    with path.open("w", encoding="utf-8") as fh:
        fh.write(encoded)


def compute_expiry(raw_value: Any, default_seconds: int) -> int:
    """将可能为绝对或相对的过期字段转换为绝对时间戳。"""
    now = int(time.time())
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = 0
    if value > now + 60:
        return value
    if value > 0:
        return now + value
    return now + default_seconds


def token_entry_from_info(token_info: Dict[str, Any]) -> Dict[str, Any]:
    """从接口返回构建缓存条目。"""
    return {
        "access_token": token_info.get("access_token", ""),
        "refresh_token": token_info.get("refresh_token", ""),
        "token_expires_at": compute_expiry(token_info.get("token_expires_in"), 6 * 3600),
        "refresh_expires_at": compute_expiry(token_info.get("refresh_token_expires_in"), 30 * 24 * 3600),
    }


def is_token_valid(expiry: int, margin: int = 300) -> bool:
    """判断令牌是否在 margin 时间内即将过期。"""
    if expiry <= 0:
        return False
    return int(time.time()) < expiry - margin


def obtain_access_token(account: str, password_md5: str, cache_path: Path) -> str:
    """优先使用缓存/刷新，必要时重新登录以获取 token。"""
    cache = load_token_cache(cache_path)
    key = normalize_account(account)
    entry = cache.get(key)

    if entry and is_token_valid(entry.get("token_expires_at", 0)):
        log("使用缓存 access_token")
        return entry["access_token"]

    if entry and entry.get("refresh_token") and is_token_valid(entry.get("refresh_expires_at", 0)):
        try:
            token_info = refresh_access_token(entry["refresh_token"])
            new_entry = token_entry_from_info(token_info)
            cache[key] = new_entry
            save_token_cache(cache_path, cache)
            log("使用 refresh_token 刷新 access_token 成功")
            return new_entry["access_token"]
        except RuntimeError as err:
            log(f"刷新 token 失败，改为重新登录: {err}")

    token_info = login(account, password_md5)
    new_entry = token_entry_from_info(token_info)
    cache[key] = new_entry
    save_token_cache(cache_path, cache)
    log("重新登录获取 access_token")
    return new_entry["access_token"]


def fetch_sn(access_token: str, preferred_sn: str) -> str:
    """优先使用用户指定的 SN，否则读取账号下的默认车辆。"""
    if preferred_sn:
        return preferred_sn
    req = urllib.request.Request(f"{DATA_API_BASE}/v5/scooter/list")
    req.add_header("User-Agent", NIU_USER_AGENT)
    req.add_header("token", access_token)
    req.add_header("Accept", "*/*")
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
    data = json.loads(raw)
    items = data.get("data", {}).get("items", [])
    for item in items:
        if item.get("isDefault"):
            sn = item.get("sn_id")
            if sn:
                return sn
    if items:
        return items[0].get("sn_id", "")
    raise RuntimeError("无法获取设备 SN")


def to_int(value: Any) -> int:
    """安全地将任意值转换为 int，非法值返回 0。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def to_float(value: Any) -> Optional[float]:
    """安全地将任意值转换为 float，非法值返回 None。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def speed_to_color(speed: float) -> str:
    """根据均速返回颜色（低速黄色，高速红色）。"""
    min_color = (255, 213, 0)  # #ffd500
    max_color = (215, 48, 39)  # #d73027
    ratio = max(0.0, min(speed, 30.0)) / 30.0
    r = int(min_color[0] + (max_color[0] - min_color[0]) * ratio)
    g = int(min_color[1] + (max_color[1] - min_color[1]) * ratio)
    b = int(min_color[2] + (max_color[2] - min_color[2]) * ratio)
    return f"#{r:02x}{g:02x}{b:02x}"


def first_valid_float(container: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[float]:
    """根据候选键列表提取首个可转换为 float 的值。"""
    for key in keys:
        if key in container:
            val = to_float(container.get(key))
            if val is not None:
                return val
    return None


def collect_tracks(access_token: str, sn: str, min_date_cutoff: int) -> List[Dict[str, Any]]:
    """分页拉取行程，直到数据不足一页或已覆盖目标日期。"""
    index = 0
    all_items: List[Dict[str, Any]] = []
    headers = {"User-Agent": NIU_USER_AGENT, "token": access_token, "Accept": "*/*"}
    # 循环分页获取行程，直到行数不足一页或触达周期开始日期
    while True:
        payload = {"index": str(index), "pagesize": TRACK_PAGE_SIZE, "sn": sn}
        resp = http_json(f"{DATA_API_BASE}/v5/track/list/v2", payload, headers)
        status = resp.get("status")
        if status not in (0, "0", None):
            raise RuntimeError(f"获取行程列表失败({status}): {resp}")
        items = resp.get("data", {}).get("items", []) or []
        all_items.extend(items)
        if len(items) < TRACK_PAGE_SIZE:
            break
        oldest_date = to_int(items[-1].get("date"))
        if oldest_date and oldest_date < min_date_cutoff:
            break
        index += len(items)
    return all_items


def filter_tracks(tracks: List[Dict[str, Any]], start: int, end: int) -> List[Dict[str, Any]]:
    """仅保留处于目标日期区间的行程。"""
    result = []
    for item in tracks:
        date_val = to_int(item.get("date"))
        if start <= date_val <= end:
            result.append(item)
    return result


def meters_to_km(meters: int) -> str:
    """把米转为字符串形式的公里数。"""
    return f"{meters / 1000:.2f}"


def avg_speed_kmh(distance_m: int, riding_time_s: int) -> str:
    """根据总里程和骑行秒数计算平均速度（km/h）。"""
    if riding_time_s <= 0:
        return "0.00"
    return f"{(distance_m / riding_time_s) * 3.6:.2f}"


def format_timestamp(ms: Any) -> str:
    """将毫秒时间戳转换为北京时间字符串。"""
    ms_int = to_int(ms)
    if ms_int <= 0:
        return "未知时间"
    tz = ZoneInfo(TARGET_TZ) if ZoneInfo else dt.timezone(dt.timedelta(hours=8))
    dt_obj = dt.datetime.fromtimestamp(ms_int / 1000, tz)
    return dt_obj.strftime("%Y-%m-%d %H:%M")


def trim_year(value: str) -> str:
    """裁掉日期字符串中的年份部分，保留 MM-DD HH:MM。"""
    if len(value) >= 11 and value[4] == "-":
        return value[5:]
    return value


def send_bark(bark_key: str, title: str, body: str, image_url: str) -> None:
    """发送 Bark 推送，附带图像、icon、跳转链接等配置。"""
    payload: Dict[str, Any] = {
        "title": title,
        "body": body,
        "device_key": bark_key,
        "url": BARK_OPEN_URL,
        "isArchive": 1,
        "group": BARK_GROUP,
        "sound": BARK_SOUND,
    }
    if image_url:
        payload["image"] = image_url
    if BARK_ICON_URL:
        payload["icon"] = BARK_ICON_URL
    http_json(BARK_ENDPOINT, payload)


def summarize_period(tracks: List[Dict[str, Any]]) -> Tuple[int, int, Dict[str, Any]]:
    """返回总里程、总骑行时间以及单次最长行程。"""
    total_distance = sum(to_int(t.get("distance")) for t in tracks)
    total_riding = sum(to_int(t.get("ridingtime")) for t in tracks)
    if not tracks:
        raise RuntimeError("没有骑行数据")
    longest = max(tracks, key=lambda t: to_int(t.get("distance")))
    return total_distance, total_riding, longest


def fetch_track_detail(
    access_token: str, sn: str, track_id: str, track_date: Any, track_category: Any
) -> Dict[str, Any]:
    """调用详情接口获取单条行程的轨迹点。"""
    headers: Dict[str, str] = {"User-Agent": NIU_USER_AGENT, "token": access_token, "Accept": "*/*"}
    payload = {
        "date": str(track_date),
        "trackId": track_id,
        # 行程详情接口实测仅接受 trackCategory=1，强制写死避免返回空数据。
        "trackCategory": "1",
        "sn": sn,
    }
    resp = http_json(f"{DATA_API_BASE}/v5/track/detail/v3", payload, headers)
    status = resp.get("status")
    if status not in (0, "0", None):
        raise RuntimeError(f"获取行程详情失败({status}): {resp}")
    return resp.get("data") or {}


def enrich_tracks_with_details(
    access_token: str, sn: str, tracks: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """为每条行程补充轨迹点数据。"""
    detailed: List[Dict[str, Any]] = []
    total = len(tracks)
    for idx, track in enumerate(tracks, 1):
        track_id = track.get("trackId")
        track_date = track.get("date")
        if not track_id or not track_date:
            log(f"跳过缺少 trackId/date 的行程: {track}")
            continue
        track_category = track.get("trackCategory", 0)
        log(f"拉取行程详情 {idx}/{total}: trackId={track_id}")
        detail = fetch_track_detail(access_token, sn, track_id, track_date, track_category)
        detailed.append({"summary": track, "detail": detail})
    return detailed


def extract_track_points(detail: Dict[str, Any], track_id: str) -> List[Dict[str, float]]:
    """从行程详情中提取坐标和速度，并在异常时记录日志。"""
    raw_items = detail.get("trackItems") or []
    if isinstance(raw_items, dict):
        for key in ("items", "trackItems", "list", "data"):
            nested = raw_items.get(key)
            if isinstance(nested, list):
                raw_items = nested
                break
        else:
            log(f"trackId={track_id} 的 trackItems 结构异常: {raw_items}")
            return []
    if not isinstance(raw_items, list):
        log(f"trackId={track_id} 的 trackItems 类型异常: {type(raw_items).__name__}")
        return []
    points: List[Dict[str, float]] = []
    for point in raw_items:
        lng_val: Optional[float] = None
        lat_val: Optional[float] = None
        speed_val: Optional[float] = None
        if isinstance(point, dict):
            lng_val = first_valid_float(point, ("lng", "lon", "longitude", "x"))
            lat_val = first_valid_float(point, ("lat", "latitude", "y"))
            speed_val = to_float(point.get("speed"))
        elif isinstance(point, (list, tuple)) and len(point) >= 2:
            lng_val = to_float(point[0])
            lat_val = to_float(point[1])
        if lng_val is None or lat_val is None:
            continue
        wgs_lng, wgs_lat = gcj02_to_wgs84(lng_val, lat_val)
        points.append({"lng": wgs_lng, "lat": wgs_lat, "speed": speed_val or 0.0})
    if len(points) < 2:
        log(f"trackId={track_id} 轨迹点数量 {len(points)}, 无法绘制完整路径")
    return points


def build_geojson_features(
    detailed_tracks: List[Dict[str, Any]]
) -> Tuple[Dict[str, Any], Optional[Tuple[float, float]], List[Dict[str, Any]]]:
    """把轨迹点转为 GeoJSON FeatureCollection，并返回初始视角和摘要。"""
    features: List[Dict[str, Any]] = []
    summaries: List[Dict[str, Any]] = []
    first_center: Optional[Tuple[float, float]] = None
    for seq, entry in enumerate(detailed_tracks, 1):
        track = entry.get("summary", {})
        detail = entry.get("detail", {})
        track_id = str(track.get("trackId", ""))
        track_points = extract_track_points(detail, track_id)
        distance_m = to_int(track.get("distance"))
        riding_sec = to_int(track.get("ridingtime"))
        avg_speed_val = to_float(track.get("avespeed")) or 0.0
        duration_min = f"{(riding_sec / 60):.1f}" if riding_sec else "0.0"
        start_fmt = trim_year(format_timestamp(track.get("startTime")))
        end_fmt = trim_year(format_timestamp(track.get("endTime")))
        start_time_ms = to_int(track.get("startTime"))
        end_time_ms = to_int(track.get("endTime"))
        color = speed_to_color(avg_speed_val)
        summaries.append(
            {
                "seq": seq,
                "trackId": track_id,
                "distanceKm": meters_to_km(distance_m),
                "durationMin": duration_min,
                "start": start_fmt,
                "end": end_fmt,
                "color": color,
                "startTimeMs": start_time_ms,
                "color": color,
            }
        )
        if len(track_points) < 2:
            continue
        if not first_center:
            first_center = (track_points[0]["lat"], track_points[0]["lng"])
        for idx in range(len(track_points) - 1):
            start_point = track_points[idx]
            end_point = track_points[idx + 1]
            seg_speed = start_point.get("speed") or end_point.get("speed") or avg_speed_val
            seg_color = speed_to_color(seg_speed)
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [start_point["lng"], start_point["lat"]],
                        [end_point["lng"], end_point["lat"]],
                    ],
                },
                "properties": {
                    "seq": seq,
                    "trackId": track_id,
                    "distanceKm": meters_to_km(distance_m),
                    "distanceM": distance_m,
                    "durationMin": duration_min,
                    "avgSpeed": f"{avg_speed_val:.1f}",
                    "start": start_fmt,
                    "end": end_fmt,
                    "power": to_int(track.get("power_consumption")),
                    "color": seg_color,
                    "startTimeMs": start_time_ms,
                    "endTimeMs": end_time_ms,
                    "segmentIndex": idx,
                },
            }
            features.append(feature)
    return {"type": "FeatureCollection", "features": features}, first_center, summaries


def resolve_html_output_path(base: Path, label: str) -> Path:
    """根据用户输入推断输出文件路径。"""
    base_path = base.expanduser()
    if base_path.suffix.lower() == ".html":
        return base_path
    return base_path / f"niu_tracks_{label}.html"


def render_map_html(
    feature_collection: Dict[str, Any],
    meta: Dict[str, Any],
) -> str:
    """生成自包含的 Mapbox GL HTML。"""
    track_json = json.dumps(feature_collection, ensure_ascii=False)
    meta_json = json.dumps(meta, ensure_ascii=False)
    title = meta.get("title", "NIU 行程地图")
    subtitle = meta.get("subtitle", "")
    stats_text = meta.get("statsText", "")
    generated_at = meta.get("generatedAt", "")
    template = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta http-equiv="X-UA-Compatible" content="IE=edge" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{title}</title>
  <link href="https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.css" rel="stylesheet" />
  <style>
    :root {{
      color-scheme: light dark;
    }}
    body {{
      margin: 0;
      font-family: "SF Pro SC", "PingFang SC", "Segoe UI", system-ui, sans-serif;
      background: #111;
      color: #f4f4f4;
    }}
    body.light {{
      background: #fafafa;
      color: #1f1f1f;
    }}
    .summary {{
      padding: 1.5rem;
      border-bottom: 1px solid rgba(255,255,255,0.1);
    }}
    .summary h1 {{
      margin: 0;
      font-size: 1.6rem;
    }}
    .summary p {{
      margin: 0.4rem 0 0;
      font-size: 0.95rem;
    }}
    #map {{
      height: 70vh;
    }}
    .details {{
      padding: 1rem 1.5rem 2rem;
    }}
    .details h2 {{
      margin-top: 0;
      font-size: 1.2rem;
    }}
    #track-list {{
      list-style: none;
      padding: 0;
      margin: 0;
      display: flex;
      flex-direction: column;
      gap: 0.6rem;
    }}
    #track-list li {{
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding-bottom: 0.5rem;
      border-bottom: 1px solid rgba(255,255,255,0.1);
    }}
    .dot {{
      width: 0.85rem;
      height: 0.85rem;
      border-radius: 50%;
      flex-shrink: 0;
    }}
    .empty {{
      margin-top: 1rem;
      font-size: 0.95rem;
      opacity: 0.7;
    }}
    .legend {{
      font-size: 0.9rem;
    }}
    @media (max-width: 768px) {{
      #map {{
        height: 60vh;
      }}
    }}
  </style>
</head>
<body class="light">
  <section class="summary">
    <h1>{title}</h1>
    <p>{subtitle}</p>
    <p>{stats_text}</p>
    <p>生成时间：{generated_at}</p>
  </section>
  <div id="map"></div>
  <section class="details">
    <h2>行程列表</h2>
    <ul id="track-list"></ul>
    <p id="empty-indicator" class="empty" style="display:none;">没有可展示的轨迹。</p>
  </section>
  <script src="https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.js"></script>
  <script>
    const trackData = {track_data};
    const meta = {meta_data};
    const defaultColors = ['#ffd500', '#ffb400', '#ff9000', '#ff5b00', '#d73027'];
    const trackSummaries = meta.trackSummaries || [];
    const trackFeatures = [...(trackData.features || [])];
    trackFeatures.forEach((feature) => {{
      const props = feature.properties || {{}};
      const color =
        props.color || defaultColors[(props.seq - 1 + defaultColors.length) % defaultColors.length];
      feature.properties = {{ ...props, color }};
    }});
    mapboxgl.accessToken = meta.mapboxToken;
    const fallback = meta.fallbackCenter || {{ lat: 39.9042, lng: 116.4074 }};
    const map = new mapboxgl.Map({{
      container: 'map',
      style: meta.mapboxStyle || 'mapbox://styles/mapbox/streets-v12',
      center: [fallback.lng, fallback.lat],
      zoom: 12
    }});
    map.addControl(new mapboxgl.NavigationControl());
    const listEl = document.getElementById('track-list');
    const emptyIndicator = document.getElementById('empty-indicator');
    if (trackData.features.length === 0) {{
      emptyIndicator.style.display = trackSummaries.length === 0 ? 'block' : 'none';
    }}
    const chronologicalFeatures = [...trackFeatures].sort((a, b) => {{
      const aTime = Number(a.properties?.startTimeMs) || 0;
      const bTime = Number(b.properties?.startTimeMs) || 0;
      if (aTime !== bTime) return aTime - bTime;
      return (a.properties?.seq || 0) - (b.properties?.seq || 0);
    }});

    map.on('load', () => {{
      if (trackData.features.length > 0) {{
        map.addSource('tracks', {{
          type: 'geojson',
          data: {{ type: 'FeatureCollection', features: trackFeatures }}
        }});
        if (!map.hasImage('track-arrow')) {{
          const arrowCanvas = document.createElement('canvas');
          arrowCanvas.width = 32;
          arrowCanvas.height = 32;
          const ctx = arrowCanvas.getContext('2d');
          ctx.translate(16, 16);
          ctx.fillStyle = '#ffffff';
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(12, 0);
          ctx.lineTo(-8, 8);
          ctx.lineTo(-8, -8);
          ctx.closePath();
          ctx.fill();
          const imageData = ctx.getImageData(0, 0, 32, 32);
          map.addImage('track-arrow', {{
            width: 32,
            height: 32,
            data: imageData.data,
            pixelRatio: 2
          }});
        }}
        map.addLayer({{
          id: 'tracks-line',
          type: 'line',
          source: 'tracks',
          layout: {{
            'line-join': 'round',
            'line-cap': 'round'
          }},
          paint: {{
            'line-color': ['get', 'color'],
            'line-width': 4,
            'line-opacity': 0.9
          }}
        }});
        map.addLayer({{
          id: 'tracks-arrows',
          type: 'symbol',
          source: 'tracks',
          layout: {{
            'symbol-placement': 'line',
            'symbol-spacing': 40,
            'icon-image': 'track-arrow',
            'icon-size': 0.5,
            'icon-allow-overlap': true,
            'icon-ignore-placement': true,
            'icon-rotation-alignment': 'map'
          }},
          paint: {{
            'icon-color': ['get', 'color']
          }}
        }});
        const connectionFeatures = [];
        for (let i = 0; i < chronologicalFeatures.length - 1; i += 1) {{
          const current = chronologicalFeatures[i];
          const next = chronologicalFeatures[i + 1];
          const currCoords = current.geometry?.coordinates || [];
          const nextCoords = next.geometry?.coordinates || [];
          const start = currCoords[currCoords.length - 1];
          const end = nextCoords[0];
          if (!start || !end) continue;
          connectionFeatures.push({{
            type: 'Feature',
            geometry: {{ type: 'LineString', coordinates: [start, end] }},
            properties: {{
              seqStart: current.properties.seq,
              seqEnd: next.properties.seq
            }}
          }});
        }}
        if (connectionFeatures.length) {{
          map.addSource('track-connections', {{
            type: 'geojson',
            data: {{ type: 'FeatureCollection', features: connectionFeatures }}
          }});
          map.addLayer({{
            id: 'track-connections',
            type: 'line',
            source: 'track-connections',
            layout: {{
              'line-join': 'round',
              'line-cap': 'round'
            }},
            paint: {{
              'line-color': '#ffcc00',
              'line-width': 3,
              'line-opacity': 0.85,
              'line-dasharray': [1.2, 1.2],
              'line-blur': 0.5
            }}
          }});
        }}
        const bounds = new mapboxgl.LngLatBounds();
        trackFeatures.forEach((feature) => {{
          feature.geometry.coordinates.forEach((coord) => bounds.extend(coord));
        }});
        if (!bounds.isEmpty()) {{
          map.fitBounds(bounds, {{ padding: 32 }});
        }}
        const popup = new mapboxgl.Popup({{ closeButton: false, closeOnMove: true }});
        map.on('mousemove', 'tracks-line', (event) => {{
          const props = event.features[0].properties;
          const html = `<strong>第${{props.seq}}段</strong><br/>
            里程：${{props.distanceKm}} km<br/>
            用时：${{props.durationMin}} 分钟<br/>
            均速：${{props.avgSpeed}} km/h<br/>
            起点：${{props.start}}<br/>
            终点：${{props.end}}<br/>
            TrackID：${{props.trackId}}`;
          popup.setLngLat(event.lngLat).setHTML(html).addTo(map);
        }});
        map.on('mouseleave', 'tracks-line', () => popup.remove());
      }} else {{
        map.setCenter([fallback.lng, fallback.lat]);
        map.setZoom(12);
      }}
    }});
    const listSource = trackData.features.length
      ? chronologicalFeatures.map((feature) => feature.properties)
      : trackSummaries.sort((a, b) => (a.startTimeMs || 0) - (b.startTimeMs || 0));
    listEl.innerHTML = listSource.map((props, idx) => {{
      const color = props.color || defaultColors[idx % defaultColors.length];
      return `<li><span class="dot" style="background:${{color}}"></span>
        <div>
          <div><strong>第${{props.seq}}段</strong> · ${{props.distanceKm}} km · ${{props.durationMin}} 分钟</div>
          <div class="legend">${{props.start}} → ${{props.end}}</div>
        </div>
      </li>`;
    }}).join('');
  </script>
</body>
</html>
"""
    return template.format(
        title=title,
        subtitle=subtitle,
        stats_text=stats_text,
        generated_at=generated_at,
        track_data=track_json,
        meta_data=meta_json,
    )

def export_tracks_html(
    access_token: str,
    sn: str,
    tracks: List[Dict[str, Any]],
    period_start: str,
    period_end: str,
    total_distance: int,
    total_riding: int,
    export_target: Path,
    mapbox_token: str,
    mapbox_style: str,
) -> Path:
    """把指定周期的轨迹导出为 HTML 文件并返回路径。"""
    if tracks:
        detailed = enrich_tracks_with_details(access_token, sn, tracks)
        feature_collection, center, summaries = build_geojson_features(detailed)
    else:
        feature_collection = {"type": "FeatureCollection", "features": []}
        center = None
        summaries = []
    label = period_start if period_start == period_end else f"{period_start}-{period_end}"
    output_path = resolve_html_output_path(export_target, label)
    stats_text = (
        f"共 {len(tracks)} 次 · 总里程 {meters_to_km(total_distance)} km · "
        f"均速 {avg_speed_kmh(total_distance, total_riding)} km/h"
    )
    meta = {
        "title": f"{label} 行程地图",
        "subtitle": f"日期范围：{period_start} ~ {period_end}",
        "statsText": stats_text,
        "generatedAt": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fallbackCenter": (
            {"lat": center[0], "lng": center[1]} if center else {"lat": 39.9042, "lng": 116.4074}
        ),
        "trackSummaries": summaries,
        "mapboxToken": mapbox_token,
        "mapboxStyle": mapbox_style,
    }
    html = render_map_html(feature_collection, meta)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def main() -> None:
    """解析命令行参数，汇总骑行数据并发送 Bark 通知。"""
    global PERIOD, WEEK_START, TARGET_DATE, NIU_SN, TRACK_PAGE_SIZE, BARK_GROUP, BARK_SOUND
    global BARK_ENDPOINT, BARK_ICON_URL, BARK_OPEN_URL, TOKEN_CACHE_PATH, MAPBOX_ACCESS_TOKEN, MAPBOX_STYLE
    usage_text = """\
python3 notify_today_ride.py [必填参数] [可选参数]

功能简介：
  * 自动登录 NIU 账号，取默认或指定车辆 SN。
  * 支持日/周/月统计，输出里程、次数、均速、最长行程及时间区间。
  * 自动分页拉取行程，避免漏掉月初记录。
  * 自动缓存 token，优先使用 refresh_token 刷新，减少重复登录。
  * 发送 Bark 推送，可自定义 icon、分组、提示音、跳转 URL。

必填参数 (可乱序)：
  -b, --bark-key       Bark 设备 key (可用环境变量 BARK_KEY)
  -a, --niu-account    NIU 登录账号 (可用环境变量 NIU_ACCOUNT)
  -p, --niu-password   NIU 明文密码 (可用环境变量 NIU_PASSWORD)

可选参数：
  --period {day,week,month}     统计周期，默认 day
  --week-start WEEK_START       周统计的起始星期 (1=周一)
  --target-date YYYYMMDD        指定统计参考日期
  --niu-sn SN                   指定设备 sn_id
  --track-page-size N           分页拉取记录条数
  --export-html PATH            导出行程地图 HTML (文件或目录)
  --no-bark                     仅生成统计/HTML，不发送 Bark
  --mapbox-token TOKEN          Mapbox access token (导出 HTML 必填)
  --mapbox-style STYLE          Mapbox 样式 URL，默认 streets-v12
  --bark-group NAME             Bark 通知分组
  --bark-sound SOUND            Bark 提示音
  --bark-endpoint URL           Bark 推送接口
  --bark-icon-url URL           通知 icon URL
  --bark-open-url URL           点击通知跳转 URL
  --token-cache PATH            token 缓存文件路径

示例:
  python3 notify_today_ride.py -b xxx -a you@niu.com -p password --period week
"""
    parser = argparse.ArgumentParser(
        description="发送 NIU 骑行 Bark 通知",
        usage=usage_text,
        formatter_class=argparse.RawTextHelpFormatter,
        add_help=False,
    )
    parser.add_argument(
        "--bark-key",
        "-b",
        dest="bark_key",
        default=os.environ.get("BARK_KEY"),
        help="Bark 设备 key (或设置环境变量 BARK_KEY)",
    )
    parser.add_argument(
        "--niu-account",
        "-a",
        dest="niu_account",
        default=os.environ.get("NIU_ACCOUNT"),
        help="NIU 账号 (或设置环境变量 NIU_ACCOUNT)",
    )
    parser.add_argument(
        "--niu-password",
        "-p",
        dest="niu_password",
        default=os.environ.get("NIU_PASSWORD"),
        help="NIU 明文密码 (或设置环境变量 NIU_PASSWORD)",
    )
    parser.add_argument(
        "--period",
        choices=["day", "week", "month"],
        default=PERIOD,
        help="统计周期 (day/week/month)，默认读取 PERIOD 环境变量或 day",
    )
    parser.add_argument(
        "--week-start",
        type=int,
        default=WEEK_START,
        help="周统计起始星期 (1=周一, 默认读 WEEK_START 环境变量或 1)",
    )
    parser.add_argument(
        "--target-date",
        dest="target_date",
        default=TARGET_DATE or None,
        help="以 YYYYMMDD 指定统计参考日期 (默认今天)",
    )
    parser.add_argument(
        "--niu-sn",
        dest="niu_sn",
        default=NIU_SN,
        help="指定设备 sn_id (默认账号的默认车辆)",
    )
    parser.add_argument(
        "--track-page-size",
        type=int,
        default=TRACK_PAGE_SIZE,
        help="分页拉取行程的每页条数 (默认 50)",
    )
    parser.add_argument(
        "--export-html",
        dest="export_html",
        default=None,
        help="将指定周期的行程导出为 HTML 地图 (可填写目录或 HTML 文件路径)",
    )
    parser.add_argument(
        "--no-bark",
        dest="no_bark",
        action="store_true",
        help="仅生成统计或导出 HTML，不发送 Bark 推送",
    )
    parser.add_argument(
        "--mapbox-token",
        dest="mapbox_token",
        default=MAPBOX_ACCESS_TOKEN or None,
        help="Mapbox access token (导出 HTML 时必填，可设置 MAPBOX_ACCESS_TOKEN)",
    )
    parser.add_argument(
        "--mapbox-style",
        dest="mapbox_style",
        default=MAPBOX_STYLE,
        help="Mapbox 样式 URL (默认 mapbox://styles/mapbox/streets-v12，可设置 MAPBOX_STYLE)",
    )
    parser.add_argument(
        "--bark-group",
        dest="bark_group",
        default=BARK_GROUP,
        help="Bark 分组 (默认 niu-rides)",
    )
    parser.add_argument(
        "--bark-sound",
        dest="bark_sound",
        default=BARK_SOUND,
        help="Bark 提示音 (默认 shake)",
    )
    parser.add_argument(
        "--bark-endpoint",
        dest="bark_endpoint",
        default=BARK_ENDPOINT,
        help="Bark 推送接口地址",
    )
    parser.add_argument(
        "--bark-icon-url",
        dest="bark_icon_url",
        default=BARK_ICON_URL,
        help="Bark 通知图标 URL",
    )
    parser.add_argument(
        "--bark-open-url",
        dest="bark_open_url",
        default=BARK_OPEN_URL,
        help="点击通知跳转的 URL",
    )
    parser.add_argument(
        "--token-cache",
        dest="token_cache",
        default=str(TOKEN_CACHE_PATH),
        help="token 缓存文件路径 (默认 ./niu_token_cache.bin 或 NIU_TOKEN_CACHE 环境变量)",
    )
    parser.add_argument(
        "-h",
        "--help",
        action="help",
        default=argparse.SUPPRESS,
        help="显示帮助信息并退出",
    )
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)
    args = parser.parse_args()

    bark_key = args.bark_key
    niu_account = args.niu_account
    niu_password_raw = args.niu_password
    export_html_target = Path(args.export_html).expanduser() if args.export_html else None
    no_bark = args.no_bark
    MAPBOX_ACCESS_TOKEN = (args.mapbox_token or "").strip()
    MAPBOX_STYLE = args.mapbox_style or MAPBOX_STYLE

    if not bark_key and not no_bark:
        parser.error("必须提供 --bark-key 或设置环境变量 BARK_KEY")
    if not niu_account:
        parser.error("必须提供 --niu-account 或设置环境变量 NIU_ACCOUNT")
    if not niu_password_raw:
        parser.error("必须提供 --niu-password 或设置环境变量 NIU_PASSWORD")
    if export_html_target and not MAPBOX_ACCESS_TOKEN:
        parser.error("导出 HTML 需要提供 Mapbox token (--mapbox-token 或 MAPBOX_ACCESS_TOKEN)")

    PERIOD = args.period.lower()
    WEEK_START = args.week_start
    explicit_target_date = bool(args.target_date)
    TARGET_DATE = args.target_date or ""
    NIU_SN = args.niu_sn or ""
    TRACK_PAGE_SIZE = args.track_page_size
    BARK_GROUP = args.bark_group
    BARK_SOUND = args.bark_sound
    BARK_ENDPOINT = args.bark_endpoint
    BARK_ICON_URL = args.bark_icon_url
    BARK_OPEN_URL = args.bark_open_url
    TOKEN_CACHE_PATH = Path(args.token_cache).expanduser()

    password_md5 = hash_password(niu_password_raw)

    ensure_dependencies()
    date_str = target_date()
    period_start, period_end = compute_period_bounds(date_str)
    log(f"筛选日期范围: {period_start} ~ {period_end} (时区 {TARGET_TZ})")

    access_token = obtain_access_token(niu_account, password_md5, TOKEN_CACHE_PATH)
    log("已获取 token, 获取设备列表...")
    sn = fetch_sn(access_token, NIU_SN)
    log(f"使用设备 SN: {sn}")

    tracks = collect_tracks(access_token, sn, int(period_start))
    period_tracks = filter_tracks(tracks, int(period_start), int(period_end))

    titles = {"day": "今日骑行统计", "week": "本周骑行统计", "month": "本月骑行统计"}
    tips = {"day": "今天", "week": "本周", "month": "本月"}
    range_label = period_start if period_start == period_end else f"{period_start} ~ {period_end}"
    if explicit_target_date:
        title = f"{range_label} 骑行统计"
        tip = range_label
    else:
        title = titles[PERIOD]
        tip = tips[PERIOD]

    if not period_tracks:
        body = f"{tip}还没有骑行记录, 记得出门骑车哦~"
        if export_html_target:
            exported = export_tracks_html(
                access_token,
                sn,
                [],
                period_start,
                period_end,
                0,
                0,
                export_html_target,
                MAPBOX_ACCESS_TOKEN,
                MAPBOX_STYLE,
            )
            log(f"无骑行记录, 仍已生成空地图: {exported}")
        if not no_bark:
            send_bark(bark_key, title, body, "")
            log("无骑行记录, 已发送提示")
        else:
            log("无骑行记录, 已跳过 Bark 推送 (--no-bark)")
        return

    ride_count = len(period_tracks)
    total_distance, total_riding, longest = summarize_period(period_tracks)
    longest_distance = to_int(longest.get("distance"))
    longest_image = longest.get("track_thumb", "") or ""
    start_fmt = format_timestamp(longest.get("startTime"))
    end_fmt = format_timestamp(longest.get("endTime"))

    body = (
        f"{tip}里程：{meters_to_km(total_distance)} km\n"
        f"{tip}次数：{ride_count} 次\n"
        f"{tip}均速：{avg_speed_kmh(total_distance, total_riding)} km/h\n"
        f"最长里程：{meters_to_km(longest_distance)} km\n"
        f"最长时间：{trim_year(start_fmt)} → {trim_year(end_fmt)}"
    )

    if export_html_target:
        exported = export_tracks_html(
            access_token,
            sn,
            period_tracks,
            period_start,
            period_end,
            total_distance,
            total_riding,
            export_html_target,
            MAPBOX_ACCESS_TOKEN,
            MAPBOX_STYLE,
        )
        log(f"行程地图已导出到: {exported}")

    if not no_bark:
        send_bark(bark_key, title, body, longest_image)
        log(f"{title} 通知已发送")
    else:
        log("已根据 --no-bark 参数跳过 Bark 推送")


if __name__ == "__main__":
    main()
def build_curl_command(url: str, headers: Dict[str, str], payload: Dict[str, Any]) -> str:
    """在调试模式下将请求转换为 curl 命令，方便对比。"""
    parts = [f"curl --location --request POST '{url}' \\"]
    for key, value in headers.items():
        if key.lower() == "content-length":
            continue
        parts.append(f"  --header '{key}: {value}' \\")
    body = json.dumps(payload, ensure_ascii=False)
    parts.append(f"  --data-raw '{body}'")
    return "\n".join(parts)

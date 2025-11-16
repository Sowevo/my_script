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


def http_json(url: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """POST 请求并解析 JSON 响应，异常时报出详细信息。"""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
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


def collect_tracks(access_token: str, sn: str, min_date_cutoff: int) -> List[Dict[str, Any]]:
    """分页拉取行程，直到数据不足一页或已覆盖目标日期。"""
    index = 0
    all_items: List[Dict[str, Any]] = []
    headers = {"User-Agent": NIU_USER_AGENT, "token": access_token}
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


def main() -> None:
    """解析命令行参数，汇总骑行数据并发送 Bark 通知。"""
    global PERIOD, WEEK_START, TARGET_DATE, NIU_SN, TRACK_PAGE_SIZE, BARK_GROUP, BARK_SOUND
    global BARK_ENDPOINT, BARK_ICON_URL, BARK_OPEN_URL, TOKEN_CACHE_PATH
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

    if not bark_key:
        parser.error("必须提供 --bark-key 或设置环境变量 BARK_KEY")
    if not niu_account:
        parser.error("必须提供 --niu-account 或设置环境变量 NIU_ACCOUNT")
    if not niu_password_raw:
        parser.error("必须提供 --niu-password 或设置环境变量 NIU_PASSWORD")

    PERIOD = args.period.lower()
    WEEK_START = args.week_start
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
    title = titles[PERIOD]
    tip = tips[PERIOD]

    if not period_tracks:
        body = f"{tip}还没有骑行记录, 记得出门骑车哦~"
        send_bark(bark_key, title, body, "")
        log("无骑行记录, 已发送提示")
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

    send_bark(bark_key, title, body, longest_image)
    log(f"{title} 通知已发送")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Duolingo ADB driver (Approach A).

- Reads UI tree via uiautomator (not OCR).
- Executes taps / check / continue.
- Does NOT decide answers itself.

Usage:
  python3 duo_driver.py status              # dump structured question state (JSON)
  python3 duo_driver.py start               # start lesson from home popup
  python3 duo_driver.py chips 今日 は 少し     # tap word-bank chips in order
  python3 duo_driver.py choice 悪い          # tap an option by text/desc
  python3 duo_driver.py tap <x> <y>         # raw tap
  python3 duo_driver.py tap-id submitButton
  python3 duo_driver.py check | continue | skip | back
  python3 duo_driver.py go-home             # tap bottom house (Learn tab)
  python3 duo_driver.py screenshot [path]

Later: swap the external "judge" (chat AI / LLM API) without changing this driver.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path

WORKDIR = Path(__file__).resolve().parent
DUMP_PATH = WORKDIR / "window_dump.xml"
SCREEN_PATH = WORKDIR / "duo_play.png"
REMOTE_DUMP = "/sdcard/window_dump.xml"
REMOTE_SCREEN = "/sdcard/duo_play.png"


def adb(*args: str, check: bool = True) -> str:
    r = subprocess.run(["adb", *args], capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    if check and r.returncode != 0:
        raise RuntimeError(f"adb {' '.join(args)} failed:\n{out}")
    return out


def parse_bounds(bounds: str) -> tuple[int, int, int, int] | None:
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds or "")
    if not m:
        return None
    return tuple(map(int, m.groups()))  # type: ignore


def center_of(bounds: str) -> tuple[int, int] | None:
    b = parse_bounds(bounds)
    if not b:
        return None
    x1, y1, x2, y2 = b
    return (x1 + x2) // 2, (y1 + y2) // 2


# When True, action commands skip post-action status dump (much faster).
QUIET = False

# Timing profile (seconds). FAST is default; DUO_SAFE=1 for slower/safer.
import os as _os

_FAST = _os.environ.get("DUO_SAFE", "").strip() not in {"1", "true", "yes"}
CHIP_TAP = 0.12 if _FAST else 0.28
CHIP_GAP = 0.05 if _FAST else 0.12
AFTER_CHIPS = 0.15 if _FAST else 0.35
# After 检查, wait for result banner then tap same bottom button (继续/知道了)
AFTER_CHECK = 0.45 if _FAST else 0.70
AFTER_CONTINUE = 0.30 if _FAST else 0.55
AFTER_CTA = 0.55 if _FAST else 1.20
PATH_TAP = 0.35 if _FAST else 0.90
DEFAULT_TAP = 0.15 if _FAST else 0.35

# Bottom primary button (检查 / 继续 / 知道了) — same slot on 1080×2400 Duolingo
_BOTTOM_CTA_CACHE: tuple[int, int] | None = None
# Package probe cache — dumpsys is ~50–200ms; avoid on every chip tap
_PKG_CACHE: tuple[float, str] | None = None
_PKG_TTL = 2.5
# After require_duolingo(), skip per-tap package probes for a short window
_PKG_TRUST_UNTIL = 0.0


def _wm_size() -> tuple[int, int]:
    """Physical screen size (w, h); fallback 1080×2400."""
    try:
        out = adb("shell", "wm", "size", check=False)
        import re as _re

        m = _re.search(r"(\d+)x(\d+)", out or "")
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    return 1080, 2400


def bottom_cta_xy() -> tuple[int, int]:
    """Center of the big green bottom button; position is stable across 检查/继续/知道了."""
    global _BOTTOM_CTA_CACHE
    if _BOTTOM_CTA_CACHE is not None:
        return _BOTTOM_CTA_CACHE
    w, h = _wm_size()
    # Observed lesson CTA: [44,2169][1036,2312] on 1080x2400 → ~50% x, ~93% y
    _BOTTOM_CTA_CACHE = (w // 2, int(h * 0.932))
    return _BOTTOM_CTA_CACHE


def bottom_cta_xy_candidates() -> list[tuple[int, int]]:
    """
    Bottom primary CTAs are not always at the same Y:
      · normal 检查/继续 ~0.932h (y≈2240 on 2400)
      · unit-complete / some reward sheets ~0.898h (y≈2155) — fixed 0.932 taps *below* the button
    """
    w, h = _wm_size()
    cx = w // 2
    ys = sorted({int(h * r) for r in (0.932, 0.915, 0.898)}, reverse=True)
    return [(cx, y) for y in ys]


def tap_bottom_cta(delay: float | None = None) -> dict:
    """Blind-tap bottom primary CTA (no UI read). Uses classic lesson slot."""
    x, y = bottom_cta_xy()
    tap_xy(x, y, delay=delay if delay is not None else DEFAULT_TAP, force=True)
    return {"x": x, "y": y}


def find_bottom_cta_bounds(st: "UiState | None") -> str | None:
    """
    Locate the wide bottom primary CTA from a dumped hierarchy.
    Prefer resource-id, then label text expanded to covering Button, then widest bottom Button.
    """
    if st is None:
        return None
    sid_pref = (
        "continueButton",
        "continueButtonGreenStub",
        "submitButton",
        "storiesLessonGreenContinueButton",
        "storiesLessonContinueButton",
    )
    for sid in sid_pref:
        for n in st._all:
            if n.short_id == sid and n.bounds:
                return n.bounds

    labels = {"继续", "知道了", "检查", "CHECK", "Continue", "Got it", "领取经验", "领取奖励"}
    label_nodes = [
        n
        for n in st._all
        if n.bounds and ((n.text in labels) or (n.desc in labels))
    ]
    for ln in label_nodes:
        lb = parse_bounds(ln.bounds)
        if not lb:
            continue
        lcx, lcy = (lb[0] + lb[2]) // 2, (lb[1] + lb[3]) // 2
        best = ln.bounds
        best_w = lb[2] - lb[0]
        for n in st._all:
            if not n.bounds:
                continue
            # Compose often marks Button clickable=false; still use geometry
            if n.cls not in {"Button", "View", "FrameLayout", "LinearLayout"} and not n.clickable:
                continue
            b = parse_bounds(n.bounds)
            if not b:
                continue
            w = b[2] - b[0]
            h = b[3] - b[1]
            if w < 280 or h < 60 or h > 400:
                continue
            if not (b[0] <= lcx <= b[2] and b[1] <= lcy <= b[3]):
                continue
            if w > best_w:
                best, best_w = n.bounds, w
        return best

    # Fallback: widest Button / submit-like node in lower third of screen
    _, sh = _wm_size()
    y_min = int(sh * 0.72)
    best_b: str | None = None
    best_w = 0
    for n in st._all:
        if not n.bounds:
            continue
        if n.cls != "Button" and n.short_id not in sid_pref:
            continue
        b = parse_bounds(n.bounds)
        if not b or b[1] < y_min:
            continue
        w = b[2] - b[0]
        if w > best_w and w >= 400:
            best_b, best_w = n.bounds, w
    return best_b


def tap_bottom_cta_smart(
    st: "UiState | None" = None,
    *,
    dump: bool = False,
    delay: float | None = None,
    multi_y_fallback: bool = True,
) -> dict:
    """
    Tap bottom primary CTA using dump bounds when available.
    Falls back to classic fixed Y, then alternate higher Ys (unit-complete sheet).
    """
    d = delay if delay is not None else DEFAULT_TAP
    if dump and st is None:
        try:
            st = get_state()
        except Exception:
            st = None
    b = find_bottom_cta_bounds(st)
    if b:
        tap_bounds(b, delay=d)
        return {"mode": "cta_bounds", "bounds": b, **(dict(zip(("x", "y"), center_of(b) or (0, 0))))}

    t = tap_bottom_cta(delay=d)
    if not multi_y_fallback:
        return {"mode": "fixed_bottom", **t}

    # Extra higher taps cover reward / unit-complete sheets where 0.932 is below the button
    extras = []
    primary = bottom_cta_xy()
    for x, y in bottom_cta_xy_candidates():
        if (x, y) == primary:
            continue
        tap_xy(x, y, delay=d * 0.5, force=True)
        extras.append({"x": x, "y": y})
    return {"mode": "fixed_bottom_multi_y", "primary": t, "extras": extras}


def _submit_bounds_from_state(st: "UiState | None") -> str | None:
    """Wide submitButton / 检查 from an already-dumped state (no extra dump)."""
    if st is None:
        return None
    for n in st._all:
        if n.short_id == "submitButton" and n.bounds:
            return n.bounds
        if n.text == "检查" and n.bounds:
            b = parse_bounds(n.bounds)
            if b and (b[2] - b[0]) > 400:
                return n.bounds
    return None


def tap_check_button(*, bounds: str | None = None, dump: bool = False) -> dict:
    """
    Tap 检查.
    Default: fixed bottom CTA (0 dumps). Optional bounds from a prior dump.
    dump=True only when caller truly needs a fresh hierarchy (slow, ~3s).
    """
    if bounds:
        tap_bounds(bounds, delay=DEFAULT_TAP)
        return {"mode": "submit_bounds", "bounds": bounds}
    if dump:
        st = get_state()
        b = _submit_bounds_from_state(st)
        if b:
            tap_bounds(b, delay=DEFAULT_TAP)
            return {"mode": "submitButton", "bounds": b}
    t = tap_bottom_cta()
    return {"mode": "fixed_bottom", **t}


def submit_and_advance(*, check_bounds: str | None = None) -> dict:
    """
    Post-answer advance with ZERO uiautomator dumps.
    Bottom slot is the same for 检查 → 继续 / 知道了 on this device.
    Optional check_bounds from the answer-step dump (submitButton) for precision.
    """
    t1 = tap_check_button(bounds=check_bounds, dump=False)
    time.sleep(AFTER_CHECK)
    t2 = tap_bottom_cta()
    t2 = {"mode": "fixed_bottom_continue", **t2}
    time.sleep(AFTER_CONTINUE)
    return {"check_tap": t1, "advance_tap": t2, "mode": "fixed_cta_fast"}


def tap_xy(x: int, y: int, delay: float | None = None, *, force: bool = False) -> None:
    if delay is None:
        delay = DEFAULT_TAP
    if not force:
        # Never tap if we left Duolingo (e.g. 拼多多). Trust recent require_duolingo().
        global _PKG_TRUST_UNTIL
        if time.time() >= _PKG_TRUST_UNTIL:
            pkg = current_package()
            if pkg and pkg != DUOLINGO_PKG:
                raise RuntimeError(f"blocked tap: foreground is {pkg!r}, not Duolingo")
            _PKG_TRUST_UNTIL = time.time() + _PKG_TTL
    adb("shell", "input", "tap", str(x), str(y))
    if delay > 0:
        time.sleep(delay)


def tap_bounds(bounds: str, delay: float | None = None) -> bool:
    c = center_of(bounds)
    if not c:
        return False
    tap_xy(*c, delay=delay)
    return True


def swipe_xy(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    duration_ms: int = 500,
    *,
    force: bool = True,
) -> None:
    """Drag from (x1,y1) to (x2,y2). Used for story order challenges."""
    if not force:
        pkg = current_package()
        if pkg and pkg != DUOLINGO_PKG:
            raise RuntimeError(f"blocked swipe: foreground is {pkg!r}, not Duolingo")
    adb(
        "shell",
        "input",
        "swipe",
        str(x1),
        str(y1),
        str(x2),
        str(y2),
        str(int(duration_ms)),
    )
    time.sleep(0.15)


def _json_safe(obj):
    """Make payload JSON-serializable (strip Node etc.)."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items() if not str(k).startswith("_")}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(x) for x in obj]
    if isinstance(obj, Node):
        return {
            "text": obj.text,
            "desc": obj.desc,
            "rid": obj.short_id,
            "bounds": obj.bounds,
            "cls": obj.cls,
        }
    return str(obj)


def emit(payload: dict) -> None:
    print(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2))


def maybe_state() -> dict | None:
    if QUIET:
        return None
    return get_state().to_public_dict()


def dump_root() -> ET.Element:
    """Dump UI hierarchy; retry once on empty/race (animation frames)."""
    last_err: Exception | None = None
    for attempt in range(3):
        r = subprocess.run(
            [
                "adb",
                "shell",
                f"uiautomator dump {REMOTE_DUMP} >/dev/null 2>&1 && cat {REMOTE_DUMP}",
            ],
            capture_output=True,
        )
        raw = r.stdout or b""
        # strip junk before xml
        idx = raw.find(b"<?xml")
        if idx < 0:
            idx = raw.find(b"<hierarchy")
        if idx >= 0:
            raw = raw[idx:]
        if b"<hierarchy" in raw:
            try:
                DUMP_PATH.write_bytes(raw)
                return ET.fromstring(raw)
            except ET.ParseError as e:
                last_err = e
        # classic dump + pull fallback
        try:
            adb("shell", "uiautomator", "dump", REMOTE_DUMP, check=False)
            adb("pull", REMOTE_DUMP, str(DUMP_PATH), check=False)
            if DUMP_PATH.exists() and DUMP_PATH.stat().st_size > 50:
                return ET.parse(DUMP_PATH).getroot()
        except Exception as e:
            last_err = e
        time.sleep(0.15 * (attempt + 1))
    raise RuntimeError(f"uiautomator dump failed: {last_err}")


def screenshot(path: Path | None = None) -> Path:
    dest = path or SCREEN_PATH
    adb("shell", "screencap", "-p", REMOTE_SCREEN, check=False)
    adb("pull", REMOTE_SCREEN, str(dest), check=False)
    return dest


@dataclass
class Node:
    text: str = ""
    desc: str = ""
    rid: str = ""
    clickable: bool = False
    enabled: bool = True
    bounds: str = ""
    cls: str = ""

    @property
    def short_id(self) -> str:
        return self.rid.split("/")[-1] if self.rid else ""

    @property
    def label(self) -> str:
        # Prefer content-desc for JP chips (text often has bidi marks)
        return (self.desc or self.text or "").strip()


def iter_nodes(root: ET.Element) -> list[Node]:
    out: list[Node] = []
    for n in root.iter("node"):
        out.append(
            Node(
                text=(n.attrib.get("text") or "").strip(),
                desc=(n.attrib.get("content-desc") or "").strip(),
                rid=n.attrib.get("resource-id") or "",
                clickable=n.attrib.get("clickable") == "true",
                # missing attr → treat as enabled (old dumps)
                enabled=n.attrib.get("enabled", "true") == "true",
                bounds=n.attrib.get("bounds") or "",
                cls=(n.attrib.get("class") or "").split(".")[-1],
            )
        )
    return out


DUOLINGO_PKG = "com.duolingo"


def focus_activity() -> str:
    out = adb("shell", "dumpsys", "window", check=False)
    for line in out.splitlines():
        if "mCurrentFocus" in line or "mFocusedApp" in line:
            return line.strip()
    return ""


def current_package(*, fresh: bool = False) -> str:
    """Foreground app package, e.g. com.duolingo / com.xunmeng.pinduoduo."""
    global _PKG_CACHE
    now = time.time()
    if not fresh and _PKG_CACHE is not None and (now - _PKG_CACHE[0]) < _PKG_TTL:
        return _PKG_CACHE[1]
    act = focus_activity()
    m = re.search(r"\su0\s+([a-zA-Z0-9._]+)/", act)
    pkg = m.group(1) if m else ""
    if not pkg:
        m = re.search(r"([a-zA-Z0-9._]+)/[a-zA-Z0-9._]+", act)
        pkg = m.group(1) if m else ""
    _PKG_CACHE = (now, pkg)
    return pkg


def is_duolingo_foreground() -> bool:
    return current_package() == DUOLINGO_PKG


def ensure_duolingo(*, bring_to_front: bool = True, attempts: int = 4) -> str:
    """
    Hard gate: refuse to tap/scroll unless Duolingo is the foreground app.
    Never operate on 拼多多 or anything else.
    """
    global _PKG_TRUST_UNTIL
    pkg = current_package(fresh=True)
    if pkg == DUOLINGO_PKG:
        _PKG_TRUST_UNTIL = time.time() + 8.0
        return pkg
    if not bring_to_front:
        raise RuntimeError(
            f"refusing to act: foreground app is {pkg!r}, expected {DUOLINGO_PKG}"
        )
    for i in range(attempts):
        # Prefer explicit activity start over monkey (less flaky)
        adb(
            "shell",
            "am",
            "start",
            "-n",
            "com.duolingo/.splash.LaunchActivity",
            check=False,
        )
        time.sleep(1.0 + 0.3 * i)
        pkg = current_package(fresh=True)
        if pkg == DUOLINGO_PKG:
            _PKG_TRUST_UNTIL = time.time() + 8.0
            return pkg
        adb(
            "shell",
            "monkey",
            "-p",
            DUOLINGO_PKG,
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
            check=False,
        )
        time.sleep(1.2)
        pkg = current_package(fresh=True)
        if pkg == DUOLINGO_PKG:
            _PKG_TRUST_UNTIL = time.time() + 8.0
            return pkg
    raise RuntimeError(
        f"cannot bring Duolingo to front; still on {current_package(fresh=True)!r}. "
        "Stop — will not tap other apps."
    )


def require_duolingo() -> None:
    """Call before any UI interaction that is not 'foreground' itself."""
    ensure_duolingo(bring_to_front=True)


def unique_chips(chips: list[Node]) -> list[Node]:
    """Dedupe glyph+underline pairs only; keep multiple chips with the same word (e.g. two を)."""
    # First drop thin underlines stacked under the same label at nearly same x
    filtered: list[Node] = []
    for n in chips:
        lab = n.label
        if not lab:
            continue
        b = parse_bounds(n.bounds)
        if not b:
            continue
        h = b[3] - b[1]
        cx = (b[0] + b[2]) // 2
        # find if this is underline of an existing taller chip
        replaced = False
        for i, prev in enumerate(filtered):
            if prev.label != lab:
                continue
            pb = parse_bounds(prev.bounds)
            if not pb:
                continue
            pcx = (pb[0] + pb[2]) // 2
            ph = pb[3] - pb[1]
            # same column, overlapping/near vertically → glyph vs underline
            if abs(cx - pcx) <= 40 and abs(b[1] - pb[1]) <= 100:
                if h > ph:
                    filtered[i] = n
                replaced = True
                break
        if not replaced:
            filtered.append(n)

    def key(n: Node):
        b = parse_bounds(n.bounds) or (0, 0, 0, 0)
        return (b[1] // 40, b[0])

    return sorted(filtered, key=key)


# Feedback chrome — not answer chips
_FEEDBACK_NOISE = frozenset(
    {
        "你太棒了！",
        "你太棒了",
        "太棒了！",
        "太棒了",
        "真棒！",
        "真棒",
        "真厉害！",
        "真厉害",
        "泰裤辣！",
        "棒棒哒！",
        "不错哦！",
        "不错哦",
        "纠错成功！",
        "不正确",
        "正确答案：",
        "正确答案",
        "差了一点点哦～",
        "知道了",
        "继续",
        "检查",
    }
)


@dataclass
class UiState:
    screen: str = "unknown"  # home | session | end | other
    activity: str = ""
    instruction: str = ""
    prompt: str = ""
    chips: list[str] = field(default_factory=list)
    options: list[str] = field(default_factory=list)
    buttons: list[str] = field(default_factory=list)
    hearts: str = ""
    raw_texts: list[str] = field(default_factory=list)
    # Hardcoded feedback detection (script-owned, not LLM)
    feedback: dict = field(default_factory=dict)
    # for executor
    _chip_nodes: list[Node] = field(default_factory=list, repr=False)
    _option_nodes: list[Node] = field(default_factory=list, repr=False)
    _all: list[Node] = field(default_factory=list, repr=False)

    def to_public_dict(self) -> dict:
        pkg = current_package()
        img = getattr(self, "image_options", None) or []
        return {
            "screen": self.screen,
            "package": pkg,
            "duolingo": pkg == DUOLINGO_PKG,
            "activity": self.activity,
            "mode": getattr(self, "mode", "lesson"),
            "instruction": self.instruction,
            "prompt": self.prompt,
            "chips": self.chips,
            "options": self.options,
            "match_left": getattr(self, "match_left", None) or [],
            "match_right": getattr(self, "match_right", None) or [],
            "image_options": img,
            "buttons": self.buttons,
            # 小故事：继续可点=true / 灰色禁用=false → 需先答题
            "continue_enabled": getattr(self, "continue_enabled", None),
            # 小故事排序等：检查可点
            "check_enabled": getattr(self, "check_enabled", None),
            "challenge": getattr(self, "challenge", None),
            # Stories multi-blank gap-fill (inferred from sentence ∩ word bank)
            "gap_sentence": getattr(self, "gap_sentence", None) or "",
            "gap_words": getattr(self, "gap_words", None) or [],
            "blank_count": getattr(self, "blank_count", None),
            "hearts": self.hearts,
            "raw_texts": self.raw_texts[:40],
            "feedback": self.feedback,
            "hint": judge_hint(self),
        }


def _is_stories_ui(ns: list[Node], activity: str = "") -> bool:
    if "Stories" in (activity or ""):
        return True
    return any((n.short_id or "").startswith("stories") for n in ns)


def infer_gap_fill_words(sentence: str, bank: list[str]) -> list[str]:
    """
    Stories gap-fill: accessibility sentence often already contains the blank
    answers as plain text. Bank words that appear in the sentence (L→R) are
    the multi-blank answers. Prefer longer tokens; non-overlapping.
    """
    if not sentence or not bank:
        return []
    # longest first so メッセージ wins over メー if both existed
    ordered = sorted({w for w in bank if w}, key=lambda w: (-len(w), w))
    used: list[tuple[int, int]] = []
    hits: list[tuple[int, str]] = []
    for w in ordered:
        start = 0
        while True:
            i = sentence.find(w, start)
            if i < 0:
                break
            j = i + len(w)
            if any(not (j <= a or i >= b) for a, b in used):
                start = i + 1
                continue
            used.append((i, j))
            hits.append((i, w))
            break  # one placement per bank word
    hits.sort(key=lambda x: x[0])
    return [w for _, w in hits]


def extract_gap_sentence(prompt: str = "", raw_texts: list[str] | None = None) -> str:
    """Pull [填空文] passage or sentenceText-like line from status fields."""
    p = prompt or ""
    if "[填空文]" in p:
        return p.split("[填空文]", 1)[1].strip().split(" | ")[0].strip()
    for t in raw_texts or []:
        if t and t not in {"继续", "检查", "文章を完成させてください"} and len(t) >= 8:
            # prefer longer Japanese prose
            if any(ch in t for ch in "。！？"):
                return t
    return ""


def detect_feedback(ns: list[Node], buttons: list[str], raw_texts: list[str], *, activity: str = "") -> dict:
    """
    Hardcoded result-page detection. No LLM.

    Lesson session:
      - bottom CTA is 继续 and 检查 is gone → feedback
      - 知道了 → wrong dismiss

    Stories (StoriesSessionActivity):
      - 继续 is normal page advance (NOT feedback by itself)
      - only praise/wrong banner after a quiz is feedback
    """
    is_stories = _is_stories_ui(ns, activity)
    has_continue = "继续" in buttons or any(
        n.short_id
        in {
            "continueButton",
            "continueButtonGreenStub",
            "playerContinueButton",
            "storiesLessonGreenContinueButton",
            "storiesLessonContinueButton",
        }
        or n.text == "继续"
        for n in ns
    )
    has_check = "检查" in buttons or any(n.short_id == "submitButton" or n.text == "检查" for n in ns)
    has_got_it = "知道了" in buttons or any(n.text == "知道了" for n in ns)

    # Left checkmark / status icon: empty View left of feedback text band
    has_result_icon = False
    for n in ns:
        b = parse_bounds(n.bounds)
        if not b:
            continue
        x1, y1, x2, y2 = b
        # observed: check icon ~ [11,1905][143,2037]
        if y1 >= 1850 and y2 <= 2120 and x2 <= 180 and (x2 - x1) >= 80 and (y2 - y1) >= 80:
            if n.cls in {"View", "ImageView", "FrameLayout"} and not (n.text or "").strip():
                has_result_icon = True
                break

    blob = " ".join(raw_texts)
    praise = any(k in blob for k in ("你太棒了", "真棒", "不错哦", "泰裤辣", "棒棒哒", "纠错成功"))
    wrongish = any(k in blob for k in ("不正确", "正确答案", "差了一点", "知道了"))
    if has_got_it or wrongish:
        kind = "wrong"
    elif praise or (has_continue and not has_check and has_result_icon):
        kind = "correct"
    elif has_continue and not has_check and not is_stories:
        kind = "result"
    else:
        kind = "none"

    if is_stories:
        # Story pages always show 继续; only quiz result banners are feedback.
        is_feedback = bool(praise or has_got_it or wrongish)
    else:
        is_feedback = bool((has_continue and not has_check) or has_got_it)

    action = "none"
    if is_feedback:
        if has_got_it and not has_continue:
            action = "got_it"
        elif has_continue:
            action = "continue"
        elif has_got_it:
            action = "got_it"

    return {
        "is_feedback": is_feedback,
        "kind": kind,
        "action": action,  # continue | got_it | none — script should do this, not LLM
        "has_continue": has_continue,
        "has_check": has_check,
        "has_got_it": has_got_it,
        "has_result_icon": has_result_icon,
        "is_stories": is_stories,
    }


def judge_hint(s: UiState) -> str:
    """Guidance for the external judge (you / future LLM)."""
    fb = s.feedback or {}
    if fb.get("is_feedback"):
        return f"HARDCODED feedback — script should {fb.get('action')} (do not call LLM)"
    if s.screen == "home":
        return "On home. Call: start"
    if s.screen == "end":
        return "Lesson end / reward. Call: continue (maybe multiple times)"
    if s.screen == "other":
        return "Not on learn path. Prefer go-home (house tab) then start"
    mode = getattr(s, "mode", "lesson")
    if mode == "story":
        ch = getattr(s, "challenge", None)
        if ch == "sort" or (s.options and ("順番" in (s.instruction or "") or "並べ" in (s.instruction or ""))):
            return (
                "STORY ORDER: drag sentences into chronological order. "
                f"Reply: order with labels = correct top→bottom sequence using EXACT options: {s.options}. "
                "Script will drag then tap 检查."
            )
        if ch == "gap_fill" or (s.options and s.chips and "完成" in (s.instruction or "")):
            gw = getattr(s, "gap_words", None) or []
            bc = getattr(s, "blank_count", None) or (len(gw) if gw else None)
            extra = (
                f" Inferred blanks L→R ({bc}): {gw}."
                if gw
                else " Count blanks from passage; usually 2+ words."
            )
            return (
                "STORY GAP-FILL multi-blank: fill EVERY blank left→right in one chips action. "
                f"Word bank: {s.options}.{extra} "
                "words length MUST equal blank count (not 1 unless single blank). No check."
            )
        if s.options:
            return (
                "STORY quiz — answerable options present. "
                f"Reply: choice <exact option from {s.options}> — no check; "
                "script taps continue after."
            )
        cont_on = getattr(s, "continue_enabled", None)
        if cont_on is False:
            return (
                "STORY — 继续 gray but NO options: waiting for audio/animation. "
                "HARDCODED wait (do not skip, do not call LLM for answers)."
            )
        return "STORY — 继续 green; HARDCODED continue (do not call LLM)"
    instr = s.instruction or ""
    if "配对" in instr or "Match" in instr or "match" in instr.lower():
        left = getattr(s, "match_left", None) or []
        right = getattr(s, "match_right", None) or []
        if left and right:
            return (
                f"PAIRING: left column ({len(left)}) ↔ right column ({len(right)}). "
                f"Reply match labels as L1,R1,L2,R2,... using each card once. "
                f"left={left} right={right}"
            )
        pool = list(s.options or [])
        n = len(pool)
        return (
            f"PAIRING: one match with ALL {n} cards (multiset; CN/JP same spelling e.g. 胸 appears twice). "
            f"labels length must be {n}. pool={pool}"
        )

    if "图片" in instr or "image" in instr.lower():
        opts = s.options or [x.get("text") for x in (getattr(s, "image_options", None) or []) if x.get("text")]
        return (
            f"IMAGE choice: pick caption matching prompt. "
            f"Use choice with exact option text from: {opts}"
        )
    if "翻译" in instr or "Translate" in instr:
        if s.chips and "检查" in s.buttons:
            return (
                "Word-bank translation. Reply with chip sequence, e.g. "
                "chips 今日 は 少し 調子 が 悪い です  then check"
            )
        return "Translation without chips (maybe typing). Consider skip if stuck."
    if s.options and "检查" in s.buttons:
        return "Multiple choice. Reply: choice <exact option text>  then check"
    if "检查" in s.buttons or "CHECK" in s.buttons:
        return "Answer selected or need answer, then: check"
    return "Inspect raw_texts / screenshot; use tap-id or choice/chips."


def classify(ns: list[Node], activity: str) -> UiState:
    st = UiState(activity=activity, _all=ns)
    st.mode = "lesson"  # type: ignore[attr-defined]

    def by_id(sid: str) -> Node | None:
        for n in ns:
            if n.short_id == sid:
                return n
        return None

    instr = by_id("challengeInstruction")
    prompt = by_id("hintablePrompt") or by_id("challengePrompt")
    st.instruction = instr.text if instr else ""
    st.prompt = prompt.text if prompt else ""

    # hearts
    for n in ns:
        if "红心" in n.desc or "heart" in n.desc.lower():
            st.hearts = n.desc
            break

    texts = [n.text for n in ns if n.text]
    st.raw_texts = list(dict.fromkeys(texts))

    buttons = []
    for n in ns:
        if n.short_id in {
            "submitButton",
            "continueButton",
            "xpBoostLearnButton",
            "playerContinueButton",
            "storiesLessonGreenContinueButton",
            "storiesLessonContinueButton",
            "storiesLessonCheckButton",
        } or n.text in {
            "检查",
            "继续",
            "跳过",
            "开始",
            "CHECK",
            "CONTINUE",
            "领取奖励",
            "完成",
            "知道了",
        }:
            lab = n.text or n.short_id
            if n.short_id == "storiesLessonCheckButton":
                lab = n.text or "检查"
            if lab and lab not in buttons:
                buttons.append(lab)
    st.buttons = buttons
    st.feedback = detect_feedback(ns, buttons, st.raw_texts, activity=activity)

    # home?
    if by_id("tabLearn") and (by_id("primaryCardView") or by_id("sectionUnitText") or by_id("xpBoostLearnButton")):
        st.screen = "home"
        return st

    # ——— Stories (小故事): book node / StoriesSessionActivity ———
    if _is_stories_ui(ns, activity):
        st.mode = "story"  # type: ignore[attr-defined]
        st.screen = "session"
        # 继续：enabled=true 绿可点；enabled=false 灰色 → 必须先答题
        cont_btn = by_id("storiesLessonGreenContinueButton") or by_id(
            "storiesLessonContinueButton"
        )
        if cont_btn is not None:
            st.continue_enabled = cont_btn.enabled  # type: ignore[attr-defined]
        else:
            # 无继续按钮（排序题只有检查）→ None
            st.continue_enabled = None if by_id("storiesLessonCheckButton") else ("继续" in st.buttons)  # type: ignore[attr-defined]

        check_btn = by_id("storiesLessonCheckButton") or by_id("submitButton")
        if check_btn is not None:
            st.check_enabled = check_btn.enabled  # type: ignore[attr-defined]
        else:
            st.check_enabled = None  # type: ignore[attr-defined]

        # Question: challenge prompt / multi-choice stem / point-to-phrase
        q = (
            by_id("storiesChallengePromptText")
            or by_id("storiesChallengePrompt")
            or by_id("storiesMultipleOptionQuestion")
            or by_id("storiesPointToPhraseQuestion")
        )
        stem = by_id("storiesMultipleOptionQuestion")
        if q and q.text:
            st.instruction = q.text.strip()
        elif stem and stem.text:
            st.instruction = stem.text.strip()
        else:
            st.instruction = "小故事"
        # Context: dialogue + prose; incomplete stem also goes here for fill-in style
        ctx: list[str] = []
        for n in ns:
            if n.short_id in {
                "storiesCharacterText",
                "storiesProseText",
                "storiesHeaderTitleText",
            } and n.text:
                ctx.append(n.text.strip())
        # gap-fill passage (sentence with blanks)
        sent = by_id("sentenceText")
        if sent and sent.text and sent.text.strip():
            ctx.append(f"[填空文] {sent.text.strip()}")
        if stem and stem.text and stem.text.strip() not in ctx:
            # e.g. ルーシーはオスカーのリュックが _____
            ctx.insert(0, f"[填空] {stem.text.strip()}")
        if ctx:
            st.prompt = " | ".join(ctx[:6])

        opt_nodes: list[Node] = []
        opt_labels: list[str] = []
        gap_fill = False

        # A) storiesMultipleOption0/1/2 cards + nested optionText
        for n in ns:
            sid = n.short_id or ""
            if not re.match(r"storiesMultipleOption\d+$", sid):
                continue
            if not n.bounds:
                continue
            card_b = parse_bounds(n.bounds)
            if not card_b:
                continue
            cap = ""
            for tnode in ns:
                if tnode.short_id != "optionText" or not tnode.text:
                    continue
                tb = parse_bounds(tnode.bounds)
                if not tb:
                    continue
                tcx, tcy = (tb[0] + tb[2]) // 2, (tb[1] + tb[3]) // 2
                if card_b[0] <= tcx <= card_b[2] and card_b[1] <= tcy <= card_b[3]:
                    cap = tnode.text.strip()
                    break
            if not cap:
                continue
            opt_labels.append(cap)
            opt_nodes.append(
                Node(
                    text=cap,
                    desc=n.desc,
                    rid=n.rid,
                    clickable=True,
                    enabled=n.enabled,
                    bounds=n.bounds,
                    cls=n.cls,
                )
            )

        # B) point-to-phrase selectable segments
        for n in ns:
            if n.short_id != "storiesPointToPhraseSelectablePartText" or not n.text:
                continue
            t = n.text.strip()
            if not t or t in opt_labels:
                continue
            tb = parse_bounds(n.bounds)
            hit = n
            if tb:
                tcx, tcy = (tb[0] + tb[2]) // 2, (tb[1] + tb[3]) // 2
                best_a = 10**18
                for p in ns:
                    if not p.clickable or not p.bounds:
                        continue
                    pb = parse_bounds(p.bounds)
                    if not pb:
                        continue
                    if not (pb[0] <= tcx <= pb[2] and pb[1] <= tcy <= pb[3]):
                        continue
                    a = (pb[2] - pb[0]) * (pb[3] - pb[1])
                    if 1500 < a < 400_000 and a < best_a:
                        best_a = a
                        hit = Node(
                            text=t,
                            desc=n.desc,
                            rid=p.rid or n.rid,
                            clickable=True,
                            enabled=p.enabled,
                            bounds=p.bounds,
                            cls=p.cls,
                        )
            opt_labels.append(t)
            opt_nodes.append(hit if hit.bounds else n)

        # C) other story option text ids
        for n in ns:
            if n.short_id in {
                "storiesChallengeOptionText",
                "storiesOptionText",
                "storiesChallengeAnswerText",
            } and n.text:
                t = n.text.strip()
                if t and t not in opt_labels:
                    opt_labels.append(t)
                    opt_nodes.append(n)

        # E) gap-fill word bank: storiesGapFillOption + gapFillOptionN pad
        #    Multi-blank: tap several bank words L→R (sentence a11y often contains answers).
        gap_nodes: list[Node] = []
        gap_sentence = (sent.text.strip() if sent and sent.text else "") or ""
        for n in ns:
            if n.short_id != "storiesGapFillOption" or not n.text:
                continue
            t = n.text.strip()
            if not t or t in opt_labels:
                continue
            tb = parse_bounds(n.bounds)
            parent_en = True
            parent_click = True
            hit = Node(
                text=t,
                desc=n.desc or t,
                rid=n.rid,
                clickable=True,
                enabled=n.enabled,
                bounds=n.bounds,
                cls=n.cls,
            )
            if tb:
                tcx, tcy = (tb[0] + tb[2]) // 2, (tb[1] + tb[3]) // 2
                best_a = 10**18
                for p in ns:
                    sid = p.short_id or ""
                    if not re.match(r"gapFillOption\d+$", sid) or not p.bounds:
                        continue
                    pb = parse_bounds(p.bounds)
                    if not pb:
                        continue
                    if not (pb[0] <= tcx <= pb[2] and pb[1] <= tcy <= pb[3]):
                        continue
                    a = (pb[2] - pb[0]) * (pb[3] - pb[1])
                    if 800 < a < 200_000 and a < best_a:
                        best_a = a
                        parent_en = p.enabled
                        parent_click = p.clickable
                        hit = Node(
                            text=t,
                            desc=t,
                            rid=p.rid or n.rid,
                            clickable=True,
                            enabled=p.enabled,
                            bounds=p.bounds,
                            cls=p.cls,
                        )
            # Keep all labels for LLM context; only enabled chips are tappable.
            opt_labels.append(t)
            opt_nodes.append(hit)
            if parent_en or parent_click or hit.enabled:
                gap_nodes.append(hit)
            else:
                # already used / disabled — still list for context, not in chip pool
                pass
        if opt_labels and (
            gap_nodes
            or gap_sentence
            or "完成" in (st.instruction or "")
            or any(n.short_id == "storiesGapFillOption" for n in ns)
        ):
            # rebuild full gap pool including disabled labels' nodes for option list
            if not gap_nodes:
                gap_nodes = list(opt_nodes)
            gap_fill = True
            st.challenge = "gap_fill"  # type: ignore[attr-defined]
            st.gap_sentence = gap_sentence  # type: ignore[attr-defined]
            inferred = infer_gap_fill_words(gap_sentence, opt_labels)
            st.gap_words = inferred  # type: ignore[attr-defined]
            st.blank_count = len(inferred) if inferred else None  # type: ignore[attr-defined]

        # D) 排序题：content-desc 干净的句子卡（text 带 bidi 标记）
        is_sort = bool(
            by_id("storiesLessonCheckButton")
            or "順番" in st.instruction
            or "並べ" in st.instruction
            or "顺序" in st.instruction
        )
        if is_sort and not opt_labels:
            st.challenge = "sort"  # type: ignore[attr-defined]
            sort_nodes: list[Node] = []
            for n in ns:
                lab = (n.desc or "").strip()
                if not lab or len(lab) < 6:
                    continue
                if n.cls != "TextView":
                    continue
                b = parse_bounds(n.bounds)
                if not b:
                    continue
                if b[1] < 720 or b[3] > 2150:
                    continue
                if (b[2] - b[0]) < 200:
                    continue
                if lab in {"检查", "继续", "跳过"} or lab == st.instruction:
                    continue
                sort_nodes.append(n)
            sort_nodes.sort(key=lambda n: (parse_bounds(n.bounds) or (0, 0, 0, 0))[1])
            seen_l: set[str] = set()
            for n in sort_nodes:
                lab = n.desc.strip()
                if lab in seen_l:
                    continue
                seen_l.add(lab)
                opt_labels.append(lab)
                opt_nodes.append(
                    Node(
                        text=lab,
                        desc=lab,
                        rid=n.rid,
                        clickable=True,
                        enabled=True,
                        bounds=n.bounds,
                        cls=n.cls,
                    )
                )
        elif is_sort:
            st.challenge = "sort"  # type: ignore[attr-defined]

        st._option_nodes = opt_nodes
        st.options = list(dict.fromkeys(opt_labels))
        # gap-fill bank is also chips so multi-blank can use chips op
        if gap_fill and gap_nodes:
            st._chip_nodes = list(gap_nodes)
            # chips = currently tappable bank words; options = full bank labels
            st.chips = list(dict.fromkeys([(n.text or n.desc or "").strip() for n in gap_nodes if n.text or n.desc]))
            if not st.chips:
                st.chips = list(dict.fromkeys(opt_labels))
        else:
            st._chip_nodes = []
            st.chips = []
        st.image_options = []  # type: ignore[attr-defined]
        # Re-detect feedback with story-aware rules (buttons already set)
        st.feedback = detect_feedback(ns, st.buttons, st.raw_texts, activity=activity)
        return st

    # session end-ish
    blob = " ".join(texts)
    if any(k in blob for k in ("课程完成", "领取奖励", "Lesson complete", "你完成了", "精彩")) and not st.instruction:
        st.screen = "end"
        return st

    if "SessionActivity" in activity or st.instruction or by_id("submitButton"):
        st.screen = "session"
    elif "Legendary" in activity:
        # intro / gate before legendary session — still "starting"
        st.screen = "other"
    else:
        st.screen = "other"

    # Word-bank chips: collect by exclusion, not a tight y window.
    # (Fixed y cuts kept dropping bank rows next to 检查, e.g. よく/も.)
    # Skip prompt, chrome, feedback; skip answer-tray row if we can detect bank lower cluster.
    chip_nodes: list[Node] = []
    prompt_text = st.prompt
    for n in ns:
        if n.cls != "TextView":
            continue
        if n.short_id in {
            "challengeInstruction",
            "hintablePrompt",
            "submitButton",
            "continueButton",
            "playerButton",
            "headerText",
            "sectionUnitText",
            "teachingObjectiveText",
            "titleText",
            "subtitleText",
        }:
            continue
        lab = n.label
        if not lab:
            continue
        if lab in _FEEDBACK_NOISE:
            continue
        if lab in {
            "检查",
            "继续",
            "跳过",
            "CHECK",
            "CONTINUE",
            "知道了",
            "不正确",
            "正确答案：",
            "差了一点点哦～",
            "轻点此处查看词库",
            "翻译这句话",
            "完成对话",
            "选择配对",
            "选择对应的图片",
            "新",
            "单词",
        }:
            continue
        if prompt_text and lab == prompt_text:
            continue
        if prompt_text and len(lab) > 8 and lab in prompt_text:
            continue
        b = parse_bounds(n.bounds)
        if not b:
            continue
        # skip chrome top / full-width bars
        if b[1] < 400:
            continue
        if (b[2] - b[0]) > 900:
            continue
        if (b[3] - b[1]) <= 6:
            continue
        # skip hearts etc.
        if "红心" in lab or "连胜" in lab:
            continue
        chip_nodes.append(n)
    chip_nodes = unique_chips(chip_nodes)
    # drop feedback chrome mis-parsed as chips (你太棒了 etc.)
    chip_nodes = [c for c in chip_nodes if c.label not in _FEEDBACK_NOISE]
    st._chip_nodes = chip_nodes
    st.chips = [c.label for c in chip_nodes]

    # options: mid-screen selectable answers + optionText labels (match pairs)
    # + image cards (选择对应的图片): option1..option4 with imageText caption
    opt_nodes: list[Node] = []
    seen_bounds: set[str] = set()
    # keep every card; CN/JP cognates may share identical text (e.g. 胸/胸)
    option_text_nodes: list[Node] = []
    image_options: list[dict] = []  # {id, text, bounds}

    # Pair optionN clickable with nearby imageText
    option_slots: list[Node] = []
    image_texts: list[Node] = []
    for n in ns:
        if n.short_id == "optionText" and n.text:
            option_text_nodes.append(n)
        if n.short_id == "imageText" and n.text:
            image_texts.append(n)
        if n.short_id.startswith("option") and n.clickable and n.bounds:
            option_slots.append(n)
        b = parse_bounds(n.bounds)
        if not b:
            continue
        if n.clickable and 450 < b[1] < 2000:
            if n.short_id in {"settingsButton", "submitButton", "continueButton"}:
                continue
            if "Tab" in n.desc or "tab" in n.short_id.lower():
                continue
            if n.bounds in seen_bounds:
                continue
            if b[1] < 280:
                continue
            seen_bounds.add(n.bounds)
            opt_nodes.append(n)

    for slot in option_slots:
        sb = parse_bounds(slot.bounds)
        if not sb:
            continue
        cap = ""
        for it in image_texts:
            ib = parse_bounds(it.bounds)
            if not ib:
                continue
            # caption inside or overlapping option card
            cx, cy = (ib[0] + ib[2]) // 2, (ib[1] + ib[3]) // 2
            if sb[0] <= cx <= sb[2] and sb[1] <= cy <= sb[3]:
                cap = it.text
                break
        image_options.append(
            {"id": slot.short_id, "text": cap, "bounds": slot.bounds}
        )
        if cap:
            # image captions: still collect as synthetic nodes (no bounds dup with optionText)
            option_text_nodes.append(
                Node(text=cap, desc="", rid=slot.rid, clickable=True, bounds=slot.bounds, cls=slot.cls)
            )

    # Spatial order top→bottom, left→right (stable for match board)
    def _opt_pos(n: Node):
        b = parse_bounds(n.bounds) or (0, 0, 0, 0)
        return (b[1] // 20, b[0])

    option_text_nodes.sort(key=_opt_pos)
    option_texts = [(n.text or n.desc or "").strip() for n in option_text_nodes]
    option_texts = [t for t in option_texts if t]

    st._option_nodes = opt_nodes
    # 配对：禁止按文案去重。中日同形/同汉字词（如「胸」）左右各一张，文案相同也是两张卡。
    # 其它题型仍去重。
    pairing = "配对" in (st.instruction or "") or "Match" in (st.instruction or "")
    st.match_left = []  # type: ignore[attr-defined]
    st.match_right = []  # type: ignore[attr-defined]
    if option_texts:
        if pairing:
            st.options = option_texts  # one entry per card on the board
            # 按 x 中心分成左列 / 右列（各 5 张），降低模型配对难度
            with_cx: list[tuple[int, int, str]] = []
            for n in option_text_nodes:
                t = (n.text or n.desc or "").strip()
                b = parse_bounds(n.bounds)
                if not t or not b:
                    continue
                cx = (b[0] + b[2]) // 2
                with_cx.append((b[1], cx, t))
            if len(with_cx) >= 4:
                cxs = sorted(cx for _, cx, _ in with_cx)
                # 中位数分割两列（1080 宽屏上左~250 右~750）
                mid_x = cxs[len(cxs) // 2]
                # 若两簇分得很开，用两簇均值更稳
                if cxs[-1] - cxs[0] > 200:
                    mid_x = (cxs[0] + cxs[-1]) // 2
                left = sorted([(y, t) for y, cx, t in with_cx if cx < mid_x])
                right = sorted([(y, t) for y, cx, t in with_cx if cx >= mid_x])
                # 若分列失败（一边空），回退半宽
                if not left or not right:
                    mid_x = 540
                    left = sorted([(y, t) for y, cx, t in with_cx if cx < mid_x])
                    right = sorted([(y, t) for y, cx, t in with_cx if cx >= mid_x])
                st.match_left = [t for _, t in left]  # type: ignore[attr-defined]
                st.match_right = [t for _, t in right]  # type: ignore[attr-defined]
                # options 仍用 左列自上而下 + 右列自上而下，便于核对张数
                st.options = list(st.match_left) + list(st.match_right)
        else:
            st.options = list(dict.fromkeys(option_texts))
    else:
        labs = [o.label for o in opt_nodes if o.label]
        st.options = labs if pairing else list(dict.fromkeys(labs))

    # expose image cards for choice tapping
    st.image_options = image_options  # type: ignore[attr-defined]

    return st


def expand_word_bank_if_needed(st: UiState | None = None) -> UiState:
    """
    Some translate screens collapse the chip tray:
      「轻点此处查看词库」 — tap once to reveal chips.
    Hardcoded, no AI.
    """
    st = st or get_state()
    blob = " ".join(st.raw_texts)
    if "轻点此处查看词库" not in blob and "查看词库" not in blob:
        return st
    # already have a real bank?
    if len(st.chips) >= 2:
        return st
    # tap the tapInputView / hint area (around y=1000 from dumps)
    tapped = False
    for n in st._all:
        t = (n.text or "") + (n.desc or "")
        if "词库" in t and n.bounds:
            # prefer clickable parent covering this text
            tb = parse_bounds(n.bounds)
            if tb:
                for p in st._all:
                    if not p.clickable or not p.bounds:
                        continue
                    pb = parse_bounds(p.bounds)
                    if not pb:
                        continue
                    cx, cy = (tb[0] + tb[2]) // 2, (tb[1] + tb[3]) // 2
                    if pb[0] <= cx <= pb[2] and pb[1] <= cy <= pb[3]:
                        area = (pb[2] - pb[0]) * (pb[3] - pb[1])
                        if area < 1080 * 800:
                            tap_bounds(p.bounds, delay=0.35)
                            tapped = True
                            break
            if not tapped:
                tap_bounds(n.bounds, delay=0.35)
                tapped = True
            break
    if not tapped:
        # fallback fixed zone from dumps: ~[44,999]–[1036,1100]
        tap_xy(540, 1050, delay=0.35)
    time.sleep(0.45)
    return get_state()


def get_state() -> UiState:
    activity = focus_activity()
    root = dump_root()
    st = classify(iter_nodes(root), activity)
    return st


def cmd_status(_: argparse.Namespace) -> int:
    st = get_state()
    d = st.to_public_dict()
    if not d.get("duolingo"):
        d["warning"] = f"NOT Duolingo — foreground is {d.get('package')!r}. Refuse actions until foreground."
    print(json.dumps(d, ensure_ascii=False, indent=2))
    return 0 if d.get("duolingo") else 3


def cmd_path_targets(_: argparse.Namespace) -> int:
    """List gold vs incomplete path nodes without tapping."""
    try:
        require_duolingo()
    except RuntimeError as e:
        emit({"error": str(e), "package": current_package()})
        return 3
    st = get_state()
    gold = []
    for n in st._all:
        if n.short_id == "oval" and n.cls == "LinearLayout" and n.clickable and n.bounds:
            b = parse_bounds(n.bounds)
            if b and 250 < b[1] < 2150:
                gold.append({"y": b[1], "bounds": n.bounds, "kind": "gold"})
    gold.sort(key=lambda g: g["y"])
    inc = incomplete_path_targets(st._all)
    emit(
        {
            "package": current_package(),
            "gold_linearlayout": gold,
            "incomplete_framelayout": [{"y": t["y"], "bounds": t["bounds"]} for t in inc],
            "rule": "only tap incomplete_framelayout (FrameLayout oval+icon)",
        }
    )
    return 0


def cmd_screenshot(args: argparse.Namespace) -> int:
    path = Path(args.path) if args.path else SCREEN_PATH
    p = screenshot(path)
    print(json.dumps({"screenshot": str(p)}, ensure_ascii=False))
    return 0


# Labels / decorations — never treat as start CTAs
_NON_CTA_IDS = frozenset(
    {
        "subtitleText",
        "titleText",
        "headerText",
        "teachingObjectiveText",
        "sectionUnitText",
        "popupText",
        "hintablePrompt",
        "challengeInstruction",
    }
)

# Real start buttons (resource-id short names)
_START_BUTTON_IDS = (
    "xpBoostLearnButton",
    "legendaryButton",
    "startButton",
)


def _text_has_review(*parts: str) -> bool:
    """任何文案含「复习」→ 禁止点击。"""
    for p in parts:
        if not p:
            continue
        if "复习" in p or "review" in p.lower():
            return True
    return False


def _is_review_cta(n: Node) -> bool:
    """节点自身带「复习」——禁止。"""
    return _text_has_review(n.text or "", n.desc or "", n.short_id or "")


# 只有这些节点上的「复习」才算复习入口（忽略标题/正文里的「复习」二字）
_REVIEW_CTA_IDS = frozenset(
    {
        "xpBoostLearnButtonType",
        "xpBoostLearnButton",
        "learnButton",
        "startButton",
        "primaryButton",
        "legendaryButton",
        "playerContinueButton",
    }
)


def _is_review_button_text(text: str) -> bool:
    """按钮文案是否表示「去复习」而不是正文提到复习。"""
    t = (text or "").strip()
    if not t:
        return False
    # 明确按钮：复习 / 开始复习 / 开始复习 +15 经验
    if t == "复习" or t.startswith("开始复习") or t.startswith("复习 "):
        return True
    if t.startswith("复习+") or "开始复习" in t:
        return True
    # 单独一个词就是复习
    if t in {"复习", "Review", "REVIEW", "Practice"}:
        return True
    return False


def _popup_mentions_review(ns: list[Node]) -> bool:
    """
    是否出现「复习」类开课按钮（黑名单）。

    只看按钮/类型标签，不看 titleText、subtitle、说明正文。
    否则说明里写了「复习」会被误判成复习弹窗，正常「开始」点不了。
    """
    for n in ns:
        sid = n.short_id or ""
        text = (n.text or "").strip()
        desc = (n.desc or "").strip()
        # 1) 类型标签：xpBoostLearnButtonType =「复习」
        if sid == "xpBoostLearnButtonType" and (
            _is_review_button_text(text) or "复习" in text
        ):
            return True
        # 2) 主按钮上写着开始复习 / 复习
        if sid in _REVIEW_CTA_IDS and (
            _is_review_button_text(text) or _is_review_button_text(desc)
        ):
            return True
        # 3) 可点宽按钮，文案明确是复习入口
        if n.clickable and n.bounds and _is_review_button_text(text):
            return True
    return False


def _is_jump_test_cta(n: Node) -> bool:
    """
    真正的跳级测试入口，不要点。
    注意：阶段地图上的「跳级到这里」文案不能算（会误伤整页）。
    """
    blob = (n.text or "") + (n.desc or "")
    if n.short_id == "primaryButton" and ("开始测试" in blob or "测试" in blob):
        return True
    keys = ("开始测试", "通关测试", "开始跳级测试")
    return any(k in blob for k in keys)


def _is_listening_cta(n: Node) -> bool:
    """听力入口：开始收听 — 不要点，改点「稍后选择」。"""
    blob = (n.text or "") + (n.desc or "")
    keys = ("开始收听", "收听练习", "听力练习", "Listen", "listening")
    return any(k in blob for k in keys)


def _popup_has_listening(ns: list[Node]) -> bool:
    return any(_is_listening_cta(n) for n in ns) or any(
        "开始收听" in ((n.text or "") + (n.desc or "")) for n in ns
    )


def _popup_button_type(ns: list[Node]) -> str:
    """
    弹窗主按钮类型（黑名单判定用）:
      listening | review | start | unknown
    「巩固薄弱技能」等不算黑名单 → unknown/start 均可点。
    """
    for n in ns:
        if n.short_id == "xpBoostLearnButtonType" and (n.text or "").strip():
            t = n.text.strip()
            if "收听" in t:
                return "listening"
            if "复习" in t:
                return "review"
            if "开始" in t:
                return "start"
    blob = " ".join((n.text or "") for n in ns)
    if "开始收听" in blob:
        return "listening"
    for n in ns:
        if n.short_id == "learnButton" and n.text:
            if "复习" in n.text:
                return "review"
            if "收听" in n.text:
                return "listening"
            if "开始" in n.text:
                return "start"
    return "unknown"


def _is_jump_test_screen(ns: list[Node]) -> bool:
    """跳级/通关测试弹窗（黑名单：不点「准备开始/开始测试」）。"""
    blob = " ".join((n.text or "") + (n.desc or "") for n in ns)
    has_later = any(
        (n.text or "").strip() in {"下次再说", "以后再说"} or n.short_id == "tertiaryButton"
        for n in ns
    )
    jumpish = any(
        k in blob
        for k in ("开始测试", "通关测试", "跳级到这儿", "跳级到这", "直接跳级", "挑战通关")
    )
    if not has_later:
        return False
    if jumpish:
        return True
    if "测试" in blob and any(
        (n.text or "").strip() in {"准备开始", "开始测试"} for n in ns
    ):
        return True
    return False


def _cta_blacklisted(n: Node, ns: list[Node]) -> bool:
    """
    黑名单（用户口径）：默认可点，只禁这些。
      - 复习
      - 开始收听 / 收听*
      - 跳级测试的主按钮（开始测试 / 准备开始 在跳级上下文）
      - 下次再说 / 稍后选择（关弹窗用，不当开课）
    """
    blob = (n.text or "") + (n.desc or "")
    if _text_has_review(blob):
        return True
    if _is_listening_cta(n) or "开始收听" in blob or (
        "收听" in blob and "开始" in blob
    ):
        return True
    t = (n.text or "").strip()
    if t in {"下次再说", "以后再说", "稍后选择"}:
        return True
    # 整屏是跳级测试时，禁止点 primary 上的 准备开始/开始测试
    if _is_jump_test_screen(ns):
        if t in {"准备开始", "开始测试"} or n.short_id == "primaryButton":
            return True
        if _is_jump_test_cta(n):
            return True
    # 整屏类型标签是复习/收听 → 主绿色按钮也算黑名单
    btype = _popup_button_type(ns)
    if btype == "review" and n.short_id in {
        "xpBoostLearnButton",
        "learnButton",
        "startButton",
        "primaryButton",
    }:
        return True
    if btype == "listening" and n.short_id in {
        "xpBoostLearnButton",
        "learnButton",
        "startButton",
        "primaryButton",
    }:
        return True
    if _popup_mentions_review(ns) and n.short_id in {
        "xpBoostLearnButton",
        "learnButton",
        "startButton",
        "primaryButton",
    }:
        return True
    return False


def _find_later_choice(ns: list[Node]) -> Node | None:
    """听力弹窗旁的「稍后选择」。"""
    for n in ns:
        if not n.bounds:
            continue
        blob = (n.text or "") + (n.desc or "")
        if "稍后选择" in blob or n.short_id == "skipButton" and "稍后" in blob:
            return n
        if n.short_id == "skipButton" and n.clickable and n.text:
            # 听力弹窗 secondary：稍后选择
            if "稍后" in n.text or "以后" in n.text or "Later" in n.text:
                return n
    for n in ns:
        if n.short_id == "skipButton" and n.clickable and n.bounds:
            # 与「开始收听」同屏的 skipButton 几乎就是稍后选择
            if _popup_has_listening(ns):
                return n
    return None


def _find_by_text(ns: list[Node], *needles: str, clickable_only: bool = False) -> Node | None:
    for n in ns:
        if clickable_only and not n.clickable:
            continue
        blob = (n.text or "") + (n.desc or "")
        if any(nd in blob for nd in needles) and n.bounds:
            if _is_review_cta(n) or _is_jump_test_cta(n) or _is_listening_cta(n):
                continue
            return n
    return None


def _is_legendary_cta(n: Node) -> bool:
    """Only the real legendary button — not subtitle copy that mentions 传奇."""
    if n.short_id == "legendaryButton":
        return True
    if n.short_id in _NON_CTA_IDS:
        return False
    blob = (n.text or "") + (n.desc or "")
    # Must look like the CTA, not "完成传奇挑战，展示你的传奇实力"
    return "晋升传奇" in blob


def _wide_cta(n: Node) -> bool:
    b = parse_bounds(n.bounds)
    return bool(b and (b[2] - b[0]) > 200 and (b[3] - b[1]) > 60)


def _is_plausible_cta(n: Node) -> bool:
    """看起来像底部主 CTA 的宽按钮（不含黑名单语义，黑名单另判）。"""
    if not n.bounds or n.short_id in _NON_CTA_IDS:
        return False
    if not _wide_cta(n):
        return False
    if n.short_id in _START_BUTTON_IDS or n.short_id == "primaryButton":
        return True
    if n.clickable and (n.text or n.desc):
        return True
    return False


def _find_start_cta(ns: list[Node]) -> Node | None:
    """
    黑名单模式（用户口径）：
      默认：宽主按钮 / 开始 / 打开 / 领取 / 巩固薄弱技能… 都可点
      黑名单：复习、开始收听、跳级测试主钮、稍后选择/下次再说
    """
    # 整屏是听力 → 不点开始收听（由稍后选择处理）
    if _popup_has_listening(ns) or _popup_button_type(ns) == "listening":
        return None
    # 整屏是复习 → 不点
    if _popup_mentions_review(ns) or _popup_button_type(ns) == "review":
        return None
    # 整屏是跳级测试 → 不点准备开始
    if _is_jump_test_screen(ns):
        return None

    candidates: list[Node] = []

    # 1) 标准主按钮 id
    for n in ns:
        if not n.bounds or not n.clickable:
            continue
        if n.short_id in {
            "learnButton",
            "xpBoostLearnButton",
            "startButton",
            "legendaryButton",
            "primaryButton",
        }:
            candidates.append(n)

    # 2) 文案像开课的宽按钮
    for n in ns:
        if not n.bounds or not n.clickable:
            continue
        blob = (n.text or "") + (n.desc or "")
        t = (n.text or "").strip()
        if not blob:
            continue
        if t in {"开始", "打开", "领取", "Start", "START", "Open"}:
            candidates.append(n)
        elif "开始 +" in t or (t.startswith("开始") and "经验" in t):
            candidates.append(n)
        elif "打开" in t or "领取" in t or "晋升传奇" in t:
            if _wide_cta(n):
                candidates.append(n)
        elif t == "开始" or (t.startswith("开始") and "收听" not in t and "测试" not in t):
            if _wide_cta(n):
                candidates.append(n)

    # 去重保序 + 黑名单过滤
    seen: set[str] = set()
    for n in candidates:
        key = n.bounds or id(n)
        if key in seen:
            continue
        seen.add(str(key))
        if _cta_blacklisted(n, ns):
            continue
        return n
    return None


def _popup_kind(ns: list[Node]) -> str:
    """Classify popup. 黑名单优先，其余有可点主钮 → startable。"""
    blob = " ".join((n.text or "") + (n.desc or "") for n in ns)
    # 阶段总览图
    if any(n.short_id == "courseTitle" for n in ns):
        return "section_map"
    if any(k in blob for k in ("未解锁", "完成以上全部等级才可以解锁", "锁着")):
        return "locked"
    # —— 黑名单类弹窗 ——
    if _popup_has_listening(ns) or _popup_button_type(ns) == "listening" or "开始收听" in blob:
        return "listening"
    if _popup_mentions_review(ns) or _popup_button_type(ns) == "review":
        return "review_only"
    if _is_jump_test_screen(ns):
        return "jump"
    # —— 默认可开：有任何非黑名单主按钮 ——
    if _find_start_cta(ns):
        return "startable"
    return "empty"


def _dismiss_same_entry(entry_bounds: str | None, steps: list[str], *, tag: str = "dismiss") -> None:
    """
    关弹窗铁律：点谁打开的，就再点谁关掉。
    禁止乱点空白/固定坐标（会误触黄条、别的圆点、进课程列表）。
    没有入口坐标时才 BACK。
    """
    if entry_bounds:
        steps.append(f"{tag}:same_entry:{entry_bounds}")
        tap_bounds(entry_bounds, delay=0.35)
        time.sleep(0.4)
        return
    steps.append(f"{tag}:no_entry→back")
    adb("shell", "input", "keyevent", "4", check=False)
    time.sleep(0.4)


def _dismiss_listening_popup(
    ns: list[Node], steps: list[str], *, entry_bounds: str | None = None
) -> str:
    """
    看到「开始收听」：
      - 有「稍后选择」→ 点它，返回 "later"
      - 没有 → 再点打开它的那个节点关掉，返回 "skip_unit"
    """
    later = _find_later_choice(ns)
    if later and later.bounds:
        steps.append(f"dismiss_listening:{later.text or later.short_id}")
        tap_bounds(later.bounds, delay=0.45)
        time.sleep(0.5)
        return "later"
    for n in ns:
        if n.bounds and "稍后选择" in ((n.text or "") + (n.desc or "")):
            steps.append("dismiss_listening:稍后选择")
            tap_bounds(n.bounds, delay=0.45)
            time.sleep(0.5)
            return "later"
    # 无稍后选择：点回入口节点关掉
    steps.append("listening_no_later→same_entry")
    _dismiss_same_entry(entry_bounds, steps, tag="listening_close")
    return "skip_unit"


def try_skip_in_session(steps: list[str] | None = None) -> bool:
    """
    Headphones / listening units: tap 跳过 if present (hardcoded, no AI).
    Returns True if a skip control was tapped.
    """
    if steps is None:
        steps = []
    require_duolingo()
    st = get_state()
    # settings gear sometimes hides skip — try visible first
    for needle in ("跳过", "Skip", "跳过此课", "跳过课程"):
        for n in st._all:
            blob = (n.text or "") + (n.desc or "")
            if needle in blob and n.bounds and "复习" not in blob:
                # avoid tiny icons without text in wrong place
                b = parse_bounds(n.bounds)
                if not b:
                    continue
                steps.append(f"skip:{n.short_id}:{n.text or n.desc}")
                tap_bounds(n.bounds, delay=0.45)
                time.sleep(0.6)
                # confirm dialog 跳过 / 确定
                st2 = get_state()
                for n2 in st2._all:
                    t = (n2.text or "") + (n2.desc or "")
                    if n2.bounds and any(k in t for k in ("跳过", "确定", "确认", "Skip", "是")):
                        if "取消" in t or "下次" in t:
                            continue
                        tap_bounds(n2.bounds, delay=0.4)
                        time.sleep(0.5)
                        break
                return True
    # gear menu
    for n in st._all:
        if n.short_id == "settingsButton" and n.bounds:
            steps.append("skip:open_settings")
            tap_bounds(n.bounds, delay=0.4)
            time.sleep(0.5)
            st2 = get_state()
            for n2 in st2._all:
                t = (n2.text or "") + (n2.desc or "")
                if n2.bounds and ("跳过" in t or "Skip" in t):
                    steps.append(f"skip:menu:{n2.text}")
                    tap_bounds(n2.bounds, delay=0.4)
                    time.sleep(0.5)
                    st3 = get_state()
                    for n3 in st3._all:
                        t3 = n3.text or ""
                        if n3.bounds and t3 in {"跳过", "确定", "确认", "是"}:
                            tap_bounds(n3.bounds, delay=0.4)
                            time.sleep(0.5)
                            return True
                    return True
            # close settings if no skip
            adb("shell", "input", "keyevent", "4", check=False)
            time.sleep(0.3)
            break
    return False


def _path_node_list(ns: list[Node]) -> list[Node]:
    """Legacy: clickable icon/oval (not chest). Prefer path_action_targets()."""
    out: list[tuple[int, Node]] = []
    for n in ns:
        if n.short_id not in {"icon", "oval"} or not n.clickable or not n.bounds:
            continue
        b = parse_bounds(n.bounds)
        if not b or not (250 < b[1] < 2150):
            continue
        out.append((b[1], n))
    out.sort(key=lambda x: x[0])
    return [n for _, n in out]


def incomplete_path_targets(ns: list[Node] | None = None) -> list[dict]:
    """
    Only UNFINISHED path lessons (not gold, not stars).

    Pattern agreed with user:
      oval  = FrameLayout, clickable=false
      icon  = FrameLayout, clickable=true
      same bounds (paired)

    Gold completed uses LinearLayout oval + ImageView icon — ignored.
    """
    # Need raw XML classes — Node.cls only has short class name, good enough
    if ns is None:
        # re-dump with class info already on nodes
        st = get_state()
        ns = st._all
    else:
        pass

    ovals: list[Node] = []
    icons: list[Node] = []
    for n in ns:
        if not n.bounds:
            continue
        b = parse_bounds(n.bounds)
        if not b or b[1] < 250 or b[1] > 2120:
            continue
        if n.short_id == "oval" and n.cls == "FrameLayout" and not n.clickable:
            ovals.append(n)
        if n.short_id == "icon" and n.cls == "FrameLayout" and n.clickable:
            icons.append(n)

    targets: list[dict] = []
    used_icon: set[str] = set()
    for ov in ovals:
        ob = parse_bounds(ov.bounds)
        if not ob:
            continue
        pair = None
        for ic in icons:
            if ic.bounds in used_icon:
                continue
            ib = parse_bounds(ic.bounds)
            if not ib:
                continue
            if abs(ib[0] - ob[0]) <= 8 and abs(ib[1] - ob[1]) <= 8:
                pair = ic
                break
        if not pair:
            continue
        used_icon.add(pair.bounds)
        targets.append(
            {
                "y": ob[1],
                "bounds": pair.bounds,  # tap the clickable icon
                "oval_bounds": ov.bounds,
                "tap_node": pair,
                "kind": "incomplete",  # pink or grey — not distinguished yet
            }
        )
    targets.sort(key=lambda t: t["y"])
    return targets


def chest_path_targets(ns: list[Node] | None = None) -> list[dict]:
    """Clickable treasure chests on the path (must open to progress)."""
    if ns is None:
        ns = get_state()._all
    out: list[dict] = []
    for n in ns:
        if n.short_id != "chest" or not n.clickable or not n.bounds:
            continue
        b = parse_bounds(n.bounds)
        if not b or b[1] < 250 or b[1] > 2120:
            continue
        out.append(
            {
                "y": b[1],
                "bounds": n.bounds,
                "tap_node": n,
                "kind": "chest",
            }
        )
    out.sort(key=lambda t: t["y"])
    return out


def path_action_targets(ns: list[Node] | None = None) -> list[dict]:
    """
    Path nodes to interact with, top→bottom:
      incomplete lessons + chests (chests block the road if skipped).
    """
    if ns is None:
        ns = get_state()._all
    targets = incomplete_path_targets(ns) + chest_path_targets(ns)
    targets.sort(key=lambda t: t["y"])
    return targets


def _tap_current_path_node(ns: list[Node]) -> bool:
    """Open the current path node popup (near 打开 tooltip / active icon)."""
    open_y = None
    for n in ns:
        if (n.text == "打开" or n.desc == "打开") and n.bounds:
            b = parse_bounds(n.bounds)
            if b:
                open_y = (b[1] + b[3]) // 2
    for n in ns:
        if n.short_id == "tooltip" and n.clickable and n.bounds:
            tap_bounds(n.bounds, delay=0.9)
            return True

    candidates: list[tuple[int, Node]] = []
    for n in _path_node_list(ns):
        b = parse_bounds(n.bounds)
        if not b:
            continue
        cy = (b[1] + b[3]) // 2
        score = abs(cy - open_y) if open_y is not None else abs(cy - 1100)
        if n.short_id == "oval":
            score += 80
        candidates.append((score, n))
    candidates.sort(key=lambda x: x[0])
    if candidates:
        tap_bounds(candidates[0][1].bounds, delay=0.9)
        return True
    return False


def _in_lesson(st: UiState) -> bool:
    """True only for real learn sessions — not DuoRadio / pure listening."""
    act = st.activity or ""
    # 听力电台课：用户不要，不算成功开课
    if "DuoRadio" in act or "RadioSession" in act:
        return False
    if "StoriesSession" in act:
        return True
    if st.screen == "session" or st.instruction:
        return True
    return "SessionActivity" in act


def _confirm_start_screens(steps: list[str], *, primary_cta: str) -> tuple[bool, dict]:
    """
    After tapping path CTA, clear intro gates (legendary intro, etc.).
    Never taps 开始复习 / 下次再说.
    """
    last_cta = primary_cta
    for i in range(4):
        st = get_state()
        if _in_lesson(st):
            return True, {"started": True, "cta": last_cta, "state": st.to_public_dict()}

        # Legendary intro / pre-session: "开始 +40 经验" —— 有「复习」整屏不点
        if _popup_mentions_review(st._all):
            steps.append(f"intro_blocked_review:{i}")
            break
        picked = None
        for n in st._all:
            if not n.bounds or _is_review_cta(n):
                continue
            blob = (n.text or "") + (n.desc or "")
            if _text_has_review(blob) or "收听" in blob:
                continue
            if "下次再说" in blob or "以后再说" in blob or "不了" in blob:
                continue
            if n.short_id in _NON_CTA_IDS:
                continue
            # real start on intro
            if n.clickable or n.short_id in _START_BUTTON_IDS or "Button" in n.short_id:
                if ("开始" in blob) or "晋升传奇" in blob:
                    # prefer wider bottom CTAs
                    if _wide_cta(n) or "经验" in blob:
                        picked = n
                        break
        # also match by exact-ish option text without clickable flag
        if not picked:
            for n in st._all:
                t = n.text or ""
                if _text_has_review(t):
                    continue
                if t.startswith("开始") and "经验" in t and n.bounds:
                    picked = n
                    break

        if picked:
            steps.append(f"intro_cta:{picked.short_id}:{picked.text}")
            last_cta = picked.text or picked.short_id
            tap_bounds(picked.bounds, delay=AFTER_CTA * 0.6)
            time.sleep(AFTER_CTA)
            continue

        steps.append(f"intro_wait:{i}:{st.screen}")
        time.sleep(0.35)

    st = get_state()
    ok = _in_lesson(st)
    return ok, {"started": ok, "cta": last_cta, "state": st.to_public_dict()}


def _try_tap_cta(cta: Node, steps: list[str], *, popup_ns: list[Node] | None = None) -> tuple[bool, dict]:
    """Tap CTA; hard-refuse review / listening. Returns (ok, payload extras)."""
    # 点之前再扫一遍整屏：有「复习」就死也不点
    if popup_ns is not None and _popup_mentions_review(popup_ns):
        steps.append("blocked_review:screen_mentions_复习")
        return False, {"error": "refused review (screen has 复习)", "started": False}
    if _is_review_cta(cta) or _text_has_review(cta.text or "", cta.desc or ""):
        steps.append(f"blocked_review:{cta.short_id}:{cta.text}")
        return False, {"error": "refused review CTA", "cta": cta.text, "started": False}
    if _is_listening_cta(cta) or "收听" in ((cta.text or "") + (cta.desc or "")):
        steps.append(f"blocked_listening:{cta.short_id}:{cta.text}")
        return False, {"error": "refused listening CTA", "cta": cta.text, "started": False}
    label = f"{cta.short_id or ''}:{cta.text}"
    steps.append(f"cta:{label}")
    tap_bounds(cta.bounds, delay=AFTER_CTA * 0.5)
    time.sleep(AFTER_CTA * 0.8)
    return _confirm_start_screens(steps, primary_cta=cta.text or cta.short_id)


def _ensure_learn_path(steps: list[str]) -> UiState:
    """Back out of section map / stray screens onto the house path."""
    st = get_state()
    for _ in range(4):
        kind = _popup_kind(st._all)
        if kind == "section_map":
            steps.append("leave_section_map")
            for n in st._all:
                if n.short_id == "quitButton" and n.bounds:
                    tap_bounds(n.bounds, delay=0.4)
                    break
            else:
                adb("shell", "input", "keyevent", "4", check=False)
            time.sleep(0.6)
            st = get_state()
            continue
        if kind == "jump":
            for n in st._all:
                if (n.text == "下次再说" or n.short_id == "tertiaryButton") and n.bounds:
                    steps.append("dismiss_jump_pre")
                    tap_bounds(n.bounds, delay=0.4)
                    time.sleep(0.5)
                    break
            else:
                adb("shell", "input", "keyevent", "4", check=False)
                time.sleep(0.4)
            st = get_state()
            continue
        if kind == "listening":
            _dismiss_listening_popup(st._all, steps)
            st = get_state()
            continue
        if st.screen == "home":
            return st
        # try Learn tab
        for n in st._all:
            if n.short_id == "tabLearn" and n.bounds:
                steps.append("tap_tabLearn")
                tap_bounds(n.bounds, delay=0.4)
                time.sleep(0.7)
                break
        else:
            adb("shell", "input", "keyevent", "4", check=False)
            time.sleep(0.5)
        st = get_state()
    return st


def cmd_start(_: argparse.Namespace) -> int:
    """
    Enter a lesson / clear path blockers.

      Path targets (top→bottom): incomplete lessons first, then chests.
      (Locked chests often don't open — don't block forever.)

      Popup handling:
        开始 +经验 → enter
        打开/领取 → claim chest
        开始收听 + 稍后选择 → 稍后选择，再试下一个节点
        开始收听且无稍后选择 → 关弹窗，跳过本单元
        开始测试+下次再说 → 下次再说
        开始复习 / 锁 → dismiss, next
    """
    try:
        require_duolingo()
    except RuntimeError as e:
        emit({"error": str(e), "started": False, "package": current_package()})
        return 3
    if current_package() != DUOLINGO_PKG:
        emit({"error": "not on Duolingo", "started": False, "package": current_package()})
        return 3
    steps: list[str] = []
    skip_bounds: set[str] = set()

    st = _ensure_learn_path(steps)

    def _handle_open_popup(st_now: UiState, *, picked: dict | None = None) -> tuple[bool, dict]:
        kind = _popup_kind(st_now._all)
        steps.append(f"popup:{kind}")

        if kind == "section_map":
            steps.append("unexpected_section_map")
            for n in st_now._all:
                if n.short_id == "quitButton" and n.bounds:
                    tap_bounds(n.bounds, delay=0.4)
                    break
            else:
                adb("shell", "input", "keyevent", "4", check=False)
            time.sleep(0.5)
            return False, {"dismissed": "section_map"}

        entry = str(picked["bounds"]) if picked and picked.get("bounds") else None

        if kind == "listening":
            how = _dismiss_listening_popup(st_now._all, steps, entry_bounds=entry)
            if entry:
                skip_bounds.add(entry)
                steps.append(f"mark_skip_listening:{entry}")
            return False, {
                "dismissed": "listening_later" if how == "later" else "listening_skip_unit",
                "skip_unit": True,
            }

        if kind == "jump":
            for m in st_now._all:
                if (m.text == "下次再说" or m.short_id == "tertiaryButton") and m.bounds:
                    tap_bounds(m.bounds, delay=0.4)
                    steps.append("dismiss_jump:下次再说")
                    time.sleep(0.45)
                    if entry:
                        skip_bounds.add(entry)
                    return False, {"dismissed": "jump", "skip_unit": True}
            # 没有「下次再说」：点回入口关掉
            _dismiss_same_entry(entry, steps, tag="jump_close")
            if entry:
                skip_bounds.add(entry)
            return False, {"dismissed": "jump_same_entry", "skip_unit": True}

        if kind == "locked":
            steps.append("locked_skip")
            _dismiss_same_entry(entry, steps, tag="locked_close")
            if entry:
                skip_bounds.add(entry)
            return False, {"skip_unit": True}

        if kind == "review_only":
            # 复习：点谁打开就点谁关掉（不要乱点空白/黄条）
            steps.append("review_only_skip")
            _dismiss_same_entry(entry, steps, tag="review_close")
            if entry:
                skip_bounds.add(entry)
            return False, {"skip_unit": True, "dismissed": "review_only"}

        if kind == "startable":
            # 双保险：屏上有「复习」→ 当复习，点回入口关掉
            if _popup_mentions_review(st_now._all):
                steps.append("startable_but_has_复习→same_entry")
                _dismiss_same_entry(entry, steps, tag="review_close")
                if entry:
                    skip_bounds.add(entry)
                return False, {"skip_unit": True, "dismissed": "review_only"}
            cta = _find_start_cta(st_now._all)
            if cta:
                is_chest_claim = (picked or {}).get("kind") == "chest" or any(
                    k in ((cta.text or "") + (cta.desc or "")) for k in ("打开", "领取")
                )
                ok, extra = _try_tap_cta(cta, steps, popup_ns=st_now._all)
                if ok:
                    st_chk = get_state()
                    act = st_chk.activity or ""
                    if "DuoRadio" in act or "RadioSession" in act:
                        # 误进听力电台：退出并跳过
                        steps.append("abort_duoradio")
                        adb("shell", "input", "keyevent", "4", check=False)
                        time.sleep(0.5)
                        # 确认退出弹窗
                        st2 = get_state()
                        for n in st2._all:
                            if n.bounds and any(
                                k in (n.text or "") for k in ("退出", "结束", "离开", "放弃")
                            ):
                                tap_bounds(n.bounds, delay=0.4)
                                time.sleep(0.4)
                                break
                        if picked and picked.get("bounds"):
                            skip_bounds.add(str(picked["bounds"]))
                        return False, {"skip_unit": True, "dismissed": "duoradio"}
                    # 仅在真正进 session 后尝试听力跳过
                    if st_chk.screen == "session":
                        try_skip_in_session(steps)
                    return True, {**extra, "picked": picked, "started": True}
                if is_chest_claim:
                    steps.append("chest_claim_tapped")
                    time.sleep(0.5)
                    return True, {
                        "started": False,
                        "chest_opened": True,
                        "picked": picked,
                        "cta": cta.text or cta.short_id,
                    }
            return False, {}

        # empty: no popup
        return False, {"dismissed": "empty"}

    # Pass 1: already-open popup
    kind0 = _popup_kind(st._all)
    if kind0 not in {"empty"}:
        done, extra = _handle_open_popup(st, picked=None)
        if done and extra.get("started"):
            emit({"steps": steps, **extra, "state": get_state().to_public_dict()})
            return 0
        st = get_state()
        st = _ensure_learn_path(steps)

    def _try_home_startable(tag: str) -> bool:
        """
        黑名单模式：屏上已有非黑名单主按钮就点（含巩固薄弱技能、开始+经验等）。
        不依赖路径圆点。
        """
        st_p = get_state()
        kind = _popup_kind(st_p._all)
        if kind in {"listening", "review_only", "jump", "section_map", "locked"}:
            return False
        cta = _find_start_cta(st_p._all)
        if not cta or not cta.bounds:
            return False
        blob = " ".join(st_p.raw_texts)
        title = "巩固薄弱技能" if "巩固薄弱技能" in blob else (cta.text or cta.short_id or "start")
        steps.append(f"{tag}:home_start→{title}")
        ok, extra = _try_tap_cta(cta, steps, popup_ns=st_p._all)
        if not ok:
            return False
        st_chk = get_state()
        act = st_chk.activity or ""
        if "DuoRadio" in act or "RadioSession" in act:
            steps.append(f"{tag}:entered_radio→abort")
            adb("shell", "input", "keyevent", "4", check=False)
            time.sleep(0.5)
            return False
        if st_chk.screen == "session" or _in_lesson(st_chk):
            if st_chk.screen == "session":
                try_skip_in_session(steps)
            emit(
                {
                    "steps": steps,
                    "started": True,
                    "cta": cta.text or cta.short_id,
                    "picked": {"kind": "home_cta", "title": title},
                    "state": st_chk.to_public_dict(),
                }
            )
            return True
        steps.append(f"{tag}:tap_but_not_session")
        return False

    # Pass 1.5：屏上已有可点开始（含巩固薄弱技能）→ 直接开，不依赖路径圆点
    if _try_home_startable("pass1_5"):
        return 0

    # Pass 2: incomplete lessons first, then chests (locked chests won't block forever)
    def _ordered_targets(ns: list[Node]) -> list[dict]:
        inc = incomplete_path_targets(ns)
        chests = chest_path_targets(ns)
        # 未完成课优先；宝箱穿插在路径 y 序里但跳过点不开的
        mixed = inc + chests
        mixed.sort(key=lambda t: t["y"])
        return mixed

    targets = _ordered_targets(st._all)
    steps.append(f"path_targets:{len(targets)}")
    for t in targets:
        steps.append(f"path_{t['kind']}_y:{t['y']}")

    if not targets:
        emit(
            {
                "error": "no incomplete lessons or chests on path",
                "started": False,
                "steps": steps,
                "package": current_package(),
                "state": st.to_public_dict(),
            }
        )
        return 1

    for t in targets:
        if current_package() != DUOLINGO_PKG:
            emit({"error": "left Duolingo during start", "package": current_package(), "steps": steps})
            return 3
        bkey = str(t.get("bounds") or "")
        if bkey and bkey in skip_bounds:
            steps.append(f"skip_marked:{t['kind']}:{bkey}")
            continue

        steps.append(f"tap_{t['kind']}:{t['bounds']}")
        tap_bounds(t["bounds"], delay=PATH_TAP)
        time.sleep(0.85)
        st = get_state()
        kind = _popup_kind(st._all)
        steps.append(f"after_tap:{kind}")

        # 宝箱点了没弹窗 = 多半还锁着，别死磕
        if t.get("kind") == "chest" and kind == "empty":
            steps.append(f"chest_locked_or_noop:{t['bounds']}")
            skip_bounds.add(bkey)
            continue

        done, extra = _handle_open_popup(
            st, picked={"y": t.get("y"), "bounds": t.get("bounds"), "kind": t.get("kind")}
        )
        if done and extra.get("started"):
            emit(
                {
                    "steps": steps,
                    **{k: v for k, v in extra.items() if k != "state"},
                    "state": get_state().to_public_dict(),
                }
            )
            return 0
        if done and extra.get("chest_opened"):
            steps.append("chest_opened_ok")
            st = _ensure_learn_path(steps)
            continue
        if extra.get("skip_unit") or extra.get("dismissed") in {
            "listening_later",
            "listening_skip_unit",
            "jump",
            "jump_back",
            "review_only",
        }:
            # 听力稍后选择后：先抢「巩固薄弱技能」（用户明确要求可点），再扫下一个路径点
            st = get_state()
            if extra.get("dismissed") in {"listening_later", "listening_skip_unit"}:
                if _try_home_startable("after_listening"):
                    return 0
            continue

    # Pass 3：路径扫完仍未开课 → 再试屏上任意非黑名单开始
    if _try_home_startable("pass3"):
        return 0

    emit(
        {
            "error": "no startable lesson after path scan",
            "started": False,
            "steps": steps,
            "package": current_package(),
            "state": get_state().to_public_dict(),
        }
    )
    return 1


def _chip_label_match(n: Node, label: str) -> bool:
    if n.label == label or n.text == label or n.desc == label:
        return True
    return n.label.replace(" ", "") == label.replace(" ", "")


def _center_key(bounds: str, grid: int = 24) -> tuple[int, int] | None:
    c = center_of(bounds)
    if not c:
        return None
    return (c[0] // grid, c[1] // grid)


def find_chip_candidates(st: UiState, label: str, *, exclude_keys: set[tuple[int, int]]) -> list[Node]:
    """All remaining bank chips for label, distinct screen positions, L→R then T→B."""
    out: list[Node] = []
    seen: set[tuple[int, int]] = set()
    for n in st._chip_nodes:
        if not _chip_label_match(n, label) or not n.bounds:
            continue
        key = _center_key(n.bounds)
        if key is None or key in seen or key in exclude_keys:
            continue
        seen.add(key)
        out.append(n)

    def sort_key(n: Node):
        b = parse_bounds(n.bounds) or (0, 0, 0, 0)
        return (b[1] // 30, b[0])

    return sorted(out, key=sort_key)


def clickable_bounds_for(node: Node, all_nodes: list[Node]) -> str:
    """
    Prefer the SMALLEST clickable container covering the glyph center.
    (Largest parent was wrong: whole word-bank → every の tapped the same place.)
    """
    tb = parse_bounds(node.bounds)
    if not tb:
        return node.bounds
    tcx, tcy = (tb[0] + tb[2]) // 2, (tb[1] + tb[3]) // 2
    best = node.bounds
    best_area = (tb[2] - tb[0]) * (tb[3] - tb[1])
    # If text is already reasonable size, keep it unless a slightly larger chip pad exists
    for n in all_nodes:
        if not n.clickable:
            continue
        b = parse_bounds(n.bounds)
        if not b:
            continue
        if not (b[0] <= tcx <= b[2] and b[1] <= tcy <= b[3]):
            continue
        w, h = b[2] - b[0], b[3] - b[1]
        area = w * h
        # chip-sized only — reject full-width bank containers
        if w > 420 or h > 200 or area > 80_000:
            continue
        # tightest fit that still larger than tiny underline
        if area < best_area and area >= 800:
            best_area = area
            best = n.bounds
        elif best == node.bounds and 800 <= area <= 80_000 and area > best_area:
            # text node not clickable; take modest chip pad
            best_area = area
            best = n.bounds
    return best


def count_chip(st: UiState, label: str) -> int:
    return len(find_chip_candidates(st, label, exclude_keys=set()))


def answer_tray_labels(st: UiState) -> list[str]:
    """Words already placed in the construction area (above bank)."""
    labels: list[tuple[int, int, str]] = []
    for n in st._all:
        if n.cls != "TextView":
            continue
        lab = n.label
        if not lab or lab in {"检查", "继续", "跳过", "CHECK"}:
            continue
        b = parse_bounds(n.bounds)
        if not b:
            continue
        # tray roughly mid-screen; bank is y>=1700
        if 900 <= b[1] < 1700 and (b[2] - b[0]) < 900:
            labels.append((b[1], b[0], lab))
    labels.sort()
    # dedupe glyph+underline
    out: list[str] = []
    prev = None
    for y, x, lab in labels:
        key = (lab, x // 30, y // 50)
        if key == prev:
            continue
        prev = key
        out.append(lab)
    return out


def cmd_chips(args: argparse.Namespace) -> int:
    """
    Fast path: 1 dump → plan all chip centers → rapid taps → 1 verify dump.
    Avoids per-chip uiautomator dump (was ~0.5–1s each).
    """
    from collections import defaultdict, deque

    try:
        require_duolingo()
    except RuntimeError as e:
        emit({"error": str(e), "package": current_package()})
        return 3

    words: list[str] = args.words
    st = get_state()
    is_story = getattr(st, "mode", None) == "story" or _is_stories_ui(st._all, st.activity)
    is_gap = getattr(st, "challenge", None) == "gap_fill" or bool(st.chips and is_story)

    # Stories gap-fill: options live in _option_nodes; also mirror into chip pools
    chip_source = list(st._chip_nodes)
    if is_gap and not chip_source and st._option_nodes:
        chip_source = list(st._option_nodes)

    need: dict[str, int] = {}
    for w in words:
        need[w] = need.get(w, 0) + 1

    def _count_in(src: list[Node], label: str) -> int:
        return sum(1 for n in src if _chip_label_match(n, label) and n.bounds)

    short = {w: need[w] for w in need if _count_in(chip_source, w) < need[w]}
    if short and not is_gap:
        # lesson path: fall back to st._chip_nodes via count_chip
        short = {w: need[w] for w in need if count_chip(st, w) < need[w]}
    if short:
        emit(
            {
                "error": "not enough chip copies",
                "need": need,
                "short": short,
                "available": st.chips or st.options,
                "available_counts": {w: _count_in(chip_source, w) for w in need},
            }
        )
        return 1

    # pools of distinct positions per label
    pools: dict[str, deque] = defaultdict(deque)
    seen_keys: set[tuple] = set()
    for n in chip_source or st._chip_nodes:
        lab = n.label or n.text
        if not lab or not n.bounds:
            continue
        key = (lab, _center_key(n.bounds))
        if key in seen_keys or key[1] is None:
            continue
        seen_keys.add(key)
        c = center_of(n.bounds)
        if c:
            pools[lab].append({"word": lab, "bounds": n.bounds, "center": c})

    plan: list[dict] = []
    for w in words:
        # fuzzy match pool key
        q = pools.get(w)
        if not q:
            for k in list(pools.keys()):
                if k.replace(" ", "") == w.replace(" ", ""):
                    q = pools[k]
                    break
        if not q:
            emit(
                {
                    "error": "chip vanished while planning",
                    "missing": w,
                    "planned": [p["word"] for p in plan],
                    "available": st.chips or st.options,
                }
            )
            return 1
        plan.append(q.popleft())

    tapped: list[dict] = []
    for item in plan:
        x, y = item["center"]
        # force: package already gated by require_duolingo; skip per-chip dumpsys
        tap_xy(x, y, delay=CHIP_TAP, force=True)
        if CHIP_GAP:
            time.sleep(CHIP_GAP)
        tapped.append({"word": item["word"], "bounds": item["bounds"], "center": [x, y]})

    time.sleep(AFTER_CHIPS)
    if is_story or is_gap:
        # Stories: no 检查. Only advance when 继续 is green.
        # Partial multi-blank (continue still gray) → return without long wait / blind tap.
        advance: dict | list | None = None
        advanced = False
        st_mid = get_state() if not QUIET else None
        for _ in range(3):
            st_now = st_mid if st_mid is not None else get_state()
            cont_on = getattr(st_now, "continue_enabled", None)
            if cont_on is True or (st_now.feedback or {}).get("is_feedback"):
                advance = _tap_story_continue(st_now)
                time.sleep(AFTER_CONTINUE)
                advanced = True
                if not QUIET:
                    st2 = get_state()
                    if (st2.feedback or {}).get("is_feedback") or (
                        "你太棒了" in " ".join(st2.raw_texts)
                    ):
                        advance = {
                            "fill_continue": advance,
                            "praise_continue": _tap_story_continue(st2),
                        }
                        time.sleep(AFTER_CONTINUE * 0.5)
                break
            # still gray — if more bank chips remain, treat as partial fill
            if cont_on is False and (st_now.chips or st_now.options):
                time.sleep(0.25)
                st_mid = get_state()
                cont_on2 = getattr(st_mid, "continue_enabled", None)
                if cont_on2 is True:
                    continue
                break
            time.sleep(0.25)
            st_mid = get_state()
        st_final = get_state() if not QUIET else st_mid
        emit(
            {
                "tapped": tapped,
                "tray_ok": None,
                "checked": False,
                "advanced": advanced,
                "mode": "story_gap_fill_chips" if advanced else "story_gap_fill_partial",
                "cta": advance,
                "words": words,
                "state": st_final.to_public_dict()
                if st_final is not None
                else {"note": "quiet skip full dump"},
            }
        )
        return 0

    # 检查 → 继续：固定底栏，0 次 dump（坐标来自本题已读到的 submitButton）
    advance = submit_and_advance(check_bounds=_submit_bounds_from_state(st))
    st_final = get_state() if not QUIET else None
    emit(
        {
            "tapped": tapped,
            "tray_ok": None,
            "checked": True,
            "advanced": True,
            "mode": "batch+fixed_cta_fast",
            "cta": advance,
            "state": st_final.to_public_dict()
            if st_final is not None
            else {"note": "quiet skip full dump"},
        }
    )
    return 0


def _tap_story_continue(st: UiState | None = None) -> dict:
    """Stories bottom green 继续 (same slot as lesson CTA)."""
    if st is not None:
        for n in st._all:
            if n.short_id in {
                "storiesLessonGreenContinueButton",
                "storiesLessonContinueButton",
            } and n.bounds:
                tap_bounds(n.bounds, delay=DEFAULT_TAP)
                return {"mode": "stories_continue", "bounds": n.bounds}
    t = tap_bottom_cta()
    return {"mode": "fixed_bottom_story", **t}


def cmd_choice(args: argparse.Namespace) -> int:
    """Tap a text option or image card (imageText caption / option1..4)."""
    try:
        require_duolingo()
    except RuntimeError as e:
        emit({"error": str(e), "package": current_package()})
        return 3
    label = args.label
    st = get_state()
    is_story = getattr(st, "mode", None) == "story" or _is_stories_ui(st._all, st.activity)

    def _finish(tapped: str) -> int:
        time.sleep(0.08)
        if is_story:
            # Stories: select answer → (often praise) → 继续; no 检查
            # gap-fill multi-blank: continue stays gray until all blanks filled —
            # do NOT force continue so the loop can apply the next choice/chips.
            time.sleep(0.35)
            st_mid = get_state() if not QUIET else st
            cont_on = getattr(st_mid, "continue_enabled", None) if st_mid else None
            still_gap = (
                getattr(st_mid, "challenge", None) == "gap_fill"
                if st_mid is not None
                else getattr(st, "challenge", None) == "gap_fill"
            )
            if cont_on is False and still_gap:
                emit(
                    {
                        "tapped": tapped,
                        "checked": False,
                        "advanced": False,
                        "mode": "story_gap_fill_partial",
                        "continue_enabled": cont_on,
                        "state": None if QUIET or st_mid is None else st_mid.to_public_dict(),
                    }
                )
                return 0
            advance = _tap_story_continue(st_mid if st_mid is not None else st)
            time.sleep(AFTER_CONTINUE)
            # praise page may need a second 继续
            if not QUIET:
                st2 = get_state()
                if (st2.feedback or {}).get("is_feedback") or (
                    "你太棒了" in " ".join(st2.raw_texts)
                ):
                    advance2 = _tap_story_continue(st2)
                    time.sleep(AFTER_CONTINUE * 0.6)
                    advance = {"select_continue": advance, "praise_continue": advance2}
            else:
                # Quiet: one more blind continue covers praise banner
                time.sleep(0.25)
                advance2 = tap_bottom_cta()
                time.sleep(AFTER_CONTINUE * 0.5)
                advance = {"select_continue": advance, "praise_continue": advance2}
            st_final = get_state() if not QUIET else None
            emit(
                {
                    "tapped": tapped,
                    "checked": False,
                    "advanced": True,
                    "cta": advance,
                    "mode": "story_choice",
                    "state": None if st_final is None else st_final.to_public_dict(),
                }
            )
            return 0
        advance = submit_and_advance(check_bounds=_submit_bounds_from_state(st))
        st2 = get_state() if not QUIET else None
        emit(
            {
                "tapped": tapped,
                "checked": True,
                "advanced": True,
                "cta": advance,
                "mode": "choice+fixed_cta_fast",
                "state": None if st2 is None else st2.to_public_dict(),
            }
        )
        return 0

    # 1) Image cards: optionN + imageText
    for img in getattr(st, "image_options", None) or []:
        if img.get("text") == label and img.get("bounds"):
            tap_bounds(img["bounds"], delay=DEFAULT_TAP)
            return _finish(label)

    # 2) Story phrase segments / option nodes (pre-resolved bounds)
    for n in st._option_nodes:
        if n.label == label or n.text == label or n.desc == label:
            if n.bounds:
                tap_bounds(n.bounds, delay=DEFAULT_TAP)
                return _finish(label)

    # 3) optionText / generic labels
    candidates = st._option_nodes + st._all
    for n in candidates:
        if n.label == label or n.text == label or n.desc == label:
            if n.bounds:
                # prefer clickable parent card
                tb = parse_bounds(n.bounds)
                tapped_bounds = n.bounds
                if tb:
                    for p in st._all:
                        if not p.clickable or not p.bounds:
                            continue
                        pb = parse_bounds(p.bounds)
                        if not pb:
                            continue
                        cx, cy = (tb[0] + tb[2]) // 2, (tb[1] + tb[3]) // 2
                        if pb[0] <= cx <= pb[2] and pb[1] <= cy <= pb[3]:
                            area = (pb[2] - pb[0]) * (pb[3] - pb[1])
                            if 3000 < area < 1080 * 1000:
                                tapped_bounds = p.bounds
                                break
                tap_bounds(tapped_bounds, delay=DEFAULT_TAP)
                return _finish(label)

    # 4) contains
    for n in candidates:
        if label in (n.label or "") or label in (n.text or ""):
            if n.bounds:
                tap_bounds(n.bounds, delay=DEFAULT_TAP)
                return _finish(n.label or n.text)

    emit(
        {
            "error": "choice not found",
            "label": label,
            "options": st.options,
            "image_options": getattr(st, "image_options", None) or [],
            "raw_texts": st.raw_texts,
        }
    )
    return 1


def tap_by_text_or_id(st: UiState, *, text: str | None = None, rid: str | None = None) -> bool:
    for n in st._all:
        if rid and n.short_id == rid and n.bounds:
            return tap_bounds(n.bounds, delay=0.7)
        if text and (n.text == text or n.desc == text) and n.bounds:
            return tap_bounds(n.bounds, delay=0.7)
    return False


def cmd_check(_: argparse.Namespace) -> int:
    """Tap bottom CTA once (= 检查). Prefer fixed position."""
    t = tap_bottom_cta()
    time.sleep(AFTER_CHECK * 0.5)
    print(json.dumps({"checked": True, "cta": t, "mode": "fixed_bottom"}, ensure_ascii=False, indent=2))
    return 0


def cmd_continue(_: argparse.Namespace) -> int:
    """Tap bottom CTA once (= 继续 / 知道了 / 领取… / stories continue)."""
    # Prefer stories green button without full re-classify cost when dump available
    try:
        st = get_state()
    except Exception:
        st = None
    if st is not None and _is_stories_ui(st._all, st.activity):
        t = _tap_story_continue(st)
        time.sleep(AFTER_CONTINUE)
        print(json.dumps({"continued": True, "cta": t, "mode": t.get("mode")}, ensure_ascii=False, indent=2))
        return 0
    t = tap_bottom_cta_smart(st, multi_y_fallback=True)
    time.sleep(AFTER_CONTINUE)
    print(json.dumps({"continued": True, "cta": t, "mode": t.get("mode")}, ensure_ascii=False, indent=2))
    return 0


def cmd_handle_feedback(_: argparse.Namespace) -> int:
    """
    Result / reward / unit-complete sheet: tap 继续 or 知道了.
    Prefer real button bounds from dump (fixed Y 0.932 misses some higher CTAs).
    Second tap covers 知道了 → 继续 chain.
    """
    try:
        st = get_state()
    except Exception:
        st = None
    # First tap must hit real CTA (unit-complete sheet is higher than lesson CTA).
    t1 = tap_bottom_cta_smart(st, multi_y_fallback=True)
    time.sleep(AFTER_CONTINUE)
    # Second tap covers 知道了→继续; stay on classic slot only (multi-Y can mis-tap next page).
    t2 = tap_bottom_cta()
    time.sleep(AFTER_CONTINUE * 0.6)
    emit(
        {
            "handled": True,
            "action": "bottom_cta",
            "taps": [t1, t2],
            "mode": "feedback_smart_double",
        }
    )
    return 0


def cmd_skip(_: argparse.Namespace) -> int:
    st = get_state()
    ok = tap_by_text_or_id(st, text="跳过") or tap_by_text_or_id(st, text="Skip")
    time.sleep(0.5)
    print(json.dumps({"skipped": ok, "state": get_state().to_public_dict()}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def cmd_back(_: argparse.Namespace) -> int:
    adb("shell", "input", "keyevent", "4")
    time.sleep(0.5)
    print(json.dumps({"back": True, "state": get_state().to_public_dict()}, ensure_ascii=False, indent=2))
    return 0


def cmd_tap(args: argparse.Namespace) -> int:
    tap_xy(args.x, args.y, delay=args.delay)
    payload: dict = {"tapped": [args.x, args.y]}
    st = maybe_state()
    if st is not None:
        payload["state"] = st
    emit(payload)
    return 0


def _option_centers_from_nodes(ns: list[Node]) -> dict[str, list[tuple[int, int]]]:
    """label -> list of tap centers (clickable card center preferred)."""
    from collections import defaultdict

    centers: dict[str, list[tuple[int, int]]] = defaultdict(list)
    texts: list[Node] = []
    for n in ns:
        if n.short_id == "optionText" and n.label:
            texts.append(n)
        elif n.text and n.cls == "TextView" and n.bounds:
            # fallback texts on match board
            b = parse_bounds(n.bounds)
            if b and 400 < b[1] < 2100 and n.text not in {"检查", "继续", "选择配对"}:
                texts.append(n)

    clickables = [n for n in ns if n.clickable and n.bounds]
    for tnode in texts:
        lab = tnode.label or tnode.text
        if not lab:
            continue
        tb = parse_bounds(tnode.bounds)
        if not tb:
            continue
        tcx, tcy = (tb[0] + tb[2]) // 2, (tb[1] + tb[3]) // 2
        best = (tcx, tcy)
        best_area = 10**18
        for n in clickables:
            b = parse_bounds(n.bounds)
            if not b:
                continue
            if not (b[0] <= tcx <= b[2] and b[1] <= tcy <= b[3]):
                continue
            area = (b[2] - b[0]) * (b[3] - b[1])
            if 2000 < area < 1080 * 900 and area < best_area:
                best_area = area
                best = ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)
        # de-dupe near-identical centers for same label
        if not any(abs(best[0] - x) < 12 and abs(best[1] - y) < 12 for x, y in centers[lab]):
            centers[lab].append(best)
    return centers


def _tap_option_label(label: str) -> bool:
    """Single-label tap (one dump). Prefer cmd_match batch path."""
    root = dump_root()
    ns = iter_nodes(root)
    centers = _option_centers_from_nodes(ns)
    pts = centers.get(label) or []
    if not pts:
        return False
    x, y = pts[0]
    tap_xy(x, y, delay=CHIP_TAP)
    return True


def _story_sort_items(st: UiState | None = None) -> list[dict]:
    """Current top→bottom sort cards: {label, center, bounds}."""
    if st is None:
        st = get_state()
    items: list[dict] = []
    for n in st._option_nodes or []:
        lab = (n.desc or n.text or n.label or "").strip()
        c = center_of(n.bounds) if n.bounds else None
        if not lab or not c:
            continue
        items.append({"label": lab, "center": c, "bounds": n.bounds})
    if items:
        items.sort(key=lambda it: (parse_bounds(it["bounds"]) or (0, 0, 0, 0))[1])
        return items
    # fallback scan
    for n in st._all:
        lab = (n.desc or "").strip()
        if not lab or len(lab) < 6 or n.cls != "TextView":
            continue
        b = parse_bounds(n.bounds)
        if not b or b[1] < 720 or b[3] > 2150 or (b[2] - b[0]) < 200:
            continue
        c = center_of(n.bounds)
        if not c:
            continue
        items.append({"label": lab, "center": c, "bounds": n.bounds})
    items.sort(key=lambda it: (parse_bounds(it["bounds"]) or (0, 0, 0, 0))[1])
    # dedupe
    seen: set[str] = set()
    out: list[dict] = []
    for it in items:
        if it["label"] in seen:
            continue
        seen.add(it["label"])
        out.append(it)
    return out


def _reorder_story_sort(target: list[str]) -> dict:
    """
    Drag cards so top→bottom matches target labels.
    Re-dump after each drag (positions shift).
    """
    moves: list[dict] = []
    for i, want in enumerate(target):
        st = get_state()
        cur = _story_sort_items(st)
        # fuzzy match label
        def find_idx(label: str) -> int:
            for j, it in enumerate(cur):
                if it["label"] == label:
                    return j
            for j, it in enumerate(cur):
                if it["label"].replace(" ", "") == label.replace(" ", ""):
                    return j
            for j, it in enumerate(cur):
                if label in it["label"] or it["label"] in label:
                    return j
            return -1

        j = find_idx(want)
        if j < 0:
            return {
                "ok": False,
                "error": "label not on board",
                "missing": want,
                "current": [x["label"] for x in cur],
                "moves": moves,
            }
        if j == i:
            continue
        if i >= len(cur):
            break
        x1, y1 = cur[j]["center"]
        x2, y2 = cur[i]["center"]
        # slightly longer drag is more reliable for Compose reorder
        swipe_xy(x1, y1, x2, y2, duration_ms=550, force=True)
        time.sleep(0.55)
        moves.append(
            {
                "word": want,
                "from_index": j,
                "to_index": i,
                "from": [x1, y1],
                "to": [x2, y2],
            }
        )
    st_final = get_state()
    final = [x["label"] for x in _story_sort_items(st_final)]
    return {
        "ok": final == target or set(final) == set(target),
        "moves": moves,
        "final_order": final,
        "target": target,
    }


def _tap_story_check(st: UiState | None = None) -> dict:
    if st is None:
        st = get_state()
    for n in st._all:
        if n.short_id == "storiesLessonCheckButton" and n.bounds:
            if not n.enabled:
                # still try — sometimes attribute lags
                pass
            tap_bounds(n.bounds, delay=DEFAULT_TAP)
            return {"mode": "stories_check", "bounds": n.bounds, "enabled": n.enabled}
        if n.text == "检查" and n.bounds:
            b = parse_bounds(n.bounds)
            if b and (b[2] - b[0]) > 400:
                tap_bounds(n.bounds, delay=DEFAULT_TAP)
                return {"mode": "text_检查", "bounds": n.bounds}
    t = tap_bottom_cta()
    return {"mode": "fixed_bottom_check", **t}


def cmd_order(args: argparse.Namespace) -> int:
    """
    Story chronological order: drag options top→bottom into labels order, then 检查.
    """
    try:
        require_duolingo()
    except RuntimeError as e:
        emit({"error": str(e), "package": current_package()})
        return 3
    labels: list[str] = list(args.labels)
    if not labels:
        emit({"error": "order needs labels", "labels": labels})
        return 1

    st0 = get_state()
    available = [x["label"] for x in _story_sort_items(st0)]
    # validate membership (allow reorder of same set)
    if available and set(labels) != set(available):
        # still try if all labels present
        missing = [w for w in labels if w not in available]
        if missing:
            emit(
                {
                    "error": "order labels not on board",
                    "missing": missing,
                    "available": available,
                    "labels": labels,
                }
            )
            return 1

    result = _reorder_story_sort(labels)
    time.sleep(0.25)
    # 检查 (becomes enabled after drag)
    st1 = get_state()
    check_tap = _tap_story_check(st1)
    time.sleep(AFTER_CHECK)
    # praise / 继续
    st2 = get_state()
    advance: dict
    if _is_stories_ui(st2._all, st2.activity):
        advance = _tap_story_continue(st2)
        time.sleep(AFTER_CONTINUE)
        # optional second continue after praise
        if QUIET:
            time.sleep(0.2)
            advance2 = tap_bottom_cta()
            time.sleep(AFTER_CONTINUE * 0.5)
            advance = {"after_check": advance, "extra": advance2}
        else:
            st3 = get_state()
            if (st3.feedback or {}).get("is_feedback") or "你太棒了" in " ".join(st3.raw_texts):
                advance2 = _tap_story_continue(st3)
                time.sleep(AFTER_CONTINUE * 0.5)
                advance = {"after_check": advance, "praise": advance2}
    else:
        advance = tap_bottom_cta()
        time.sleep(AFTER_CONTINUE)

    emit(
        {
            "ordered": labels,
            "reorder": result,
            "checked": True,
            "cta": {"check": check_tap, "advance": advance},
            "mode": "story_order",
            "state": None if QUIET else get_state().to_public_dict(),
        }
    )
    return 0 if result.get("ok", True) else 1


def cmd_match(args: argparse.Namespace) -> int:
    """
    Fast match: ONE dump → plan all centers → rapid taps (10 words = 1 dump).
    Cards usually keep positions when pairs clear; if a mid-label misses, one recovery dump.
    """
    try:
        require_duolingo()
    except RuntimeError as e:
        emit({"error": str(e), "package": current_package()})
        return 3
    labels: list[str] = args.labels
    root = dump_root()
    centers = _option_centers_from_nodes(iter_nodes(root))
    # Consume a queue per label so duplicates work
    from collections import defaultdict, deque

    queues: dict[str, deque] = defaultdict(deque)
    for lab, pts in centers.items():
        for p in pts:
            queues[lab].append(p)

    plan: list[tuple[str, int, int]] = []
    for lab in labels:
        if not queues.get(lab):
            emit(
                {
                    "error": "label not found in first dump",
                    "missing": lab,
                    "available": list(centers.keys()),
                    "mode": "match_once",
                }
            )
            return 1
        x, y = queues[lab].popleft()
        plan.append((lab, x, y))

    tapped: list[dict] = []
    for lab, x, y in plan:
        tap_xy(x, y, delay=CHIP_TAP, force=True)
        if CHIP_GAP:
            time.sleep(CHIP_GAP)
        tapped.append({"word": lab, "center": [x, y]})

    # 配对成功后通常直接出「继续」/「非常好」；失败则仍停在选择配对+检查
    time.sleep(0.45)
    st_after = get_state()
    dumps = 2
    blob = " ".join(st_after.raw_texts)
    has_continue = "继续" in (st_after.buttons or []) or any(
        n.text == "继续" or n.short_id in {"continueButton", "continueButtonGreenStub"}
        for n in st_after._all
    )
    praise = any(k in blob for k in ("非常好", "你太棒了", "真棒", "不错哦", "太棒了"))
    still_pairing = (
        "配对" in (st_after.instruction or "")
        and not has_continue
        and not praise
        and not (st_after.feedback or {}).get("is_feedback")
    )

    advance: dict | None = None
    if not still_pairing or has_continue or praise or (st_after.feedback or {}).get("is_feedback"):
        # 点继续（反馈页）——不要点「检查」（检查=未完成/错误残留）
        tapped_cont = False
        for n in st_after._all:
            if n.text in {"继续", "知道了"} and n.bounds:
                b = parse_bounds(n.bounds)
                if b and (b[2] - b[0]) > 300:
                    tap_bounds(n.bounds, delay=DEFAULT_TAP)
                    advance = {"mode": f"text_{n.text}", "bounds": n.bounds}
                    tapped_cont = True
                    break
        if not tapped_cont:
            t = tap_bottom_cta()
            advance = {"mode": "fixed_bottom_continue", **t}
        time.sleep(AFTER_CONTINUE)
        still_pairing = False
    emit(
        {
            "matched": [t["word"] for t in tapped],
            "tapped": tapped,
            "pair_count": len(labels) // 2,
            "mode": "match_once+continue" if advance else "match_once",
            "dumps": dumps,
            "still_pairing": still_pairing,
            "advanced": advance is not None,
            "cta": advance,
            "state": None if QUIET else st_after.to_public_dict(),
        }
    )
    return 0


def cmd_tap_labels(args: argparse.Namespace) -> int:
    """Tap any labels by text without full state between taps."""
    labels: list[str] = args.labels
    # one dump, resolve all centers, tap fast
    root = dump_root()
    ns = iter_nodes(root)
    by_text: dict[str, list[Node]] = {}
    for n in ns:
        if n.text:
            by_text.setdefault(n.text, []).append(n)
        if n.desc:
            by_text.setdefault(n.desc, []).append(n)

    tapped = []
    for lab in labels:
        nodes = by_text.get(lab) or []
        if not nodes:
            emit({"error": "not found", "missing": lab, "tapped": tapped})
            return 1
        # if optionText style, use helper which re-dumps; else first node
        if not _tap_option_label(lab):
            tap_bounds(nodes[0].bounds, delay=0.2)
        tapped.append(lab)
        time.sleep(0.1)
    payload: dict = {"tapped_labels": tapped}
    payload["state"] = get_state().to_public_dict()
    emit(payload)
    return 0


def cmd_tap_id(args: argparse.Namespace) -> int:
    st = get_state()
    ok = tap_by_text_or_id(st, rid=args.rid)
    print(json.dumps({"tapped_id": args.rid, "ok": ok, "state": get_state().to_public_dict()}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def cmd_foreground(_: argparse.Namespace) -> int:
    try:
        pkg = ensure_duolingo(bring_to_front=True)
    except RuntimeError as e:
        print(json.dumps({"error": str(e), "package": current_package()}, ensure_ascii=False, indent=2))
        return 3
    time.sleep(0.4)
    st = get_state()
    d = st.to_public_dict()
    d["ensured_package"] = pkg
    print(json.dumps(d, ensure_ascii=False, indent=2))
    return 0 if d.get("duolingo") else 3


def _tap_learn_tab(st: UiState) -> bool:
    """Tap bottom house icon (Learn tab)."""
    # resource-id first
    if tap_by_text_or_id(st, rid="tabLearn"):
        return True
    for n in st._all:
        if n.short_id == "tabLearn" and n.bounds:
            return tap_bounds(n.bounds, delay=0.6)
        if n.desc in {"Learn Tab", "学习", "学习选项卡"} and n.bounds:
            return tap_bounds(n.bounds, delay=0.6)
    # fallback: leftmost bottom tab on 1080x2400-ish screens
    # earlier dump: tabLearn ~ [41,2175][173,2307] → (107, 2241)
    tap_xy(107, 2241, delay=0.6)
    return True


def _dismiss_easy_popups(st: UiState) -> bool:
    for label in (
        "下次再说",
        "关闭",
        "不了",
        "知道了",
        "以后再说",
        "暂不",
        "跳过",
        "No thanks",
        "Not now",
        "Close",
    ):
        for n in st._all:
            if (n.text == label or n.desc == label) and n.bounds:
                # avoid full-screen false positives with empty
                b = parse_bounds(n.bounds)
                if b and (b[3] - b[1]) < 400:
                    tap_bounds(n.bounds, delay=0.5)
                    return True
                if b and b[1] > 1800:  # bottom CTA
                    tap_bounds(n.bounds, delay=0.5)
                    return True
    return False


def cmd_go_home(_: argparse.Namespace) -> int:
    """
    Navigate to learn path (house tab).
    Safe-ish: if already in a lesson session, does NOT abandon.
    """
    st = get_state()
    # Mid-lesson: never leave (instruction 可能为空，不能当条件)
    if st.screen == "session":
        emit(
            {
                "go_home": False,
                "reason": "已在做题中，拒绝回主页",
                "state": st.to_public_dict(),
            }
        )
        return 1

    # dismiss one popup layer if present
    if _dismiss_easy_popups(st):
        time.sleep(0.5)
        st = get_state()

    if st.screen == "home":
        emit({"go_home": True, "already": True, "state": st.to_public_dict()})
        return 0

    ok = _tap_learn_tab(st)
    time.sleep(1.0)
    st = get_state()

    # one more popup clear after tab switch
    if st.screen != "home" and _dismiss_easy_popups(st):
        time.sleep(0.5)
        st = get_state()

    # if still not home and not session, try tab again
    if st.screen not in {"home", "session"}:
        ok = _tap_learn_tab(st) or ok
        time.sleep(1.0)
        st = get_state()

    emit(
        {
            "go_home": st.screen == "home",
            "tapped_learn_tab": ok,
            "state": st.to_public_dict(),
        }
    )
    return 0 if st.screen == "home" else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Duolingo ADB driver (judge externally)")
    p.add_argument("-q", "--quiet", action="store_true", help="skip post-action full status dump")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="dump structured UI state").set_defaults(func=cmd_status)
    sub.add_parser(
        "path-targets",
        help="list gold vs incomplete path nodes (no taps)",
    ).set_defaults(func=cmd_path_targets)
    sub.add_parser(
        "start",
        help="start lesson: only FrameLayout incomplete nodes",
    ).set_defaults(func=cmd_start)
    sub.add_parser("check", help="tap 检查").set_defaults(func=cmd_check)
    sub.add_parser("continue", help="tap 继续 / end CTA").set_defaults(func=cmd_continue)
    sub.add_parser(
        "handle-feedback",
        help="hardcoded: 继续/知道了 on result page (no LLM)",
    ).set_defaults(func=cmd_handle_feedback)
    sub.add_parser("skip", help="tap 跳过").set_defaults(func=cmd_skip)
    sub.add_parser("back", help="Android back").set_defaults(func=cmd_back)
    sub.add_parser("go-home", help="tap bottom house / Learn tab").set_defaults(func=cmd_go_home)
    sub.add_parser("foreground", help="bring Duolingo to front").set_defaults(func=cmd_foreground)

    sp = sub.add_parser("chips", help="tap word-bank chips in order")
    sp.add_argument("words", nargs="+")
    sp.set_defaults(func=cmd_chips)

    sp = sub.add_parser("choice", help="tap a choice by label")
    sp.add_argument("label")
    sp.set_defaults(func=cmd_choice)

    sp = sub.add_parser("match", help="tap match-pair labels in order")
    sp.add_argument("labels", nargs="+")
    sp.set_defaults(func=cmd_match)

    sp = sub.add_parser(
        "order",
        help="story sort: drag labels into top→bottom order then 检查",
    )
    sp.add_argument("labels", nargs="+")
    sp.set_defaults(func=cmd_order)

    sp = sub.add_parser("tap-labels", help="tap labels by text (batch)")
    sp.add_argument("labels", nargs="+")
    sp.set_defaults(func=cmd_tap_labels)

    sp = sub.add_parser("tap", help="raw coordinate tap")
    sp.add_argument("x", type=int)
    sp.add_argument("y", type=int)
    sp.add_argument("--delay", type=float, default=0.2)
    sp.set_defaults(func=cmd_tap)

    sp = sub.add_parser("tap-id", help="tap resource-id short name")
    sp.add_argument("rid")
    sp.set_defaults(func=cmd_tap_id)

    sp = sub.add_parser("screenshot")
    sp.add_argument("path", nargs="?", default=None)
    sp.set_defaults(func=cmd_screenshot)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    global QUIET
    QUIET = bool(getattr(args, "quiet", False))
    try:
        return args.func(args)
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    sys.exit(main())

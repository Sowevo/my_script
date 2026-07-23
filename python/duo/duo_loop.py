#!/usr/bin/env python3
"""
多邻国 ADB 编排：driver 负责读屏/点击，judge 负责答题（DeepSeek 等）。

  python3 duo_loop.py --judge openai --lessons 1
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from duo_judge import get_judge

WORKDIR = Path(__file__).resolve().parent
DRIVER = [sys.executable, str(WORKDIR / "duo_driver.py")]
LOG_DIR = WORKDIR / "logs"
LOG_PATH: Path | None = None

# 控制台是否刷 driver 原始 JSON（文件日志默认只写中文摘要）
VERBOSE_DRIVER = False


def _is_adb_lost_text(msg: str) -> bool:
    m = (msg or "").lower()
    return "no devices/emulators found" in m or "device offline" in m


def adb_has_device() -> bool:
    """True 当 adb devices 里至少有一个 device。"""
    try:
        r = subprocess.run(
            ["adb", "devices"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return False
    for line in (r.stdout or "").splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[1] == "device":
            return True
    return False

_SCREEN_CN = {
    "home": "主页/路径",
    "session": "做题中",
    "end": "结算页",
    "other": "其它页面",
    "unknown": "未知",
}

_OP_CN = {
    "chips": "组词点击",
    "choice": "点选项",
    "match": "配对点击",
    "order": "排序拖动",
    "check": "点检查",
    "continue": "点继续/底部按钮",
    "start": "选课并开课",
    "skip": "点跳过",
    "go-home": "回学习页房子",
    "back": "系统返回",
    "wait": "等待",
    "done": "结束",
    "handle-feedback": "处理答对/答错反馈",
    "foreground": "拉起多邻国",
    "status": "读取屏幕",
    "tap-labels": "按文字点击",
}


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def setup_log(path: Path | None = None) -> Path:
    global LOG_PATH
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_PATH = path or (LOG_DIR / f"duo_loop_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(f"\n===== 会话开始 {_ts()} =====\n")
    print(f"[{_ts()}] 【日志】写入 {LOG_PATH}", flush=True)
    return LOG_PATH


def log(msg: str, *, also_print: bool = True, data: dict | None = None) -> None:
    # 控制台与文件统一：前面带时间
    line = f"[{_ts()}] {msg}"
    if data is not None:
        line += " " + json.dumps(data, ensure_ascii=False)
    if also_print:
        print(line, flush=True)
    if LOG_PATH is not None:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def _screen_cn(screen: str | None) -> str:
    return _SCREEN_CN.get(screen or "", screen or "?")


def _op_cn(op: str) -> str:
    return _OP_CN.get(op, op)


def _summarize_status(st: dict) -> str:
    parts = [
        f"界面={_screen_cn(st.get('screen'))}",
        f"包名={st.get('package') or '?'}",
    ]
    if st.get("mode") and st.get("mode") != "lesson":
        parts.append(f"模式={st.get('mode')}")
    if st.get("mode") == "story" and st.get("continue_enabled") is not None:
        parts.append("继续=可点" if st.get("continue_enabled") else "继续=灰色")
    if st.get("instruction"):
        parts.append(f"题型={st.get('instruction')}")
    if st.get("prompt"):
        p = str(st.get("prompt"))
        if len(p) > 40:
            p = p[:40] + "…"
        parts.append(f"题干={p}")
    chips = st.get("chips") or []
    opts = st.get("options") or []
    if chips:
        parts.append(f"词块{len(chips)}个")
    if opts:
        parts.append(f"选项{len(opts)}个")
    ml, mr = st.get("match_left") or [], st.get("match_right") or []
    if ml and mr:
        parts.append(f"配对左{len(ml)}/右{len(mr)}")
    btns = st.get("buttons") or []
    if btns:
        parts.append(f"按钮={btns}")
    fb = st.get("feedback") or {}
    if fb.get("is_feedback"):
        parts.append(f"反馈页→{fb.get('action')}")
    return " | ".join(parts)


def _summarize_action(act: dict) -> str:
    op = act.get("op", "")
    cn = _op_cn(op)
    if op == "chips":
        w = act.get("words") or []
        return f"{cn}：{' '.join(w)}"
    if op == "choice":
        return f"{cn}：{act.get('label')}"
    if op == "match":
        labs = act.get("labels") or []
        return f"{cn}：{' → '.join(labs)}（共{len(labs)}词/{len(labs)//2}对）"
    if op == "order":
        labs = act.get("labels") or []
        short = [((x[:12] + "…") if len(x) > 12 else x) for x in labs]
        return f"{cn}：{' → '.join(short)}（{len(labs)}条）"
    if op == "start":
        return f"{cn}"
    return cn


def _summarize_driver_result(op: str, result: dict) -> str:
    if not result:
        return "无返回"
    if result.get("error"):
        return f"失败：{result.get('error')}"
    bits = []
    if op == "start":
        bits.append("已开课" if result.get("started") else "未开课")
        if result.get("cta"):
            bits.append(f"按钮={result.get('cta')}")
        if result.get("picked"):
            bits.append(f"节点={result.get('picked')}")
    elif op == "chips":
        bits.append(f"模式={result.get('mode') or '组词'}")
        if result.get("checked"):
            bits.append("已点检查/继续")
        n = len(result.get("tapped") or result.get("matched") or [])
        if n:
            bits.append(f"点了{n}下")
    elif op == "match":
        bits.append(f"模式={result.get('mode') or '配对'}")
        bits.append(f"dump次数={result.get('dumps', '?')}")
        if result.get("still_pairing"):
            bits.append("仍停在配对页(未点继续)")
        elif result.get("advanced"):
            bits.append("已点继续")
        else:
            bits.append("配完(状态未知)")
        if result.get("cta"):
            bits.append(f"cta={result.get('cta')}")
    elif op == "choice":
        bits.append(f"点了={result.get('tapped')}")
        if result.get("checked"):
            bits.append("已点检查/继续")
        elif result.get("advanced") is False:
            bits.append("页面未推进")
    elif op in {"check", "continue", "handle-feedback"}:
        bits.append(str(result.get("mode") or result.get("action") or "完成"))
        if result.get("cta"):
            bits.append(f"坐标={result.get('cta')}")
    if result.get("ok") is False and not result.get("error"):
        bits.append("ok=false")
    return "；".join(bits) if bits else "完成"


_QUIET_OPS = {
    "chips",
    "check",
    "continue",
    "choice",
    "match",
    "order",
    "handle-feedback",
    "tap",
    "tap-id",
    "tap-labels",
    "skip",
    "back",
    "start",
    "go-home",
    "foreground",
}


def run_driver(*args: str, quiet: bool | None = None, phase: str = "") -> dict:
    """
    调用 duo_driver。日志写中文阶段说明，默认不刷整段 JSON。
    phase: 读屏 / 点击 / 拉起应用 等
    ADB 掉线 → 抛 AdbLostError，调用方必须立刻停。
    """
    if quiet is None:
        quiet = bool(args and args[0] in _QUIET_OPS)
    op = args[0] if args else ""
    phase = phase or ("读屏" if op == "status" else "点击")
    short_args = " ".join(args[1:8])
    if len(args) > 8:
        short_args += " …"
    log(f"【{phase}】开始 {_op_cn(op)}" + (f" ← {short_args}" if short_args else ""))

    cmd = DRIVER + (["-q"] if quiet else []) + list(args)
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.time() - t0
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()

    data: dict
    if not out:
        data = {"ok": r.returncode == 0, "rc": r.returncode}
        if r.returncode != 0:
            data["error"] = err or f"driver 失败: {args}"
            log(f"【{phase}】失败 {_op_cn(op)}（{elapsed:.1f}s）{data.get('error')}")
            if r.returncode != 0 and not out:
                raise RuntimeError(data["error"])
        else:
            log(f"【{phase}】完成 {_op_cn(op)}（{elapsed:.1f}s）")
        return data

    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        chunks = []
        buf = []
        depth = 0
        for line in out.splitlines():
            buf.append(line)
            depth += line.count("{") - line.count("}")
            if depth == 0 and buf:
                try:
                    chunks.append(json.loads("\n".join(buf)))
                except json.JSONDecodeError:
                    pass
                buf = []
        if chunks:
            data = chunks[-1]
        else:
            log(f"【{phase}】解析失败 {_op_cn(op)}：{out[:200]}")
            raise RuntimeError(f"driver 输出不是 JSON:\n{out}\n{err}")

    if isinstance(data, dict):
        data.setdefault("rc", r.returncode)
        data.setdefault("ok", r.returncode == 0)
    else:
        data = {"ok": r.returncode == 0, "rc": r.returncode, "raw": data}

    summary = _summarize_driver_result(op, data if isinstance(data, dict) else {})
    log(f"【{phase}】完成 {_op_cn(op)}（{elapsed:.1f}s）→ {summary}")

    if VERBOSE_DRIVER and LOG_PATH is not None:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"[{_ts()}] [原始] {' '.join(cmd)} rc={r.returncode}\n")
            f.write(out[:4000] + ("\n…\n" if len(out) > 4000 else "\n"))

    if r.returncode != 0 and isinstance(data, dict) and data.get("error"):
        # start 等命令可能 rc!=0 但仍有有用信息
        pass
    return data


def status() -> dict:
    st = run_driver("status", quiet=False, phase="读屏")
    if "state" in st and "screen" not in st:
        return st["state"]
    return st


def exec_action(action: dict) -> dict:
    op = action.get("op", "")
    if op == "chips":
        words = action.get("words") or []
        return run_driver("chips", *words, phase="点击")
    if op == "choice":
        return run_driver("choice", action.get("label") or "", phase="点击")
    if op == "match":
        labels = action.get("labels") or []
        return run_driver("match", *labels, phase="点击")
    if op == "order":
        labels = action.get("labels") or []
        return run_driver("order", *labels, phase="点击")
    if op == "check":
        return run_driver("check", phase="点击")
    if op == "continue":
        return run_driver("continue", phase="点击")
    if op == "skip":
        return run_driver("skip", phase="点击")
    if op == "start":
        return run_driver("start", phase="开课")
    if op in {"go-home", "gohome", "home"}:
        return run_driver("go-home", phase="点击")
    if op == "back":
        return run_driver("back", phase="点击")
    if op == "wait":
        sec = float(action.get("sec", 0.5))
        log(f"【等待】{sec}s")
        time.sleep(sec)
        return {"waited": sec}
    if op == "done":
        return {"done": True}
    raise RuntimeError(f"未知操作: {op}")


def unwrap_state(result: dict) -> dict:
    if not result:
        return status()
    if "state" in result and isinstance(result["state"], dict):
        return result["state"]
    if "screen" in result:
        return result
    return status()


def ensure_learn_home() -> dict:
    log("【准备】确认前台是多邻国…")
    result = run_driver("foreground", phase="拉起应用")
    if result.get("package") and result.get("package") != "com.duolingo":
        log(f"【致命】拉起后不是多邻国：{result.get('package')}")
        raise RuntimeError(f"wrong app: {result.get('package')}")
    if result.get("duolingo") is False:
        log("【致命】duolingo=false")
        raise RuntimeError("Duolingo not in foreground")
    time.sleep(0.4)
    st = status()
    log(f"【准备】{_summarize_status(st)}")
    if st.get("package") and st.get("package") != "com.duolingo":
        raise RuntimeError(f"wrong app before start: {st.get('package')}")
    # 已在做题：绝不能点房子（instruction 有时为空，不能当判断条件）
    if st.get("screen") == "session":
        log("【准备】已在做题中，继续当前课（不回主页）")
        return st
    if st.get("screen") == "home" and st.get("learn_path") is True:
        log("【准备】已在学习路径主页")
        return st
    log("【准备】点房子回学习页…")
    result = run_driver("go-home", phase="点击")
    st = unwrap_state(result)
    if st.get("package") and st.get("package") != "com.duolingo":
        raise RuntimeError(f"left Duolingo during go-home: {st.get('package')}")
    if st.get("screen") == "session":
        log("【准备】回房子后仍在做题页，继续当前课")
        return st
    if st.get("screen") not in {"home", "session"}:
        log("【准备】再点一次房子…")
        result = run_driver("go-home", phase="点击")
        st = unwrap_state(result)
    log(f"【准备】就绪 → {_summarize_status(st)}")
    return st


def play(lessons: int, judge_name: str, max_steps: int) -> None:
    log(f"【启动】答题引擎={judge_name}，目标完成 {lessons} 课，最多 {max_steps} 步")
    judge = get_judge(judge_name)
    # 开局读屏一次，第一步直接复用，避免再 dump ~3s
    cached_st = ensure_learn_home()

    finished = 0
    step = 0
    idle = 0
    saw_session = False
    start_fails = 0
    story_history: list[str] = []
    story_choice_key: tuple[str, str, tuple[str, ...]] | None = None
    story_rejected: set[str] = set()

    while finished < lessons and step < max_steps:
        step += 1
        log(f"\n======== 第 {step} 步 | 已完成课数 {finished}/{lessons} ========")
        # 只在这里查一次 ADB；掉了就停，别处不再重复查
        if not adb_has_device():
            log("【致命】ADB 无设备，停止")
            break
        if cached_st is not None:
            st = cached_st
            cached_st = None
            log(f"【读屏】复用准备阶段读屏（省一次 dump）")
        else:
            st = status()
        pkg = st.get("package") or ""
        if pkg and pkg != "com.duolingo":
            log(f"【致命】前台是 {pkg!r}，不是多邻国 — 尝试拉回一次")
            try:
                run_driver("foreground", phase="拉起应用")
                st = status()
                pkg = st.get("package") or ""
            except Exception as e:
                log(f"【致命】拉回失败：{e}")
                break
            if pkg != "com.duolingo":
                log("【致命】仍不是多邻国，停止全部点击")
                break

        screen = st.get("screen")
        if st.get("mode") == "story" and screen == "session":
            for part in str(st.get("prompt") or "").split(" | "):
                part = part.strip()
                if part and part not in story_history:
                    story_history.append(part)
            # Runtime-only context for questions about earlier story events.
            st["story_history"] = story_history[-80:]
            choice_key = (
                str(st.get("instruction") or ""),
                str(st.get("prompt") or ""),
                tuple(st.get("options") or []),
            )
            if choice_key != story_choice_key:
                story_choice_key = choice_key
                story_rejected.clear()
            if story_rejected:
                st["rejected_options"] = sorted(story_rejected)
        elif screen in {"home", "end"}:
            story_history.clear()
            story_choice_key = None
            story_rejected.clear()
        log(f"【读屏摘要】{_summarize_status(st)}")
        # 词库收起：「轻点此处查看词库」→ 硬编码点开再读一次
        raw_pre = " ".join(st.get("raw_texts") or [])
        chips_n = len(st.get("chips") or [])
        if (
            st.get("screen") == "session"
            and ("查看词库" in raw_pre or "轻点此处查看词库" in raw_pre)
            and chips_n < 2
        ):
            log("【硬编码】词库收起 → 点「轻点此处查看词库」展开")
            try:
                from duo_driver import expand_word_bank_if_needed, get_state as _gs

                # expand uses live dump; refresh st for judge
                st2 = expand_word_bank_if_needed()
                # convert UiState to public dict if needed
                if hasattr(st2, "to_public_dict"):
                    st = st2.to_public_dict()
                else:
                    st = status()
                log(f"【读屏】展开词库后：词块{len(st.get('chips') or [])}个 {st.get('chips')}")
            except Exception as e:
                log(f"【硬编码】展开词库失败：{e}")
                st = status()

        # 详细题面（中文标签）
        detail = {
            "题型": st.get("instruction") or "",
            "题干": st.get("prompt") or "",
            "词块": st.get("chips") or [],
            "选项": st.get("options") or [],
            "按钮": st.get("buttons") or [],
        }
        log("【读屏详情】", data=detail)

        if screen == "session":
            saw_session = True
            start_fails = 0
        if screen == "home" and saw_session:
            finished += 1
            saw_session = False
            start_fails = 0
            log(f"【进度】一课结束，回到主页 → 已完成 {finished}/{lessons}")
            if finished >= lessons:
                break
            idle = 0

        if screen == "other" and not saw_session:
            raw_o = " ".join(st.get("raw_texts") or [])
            if "下次再说" in raw_o:
                log("【硬编码】关闭跳级弹窗（下次再说）")
                try:
                    run_driver("tap-labels", "下次再说", phase="点击")
                except Exception:
                    exec_action({"op": "continue"})
                time.sleep(0.35)
                continue
            if "准备开始" in raw_o and "跳级" not in raw_o:
                log("【硬编码】点准备开始")
                try:
                    run_driver("tap-labels", "准备开始", phase="点击")
                except Exception as e:
                    log(f"【硬编码】准备开始失败：{e}")
                time.sleep(0.5)
                continue
            log("【硬编码】其它页 → 回学习房子")
            if st.get("package") != "com.duolingo":
                log("【致命】回房子前包名不对，停止")
                break
            exec_action({"op": "go-home"})
            time.sleep(0.35)
            continue

        if screen == "end":
            log("【硬编码】结算页 → 点底部继续")
            exec_action({"op": "continue"})
            time.sleep(0.35)
            continue

        raw_join = " ".join(st.get("raw_texts") or [])
        if "领取经验" in raw_join or "领取奖励" in raw_join:
            log("【硬编码】领取经验/奖励 → 点底部按钮")
            exec_action({"op": "continue"})
            time.sleep(0.4)
            exec_action({"op": "continue"})
            time.sleep(0.35)
            continue

        if (
            screen == "session"
            and not st.get("instruction")
            and not st.get("prompt")
            and not (st.get("chips") or [])
            and not (st.get("options") or [])
            and not (st.get("buttons") or [])
            and not (st.get("raw_texts") or [])
        ):
            log("【硬编码】做题页瞬时空白 → 等待下一帧（不调 API）")
            time.sleep(0.5)
            continue

        fb = st.get("feedback") or {}
        mode = st.get("mode") or "lesson"
        # 普通课：继续且无检查 = 反馈页。小故事页本身只有「继续」，不能套这条。
        if fb.get("is_feedback") or (
            mode != "story"
            and "继续" in (st.get("buttons") or [])
            and "检查" not in (st.get("buttons") or [])
        ):
            log("【硬编码】答对/答错反馈页 → 点继续（不调 API）", data=fb)
            run_driver("handle-feedback", phase="点击")
            time.sleep(0.35)
            idle = 0
            continue

        # 小故事判定（关键：看「有没有题」，不要只看继续灰/绿）
        #   · 有 options / 排序卡 / 检查题 → 答题（调 API）
        #   · 无 options，继续绿 → 点继续
        #   · 无 options，继续灰 → 多半在播语音/动画，等它变绿再点；绝不能 skip/调 API
        if mode == "story" and screen == "session" and not fb.get("is_feedback"):
            cont_on = st.get("continue_enabled")
            opts = st.get("options") or []
            ch = st.get("challenge")
            instr = st.get("instruction") or ""
            is_sort = ch == "sort" or ("順番" in instr or "並べ" in instr or "顺序" in instr)
            needs_answer = bool(opts) or is_sort or (
                st.get("check_enabled") is False and "检查" in (st.get("buttons") or [])
            )

            if needs_answer:
                log(
                    f"【小故事】需答题 challenge={ch} options={len(opts)} "
                    f"continue={cont_on} check={st.get('check_enabled')}"
                )
                # 多空填空：句中 ∩ 词库已能推断全部空 → 硬编码一次点齐，不调 API
                if ch in {"gap_fill", "tap_sequence"} or "文章を完成" in instr or "完成文章" in instr:
                    gap_words = list(st.get("gap_words") or [])
                    if not gap_words:
                        try:
                            from duo_driver import extract_gap_sentence, infer_gap_fill_words

                            sent = st.get("gap_sentence") or extract_gap_sentence(
                                st.get("prompt") or "", st.get("raw_texts") or []
                            )
                            gap_words = infer_gap_fill_words(
                                sent, list(st.get("options") or st.get("chips") or [])
                            )
                        except Exception as e:
                            log(f"【小故事】gap 推断失败：{e}")
                            gap_words = []
                    if len(gap_words) >= 1:
                        log(
                            f"【硬编码】小故事多空填空 → 一次点 {len(gap_words)} 词：{' '.join(gap_words)}"
                        )
                        run_driver("chips", *gap_words, phase="点击")
                        time.sleep(0.35)
                        idle = 0
                        continue
                # fall through to API
            elif cont_on is True:
                log("【硬编码】小故事「继续」可点 → 点继续")
                run_driver("continue", phase="点击")
                time.sleep(0.25)
                idle = 0
                continue
            else:
                # 继续灰 + 无选项：等语音/动画，最多轮询几次再点
                log("【硬编码】小故事继续灰且无题 → 等语音/动画（不调 API）")
                ready = False
                for _wait_i in range(4):
                    time.sleep(0.7)
                    st_w = status()
                    if st_w.get("mode") != "story":
                        st = st_w
                        break
                    w_opts = st_w.get("options") or []
                    w_ch = st_w.get("challenge")
                    w_instr = st_w.get("instruction") or ""
                    if w_opts or w_ch == "sort" or "順番" in w_instr or "並べ" in w_instr:
                        # 等的过程中出现了题
                        log(f"【小故事】等待中出现题目 options={len(w_opts)}")
                        st = st_w
                        needs_answer = True
                        break
                    if st_w.get("continue_enabled") is True:
                        log("【硬编码】继续已变绿 → 点继续")
                        run_driver("continue", phase="点击")
                        time.sleep(0.25)
                        ready = True
                        idle = 0
                        break
                    st = st_w
                else:
                    # 仍灰：盲点一次底栏（有时 enabled 滞后），或点一下正文推进
                    log("【硬编码】等待后仍灰 → 盲点继续/正文")
                    run_driver("continue", phase="点击")
                    time.sleep(0.35)
                    ready = True
                    idle = 0
                if ready and not needs_answer:
                    continue
                if not needs_answer:
                    continue
                log(
                    f"【小故事】需答题 challenge={st.get('challenge')} "
                    f"options={len(st.get('options') or [])}"
                )

        raw_join2 = " ".join(st.get("raw_texts") or [])
        if screen == "session" and ("跳过" in raw_join2 or "Skip" in raw_join2):
            log("【硬编码】课内出现跳过 → 尝试点击（不调 API）")
            try:
                from duo_driver import try_skip_in_session

                if try_skip_in_session():
                    time.sleep(0.4)
                    idle = 0
                    continue
            except Exception as e:
                log(f"【硬编码】跳过失败：{e}")

        # 主页选课是确定性操作，不需要浪费一次模型调用。
        if screen == "home":
            log("【硬编码】主页/路径 → 直接选课并开课（不调 API）")
            decision = {"actions": [{"op": "start"}], "reason": "home_hardcoded"}
        else:
            # —— 需要 AI 答题 ——
            log("【API】请求大模型答题…")
            t_api = time.time()
            try:
                decision = judge(st)
            except Exception as e:
                log(f"【API】调用失败：{e}")
                idle += 1
                if idle >= 3:
                    log("【停止】API 连续失败")
                    break
                time.sleep(0.5)
                continue
            log(f"【API】返回（{time.time() - t_api:.1f}s）", data=decision)

        actions = decision.get("actions") or []
        if not actions:
            idle += 1
            log(f"【API】无动作（空转 {idle}/3）")
            if idle >= 3:
                log("【停止】模型连续无动作")
                break
            time.sleep(0.4)
            continue

        idle = 0
        cleaned = []
        for a in actions:
            if a.get("op") == "check" and cleaned and cleaned[-1].get("op") in {
                "chips",
                "choice",
            }:
                log("【过滤】去掉多余的检查（组词/选项后已自动点）")
                continue
            cleaned.append(a)
        actions = cleaned

        if "配对" in (st.get("instruction") or ""):
            from duo_judge import _match_pool, _match_complete

            pool = _match_pool(st)
            fixed = []
            for a in actions:
                if a.get("op") != "match":
                    fixed.append(a)
                    continue
                labels = list(a.get("labels") or [])
                ok, missing = _match_complete(labels, pool)
                if not ok:
                    log(
                        "【过滤】配对不完整，拒绝执行",
                        data={
                            "给了": len(labels),
                            "需要": len(pool),
                            "labels": labels,
                            "缺的": missing,
                            "全部": pool,
                        },
                    )
                    continue
                fixed.append(a)
            actions = fixed
            if not actions:
                idle += 1
                log("【过滤】本轮无有效配对动作")
                time.sleep(0.3)
                continue

        if not hasattr(play, "_last_match_key"):
            play._last_match_key = None  # type: ignore[attr-defined]
        filtered = []
        for a in actions:
            if a.get("op") == "match":
                key = tuple(a.get("labels") or [])
                if key and key == play._last_match_key:  # type: ignore[attr-defined]
                    log("【过滤】与上一轮相同的配对，跳过防死循环")
                    continue
                play._last_match_key = key  # type: ignore[attr-defined]
            filtered.append(a)
        actions = filtered
        if not actions:
            idle += 1
            time.sleep(0.3)
            continue

        for act in actions:
            op = act.get("op")
            if op == "done":
                finished = lessons
                break
            if op not in {
                "chips",
                "choice",
                "match",
                "order",
                "check",
                "continue",
                "start",
                "skip",
                "go-home",
                "wait",
                "done",
            }:
                log(f"【过滤】忽略未知动作：{op}")
                continue
            # 小故事禁止 skip（灰继续≠可跳过）
            if mode == "story" and op == "skip":
                log("【过滤】小故事忽略 skip（灰继续应等待或答题，不跳过）")
                continue
            if (
                act.get("op") in {"chips", "choice", "match"}
                and mode != "story"
                and "检查" not in (st.get("buttons") or [])
            ):
                log("【硬编码】无检查按钮却要答题 → 当反馈页处理")
                run_driver("handle-feedback", phase="点击")
                time.sleep(0.3)
                break
            try:
                log(f"【执行】{_summarize_action(act)}")
                result = exec_action(act)
            except Exception as e:
                log(f"【执行】失败 {op}：{e}")
                # 点的时候才发现 adb 掉了 → 也停（错误信息里带 no devices）
                if _is_adb_lost_text(str(e)):
                    log("【致命】ADB 断开，停止")
                    finished = lessons
                break

            if (
                mode == "story"
                and op == "choice"
                and result.get("advanced") is False
            ):
                rejected = str(act.get("label") or "")
                if rejected:
                    story_rejected.add(rejected)
                    log(
                        f"【小故事】选项未推进，下一轮排除：{rejected}",
                        data={"已排除": sorted(story_rejected)},
                    )

            if act.get("op") == "start":
                if result.get("chest_opened") or result.get("path_advanced"):
                    reason = "已打开路径宝箱" if result.get("chest_opened") else "路径已推进"
                    log(f"【开课】{reason}，下一步重新读屏选课")
                    start_fails = 0
                elif result.get("started") is False or result.get("error") or result.get("rc", 0) != 0:
                    # 若其实已进 session，不算失败
                    st_after = unwrap_state(result)
                    if st_after.get("screen") == "session" or st_after.get("instruction"):
                        log("【开课】返回异常但已在做题页，当作成功")
                        start_fails = 0
                        saw_session = True
                    else:
                        start_fails += 1
                        log(f"【开课】失败（{start_fails}/3）")
                        if start_fails >= 3:
                            log("【停止】连续开课失败")
                            return
                else:
                    st_after = unwrap_state(result)
                    if st_after.get("screen") == "session" or st_after.get("instruction"):
                        start_fails = 0
                        saw_session = True
                    else:
                        start_fails += 1
                        if start_fails >= 3:
                            log("【停止】开课后未进入做题页")
                            return

            if act.get("op") == "check" and not result.get("advanced"):
                log("【硬编码】检查后点底部继续")
                run_driver("continue", phase="点击")
                time.sleep(0.2)

        time.sleep(0.08)

    summary = {
        "完成课数": finished,
        "总步数": step,
        "日志文件": str(LOG_PATH),
    }
    log("【结束】", data=summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main() -> int:
    p = argparse.ArgumentParser(description="多邻国自动做题 loop")
    p.add_argument("--judge", default=None, help="manual | openai")
    p.add_argument("--lessons", type=int, default=1)
    p.add_argument("--max-steps", type=int, default=120)
    p.add_argument("--log", default=None, help="日志路径")
    p.add_argument("--verbose-driver", action="store_true", help="日志里保留 driver 原始 JSON")
    args = p.parse_args()
    global VERBOSE_DRIVER
    VERBOSE_DRIVER = bool(args.verbose_driver)
    setup_log(Path(args.log) if args.log else None)
    play(args.lessons, args.judge or "manual", args.max_steps)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

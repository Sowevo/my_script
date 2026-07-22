#!/usr/bin/env python3
"""
Answer judge for Duolingo driver.

Contract (stable — swap models without touching duo_driver.py):

  Input:  status JSON from `duo_driver.py status` (screen/instruction/prompt/chips/options/...)
  Output: {"actions": [ {"op": "...", ...}, ... ], "reason": "..."}

Supported ops (executed by duo_loop / driver CLI):
  chips   {"op":"chips","words":["今日","は",...]}
  choice  {"op":"choice","label":"飲みたい"}
  match   {"op":"match","labels":["恋爱","恋愛",...]}
  check   {"op":"check"}
  continue {"op":"continue"}
  skip    {"op":"skip"}
  start   {"op":"start"}
  go-home {"op":"go-home"}       # bottom house / Learn tab
  done    {"op":"done"}          # lesson/session finished from judge POV
  wait    {"op":"wait","sec":1}

Judges:
  manual   — print status, read one JSON line from stdin (Approach A / you in chat)
  openai   — any OpenAI-compatible chat API (DeepSeek, etc.)

Env for openai judge (DeepSeek example):
  DUO_JUDGE=openai
  OPENAI_API_KEY=sk-...                 # or DEEPSEEK_API_KEY
  OPENAI_BASE_URL=https://api.deepseek.com
  OPENAI_MODEL=deepseek-chat            # cheap/fast; change when you get Flash
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any


SYSTEM_PROMPT = """你是多邻国答题器。根据 UI 状态 JSON 决定要点什么，不要解释长篇。

规则：
1. 只使用状态里出现的 chips / options 原文，不要发明不存在的词。
2. 翻译组句：返回 chips 动作，words 必须是正确日语语序，且只用 chips 里有的词。
   - 助词/接续要合理（は/が/を/ので/こと 等位置要对）。
   - 例：山里的天气…突然下雨 → 往往是 山 は 天気 が 変わる ので 急に 降る こと が あります 这类；
     若 chips 无「が」则按现有词凑最通顺语序，不要乱序堆砌。
3. chips 列表里同一个词可能出现多次（例如两个「を」）——需要几次就写几次，不要合并。
4. 单选/填空：返回 choice，label 必须与 options 完全一致。
4b. 选图（instruction 含「图片」）：prompt 是词（如「谷」），options/image_options 是图下文字（如山谷/医院）。
    返回 choice，label=正确图的文字（例：谷→山谷）。不要 skip。
4c. 小故事 mode=story：
   - continue_enabled=true：脚本自己点继续，你不该被问到。
   - continue_enabled=false（继续灰色）：必须先答题。
     · 多选：instruction 是题干残句，options 是完整选项（如 重いと思いました）。
     · 点选词段：options 是句子切段（如 苦労）。
     返回 choice，label=正确选项原文。不要 chips，不要 check。
   - challenge=gap_fill 或 instruction 含「文章を完成」「完成文章」：
     多空填空！prompt/[填空文]/gap_sentence 是句子，options/chips 是词库。
     若状态有 gap_words / blank_count：必须原样用 gap_words（已按空位左→右推断）。
     否则：词库里出现在句子中的词，按在句中出现顺序全部选出（通常 2+ 个，禁止只回 1 个除非真的单空）。
     返回一个 chips，words=全部空位用词。例：{"actions":[{"op":"chips","words":["きれい","メッセージ"]}],"reason":"..."}
     不要只填第一个空。不要 order/check/continue。
   - challenge=sort 或 instruction 含「順番に並べ」「並べて」：
     把 options 按故事时间顺序从上到下排列。
     返回 order，labels=正确顺序的全文列表（必须用 options 原文，每个恰好一次）。
     例：{"actions":[{"op":"order","labels":["先发生…","然后…","最后…"]}],"reason":"..."}
     不要 choice，不要 chips。脚本会拖动并点检查。
   - prompt 是对话上下文，可用来判断。
5. 配对（instruction 含「选择配对」/「配对」）：
   - 这不是选择题。不要用 choice。
   - 状态里有 left（左列，通常中文）和 right（右列，通常日语）。
   - 为 left 每个词在 right 找对应；labels=[L1,R1,L2,R2,...]，长度=left+right。
   - 中日同形（两列都是「胸」）各写一次。禁止只配一部分。
   - 例 left=["山谷","街道","胸"] right=["通り","谷","胸"]：
     {"actions":[{"op":"match","labels":["山谷","谷","街道","通り","胸","胸"]}],"reason":"..."}
6. feedback 由脚本处理，不要 continue。
7. home：start。other：go-home。禁止开始复习。
8. 组词/单选：chips 或 choice。
9. 看不懂：skip。

输出格式（必须严格遵守，不要 markdown）：
{"actions":[{"op":"choice","label":"选项原文"}],"reason":"短"}
- 顶层键只能是 actions（数组）和 reason（字符串）。
- 每个动作必须有 "op" 字段（不要用 action / type）。
- 例：{"actions":[{"op":"chips","words":["今日","は"]}],"reason":"ok"}
- 禁止：{"action":"choice","label":"..."}、{"op":"choice",...} 单独一个对象、多余字段乱套。
"""


def _normalize_actions(data: Any) -> dict:
    """只认标准格式：{"actions":[{"op":...}, ...], "reason":"..."}。"""
    if isinstance(data, list):
        data = {"actions": data, "reason": ""}
    if not isinstance(data, dict):
        return {"actions": [{"op": "wait", "sec": 0.5}], "reason": "invalid judge output"}
    actions = data.get("actions") or []
    if isinstance(actions, dict):
        actions = [actions]
    out = []
    for a in actions:
        if not isinstance(a, dict) or "op" not in a:
            continue
        op = str(a["op"]).lower().strip()
        item = {"op": op}
        if op == "chips":
            words = a.get("words") or a.get("chips") or []
            if isinstance(words, str):
                words = words.split()
            item["words"] = [str(w) for w in words]
        elif op == "choice":
            item["label"] = str(a.get("label") or a.get("text") or "")
        elif op == "match":
            labels = a.get("labels") or a.get("pairs") or []
            if isinstance(labels, str):
                labels = labels.split()
            item["labels"] = [str(x) for x in labels]
        elif op in {"order", "sort", "reorder"}:
            item["op"] = "order"
            labels = a.get("labels") or a.get("words") or a.get("order") or []
            if isinstance(labels, str):
                labels = labels.split()
            item["labels"] = [str(x) for x in labels]
        elif op == "wait":
            item["sec"] = float(a.get("sec", 0.5))
        out.append(item)
    return {"actions": out, "reason": str(data.get("reason") or "")}


def judge_manual(status: dict) -> dict:
    """Approach A: external human / chat agent supplies JSON on stdin."""
    print("=== JUDGE INPUT (status) ===", file=sys.stderr)
    print(json.dumps(status, ensure_ascii=False, indent=2), file=sys.stderr)
    print(
        '=== paste one JSON line, e.g. '
        '{"actions":[{"op":"choice","label":"飲みたい"},{"op":"check"}],"reason":"..."} ===',
        file=sys.stderr,
    )
    line = sys.stdin.readline()
    if not line.strip():
        return {"actions": [{"op": "wait", "sec": 1}], "reason": "empty stdin"}
    try:
        return _normalize_actions(json.loads(line))
    except json.JSONDecodeError as e:
        return {"actions": [], "reason": f"bad json: {e}"}


def _chat_completion(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    timeout: float = 60,
    *,
    max_tokens: int | None = None,
    temperature: float = 0.1,
) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        body["max_tokens"] = max_tokens
    # DeepSeek / some hosts support json object mode; keep optional
    if os.environ.get("OPENAI_JSON_MODE", "1") not in {"0", "false", "False"}:
        body["response_format"] = {"type": "json_object"}

    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {err}") from e

    return raw["choices"][0]["message"]["content"]


# 配对专用短 system：完整 SYSTEM_PROMPT 太长，模型在 5 对中日词上会「想很久」
PAIRING_SYSTEM = """多邻国「选择配对」答题器。只输出一个 JSON。
屏幕是两列：left=左列（通常中文）5 张，right=右列（通常日语）5 张。
任务：为 left 里每个词在 right 里找对应翻译/同义，组成 5 对。
规则：
- 唯一动作：{"op":"match","labels":[...]}
- labels 顺序：L1,R1, L2,R2, ...（先左后右，共 must_label_count 个）
- left 每个用一次，right 每个用一次；中日同形（两列都是「胸」）也要各写一次
- 禁止只配一部分、禁止 choice/chips
例 left=["山谷","街道","胸"] right=["通り","谷","胸"]
→ {"actions":[{"op":"match","labels":["山谷","谷","街道","通り","胸","胸"]}],"reason":"ok"}
"""


def _extract_json(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            return json.loads(m.group(0))
        raise


def _match_columns(status: dict) -> tuple[list[str], list[str]]:
    """Return (left_column, right_column) if present."""
    left = [str(x).strip() for x in (status.get("match_left") or []) if str(x).strip()]
    right = [str(x).strip() for x in (status.get("match_right") or []) if str(x).strip()]
    return left, right


def _match_pool(status: dict) -> list[str]:
    """
    All cards on the match board as a multiset.
    Prefer left+right columns when available; else options/chips.
    """
    skip = {
        "选择配对",
        "检查",
        "继续",
        "翻译这句话",
        "CHECK",
        "Continue",
        "选择对应的图片",
    }
    left, right = _match_columns(status)
    if left and right:
        return list(left) + list(right)
    opts = [str(x).strip() for x in (status.get("options") or []) if str(x).strip()]
    chips = [
        str(x).strip()
        for x in (status.get("chips") or [])
        if str(x).strip() and str(x).strip() not in skip
    ]
    pool = opts
    if len(chips) > len(pool):
        pool = chips
    if len(pool) >= 4:
        return pool
    for t in status.get("raw_texts") or []:
        t = str(t).strip()
        if t and t not in skip:
            pool.append(t)
    return pool


def _is_pairing(status: dict) -> bool:
    instr = str(status.get("instruction") or "")
    return "配对" in instr or "Match" in instr


def _match_complete(labels: list[str], pool: list[str]) -> tuple[bool, list[str]]:
    """True if labels is a permutation of pool (each once)."""
    if not pool:
        return False, pool
    if len(labels) != len(pool):
        return False, [w for w in pool if w not in labels]
    from collections import Counter

    if Counter(labels) != Counter(pool):
        missing = []
        c = Counter(labels)
        for w in pool:
            if c[w] != 1:
                missing.append(w)
        return False, missing
    return True, []


def judge_openai(status: dict) -> dict:
    """
    OpenAI-compatible judge — works with DeepSeek today.

    Pairing: validates full coverage; re-asks once if AI only returns partial pairs.
    """
    api_key = (
        os.environ.get("OPENAI_API_KEY")
        or os.environ.get("DEEPSEEK_API_KEY")
        or ""
    )
    if not api_key:
        raise RuntimeError("Set OPENAI_API_KEY or DEEPSEEK_API_KEY for openai judge")

    base_url = os.environ.get("OPENAI_BASE_URL") or os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
    model = os.environ.get("OPENAI_MODEL") or os.environ.get("DEEPSEEK_MODEL") or "deepseek-chat"

    pairing = _is_pairing(status)
    pool = _match_pool(status) if pairing else []

    instr = str(status.get("instruction") or "")
    image_pick = "图片" in instr
    is_story = (
        status.get("mode") == "story"
        or (status.get("feedback") or {}).get("is_stories")
        or "Stories" in str(status.get("activity") or "")
    )
    instr_l = instr
    story_sort = is_story and (
        status.get("challenge") == "sort"
        or "順番" in instr_l
        or "並べ" in instr_l
        or "顺序" in instr_l
    )
    story_gap = is_story and (
        status.get("challenge") in {"gap_fill", "tap_sequence"}
        or "文章を完成" in instr_l
        or "完成文章" in instr_l
        or (
            bool(status.get("chips"))
            and bool(status.get("options"))
            and "完成" in instr_l
        )
    )
    story_quiz = (
        is_story
        and bool(status.get("options"))
        and not story_sort
        and not story_gap
        and status.get("continue_enabled") is False
    )

    slim = {
        "screen": status.get("screen"),
        "instruction": status.get("instruction"),
        "prompt": status.get("prompt"),
        "buttons": status.get("buttons"),
        "hearts": status.get("hearts"),
        "hint": status.get("hint"),
    }
    if pairing:
        left, right = _match_columns(status)
        # 极简载荷：标明左右列，模型只需「左→右」配对
        slim = {
            "type": "pairing",
            "left": left or None,
            "right": right or None,
            "match_pool": pool,
            "must_label_count": len(pool),
            "rule": (
                f"Pair each left[i] with one right[j]. "
                f"labels = [L,R, L,R, ...] length {len(pool)}; "
                "use every left and every right once."
                if left and right
                else (
                    f"labels length={len(pool)}; multiset equal to match_pool; "
                    "CN↔JP pairs"
                )
            ),
        }
        # 去掉空字段
        if not slim["left"]:
            slim.pop("left", None)
            slim.pop("right", None)
    elif story_sort:
        opts = list(status.get("options") or [])
        slim["type"] = "story_sort"
        slim["mode"] = "story"
        slim["challenge"] = "sort"
        slim["question"] = status.get("instruction")
        slim["context"] = status.get("story_history") or status.get("prompt")
        slim["options"] = opts
        slim["current_order_top_to_bottom"] = opts
        slim["must_label_count"] = len(opts)
        slim["raw_texts"] = (status.get("raw_texts") or [])[:20]
        slim["rule"] = (
            "MUST return one order action. labels = chronological order top→bottom, "
            f"length {len(opts)}, each option exactly once, exact strings from options. "
            "No choice/chips/check/continue."
        )
        slim["example"] = {
            "actions": [{"op": "order", "labels": opts}],
            "reason": "chronological",
        }
    elif story_gap:
        opts = list(status.get("options") or status.get("chips") or [])
        gap_words = list(status.get("gap_words") or [])
        blank_count = status.get("blank_count") or (len(gap_words) if gap_words else None)
        gap_sentence = status.get("gap_sentence") or ""
        if not gap_sentence and isinstance(status.get("prompt"), str) and "[填空文]" in status["prompt"]:
            gap_sentence = status["prompt"].split("[填空文]", 1)[1].strip()
        # If driver already inferred multi-blank answers, force that multiset
        if gap_words:
            must_words = gap_words
            must_n = len(gap_words)
        else:
            must_words = None
            must_n = blank_count
        slim["type"] = "story_gap_fill"
        slim["mode"] = "story"
        slim["challenge"] = "gap_fill"
        slim["question"] = status.get("instruction")
        slim["gap_sentence"] = gap_sentence or status.get("prompt")
        slim["word_bank"] = opts
        slim["chips"] = status.get("chips") or opts
        slim["gap_words"] = gap_words or None
        slim["blank_count"] = must_n
        slim["raw_texts"] = (status.get("raw_texts") or [])[:20]
        if must_words:
            # Deterministic multi-blank — do not call the model (it often returns only 1 word).
            return {
                "actions": [{"op": "chips", "words": list(must_words)}],
                "reason": f"gap_fill blanks×{must_n} from sentence∩bank",
            }
        slim["rule"] = (
            "MULTI-BLANK gap-fill. Pick EVERY bank word that belongs in the sentence blanks, "
            "left→right order, exact strings from word_bank. "
            "Usually 2+ words — returning only 1 word is WRONG unless blank_count=1. "
            "No choice/order/check/continue."
        )
        slim["example"] = {
            "actions": [{"op": "chips", "words": opts[:2] if len(opts) >= 2 else opts[:1] or ["…"]}],
            "reason": "fill all blanks L→R",
        }
    elif story_quiz:
        slim["type"] = "story_quiz"
        slim["mode"] = "story"
        slim["continue_enabled"] = False
        slim["question"] = status.get("instruction")
        slim["context"] = status.get("prompt")
        slim["options"] = status.get("options")
        slim["raw_texts"] = (status.get("raw_texts") or [])[:20]
        slim["rule"] = (
            "MUST return exactly one choice. label MUST be one of options (exact string). "
            "No empty actions. No chips. No check. No continue."
        )
        slim["example"] = {
            "actions": [{"op": "choice", "label": (status.get("options") or ["…"])[0]}],
            "reason": "short",
        }
    elif image_pick:
        slim["type"] = "image_choice"
        slim["options"] = status.get("options")
        slim["image_options"] = status.get("image_options") or []
        slim["rule"] = "choice with exact caption text matching the prompt word (e.g. 谷→山谷)"
        slim["raw_texts"] = (status.get("raw_texts") or [])[:20]
    else:
        slim["mode"] = status.get("mode")
        chips = list(status.get("chips") or [])
        retry_tray = list(status.get("retry_tray") or [])
        if retry_tray and not status.get("options"):
            # After an incorrect word-bank answer, Duolingo keeps the previous
            # selection in the upper tray and restores the remaining words below.
            # The executor clears that tray before retrying, so the judge needs
            # the complete multiset to build a fresh full answer.
            slim["chips"] = retry_tray + chips
            slim["retry_tray"] = retry_tray
            slim["rule"] = (
                "Retry state: chips contains the COMPLETE word bank (upper retained "
                "+ lower remaining). Return a fresh full chips sequence using exact "
                "strings; the executor will clear retry_tray first."
            )
        else:
            slim["chips"] = chips
        slim["options"] = status.get("options")
        slim["raw_texts"] = (status.get("raw_texts") or [])[:30]

    sys_prompt = PAIRING_SYSTEM if pairing else SYSTEM_PROMPT
    # 注意：DeepSeek + max_tokens 有时会返回空 content，配对不要限 max_tokens
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": json.dumps(slim, ensure_ascii=False)},
    ]
    content = _chat_completion(
        base_url, api_key, model, messages, temperature=0.0 if pairing else 0.1
    )
    try:
        decision = _normalize_actions(_extract_json(content))
    except Exception as e:
        decision = {"actions": [], "reason": f"parse_fail: {e} | raw={content[:200]}"}
    api_calls = 1

    # 格式不对 / 空 actions：提示词重试一次（不兼容花式字段，只纠正格式）
    if not (decision.get("actions") or []):
        repair = {
            "error": "bad_or_empty_format",
            "got": (content or "")[:300],
            "fix": (
                "上一条无效。必须只输出：\n"
                '{"actions":[{"op":"choice","label":"…"}],"reason":"…"} 或 chips/match/order/start 等\n'
                '禁止 {"action":"choice",...}；必须用 actions 数组 + 每项 op 字段。'
            ),
        }
        if story_sort:
            repair["fix"] = (
                '输出：{"actions":[{"op":"order","labels":[...]}],"reason":"…"} '
                f"labels 长度 {len(status.get('options') or [])}"
            )
        elif story_quiz or (status.get("options") and "检查" in (status.get("buttons") or [])):
            opts = list(status.get("options") or [])
            repair["fix"] = (
                '输出：{"actions":[{"op":"choice","label":"<options之一>"}],"reason":"…"} '
                f"label 必须是 {opts} 之一"
            )
        messages.append({"role": "assistant", "content": content or ""})
        messages.append({"role": "user", "content": json.dumps(repair, ensure_ascii=False)})
        content = _chat_completion(
            base_url, api_key, model, messages, temperature=0.0
        )
        api_calls += 1
        try:
            decision = _normalize_actions(_extract_json(content))
        except Exception as e:
            decision = {"actions": [], "reason": f"format_retry_fail: {e} | raw={content[:200]}"}
        if decision.get("actions"):
            decision["reason"] = (decision.get("reason") or "") + f" | format_retry api_calls={api_calls}"

    # Story quiz/sort: never accept empty — retry once with stricter reminder
    if (story_quiz or story_sort) and not (decision.get("actions") or []):
        opts = list(status.get("options") or [])
        if story_sort:
            repair = {
                "error": "empty_actions_not_allowed",
                "type": "story_sort",
                "question": status.get("instruction"),
                "context": status.get("prompt"),
                "options": opts,
                "fix": (
                    "Output ONLY: "
                    '{"actions":[{"op":"order","labels":[...]}],"reason":"..."} '
                    f"labels length {len(opts)}, permutation of {opts}"
                ),
            }
        else:
            repair = {
                "error": "empty_actions_not_allowed",
                "type": "story_quiz",
                "question": status.get("instruction"),
                "context": status.get("prompt"),
                "options": opts,
                "fix": (
                    "Previous reply had no actions. Output ONLY: "
                    '{"actions":[{"op":"choice","label":"<one of options>"}],"reason":"..."} '
                    f"label must be exact one of {opts}"
                ),
            }
        messages.append({"role": "assistant", "content": content})
        messages.append({"role": "user", "content": json.dumps(repair, ensure_ascii=False)})
        content = _chat_completion(base_url, api_key, model, messages)
        try:
            decision = _normalize_actions(_extract_json(content))
        except Exception as e:
            decision = {"actions": [], "reason": f"story_retry_parse_fail: {e}"}

    # Validate story_sort: labels must be full permutation
    if story_sort:
        opts = list(status.get("options") or [])
        labels: list[str] = []
        for a in decision.get("actions") or []:
            if a.get("op") == "order":
                labels = list(a.get("labels") or [])
                break
        from collections import Counter

        unchanged_unsolved = (
            labels == opts and status.get("check_enabled") is False
        )
        if not opts or Counter(labels) != Counter(opts) or unchanged_unsolved:
            repair = {
                "error": "unchanged_unsolved_order" if unchanged_unsolved else "bad_order",
                "got": labels,
                "options": opts,
                "story_context": status.get("story_history") or status.get("prompt"),
                "fix": (
                    "The current displayed order is still unsolved (Check is disabled). "
                    "Use story_context and return a DIFFERENT chronological permutation."
                    if unchanged_unsolved
                    else f"labels must be a permutation of options (len={len(opts)}). Re-output order only."
                ),
            }
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": json.dumps(repair, ensure_ascii=False)})
            content = _chat_completion(base_url, api_key, model, messages)
            try:
                decision = _normalize_actions(_extract_json(content))
            except Exception as e:
                decision = {"actions": [], "reason": f"sort_repair_fail: {e}"}

    # If still empty on story quiz, coerce flat JSON
    if story_quiz and not (decision.get("actions") or []):
        try:
            raw_obj = _extract_json(content)
            if isinstance(raw_obj, dict):
                lab = raw_obj.get("label") or raw_obj.get("choice") or raw_obj.get("answer")
                if lab and str(lab) in (status.get("options") or []):
                    decision = {
                        "actions": [{"op": "choice", "label": str(lab)}],
                        "reason": "coerced_from_flat",
                    }
        except Exception:
            pass

    if not pairing or not pool:
        if api_calls > 1:
            decision["reason"] = (decision.get("reason") or "") + f" | api_calls={api_calls}"
        return decision

    # 最多再修 1 次（以前最多 2 次修复=共 3 次请求，配对 50s×3 会炸）
    labels: list[str] = []
    for a in decision.get("actions") or []:
        if a.get("op") == "match":
            labels = list(a.get("labels") or [])
            break
    ok, missing = _match_complete(labels, pool)
    if ok:
        decision["reason"] = (decision.get("reason") or "") + f" | api_calls={api_calls}"
        return decision

    repair = {
        "error": "incomplete_match",
        "got_labels": labels,
        "got_count": len(labels),
        "need_count": len(pool),
        "match_pool": pool,
        "missing_or_wrong": missing,
        "fix": (
            f"Re-output ONE match; labels multiset MUST equal match_pool "
            f"(len={len(pool)}). Same-text cards twice if pool has them twice."
        ),
    }
    messages.append({"role": "assistant", "content": content})
    messages.append({"role": "user", "content": json.dumps(repair, ensure_ascii=False)})
    content = _chat_completion(base_url, api_key, model, messages, temperature=0.0)
    api_calls += 1
    try:
        decision = _normalize_actions(_extract_json(content))
    except Exception as e:
        decision = {"actions": [], "reason": f"match_repair_parse_fail: {e} | raw={content[:120]!r}"}

    labels = []
    for a in decision.get("actions") or []:
        if a.get("op") == "match":
            labels = list(a.get("labels") or [])
            break
    ok, missing = _match_complete(labels, pool)
    if not ok:
        decision["actions"] = [a for a in (decision.get("actions") or []) if a.get("op") != "match"]
        decision["reason"] = (
            (decision.get("reason") or "")
            + f" | REJECTED incomplete match missing={missing} api_calls={api_calls}"
        )
    else:
        decision["reason"] = (decision.get("reason") or "") + f" | repaired api_calls={api_calls}"
    return decision


def get_judge(name: str | None = None):
    name = (name or os.environ.get("DUO_JUDGE") or "manual").lower()
    if name in {"manual", "human", "stdin", "a"}:
        return judge_manual
    if name in {"openai", "deepseek", "llm", "api"}:
        return judge_openai
    raise SystemExit(f"unknown judge: {name} (use manual|openai)")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    judge_name = None
    if argv and argv[0] in {"manual", "openai", "deepseek", "llm"}:
        judge_name = "openai" if argv[0] in {"deepseek", "llm"} else argv[0]
        argv = argv[1:]

    if argv and argv[0] not in {"-"}:
        status = json.loads(Path_read(argv[0]))
    else:
        status = json.load(sys.stdin)

    judge = get_judge(judge_name)
    result = judge(status)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def Path_read(p: str) -> str:
    from pathlib import Path

    return Path(p).read_text(encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

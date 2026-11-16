#!/usr/bin/env python3
"""translate.py — 把日文新聞標題翻成繁體中文。零 token 之外唯一會用到模型的地方。

刻意設計成「很小、很便宜」：
  * 只翻含假名的條目（玩具類 20 條左右，英文/中文條目完全不碰）
  * 只翻標題（摘要不值得花錢，圖和價格才是重點）
  * 整批一次呼叫（不是一條一個 request）
  * 快取以「日文原文」為 key，同一條永遠不重翻
  * thinking 關掉：實測 2.6 秒 / 2 條 / 287 token（開著是 16 秒、2639 token）

實測成本：20 條 ≈ 3,000 token ≈ 月額度的 0.01%。
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
import uuid

BASE = "https://opencode.ai/zen/go/v1/chat/completions"
MODEL = "deepseek-v4.1-flash"
JP_RE = re.compile(r"[\u3040-\u30ff]")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
BATCH = 20
EN_MAX = 60        # 每輪最多翻幾條英文（新的在前）：防三源一次灌太多標題進去

_HEADERS_TMPL = {
    "Content-Type": "application/json",
    "User-Agent": "Hermes/1.0 (+https://hermes-agent.nousresearch.com)",
    "HTTP-Referer": "https://hermes-agent.nousresearch.com",
}


def _env_file() -> str:
    r"""Windows: %LOCALAPPDATA%\hermes\.env · Linux/macOS: $HERMES_HOME/.env"""
    if os.name == "nt":
        la = os.environ.get("LOCALAPPDATA")
        if la:
            return os.path.join(la, "hermes", ".env")
    return os.path.join(os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes"), ".env")


def _key() -> str:
    p = _env_file()
    try:
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line.startswith("OPENCODE_GO_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return os.environ.get("OPENCODE_GO_API_KEY", "")


def _call(key: str, titles: list[str], timeout: int = 60, strict: bool = False) -> list[str]:
    sys_prompt = (
        "你是翻譯。把標題翻成繁體中文（台灣用語）。原文可能是日文或英文。"
        "日文：正常翻譯。英文：壓成一句 20 字內的中文重點，講清楚這是什麼、有什麼用，"
        "不要逐字直譯，不要保留英文語序。"
        "輸入可能是「標題 || 摘要」，摘要只幫你判斷內容，"
        "輸出仍是那句中文重點，不要照抄摘要、不要輸出兩段。"
        "專有名詞（機體名、作品名、角色名、品牌、專案名）保留原文並用括號附註中文。"
        "不要加解釋、不要加引號、不要編號。"
        "只輸出 JSON 字串陣列，長度與輸入完全相同。"
    )
    if strict:
        sys_prompt += (
            "⚠ 這一輪是補翻：上一輪你只回了英文原文。這次一定要輸出中文，"
            "即使只有專案名或論文名，也要依摘要寫出它做什麼；不准只回英文原名。"
        )
    payload = {
        "model": MODEL,
        "temperature": 0.1,
        "thinking": {"type": "disabled"},
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": json.dumps(titles, ensure_ascii=False)},
        ],
    }
    h = dict(_HEADERS_TMPL)
    h["Authorization"] = f"Bearer {key}"
    h["x-opencode-session"] = str(uuid.uuid4())
    req = urllib.request.Request(BASE, data=json.dumps(payload).encode(), headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    txt = d["choices"][0]["message"]["content"].strip()
    txt = re.sub(r"^```(?:json)?|```$", "", txt, flags=re.M).strip()
    out = json.loads(txt)
    if not isinstance(out, list):
        raise ValueError("not a list")
    return [str(x) for x in out]


def translate_items(items: list[dict], cache_path: str) -> int:
    """就地補上 item["zh"]。回傳這次新翻譯的條數（0 = 全部命中快取）。"""
    cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}

    # 只翻「日文或英文」且快取沒有的；中文標題不碰。
    # 英文（arXiv／HN／GitHub）每輪上限 EN_MAX 條，新的在前——items 進來時已按 ts 排好。
    need, en_taken = [], 0
    for it in items:
        t = it.get("title") or ""
        is_jp = bool(JP_RE.search(t))
        is_en = (not CJK_RE.search(t)) and len(re.findall(r"[A-Za-z]{3,}", t)) >= 3
        if not (is_jp or is_en):
            continue
        if t in cache:
            it["zh"] = cache[t]
            continue
        if is_en and not is_jp:
            if en_taken >= EN_MAX:
                continue
            en_taken += 1
        need.append(it)

    if not need:
        return 0

    key = _key()
    if not key:
        print("[translate] no OPENCODE_GO_API_KEY; skipped", flush=True)
        return 0

    def _payload(x):
        t = x["title"]
        if (not JP_RE.search(t)) and not CJK_RE.search(t):
            s = (x.get("summary") or "")[:180].replace("\n", " ").strip()
            return f"{t} || {s}" if s else t
        return t

    def _clean(t, zh):
        zh = (zh or "").strip().strip('"').strip()
        # 模型偶爾把「標題 || 摘要」整串吐回來：砍掉前面的原文只留中文
        if zh.startswith(t):
            zh = zh[len(t):]
        return zh.lstrip(" ｜|:：-—·、,，").strip()

    def _accept(it, zh) -> bool:
        t = it["title"]
        zh = _clean(t, zh)
        if not zh or zh == t or not CJK_RE.search(zh):
            return False
        it["zh"] = zh
        cache[t] = zh
        return True

    done = 0
    for strict in (False, True):
        pending = [x for x in need if x["title"] not in cache]
        if not pending:
            break
        for i in range(0, len(pending), BATCH):
            chunk = pending[i:i + BATCH]
            payloads = [_payload(x) for x in chunk]
            try:
                outs = _call(key, payloads, strict=strict)
            except Exception as e:
                print(f"[translate] batch failed: {type(e).__name__}: {str(e)[:80]}", flush=True)
                continue
            if len(outs) != len(chunk):
                print(f"[translate] length mismatch {len(outs)}!={len(chunk)}; skip batch", flush=True)
                continue
            for it, zh in zip(chunk, outs):
                if _accept(it, zh):
                    done += 1
        if strict:
            break

    if done:
        try:
            if len(cache) > 2000:                     # 快取別無限長
                cache = dict(list(cache.items())[-1500:])
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=0)
        except Exception:
            pass
    return done


if __name__ == "__main__":
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "items.json")
    d = json.load(open(p, encoding="utf-8"))
    n = translate_items(d["items"], os.path.join(os.path.dirname(p), "translate_cache.json"))
    print(f"translated {n}")
    for x in d["items"][:200]:
        if x.get("zh"):
            print(f"  {x['source']:12} {x['zh'][:50]}")

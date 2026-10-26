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
BATCH = 20

_HEADERS_TMPL = {
    "Content-Type": "application/json",
    "User-Agent": "Hermes/1.0 (+https://hermes-agent.nousresearch.com)",
    "HTTP-Referer": "https://hermes-agent.nousresearch.com",
}


def _key() -> str:
    p = os.path.expanduser("~/AppData/Local/hermes/.env")
    try:
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line.startswith("OPENCODE_GO_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return os.environ.get("OPENCODE_GO_API_KEY", "")


def _call(key: str, titles: list[str], timeout: int = 60) -> list[str]:
    payload = {
        "model": MODEL,
        "temperature": 0.1,
        "thinking": {"type": "disabled"},
        "messages": [
            {"role": "system", "content":
                "你是翻譯。把日文標題翻成繁體中文（台灣用語）。"
                "專有名詞（機體名、作品名、角色名、品牌）保留日文原文並用括號附註中文。"
                "不要加解釋、不要加引號、不要編號。"
                "只輸出 JSON 字串陣列，長度與輸入完全相同。"},
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

    # 只翻「含假名」且快取沒有的
    need = []
    for it in items:
        t = it.get("title") or ""
        if not JP_RE.search(t):
            continue
        if t in cache:
            it["zh"] = cache[t]
        else:
            need.append(it)

    if not need:
        return 0

    key = _key()
    if not key:
        print("[translate] no OPENCODE_GO_API_KEY; skipped", flush=True)
        return 0

    done = 0
    for i in range(0, len(need), BATCH):
        chunk = need[i:i + BATCH]
        titles = [x["title"] for x in chunk]
        try:
            outs = _call(key, titles)
        except Exception as e:
            print(f"[translate] batch failed: {type(e).__name__}: {str(e)[:80]}", flush=True)
            continue
        if len(outs) != len(titles):
            print(f"[translate] length mismatch {len(outs)}!={len(titles)}; skip batch", flush=True)
            continue
        for it, zh in zip(chunk, outs):
            zh = zh.strip().strip('"').strip()
            if zh and zh != it["title"]:
                it["zh"] = zh
                cache[it["title"]] = zh
                done += 1

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

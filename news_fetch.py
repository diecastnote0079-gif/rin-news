#!/usr/bin/env python3
"""news_fetch.py — feed list -> items.json.  Zero tokens, no LLM.

This is the ONLY part that changes when content updates. The page shell
(index.html) reads items.json at runtime, so refreshing data never touches
the layout.

Usage:  python news_fetch.py [--limit N] [--out DIR]
Exit:   0 ok, 1 nothing fetched (page keeps last data)
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

# (display name, category, feed url)
FEEDS = [
    ("Hermes",        "hermes",   "https://github.com/NousResearch/hermes-agent/releases.atom"),
    ("ComfyUI",       "pipeline", "https://github.com/comfyanonymous/ComfyUI/releases.atom"),
    ("mlllm",         "image",    "https://mlllm.io/rss.xml"),
    ("local-ai.net",  "local",    "https://local-ai.net/rss.xml"),
    ("HF Blog",       "model",    "https://huggingface.co/blog/feed.xml"),
    ("r/LocalLLaMA",  "local",    "https://www.reddit.com/r/LocalLLaMA/.rss"),
    ("Simon Willison","agent",    "https://simonwillison.net/atom/everything/"),
    ("HN 150+",       "agent",    "https://hnrss.org/newest?points=150"),
]

CATS = [
    ("all",      "全部"),
    ("image",    "生圖"),
    ("local",    "本地 LLM"),
    ("agent",    "Agent／工具"),
    ("pipeline", "Pipeline"),
    ("model",    "模型／研究"),
    ("hermes",   "Hermes"),
]

UA = "HermesRin-news/1.0 (+local reader)"
DEFAULT_OUT = r"D:\AI\news"


def clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def parse_date(s: str):
    if not s:
        return None
    s = s.strip().replace("GMT", "+0000")
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            d = datetime.strptime(s, fmt)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch(url: str, limit: int):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        root = ET.fromstring(r.read())

    rows = []
    for it in root.iter("item"):
        rows.append((clean(it.findtext("title") or ""),
                     (it.findtext("link") or "").strip(),
                     clean(it.findtext("description") or "")[:280],
                     parse_date(it.findtext("pubDate") or "")))
    if not rows:
        A = "{http://www.w3.org/2005/Atom}"
        for it in root.iter(A + "entry"):
            link = ""
            for ln in it.findall(A + "link"):
                if ln.get("rel") in (None, "alternate"):
                    link = ln.get("href") or ""
                    break
            rows.append((clean(it.findtext(A + "title") or ""), link,
                         clean(it.findtext(A + "summary") or it.findtext(A + "content") or "")[:280],
                         parse_date(it.findtext(A + "updated") or it.findtext(A + "published") or "")))
    return rows[:limit]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--out", default=DEFAULT_OUT)
    a = ap.parse_args()

    items, failed = [], []
    for name, cat, url in FEEDS:
        try:
            rows = fetch(url, a.limit)
        except Exception:
            failed.append(name)
            continue
        for title, link, summary, d in rows:
            if not title or not link:
                continue
            if "/ru/" in link or "/zh/" in link:   # translated duplicates
                continue
            items.append({
                "source": name, "cat": cat, "title": title, "link": link,
                "summary": summary,
                "ts": int(d.timestamp()) if d else 0,
                "date": d.astimezone().strftime("%m-%d %H:%M") if d else "",
            })

    if not items:
        print("nothing fetched; keeping existing items.json", file=sys.stderr)
        return 1

    os.makedirs(a.out, exist_ok=True)
    p = os.path.join(a.out, "items.json")

    old = None
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                old = json.load(f)
        except Exception:
            old = None

    # 某個來源這次抓不到（限流／逾時）→ 沿用它上次的條目。
    # 否則資料會在「85 條 / 73 條」之間來回跳，每輪都留一個假 commit。
    if failed and old:
        have = {i["title"].lower()[:80] for i in items}
        carried = [i for i in old.get("items", [])
                   if i.get("source") in failed and i["title"].lower()[:80] not in have]
        if carried:
            items.extend(carried)
        print(f"[carry-over] {', '.join(failed)} → +{len(carried)} 條", file=sys.stderr)

    seen, uniq = set(), []
    for it in sorted(items, key=lambda x: -x["ts"]):
        k = it["title"].lower()[:80]
        if k in seen:
            continue
        seen.add(k)
        uniq.append(it)

    # 內容沒變就不重寫（否則 generated_at 每次都變，git 每輪都留下一個空 commit）
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                old = json.load(f)
            if old.get("items") == uniq and old.get("cats") == [list(c) for c in CATS]:
                print(f"{len(uniq)} items, no change -> keep {p}")
                return 0
        except Exception:
            pass

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cats": CATS,
        "items": uniq,
    }
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, p)          # atomic: page never reads a half-written file

    print(f"{len(uniq)} items, {len(failed)} feed(s) failed -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

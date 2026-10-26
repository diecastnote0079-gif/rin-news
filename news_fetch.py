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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import rank as rank_mod
except ImportError:
    rank_mod = None

# (display name, category, feed url)
# 原則：中文優先、跟阿夜手上的東西直接相關。英文工程師 changelog 一律不收。
# 2026-10-26 實測：以下 10 個來源可讀（星洲／中國報／玩具人／原價屋的 RSS 全部失效或被擋）
FEEDS = [
    ("4Gamers",      "game",     "https://www.4gamers.com.tw/rss"),
    ("巴哈 GNN",     "game",     "https://gnn.gamer.com.tw/rss.xml"),
    ("INSIDE",       "tech",     "https://www.inside.com.tw/feed/rss"),
    ("iThome",       "tech",     "https://www.ithome.com.tw/rss"),
    ("Unwire HK",    "tech",     "https://unwire.hk/feed/"),
    ("SoyaCincau",   "local",    "https://soyacincau.com/feed/"),
    ("Lowyat",       "local",    "https://www.lowyat.net/feed/"),
    ("Hermes",       "hermes",   "https://github.com/NousResearch/hermes-agent/releases.atom"),
    ("ComfyUI",      "pipeline", "https://github.com/comfyanonymous/ComfyUI/releases.atom"),
    ("mlllm",        "image",    "https://mlllm.io/rss.xml"),
    # 2026-10-26 第二輪擴充：實測 53 個候選，這 8 個可讀（中文優先）
    ("電腦玩物",      "tech",     "https://www.playpcesor.com/feeds/posts/default"),
    ("電腦王阿達",    "tech",     "https://www.kocpc.com.tw/feed/"),
    ("愛范兒",        "tech",     "https://www.ifanr.com/feed"),
    ("科技新報",      "tech",     "https://technews.tw/feed/"),
    ("Hobby Japan",   "toy",      "https://hjweb.jp/feed/"),
    ("電撃Hobby",     "toy",      "https://hobby.dengeki.com/feed/"),
    ("Hypebeast",     "hype",     "https://hypebeast.com/zh/feed"),
    ("ToyArk",        "toy",      "https://news.toyark.com/feed"),
]

CATS = [
    ("all",      "全部"),
    ("game",     "遊戲"),
    ("tech",     "科技"),
    ("toy",      "玩具模型"),
    ("hype",     "炒賣"),
    ("local",    "本地"),
    ("image",    "生圖"),
    ("pipeline", "Pipeline"),
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


BAD_IMG = ("gravatar", "feedburner", "doubleclick", "facebook.com/tr", "stats.wordpress",
           "avatars.githubusercontent", "github.githubassets", "/pixel", "1x1.",
           "badge", "shields.io", "spacer", "blank.gif")


def _ok_img(u: str) -> bool:
    if not u or u.startswith("data:"):
        return False
    low = u.lower()
    return not any(b in low for b in BAD_IMG)


def pick_image(node, ns_map):
    """找這則新聞的縮圖：enclosure / media:content / media:thumbnail / 內文第一個 <img>。
    排除頭像、追蹤像素、badge 這類假圖。"""
    for enc in node.findall("enclosure"):
        u = enc.get("url")
        if (enc.get("type") or "").startswith("image") and _ok_img(u):
            return u
    for tag in ("{http://search.yahoo.com/mrss/}content", "{http://search.yahoo.com/mrss/}thumbnail"):
        for el in node.iter(tag):
            u = el.get("url")
            if _ok_img(u) and (el.get("type", "image").startswith("image") or el.get("medium") == "image"):
                return u
    for ln in node.findall("{http://www.w3.org/2005/Atom}link"):
        u = ln.get("href")
        if (ln.get("rel") or "") in ("enclosure", "image") and (ln.get("type") or "").startswith("image") and _ok_img(u):
            return u
    # 內文 HTML 裡的第一張圖
    for field in ("description", "{http://www.w3.org/2005/Atom}content",
                  "{http://www.w3.org/2005/Atom}summary"):
        raw = node.findtext(field) or ""
        for m in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', raw):
            u = html.unescape(m.group(1))
            if _ok_img(u):
                return u
    return ""


def fetch(url: str, limit: int):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        root = ET.fromstring(r.read())

    rows = []
    for it in root.iter("item"):
        rows.append((clean(it.findtext("title") or ""),
                     (it.findtext("link") or "").strip(),
                     clean(it.findtext("description") or "")[:280],
                     parse_date(it.findtext("pubDate") or ""),
                     pick_image(it, None)))
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
                         parse_date(it.findtext(A + "updated") or it.findtext(A + "published") or ""),
                         pick_image(it, None)))
    return rows[:limit]


_NOISE = ("分享", "讚好", "個讚", "複製連結", "WhatsApp", "Facebook", "Threads",
          "Advertisement", "Photo Credit", "-->", "閱讀時間", "字體大小", "訂閱",
          "追蹤我們", "版權所有", "相關文章", "延伸閱讀", "留言", "熱門")


def _plain(s: str) -> str:
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def article_text(url: str, limit: int = 1600) -> str:
    """抓一頁的正文段落，給頁內閱讀模式用。失敗回空字串（前端退回摘要）。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                  "Accept-Language": "zh-TW,zh;q=0.9"})
        raw = urllib.request.urlopen(req, timeout=12).read()
        enc = "utf-8"
        m = re.search(rb'charset=["\']?([a-zA-Z0-9_-]+)', raw[:3000])
        if m:
            enc = m.group(1).decode("ascii", "ignore")
        try:
            t = raw.decode(enc, "ignore")
        except LookupError:
            t = raw.decode("utf-8", "ignore")
        # 有內文容器就縮進去，避免抓到整頁導航
        for pat in (r"<article[^>]*>(.*?)</article>",
                    r'<div[^>]*(?:id|class)="[^"]*(?:article-content|entry-content'
                    r'|post-content|articleContent|content-body|story)[^"]*"[^>]*>(.*?)</div>\s*</div>'):
            mm = re.search(pat, t, re.S | re.I)
            if mm and len(mm.group(1)) > 800:
                t = mm.group(1)
                break
        # 正文幾乎都在 <p>：短行（導航、標籤列）與噪音行濾掉
        ps = [_plain(x) for x in re.findall(r"<p[^>]*>(.*?)</p>", t, re.S | re.I)]
        ps = [x for x in ps if len(x) >= 25 and not any(k in x for k in _NOISE)]
        if sum(len(x) for x in ps) < 200:          # <p> 太少 → 退回全文剝標籤
            ps = [x for x in re.split(r"\n{2,}", _plain(t))
                  if len(x) >= 40 and not any(k in x for k in _NOISE)]
        return "\n\n".join(ps)[:limit]
    except Exception:
        return ""


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
        for title, link, summary, d, img in rows:
            if not title or not link:
                continue
            if name in ("Hermes", "ComfyUI") and ("/ru/" in link or "/zh/" in link):
                continue                        # GitHub release 的翻譯頁
            items.append({
                "source": name, "cat": cat, "title": title, "link": link,
                "summary": summary, "img": img,
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

    # 日文標題翻中文：只翻含假名的（20 條左右），整批一次呼叫，快取命中就 0 成本。
    # ⚠ 必須排在 rank() 之前：rank 回傳的是複製品，先翻再排才不會只翻到 items。
    try:
        import translate as translate_mod
        n_tr = translate_mod.translate_items(uniq, os.path.join(a.out, "translate_cache.json"))
        if n_tr:
            print(f"[translate] {n_tr} 條日文標題已翻", file=sys.stderr)
    except Exception as e:
        print(f"[translate] failed: {type(e).__name__}: {e}", file=sys.stderr)

    # 評分與每日精選（純規則，零 token）。每輪都重算——評分規則會改，即使新聞沒變。
    picks, stats = uniq[:15], {}
    if rank_mod is not None:
        try:
            ranked = rank_mod.rank(uniq, limit=15)
            picks, stats = ranked["picks"], ranked["stats"]
        except Exception as e:
            print(f"[rank] failed: {type(e).__name__}: {e}", file=sys.stderr)

    # 頁內閱讀模式：只給精選抓正文（11 條約 3 秒）。link 沒變就吃快取，
    # 否則 cron 每 2 小時會把同樣那 11 頁重抓一次。
    cache_p = os.path.join(a.out, "article_cache.json")
    cache = {}
    if os.path.exists(cache_p):
        try:
            with open(cache_p, encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}
    fresh = 0
    for it in picks:
        lk = it.get("link", "")
        if lk in cache:
            it["full"] = cache[lk]
        else:
            it["full"] = article_text(lk)
            cache[lk] = it["full"]
            fresh += 1
    if fresh:
        if len(cache) > 400:                      # 快取別無限長
            keep = {x.get("link", "") for x in picks}
            cache = {k: v for k, v in cache.items() if k in keep}
        try:
            with open(cache_p, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False)
        except Exception:
            pass
        print(f"[reader] 新抓 {fresh} 篇正文", file=sys.stderr)

    # 內容沒變就不重寫（否則 generated_at 每次都變，git 每輪都留下一個空 commit）
    # picks 也算進「有沒有變」，因為評分規則改了就要更新。
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                old = json.load(f)
            sig = lambda ps: [(x.get("link"), x.get("zh")) for x in ps]
            if (old.get("items") == uniq
                    and sig(old.get("picks", [])) == sig(picks)
                    and all("full" in x for x in old.get("picks", []))
                    and old.get("cats") == [list(c) for c in CATS]):
                print(f"{len(uniq)} items, no change -> keep {p}")
                return 0
        except Exception:
            pass

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cats": CATS,
        "items": uniq,
        "picks": picks,
        "stats": stats,
    }
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, p)          # atomic: page never reads a half-written file

    print(f"{len(uniq)} items, {len(failed)} feed(s) failed -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

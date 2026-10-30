#!/usr/bin/env python3
"""把手挑的新聞加進新聞台（不是 RSS 抓的）。

用法：
    python add_curated.py --title "標題" --link "https://..." \
        --source "4Gamers" --cat game --summary "一兩句摘要" [--img https://...] [--ts 1793217640]

規則：
- 以 link 去重（同一個 link 已存在就更新內容，不新增）
- ts 預設現在；同一條新聞請用原始發布時間，這樣排序才正確
- 條目在 news_fetch.py 執行後併入 items/picks，14 天後自動淘汰
- 只寫 D:\\AI\\news\\curated.json，不碰 items.json（那是產出物）
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

OUT = r"D:\AI\news"
PATH = os.path.join(OUT, "curated.json")
CATS = {"game", "tech", "ai", "toy", "hype", "local", "image", "pipeline", "hermes"}


def load() -> list:
    if not os.path.exists(PATH):
        return []
    try:
        with open(PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save(items: list) -> None:
    os.makedirs(OUT, exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    os.replace(tmp, PATH)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", default="")
    ap.add_argument("--link", default="")
    ap.add_argument("--source", default="手挑")
    ap.add_argument("--cat", default="tech", choices=sorted(CATS))
    ap.add_argument("--summary", default="")
    ap.add_argument("--img", default="")
    ap.add_argument("--ts", type=int, default=0, help="原始發布時間（unix）")
    ap.add_argument("--list", action="store_true", help="列出目前所有手挑條目")
    ap.add_argument("--remove", metavar="LINK", default="", help="依 link 刪除")
    a = ap.parse_args()

    items = load()

    if a.list:
        for i, it in enumerate(items):
            d = datetime.fromtimestamp(it.get("ts", 0), timezone.utc).strftime("%Y-%m-%d %H:%M")
            print(f"{i}. [{it.get('cat')}] {d}Z ({it.get('source')}) {it.get('title')}")
            print(f"   {it.get('link')}")
        print(f"共 {len(items)} 條")
        return 0

    if a.remove:
        before = len(items)
        items = [x for x in items if x.get("link") != a.remove]
        save(items)
        print(f"移除 {before - len(items)} 條，剩 {len(items)}")
        return 0

    if not (a.title and a.link):
        print("需要 --title 和 --link", file=sys.stderr)
        return 2

    ts = a.ts or int(datetime.now(timezone.utc).timestamp())
    entry = {
        "title": a.title.strip(),
        "link": a.link.strip(),
        "source": a.source.strip() or "手挑",
        "cat": a.cat,
        "summary": a.summary.strip(),
        "img": a.img.strip(),
        "ts": ts,
        "date": datetime.fromtimestamp(ts).strftime("%m-%d %H:%M"),
    }

    for i, it in enumerate(items):
        if it.get("link") == entry["link"]:
            items[i] = entry
            save(items)
            print(f"已更新（同 link）→ 共 {len(items)} 條")
            return 0

    items.append(entry)
    save(items)
    print(f"已加入 → 共 {len(items)} 條。跑 python news_fetch.py 後會出現在新聞台。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

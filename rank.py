#!/usr/bin/env python3
"""rank.py — 評分、去重、每日精選。純規則，不呼叫任何模型，零 token。

設計依據（2026-10-26 三份研究）：
- Apple News：上層編輯精選 + 下層演算法 → 我們做「精選 picks」+「全部 all」
- SmartNews：寧可做「發現與多樣性」，不要假裝個人化（沒有行為數據時的誠實做法）
- Feedly：85% 重疊就當重複，跨來源
- 通用：新鮮度 3–4 天見頂、單一來源每日有份額上限、同主題不要連續三篇

他的判斷標準（實際訪談得到）：要中文、要「能行動」、不要版本號與企業 IT 新聞。
"""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import datetime, timezone

# ── 權重（沒有行為數據，所以不設 engage / personalization 項）──
W_FRESH = 1.0
W_SOURCE = 0.8
W_ACTION = 1.2      # 「能行動」是他的核心判準，權重最高
W_IMAGE = 0.5
W_NOISE = 1.5       # 噪音類直接扣

# 來源可信度（依目前訂閱的來源）。英文來源刻意低於中文，因為他要的是中文。
SOURCE_TRUST = {
    "4Gamers": 0.9,
    "巴哈 GNN": 0.85,
    "INSIDE": 0.85,
    "iThome": 0.85,
    "Unwire HK": 0.8,
    "SoyaCincau": 0.55,   # 英文，但本地（馬來西亞）消息仍是硬需求
    "Lowyat": 0.6,        # 英文，本地科技論壇
    "Hermes": 0.95,
    "ComfyUI": 0.9,
    "mlllm": 0.7,
    # 2026-10-26 第二輪
    "電腦玩物": 0.85,      # 中文 AI 工具教學，他點名「AI 工具中文說明」
    "電腦王阿達": 0.75,    # 消費電子＋優惠，但業配多
    "愛范兒": 0.8,
    "科技新報": 0.75,
    "Hobby Japan": 0.62,  # 日文，價值在發售日與價格（他讀不懂，靠數字和圖）
    "電撃Hobby": 0.62,
    "Hypebeast": 0.5,     # 炒賣／限量／聯名（中文）；但 8 成是球鞋時裝，不是他的收藏範圍
    "ToyArk": 0.6,        # 英文玩具新聞
}
DEFAULT_TRUST = 0.5
RELEASE_SOURCES = {"Hermes", "ComfyUI"}

# 「能行動」的詞：買得到、下載得到、該避開、價格變了
ACTION_WORDS = [
    # 買賣 / 價格
    "發售", "開賣", "預購", "上市", "特價", "優惠", "降價", "折扣", "清倉",
    "到貨", "收購", "二手", "漲價", "停售", "跳水", "下殺", "限時",
    # 能拿到手
    "釋出", "推出", "更新", "新增", "支援", "開放", "下載", "免費", "限免",
    "開源", "發布", "上線",
    # 收藏 / 實體
    "限定", "復刻", "再版", "絕版", "週邊", "模型", "公仔", "聯名", "開箱", "評測",
    # 該避開
    "漏洞", "警告", "停止", "終止", "召回", "下架", "災情", "風險",
    # 炒賣／轉賣市場（他要的「炒賣物」那一類）
    "炒價", "炒貴", "炒起", "溢價", "抽選", "抽籤", "現貨", "掃貨", "斷貨",
    "缺貨", "行情", "成交價", "翻倍", "受注", "預訂", "發售日", "入手",
]

# 純活動 / 社群噪音（沒有行動價值）
NOISE_WORDS = [
    "站聚", "抽獎", "投票", "徵稿", "報名", "徵才", "專訪", "座談", "直播",
    "市集", "板攤", "週年", "生日", "見面會", "得獎", "心得分享", "同人展",
]

TAU_HOURS = 24.0       # 新鮮度半衰（普通欄目）
TAU_HOURS_HOT = 6.0    # 重要欄目（Hermes / ComfyUI 這種會直接影響他的）
HOT_CATS = {"hermes", "pipeline"}
MAX_AGE_HOURS = 48     # 超過就不進「精選」
SOURCE_QUOTA = 3       # 單一來源每日精選上限
CAT_CAP = 4            # 同分類精選上限


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"\s+", "", s)


def _hours_old(ts: int, now: float) -> float:
    if not ts:
        return MAX_AGE_HOURS * 2      # 沒有時間 = 當很舊
    return max(0.0, (now - ts) / 3600.0)


def freshness(ts: int, cat: str, now: float) -> float:
    tau = TAU_HOURS_HOT if cat in HOT_CATS else TAU_HOURS
    return 2 ** (-_hours_old(ts, now) / tau)


def hits(text: str, words) -> int:
    t = _norm(text)
    return sum(1 for w in words if _norm(w) in t)


VERSION_RE = re.compile(r"^v?\d+(\.\d+)+")


def score(item: dict, now: float) -> float:
    """0–1 分數。沒有行為數據，所以只用內容本身能判斷的東西。"""
    title = item.get("title") or ""
    summary = item.get("summary") or ""
    cat = item.get("cat") or ""

    # release note 不是新聞：Hermes / ComfyUI 的版本號留在「全部」，不進精選。
    if item.get("source") in RELEASE_SOURCES and re.search(r"\bv?\d+\.\d+", title):
        return 0.05
    if VERSION_RE.match(title.strip()) and len(title) < 48:
        return 0.05

    fresh = freshness(item.get("ts") or 0, cat, now)
    src = SOURCE_TRUST.get(item.get("source") or "", DEFAULT_TRUST)

    # 「能行動」：標題命中權重高於摘要
    act = min(3.0, hits(title, ACTION_WORDS) * 1.5 + hits(summary, ACTION_WORDS) * 0.4) / 3.0
    noise_n = hits(title, NOISE_WORDS) + hits(summary, NOISE_WORDS) * 0.5
    noise = min(2.0, noise_n) / 2.0
    img = 1.0 if item.get("img") else 0.0

    # 標題太短通常是標籤或活動公告
    tlen = len(title)
    len_factor = 1.0 if 12 <= tlen <= 80 else (0.6 if tlen < 12 else 0.85)

    raw = (W_FRESH * fresh + W_SOURCE * src + W_ACTION * act
           + W_IMAGE * img - W_NOISE * noise) * len_factor
    ceiling = W_FRESH + W_SOURCE + W_ACTION + W_IMAGE
    s = max(0.0, min(1.0, raw / ceiling))

    # 活動／社群類：命中越多砍越重（「限定商品」「首賣」不該救活一篇站聚報導）
    if noise_n >= 2:
        s *= 0.25
    elif noise_n >= 1:
        s *= 0.6
    return s


def _title_tokens(title: str) -> set:
    """中文：用二字切片（bigram）當 token；英文：用單字。夠用且不用斷詞器。"""
    s = _norm(title)
    toks = set(re.findall(r"[a-z0-9]{2,}", s))
    zh = re.sub(r"[a-z0-9\s\W]", "", s)
    toks |= {zh[i:i + 2] for i in range(len(zh) - 1)}
    return toks


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def dedupe(items: list[dict]) -> list[dict]:
    """標題相似度 >= 0.85 視為同一則，保留分數最高的那篇。
    門檻刻意保守：寧可留兩篇相關的，也不要誤殺不同事件。"""
    toks = [_title_tokens(i.get("title") or "") for i in items]
    keep = []
    for idx, item in enumerate(items):
        dup = False
        for kept_idx in keep:
            if jaccard(toks[idx], toks[kept_idx]) >= 0.85:
                dup = True
                break
        if not dup:
            keep.append(idx)
    return [items[i] for i in keep]


def select(items: list[dict], now: float, limit: int = 15) -> tuple[list[dict], list[dict]]:
    """回傳 (picks, rest)。picks 是「今天該知道的」，rest 是其餘（給「顯示更多」）。

    刪除順序照研究建議：時間過期 → 去重 → 低分 → 主題飽和 → 來源份額。
    """
    scored = []
    for it in items:
        s = score(it, now)
        scored.append({**it, "score": round(s * 100)})
    scored.sort(key=lambda x: -x["score"])

    alive = [it for it in scored if _hours_old(it.get("ts") or 0, now) <= MAX_AGE_HOURS * 2]
    alive = dedupe(alive)

    picks, cat_count, src_count = [], {}, {}
    for it in alive:
        if len(picks) >= limit:
            break
        cat = it.get("cat") or ""
        src = it.get("source") or ""
        if it["score"] < 20:      # 只濾掉真正的噪音（站聚、版本號）
            continue
        if src_count.get(src, 0) >= SOURCE_QUOTA:
            continue
        if cat_count.get(cat, 0) >= CAT_CAP:
            continue
        picks.append(it)
        cat_count[cat] = cat_count.get(cat, 0) + 1
        src_count[src] = src_count.get(src, 0) + 1

    picked_ids = {id(x) for x in picks}
    rest = [it for it in scored if id(it) not in picked_ids]
    return picks, rest


def rank(items: list[dict], limit: int = 15) -> dict:
    now = datetime.now(timezone.utc).timestamp()
    picks, rest = select(items, now, limit)
    return {
        "picks": picks,
        "rest": rest,
        "stats": {
            "total": len(items),
            "picks": len(picks),
            "dropped_old": sum(1 for i in items if _hours_old(i.get("ts") or 0, now) > MAX_AGE_HOURS * 2),
        },
    }

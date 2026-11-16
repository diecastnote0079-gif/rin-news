import json

obj = json.loads(open('items.json', encoding='utf-8').read())
items = obj['items']

# (index, one-line headline)  headline <= 25 chars
sel = [
    (0,  "超長對話插件：100K 視窗即可跑數十億 token"),
    (2,  "開源 Grok Bot 替代 機器人自帶虛擬機"),
    (5,  "Anthropic 開源 Agent Skills 公共倉庫 技能可模組化"),
    (7,  "Google 開源 Agent Skills 倉庫 技能可模組化"),
    (9,  "Cloudflare 開源安全稽核 agent 技能 多階段跑"),
    (10, "Vercel 開源 agent 瀏覽器自動化 CLI"),
    (111, "工程師圈討論：我仍不信 AI 泡沫存在"),
    (116, "AI 腦炸怎麼自救：個人防禦筆記"),
    (130, "64GB RAM 跑 284B DeepSeek 模型 不用 GPU"),
    (138, "AI 代理記憶 急需開放標準 像 OpenTelemetry"),
    (149, "再見 Claude，迎接 Pi：AI 助理路線之爭"),
    (20,  "美中卡關拖 H200 銷中 供應鏈 時間軸"),
    (21,  "搶寶可夢卡 6 歲女兒獨留店外過夜 父被捕"),
    (24,  "ReFantazio 11/12 登 Switch 2 原平台數位版降價"),
    (42,  "免費開源瀏覽器翻譯插件 LLM 本地跑 免註冊"),
    (44,  "開源 FAH 模型 單卡 101fps 實時估手"),
    (48,  "Grok Bot 降智 Ultra 級別 變慢 Token 減 4 倍"),
    (51,  "馬來西亞 加快量子抗性通訊 與軍方電訊商合作"),
    (55,  "法學教授 AI 助教把一年講義刪掉"),
    (68,  "Google 台灣推 Gemini 中文 購物 自動比價"),
    (85,  "每天寫信提醒 OpenAI 執行長 有閒置 RAM"),
    (88,  "PS5 藍牙喇叭 PULSE Elevate 延期 發售日未定"),
    (107, "高盛收回 Claude Code 程式碼代理 金融業考驗"),
    (117, "歐洲超市血庫冰箱大駭 靠預設密碼"),
    (132, "AI 駭客能力 9 個月 35% 升 95% 漏洞成 exploit"),
    (161, "一批 NVIDIA 硬體失蹤 運中 值 1140 萬"),
    (220, "Realme 11.11 促 最高 55 折 手機從 RM499"),
    (226, "塞爾達 時之笛 完全重製版 11/10 發售"),
    (234, "GTA 6 預購破 771 萬套 75% 來自 PS5 玩家"),
]

missing = [i for i, _ in sel if not items[i].get('link')]
assert not missing, missing

feed = [items[i]['link'] for i, _ in sel]
notes = {items[i]['link']: t for i, t in sel}

with open('feed.json', 'w', encoding='utf-8') as f:
    json.dump(feed, f, ensure_ascii=False, indent=1)
with open('notes.json', 'w', encoding='utf-8') as f:
    json.dump(notes, f, ensure_ascii=False, indent=1)

# verify
assert len(feed) == len(set(feed)) == len(notes)
for k, v in notes.items():
    assert len(v) <= 25, (k, len(v))
print("total:", len(feed))
print("AI/dev:", sum(1 for i, _ in sel if items[i]['source'] in ('Hacker News', 'arXiv', 'GitHub Trending')))
print("done")

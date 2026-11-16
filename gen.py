import json

obj = json.loads(open('items.json', encoding='utf-8').read())
items = obj['items']

sel = [
    (0,  "壓縮長對話 100K 視窗跑數十億 token"),
    (2,  "開源 Grok Bot 代替 機器人自帶虛擬機"),
    (5,  "開源 Agent Skills 公共倉庫 技能可模組"),
    (7,  "Google 開源 Skills 倉庫 技能可模組"),
    (9,  "Cloudflare 開源安全稽核技能"),
    (10, "Vercel 開源 agent 瀏覽器自動化"),
    (111, "工程師圈討論：我仍不信 AI 泡沫存在"),
    (116, "AI 腦炸怎麼自救：個人防禦筆記"),
    (130, "64GB RAM 跑 284B 模型 不用 GPU"),
    (138, "AI 代理記憶 急需開放標準 像 OTel"),
    (149, "再見 Claude，迎接 Pi 路線之爭"),
    (20,  "美中卡關拖 H200 銷中 供應鏈 時間軸"),
    (21,  "搶寶可夢卡 6 歲女兒獨留店外過夜 父被捕"),
    (24,  "暗喻幻想 11/12 登 Switch 2 數位降價"),
    (42,  "免費開源瀏覽器翻譯插件 LLM 本地跑 免註冊"),
    (44,  "開源 FAH 模型 單卡 101fps 實時估手"),
    (48,  "Grok Bot 降智 變慢 Token 減4倍"),
    (51,  "馬來西亞 加快量子抗性通訊 與軍方電訊商合作"),
    (55,  "法學教授 AI 助教把一年講義刪掉"),
    (68,  "Google 台灣推 Gemini 中文 比價"),
    (85,  "每天寫信提醒 OpenAI 執行長 有閒置 RAM"),
    (88,  "PS5 藍牙喇叭 PULSE Elevate 延期"),
    (107, "高盛收回 Claude Code 程式碼代理"),
    (117, "歐洲超市血庫冰箱大駭 靠預設密碼"),
    (132, "AI 駭客 9 個月 35%→95% 漏洞成"),
    (161, "NVIDIA 硬體失蹤 值 1140 萬"),
    (220, "Realme 11.11 55 折 從 RM499"),
    (226, "塞爾達 時之笛 完全重製版 11/10 發售"),
    (234, "GTA 6 預購 771 萬 75% 靠 PS5"),
]

# sanity: length of each headline <= 25
for i, t in sel:
    assert len(t) <= 25, (i, len(t), t)

feed = [items[i]['link'] for i, _ in sel]
notes = {items[i]['link']: t for i, _ in sel}

with open('feed.json', 'w', encoding='utf-8') as f:
    json.dump(feed, f, ensure_ascii=False, indent=1)
with open('notes.json', 'w', encoding='utf-8') as f:
    json.dump(notes, f, ensure_ascii=False, indent=1)

print("total:", len(feed))
print("AI/dev:", sum(1 for i, _ in sel if items[i]['source'] in ('Hacker News', 'arXiv', 'GitHub Trending')))
print("engine/others:", sum(1 for i, _ in sel if items[i]['source'] not in ('Hacker News', 'arXiv', 'GitHub Trending')))

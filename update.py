#!/usr/bin/env python3
"""update.py — refresh items.json and publish. NO LLM, NO TOKENS.

Pipeline:  news_fetch.py  ->  git commit items.json  ->  git push
Only commits when items.json actually changed, so an empty cycle costs nothing.

Run by:    cron job (no_agent=true)
Manual:    python update.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
GIT_USER = ["-c", "user.name=Rin-news", "-c", "user.email=news@local"]
REPO_SLUG = "diecastnote0079-gif/rin-news"
def _hermes_env() -> str:
    r"""Windows: %LOCALAPPDATA%\hermes\.env · Linux/macOS: $HERMES_HOME/.env"""
    if os.name == "nt":
        la = os.environ.get("LOCALAPPDATA")
        if la:
            return os.path.join(la, "hermes", ".env")
    home = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
    return os.path.join(home, ".env")


HERMES_ENV = _hermes_env()


def github_token() -> str | None:
    """Read the token from Hermes' .env. Never printed, never written to .git/config."""
    try:
        with open(HERMES_ENV, encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.strip().startswith("GITHUB_TOKEN"):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return os.environ.get("GITHUB_TOKEN")


def sh(args, check=False):
    r = subprocess.run(args, cwd=HERE, capture_output=True, text=True, timeout=420)
    msg = (r.stdout + r.stderr).strip()
    return r.returncode, msg.replace(os.environ.get("_PUSH_SECRET", "\0"), "***")


def main() -> int:
    # 1) fetch
    code, out = sh([PY, os.path.join(HERE, "news_fetch.py")], )
    print(out)
    if code != 0:
        print("fetch failed; page keeps previous data")
        return 0            # not an error: last data stays live

    # 1b) 狀態頁的健康資料（實跑 doctor + runs 表；失敗不影響新聞）
    try:
        code, out = sh([PY, os.path.expanduser("~/.hermes/scripts/build_health.py")])
        print("health:", (out or "").strip())
    except Exception as e:
        print("health build skipped:", e)

    # 1a-2) notes.json 守門：curate 模型偶爾把所有 link 寫成同一句（2026-11-09 實際發生，
    # 前端每一列都顯示同一個標題）。重複率過高就整個作廢，退回 items 的 zh／原標題。
    try:
        np = os.path.join(HERE, "notes.json")
        if os.path.exists(np):
            import json as _json
            with open(np, encoding="utf-8") as _f:
                _n = _json.load(_f)
            if isinstance(_n, dict) and len(_n) >= 5:
                vals = list(_n.values())
                top = max(vals.count(v) for v in set(vals))
                if top / len(vals) > 0.5:
                    with open(np, "w", encoding="utf-8") as _f:
                        _json.dump({}, _f, ensure_ascii=False)
                    print(f"notes.json 異常（{top}/{len(vals)} 條重複），已清空退回原標題")
    except Exception as e:
        print("notes guard skipped:", e)

    # 1a-3) notes2.json：index.html 讀這個名字（CDN 會把 notes.json 快取住，
    # 2026-11-09 因此推不動修正）。每次同步寫一份。
    try:
        _src = os.path.join(HERE, "notes.json")
        if os.path.exists(_src):
            import shutil as _sh
            _sh.copyfile(_src, os.path.join(HERE, "notes2.json"))
    except Exception as e:
        print("notes2 copy skipped:", e)

    # 2) anything to publish?
    if not os.path.isdir(os.path.join(HERE, ".git")):
        print("no git repo here; done (local only)")
        return 0
    code, diff = sh(["git", "status", "--porcelain", "items.json", "feed.json", "notes.json", "notices.json", "status.json", "digest.json", "health.json", "game-news.json"])
    if not diff.strip():
        print("items.json unchanged; nothing to publish")
        return 0

    # 3) commit + push
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    sh(["git", "add", "items.json"])
    for extra in ("feed.json", "notes.json", "notes2.json", "notices.json", "status.json", "digest.json", "health.json", "game-news.json"):
        if os.path.exists(os.path.join(HERE, extra)):
            sh(["git", "add", extra])
    code, out = sh(["git", *GIT_USER, "commit", "-m", f"items: {stamp}"])
    print("commit:", out.splitlines()[0] if out else code)

    tok = github_token()
    if not tok:
        print("push skipped: no GITHUB_TOKEN")
        return 1
    os.environ["_PUSH_SECRET"] = tok
    url = f"https://x-access-token:{tok}@github.com/{REPO_SLUG}.git"
    code, out = sh(["git", "-c", "credential.helper=", "push", url, "HEAD:main"])
    os.environ.pop("_PUSH_SECRET", None)
    print("push:", out.splitlines()[-1] if out else code)
    return 0 if code == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

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
HERMES_ENV = os.path.expanduser("~/AppData/Local/hermes/.env")


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
    r = subprocess.run(args, cwd=HERE, capture_output=True, text=True, timeout=180)
    msg = (r.stdout + r.stderr).strip()
    return r.returncode, msg.replace(os.environ.get("_PUSH_SECRET", "\0"), "***")


def main() -> int:
    # 1) fetch
    code, out = sh([PY, os.path.join(HERE, "news_fetch.py")], )
    print(out)
    if code != 0:
        print("fetch failed; page keeps previous data")
        return 0            # not an error: last data stays live

    # 2) anything to publish?
    if not os.path.isdir(os.path.join(HERE, ".git")):
        print("no git repo here; done (local only)")
        return 0
    code, diff = sh(["git", "status", "--porcelain", "items.json"])
    if not diff.strip():
        print("items.json unchanged; nothing to publish")
        return 0

    # 3) commit + push
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    sh(["git", "add", "items.json"])
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

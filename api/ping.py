"""Self-contained runtime probe for Vercel (no project imports).

Answers: which python, whether the ``app`` package shipped into the
function bundle, and which environment variables are visible. Used to
diagnose cold-start failures; safe to keep (read-only facts).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI

app = FastAPI()


@app.get("/api/ping")
async def ping() -> dict:
    cwd = Path.cwd()
    try:
        entries = sorted(item.name for item in cwd.iterdir())[:60]
    except OSError:
        entries = ["<unreadable>"]
    return {
        "ok": "pong",
        "cwd": str(cwd),
        "python": sys.version.split()[0],
        "has_app_dir": (cwd / "app").is_dir(),
        "has_api_dir": (cwd / "api").is_dir(),
        "entries": entries,
        "sys_path_head": sys.path[:5],
        "vercel_env": os.getenv("VERCEL", ""),
        "bot_token_set": bool(os.getenv("BOT_TOKEN")),
        "postgres_set": bool(os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL")),
    }

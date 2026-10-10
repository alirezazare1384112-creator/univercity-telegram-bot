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


# Vercel invokes this module as ``/api/index/ping`` (the platform always
# prefixes non-root files with ``/api/index``). Declare the bare path too so
# the handler matches whatever scope the platform hands us.
@app.get("/ping")
@app.get("/api/ping")
@app.get("/api/index/ping")
async def ping() -> dict:
    cwd = Path.cwd()
    try:
        entries = sorted(item.name for item in cwd.iterdir())[:60]
    except OSError:
        entries = ["<unreadable>"]

    # Check the database schema for the photo_url column and how many users
    # have it set. This runs on every ping call but is cheap (two tiny
    # queries) and invaluable for diagnosing "profile photo not showing".
    db_info: dict = {}
    db_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or ""
    if db_url:
        try:
            import asyncpg

            # asyncpg wants postgresql:// not postgresql+asyncpg://
            clean = db_url
            for prefix in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
                if clean.startswith(prefix):
                    clean = "postgresql://" + clean[len(prefix):]
                    break
            conn = await asyncpg.connect(clean, ssl="require")
            try:
                col = await conn.fetchval(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='users' AND column_name='photo_url'"
                )
                db_info["users_has_photo_url"] = bool(col)
                if col:
                    total = await conn.fetchval("SELECT count(*) FROM users")
                    with_photo = await conn.fetchval(
                        "SELECT count(*) FROM users WHERE photo_url IS NOT NULL"
                    )
                    db_info["users_total"] = total
                    db_info["users_with_photo"] = with_photo
                cols = await conn.fetch(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='university_links' "
                    "AND column_name IN ('ciphertext_b64','wrapped_key_b64')"
                )
                db_info["links_has_cred_columns"] = len(cols)
            finally:
                await conn.close()
        except Exception as exc:  # noqa: BLE001
            db_info["db_error"] = f"{type(exc).__name__}: {exc}"[:200]

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
        "postgres_set": bool(db_url),
        "credentials_enabled": bool(os.getenv("CREDENTIALS_MASTER_KEY")),
        "db": db_info,
    }

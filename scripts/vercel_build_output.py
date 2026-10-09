"""Emit Vercel Build Output API layout for the Python function + SPA.

Vercel's `functions`/`rewrites` cannot express "all /api/* except ping"
on backend-framework projects without the SPA rewrite shadowing the
function. The Build Output API gives explicit routes:

  /api/ping               -> api/ping.py (self-contained probe)
  /api/((?!ping).*)       -> api/index.py (FastAPI app, path-normalized)
  filesystem              -> public/index.html + assets from the CDN
  (/.*)                   -> index.html SPA fallback
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / ".vercel" / "output"


def _run(cmd: list[str]) -> None:
    subprocess.check_call(cmd, cwd=ROOT)


def main() -> int:
    # 1. Build the Mini App
    _run(["npm", "install"])
    _run(["npm", "run", "build"])

    # 2. Stage the Python function bundle
    fn = OUT / "functions" / "api" / "index.py"
    fn.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "api" / "index.py", fn)
    shutil.copy2(ROOT / "api" / "ping.py", fn.with_name("ping.py"))
    # ship the app package so `from app...` resolves at runtime
    app_dest = OUT / "functions" / "api" / "app"
    shutil.copytree(ROOT / "app", app_dest, dirs_exist_ok=True)
    # alembic migrations (schema bootstrap still uses Base.metadata)
    shutil.copy2(ROOT / "alembic.ini", OUT / "functions" / "api" / "alembic.ini")
    migrations = OUT / "functions" / "api" / "migrations"
    if (ROOT / "migrations").is_dir():
        shutil.copytree(ROOT / "migrations", migrations, dirs_exist_ok=True)

    # 3. Stage static files (SPA)
    static = OUT / "static"
    if static.exists():
        shutil.rmtree(static)
    shutil.copytree(ROOT / "frontend" / "dist", static)

    # 4. Routes
    (OUT / "config.json").write_text(
        json.dumps(
            {
                "version": 3,
                "routes": [
                    {"src": "/api/ping", "dest": "/api/ping.py"},
                    {"src": "/api/((?!ping).*)", "dest": "/api/index.py"},
                    {"handle": "filesystem"},
                    {"src": "/(.*)", "dest": "/index.html"},
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("Build Output API layout written to .vercel/output")
    return 0


if __name__ == "__main__":
    sys.exit(main())

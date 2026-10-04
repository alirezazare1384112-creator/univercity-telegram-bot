"""Project entry point.

Usage:
    python run.py            # start the Telegram bot (needs BOT_TOKEN)
    python run.py --check    # local environment check, no Telegram needed
"""

from __future__ import annotations

import asyncio
import sys


def main() -> int:
    if "--check" in sys.argv:
        from app.main import healthcheck

        return asyncio.run(healthcheck())

    from app.main import run_bot

    run_bot()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

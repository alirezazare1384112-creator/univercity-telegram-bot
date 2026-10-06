"""Project entry point.

Usage:
    python run.py            # start the bot + Mini App API (needs BOT_TOKEN)
    python run.py --bot      # start only the Telegram bot (no HTTP API)
    python run.py --check    # local environment check, no Telegram needed
"""

from __future__ import annotations

import asyncio
import sys


def main() -> int:
    if "--check" in sys.argv:
        from app.main import healthcheck

        return asyncio.run(healthcheck())

    from app.main import run_bot, run_services

    if "--bot" in sys.argv:
        run_bot()
    else:
        run_services()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

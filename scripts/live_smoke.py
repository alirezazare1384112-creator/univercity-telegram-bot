"""Live smoke test for the running bot + Mini App (outbound checks only).

Run from the project root:

    py -3.13 scripts/live_smoke.py             # health/auth/API/static checks
    py -3.13 scripts/live_smoke.py --reminder   # + one real reminder round-trip

The optional reminder check creates a reminder ~45 s from now for the owner
account, waits until the scheduler really delivers it to Telegram, then
deletes it again. Exit code 0 means every executed check passed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx
from sqlalchemy import select

from app.config import get_settings
from app.database.database import get_session
from app.database.models.reminder import ReminderNotification
from app.utils.datetime_utils import utc_to_local, utcnow_naive
from tests.conftest import sign_init_data

OWNER_ID = 7501219056
LOCAL = "http://127.0.0.1:8000"
HEADER = "X-Telegram-Init-Data"

results: list[tuple[str, bool, str]] = []


def record(label: str, ok: bool, detail: str = "") -> None:
    results.append((label, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  [{detail}]" if detail else ""))


def auth_headers() -> dict[str, str]:
    fields = {
        "user": json.dumps({"id": OWNER_ID, "first_name": "Smoke"}, ensure_ascii=False),
        "auth_date": str(int(time.time())),
        "query_id": "live-smoke",
    }
    return {HEADER: sign_init_data(fields)}


async def expect_list(client: httpx.AsyncClient, path: str) -> None:
    response = await client.get(f"{LOCAL}{path}", headers=auth_headers())
    ok = response.status_code == 200 and isinstance(response.json(), list)
    record(f"GET {path} -> list", ok, f"{response.status_code}")


async def run_checks(tunnel: str) -> None:
    async with httpx.AsyncClient(trust_env=False, timeout=30) as client:
        home = await client.get(f"{tunnel}/")
        record(
            "tunnel serves the SPA shell",
            home.status_code == 200 and '<div id="root">' in home.text,
            f"{home.status_code}",
        )

        health = await client.get(f"{tunnel}/api/health")
        record(
            "tunnel /api/health",
            health.status_code == 200 and health.json().get("status") == "ok",
            f"{health.status_code}",
        )

        record(
            "hardening headers through the tunnel",
            home.headers.get("X-Content-Type-Options") == "nosniff"
            and home.headers.get("Referrer-Policy") == "no-referrer",
        )

        unknown = await client.get(f"{tunnel}/api/does-not-exist")
        record(
            "unknown API path stays JSON 404",
            unknown.status_code == 404
            and unknown.headers.get("content-type", "").startswith("application/json"),
            f"{unknown.status_code}",
        )

        me = await client.get(f"{LOCAL}/api/me", headers=auth_headers())
        body = me.json() if me.status_code == 200 else {}
        record(
            "signed initData -> /api/me",
            me.status_code == 200 and body.get("telegram_id") == OWNER_ID,
            f"{me.status_code}, is_admin={body.get('is_admin')}",
        )

        forged = await client.get(
            f"{LOCAL}/api/me", headers={HEADER: "hash=deadbeef&auth_date=1&user=%7B%7D"}
        )
        record("forged initData rejected", forged.status_code == 401, f"{forged.status_code}")

        dash = await client.get(f"{LOCAL}/api/dashboard", headers=auth_headers())
        record("GET /api/dashboard", dash.status_code == 200, f"{dash.status_code}")

        for path in (
            "/api/courses",
            "/api/notes",
            "/api/calendar",
            "/api/reminders",
            "/api/announcements",
            "/api/links",
        ):
            await expect_list(client, path)

        schedule = await client.get(f"{LOCAL}/api/schedule", headers=auth_headers())
        record(
            "GET /api/schedule",
            schedule.status_code in (200, 404),
            f"{schedule.status_code} (404 = no schedule uploaded)",
        )

        stats = await client.get(f"{LOCAL}/api/admin/stats", headers=auth_headers())
        record("GET /api/admin/stats", stats.status_code == 200, f"{stats.status_code}")

        users = await client.get(f"{LOCAL}/api/admin/users", headers=auth_headers())
        total = users.json().get("total") if users.status_code == 200 else 0
        record(
            "GET /api/admin/users",
            users.status_code == 200 and total >= 1,
            f"{users.status_code}, total={total}",
        )


async def reminder_round_trip(client: httpx.AsyncClient) -> None:
    settings = get_settings()
    fire_local = utc_to_local(utcnow_naive(), settings.timezone) + timedelta(seconds=45)
    created = await client.post(
        f"{LOCAL}/api/reminders",
        headers=auth_headers(),
        json={
            "title": "یادآوری تست دود (خودکار حذف می‌شود)",
            "local_datetime": fire_local.isoformat(timespec="seconds"),
            "alert_offsets": ["AT_TIME"],
        },
    )
    if created.status_code != 200:
        record("create live reminder", False, f"{created.status_code}: {created.text[:120]}")
        return
    reminder_id = created.json()["id"]
    record("create live reminder", True, f"id={reminder_id}, fires at {fire_local:%H:%M:%S}")

    try:
        sent = False
        last_state = "no rows yet"
        for _ in range(24):  # up to ~2 min: 45 s until due + 30 s poll interval
            await asyncio.sleep(5)
            async with get_session() as session:
                rows = (
                    await session.execute(
                        select(ReminderNotification).where(
                            ReminderNotification.reminder_id == reminder_id
                        )
                    )
                ).scalars().all()
            if rows:
                last_state = ", ".join(
                    f"{row.alert_offset}@{row.fire_datetime:%H:%M:%S} sent={row.is_sent}"
                    for row in rows
                )
                if all(row.is_sent for row in rows):
                    sent = True
                    break
        record(
            "scheduler delivered the reminder to Telegram",
            sent,
            last_state if not sent else "",
        )
        if not sent:
            from app.database.models.notification import NotificationLog

            async with get_session() as session:
                logs = (
                    await session.execute(
                        select(NotificationLog)
                        .where(NotificationLog.related_id == reminder_id)
                        .order_by(NotificationLog.id)
                    )
                ).scalars().all()
            if logs:
                print(
                    "      notification log: "
                    + "; ".join(f"{row.status}/{row.error_message}" for row in logs)
                )
    finally:
        deleted = await client.delete(
            f"{LOCAL}/api/reminders/{reminder_id}", headers=auth_headers()
        )
        record("cleanup: reminder deleted", deleted.status_code == 200, f"{deleted.status_code}")


async def main() -> int:
    parser = argparse.ArgumentParser(description="live smoke test")
    parser.add_argument("--reminder", action="store_true", help="also test real reminder delivery")
    args = parser.parse_args()

    settings = get_settings()
    tunnel = settings.webapp_url.rstrip("/")
    if not tunnel.startswith("https://"):
        print("WEBAPP_URL is not an https tunnel - set it first.")
        return 2

    print(f"tunnel: {tunnel}")
    await run_checks(tunnel)

    if args.reminder:
        async with httpx.AsyncClient(trust_env=False, timeout=30) as client:
            await reminder_round_trip(client)

    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

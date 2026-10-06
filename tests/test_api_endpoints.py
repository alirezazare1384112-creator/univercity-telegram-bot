"""Mini App endpoints: /api/health and /api/dashboard (no network)."""

from __future__ import annotations

import json
import time
from datetime import timedelta

from app.api.auth import INIT_DATA_HEADER
from app.config import get_settings
from app.database.models import CalendarEvent, Course, Reminder
from app.database.repositories.user_repository import UserRepository
from app.utils.datetime_utils import utc_to_local, utcnow_naive
from tests.conftest import sign_init_data


def _headers(*, user_id: int = 111, first_name: str = "سارا") -> dict[str, str]:
    fields = {
        "user": json.dumps(
            {"id": user_id, "first_name": first_name, "username": f"u{user_id}"},
            ensure_ascii=False,
        ),
        "auth_date": str(int(time.time())),
        "query_id": "AAF-test",
    }
    return {INIT_DATA_HEADER: sign_init_data(fields)}


async def test_health_is_public(api_client):
    response = await api_client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_dashboard_requires_authentication(api_client):
    response = await api_client.get("/api/dashboard")
    assert response.status_code == 401


async def test_dashboard_counts_and_user_isolation(api_client, db):
    settings = get_settings()
    today = utc_to_local(utcnow_naive(), settings.timezone).date()
    now_utc = utcnow_naive()

    async with db() as session:
        owner, _ = await UserRepository(session).get_or_create_from_telegram(
            telegram_id=111, username="u111", first_name="سارا", last_name=None
        )
        session.add_all(
            [
                Course(user_id=owner.id, name="ریاضی"),
                Course(user_id=owner.id, name="فیزیک"),
                CalendarEvent(user_id=owner.id, title="کنفرانس", event_date=today),
                CalendarEvent(user_id=owner.id, title="دیروز", event_date=today - timedelta(days=1)),
                Reminder(
                    user_id=owner.id,
                    title="سریع‌ترین",
                    reminder_datetime=now_utc + timedelta(hours=2),
                ),
                Reminder(
                    user_id=owner.id,
                    title="کند",
                    reminder_datetime=now_utc + timedelta(hours=5),
                ),
                Reminder(
                    user_id=owner.id,
                    title="گذشته",
                    reminder_datetime=now_utc - timedelta(hours=2),
                ),
            ]
        )
        await session.commit()

    response = await api_client.get("/api/dashboard", headers=_headers())
    assert response.status_code == 200
    data = response.json()
    assert data["user"]["telegram_id"] == 111
    assert data["counts"]["courses"] == 2
    assert data["counts"]["events_today"] == 1
    assert data["counts"]["reminders"] == 3
    assert data["counts"]["announcements"] == 0
    assert data["counts"]["notes"] == 0
    assert data["schedule"] is False
    assert data["next_reminder"]["title"] == "سریع‌ترین"
    assert "/" in data["today"]

    # A different Telegram account sees only its own (empty) data.
    other = await api_client.get("/api/dashboard", headers=_headers(user_id=222))
    assert other.status_code == 200
    other_data = other.json()
    assert other_data["user"]["telegram_id"] == 222
    assert other_data["counts"]["courses"] == 0
    assert other_data["counts"]["events_today"] == 0
    assert other_data["counts"]["reminders"] == 0
    assert other_data["next_reminder"] is None

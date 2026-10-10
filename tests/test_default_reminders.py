"""Tests for the default reminder auto-provisioning feature."""

from __future__ import annotations

import json
import time

import pytest
from sqlalchemy import select

from app.api.auth import INIT_DATA_HEADER
from app.config import reset_settings_cache
from app.database.models import Reminder
from app.database.repositories.reminder_repository import (
    ReminderNotificationRepository,
    ReminderRepository,
)
from app.services.reminder_service import ensure_default_reminders
from tests.conftest import sign_init_data


def _headers(*, user_id: int = 111) -> dict[str, str]:
    fields = {
        "user": json.dumps(
            {"id": user_id, "first_name": "سارا", "username": f"u{user_id}"},
            ensure_ascii=False,
        ),
        "auth_date": str(int(time.time())),
        "query_id": "AAF-test",
    }
    return {INIT_DATA_HEADER: sign_init_data(fields)}


@pytest.fixture(autouse=True)
def _enable_default_reminders(monkeypatch):
    """Enable the feature for this module (conftest disables it globally)."""
    monkeypatch.setenv("DEFAULT_REMINDERS_ENABLED", "true")
    reset_settings_cache()
    yield
    monkeypatch.setenv("DEFAULT_REMINDERS_ENABLED", "false")
    reset_settings_cache()


async def test_default_reminder_created_on_first_login(api_client, db):
    """First Mini App login creates the food reservation reminder."""
    response = await api_client.get("/api/me", headers=_headers())
    assert response.status_code == 200

    # The reminder should exist in the database
    async with db() as session:
        repo = ReminderRepository(session)
        reminders = await repo.list_by_user(1, active_only=False)
    titles = [r.title for r in reminders]
    assert "رزرو غذا" in titles

    # The created reminder should be daily + active
    food = next(r for r in reminders if r.title == "رزرو غذا")
    assert food.repeat_type == "DAILY"
    assert food.is_active is True


async def test_default_reminder_has_pending_notification(api_client, db):
    """The created reminder must have a pending fire_datetime."""
    await api_client.get("/api/me", headers=_headers())

    async with db() as session:
        repo = ReminderRepository(session)
        reminders = await repo.list_by_user(1)
        assert len(reminders) == 1
        notif_repo = ReminderNotificationRepository(session)
        pending = await notif_repo.pending_for_reminder(reminders[0].id)
    assert len(pending) == 1
    assert pending[0].alert_offset == "AT_TIME"
    assert pending[0].is_sent is False


async def test_second_login_does_not_duplicate(api_client, db):
    """Second login must not create a second food reminder."""
    await api_client.get("/api/me", headers=_headers())
    await api_client.get("/api/me", headers=_headers())

    async with db() as session:
        repo = ReminderRepository(session)
        reminders = await repo.list_by_user(1, active_only=False)
    food_count = sum(1 for r in reminders if r.title == "رزرو غذا")
    assert food_count == 1


async def test_paused_default_reminder_stays_paused(api_client, db):
    """If the user pauses the default reminder, it stays paused (not re-activated)."""
    # First login creates it
    await api_client.get("/api/me", headers=_headers())
    async with db() as session:
        repo = ReminderRepository(session)
        reminders = await repo.list_by_user(1)
        assert len(reminders) == 1
        # Pause it (set is_active=False) instead of deleting
        await repo.update(reminders[0], is_active=False)
        await session.commit()

    # Second login should NOT re-activate the paused reminder
    await api_client.get("/api/me", headers=_headers())
    async with db() as session:
        repo = ReminderRepository(session)
        reminders = await repo.list_by_user(1, active_only=False)
    # The reminder still exists (ensure_default_reminders found it by title)
    food = [r for r in reminders if r.title == "رزرو غذا"]
    assert len(food) == 1
    # And it stays paused
    assert food[0].is_active is False


async def test_reminder_visible_in_reminders_api(api_client):
    """The default reminder shows up in GET /api/reminders."""
    await api_client.get("/api/me", headers=_headers())
    response = await api_client.get("/api/reminders", headers=_headers())
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["title"] == "رزرو غذا"
    assert data[0]["repeat_type"] == "DAILY"
    assert data[0]["is_active"] is True


async def test_ensure_default_reminders_idempotent_direct(db):
    """Calling ensure_default_reminders twice directly does not duplicate."""
    from app.database.repositories import UserRepository

    # Create a user first (FK constraint requires it)
    async with db() as session:
        user, _ = await UserRepository(session).get_or_create_from_telegram(
            telegram_id=999, username="test", first_name="Test", last_name=None
        )
        await session.commit()
        user_id = user.id

    async with db() as session:
        await ensure_default_reminders(session, user_id, "Asia/Tehran")
        await session.commit()

    async with db() as session:
        await ensure_default_reminders(session, user_id, "Asia/Tehran")
        await session.commit()
        result = await session.execute(
            select(Reminder).where(
                Reminder.user_id == user_id, Reminder.title == "رزرو غذا"
            )
        )
        count = len(result.scalars().all())
    assert count == 1

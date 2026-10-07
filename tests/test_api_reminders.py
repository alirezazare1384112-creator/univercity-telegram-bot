"""/api/reminders tests: create with alerts, timezone round trip, pause, isolation."""

from __future__ import annotations

import json
import time

from app.api.auth import INIT_DATA_HEADER
from app.database.database import get_session
from app.database.repositories.reminder_repository import ReminderNotificationRepository
from tests.conftest import sign_init_data

_FUTURE = "2026-12-01T09:30"


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


def _payload(**overrides) -> dict:
    payload = {"title": "کنفرانس دانشکده", "local_datetime": _FUTURE}
    payload.update(overrides)
    return payload


async def _create(client, *, user_id: int = 111, **overrides) -> dict:
    response = await client.post(
        "/api/reminders", headers=_headers(user_id=user_id), json=_payload(**overrides)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_reminders_start_empty_and_require_auth(api_client):
    response = await api_client.get("/api/reminders", headers=_headers())
    assert response.status_code == 200
    assert response.json() == []
    assert (await api_client.get("/api/reminders")).status_code == 401
    assert (
        await api_client.post("/api/reminders", json=_payload())
    ).status_code == 401
    assert (await api_client.delete("/api/reminders/1")).status_code == 401


async def test_create_returns_local_time_display_and_default_alert(api_client):
    body = await _create(api_client)
    assert body["title"] == "کنفرانس دانشکده"
    assert body["local_datetime"].startswith("2026-12-01T09:30")
    assert "ساعت 09:30" in body["display"]
    assert body["repeat_type"] == "NONE"
    assert body["repeat_label"] == "بدون تکرار"
    assert body["alert_offsets"] == ["AT_TIME"]
    assert body["is_active"] is True
    assert body["course_name"] is None


async def test_create_builds_pending_alerts(api_client):
    created = await _create(api_client, alert_offsets=["AT_TIME", "DAYS_1"])
    async with get_session() as session:
        rows = await ReminderNotificationRepository(session).list_for_reminder(
            created["id"]
        )
    assert {row.alert_offset for row in rows} == {"AT_TIME", "DAYS_1"}
    assert all(not row.is_sent for row in rows)


async def test_bad_alert_offsets_and_repeat_are_422(api_client):
    bad_offset = await api_client.post(
        "/api/reminders", headers=_headers(), json=_payload(alert_offsets=["WHEN"])
    )
    assert bad_offset.status_code == 422

    empty = await api_client.post(
        "/api/reminders", headers=_headers(), json=_payload(alert_offsets=[])
    )
    assert empty.status_code == 422

    bad_repeat = await api_client.post(
        "/api/reminders", headers=_headers(), json=_payload(repeat_type="HOURLY")
    )
    assert bad_repeat.status_code == 422


async def test_reminder_shows_its_course_name(api_client):
    course = await api_client.post(
        "/api/courses", headers=_headers(), json={"name": "آمار", "units": 3}
    )
    body = await _create(api_client, course_id=course.json()["id"])
    assert body["course_name"] == "آمار"


async def test_upload_to_a_foreign_course_is_404(api_client):
    foreign = await api_client.post(
        "/api/courses", headers=_headers(user_id=222), json={"name": "دیگران", "units": 3}
    )
    response = await api_client.post(
        "/api/reminders",
        headers=_headers(user_id=111),
        json=_payload(course_id=foreign.json()["id"]),
    )
    assert response.status_code == 404


async def test_pause_moves_a_reminder_out_of_the_active_list(api_client):
    created = await _create(api_client)
    paused = await api_client.put(
        f"/api/reminders/{created['id']}",
        headers=_headers(),
        json=_payload(is_active=False),
    )
    assert paused.status_code == 200
    assert paused.json()["is_active"] is False

    active = await api_client.get(
        "/api/reminders", headers=_headers(), params={"active_only": "true"}
    )
    assert active.json() == []
    everything = await api_client.get("/api/reminders", headers=_headers())
    assert len(everything.json()) == 1


async def test_update_changes_title_and_datetime(api_client):
    created = await _create(api_client)
    response = await api_client.put(
        f"/api/reminders/{created['id']}",
        headers=_headers(),
        json=_payload(title="عنوان تازه", local_datetime="2026-12-02T18:45"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "عنوان تازه"
    assert body["local_datetime"].startswith("2026-12-02T18:45")
    assert "18:45" in body["display"]


async def test_delete_removes_the_reminder_and_its_alerts(api_client):
    created = await _create(api_client)
    deleted = await api_client.delete(
        f"/api/reminders/{created['id']}", headers=_headers()
    )
    assert deleted.status_code == 200

    async with get_session() as session:
        rows = await ReminderNotificationRepository(session).list_for_reminder(
            created["id"]
        )
    assert rows == []
    assert (await api_client.get("/api/reminders", headers=_headers())).json() == []
    again = await api_client.delete(f"/api/reminders/{created['id']}", headers=_headers())
    assert again.status_code == 404


async def test_users_can_touch_only_their_own_reminders(api_client):
    created = await _create(api_client, user_id=111)
    stranger = _headers(user_id=222)
    assert (await api_client.get("/api/reminders", headers=stranger)).json() == []
    assert (
        await api_client.put(
            f"/api/reminders/{created['id']}", headers=stranger, json=_payload()
        )
    ).status_code == 404
    assert (
        await api_client.delete(f"/api/reminders/{created['id']}", headers=stranger)
    ).status_code == 404


async def test_blank_title_is_422(api_client):
    response = await api_client.post(
        "/api/reminders", headers=_headers(), json=_payload(title="   ")
    )
    assert response.status_code == 422

"""/api/calendar tests: create/list/update (incl. done toggle)/delete/isolation."""

from __future__ import annotations

import json
import time

import httpx
import pytest_asyncio

from app.api import create_api
from app.api.auth import INIT_DATA_HEADER
from tests.conftest import sign_init_data


@pytest_asyncio.fixture
async def calendar_client(db):
    app = create_api(None)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


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


async def _create(client, *, user_id: int = 111, **overrides) -> dict:
    payload = {"title": "امتحان ریاضی", "event_date": "2026-10-20"}
    payload.update(overrides)
    response = await client.post("/api/calendar", headers=_headers(user_id=user_id), json=payload)
    assert response.status_code == 200, response.text
    return response.json()


async def test_calendar_starts_empty_and_requires_auth(calendar_client):
    response = await calendar_client.get("/api/calendar", headers=_headers())
    assert response.status_code == 200
    assert response.json() == []
    assert (await calendar_client.get("/api/calendar")).status_code == 401
    assert (await calendar_client.delete("/api/calendar/1")).status_code == 401


async def test_create_all_day_event_shows_a_jalali_label(calendar_client):
    body = await _create(calendar_client, description="  ")
    assert body["title"] == "امتحان ریاضی"
    assert body["event_date"] == "2026-10-20"
    assert body["event_time"] is None
    assert body["is_done"] is False
    assert body["description"] is None
    assert "/" in body["date_label"] and "(" in body["date_label"]


async def test_create_event_with_a_time(calendar_client):
    body = await _create(calendar_client, title="جلسهٔ گروه", event_time="14:30")
    assert body["event_time"] == "14:30"


async def test_pending_list_is_ordered_soonest_first(calendar_client):
    await _create(calendar_client, title="خیلی دور", event_date="2027-01-01")
    await _create(calendar_client, title="گذشته", event_date="2026-01-01")
    await _create(calendar_client, title="نزدیک", event_date="2026-11-01")

    titles = [e["title"] for e in (await calendar_client.get("/api/calendar", headers=_headers())).json()]
    assert titles == ["گذشته", "نزدیک", "خیلی دور"]


async def test_done_toggle_moves_between_tabs(calendar_client):
    event = await _create(calendar_client)
    toggled = await calendar_client.put(
        f"/api/calendar/{event['id']}",
        headers=_headers(),
        json={
            "title": event["title"],
            "event_date": event["event_date"],
            "event_time": None,
            "description": None,
            "is_done": True,
        },
    )
    assert toggled.status_code == 200
    assert toggled.json()["is_done"] is True

    pending = await calendar_client.get("/api/calendar", headers=_headers())
    assert pending.json() == []
    done = await calendar_client.get("/api/calendar", headers=_headers(), params={"done": "true"})
    assert [e["title"] for e in done.json()] == ["امتحان ریاضی"]


async def test_update_edits_title_date_and_clears_time(calendar_client):
    event = await _create(calendar_client, event_time="09:00")
    response = await calendar_client.put(
        f"/api/calendar/{event['id']}",
        headers=_headers(),
        json={"title": "عنوان تازه", "event_date": "2026-12-24", "event_time": None},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "عنوان تازه"
    assert body["event_date"] == "2026-12-24"
    assert body["event_time"] is None


async def test_delete_removes_the_event(calendar_client):
    event = await _create(calendar_client)
    deleted = await calendar_client.delete(f"/api/calendar/{event['id']}", headers=_headers())
    assert deleted.status_code == 200
    assert (await calendar_client.get("/api/calendar", headers=_headers())).json() == []
    again = await calendar_client.delete(f"/api/calendar/{event['id']}", headers=_headers())
    assert again.status_code == 404


async def test_users_can_touch_only_their_own_events(calendar_client):
    event = await _create(calendar_client, user_id=111)
    stranger = _headers(user_id=222)
    assert (await calendar_client.get("/api/calendar", headers=stranger)).json() == []
    assert (
        await calendar_client.put(
            f"/api/calendar/{event['id']}",
            headers=stranger,
            json={"title": "x", "event_date": "2026-10-20"},
        )
    ).status_code == 404
    assert (
        await calendar_client.delete(f"/api/calendar/{event['id']}", headers=stranger)
    ).status_code == 404


async def test_invalid_title_and_date_are_422(calendar_client):
    blank = await calendar_client.post(
        "/api/calendar", headers=_headers(), json={"title": "   ", "event_date": "2026-10-20"}
    )
    assert blank.status_code == 422

    far_past = await calendar_client.post(
        "/api/calendar", headers=_headers(), json={"title": "x", "event_date": "1999-01-01"}
    )
    assert far_past.status_code == 422

    garbage = await calendar_client.post(
        "/api/calendar", headers=_headers(), json={"title": "x", "event_date": "فردا"}
    )
    assert garbage.status_code == 422

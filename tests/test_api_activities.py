"""/api/activities tests: create/list/update/delete/isolation/validation."""

from __future__ import annotations

import json
import time

import httpx
import pytest_asyncio

from app.api import create_api
from app.api.auth import INIT_DATA_HEADER
from tests.conftest import sign_init_data


@pytest_asyncio.fixture
async def activities_client(db):
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
    payload = {
        "title": "مطالعه ریاضی",
        "day_of_week": 1,  # Saturday
        "start_time": "14:00",
        "duration_hours": 1.5,
        "category": "STUDY",
    }
    payload.update(overrides)
    response = await client.post(
        "/api/activities", headers=_headers(user_id=user_id), json=payload
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_activities_start_empty_and_require_auth(activities_client):
    response = await activities_client.get("/api/activities", headers=_headers())
    assert response.status_code == 200
    assert response.json() == []
    assert (await activities_client.get("/api/activities")).status_code == 401
    assert (await activities_client.delete("/api/activities/1")).status_code == 401


async def test_create_activity_returns_full_payload(activities_client):
    body = await _create(activities_client, description="  ")
    assert body["title"] == "مطالعه ریاضی"
    assert body["day_of_week"] == 1
    assert body["start_time"] == "14:00"
    assert body["duration_hours"] == 1.5
    assert body["category"] == "STUDY"
    assert body["is_active"] is True
    assert body["description"] is None


async def test_list_orders_by_day_then_start_time(activities_client):
    # Friday (7) morning, Saturday (1) evening, Saturday (1) morning
    await _create(
        activities_client,
        title="جمعه صبح",
        day_of_week=7,
        start_time="08:00",
    )
    await _create(
        activities_client,
        title="شنبه شب",
        day_of_week=1,
        start_time="20:00",
    )
    await _create(
        activities_client,
        title="شنبه صبح",
        day_of_week=1,
        start_time="08:00",
    )

    titles = [
        a["title"]
        for a in (
            await activities_client.get("/api/activities", headers=_headers())
        ).json()
    ]
    assert titles == ["شنبه صبح", "شنبه شب", "جمعه صبح"]


async def test_update_changes_title_and_duration(activities_client):
    activity = await _create(activities_client)
    response = await activities_client.put(
        f"/api/activities/{activity['id']}",
        headers=_headers(),
        json={
            "title": "ورزش صبحگاهی",
            "day_of_week": 2,
            "start_time": "07:00",
            "duration_hours": 2.0,
            "category": "SPORT",
            "is_active": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "ورزش صبحگاهی"
    assert body["day_of_week"] == 2
    assert body["duration_hours"] == 2.0
    assert body["category"] == "SPORT"
    assert body["is_active"] is False


async def test_delete_removes_activity(activities_client):
    activity = await _create(activities_client)
    deleted = await activities_client.delete(
        f"/api/activities/{activity['id']}", headers=_headers()
    )
    assert deleted.status_code == 200
    assert (
        await activities_client.get("/api/activities", headers=_headers())
    ).json() == []
    again = await activities_client.delete(
        f"/api/activities/{activity['id']}", headers=_headers()
    )
    assert again.status_code == 404


async def test_users_can_touch_only_their_own_activities(activities_client):
    activity = await _create(activities_client, user_id=111)
    stranger = _headers(user_id=222)
    assert (
        await activities_client.get("/api/activities", headers=stranger)
    ).json() == []
    assert (
        await activities_client.put(
            f"/api/activities/{activity['id']}",
            headers=stranger,
            json={
                "title": "x",
                "day_of_week": 1,
                "start_time": "10:00",
                "duration_hours": 1.0,
            },
        )
    ).status_code == 404
    assert (
        await activities_client.delete(
            f"/api/activities/{activity['id']}", headers=stranger
        )
    ).status_code == 404


async def test_invalid_day_duration_and_category_are_422(activities_client):
    bad_day = await activities_client.post(
        "/api/activities",
        headers=_headers(),
        json={
            "title": "x",
            "day_of_week": 9,
            "start_time": "10:00",
            "duration_hours": 1.0,
        },
    )
    assert bad_day.status_code == 422

    bad_duration = await activities_client.post(
        "/api/activities",
        headers=_headers(),
        json={
            "title": "x",
            "day_of_week": 1,
            "start_time": "10:00",
            "duration_hours": 0,
        },
    )
    assert bad_duration.status_code == 422

    bad_category = await activities_client.post(
        "/api/activities",
        headers=_headers(),
        json={
            "title": "x",
            "day_of_week": 1,
            "start_time": "10:00",
            "duration_hours": 1.0,
            "category": "PARTY",
        },
    )
    assert bad_category.status_code == 422

    blank_title = await activities_client.post(
        "/api/activities",
        headers=_headers(),
        json={
            "title": "   ",
            "day_of_week": 1,
            "start_time": "10:00",
            "duration_hours": 1.0,
        },
    )
    assert blank_title.status_code == 422

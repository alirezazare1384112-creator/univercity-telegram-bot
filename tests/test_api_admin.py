"""/api/admin tests: admin-only gate, stats totals and the user list."""

from __future__ import annotations

import json
import time

from app.api.auth import INIT_DATA_HEADER
from app.database.database import get_session
from app.database.repositories.admin_repository import AdminRepository
from tests.conftest import sign_init_data


def _headers(*, user_id: int = 111) -> dict[str, str]:
    fields = {
        "user": json.dumps(
            {"id": user_id, "first_name": "مدیر", "username": f"u{user_id}"},
            ensure_ascii=False,
        ),
        "auth_date": str(int(time.time())),
        "query_id": "AAF-admin",
    }
    return {INIT_DATA_HEADER: sign_init_data(fields)}


async def _make_admin(telegram_id: int = 111) -> None:
    async with get_session() as session:
        await AdminRepository(session).upsert(
            telegram_id=telegram_id, username=None, first_name="ادمین"
        )


async def test_admin_endpoints_require_auth(api_client):
    for path in ("/api/admin/stats", "/api/admin/users"):
        response = await api_client.get(path)
        assert response.status_code == 401, path


async def test_regular_users_get_403(api_client):
    await api_client.get("/api/me", headers=_headers())  # ensure the user exists
    for path in ("/api/admin/stats", "/api/admin/users"):
        response = await api_client.get(path, headers=_headers())
        assert response.status_code == 403, path


async def test_me_reports_admin_flag(api_client):
    before = await api_client.get("/api/me", headers=_headers())
    assert before.status_code == 200
    assert before.json()["is_admin"] is False

    await _make_admin()
    after = await api_client.get("/api/me", headers=_headers())
    assert after.json()["is_admin"] is True


async def test_stats_counts_totals(api_client):
    await _make_admin()
    await api_client.post(
        "/api/links",
        headers=_headers(),
        json={"title": "لینک", "url": "https://ut.ac.ir"},
    )
    response = await api_client.get("/api/admin/stats", headers=_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["users"] == 1
    assert body["active_users"] == 1
    assert body["admins"] == 1
    assert body["links"] == 1
    assert body["courses"] == 0
    assert body["announcements"] == 0
    assert set(body) == {
        "users", "active_users", "admins", "courses", "grades", "reminders",
        "announcements", "notes", "links", "events", "schedules",
    }


async def test_users_list_shape(api_client):
    await _make_admin()
    await api_client.get("/api/me", headers=_headers(user_id=111))
    await api_client.get("/api/me", headers=_headers(user_id=222))

    response = await api_client.get("/api/admin/users", headers=_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["active"] == 2
    assert len(body["users"]) == 2
    first = body["users"][0]
    assert first["telegram_id"] in (111, 222)
    assert set(first) == {
        "id", "telegram_id", "username", "first_name", "last_name", "is_active",
    }


async def test_users_list_limit_and_validation(api_client):
    await _make_admin()
    await api_client.get("/api/me", headers=_headers(user_id=111))
    await api_client.get("/api/me", headers=_headers(user_id=222))

    response = await api_client.get(
        "/api/admin/users", params={"limit": 1}, headers=_headers()
    )
    body = response.json()
    assert len(body["users"]) == 1
    assert body["total"] == 2

    assert (
        await api_client.get(
            "/api/admin/users", params={"limit": 0}, headers=_headers()
        )
    ).status_code == 422
    assert (
        await api_client.get(
            "/api/admin/users", params={"limit": 500}, headers=_headers()
        )
    ).status_code == 422


async def test_config_admin_ids_are_accepted(api_client, monkeypatch):
    from app.config import reset_settings_cache

    monkeypatch.setenv("ADMIN_IDS", "111")
    reset_settings_cache()
    try:
        response = await api_client.get("/api/admin/stats", headers=_headers())
        assert response.status_code == 200
        assert response.json()["users"] >= 1
    finally:
        monkeypatch.setenv("ADMIN_IDS", "")
        reset_settings_cache()

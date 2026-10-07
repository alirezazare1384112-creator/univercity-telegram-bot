"""/api/links tests: CRUD with http(s)-only URLs and isolation."""

from __future__ import annotations

import json
import time

from app.api.auth import INIT_DATA_HEADER
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


def _payload(**overrides) -> dict:
    payload = {"title": "آموزش یکپارچه", "url": "https://ums.ut.ac.ir"}
    payload.update(overrides)
    return payload


async def _create(client, *, user_id: int = 111, **overrides) -> dict:
    response = await client.post(
        "/api/links", headers=_headers(user_id=user_id), json=_payload(**overrides)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_links_start_empty_and_require_auth(api_client):
    response = await api_client.get("/api/links", headers=_headers())
    assert response.status_code == 200
    assert response.json() == []
    assert (await api_client.get("/api/links")).status_code == 401
    assert (await api_client.post("/api/links", json=_payload())).status_code == 401
    assert (await api_client.delete("/api/links/1")).status_code == 401


async def test_create_and_list_link(api_client):
    body = await _create(api_client, description="  پورتال دانشجویی  ")
    assert body["title"] == "آموزش یکپارچه"
    assert body["url"] == "https://ums.ut.ac.ir"
    assert body["description"] == "پورتال دانشجویی"
    listed = await api_client.get("/api/links", headers=_headers())
    assert len(listed.json()) == 1


async def test_non_http_urls_and_blank_titles_are_422(api_client):
    for bad_url in ("javascript:alert(1)", "ftp://x", "example.com", ""):
        response = await api_client.post(
            "/api/links", headers=_headers(), json=_payload(url=bad_url)
        )
        assert response.status_code == 422, bad_url

    blank = await api_client.post(
        "/api/links", headers=_headers(), json=_payload(title="   ")
    )
    assert blank.status_code == 422

    long_title = await api_client.post(
        "/api/links", headers=_headers(), json=_payload(title="x" * 65)
    )
    assert long_title.status_code == 422


async def test_update_edits_title_and_url(api_client):
    created = await _create(api_client)
    response = await api_client.put(
        f"/api/links/{created['id']}",
        headers=_headers(),
        json={"title": "نمرات", "url": "http://classroom.ut.ac.ir"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "نمرات"
    assert body["url"] == "http://classroom.ut.ac.ir"


async def test_delete_removes_the_link(api_client):
    created = await _create(api_client)
    deleted = await api_client.delete(f"/api/links/{created['id']}", headers=_headers())
    assert deleted.status_code == 200
    assert (await api_client.get("/api/links", headers=_headers())).json() == []
    again = await api_client.delete(f"/api/links/{created['id']}", headers=_headers())
    assert again.status_code == 404


async def test_users_can_touch_only_their_own_links(api_client):
    created = await _create(api_client, user_id=111)
    stranger = _headers(user_id=222)
    assert (await api_client.get("/api/links", headers=stranger)).json() == []
    assert (
        await api_client.put(
            f"/api/links/{created['id']}", headers=stranger, json=_payload()
        )
    ).status_code == 404
    assert (
        await api_client.delete(f"/api/links/{created['id']}", headers=stranger)
    ).status_code == 404

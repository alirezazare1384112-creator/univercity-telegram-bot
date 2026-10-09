"""/api/links credentials tests: encrypted username/password storage."""

from __future__ import annotations

import base64
import json
import time

import pytest

from app.api.auth import INIT_DATA_HEADER
from app.config import reset_settings_cache
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
    payload = {"title": "تغذیه", "url": "https://food.ut.ac.ir"}
    payload.update(overrides)
    return payload


async def _create(client, **overrides) -> dict:
    response = await client.post(
        "/api/links", headers=_headers(), json=_payload(**overrides)
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(autouse=True)
def _master_key(monkeypatch):
    """Enable the credentials feature for every test in this module."""
    monkeypatch.setenv(
        "CREDENTIALS_MASTER_KEY",
        base64.urlsafe_b64encode(b"k" * 32).decode(),
    )
    reset_settings_cache()
    yield
    monkeypatch.delenv("CREDENTIALS_MASTER_KEY", raising=False)
    reset_settings_cache()


async def test_link_without_credentials_reports_false(api_client):
    body = await _create(api_client)
    assert body["has_credentials"] is False

    listed = (await api_client.get("/api/links", headers=_headers())).json()
    assert listed[0]["has_credentials"] is False


async def test_create_with_credentials_stores_encrypted(api_client):
    body = await _create(api_client, username="402123456", password="s3cret")
    assert body["has_credentials"] is True

    # Listing also reports has_credentials=True
    listed = (await api_client.get("/api/links", headers=_headers())).json()
    assert listed[0]["has_credentials"] is True


async def test_get_credentials_returns_plaintext(api_client):
    created = await _create(api_client, username="402123456", password="s3cret")
    response = await api_client.get(
        f"/api/links/{created['id']}/credentials", headers=_headers()
    )
    assert response.status_code == 200
    body = response.json()
    assert body["has_credentials"] is True
    assert body["username"] == "402123456"
    assert body["password"] == "s3cret"
    assert body["url"] == "https://food.ut.ac.ir"


async def test_get_credentials_for_link_without_them(api_client):
    created = await _create(api_client)
    response = await api_client.get(
        f"/api/links/{created['id']}/credentials", headers=_headers()
    )
    assert response.status_code == 200
    assert response.json() == {"has_credentials": False}


async def test_update_clears_credentials_when_username_password_null(api_client):
    created = await _create(api_client, username="402123456", password="s3cret")
    assert created["has_credentials"] is True

    # Update without credentials -> both should be cleared
    response = await api_client.put(
        f"/api/links/{created['id']}",
        headers=_headers(),
        json={"title": "تغذیه", "url": "https://food.ut.ac.ir"},
    )
    assert response.status_code == 200
    assert response.json()["has_credentials"] is False

    # Confirm the credentials endpoint also reports no credentials
    creds = await api_client.get(
        f"/api/links/{created['id']}/credentials", headers=_headers()
    )
    assert creds.json() == {"has_credentials": False}


async def test_update_replaces_credentials(api_client):
    created = await _create(api_client, username="old_user", password="old_pass")
    response = await api_client.put(
        f"/api/links/{created['id']}",
        headers=_headers(),
        json={
            "title": "تغذیه",
            "url": "https://food.ut.ac.ir",
            "username": "new_user",
            "password": "new_pass",
        },
    )
    assert response.status_code == 200

    creds = await api_client.get(
        f"/api/links/{created['id']}/credentials", headers=_headers()
    )
    assert creds.json()["username"] == "new_user"
    assert creds.json()["password"] == "new_pass"


async def test_username_without_password_is_422(api_client):
    response = await api_client.post(
        "/api/links",
        headers=_headers(),
        json=_payload(username="402123456"),  # no password
    )
    assert response.status_code == 422


async def test_password_without_username_is_422(api_client):
    response = await api_client.post(
        "/api/links",
        headers=_headers(),
        json=_payload(password="s3cret"),  # no username
    )
    assert response.status_code == 422


async def test_credentials_endpoint_is_user_scoped(api_client):
    """User A cannot read user B's credentials."""
    response_a = await api_client.post(
        "/api/links",
        headers=_headers(user_id=111),
        json=_payload(username="402123456", password="s3cret"),
    )
    assert response_a.status_code == 200
    link_id = response_a.json()["id"]

    stranger = _headers(user_id=222)
    response_b = await api_client.get(
        f"/api/links/{link_id}/credentials", headers=stranger
    )
    assert response_b.status_code == 404


async def test_credentials_disabled_when_no_master_key(api_client, monkeypatch):
    """When CREDENTIALS_MASTER_KEY is empty, writes are rejected with 503."""
    monkeypatch.delenv("CREDENTIALS_MASTER_KEY", raising=False)
    reset_settings_cache()

    response = await api_client.post(
        "/api/links",
        headers=_headers(),
        json=_payload(username="402123456", password="s3cret"),
    )
    assert response.status_code == 503

    # Reading is also rejected
    created = await _create(api_client)  # link without credentials, OK
    creds = await api_client.get(
        f"/api/links/{created['id']}/credentials", headers=_headers()
    )
    assert creds.status_code == 503


async def test_me_reports_credentials_enabled(api_client):
    response = await api_client.get("/api/me", headers=_headers())
    assert response.status_code == 200
    assert response.json()["credentials_enabled"] is True

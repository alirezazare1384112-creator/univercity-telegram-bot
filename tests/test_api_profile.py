"""/api/me PUT tests: profile round trip, digit normalization, clearing, limits."""

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


def _profile(**overrides) -> dict:
    payload = {
        "student_number": "402123456",
        "field_of_study": "مهندسی کامپیوتر",
        "university": "دانشگاه تهران",
        "semester": "1404-1",
        "bio": "دانشجوی ترم پنجم",
    }
    payload.update(overrides)
    return payload


async def test_put_updates_the_full_profile(api_client):
    response = await api_client.put("/api/me", headers=_headers(), json=_profile())
    assert response.status_code == 200, response.text

    me = (await api_client.get("/api/me", headers=_headers())).json()
    assert me["student_number"] == "402123456"
    assert me["field_of_study"] == "مهندسی کامپیوتر"
    assert me["university"] == "دانشگاه تهران"
    assert me["semester"] == "1404-1"
    assert me["bio"] == "دانشجوی ترم پنجم"


async def test_persian_digits_are_normalized(api_client):
    response = await api_client.put(
        "/api/me", headers=_headers(), json=_profile(student_number="۴۰۲۱۲۳۴۵۶")
    )
    assert response.status_code == 200
    assert response.json()["student_number"] == "402123456"


async def test_invalid_values_are_422(api_client):
    bad_number = await api_client.put(
        "/api/me", headers=_headers(), json=_profile(student_number="abc")
    )
    assert bad_number.status_code == 422

    long_bio = await api_client.put(
        "/api/me", headers=_headers(), json=_profile(bio="x" * 501)
    )
    assert long_bio.status_code == 422

    long_university = await api_client.put(
        "/api/me", headers=_headers(), json=_profile(university="x" * 129)
    )
    assert long_university.status_code == 422


async def test_empty_values_clear_the_fields(api_client):
    await api_client.put("/api/me", headers=_headers(), json=_profile())
    cleared = await api_client.put(
        "/api/me",
        headers=_headers(),
        json=_profile(
            student_number="",
            field_of_study="",
            university="",
            semester="",
            bio="   ",
        ),
    )
    assert cleared.status_code == 200
    body = cleared.json()
    assert body["student_number"] is None
    assert body["field_of_study"] is None
    assert body["university"] is None
    assert body["semester"] is None
    assert body["bio"] is None


async def test_whitespace_is_collapsed(api_client):
    response = await api_client.put(
        "/api/me", headers=_headers(), json=_profile(field_of_study="  مهندسی    برق  ")
    )
    assert response.status_code == 200
    assert response.json()["field_of_study"] == "مهندسی برق"


async def test_profile_requires_auth(api_client):
    assert (await api_client.get("/api/me")).status_code == 401
    assert (await api_client.put("/api/me", json=_profile())).status_code == 401

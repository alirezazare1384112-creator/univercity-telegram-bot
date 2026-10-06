"""/api/courses tests: CRUD, validation and per-user isolation."""

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
    payload = {
        "name": "ریاضی",
        "units": 3,
        "teacher_name": "دکتر محمدی",
        "semester": "پاییز",
        "academic_year": "1405",
    }
    payload.update(overrides)
    return payload


async def test_courses_start_empty(api_client):
    response = await api_client.get("/api/courses", headers=_headers())
    assert response.status_code == 200
    assert response.json() == []


async def test_create_course_and_list_it(api_client):
    created = await api_client.post(
        "/api/courses", headers=_headers(), json=_payload()
    )
    assert created.status_code == 200
    body = created.json()
    assert body["name"] == "ریاضی"
    assert body["units"] == 3

    listed = await api_client.get("/api/courses", headers=_headers())
    assert [c["id"] for c in listed.json()] == [body["id"]]


async def test_blank_name_is_rejected(api_client):
    response = await api_client.post(
        "/api/courses", headers=_headers(), json=_payload(name="   ")
    )
    assert response.status_code == 422


async def test_units_out_of_range_is_rejected(api_client):
    response = await api_client.post(
        "/api/courses", headers=_headers(), json=_payload(units=31)
    )
    assert response.status_code == 422


async def test_update_course(api_client):
    created = await api_client.post(
        "/api/courses", headers=_headers(), json=_payload()
    )
    course_id = created.json()["id"]

    updated = await api_client.put(
        f"/api/courses/{course_id}",
        headers=_headers(),
        json=_payload(name="فیزیک", units=2, teacher_name="", semester=None),
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "فیزیک"
    assert updated.json()["units"] == 2
    assert updated.json()["teacher_name"] is None


async def test_delete_course(api_client):
    created = await api_client.post(
        "/api/courses", headers=_headers(), json=_payload()
    )
    course_id = created.json()["id"]

    deleted = await api_client.delete(f"/api/courses/{course_id}", headers=_headers())
    assert deleted.status_code == 200

    again = await api_client.delete(f"/api/courses/{course_id}", headers=_headers())
    assert again.status_code == 404
    listed = await api_client.get("/api/courses", headers=_headers())
    assert listed.json() == []


async def test_other_users_course_is_invisible(api_client):
    created = await api_client.post(
        "/api/courses", headers=_headers(user_id=111), json=_payload()
    )
    course_id = created.json()["id"]

    stranger_list = await api_client.get("/api/courses", headers=_headers(user_id=222))
    assert stranger_list.json() == []

    stranger_get = await api_client.put(
        f"/api/courses/{course_id}",
        headers=_headers(user_id=222),
        json=_payload(name="هک"),
    )
    assert stranger_get.status_code == 404

    stranger_delete = await api_client.delete(
        f"/api/courses/{course_id}", headers=_headers(user_id=222)
    )
    assert stranger_delete.status_code == 404


async def test_courses_require_auth(api_client):
    assert (await api_client.get("/api/courses")).status_code == 401
    assert (
        await api_client.post("/api/courses", json=_payload())
    ).status_code == 401

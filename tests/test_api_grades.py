"""/api/courses/{id}/grades tests: CRUD, totals, validation, isolation."""

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


def _grade(**overrides) -> dict:
    payload = {"title": "میان‌ترم", "score": 15.0, "max_score": 20.0}
    payload.update(overrides)
    return payload


async def _new_course(api_client) -> int:
    response = await api_client.post(
        "/api/courses", headers=_headers(), json={"name": "ریاضی"}
    )
    assert response.status_code == 200
    return response.json()["id"]


async def test_grades_start_empty(api_client):
    course_id = await _new_course(api_client)
    response = await api_client.get(
        f"/api/courses/{course_id}/grades", headers=_headers()
    )
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["totals"] == {"total": 0.0, "maximum": 0.0, "percent": 0.0}


async def test_create_grade_updates_totals(api_client):
    course_id = await _new_course(api_client)
    first = await api_client.post(
        f"/api/courses/{course_id}/grades",
        headers=_headers(),
        json=_grade(title="میان‌ترم", score=15, max_score=20),
    )
    assert first.status_code == 200
    assert first.json()["kind"] == "OTHER"
    assert first.json()["percent"] == 75.0

    await api_client.post(
        f"/api/courses/{course_id}/grades",
        headers=_headers(),
        json=_grade(title="تمرین ۱", score=4, max_score=5, kind="HOMEWORK"),
    )
    body = (await api_client.get(f"/api/courses/{course_id}/grades", headers=_headers())).json()
    assert len(body["items"]) == 2
    assert body["totals"]["total"] == 19.0
    assert body["totals"]["maximum"] == 25.0
    assert body["totals"]["percent"] == 76.0


async def test_grade_validation(api_client):
    course_id = await _new_course(api_client)
    cases = [
        _grade(title="   "),
        _grade(score=25),
        _grade(score=-1),
        _grade(max_score=0),
        _grade(kind="SUPER"),
    ]
    for payload in cases:
        response = await api_client.post(
            f"/api/courses/{course_id}/grades", headers=_headers(), json=payload
        )
        assert response.status_code == 422, payload


async def test_update_grade_and_kind(api_client):
    course_id = await _new_course(api_client)
    created = await api_client.post(
        f"/api/courses/{course_id}/grades", headers=_headers(), json=_grade()
    )
    item_id = created.json()["id"]

    updated = await api_client.put(
        f"/api/courses/{course_id}/grades/{item_id}",
        headers=_headers(),
        json=_grade(title="پایان‌ترم", score=45, max_score=50, kind="FINAL"),
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "پایان‌ترم"
    assert updated.json()["kind"] == "FINAL"
    assert updated.json()["percent"] == 90.0


async def test_delete_grade(api_client):
    course_id = await _new_course(api_client)
    created = await api_client.post(
        f"/api/courses/{course_id}/grades", headers=_headers(), json=_grade()
    )
    item_id = created.json()["id"]

    deleted = await api_client.delete(
        f"/api/courses/{course_id}/grades/{item_id}", headers=_headers()
    )
    assert deleted.status_code == 200

    again = await api_client.delete(
        f"/api/courses/{course_id}/grades/{item_id}", headers=_headers()
    )
    assert again.status_code == 404


async def test_stranger_cannot_touch_the_grades(api_client):
    course_id = await _new_course(api_client)
    created = await api_client.post(
        f"/api/courses/{course_id}/grades", headers=_headers(), json=_grade()
    )
    item_id = created.json()["id"]

    stranger = _headers(user_id=222)
    read = await api_client.get(f"/api/courses/{course_id}/grades", headers=stranger)
    assert read.status_code == 404

    write = await api_client.post(
        f"/api/courses/{course_id}/grades", headers=stranger, json=_grade()
    )
    assert write.status_code == 404

    edit = await api_client.put(
        f"/api/courses/{course_id}/grades/{item_id}",
        headers=stranger,
        json=_grade(title="هک"),
    )
    assert edit.status_code == 404

    remove = await api_client.delete(
        f"/api/courses/{course_id}/grades/{item_id}", headers=stranger
    )
    assert remove.status_code == 404


async def test_grades_require_auth(api_client):
    assert (await api_client.get("/api/courses/1/grades")).status_code == 401
    assert (
        await api_client.post("/api/courses/1/grades", json=_grade())
    ).status_code == 401


# --- /api/grades summary (dashboard entry point) ------------------------


async def test_grades_summary_lists_every_course_with_totals(api_client):
    course_id = await _new_course(api_client)
    await api_client.post(
        f"/api/courses/{course_id}/grades",
        headers=_headers(),
        json=_grade(title="میان‌ترم", score=15, max_score=20),
    )
    await api_client.post(
        f"/api/courses/{course_id}/grades",
        headers=_headers(),
        json=_grade(title="تمرین ۱", score=4, max_score=5, kind="HOMEWORK"),
    )
    empty = await api_client.post(
        "/api/courses", headers=_headers(), json={"name": "فیزیک"}
    )
    empty_id = empty.json()["id"]

    response = await api_client.get("/api/grades", headers=_headers())
    assert response.status_code == 200
    body = response.json()

    assert body["item_count"] == 2
    assert body["totals"] == {"total": 19.0, "maximum": 25.0, "percent": 76.0}

    rows = {row["course_id"]: row for row in body["courses"]}
    assert rows[course_id]["name"] == "ریاضی"
    assert rows[course_id]["item_count"] == 2
    assert rows[course_id]["totals"] == {"total": 19.0, "maximum": 25.0, "percent": 76.0}
    assert rows[empty_id]["name"] == "فیزیک"
    assert rows[empty_id]["item_count"] == 0
    assert rows[empty_id]["totals"] == {"total": 0.0, "maximum": 0.0, "percent": 0.0}


async def test_grades_summary_is_scoped_to_user(api_client):
    await _new_course(api_client)  # user 111, no items
    stranger = _headers(user_id=222)
    other = await api_client.post(
        "/api/courses", headers=stranger, json={"name": "دیگری"}
    )
    await api_client.post(
        f"/api/courses/{other.json()['id']}/grades", headers=stranger, json=_grade()
    )

    response = await api_client.get("/api/grades", headers=_headers(user_id=111))
    body = response.json()
    assert body["item_count"] == 0
    assert body["totals"] == {"total": 0.0, "maximum": 0.0, "percent": 0.0}
    assert [row["name"] for row in body["courses"]] == ["ریاضی"]


async def test_grades_summary_requires_auth(api_client):
    assert (await api_client.get("/api/grades")).status_code == 401

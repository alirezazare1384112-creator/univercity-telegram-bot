"""/api/notes tests: upload via a fake bot, list/filter, edit, delete, isolation."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import httpx
import pytest_asyncio

from app.api import create_api
from app.api.auth import INIT_DATA_HEADER
from tests.conftest import sign_init_data
from tests.fake_bot import FakeBot

_PDF_BYTES = b"%PDF-1.4 fake-note"


@pytest_asyncio.fixture
async def fake_bot() -> FakeBot:
    return FakeBot(file_path="documents/lecture.pdf", payload=_PDF_BYTES)


@pytest_asyncio.fixture
async def notes_client(db, fake_bot):
    app = create_api(SimpleNamespace(bot=fake_bot))
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


async def _create_course(client, *, user_id: int = 111, name: str = "ریاضی") -> int:
    response = await client.post(
        "/api/courses",
        headers=_headers(user_id=user_id),
        json={"name": name, "units": 3},
    )
    assert response.status_code == 200
    return int(response.json()["id"])


async def _upload(client, *, user_id: int = 111, course_id: int | None = None, title: str = "جزوهٔ فصل ۱") -> httpx.Response:
    data = {"title": title}
    if course_id is not None:
        data["course_id"] = str(course_id)
    return await client.post(
        "/api/notes",
        headers=_headers(user_id=user_id),
        data=data,
        files={"file": ("lecture.pdf", _PDF_BYTES, "application/pdf")},
    )


async def test_notes_start_empty_and_require_auth(notes_client):
    response = await notes_client.get("/api/notes", headers=_headers())
    assert response.status_code == 200
    assert response.json() == []
    assert (await notes_client.get("/api/notes")).status_code == 401
    assert (await notes_client.delete("/api/notes/1")).status_code == 401


async def test_upload_document_is_sent_through_the_bot(notes_client, fake_bot):
    response = await _upload(notes_client)
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "جزوهٔ فصل ۱"
    assert body["file_type"] == "document"
    assert body["file_name"] == "lecture.pdf"
    assert body["course_id"] is None
    assert fake_bot.sent == [("document", 111)]
    assert fake_bot.deleted == [102]  # temporary message is cleaned up


async def test_upload_image_uses_send_photo(notes_client, fake_bot):
    response = await notes_client.post(
        "/api/notes",
        headers=_headers(),
        data={"title": "اسکن صفحه"},
        files={"file": ("scan.jpg", b"\xff\xd8jpeg", "image/jpeg")},
    )
    assert response.status_code == 200
    assert response.json()["file_type"] == "photo"
    assert fake_bot.sent == [("photo", 111)]


async def test_note_shows_its_course_name(notes_client):
    course_id = await _create_course(notes_client, name="فیزیک")
    response = await _upload(notes_client, course_id=course_id, title="جزوهٔ فیزیک")
    assert response.status_code == 200
    assert response.json()["course_name"] == "فیزیک"


async def test_course_filter_returns_only_matching_notes(notes_client):
    course_a = await _create_course(notes_client, name="شیمی")
    course_b = await _create_course(notes_client, name="آمار")
    await _upload(notes_client, course_id=course_a, title="نوت شیمی")
    await _upload(notes_client, course_id=course_b, title="نوت آمار")
    await _upload(notes_client, title="نوت آزاد")

    only_a = await notes_client.get("/api/notes", headers=_headers(), params={"course_id": course_a})
    assert [n["title"] for n in only_a.json()] == ["نوت شیمی"]
    without_course = await notes_client.get(
        "/api/notes", headers=_headers(), params={"course_id": 99999}
    )
    assert without_course.json() == []


async def test_upload_to_a_foreign_course_is_404(notes_client):
    their_course = await _create_course(notes_client, user_id=222)
    response = await _upload(notes_client, user_id=111, course_id=their_course)
    assert response.status_code == 404


async def test_served_file_comes_back_from_telegram(notes_client, fake_bot):
    created = await _upload(notes_client)
    note_id = created.json()["id"]
    response = await notes_client.get(f"/api/notes/{note_id}/file", headers=_headers())
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content == _PDF_BYTES
    assert fake_bot.get_file_calls == ["DOC-FILE-1"]


async def test_update_edits_title_description_and_course(notes_client):
    course_id = await _create_course(notes_client)
    created = await _upload(notes_client)
    note_id = created.json()["id"]

    response = await notes_client.put(
        f"/api/notes/{note_id}",
        headers=_headers(),
        json={"title": "عنوان تازه", "description": "  توضیح  ", "course_id": course_id},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "عنوان تازه"
    assert body["description"] == "توضیح"
    assert body["course_name"] == "ریاضی"


async def test_delete_removes_the_note(notes_client):
    created = await _upload(notes_client)
    note_id = created.json()["id"]
    deleted = await notes_client.delete(f"/api/notes/{note_id}", headers=_headers())
    assert deleted.status_code == 200
    assert (await notes_client.get("/api/notes", headers=_headers())).json() == []
    again = await notes_client.delete(f"/api/notes/{note_id}", headers=_headers())
    assert again.status_code == 404


async def test_users_can_touch_only_their_own_notes(notes_client):
    created = await _upload(notes_client, user_id=111)
    note_id = created.json()["id"]
    stranger = _headers(user_id=222)
    assert (await notes_client.get("/api/notes", headers=stranger)).json() == []
    assert (
        await notes_client.get(f"/api/notes/{note_id}/file", headers=stranger)
    ).status_code == 404
    assert (
        await notes_client.put(
            f"/api/notes/{note_id}", headers=stranger, json={"title": "x"}
        )
    ).status_code == 404
    assert (
        await notes_client.delete(f"/api/notes/{note_id}", headers=stranger)
    ).status_code == 404


async def test_empty_file_and_blank_title_are_rejected(notes_client):
    empty = await notes_client.post(
        "/api/notes",
        headers=_headers(),
        data={"title": "خالی"},
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert empty.status_code == 400

    blank = await notes_client.post(
        "/api/notes",
        headers=_headers(),
        data={"title": "   "},
        files={"file": ("x.pdf", _PDF_BYTES, "application/pdf")},
    )
    assert blank.status_code == 422


async def test_oversized_upload_is_rejected(notes_client, monkeypatch):
    from app.api import files as files_module

    monkeypatch.setattr(files_module, "MAX_FILE_BYTES", 8)
    response = await _upload(notes_client, title="بزرگ")
    assert response.status_code == 413


async def test_file_token_grants_headerless_download(notes_client, fake_bot):
    created = await _upload(notes_client)
    note_id = created.json()["id"]

    token_resp = await notes_client.post(
        f"/api/notes/{note_id}/file-token", headers=_headers()
    )
    assert token_resp.status_code == 200
    body = token_resp.json()
    assert body["media_type"] == "application/pdf"

    # <img>/<iframe> cannot attach headers: the signed URL alone must work.
    served = await notes_client.get(
        f"/api/notes/{note_id}/file", params={"t": body["token"]}
    )
    assert served.status_code == 200
    assert served.content == _PDF_BYTES
    assert served.headers["cache-control"] == "private, max-age=3600"
    assert served.headers["etag"]

    # Missing credentials are still rejected.
    assert (await notes_client.get(f"/api/notes/{note_id}/file")).status_code == 401

    # Photos report image/jpeg so the frontend picks the <img> renderer.
    image = await notes_client.post(
        "/api/notes",
        headers=_headers(),
        data={"title": "اسکن"},
        files={"file": ("scan.jpg", b"\xff\xd8jpeg", "image/jpeg")},
    )
    image_token = await notes_client.post(
        f"/api/notes/{image.json()['id']}/file-token", headers=_headers()
    )
    assert image_token.json()["media_type"] == "image/jpeg"


async def test_file_token_is_bound_to_one_note(notes_client):
    mine = (await _upload(notes_client, user_id=111)).json()["id"]
    theirs = (await _upload(notes_client, user_id=222)).json()["id"]
    token = (
        await notes_client.post(f"/api/notes/{mine}/file-token", headers=_headers())
    ).json()["token"]

    # The note id is inside the signature: this token opens no other file.
    crossed = await notes_client.get(
        f"/api/notes/{theirs}/file", params={"t": token}
    )
    assert crossed.status_code == 401


async def test_expired_file_token_is_rejected(notes_client):
    from app.api.auth import sign_file_token
    from app.config import get_settings

    note_id = (await _upload(notes_client)).json()["id"]
    expired = sign_file_token(
        111,
        note_id,
        int(time.time()) - 5,
        bot_token=get_settings().bot_token,
    )
    response = await notes_client.get(f"/api/notes/{note_id}/file", params={"t": expired})
    assert response.status_code == 401


async def test_etag_short_circuits_repeat_downloads(notes_client, fake_bot):
    note_id = (await _upload(notes_client)).json()["id"]
    first = await notes_client.get(f"/api/notes/{note_id}/file", headers=_headers())
    assert first.status_code == 200

    revalidated = await notes_client.get(
        f"/api/notes/{note_id}/file",
        headers={**_headers(), "If-None-Match": first.headers["etag"]},
    )
    assert revalidated.status_code == 304
    assert revalidated.headers["etag"] == first.headers["etag"]
    # Telegram was touched exactly once for the two requests.
    assert fake_bot.get_file_calls == ["DOC-FILE-1"]


async def test_large_pdf_is_served_without_gzip(db):
    big_pdf = b"%PDF-1.4 " + b"x" * 4000
    fake = FakeBot(file_path="documents/lecture.pdf", payload=big_pdf)
    app = create_api(SimpleNamespace(bot=fake))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/notes",
            headers=_headers(),
            data={"title": "جزوهٔ حجیم"},
            files={"file": ("lecture.pdf", big_pdf, "application/pdf")},
        )
        assert created.status_code == 200
        response = await client.get(
            f"/api/notes/{created.json()['id']}/file",
            headers={**_headers(), "Accept-Encoding": "gzip"},
        )
    # PDFs are already compressed: no wasted CPU on the wire.
    assert response.status_code == 200
    assert "content-encoding" not in response.headers
    assert response.content == big_pdf

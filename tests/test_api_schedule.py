"""/api/schedule tests: upload via a fake bot, serving, delete, isolation."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import httpx
import pytest_asyncio

from app.api import create_api
from app.api.auth import INIT_DATA_HEADER
from tests.conftest import sign_init_data


class _FakeTgFile:
    file_path = "photos/schedule_1.jpg"

    async def download_as_bytearray(self) -> bytearray:
        return bytearray(b"\xff\xd8fake-jpeg-bytes")


class _FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[str, int]] = []
        self.deleted: list[int] = []
        self.get_file_calls: list[str] = []

    async def send_photo(self, *, chat_id: int, photo: object) -> SimpleNamespace:
        self.sent.append(("photo", chat_id))
        size = SimpleNamespace(file_id="PHOTO-FILE-1", file_unique_id="photo-unique-1")
        return SimpleNamespace(message_id=101, photo=[size], document=None)

    async def send_document(self, *, chat_id: int, document: object) -> SimpleNamespace:
        self.sent.append(("document", chat_id))
        doc = SimpleNamespace(file_id="DOC-FILE-1", file_unique_id="doc-unique-1")
        return SimpleNamespace(message_id=102, photo=None, document=doc)

    async def delete_message(self, *, chat_id: int, message_id: int) -> bool:
        self.deleted.append(message_id)
        return True

    async def get_file(self, file_id: str) -> _FakeTgFile:
        self.get_file_calls.append(file_id)
        return _FakeTgFile()


@pytest_asyncio.fixture
async def fake_bot() -> _FakeBot:
    return _FakeBot()


@pytest_asyncio.fixture
async def schedule_client(db, fake_bot):
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


async def test_schedule_starts_empty(schedule_client):
    response = await schedule_client.get("/api/schedule", headers=_headers())
    assert response.status_code == 200
    assert response.json() == {"exists": False, "file_type": None, "caption": None}


async def test_schedule_requires_auth(schedule_client):
    assert (await schedule_client.get("/api/schedule")).status_code == 401
    assert (await schedule_client.delete("/api/schedule")).status_code == 401


async def test_upload_image_is_sent_through_the_bot(schedule_client, fake_bot):
    response = await schedule_client.post(
        "/api/schedule",
        headers=_headers(),
        files={"file": ("program.jpg", b"\xff\xd8jpeg-bytes", "image/jpeg")},
    )
    assert response.status_code == 200
    assert response.json() == {
        "exists": True,
        "file_type": "photo",
        "caption": "program.jpg",
    }
    assert fake_bot.sent == [("photo", 111)]
    assert fake_bot.deleted == [101]  # temporary message is cleaned up


async def test_upload_document_uses_send_document(schedule_client, fake_bot):
    response = await schedule_client.post(
        "/api/schedule",
        headers=_headers(),
        files={"file": ("program.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert response.status_code == 200
    assert response.json()["file_type"] == "document"
    assert fake_bot.sent == [("document", 111)]


async def test_served_file_matches_what_telegram_stored(schedule_client, fake_bot):
    await schedule_client.post(
        "/api/schedule",
        headers=_headers(),
        files={"file": ("program.jpg", b"\xff\xd8jpeg-bytes", "image/jpeg")},
    )
    response = await schedule_client.get("/api/schedule/file", headers=_headers())
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/jpeg")
    assert response.content == b"\xff\xd8fake-jpeg-bytes"
    assert fake_bot.get_file_calls == ["PHOTO-FILE-1"]


async def test_serving_without_schedule_is_404(schedule_client):
    response = await schedule_client.get("/api/schedule/file", headers=_headers())
    assert response.status_code == 404


async def test_delete_removes_the_schedule(schedule_client):
    await schedule_client.post(
        "/api/schedule",
        headers=_headers(),
        files={"file": ("program.jpg", b"data", "image/jpeg")},
    )
    deleted = await schedule_client.delete("/api/schedule", headers=_headers())
    assert deleted.status_code == 200
    after = await schedule_client.get("/api/schedule", headers=_headers())
    assert after.json()["exists"] is False
    again = await schedule_client.delete("/api/schedule", headers=_headers())
    assert again.status_code == 404


async def test_empty_upload_is_rejected(schedule_client):
    response = await schedule_client.post(
        "/api/schedule",
        headers=_headers(),
        files={"file": ("empty.jpg", b"", "image/jpeg")},
    )
    assert response.status_code == 400


async def test_oversized_upload_is_rejected(
    schedule_client, monkeypatch
):
    from app.api.routers import schedule as schedule_module

    monkeypatch.setattr(schedule_module, "MAX_PHOTO_BYTES", 8)
    response = await schedule_client.post(
        "/api/schedule",
        headers=_headers(),
        files={"file": ("big.jpg", b"0123456789", "image/jpeg")},
    )
    assert response.status_code == 413


async def test_users_see_only_their_own_schedule(schedule_client):
    await schedule_client.post(
        "/api/schedule",
        headers=_headers(user_id=111),
        files={"file": ("mine.jpg", b"data", "image/jpeg")},
    )
    other = await schedule_client.get("/api/schedule", headers=_headers(user_id=222))
    assert other.json()["exists"] is False
    other_file = await schedule_client.get("/api/schedule/file", headers=_headers(user_id=222))
    assert other_file.status_code == 404

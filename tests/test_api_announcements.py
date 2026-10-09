"""/api/announcements tests: bot-created inbox items, file serving, delete."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import httpx
import pytest_asyncio

from app.api import create_api
from app.api.auth import INIT_DATA_HEADER
from app.database.database import get_session
from app.database.repositories.announcement_repository import AnnouncementRepository
from app.database.repositories.user_repository import UserRepository
from tests.conftest import sign_init_data
from tests.fake_bot import FakeBot

_PDF_BYTES = b"%PDF-1.4 announcement"


@pytest_asyncio.fixture
async def fake_bot() -> FakeBot:
    return FakeBot(file_path="documents/notice.pdf", payload=_PDF_BYTES)


@pytest_asyncio.fixture
async def announcements_client(db, fake_bot):
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


async def _insert(client, *, telegram_id: int = 111, **overrides) -> int:
    # authenticate once so the user row exists, then use its real pk
    response = await client.get("/api/announcements", headers=_headers(user_id=telegram_id))
    assert response.status_code == 200
    async with get_session() as session:
        user = await UserRepository(session).get_by_telegram_id(telegram_id)
        assert user is not None
        payload = {"user_id": user.id, "title": "اطلاعیهٔ دانشکده"}
        payload.update(overrides)
        announcement = await AnnouncementRepository(session).create(**payload)
        return announcement.id


async def test_announcements_start_empty_and_require_auth(announcements_client):
    response = await announcements_client.get("/api/announcements", headers=_headers())
    assert response.status_code == 200
    assert response.json() == []
    assert (await announcements_client.get("/api/announcements")).status_code == 401
    assert (
        await announcements_client.delete("/api/announcements/1")
    ).status_code == 401


async def test_list_shows_a_bot_saved_post(announcements_client):
    await _insert(
        announcements_client,
        text="   زمان ثبت‌نام    ",
        source_url="https://t.me/channel/123",
        source="telegram",
    )
    response = await announcements_client.get("/api/announcements", headers=_headers())
    body = response.json()
    assert len(body) == 1
    assert body[0]["title"] == "اطلاعیهٔ دانشکده"
    assert body[0]["text"] == "زمان ثبت‌نام"  # whitespace collapsed by repo
    assert body[0]["source_url"] == "https://t.me/channel/123"
    assert body[0]["source"] == "telegram"
    assert "/" in body[0]["display"]


async def test_announcement_media_is_served_from_telegram(announcements_client, fake_bot):
    announcement_id = await _insert(
        announcements_client, file_type="document", file_id="DOC-NOTICE-1"
    )
    response = await announcements_client.get(
        f"/api/announcements/{announcement_id}/file", headers=_headers()
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content == _PDF_BYTES
    assert fake_bot.get_file_calls == ["DOC-NOTICE-1"]


async def test_announcement_without_media_or_for_stranger_is_404(announcements_client):
    plain = await _insert(announcements_client)  # no file
    assert (
        await announcements_client.get(
            f"/api/announcements/{plain}/file", headers=_headers()
        )
    ).status_code == 404

    theirs = await _insert(announcements_client, telegram_id=222, file_type="document", file_id="DOC-X")
    stranger = _headers(user_id=333)
    assert (
        await announcements_client.get(
            f"/api/announcements/{theirs}/file", headers=stranger
        )
    ).status_code == 404


async def test_delete_removes_only_your_announcement(announcements_client):
    mine = await _insert(announcements_client, telegram_id=111)
    others = await _insert(announcements_client, telegram_id=222)

    stranger = _headers(user_id=222)
    assert (
        await announcements_client.delete(f"/api/announcements/{mine}", headers=stranger)
    ).status_code == 404

    deleted = await announcements_client.delete(
        f"/api/announcements/{mine}", headers=_headers()
    )
    assert deleted.status_code == 200
    assert (await announcements_client.get("/api/announcements", headers=_headers())).json() == []
    again = await announcements_client.delete(
        f"/api/announcements/{mine}", headers=_headers()
    )
    assert again.status_code == 404

    remaining = await announcements_client.get("/api/announcements", headers=stranger)
    assert [a["id"] for a in remaining.json()] == [others]


# --- channel subscriptions ------------------------------------------------
async def test_channels_crud_and_scope(announcements_client):
    client = announcements_client
    mine = _headers(user_id=111)
    stranger = _headers(user_id=222)

    assert (await client.get("/api/announcements/channels")).status_code == 401

    added = await client.post(
        "/api/announcements/channels", json={"url": "https://t.me/my_chan"}, headers=mine
    )
    assert added.status_code == 200
    channel = added.json()
    assert channel["platform"] == "telegram"
    assert channel["handle"] == "my_chan"
    assert channel["url"] == "https://t.me/my_chan"

    listed = await client.get("/api/announcements/channels", headers=mine)
    assert [c["id"] for c in listed.json()] == [channel["id"]]
    # another student sees nothing of mine
    assert (
        await client.get("/api/announcements/channels", headers=stranger)
    ).json() == []

    # the same channel in a short form is idempotent
    again = await client.post(
        "/api/announcements/channels", json={"url": "t.me/my_chan"}, headers=mine
    )
    assert again.status_code == 200
    assert len((await client.get("/api/announcements/channels", headers=mine)).json()) == 1

    bad = await client.post(
        "/api/announcements/channels", json={"url": "https://example.com/x"}, headers=mine
    )
    assert bad.status_code == 400

    deleted = await client.delete(
        f"/api/announcements/channels/{channel['id']}", headers=mine
    )
    assert deleted.json() == {"deleted": True}
    assert (await client.get("/api/announcements/channels", headers=mine)).json() == []
    assert (
        await client.delete(f"/api/announcements/channels/{channel['id']}", headers=mine)
    ).status_code == 404

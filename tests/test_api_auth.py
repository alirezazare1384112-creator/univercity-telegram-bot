"""Mini App authentication tests: initData verification, no network."""

from __future__ import annotations

import json
import time
from urllib.parse import parse_qsl, urlencode

from sqlalchemy import func, select

from app.api.auth import INIT_DATA_HEADER
from app.database.models import User
from tests.conftest import sign_init_data


def _fields(
    *,
    user_id: int = 111,
    auth_date: int | None = None,
    name: str = "سارا",
    photo_url: str | None = None,
) -> dict[str, str]:
    user_obj: dict[str, object] = {
        "id": user_id,
        "first_name": name,
        "username": f"u{user_id}",
    }
    if photo_url is not None:
        user_obj["photo_url"] = photo_url
    return {
        "user": json.dumps(user_obj, ensure_ascii=False),
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "AAF-test",
    }


async def _user_count(db) -> int:
    async with db() as session:
        return int(await session.scalar(select(func.count()).select_from(User)) or 0)


async def test_valid_init_data_returns_and_creates_user(api_client, db):
    response = await api_client.get(
        "/api/me", headers={INIT_DATA_HEADER: sign_init_data(_fields())}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["telegram_id"] == 111
    assert data["first_name"] == "سارا"
    assert data["username"] == "u111"
    assert await _user_count(db) == 1


async def test_login_twice_keeps_a_single_row(api_client, db):
    for _ in range(2):
        response = await api_client.get(
            "/api/me", headers={INIT_DATA_HEADER: sign_init_data(_fields())}
        )
        assert response.status_code == 200
    assert await _user_count(db) == 1


async def test_two_telegram_accounts_get_separate_rows(api_client, db):
    first = await api_client.get(
        "/api/me", headers={INIT_DATA_HEADER: sign_init_data(_fields(user_id=111))}
    )
    second = await api_client.get(
        "/api/me", headers={INIT_DATA_HEADER: sign_init_data(_fields(user_id=222))}
    )
    assert first.json()["id"] != second.json()["id"]
    assert await _user_count(db) == 2


async def test_missing_header_is_rejected(api_client):
    response = await api_client.get("/api/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "missing init data"


async def test_tampered_user_payload_is_rejected(api_client, db):
    signed = sign_init_data(_fields(user_id=111))
    pairs = dict(parse_qsl(signed, keep_blank_values=True))
    pairs["user"] = json.dumps({"id": 999, "first_name": "Hacker"}, ensure_ascii=False)
    response = await api_client.get("/api/me", headers={INIT_DATA_HEADER: urlencode(pairs)})
    assert response.status_code == 401
    assert response.json()["detail"] == "signature mismatch"
    assert await _user_count(db) == 0


async def test_expired_init_data_is_rejected(api_client):
    stale = int(time.time()) - 90_000  # older than the default 86400s window
    response = await api_client.get(
        "/api/me", headers={INIT_DATA_HEADER: sign_init_data(_fields(auth_date=stale))}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "initData expired"


async def test_future_auth_date_is_rejected(api_client):
    future = int(time.time()) + 3600
    response = await api_client.get(
        "/api/me", headers={INIT_DATA_HEADER: sign_init_data(_fields(auth_date=future))}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "auth_date is in the future"


async def test_signature_signed_with_the_wrong_token_is_rejected(api_client, db):
    wrong = sign_init_data(_fields(), bot_token="999:WRONG-TOKEN")
    response = await api_client.get("/api/me", headers={INIT_DATA_HEADER: wrong})
    assert response.status_code == 401
    assert response.json()["detail"] == "signature mismatch"
    assert await _user_count(db) == 0


async def test_hash_field_must_be_present(api_client):
    pairs = sorted(_fields().items())
    response = await api_client.get(
        "/api/me", headers={INIT_DATA_HEADER: urlencode(pairs)}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "missing hash"


async def test_photo_url_is_persisted_and_returned(api_client, db):
    """Telegram sends photo_url inside initData; we store and surface it."""
    photo = "https://telegram.org/img/user/111.jpg"
    response = await api_client.get(
        "/api/me", headers={INIT_DATA_HEADER: sign_init_data(_fields(photo_url=photo))}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["photo_url"] == photo

    # Stored in the database
    async with db() as session:
        user = await session.scalar(select(User).where(User.telegram_id == 111))
    assert user is not None and user.photo_url == photo


async def test_missing_photo_url_is_null(api_client, db):
    """Users without a profile photo get null, not an empty string."""
    response = await api_client.get(
        "/api/me", headers={INIT_DATA_HEADER: sign_init_data(_fields())}
    )
    assert response.status_code == 200
    assert response.json()["photo_url"] is None


async def test_photo_url_is_refreshed_on_each_login(api_client, db):
    """Telegram rotates the URL on each initData; we always store the latest."""
    first = "https://telegram.org/img/user/111-v1.jpg"
    await api_client.get(
        "/api/me", headers={INIT_DATA_HEADER: sign_init_data(_fields(photo_url=first))}
    )
    second = "https://telegram.org/img/user/111-v2.jpg"
    response = await api_client.get(
        "/api/me", headers={INIT_DATA_HEADER: sign_init_data(_fields(photo_url=second))}
    )
    assert response.json()["photo_url"] == second
    async with db() as session:
        user = await session.scalar(select(User).where(User.telegram_id == 111))
    assert user is not None and user.photo_url == second


async def test_photo_url_not_cleared_when_absent(api_client, db):
    """When Telegram omits photo_url we keep the previously stored value.

    This matches Telegram's behaviour: a user who once had a profile photo
    keeps it even if they later open the Mini App from a client that does
    not include the field. Only an explicit ``null`` would clear it, and
    Telegram never sends null.
    """
    photo = "https://telegram.org/img/user/111.jpg"
    await api_client.get(
        "/api/me", headers={INIT_DATA_HEADER: sign_init_data(_fields(photo_url=photo))}
    )
    # Second call without photo_url in the user object
    await api_client.get(
        "/api/me", headers={INIT_DATA_HEADER: sign_init_data(_fields())}
    )
    async with db() as session:
        user = await session.scalar(select(User).where(User.telegram_id == 111))
    assert user is not None and user.photo_url == photo

"""Telegram Mini App authentication (initData verification).

Telegram signs the ``initData`` query string with the bot token:
``HMAC_SHA256(key="WebAppData", msg=bot_token)`` is the secret key, then
``HMAC_SHA256(secret_key, data_check_string)`` is the ``hash`` field.
Everything is checked server side; the frontend never proves anything
on its own.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Annotated
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException

from app.config import get_settings
from app.database.database import get_session
from app.database.models import User
from app.database.repositories.admin_repository import AdminRepository
from app.database.repositories.user_repository import UserRepository

INIT_DATA_HEADER = "X-Telegram-Init-Data"

# Accept a small clock difference between Telegram and this server.
_CLOCK_SKEW_SECONDS = 60


class InitDataError(ValueError):
    """Raised when Mini App init data fails verification."""


def verify_init_data(
    init_data: str,
    *,
    bot_token: str,
    max_age: int,
    now_ts: int | None = None,
) -> dict[str, str]:
    """Return the init data fields after checking the signature and age."""
    pairs = parse_qsl(init_data, keep_blank_values=True)
    hashes = [value for key, value in pairs if key == "hash"]
    if len(hashes) != 1 or not hashes[0]:
        raise InitDataError("missing hash")
    if not bot_token:
        raise InitDataError("server has no bot token")

    check_pairs = [(key, value) for key, value in pairs if key != "hash"]
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(check_pairs))

    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, hashes[0]):
        raise InitDataError("signature mismatch")

    fields = dict(check_pairs)
    try:
        auth_date = int(fields.get("auth_date", ""))
    except ValueError as exc:
        raise InitDataError("invalid auth_date") from exc

    current = now_ts if now_ts is not None else int(time.time())
    if auth_date > current + _CLOCK_SKEW_SECONDS:
        raise InitDataError("auth_date is in the future")
    if current - auth_date > max_age:
        raise InitDataError("initData expired")

    return fields


def parse_init_user(fields: dict[str, str]) -> dict:
    """Extract and validate the Telegram user object from init data."""
    raw = fields.get("user")
    if not raw:
        raise InitDataError("missing user")
    try:
        user_data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InitDataError("invalid user json") from exc
    if not isinstance(user_data, dict) or not isinstance(user_data.get("id"), int):
        raise InitDataError("invalid user")
    return user_data


async def user_from_init_data(init_data: str) -> User:
    """Verify an initData string and return the shared User row."""
    settings = get_settings()
    try:
        fields = verify_init_data(
            init_data,
            bot_token=settings.bot_token,
            max_age=settings.webapp_auth_max_age,
        )
        user_data = parse_init_user(fields)
    except InitDataError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from None

    async with get_session() as session:
        user, _created = await UserRepository(session).get_or_create_from_telegram(
            telegram_id=user_data["id"],
            username=user_data.get("username"),
            first_name=user_data.get("first_name"),
            last_name=user_data.get("last_name"),
        )
    return user


# Signed URLs for file previews (<img>/<iframe> cannot send headers).
FILE_TOKEN_TTL_SECONDS = 3600


def _file_signature(user_id: int, note_id: int, expires: int, *, bot_token: str) -> str:
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    message = f"file:{note_id}:{user_id}:{expires}".encode()
    return hmac.new(secret_key, message, hashlib.sha256).hexdigest()[:32]


def sign_file_token(user_id: int, note_id: int, expires: int, *, bot_token: str) -> str:
    """Sign ``{user}.{expires}.{sig}`` authorising one note download.

    Reuses the initData secret key; the note id is inside the signature, so
    a token minted for one file can never unlock another.
    """
    signature = _file_signature(user_id, note_id, expires, bot_token=bot_token)
    return f"{user_id}.{expires}.{signature}"


def verify_file_token(
    token: str,
    note_id: int,
    *,
    bot_token: str,
    now_ts: int | None = None,
) -> int | None:
    """Return the issuing user id, or ``None`` for invalid/expired tokens."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    user_part, expires_part, signature = parts
    try:
        user_id = int(user_part)
        expires = int(expires_part)
    except ValueError:
        return None
    now = now_ts if now_ts is not None else int(time.time())
    if now > expires:
        return None
    expected = _file_signature(user_id, note_id, expires, bot_token=bot_token)
    if not hmac.compare_digest(expected, signature):
        return None
    return user_id


async def current_user(
    init_data: str | None = Header(default=None, alias=INIT_DATA_HEADER),
) -> User:
    """FastAPI dependency: verify the header and return the shared User row."""
    if not init_data:
        raise HTTPException(status_code=401, detail="missing init data")
    return await user_from_init_data(init_data)


async def current_admin(user: Annotated[User, Depends(current_user)]) -> User:
    """Dependency: the authenticated user must be an admin (403 otherwise)."""
    async with get_session() as session:
        allowed = await AdminRepository(session).is_admin(user.telegram_id)
    if not allowed:
        raise HTTPException(status_code=403, detail="دسترسی ادمین ندارید")
    return user

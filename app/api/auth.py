"""Telegram Mini App authentication (initData verification).

Telegram signs the ``initData`` query string with the bot token:
``HMAC_SHA256(key=bot_token, msg="WebAppData")`` is the secret key, then
``HMAC_SHA256(secret_key, data_check_string)`` is the ``hash`` field.
Everything is checked server side; the frontend never proves anything
on its own.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException

from app.config import get_settings
from app.database.database import get_session
from app.database.models import User
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

    secret_key = hmac.new(bot_token.encode(), b"WebAppData", hashlib.sha256).digest()
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
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InitDataError("invalid user json") from exc
    if not isinstance(data, dict) or not isinstance(data.get("id"), int):
        raise InitDataError("invalid user")
    return data


async def current_user(
    init_data: str | None = Header(default=None, alias=INIT_DATA_HEADER),
) -> User:
    """FastAPI dependency: verify the header and return the shared User row."""
    if not init_data:
        raise HTTPException(status_code=401, detail="missing init data")

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

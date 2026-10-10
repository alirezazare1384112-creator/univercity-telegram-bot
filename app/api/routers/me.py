"""/api/me - the authenticated Telegram user's profile."""

from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.api.auth import (
    FILE_TOKEN_TTL_SECONDS,
    current_user,
    sign_file_token,
    verify_file_token,
)
from app.api.schemas import MeOut, ProfileIn
from app.config import get_settings
from app.database.database import get_session
from app.database.models import User
from app.database.repositories.admin_repository import AdminRepository
from app.database.repositories.user_repository import UserRepository

router = APIRouter(prefix="/api", tags=["me"])


async def _me_out(user: User) -> MeOut:
    out = MeOut.model_validate(user)
    async with get_session() as session:
        out.is_admin = await AdminRepository(session).is_admin(user.telegram_id)
    out.credentials_enabled = get_settings().credentials_enabled
    return out


@router.get("/me", response_model=MeOut)
async def read_me(user: Annotated[User, Depends(current_user)]) -> MeOut:
    out = await _me_out(user)
    # When the user has a photo, mint a short-lived signed token so the
    # browser can load the image via /api/me/photo?token=... without
    # sending the initData header (which <img> cannot do).
    if user.photo_url:
        import time
        expires = int(time.time()) + FILE_TOKEN_TTL_SECONDS
        token = sign_file_token(user.id, 0, expires, bot_token=get_settings().bot_token)
        # Use note_id=0 as a sentinel for "user photo"; verify_file_token
        # checks the signature against the same {user_id}:{expires} pair.
        out.photo_token = token  # type: ignore[attr-defined]
    return out


@router.get("/me/photo")
async def me_photo(
    token: Annotated[str, Query()],
) -> Response:
    """Proxy the user's Telegram profile photo through our own server.

    Telegram photo URLs (``https://t.me/i/userpic/...``) redirect to a
    CDN that may not load inside Telegram's in-app browser due to cookie
    or referrer restrictions. This endpoint fetches the image server-side
    and returns the bytes directly, so the ``<img>`` tag works everywhere.

    Auth is via a signed token (minted by ``GET /api/me``) because
    ``<img>`` cannot send the ``X-Telegram-Init-Data`` header.
    """
    # verify_file_token with note_id=0 validates the token signed for
    # the user's photo. Returns the user_id or None.
    user_id = verify_file_token(token, 0, bot_token=get_settings().bot_token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="invalid or expired token")

    async with get_session() as session:
        user = await UserRepository(session).get_by_id(user_id)
    if user is None or not user.photo_url:
        raise HTTPException(status_code=404, detail="no photo")

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(user.photo_url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "image/jpeg")
            return Response(content=resp.content, media_type=content_type)
    except Exception:  # noqa: BLE001 - network errors are expected here
        raise HTTPException(status_code=502, detail="could not fetch photo") from None


@router.put("/me", response_model=MeOut)
async def update_me(
    payload: ProfileIn,
    user: Annotated[User, Depends(current_user)],
) -> MeOut:
    async with get_session() as session:
        repository = UserRepository(session)
        fresh = await repository.get_by_id(user.id)
        if fresh is not None:
            user = await repository.update_profile(
                fresh,
                student_number=payload.student_number,
                field_of_study=payload.field_of_study,
                university=payload.university,
                semester=payload.semester,
                bio=payload.bio,
            )
    return await _me_out(user)

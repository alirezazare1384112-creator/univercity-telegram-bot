from __future__ import annotations

import contextlib
import mimetypes
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import Response
from telegram import InputFile
from telegram.error import TelegramError

from app.api.auth import current_user
from app.api.schemas import ScheduleOut
from app.database.database import get_session
from app.database.models import User
from app.database.repositories.schedule_repository import WeeklyScheduleRepository

router = APIRouter(prefix="/api", tags=["schedule"])

# Photos are limited to 10MB by Telegram; every other file must stay below
# the 20MB Bot API download limit so the Mini App can serve it back.
MAX_PHOTO_BYTES = 10 * 1024 * 1024
MAX_FILE_BYTES = 20 * 1024 * 1024

# Types that must never be served as active content from our origin.
_UNSAFE_MIME_PREFIXES = ("text/html", "application/xhtml", "image/svg")


def _bot(request: Request) -> Any:
    application = getattr(request.app.state, "bot_application", None)
    if application is None:
        raise HTTPException(status_code=503, detail="bot is not running")
    return application.bot


def _safe_media_type(guessed: str | None) -> str:
    if not guessed:
        return "application/octet-stream"
    lowered = guessed.lower()
    if lowered.startswith(_UNSAFE_MIME_PREFIXES):
        return "application/octet-stream"
    return lowered


@router.get("/schedule", response_model=ScheduleOut)
async def read_schedule(user: Annotated[User, Depends(current_user)]) -> ScheduleOut:
    async with get_session() as session:
        schedule = await WeeklyScheduleRepository(session).get_active(user.id)
    if schedule is None:
        return ScheduleOut(exists=False)
    return ScheduleOut(exists=True, file_type=schedule.file_type, caption=schedule.caption)


@router.get("/schedule/file")
async def download_schedule(
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> Response:
    async with get_session() as session:
        schedule = await WeeklyScheduleRepository(session).get_active(user.id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="no schedule")

    bot = _bot(request)
    try:
        tg_file = await bot.get_file(schedule.telegram_file_id)
        data = await tg_file.download_as_bytearray()
    except (TelegramError, OSError) as exc:
        raise HTTPException(status_code=502, detail="could not download from Telegram") from exc

    media_type = _safe_media_type(mimetypes.guess_type(tg_file.file_path or "")[0])
    headers = {"Cache-Control": "private, max-age=300"}
    return Response(content=bytes(data), media_type=media_type, headers=headers)


@router.post("/schedule", response_model=ScheduleOut)
async def upload_schedule(
    request: Request,
    file: UploadFile,
    user: Annotated[User, Depends(current_user)],
) -> ScheduleOut:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")

    content_type = (file.content_type or "application/octet-stream").lower()
    is_image = content_type.startswith("image/")
    limit = MAX_PHOTO_BYTES if is_image else MAX_FILE_BYTES
    if len(data) > limit:
        raise HTTPException(status_code=413, detail="file too large")

    bot = _bot(request)
    payload = InputFile(data, filename=file.filename or "schedule")
    try:
        if is_image:
            message = await bot.send_photo(chat_id=user.telegram_id, photo=payload)
            best = message.photo[-1]
            file_id, file_unique_id, file_type = best.file_id, best.file_unique_id, "photo"
        else:
            message = await bot.send_document(chat_id=user.telegram_id, document=payload)
            doc = message.document
            file_id, file_unique_id, file_type = doc.file_id, doc.file_unique_id, "document"
        with contextlib.suppress(TelegramError):
            await bot.delete_message(chat_id=user.telegram_id, message_id=message.message_id)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail="could not upload to Telegram") from exc

    caption = file.filename or None
    async with get_session() as session:
        await WeeklyScheduleRepository(session).save(
            user_id=user.id,
            telegram_file_id=file_id,
            file_unique_id=file_unique_id,
            file_type=file_type,
            caption=caption,
        )
    return ScheduleOut(exists=True, file_type=file_type, caption=caption)


@router.delete("/schedule")
async def delete_schedule(user: Annotated[User, Depends(current_user)]) -> dict[str, bool]:
    async with get_session() as session:
        removed = await WeeklyScheduleRepository(session).delete_active(user.id)
    if not removed:
        raise HTTPException(status_code=404, detail="no schedule")
    return {"deleted": True}

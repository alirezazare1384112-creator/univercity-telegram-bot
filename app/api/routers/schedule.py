from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import Response

from app.api.auth import current_user
from app.api.files import (
    MAX_FILE_BYTES,
    MAX_PHOTO_BYTES,
    check_mini_app_size,
    fetch_telegram_file,
    send_and_cleanup,
)
from app.api.files import (
    bot_of as _bot,
)
from app.api.schemas import ScheduleOut
from app.database.database import get_session
from app.database.models import User
from app.database.repositories.schedule_repository import WeeklyScheduleRepository

router = APIRouter(prefix="/api", tags=["schedule"])


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
    data, media_type = await fetch_telegram_file(bot, schedule.telegram_file_id)
    headers = {"Cache-Control": "private, max-age=300"}
    return Response(content=data, media_type=media_type, headers=headers)


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
    # Mini App uploads are capped at 4MB by Vercel's serverless body limit.
    # Larger files must come through the Telegram bot chat.
    check_mini_app_size(data)
    is_image = content_type.startswith("image/")
    limit = MAX_PHOTO_BYTES if is_image else MAX_FILE_BYTES
    if len(data) > limit:
        raise HTTPException(status_code=413, detail="file too large")

    bot = _bot(request)
    file_id, file_unique_id, file_type = await send_and_cleanup(
        bot,
        chat_id=user.telegram_id,
        data=data,
        filename=file.filename or "schedule",
        content_type=content_type,
    )

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

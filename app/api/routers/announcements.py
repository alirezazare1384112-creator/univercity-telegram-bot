from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from app.api.auth import current_user
from app.api.files import bot_of, fetch_telegram_file
from app.api.schemas import AnnouncementOut
from app.config import get_settings
from app.database.database import get_session
from app.database.models import Announcement, User
from app.database.repositories.announcement_repository import AnnouncementRepository
from app.utils.datetime_utils import format_jalali

router = APIRouter(prefix="/api", tags=["announcements"])


def _out(announcement: Announcement) -> AnnouncementOut:
    tz = get_settings().timezone
    return AnnouncementOut(
        id=announcement.id,
        title=announcement.title,
        text=announcement.text,
        source=announcement.source,
        source_url=announcement.source_url,
        file_type=announcement.file_type,
        created_at=announcement.created_at,
        display=format_jalali(announcement.created_at, tz),
    )


@router.get("/announcements", response_model=list[AnnouncementOut])
async def list_announcements(
    user: Annotated[User, Depends(current_user)],
) -> list[AnnouncementOut]:
    async with get_session() as session:
        announcements = await AnnouncementRepository(session).list_by_user(user.id)
    return [_out(announcement) for announcement in announcements]


@router.get("/announcements/{announcement_id}/file")
async def download_announcement(
    announcement_id: int,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> Response:
    async with get_session() as session:
        announcement = await AnnouncementRepository(session).get(announcement_id, user.id)
    if announcement is None or not announcement.file_id:
        raise HTTPException(status_code=404, detail="announcement not found")

    data, media_type = await fetch_telegram_file(bot_of(request), announcement.file_id)
    return Response(
        content=data,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.delete("/announcements/{announcement_id}")
async def delete_announcement(
    announcement_id: int,
    user: Annotated[User, Depends(current_user)],
) -> dict[str, bool]:
    async with get_session() as session:
        repository = AnnouncementRepository(session)
        announcement = await repository.get(announcement_id, user.id)
        if announcement is None:
            raise HTTPException(status_code=404, detail="announcement not found")
        await repository.delete(announcement)
    return {"deleted": True}

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from app.api.auth import current_user
from app.api.files import bot_of, fetch_telegram_file
from app.api.schemas import AnnouncementOut, ChannelIn, ChannelOut
from app.config import get_settings
from app.database.database import get_session
from app.database.models import Announcement, User
from app.database.models.user_channel import UserChannel
from app.database.repositories.announcement_repository import AnnouncementRepository
from app.database.repositories.user_channel_repository import UserChannelRepository
from app.services.channel_sync import normalize_channel_url
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


def _channel_out(channel: UserChannel) -> ChannelOut:
    return ChannelOut(
        id=channel.id,
        platform=channel.platform,
        url=channel.url,
        handle=channel.handle,
        created_at=channel.created_at,
    )


@router.get("/announcements/channels", response_model=list[ChannelOut])
async def list_channels(
    user: Annotated[User, Depends(current_user)],
) -> list[ChannelOut]:
    async with get_session() as session:
        channels = await UserChannelRepository(session).list_by_user(user.id)
    return [_channel_out(channel) for channel in channels]


@router.post("/announcements/channels", response_model=ChannelOut)
async def add_channel(
    payload: ChannelIn,
    user: Annotated[User, Depends(current_user)],
) -> ChannelOut:
    normalized = normalize_channel_url(payload.url)
    if normalized is None:
        raise HTTPException(status_code=400, detail="لینک کانال معتبر نیست")
    platform, url, handle = normalized
    async with get_session() as session:
        channel, _created = await UserChannelRepository(session).add(
            user_id=user.id, platform=platform, url=url, handle=handle
        )
    return _channel_out(channel)


@router.delete("/announcements/channels/{channel_id}")
async def delete_channel(
    channel_id: int,
    user: Annotated[User, Depends(current_user)],
) -> dict[str, bool]:
    async with get_session() as session:
        repository = UserChannelRepository(session)
        channel = await repository.get(channel_id, user.id)
        if channel is None:
            raise HTTPException(status_code=404, detail="channel not found")
        await repository.delete(channel)
    return {"deleted": True}


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

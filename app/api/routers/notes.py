from __future__ import annotations

import json
import mimetypes
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError
from telegram.error import TelegramError

from app.api.auth import (
    FILE_TOKEN_TTL_SECONDS,
    INIT_DATA_HEADER,
    current_user,
    sign_file_token,
    user_from_init_data,
    verify_file_token,
)
from app.api.files import (
    bot_of,
    check_mini_app_size,
    check_size,
    fetch_telegram_file,
    safe_media_type,
    send_and_cleanup,
)
from app.api.routers.courses import _own_course
from app.api.schemas import FileTokenOut, NoteIn, NoteOut
from app.config import get_settings
from app.database.database import get_session
from app.database.models import Note, User
from app.database.models.note import NOTE_PHOTO
from app.database.repositories.course_repository import CourseRepository
from app.database.repositories.note_repository import NoteRepository

router = APIRouter(prefix="/api", tags=["notes"])


def _validate_meta(title: str, description: str | None, course_id: int | None) -> NoteIn:
    """Reuse the NoteIn validators on raw multipart form fields."""
    try:
        return NoteIn(title=title, description=description, course_id=course_id)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=json.loads(exc.json())) from exc


def _note_out(note: Note, course_names: dict[int, str]) -> NoteOut:
    return NoteOut(
        id=note.id,
        title=note.title,
        description=note.description,
        course_id=note.course_id,
        course_name=course_names.get(note.course_id) if note.course_id else None,
        file_type=note.file_type,
        file_name=note.file_name,
    )


def _media_type_for(note: Note) -> str:
    """Best-effort content type without downloading the file.

    Photos are always JPEG after Telegram's processing; everything else is
    guessed from the uploaded filename.
    """
    if note.file_type == NOTE_PHOTO:
        return "image/jpeg"
    return safe_media_type(mimetypes.guess_type(note.file_name or "")[0])


@router.get("/notes", response_model=list[NoteOut])
async def list_notes(
    user: Annotated[User, Depends(current_user)],
    course_id: int | None = Query(default=None),
) -> list[NoteOut]:
    async with get_session() as session:
        notes = await NoteRepository(session).list_by_user(user.id, course_id=course_id)
        courses = await CourseRepository(session).list_by_user(user.id)
    names = {course.id: course.name for course in courses}
    return [_note_out(note, names) for note in notes]


@router.post("/notes", response_model=NoteOut)
async def create_note(
    request: Request,
    file: UploadFile,
    title: Annotated[str, Form(min_length=1, max_length=128)],
    user: Annotated[User, Depends(current_user)],
    description: Annotated[str | None, Form()] = None,
    course_id: Annotated[int | None, Form()] = None,
) -> NoteOut:
    meta = _validate_meta(title, description, course_id)

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    content_type = (file.content_type or "application/octet-stream").lower()
    # Mini App uploads are capped at 4MB by the Vercel serverless body
    # limit (4.5MB hard). Larger files must come through the Telegram bot
    # chat. This check fires *before* we forward anything to Telegram so
    # the user gets a clear Persian error instead of a Vercel 413.
    check_mini_app_size(data)
    check_size(data, content_type)

    bot = bot_of(request)
    async with get_session() as session:
        names: dict[int, str] = {}
        if meta.course_id is not None:
            course = await _own_course(session, meta.course_id, user)
            names[course.id] = course.name
        file_id, file_unique_id, file_type = await send_and_cleanup(
            bot,
            chat_id=user.telegram_id,
            data=data,
            filename=file.filename or "note",
            content_type=content_type,
        )
        note = await NoteRepository(session).create(
            user_id=user.id,
            title=meta.title,
            description=meta.description,
            course_id=meta.course_id,
            file_type=file_type,
            file_id=file_id,
            file_unique_id=file_unique_id,
            file_name=file.filename or None,
        )
    return _note_out(note, names)


@router.post("/notes/{note_id}/file-token", response_model=FileTokenOut)
async def create_note_file_token(
    note_id: int,
    user: Annotated[User, Depends(current_user)],
) -> FileTokenOut:
    """Mint a signed, one-hour URL so ``<img>``/``<iframe>`` can fetch the file.

    Browser elements cannot attach the initData header; the token is bound
    to one note + one user and never authorises anything else.
    """
    async with get_session() as session:
        note = await NoteRepository(session).get(note_id, user.id)
    if note is None:
        raise HTTPException(status_code=404, detail="note not found")
    expires = int(time.time()) + FILE_TOKEN_TTL_SECONDS
    token = sign_file_token(user.id, note_id, expires, bot_token=get_settings().bot_token)
    return FileTokenOut(token=token, media_type=_media_type_for(note))


@router.get("/notes/{note_id}/file")
async def download_note(
    note_id: int,
    request: Request,
    t: Annotated[str | None, Query(max_length=256)] = None,
) -> Response:
    """Serve the file with either the initData header or a signed ``?t=`` token.

    Responses carry an ETag: repeat views revalidate for a cheap 304 instead
    of re-downloading from Telegram.
    """
    if t is not None:
        user_id = verify_file_token(t, note_id, bot_token=get_settings().bot_token)
        if user_id is None:
            raise HTTPException(status_code=401, detail="invalid or expired file token")
    elif init_data := request.headers.get(INIT_DATA_HEADER):
        user_id = (await user_from_init_data(init_data)).id
    else:
        raise HTTPException(status_code=401, detail="missing init data")

    async with get_session() as session:
        note = await NoteRepository(session).get(note_id, user_id)
    if note is None:
        raise HTTPException(status_code=404, detail="note not found")

    etag = f'"{note.file_unique_id or note.id}"'
    headers = {"Cache-Control": "private, max-age=3600", "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)

    data, media_type = await fetch_telegram_file(bot_of(request), note.file_id)
    return Response(content=data, media_type=media_type, headers=headers)


@router.post("/notes/{note_id}/send")
async def send_note_to_telegram(
    note_id: int,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> dict[str, bool]:
    """Push the note's file into the student's private chat with the bot."""
    async with get_session() as session:
        note = await NoteRepository(session).get(note_id, user.id)
    if note is None:
        raise HTTPException(status_code=404, detail="note not found")
    bot = bot_of(request)
    try:
        if note.file_type == NOTE_PHOTO:
            await bot.send_photo(
                chat_id=user.telegram_id, photo=note.file_id, caption=note.title
            )
        else:
            await bot.send_document(
                chat_id=user.telegram_id, document=note.file_id, caption=note.title
            )
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail="could not send to Telegram") from exc
    return {"sent": True}


@router.put("/notes/{note_id}", response_model=NoteOut)
async def update_note(
    note_id: int,
    payload: NoteIn,
    user: Annotated[User, Depends(current_user)],
) -> NoteOut:
    async with get_session() as session:
        repository = NoteRepository(session)
        note = await repository.get(note_id, user.id)
        if note is None:
            raise HTTPException(status_code=404, detail="note not found")
        names: dict[int, str] = {}
        if payload.course_id is not None:
            course = await _own_course(session, payload.course_id, user)
            names[course.id] = course.name
        note = await repository.update(
            note,
            title=payload.title,
            description=payload.description,
            course_id=payload.course_id,
        )
    return _note_out(note, names)


@router.delete("/notes/{note_id}")
async def delete_note(
    note_id: int,
    user: Annotated[User, Depends(current_user)],
) -> dict[str, bool]:
    async with get_session() as session:
        repository = NoteRepository(session)
        note = await repository.get(note_id, user.id)
        if note is None:
            raise HTTPException(status_code=404, detail="note not found")
        await repository.delete(note)
    return {"deleted": True}

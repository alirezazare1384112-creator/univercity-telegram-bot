"""Shared helpers for moving files through Telegram (upload + download).

Used by ``/api/schedule`` and ``/api/notes``: the Mini App posts bytes
here, the bot forwards them to the student's private chat, we keep the
``file_id`` and delete the temporary message again.
"""

from __future__ import annotations

import contextlib
import mimetypes
from typing import Any

from fastapi import HTTPException, Request
from telegram import InputFile
from telegram.error import TelegramError

from app.database.models.note import NOTE_DOCUMENT, NOTE_PHOTO

# Photos are limited to 10MB by Telegram; every other file must stay below
# the 20MB Bot API download limit so the Mini App can serve it back.
MAX_PHOTO_BYTES = 10 * 1024 * 1024
MAX_FILE_BYTES = 20 * 1024 * 1024

# Types that must never be served as active content from our origin.
_UNSAFE_MIME_PREFIXES = ("text/html", "application/xhtml", "image/svg")


def bot_of(request: Request) -> Any:
    """The running PTB application's bot, or 503 if this is API-only mode."""
    application = getattr(request.app.state, "bot_application", None)
    if application is None:
        raise HTTPException(status_code=503, detail="bot is not running")
    return application.bot


def safe_media_type(guessed: str | None) -> str:
    """Map a guessed MIME type to something safe to serve."""
    if not guessed:
        return "application/octet-stream"
    lowered = guessed.lower()
    if lowered.startswith(_UNSAFE_MIME_PREFIXES):
        return "application/octet-stream"
    return lowered


def check_size(data: bytes, content_type: str) -> None:
    """Enforce the Telegram size limits before anything is sent."""
    is_image = content_type.startswith("image/")
    limit = MAX_PHOTO_BYTES if is_image else MAX_FILE_BYTES
    if len(data) > limit:
        raise HTTPException(status_code=413, detail="file too large")


async def send_and_cleanup(
    bot: Any,
    *,
    chat_id: int,
    data: bytes,
    filename: str,
    content_type: str,
) -> tuple[str, str, str]:
    """Send bytes through the bot and delete the temporary message.

    Returns ``(file_id, file_unique_id, file_type)``.
    """
    is_image = content_type.startswith("image/")
    payload = InputFile(data, filename=filename)
    try:
        if is_image:
            message = await bot.send_photo(chat_id=chat_id, photo=payload)
            best = message.photo[-1]
            file_id, unique_id = best.file_id, best.file_unique_id
            file_type = NOTE_PHOTO
        else:
            message = await bot.send_document(chat_id=chat_id, document=payload)
            doc = message.document
            file_id, unique_id = doc.file_id, doc.file_unique_id
            file_type = NOTE_DOCUMENT
        with contextlib.suppress(TelegramError):
            await bot.delete_message(chat_id=chat_id, message_id=message.message_id)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail="could not upload to Telegram") from exc
    return file_id, unique_id, file_type


async def fetch_telegram_file(bot: Any, file_id: str) -> tuple[bytes, str]:
    """Download a file from Telegram; returns ``(bytes, media_type)``."""
    try:
        tg_file = await bot.get_file(file_id)
        data = await tg_file.download_as_bytearray()
    except (TelegramError, OSError) as exc:
        raise HTTPException(status_code=502, detail="could not download from Telegram") from exc
    media_type = safe_media_type(mimetypes.guess_type(tg_file.file_path or "")[0])
    return bytes(data), media_type

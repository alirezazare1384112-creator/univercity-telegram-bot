"""Shared helpers for moving files through Telegram (upload + download).

Used by ``/api/schedule`` and ``/api/notes``: the Mini App posts bytes
here, the bot forwards them to the student's private chat, we keep the
``file_id`` and delete the temporary message again.
"""

from __future__ import annotations

import contextlib
import logging
import mimetypes
import os
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from telegram import InputFile
from telegram.error import TelegramError

from app.database.models.note import NOTE_DOCUMENT, NOTE_PHOTO

logger = logging.getLogger(__name__)

# Photos are limited to 10MB by Telegram; every other file must stay below
# the 20MB Bot API download limit so the Mini App can serve it back.
MAX_PHOTO_BYTES = 10 * 1024 * 1024
MAX_FILE_BYTES = 20 * 1024 * 1024

# Types that must never be served as active content from our origin.
_UNSAFE_MIME_PREFIXES = ("text/html", "application/xhtml", "image/svg")

# In-process LRU for downloads: previews re-serve the same files all day,
# and every cache miss would otherwise cost a Telegram round trip.
_CACHE_TTL_SECONDS = 3600
_CACHE_MAX_BYTES = 64 * 1024 * 1024

_file_cache: OrderedDict[str, tuple[float, bytes, str]] = OrderedDict()
_file_cache_bytes = 0

# Second tier: a persistent on-disk copy. Without it every cache miss (and
# every bot restart) costs a Telegram round trip, which made PDF previews
# feel slow on mobile. ``set_disk_cache_dir(None)`` disables it (tests point
# it at a per-test tmp dir).
_disk_dir: Path | None = Path("storage") / "telegram_files"


def set_disk_cache_dir(path: Path | str | None) -> None:
    """Where downloaded Telegram files are kept between restarts."""
    global _disk_dir
    _disk_dir = Path(path) if path is not None else None


def clear_file_cache() -> None:
    """Drop every in-memory download (tests reset this between cases)."""
    global _file_cache_bytes
    _file_cache.clear()
    _file_cache_bytes = 0


def _disk_paths(file_id: str) -> tuple[Path, Path] | None:
    """``(data, mime)`` paths for a Telegram ``file_id``, or None if unsafe."""
    if _disk_dir is None or not file_id:
        return None
    if not all(char.isalnum() or char in "-_" for char in file_id):
        return None
    return _disk_dir / file_id, _disk_dir / f"{file_id}.mime"


def _disk_load(file_id: str) -> tuple[bytes, str] | None:
    paths = _disk_paths(file_id)
    if paths is None:
        return None
    data_path, mime_path = paths
    try:
        payload = data_path.read_bytes()
    except OSError:
        return None
    try:
        media_type = mime_path.read_text(encoding="utf-8").strip()
    except OSError:
        media_type = ""
    if not media_type:
        media_type = "application/octet-stream"
    return payload, media_type


def _disk_store(file_id: str, payload: bytes, media_type: str) -> None:
    """Best-effort atomic write: mime first, data last (the commit point)."""
    paths = _disk_paths(file_id)
    directory = _disk_dir
    if paths is None or directory is None:
        return
    data_path, mime_path = paths
    try:
        directory.mkdir(parents=True, exist_ok=True)
        mime_tmp = directory / f"{mime_path.name}.tmp"
        mime_tmp.write_text(media_type, encoding="utf-8")
        os.replace(mime_tmp, mime_path)
        data_tmp = directory / f"{data_path.name}.tmp"
        data_tmp.write_bytes(payload)
        os.replace(data_tmp, data_path)
    except OSError:
        logger.warning("Could not persist Telegram file %s to disk", file_id)


def _cache_put(file_id: str, data: bytes, media_type: str) -> None:
    global _file_cache_bytes
    previous = _file_cache.pop(file_id, None)
    if previous is not None:
        _file_cache_bytes -= len(previous[1])
    if len(data) > _CACHE_MAX_BYTES:
        return
    while _file_cache and _file_cache_bytes + len(data) > _CACHE_MAX_BYTES:
        _evicted_id, evicted = _file_cache.popitem(last=False)
        _file_cache_bytes -= len(evicted[1])
    _file_cache[file_id] = (time.monotonic(), data, media_type)
    _file_cache_bytes += len(data)


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
    """Download a file from Telegram (memory LRU → disk → network).

    Returns ``(bytes, media_type)``. The on-disk copy means each file is
    fetched from Telegram at most once for the lifetime of the install.
    """
    now = time.monotonic()
    cached = _file_cache.get(file_id)
    if cached is not None and now - cached[0] < _CACHE_TTL_SECONDS:
        _file_cache.move_to_end(file_id)
        return cached[1], cached[2]

    on_disk = _disk_load(file_id)
    if on_disk is not None:
        _cache_put(file_id, on_disk[0], on_disk[1])
        return on_disk

    try:
        tg_file = await bot.get_file(file_id)
        data = await tg_file.download_as_bytearray()
    except (TelegramError, OSError) as exc:
        raise HTTPException(status_code=502, detail="could not download from Telegram") from exc
    media_type = safe_media_type(mimetypes.guess_type(tg_file.file_path or "")[0])
    payload = bytes(data)
    _cache_put(file_id, payload, media_type)
    _disk_store(file_id, payload, media_type)
    return payload, media_type

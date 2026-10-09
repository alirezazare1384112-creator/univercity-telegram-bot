"""Database-backed PTB persistence for serverless (Vercel) deployments.

On a long-running process the default in-memory persistence is fine, but
serverless instances freeze between requests and lose their memory. This
store keeps conversations, user/chat data and the callback-data cache in
the same database as everything else (one JSON row per entry), so a cold
start resumes exactly where the previous request left off.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text
from telegram.ext import BasePersistence

from app.database.database import get_session

logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS persistence_store (
    kind TEXT NOT NULL,
    entry_key TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (kind, entry_key)
)
"""


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _loads(raw: str) -> Any:
    return json.loads(raw)


class DatabasePersistence(BasePersistence[Any, dict[str, Any], dict[str, Any]]):
    """JSON-per-row persistence over the project's async SQLAlchemy engine."""

    def __init__(self) -> None:
        super().__init__()
        self._bot: Any = None
        self._ready = False

    # ---- internals ----------------------------------------------------
    async def _ensure_table(self) -> None:
        if self._ready:
            return
        async with get_session() as session:
            await session.execute(text(_DDL))
            await session.commit()
        self._ready = True

    async def _load_kind(self, kind: str) -> dict[str, str]:
        await self._ensure_table()
        async with get_session() as session:
            rows = await session.execute(
                text(
                    "SELECT entry_key, value FROM persistence_store WHERE kind = :kind"
                ),
                {"kind": kind},
            )
            return {key: value for key, value in rows.all()}

    async def _put(self, kind: str, entry_key: str, value: Any) -> None:
        await self._ensure_table()
        async with get_session() as session:
            await session.execute(
                text(
                    "INSERT INTO persistence_store (kind, entry_key, value) "
                    "VALUES (:kind, :entry_key, :value) "
                    "ON CONFLICT (kind, entry_key) DO UPDATE SET value = :value"
                ),
                {"kind": kind, "entry_key": entry_key, "value": _dumps(value)},
            )
            await session.commit()

    async def _delete(self, kind: str, entry_key: str) -> None:
        await self._ensure_table()
        async with get_session() as session:
            await session.execute(
                text(
                    "DELETE FROM persistence_store WHERE kind = :kind "
                    "AND entry_key = :entry_key"
                ),
                {"kind": kind, "entry_key": entry_key},
            )
            await session.commit()

    # ---- BasePersistence API -------------------------------------------
    def set_bot(self, bot: Any) -> None:
        self._bot = bot

    async def get_bot_data(self) -> dict[str, Any]:
        rows = await self._load_kind("bot_data")
        return _loads(rows["main"]) if "main" in rows else {}

    async def update_bot_data(self, data: dict[str, Any]) -> None:
        # task handles inside bot_data are not serialisable; keep JSON-safe copy
        await self._put("bot_data", "main", {k: v for k, v in data.items()})

    async def refresh_bot_data(self, bot_data: dict[str, Any]) -> None:
        bot_data.clear()
        bot_data.update(await self.get_bot_data())

    async def get_chat_data(self) -> dict[int, dict[str, Any]]:
        rows = await self._load_kind("chat_data")
        return {int(key): _loads(value) for key, value in rows.items()}

    async def update_chat_data(self, chat_id: int, data: dict[str, Any]) -> None:
        await self._put("chat_data", str(chat_id), data)

    async def refresh_chat_data(self, chat_id: int, chat_data: dict[str, Any]) -> None:
        rows = await self._load_kind("chat_data")
        chat_data.clear()
        if str(chat_id) in rows:
            chat_data.update(_loads(rows[str(chat_id)]))

    async def get_user_data(self) -> dict[int, dict[str, Any]]:
        rows = await self._load_kind("user_data")
        return {int(key): _loads(value) for key, value in rows.items()}

    async def update_user_data(self, user_id: int, data: dict[str, Any]) -> None:
        await self._put("user_data", str(user_id), data)

    async def refresh_user_data(self, user_id: int, user_data: dict[str, Any]) -> None:
        rows = await self._load_kind("user_data")
        user_data.clear()
        if str(user_id) in rows:
            user_data.update(_loads(rows[str(user_id)]))

    async def drop_user_data(self, user_id: int) -> None:
        await self._delete("user_data", str(user_id))

    async def drop_chat_data(self, chat_id: int) -> None:
        await self._delete("chat_data", str(chat_id))

    async def get_conversations(self, name: str) -> dict[tuple[Any, ...], Any]:
        rows = await self._load_kind("conversation")
        if name not in rows:
            return {}
        raw = _loads(rows[name])
        # mapping keys are json-encoded lists ("[42, 7]") -> back to tuples
        return {tuple(_loads(key)): state for key, state in raw.items()}

    async def update_conversation(
        self, name: str, key: tuple[Any, ...], new_state: object
    ) -> None:
        rows = await self._load_kind("conversation")
        mapping: dict[str, Any] = _loads(rows[name]) if name in rows else {}
        store_key = _dumps(list(key))
        if new_state is None:
            mapping.pop(store_key, None)
        else:
            mapping[store_key] = new_state
        if mapping:
            await self._put("conversation", name, mapping)
        else:
            await self._delete("conversation", name)

    async def get_callback_data(
        self,
    ) -> tuple[list[tuple[str, float, dict[str, Any]]], dict[str, str]] | None:
        rows = await self._load_kind("callback_data")
        if "main" not in rows:
            return None
        cached, iq = _loads(rows["main"])
        return cached, iq

    async def update_callback_data(
        self, data: tuple[list[tuple[str, float, dict[str, Any]]], dict[str, str]]
    ) -> None:
        await self._put("callback_data", "main", data)

    async def refresh_callback_data(
        self, callback_data: Any
    ) -> None:
        stored = await self.get_callback_data()
        if stored is None:
            return
        loader = getattr(callback_data, "load_persistence_data", None)
        if loader is not None:
            loader(stored)
            return
        cache = getattr(callback_data, "data", None)
        index = getattr(callback_data, "index", None)
        if cache is None or index is None:
            return
        cache.clear()
        index.clear()
        cached, iq = stored
        cache.extend(cached)
        index.update(iq)

    async def update_persistence(self) -> None:
        # every update_* writes through immediately; nothing to flush
        return None

    async def flush(self) -> None:
        return None

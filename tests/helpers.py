"""Builders for Telegram update objects used in handler tests.

The objects are constructed locally; no network call is ever made, so a
fake token is completely safe.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from telegram import Bot, CallbackQuery, Chat, Document, Message, PhotoSize, Update, User

FAKE_BOT = Bot(token="123456:TEST-TOKEN-NOT-REAL")


def make_message(
    text: str | None,
    *,
    user_id: int = 111,
    username: str = "tester",
    first_name: str = "Tester",
    chat_id: int | None = None,
    message_id: int = 1,
    **message_kwargs,
) -> Message:
    user = User(id=user_id, is_bot=False, first_name=first_name, username=username)
    chat = Chat(id=chat_id if chat_id is not None else user_id, type="private")
    message = Message(
        message_id=message_id,
        date=datetime.now(UTC),
        chat=chat,
        from_user=user,
        text=text,
        **message_kwargs,
    )
    message.set_bot(FAKE_BOT)
    return message


def make_photo_update(
    file_id: str = "photo-file-id",
    file_unique_id: str = "photo-unique-id",
    caption: str | None = None,
    **kwargs,
) -> Update:
    """A message carrying a photo (two sizes, like Telegram does)."""
    photo = [
        PhotoSize(file_id + "-small", file_unique_id, 90, 60),
        PhotoSize(file_id, file_unique_id, 800, 600),
    ]
    message = make_message(None, photo=photo, caption=caption, **kwargs)
    update = Update(update_id=abs(hash((file_id, kwargs.get("user_id", 111)))) % 10**9, message=message)
    update.set_bot(FAKE_BOT)
    return update


def make_document_update(
    file_id: str = "doc-file-id",
    file_unique_id: str = "doc-unique-id",
    mime_type: str = "application/pdf",
    **kwargs,
) -> Update:
    """A message carrying an image document (a screenshot sent as a file)."""
    document = Document(
        file_id=file_id,
        file_unique_id=file_unique_id,
        file_name="schedule.png",
        mime_type=mime_type,
    )
    message = make_message(None, document=document, **kwargs)
    update = Update(update_id=abs(hash((file_id, kwargs.get("user_id", 111)))) % 10**9, message=message)
    update.set_bot(FAKE_BOT)
    return update


def make_text_update(text: str, **kwargs) -> Update:
    """A normal private message from a user."""
    message = make_message(text, **kwargs)
    update = Update(update_id=abs(hash((text, kwargs.get("user_id", 111)))) % 10**9, message=message)
    update.set_bot(FAKE_BOT)
    return update


def make_callback_update(data: str, text: str | None = None, **kwargs) -> Update:
    """A callback query coming from an inline keyboard button."""
    message = make_message(text, **kwargs)
    query = CallbackQuery(
        id="1",
        from_user=message.from_user,
        chat_instance="test-chat-instance",
        data=data,
        message=message,
    )
    query.set_bot(FAKE_BOT)
    update = Update(update_id=abs(hash((data, kwargs.get("user_id", 111)))) % 10**9, callback_query=query)
    update.set_bot(FAKE_BOT)
    return update


class FakeContext:
    """Minimal stand-in for ``ContextTypes.DEFAULT_TYPE``."""

    def __init__(self, user_data: dict | None = None) -> None:
        self.bot = AsyncMock()
        self.user_data = user_data if user_data is not None else {}
        self.args: list[str] = []
        self.match = None
        self.application = None

    @property
    def sent_messages(self) -> list[dict]:
        """Keyword arguments of every ``send_message`` call."""
        return [call.kwargs for call in self.bot.send_message.call_args_list]

    @property
    def sent_texts(self) -> list[str]:
        return [call.get("text", "") for call in self.sent_messages]

    @property
    def last_markup(self):
        marks = [call.get("reply_markup") for call in self.sent_messages if call.get("reply_markup")]
        return marks[-1] if marks else None

"""یک‌کانونه بودن: باز شدن یک ویژگی، ویژگیِ بازِ قبلی را می‌بندد."""

from __future__ import annotations

from telegram.ext import CommandHandler, ConversationHandler, MessageHandler

from app.bot.handlers import (
    focus_conversations,
    gpa,
    notes,
    register_handlers,
    schedule,
    start,
)
from app.bot.keyboards.main_menu import GPA, NOTES
from app.bot.middlewares import capture_user
from app.bot.states.note_states import NoteState
from app.bot.states.schedule_states import ScheduleState
from tests.helpers import FakeContext, make_text_update


class RecordingApp:
    """Captures every handler instead of talking to Telegram."""

    def __init__(self) -> None:
        self.added: list = []

    def add_handler(self, handler, group: int = 0) -> None:
        self.added.append((group, handler))


async def test_opening_notes_closes_the_background_schedule(db):
    schedule_conversation = schedule.build_conversation()
    notes_conversation = notes.build_conversation()
    focus_conversations([schedule_conversation, notes_conversation])

    update = make_text_update(NOTES, user_id=4101)
    schedule_key = schedule_conversation._get_key(update)
    schedule_conversation._conversations[schedule_key] = ScheduleState.MENU
    notes_key = notes_conversation._get_key(update)
    notes_conversation._conversations[notes_key] = NoteState.WIZARD

    context = FakeContext()
    await capture_user(update, context)
    entry = next(
        handler
        for handler in notes_conversation.entry_points
        if isinstance(handler, MessageHandler)
        and handler.filters is not None
        and handler.filters.check_update(update)
    )
    state = await entry.callback(update, context)

    # the background schedule screen is gone: its next photo can no longer
    # reach on_photo_received instead of the note wizard
    assert state == NoteState.MENU
    assert schedule_key not in schedule_conversation._conversations
    # the entering conversation keeps its own state (only siblings close)
    assert notes_conversation._conversations[notes_key] == NoteState.WIZARD


def test_announcements_outrank_the_notes_free_file_entry():
    app = RecordingApp()
    register_handlers(app)

    names = [
        handler.name
        for group, handler in app.added
        if group == 0 and isinstance(handler, ConversationHandler)
    ]
    assert names.index("announcements_conversation") < names.index("notes_conversation")
    assert names.index("schedule_conversation") < names.index("notes_conversation")


def test_navigation_entries_take_the_focus():
    app = RecordingApp()
    register_handlers(app)

    start_handler = next(
        handler
        for group, handler in app.added
        if group == 0 and isinstance(handler, CommandHandler) and "start" in handler.commands
    )
    assert start_handler.callback is not start.cmd_start

    gpa_entry = next(
        handler
        for group, handler in app.added
        if group == 0
        and isinstance(handler, MessageHandler)
        and handler.check_update(make_text_update(GPA, user_id=4103))
    )
    assert gpa_entry.callback is not gpa.gpa_handler

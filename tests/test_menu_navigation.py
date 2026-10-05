"""دکمه‌های منوی اصلی باید همیشه به ویژگی خودشان بروند — حتی وسط هر ویزارد."""

from __future__ import annotations

from telegram.ext import MessageHandler

from app.bot.handlers import (
    admin,
    announcements,
    calendar_events,
    courses,
    grades,
    links,
    notes,
    profile,
    reminders,
    schedule,
)
from app.bot.keyboards.main_menu import MENU_LABELS
from app.bot.states.schedule_states import ScheduleState
from tests.helpers import make_text_update

BUILDERS = (
    admin.build_conversation,
    announcements.build_conversation,
    calendar_events.build_conversation,
    courses.build_conversation,
    grades.build_conversation,
    links.build_conversation,
    notes.build_conversation,
    profile.build_conversation,
    reminders.build_conversation,
    schedule.build_conversation,
)


def test_no_wizard_step_swallows_a_main_menu_button():
    free = make_text_update("یک متن آزاد", user_id=1)
    for build in BUILDERS:
        conversation = build()
        for state, handlers in conversation.states.items():
            for handler in handlers:
                if not isinstance(handler, MessageHandler):
                    continue
                if handler.filters is None or not handler.filters.check_update(free):
                    continue
                for label in MENU_LABELS:
                    button = make_text_update(label, user_id=1)
                    assert not handler.filters.check_update(button), (
                        f"{build.__module__}.{state} swallows the menu button {label!r}"
                    )


def test_free_text_still_reaches_the_awaiting_step():
    conversation = schedule.build_conversation()
    waiting = conversation.states[ScheduleState.WAITING_PHOTO]
    free = make_text_update("سلام", user_id=1)

    assert any(
        isinstance(handler, MessageHandler)
        and handler.filters is not None
        and handler.filters.check_update(free)
        for handler in waiting
    )

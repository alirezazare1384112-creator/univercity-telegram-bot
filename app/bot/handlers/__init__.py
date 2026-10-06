"""Handler registration.

Every feature registers its handlers here, so ``app.main`` never has to
know about individual features. Order matters:

* group ``-1``: middleware (runs before everything else)
* group ``0``:  feature handlers, checked in registration order
* group ``1``:  fallback for unknown text (must stay last)

Only one feature may own the screen: every entry point is wrapped with
``open_exclusive`` so opening a feature closes the ones left open in the
background.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    TypeHandler,
    filters,
)

from app.bot.handlers import (
    admin,
    announcements,
    calendar_events,
    courses,
    gpa,
    grades,
    links,
    notes,
    profile,
    reminders,
    schedule,
    start,
)
from app.bot.helpers import open_exclusive
from app.bot.middlewares import capture_user


def build_conversations() -> list[ConversationHandler]:
    """Fresh instances of every feature conversation, in registration order."""
    return [
        courses.build_conversation(),
        grades.build_conversation(),
        schedule.build_conversation(),
        # announcements must precede notes: while its screen is open a
        # forwarded photo has to be saved, not claimed by the notes entry
        announcements.build_conversation(),
        # notes accepts stray files -> stays right after announcements
        notes.build_conversation(),
        profile.build_conversation(),
        reminders.build_conversation(),
        links.build_conversation(),
        calendar_events.build_conversation(),
        admin.build_conversation(),
    ]


def focus_conversations(conversations: list[ConversationHandler]) -> None:
    """Wrap every entry point so it steals the focus from its siblings."""
    for index, conversation in enumerate(conversations):
        siblings = [other for i, other in enumerate(conversations) if i != index]
        # the handlers are wrapped in place: ConversationHandler forbids
        # reassigning entry_points after initialization
        for entry in conversation.entry_points:
            open_exclusive(entry, siblings)


def register_handlers(app: Application) -> None:
    """Attach all bot handlers to the application."""

    # --- middleware ---------------------------------------------------
    app.add_handler(TypeHandler(Update, capture_user), group=-1)

    # --- features (built first so every entry can take the focus) ----
    conversations = build_conversations()
    focus_conversations(conversations)

    # --- core ---------------------------------------------------------
    app.add_handler(
        open_exclusive(CommandHandler(["start", "menu"], start.cmd_start), conversations),
        group=0,
    )
    app.add_handler(CommandHandler("help", start.cmd_help), group=0)

    # --- features (each phase appends its own registration here) ------
    gpa.register(app, conversations)
    for conversation in conversations:
        app.add_handler(conversation, group=0)

    # --- fallback (keep last) -----------------------------------------
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, start.fallback_text),
        group=1,
    )

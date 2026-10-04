"""Handler registration.

Every feature registers its handlers here, so ``app.main`` never has to
know about individual features. Order matters:

* group ``-1``: middleware (runs before everything else)
* group ``0``:  feature handlers, checked in registration order
* group ``1``:  fallback for unknown text (must stay last)
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, TypeHandler, filters

from app.bot.handlers import (
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
from app.bot.middlewares import capture_user


def register_handlers(app: Application) -> None:
    """Attach all bot handlers to the application."""

    # --- middleware ---------------------------------------------------
    app.add_handler(TypeHandler(Update, capture_user), group=-1)

    # --- core ---------------------------------------------------------
    app.add_handler(CommandHandler(["start", "menu"], start.cmd_start), group=0)
    app.add_handler(CommandHandler("help", start.cmd_help), group=0)

    # --- features (each phase appends its own registration here) ------
    gpa.register(app)
    app.add_handler(courses.build_conversation(), group=0)
    app.add_handler(grades.build_conversation(), group=0)
    app.add_handler(schedule.build_conversation(), group=0)
    # notes accepts stray files -> must be registered after the schedule
    app.add_handler(notes.build_conversation(), group=0)
    app.add_handler(profile.build_conversation(), group=0)
    app.add_handler(reminders.build_conversation(), group=0)
    app.add_handler(links.build_conversation(), group=0)
    app.add_handler(announcements.build_conversation(), group=0)
    app.add_handler(calendar_events.build_conversation(), group=0)

    # --- fallback (keep last) -----------------------------------------
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, start.fallback_text),
        group=1,
    )

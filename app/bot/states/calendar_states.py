"""Conversation states for the calendar section."""

from __future__ import annotations

from enum import Enum


class CalendarState(Enum):
    """📆 تقویم و کارهای آینده"""

    MENU = "calendar_menu"
    DONE = "calendar_done"
    DETAIL = "calendar_detail"
    WIZARD = "calendar_wizard"

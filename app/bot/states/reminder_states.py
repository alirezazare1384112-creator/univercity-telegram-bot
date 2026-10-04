"""Conversation states for the reminders section."""

from __future__ import annotations

from enum import Enum


class ReminderState(Enum):
    """⏰ یادآوری‌ها"""

    LIST = "reminders_list"
    DETAIL = "reminders_detail"
    WIZARD = "reminders_wizard"

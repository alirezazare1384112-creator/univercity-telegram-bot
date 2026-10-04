"""Conversation states for the weekly schedule section."""

from __future__ import annotations

from enum import Enum


class ScheduleState(Enum):
    """📅 برنامه هفتگی"""

    MENU = "schedule_menu"
    WAITING_PHOTO = "schedule_waiting_photo"

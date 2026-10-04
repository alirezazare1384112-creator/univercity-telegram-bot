"""Conversation states for the announcements section."""

from __future__ import annotations

from enum import Enum


class AnnouncementState(Enum):
    """📢 اطلاعیه‌ها"""

    MENU = "announcements_menu"
    DETAIL = "announcements_detail"
    # waiting for the forwarded post (or typed text) to be saved
    WAITING = "announcements_waiting"

"""Conversation states for the announcements section."""

from __future__ import annotations

from enum import Enum


class AnnouncementState(Enum):
    """📢 اطلاعیه‌ها"""

    MENU = "announcements_menu"
    DETAIL = "announcements_detail"
    # waiting for the forwarded post (or typed text) to be saved
    WAITING = "announcements_waiting"
    # the student's own channel subscription list
    CHANNELS = "announcements_channels"
    # waiting for a channel link to subscribe to
    CHANNEL_ADD = "announcements_channel_add"

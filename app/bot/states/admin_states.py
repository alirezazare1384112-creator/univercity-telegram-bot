"""Conversation states for the admin panel."""

from __future__ import annotations

from enum import Enum


class AdminState(Enum):
    """🛠 پنل ادمین"""

    MENU = "admin_menu"
    # waiting for the broadcast text
    WAITING = "admin_broadcast_waiting"

"""Conversation states for the university links section."""

from __future__ import annotations

from enum import Enum


class LinkState(Enum):
    """🔗 سامانه‌های دانشگاه"""

    MENU = "links_menu"
    MANAGE = "links_manage"
    DETAIL = "links_detail"
    WIZARD = "links_wizard"

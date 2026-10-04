"""Conversation states for the notes section."""

from __future__ import annotations

from enum import Enum


class NoteState(Enum):
    """📚 جزوه‌ها"""

    MENU = "notes_menu"
    DETAIL = "notes_detail"
    WIZARD = "notes_wizard"

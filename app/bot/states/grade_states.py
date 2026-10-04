"""Conversation states for the grades section."""

from __future__ import annotations

from enum import Enum


class GradeState(Enum):
    """📝 نمرات من"""

    PICK_COURSE = "grades_pick_course"
    ITEMS = "grades_items"
    DETAIL = "grades_item_detail"
    WIZARD = "grades_wizard"

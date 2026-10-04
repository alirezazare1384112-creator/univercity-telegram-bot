"""Conversation states for the courses section."""

from __future__ import annotations

from enum import Enum


class CourseState(Enum):
    """📚 درس‌های من"""

    MENU = "course_menu"          # list of courses
    WIZARD = "course_wizard"      # creating / editing one field
    DETAIL = "course_detail"      # one course, with edit/delete buttons

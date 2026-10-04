"""Conversation states (used by ``telegram.ext.ConversationHandler``)."""

from __future__ import annotations

from enum import Enum


class ProfileState(Enum):
    """Editing the student profile."""

    CHOOSING_FIELD = "profile_choosing_field"
    ENTERING_VALUE = "profile_entering_value"

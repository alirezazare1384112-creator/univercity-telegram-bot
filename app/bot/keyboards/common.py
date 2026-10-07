"""Reusable keyboard builders.

All labels live next to the keyboards so no feature ever hard-codes the
text of a button defined somewhere else.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

BACK = "🔙 بازگشت"
CANCEL = "❌ لغو"


def reply_keyboard(
    rows: list[list[str | KeyboardButton]], resize: bool = True
) -> ReplyKeyboardMarkup:
    """Build a reply keyboard from a list of rows of labels or buttons."""
    return ReplyKeyboardMarkup(
        [
            [label if isinstance(label, KeyboardButton) else KeyboardButton(label) for label in row]
            for row in rows
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="یک گزینه را انتخاب کنید" if resize else None,
    )


def inline_buttons(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    """Build an inline keyboard from ``[(label, callback_data), ...]`` rows."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(label, callback_data=data) for label, data in row]
            for row in rows
        ]
    )


def url_buttons(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    """Build an inline keyboard of ``[(label, url), ...]`` rows.

    Used by screens that open an external site instead of running a
    callback (university links, the GPA calculator, ...).
    """
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(label, url=url) for label, url in row]
            for row in rows
        ]
    )

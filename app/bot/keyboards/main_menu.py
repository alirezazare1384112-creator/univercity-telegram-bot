"""Main menu (reply keyboard) - single source of truth for menu labels."""

from __future__ import annotations

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
from telegram.ext import filters

from app.bot.keyboards.common import reply_keyboard
from app.config import get_settings

# --- labels -------------------------------------------------------------
SCHEDULE = "📅 برنامه هفتگی"
COURSES = "📚 درس‌های من"
GRADES = "📝 نمرات من"
GPA = "🧮 محاسبه معدل"
REMINDERS = "⏰ یادآوری‌ها"
CALENDAR = "📆 تقویم و کارهای آینده"
ANNOUNCEMENTS = "📢 اطلاعیه‌ها"
NOTES = "📚 جزوه‌ها"
LINKS = "🔗 سامانه‌های دانشگاه"
PROFILE = "👤 پروفایل"
MINI_APP = "📱 باز کردن مینی‌اپ"

MAIN_MENU_TITLE = "🎓 دستیار دانشجو\nمنوی اصلی — یک گزینه را انتخاب کنید:"

MENU_LABELS: tuple[str, ...] = (
    SCHEDULE,
    COURSES,
    GRADES,
    GPA,
    REMINDERS,
    CALENDAR,
    ANNOUNCEMENTS,
    NOTES,
    LINKS,
    PROFILE,
)


def menu_buttons_filter() -> filters.Filter:
    """Main-menu labels as a text filter - steps subtract it so any menu button always opens its own feature."""
    return filters.Text(list(MENU_LABELS))


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """The permanent main menu of the bot.

    When ``WEBAPP_URL`` points at an https address, the first row becomes a
    Telegram WebApp button that opens the Mini App (bot API rejects plain
    http or non-url values, so those are ignored).
    """
    rows: list[list[str | KeyboardButton]] = [
        [SCHEDULE],
        [COURSES, GRADES],
        [GPA],
        [REMINDERS, CALENDAR],
        [ANNOUNCEMENTS, NOTES],
        [LINKS, PROFILE],
    ]
    webapp_url = get_settings().webapp_url
    if webapp_url.startswith("https://"):
        rows.insert(
            0,
            [KeyboardButton(MINI_APP, web_app=WebAppInfo(url=webapp_url))],
        )
    return reply_keyboard(rows)


def mini_app_inline_keyboard() -> InlineKeyboardMarkup | None:
    """Inline variant of the Mini App button.

    Some Android clients open reply-keyboard WebApp buttons without auth
    data (empty ``initData``); inline ``web_app`` buttons are the
    longest-supported path, so /start offers both.
    """
    webapp_url = get_settings().webapp_url
    if not webapp_url.startswith("https://"):
        return None
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(MINI_APP, web_app=WebAppInfo(url=webapp_url))]]
    )

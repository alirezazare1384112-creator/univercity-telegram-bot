"""Main menu (reply keyboard) - single source of truth for menu labels."""

from __future__ import annotations

from telegram import ReplyKeyboardMarkup
from telegram.ext import filters

from app.bot.keyboards.common import reply_keyboard

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
    """The permanent main menu of the bot."""
    return reply_keyboard(
        [
            [SCHEDULE],
            [COURSES, GRADES],
            [GPA],
            [REMINDERS, CALENDAR],
            [ANNOUNCEMENTS, NOTES],
            [LINKS, PROFILE],
        ]
    )

"""Main menu (reply keyboard) - single source of truth for menu labels."""

from __future__ import annotations

from telegram import ReplyKeyboardMarkup

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

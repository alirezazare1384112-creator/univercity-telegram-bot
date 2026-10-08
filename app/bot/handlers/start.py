"""/start, /help and the main menu entry point."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.helpers import answer
from app.bot.keyboards.main_menu import (
    MAIN_MENU_TITLE,
    main_menu_keyboard,
    mini_app_inline_keyboard,
)

logger = logging.getLogger(__name__)

WELCOME_TEXT = """سلام {name}! 👋

به ربات «دستیار دانشجو» خوش آمدی.

از منوی پایین می‌توانی:
📅 برنامه هفتگی‌ات را ثبت کنی
📚 درس‌های این ترم را اضافه کنی
📝 نمراتت را ثبت کنی
⏰ یادآوری بسازی
📆 کارهای آینده را ببینی
📢 اطلاعیه‌های دانشگاه را دنبال کنی

همین حالا شروع کن 👇
"""

HELP_TEXT = """راهنمای ربات دستیار دانشجو 🎓

/start  نمایش منوی اصلی
/help   نمایش همین پیام
/admin  پنل ادمین (فقط مدیر)

منوی اصلی:
📅 برنامه هفتگی — ثبت و مشاهده عکس برنامه
📚 درس‌های من — افزودن و ویرایش درس‌های ترم
📝 نمرات من — ثبت آیتم‌های نمره هر درس
🧮 محاسبه معدل — صفحهٔ معدل داخل مینی‌اپ (معدل ترم/کل + سوابق)
⏰ یادآوری‌ها — یادآوری کارها با زمان‌بندی
📆 تقویم و کارهای آینده — امتحان، کوئیز، تمرین
📢 اطلاعیه‌ها — اطلاعیه‌های کانال دانشگاه
📚 جزوه‌ها — فایل‌های درسی
🔗 سامانه‌های دانشگاه — لینک سامانه‌ها
👤 پروفایل — اطلاعات دانشجویی
"""


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.effective_user
    name = (tg_user.first_name or tg_user.username or "دوست عزیز") if tg_user else "دوست عزیز"
    is_new = bool(context.user_data.get("is_new_user", False))

    greeting = WELCOME_TEXT.format(name=name)
    if not is_new:
        greeting = f"خوش برگشتی {name}! 👋\n\n" + WELCOME_TEXT.split("\n", 1)[1].lstrip("\n")

    await answer(update, context, greeting, reply_markup=main_menu_keyboard())
    inline = mini_app_inline_keyboard()
    if inline is not None:
        await answer(
            update,
            context,
            "یا مینی‌اپ را از این دکمه باز کن 👇",
            reply_markup=inline,
        )
    logger.info("User %s started the bot (new=%s)", getattr(tg_user, "id", "?"), is_new)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await answer(update, context, HELP_TEXT, reply_markup=main_menu_keyboard())


async def fallback_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unknown text: guide the user instead of ignoring him."""
    await answer(
        update,
        context,
        f"{MAIN_MENU_TITLE}\n\nاگر دکمه‌ای را نمی‌بینی /start را بزن.",
        reply_markup=main_menu_keyboard(),
    )

"""🧮 محاسبه معدل - link to the external GPA calculator website.

The bot does **not** calculate the GPA itself. The URL lives in ``.env``
(``GPA_CALCULATOR_URL``) and is never hard-coded in the source.
"""

from __future__ import annotations

import logging
import urllib.parse

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes, MessageHandler, filters

from app.bot.helpers import answer
from app.bot.keyboards.main_menu import GPA, main_menu_keyboard
from app.config import get_settings

logger = logging.getLogger(__name__)

BUTTON_LABEL = "🌐 باز کردن سایت محاسبه معدل"


def _valid_url(url: str) -> bool:
    try:
        parts = urllib.parse.urlparse(url)
    except ValueError:  # pragma: no cover - urlparse is very forgiving
        return False
    return parts.scheme in ("http", "https") and bool(parts.netloc)


async def gpa_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_settings()
    url = settings.gpa_calculator_url

    if not url:
        await answer(
            update,
            context,
            "آدرس سایت محاسبه معدل هنوز توسط مدیر ربات تنظیم نشده است.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if not _valid_url(url):
        logger.error("GPA_CALCULATOR_URL is not a valid http(s) URL")
        await answer(
            update,
            context,
            "آدرس سایت محاسبه معدل نامعتبر است. لطفاً با مدیر ربات تماس بگیر.",
            reply_markup=main_menu_keyboard(),
        )
        return

    markup = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(BUTTON_LABEL, url=url)],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="gpa:back")],
        ]
    )
    await answer(
        update,
        context,
        "🧮 محاسبه معدل\n\n"
        "برای محاسبه معدل، ریزنمرات خود را در سایت زیر وارد کن:\n"
        f"{url}\n\n"
        "روی دکمه زیر بزن تا سایت باز شود.",
        reply_markup=markup,
    )


async def gpa_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query is not None:
        await update.callback_query.answer()
    await answer(update, context, "به منوی اصلی برگشتی 👇", reply_markup=main_menu_keyboard())


def register(app) -> None:
    """The GPA section is a simple handler, no conversation needed."""
    app.add_handler(MessageHandler(filters.Text([GPA]), gpa_handler), group=0)
    app.add_handler(CallbackQueryHandler(gpa_back, pattern=r"^gpa:back$"), group=0)

"""🧮 محاسبه معدل - open the built-in GPA page inside the Mini App.

Primary path: ``{WEBAPP_URL}/#/gpa`` (the calculator shipped with the Mini App).
Fallback: ``GPA_CALCULATOR_URL`` from ``.env`` when no https WEBAPP_URL exists.
Neither URL is ever hard-coded in the source.
"""

from __future__ import annotations

import logging
import urllib.parse

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.bot.helpers import answer, open_exclusive
from app.bot.keyboards.main_menu import GPA, main_menu_keyboard
from app.config import get_settings

logger = logging.getLogger(__name__)

MINI_APP_BUTTON = "📱 باز کردن صفحهٔ معدل"
EXTERNAL_BUTTON = "🌐 باز کردن سایت محاسبه معدل"


def _valid_url(url: str) -> bool:
    try:
        parts = urllib.parse.urlparse(url)
    except ValueError:  # pragma: no cover - urlparse is very forgiving
        return False
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def _mini_app_url(webapp_url: str) -> str:
    """GPA route of the Mini App for an https WEBAPP_URL, else empty string."""
    if not webapp_url.startswith("https://"):
        return ""
    return f"{webapp_url}/#/gpa"


async def gpa_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_settings()

    mini_url = _mini_app_url(settings.webapp_url)
    if mini_url:
        markup = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton(MINI_APP_BUTTON, web_app=WebAppInfo(url=mini_url))],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="gpa:back")],
            ]
        )
        await answer(
            update,
            context,
            "🧮 محاسبه معدل\n\n"
            "نمرات و تعداد واحد دروس را داخل مینی‌اپ وارد کن تا معدل ترم جاری، "
            "معدل کل و سوابق ترم‌ها محاسبه شود.\n\n"
            "روی دکمهٔ زیر بزن تا صفحهٔ معدل باز شود.",
            reply_markup=markup,
        )
        return

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
            [InlineKeyboardButton(EXTERNAL_BUTTON, url=url)],
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


def register(app, conversations: list[ConversationHandler]) -> None:
    """The GPA section is a simple handler, no conversation needed."""
    handler = MessageHandler(filters.Text([GPA]), gpa_handler)
    app.add_handler(open_exclusive(handler, conversations), group=0)
    app.add_handler(CallbackQueryHandler(gpa_back, pattern=r"^gpa:back$"), group=0)

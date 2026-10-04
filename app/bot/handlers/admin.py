"""🛠 پنل ادمین - admin panel: stats, users, broadcast and Eitaa sync.

Access comes from the ``admins`` table; ids listed in ``ADMIN_IDS`` are
accepted as well and are stored there on the first ``/admin`` (bootstrap).
"""

from __future__ import annotations

import logging

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.bot.helpers import answer
from app.bot.keyboards.common import inline_buttons
from app.bot.keyboards.main_menu import main_menu_keyboard
from app.bot.states.admin_states import AdminState
from app.config import get_settings
from app.database.database import get_session
from app.database.repositories import AdminRepository, StatsRepository, UserRepository
from app.services.eitaa_sync import sync_channels

logger = logging.getLogger(__name__)

STATS = "📊 آمار سامانه"
USERS = "👥 کاربران"
BROADCAST = "📢 ارسال همگگانی"
SYNC = "🔁 همگام‌سازی ایتا"
CLOSE = "✖️ بستن"

PANEL_TITLE = "🛠 پنل ادمین\nیک گزینه را انتخاب کن:"
BROADCAST_PROMPT = (
    "متن پیام همگگانی را بفرست؛ برای همهٔ کاربران فعال ارسال می‌شود.\n"
    "برای انصراف /cancel یا /admin را بزن."
)
SYNC_DISABLED = "همگام‌سازی ایتا تنظیم نشده است (EITAA_SYNC_URLS خالی است)."
CLOSED_TEXT = "پنل ادمین بسته شد."
USERS_LIMIT = 10


def _panel_keyboard() -> InlineKeyboardMarkup:
    return inline_buttons(
        [
            [(STATS, "adm:stats"), (USERS, "adm:users")],
            [(BROADCAST, "adm:broadcast"), (SYNC, "adm:sync")],
            [(CLOSE, "adm:close")],
        ]
    )


async def _is_admin(update: Update) -> bool:
    user = update.effective_user
    if user is None:
        return False
    async with get_session() as session:
        return await AdminRepository(session).is_admin(user.id)


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = update.effective_user
    if tg_user is None:
        return None
    async with get_session() as session:
        repo = AdminRepository(session)
        if not await repo.is_admin(tg_user.id):
            return None
        await repo.upsert(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
        )
    await answer(update, context, PANEL_TITLE, reply_markup=_panel_keyboard())
    return AdminState.MENU


async def on_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _is_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    if query is not None:
        await query.answer()
    async with get_session() as session:
        totals = await StatsRepository(session).totals()
    lines = [
        STATS,
        f"کاربران: {totals['users']} (فعال: {totals['active_users']})",
        f"ادمین‌ها: {totals['admins']}",
        f"درس‌ها: {totals['courses']}",
        f"نمرات: {totals['grades']}",
        f"یادآوری‌ها: {totals['reminders']}",
        f"اطلاعیه‌ها: {totals['announcements']}",
        f"جزوه‌ها: {totals['notes']}",
        f"لینک‌ها: {totals['links']}",
        f"رویدادهای تقویم: {totals['events']}",
        f"برنامه هفتگی: {totals['schedules']}",
    ]
    await answer(update, context, "\n".join(lines), reply_markup=_panel_keyboard())
    return AdminState.MENU


async def on_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _is_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    if query is not None:
        await query.answer()
    async with get_session() as session:
        repo = UserRepository(session)
        total = await repo.count()
        active = await repo.count(active_only=True)
        users = await repo.list_users(limit=USERS_LIMIT)
    lines = [f"👥 کاربران — کل: {total}، فعال: {active}"]
    for index, user in enumerate(users, start=1):
        name = (
            " ".join(part for part in (user.first_name, user.last_name) if part)
            or "بدون نام"
        )
        handle = f"@{user.username}" if user.username else "بدون آیدی"
        status = "فعال" if user.is_active else "غیرفعال"
        lines.append(f"{index}. {name} | {handle} | tg: {user.telegram_id} | {status}")
    if total > USERS_LIMIT:
        lines.append(f"… {USERS_LIMIT} مورد آخر نمایش داده شد.")
    await answer(update, context, "\n".join(lines), reply_markup=_panel_keyboard())
    return AdminState.MENU


async def on_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _is_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    if query is not None:
        await query.answer()
    await answer(update, context, BROADCAST_PROMPT)
    return AdminState.WAITING


async def on_broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _is_admin(update):
        return ConversationHandler.END
    message = update.effective_message
    text = (message.text or "").strip() if message is not None else ""
    if not text:
        return AdminState.WAITING
    user = update.effective_user
    async with get_session() as session:
        ids = await UserRepository(session).list_active_telegram_ids()
    sent = 0
    failed = 0
    for telegram_id in ids:
        try:
            await context.bot.send_message(
                chat_id=telegram_id, text=text, disable_web_page_preview=True
            )
            sent += 1
        except Exception:  # noqa: BLE001 - blocked users must not stop the loop
            failed += 1
    logger.info(
        "Broadcast by admin %s: sent=%s failed=%s",
        getattr(user, "id", "?"),
        sent,
        failed,
    )
    summary = f"✅ پیام برای {sent} کاربر ارسال شد."
    if failed:
        summary += f"\n❌ ناموفق: {failed}"
    await answer(update, context, summary, reply_markup=_panel_keyboard())
    return AdminState.MENU


async def on_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _is_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    if query is not None:
        await query.answer()
    settings = get_settings()
    if not settings.eitaa_sync_urls:
        await answer(update, context, SYNC_DISABLED, reply_markup=_panel_keyboard())
        return AdminState.MENU
    total = await sync_channels(settings.eitaa_sync_urls)
    await answer(
        update,
        context,
        f"✅ همگام‌سازی انجام شد — {total} اطلاعیه جدید.",
        reply_markup=_panel_keyboard(),
    )
    return AdminState.MENU


async def close_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query is not None:
        await update.callback_query.answer()
    await answer(update, context, CLOSED_TEXT, reply_markup=main_menu_keyboard())
    return ConversationHandler.END


def build_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("admin", cmd_admin)],
        states={
            AdminState.MENU: [
                CallbackQueryHandler(on_stats, pattern=r"^adm:stats$"),
                CallbackQueryHandler(on_users, pattern=r"^adm:users$"),
                CallbackQueryHandler(on_broadcast_start, pattern=r"^adm:broadcast$"),
                CallbackQueryHandler(on_sync, pattern=r"^adm:sync$"),
                CallbackQueryHandler(close_panel, pattern=r"^adm:close$"),
                CommandHandler("admin", cmd_admin),
            ],
            AdminState.WAITING: [
                CommandHandler(["admin", "cancel"], cmd_admin),
                MessageHandler(filters.TEXT & ~filters.COMMAND, on_broadcast_text),
            ],
        },
        fallbacks=[CommandHandler(["start", "cancel"], close_panel)],
        name="admin_conversation",
        persistent=False,
        allow_reentry=True,
    )

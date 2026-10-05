"""📅 برنامه هفتگی - store and resend the weekly schedule photo."""

from __future__ import annotations

import logging

from telegram import Message, ReplyKeyboardRemove, Update
from telegram.error import TelegramError
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.bot.helpers import answer, chat_id, current_user_id
from app.bot.keyboards.common import BACK, CANCEL, inline_buttons, reply_keyboard
from app.bot.keyboards.main_menu import SCHEDULE, main_menu_keyboard, menu_buttons_filter
from app.bot.states.schedule_states import ScheduleState
from app.database.database import get_session
from app.database.repositories import WeeklyScheduleRepository

logger = logging.getLogger(__name__)

NO_SCHEDULE_TEXT = (
    "هنوز برنامه هفتگی‌ای ثبت نکرده‌ای.\n\n"
    "عکس برنامه این ترم را بفرست تا همیشه در دسترس داشته باشی."
)
WAITING_TEXT = (
    "📤 عکس برنامه هفتگی را بفرست.\n\n"
    "نکته: می‌توانی عکس را همراه با کپشن (مثلاً «ترم ۱۴۰۴») بفرستی.\n"
    f"برای انصراف {CANCEL} را بزن."
)


def _view_keyboard(has_schedule: bool):
    rows: list[list[tuple[str, str]]] = []
    if has_schedule:
        rows.append([("📤 جایگزینی برنامه", "schedule:add")])
        rows.append([("🗑 حذف برنامه", "schedule:delete")])
    else:
        rows.append([("📤 ارسال عکس برنامه هفتگی", "schedule:add")])
    rows.append([(BACK, "schedule:exit")])
    return inline_buttons(rows)


async def _load_schedule(user_id: int):
    async with get_session() as session:
        return await WeeklyScheduleRepository(session).get_active(user_id)


async def _send_schedule(
    update: Update, context: ContextTypes.DEFAULT_TYPE, schedule, reply_markup=None
) -> bool:
    """Resend the stored schedule. Returns False when Telegram rejects it."""
    target = chat_id(update)
    if target is None:
        return False
    try:
        if schedule.file_type == "document":
            await context.bot.send_document(
                chat_id=target,
                document=schedule.telegram_file_id,
                caption=schedule.caption,
                reply_markup=reply_markup,
            )
        else:
            await context.bot.send_photo(
                chat_id=target,
                photo=schedule.telegram_file_id,
                caption=schedule.caption,
                reply_markup=reply_markup,
            )
        return True
    except TelegramError:
        logger.warning("Could not resend schedule of chat %s", target)
        return False


async def _show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    schedule = await _load_schedule(user_id)
    keyboard = _view_keyboard(has_schedule=schedule is not None)

    if schedule is None:
        await answer(update, context, NO_SCHEDULE_TEXT, reply_markup=keyboard)
        return ScheduleState.WAITING_PHOTO

    # the buttons ride on the photo itself - one message instead of two
    sent = await _send_schedule(update, context, schedule, reply_markup=keyboard)
    if not sent:
        await answer(
            update,
            context,
            "⚠️ برنامه ثبت شده بود اما ارسال آن ممکن نشد.",
            reply_markup=keyboard,
        )
    return ScheduleState.MENU


async def schedule_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point - the 📅 برنامه هفتگی button."""
    user_id = await current_user_id(update, context)
    if user_id is None:
        await answer(update, context, "ابتدا /start را بزن.")
        return ConversationHandler.END
    return await _show_menu(update, context, user_id)


async def on_add_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    context.user_data["schedule_awaiting"] = True
    await answer(update, context, WAITING_TEXT, reply_markup=reply_keyboard([[CANCEL]]))
    return ScheduleState.WAITING_PHOTO


async def on_photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message: Message | None = update.effective_message
    user_id = await current_user_id(update, context)
    if message is None or user_id is None:
        return ConversationHandler.END

    file_id: str | None = None
    file_unique_id: str | None = None
    file_type = "photo"

    if message.photo:
        # the last item is the highest quality version
        best = message.photo[-1]
        file_id, file_unique_id = best.file_id, best.file_unique_id
    elif message.document is not None:
        file_id = message.document.file_id
        file_unique_id = message.document.file_unique_id
        file_type = "document"

    if file_id is None:  # pragma: no cover - filter should prevent this
        await answer(update, context, "این یک فایل تصویری نیست. لطفاً عکس بفرست.")
        return ScheduleState.WAITING_PHOTO

    caption = message.caption or message.text
    async with get_session() as session:
        await WeeklyScheduleRepository(session).save(
            user_id=user_id,
            telegram_file_id=file_id,
            file_unique_id=file_unique_id,
            file_type=file_type,
            caption=caption,
        )

    context.user_data.pop("schedule_awaiting", None)
    await answer(
        update,
        context,
        "✅ برنامه هفتگی با موفقیت ذخیره شد.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return await _show_menu(update, context, user_id)


async def on_text_while_waiting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.effective_message.text or "").strip()
    if text in (CANCEL, BACK, "/cancel"):
        user_id = await current_user_id(update, context)
        if user_id is None:
            return ConversationHandler.END
        await answer(
            update, context, "ارسال عکس لغو شد.", reply_markup=ReplyKeyboardRemove()
        )
        return await _show_menu(update, context, user_id)
    await answer(
        update,
        context,
        "لطفاً یک عکس بفرست (📎 attach -> Photo) یا دکمه لغو را بزن.",
        reply_markup=reply_keyboard([[CANCEL]]),
    )
    return ScheduleState.WAITING_PHOTO


async def on_delete_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    await answer(
        update,
        context,
        "برنامه هفتگی حذف شود؟ این عملیات قابل بازگشت نیست.",
        reply_markup=inline_buttons(
            [
                [("✅ بله، حذف شود", "schedule:delete:yes")],
                [(CANCEL, "schedule:delete:no")],
            ]
        ),
    )
    return ScheduleState.MENU


async def on_delete_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END

    async with get_session() as session:
        deleted = await WeeklyScheduleRepository(session).delete_active(user_id)

    text = "✅ برنامه هفتگی حذف شد." if deleted else " برنامه‌ای برای حذف وجود نداشت."
    await answer(update, context, text, reply_markup=_view_keyboard(has_schedule=False))
    return ScheduleState.WAITING_PHOTO


async def on_delete_cancelled(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    await answer(update, context, "حذف انجام نشد.")
    return await _show_menu(update, context, user_id)


async def exit_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query is not None:
        await update.callback_query.answer()
    context.user_data.pop("schedule_awaiting", None)
    await answer(update, context, "به منوی اصلی برگشتی 👇", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("schedule_awaiting", None)
    await answer(update, context, "عملیات لغو شد.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


def build_conversation() -> ConversationHandler:
    photo_filter = filters.PHOTO | filters.Document.ALL
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Text([SCHEDULE]), schedule_menu),
            CallbackQueryHandler(schedule_menu, pattern=r"^schedule:view$"),
        ],
        states={
            ScheduleState.MENU: [
                CallbackQueryHandler(on_add_clicked, pattern=r"^schedule:add$"),
                CallbackQueryHandler(on_delete_clicked, pattern=r"^schedule:delete$"),
                CallbackQueryHandler(
                    on_delete_confirmed, pattern=r"^schedule:delete:yes$"
                ),
                CallbackQueryHandler(
                    on_delete_cancelled, pattern=r"^schedule:delete:no$"
                ),
                CallbackQueryHandler(exit_schedule, pattern=r"^schedule:exit$"),
                # a photo/document sent while browsing replaces the schedule
                MessageHandler(photo_filter, on_photo_received),
                MessageHandler(filters.Text([SCHEDULE]), schedule_menu),
            ],
            ScheduleState.WAITING_PHOTO: [
                MessageHandler(photo_filter, on_photo_received),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_buttons_filter(), on_text_while_waiting),
                CallbackQueryHandler(on_add_clicked, pattern=r"^schedule:add$"),
                CallbackQueryHandler(
                    on_delete_confirmed, pattern=r"^schedule:delete:yes$"
                ),
                CallbackQueryHandler(exit_schedule, pattern=r"^schedule:exit$"),
            ],
        },
        fallbacks=[
            CommandHandler(["start", "cancel"], cancel_conversation),
            MessageHandler(filters.Text([BACK]), cancel_conversation),
        ],
        name="schedule_conversation",
        persistent=False,
        allow_reentry=True,
    )

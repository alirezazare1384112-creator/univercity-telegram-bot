"""👤 پروفایل - view and edit the student profile."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.bot.helpers import answer
from app.bot.keyboards.common import BACK, CANCEL, inline_buttons, reply_keyboard
from app.bot.keyboards.main_menu import PROFILE, main_menu_keyboard, menu_buttons_filter
from app.bot.states.profile_states import ProfileState
from app.database.database import get_session
from app.database.repositories import UserRepository
from app.utils.validation import PROFILE_FIELD_LABELS, validate_profile_field

logger = logging.getLogger(__name__)

_FIELD_ORDER = ("student_number", "field_of_study", "university", "semester")

_EMPTY = "—"


def _profile_text(user) -> str:
    def show(value: str | None) -> str:
        return value if value else _EMPTY

    username = f"@{user.username}" if user.username else _EMPTY
    lines = [
        "👤 پروفایل دانشجویی",
        "",
        f"📛 نام: {show(user.first_name)} {show(user.last_name)}".rstrip(),
        f"🆔 یوزرنیم: {username}",
        f"🎓 شماره دانشجویی: {show(user.student_number)}",
        f"📚 رشته: {show(user.field_of_study)}",
        f"🏫 دانشگاه: {show(user.university)}",
        f"🗓 ترم: {show(user.semester)}",
        "",
        "برای ویرایش، یکی از گزینه‌ها را انتخاب کن:",
    ]
    return "\n".join(lines)


def _edit_keyboard():
    rows = [
        [(f"🎓 {PROFILE_FIELD_LABELS['student_number']}", "profile:field:student_number")],
        [(f"📚 {PROFILE_FIELD_LABELS['field_of_study']}", "profile:field:field_of_study")],
        [(f"🏫 {PROFILE_FIELD_LABELS['university']}", "profile:field:university")],
        [(f"🗓 {PROFILE_FIELD_LABELS['semester']}", "profile:field:semester")],
        [(BACK, "profile:exit")],
    ]
    return inline_buttons(rows)


async def _get_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = update.effective_user
    if tg_user is None:
        return None
    async with get_session() as session:
        return await UserRepository(session).get_by_telegram_id(tg_user.id)


async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point: called from the 👤 پروفایل menu button or inline 'view'."""
    user = await _get_user(update, context)
    if user is None:
        await answer(update, context, "ابتدا /start را بزن تا ثبت نامت انجام شود.")
        return ConversationHandler.END

    if update.callback_query is not None:
        await update.callback_query.answer()
        await answer(update, context, _profile_text(user), reply_markup=_edit_keyboard())
    else:
        await answer(
            update,
            context,
            _profile_text(user),
            reply_markup=reply_keyboard([[PROFILE, BACK]]),
        )
    return ProfileState.CHOOSING_FIELD


async def on_field_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None:  # pragma: no cover - defensive
        return ConversationHandler.END
    await query.answer()

    data = (query.data or "").split(":")
    if len(data) != 3 or data[2] not in PROFILE_FIELD_LABELS:
        return ProfileState.CHOOSING_FIELD

    context.user_data["profile_field"] = data[2]
    label = PROFILE_FIELD_LABELS[data[2]]
    await answer(
        update,
        context,
        f"مقدار جدید «{label}» را بفرست.\n\nمثال: 402123456\n\nیا {CANCEL} را بزن.",
        reply_markup=reply_keyboard([[CANCEL]]),
    )
    return ProfileState.ENTERING_VALUE


async def on_value_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.effective_message.text or "").strip()

    if text in (CANCEL, BACK, "/cancel"):
        context.user_data.pop("profile_field", None)
        await show_profile(update, context)
        return ProfileState.CHOOSING_FIELD

    field = context.user_data.get("profile_field")
    if field not in PROFILE_FIELD_LABELS:  # pragma: no cover - defensive
        await show_profile(update, context)
        return ProfileState.CHOOSING_FIELD

    ok, value, error = validate_profile_field(field, text)
    if not ok:
        await answer(
            update,
            context,
            f"⚠️ {error}\n\nدوباره تلاش کن یا {CANCEL} را بزن.",
            reply_markup=reply_keyboard([[CANCEL]]),
        )
        return ProfileState.ENTERING_VALUE

    tg_user = update.effective_user
    async with get_session() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(tg_user.id)
        if user is None:  # pragma: no cover - defensive
            await answer(update, context, "کاربر پیدا نشد. دوباره /start بزن.")
            return ConversationHandler.END
        await repo.update_profile(user, **{field: value})

    context.user_data.pop("profile_field", None)
    await answer(update, context, f"✅ «{PROFILE_FIELD_LABELS[field]}» با موفقیت ذخیره شد.")
    await show_profile(update, context)
    return ProfileState.CHOOSING_FIELD


async def exit_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query is not None:
        await update.callback_query.answer()
    context.user_data.pop("profile_field", None)
    await answer(update, context, "به منوی اصلی برگشتی 👇", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("profile_field", None)
    await answer(update, context, "عملیات لغو شد.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


def build_conversation() -> ConversationHandler:
    """Conversation for the profile section."""
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Text([PROFILE]), show_profile),
            CallbackQueryHandler(show_profile, pattern=r"^profile:view$"),
        ],
        states={
            ProfileState.CHOOSING_FIELD: [
                CallbackQueryHandler(on_field_chosen, pattern=r"^profile:field:"),
                CallbackQueryHandler(exit_profile, pattern=r"^profile:exit$"),
                MessageHandler(filters.Text([PROFILE]), show_profile),
            ],
            ProfileState.ENTERING_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_buttons_filter(), on_value_received),
            ],
        },
        fallbacks=[
            CommandHandler(["start", "cancel"], cancel_conversation),
            MessageHandler(filters.Text([BACK]), cancel_conversation),
        ],
        name="profile_conversation",
        persistent=False,
        allow_reentry=True,
    )

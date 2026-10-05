"""⏰ یادآوری‌ها - create, edit, pause and delete reminders."""

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

from app.bot.helpers import answer, current_user_id
from app.bot.keyboards.common import BACK, CANCEL, inline_buttons
from app.bot.keyboards.main_menu import REMINDERS, main_menu_keyboard, menu_buttons_filter
from app.bot.states.reminder_states import ReminderState
from app.config import get_settings
from app.database.database import get_session
from app.database.models.reminder import (
    ALERT_AT_TIME,
    ALERT_LABELS,
    ALERT_OFFSETS,
    REPEAT_LABELS,
    REPEAT_NONE,
    REPEAT_TYPES,
)
from app.database.repositories import CourseRepository, ReminderRepository
from app.services.reminder_service import alert_offsets_of, sync_notifications
from app.utils.datetime_utils import format_jalali, parse_reminder_datetime, relative_label
from app.utils.validation import validate_short_text

logger = logging.getLogger(__name__)

TEXT_FIELDS: tuple[str, ...] = ("title", "datetime", "description")
CREATE_FIELDS: tuple[str, ...] = ("title", "datetime", "course", "repeat", "description", "alerts")

# wizard field -> database column
FIELD_TO_MODEL: dict[str, str] = {
    "title": "title",
    "datetime": "reminder_datetime",
    "course": "course_id",
    "repeat": "repeat_type",
    "description": "description",
}

FIELD_LABELS: dict[str, str] = {
    "title": "عنوان",
    "datetime": "زمان",
    "course": "درس مرتبط",
    "repeat": "تکرار",
    "description": "توضیح",
    "alerts": "هشدارها",
}

PROMPTS: dict[str, str] = {
    "title": "عنوان یادآوری را بنویس.\nمثال: تحویل پاورپوینت پایگاه داده",
    "datetime": (
        "زمان یادآوری (تاریخ + ساعت) را بنویس.\n"
        "مثال‌ها:\n"
        "• فردا ساعت 18:30\n"
        "• امروز 20:00\n"
        "• 1404/07/05 ساعت 9"
    ),
    "description": "توضیح (اختیاری).\nبرای رد شدن دکمه «⏭ رد شد» را بزن.",
}
ALERTS_PROMPT = "کدام هشدارها فعال شوند؟ (می‌توانی چند مورد را انتخاب کنی)"
COURSE_PROMPT = "این یادآوری به کدام درس مرتبط است؟"
REPEAT_PROMPT = "چند بار تکرار شود؟"

SKIP = "⏭ رد شد"
ADD_REMINDER = "➕ یادآوری جدید"


# --- text builders ------------------------------------------------------
def _pause_label(is_active: bool) -> str:
    return "⏸ غیرفعال کردن" if is_active else "▶️ فعال کردن"


def _list_text(reminders: list) -> str:
    if not reminders:
        return (
            "هنوز یادآوری‌ای نساخته‌ای.\n\n"
            f"با دکمه «{ADD_REMINDER}» اولین یادآوری‌ات را بساز."
        )
    tz = get_settings().timezone
    lines = ["⏰ یادآوری‌های من", ""]
    for index, reminder in enumerate(reminders, start=1):
        mark = "" if reminder.is_active else " ⏸"
        label = relative_label(reminder.reminder_datetime, tz)
        suffix = f" ({label})" if label else ""
        lines.append(
            f"{index}){mark} {reminder.title} — "
            f"{format_jalali(reminder.reminder_datetime, tz)}{suffix}"
        )
    return "\n".join(lines)


def _reminder_text(reminder, offsets: list[str], course_name: str | None) -> str:
    tz = get_settings().timezone
    label = relative_label(reminder.reminder_datetime, tz)
    alerts = "، ".join(ALERT_LABELS.get(offset, offset) for offset in offsets) or "—"
    lines = [
        "⏰ یادآوری",
        "",
        f"📌 عنوان: {reminder.title}",
        f"🕒 زمان: {format_jalali(reminder.reminder_datetime, tz)}"
        + (f" ({label})" if label else ""),
        f"🔁 تکرار: {REPEAT_LABELS.get(reminder.repeat_type, reminder.repeat_type)}",
        f"📎 درس: {course_name or '—'}",
        f"🔔 هشدارها: {alerts}",
        f"📝 توضیح: {reminder.description or '—'}",
        "وضعیت: فعال ✅" if reminder.is_active else "وضعیت: متوقف ⏸",
    ]
    return "\n".join(lines)


# --- keyboards ----------------------------------------------------------
def _text_keyboard(field: str):
    rows: list[list[tuple[str, str]]] = []
    if field == "description":
        rows.append([(SKIP, "rem:skip")])
    rows.append([(CANCEL, "rem:cancel")])
    return inline_buttons(rows)


def _detail_keyboard(reminder_id: int, is_active: bool):
    rows: list[list[tuple[str, str]]] = [[(_pause_label(is_active), f"rem:pause:{reminder_id}")]]
    rows.append(
        [
            ("✏️ عنوان", f"rem:edit:{reminder_id}:title"),
            ("✏️ زمان", f"rem:edit:{reminder_id}:datetime"),
        ]
    )
    rows.append(
        [
            ("📎 درس", f"rem:edit:{reminder_id}:course"),
            ("🔁 تکرار", f"rem:edit:{reminder_id}:repeat"),
        ]
    )
    rows.append(
        [
            ("📝 توضیح", f"rem:edit:{reminder_id}:description"),
            ("🔔 هشدارها", f"rem:edit:{reminder_id}:alerts"),
        ]
    )
    rows.append([("🗑 حذف یادآوری", f"rem:delete:{reminder_id}")])
    rows.append([("🔙 لیست یادآوری‌ها", "rem:list"), ("🔙 منوی اصلی", "rem:exit")])
    return inline_buttons(rows)


# --- screens ------------------------------------------------------------
async def _load_reminders(user_id: int):
    async with get_session() as session:
        return await ReminderRepository(session).list_by_user(user_id, active_only=False)


async def _show_list(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    reminders = await _load_reminders(user_id)
    rows: list[list[tuple[str, str]]] = [
        [((("⏸ " if not r.is_active else "") + f"⏰ {r.title}"), f"rem:open:{r.id}")]
        for r in reminders
    ]
    rows.append([(ADD_REMINDER, "rem:add")])
    rows.append([("🔙 منوی اصلی", "rem:exit")])
    await answer(update, context, _list_text(reminders), reply_markup=inline_buttons(rows))
    return ReminderState.LIST


async def reminders_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("reminder_wizard", None)
    user_id = await current_user_id(update, context)
    if user_id is None:
        await answer(update, context, "ابتدا /start را بزن.")
        return ConversationHandler.END
    return await _show_list(update, context, user_id)


async def _show_detail(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    reminder_id: int,
):
    reminder = None
    offsets: list[str] = []
    course_name: str | None = None
    # read everything first: never open a session inside another one
    async with get_session() as session:
        reminder = await ReminderRepository(session).get(reminder_id, user_id)
        if reminder is not None:
            offsets = await alert_offsets_of(session, reminder_id)
            if reminder.course_id:
                course = await CourseRepository(session).get(reminder.course_id, user_id)
                course_name = course.name if course else None

    if reminder is None:
        await answer(update, context, "این یادآوری پیدا نشد.")
        return await _show_list(update, context, user_id)

    context.user_data["reminder_id"] = reminder_id
    await answer(
        update,
        context,
        _reminder_text(reminder, offsets, course_name),
        reply_markup=_detail_keyboard(reminder_id, reminder.is_active),
    )
    return ReminderState.DETAIL


async def on_open(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    reminder_id = int((query.data or "").split(":")[-1])
    return await _show_detail(update, context, user_id, reminder_id)


# --- wizard -------------------------------------------------------------
def _next_field(wizard: dict) -> str | None:
    """Next field of the create flow (edit mode edits exactly one field)."""
    if wizard["mode"] == "edit":
        return None
    try:
        index = CREATE_FIELDS.index(wizard["field"])
    except ValueError:  # pragma: no cover - defensive
        return None
    return CREATE_FIELDS[index + 1] if index + 1 < len(CREATE_FIELDS) else None


async def _render_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the input screen of the wizard's current field."""
    wizard = context.user_data["reminder_wizard"]
    field = wizard["field"]
    prefix = "✏️ ویرایش\n" if wizard["mode"] == "edit" else "➕ یادآوری جدید\n"

    if field in TEXT_FIELDS:
        await answer(update, context, prefix + PROMPTS[field], reply_markup=_text_keyboard(field))
        return ReminderState.WIZARD

    if field == "course":
        user_id = await current_user_id(update, context)
        courses = []
        if user_id is not None:
            async with get_session() as session:
                courses = await CourseRepository(session).list_by_user(user_id)
        rows: list[list[tuple[str, str]]] = [
            [(f"📖 {course.name}", f"rem:course:{course.id}")] for course in courses
        ]
        rows.append([(f"{SKIP} (بدون درس)", "rem:course:none")])
        rows.append([(CANCEL, "rem:cancel")])
        await answer(update, context, prefix + COURSE_PROMPT, reply_markup=inline_buttons(rows))
        return ReminderState.WIZARD

    if field == "repeat":
        rows = [[(label, f"rem:repeat:{value}")] for value, label in REPEAT_LABELS.items()]
        rows.append([(CANCEL, "rem:cancel")])
        await answer(update, context, prefix + REPEAT_PROMPT, reply_markup=inline_buttons(rows))
        return ReminderState.WIZARD

    # alerts (multi select)
    selected = set(wizard.setdefault("data", {}).get("alerts") or [])
    rows = []
    for offset in ALERT_OFFSETS:
        mark = " ✅" if offset in selected else ""
        rows.append([(f"{ALERT_LABELS[offset]}{mark}", f"rem:alert:{offset}")])
    rows.append([("✅ ذخیره هشدارها", "rem:alert:save")])
    rows.append([(CANCEL, "rem:cancel")])
    await answer(update, context, prefix + ALERTS_PROMPT, reply_markup=inline_buttons(rows))
    return ReminderState.WIZARD


async def _start_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE, wizard: dict):
    context.user_data["reminder_wizard"] = wizard
    return await _render_field(update, context)


async def on_add_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    return await _start_wizard(
        update,
        context,
        {
            "mode": "create",
            "reminder_id": None,
            "field": "title",
            "data": {"alerts": [ALERT_AT_TIME]},
        },
    )


async def on_edit_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    _, _, reminder_id, field = (query.data or "").split(":")
    if field not in FIELD_LABELS:  # pragma: no cover - defensive
        return ReminderState.DETAIL

    wizard: dict = {
        "mode": "edit",
        "reminder_id": int(reminder_id),
        "field": field,
        "data": {},
    }
    if field == "alerts":
        user_id = await current_user_id(update, context)
        if user_id is None:
            return ConversationHandler.END
        async with get_session() as session:
            if await ReminderRepository(session).get(int(reminder_id), user_id) is None:
                await answer(update, context, "این یادآوری پیدا نشد.")
                return await _show_list(update, context, user_id)
            wizard["data"]["alerts"] = await alert_offsets_of(session, int(reminder_id))
    return await _start_wizard(update, context, wizard)


async def _advance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wizard = context.user_data["reminder_wizard"]
    nxt = _next_field(wizard)
    if nxt is None:
        return await _finish(update, context)
    wizard["field"] = nxt
    context.user_data["reminder_wizard"] = wizard
    return await _render_field(update, context)


async def _finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wizard = context.user_data.pop("reminder_wizard", None) or {}
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END

    data = dict(wizard.get("data") or {})
    has_alerts = "alerts" in data
    offsets = list(data.pop("alerts", None) or [ALERT_AT_TIME])
    values = {FIELD_TO_MODEL[key]: value for key, value in data.items() if key in FIELD_TO_MODEL}
    if wizard["mode"] == "create":
        values.setdefault("repeat_type", REPEAT_NONE)

    reminder_id: int | None = None
    missing = False
    async with get_session() as session:
        repo = ReminderRepository(session)
        if wizard["mode"] == "create":
            reminder = await repo.create(user_id=user_id, is_active=True, **values)
        else:
            reminder = await repo.get(int(wizard["reminder_id"]), user_id)
            if reminder is None:
                missing = True
            else:
                await repo.update(reminder, **values)
        if not missing:
            reminder_id = reminder.id
            if not has_alerts and wizard["mode"] == "edit":
                # editing any other field must not touch the chosen alerts
                offsets = await alert_offsets_of(session, reminder_id)
            await sync_notifications(session, reminder, offsets)

    if missing or reminder_id is None:
        await answer(update, context, "این یادآوری دیگر وجود ندارد.")
        return await _show_list(update, context, user_id)

    verb = "✅ یادآوری ساخته شد." if wizard["mode"] == "create" else "✅ تغییرات ذخیره شد."
    await answer(update, context, verb)
    return await _show_detail(update, context, user_id, reminder_id)


async def on_wizard_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wizard = context.user_data.get("reminder_wizard")
    user_id = await current_user_id(update, context)
    if wizard is None or user_id is None:
        return ConversationHandler.END

    field = wizard["field"]
    if field not in TEXT_FIELDS:  # pragma: no cover - a button was expected
        return ReminderState.WIZARD

    raw = (update.effective_message.text or "").strip()

    if raw in (CANCEL, BACK, "/cancel"):
        context.user_data.pop("reminder_wizard", None)
        await answer(update, context, "عملیات لغو شد.")
        return await _show_list(update, context, user_id)

    if field == "title":
        ok, value, error = validate_short_text(raw, FIELD_LABELS[field], max_length=128, required=True)
    elif field == "datetime":
        ok, value, error = parse_reminder_datetime(raw, get_settings().timezone)
    else:
        ok, value, error = validate_short_text(raw, FIELD_LABELS[field], max_length=500, required=False)

    if not ok:
        await answer(update, context, f"⚠️ {error}", reply_markup=_text_keyboard(field))
        return ReminderState.WIZARD

    wizard.setdefault("data", {})[field] = value
    context.user_data["reminder_wizard"] = wizard
    return await _advance(update, context)


async def on_skip_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    wizard = context.user_data.get("reminder_wizard")
    user_id = await current_user_id(update, context)
    if wizard is None or user_id is None:
        return ConversationHandler.END

    wizard.setdefault("data", {})[wizard["field"]] = None
    context.user_data["reminder_wizard"] = wizard
    return await _advance(update, context)


async def on_single_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle ``rem:course:*`` and ``rem:repeat:*`` buttons."""
    query = update.callback_query
    if query is not None:
        await query.answer()
    wizard = context.user_data.get("reminder_wizard")
    user_id = await current_user_id(update, context)
    if wizard is None or user_id is None:
        return ConversationHandler.END

    _, kind, value = (query.data or "").split(":")
    if kind == "course":
        wizard.setdefault("data", {})["course"] = None if value == "none" else int(value)
    else:
        if value not in REPEAT_TYPES:  # pragma: no cover - defensive
            return ReminderState.WIZARD
        wizard.setdefault("data", {})["repeat"] = value

    context.user_data["reminder_wizard"] = wizard
    if wizard["mode"] == "edit":
        return await _finish(update, context)
    return await _advance(update, context)


async def on_alert_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    wizard = context.user_data.get("reminder_wizard")
    if wizard is None or query is None:
        return ConversationHandler.END

    offset = (query.data or "").split(":")[-1]
    if offset not in ALERT_OFFSETS:  # pragma: no cover - defensive
        return ReminderState.WIZARD

    selected = list(wizard.setdefault("data", {}).get("alerts") or [])
    if offset in selected:
        selected.remove(offset)
    else:
        selected.append(offset)
    wizard["data"]["alerts"] = selected
    context.user_data["reminder_wizard"] = wizard
    return await _render_field(update, context)


async def on_alert_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    wizard = context.user_data.get("reminder_wizard")
    user_id = await current_user_id(update, context)
    if wizard is None or user_id is None:
        return ConversationHandler.END

    selected = list(wizard.setdefault("data", {}).get("alerts") or [])
    wizard["data"]["alerts"] = selected or [ALERT_AT_TIME]
    context.user_data["reminder_wizard"] = wizard
    if wizard["mode"] == "edit":
        return await _finish(update, context)
    return await _advance(update, context)


# --- pause / delete -----------------------------------------------------
async def on_pause_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    reminder_id = int((query.data or "").split(":")[-1])

    text = ""
    async with get_session() as session:
        repo = ReminderRepository(session)
        reminder = await repo.get(reminder_id, user_id)
        if reminder is None:
            text = "این یادآوری پیدا نشد."
        else:
            await repo.update(reminder, is_active=not reminder.is_active)
            text = (
                "▶️ یادآوری دوباره فعال شد."
                if reminder.is_active
                else "⏸ یادآوری غیرفعال شد."
            )
            if reminder.is_active:
                await sync_notifications(session, reminder, await alert_offsets_of(session, reminder_id))

    await answer(update, context, text)
    return await _show_detail(update, context, user_id, reminder_id)


async def on_delete_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    reminder_id = int((query.data or "").split(":")[-1])
    await answer(
        update,
        context,
        "این یادآوری حذف شود؟",
        reply_markup=inline_buttons(
            [
                [("✅ بله، حذف شود", f"rem:delete:{reminder_id}:yes")],
                [(CANCEL, "rem:delete:no")],
            ]
        ),
    )
    return ReminderState.DETAIL


async def on_delete_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    reminder_id = int((query.data or "").split(":")[2])

    async with get_session() as session:
        repo = ReminderRepository(session)
        reminder = await repo.get(reminder_id, user_id)
        if reminder is not None:
            await repo.delete(reminder)
            deleted = True
        else:
            deleted = False

    await answer(
        update, context, "✅ یادآوری حذف شد." if deleted else "این یادآوری پیدا نشد."
    )
    return await _show_list(update, context, user_id)


async def on_delete_cancelled(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    reminder_id = context.user_data.get("reminder_id")
    if reminder_id:
        return await _show_detail(update, context, user_id, int(reminder_id))
    return await _show_list(update, context, user_id)


# --- conversation exits -------------------------------------------------
async def exit_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query is not None:
        await update.callback_query.answer()
    context.user_data.pop("reminder_wizard", None)
    await answer(update, context, "به منوی اصلی برگشتی 👇", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("reminder_wizard", None)
    await answer(update, context, "عملیات لغو شد.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


def build_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Text([REMINDERS]), reminders_menu),
            CallbackQueryHandler(reminders_menu, pattern=r"^rem:list$"),
        ],
        states={
            ReminderState.LIST: [
                CallbackQueryHandler(on_add_clicked, pattern=r"^rem:add$"),
                CallbackQueryHandler(on_open, pattern=r"^rem:open:\d+$"),
                CallbackQueryHandler(exit_conversation, pattern=r"^rem:exit$"),
                MessageHandler(filters.Text([REMINDERS]), reminders_menu),
            ],
            ReminderState.DETAIL: [
                CallbackQueryHandler(on_edit_clicked, pattern=r"^rem:edit:\d+:\w+$"),
                CallbackQueryHandler(on_pause_clicked, pattern=r"^rem:pause:\d+$"),
                CallbackQueryHandler(on_delete_confirmed, pattern=r"^rem:delete:\d+:yes$"),
                CallbackQueryHandler(on_delete_cancelled, pattern=r"^rem:delete:no$"),
                CallbackQueryHandler(on_delete_clicked, pattern=r"^rem:delete:\d+$"),
                CallbackQueryHandler(reminders_menu, pattern=r"^rem:list$"),
                CallbackQueryHandler(exit_conversation, pattern=r"^rem:exit$"),
                MessageHandler(filters.Text([REMINDERS]), reminders_menu),
            ],
            ReminderState.WIZARD: [
                CallbackQueryHandler(on_single_choice, pattern=r"^rem:(course|repeat):"),
                CallbackQueryHandler(on_alert_toggle, pattern=r"^rem:alert:(?!save$)"),
                CallbackQueryHandler(on_alert_save, pattern=r"^rem:alert:save$"),
                CallbackQueryHandler(on_skip_clicked, pattern=r"^rem:skip$"),
                CallbackQueryHandler(exit_conversation, pattern=r"^rem:exit$"),
                MessageHandler(filters.Text([REMINDERS]), reminders_menu),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_buttons_filter(), on_wizard_text),
            ],
        },
        fallbacks=[
            CommandHandler(["start", "cancel"], cancel_conversation),
            MessageHandler(filters.Text([BACK]), cancel_conversation),
            CallbackQueryHandler(cancel_conversation, pattern=r"^rem:cancel$"),
        ],
        name="reminder_conversation",
        persistent=False,
        allow_reentry=True,
    )

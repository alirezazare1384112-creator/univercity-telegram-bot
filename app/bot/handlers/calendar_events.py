"""📆 تقویم و کارهای آینده - the student's dated task list.

Dates are typed in the Jalali calendar (or as فردا/امروز) and stored as
plain local dates - see ``app/database/models/calendar_event.py``.
"""

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
from app.bot.keyboards.main_menu import CALENDAR, main_menu_keyboard
from app.bot.states.calendar_states import CalendarState
from app.config import get_settings
from app.database.database import get_session
from app.database.repositories import CalendarEventRepository
from app.utils.datetime_utils import (
    format_jalali_date,
    parse_time,
    parse_user_date,
    relative_date_label,
)
from app.utils.validation import validate_short_text

logger = logging.getLogger(__name__)

CREATE_FIELDS: tuple[str, ...] = ("title", "date", "time", "description")
EDIT_FIELDS: frozenset[str] = frozenset(CREATE_FIELDS)
# fields that may be skipped (no time = all day, no description = none)
OPTIONAL_FIELDS: frozenset[str] = frozenset({"time", "description"})

PROMPTS: dict[str, str] = {
    "title": "عنوان رویداد را بنویس.\nمثال: امتحان پایگاه داده",
    "date": "تاریخ را وارد کن.\nمثال: فردا، امروز، 1404/07/12 یا 2026/10/05",
    "time": (
        "ساعت را وارد کن. مثال: 18:30\n"
        "رویداد تمام‌روز است؟ «⏭ رد شد» را بزن."
    ),
    "description": "توضیح (اختیاری).\nبرای رد شدن دکمه «⏭ رد شد» را بزن.",
}
FIELD_LABELS: dict[str, str] = {
    "title": "عنوان",
    "date": "تاریخ",
    "time": "ساعت",
    "description": "توضیح",
}
FIELD_TO_MODEL: dict[str, str] = {
    "title": "title",
    "date": "event_date",
    "time": "event_time",
    "description": "description",
}

SKIP = "⏭ رد شد"
ADD_EVENT = "➕ رویداد جدید"
DONE_LIST = "✔️ انجام‌شده‌ها"
NO_EVENTS = (
    "هنوز رویدادی ثبت نکرده‌ای.\n"
    f"با دکمه «{ADD_EVENT}» اولین کارت را اضافه کن."
)


# --- text builders ------------------------------------------------------
def _list_text(events: list, done_count: int, tz: str) -> str:
    if not events:
        return "📆 تقویم و کارهای آینده\n\n" + NO_EVENTS
    lines = ["📆 کارهای آینده", ""]
    for index, event in enumerate(events, start=1):
        time_part = f" — ساعت {event.event_time:%H:%M}" if event.event_time else ""
        relative = relative_date_label(event.event_date, tz)
        rel_part = f" ({relative})" if relative else ""
        lines.append(
            f"{index}) 📌 {event.title}{rel_part} — "
            f"{format_jalali_date(event.event_date)}{time_part}"
        )
    if done_count:
        lines.append("")
        lines.append(f"✔️ {done_count} مورد انجام‌شده")
    return "\n".join(lines)


def _done_text(events: list, tz: str) -> str:
    if not events:
        return "✔️ هنوز رویدادی را انجام نشده داری."
    lines = ["✔️ رویدادهای انجام‌شده", ""]
    for index, event in enumerate(events, start=1):
        lines.append(
            f"{index}) ✅ {event.title} — {format_jalali_date(event.event_date)}"
        )
    return "\n".join(lines)


def _detail_text(event, tz: str) -> str:
    relative = relative_date_label(event.event_date, tz)
    rel_part = f" — {relative}" if relative else ""
    time_part = f"ساعت {event.event_time:%H:%M}" if event.event_time else "تمام روز"
    status = "✅ انجام شده" if event.is_done else "⏳ در انتظار"
    return "\n".join(
        [
            "📆 رویداد",
            "",
            f"📌 عنوان: {event.title}",
            f"🗓 تاریخ: {format_jalali_date(event.event_date)}{rel_part}",
            f"⏰ {time_part}",
            f"📝 توضیح: {event.description or '—'}",
            f"وضعیت: {status}",
        ]
    )


# --- keyboards ----------------------------------------------------------
def _text_keyboard(field: str):
    rows: list[list[tuple[str, str]]] = []
    if field in OPTIONAL_FIELDS:
        rows.append([(SKIP, "cal:skip")])
    rows.append([(CANCEL, "cal:cancel")])
    return inline_buttons(rows)


def _menu_keyboard(events: list, done_count: int):
    rows: list[list[tuple[str, str]]] = [
        [(f"📌 {event.title[:46]}", f"cal:open:{event.id}")] for event in events
    ]
    rows.append([(f"{DONE_LIST} ({done_count})", "cal:done")])
    rows.append([(ADD_EVENT, "cal:add")])
    rows.append([("🔙 منوی اصلی", "cal:exit")])
    return inline_buttons(rows)


def _done_keyboard(events: list):
    rows: list[list[tuple[str, str]]] = [
        [(f"✅ {event.title[:46]}", f"cal:open_done:{event.id}")] for event in events
    ]
    rows.append([("🔙 رویدادهای آینده", "cal:list")])
    rows.append([("🔙 منوی اصلی", "cal:exit")])
    return inline_buttons(rows)


def _detail_keyboard(event):
    toggle_label = "↩️ برگردان به آینده‌ها" if event.is_done else "✅ انجام شد"
    return inline_buttons(
        [
            [(toggle_label, f"cal:toggle:{event.id}")],
            [
                ("✏️ عنوان", f"cal:edit:{event.id}:title"),
                ("🗓 تاریخ", f"cal:edit:{event.id}:date"),
            ],
            [
                ("⏰ ساعت", f"cal:edit:{event.id}:time"),
                ("📝 توضیح", f"cal:edit:{event.id}:description"),
            ],
            [("🗑 حذف رویداد", f"cal:delete:{event.id}")],
            [("🔙 لیست", "cal:back"), ("🔙 منوی اصلی", "cal:exit")],
        ]
    )


# --- screens ------------------------------------------------------------
async def _load(user_id: int, *, done: bool = False):
    async with get_session() as session:
        return await CalendarEventRepository(session).list_by_user(user_id, done=done)


async def _show_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    tz = get_settings().timezone
    events = await _load(user_id)
    async with get_session() as session:
        done_count = await CalendarEventRepository(session).count(user_id, done=True)
    await answer(
        update,
        context,
        _list_text(events, done_count, tz),
        reply_markup=_menu_keyboard(events, done_count),
    )
    context.user_data["cal_origin"] = "menu"
    return CalendarState.MENU


async def calendar_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    context.user_data.pop("cal_wizard", None)
    user_id = await current_user_id(update, context)
    if user_id is None:
        await answer(update, context, "ابتدا /start را بزن.")
        return ConversationHandler.END
    return await _show_menu(update, context, user_id)


async def _show_done(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
):
    tz = get_settings().timezone
    events = await _load(user_id, done=True)
    await answer(
        update, context, _done_text(events, tz), reply_markup=_done_keyboard(events)
    )
    context.user_data["cal_origin"] = "done"
    return CalendarState.DONE


async def on_done_clicked(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    return await _show_done(update, context, user_id)


async def _show_detail(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, event_id: int
):
    async with get_session() as session:
        event = await CalendarEventRepository(session).get(event_id, user_id)

    if event is None:
        await answer(update, context, "این رویداد پیدا نشد.")
        return await _show_menu(update, context, user_id)

    context.user_data["event_id"] = event_id
    await answer(
        update,
        context,
        _detail_text(event, get_settings().timezone),
        reply_markup=_detail_keyboard(event),
    )
    return CalendarState.DETAIL


async def on_open(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    event_id = int((query.data or "").split(":")[-1])
    context.user_data["cal_origin"] = "menu"
    return await _show_detail(update, context, user_id, event_id)


async def on_open_done(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    event_id = int((query.data or "").split(":")[-1])
    context.user_data["cal_origin"] = "done"
    return await _show_detail(update, context, user_id, event_id)


async def on_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detail -> wherever the item was opened from (done list or menu)."""
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    if context.user_data.get("cal_origin") == "done":
        return await _show_done(update, context, user_id)
    return await _show_menu(update, context, user_id)


# --- wizard -------------------------------------------------------------
def _next_field(wizard: dict) -> str | None:
    if wizard["mode"] == "edit":
        return None
    try:
        index = CREATE_FIELDS.index(wizard["field"])
    except ValueError:  # pragma: no cover - defensive
        return None
    return CREATE_FIELDS[index + 1] if index + 1 < len(CREATE_FIELDS) else None


async def _ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wizard = context.user_data["cal_wizard"]
    field = wizard["field"]
    prefix = "✏️ ویرایش\n" if wizard["mode"] == "edit" else "➕ رویداد جدید\n"
    await answer(
        update, context, prefix + PROMPTS[field], reply_markup=_text_keyboard(field)
    )
    return CalendarState.WIZARD


async def _start_wizard(
    update: Update, context: ContextTypes.DEFAULT_TYPE, wizard: dict
):
    context.user_data["cal_wizard"] = wizard
    return await _ask(update, context)


async def on_add_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    return await _start_wizard(
        update,
        context,
        {"mode": "create", "event_id": None, "field": "title", "data": {}},
    )


async def on_edit_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    _, _, event_id, field = (query.data or "").split(":")
    if field not in EDIT_FIELDS:  # pragma: no cover - defensive
        return CalendarState.DETAIL
    return await _start_wizard(
        update,
        context,
        {"mode": "edit", "event_id": int(event_id), "field": field, "data": {}},
    )


async def _advance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wizard = context.user_data["cal_wizard"]
    nxt = _next_field(wizard)
    if nxt is None:
        return await _finish(update, context)
    wizard["field"] = nxt
    context.user_data["cal_wizard"] = wizard
    return await _ask(update, context)


def _validate_field(field: str, raw: str, tz: str):
    """Validate one wizard answer for the given field."""
    if field == "title":
        return validate_short_text(raw, FIELD_LABELS[field], max_length=128, required=True)
    if field == "date":
        return parse_user_date(raw, tz)
    if field == "time":
        return parse_time(raw)
    return validate_short_text(  # description (optional)
        raw, FIELD_LABELS[field], max_length=500, required=False
    )


async def _finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wizard = context.user_data.pop("cal_wizard", None) or {}
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END

    data = dict(wizard.get("data") or {})
    event_id: int | None = None
    missing = False

    async with get_session() as session:
        repo = CalendarEventRepository(session)
        if wizard["mode"] == "create":
            event = await repo.create(
                user_id=user_id,
                title=data["title"],
                event_date=data["date"],
                event_time=data.get("time"),
                description=data.get("description"),
            )
        else:
            event = await repo.get(int(wizard["event_id"]), user_id)
            if event is None:
                missing = True
            else:
                field = wizard["field"]
                await repo.update(event, **{FIELD_TO_MODEL[field]: data.get(field)})
        if event is not None:
            event_id = event.id

    if missing or event_id is None:
        await answer(update, context, "این رویداد دیگر وجود ندارد.")
        return await _show_menu(update, context, user_id)

    verb = "✅ رویداد ذخیره شد." if wizard["mode"] == "create" else "✅ تغییرات ذخیره شد."
    await answer(update, context, verb)
    return await _show_detail(update, context, user_id, event_id)


async def on_wizard_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wizard = context.user_data.get("cal_wizard")
    user_id = await current_user_id(update, context)
    if wizard is None or user_id is None:
        return ConversationHandler.END

    field = wizard["field"]
    raw = (update.effective_message.text or "").strip()

    if raw in (CANCEL, BACK, "/cancel"):
        context.user_data.pop("cal_wizard", None)
        await answer(update, context, "عملیات لغو شد.")
        return await _show_menu(update, context, user_id)

    tz = get_settings().timezone
    ok, value, error = _validate_field(field, raw, tz)
    if not ok:
        await answer(update, context, f"⚠️ {error}", reply_markup=_text_keyboard(field))
        return CalendarState.WIZARD

    wizard.setdefault("data", {})[field] = value
    context.user_data["cal_wizard"] = wizard
    return await _advance(update, context)


async def on_skip_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    wizard = context.user_data.get("cal_wizard")
    user_id = await current_user_id(update, context)
    if wizard is None or user_id is None:
        return ConversationHandler.END

    wizard.setdefault("data", {})[wizard["field"]] = None
    context.user_data["cal_wizard"] = wizard
    return await _advance(update, context)


# --- done / delete ------------------------------------------------------
async def on_toggle_clicked(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    event_id = int((query.data or "").split(":")[-1])

    async with get_session() as session:
        repo = CalendarEventRepository(session)
        event = await repo.get(event_id, user_id)
        if event is None:
            await answer(update, context, "این رویداد پیدا نشد.")
            return await _show_menu(update, context, user_id)
        now_done = not event.is_done
        await repo.update(event, is_done=now_done)

    await answer(
        update,
        context,
        "✅ انجام شد. آفرین!" if now_done else "↩️ رویداد به لیست آینده‌ها برگشت.",
    )
    return await _show_detail(update, context, user_id, event_id)


async def on_delete_clicked(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    event_id = int((query.data or "").split(":")[-1])
    await answer(
        update,
        context,
        "این رویداد حذف شود؟",
        reply_markup=inline_buttons(
            [
                [("✅ بله، حذف شود", f"cal:delete:{event_id}:yes")],
                [(CANCEL, "cal:delete:no")],
            ]
        ),
    )
    return CalendarState.DETAIL


async def on_delete_confirmed(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    event_id = int((query.data or "").split(":")[2])

    async with get_session() as session:
        repo = CalendarEventRepository(session)
        event = await repo.get(event_id, user_id)
        deleted = event is not None
        if event is not None:
            await repo.delete(event)

    await answer(
        update, context, "✅ رویداد حذف شد." if deleted else "این رویداد پیدا نشد."
    )
    return await _show_menu(update, context, user_id)


async def on_delete_cancelled(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    event_id = context.user_data.get("event_id")
    if event_id:
        return await _show_detail(update, context, user_id, int(event_id))
    return await _show_menu(update, context, user_id)


# --- conversation exits -------------------------------------------------
async def exit_conversation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    if update.callback_query is not None:
        await update.callback_query.answer()
    context.user_data.pop("cal_wizard", None)
    await answer(update, context, "به منوی اصلی برگشتی 👇", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def cancel_conversation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    context.user_data.pop("cal_wizard", None)
    await answer(update, context, "عملیات لغو شد.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


def build_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Text([CALENDAR]), calendar_menu),
            CallbackQueryHandler(calendar_menu, pattern=r"^cal:list$"),
        ],
        states={
            CalendarState.MENU: [
                CallbackQueryHandler(on_add_clicked, pattern=r"^cal:add$"),
                CallbackQueryHandler(on_done_clicked, pattern=r"^cal:done$"),
                CallbackQueryHandler(on_open, pattern=r"^cal:open:\d+$"),
                CallbackQueryHandler(exit_conversation, pattern=r"^cal:exit$"),
                MessageHandler(filters.Text([CALENDAR]), calendar_menu),
            ],
            CalendarState.DONE: [
                CallbackQueryHandler(on_open_done, pattern=r"^cal:open_done:\d+$"),
                CallbackQueryHandler(calendar_menu, pattern=r"^cal:list$"),
                CallbackQueryHandler(on_add_clicked, pattern=r"^cal:add$"),
                CallbackQueryHandler(exit_conversation, pattern=r"^cal:exit$"),
                MessageHandler(filters.Text([CALENDAR]), calendar_menu),
            ],
            CalendarState.DETAIL: [
                CallbackQueryHandler(on_toggle_clicked, pattern=r"^cal:toggle:\d+$"),
                CallbackQueryHandler(on_edit_clicked, pattern=r"^cal:edit:\d+:\w+$"),
                CallbackQueryHandler(on_delete_confirmed, pattern=r"^cal:delete:\d+:yes$"),
                CallbackQueryHandler(on_delete_cancelled, pattern=r"^cal:delete:no$"),
                CallbackQueryHandler(on_delete_clicked, pattern=r"^cal:delete:\d+$"),
                CallbackQueryHandler(on_back, pattern=r"^cal:back$"),
                CallbackQueryHandler(calendar_menu, pattern=r"^cal:list$"),
                CallbackQueryHandler(exit_conversation, pattern=r"^cal:exit$"),
                MessageHandler(filters.Text([CALENDAR]), calendar_menu),
            ],
            CalendarState.WIZARD: [
                CallbackQueryHandler(on_skip_clicked, pattern=r"^cal:skip$"),
                CallbackQueryHandler(calendar_menu, pattern=r"^cal:list$"),
                CallbackQueryHandler(exit_conversation, pattern=r"^cal:exit$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, on_wizard_text),
            ],
        },
        fallbacks=[
            CommandHandler(["start", "cancel"], cancel_conversation),
            MessageHandler(filters.Text([BACK]), cancel_conversation),
            CallbackQueryHandler(cancel_conversation, pattern=r"^cal:cancel$"),
        ],
        name="calendar_conversation",
        persistent=False,
        allow_reentry=True,
    )

"""📝 نمرات من - scored items of every course."""

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
from app.bot.keyboards.main_menu import GRADES, main_menu_keyboard, menu_buttons_filter
from app.bot.states.grade_states import GradeState
from app.database.database import get_session
from app.database.repositories import CourseRepository, GradeItemRepository
from app.utils.validation import validate_number, validate_short_text

logger = logging.getLogger(__name__)

FIELD_LABELS: dict[str, str] = {
    "title": "عنوان نمره",
    "max_score": "نمره کامل",
    "score": "نمره",
    "description": "توضیحات",
}

CREATE_FIELDS: tuple[str, ...] = ("title", "max_score", "score", "description")
OPTIONAL_FIELDS: frozenset[str] = frozenset({"description"})

PROMPTS: dict[str, str] = {
    "title": (
        "عنوان نمره را بنویس.\n"
        "مثال: میان‌ترم، پایان‌ترم، تمرین ۱، پروژه، کوئیز، ارائه، فعالیت کلاسی"
    ),
    "max_score": "نمره کامل را وارد کن.\nمثال: 20",
    "score": "نمره خودت را وارد کن.\nمثال: 16.5",
    "description": "توضیح (اختیاری).\nبرای رد شدن دکمه «⏭ رد شد» را بزن.",
}

SKIP = "⏭ رد شد"
ADD_ITEM = "➕ افزودن نمره"


def _fmt(number: float) -> str:
    """Show 6 instead of 6.0 and 1.5 instead of 1.5."""
    return str(int(number)) if float(number).is_integer() else f"{number:g}"


def _validate(field: str, raw: str, *, item=None, pending: dict | None = None):
    if field == "title":
        return validate_short_text(raw, FIELD_LABELS[field], max_length=64, required=True)

    if field == "description":
        return validate_short_text(raw, FIELD_LABELS[field], max_length=500, required=False)

    if field == "max_score":
        ok, value, error = validate_number(raw, FIELD_LABELS[field], minimum=0)
        if not ok:
            return ok, value, error
        if value == 0:
            return False, None, "نمره کامل باید بزرگ‌تر از صفر باشد."
        if item is not None and value < item.score:
            return False, None, f"نمره کامل نمی‌تواند کمتر از نمره فعلی ({_fmt(item.score)}) باشد."
        return True, value, ""

    # score
    ok, value, error = validate_number(raw, FIELD_LABELS[field], minimum=0)
    if not ok:
        return ok, value, error

    limit = None
    if item is not None:
        limit = item.max_score
    elif pending is not None and pending.get("max_score") is not None:
        limit = pending["max_score"]

    if limit is not None and value > limit:
        return False, None, f"نمره نمی‌تواند بزرگ‌تر از نمره کامل ({_fmt(limit)}) باشد."
    return True, value, ""


def _item_text(index: int, item) -> str:
    lines = [f"{index}. {item.title}"]
    lines.append(f"   نمره: {_fmt(item.score)} از {_fmt(item.max_score)} ({item.percent}%)")
    if item.description:
        lines.append(f"   توضیح: {item.description}")
    return "\n".join(lines)


def _items_text(course, items: list, totals: tuple[float, float]) -> str:
    if not items:
        return f"📝 هنوز نمره‌ای برای درس «{course.name}» ثبت نشده.\n\nبا دکمه «➕ افزودن نمره» شروع کن."
    lines = [f"📝 نمرات درس {course.name}", ""]
    for index, item in enumerate(items, start=1):
        lines.append(_item_text(index, item))
    total, maximum = totals
    percent = round(total / maximum * 100, 1) if maximum else 0.0
    lines.append("")
    lines.append(f"──────────\n🔢 مجموع: {_fmt(total)} از {_fmt(maximum)} ({percent}%)")
    return "\n".join(lines)


def _wizard_keyboard(field: str):
    rows: list[list[tuple[str, str]]] = []
    if field in OPTIONAL_FIELDS:
        rows.append([(SKIP, "grades:skip")])
    rows.append([(CANCEL, "grades:cancel")])
    return inline_buttons(rows)


async def _load_courses(user_id: int):
    async with get_session() as session:
        return await CourseRepository(session).list_by_user(user_id)


async def _show_courses(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    courses = await _load_courses(user_id)
    if not courses:
        await answer(
            update,
            context,
            "برای ثبت نمره اول باید درسی داشته باشی.\n"
            "به منوی اصلی برگرد و «📚 درس‌های من» را باز کن.",
            reply_markup=inline_buttons([[("🔙 منوی اصلی", "grades:exit")]]),
        )
        return GradeState.PICK_COURSE

    rows = [[(f"📖 {course.name}", f"grades:course:{course.id}")] for course in courses]
    rows.append([(BACK, "grades:exit")])
    await answer(
        update,
        context,
        "📝 برای کدام درس می‌خواهی نمره ببینی؟",
        reply_markup=inline_buttons(rows),
    )
    return GradeState.PICK_COURSE


async def grades_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = await current_user_id(update, context)
    if user_id is None:
        await answer(update, context, "ابتدا /start را بزن.")
        return ConversationHandler.END
    return await _show_courses(update, context, user_id)


async def _show_items(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, course_id: int):
    # Never open a session inside another one: read everything first,
    # then decide what to render.
    course = None
    items: list = []
    totals = (0.0, 0.0)
    async with get_session() as session:
        course = await CourseRepository(session).get(course_id, user_id)
        if course is not None:
            repo = GradeItemRepository(session)
            items = await repo.list_by_course(course_id)
            totals = await repo.totals(course_id)

    if course is None:
        await answer(update, context, "این درس پیدا نشد.")
        return await _show_courses(update, context, user_id)

    context.user_data["grade_course_id"] = course_id
    rows: list[list[tuple[str, str]]] = []
    for index, item in enumerate(items, start=1):
        rows.append([(f"{index}. {item.title}", f"grades:open:{item.id}")])
    rows.append([(ADD_ITEM, f"grades:add:{course_id}")])
    rows.append([(BACK, "grades:list")])
    rows.append([("🔙 منوی اصلی", "grades:exit")])

    await answer(update, context, _items_text(course, items, totals), reply_markup=inline_buttons(rows))
    return GradeState.ITEMS


async def on_pick_course(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    course_id = int((query.data or "").split(":")[-1])
    return await _show_items(update, context, user_id, course_id)


async def _item_detail(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, item_id: int):
    course_id = context.user_data.get("grade_course_id")
    async with get_session() as session:
        repo = GradeItemRepository(session)
        item = await repo.get(item_id, int(course_id)) if course_id else None
    if item is None:
        await answer(update, context, "این آیتم نمره پیدا نشد.")
        if course_id:
            return await _show_items(update, context, user_id, int(course_id))
        return await _show_courses(update, context, user_id)

    context.user_data["grade_item_id"] = item_id
    buttons: list[list[tuple[str, str]]] = [[(f"✏️ {FIELD_LABELS['title']}", f"grades:edit:{item_id}:title")]]
    buttons.append(
        [
            (f"✏️ {FIELD_LABELS['score']}", f"grades:edit:{item_id}:score"),
            (f"✏️ {FIELD_LABELS['max_score']}", f"grades:edit:{item_id}:max_score"),
        ]
    )
    buttons.append([(f"✏️ {FIELD_LABELS['description']}", f"grades:edit:{item_id}:description")])
    buttons.append([("🗑 حذف نمره", f"grades:delete:{item_id}")])
    buttons.append([(BACK, f"grades:course:{course_id}")])

    await answer(update, context, _item_text(1, item), reply_markup=inline_buttons(buttons))
    return GradeState.DETAIL


async def on_open_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    item_id = int((query.data or "").split(":")[-1])
    return await _item_detail(update, context, user_id, item_id)


async def _ask(field: str, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    wizard = context.user_data["grade_wizard"]
    prefix = "✏️ ویرایش\n" if wizard["mode"] == "edit" else "➕ نمره جدید\n"
    await answer(update, context, prefix + PROMPTS[field], reply_markup=_wizard_keyboard(field))


async def on_add_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if query is None or user_id is None:
        return ConversationHandler.END

    course_id = int((query.data or "").split(":")[-1])
    # callback_data comes from the client: only accept the id when the
    # course really belongs to the sender (a forwarded/copied button must
    # not be able to write a mark into another student's course).
    async with get_session() as session:
        course = await CourseRepository(session).get(course_id, user_id)
    if course is None:
        await answer(update, context, "این درس پیدا نشد.")
        return await _show_courses(update, context, user_id)

    context.user_data["grade_course_id"] = course_id
    context.user_data["grade_wizard"] = {
        "mode": "create",
        "course_id": course_id,
        "item_id": None,
        "field": "title",
        "data": {},
    }
    await _ask("title", update, context)
    return GradeState.WIZARD


async def on_edit_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    _, _, item_id, field = (query.data or "").split(":")
    if field not in FIELD_LABELS:  # pragma: no cover - defensive
        return GradeState.DETAIL
    context.user_data["grade_wizard"] = {
        "mode": "edit",
        "course_id": context.user_data.get("grade_course_id"),
        "item_id": int(item_id),
        "field": field,
        "data": {},
    }
    await _ask(field, update, context)
    return GradeState.WIZARD


def _next_field(wizard: dict) -> str | None:
    fields = CREATE_FIELDS if wizard["mode"] == "create" else (wizard["field"],)
    try:
        index = fields.index(wizard["field"])
    except ValueError:
        return None
    return fields[index + 1] if index + 1 < len(fields) else None


async def _current_item(wizard: dict):
    item_id = wizard.get("item_id")
    course_id = wizard.get("course_id")
    if item_id is None or course_id is None:  # stale / expired button
        return None
    async with get_session() as session:
        return await GradeItemRepository(session).get(int(item_id), int(course_id))


async def _finish(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    wizard = context.user_data.pop("grade_wizard", None) or {}
    data = dict(wizard.get("data") or {})
    course_id = wizard.get("course_id")
    if course_id is None:  # the selection was cleared (e.g. /cancel)
        await answer(
            update, context, "این عملیات منقضی شده است. دوباره از منوی نمرات شروع کن."
        )
        return await _show_courses(update, context, user_id)
    course_id = int(course_id)

    async with get_session() as session:
        repo = GradeItemRepository(session)
        if wizard["mode"] == "create":
            item = await repo.create(course_id=course_id, **data)
        else:
            item = await repo.get(int(wizard["item_id"]), course_id)
            if item is None:
                await answer(update, context, "این آیتم دیگر وجود ندارد.")
                return await _show_items(update, context, user_id, course_id)
            await repo.update(item, **data)
        item_id = item.id

    verb = "✅ نمره ثبت شد." if wizard["mode"] == "create" else "✅ تغییرات ذخیره شد."
    await answer(update, context, verb)
    return await _item_detail(update, context, user_id, item_id)


async def on_wizard_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wizard = context.user_data.get("grade_wizard")
    user_id = await current_user_id(update, context)
    if wizard is None or user_id is None:
        return ConversationHandler.END

    field = wizard["field"]
    raw = (update.effective_message.text or "").strip()

    if raw in (CANCEL, BACK, "/cancel"):
        context.user_data.pop("grade_wizard", None)
        await answer(update, context, "عملیات لغو شد.")
        course_id = int(wizard["course_id"])
        return await _show_items(update, context, user_id, course_id)

    item = await _current_item(wizard) if wizard["mode"] == "edit" else None
    ok, value, error = _validate(
        field, raw, item=item, pending=wizard.get("data")
    )
    if not ok:
        await answer(update, context, f"⚠️ {error}", reply_markup=_wizard_keyboard(field))
        return GradeState.WIZARD

    wizard.setdefault("data", {})[field] = value
    nxt = _next_field(wizard)
    if nxt is None:
        return await _finish(update, context, user_id)

    wizard["field"] = nxt
    context.user_data["grade_wizard"] = wizard
    await _ask(nxt, update, context)
    return GradeState.WIZARD


async def on_skip_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    wizard = context.user_data.get("grade_wizard")
    user_id = await current_user_id(update, context)
    if wizard is None or user_id is None:
        return ConversationHandler.END

    wizard.setdefault("data", {})[wizard["field"]] = None
    nxt = _next_field(wizard)
    if nxt is None:
        return await _finish(update, context, user_id)

    wizard["field"] = nxt
    context.user_data["grade_wizard"] = wizard
    await _ask(nxt, update, context)
    return GradeState.WIZARD


async def on_delete_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    item_id = int((query.data or "").split(":")[-1])
    course_id = context.user_data.get("grade_course_id")
    item = await _current_item({"item_id": item_id, "course_id": course_id})
    if item is None:
        await answer(update, context, "این آیتم پیدا نشد.")
        return GradeState.DETAIL

    await answer(
        update,
        context,
        f"«{item.title}» حذف شود؟",
        reply_markup=inline_buttons(
            [
                [("✅ بله، حذف شود", f"grades:delete:{item_id}:yes")],
                [(CANCEL, "grades:delete:no")],
            ]
        ),
    )
    return GradeState.DETAIL


async def on_delete_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    item_id = int((query.data or "").split(":")[2])
    course_id_raw = context.user_data.get("grade_course_id")
    if course_id_raw is None:  # stale button from an ended conversation
        await answer(
            update, context, "این عملیات منقضی شده است. دوباره از منوی نمرات شروع کن."
        )
        return ConversationHandler.END
    course_id = int(course_id_raw)

    async with get_session() as session:
        repo = GradeItemRepository(session)
        item = await repo.get(item_id, course_id)
        if item is None:
            await answer(update, context, "این آیتم پیدا نشد.")
            return await _show_items(update, context, user_id, course_id)
        await repo.delete(item)

    await answer(update, context, "✅ نمره حذف شد.")
    return await _show_items(update, context, user_id, course_id)


async def on_delete_cancelled(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    item_id = context.user_data.get("grade_item_id")
    course_id = context.user_data.get("grade_course_id")
    if item_id and course_id:
        return await _item_detail(update, context, user_id, int(item_id))
    return await _show_items(update, context, user_id, int(course_id or 0))


async def back_to_courses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query is not None:
        await update.callback_query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    context.user_data.pop("grade_wizard", None)
    return await _show_courses(update, context, user_id)


async def exit_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query is not None:
        await update.callback_query.answer()
    context.user_data.pop("grade_wizard", None)
    await answer(update, context, "به منوی اصلی برگشتی 👇", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query is not None:
        await update.callback_query.answer()
    context.user_data.pop("grade_wizard", None)
    context.user_data.pop("grade_course_id", None)
    context.user_data.pop("grade_item_id", None)
    await answer(update, context, "عملیات لغو شد.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


def build_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Text([GRADES]), grades_menu),
            CallbackQueryHandler(grades_menu, pattern=r"^grades:list$"),
        ],
        states={
            GradeState.PICK_COURSE: [
                CallbackQueryHandler(on_pick_course, pattern=r"^grades:course:\d+$"),
                CallbackQueryHandler(exit_conversation, pattern=r"^grades:exit$"),
                MessageHandler(filters.Text([GRADES]), grades_menu),
            ],
            GradeState.ITEMS: [
                CallbackQueryHandler(on_open_item, pattern=r"^grades:open:\d+$"),
                CallbackQueryHandler(on_add_clicked, pattern=r"^grades:add:\d+$"),
                CallbackQueryHandler(back_to_courses, pattern=r"^grades:list$"),
                CallbackQueryHandler(exit_conversation, pattern=r"^grades:exit$"),
                MessageHandler(filters.Text([GRADES]), grades_menu),
            ],
            GradeState.DETAIL: [
                CallbackQueryHandler(on_edit_clicked, pattern=r"^grades:edit:\d+:\w+$"),
                CallbackQueryHandler(on_delete_clicked, pattern=r"^grades:delete:\d+$"),
                CallbackQueryHandler(on_delete_confirmed, pattern=r"^grades:delete:\d+:yes$"),
                CallbackQueryHandler(on_delete_cancelled, pattern=r"^grades:delete:no$"),
                CallbackQueryHandler(on_pick_course, pattern=r"^grades:course:\d+$"),
                CallbackQueryHandler(exit_conversation, pattern=r"^grades:exit$"),
            ],
            GradeState.WIZARD: [
                CallbackQueryHandler(on_skip_clicked, pattern=r"^grades:skip$"),
                CallbackQueryHandler(exit_conversation, pattern=r"^grades:exit$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_buttons_filter(), on_wizard_text),
            ],
        },
        fallbacks=[
            CommandHandler(["start", "cancel"], cancel_conversation),
            MessageHandler(filters.Text([BACK]), cancel_conversation),
            CallbackQueryHandler(cancel_conversation, pattern=r"^grades:cancel$"),
        ],
        name="grades_conversation",
        persistent=False,
        allow_reentry=True,
    )

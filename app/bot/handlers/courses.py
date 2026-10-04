"""📚 درس‌های من - add, edit and delete the courses of the semester."""

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
from app.bot.keyboards.main_menu import COURSES, main_menu_keyboard
from app.bot.states.course_states import CourseState
from app.database.database import get_session
from app.database.repositories import CourseRepository
from app.utils.validation import (
    validate_positive_int,
    validate_short_text,
)

logger = logging.getLogger(__name__)

FIELD_LABELS: dict[str, str] = {
    "name": "نام درس",
    "units": "تعداد واحد",
    "teacher_name": "نام استاد",
    "semester": "نیمسال",
    "academic_year": "سال تحصیلی",
}

# order of the creation wizard
CREATE_FIELDS: tuple[str, ...] = ("name", "units", "teacher_name", "semester", "academic_year")
# fields that may be skipped
OPTIONAL_FIELDS: frozenset[str] = frozenset({"teacher_name", "semester", "academic_year"})

PROMPTS: dict[str, str] = {
    "name": "نام درس را بنویس.\nمثال: پایگاه داده",
    "units": "تعداد واحد را به صورت عدد وارد کنید.\nمثال: 3",
    "teacher_name": "نام استاد (اختیاری).\nبرای رد شدن، دکمه «⏭ رد شد» را بزن.",
    "semester": "نیمسال (اختیاری).\nمثال: 1404-1\nبرای رد شدن، دکمه «⏭ رد شد» را بزن.",
    "academic_year": "سال تحصیلی (اختیاری).\nمثال: 1404-1405\nبرای رد شد، دکمه «⏭ رد شد» را بزن.",
}

MAX_LENGTHS: dict[str, int] = {
    "name": 128,
    "units": 0,
    "teacher_name": 128,
    "semester": 64,
    "academic_year": 32,
}

SKIP = "⏭ رد شد"
ADD_COURSE = "➕ افزودن درس"


def _validate(field: str, raw: str):
    if field == "units":
        return validate_positive_int(raw, field_label="تعداد واحد", minimum=1, maximum=30)
    return validate_short_text(
        raw,
        FIELD_LABELS[field],
        max_length=MAX_LENGTHS[field],
        required=field not in OPTIONAL_FIELDS,
    )


def _course_text(course) -> str:
    lines = [f"📚 {course.name}", ""]
    lines.append(f"🔢 تعداد واحد: {course.units}")
    lines.append(f"🎓 استاد: {course.teacher_name or '—'}")
    lines.append(f"🗓 نیمسال: {course.semester or '—'}")
    lines.append(f"📆 سال تحصیلی: {course.academic_year or '—'}")
    return "\n".join(lines)


def _list_text(courses: list) -> str:
    if not courses:
        return (
            "هنوز درسی ثبت نکرده‌ای.\n\n"
            "با دکمه «➕ افزودن درس» اولین درس این ترم را اضافه کن."
        )
    lines = ["📚 درس‌های من", ""]
    total = 0
    for index, course in enumerate(courses, start=1):
        teacher = f" — {course.teacher_name}" if course.teacher_name else ""
        lines.append(f"{index}) {course.name} — {course.units} واحد{teacher}")
        total += course.units
    lines.append("")
    lines.append(f"🔢 مجموع واحد: {total}")
    return "\n".join(lines)


def _list_keyboard(courses: list):
    rows: list[list[tuple[str, str]]] = []
    for course in courses:
        rows.append([(f"📖 {course.name}", f"course:open:{course.id}")])
    rows.append([(ADD_COURSE, "course:add")])
    rows.append([(BACK, "course:exit")])
    return inline_buttons(rows)


def _wizard_keyboard(field: str):
    rows: list[list[tuple[str, str]]] = []
    if field in OPTIONAL_FIELDS:
        rows.append([(SKIP, "course:skip")])
    rows.append([(CANCEL, "course:cancel")])
    return inline_buttons(rows)


def _detail_keyboard(course_id: int):
    return inline_buttons(
        [
            [(f"✏️ {FIELD_LABELS['name']}", f"course:edit:{course_id}:name")],
            [
                (f"🔢 {FIELD_LABELS['units']}", f"course:edit:{course_id}:units"),
                (f"🎓 {FIELD_LABELS['teacher_name']}", f"course:edit:{course_id}:teacher_name"),
            ],
            [
                (f"🗓 {FIELD_LABELS['semester']}", f"course:edit:{course_id}:semester"),
                (f"📆 {FIELD_LABELS['academic_year']}", f"course:edit:{course_id}:academic_year"),
            ],
            [("🗑 حذف درس", f"course:delete:{course_id}")],
            [("🔙 بازگشت به لیست", "course:list")],
        ]
    )


async def _load_courses(user_id: int):
    async with get_session() as session:
        return await CourseRepository(session).list_by_user(user_id)


async def _show_list(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    courses = await _load_courses(user_id)
    await answer(update, context, _list_text(courses), reply_markup=_list_keyboard(courses))
    return CourseState.MENU


async def courses_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = await current_user_id(update, context)
    if user_id is None:
        await answer(update, context, "ابتدا /start را بزن.")
        return ConversationHandler.END
    return await _show_list(update, context, user_id)


async def on_add_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    context.user_data["course_wizard"] = {"mode": "create", "course_id": None, "field": "name", "data": {}}
    await answer(update, context, f"➕ درس جدید\n\n{PROMPTS['name']}", reply_markup=_wizard_keyboard("name"))
    return CourseState.WIZARD


def _next_field(wizard: dict) -> str | None:
    """Return the next field of the wizard (None when finished)."""
    fields = CREATE_FIELDS if wizard["mode"] == "create" else (wizard["field"],)
    try:
        index = fields.index(wizard["field"])
    except ValueError:
        return None
    if index + 1 >= len(fields):
        return None
    return fields[index + 1]


async def _finish_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    wizard = context.user_data.get("course_wizard") or {}
    data = dict(wizard.get("data") or {})

    course_id: int | None = None
    async with get_session() as session:
        repo = CourseRepository(session)
        if wizard["mode"] == "create":
            course = await repo.create(user_id=user_id, **data)
            course_id = course.id
        else:
            course = await repo.get(int(wizard["course_id"]), user_id)
            if course is not None:
                await repo.update(course, **data)
                course_id = course.id

    if course_id is None:
        await answer(update, context, "این درس دیگر وجود ندارد.")
        context.user_data.pop("course_wizard", None)
        return await _show_list(update, context, user_id)

    context.user_data.pop("course_wizard", None)
    context.user_data["course_id"] = course_id

    async with get_session() as session:
        course = await CourseRepository(session).get(course_id, user_id)

    verb = "✅ درس با موفقیت اضافه شد." if wizard["mode"] == "create" else "✅ تغییرات ذخیره شد."
    await answer(update, context, verb)
    await answer(update, context, _course_text(course), reply_markup=_detail_keyboard(course_id))
    return CourseState.DETAIL


async def on_wizard_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wizard = context.user_data.get("course_wizard")
    user_id = await current_user_id(update, context)
    if wizard is None or user_id is None:
        return ConversationHandler.END

    field = wizard["field"]
    raw = (update.effective_message.text or "").strip()

    if raw in (CANCEL, BACK, "/cancel"):
        context.user_data.pop("course_wizard", None)
        await answer(update, context, "عملیات لغو شد.")
        return await _show_list(update, context, user_id)

    ok, value, error = _validate(field, raw)
    if not ok:
        await answer(
            update,
            context,
            f"⚠️ {error}",
            reply_markup=_wizard_keyboard(field),
        )
        return CourseState.WIZARD

    wizard.setdefault("data", {})[field] = value
    nxt = _next_field(wizard)
    if nxt is None:
        return await _finish_wizard(update, context, user_id)

    wizard["field"] = nxt
    context.user_data["course_wizard"] = wizard
    await answer(update, context, PROMPTS[nxt], reply_markup=_wizard_keyboard(nxt))
    return CourseState.WIZARD


async def on_skip_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    wizard = context.user_data.get("course_wizard")
    user_id = await current_user_id(update, context)
    if wizard is None or user_id is None:
        return ConversationHandler.END

    wizard.setdefault("data", {})[wizard["field"]] = None
    nxt = _next_field(wizard)
    if nxt is None:
        return await _finish_wizard(update, context, user_id)

    wizard["field"] = nxt
    context.user_data["course_wizard"] = wizard
    await answer(update, context, PROMPTS[nxt], reply_markup=_wizard_keyboard(nxt))
    return CourseState.WIZARD


async def on_open_course(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END

    course_id = int((query.data or "").split(":")[-1])
    async with get_session() as session:
        course = await CourseRepository(session).get(course_id, user_id)
    if course is None:
        await answer(update, context, "این درس پیدا نشد.")
        return await _show_list(update, context, user_id)

    context.user_data["course_id"] = course_id
    await answer(update, context, _course_text(course), reply_markup=_detail_keyboard(course_id))
    return CourseState.DETAIL


async def on_edit_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END

    _, _, course_id, field = (query.data or "").split(":")
    if field not in FIELD_LABELS:  # pragma: no cover - defensive
        return CourseState.DETAIL

    context.user_data["course_wizard"] = {
        "mode": "edit",
        "course_id": int(course_id),
        "field": field,
        "data": {},
    }
    await answer(
        update,
        context,
        f"✏️ مقدار جدید «{FIELD_LABELS[field]}» را بفرست.\n\n{PROMPTS[field]}",
        reply_markup=_wizard_keyboard(field),
    )
    return CourseState.WIZARD


async def on_delete_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END

    course_id = int((query.data or "").split(":")[-1])
    async with get_session() as session:
        course = await CourseRepository(session).get(course_id, user_id)
    if course is None:
        await answer(update, context, "این درس پیدا نشد.")
        return await _show_list(update, context, user_id)

    await answer(
        update,
        context,
        f"«{course.name}» حذف شود؟\nنمرات و جزوه‌های این درس هم حذف می‌شوند.",
        reply_markup=inline_buttons(
            [
                [("✅ بله، حذف شود", f"course:delete:{course_id}:yes")],
                [(CANCEL, "course:delete:no")],
            ]
        ),
    )
    return CourseState.DETAIL


async def on_delete_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END

    course_id = int((query.data or "").split(":")[2])
    async with get_session() as session:
        repo = CourseRepository(session)
        course = await repo.get(course_id, user_id)
        if course is None:
            await answer(update, context, "این درس پیدا نشد.")
            return await _show_list(update, context, user_id)
        await repo.delete(course)

    await answer(update, context, "✅ درس حذف شد.")
    return await _show_list(update, context, user_id)


async def on_delete_cancelled(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    course_id = context.user_data.get("course_id")
    if course_id:
        return await _show_detail(update, context, user_id, int(course_id))
    return await _show_list(update, context, user_id)


async def _show_detail(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, course_id: int):
    async with get_session() as session:
        course = await CourseRepository(session).get(course_id, user_id)
    if course is None:
        return await _show_list(update, context, user_id)
    await answer(update, context, _course_text(course), reply_markup=_detail_keyboard(course_id))
    return CourseState.DETAIL


async def back_to_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query is not None:
        await update.callback_query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    context.user_data.pop("course_wizard", None)
    return await _show_list(update, context, user_id)


async def exit_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query is not None:
        await update.callback_query.answer()
    context.user_data.pop("course_wizard", None)
    await answer(update, context, "به منوی اصلی برگشتی 👇", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("course_wizard", None)
    await answer(update, context, "عملیات لغو شد.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


def build_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Text([COURSES]), courses_menu),
            CallbackQueryHandler(courses_menu, pattern=r"^course:list$"),
        ],
        states={
            CourseState.MENU: [
                CallbackQueryHandler(on_add_clicked, pattern=r"^course:add$"),
                CallbackQueryHandler(on_open_course, pattern=r"^course:open:\d+$"),
                CallbackQueryHandler(exit_conversation, pattern=r"^course:exit$"),
                MessageHandler(filters.Text([COURSES]), courses_menu),
            ],
            CourseState.WIZARD: [
                CallbackQueryHandler(on_skip_clicked, pattern=r"^course:skip$"),
                CallbackQueryHandler(exit_conversation, pattern=r"^course:exit$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, on_wizard_text),
            ],
            CourseState.DETAIL: [
                CallbackQueryHandler(on_edit_clicked, pattern=r"^course:edit:\d+:\w+$"),
                CallbackQueryHandler(on_delete_clicked, pattern=r"^course:delete:\d+$"),
                CallbackQueryHandler(
                    on_delete_confirmed, pattern=r"^course:delete:\d+:yes$"
                ),
                CallbackQueryHandler(on_delete_cancelled, pattern=r"^course:delete:no$"),
                CallbackQueryHandler(back_to_list, pattern=r"^course:list$"),
                CallbackQueryHandler(exit_conversation, pattern=r"^course:exit$"),
                MessageHandler(filters.Text([COURSES]), courses_menu),
            ],
        },
        fallbacks=[
            CommandHandler(["start", "cancel"], cancel_conversation),
            MessageHandler(filters.Text([BACK]), cancel_conversation),
        ],
        name="course_conversation",
        persistent=False,
        allow_reentry=True,
    )

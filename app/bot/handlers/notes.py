"""📚 جزوه‌ها - study files (photos / documents) kept by the student."""

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

from app.bot.helpers import answer, chat_id, current_user_id
from app.bot.keyboards.common import BACK, CANCEL, inline_buttons
from app.bot.keyboards.main_menu import COURSES, NOTES, main_menu_keyboard
from app.bot.states.note_states import NoteState
from app.config import get_settings
from app.database.database import get_session
from app.database.models.note import NOTE_DOCUMENT, NOTE_PHOTO
from app.database.repositories import CourseRepository, NoteRepository
from app.utils.datetime_utils import format_jalali
from app.utils.validation import validate_short_text

logger = logging.getLogger(__name__)

CREATE_FIELDS: tuple[str, ...] = ("title", "file", "course", "description")
EDIT_FIELDS: frozenset[str] = frozenset({"title", "description", "course"})

PROMPTS: dict[str, str] = {
    "title": "عنوان جزوه را بنویس.\nمثال: فصل ۳ پایگاه داده — نرمال‌سازی",
    "file": "فایل جزوه را بفرست (عکس یا سند PDF).",
    "course": "این جزوه به کدام درس مرتبط است؟",
    "description": "توضیح (اختیاری).\nبرای رد شدن دکمه «⏭ رد شد» را بزن.",
}
FIELD_LABELS: dict[str, str] = {
    "title": "عنوان",
    "course": "درس مرتبط",
    "description": "توضیح",
}
# wizard field -> database column
FIELD_TO_MODEL: dict[str, str] = {
    "title": "title",
    "course": "course_id",
    "description": "description",
}

SKIP = "⏭ رد شد"
ADD_NOTE = "➕ جزوه جدید"
NO_COURSE = "📂 بدون درس"


def _extract_file(message) -> tuple[str, str, str | None, str | None] | None:
    """``(file_type, file_id, file_unique_id, file_name)`` or ``None``."""
    if message.photo:
        photo = message.photo[-1]  # Telegram sends several sizes
        return NOTE_PHOTO, photo.file_id, photo.file_unique_id, None
    if message.document:
        document = message.document
        return NOTE_DOCUMENT, document.file_id, document.file_unique_id, document.file_name
    return None


# --- text builders ------------------------------------------------------
def _courses_text(courses: list, orphans: int) -> str:
    if not courses and orphans == 0:
        return (
            "هنوز درسی و جزوه‌ای ثبت نکرده‌ای.\n\n"
            f"درس‌ها را از منوی اصلی «{COURSES}» اضافه کن،\n"
            f"سپس با «{ADD_NOTE}» اولین جزوه را ذخیره کن."
        )
    if not courses:
        return (
            "📚 جزوه‌های بدون درس\n\n"
            f"هنوز درسی ثبت نکرده‌ای؛ از منوی اصلی «{COURSES}» درس اضافه کن."
        )
    return "📚 جزوه‌های من\n\nکدام درس را باز کنی؟"


def _detail_text(note, course_name: str | None) -> str:
    tz = get_settings().timezone
    lines = [
        "📚 جزوه",
        "",
        f"📌 عنوان: {note.title}",
        f"📖 درس: {course_name or '—'}",
        f"📝 توضیح: {note.description or '—'}",
        f"🕒 افزوده شده: {format_jalali(note.created_at, tz)}",
    ]
    if note.file_name:
        lines.append(f"📎 فایل: {note.file_name}")
    return "\n".join(lines)


# --- keyboards ----------------------------------------------------------
def _text_keyboard(field: str):
    rows: list[list[tuple[str, str]]] = []
    if field == "description":
        rows.append([(SKIP, "note:skip")])
    rows.append([(CANCEL, "note:cancel")])
    return inline_buttons(rows)


def _detail_keyboard(note_id: int, course_id: int | None):
    back_data = f"note:bycourse:{course_id}" if course_id else "note:list"
    back_label = "🔙 جزوه‌های همین درس" if course_id else "🔙 جزوه‌ها"
    rows: list[list[tuple[str, str]]] = [
        [
            ("✏️ عنوان", f"note:edit:{note_id}:title"),
            ("✏️ توضیح", f"note:edit:{note_id}:description"),
        ],
        [("📖 تغییر درس", f"note:edit:{note_id}:course")],
        [("🗑 حذف جزوه", f"note:delete:{note_id}")],
        [(back_label, back_data), ("🔙 منوی اصلی", "note:exit")],
    ]
    return inline_buttons(rows)


# --- screens ------------------------------------------------------------
async def _load_courses(user_id: int):
    async with get_session() as session:
        return await CourseRepository(session).list_by_user(user_id)


async def _show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    context.user_data.pop("note_course", None)
    async with get_session() as session:
        notes = await NoteRepository(session).list_by_user(user_id)
        courses = await CourseRepository(session).list_by_user(user_id)

    counts: dict[int, int] = {}
    orphans = 0
    for note in notes:
        if note.course_id:
            counts[note.course_id] = counts.get(note.course_id, 0) + 1
        else:
            orphans += 1

    buttons = [
        (f"📖 {course.name} ({counts.get(course.id, 0)})", f"note:bycourse:{course.id}")
        for course in courses
    ]
    rows: list[list[tuple[str, str]]] = [
        buttons[index : index + 2] for index in range(0, len(buttons), 2)
    ]
    if orphans or not courses:
        rows.append([(f"📂 بدون درس ({orphans})", "note:bycourse:none")])
    rows.append([(ADD_NOTE, "note:add")])
    rows.append([("🔙 منوی اصلی", "note:exit")])
    await answer(
        update,
        context,
        _courses_text(courses, orphans),
        reply_markup=inline_buttons(rows),
    )
    return NoteState.MENU


async def _show_course_notes(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    course_id: int | None,
):
    async with get_session() as session:
        notes = await NoteRepository(session).list_by_user(user_id)
        course = None
        if course_id is not None:
            course = await CourseRepository(session).get(course_id, user_id)

    if course_id is not None and course is None:
        await answer(update, context, "این درس پیدا نشد.")
        return await _show_menu(update, context, user_id)

    context.user_data["note_course"] = course_id
    scoped = [note for note in notes if (note.course_id or None) == course_id]
    title = (
        f"📚 جزوه‌های «{course.name}»" if course is not None else "📚 جزوه‌های بدون درس"
    )

    rows: list[list[tuple[str, str]]] = []
    if scoped:
        lines = [title, ""]
        for index, note in enumerate(scoped, start=1):
            icon = "📷" if note.file_type == NOTE_PHOTO else "📄"
            lines.append(f"{index}) {icon} {note.title}")
        text = "\n".join(lines)
        rows = [
            [
                (
                    ("📷 " if note.file_type == NOTE_PHOTO else "📄 ") + note.title,
                    f"note:open:{note.id}",
                )
            ]
            for note in scoped
        ]
    else:
        text = f"{title}\n\nهنوز جزوه‌ای برای این درس نداری."
    rows.append([(ADD_NOTE, "note:add")])
    rows.append([("🔙 همه درس‌ها", "note:list"), ("🔙 منوی اصلی", "note:exit")])
    await answer(update, context, text, reply_markup=inline_buttons(rows))
    return NoteState.COURSE


async def notes_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("note_wizard", None)
    user_id = await current_user_id(update, context)
    if user_id is None:
        await answer(update, context, "ابتدا /start را بزن.")
        return ConversationHandler.END
    return await _show_menu(update, context, user_id)


async def _show_detail(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, note_id: int
):
    note = None
    course_name: str | None = None
    # never open a session inside another one: read everything first
    async with get_session() as session:
        note = await NoteRepository(session).get(note_id, user_id)
        if note is not None and note.course_id:
            course = await CourseRepository(session).get(note.course_id, user_id)
            course_name = course.name if course else None

    if note is None:
        await answer(update, context, "این جزوه پیدا نشد.")
        return await _show_menu(update, context, user_id)

    context.user_data["note_id"] = note_id
    keyboard = _detail_keyboard(note_id, note.course_id)
    target = chat_id(update)
    try:
        if note.file_type == NOTE_PHOTO:
            await context.bot.send_photo(
                chat_id=target,
                photo=note.file_id,
                caption=_detail_text(note, course_name),
                reply_markup=keyboard,
            )
        else:
            await context.bot.send_document(
                chat_id=target,
                document=note.file_id,
                caption=_detail_text(note, course_name),
                reply_markup=keyboard,
            )
    except Exception:
        logger.exception("Could not resend note %s", note_id)
        await answer(
            update,
            context,
            _detail_text(note, course_name)
            + "\n⚠️ فایل قابل ارسال نیست (توکن فایل منقضی شده).",
            reply_markup=keyboard,
        )
    return NoteState.DETAIL


async def on_open(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    note_id = int((query.data or "").split(":")[-1])
    return await _show_detail(update, context, user_id, note_id)


async def on_open_course(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """The 📖 course buttons on the courses screen (and the back button)."""
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    raw = (query.data or "").split(":")[-1]
    course_id = None if raw == "none" else int(raw)
    return await _show_course_notes(update, context, user_id, course_id)


# --- wizard -------------------------------------------------------------
def _next_field(wizard: dict) -> str | None:
    if wizard["mode"] == "edit":
        return None
    try:
        index = CREATE_FIELDS.index(wizard["field"])
    except ValueError:  # pragma: no cover - defensive
        return None
    for candidate in CREATE_FIELDS[index + 1 :]:
        if candidate == "course" and "course" in (wizard.get("data") or {}):
            continue  # already chosen on the course screen
        return candidate
    return None


async def _render_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wizard = context.user_data["note_wizard"]
    field = wizard["field"]
    prefix = "✏️ ویرایش\n" if wizard["mode"] == "edit" else "➕ جزوه جدید\n"

    if field == "course":
        user_id = await current_user_id(update, context)
        courses = await _load_courses(user_id) if user_id is not None else []
        rows: list[list[tuple[str, str]]] = [
            [(f"📖 {course.name}", f"note:course:{course.id}")] for course in courses
        ]
        rows.append([(NO_COURSE, "note:course:none")])
        rows.append([(CANCEL, "note:cancel")])
        await answer(update, context, prefix + PROMPTS[field], reply_markup=inline_buttons(rows))
        return NoteState.WIZARD

    await answer(update, context, prefix + PROMPTS[field], reply_markup=_text_keyboard(field))
    return NoteState.WIZARD


async def _start_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE, wizard: dict):
    context.user_data["note_wizard"] = wizard
    return await _render_field(update, context)


async def on_add_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    data: dict = {}
    if "note_course" in context.user_data:
        # started from a course screen: the course is already known
        data["course"] = context.user_data["note_course"]
    return await _start_wizard(
        update,
        context,
        {"mode": "create", "note_id": None, "field": "title", "data": data},
    )


async def on_edit_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    _, _, note_id, field = (query.data or "").split(":")
    if field not in EDIT_FIELDS:  # pragma: no cover - defensive
        return NoteState.DETAIL
    return await _start_wizard(
        update,
        context,
        {"mode": "edit", "note_id": int(note_id), "field": field, "data": {}},
    )


async def _advance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wizard = context.user_data["note_wizard"]
    nxt = _next_field(wizard)
    if nxt is None:
        return await _finish(update, context)
    wizard["field"] = nxt
    context.user_data["note_wizard"] = wizard
    return await _render_field(update, context)


async def _finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wizard = context.user_data.pop("note_wizard", None) or {}
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END

    data = dict(wizard.get("data") or {})
    note_id: int | None = None
    missing = False

    async with get_session() as session:
        repo = NoteRepository(session)
        if wizard["mode"] == "create":
            file_info = data.get("file")
            if not file_info:  # pragma: no cover - the flow always stores it
                missing = True
                note = None
            else:
                note = await repo.create(
                    user_id=user_id,
                    title=data["title"],
                    course_id=data.get("course"),
                    description=data.get("description"),
                    file_type=file_info[0],
                    file_id=file_info[1],
                    file_unique_id=file_info[2],
                    file_name=file_info[3],
                )
        else:
            note = await repo.get(int(wizard["note_id"]), user_id)
            if note is None:
                missing = True
            else:
                field = wizard["field"]
                # data is keyed by wizard field name, the DB uses column names
                await repo.update(note, **{FIELD_TO_MODEL[field]: data.get(field)})
        if note is not None:
            note_id = note.id

    if missing or note_id is None:
        await answer(update, context, "این جزوه دیگر وجود ندارد.")
        return await _show_menu(update, context, user_id)

    verb = "✅ جزوه ذخیره شد." if wizard["mode"] == "create" else "✅ تغییرات ذخیره شد."
    await answer(update, context, verb)
    return await _show_detail(update, context, user_id, note_id)


async def on_wizard_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wizard = context.user_data.get("note_wizard")
    user_id = await current_user_id(update, context)
    if wizard is None or user_id is None:
        return ConversationHandler.END

    field = wizard["field"]
    raw = (update.effective_message.text or "").strip()

    if raw in (CANCEL, BACK, "/cancel"):
        context.user_data.pop("note_wizard", None)
        await answer(update, context, "عملیات لغو شد.")
        return await _show_menu(update, context, user_id)

    if field == "file":
        # the user typed while a file was expected
        await answer(update, context, f"⚠️ {PROMPTS['file']}")
        return NoteState.WIZARD

    if field == "course":
        # the course step is answered with buttons only
        return await _render_field(update, context)

    if field == "title":
        ok, value, error = validate_short_text(
            raw, FIELD_LABELS[field], max_length=128, required=True
        )
    else:  # description (optional)
        ok, value, error = validate_short_text(
            raw, FIELD_LABELS[field], max_length=500, required=False
        )

    if not ok:
        await answer(update, context, f"⚠️ {error}", reply_markup=_text_keyboard(field))
        return NoteState.WIZARD

    wizard.setdefault("data", {})[field] = value
    context.user_data["note_wizard"] = wizard
    return await _advance(update, context)


async def on_file_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """A photo/document arrived: use it when the wizard is waiting for one."""
    message = update.effective_message
    extracted = _extract_file(message) if message is not None else None
    if extracted is None:  # pragma: no cover - filters guarantee a file
        return NoteState.WIZARD

    wizard = context.user_data.get("note_wizard")
    user_id = await current_user_id(update, context)
    if wizard is None or user_id is None:
        # a free file outside the wizard: explain how to save it
        await answer(
            update,
            context,
            f"فایل دریافت شد، ولی برای ذخیره اول «📚 {NOTES[2:]}» را از منو بزن.\n"
            f"یا همین حالا «{ADD_NOTE}» را بزن.",
            reply_markup=inline_buttons([[(ADD_NOTE, "note:add")]]),
        )
        return ConversationHandler.END

    if wizard["field"] != "file":
        await answer(update, context, f"⚠️ {PROMPTS[wizard['field']]}")
        return NoteState.WIZARD

    wizard.setdefault("data", {})["file"] = extracted
    context.user_data["note_wizard"] = wizard
    return await _advance(update, context)


async def on_free_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """A photo/document sent outside the wizard: tell the user where to save it."""
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    await answer(
        update,
        context,
        "فایل دریافت شد، ولی ذخیره‌اش نیاز به مراحل دارد:\n"
        f"• جزوه: «📚 {NOTES.split(' ', 1)[-1]}» → «{ADD_NOTE}»\n"
        "• برنامه هفتگی: «📅 برنامه هفتگی»",
        reply_markup=inline_buttons([[(ADD_NOTE, "note:add")]]),
    )
    return ConversationHandler.END


async def on_course_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    wizard = context.user_data.get("note_wizard")
    user_id = await current_user_id(update, context)
    if wizard is None or user_id is None:
        return ConversationHandler.END

    value = (query.data or "").split(":")[-1]
    if value == "none":
        course_id: int | None = None
    else:
        course_id = int(value)
        # callback_data comes from the client: a note may only be linked to
        # a course that really belongs to the sender.
        async with get_session() as session:
            owned = await CourseRepository(session).get(course_id, user_id)
        if owned is None:
            await answer(update, context, "این درس پیدا نشد.")
            return await _render_field(update, context)

    wizard.setdefault("data", {})["course"] = course_id
    context.user_data["note_wizard"] = wizard
    if wizard["mode"] == "edit":
        return await _finish(update, context)
    return await _advance(update, context)


async def on_skip_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    wizard = context.user_data.get("note_wizard")
    user_id = await current_user_id(update, context)
    if wizard is None or user_id is None:
        return ConversationHandler.END

    wizard.setdefault("data", {})[wizard["field"]] = None
    context.user_data["note_wizard"] = wizard
    return await _advance(update, context)


# --- delete -------------------------------------------------------------
async def on_delete_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    note_id = int((query.data or "").split(":")[-1])
    await answer(
        update,
        context,
        "این جزوه حذف شود؟",
        reply_markup=inline_buttons(
            [
                [("✅ بله، حذف شود", f"note:delete:{note_id}:yes")],
                [(CANCEL, "note:delete:no")],
            ]
        ),
    )
    return NoteState.DETAIL


async def on_delete_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    note_id = int((query.data or "").split(":")[2])
    course_id: int | None = None

    async with get_session() as session:
        note = await NoteRepository(session).get(note_id, user_id)
        deleted = note is not None
        if note is not None:
            course_id = note.course_id
            await NoteRepository(session).delete(note)

    await answer(
        update, context, "✅ جزوه حذف شد." if deleted else "این جزوه پیدا نشد."
    )
    if deleted and course_id is not None:
        return await _show_course_notes(update, context, user_id, course_id)
    return await _show_menu(update, context, user_id)


async def on_delete_cancelled(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is not None:
        await query.answer()
    user_id = await current_user_id(update, context)
    if user_id is None:
        return ConversationHandler.END
    note_id = context.user_data.get("note_id")
    if note_id:
        return await _show_detail(update, context, user_id, int(note_id))
    return await _show_menu(update, context, user_id)


# --- conversation exits -------------------------------------------------
async def exit_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query is not None:
        await update.callback_query.answer()
    context.user_data.pop("note_wizard", None)
    await answer(update, context, "به منوی اصلی برگشتی 👇", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query is not None:
        await update.callback_query.answer()
    context.user_data.pop("note_wizard", None)
    context.user_data.pop("note_id", None)
    await answer(update, context, "عملیات لغو شد.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


def build_conversation() -> ConversationHandler:
    file_filter = filters.PHOTO | filters.Document.ALL
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Text([NOTES]), notes_menu),
            CallbackQueryHandler(notes_menu, pattern=r"^note:list$"),
            # saving a file that arrives before the wizard was opened
            MessageHandler(file_filter & ~filters.COMMAND, on_free_file),
        ],
        states={
            NoteState.MENU: [
                CallbackQueryHandler(
                    on_open_course, pattern=r"^note:bycourse:(?:\d+|none)$"
                ),
                CallbackQueryHandler(on_add_clicked, pattern=r"^note:add$"),
                CallbackQueryHandler(exit_conversation, pattern=r"^note:exit$"),
                MessageHandler(filters.Text([NOTES]), notes_menu),
            ],
            NoteState.COURSE: [
                CallbackQueryHandler(
                    on_open_course, pattern=r"^note:bycourse:(?:\d+|none)$"
                ),
                CallbackQueryHandler(on_open, pattern=r"^note:open:\d+$"),
                CallbackQueryHandler(on_add_clicked, pattern=r"^note:add$"),
                CallbackQueryHandler(notes_menu, pattern=r"^note:list$"),
                CallbackQueryHandler(exit_conversation, pattern=r"^note:exit$"),
                MessageHandler(filters.Text([NOTES]), notes_menu),
            ],
            NoteState.DETAIL: [
                CallbackQueryHandler(
                    on_open_course, pattern=r"^note:bycourse:(?:\d+|none)$"
                ),
                CallbackQueryHandler(on_edit_clicked, pattern=r"^note:edit:\d+:\w+$"),
                CallbackQueryHandler(on_delete_confirmed, pattern=r"^note:delete:\d+:yes$"),
                CallbackQueryHandler(on_delete_cancelled, pattern=r"^note:delete:no$"),
                CallbackQueryHandler(on_delete_clicked, pattern=r"^note:delete:\d+$"),
                CallbackQueryHandler(notes_menu, pattern=r"^note:list$"),
                CallbackQueryHandler(exit_conversation, pattern=r"^note:exit$"),
                MessageHandler(filters.Text([NOTES]), notes_menu),
            ],
            NoteState.WIZARD: [
                CallbackQueryHandler(on_course_chosen, pattern=r"^note:course:"),
                CallbackQueryHandler(on_skip_clicked, pattern=r"^note:skip$"),
                CallbackQueryHandler(notes_menu, pattern=r"^note:list$"),
                CallbackQueryHandler(exit_conversation, pattern=r"^note:exit$"),
                MessageHandler(file_filter & ~filters.COMMAND, on_file_received),
                MessageHandler(filters.TEXT & ~filters.COMMAND, on_wizard_text),
            ],
        },
        fallbacks=[
            CommandHandler(["start", "cancel"], cancel_conversation),
            MessageHandler(filters.Text([BACK]), cancel_conversation),
            CallbackQueryHandler(cancel_conversation, pattern=r"^note:cancel$"),
        ],
        name="notes_conversation",
        persistent=False,
        allow_reentry=True,
    )

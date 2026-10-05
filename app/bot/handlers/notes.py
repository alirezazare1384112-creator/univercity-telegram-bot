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
from app.bot.keyboards.main_menu import NOTES, main_menu_keyboard
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
def _list_text(notes: list, course_names: dict[int, str]) -> str:
    if not notes:
        return (
            "هنوز جزوه‌ای ذخیره نکرده‌ای.\n\n"
            f"با دکمه «{ADD_NOTE}» اولین فایلت را اضافه کن."
        )
    tz = get_settings().timezone
    lines = ["📚 جزوه‌های من", ""]
    for index, note in enumerate(notes, start=1):
        icon = "📷" if note.file_type == NOTE_PHOTO else "📄"
        course = course_names.get(note.course_id or 0)
        suffix = f" — {course}" if course else ""
        lines.append(
            f"{index}) {icon} {note.title}{suffix} "
            f"({format_jalali(note.created_at, tz)[:10]})"
        )
    return "\n".join(lines)


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


def _detail_keyboard(note_id: int):
    rows: list[list[tuple[str, str]]] = [
        [
            ("✏️ عنوان", f"note:edit:{note_id}:title"),
            ("✏️ توضیح", f"note:edit:{note_id}:description"),
        ],
        [("📖 تغییر درس", f"note:edit:{note_id}:course")],
        [("🗑 حذف جزوه", f"note:delete:{note_id}")],
        [("🔙 لیست جزوه‌ها", "note:list"), ("🔙 منوی اصلی", "note:exit")],
    ]
    return inline_buttons(rows)


# --- screens ------------------------------------------------------------
async def _load_courses(user_id: int):
    async with get_session() as session:
        return await CourseRepository(session).list_by_user(user_id)


async def _show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    async with get_session() as session:
        notes = await NoteRepository(session).list_by_user(user_id)
        courses = await CourseRepository(session).list_by_user(user_id)

    course_names = {course.id: course.name for course in courses}
    rows: list[list[tuple[str, str]]] = [
        [(("📷 " if n.file_type == NOTE_PHOTO else "📄 ") + n.title, f"note:open:{n.id}")]
        for n in notes
    ]
    rows.append([(ADD_NOTE, "note:add")])
    rows.append([("🔙 منوی اصلی", "note:exit")])
    await answer(
        update, context, _list_text(notes, course_names), reply_markup=inline_buttons(rows)
    )
    return NoteState.MENU


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
    keyboard = _detail_keyboard(note_id)
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


# --- wizard -------------------------------------------------------------
def _next_field(wizard: dict) -> str | None:
    if wizard["mode"] == "edit":
        return None
    try:
        index = CREATE_FIELDS.index(wizard["field"])
    except ValueError:  # pragma: no cover - defensive
        return None
    return CREATE_FIELDS[index + 1] if index + 1 < len(CREATE_FIELDS) else None


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
    return await _start_wizard(
        update,
        context,
        {"mode": "create", "note_id": None, "field": "title", "data": {}},
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

    async with get_session() as session:
        note = await NoteRepository(session).get(note_id, user_id)
        deleted = note is not None
        if note is not None:
            await NoteRepository(session).delete(note)

    await answer(
        update, context, "✅ جزوه حذف شد." if deleted else "این جزوه پیدا نشد."
    )
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
                CallbackQueryHandler(on_add_clicked, pattern=r"^note:add$"),
                CallbackQueryHandler(on_open, pattern=r"^note:open:\d+$"),
                CallbackQueryHandler(exit_conversation, pattern=r"^note:exit$"),
                MessageHandler(filters.Text([NOTES]), notes_menu),
            ],
            NoteState.DETAIL: [
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

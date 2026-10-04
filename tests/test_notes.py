"""📚 جزوه‌ها tests: wizard (title/file/course/description) and CRUD."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from telegram.ext import ConversationHandler

from app.bot.handlers.notes import (
    build_conversation,
    notes_menu,
    on_add_clicked,
    on_course_chosen,
    on_delete_cancelled,
    on_delete_clicked,
    on_delete_confirmed,
    on_edit_clicked,
    on_file_received,
    on_free_file,
    on_open,
    on_skip_clicked,
    on_wizard_text,
)
from app.bot.keyboards.main_menu import NOTES
from app.bot.middlewares import capture_user
from app.bot.states.note_states import NoteState
from app.database.database import get_session
from app.database.models import Note
from app.database.repositories import CourseRepository, NoteRepository, UserRepository
from tests.helpers import (
    FakeContext,
    make_callback_update,
    make_document_update,
    make_photo_update,
    make_text_update,
)


async def _register(telegram_id: int) -> FakeContext:
    context = FakeContext()
    await capture_user(make_text_update("/start", user_id=telegram_id), context)
    return context


async def _create_note(
    context: FakeContext,
    telegram_id: int,
    *,
    title: str = "فصل ۳ نرمال‌سازی",
    as_document: bool = False,
) -> int:
    """Drive the whole creation wizard and return the new note id."""
    user_id = context.user_data.get("user_id")
    async with get_session() as session:
        known_ids = {n.id for n in await NoteRepository(session).list_by_user(user_id)}

    await notes_menu(make_text_update(NOTES, user_id=telegram_id), context)
    await on_add_clicked(make_callback_update("note:add", user_id=telegram_id), context)
    await on_wizard_text(make_text_update(title, user_id=telegram_id), context)
    if as_document:
        await on_file_received(
            make_document_update(user_id=telegram_id), context
        )
    else:
        await on_file_received(make_photo_update(user_id=telegram_id), context)
    await on_course_chosen(
        make_callback_update("note:course:none", user_id=telegram_id), context
    )
    await on_skip_clicked(make_callback_update("note:skip", user_id=telegram_id), context)

    async with get_session() as session:
        notes = await NoteRepository(session).list_by_user(user_id)
    created = [note for note in notes if note.id not in known_ids]
    assert len(created) == 1
    return created[0].id


async def _create_course(context: FakeContext, telegram_id: int, name: str) -> int:
    user_id = context.user_data["user_id"]
    async with get_session() as session:
        course = await CourseRepository(session).create(user_id=user_id, name=name, units=3)
        return course.id


# --- menu ---------------------------------------------------------------
async def test_empty_menu_invites_the_student(db):
    context = await _register(7001)

    state = await notes_menu(make_text_update(NOTES, user_id=7001), context)

    assert state == NoteState.MENU
    assert "هنوز جزوه‌ای ذخیره نکرده‌ای" in context.sent_texts[-1]
    assert "➕ جزوه جدید" in str(context.last_markup)


async def test_list_shows_saved_notes(db):
    context = await _register(7002)
    await _create_note(context, 7002, title="حل تمرین ۱")

    context.bot.send_message.reset_mock()
    state = await notes_menu(make_text_update(NOTES, user_id=7002), context)

    assert state == NoteState.MENU
    assert "حل تمرین ۱" in context.sent_texts[-1]


# --- creation -----------------------------------------------------------
async def test_create_note_from_a_photo(db):
    context = await _register(7003)
    note_id = await _create_note(context, 7003, title="اسکن صفحه ۴۲")

    assert any("✅ جزوه ذخیره شد" in text for text in context.sent_texts)
    user_id = context.user_data["user_id"]
    async with get_session() as session:
        note = await NoteRepository(session).get(note_id, user_id)

    assert note.title == "اسکن صفحه ۴۲"
    assert note.file_type == "photo"
    assert note.file_id.startswith("photo-file-id")
    assert note.course_id is None
    assert note.description is None
    assert note.user_id == user_id

    # the detail screen resends the file with an informative caption
    context.bot.send_photo.assert_awaited()
    caption = context.bot.send_photo.call_args.kwargs["caption"]
    assert "اسکن صفحه ۴۲" in caption
    assert "افزوده شده" in caption


async def test_create_note_from_a_document(db):
    context = await _register(7004)
    note_id = await _create_note(context, 7004, title="جزوه PDF", as_document=True)

    user_id = context.user_data["user_id"]
    async with get_session() as session:
        note = await NoteRepository(session).get(note_id, user_id)

    assert note.file_type == "document"
    assert note.file_name == "schedule.png"
    context.bot.send_document.assert_awaited()
    assert context.bot.send_document.call_args.kwargs["document"] == note.file_id


async def test_note_can_be_linked_to_a_course(db):
    context = await _register(7005)
    course_id = await _create_course(context, 7005, "پایگاه داده")

    await notes_menu(make_text_update(NOTES, user_id=7005), context)
    await on_add_clicked(make_callback_update("note:add", user_id=7005), context)
    await on_wizard_text(make_text_update("نرمال‌سازی", user_id=7005), context)
    await on_file_received(make_photo_update(user_id=7005), context)
    state = await on_course_chosen(
        make_callback_update(f"note:course:{course_id}", user_id=7005), context
    )
    assert state == NoteState.WIZARD  # description step
    state = await on_skip_clicked(
        make_callback_update("note:skip", user_id=7005), context
    )
    assert state == NoteState.DETAIL

    user_id = context.user_data["user_id"]
    async with get_session() as session:
        notes = await NoteRepository(session).list_by_user(user_id)
    assert notes[0].course_id == course_id

    # the course name appears on the detail screen
    caption = context.bot.send_photo.call_args.kwargs["caption"]
    assert "پایگاه داده" in caption


async def test_empty_title_is_rejected(db):
    context = await _register(7006)
    await notes_menu(make_text_update(NOTES, user_id=7006), context)
    await on_add_clicked(make_callback_update("note:add", user_id=7006), context)

    state = await on_wizard_text(make_text_update("   ", user_id=7006), context)

    assert state == NoteState.WIZARD
    assert "⚠️" in context.sent_texts[-1]
    user_id = context.user_data["user_id"]
    async with get_session() as session:
        assert await NoteRepository(session).count(user_id) == 0


async def test_text_is_rejected_while_waiting_for_the_file(db):
    context = await _register(7007)
    await notes_menu(make_text_update(NOTES, user_id=7007), context)
    await on_add_clicked(make_callback_update("note:add", user_id=7007), context)
    await on_wizard_text(make_text_update("جزوه ریاضی", user_id=7007), context)

    state = await on_wizard_text(make_text_update("این متن است", user_id=7007), context)

    assert state == NoteState.WIZARD
    assert "فایل جزوه را بفرست" in context.sent_texts[-1]


async def test_file_outside_the_wizard_is_explained(db):
    context = await _register(7008)

    state = await on_free_file(make_photo_update(user_id=7008), context)

    assert state == ConversationHandler.END
    assert any("دریافت شد" in text for text in context.sent_texts)
    user_id = context.user_data["user_id"]
    async with get_session() as session:
        assert await NoteRepository(session).count(user_id) == 0


# --- edit / delete ------------------------------------------------------
async def test_edit_title(db):
    context = await _register(7009)
    note_id = await _create_note(context, 7009, title="عنوان قدیمی")

    state = await on_edit_clicked(
        make_callback_update(f"note:edit:{note_id}:title", user_id=7009), context
    )
    assert state == NoteState.WIZARD
    assert "عنوان جزوه" in context.sent_texts[-1]

    state = await on_wizard_text(
        make_text_update("عنوان تازه", user_id=7009), context
    )
    assert state == NoteState.DETAIL
    assert any("✅ تغییرات ذخیره شد" in text for text in context.sent_texts)

    user_id = context.user_data["user_id"]
    async with get_session() as session:
        note = await NoteRepository(session).get(note_id, user_id)
    assert note.title == "عنوان تازه"
    assert note.file_id.startswith("photo-file-id")  # file untouched


async def test_edit_course(db):
    context = await _register(7010)
    note_id = await _create_note(context, 7010)
    course_id = await _create_course(context, 7010, "آمار")

    await on_edit_clicked(
        make_callback_update(f"note:edit:{note_id}:course", user_id=7010), context
    )
    state = await on_course_chosen(
        make_callback_update(f"note:course:{course_id}", user_id=7010), context
    )

    assert state == NoteState.DETAIL
    user_id = context.user_data["user_id"]
    async with get_session() as session:
        note = await NoteRepository(session).get(note_id, user_id)
    assert note.course_id == course_id


async def test_delete_requires_confirmation(db):
    context = await _register(7011)
    note_id = await _create_note(context, 7011)

    state = await on_delete_clicked(
        make_callback_update(f"note:delete:{note_id}", user_id=7011), context
    )
    assert state == NoteState.DETAIL
    assert "حذف شود" in context.sent_texts[-1]

    user_id = context.user_data["user_id"]
    await on_delete_cancelled(make_callback_update("note:delete:no", user_id=7011), context)
    async with get_session() as session:
        assert await NoteRepository(session).get(note_id, user_id) is not None

    await on_delete_clicked(
        make_callback_update(f"note:delete:{note_id}", user_id=7011), context
    )
    state = await on_delete_confirmed(
        make_callback_update(f"note:delete:{note_id}:yes", user_id=7011), context
    )
    assert state == NoteState.MENU
    async with get_session() as session:
        assert await NoteRepository(session).get(note_id, user_id) is None


async def test_one_student_cannot_open_another_students_note(db):
    context_a = await _register(7012)
    note_id = await _create_note(context_a, 7012, title="خصوصی")

    context_b = await _register(7013)
    state = await on_open(
        make_callback_update(f"note:open:{note_id}", user_id=7013), context_b
    )

    assert state == NoteState.MENU
    assert any("پیدا نشد" in text for text in context_b.sent_texts)
    assert "خصوصی" not in "\n".join(context_b.sent_texts)


# --- database rules -----------------------------------------------------
async def test_database_rejects_an_unknown_file_type(session):
    user = await UserRepository(session).upsert_from_telegram(
        telegram_id=7014, username="u", first_name="U", last_name=None
    )
    await session.flush()
    session.add(
        Note(
            user_id=user.id,
            title="Bad",
            file_type="video",
            file_id="f",
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_deleting_a_user_removes_his_notes(session):
    user = await UserRepository(session).upsert_from_telegram(
        telegram_id=7015, username="u", first_name="U", last_name=None
    )
    await session.flush()
    await NoteRepository(session).create(
        user_id=user.id, title="N", file_type="photo", file_id="f"
    )
    await session.commit()

    await session.delete(user)
    await session.commit()

    assert await NoteRepository(session).count(user.id) == 0


def test_conversation_covers_the_three_states():
    handler = build_conversation()
    assert set(handler.states) == {
        NoteState.MENU,
        NoteState.DETAIL,
        NoteState.WIZARD,
    }

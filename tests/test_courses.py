"""📚 درس‌های من tests."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.bot.handlers.courses import (
    courses_menu,
    on_add_clicked,
    on_delete_cancelled,
    on_delete_clicked,
    on_delete_confirmed,
    on_edit_clicked,
    on_skip_clicked,
    on_wizard_text,
)
from app.bot.keyboards.main_menu import COURSES
from app.bot.middlewares import capture_user
from app.bot.states.course_states import CourseState
from app.database.database import get_session
from app.database.models import Course
from app.database.repositories import CourseRepository, UserRepository
from tests.helpers import FakeContext, make_callback_update, make_text_update


async def _register(user_id: int) -> FakeContext:
    context = FakeContext()
    await capture_user(make_text_update("/start", user_id=user_id), context)
    return context


async def _create_course(context: FakeContext, user_id: int, name="Database", units="3"):
    """Drive the whole creation wizard."""
    await courses_menu(make_text_update(COURSES, user_id=user_id), context)
    await on_add_clicked(make_callback_update("course:add", user_id=user_id), context)
    await on_wizard_text(make_text_update(name, user_id=user_id), context)
    await on_wizard_text(make_text_update(units, user_id=user_id), context)
    await on_skip_clicked(make_callback_update("course:skip", user_id=user_id), context)
    await on_wizard_text(make_text_update("1404-1", user_id=user_id), context)
    return await on_skip_clicked(
        make_callback_update("course:skip", user_id=user_id), context
    )


async def test_empty_list_invites_the_student(db):
    context = await _register(4001)
    state = await courses_menu(make_text_update(COURSES, user_id=4001), context)

    assert state == CourseState.MENU
    assert "هنوز درسی" in context.sent_texts[-1]


async def test_full_creation_wizard(db):
    context = await _register(4002)
    state = await _create_course(context, 4002, name="پایگاه داده", units="3")

    assert state == CourseState.DETAIL
    assert any("اضافه شد" in text for text in context.sent_texts)
    assert "پایگاه داده" in context.sent_texts[-1]

    async with get_session() as session:
        user = await UserRepository(session).get_by_telegram_id(4002)
        courses = await CourseRepository(session).list_by_user(user.id)
    assert len(courses) == 1
    course = courses[0]
    assert course.name == "پایگاه داده"
    assert course.units == 3
    assert course.teacher_name is None  # skipped
    assert course.semester == "1404-1"
    assert course.academic_year is None  # skipped


async def test_units_must_be_a_number(db):
    context = await _register(4003)
    await courses_menu(make_text_update(COURSES, user_id=4003), context)
    await on_add_clicked(make_callback_update("course:add", user_id=4003), context)
    await on_wizard_text(make_text_update("Software Eng", user_id=4003), context)

    state = await on_wizard_text(make_text_update("سه", user_id=4003), context)

    assert state == CourseState.WIZARD
    assert "عدد" in context.sent_texts[-1]

    async with get_session() as session:
        user = await UserRepository(session).get_by_telegram_id(4003)
        assert await CourseRepository(session).count(user.id) == 0


async def test_units_out_of_range_is_rejected(db):
    context = await _register(4004)
    await courses_menu(make_text_update(COURSES, user_id=4004), context)
    await on_add_clicked(make_callback_update("course:add", user_id=4004), context)
    await on_wizard_text(make_text_update("X", user_id=4004), context)
    state = await on_wizard_text(make_text_update("0", user_id=4004), context)
    assert state == CourseState.WIZARD
    state = await on_wizard_text(make_text_update("99", user_id=4004), context)
    assert state == CourseState.WIZARD


async def test_persian_digits_are_accepted_for_units(db):
    context = await _register(4005)
    await courses_menu(make_text_update(COURSES, user_id=4005), context)
    await on_add_clicked(make_callback_update("course:add", user_id=4005), context)
    await on_wizard_text(make_text_update("X", user_id=4005), context)
    state = await on_wizard_text(make_text_update("۲", user_id=4005), context)
    assert state == CourseState.WIZARD  # moved on to teacher_name

    await on_skip_clicked(make_callback_update("course:skip", user_id=4005), context)
    await on_skip_clicked(make_callback_update("course:skip", user_id=4005), context)
    state = await on_skip_clicked(
        make_callback_update("course:skip", user_id=4005), context
    )
    assert state == CourseState.DETAIL

    async with get_session() as session:
        user = await UserRepository(session).get_by_telegram_id(4005)
        courses = await CourseRepository(session).list_by_user(user.id)
    assert courses[0].units == 2


async def test_course_list_shows_totals(db):
    context = await _register(4006)
    await _create_course(context, 4006, name="DB", units="3")
    context.bot.send_message.reset_mock()

    state = await courses_menu(make_text_update(COURSES, user_id=4006), context)

    assert state == CourseState.MENU
    assert "مجموع واحد: 3" in context.sent_texts[-1]


async def test_edit_one_field(db):
    context = await _register(4007)
    await _create_course(context, 4007, name="DB", units="3")

    async with get_session() as session:
        user = await UserRepository(session).get_by_telegram_id(4007)
        user_id = user.id
        course = (await CourseRepository(session).list_by_user(user_id))[0]
        course_id = course.id

    state = await on_edit_clicked(
        make_callback_update(f"course:edit:{course_id}:units", user_id=4007), context
    )
    assert state == CourseState.WIZARD
    assert "تعداد واحد" in context.sent_texts[-1]

    state = await on_wizard_text(make_text_update("4", user_id=4007), context)
    assert state == CourseState.DETAIL

    async with get_session() as session:
        updated = await CourseRepository(session).get(course_id, user_id)
    assert updated.units == 4
    assert updated.name == "DB"  # untouched fields stay the same


async def test_delete_requires_confirmation(db):
    context = await _register(4008)
    await _create_course(context, 4008, name="DB", units="3")

    async with get_session() as session:
        user = await UserRepository(session).get_by_telegram_id(4008)
        user_id = user.id
        course = (await CourseRepository(session).list_by_user(user_id))[0]
        course_id = course.id

    state = await on_delete_clicked(
        make_callback_update(f"course:delete:{course_id}", user_id=4008), context
    )
    assert state == CourseState.DETAIL
    assert "حذف شود" in context.sent_texts[-1]

    # cancelling keeps the course
    await on_delete_cancelled(
        make_callback_update("course:delete:no", user_id=4008), context
    )
    async with get_session() as session:
        assert await CourseRepository(session).get(course_id, user_id) is not None

    await on_delete_clicked(
        make_callback_update(f"course:delete:{course_id}", user_id=4008), context
    )
    await on_delete_confirmed(
        make_callback_update(f"course:delete:{course_id}:yes", user_id=4008), context
    )
    async with get_session() as session:
        assert await CourseRepository(session).get(course_id, user_id) is None
        assert await CourseRepository(session).count(user_id) == 0


async def test_one_student_cannot_see_another_students_course(db):
    context_a = await _register(4009)
    await _create_course(context_a, 4009, name="SecretCourse", units="3")

    async with get_session() as session:
        user_a = await UserRepository(session).get_by_telegram_id(4009)
        course = (await CourseRepository(session).list_by_user(user_a.id))[0]

        user_b = await UserRepository(session).upsert_from_telegram(
            telegram_id=4010, username="other", first_name="Other", last_name=None
        )
        repo = CourseRepository(session)
        assert await repo.get(course.id, user_b.id) is None
        assert await repo.list_by_user(user_b.id) == []


async def test_database_rejects_zero_units(session):
    user = await UserRepository(session).upsert_from_telegram(
        telegram_id=4011, username="u", first_name="U", last_name=None
    )
    await session.flush()
    session.add(Course(user_id=user.id, name="Bad", units=0))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_deleting_a_user_removes_his_courses(session):
    user = await UserRepository(session).upsert_from_telegram(
        telegram_id=4012, username="u", first_name="U", last_name=None
    )
    await session.flush()
    await CourseRepository(session).create(user_id=user.id, name="DB", units=3)
    await session.commit()

    await session.delete(user)
    await session.commit()

    assert await CourseRepository(session).count(user.id) == 0

"""📝 نمرات من tests."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.bot.handlers.grades import (
    grades_menu,
    on_add_clicked,
    on_pick_course,
    on_skip_clicked,
    on_wizard_text,
)
from app.bot.keyboards.main_menu import COURSES, GRADES
from app.bot.middlewares import capture_user
from app.bot.states.grade_states import GradeState
from app.database.database import get_session
from app.database.models import GradeItem
from app.database.repositories import CourseRepository, GradeItemRepository, UserRepository
from tests.helpers import FakeContext, make_callback_update, make_text_update


async def _register(user_id: int) -> FakeContext:
    context = FakeContext()
    await capture_user(make_text_update("/start", user_id=user_id), context)
    return context


async def _create_course(context: FakeContext, user_id: int, name: str) -> int:
    from app.bot.handlers.courses import courses_menu
    from app.bot.handlers.courses import on_add_clicked as course_add
    from app.bot.handlers.courses import on_skip_clicked as course_skip
    from app.bot.handlers.courses import on_wizard_text as course_text

    await courses_menu(make_text_update(COURSES, user_id=user_id), context)
    await course_add(make_callback_update("course:add", user_id=user_id), context)
    await course_text(make_text_update(name, user_id=user_id), context)
    await course_text(make_text_update("3", user_id=user_id), context)
    await course_skip(make_callback_update("course:skip", user_id=user_id), context)
    await course_skip(make_callback_update("course:skip", user_id=user_id), context)
    await course_skip(make_callback_update("course:skip", user_id=user_id), context)

    async with get_session() as session:
        user = await UserRepository(session).get_by_telegram_id(user_id)
        course = (await CourseRepository(session).list_by_user(user.id))[0]
        return course.id


async def _add_grade(context: FakeContext, user_id: int, course_id: int,
                     title: str, max_score: str, score: str, description: str | None = None):
    # realistic navigation: pick the course first, then add an item
    from app.bot.handlers.grades import on_pick_course as pick

    await pick(
        make_callback_update(f"grades:course:{course_id}", user_id=user_id), context
    )
    await on_add_clicked(
        make_callback_update(f"grades:add:{course_id}", user_id=user_id), context
    )
    await on_wizard_text(make_text_update(title, user_id=user_id), context)
    await on_wizard_text(make_text_update(max_score, user_id=user_id), context)
    await on_wizard_text(make_text_update(score, user_id=user_id), context)
    if description is None:
        return await on_skip_clicked(
            make_callback_update("grades:skip", user_id=user_id), context
        )
    return await on_wizard_text(make_text_update(description, user_id=user_id), context)


async def test_menu_without_courses(db):
    context = await _register(5001)
    state = await grades_menu(make_text_update(GRADES, user_id=5001), context)
    assert state == GradeState.PICK_COURSE
    assert "درسی داشته باشی" in context.sent_texts[-1]


async def test_course_is_listed_then_grades_are_empty(db):
    context = await _register(5002)
    course_id = await _create_course(context, 5002, "DB")

    state = await grades_menu(make_text_update(GRADES, user_id=5002), context)
    assert state == GradeState.PICK_COURSE
    assert "کدام درس" in context.sent_texts[-1]

    state = await on_pick_course(
        make_callback_update(f"grades:course:{course_id}", user_id=5002), context
    )
    assert state == GradeState.ITEMS
    assert "ثبت نشده" in context.sent_texts[-1]


async def test_add_a_grade_item(db):
    context = await _register(5003)
    course_id = await _create_course(context, 5003, "DB")
    state = await _add_grade(context, 5003, course_id, "Midterm", "8", "6")

    assert state == GradeState.DETAIL
    assert any("ثبت شد" in text for text in context.sent_texts)

    async with get_session() as session:
        items = await GradeItemRepository(session).list_by_course(course_id)
    assert len(items) == 1
    assert items[0].title == "Midterm"
    assert items[0].max_score == 8.0
    assert items[0].score == 6.0
    assert items[0].description is None
    assert items[0].percent == 75.0


async def test_score_greater_than_max_is_rejected(db):
    context = await _register(5004)
    course_id = await _create_course(context, 5004, "DB")

    await on_add_clicked(
        make_callback_update(f"grades:add:{course_id}", user_id=5004), context
    )
    await on_wizard_text(make_text_update("Midterm", user_id=5004), context)
    await on_wizard_text(make_text_update("10", user_id=5004), context)

    state = await on_wizard_text(make_text_update("15", user_id=5004), context)

    assert state == GradeState.WIZARD
    assert "بزرگ‌تر از نمره کامل" in context.sent_texts[-1]

    async with get_session() as session:
        assert await GradeItemRepository(session).count(course_id) == 0


async def test_negative_and_non_numeric_scores_are_rejected(db):
    context = await _register(5005)
    course_id = await _create_course(context, 5005, "DB")
    await on_add_clicked(
        make_callback_update(f"grades:add:{course_id}", user_id=5005), context
    )
    await on_wizard_text(make_text_update("Quiz", user_id=5005), context)
    await on_wizard_text(make_text_update("10", user_id=5005), context)

    state = await on_wizard_text(make_text_update("-2", user_id=5005), context)
    assert state == GradeState.WIZARD
    state = await on_wizard_text(make_text_update("abc", user_id=5005), context)
    assert state == GradeState.WIZARD

    async with get_session() as session:
        assert await GradeItemRepository(session).count(course_id) == 0


async def test_zero_max_score_is_rejected(db):
    context = await _register(5006)
    course_id = await _create_course(context, 5006, "DB")
    await on_add_clicked(
        make_callback_update(f"grades:add:{course_id}", user_id=5006), context
    )
    await on_wizard_text(make_text_update("Final", user_id=5006), context)
    state = await on_wizard_text(make_text_update("0", user_id=5006), context)
    assert state == GradeState.WIZARD
    assert "بزرگ‌تر از صفر" in context.sent_texts[-1]


async def test_persian_digits_and_decimal_separator(db):
    context = await _register(5007)
    course_id = await _create_course(context, 5007, "DB")
    state = await _add_grade(context, 5007, course_id, "Project", "۲۰", "۱۵٫۵")
    assert state == GradeState.DETAIL

    async with get_session() as session:
        items = await GradeItemRepository(session).list_by_course(course_id)
    assert items[0].max_score == 20.0
    assert items[0].score == 15.5


async def test_summary_shows_totals(db):
    context = await _register(5008)
    course_id = await _create_course(context, 5008, "DB")
    await _add_grade(context, 5008, course_id, "Midterm", "8", "6")
    await _add_grade(context, 5008, course_id, "Homework", "2", "1.5")

    context.bot.send_message.reset_mock()
    from app.bot.handlers.grades import on_pick_course as pick

    await pick(
        make_callback_update(f"grades:course:{course_id}", user_id=5008), context
    )
    text = context.sent_texts[-1]
    assert "مجموع: 7.5 از 10" in text
    assert "(75.0%)" in text


async def test_database_rejects_score_above_max(session):
    user = await UserRepository(session).upsert_from_telegram(
        telegram_id=5009, username="u", first_name="U", last_name=None
    )
    await session.flush()
    course = await CourseRepository(session).create(user_id=user.id, name="DB", units=3)
    await session.flush()

    session.add(
        GradeItem(course_id=course.id, title="Bad", score=15.0, max_score=10.0)
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_database_rejects_negative_score(session):
    user = await UserRepository(session).upsert_from_telegram(
        telegram_id=5010, username="u", first_name="U", last_name=None
    )
    await session.flush()
    course = await CourseRepository(session).create(user_id=user.id, name="DB", units=3)
    await session.flush()

    session.add(GradeItem(course_id=course.id, title="Bad", score=-1.0, max_score=10.0))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_deleting_course_removes_its_grades(session):
    user = await UserRepository(session).upsert_from_telegram(
        telegram_id=5011, username="u", first_name="U", last_name=None
    )
    await session.flush()
    course = await CourseRepository(session).create(user_id=user.id, name="DB", units=3)
    await GradeItemRepository(session).create(
        course_id=course.id, title="Mid", score=6.0, max_score=8.0
    )
    await session.commit()

    await CourseRepository(session).delete(course)
    await session.commit()

    assert await GradeItemRepository(session).count(course.id) == 0

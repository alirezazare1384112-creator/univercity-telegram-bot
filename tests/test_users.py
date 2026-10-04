"""User repository tests (Phase 1)."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.database.models import User
from app.database.repositories import AdminRepository, UserRepository


async def test_first_contact_creates_the_user(session):
    repo = UserRepository(session)
    user = await repo.upsert_from_telegram(
        telegram_id=111, username="alireza", first_name="Alireza", last_name="Test"
    )
    await session.flush()

    assert user.id is not None
    assert user.telegram_id == 111
    assert user.is_active is True
    assert user.created_at is not None
    assert user.updated_at is not None


async def test_second_contact_updates_profile_without_duplicate(session):
    repo = UserRepository(session)
    first = await repo.upsert_from_telegram(
        telegram_id=222, username="old", first_name="A", last_name=None
    )
    second = await repo.upsert_from_telegram(
        telegram_id=222, username="new", first_name="A", last_name="B"
    )

    assert first.id == second.id
    assert second.username == "new"
    assert second.last_name == "B"
    assert await repo.count() == 1


async def test_telegram_id_must_be_unique(session):
    repo = UserRepository(session)
    await repo.upsert_from_telegram(telegram_id=333, username="a", first_name="A", last_name=None)
    session.add(
        User(telegram_id=333, username="b", first_name="B", is_active=True)
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_get_by_telegram_id_returns_none_for_unknown(session):
    repo = UserRepository(session)
    assert await repo.get_by_telegram_id(999) is None


async def test_update_profile_fields(session):
    repo = UserRepository(session)
    user = await repo.upsert_from_telegram(
        telegram_id=444, username="u", first_name="U", last_name=None
    )
    await repo.update_profile(
        user,
        student_number="402123456",
        field_of_study="Computer Engineering",
        university="Test University",
        semester="1404-1",
    )
    assert user.student_number == "402123456"
    assert user.semester == "1404-1"


async def test_update_profile_rejects_unknown_field(session):
    repo = UserRepository(session)
    user = await repo.upsert_from_telegram(
        telegram_id=445, username="u", first_name="U", last_name=None
    )
    with pytest.raises(AttributeError):
        await repo.update_profile(user, wrong_field="x")


async def test_deactivate_user_and_count(session):
    repo = UserRepository(session)
    user = await repo.upsert_from_telegram(
        telegram_id=555, username="u", first_name="U", last_name=None
    )
    assert await repo.count(active_only=True) == 1
    await repo.deactivate(user)
    assert await repo.count(active_only=True) == 0
    assert await repo.count() == 1
    assert await repo.list_active_telegram_ids() == []


async def test_admin_is_checked_by_telegram_id(session):
    repo = AdminRepository(session)
    assert await repo.is_admin(12345, allow_config=False) is False

    await repo.upsert(telegram_id=12345, username="boss", first_name="Boss")
    assert await repo.is_admin(12345, allow_config=False) is True
    assert (await repo.get_by_telegram_id(12345)).is_active is True
    assert len(await repo.list_all()) == 1

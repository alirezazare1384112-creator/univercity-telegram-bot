"""🔗 سامانه‌های دانشگاه tests: wizard, url validation and CRUD."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.bot.handlers.links import (
    IMPORTANT_LINKS,
    build_conversation,
    links_menu,
    on_add_clicked,
    on_delete_cancelled,
    on_delete_clicked,
    on_delete_confirmed,
    on_edit_clicked,
    on_manage_clicked,
    on_open,
    on_skip_clicked,
    on_wizard_text,
)
from app.bot.keyboards.main_menu import LINKS
from app.bot.middlewares import capture_user
from app.bot.states.link_states import LinkState
from app.database.database import get_session
from app.database.models import UniversityLink
from app.database.repositories import LinkRepository, UserRepository
from app.utils.validation import validate_url
from tests.helpers import FakeContext, make_callback_update, make_text_update


async def _register(telegram_id: int) -> FakeContext:
    context = FakeContext()
    await capture_user(make_text_update("/start", user_id=telegram_id), context)
    return context


async def _create_link(
    context: FakeContext,
    telegram_id: int,
    *,
    title: str = "آموزش یکپارچه",
    url: str = "https://portal.university.ir",
) -> int:
    """Drive the whole creation wizard and return the new link id."""
    user_id = context.user_data.get("user_id")
    async with get_session() as session:
        known_ids = {item.id for item in await LinkRepository(session).list_by_user(user_id)}

    await links_menu(make_text_update(LINKS, user_id=telegram_id), context)
    await on_add_clicked(make_callback_update("link:add", user_id=telegram_id), context)
    await on_wizard_text(make_text_update(title, user_id=telegram_id), context)
    await on_wizard_text(make_text_update(url, user_id=telegram_id), context)
    await on_skip_clicked(make_callback_update("link:skip", user_id=telegram_id), context)

    async with get_session() as session:
        links = await LinkRepository(session).list_by_user(user_id)
    created = [link for link in links if link.id not in known_ids]
    assert len(created) == 1
    return created[0].id


# --- menu ---------------------------------------------------------------
async def test_empty_menu_invites_the_student(db):
    context = await _register(8001)

    state = await links_menu(make_text_update(LINKS, user_id=8001), context)

    assert state == LinkState.MENU
    assert "هنوز لینکی ذخیره نکرده‌ای" in context.sent_texts[-1]
    assert "➕ لینک جدید" in str(context.last_markup)


async def test_menu_shows_a_button_that_opens_the_site(db):
    context = await _register(8002)
    link_id = await _create_link(context, 8002, title="کتابخانه مرکزی")

    context.bot.send_message.reset_mock()
    state = await links_menu(make_text_update(LINKS, user_id=8002), context)

    assert state == LinkState.MENU
    assert "روی هر کدام بزن" in context.sent_texts[-1]

    keyboard = context.last_markup.inline_keyboard
    # the title lives on the button, and that button opens the URL directly
    assert keyboard[0][0].text == "کتابخانه مرکزی"
    assert keyboard[0][0].url == "https://portal.university.ir"
    assert keyboard[0][0].callback_data is None
    assert any(
        button.callback_data == "link:manage" for row in keyboard for button in row
    )
    assert link_id > 0


async def test_menu_shows_the_important_university_sites(db):
    context = await _register(8014)

    await links_menu(make_text_update(LINKS, user_id=8014), context)

    urls = [
        button.url
        for row in context.last_markup.inline_keyboard
        for button in row
        if button.url
    ]
    assert urls == [url for _, url in IMPORTANT_LINKS]
    assert len(urls) == 4


# --- creation -----------------------------------------------------------
async def test_full_creation_wizard(db):
    context = await _register(8003)
    link_id = await _create_link(
        context, 8003, title="نمرات", url="https://scores.university.ir"
    )

    assert any("✅ لینک ذخیره شد" in text for text in context.sent_texts)
    assert "📌 عنوان: نمرات" in context.sent_texts[-1]

    user_id = context.user_data["user_id"]
    async with get_session() as session:
        link = await LinkRepository(session).get(link_id, user_id)
    assert link.title == "نمرات"
    assert link.url == "https://scores.university.ir"
    assert link.description is None


async def test_missing_scheme_is_added(db):
    context = await _register(8004)
    link_id = await _create_link(
        context, 8004, title="پورتال", url="portal.university.ir"
    )

    user_id = context.user_data["user_id"]
    async with get_session() as session:
        link = await LinkRepository(session).get(link_id, user_id)
    assert link.url == "https://portal.university.ir"


async def test_empty_title_is_rejected(db):
    context = await _register(8005)
    await links_menu(make_text_update(LINKS, user_id=8005), context)
    await on_add_clicked(make_callback_update("link:add", user_id=8005), context)

    state = await on_wizard_text(make_text_update("  ", user_id=8005), context)

    assert state == LinkState.WIZARD
    assert "⚠️" in context.sent_texts[-1]
    user_id = context.user_data["user_id"]
    async with get_session() as session:
        assert await LinkRepository(session).count(user_id) == 0


async def test_schemeless_junk_is_rejected(db):
    context = await _register(8006)
    await links_menu(make_text_update(LINKS, user_id=8006), context)
    await on_add_clicked(make_callback_update("link:add", user_id=8006), context)
    await on_wizard_text(make_text_update("لینک", user_id=8006), context)

    state = await on_wizard_text(make_text_update("بدون آدرس", user_id=8006), context)

    assert state == LinkState.WIZARD
    assert "http" in context.sent_texts[-1]


# --- edit / manage / delete --------------------------------------------
async def test_edit_title(db):
    context = await _register(8007)
    link_id = await _create_link(context, 8007)

    state = await on_edit_clicked(
        make_callback_update(f"link:edit:{link_id}:title", user_id=8007), context
    )
    assert state == LinkState.WIZARD
    assert "عنوان سامانه" in context.sent_texts[-1]

    state = await on_wizard_text(make_text_update("عنوان تازه", user_id=8007), context)
    assert state == LinkState.DETAIL
    assert any("✅ تغییرات ذخیره شد" in text for text in context.sent_texts)

    user_id = context.user_data["user_id"]
    async with get_session() as session:
        link = await LinkRepository(session).get(link_id, user_id)
    assert link.title == "عنوان تازه"
    assert link.url == "https://portal.university.ir"  # untouched


async def test_manage_screen_lists_every_link(db):
    context = await _register(8008)
    await _create_link(context, 8008, title="لینک اول")

    state = await on_manage_clicked(
        make_callback_update("link:manage", user_id=8008), context
    )

    assert state == LinkState.MANAGE
    assert "مدیریت لینک‌ها" in context.sent_texts[-1]
    # link titles are buttons, not message text
    assert "لینک اول" in str(context.last_markup)


async def test_delete_requires_confirmation(db):
    context = await _register(8009)
    link_id = await _create_link(context, 8009)

    state = await on_delete_clicked(
        make_callback_update(f"link:delete:{link_id}", user_id=8009), context
    )
    assert state == LinkState.DETAIL
    assert "حذف شود" in context.sent_texts[-1]

    user_id = context.user_data["user_id"]
    await on_delete_cancelled(make_callback_update("link:delete:no", user_id=8009), context)
    async with get_session() as session:
        assert await LinkRepository(session).get(link_id, user_id) is not None

    await on_delete_clicked(
        make_callback_update(f"link:delete:{link_id}", user_id=8009), context
    )
    state = await on_delete_confirmed(
        make_callback_update(f"link:delete:{link_id}:yes", user_id=8009), context
    )
    # the manage screen falls back to the menu when nothing is left to manage
    assert state == LinkState.MENU
    async with get_session() as session:
        assert await LinkRepository(session).get(link_id, user_id) is None


async def test_one_student_cannot_open_another_students_link(db):
    context_a = await _register(8010)
    link_id = await _create_link(context_a, 8010, title="خصوصی")

    context_b = await _register(8011)
    state = await on_open(
        make_callback_update(f"link:open:{link_id}", user_id=8011), context_b
    )

    assert state == LinkState.MENU
    assert any("پیدا نشد" in text for text in context_b.sent_texts)
    assert "خصوصی" not in "\n".join(context_b.sent_texts)


# --- validation ---------------------------------------------------------
def test_validate_url_accepts_and_normalises():
    ok, value, _ = validate_url("https://a.ir")
    assert ok and value == "https://a.ir"

    ok, value, _ = validate_url("http://a.ir")
    assert ok and value == "http://a.ir"

    ok, value, _ = validate_url("a.ir")
    assert ok and value == "https://a.ir"


def test_validate_url_rejects_dangerous_schemes():
    for bad in ("javascript:alert(1)", "javascript://x", "data:text/html,x", "ftp://x.ir", ""):
        ok, value, error = validate_url(bad)
        assert not ok, bad
        assert value == ""
        assert error


# --- database rules -----------------------------------------------------
async def test_database_rejects_a_non_http_url(session):
    user = await UserRepository(session).upsert_from_telegram(
        telegram_id=8012, username="u", first_name="U", last_name=None
    )
    await session.flush()
    session.add(
        UniversityLink(user_id=user.id, title="Bad", url="javascript:alert(1)")
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_deleting_a_user_removes_his_links(session):
    user = await UserRepository(session).upsert_from_telegram(
        telegram_id=8013, username="u", first_name="U", last_name=None
    )
    await session.flush()
    await LinkRepository(session).create(
        user_id=user.id, title="L", url="https://x.ir"
    )
    await session.commit()

    await session.delete(user)
    await session.commit()

    assert await LinkRepository(session).count(user.id) == 0


def test_conversation_covers_the_four_states():
    handler = build_conversation()
    assert set(handler.states) == {
        LinkState.MENU,
        LinkState.MANAGE,
        LinkState.DETAIL,
        LinkState.WIZARD,
    }

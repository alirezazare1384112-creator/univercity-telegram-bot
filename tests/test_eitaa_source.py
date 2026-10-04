"""📮 منبع ایتا tests: saving Eitaa announcements without an external API."""

from __future__ import annotations

from app.bot.handlers.announcements import (
    _first_eitaa_link,
    announcements_menu,
    on_add_clicked,
    on_post_text,
    on_source_clicked,
)
from app.bot.keyboards.main_menu import ANNOUNCEMENTS
from app.bot.middlewares import capture_user
from app.bot.states.announcement_states import AnnouncementState
from app.database.database import get_session
from app.database.models.announcement import ANNOUNCEMENT_EITAA, ANNOUNCEMENT_TELEGRAM
from app.database.repositories import AnnouncementRepository
from tests.helpers import FakeContext, make_callback_update, make_text_update


async def _register(telegram_id: int) -> FakeContext:
    context = FakeContext()
    await capture_user(make_text_update("/start", user_id=telegram_id), context)
    return context


async def _start_waiting(context: FakeContext, telegram_id: int) -> int:
    await announcements_menu(make_text_update(ANNOUNCEMENTS, user_id=telegram_id), context)
    state = await on_add_clicked(
        make_callback_update("ann:add", user_id=telegram_id), context
    )
    assert state == AnnouncementState.WAITING
    return context.user_data["user_id"]


# --- source choice ------------------------------------------------------
async def test_add_asks_where_the_announcement_comes_from(db):
    context = await _register(9101)

    user_id = await _start_waiting(context, 9101)

    assert user_id > 0  # the helper already asserted the WAITING state
    assert "از کجا آمده" in context.sent_texts[-1]
    keyboard = str(context.last_markup)
    assert "📨 از تلگرام" in keyboard
    assert "📮 از ایتا" in keyboard


async def test_eitaa_button_explains_the_paste_flow(db):
    context = await _register(9102)
    await _start_waiting(context, 9102)

    state = await on_source_clicked(
        make_callback_update("ann:src:eitaa", user_id=9102), context
    )

    assert state == AnnouncementState.WAITING
    assert "لینک" in context.sent_texts[-1]
    assert "eitaa.com" in context.sent_texts[-1]
    assert context.user_data["ann_source"] == ANNOUNCEMENT_EITAA


async def test_telegram_button_keeps_the_forward_flow(db):
    context = await _register(9103)
    await _start_waiting(context, 9103)

    state = await on_source_clicked(
        make_callback_update("ann:src:telegram", user_id=9103), context
    )

    assert state == AnnouncementState.WAITING
    assert "فوروارد" in context.sent_texts[-1]
    assert context.user_data["ann_source"] == ANNOUNCEMENT_TELEGRAM


# --- saving -------------------------------------------------------------
async def test_pasted_eitaa_text_saves_source_and_link(db):
    context = await _register(9104)
    user_id = await _start_waiting(context, 9104)
    await on_source_clicked(
        make_callback_update("ann:src:eitaa", user_id=9104), context
    )

    state = await on_post_text(
        make_text_update(
            "برنامه امتحانات نهایی\nhttps://eitaa.com/uni_channel/55",
            user_id=9104,
        ),
        context,
    )

    assert state == AnnouncementState.DETAIL
    async with get_session() as session:
        announcement = (await AnnouncementRepository(session).list_by_user(user_id))[0]
    assert announcement.source == ANNOUNCEMENT_EITAA
    assert announcement.source_url == "https://eitaa.com/uni_channel/55"
    assert announcement.title == "برنامه امتحانات نهایی"
    assert announcement.text.startswith("برنامه امتحانات")
    # the detail screen offers a button that opens the original post
    assert context.last_markup.inline_keyboard[0][0].url == (
        "https://eitaa.com/uni_channel/55"
    )
    assert "📮 منبع: ایتا" in context.sent_texts[-1]


async def test_eitaa_link_only_becomes_the_title(db):
    context = await _register(9105)
    user_id = await _start_waiting(context, 9105)
    await on_source_clicked(
        make_callback_update("ann:src:eitaa", user_id=9105), context
    )

    state = await on_post_text(
        make_text_update("https://eitaa.com/notice/9", user_id=9105), context
    )

    assert state == AnnouncementState.DETAIL
    async with get_session() as session:
        announcement = (await AnnouncementRepository(session).list_by_user(user_id))[0]
    assert announcement.title == "https://eitaa.com/notice/9"
    assert announcement.source_url == "https://eitaa.com/notice/9"


async def test_eitaa_text_without_link_is_still_saved(db):
    context = await _register(9106)
    user_id = await _start_waiting(context, 9106)
    await on_source_clicked(
        make_callback_update("ann:src:eitaa", user_id=9106), context
    )

    state = await on_post_text(
        make_text_update("اطلاعیه بدون لینک", user_id=9106), context
    )

    assert state == AnnouncementState.DETAIL
    async with get_session() as session:
        announcement = (await AnnouncementRepository(session).list_by_user(user_id))[0]
    assert announcement.source == ANNOUNCEMENT_EITAA
    assert announcement.source_url is None
    assert announcement.title == "اطلاعیه بدون لینک"


async def test_default_flow_stays_telegram(db):
    context = await _register(9107)
    user_id = await _start_waiting(context, 9107)
    # no source button pressed: forwarding right away must work
    state = await on_post_text(
        make_text_update("اطلاعیه تلگرام", user_id=9107), context
    )

    assert state == AnnouncementState.DETAIL
    async with get_session() as session:
        announcement = (await AnnouncementRepository(session).list_by_user(user_id))[0]
    assert announcement.source == ANNOUNCEMENT_TELEGRAM
    assert announcement.source_url is None


async def test_menu_marks_eitaa_items_with_their_icon(db):
    context = await _register(9108)
    await _start_waiting(context, 9108)
    await on_source_clicked(
        make_callback_update("ann:src:eitaa", user_id=9108), context
    )
    await on_post_text(
        make_text_update("اطلاعیه ایتا\nhttps://eitaa.com/c/1", user_id=9108), context
    )

    context.bot.send_message.reset_mock()
    state = await announcements_menu(make_text_update(ANNOUNCEMENTS, user_id=9108), context)

    assert state == AnnouncementState.MENU
    assert "1) 📮" in context.sent_texts[-1]
    open_buttons = [
        button
        for row in context.last_markup.inline_keyboard
        for button in row
        if (button.callback_data or "").startswith("ann:open:")
    ]
    # the list button is a callback (the URL lives on the detail screen)
    assert open_buttons and open_buttons[0].text.startswith("📮")


# --- link extraction ----------------------------------------------------
def test_first_eitaa_link_is_found_and_cleaned():
    assert (
        _first_eitaa_link("متن https://eitaa.com/ch/1.")
        == "https://eitaa.com/ch/1"
    )
    assert (
        _first_eitaa_link("https://www.eitaa.ir/x/2، بعدی")
        == "https://www.eitaa.ir/x/2"
    )
    assert _first_eitaa_link("HTTPS://EITAA.COM/UP/3") == "HTTPS://EITAA.COM/UP/3"


def test_first_eitaa_link_ignores_other_sites():
    assert _first_eitaa_link("https://t.me/uni/1") is None
    assert _first_eitaa_link("eitaa.com/without-scheme") is None
    assert _first_eitaa_link("بدون لینک") is None
    assert _first_eitaa_link(None) is None

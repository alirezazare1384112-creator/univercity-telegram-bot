"""📢 اطلاعیه‌ها tests: forward-to-save, origin info, CRUD and scope."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from telegram import Chat, MessageOriginChannel

from app.bot.handlers.announcements import (
    _derive_title,
    announcements_menu,
    build_conversation,
    on_add_clicked,
    on_delete_cancelled,
    on_delete_clicked,
    on_delete_confirmed,
    on_open,
    on_post_file,
    on_post_text,
)
from app.bot.keyboards.main_menu import ANNOUNCEMENTS
from app.bot.middlewares import capture_user
from app.bot.states.announcement_states import AnnouncementState
from app.database.database import get_session
from app.database.models import Announcement
from app.database.models.announcement import ANNOUNCEMENT_TELEGRAM, MAX_TEXT_LENGTH
from app.database.repositories import AnnouncementRepository, UserRepository
from tests.helpers import FakeContext, make_callback_update, make_photo_update, make_text_update


def _origin(
    title: str = "کانال دانشگاه", username: str = "uni_channel", message_id: int = 42
) -> MessageOriginChannel:
    return MessageOriginChannel(
        date=datetime.now(UTC),
        chat=Chat(id=-100123456, type="channel", title=title, username=username),
        message_id=message_id,
    )


async def _register(telegram_id: int) -> FakeContext:
    context = FakeContext()
    await capture_user(make_text_update("/start", user_id=telegram_id), context)
    return context


async def _start_waiting(context: FakeContext, telegram_id: int):
    await announcements_menu(make_text_update(ANNOUNCEMENTS, user_id=telegram_id), context)
    return await on_add_clicked(
        make_callback_update("ann:add", user_id=telegram_id), context
    )


# --- menu ---------------------------------------------------------------
async def test_empty_menu_invites_the_student(db):
    context = await _register(9001)

    state = await announcements_menu(make_text_update(ANNOUNCEMENTS, user_id=9001), context)

    assert state == AnnouncementState.MENU
    assert "هنوز اطلاعیه‌ای ذخیره نکرده‌ای" in context.sent_texts[-1]
    assert "➕ ذخیره اطلاعیه" in str(context.last_markup)


async def test_add_asks_for_the_forwarded_post(db):
    context = await _register(9002)

    state = await _start_waiting(context, 9002)

    assert state == AnnouncementState.WAITING
    assert "فوروارد" in context.sent_texts[-1]
    assert "❌ لغو" in str(context.last_markup)


async def test_menu_has_url_buttons_for_the_eitaa_channels(db):
    context = await _register(9013)

    await announcements_menu(make_text_update(ANNOUNCEMENTS, user_id=9013), context)

    markup = context.last_markup
    urls = [b.url for row in markup.inline_keyboard for b in row if b.url]
    assert urls == [
        "https://eitaa.com/ArdakanUni_Resaneh",
        "https://eitaa.com/atriardakani",
    ]
    callbacks = [
        b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data
    ]
    assert "ann:add" in callbacks
    assert "ann:exit" in callbacks


# --- saving -------------------------------------------------------------
async def test_forwarded_channel_post_is_saved(db):
    context = await _register(9003)
    await _start_waiting(context, 9003)

    update = make_text_update(
        "تست پایان‌ترم فردا ساعت ۹ برگزار می‌شود",
        user_id=9003,
        forward_origin=_origin(),
    )
    state = await on_post_text(update, context)

    assert state == AnnouncementState.DETAIL
    user_id = context.user_data["user_id"]
    async with get_session() as session:
        announcements = await AnnouncementRepository(session).list_by_user(user_id)
    assert len(announcements) == 1
    item = announcements[0]
    # the channel title becomes the title, and the direct link is rebuilt
    assert item.title == "کانال دانشگاه"
    assert item.source_url == "https://t.me/uni_channel/42"
    assert item.source == ANNOUNCEMENT_TELEGRAM
    assert item.text == "تست پایان‌ترم فردا ساعت ۹ برگزار می‌شود"
    assert "✅ اطلاعیه ذخیره شد" in context.sent_texts[-2]
    assert "🔗 پیوند: https://t.me/uni_channel/42" in context.sent_texts[-1]


async def test_typed_announcement_uses_first_line_as_title(db):
    context = await _register(9004)
    await _start_waiting(context, 9004)

    update = make_text_update("برنامه امتحانات\nجزئیات در وب‌سایت", user_id=9004)
    state = await on_post_text(update, context)

    assert state == AnnouncementState.DETAIL
    user_id = context.user_data["user_id"]
    async with get_session() as session:
        announcement = (await AnnouncementRepository(session).list_by_user(user_id))[0]
    assert announcement.title == "برنامه امتحانات"
    assert announcement.source_url is None  # nothing was forwarded


async def test_photo_announcement_keeps_the_file_and_caption(db):
    context = await _register(9005)
    await _start_waiting(context, 9005)

    update = make_photo_update(
        "poster-file-id",
        caption="بنر ثبت‌نام مهمانی",
        user_id=9005,
        forward_origin=_origin(title="روابط عمومی", username="pr_channel"),
    )
    state = await on_post_file(update, context)

    assert state == AnnouncementState.DETAIL
    # the media is re-sent from Telegram, no upload happens
    assert context.bot.send_photo.call_count == 1
    assert context.bot.send_photo.call_args.kwargs["photo"] == "poster-file-id"

    user_id = context.user_data["user_id"]
    async with get_session() as session:
        announcement = (await AnnouncementRepository(session).list_by_user(user_id))[0]
    assert announcement.file_type == "photo"
    assert announcement.file_id == "poster-file-id"
    assert announcement.text == "بنر ثبت‌نام مهمانی"
    assert announcement.title == "روابط عمومی"


async def test_menu_label_stops_the_wait_without_saving(db):
    context = await _register(9006)
    await _start_waiting(context, 9006)

    state = await on_post_text(make_text_update(ANNOUNCEMENTS, user_id=9006), context)

    assert state == AnnouncementState.MENU
    user_id = context.user_data["user_id"]
    async with get_session() as session:
        assert await AnnouncementRepository(session).count(user_id) == 0


async def test_cancel_text_keeps_the_inbox_empty(db):
    context = await _register(9007)
    await _start_waiting(context, 9007)

    state = await on_post_text(make_text_update("❌ لغو", user_id=9007), context)

    assert state == AnnouncementState.MENU
    assert any("لغو شد" in text for text in context.sent_texts)
    user_id = context.user_data["user_id"]
    async with get_session() as session:
        assert await AnnouncementRepository(session).count(user_id) == 0


# --- browsing / delete --------------------------------------------------
async def test_menu_lists_saved_announcements(db):
    context = await _register(9008)
    await _start_waiting(context, 9008)
    await on_post_text(
        make_text_update("اطلاعیه مهم", user_id=9008, forward_origin=_origin()), context
    )

    context.bot.send_message.reset_mock()
    state = await announcements_menu(make_text_update(ANNOUNCEMENTS, user_id=9008), context)

    assert state == AnnouncementState.MENU
    # the list shows titles (here the channel name), not the raw body
    assert "1) 📨 کانال دانشگاه" in context.sent_texts[-1]
    assert any(
        (button.callback_data or "").startswith("ann:open:")
        for row in context.last_markup.inline_keyboard
        for button in row
    )


async def test_delete_requires_confirmation(db):
    context = await _register(9009)
    await _start_waiting(context, 9009)
    await on_post_text(
        make_text_update("برای حذف", user_id=9009, forward_origin=_origin()), context
    )
    user_id = context.user_data["user_id"]
    async with get_session() as session:
        announcement_id = (await AnnouncementRepository(session).list_by_user(user_id))[0].id

    state = await on_delete_clicked(
        make_callback_update(f"ann:delete:{announcement_id}", user_id=9009), context
    )
    assert state == AnnouncementState.DETAIL
    assert "حذف شود" in context.sent_texts[-1]

    # cancel first: the item must survive
    await on_delete_cancelled(
        make_callback_update("ann:delete:no", user_id=9009), context
    )
    async with get_session() as session:
        assert await AnnouncementRepository(session).get(announcement_id, user_id) is not None

    await on_delete_clicked(
        make_callback_update(f"ann:delete:{announcement_id}", user_id=9009), context
    )
    state = await on_delete_confirmed(
        make_callback_update(f"ann:delete:{announcement_id}:yes", user_id=9009), context
    )
    assert state == AnnouncementState.MENU
    async with get_session() as session:
        assert await AnnouncementRepository(session).get(announcement_id, user_id) is None


async def test_one_student_cannot_open_another_students_announcement(db):
    context_a = await _register(9010)
    await _start_waiting(context_a, 9010)
    await on_post_text(
        make_text_update("اطلاعیه خصوصی", user_id=9010, forward_origin=_origin()),
        context_a,
    )
    user_a = context_a.user_data["user_id"]
    async with get_session() as session:
        announcement_id = (
            await AnnouncementRepository(session).list_by_user(user_a)
        )[0].id

    context_b = await _register(9011)
    state = await on_open(
        make_callback_update(f"ann:open:{announcement_id}", user_id=9011), context_b
    )

    assert state == AnnouncementState.MENU
    assert any("پیدا نشد" in text for text in context_b.sent_texts)
    assert "اطلاعیه خصوصی" not in "\n".join(context_b.sent_texts)


# --- pure helpers -------------------------------------------------------
def test_title_falls_back_to_first_line():
    assert _derive_title(None, "سرخط اول\nدوم") == "سرخط اول"
    assert _derive_title(None, "   \n  سرخط دوم  ") == "سرخط دوم"
    assert _derive_title(None, "بدون متن") == "بدون متن"
    assert _derive_title("کانال", "متن") == "کانال"
    assert _derive_title(None, "") == "اطلاعیه"


async def test_repository_caps_the_text_length(db):
    context = await _register(9012)
    user_id = context.user_data["user_id"]

    async with get_session() as session:
        announcement = await AnnouncementRepository(session).create(
            user_id=user_id, title="بلند", text="م" * (MAX_TEXT_LENGTH + 500)
        )
        await session.flush()
        assert len(announcement.text) == MAX_TEXT_LENGTH


# --- database rules -----------------------------------------------------
async def test_database_rejects_an_unknown_source(session):
    user = await UserRepository(session).upsert_from_telegram(
        telegram_id=9013, username="u", first_name="U", last_name=None
    )
    await session.flush()
    session.add(
        Announcement(user_id=user.id, source="pigeon", title="بدون منبع", text=None)
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_database_rejects_an_unknown_file_type(session):
    user = await UserRepository(session).upsert_from_telegram(
        telegram_id=9014, username="u", first_name="U", last_name=None
    )
    await session.flush()
    session.add(
        Announcement(
            user_id=user.id, title="عجیب", file_type="voice", file_id="whatever"
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_deleting_a_user_removes_his_announcements(session):
    user = await UserRepository(session).upsert_from_telegram(
        telegram_id=9015, username="u", first_name="U", last_name=None
    )
    await session.flush()
    await AnnouncementRepository(session).create(user_id=user.id, title="I")
    await session.commit()

    await session.delete(user)
    await session.commit()

    assert await AnnouncementRepository(session).count(user.id) == 0


def test_conversation_covers_the_three_states():
    handler = build_conversation()
    assert set(handler.states) == {
        AnnouncementState.MENU,
        AnnouncementState.DETAIL,
        AnnouncementState.WAITING,
    }

"""📡 کانال‌های من tests: URL normalization, Telegram preview parsing,
the bot conversation flow and the per-user sync."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import app.services.channel_sync as channel_sync
from app.bot.handlers.announcements import (
    announcements_menu,
    on_add_channel_clicked,
    on_channel_delete,
    on_channel_text,
    on_channels_clicked,
)
from app.bot.keyboards.main_menu import ANNOUNCEMENTS
from app.bot.middlewares import capture_user
from app.bot.states.announcement_states import AnnouncementState
from app.database.database import get_session
from app.database.models.announcement import ANNOUNCEMENT_TELEGRAM
from app.database.models.user_channel import CHANNEL_TELEGRAM
from app.database.repositories import (
    AnnouncementRepository,
    UserChannelRepository,
    UserRepository,
)
from app.services.channel_sync import (
    new_posts_notice,
    normalize_channel_url,
    sync_user_channels,
)
from app.services.eitaa_sync import EitaaPost, parse_posts
from tests.helpers import FakeContext, make_callback_update, make_text_update


# --- normalize_channel_url ----------------------------------------------
def test_normalize_accepts_supported_channel_links():
    cases = {
        "https://eitaa.com/MyChannel": ("eitaa", "https://eitaa.com/MyChannel", "MyChannel"),
        "https://eitaa.com/chan/456": ("eitaa", "https://eitaa.com/chan", "chan"),
        "http://www.eitaa.ir/x": ("eitaa", "https://eitaa.com/x", "x"),
        "https://t.me/my_chan": ("telegram", "https://t.me/my_chan", "my_chan"),
        "t.me/my_chan": ("telegram", "https://t.me/my_chan", "my_chan"),
        "https://t.me/s/my_chan": ("telegram", "https://t.me/my_chan", "my_chan"),
        "https://t.me/my_chan/123": ("telegram", "https://t.me/my_chan", "my_chan"),
        "HTTPS://T.ME/My_Chan": ("telegram", "https://t.me/my_chan", "my_chan"),
    }
    for raw, expected in cases.items():
        assert normalize_channel_url(raw) == expected, raw


def test_normalize_rejects_unsupported_links():
    invalid = [
        "",
        "   ",
        "not a url",
        "@channel",
        "https://example.com/x",
        "https://t.me/joinchat/AbCdEf",
        "https://t.me/+AbCdEf",
        "https://t.me/ab",  # telegram usernames are at least 5 chars
        "https://eitaa.com/",
    ]
    for raw in invalid:
        assert normalize_channel_url(raw) is None, raw


# --- telegram public preview --------------------------------------------
TG_PAGE = """
<html><body>
<div class="tgme_widget_message_wrap js-widget_message_wrap" id="10">
  <div class="tgme_widget_message js-widget_message" data-post="my_chan/10">
    <div class="tgme_widget_message_text js-message_text" dir="rtl"><strong>اطلاعیه مهم</strong><br>فردا کلاس دارد</div>
    <time datetime="2026-10-01T08:00:00+00:00" class="time">08:00</time>
  </div>
</div>
<div class="tgme_widget_message_wrap js-widget_message_wrap" id="11">
  <div class="tgme_widget_message js-widget_message" data-post="my_chan/11">
    <div class="tgme_widget_message_bubble"><time datetime="2026-10-01T09:00:00+00:00" class="time">09:00</time></div>
  </div>
</div>
</body></html>
"""


def test_parse_telegram_preview_reads_text_posts():
    posts = parse_posts(TG_PAGE, channel_url="https://t.me/my_chan", widget="tgme")

    assert [post.url for post in posts] == ["https://t.me/my_chan/10"]
    assert posts[0].text == "اطلاعیه مهم\nفردا کلاس دارد"
    assert posts[0].published_at == datetime(2026, 10, 1, 8, 0, 0)


# --- bot conversation ----------------------------------------------------
async def _register(telegram_id: int) -> FakeContext:
    context = FakeContext()
    await capture_user(make_text_update("/start", user_id=telegram_id), context)
    return context


async def test_channel_flow_from_menu_to_delete(db):
    context = await _register(7711)

    await announcements_menu(make_text_update(ANNOUNCEMENTS, user_id=7711), context)
    callbacks = [
        button.callback_data
        for row in context.last_markup.inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert "ann:ch" in callbacks  # the menu offers the channels screen

    state = await on_channels_clicked(make_callback_update("ann:ch", user_id=7711), context)
    assert state == AnnouncementState.CHANNELS
    assert "هنوز کانالی" in context.sent_texts[-1]

    state = await on_add_channel_clicked(
        make_callback_update("ann:chadd", user_id=7711), context
    )
    assert state == AnnouncementState.CHANNEL_ADD
    assert "لینک کانال را بفرست" in context.sent_texts[-1]

    state = await on_channel_text(
        make_text_update("https://t.me/my_chan", user_id=7711), context
    )
    assert state == AnnouncementState.CHANNELS
    assert "اضافه شد" in context.sent_texts[-2]  # saved notice, then the list

    user_id = context.user_data["user_id"]
    async with get_session() as session:
        channels = await UserChannelRepository(session).list_by_user(user_id)
    assert [(c.platform, c.handle, c.url) for c in channels] == [
        ("telegram", "my_chan", "https://t.me/my_chan")
    ]

    # the same channel again (also in the short t.me/ form) is a no-op
    await on_add_channel_clicked(make_callback_update("ann:chadd", user_id=7711), context)
    state = await on_channel_text(make_text_update("t.me/my_chan", user_id=7711), context)
    assert state == AnnouncementState.CHANNELS
    assert "قبلاً" in context.sent_texts[-2]  # exists notice, then the list

    # an unsupported link keeps the prompt
    await on_add_channel_clicked(make_callback_update("ann:chadd", user_id=7711), context)
    state = await on_channel_text(
        make_text_update("https://example.com/x", user_id=7711), context
    )
    assert state == AnnouncementState.CHANNEL_ADD
    assert "معتبر" in context.sent_texts[-1]

    # delete
    state = await on_channel_delete(
        make_callback_update(f"ann:chdel:{channels[0].id}", user_id=7711), context
    )
    assert state == AnnouncementState.CHANNELS
    async with get_session() as session:
        assert await UserChannelRepository(session).list_by_user(user_id) == []


async def test_cancel_returns_to_the_channel_list(db):
    context = await _register(7712)
    await announcements_menu(make_text_update(ANNOUNCEMENTS, user_id=7712), context)
    await on_channels_clicked(make_callback_update("ann:ch", user_id=7712), context)
    await on_add_channel_clicked(make_callback_update("ann:chadd", user_id=7712), context)

    state = await on_channel_text(
        make_text_update("❌ لغو", user_id=7712), context
    )

    assert state == AnnouncementState.CHANNELS
    assert "کانال‌های من" in context.sent_texts[-1]


# --- sync ----------------------------------------------------------------
async def _user(telegram_id: int) -> int:
    async with get_session() as session:
        user, _ = await UserRepository(session).get_or_create_from_telegram(
            telegram_id=telegram_id,
            username=f"u{telegram_id}",
            first_name="Student",
            last_name=None,
        )
        return user.id


async def test_sync_imports_posts_only_for_subscribers(db, monkeypatch):
    subscriber = await _user(7701)
    bystander = await _user(7702)
    async with get_session() as session:
        await UserChannelRepository(session).add(
            user_id=subscriber,
            platform=CHANNEL_TELEGRAM,
            url="https://t.me/my_chan",
            handle="my_chan",
        )

    post = EitaaPost(
        url="https://t.me/my_chan/10", text="اطلاعیه جدید", published_at=None
    )
    fetch = AsyncMock(return_value=[post])
    monkeypatch.setattr(channel_sync, "fetch_posts", fetch)

    counts = await sync_user_channels()

    assert counts == {7701: 1}  # keyed by telegram_id, only for the subscriber
    fetch.assert_awaited_once_with(CHANNEL_TELEGRAM, "https://t.me/my_chan")
    async with get_session() as session:
        subscriber_items = await AnnouncementRepository(session).list_by_user(subscriber)
        bystander_items = await AnnouncementRepository(session).list_by_user(bystander)
    assert len(subscriber_items) == 1
    assert subscriber_items[0].source == ANNOUNCEMENT_TELEGRAM
    assert bystander_items == []

    # second run: everything deduped, so nobody is notified
    assert await sync_user_channels() == {}


async def test_sync_survives_one_broken_channel(db, monkeypatch):
    only_user = await _user(7703)
    async with get_session() as session:
        await UserChannelRepository(session).add(
            user_id=only_user,
            platform=CHANNEL_TELEGRAM,
            url="https://t.me/broken_chan",
            handle="broken_chan",
        )
    monkeypatch.setattr(channel_sync, "fetch_posts", AsyncMock(side_effect=OSError))

    assert await sync_user_channels() == {}


def test_notice_uses_persian_digits():
    text = new_posts_notice(3)
    assert "۳" in text
    assert "اطلاعیه جدید" in text


async def test_fetch_falls_back_between_proxy_and_direct(monkeypatch):
    calls: list[bool] = []

    async def flaky(url: str, *, trust_env: bool = False) -> str:
        calls.append(trust_env)
        if len(calls) == 1:
            raise OSError("proxy dropped the connection")
        return TG_PAGE

    monkeypatch.setattr(channel_sync, "fetch_channel_html", flaky)

    posts = await channel_sync.fetch_posts(CHANNEL_TELEGRAM, "https://t.me/my_chan")

    assert posts  # second attempt (direct) succeeded
    assert calls == [True, False]

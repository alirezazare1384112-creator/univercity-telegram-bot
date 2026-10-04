"""Automatic Eitaa import tests: parse the public page, copy posts, dedup.

Nothing here touches the network - ``import_posts`` is fed a local page.
"""

from __future__ import annotations

from datetime import datetime

from app.database.database import get_session
from app.database.models.announcement import ANNOUNCEMENT_EITAA
from app.database.repositories import AnnouncementRepository, UserRepository
from app.services.eitaa_sync import import_posts, parse_posts

CHANNEL = "https://eitaa.com/atriardakani"

PAGE = """
<html><body>
<div class="etme_widget_message_wrap js-widget_message_wrap" id="1524">
  <div class="etme_widget_message js-widget_message" data-post="atriardakani/1524">
    <div class="etme_widget_message_text js-message_text" dir="rtl"><strong>مهلت حذف و اضافه</strong> تا ساعت ۱۰:۰۰<br>روز چهارشنبه</div>
    <time datetime="2026-09-28T05:49:02+00:00" class="time">05:49</time>
  </div>
</div>
<div class="etme_widget_message_wrap js-widget_message_wrap" id="1525">
  <div class="etme_widget_message js-widget_message" data-post="atriardakani/1525">
    <div class="etme_widget_message_text js-message_text">برنامه سرویس خوابگاه اعلام شد<br></div>
    <time datetime="2026-09-28T06:43:36+00:00" class="time">06:43</time>
  </div>
</div>
<div class="etme_widget_message_wrap js-widget_message_wrap" id="1526">
  <div class="etme_widget_message js-widget_message" data-post="atriardakani/1526">
    <div class="etme_widget_message_bubble"><time datetime="2026-09-28T07:00:00+00:00" class="time">07:00</time></div>
  </div>
</div>
</body></html>
"""


async def _user(telegram_id: int) -> int:
    async with get_session() as session:
        user, _ = await UserRepository(session).get_or_create_from_telegram(
            telegram_id=telegram_id, username="stu", first_name="Student", last_name=None
        )
        return user.id


def test_parse_posts_reads_links_text_and_times():
    posts = parse_posts(PAGE, channel_url=CHANNEL)

    assert [post.url for post in posts] == [
        "https://eitaa.com/atriardakani/1524",
        "https://eitaa.com/atriardakani/1525",
    ]
    assert posts[0].text == "مهلت حذف و اضافه تا ساعت ۱۰:۰۰\nروز چهارشنبه"
    assert posts[0].published_at == datetime(2026, 9, 28, 5, 49, 2)


def test_parse_skips_media_only_posts_and_empty_pages():
    assert parse_posts("<html>no posts</html>", channel_url=CHANNEL) == []
    media_only = """
    <div class="etme_widget_message_wrap" id="1">
      <div data-post="atriardakani/9"><time datetime="2026-09-28T07:00:00+00:00"></time></div>
    </div>
    """
    assert parse_posts(media_only, channel_url=CHANNEL) == []


async def test_import_copies_new_posts_to_every_active_user(db):
    await _user(9601)
    await _user(9602)

    created = await import_posts(PAGE, channel_url=CHANNEL)

    assert created == 4  # two posts, two students
    async with get_session() as session:
        repo = AnnouncementRepository(session)
        for user_id in await UserRepository(session).list_active_ids():
            items = await repo.list_by_user(user_id)
            assert [item.source_url for item in items] == [
                "https://eitaa.com/atriardakani/1525",
                "https://eitaa.com/atriardakani/1524",
            ]
            assert all(item.source == ANNOUNCEMENT_EITAA for item in items)
            assert items[0].created_at == datetime(2026, 9, 28, 6, 43, 36)


async def test_import_never_duplicates_and_backfills_late_joiners(db):
    await _user(9611)
    assert await import_posts(PAGE, channel_url=CHANNEL) == 2
    assert await import_posts(PAGE, channel_url=CHANNEL) == 0

    await _user(9612)  # joins after the first sync
    assert await import_posts(PAGE, channel_url=CHANNEL) == 2

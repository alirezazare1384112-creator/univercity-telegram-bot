"""Date/time helper tests (Jalali parsing, formatting, relative labels)."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.utils.datetime_utils import (
    format_jalali,
    parse_reminder_datetime,
    relative_label,
)

TZ = "Asia/Tehran"
# 15:30 in Tehran (UTC+3:30)
NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)


def test_relative_day_and_time_is_converted_to_utc():
    ok, value, error = parse_reminder_datetime("فردا ساعت 18:30", TZ, now_utc=NOW)

    assert ok, error
    # 2026-10-05 18:30 Tehran == 15:00 UTC
    assert value == datetime(2026, 10, 5, 15, 0)
    assert value.tzinfo is None  # stored as naive UTC


def test_persian_digits_are_accepted():
    ok, value, _ = parse_reminder_datetime("فردا ساعت ۱۸:۳۰", TZ, now_utc=NOW)

    assert ok
    assert value == datetime(2026, 10, 5, 15, 0)


def test_tehran_offset_is_not_ignored():
    ok, value, _ = parse_reminder_datetime("فردا ساعت 12", TZ, now_utc=NOW)

    assert ok
    # 12:00 Tehran == 08:30 UTC
    assert value == datetime(2026, 10, 5, 8, 30)


def test_bare_time_rolls_to_tomorrow_when_it_already_passed():
    # 15:30 in Tehran -> 14:00 already happened today
    ok, value, _ = parse_reminder_datetime("14:00", TZ, now_utc=NOW)

    assert ok
    assert value == datetime(2026, 10, 5, 10, 30)


def test_past_day_is_rejected():
    ok, value, error = parse_reminder_datetime("ديروز ساعت 10:00", TZ, now_utc=NOW)

    assert not ok
    assert value is None
    assert "آینده" in error


def test_jalali_date_is_converted():
    # Nowruz 1405 == 2026-03-21, months before the "now" of this test
    now = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    ok, value, error = parse_reminder_datetime("1405/01/01 ساعت 12", TZ, now_utc=now)

    assert ok, error
    assert value == datetime(2026, 3, 21, 8, 30)  # 12:00 Tehran


def test_garbage_input_is_rejected_with_a_hint():
    ok, value, error = parse_reminder_datetime("هر وقت", TZ, now_utc=NOW)

    assert not ok
    assert value is None
    assert "18:30" in error  # the hint shows a working example


def test_format_jalali_shows_tehran_wall_clock():
    text = format_jalali(datetime(2026, 3, 21, 8, 30), TZ)

    assert text == "1405/01/01 ساعت 12:00"


def test_relative_label_follows_the_tehran_calendar():
    tz = ZoneInfo(TZ)
    tomorrow_local = datetime.now(UTC).astimezone(tz).date() + timedelta(days=1)
    target = (
        datetime.combine(tomorrow_local, time(12, 0), tzinfo=tz)
        .astimezone(UTC)
        .replace(tzinfo=None)
    )

    assert relative_label(target, TZ) == "فردا"

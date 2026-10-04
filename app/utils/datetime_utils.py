"""Date and time helpers.

Rules used everywhere in this project:

* everything stored in the database is **naive UTC**
* everything shown to the user is **Tehran local time, Jalali calendar**
* users can type Persian digits and Persian words (فردا, ساعت, ...)
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import jdatetime

from app.utils.validation import clean_text, to_persian_digits

TIME_WORDS = ("ساعت", "در")
_RELATIVE_DATES = {
    "امروز": 0,
    "فردا": 1,
    "پس فردا": 2,
    "پس‌فردا": 2,
    "ديروز": -1,
    "دیروز": -1,
}
_DATE_SEPARATORS = re.compile(r"[/\-\.]")
_TIME_PATTERN = re.compile(r"^(\d{1,2})[:.h٫](\d{1,2})$|^(\d{1,2})$")


def utcnow_naive() -> datetime:
    """Current UTC time without tzinfo (the format stored in the DB)."""
    return datetime.now(UTC).replace(tzinfo=None)


def get_tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 - fall back to UTC on a bad TIMEZONE
        return ZoneInfo("UTC")


def utc_to_local(dt_utc: datetime, tz_name: str) -> datetime:
    """Naive UTC -> aware local time."""
    aware = dt_utc.replace(tzinfo=UTC)
    return aware.astimezone(get_tz(tz_name))


def local_to_utc_naive(dt_local: datetime, tz_name: str) -> datetime:
    """Aware local time -> naive UTC."""
    return dt_local.astimezone(UTC).replace(tzinfo=None)


def parse_time(raw: str) -> tuple[bool, time | None, str]:
    """Accept ``18``, ``18:30``, ``18.30`` (Persian digits allowed)."""
    text = to_persian_digits(clean_text(raw)).lower()
    match = _TIME_PATTERN.match(text)
    if not match:
        return False, None, "ساعت را به صورت 18:30 یا 18 وارد کن."

    hour = int(match.group(1) or match.group(3))
    minute = int(match.group(2) or 0)
    if not (0 <= hour <= 23) or not (0 <= minute <= 59):
        return False, None, "ساعت نامعتبر است. مثال: 18:30"
    return True, time(hour=hour, minute=minute), ""


def _parse_date_token(token: str, today_local: date) -> tuple[bool, date | None, str]:
    text = to_persian_digits(clean_text(token)).lower()

    if text in _RELATIVE_DATES:
        return True, today_local + timedelta(days=_RELATIVE_DATES[text]), ""

    parts = [part for part in _DATE_SEPARATORS.split(text) if part]
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return False, None, (
            "تاریخ را یکی از این‌طور وارد کن:\n"
            "• فردا\n• امروز\n• 1404/07/05 (شمسی)\n• 2026/10/05 (میلادی)"
        )

    year, month, day = (int(part) for part in parts)
    try:
        if 1200 <= year <= 1600:  # Jalali
            return True, jdatetime.date(year, month, day).togregorian(), ""
        if 1900 <= year <= 2200:  # Gregorian
            return True, date(year, month, day), ""
    except ValueError:
        return False, None, "چنین تاریخی وجود ندارد. مثال: 1404/07/05"
    return False, None, "سال تاریخ نامعتبر است. مثال: 1404/07/05"


def looks_like_time(token: str) -> bool:
    return bool(_TIME_PATTERN.match(to_persian_digits(clean_text(token)).lower()))


def parse_reminder_datetime(
    raw: str,
    tz_name: str,
    *,
    now_utc: datetime | None = None,
) -> tuple[bool, datetime | None, str]:
    """Parse one message like ``فردا ساعت 18:30`` into naive UTC.

    A bare time (``18:30``) means today, or tomorrow when that moment has
    already passed.
    """
    text = clean_text(raw)
    # "پس فردا" and "ساعت" would otherwise split into two tokens
    text = text.replace("پس فردا", "پس‌فردا")
    for word in TIME_WORDS:
        text = text.replace(word, " ")
    text = clean_text(text)

    if not text:
        return False, None, "زمان یادآوری را وارد کن. مثال: فردا ساعت 18:30"

    tokens = text.split()
    if len(tokens) == 1:
        if looks_like_time(tokens[0]):
            date_token, time_token = None, tokens[0]
        else:
            return False, None, "ساعت را هم اضافه کن. مثال: فردا ساعت 18:30"
    elif len(tokens) == 2:
        date_token, time_token = tokens
    else:
        return False, None, "فرمت درست: تاریخ + ساعت. مثال: فردا ساعت 18:30"

    tz = get_tz(tz_name)
    now = now_utc or utcnow_naive()
    today_local = now.replace(tzinfo=UTC).astimezone(tz).date()

    ok, parsed_time, error = parse_time(time_token)
    if not ok:
        return False, None, error

    if date_token is None:
        candidate_date = today_local
    else:
        ok, candidate_date, error = _parse_date_token(date_token, today_local)
        if not ok:
            return False, None, error

    local_dt = datetime.combine(candidate_date, parsed_time, tzinfo=tz)

    if date_token is None and local_dt <= now.replace(tzinfo=UTC).astimezone(tz):
        local_dt = local_dt + timedelta(days=1)  # 18:30 already passed -> tomorrow

    if local_dt <= now.replace(tzinfo=UTC).astimezone(tz):
        return False, None, "زمان یادآوری باید در آینده باشد."

    return True, local_to_utc_naive(local_dt, tz_name), ""


def relative_label(dt_utc: datetime, tz_name: str) -> str:
    """امروز / فردا / پس‌فردا / otherwise empty."""
    tz = get_tz(tz_name)
    now_local = datetime.now(UTC).astimezone(tz)
    target_local = dt_utc.replace(tzinfo=UTC).astimezone(tz)
    delta = (target_local.date() - now_local.date()).days
    for label, offset in (("امروز", 0), ("فردا", 1), ("پس‌فردا", 2)):
        if delta == offset:
            return label
    return ""


# --- calendar helpers (date only, no timezone conversion needed) --------
PERSIAN_WEEKDAYS: tuple[str, ...] = (
    "شنبه",
    "یکشنبه",
    "دوشنبه",
    "سه‌شنبه",
    "چهارشنبه",
    "پنجشنبه",
    "جمعه",
)


def parse_user_date(raw: str, tz_name: str) -> tuple[bool, date | None, str]:
    """Parse a date typed by the student: فردا / 1404/07/12 / 2026/10/05.

    The result is a plain Gregorian date meaning "that day in the
    student's local calendar" - calendar events never shift with UTC.
    """
    text = clean_text(raw)
    if not text:
        return False, None, "تاریخ را وارد کن. مثال: فردا یا 1404/07/12"
    tz = get_tz(tz_name)
    today_local = datetime.now(UTC).astimezone(tz).date()
    return _parse_date_token(text, today_local)


def format_jalali_date(day: date) -> str:
    """``1404/07/12 (شنبه)`` for a plain date."""
    jalali = jdatetime.date.fromgregorian(date=day)
    weekday = PERSIAN_WEEKDAYS[jalali.weekday()]
    return f"{jalali.year:04d}/{jalali.month:02d}/{jalali.day:02d} ({weekday})"


def relative_date_label(day: date, tz_name: str) -> str:
    """امروز / فردا / پس‌فردا / دیروز relative to today (local)."""
    tz = get_tz(tz_name)
    today = datetime.now(UTC).astimezone(tz).date()
    delta = (day - today).days
    for label, offset in (("امروز", 0), ("فردا", 1), ("پس‌فردا", 2), ("دیروز", -1)):
        if delta == offset:
            return label
    return ""


def format_jalali(dt_utc: datetime, tz_name: str) -> str:
    """``1404/07/05 ساعت 18:30`` (Jalali, local time)."""
    local = utc_to_local(dt_utc, tz_name)
    jalali = jdatetime.datetime.fromgregorian(datetime=local.replace(tzinfo=None))
    return f"{jalali.year:04d}/{jalali.month:02d}/{jalali.day:02d} ساعت {local:%H:%M}"


def format_jalali_short(dt_utc: datetime, tz_name: str) -> str:
    local = utc_to_local(dt_utc, tz_name)
    jalali = jdatetime.datetime.fromgregorian(datetime=local.replace(tzinfo=None))
    return f"{jalali.year:04d}/{jalali.month:02d}/{jalali.day:02d}"

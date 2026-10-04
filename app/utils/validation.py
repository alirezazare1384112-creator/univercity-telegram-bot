"""Input validation helpers shared by all handlers.

Every function returns ``(is_valid, cleaned_value, error_message)`` so the
handler can show the exact hint the user needs.
"""

from __future__ import annotations

import re

_ARABIC_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")

PROFILE_FIELD_LABELS: dict[str, str] = {
    "student_number": "شماره دانشجویی",
    "field_of_study": "رشته تحصیلی",
    "university": "دانشگاه",
    "semester": "ترم",
}

PROFILE_FIELD_MAX_LENGTH: dict[str, int] = {
    "student_number": 32,
    "field_of_study": 128,
    "university": 128,
    "semester": 64,
}


def to_persian_digits(text: str) -> str:
    """Normalize ۰-۹ and Arabic ٠-٩ to ASCII digits."""
    text = text.translate(_ARABIC_DIGITS)
    return re.sub(r"[٠-٩]", lambda m: str("٠١٢٣٤٥٦٧٨٩".index(m.group(0))), text)


def clean_text(value: str) -> str:
    return " ".join((value or "").strip().split())


def validate_positive_int(raw: str, *, field_label: str, minimum: int = 1, maximum: int = 100) -> tuple[bool, int | None, str]:
    """Accept only digits (ASCII or Persian) inside ``[minimum, maximum]``."""
    text = to_persian_digits(clean_text(raw))
    if not text:
        return False, None, f"لطفاً {field_label} را وارد کنید."
    if not text.isdigit():
        return False, None, (
            f"لطفاً {field_label} را به صورت عدد وارد کنید. مثال: {minimum}"
        )
    number = int(text)
    if number < minimum or number > maximum:
        return False, None, (
            f"{field_label} باید بین {minimum} تا {maximum} باشد. مثال: {minimum}"
        )
    return True, number, ""


def validate_profile_field(field: str, raw: str) -> tuple[bool, str, str]:
    """Validate one profile field before it is stored."""
    if field not in PROFILE_FIELD_LABELS:
        return False, "", "فیلد نامعتبر است."

    label = PROFILE_FIELD_LABELS[field]
    value = clean_text(raw)

    if not value:
        return False, "", f"مقدار {label} خالی است. لطفاً دوباره تلاش کنید."

    if len(value) > PROFILE_FIELD_MAX_LENGTH[field]:
        return False, "", f"{label} نباید بیشتر از {PROFILE_FIELD_MAX_LENGTH[field]} کاراکتر باشد."

    if field == "student_number":
        value = to_persian_digits(value)
        if not value.replace("-", "").isdigit():
            return False, "", "شماره دانشجویی فقط باید شامل عدد باشد. مثال: 402123456"

    if field == "semester":
        # keep "1404-1" style values, but normalise ۰-۹ to 0-9
        value = to_persian_digits(value)

    return True, value, ""


def validate_short_text(
    raw: str,
    label: str,
    *,
    max_length: int = 128,
    required: bool = True,
) -> tuple[bool, str, str]:
    """Generic text validation used by courses, notes, reminders, ..."""
    value = clean_text(raw)

    if not value:
        if required:
            return False, "", f"لطفاً {label} را وارد کنید."
        return True, "", ""

    if len(value) > max_length:
        return False, "", f"{label} نباید بیشتر از {max_length} کاراکتر باشد."

    return True, value, ""


def validate_number(
    raw: str,
    label: str,
    *,
    minimum: float = 0.0,
    maximum: float | None = None,
) -> tuple[bool, float | None, str]:
    """Accept one number (ASCII/Persian digits, ``.`` or ``٫`` separator)."""
    text = to_persian_digits(clean_text(raw)).replace("/", ".").replace("٫", ".")
    if not text:
        return False, None, f"لطفاً {label} را وارد کنید. مثال: 16"

    try:
        value = float(text)
    except ValueError:
        return False, None, f"{label} باید عدد باشد. مثال: 15.5"

    if value < minimum:
        return False, None, f"{label} نمی‌تواند کمتر از {minimum:g} باشد."
    if maximum is not None and value > maximum:
        return False, None, f"{label} نمی‌تواند بیشتر از {maximum:g} باشد."

    return True, value, ""


def validate_url(raw: str, label: str = "آدرس") -> tuple[bool, str, str]:
    """Accept a http(s) URL; ``portal.uni.ir`` becomes ``https://portal.uni.ir``.

    Only http/https are allowed so nothing like ``javascript:`` can ever be
    stored and handed to Telegram's inline url buttons.
    """
    value = clean_text(raw)

    if not value:
        return False, "", (
            f"لطفاً {label} را وارد کنید. "
            "مثال: https://portal.university.ir"
        )

    if len(value) > 255:
        return False, "", f"{label} نباید بیشتر از 255 کاراکتر باشد."

    if " " in value:
        return False, "", f"{label} نباید فاصله داشته باشد. مثال: https://portal.uni.ir"

    if "://" not in value:
        if value.startswith("//"):
            value = "https:" + value
        elif "." in value:
            value = "https://" + value
        else:
            return False, "", (
                f"{label} باید با http:// یا https:// شروع شود. "
                "مثال: https://portal.university.ir"
            )

    scheme = value.split("://", 1)[0].lower()
    if scheme not in ("http", "https"):
        return False, "", "فقط آدرس‌های http و https پشتیبانی می‌شوند."

    return True, value, ""


def validate_score(raw_score: str, raw_max: str) -> tuple[bool, float | None, float | None, str]:
    """Validate a grade item: ``0 <= score <= max_score`` and ``max_score > 0``."""
    score_text = to_persian_digits(clean_text(raw_score)).replace("/", ".").replace("٫", ".")
    max_text = to_persian_digits(clean_text(raw_max)).replace("/", ".").replace("٫", ".")

    if not score_text or not max_text:
        return False, None, None, "نمره و نمره کامل را وارد کنید. مثال: 16 و 20"

    try:
        score = float(score_text)
        max_score = float(max_text)
    except ValueError:
        return False, None, None, "نمره باید عدد باشد. مثال: 15.5"

    if max_score <= 0:
        return False, None, None, "نمره کامل باید بزرگ‌تر از صفر باشد."
    if score < 0:
        return False, None, None, "نمره نمی‌تواند منفی باشد."
    if score > max_score:
        return False, None, None, "نمره نمی‌تواند بزرگ‌تر از نمره کامل باشد."

    return True, score, max_score, ""

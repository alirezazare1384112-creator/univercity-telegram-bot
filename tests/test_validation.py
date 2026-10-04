"""Validation helper tests (shared by profile, courses and grades)."""

from __future__ import annotations

from app.utils.validation import (
    to_persian_digits,
    validate_positive_int,
    validate_profile_field,
    validate_score,
)


def test_persian_digits_are_normalized():
    assert to_persian_digits("۴۰۲۱") == "4021"
    assert to_persian_digits("4021") == "4021"


def test_positive_int_accepts_digits():
    ok, value, error = validate_positive_int("3", field_label="تعداد واحد")
    assert ok and value == 3 and error == ""


def test_positive_int_accepts_persian_digits():
    ok, value, _ = validate_positive_int("۳", field_label="تعداد واحد")
    assert ok and value == 3


def test_positive_int_rejects_words_with_a_helpful_message():
    ok, value, error = validate_positive_int("سه", field_label="تعداد واحد")
    assert not ok and value is None
    assert "عدد" in error and "مثال" in error


def test_positive_int_rejects_zero_and_out_of_range():
    assert validate_positive_int("0", field_label="تعداد واحد")[0] is False
    assert validate_positive_int("999", field_label="تعداد واحد")[0] is False


def test_profile_student_number_must_be_numeric():
    assert validate_profile_field("student_number", "402123456")[0] is True
    assert validate_profile_field("student_number", "abc")[0] is False


def test_profile_rejects_empty_and_too_long():
    assert validate_profile_field("university", "   ")[0] is False
    assert validate_profile_field("university", "x" * 200)[0] is False


def test_score_rules():
    ok, score, max_score, _ = validate_score("16", "20")
    assert ok and score == 16.0 and max_score == 20.0

    assert validate_score("15.5", "20")[0] is True
    assert validate_score("-1", "20")[0] is False  # negative
    assert validate_score("21", "20")[0] is False  # greater than max
    assert validate_score("10", "0")[0] is False  # max must be > 0
    assert validate_score("abc", "20")[0] is False  # not a number
    assert validate_score("", "20")[0] is False  # missing


def test_score_accepts_persian_decimal_separator():
    ok, score, _, _ = validate_score("۱۵٫۵", "۲۰")
    assert ok and score == 15.5

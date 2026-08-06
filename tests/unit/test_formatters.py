"""Unit tests for the pure display-formatting helpers in achievements/__init__.py
(activity calendar math, date/duration formatting, description wrapping)."""

from datetime import date

import achievements as addon


def test_format_duration_edge_cases():
    assert addon.format_duration(0) == "—"
    assert addon.format_duration(-5) == "—"
    assert addon.format_duration(30) == "< 1 min"
    assert addon.format_duration(90) == "1 min"
    assert addon.format_duration(3600) == "1 h"
    assert addon.format_duration(3660) == "1 h 1 min"
    assert addon.format_duration("not a number") == "—"


def test_calendar_level_thresholds():
    assert addon.calendar_level(0) == 0
    assert addon.calendar_level(1) == 1
    assert addon.calendar_level(3599) == 1
    assert addon.calendar_level(3600) == 2
    assert addon.calendar_level(10800) == 3
    assert addon.calendar_level(21600) == 4
    assert addon.calendar_level(999_999) == 4


def test_calendar_days_shape_and_alignment():
    today = date(2026, 8, 5)  # Wednesday
    weeks = addon.calendar_days(weeks=3, today=today)
    assert len(weeks) == 3
    assert all(len(w) == 7 for w in weeks)
    # The grid is rendered with weeks as UI columns (see draw_activity_calendar,
    # which iterates weekday as the outer/row loop and weeks as the inner/
    # column loop) — so "today is always in the rightmost column" means today
    # sits somewhere in weeks[-1], at its own weekday's row.
    assert weeks[-1][today.weekday()] == today
    # Every week starts on a Monday.
    assert all(w[0].weekday() == 0 for w in weeks)


def test_format_unlock_date_valid_and_invalid():
    assert addon.format_unlock_date("") == ""
    assert addon.format_unlock_date("not-a-timestamp") == ""
    assert addon.format_unlock_date("2026-08-05T14:30:00+00:00") == "5 Aug 2026, 14:30"


def test_split_description_returns_single_line_when_it_fits():
    assert addon._split_description("") == []
    assert addon._split_description("Short text") == ["Short text"]


def test_split_description_wraps_to_two_lines_and_truncates_overflow():
    long_text = "word " * 30
    lines = addon._split_description(long_text, max_line_chars=20)
    assert len(lines) == 2
    assert len(lines[0]) <= 20
    assert lines[1].endswith("...")


def test_split_description_no_ellipsis_when_second_line_is_the_end():
    # Fits in exactly two lines with nothing left over -> no truncation mark.
    text = "one two three four five six"
    lines = addon._split_description(text, max_line_chars=15)
    assert len(lines) == 2
    assert not lines[1].endswith("...")

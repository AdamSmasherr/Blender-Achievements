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


def test_format_progress_value_scales():
    assert addon.format_progress_value(0) == "0"
    assert addon.format_progress_value(940) == "940"
    assert addon.format_progress_value(12_345) == "12,345"
    assert addon.format_progress_value(999_999) == "999,999"
    assert addon.format_progress_value(1_000_000) == "1M"
    assert addon.format_progress_value(1_260_000) == "1.3M"
    assert addon.format_progress_value(12_345_678) == "12.3M"
    # Three significant digits: past a hundred million the decimal is noise.
    assert addon.format_progress_value(948_300_000) == "948M"
    # Rounding picks the unit, so this must not come out as "1000M".
    assert addon.format_progress_value(999_999_999) == "1B"
    assert addon.format_progress_value(1_000_000_000) == "1B"
    assert addon.format_progress_value(2_500_000_000) == "2.5B"


def test_format_progress_value_bad_input():
    assert addon.format_progress_value(-5) == "0"
    assert addon.format_progress_value("not a number") == "0"
    assert addon.format_progress_value(None) == "0"


def test_format_progress_pairs_current_and_target():
    assert addon.format_progress(340, 1_000) == "340 / 1,000"
    assert addon.format_progress(12_345_678, 1_000_000_000) == "12.3M / 1B"


def test_description_line_chars_follows_width_and_scale():
    # Same panel, twice the UI scale -> half the characters.
    at_1x = addon.description_line_chars(600, ui_scale=1.0)
    at_2x = addon.description_line_chars(600, ui_scale=2.0)
    assert at_1x > at_2x
    # Wider panel -> more characters.
    assert addon.description_line_chars(900) > addon.description_line_chars(400)
    # The icon column eats its share.
    assert (addon.description_line_chars(600, text_fraction=0.75)
            < addon.description_line_chars(600, text_fraction=1.0))


def test_description_line_chars_clamps_degenerate_input():
    assert addon.description_line_chars(1) == 14        # collapsed region
    assert addon.description_line_chars(0) == 14
    assert addon.description_line_chars(100_000) == 120
    assert addon.description_line_chars("nonsense") == 14
    assert addon.description_line_chars(None) == 14
    assert addon.description_line_chars(600, ui_scale=0) > 14   # scale falls back to 1


def test_description_line_chars_matches_measured_font_width():
    # 360 px sidebar at ui_scale 1.5 with a quarter given to the icon: the
    # widget font measures 8 px/char there, so ~28 characters fit.
    chars = addon.description_line_chars(360, ui_scale=1.5, text_fraction=0.75)
    assert 25 <= chars <= 31


def test_split_description_honours_max_lines():
    text = "Run a Cloth simulation where mesh vertices travel over 100 units away instantly."
    two = addon._split_description(text, max_line_chars=28, max_lines=2)
    assert len(two) == 2 and two[-1].endswith("...")

    four = addon._split_description(text, max_line_chars=28, max_lines=4)
    assert not four[-1].endswith("...")
    assert " ".join(four) == text
    assert all(len(line) <= 28 for line in four)


def test_split_description_survives_word_longer_than_the_line():
    lines = addon._split_description("supercalifragilistic and more", max_line_chars=8)
    assert lines[0] == "supercalifragilistic"


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

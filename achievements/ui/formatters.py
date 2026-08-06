"""
Pure display-formatting helpers for Achievements UI.

Activity-calendar math (thresholds, day grid) and human-readable text
formatting (durations, dates, description wrapping). None of this touches
bpy, so it's exercised directly by tests/unit without any Blender stub.
"""

# Скільки тижнів показує хітмапа. Рік (53 колонки) у ширину N-панелі не
# влазить фізично, тож 13 тижнів — не компроміс, а єдиний робочий варіант.
CALENDAR_WEEKS = 13

# Пороги в секундах для 5 рівнів інтенсивності: 0 / <1 год / <3 / <6 / 6+.
CALENDAR_THRESHOLDS = (1, 3600, 10800, 21600)

# Темний фон для «нічого не було» + тепла шкала від жовтого до палено-жовтогарячого.
# Значення — sRGB 0..1, тобто рівно те, що стоїть у полі hex кольоропікера.
CALENDAR_COLORS = (
    (0.1451, 0.1451, 0.1451),   # #252525 — активності не було
    (0.7098, 0.3569, 0.0000),   # #b55b00
    (0.9765, 0.5294, 0.0863),   # #f98716
    (1.0000, 0.6941, 0.2118),   # #ffb136
    (1.0000, 0.8784, 0.4000),   # #ffe066
)

CALENDAR_LEVEL_LABELS = (
    "No activity",
    "Under 1 hour",
    "1 to 3 hours",
    "3 to 6 hours",
    "Over 6 hours",
)

# Те саме, але для підписів під зразками кольору, де є місце на 4-5 символів.
CALENDAR_LEVEL_SHORT = ("None", "< 1h", "1-3h", "3-6h", "6h+")


def format_duration(seconds) -> str:
    """`4 h 12 min` / `12 min` / `—` для нуля."""
    try:
        total = int(seconds)
    except Exception:
        return "—"
    if total <= 0:
        return "—"
    hours, minutes = divmod(total // 60, 60)
    if hours and minutes:
        return f"{hours} h {minutes} min"
    if hours:
        return f"{hours} h"
    return f"{minutes} min" if minutes else "< 1 min"


def calendar_level(seconds) -> int:
    """Індекс рівня інтенсивності (0..4) для відпрацьованих секунд."""
    try:
        value = int(seconds)
    except Exception:
        return 0
    level = 0
    for threshold in CALENDAR_THRESHOLDS:
        if value >= threshold:
            level += 1
    return level


def calendar_days(weeks: int = CALENDAR_WEEKS, today=None) -> list:
    """Сітка дат: список тижнів, у кожному 7 днів з понеділка.

    Останній тиждень — поточний, тож сьогоднішній день завжди в правій
    колонці. Дні після сьогодні входять у сітку (тиждень же не скінчився) і
    малюються порожніми.
    """
    from datetime import date, timedelta
    if today is None:
        today = date.today()
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks - 1)
    return [[start + timedelta(days=w * 7 + d) for d in range(7)] for w in range(weeks)]


def format_day_label(day_iso: str) -> str:
    """`2026-08-03` → `3 Aug 2026`; при негодящому вводі повертає як є."""
    try:
        from datetime import date
        parsed = date.fromisoformat(day_iso)
    except Exception:
        return day_iso
    months = {
        1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
        7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
    }
    return f"{parsed.day} {months.get(parsed.month, '')} {parsed.year}"


def format_unlock_date(timestamp_str: str) -> str:
    if not timestamp_str:
        return ""
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(timestamp_str)
        months = {
            1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
            5: "May", 6: "Jun", 7: "Jul", 8: "Aug",
            9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"
        }
        m_str = months.get(dt.month, "")
        return f"{dt.day} {m_str} {dt.year}, {dt.hour:02d}:{dt.minute:02d}"
    except Exception:
        return ""


def _split_description(text: str, max_line_chars: int = 40) -> list[str]:
    """Splits description into 1 or 2 lines dynamically. Truncates with '...' only if text overflows 2 lines."""
    if not text:
        return []

    # 1. If text fits completely on 1 line: return ONLY 1 line
    if len(text) <= max_line_chars:
        return [text]

    words = text.split()
    line1_words = []
    len1 = 0
    idx = 0
    for i, w in enumerate(words):
        space = 1 if line1_words else 0
        if len1 + space + len(w) <= max_line_chars:
            line1_words.append(w)
            len1 += space + len(w)
            idx = i + 1
        else:
            break

    line1 = " ".join(line1_words)
    remaining_words = words[idx:]
    if not remaining_words:
        return [line1]

    line2_words = []
    len2 = 0
    idx2 = 0
    for i, w in enumerate(remaining_words):
        space = 1 if line2_words else 0
        if len2 + space + len(w) <= max_line_chars:
            line2_words.append(w)
            len2 += space + len(w)
            idx2 = i + 1
        else:
            break

    line2 = " ".join(line2_words)
    leftover = remaining_words[idx2:]
    if leftover:
        line2 = line2.rstrip(". ") + "..."

    return [line1, line2]

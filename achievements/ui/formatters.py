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


def format_progress_value(value) -> str:
    """`940` / `12,345` / `12.3M` / `1B`.

    Підпис живе *всередині* прогрес-бару, а бар у N-панелі вузький, тож
    «1000000000» туди не влізе. До мільйона число лишається точним (з
    роздільниками), далі стискається до M/B — на такому масштабі різниця між
    12.3M і 12,345,678 для ока однакова, а місця економиться втричі.
    """
    try:
        number = int(value)
    except Exception:
        return "0"
    if number < 0:
        number = 0
    if number < 1_000_000:
        return f"{number:,}"

    # Три значущі цифри: 1.2M, 12.3M, 948M, 1B. Десятковий знак після сотень —
    # це шум: різниця між 948.3M і 948M на прогрес-барі до мільярда невидима.
    #
    # Одиниця вибирається за вже заокругленим значенням, інакше 999,999,999
    # дало б "1000M" замість "1B".
    for divisor, suffix in ((1_000_000_000, "B"), (1_000_000, "M")):
        scaled = number / divisor
        if scaled < 0.9995:
            continue
        text = f"{scaled:.0f}" if scaled >= 99.95 else f"{scaled:.1f}"
        if text.endswith(".0"):
            text = text[:-2]
        return text + suffix
    return f"{number:,}"


def format_progress(current, target, unit="COUNT") -> str:
    """Format counts or elapsed time without changing the underlying progress."""
    if unit == 'SECONDS':
        def duration(value):
            text = format_duration(value)
            return "0 min" if text == "—" else text
        return f"{duration(current)} / {duration(target)}"
    return f"{format_progress_value(current)} / {format_progress_value(target)}"


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


# --- Description wrapping -------------------------------------------------

# Середня ширина символу опису в пікселях при ui_scale = 1. Заміряно
# blf.dimensions() віджетним шрифтом (11 pt) на справжньому реченні з опису
# ачивки: 8.0 px при ui_scale 1.5, тобто 5.33 на одиницю масштабу. Округлено
# вгору навмисно — недооцінка ширини символу дає переповнення, а переповнений
# лейбл Blender обрізає мовчки, без жодного «...»; переоцінка ж коштує щонайбільше
# зайвого переносу.
DESCRIPTION_CHAR_PX = 5.6

# Скільки рядків максимум віддаємо опису. Найдовший опис у реєстрі — 80
# символів, тож у вузькому сайдбарі (≈28 символів у рядок) йому треба три
# рядки; четвертий — запас на випадок ще вужчої панелі.
DESCRIPTION_MAX_LINES = 4

# Нижче — панель настільки вузька, що читати там нічого; вище — ширша за
# найдовший опис, тож рахувати далі немає сенсу.
DESCRIPTION_MIN_CHARS = 14
DESCRIPTION_MAX_CHARS = 120


def description_line_chars(region_width, ui_scale: float = 1.0,
                           text_fraction: float = 1.0,
                           padding: float = 30.0) -> int:
    """Скільки символів опису влазить у рядок списку завширшки `region_width`.

    `text_fraction` — частка ширини, що лишається тексту після колонки з
    іконкою (тобто `1 - factor`, з яким кличеться layout.split). `padding` —
    сумарні відступи вкладених боксів і полів регіону, у пікселях при
    ui_scale = 1; масштабуються разом зі шрифтом.

    Аргументи приходять із bpy, який під час перетягування межі регіону встигає
    віддати і сміття, і одиничну ширину згорнутої панелі, тож усе, що не схоже
    на число, зводиться до мінімуму, а не валить малювання.
    """
    try:
        width = float(region_width)
        scale = float(ui_scale)
    except (TypeError, ValueError):
        return DESCRIPTION_MIN_CHARS
    if scale <= 0:
        scale = 1.0
    usable = (width - padding * scale) * max(0.05, min(1.0, text_fraction))
    chars = int(usable // (DESCRIPTION_CHAR_PX * scale))
    return max(DESCRIPTION_MIN_CHARS, min(DESCRIPTION_MAX_CHARS, chars))


def _split_description(text: str, max_line_chars: int = 40,
                       max_lines: int = 2) -> list[str]:
    """Переносить опис по словах на щонайбільше `max_lines` рядків.

    Хвіст, що не влазить, обрізається з «...». Слово, довше за ліміт рядка,
    забирає рядок собі цілком — інакше цикл не зрушив би з місця.
    """
    if not text:
        return []

    # Влазить в один рядок — жодного розбору не потрібно.
    if len(text) <= max_line_chars:
        return [text]

    words = text.split()
    lines = []
    while words and len(lines) < max_lines:
        line_words = []
        length = 0
        while words:
            word = words[0]
            space = 1 if line_words else 0
            if line_words and length + space + len(word) > max_line_chars:
                break
            line_words.append(words.pop(0))
            length += space + len(word)
        lines.append(" ".join(line_words))

    if words and lines:
        lines[-1] = lines[-1].rstrip(". ") + "..."

    return lines

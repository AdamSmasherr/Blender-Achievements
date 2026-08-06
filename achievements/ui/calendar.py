"""
Activity-calendar heatmap: colour resolution, the generated-tile icon cache,
the pinned-day operator, and the grid drawing routine itself.
"""

import bpy

from .. import debug
from .. import engine
from .formatters import CALENDAR_COLORS, calendar_days, calendar_level, format_day_label, format_duration
from .helpers import get_preferences, _tag_redraw_all

_CELL_PX = 8                 # сторона згенерованої плитки в пікселях
_level_icons = None          # previews-колекція з плитками, або None
_level_icons_failed = False  # True — генерація не вдалась, малюємо запасним шляхом
_pinned_day = ""             # день, закріплений кліком під сіткою


def calendar_color(level):
    """Колір рівня інтенсивності: значення з налаштувань або дефолт шкали."""
    rgb = CALENDAR_COLORS[max(0, min(len(CALENDAR_COLORS) - 1, level))]
    try:
        prefs = get_preferences()
        if prefs is not None:
            value = getattr(prefs, f"cal_col_{level}", None)
            if value is not None:
                rgb = (value[0], value[1], value[2])
    except Exception as _dbg_err:  # noqa: BLE001
        debug.log("ui/calendar.py:calendar_color", _dbg_err)
    return (rgb[0], rgb[1], rgb[2], 1.0)


def _drop_level_icons():
    """Викидає згенеровані плитки, щоб наступний draw() перемалював їх у нових
    кольорах. На відміну від clear_level_icons() не чіпає закріплений день."""
    global _level_icons, _level_icons_failed
    if _level_icons is not None:
        try:
            import bpy.utils.previews
            bpy.utils.previews.remove(_level_icons)
        except Exception:
            pass
    _level_icons = None
    _level_icons_failed = False


def _calendar_colors_changed(self, context):
    _drop_level_icons()
    _tag_redraw_all()


def get_level_icons():
    """Прев'юшки-плитки під рівні інтенсивності (лениво, з кешем).

    Пікселі малюємо самі й віддаємо Blender'у готову картинку: `UILayout` не
    вміє заливати комірку довільним кольором, а `template_icon`/`icon_value`
    вміє. None означає, що згенерувати не вийшло — тоді сітка малюється
    підсвіченими кнопками (див. `_draw_calendar_grid`).
    """
    global _level_icons, _level_icons_failed
    if _level_icons is not None or _level_icons_failed:
        return _level_icons
    pcoll = None
    try:
        import bpy.utils.previews
        pcoll = bpy.utils.previews.new()
        px_count = _CELL_PX * _CELL_PX
        for i in range(len(CALENDAR_COLORS)):
            prev = pcoll.new(f"cal_lvl_{i}")
            prev.image_size = (_CELL_PX, _CELL_PX)
            prev.image_pixels_float = list(calendar_color(i)) * px_count
        _level_icons = pcoll
    except Exception as _dbg_err:  # noqa: BLE001
        debug.log("ui/calendar.py:get_level_icons", _dbg_err)
        if pcoll is not None:
            try:
                import bpy.utils.previews
                bpy.utils.previews.remove(pcoll)
            except Exception:
                pass
        _level_icons = None
        _level_icons_failed = True
    return _level_icons


def clear_level_icons():
    global _pinned_day
    _drop_level_icons()
    _pinned_day = ""


def describe_day(day_iso: str) -> str:
    """Рядок для тултіпа/закріпленого дня."""
    label = format_day_label(day_iso)
    try:
        from datetime import date
        if date.fromisoformat(day_iso) > date.today():
            return f"{label} — not yet"
    except Exception:
        pass
    try:
        seconds = engine.get_engine().get_days().get(day_iso, 0)
    except Exception as _dbg_err:  # noqa: BLE001
        debug.log("ui/calendar.py:describe_day", _dbg_err)
        seconds = 0
    if not seconds:
        return f"{label} — no activity"
    return f"{label} — {format_duration(seconds)}"


def draw_activity_calendar(layout):
    """Хітмапа останніх CALENDAR_WEEKS тижнів + закріплений клікою день.

    Ширину сітки НЕ обмежуємо через `UILayout.alignment`: сітка — це 91 кнопка
    у вкладених рядках із align=True, і ставити на такий рядок ще й alignment
    означає вести розкладку шляхом, яким у Blender ходять рідко. Саме на
    вирівнюванні кнопок (`ui::item_align`) валилось вікно налаштувань, тож
    ширину тепер обмежує викликач звичайним split'ом.
    """
    from datetime import date

    eng = engine.get_engine()
    days = eng.get_days()
    today = date.today()
    icons = get_level_icons()
    weeks = calendar_days()

    # Кнопки-плитки іконкові (text=""), тож не розтягуються на всю ширину
    # рядка — сітка завжди природної, фіксованої ширини. Без обгортки вона
    # просто лишається ліворуч, коли N-панель ширша за 13 тижнів. Обгортка —
    # ОКРЕМИЙ рядок без align=True: alignment='CENTER' на ньому центрує сітку
    # як єдиний блок, не чіпаючи вирівнювання самих кнопок усередині.
    grid_wrap = layout.row()
    grid_wrap.alignment = 'CENTER'
    grid = grid_wrap.column(align=True)
    for weekday in range(7):
        row = grid.row(align=True)
        for week in weeks:
            day = week[weekday]
            iso = day.isoformat()
            future = day > today
            level = 0 if future else calendar_level(days.get(iso, 0))
            cell = row.row(align=True)
            cell.enabled = not future
            if icons is not None:
                op = cell.operator("achievement.day_info", text="", emboss=False,
                                   icon_value=icons[f"cal_lvl_{level}"].icon_id)
            else:
                # Запасний шлях, якщо згенерувати плитки не вдалось: підсвічена
                # кнопка замість кольору. Менш красиво, але тултіпи ті самі.
                op = cell.operator("achievement.day_info", text=" ", depress=level > 0)
            op.day = iso

    legend_wrap = layout.row()
    legend_wrap.alignment = 'CENTER'
    legend = legend_wrap.row(align=True)
    legend.label(text="Less")
    if icons is not None:
        for i in range(len(CALENDAR_COLORS)):
            legend.label(text="", icon_value=icons[f"cal_lvl_{i}"].icon_id)
    legend.label(text="More")

    detail = layout.row()
    detail.enabled = False
    detail.label(text=describe_day(_pinned_day or today.isoformat()))

    if not days:
        hint = layout.row()
        hint.enabled = False
        hint.label(text="History starts from today.", icon='INFO')


class ACHIEVEMENT_OT_day_info(bpy.types.Operator):
    """Один день у календарі активності.

    Кнопка існує заради двох речей, яких не дає намальована картинка: тултіп
    під курсором (рахується в `description` з властивості `day`) і клік, що
    закріплює день рядком під сіткою — у вузькому сайдбарі це надійніше за
    наведення.
    """
    bl_idname = "achievement.day_info"
    bl_label = "Day Activity"
    bl_options = {'INTERNAL'}

    day: bpy.props.StringProperty(name="Day", default="")

    @classmethod
    def description(cls, context, properties):
        return describe_day(getattr(properties, "day", "") or "")

    def execute(self, context):
        global _pinned_day
        _pinned_day = self.day
        try:
            if context.area is not None:
                context.area.tag_redraw()
        except Exception as _dbg_err:  # noqa: BLE001
            debug.log("ui/calendar.py:day_info/redraw", _dbg_err)
        return {'FINISHED'}

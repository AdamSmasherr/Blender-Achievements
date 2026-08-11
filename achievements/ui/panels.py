"""
Read-only display panels: the achievements list (used both in the N-panel
sidebar and at the bottom of AddonPreferences) and the two Panel classes
that host it plus the activity calendar in the 3D-View sidebar.
"""

import bpy

from .. import registry
from ..rules import get_achievement_progress
from .. import engine
from .calendar import draw_activity_calendar
from .formatters import (DESCRIPTION_MAX_LINES, _split_description,
                         description_line_chars, format_progress,
                         format_unlock_date)
from .helpers import get_preferences, layout_metrics
from .icons import get_custom_icons

# Частка ширини регіону, яка реально дістається списку. У сайдбарі це весь
# регіон; у вікні налаштувань список малюється всередині розгорнутого блоку
# аддона, з відступами, розміру яких API не повідомляє, тож беремо із запасом
# униз. Промахнутися тут дешево: те вікно широке, і навіть 0.7 дає більше
# символів, ніж треба найдовшому опису.
PREFS_WIDTH_FRACTION = 0.7

# Ширини, з яких список малювався до того, як почав рахувати від регіону.
# Лишаються запасним варіантом на випадок, коли контексту нема (виклик із
# тестів) або регіон ще не має осмисленої ширини.
FALLBACK_SIDEBAR_CHARS = 36
FALLBACK_PREFS_CHARS = 65

# --- Compact mode ---------------------------------------------------------
# Іконка в компактному рядку — заввишки з рядок, не збільшена.
COMPACT_ICON_SCALE = 1.0
# Скільки ширини рядка після іконки віддано назві; решта — бару або даті.
COMPACT_TITLE_FACTOR = 0.55
# Частка ширини під саму іконку — для розрахунку, скільки символів лишається
# тексту (у розгорнутому режимі це 0.25, тут іконка на порядок менша).
COMPACT_ICON_FACTOR = 0.12


def _description_chars(context, split_factor, is_sidebar):
    """Ліміт символів у рядку опису для поточної ширини панелі."""
    width, ui_scale = layout_metrics(context)
    if width is None:
        return FALLBACK_SIDEBAR_CHARS if is_sidebar else FALLBACK_PREFS_CHARS
    text_fraction = (1.0 - split_factor)
    if not is_sidebar:
        text_fraction *= PREFS_WIDTH_FRACTION
    return description_line_chars(width, ui_scale, text_fraction)


def _draw_icon(container, ach_id, ach_def, pcoll, icon_scale, locked):
    """Артворк ачивки, або вбудований значок, якщо його немає."""
    fallback = 'LOCKED' if locked else ('SOLO_ON' if ach_def.rare else 'FUND')
    if pcoll and ach_id in pcoll:
        try:
            container.template_icon(icon_value=pcoll[ach_id].icon_id, scale=icon_scale)
            return
        except Exception:
            pass
    container.label(text="", icon=fallback)


def _draw_progress(container, prog):
    """Прогрес-бар заблокованої ачивки.

    `progress()` є на UILayout ще з Blender 4.0, а аддон вимагає 4.4+, тож
    запасний варіант із голим числом — не про старі версії, а про layout-
    заглушки, у які малюють тести.
    """
    curr, target = prog
    label = format_progress(curr, target)
    if hasattr(container, "progress"):
        container.progress(factor=min(1.0, max(0.0, curr / target)),
                           text=label, type='BAR')
    else:
        container.label(text=label)


def _draw_full_item(box, ach_id, ach_def, pcoll, icon_scale, split_factor,
                    max_chars, unlocked_at=None, prog=None):
    """Розгорнутий рядок: велика іконка, назва, опис і бар під ним."""
    locked = unlocked_at is None
    item_box = box.box()
    if hasattr(item_box, "split"):
        split = item_box.split(factor=split_factor, align=True)
    else:
        split = item_box.row(align=True)

    # Колонка з іконкою. Фіксована частка ширини — те, що утримує масштаб
    # іконки незалежно від ширини панелі.
    icon_col = split.column(align=True)
    if locked:
        icon_col = icon_col.row(align=True)
        if hasattr(icon_col, "active"):
            icon_col.active = False
    _draw_icon(icon_col, ach_id, ach_def, pcoll, icon_scale, locked)

    main_col = split.column(align=True)

    # Назва, а для розблокованої — ще й дата, праворуч на тій самій висоті.
    title_row = main_col.row(align=True)
    title_row.label(text=ach_def.title)
    if not locked:
        date_row = title_row.row(align=True)
        if hasattr(date_row, "alignment"):
            date_row.alignment = 'RIGHT'
        date_row.label(text=format_unlock_date(unlocked_at))

    for line in _split_description(ach_def.description,
                                   max_line_chars=max_chars,
                                   max_lines=DESCRIPTION_MAX_LINES):
        main_col.label(text=line)

    # Бар — останнім рядком, на всю ширину під описом. Число всередині нього,
    # тому в рядку назви його вже немає.
    if prog is not None:
        _draw_progress(main_col.row(align=True), prog)


def _draw_compact_item(container, ach_id, ach_def, pcoll, title_chars,
                       unlocked_at=None, prog=None):
    """Компактний рядок: мала іконка, назва і бар (або дата) — одна лінія.

    Без вкладеного box'а: саме його поля й робили зі списку рулон.
    """
    locked = unlocked_at is None
    row = container.row(align=True)

    icon_holder = row.row(align=True)
    if locked and hasattr(icon_holder, "active"):
        icon_holder.active = False
    _draw_icon(icon_holder, ach_id, ach_def, pcoll, COMPACT_ICON_SCALE, locked)

    if hasattr(row, "split"):
        body = row.split(factor=COMPACT_TITLE_FACTOR, align=True)
    else:
        body = row.row(align=True)

    # Назва в один рядок: тут вона єдине, що описує ачивку, тож обрізати її
    # своїм «...» краще, ніж дати Blender'у мовчки зрізати хвіст.
    title = _split_description(ach_def.title, max_line_chars=title_chars, max_lines=1)
    body.label(text=title[0] if title else ach_def.title)

    right = body.row(align=True)
    if prog is not None:
        _draw_progress(right, prog)
    elif not locked:
        if hasattr(right, "alignment"):
            right.alignment = 'RIGHT'
        right.label(text=format_unlock_date(unlocked_at))


def draw_achievements_list(layout, context=None, icon_scale=3.4375, is_sidebar=False):
    eng = engine.get_engine()
    stats = eng.get_stats()
    pcoll = get_custom_icons()

    prefs = get_preferences(context)
    compact = is_sidebar and bool(getattr(prefs, "compact_sidebar", False))

    if compact:
        # Іконка тут завширшки в один рядок, а не чверть панелі, тож тексту
        # дістається майже все — але ділиться воно між назвою і баром.
        split_factor = COMPACT_ICON_FACTOR
        max_chars = _description_chars(context, split_factor, is_sidebar)
        title_chars = max(6, int(max_chars * COMPACT_TITLE_FACTOR))
    else:
        split_factor = 0.25 if is_sidebar else 0.12
        max_chars = _description_chars(context, split_factor, is_sidebar)
        title_chars = max_chars

    # 1. Overall Progress Header (at top of list)
    top_box = layout.box()
    top_box.label(text=f"Progress: {stats['unlocked']}/{stats['total']} ({stats['percentage']}%)", icon='SOLO_ON')

    # Split achievements into unlocked and locked
    unlocked_list = []
    locked_list = []

    for ach_id, ach_def in registry.ACHIEVEMENTS.items():
        if eng.is_unlocked(ach_id):
            unlocked_list.append((ach_id, ach_def, eng.get_unlocked_at(ach_id)))
        else:
            locked_list.append((ach_id, ach_def))

    # Sort unlocked by timestamp descending
    unlocked_list.sort(key=lambda x: str(x[2]), reverse=True)

    # 2. Unlocked Achievements Section (Listed first)
    if unlocked_list:
        unlocked_box = layout.box()
        unlocked_box.label(text=f"UNLOCKED ACHIEVEMENTS ({len(unlocked_list)})", icon='CHECKMARK')

        for ach_id, ach_def, unlocked_at in unlocked_list:
            if compact:
                _draw_compact_item(unlocked_box, ach_id, ach_def, pcoll,
                                   title_chars, unlocked_at=unlocked_at)
            else:
                _draw_full_item(unlocked_box, ach_id, ach_def, pcoll, icon_scale,
                                split_factor, max_chars, unlocked_at=unlocked_at)

    # 3. Locked Achievements Section (Listed second)
    if locked_list:
        locked_box = layout.box()
        locked_box.label(text=f"LOCKED ACHIEVEMENTS ({len(locked_list)})", icon='LOCKED')

        for ach_id, ach_def in locked_list:
            # Нічого не коштує: значення вже пораховані одним проходом по всіх
            # правилах і кешуються на секунду (rules.get_achievement_progress).
            prog = get_achievement_progress(ach_id)
            if compact:
                _draw_compact_item(locked_box, ach_id, ach_def, pcoll,
                                   title_chars, prog=prog)
            else:
                _draw_full_item(locked_box, ach_id, ach_def, pcoll, icon_scale,
                                split_factor, max_chars, prog=prog)


class ACHIEVEMENT_PT_panel(bpy.types.Panel):
    """Sidebar Panel for Blender Achievements."""
    bl_label = "Achievements"
    bl_idname = "ACHIEVEMENT_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Achievements"
    # Календар стоїть вище, тож списку ачивок лишається наступний порядковий.
    bl_order = 1

    @classmethod
    def poll(cls, context):
        prefs = get_preferences(context)
        return getattr(prefs, "show_in_sidebar", True) if prefs is not None else True

    def draw(self, context):
        layout = self.layout
        draw_achievements_list(layout, context, icon_scale=3.4375, is_sidebar=True)


class ACHIEVEMENT_PT_calendar(bpy.types.Panel):
    """Календар активності. Окремою панеллю і згорнутий за замовчуванням
    навмисно: сітка — це 91 UI-елемент, а вміст згорнутої панелі Blender не
    малює взагалі, тож поки її не розгорнули, вона не коштує нічого."""
    bl_label = "Activity Calendar"
    bl_idname = "ACHIEVEMENT_PT_calendar"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Achievements"
    bl_order = 0
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        prefs = get_preferences(context)
        return getattr(prefs, "show_calendar_in_sidebar", True) if prefs is not None else True

    def draw(self, context):
        draw_activity_calendar(self.layout)

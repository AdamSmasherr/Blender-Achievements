"""
Read-only display panels: the achievements list (used both in the N-panel
sidebar and at the bottom of AddonPreferences) and the two Panel classes
that host it plus the activity calendar in the 3D-View sidebar.
"""

import textwrap

import bpy

from .. import registry
from ..rules import get_achievement_progress
from .. import engine
from .calendar import draw_activity_calendar
from .catalog import filter_achievements, get_browser
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
    # The sidebar includes tabs, its scrollbar and two nested box margins.
    # Reserve that space before wrapping, so Blender does not truncate a line
    # that our character estimate thought would fit.
    return description_line_chars(width, ui_scale, text_fraction,
                                  padding=60.0 if is_sidebar else 30.0)


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


def _draw_title(container, ach_id, title):
    """Render a stable left edge and keep details one click away.

    An ``emboss=False`` operator is still a button in Blender's layout engine:
    its text is centered in the available cell, so short achievement names
    appeared at different x positions. A label owns the text alignment; the
    adjacent info button owns the popup action.
    """
    row = container.row(align=True)
    row.alignment = 'LEFT'
    row.label(text=title)
    button = row.operator("achievement.details", text="", icon='INFO',
                          emboss=False)
    button.achievement_id = ach_id


def _draw_progress(container, prog, unit="COUNT"):
    """Прогрес-бар заблокованої ачивки.

    `progress()` є на UILayout ще з Blender 4.0, а аддон вимагає 4.4+, тож
    запасний варіант із голим числом — не про старі версії, а про layout-
    заглушки, у які малюють тести.
    """
    curr, target = prog
    label = format_progress(curr, target, unit)
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

    # Give the clickable title its own line; a timestamp crowds it in a sidebar.
    _draw_title(main_col, ach_id, ach_def.title)
    if not locked:
        date_row = main_col.row(align=True)
        date_row.label(text=format_unlock_date(unlocked_at))

    for line in _split_description(ach_def.description,
                                   max_line_chars=max_chars,
                                   max_lines=DESCRIPTION_MAX_LINES):
        main_col.label(text=line)

    # Бар — останнім рядком, на всю ширину під описом. Число всередині нього,
    # тому в рядку назви його вже немає.
    if prog is not None:
        _draw_progress(main_col.row(align=True), prog, ach_def.progress_unit)


def _draw_compact_item(container, ach_id, ach_def, pcoll, title_chars,
                       unlocked_at=None, prog=None):
    """Компактний рядок: мала іконка, назва і бар (або дата) — одна лінія.

    Без вкладеного box'а: саме його поля й робили зі списку рулон.
    """
    locked = unlocked_at is None
    # Keep three explicit slots.  A row with no progress bar must reserve the
    # same right-hand space as a row with one; otherwise Blender's auto-width
    # layout reallocates the empty column and moves the title to the right.
    row = container.row(align=True)
    if hasattr(row, "split"):
        outer = row.split(factor=COMPACT_ICON_FACTOR, align=True)
        icon_col = outer.column(align=True)
        content = outer.column(align=True)
        content_split = content.split(factor=COMPACT_TITLE_FACTOR, align=True)
        title_col = content_split.column(align=True)
        right = content_split.column(align=True)
    else:
        icon_col = row.row(align=True)
        title_col = row.row(align=True)
        right = row.row(align=True)

    icon_holder = icon_col.row(align=True)
    if locked and hasattr(icon_holder, "active"):
        icon_holder.active = False
    _draw_icon(icon_holder, ach_id, ach_def, pcoll, COMPACT_ICON_SCALE, locked)

    # Назва в один рядок: тут вона єдине, що описує ачивку, тож обрізати її
    # своїм «...» краще, ніж дати Blender'у мовчки зрізати хвіст.
    title = _split_description(ach_def.title, max_line_chars=title_chars, max_lines=1)
    _draw_title(title_col, ach_id, title[0] if title else ach_def.title)

    if prog is not None:
        _draw_progress(right, prog, ach_def.progress_unit)
    elif not locked:
        if hasattr(right, "alignment"):
            right.alignment = 'RIGHT'
        right.label(text=format_unlock_date(unlocked_at))


def draw_achievements_list(layout, context=None, icon_scale=3.4375, is_sidebar=False):
    if context is None:
        context = bpy.context
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

    browser = get_browser(context)
    definitions = list(registry.ACHIEVEMENTS.values())
    if browser is not None:
        controls = layout.column(align=True)
        search = controls.row(align=True)
        search.prop(browser, "query", text="", icon='VIEWZOOM')
        clear = search.row(align=True)
        clear.enabled = bool(browser.query.strip() or browser.status != 'ALL'
                             or browser.category != 'ALL')
        clear.operator("achievement.clear_filters", text="", icon='LOOP_BACK')
        controls.row(align=True).prop(browser, "status", expand=True)
        controls.prop(browser, "category", text="")
        if is_sidebar and prefs is not None:
            controls.prop(prefs, "compact_sidebar", text="Compact list")
        definitions = filter_achievements(
            definitions, set(eng.get_unlocked_ids()), browser.query,
            browser.status, browser.category)
        if len(definitions) != stats['total']:
            layout.label(text=f"Showing {len(definitions)} of {stats['total']}")

    if not definitions:
        empty = layout.column(align=True)
        empty.label(text="No matching achievements", icon='INFO')
        empty.operator("achievement.clear_filters", text="Show All Achievements")
        return

    hint = layout.row()
    hint.enabled = False
    hint.label(text="Click a name for details", icon='INFO')

    # Split achievements into unlocked and locked
    unlocked_list = []
    locked_list = []

    for ach_def in definitions:
        ach_id = ach_def.id
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


def draw_achievement_details(layout, ach_def):
    """Read-only popup content; long conditions are wrapped without truncation."""
    def paragraph(text):
        col = layout.column(align=True)
        for line in textwrap.wrap(text, width=52):
            col.label(text=line)

    eng = engine.get_engine()
    header = layout.row()
    _draw_icon(header, ach_def.id, ach_def, get_custom_icons(), 2.0,
               not eng.is_unlocked(ach_def.id))
    title = header.column(align=True)
    for line in textwrap.wrap(ach_def.title, width=38):
        title.label(text=line)
    title.label(text=ach_def.category)
    if ach_def.rare:
        title.label(text="Rare achievement", icon='SOLO_ON')

    layout.separator()
    paragraph(ach_def.description)
    layout.separator()
    layout.label(text="How it counts", icon='INFO')
    paragraph(ach_def.tracking_hint)
    layout.separator()
    if eng.is_unlocked(ach_def.id):
        layout.label(text="Unlocked", icon='CHECKMARK')
        layout.label(text=format_unlock_date(eng.get_unlocked_at(ach_def.id)))
    else:
        layout.label(text="Locked", icon='LOCKED')
        prog = get_achievement_progress(ach_def.id)
        if prog is not None:
            _draw_progress(layout.row(), prog, ach_def.progress_unit)
            if ach_def.check is not None:
                paragraph("The bar shows the amount reached so far. Complete the condition above as well to unlock.")


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

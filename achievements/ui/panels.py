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
from .formatters import _split_description, format_unlock_date
from .helpers import get_preferences
from .icons import get_custom_icons


def draw_achievements_list(layout, icon_scale=3.4375, is_sidebar=False):
    eng = engine.get_engine()
    stats = eng.get_stats()
    pcoll = get_custom_icons()
    max_chars = 36 if is_sidebar else 65

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
            item_box = unlocked_box.box()
            if hasattr(item_box, "split"):
                split = item_box.split(factor=0.25 if is_sidebar else 0.12, align=True)
            else:
                split = item_box.row(align=True)

            # Icon column (Fixed proportion guarantees max scale=3.4375 regardless of panel width)
            icon_col = split.column(align=True)
            if pcoll and ach_id in pcoll:
                try:
                    icon_col.template_icon(icon_value=pcoll[ach_id].icon_id, scale=icon_scale)
                except Exception:
                    icon_col.label(text="", icon='SOLO_ON' if ach_def.rare else 'FUND')
            else:
                icon_col.label(text="", icon='SOLO_ON' if ach_def.rare else 'FUND')

            # Main content column
            main_col = split.column(align=True)

            # Line 1: Title (left) + Date (right) on the exact same height
            title_row = main_col.row(align=True)
            title_row.label(text=ach_def.title)

            date_row = title_row.row(align=True)
            if hasattr(date_row, "alignment"):
                date_row.alignment = 'RIGHT'
            date_str = format_unlock_date(unlocked_at)
            date_row.label(text=date_str)

            # Line 2 & Line 3: Description spanning full width under title/date
            desc_lines = _split_description(ach_def.description, max_line_chars=max_chars)
            for line in desc_lines:
                main_col.label(text=line)

    # 3. Locked Achievements Section (Listed second)
    if locked_list:
        locked_box = layout.box()
        locked_box.label(text=f"LOCKED ACHIEVEMENTS ({len(locked_list)})", icon='LOCKED')

        for ach_id, ach_def in locked_list:
            item_box = locked_box.box()
            if hasattr(item_box, "split"):
                split = item_box.split(factor=0.25 if is_sidebar else 0.12, align=True)
            else:
                split = item_box.row(align=True)

            # Icon column (Fixed proportion guarantees max scale=3.4375 regardless of panel width)
            icon_col = split.column(align=True)
            icon_sub = icon_col.row(align=True)
            if hasattr(icon_sub, "active"):
                icon_sub.active = False
            if pcoll and ach_id in pcoll:
                try:
                    icon_sub.template_icon(icon_value=pcoll[ach_id].icon_id, scale=icon_scale)
                except Exception:
                    icon_sub.label(text="", icon='LOCKED')
            else:
                icon_sub.label(text="", icon='LOCKED')

            # Main content column
            main_col = split.column(align=True)

            # Line 1: Title (left) + Progress counter (right) on the exact same height
            title_row = main_col.row(align=True)
            title_row.label(text=ach_def.title)

            prog = get_achievement_progress(ach_id)
            if prog is not None:
                curr, target = prog
                prog_row = title_row.row(align=True)
                if hasattr(prog_row, "alignment"):
                    prog_row.alignment = 'RIGHT'
                prog_row.label(text=f"{curr} / {target}")

            # Line 2 & Line 3: Description spanning full width under title/progress
            desc_lines = _split_description(ach_def.description, max_line_chars=max_chars)
            for line in desc_lines:
                main_col.label(text=line)


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
        draw_achievements_list(layout, icon_scale=3.4375, is_sidebar=True)


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

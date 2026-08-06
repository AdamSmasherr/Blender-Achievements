"""
UI layer for Blender Achievements: AddonPreferences, sidebar panels,
operators, and the pure display-formatting helpers behind them.

Split out of what used to be a single achievements/__init__.py so each piece
(formatting math, calendar widget, sound-profile plumbing, operators,
panels, preferences) lives in its own module. This package's public names
are re-exported one level up, from achievements/__init__.py, so
`import achievements as addon; addon.format_duration(...)` etc. keep
working for existing callers/tests.
"""

import bpy

from .calendar import ACHIEVEMENT_OT_day_info, calendar_color, clear_level_icons, describe_day, get_level_icons
from .formatters import (
    CALENDAR_COLORS,
    CALENDAR_LEVEL_LABELS,
    CALENDAR_LEVEL_SHORT,
    CALENDAR_THRESHOLDS,
    CALENDAR_WEEKS,
    _split_description,
    calendar_days,
    calendar_level,
    format_day_label,
    format_duration,
    format_unlock_date,
)
from .helpers import _tag_redraw_all, get_preferences
from .icons import clear_custom_icons, get_custom_icons
from .operators import (
    ACHIEVEMENT_OT_preview_sound,
    ACHIEVEMENT_OT_profile_add,
    ACHIEVEMENT_OT_profile_duplicate,
    ACHIEVEMENT_OT_profile_remove,
    ACHIEVEMENT_OT_profiles_export,
    ACHIEVEMENT_OT_profiles_import,
    ACHIEVEMENT_OT_reset_colors,
    ACHIEVEMENT_OT_reset_progress,
    ACHIEVEMENT_OT_test_toast,
)
from .panels import ACHIEVEMENT_PT_calendar, ACHIEVEMENT_PT_panel, draw_achievements_list
from .preferences import ACHIEVEMENT_AddonPreferences, ACHIEVEMENT_SoundProfile, ACHIEVEMENT_UL_sound_profiles
from .sound_paths import DEFAULT_PROFILE_FILE, _pack_sound_path, _unpack_sound_path

# Порядок реєстрації важливий: PropertyGroup та UIList мають бути
# зареєстровані ДО AddonPreferences, яка на них посилається
# (CollectionProperty(type=...) / template_list). Порядок панелей у
# сайдбарі задає bl_order, а не порядок реєстрації.
CLASSES = (
    ACHIEVEMENT_SoundProfile,
    ACHIEVEMENT_UL_sound_profiles,
    ACHIEVEMENT_AddonPreferences,
    ACHIEVEMENT_OT_reset_progress,
    ACHIEVEMENT_OT_test_toast,
    ACHIEVEMENT_OT_profile_add,
    ACHIEVEMENT_OT_profile_remove,
    ACHIEVEMENT_OT_profile_duplicate,
    ACHIEVEMENT_OT_profiles_export,
    ACHIEVEMENT_OT_profiles_import,
    ACHIEVEMENT_OT_preview_sound,
    ACHIEVEMENT_OT_reset_colors,
    ACHIEVEMENT_OT_day_info,
    ACHIEVEMENT_PT_calendar,
    ACHIEVEMENT_PT_panel,
)


def register():
    for cls in CLASSES:
        if not hasattr(bpy.types, cls.__name__):
            try:
                bpy.utils.register_class(cls)
            except (ValueError, RuntimeError):
                pass


def unregister():
    clear_custom_icons()
    clear_level_icons()

    for cls in reversed(CLASSES):
        if hasattr(bpy.types, cls.__name__):
            try:
                bpy.utils.unregister_class(cls)
            except (ValueError, RuntimeError):
                pass

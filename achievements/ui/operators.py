"""
Operators driving the UI: progress reset, sound-profile CRUD/export/import,
colour-palette reset, toast/sound previews.
"""

import json
import os

import bpy
from bpy_extras.io_utils import ExportHelper, ImportHelper

from .. import engine
from .. import registry
from .. import sounds
from .. import toast
from .formatters import CALENDAR_COLORS
from .helpers import get_preferences, _tag_redraw_all
from .sound_paths import (
    DEFAULT_PROFILE_FILE,
    _dict_to_profile,
    _profile_to_dict,
    _validated_json_path,
)


class ACHIEVEMENT_OT_reset_progress(bpy.types.Operator):
    """Erase every unlocked achievement and all cumulative stats."""
    bl_idname = "achievement.reset_progress"
    bl_label = "Reset All Progress"
    bl_description = ("Permanently erase all unlocked achievements and cumulative "
                      "stats. This cannot be undone")
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        # Дія незворотна і стирає прогрес за всі сесії — питаємо підтвердження.
        wm = context.window_manager
        try:
            return wm.invoke_confirm(
                self, event,
                title="Reset all achievement progress?",
                message="Every unlocked achievement and all cumulative stats "
                        "will be erased. This cannot be undone.",
                confirm_text="Reset",
                icon='WARNING',
            )
        except TypeError:
            # Старіші збірки не знають іменованих аргументів invoke_confirm.
            return wm.invoke_confirm(self, event)

    def execute(self, context):
        eng = engine.get_engine()
        ok = eng.reset_all()
        if ok:
            self.report({'INFO'}, "All achievement progress has been reset")
        else:
            self.report({'ERROR'}, "Could not write the reset state to disk")
        _tag_redraw_all()
        return {'FINISHED'} if ok else {'CANCELLED'}


class ACHIEVEMENT_OT_test_toast(bpy.types.Operator):
    """Trigger a custom viewport achievement notification."""
    bl_idname = "achievement.test_toast"
    bl_label = "Test Notification"
    bl_description = "Show a test viewport achievement notification"

    # Прев'ю показує справжню іконку — інакше картка з порожньою плиткою не
    # давала побачити ні відтінок, ні фон, які саме тут і налаштовують.
    PREVIEW_ICON_ID = "LIVE_TO_DIE_ANOTHER_DAY"

    rare: bpy.props.BoolProperty(name="Rare Golden Glow", default=True)

    def execute(self, context):
        icon_path = engine._resolve_icon_path(
            registry.ACHIEVEMENTS.get(self.PREVIEW_ICON_ID))
        # sound_path не передаємо — звук візьметься зі схеми (пресет/профіль).
        if self.rare:
            toast.show(
                "Legendary Unlock",
                "You did something truly rare.",
                rare=True,
                icon_path=icon_path,
            )
        else:
            toast.show(
                "Winner",
                "Standard achievement unlocked.",
                rare=False,
                icon_path=icon_path,
            )
        return {'FINISHED'}


class ACHIEVEMENT_OT_profile_add(bpy.types.Operator):
    """Add a new custom sound profile."""
    bl_idname = "achievement.profile_add"
    bl_label = "Add Sound Profile"
    bl_description = "Create a new custom sound profile"

    def execute(self, context):
        prefs = get_preferences(context)
        if prefs is None:
            return {'CANCELLED'}
        p = prefs.sound_profiles.add()
        p.name = f"Profile {len(prefs.sound_profiles)}"
        # Prefill from the currently selected built-in preset for convenience.
        base = prefs.sound_preset if prefs.sound_preset != 'CUSTOM' else 'STEAM'
        for slot in sounds.SLOTS:
            path = sounds.preset_path(base, slot)
            if path:
                setattr(p, f"{slot}_sound", path)
        prefs.active_profile_index = len(prefs.sound_profiles) - 1
        return {'FINISHED'}


class ACHIEVEMENT_OT_profile_remove(bpy.types.Operator):
    """Remove the selected custom sound profile."""
    bl_idname = "achievement.profile_remove"
    bl_label = "Remove Sound Profile"
    bl_description = "Delete the selected custom sound profile"

    def execute(self, context):
        prefs = get_preferences(context)
        if prefs is None or not prefs.sound_profiles:
            return {'CANCELLED'}
        idx = prefs.active_profile_index
        if 0 <= idx < len(prefs.sound_profiles):
            prefs.sound_profiles.remove(idx)
            prefs.active_profile_index = max(0, min(idx, len(prefs.sound_profiles) - 1))
        return {'FINISHED'}


class ACHIEVEMENT_OT_profile_duplicate(bpy.types.Operator):
    """Duplicate the selected custom sound profile."""
    bl_idname = "achievement.profile_duplicate"
    bl_label = "Duplicate Sound Profile"
    bl_description = "Create a copy of the selected profile"

    def execute(self, context):
        prefs = get_preferences(context)
        if prefs is None:
            return {'CANCELLED'}
        src = sounds.get_active_profile(prefs)
        if src is None:
            return {'CANCELLED'}
        new = prefs.sound_profiles.add()
        new.name = f"{src.name} Copy"
        for slot in sounds.SLOTS:
            setattr(new, f"{slot}_sound", getattr(src, f"{slot}_sound", ""))
            setattr(new, f"{slot}_volume", getattr(src, f"{slot}_volume", 1.0))
        prefs.active_profile_index = len(prefs.sound_profiles) - 1
        return {'FINISHED'}


class ACHIEVEMENT_OT_profiles_export(bpy.types.Operator, ExportHelper):
    """Export all custom sound profiles to a JSON file."""
    bl_idname = "achievement.profiles_export"
    bl_label = "Export Profiles"
    bl_description = "Save all custom sound profiles to a JSON file, so they can be moved to another machine"

    filename_ext = ".json"
    filter_glob: bpy.props.StringProperty(default="*.json", options={'HIDDEN'})
    filepath: bpy.props.StringProperty(subtype='FILE_PATH', default=DEFAULT_PROFILE_FILE)

    def invoke(self, context, event):
        # ExportHelper типово підставляє ім'я .blend-файлу; профілі до нього
        # відношення не мають, тож пропонуємо власне ім'я.
        self.filepath = DEFAULT_PROFILE_FILE
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        prefs = get_preferences(context)
        if prefs is None or not prefs.sound_profiles:
            self.report({'WARNING'}, "No custom profiles to export")
            return {'CANCELLED'}

        path = _validated_json_path(self.filepath)
        if path is None:
            self.report({'ERROR'}, "Enter a file name for the export")
            return {'CANCELLED'}

        data = [_profile_to_dict(p) for p in prefs.sound_profiles]
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError as err:
            self.report({'ERROR'}, f"Failed to export profiles: {err}")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Exported {len(data)} profile(s) to {path}")
        return {'FINISHED'}


class ACHIEVEMENT_OT_profiles_import(bpy.types.Operator, ImportHelper):
    """Import custom sound profiles from a JSON file (appends to the existing list)."""
    bl_idname = "achievement.profiles_import"
    bl_label = "Import Profiles"
    bl_description = "Add custom sound profiles from a previously exported JSON file"

    filename_ext = ".json"
    filter_glob: bpy.props.StringProperty(default="*.json", options={'HIDDEN'})
    filepath: bpy.props.StringProperty(subtype='FILE_PATH')

    def execute(self, context):
        prefs = get_preferences(context)
        if prefs is None:
            return {'CANCELLED'}
        path = _validated_json_path(self.filepath)
        if path is None or not os.path.isfile(path):
            self.report({'ERROR'}, "Select a profiles .json file to import")
            return {'CANCELLED'}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as err:
            self.report({'ERROR'}, f"Failed to read profiles file: {err}")
            return {'CANCELLED'}
        if not isinstance(data, list):
            self.report({'ERROR'}, "Not a valid profiles export file")
            return {'CANCELLED'}
        count = 0
        missing = 0
        for entry in data:
            if isinstance(entry, dict):
                p = _dict_to_profile(prefs, entry)
                for slot in sounds.SLOTS:
                    if sounds.is_missing(getattr(p, f"{slot}_sound", "")):
                        missing += 1
                count += 1
        if count:
            prefs.active_profile_index = len(prefs.sound_profiles) - 1
        if missing:
            self.report({'WARNING'},
                        f"Imported {count} profile(s); {missing} sound file(s) "
                        f"could not be found on this machine")
        else:
            self.report({'INFO'}, f"Imported {count} profile(s)")
        return {'FINISHED'}


class ACHIEVEMENT_OT_reset_colors(bpy.types.Operator):
    """Return one palette to its shipped colours."""
    bl_idname = "achievement.reset_colors"
    bl_label = "Reset Colours"
    bl_description = "Restore the default colours of this palette"

    target: bpy.props.StringProperty(name="Target", default='STEAM')

    def execute(self, context):
        prefs = get_preferences(context)
        if prefs is None:
            return {'CANCELLED'}
        if self.target == 'CALENDAR':
            for i, rgb in enumerate(CALENDAR_COLORS):
                setattr(prefs, f"cal_col_{i}", rgb)
        elif self.target == 'ICON':
            for key in toast.ICON_COLOR_KEYS:
                setattr(prefs, toast.icon_color_prop_name(key),
                        toast.ICON_COLOR_DEFAULTS[key])
        elif self.target in toast.STYLE_COLOR_KEYS:
            for key in toast.STYLE_COLOR_KEYS[self.target]:
                setattr(prefs, toast.color_prop_name(self.target, key),
                        toast.STYLE_COLOR_DEFAULTS[self.target][key])
        else:
            return {'CANCELLED'}
        _tag_redraw_all()
        return {'FINISHED'}


class ACHIEVEMENT_OT_preview_sound(bpy.types.Operator):
    """Play the slot's sound, or stop it if it is already playing."""
    bl_idname = "achievement.preview_sound"
    bl_label = "Preview Sound"
    bl_description = "Play the sound currently assigned to this slot (click again to stop)"

    slot: bpy.props.StringProperty(name="Slot", default="unlock")

    def execute(self, context):
        # Друге натискання під час програвання — зупинка.
        if sounds.is_previewing(self.slot):
            sounds.stop_preview(self.slot)
            return {'FINISHED'}
        prefs = get_preferences(context)
        path, vol = sounds.resolve(self.slot, prefs)
        if not path:
            self.report({'WARNING'}, f"No sound assigned to '{sounds.SLOT_LABELS.get(self.slot, self.slot)}'")
            return {'CANCELLED'}
        if vol <= 0.0:
            self.report({'WARNING'}, "Volume is 0 — raise the slider to hear it")
            return {'CANCELLED'}
        sounds.play(path, vol, slot=self.slot)
        return {'FINISHED'}

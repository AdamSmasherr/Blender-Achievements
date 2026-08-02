"""
Blender Achievements

Native zero-dependency achievement tracking and custom GPU viewport notifications for Blender.
"""

import json
import os
import bpy
from bpy_extras.io_utils import ExportHelper, ImportHelper

from . import toast
from . import storage
from . import achievements
from . import engine
from . import sounds
from . import debug


# ----------------- Background Operator Watcher -----------------

class ACHIEVEMENT_OT_watcher(bpy.types.Operator):
    """Invisible always-on modal operator. Never consumes input (always
    PASS_THROUGH) — it exists solely to see key presses, which is the one
    thing no handler exposes. Everything else (joins, cuts, merges, undo,
    applied transforms) is recognised from scene state or dedicated
    handlers, see achievements.py."""
    bl_idname = "achievement.watcher"
    bl_label = "Achievement Background Watcher"
    bl_options = {'INTERNAL'}

    _timer = None

    def modal(self, context, event):
        if not achievements.is_watcher_running():
            return self._stop(context)

        if event.type == 'TIMER':
            # Пульс: доводить, що копія жива. Без нього "живість" мірялась
            # натисканнями клавіш, і після 90 с тиші watcher вважався мертвим —
            # запускалась ДРУГА копія, далі третя, і кожна рахувала ті самі
            # натискання повторно.
            achievements.watcher_heartbeat()
        elif event.value == 'PRESS':
            achievements.watcher_key_event(event)

        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        if not achievements.watcher_instance_start():
            return {'CANCELLED'}   # інша копія вже працює
        wm = context.window_manager
        win = context.window or (wm.windows[0] if wm.windows else None)
        if win is None:
            achievements.watcher_instance_stop()
            return {'CANCELLED'}
        self._timer = wm.event_timer_add(1.0, window=win)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _stop(self, context):
        wm = context.window_manager
        if self._timer is not None:
            try:
                wm.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None
        achievements.watcher_instance_stop()
        return {'CANCELLED'}


def _launch_watcher():
    """Періодичний bpy.app.timers callback: тримає модальний watcher живим.

    invoke() модального оператора потребує готового UI-контексту (вікна),
    якого немає під час register() — тому старт відкладається на трохи
    пізніше через таймер, з повторною спробою, якщо контекст ще не готовий.
    """
    try:
        if not achievements.is_watcher_running():
            return None
        # Модальна копія може загинути не через _stop() — наприклад при
        # перезавантаженні файлу. Тому таймер не одноразовий: він періодично
        # перевіряє, чи копія жива, і за потреби піднімає нову.
        if achievements.watcher_needs_launch():
            # Запуск обов'язково у контексті вікна: у callback таймера
            # context.window буває None, і тоді modal_handler_add чіпляє
            # обробник у нікуди — клавіші до нього не доходять.
            wm = bpy.context.window_manager
            if wm.windows:
                with bpy.context.temp_override(window=wm.windows[0]):
                    bpy.ops.achievement.watcher('INVOKE_DEFAULT')
    except Exception:
        pass
    return 30.0


def _init_preset_sound_paths():
    """Одноразовий callback: підставляє шляхи бандлених звуків у поля пресетів.

    Робиться через таймер, а не в register(): на момент реєстрації
    AddonPreferences ще може бути недоступним, а писати у властивості
    під час draw() не можна.
    """
    try:
        sounds.ensure_preset_defaults(get_preferences())
    except Exception:
        return 0.5
    return None


def _tag_redraw_all():
    """Перемальовує панелі, що показують прогрес (сайдбар N + Preferences)."""
    try:
        for win in bpy.context.window_manager.windows:
            for area in win.screen.areas:
                if area.type in {'VIEW_3D', 'PREFERENCES'}:
                    area.tag_redraw()
    except Exception as _dbg_err:  # noqa: BLE001
        debug.log("__init__.py:_tag_redraw_all", _dbg_err)


# ----------------- UI Operators -----------------

class ACHIEVEMENT_OT_force_unlock(bpy.types.Operator):
    """Force unlock the specified achievement for testing."""
    bl_idname = "achievement.force_unlock"
    bl_label = "Force Unlock Achievement"
    bl_description = "Force unlock the achievement with the given ID"
    # INTERNAL прибирає оператор з пошуку по F3. Без нього будь-хто міг набрати
    # "Force Unlock Achievement" і видати собі що завгодно — цінність ачивок
    # тримається лише на тому, що їх не можна просто так собі виписати.
    # Оператор лишається доступним зі скриптів (bpy.ops.achievement.force_unlock)
    # для QA.
    bl_options = {'INTERNAL'}

    achievement_id: bpy.props.StringProperty(
        name="Achievement ID",
        default="GOODBYE_CUBE"
    )

    def execute(self, context):
        eng = engine.get_engine()
        if eng.unlock(self.achievement_id):
            self.report({'INFO'}, f"Unlocked: {self.achievement_id}")
        else:
            self.report({'INFO'}, f"Already unlocked: {self.achievement_id}")
        return {'FINISHED'}


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

    rare: bpy.props.BoolProperty(name="Rare Golden Glow", default=True)

    def execute(self, context):
        # sound_path не передаємо — звук візьметься зі схеми (пресет/профіль).
        if self.rare:
            toast.show(
                "Legendary Unlock",
                "You did something truly rare.",
                rare=True,
            )
        else:
            toast.show(
                "Winner",
                "Standard achievement unlocked.",
                rare=False,
            )
        return {'FINISHED'}


# ----------------- Profiles: data, list & operators -----------------

class ACHIEVEMENT_SoundProfile(bpy.types.PropertyGroup):
    """A user-defined profile: pop-up animation + four sound slots."""
    name: bpy.props.StringProperty(name="Profile Name", default="My Profile")

    animation_style: bpy.props.EnumProperty(
        name="Animation",
        items=(
            ('STEAM', "Steam", "Card rises from the bottom; multiple toasts stack"),
            ('XBOX', "Xbox", "Green circle expands into a banner; toasts play one by one"),
            ('PS', "PlayStation", "Card slides in from the right; toasts play one by one"),
        ),
        default='STEAM',
        description="Which pop-up animation this profile uses"
    )

    unlock_sound: bpy.props.StringProperty(
        name="Unlock", subtype='FILE_PATH', default="",
        description="Sound played when a normal achievement unlocks")
    unlock_volume: bpy.props.FloatProperty(
        name="Volume", default=1.0, min=0.0, max=1.0, subtype='FACTOR')

    rare_unlock_sound: bpy.props.StringProperty(
        name="Rare Unlock", subtype='FILE_PATH', default="",
        description="Sound played when a rare achievement unlocks")
    rare_unlock_volume: bpy.props.FloatProperty(
        name="Volume", default=1.0, min=0.0, max=1.0, subtype='FACTOR')

    end_sound: bpy.props.StringProperty(
        name="Notification End", subtype='FILE_PATH', default="",
        description="Sound played when a normal achievement notification starts fading out")
    end_volume: bpy.props.FloatProperty(
        name="Volume", default=1.0, min=0.0, max=1.0, subtype='FACTOR')

    rare_end_sound: bpy.props.StringProperty(
        name="Rare Notification End", subtype='FILE_PATH', default="",
        description="Sound played when a rare achievement notification starts fading out")
    rare_end_volume: bpy.props.FloatProperty(
        name="Volume", default=1.0, min=0.0, max=1.0, subtype='FACTOR')


class ACHIEVEMENT_UL_sound_profiles(bpy.types.UIList):
    """List of custom sound profiles."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.prop(item, "name", text="", emboss=False)
        else:
            layout.label(text="")


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


# Токен, яким у експортованому JSON позначається файл із папки assets/
# самого аддона. Абсолютні шляхи на іншій машині не існують, тож бандлені
# звуки записуються відносно addon-каталогу і розгортаються при імпорті.
_ASSET_TOKEN = "<assets>/"


def _pack_sound_path(raw: str) -> str:
    """Абсолютний шлях → портативний вигляд для експорту."""
    if not raw:
        return ""
    try:
        full = os.path.abspath(bpy.path.abspath(raw))
        assets = os.path.abspath(sounds.SOUND_DIR)
        if os.path.commonpath([full, assets]) == assets:
            return _ASSET_TOKEN + os.path.relpath(full, assets).replace(os.sep, "/")
    except (ValueError, OSError):
        pass
    return raw


def _unpack_sound_path(stored: str) -> str:
    """Портативний вигляд → шлях на цій машині."""
    if stored.startswith(_ASSET_TOKEN):
        rel = stored[len(_ASSET_TOKEN):].replace("/", os.sep)
        return os.path.join(sounds.SOUND_DIR, rel)
    return stored


DEFAULT_PROFILE_FILE = "Profile.json"


def _validated_json_path(raw: str):
    """Абсолютний шлях до .json або None, якщо ім'я файлу не задано.

    Файловий браузер Blender дозволяє підтвердити вибір із порожнім полем
    імені — тоді filepath це просто тека, і open() падає з Errno 2. Ловимо
    це тут і повертаємо зрозумілу помилку в UI замість трейсбеку в консолі.
    """
    if not raw:
        return None
    path = bpy.path.abspath(raw)
    if not os.path.basename(path) or os.path.isdir(path):
        return None
    if not path.lower().endswith(".json"):
        path += ".json"
    return path


def _profile_to_dict(p) -> dict:
    d = {"name": p.name, "animation_style": p.animation_style}
    for slot in sounds.SLOTS:
        d[f"{slot}_sound"] = _pack_sound_path(getattr(p, f"{slot}_sound", ""))
        d[f"{slot}_volume"] = getattr(p, f"{slot}_volume", 1.0)
    return d


def _dict_to_profile(prefs, d: dict):
    p = prefs.sound_profiles.add()
    p.name = str(d.get("name", "Imported Profile"))
    style = d.get("animation_style", "STEAM")
    if style in ('STEAM', 'XBOX', 'PS'):
        p.animation_style = style
    for slot in sounds.SLOTS:
        setattr(p, f"{slot}_sound",
                _unpack_sound_path(str(d.get(f"{slot}_sound", "") or "")))
        try:
            setattr(p, f"{slot}_volume", float(d.get(f"{slot}_volume", 1.0)))
        except (TypeError, ValueError):
            pass
    return p


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


def _draw_sound_slot(layout, prefs, slot, profile=None):
    """One slot cell: label, file picker, volume, play/stop toggle."""
    box = layout.box()
    header = box.row(align=True)
    header.label(text=sounds.SLOT_LABELS.get(slot, slot))
    playing = sounds.is_previewing(slot)
    op = header.operator("achievement.preview_sound", text="",
                         icon='SNAP_FACE' if playing else 'PLAY')
    op.slot = slot

    raw = sounds.raw_slot_path(slot, prefs, profile=profile)

    if profile is not None:
        box.prop(profile, f"{slot}_sound", text="")
        vol_owner, vol_attr = profile, f"{slot}_volume"
    else:
        preset = getattr(prefs, "sound_preset", 'STEAM')
        box.prop(prefs, sounds.preset_override_attr(preset, slot), text="")
        vol_owner, vol_attr = prefs, f"{slot}_volume"

    if sounds.is_missing(raw):
        warn = box.row()
        warn.alert = True
        warn.label(text="missing sound file, please check file path", icon='ERROR')

    box.prop(vol_owner, vol_attr, text="Volume", slider=True)


def _draw_sound_slots_grid(layout, prefs, profile=None):
    """Слоти сіткою 2x2: звичайні зверху, рідкісні знизу; unlock зліва,
    end справа."""
    for left, right in (("unlock", "end"), ("rare_unlock", "rare_end")):
        row = layout.row(align=True)
        _draw_sound_slot(row.column(align=True), prefs, left, profile=profile)
        _draw_sound_slot(row.column(align=True), prefs, right, profile=profile)


# ----------------- UI Preferences & Panel -----------------

_custom_icons = None


def get_custom_icons():
    global _custom_icons
    if _custom_icons is None:
        try:
            import bpy.utils.previews
            _custom_icons = bpy.utils.previews.new()
            for ach_id, ach_def in achievements.ACHIEVEMENTS.items():
                icon_path = engine._resolve_icon_path(ach_def)
                if icon_path and os.path.exists(icon_path):
                    try:
                        _custom_icons.load(ach_id, icon_path, 'IMAGE')
                    except Exception:
                        pass
        except Exception:
            _custom_icons = None
    return _custom_icons


def clear_custom_icons():
    global _custom_icons
    if _custom_icons is not None:
        try:
            import bpy.utils.previews
            bpy.utils.previews.remove(_custom_icons)
        except Exception:
            pass
        _custom_icons = None


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

    for ach_id, ach_def in achievements.ACHIEVEMENTS.items():
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

            prog = achievements.get_achievement_progress(ach_id)
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


class ACHIEVEMENT_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__ if __package__ else "achievements"

    enable_sound: bpy.props.BoolProperty(
        name="Play Notification Sound",
        default=True,
        description="Play audio chime when unlocking achievements"
    )
    enable_toast: bpy.props.BoolProperty(
        name="Show Viewport Notifications",
        default=True,
        description="Show custom GPU achievement notifications in 3D Viewport"
    )
    toast_duration: bpy.props.FloatProperty(
        name="Notification Duration (seconds)",
        default=8.0,
        min=4.0,
        max=20.0,
        description="Display duration for viewport achievement notifications"
    )

    # ---- Sound scheme ----
    sound_preset: bpy.props.EnumProperty(
        name="Sound Preset",
        items=sounds.PRESET_ITEMS,
        default='STEAM',
        description="Which set of achievement sounds to use"
    )
    master_volume: bpy.props.FloatProperty(
        name="Master Volume",
        default=1.0, min=0.0, max=1.0, subtype='FACTOR',
        description="Global volume applied on top of every individual sound volume"
    )
    unlock_volume: bpy.props.FloatProperty(
        name="Volume", default=1.0, min=0.0, max=1.0, subtype='FACTOR')
    rare_unlock_volume: bpy.props.FloatProperty(
        name="Volume", default=1.0, min=0.0, max=1.0, subtype='FACTOR')
    end_volume: bpy.props.FloatProperty(
        name="Volume", default=1.0, min=0.0, max=1.0, subtype='FACTOR')
    rare_end_volume: bpy.props.FloatProperty(
        name="Volume", default=1.0, min=0.0, max=1.0, subtype='FACTOR')

    # Власні файли звуку для вбудованих пресетів. Порожньо → бандлений файл
    # пресету. Кожен пресет тримає свій набір, щоб зміна звуку для Steam не
    # чіпала Xbox/PlayStation.
    _OVERRIDE_DESC = "Leave empty to use the bundled sound for this preset"
    steam_unlock_sound: bpy.props.StringProperty(
        name="Sound", subtype='FILE_PATH', default="", description=_OVERRIDE_DESC)
    steam_rare_unlock_sound: bpy.props.StringProperty(
        name="Sound", subtype='FILE_PATH', default="", description=_OVERRIDE_DESC)
    steam_end_sound: bpy.props.StringProperty(
        name="Sound", subtype='FILE_PATH', default="", description=_OVERRIDE_DESC)
    steam_rare_end_sound: bpy.props.StringProperty(
        name="Sound", subtype='FILE_PATH', default="", description=_OVERRIDE_DESC)

    xbox_unlock_sound: bpy.props.StringProperty(
        name="Sound", subtype='FILE_PATH', default="", description=_OVERRIDE_DESC)
    xbox_rare_unlock_sound: bpy.props.StringProperty(
        name="Sound", subtype='FILE_PATH', default="", description=_OVERRIDE_DESC)
    xbox_end_sound: bpy.props.StringProperty(
        name="Sound", subtype='FILE_PATH', default="", description=_OVERRIDE_DESC)
    xbox_rare_end_sound: bpy.props.StringProperty(
        name="Sound", subtype='FILE_PATH', default="", description=_OVERRIDE_DESC)

    ps_unlock_sound: bpy.props.StringProperty(
        name="Sound", subtype='FILE_PATH', default="", description=_OVERRIDE_DESC)
    ps_rare_unlock_sound: bpy.props.StringProperty(
        name="Sound", subtype='FILE_PATH', default="", description=_OVERRIDE_DESC)
    ps_end_sound: bpy.props.StringProperty(
        name="Sound", subtype='FILE_PATH', default="", description=_OVERRIDE_DESC)
    ps_rare_end_sound: bpy.props.StringProperty(
        name="Sound", subtype='FILE_PATH', default="", description=_OVERRIDE_DESC)

    sound_profiles: bpy.props.CollectionProperty(type=ACHIEVEMENT_SoundProfile)
    active_profile_index: bpy.props.IntProperty(name="Active Profile", default=0)
    show_rare_glow: bpy.props.BoolProperty(
        name="Rare Golden Glow Shader",
        default=True,
        description="Enable GLSL conic golden ray shader for rare achievements"
    )
    show_in_sidebar: bpy.props.BoolProperty(
        name="Show Achievements List in Sidebar (N-panel)",
        default=True,
        description="Display the full achievements list in the N-panel sidebar"
    )
    rounded_corners: bpy.props.BoolProperty(
        name="Rounded Card & Icon Corners",
        default=True,
        description="Round the corners of the notification card and its icon (Steam / PlayStation styles)"
    )
    enable_debug_logging: bpy.props.BoolProperty(
        name="Debug Logging",
        default=False,
        description="Print internal errors and tracebacks to the system console. "
                     "Off by default — the addon normally fails silently so a broken "
                     "achievement check never interrupts your work"
    )

    def draw(self, context):
        layout = self.layout

        # Notification & UI Settings Section
        box_settings = layout.box()
        box_settings.label(text="Settings:", icon='PREFERENCES')
        col_s = box_settings.column(align=True)
        col_s.prop(self, "enable_sound")
        col_s.prop(self, "enable_toast")
        col_s.prop(self, "toast_duration")
        style = toast._get_style()
        # Золоте сяйво не використовується в Xbox-анімації
        row_rg = col_s.row()
        row_rg.enabled = (style != 'XBOX')
        row_rg.prop(self, "show_rare_glow")
        # Закруглення стосується лише Steam-стилю картки
        row_rc = col_s.row()
        row_rc.enabled = (style == 'STEAM')
        row_rc.prop(self, "rounded_corners")
        col_s.prop(self, "show_in_sidebar")
        col_s.prop(self, "enable_debug_logging")

        # Profiles Section
        box_snd = layout.box()
        hdr = box_snd.row(align=True)
        hdr.label(text="Profiles:")
        io = hdr.row(align=True)
        io.alignment = 'RIGHT'
        io.operator("achievement.profiles_export", text="Export", icon='EXPORT')
        io.operator("achievement.profiles_import", text="Import", icon='IMPORT')

        row_p = box_snd.row(align=True)
        row_p.prop(self, "sound_preset", expand=True)
        box_snd.prop(self, "master_volume", slider=True)

        if not self.enable_sound:
            info = box_snd.row()
            info.enabled = False
            info.label(text="Sound is disabled above — enable it to hear these.", icon='INFO')

        if self.sound_preset == 'CUSTOM':
            row_l = box_snd.row()
            row_l.template_list("ACHIEVEMENT_UL_sound_profiles", "", self,
                                "sound_profiles", self, "active_profile_index", rows=3)
            col_b = row_l.column(align=True)
            col_b.operator("achievement.profile_add", text="", icon='ADD')
            col_b.operator("achievement.profile_remove", text="", icon='REMOVE')
            col_b.separator()
            col_b.operator("achievement.profile_duplicate", text="", icon='DUPLICATE')

            profile = sounds.get_active_profile(self)
            if profile is None:
                box_snd.label(text="Add a profile to define your own animation and sounds.", icon='INFO')
            else:
                anim = box_snd.box()
                anim.label(text="Pop-up Animation:", icon='SEQ_STRIP_DUPLICATE')
                anim.row().prop(profile, "animation_style", expand=True)
                _draw_sound_slots_grid(box_snd, self, profile=profile)
        else:
            _draw_sound_slots_grid(box_snd, self, profile=None)

        layout.separator()

        # Скидання прогресу живе тільки тут, а не в сайдбарі: дія незворотна,
        # і їй не місце за один промах миші від списку ачивок.
        box_data = layout.box()
        box_data.label(text="Progress Data:", icon='FILE_REFRESH')
        row_reset = box_data.row()
        row_reset.alert = True
        row_reset.operator("achievement.reset_progress", text="Reset All Progress", icon='TRASH')
        note = box_data.row()
        note.enabled = False
        note.label(text="Erases every unlocked achievement and all cumulative stats.", icon='ERROR')

        layout.separator()

        draw_achievements_list(layout, icon_scale=3.4375)


def get_preferences(context=None):
    if context is None:
        context = bpy.context
    try:
        prefs = getattr(context, "preferences", None)
        if prefs and hasattr(prefs, "addons"):
            addon_name = __package__ if __package__ else "achievements"
            if addon_name in prefs.addons:
                return prefs.addons[addon_name].preferences
    except Exception:
        pass
    return None


class ACHIEVEMENT_PT_panel(bpy.types.Panel):
    """Sidebar Panel for Blender Achievements."""
    bl_label = "Achievements"
    bl_idname = "ACHIEVEMENT_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Achievements"

    @classmethod
    def poll(cls, context):
        prefs = get_preferences(context)
        return getattr(prefs, "show_in_sidebar", True) if prefs is not None else True

    def draw(self, context):
        layout = self.layout
        draw_achievements_list(layout, icon_scale=3.4375, is_sidebar=True)


_classes = (
    # PropertyGroup та UIList мають бути зареєстровані ДО AddonPreferences,
    # яка на них посилається (CollectionProperty(type=...) / template_list).
    ACHIEVEMENT_SoundProfile,
    ACHIEVEMENT_UL_sound_profiles,
    ACHIEVEMENT_AddonPreferences,
    ACHIEVEMENT_OT_force_unlock,
    ACHIEVEMENT_OT_reset_progress,
    ACHIEVEMENT_OT_test_toast,
    ACHIEVEMENT_OT_profile_add,
    ACHIEVEMENT_OT_profile_remove,
    ACHIEVEMENT_OT_profile_duplicate,
    ACHIEVEMENT_OT_profiles_export,
    ACHIEVEMENT_OT_profiles_import,
    ACHIEVEMENT_OT_preview_sound,
    ACHIEVEMENT_OT_watcher,
    ACHIEVEMENT_PT_panel,
)


def register():
    for cls in _classes:
        if not hasattr(bpy.types, cls.__name__):
            try:
                bpy.utils.register_class(cls)
            except (ValueError, RuntimeError):
                pass

    # Initialize engine singleton
    engine.get_engine()

    # Register event tracking handlers safely
    achievements.register_listeners()

    # Запускаємо фоновий watcher трохи пізніше, коли UI-контекст буде готовий.
    # is_registered обов'язковий: швидкий цикл вимкнути/увімкнути аддон інакше
    # лишає кілька копій того самого таймера.
    for cb in (_launch_watcher, _init_preset_sound_paths):
        try:
            if bpy.app.timers.is_registered(cb):
                continue
        except AttributeError:
            pass
        try:
            bpy.app.timers.register(cb, first_interval=0.3)
        except (ValueError, RuntimeError):
            pass


def unregister():
    # Знімаємо власні таймери в парі до register(). _launch_watcher
    # самоліквідується лише на наступному тику (через 30 с), і весь цей час
    # тримає посилання на вивантажений модуль.
    for cb in (_launch_watcher, _init_preset_sound_paths):
        try:
            if bpy.app.timers.is_registered(cb):
                bpy.app.timers.unregister(cb)
        except (AttributeError, ValueError, RuntimeError):
            pass

    # Remove viewport draw handler if active
    toast.remove_handler()

    # Stop any playing achievement/preview sounds
    sounds.stop_all()

    # Unregister event tracking handlers
    achievements.unregister_listeners()

    # Clear custom preview icons
    clear_custom_icons()

    # Reset engine singleton
    engine.reset_engine()

    for cls in reversed(_classes):
        if hasattr(bpy.types, cls.__name__):
            try:
                bpy.utils.unregister_class(cls)
            except (ValueError, RuntimeError):
                pass


if __name__ == "__main__":
    register()


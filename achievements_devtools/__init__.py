"""
Achievements — Dev Tools

A companion add-on for testing "Achievements": unlock every achievement (or
just one) at once, wipe all progress, or turn on verbose console logging.
Deliberately kept separate from the main add-on so these destructive
shortcuts and developer-only switches never ship to end users.

Nothing here duplicates the main add-on's logic — it drives the very same
engine, so anything unlocked or reset from here behaves exactly as it would
during normal use. Debug logging works the same way in reverse: the main
add-on's `debug.log()` calls stay where they are, they just check back here
to see whether logging is turned on.
"""

import datetime
import importlib
import sys

import bpy

# The main add-on can live under different module paths depending on how it
# was installed: as a user-installed extension, from extensions.blender.org,
# or as a legacy add-on. Try the known ones, then fall back to scanning.
_KNOWN_PATHS = (
    "bl_ext.user_default.achievements",
    "bl_ext.blender_org.achievements",
    "achievements",
)


def main_addon():
    """The main Achievements module, or None if it is not enabled."""
    for path in _KNOWN_PATHS:
        mod = sys.modules.get(path)
        if mod is not None and hasattr(mod, "engine"):
            return mod
    for path in _KNOWN_PATHS:
        try:
            mod = importlib.import_module(path)
        except Exception:  # noqa: BLE001 — module simply is not installed
            continue
        if hasattr(mod, "engine"):
            return mod
    # Last resort: any loaded module that looks like it.
    for name, mod in list(sys.modules.items()):
        if name.rsplit(".", 1)[-1] == "achievements" and hasattr(mod, "engine"):
            return mod
    return None


class _SilentToasts:
    """Suppresses notification pop-ups for the duration of a bulk operation.

    Unlocking 79 achievements would otherwise queue 79 pop-ups and play 79
    sounds. The engine's unlock() path is still used in full, so persistence
    and counter checks behave normally — only the visual/audio side is muted.
    """

    def __init__(self, addon):
        self._toast = getattr(addon, "toast", None)
        self._saved = None

    def __enter__(self):
        if self._toast is not None:
            self._saved = self._toast.show
            self._toast.show = lambda *a, **kw: None
        return self

    def __exit__(self, *exc):
        if self._toast is not None and self._saved is not None:
            self._toast.show = self._saved
        return False


class ACHDEV_OT_unlock_all(bpy.types.Operator):
    """Unlock every achievement at once (no pop-ups)"""
    bl_idname = "achievements_dev.unlock_all"
    bl_label = "Unlock All Achievements"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return main_addon() is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        addon = main_addon()
        if addon is None:
            self.report({'ERROR'}, "Achievements is not enabled")
            return {'CANCELLED'}

        eng = addon.engine.get_engine()
        registry = addon.achievements.ACHIEVEMENTS
        stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        locked = [a for a in registry if not eng.is_unlocked(a)]
        if not locked:
            self.report({'INFO'}, "Everything is already unlocked")
            return {'CANCELLED'}

        with _SilentToasts(addon):
            # Written straight into the engine's table and persisted once,
            # rather than calling unlock() per achievement: that would do a
            # locked read-merge-write cycle 79 times over.
            for ach_id in locked:
                eng._unlocked[ach_id] = {"unlocked_at": stamp}
            eng._persist()

        self.report({'INFO'}, f"Unlocked {len(locked)} achievement(s)")
        _redraw()
        return {'FINISHED'}


class ACHDEV_OT_force_unlock(bpy.types.Operator):
    """Force unlock one specific achievement by ID, with its normal pop-up"""
    bl_idname = "achievements_dev.force_unlock"
    bl_label = "Force Unlock Achievement"
    bl_options = {'REGISTER'}

    achievement_id: bpy.props.StringProperty(
        name="Achievement ID",
        default="GOODBYE_CUBE",
        description="ID exactly as it appears in the achievements registry",
    )

    @classmethod
    def poll(cls, context):
        return main_addon() is not None

    def execute(self, context):
        addon = main_addon()
        if addon is None:
            self.report({'ERROR'}, "Achievements is not enabled")
            return {'CANCELLED'}

        # Goes through the normal unlock() path (not the silent bulk write
        # unlock_all uses), so the pop-up and sound play exactly as they
        # would for a real player — that's the point of testing one at a time.
        if addon.engine.get_engine().unlock(self.achievement_id):
            self.report({'INFO'}, f"Unlocked: {self.achievement_id}")
        else:
            self.report({'INFO'}, f"Already unlocked: {self.achievement_id}")
        _redraw()
        return {'FINISHED'}


class ACHDEV_OT_reset_all(bpy.types.Operator):
    """Wipe all achievement progress, including global counters"""
    bl_idname = "achievements_dev.reset_all"
    bl_label = "Reset All Achievements"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return main_addon() is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        addon = main_addon()
        if addon is None:
            self.report({'ERROR'}, "Achievements is not enabled")
            return {'CANCELLED'}
        addon.engine.get_engine().reset_all()
        self.report({'WARNING'}, "All achievement progress erased")
        _redraw()
        return {'FINISHED'}


def _redraw():
    """Refreshes sidebars/preferences so the lists reflect the new state."""
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type in {'VIEW_3D', 'PREFERENCES'}:
                    area.tag_redraw()
    except Exception:  # noqa: BLE001 — cosmetic only
        pass


def _devtools_prefs(context=None):
    if context is None:
        context = bpy.context
    try:
        addon_prefs = context.preferences.addons
        if __package__ in addon_prefs:
            return addon_prefs[__package__].preferences
    except Exception:  # noqa: BLE001
        pass
    return None


def _draw_buttons(layout, context):
    addon = main_addon()
    if addon is None:
        box = layout.box()
        box.label(text="Achievements is not enabled", icon='ERROR')
        return

    eng = addon.engine.get_engine()
    stats = eng.get_stats()
    layout.label(text=f"Unlocked: {stats['unlocked']}/{stats['total']}")

    col = layout.column(align=True)
    col.operator(ACHDEV_OT_unlock_all.bl_idname, icon='FUND')
    row = col.row(align=True)
    row.alert = True
    row.operator(ACHDEV_OT_reset_all.bl_idname, icon='TRASH')

    prefs = _devtools_prefs(context)
    if prefs is not None:
        layout.separator()
        row = layout.row(align=True)
        row.prop(prefs, "force_unlock_id", text="")
        row.operator(ACHDEV_OT_force_unlock.bl_idname, text="", icon='FUND').achievement_id = prefs.force_unlock_id


class ACHDEV_PT_panel(bpy.types.Panel):
    """Sits next to the achievement list in the sidebar."""
    bl_label = "Dev Tools"
    bl_idname = "ACHDEV_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Achievements"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        _draw_buttons(self.layout, context)


class ACHDEV_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    force_unlock_id: bpy.props.StringProperty(
        name="Achievement ID",
        default="GOODBYE_CUBE",
        description="ID exactly as it appears in the achievements registry",
    )
    enable_debug_logging: bpy.props.BoolProperty(
        name="Debug Logging",
        default=False,
        description="Print the main Achievements add-on's internal errors and "
                     "tracebacks to the system console. Off by default — the "
                     "main add-on normally fails silently so a broken "
                     "achievement check never interrupts your work"
    )

    def draw(self, context):
        layout = self.layout
        layout.label(
            text="Testing shortcuts for the Achievements add-on.",
            icon='INFO',
        )
        _draw_buttons(layout, context)
        layout.separator()

        box = layout.box()
        box.label(text="Debug", icon='CONSOLE')
        box.prop(self, "enable_debug_logging")

        layout.separator()
        note = layout.column()
        note.enabled = False
        note.label(text="The unlock/reset buttons also live in View3D sidebar "
                        "(N) > Achievements > Dev Tools.")


_classes = (
    ACHDEV_OT_unlock_all,
    ACHDEV_OT_force_unlock,
    ACHDEV_OT_reset_all,
    ACHDEV_AddonPreferences,
    ACHDEV_PT_panel,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass

"""
Small bpy-dependent helpers shared across the UI submodules: reaching the
add-on's own AddonPreferences instance, and redrawing the panels that show
live progress (N-panel + Preferences).
"""

import bpy

from .. import debug

# `__package__` here is "<addon module>.ui" — this file sits one level under
# the add-on's own root package (e.g. "achievements", or
# "bl_ext.user_default.achievements" for an installed extension). Strip the
# trailing ".ui" to recover that root: it's what Blender uses to key
# context.preferences.addons and what AddonPreferences.bl_idname must equal
# for Blender to associate the Preferences panel with this add-on.
ADDON_PACKAGE = __package__.rsplit(".", 1)[0] if __package__ else "achievements"


def get_preferences(context=None):
    if context is None:
        context = bpy.context
    try:
        prefs = getattr(context, "preferences", None)
        if prefs and hasattr(prefs, "addons"):
            if ADDON_PACKAGE in prefs.addons:
                return prefs.addons[ADDON_PACKAGE].preferences
    except Exception:
        pass
    return None


def _tag_redraw_all():
    """Перемальовує панелі, що показують прогрес (сайдбар N + Preferences)."""
    try:
        for win in bpy.context.window_manager.windows:
            for area in win.screen.areas:
                if area.type in {'VIEW_3D', 'PREFERENCES'}:
                    area.tag_redraw()
    except Exception as _dbg_err:  # noqa: BLE001
        debug.log("ui/helpers.py:_tag_redraw_all", _dbg_err)

"""
Optional debug-logging helper for Blender Achievements.

The addon deliberately swallows most internal exceptions (a failed viewport
draw or a missed achievement check must never crash Blender), but that meant
failures were completely invisible. `log()` is a no-op unless the user turns
on "Debug Logging" in the addon preferences, in which case it prints the
context message and full traceback to Blender's system console.
"""

import traceback

import bpy

_ADDON_PKG = __package__ or "achievements"


def is_enabled() -> bool:
    try:
        entry = bpy.context.preferences.addons.get(_ADDON_PKG)
        return bool(entry and getattr(entry.preferences, "enable_debug_logging", False))
    except Exception:  # noqa: BLE001
        return False


def log(context_msg: str, err: BaseException = None) -> None:
    """Prints a diagnostic line + traceback when debug logging is enabled.
    Safe to call from any handler/draw callback: never raises."""
    try:
        if not is_enabled():
            return
        if err is not None:
            print(f"[BlenderAchievement][DEBUG] {context_msg}: {err!r}")
            traceback.print_exc()
        else:
            print(f"[BlenderAchievement][DEBUG] {context_msg}")
    except Exception:  # noqa: BLE001
        pass

"""
register()/unregister() cleanliness, driven directly against real bpy.

This mirrors what Blender's real "toggle the addon checkbox" does: handler
counts back to baseline, timers unregistered, draw handle cleared, session
tracking state reset. Nothing here can be checked from tests/unit (needs
real bpy.app.handlers/bpy.app.timers), and it's exactly the kind of leak
this addon has had before (see the watcher-duplication comments in
achievements/__init__.py) — cheap to catch here, expensive to catch in
someone's actual Blender session.

Registered manually (register()/unregister() called straight from the
imported package) rather than through Blender's own extension-enable flow,
so `bpy.context.preferences.addons` never gets an entry for it and
AddonPreferences-dependent code sees `get_preferences() -> None`. That's
fine for lifecycle/detector testing — the codebase falls back to defaults
in that case — but preferences UI (draw()) isn't exercised here; see
tests/live for that.
"""

import bpy

import achievements as addon
from common import expect

HANDLER_LISTS = (
    "depsgraph_update_post", "load_post", "save_post", "render_init",
    "render_post", "render_complete", "render_cancel", "frame_change_post",
    "undo_post", "blend_import_post",
)


def _handler_counts():
    return {name: len(getattr(bpy.app.handlers, name)) for name in HANDLER_LISTS}


def _timer_state():
    ach = addon.achievements
    toast = addon.toast
    return {
        "achievement_timer": bpy.app.timers.is_registered(ach.achievement_timer_callback),
        "toast_tick": bpy.app.timers.is_registered(toast._tick),
    }


def test_single_register_unregister_leaves_no_trace():
    before_handlers = _handler_counts()
    before_timers = _timer_state()
    before_draw = addon.toast._draw_handle

    addon.register()
    addon.unregister()

    expect(_handler_counts() == before_handlers,
           f"handler counts changed: before={before_handlers} after={_handler_counts()}")
    expect(_timer_state() == before_timers,
           f"timers left registered: {_timer_state()}")
    expect(addon.toast._draw_handle == before_draw, "draw handle not cleared after unregister")


def test_repeated_cycles_do_not_accumulate_handlers():
    baseline = _handler_counts()
    for _ in range(10):
        addon.register()
        addon.unregister()
    expect(_handler_counts() == baseline,
           f"handler counts drifted over 10 cycles: baseline={baseline} now={_handler_counts()}")


def test_unregister_resets_session_tracking_state():
    addon.register()
    ach = addon.achievements
    # Simulate a session having actually run (a fresh session leaves this
    # None; a leaked value here means the next session would start from
    # stale "known objects" and misdetect adds/deletes).
    ach.state.known_objects = {"placeholder": {}}
    addon.unregister()
    expect(ach.state.known_objects is None,
           "state.known_objects survived unregister — next session would start from stale data")
    expect(ach.state.watcher_running is False, "watcher flag left set after unregister")


def tests():
    return [
        ("single register/unregister leaves handlers/timers/draw-handle untouched",
         test_single_register_unregister_leaves_no_trace),
        ("10x register/unregister cycles don't leak handlers",
         test_repeated_cycles_do_not_accumulate_handlers),
        ("unregister resets session tracking state",
         test_unregister_resets_session_tracking_state),
    ]

"""
toast.invalidate_textures() is what runs on_load_post when a .blend file is
opened while a toast is showing — it drops cached GPU textures/fonts and
resets each in-flight toast's icon so it reloads from its icon_path rather
than a dead datablock reference (see the function's own docstring in
toast.py for the crash history this fixes).

Deliberately NOT tested here: actually loading a different .blend file. This
MCP connection is almost certainly the tester's real, unsaved Blender
session — `bpy.ops.wm.open_mainfile()` / `read_homefile()` would discard
whatever they're working on, which is exactly the kind of action these
tests exist to avoid ever risking (see the module docstring in
tests/live/common.py). The full "open a new file mid-toast" path needs a
disposable Blender instance the tester explicitly points at for this
purpose — not something to automate against their main session. What's
tested instead is the state transition invalidate_textures() itself
performs, directly, on a toast manufactured for the test.
"""

from common import expect, force_prefs, muted_sounds


def test_invalidate_textures_resets_in_flight_toast_icon_state(addon):
    toast = addon.toast
    with muted_sounds(addon), force_prefs(addon, enable_toast=True, enable_sound=False):
        toast.remove_handler()
        toast.show("Live Test", "icon invalidation check", rare=False,
                    icon_path=None)  # icon_path=None is fine: only the state shape matters here
        expect(len(toast._pending) == 1, "setup: expected exactly 1 pending toast")

        item = toast._pending[0]
        # Simulate a toast that had already loaded GPU-side state before the
        # (simulated) file switch — what a real toast looks like mid-display.
        item['icon_tex'] = object()
        item['icon_done'] = True

        toast.invalidate_textures()

        expect(item['icon_tex'] is None,
               "invalidate_textures() left a stale GPU texture reference on an in-flight toast")
        expect(item['icon_done'] is False,
               "invalidate_textures() left icon_done=True — _ensure_icon_tex would skip "
               "reloading and the card would keep showing whatever was there before the switch")

        toast.remove_handler()


def test_invalidate_textures_does_not_raise_with_no_toasts_active(addon):
    toast = addon.toast
    toast.remove_handler()
    toast.invalidate_textures()  # must be a no-op, not an exception, on an empty queue


def tests(addon, testing):
    return [
        ("invalidate_textures() clears icon_tex/icon_done on an in-flight toast",
         lambda: test_invalidate_textures_resets_in_flight_toast_icon_state(addon)),
        ("invalidate_textures() is a no-op (not an exception) with nothing queued",
         lambda: test_invalidate_textures_does_not_raise_with_no_toasts_active(addon)),
    ]

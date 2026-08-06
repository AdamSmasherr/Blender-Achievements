"""
Toast pop-up lifecycle: real GPU draw handler (SpaceView3D.draw_handler_add),
real bpy.app.timers-driven animation tick, real bpy.data.images loaded for
the icon. None of this exists in `--background` mode — no GPU context, no
SpaceView3D to attach a draw handler to — see toast.py's own module
docstring for what actually gets drawn.

These check the queue/lifecycle state machine (pending -> active -> faded),
not pixel-perfect rendering. A screenshot taken via MCP alongside a manual
run is still the right way to eyeball the actual visuals; that's a "look at
it" step for a human, not something asserted here.

Every test here mutes sounds.play_slot (toast activation/fade normally
plays a real sound through the tester's speakers) and forces
enable_toast/enable_sound to known values for the duration, restoring the
tester's real preferences afterwards — see common.muted_sounds/force_prefs.
"""

from common import expect, force_prefs, muted_sounds


def test_show_queues_and_creates_draw_handle(addon):
    toast = addon.toast
    with muted_sounds(addon), force_prefs(addon, enable_toast=True, enable_sound=False):
        toast.remove_handler()  # guarantee a clean slate regardless of prior state

        toast.show("Live Test Achievement", "Shown via the live/MCP test layer", rare=False)
        expect(toast._draw_handle is not None, "show() did not create a viewport draw handler")
        expect(len(toast._pending) == 1, f"expected 1 queued toast, got {len(toast._pending)}")

        toast.remove_handler()
        expect(toast._draw_handle is None, "remove_handler() did not clear the draw handle")
        expect(not toast._pending and not toast._toasts, "remove_handler() did not clear the queues")


def test_disabled_preference_suppresses_show(addon):
    toast = addon.toast
    with muted_sounds(addon), force_prefs(addon, enable_toast=False):
        toast.remove_handler()
        toast.show("Should Not Appear", "enable_toast is forced off", rare=False)
        expect(not toast._pending and toast._draw_handle is None,
               "show() queued a toast / created a draw handler despite enable_toast=False")


def test_tick_promotes_pending_toast_to_active(addon):
    toast = addon.toast
    with muted_sounds(addon), force_prefs(addon, enable_toast=True, enable_sound=False):
        toast.remove_handler()
        toast.show("Live Test", "promotion check", rare=False)
        expect(len(toast._pending) == 1, "setup: expected exactly 1 pending toast")

        # _tick() is the bpy.app.timers callback show() itself registers;
        # calling it directly keeps the test independent of Blender's actual
        # timer cadence.
        toast._tick()
        expect(len(toast._toasts) == 1, "tick did not promote the pending toast to active")
        expect(len(toast._pending) == 0, "toast still counted as pending after promotion")

        toast.remove_handler()


def test_rare_flag_survives_the_queue(addon):
    toast = addon.toast
    with muted_sounds(addon), force_prefs(addon, enable_toast=True, enable_sound=False):
        toast.remove_handler()
        toast.show("Rare Live Test", "golden glow check", rare=True)
        expect(len(toast._pending) == 1, "setup: expected exactly 1 pending toast")
        expect(toast._pending[0]['rare'] is True, "rare=True did not propagate to the queued toast")
        toast.remove_handler()


def tests(addon, testing):
    return [
        ("show() queues a toast and creates a draw handler; remove_handler() clears both",
         lambda: test_show_queues_and_creates_draw_handle(addon)),
        ("enable_toast=False suppresses show() entirely",
         lambda: test_disabled_preference_suppresses_show(addon)),
        ("the animation tick promotes a pending toast to active",
         lambda: test_tick_promotes_pending_toast_to_active(addon)),
        ("a rare toast keeps its rare flag through the queue",
         lambda: test_rare_flag_survives_the_queue(addon)),
    ]

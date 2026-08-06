"""
The modal background watcher (ACHIEVEMENT_OT_watcher) needs a real window to
invoke() — that's the whole reason it lives in this layer instead of
tests/headless. This addon has already shipped a real bug from exactly this
corner: a duplicate modal copy double-counting every keypress when the
deferred launch timer raced a manually-started instance (see the heartbeat
comment above ACHIEVEMENT_OT_watcher.modal in achievements/__init__.py).

These tests run inside the tester's real, already-in-use Blender session,
which very likely already has a live modal watcher running from the addon's
own normal operation — not a blank slate. That constrains the design:

  - The pure instance-guard logic (watcher_instance_start/_stop,
    watcher_is_stale/needs_launch) is tested by saving the real flags,
    forcing them into a known state, checking the guard, then restoring the
    saved values exactly — it never touches whatever real modal copy might
    actually be alive.
  - The one thing that genuinely needs a live invoke() (proving it succeeds
    against a real window at all) only runs if no instance is already
    active: starting a *second* real modal copy on top of a live one would
    recreate the exact duplicate-watcher bug this suite exists to catch,
    rather than test it.
"""

import time

import bpy

from common import expect


def test_watcher_instance_guard_refuses_concurrent_start(addon):
    ach = addon.achievements
    saved_active, saved_heartbeat = ach._watcher_instance_active, ach._watcher_heartbeat
    try:
        ach._watcher_instance_active = False
        first = ach.watcher_instance_start()
        second = ach.watcher_instance_start()
        expect(first is True, "first watcher_instance_start() call should succeed from a clear flag")
        expect(second is False, "a concurrent second watcher_instance_start() was not refused")
    finally:
        ach._watcher_instance_active = saved_active
        ach._watcher_heartbeat = saved_heartbeat


def test_stale_instance_flag_allows_a_fresh_start(addon):
    """A modal copy that died without calling _stop() (e.g. its window
    closed) must not permanently block every future start — watcher_is_stale()
    is the heartbeat timeout that recovers from that."""
    ach = addon.achievements
    saved_active, saved_heartbeat = ach._watcher_instance_active, ach._watcher_heartbeat
    try:
        ach._watcher_instance_active = True
        ach._watcher_heartbeat = time.time() - 999  # long past _WATCHER_STALE_AFTER
        expect(ach.watcher_is_stale(), "a 999s-old heartbeat was not recognized as stale")
        expect(ach.watcher_instance_start() is True,
               "a stale instance flag blocked a fresh start instead of being recovered from")
    finally:
        ach._watcher_instance_active = saved_active
        ach._watcher_heartbeat = saved_heartbeat


def test_invoke_starts_a_real_modal_copy_when_none_is_active(addon):
    """The actual thing this test file exists for: proving invoke() can
    succeed at all against a real window, which --background doesn't have."""
    ach = addon.achievements
    if ach._watcher_instance_active and not ach.watcher_is_stale():
        print("    (skipped the live invoke() — a modal watcher is already running in this "
              "session; starting a second one on top of it is the exact bug being guarded "
              "against, not something to test by causing it)")
        return

    wm = bpy.context.window_manager
    expect(wm.windows, "no window available in this Blender session — live tests need a real window")

    running_before = ach.is_watcher_running()
    try:
        ach.start_watcher()
        with bpy.context.temp_override(window=wm.windows[0]):
            result = bpy.ops.achievement.watcher('INVOKE_DEFAULT')
        expect(result == {'RUNNING_MODAL'}, f"invoke() did not enter RUNNING_MODAL: {result}")
        expect(ach._watcher_instance_active, "instance flag not set after a successful invoke()")
        expect(ach.watcher_instance_start() is False,
               "a second concurrent instance was allowed to start against the live one just created")
    finally:
        # Tell the live modal copy to stop on its own next event tick, and
        # drop the instance flag immediately rather than waiting for that —
        # matches what unregister_listeners() does on a real disable.
        ach.stop_watcher()
        ach.watcher_instance_stop()
        if running_before:
            # Only restores the *flag*: the addon's own deferred launch timer
            # (30s cadence) will start a real instance from it naturally,
            # same as it would on a normal register(). No second invoke()
            # here — that's the race this test is specifically avoiding.
            ach.start_watcher()


def tests(addon, testing):
    return [
        ("watcher_instance_start() refuses a concurrent second start",
         lambda: test_watcher_instance_guard_refuses_concurrent_start(addon)),
        ("a stale (dead, un-cleaned-up) instance flag allows recovery",
         lambda: test_stale_instance_flag_allows_a_fresh_start(addon)),
        ("invoke() enters RUNNING_MODAL against a real window when no copy is active",
         lambda: test_invoke_starts_a_real_modal_copy_when_none_is_active(addon)),
    ]

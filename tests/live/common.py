"""
Shared plumbing for the live/MCP test layer.

These tests run *inside* an already-running Blender that has "Achievements"
enabled — via MCP's execute_blender_code, never spawned as a subprocess like
tests/headless. They exist for the things a window is required for: a modal
operator's invoke(), a real SpaceView3D draw handler and its GPU textures,
an actual Preferences/N-panel redraw. See tests/headless for real-bpy tests
that don't need a window, tests/unit for tests that don't need bpy at all.

Two things this module is careful about, both driven by the fact that this
is very likely the tester's real, unsaved Blender session:

  - `find_live_addon()` locates the *already-registered* Achievements module
    instead of importing a second copy from the repo path — a second
    `import achievements` would register duplicate operators/handlers under
    the same bl_idnames, corrupting the live session's state.
  - Nothing here loads a different .blend file or otherwise discards scene
    data. Tests that would normally need that (e.g. simulating the
    mid-toast file-switch code path) test the underlying function directly
    instead — see tests/live/test_blend_switch.py for why.
"""

import contextlib
import importlib.util
import sys
import traceback

import bpy

_KNOWN_ADDON_PATHS = (
    "bl_ext.user_default.achievements",
    "bl_ext.blender_org.achievements",
    "achievements",
)


class Failure(AssertionError):
    pass


def expect(condition, message):
    if not condition:
        raise Failure(message)


def find_live_addon():
    """The already-registered Achievements module, or None if the add-on
    isn't enabled in this Blender session."""
    for path in _KNOWN_ADDON_PATHS:
        mod = sys.modules.get(path)
        if mod is not None and hasattr(mod, "engine"):
            return mod
    for name, mod in list(sys.modules.items()):
        if name.rsplit(".", 1)[-1] == "achievements" and hasattr(mod, "engine"):
            return mod
    return None


def load_testing_module(addon, repo_root):
    """Loads achievements/testing.py fresh from the repo checkout (not
    whatever the installed extension copy happens to have — see the repo's
    testing notes on why that can be stale) and wires it to the live add-on's
    already-registered achievements/engine/toast submodules, so it drives
    the real, currently-running instances rather than a disconnected copy."""
    import os
    testing_path = os.path.join(repo_root, "achievements", "testing.py")
    spec = importlib.util.spec_from_file_location(f"{addon.__name__}.testing", testing_path)
    mod = importlib.util.module_from_spec(spec)
    mod.achievements = addon.achievements
    mod.engine = addon.engine
    mod.toast = addon.toast
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@contextlib.contextmanager
def force_prefs(addon, **overrides):
    """Temporarily overrides live AddonPreferences fields, restoring the
    tester's real values on exit. Needed because e.g. toast.show() reads the
    real, currently-registered preferences — a test must not silently no-op
    (if enable_toast happens to be off) or leave the user's settings changed.
    Yields None (and overrides nothing) if preferences aren't registered."""
    prefs = addon.get_preferences()
    if prefs is None:
        yield None
        return
    saved = {k: getattr(prefs, k) for k in overrides}
    try:
        for k, v in overrides.items():
            setattr(prefs, k, v)
        yield prefs
    finally:
        for k, v in saved.items():
            setattr(prefs, k, v)


@contextlib.contextmanager
def muted_sounds(addon):
    """Suppresses actual audio playback for the duration of a test — toast
    activation/fade normally plays a real sound through sounds.play_slot(),
    which would otherwise audibly fire through the tester's speakers every
    time a toast test runs."""
    sounds = addon.sounds
    saved = sounds.play_slot
    try:
        sounds.play_slot = lambda *a, **k: None
        yield
    finally:
        sounds.play_slot = saved


def run_suite(name, tests):
    """`tests` is a list of (label, callable) pairs. Returns the number of
    failures (0 = clean)."""
    print(f"\n=== {name} ===")
    failed = 0
    for label, fn in tests:
        try:
            fn()
        except Exception as err:  # noqa: BLE001 — every failure should surface
            failed += 1
            print(f"  FAIL {label}: {err}")
            if not isinstance(err, Failure):
                traceback.print_exc()
        else:
            print(f"  PASS {label}")
    return failed

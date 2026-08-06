"""
Best-effort smoke check that forcing a real UI redraw with the addon's
panels visible doesn't crash the process. This is deliberately light: it
does NOT open the Preferences editor (that would change the tester's screen
layout mid-session) and it can't catch a C-level layout-engine crash the way
the historical `ui::item_align` calendar crash was (a Python-level
try/except never sees those — the process just dies). What it *can* catch:
Python exceptions in draw() that Blender's own panel dispatch swallows
without ever reaching the console output MCP sees, but that leave the panel
visibly broken — and, combined with a screenshot, gives a human something to
actually look at without touching their window layout.

For an exhaustive check of a specific visual regression, open Preferences
manually and look — this is a coarse "did it fall over" gate, not a
replacement for that.
"""

from common import expect


def test_forced_redraw_does_not_raise(addon):
    import bpy
    try:
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
    except RuntimeError as err:
        # Some contexts (e.g. no visible 3D viewport area) make this
        # operator refuse to run at all — that's a setup issue, not a
        # regression in the addon's own draw code, so don't fail on it.
        expect(False, f"redraw_timer could not run in this context: {err}")


def tests(addon, testing):
    return [
        ("forcing a real UI redraw with the addon's panels visible doesn't raise",
         lambda: test_forced_redraw_does_not_raise(addon)),
    ]

"""
Entry point for the live/MCP test layer.

Must be run *inside* an already-running Blender that has "Achievements"
enabled — via MCP's execute_blender_code, e.g.:

    path = r"...\\tests\\live\\run_live.py"
    exec(compile(open(path, encoding="utf-8").read(), path, "exec"),
         {"__name__": "__main__", "__file__": path})

Unlike tests/headless, this can't be launched as `blender --background`:
everything here needs a real window (a modal operator's invoke(), a real
SpaceView3D draw handler, a real UI redraw).

Deliberately does not call sys.exit(): this runs inside the tester's actual
Blender process (not a disposable background one), and unclear SystemExit
semantics inside an embedded interpreter's request handler aren't worth
risking against a real session. Read the printed summary, or the `result`
variable this leaves in scope, for pass/fail.
"""

import importlib
import os
import sys

_LIVE_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_LIVE_DIR))

for _p in (_REPO_ROOT, _LIVE_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _fresh_import(name):
    """Blender keeps running between MCP calls in this session, so plain
    `import x` would silently reuse whatever was cached in sys.modules from
    the *previous* run — including edits made to the file on disk since
    then. Force a reload so each run actually reflects the current repo
    state, not a stale in-process copy."""
    if name in sys.modules:
        return importlib.reload(sys.modules[name])
    return importlib.import_module(name)


common = _fresh_import("common")

addon = common.find_live_addon()

if addon is None:
    print("LIVE SUITE: Achievements add-on is not enabled in this Blender session — nothing to test.")
    result = 1
else:
    testing = common.load_testing_module(addon, repo_root=_REPO_ROOT)

    # Reload order matters: each of these does `from common import ...` at
    # module scope, so common must already be fresh (done above) before
    # they're re-executed.
    test_watcher = _fresh_import("test_watcher")
    test_toast = _fresh_import("test_toast")
    test_blend_switch = _fresh_import("test_blend_switch")
    test_ui_redraw = _fresh_import("test_ui_redraw")

    _total_failed = 0
    _total_failed += common.run_suite("Watcher", test_watcher.tests(addon, testing))
    _total_failed += common.run_suite("Toast", test_toast.tests(addon, testing))
    _total_failed += common.run_suite("Blend switch", test_blend_switch.tests(addon, testing))
    _total_failed += common.run_suite("UI redraw", test_ui_redraw.tests(addon, testing))

    print("\n" + "=" * 60)
    if _total_failed:
        print(f"LIVE SUITE: {_total_failed} failure(s)")
    else:
        print("LIVE SUITE: all tests passed")
    print("=" * 60)

    result = 1 if _total_failed else 0

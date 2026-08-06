"""
Test-support helpers for Blender Achievements.

Nothing in register()/unregister() imports this module — it exists purely so
integration tests (headless `blender --background` runs, or a live Blender
driven through an MCP connection) can exercise the add-on without touching
the user's real progress file, popping up toasts, playing sounds, or leaving
stray objects in whatever scene happens to be open.

    from achievements.testing import sandbox, scene_guard, run_depsgraph_update

    with sandbox(tmp_path) as eng, scene_guard():
        bpy.ops.mesh.primitive_monkey_add()
        run_depsgraph_update()
        assert eng.is_unlocked("SUZANNES_BLESSING")
"""

import contextlib

import bpy

from . import handlers as _handlers
from .rules import probes as _probes
from .session import reset_tracking_state as _reset_tracking_state
from . import engine as _engine
from . import toast as _toast


@contextlib.contextmanager
def sandbox(state_path):
    """Isolates one test run's persisted state and notifications.

    - Progress reads/writes are redirected to `state_path` for the duration
      of the block (via `engine.using_filepath`), so a test can never read or
      corrupt the tester's real `blender_achievements.json`.
    - `toast.show` is replaced with a no-op, so unlocking achievements during
      a test doesn't queue pop-ups or play sounds.
    - Session tracking state (baseline, per-object caches, watcher flags) is
      reset before and after, so tests don't inherit leftover state from
      whatever was happening in the session before the test ran, and don't
      leave any behind for it afterwards.

    Yields the engine singleton. The real filepath, `toast.show`, and
    tracking state are restored on exit even if the test body raises.
    """
    eng = _engine.get_engine()
    real_show = _toast.show
    try:
        _toast.show = lambda *a, **kw: None
        with eng.using_filepath(state_path):
            eng._load_state()
            _reset_tracking_state()
            _probes.capture_baseline()
            _probes.ensure_snapshot()
            yield eng
    finally:
        _toast.show = real_show
        eng._load_state()
        _reset_tracking_state()


_GUARD_DEFAULT_COLLECTIONS = ("objects", "meshes", "materials", "node_groups")


@contextlib.contextmanager
def scene_guard(collections=_GUARD_DEFAULT_COLLECTIONS):
    """Removes any bpy.data entry left over in the given collections that
    wasn't there on entry. Defaults to the datablock types the addon's own
    detectors read most (objects, meshes, materials, node groups) — pass a
    narrower tuple to skip datablocks a particular test doesn't touch.

    Collections are cleaned in the order given, and the default order
    (objects first) matters: removing an object first drops its mesh/material
    users to zero, so their own removal afterwards doesn't need `do_unlink`
    to already have happened.
    """
    before = {name: set(getattr(bpy.data, name).keys()) for name in collections}
    try:
        yield
    finally:
        for name in collections:
            coll = getattr(bpy.data, name)
            for key in set(coll.keys()) - before[name]:
                item = coll.get(key)
                if item is None:
                    continue
                try:
                    coll.remove(item, do_unlink=True)
                except TypeError:
                    coll.remove(item)


def run_depsgraph_update():
    """Fires the add-on's depsgraph handler once, synchronously — the same
    call a real scene edit would trigger via Blender's own dispatch, without
    waiting for it."""
    _handlers.on_depsgraph_update(
        bpy.context.scene, bpy.context.evaluated_depsgraph_get()
    )

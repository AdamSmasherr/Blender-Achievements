"""
Minimal `bpy`/`blf`/`gpu` stand-ins so the addon's pure-logic modules can be
imported and unit-tested without a real Blender process.

Only covers what's touched at *import time* by achievements/*.py: base
classes for bpy.types.Operator/Panel/PropertyGroup/etc. (needs to be a real
type — a Mock can't be used as a class base), no-op bpy.props.*Property
callables, and bpy.app.handlers lists the @persistent-decorated callbacks
get appended to at module scope. Anything only touched inside a function
body (bpy.context, bpy.data, bpy.ops, gpu.*, blf.*, aud) is a permissive
MagicMock — fine for unit tests, which exercise pure helpers and never call
into real scene/GPU/audio state. Tests that need real bpy behavior belong in
tests/headless or tests/live, not here.
"""

import os
import sys
import types
from unittest.mock import MagicMock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _noop_property(*args, **kwargs):
    return None


def _install_bpy_stub():
    if getattr(sys.modules.get("bpy"), "__is_test_stub__", False):
        return

    bpy = types.ModuleType("bpy")
    bpy.__is_test_stub__ = True

    bpy_types = types.ModuleType("bpy.types")
    for name in ("Operator", "Panel", "PropertyGroup", "UIList",
                 "AddonPreferences", "Menu"):
        setattr(bpy_types, name, type(name, (), {}))
    bpy.types = bpy_types

    bpy_props = types.ModuleType("bpy.props")
    for name in ("StringProperty", "BoolProperty", "FloatProperty", "IntProperty",
                 "EnumProperty", "FloatVectorProperty", "CollectionProperty",
                 "PointerProperty"):
        setattr(bpy_props, name, _noop_property)
    bpy.props = bpy_props

    bpy_utils = types.ModuleType("bpy.utils")
    bpy_utils.user_resource = lambda *a, **k: "."
    bpy_utils.register_class = lambda cls: None
    bpy_utils.unregister_class = lambda cls: None
    bpy_utils.previews = MagicMock()
    bpy.utils = bpy_utils

    bpy_handlers = types.ModuleType("bpy.app.handlers")
    for name in ("depsgraph_update_post", "load_post", "save_post",
                 "render_init", "render_post", "render_complete", "render_cancel",
                 "frame_change_post", "undo_post", "blend_import_post"):
        setattr(bpy_handlers, name, [])
    bpy_handlers.persistent = lambda fn: fn

    bpy_timers = types.ModuleType("bpy.app.timers")
    bpy_timers.register = lambda *a, **k: None
    bpy_timers.unregister = lambda *a, **k: None
    bpy_timers.is_registered = lambda *a, **k: False

    bpy_app = types.ModuleType("bpy.app")
    bpy_app.handlers = bpy_handlers
    bpy_app.timers = bpy_timers
    bpy_app.background = True
    bpy_app.version_string = "0.0.0 (test stub)"
    bpy.app = bpy_app

    bpy.context = MagicMock()
    bpy.data = MagicMock()
    bpy.msgbus = MagicMock()
    bpy.path = MagicMock()
    bpy.path.abspath = lambda p: p
    bpy.ops = MagicMock()

    for key, mod in (
        ("bpy", bpy),
        ("bpy.types", bpy_types),
        ("bpy.props", bpy_props),
        ("bpy.utils", bpy_utils),
        ("bpy.app", bpy_app),
        ("bpy.app.handlers", bpy_handlers),
        ("bpy.app.timers", bpy_timers),
    ):
        sys.modules[key] = mod

    bpy_extras = types.ModuleType("bpy_extras")
    io_utils = types.ModuleType("bpy_extras.io_utils")
    io_utils.ExportHelper = type("ExportHelper", (), {})
    io_utils.ImportHelper = type("ImportHelper", (), {})
    bpy_extras.io_utils = io_utils
    sys.modules["bpy_extras"] = bpy_extras
    sys.modules["bpy_extras.io_utils"] = io_utils

    # GPU/text/audio: only ever called from inside functions in this addon,
    # never at module scope, so a permissive Mock is enough to satisfy the
    # `import blf` / `import gpu` / `from gpu_extras.batch import ...` lines.
    blf_mock = MagicMock(name="blf")
    sys.modules["blf"] = blf_mock

    gpu_mock = MagicMock(name="gpu")
    sys.modules["gpu"] = gpu_mock

    gpu_extras = types.ModuleType("gpu_extras")
    gpu_extras_batch = types.ModuleType("gpu_extras.batch")
    gpu_extras_batch.batch_for_shader = MagicMock(name="batch_for_shader")
    gpu_extras.batch = gpu_extras_batch
    sys.modules["gpu_extras"] = gpu_extras
    sys.modules["gpu_extras.batch"] = gpu_extras_batch


_install_bpy_stub()

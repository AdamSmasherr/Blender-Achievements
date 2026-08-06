"""
The context object every rule receives, plus the memoization that keeps a
declarative rule table from turning into N separate walks of `bpy.data`.

A `RuleContext` lives for exactly one evaluation pass (one depsgraph update,
one timer tick, one progress refresh). Anything derived from the scene goes
through `@probe`, which caches the result on that context — so ten rules can
each ask "how many polygons are in the scene?" and the scene is walked once,
the same property the old hand-fused `_compute_scene_progress()` loop had,
but without the rules having to know about each other.
"""

import functools

import bpy

from .. import debug
from ..session import state


class RuleContext:
    """One evaluation pass.

    `scene` and `depsgraph` are whatever the triggering event supplied; rules
    bound to triggers that don't carry them (TIMER, SAVE) must not assume
    they're there — `ctx.scene` falls back to `bpy.context.scene`.
    """

    __slots__ = ("eng", "_scene", "depsgraph", "state", "extra", "_memo")

    def __init__(self, eng, scene=None, depsgraph=None, **extra):
        self.eng = eng
        self._scene = scene
        self.depsgraph = depsgraph
        self.state = state
        # Per-trigger payload a rule may need: `changed_meshes` from the
        # operation detector, `elapsed` for render timing, and so on.
        self.extra = extra
        self._memo = {}

    @property
    def scene(self):
        if self._scene is not None:
            return self._scene
        return getattr(bpy.context, "scene", None)

    def cached(self, key, fn):
        """Computes `fn()` once per context, under `key`."""
        if key not in self._memo:
            self._memo[key] = fn()
        return self._memo[key]

    # --- baseline helpers -------------------------------------------------
    # Most session achievements must ignore whatever was already in the file
    # when the session started, or opening someone else's .blend would hand
    # out half the list on the first depsgraph tick.

    @property
    def baseline(self):
        return state.baseline

    def is_new(self, kind: str, name: str) -> bool:
        """True, якщо датаблок `name` створено цієї сесії (немає у baseline `kind`)."""
        if state.baseline is None:
            return False
        return name not in state.baseline.get(kind, ())

    def baseline_count(self, key: str, default: int = 0) -> int:
        if state.baseline is None:
            return default
        return state.baseline.get(key, default)

    def baseline_delta(self, current: int, key: str) -> int:
        """Приріст лічильника понад baseline сесії.

        Поки baseline не знято, повертає 0, а не `current`: інакше вміст
        щойно відкритого файлу зарахувався б як зроблене цієї сесії.
        """
        if state.baseline is None:
            return 0
        return max(0, current - state.baseline.get(key, 0))

    def unlocked(self, ach_id: str) -> bool:
        return self.eng.is_unlocked(ach_id)


def probe(fn):
    """Marks a scene-reading helper as memoized per `RuleContext`.

    Probes take the context as their first argument and are keyed by name and
    remaining arguments, so `polygon_total(ctx)` costs one scene walk per pass
    no matter how many rules ask for it.
    """
    @functools.wraps(fn)
    def wrapper(ctx, *args):
        key = (fn.__name__, args)
        if key not in ctx._memo:
            ctx._memo[key] = fn(ctx, *args)
        return ctx._memo[key]
    wrapper.__wrapped_probe__ = fn
    return wrapper


def guarded_probe(default):
    """`probe`, but a raising body yields `default` instead of killing the pass.

    Scene probes read whatever the user's file happens to contain, across
    several Blender versions — a missing attribute must cost one achievement
    check, not the whole tick.
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(ctx, *args):
            key = (fn.__name__, args)
            if key not in ctx._memo:
                ctx._memo[key] = debug.guarded_value(
                    f"rules.probes:{fn.__name__}", lambda: fn(ctx, *args), default)
            return ctx._memo[key]
        wrapper.__wrapped_probe__ = fn
        return wrapper
    return decorator

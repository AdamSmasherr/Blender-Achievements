"""
The rule engine: what turns the declarative table in `registry.py` into
unlocked achievements.

A rule is `(trigger, check, progress, target)` hanging off an
`AchievementDefinition`. Handlers do not know which achievements exist — they
fire a trigger with a `RuleContext` and this module walks the definitions
filed under it:

    ctx = RuleContext(eng, scene, depsgraph)
    rules.evaluate(registry.DEPSGRAPH, ctx)

Three things fall out of that, all of which used to be hand-maintained and
therefore drifted:

  * the "is everything in this group already unlocked?" short-circuit is just
    a per-definition `is_unlocked` skip;
  * the group membership sets (DEPSGRAPH_ACHIEVEMENT_IDS and friends) are the
    `trigger` field, so a check can no longer be written without being run;
  * progress values and unlock conditions come from the same function, so the
    panel can no longer show a number that has nothing to do with the unlock.

Rules that a state predicate genuinely cannot express — the ones recognised
from a *difference* between two depsgraph passes, like Ctrl+J or a knife cut —
are bound with `trigger=MANUAL` and unlocked by the detectors in
`operations.py`. They still declare `progress`, so the panel treats them like
everything else.
"""

import time
from typing import Optional, Tuple

from .. import debug
from ..registry import (ACHIEVEMENTS, COUNTER, DEPSGRAPH, FRAME_CHANGE, LOAD,
                        MANUAL, RENDER_COMPLETE, SAVE, TIMER, rules_for)
from ..session import state
from .context import RuleContext

__all__ = [
    "RuleContext", "evaluate", "get_achievement_progress", "refresh_progress",
    "DEPSGRAPH", "TIMER", "FRAME_CHANGE", "RENDER_COMPLETE", "SAVE", "LOAD",
    "COUNTER", "MANUAL",
]


def evaluate(trigger: str, ctx: RuleContext) -> list:
    """Runs every rule bound to `trigger` and unlocks the ones that pass.

    Returns the ids unlocked in this pass. A rule that raises is logged and
    skipped: one broken detector must never take out the rest of the tick.
    """
    unlocked = []
    now = time.monotonic()
    for d in rules_for(trigger):
        if ctx.eng.is_unlocked(d.id):
            continue
        if d.interval:
            # Heavy checks (full node-tree walks, n-gon scans) run at most
            # this often. The state they look for doesn't evaporate between
            # ticks, so a delayed check still catches it.
            #
            # "Never evaluated" is None, not 0.0: time.monotonic() counts from
            # boot on Linux, so on a machine that just started `now - 0.0` can
            # be smaller than the interval — and the rule would be skipped as
            # though it had just run.
            last = state.rule_last_eval.get(d.id)
            if last is not None and (now - last) < d.interval:
                continue
            state.rule_last_eval[d.id] = now
        passed = debug.guarded_value(f"rules:{d.id}", lambda d=d: d.evaluate(ctx), False)
        if passed:
            ctx.eng.unlock(d.id)
            unlocked.append(d.id)
    return unlocked


# --- Progress -------------------------------------------------------------

PROGRESS_CACHE_TTL = 1.0      # с; UI перемальовується десятки разів на секунду

# Важка (сканувальна) половина прогресу кешується окремо від дешевої. Панель
# перемальовується постійно, і раз на секунду ганяти обхід усіх об'єктів,
# матеріалів і нод-груп — це фонове навантаження поверх 5-секундного таймера й
# per-depsgraph сканів, причому на нерухомій сцені результат щоразу той самий.
# Тому скан крутиться лише коли depsgraph повідомив про зміну (або раз на
# PROGRESS_SCENE_TTL — для джерел поза depsgraph, як-от к-сть увімкнених аддонів).
PROGRESS_SCENE_TTL = 10.0     # с


def _collect(scan: bool) -> dict:
    """Progress values for every rule whose `scan` flag matches.

    One `RuleContext` per call, so rules sharing a probe (all the object-walk
    ones, for instance) share its single pass over the scene.
    """
    from ..engine import get_engine
    ctx = RuleContext(get_engine())
    out = {}
    for aid, d in ACHIEVEMENTS.items():
        if d.progress is None or bool(d.scan) != scan:
            continue
        value = debug.guarded_value(f"rules.progress:{aid}", lambda d=d: d.current(ctx), None)
        if value is not None:
            out[aid] = value
    return out


def refresh_progress() -> dict:
    """All progress values, cheap ones fresh and scanning ones from cache."""
    now_mono = time.monotonic()
    if state.progress_scene_dirty or (now_mono - state.progress_scene_time) >= PROGRESS_SCENE_TTL:
        state.progress_scene_cache = _collect(scan=True)
        state.progress_scene_time = now_mono
        state.progress_scene_dirty = False

    values = _collect(scan=False)
    values.update(state.progress_scene_cache)
    return values


def get_achievement_progress(ach_id: str) -> Optional[Tuple[int, int]]:
    """(поточне, ціль) для ачивки або None. Кешується на PROGRESS_CACHE_TTL,
    бо викликається для кожної ачивки на кожній перемальовці панелі."""
    d = ACHIEVEMENTS.get(ach_id)
    target = d.goal if d else 0
    if not target:
        return None

    now = time.monotonic()
    if not state.progress_cache or (now - state.progress_cache_time) >= PROGRESS_CACHE_TTL:
        state.progress_cache = debug.guarded_value(
            "rules:get_achievement_progress", refresh_progress, {})
        state.progress_cache_time = now

    curr = state.progress_cache.get(ach_id, 0)
    return (min(curr, target), target)


# Importing the rule modules is what binds every rule onto its definition;
# nothing else imports them, so this list is the registration order. Kept at
# the bottom so `RuleContext` and the trigger names above are already in place.
from . import basics          # noqa: E402,F401
from . import modeling        # noqa: E402,F401
from . import nodes           # noqa: E402,F401
from . import animation       # noqa: E402,F401
from . import rendering       # noqa: E402,F401
from . import workflow        # noqa: E402,F401
from . import milestones      # noqa: E402,F401
from . import operations      # noqa: E402,F401

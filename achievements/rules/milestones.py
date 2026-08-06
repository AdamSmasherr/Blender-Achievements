"""
Global (cumulative) milestones.

These need no per-achievement code: every one of them is "counter X reached
threshold N", and the counter already lives in the engine's persisted stats.
So the binding is a loop, and adding a new tier is a line in `registry.py`
plus whatever increments the stat — no rule to write, and no way to forget one.

The unlock itself is driven from `engine.add_stat()`, which checks the
achievements bound to the counter it just moved; the COUNTER trigger below
exists so the panel can read progress and so `unbound_ids()` doesn't report
these as unreachable.
"""

from ..registry import ACHIEVEMENTS, COUNTER, bind


def _counter_progress(counter_key: str):
    def read(ctx) -> int:
        return int(ctx.eng.get_stat(counter_key, 0))
    read.__name__ = f"stat_{counter_key}"
    return read


for _aid, _d in ACHIEVEMENTS.items():
    if _d.counter:
        bind(_aid, COUNTER, progress=_counter_progress(_d.counter), target=_d.threshold)

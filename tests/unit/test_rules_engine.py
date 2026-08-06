"""Unit tests for the declarative rule layer.

The point of moving check/progress/trigger onto `AchievementDefinition` was to
make two old failure modes impossible: a check that exists but is never run
(because nobody added its id to the right hand-written set), and a progress
bar counting something other than what unlocks the achievement. Both are
structural properties, so they're tested structurally here — plus the
behaviour of the engine that walks the table.
"""

import pytest

from achievements import registry
from achievements import rules
from achievements.registry import AchievementDefinition
from achievements.rules.context import RuleContext, probe


class FakeEngine:
    """Just enough engine for the rule loop: unlock bookkeeping and stats."""

    def __init__(self, stats=None):
        self.unlocked = set()
        self.stats = stats or {}

    def is_unlocked(self, ach_id):
        return ach_id in self.unlocked

    def unlock(self, ach_id):
        self.unlocked.add(ach_id)
        return True

    def get_stat(self, key, default=0):
        return self.stats.get(key, default)


@pytest.fixture
def ctx():
    return RuleContext(FakeEngine())


# --- Structural guarantees ------------------------------------------------

def test_every_achievement_is_reachable_from_some_trigger():
    """An achievement with no trigger can never unlock — the exact bug the
    old DEPSGRAPH_ACHIEVEMENT_IDS-style sets kept producing."""
    assert registry.unbound_ids() == []


def test_every_trigger_list_only_holds_definitions_declaring_that_trigger():
    for trigger in registry.TRIGGERS:
        for d in registry.rules_for(trigger):
            assert trigger in d.trigger, f"{d.id} filed under {trigger} without declaring it"


def test_progress_and_goal_come_as_a_pair():
    """A target with nothing to count, or a count with nothing to reach,
    means the panel shows a bar that can't move (or no bar for a rule that
    tracks progress)."""
    for aid, d in registry.ACHIEVEMENTS.items():
        assert bool(d.progress) == bool(d.goal), f"{aid}: progress/goal mismatch"


def test_cumulative_achievements_report_their_counter_as_progress():
    eng = FakeEngine({"launches": 42})
    ctx = RuleContext(eng)
    assert registry.ACHIEVEMENTS["LOYALTY_1"].current(ctx) == 42
    assert registry.ACHIEVEMENTS["LOYALTY_1"].goal == 100


# --- Definition.evaluate --------------------------------------------------

def test_numeric_rule_unlocks_when_progress_reaches_target(ctx):
    d = AchievementDefinition(id="X", title="X", description="",
                              progress=lambda c: 10, target=10)
    assert d.evaluate(ctx) is True
    d.target = 11
    assert d.evaluate(ctx) is False


def test_explicit_check_wins_over_the_numeric_rule(ctx):
    """Rules whose unlock condition is stricter than "the bar is full" —
    e.g. 25 add-ons *and* one enabled this session — keep both: the number
    for the panel, the predicate for the unlock."""
    d = AchievementDefinition(id="X", title="X", description="",
                              progress=lambda c: 99, target=10,
                              check=lambda c: False)
    assert d.evaluate(ctx) is False
    assert d.current(ctx) == 99


def test_rule_without_check_or_target_never_unlocks_itself(ctx):
    """MANUAL rules are unlocked by their detector, not by the loop."""
    d = AchievementDefinition(id="X", title="X", description="",
                              progress=lambda c: 1000)
    assert d.evaluate(ctx) is False


# --- evaluate() -----------------------------------------------------------

def _temp_rule(monkeypatch, trigger, **kwargs):
    """Registers a throwaway definition under `trigger` for one test."""
    d = AchievementDefinition(id="TEST_RULE", title="Test", description="", **kwargs)
    monkeypatch.setattr(registry, "rules_for", lambda t: [d] if t == trigger else [])
    monkeypatch.setattr(rules, "rules_for", lambda t: [d] if t == trigger else [])
    return d


def test_evaluate_unlocks_passing_rules_and_reports_them(monkeypatch, ctx):
    _temp_rule(monkeypatch, registry.TIMER, check=lambda c: True)
    assert rules.evaluate(registry.TIMER, ctx) == ["TEST_RULE"]
    assert ctx.eng.is_unlocked("TEST_RULE")


def test_evaluate_skips_already_unlocked_rules(monkeypatch, ctx):
    calls = []

    def _check(c):
        calls.append(1)
        return True

    _temp_rule(monkeypatch, registry.TIMER, check=_check)
    ctx.eng.unlock("TEST_RULE")
    assert rules.evaluate(registry.TIMER, ctx) == []
    assert calls == []


def test_a_raising_rule_does_not_take_out_the_rest_of_the_pass(monkeypatch, ctx):
    def _boom(c):
        raise RuntimeError("detector broke")

    good = AchievementDefinition(id="GOOD", title="G", description="",
                                 check=lambda c: True)
    bad = AchievementDefinition(id="BAD", title="B", description="", check=_boom)
    monkeypatch.setattr(rules, "rules_for", lambda t: [bad, good])

    assert rules.evaluate(registry.TIMER, ctx) == ["GOOD"]


def test_interval_rules_are_not_re_evaluated_before_their_interval_elapses(monkeypatch, ctx):
    """The first evaluation always runs, later ones inside the window don't.

    "First" has to mean "no recorded timestamp", not "timestamp is 0" —
    time.monotonic() counts from boot on Linux, so on a freshly booted
    machine a zero default reads as "evaluated just now" and the rule never
    runs at all. (Found by CI on a runner with under a minute of uptime.)
    """
    from achievements.session import state
    state.rule_last_eval.clear()
    calls = []
    _temp_rule(monkeypatch, registry.DEPSGRAPH, interval=60.0,
               check=lambda c: calls.append(1) or False)

    rules.evaluate(registry.DEPSGRAPH, ctx)
    rules.evaluate(registry.DEPSGRAPH, ctx)
    rules.evaluate(registry.DEPSGRAPH, ctx)

    assert len(calls) == 1, "an interval-limited rule ran more than once in its window"
    state.rule_last_eval.clear()


# --- RuleContext ----------------------------------------------------------

def test_probe_runs_once_per_context(ctx):
    calls = []

    @probe
    def counter(c):
        calls.append(1)
        return len(calls)

    assert counter(ctx) == 1
    assert counter(ctx) == 1          # memoized: same pass, same answer
    assert len(calls) == 1

    assert counter(RuleContext(FakeEngine())) == 2   # new pass, fresh read


def test_baseline_delta_is_zero_until_a_baseline_exists(ctx):
    from achievements.session import state
    prev = state.baseline
    try:
        state.baseline = None
        # Без baseline вміст щойно відкритого файлу не має рахуватись як
        # зроблене цієї сесії.
        assert ctx.baseline_delta(500, 'driver_count') == 0
        state.baseline = {'driver_count': 3}
        assert ctx.baseline_delta(5, 'driver_count') == 2
        assert ctx.baseline_delta(1, 'driver_count') == 0     # ніколи не від'ємна
    finally:
        state.baseline = prev


def test_is_new_treats_everything_as_pre_existing_without_a_baseline(ctx):
    from achievements.session import state
    prev = state.baseline
    try:
        state.baseline = None
        assert ctx.is_new('objects', "Cube") is False
        state.baseline = {'objects': {"Cube"}}
        assert ctx.is_new('objects', "Cube") is False
        assert ctx.is_new('objects', "Cube.001") is True
    finally:
        state.baseline = prev


# --- bind() ---------------------------------------------------------------

def test_bind_rejects_an_unknown_achievement_id():
    with pytest.raises(KeyError):
        registry.bind("NO_SUCH_ACHIEVEMENT", registry.TIMER, check=lambda c: True)


def test_bind_rejects_an_unknown_trigger():
    with pytest.raises(ValueError):
        registry.bind("GOODBYE_CUBE", "whenever", check=lambda c: True)

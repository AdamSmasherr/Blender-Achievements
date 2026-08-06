"""Unit tests for achievements/engine.py, backed by an in-memory fake
storage so nothing here touches a real config file.

`toast.show` is monkeypatched to a no-op: the real implementation reaches
into bpy.types.SpaceView3D, which the test-time bpy stub (tests/conftest.py)
deliberately doesn't provide — GPU/viewport drawing belongs to
tests/live, not unit tests.
"""

from datetime import date

import pytest

from achievements import engine as engine_mod
from achievements import toast as toast_mod
from achievements.achievements import AchievementDefinition


class FakeStorage:
    """In-memory stand-in for AchievementStorage: same load/save/reset
    surface, no merge semantics (that's covered directly in
    test_storage_merge.py against the real implementation) and no disk I/O.
    """

    def __init__(self):
        self.data = {"unlocked": {}, "stats": {}}
        self.save_count = 0

    def load_state(self):
        return {"unlocked": dict(self.data["unlocked"]), "stats": dict(self.data["stats"])}

    def save_state(self, data, force_keys=None):
        self.data = {
            "unlocked": dict(data.get("unlocked") or {}),
            "stats": dict(data.get("stats") or {}),
        }
        self.save_count += 1
        return True

    def reset_all(self):
        self.data = {"unlocked": {}, "stats": {}}
        return True


@pytest.fixture
def storage():
    return FakeStorage()


@pytest.fixture
def eng(monkeypatch, storage):
    monkeypatch.setattr(toast_mod, "show", lambda *a, **k: None)
    engine_mod.reset_engine()
    e = engine_mod.get_engine(storage)
    yield e
    engine_mod.reset_engine()


def test_unlock_persists_state_and_is_idempotent(eng, storage):
    assert not eng.is_unlocked("TEST_ACH")

    assert eng.unlock("TEST_ACH") is True
    assert eng.is_unlocked("TEST_ACH")
    assert eng.get_unlocked_at("TEST_ACH") != ""
    assert storage.save_count == 1

    # Already unlocked: no-op, no second persist.
    assert eng.unlock("TEST_ACH") is False
    assert storage.save_count == 1


def test_get_unlocked_at_empty_for_locked_achievement(eng):
    assert eng.get_unlocked_at("NEVER_UNLOCKED") == ""


def test_add_stat_accumulates_and_get_stat_defaults(eng):
    assert eng.get_stat("counter", default=0) == 0
    eng.add_stat("counter", 3)
    eng.add_stat("counter", 2)
    assert eng.get_stat("counter") == 5


def test_add_stat_negative_amount_is_forced_on_next_flush(eng, storage):
    eng.add_stat("k", 10)
    eng.flush_stats()
    assert storage.data["stats"]["k"] == 10

    eng.add_stat("k", -4)
    eng.flush_stats()
    assert eng.get_stat("k") == 6
    assert storage.data["stats"]["k"] == 6


def test_set_stat_max_only_grows(eng):
    eng.set_stat_max("best", 5)
    assert eng.get_stat("best") == 5
    eng.set_stat_max("best", 3)
    assert eng.get_stat("best") == 5
    eng.set_stat_max("best", 9)
    assert eng.get_stat("best") == 9


def test_add_stat_unlocks_bound_counter_achievement(monkeypatch, eng):
    fake_def = AchievementDefinition(
        id="COUNTER_ACH", title="T", description="D",
        counter="my_counter", threshold=3,
    )
    monkeypatch.setattr(engine_mod, "ACHIEVEMENTS", {"COUNTER_ACH": fake_def})

    eng.add_stat("my_counter", 2)
    assert not eng.is_unlocked("COUNTER_ACH")
    eng.add_stat("my_counter", 1)
    assert eng.is_unlocked("COUNTER_ACH")


def test_record_worked_seconds_updates_todays_day_entry(eng):
    eng.record_worked_seconds(120)
    today = date.today().isoformat()
    assert eng.get_days().get(today) == 120

    eng.record_worked_seconds(30)
    assert eng.get_days().get(today) == 150


def test_session_recap_zero_before_begin_session(eng):
    recap = eng.session_recap()
    assert recap == {
        "seconds": 0, "renders_total": 0, "saves_total": 0,
        "frames_total": 0, "polygons_total": 0, "unlocked": 0,
    }


def test_session_recap_tracks_deltas_after_begin_session(eng):
    eng.begin_session()
    eng.add_stat("renders_total", 3)
    eng.record_worked_seconds(30)
    eng.unlock("SOME_ACH")

    recap = eng.session_recap()
    assert recap["renders_total"] == 3
    assert recap["seconds"] == 30
    assert recap["unlocked"] == 1


def test_previous_session_reads_last_session_from_prior_process(storage, monkeypatch):
    monkeypatch.setattr(toast_mod, "show", lambda *a, **k: None)

    engine_mod.reset_engine()
    first = engine_mod.get_engine(storage)
    first.begin_session()
    first.add_stat("renders_total", 4)
    first.record_worked_seconds(60)
    first.flush_stats()  # a real process would do this in unregister_listeners()
    engine_mod.reset_engine()

    # A fresh process reading the same storage should see the previous
    # session's recap, not the empty default.
    second = engine_mod.get_engine(storage)
    prev = second.previous_session()
    assert prev is not None
    assert prev["renders_total"] == 4
    assert prev["seconds"] == 60

    engine_mod.reset_engine()


def test_reset_all_clears_unlocked_and_stats(eng):
    eng.unlock("TEST_ACH")
    eng.add_stat("k", 5)

    assert eng.reset_all() is True

    assert not eng.is_unlocked("TEST_ACH")
    assert eng.get_stat("k") == 0


def test_get_stats_percentage_matches_unlocked_ratio(eng):
    from achievements.achievements import ACHIEVEMENTS

    total = len(ACHIEVEMENTS)
    any_id = next(iter(ACHIEVEMENTS))
    eng.unlock(any_id)

    stats = eng.get_stats()
    assert stats["total"] == total
    assert stats["unlocked"] == 1
    assert stats["percentage"] == round(1 / total * 100.0, 1)

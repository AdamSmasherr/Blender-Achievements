"""Unit tests for the merge/migration logic in achievements/storage.py.

These exercise pure dict transformations only (AchievementStorage._merge is
a staticmethod, _migrate/_sanitize_day_map are module functions) — no file
I/O, no bpy calls.
"""

from achievements.storage import AchievementStorage, SCHEMA_VERSION, _migrate, _sanitize_day_map


def test_merge_unions_unlocked_achievements():
    disk = {"unlocked": {"A": {"unlocked_at": "t1"}}, "stats": {}}
    ours = {"unlocked": {"B": {"unlocked_at": "t2"}}, "stats": {}}
    merged = AchievementStorage._merge(disk, ours)
    assert set(merged["unlocked"]) == {"A", "B"}
    assert merged["version"] == SCHEMA_VERSION


def test_merge_takes_max_of_numeric_counters():
    disk = {"unlocked": {}, "stats": {"launches": 5}}
    ours = {"unlocked": {}, "stats": {"launches": 3}}
    merged = AchievementStorage._merge(disk, ours)
    assert merged["stats"]["launches"] == 5

    disk2 = {"unlocked": {}, "stats": {"launches": 2}}
    ours2 = {"unlocked": {}, "stats": {"launches": 9}}
    merged2 = AchievementStorage._merge(disk2, ours2)
    assert merged2["stats"]["launches"] == 9


def test_merge_days_map_is_unioned_and_maxed_per_day():
    disk = {"unlocked": {}, "stats": {"days": {"2026-01-01": 100}}}
    ours = {"unlocked": {}, "stats": {"days": {"2026-01-01": 50, "2026-01-02": 200}}}
    merged = AchievementStorage._merge(disk, ours)
    assert merged["stats"]["days"] == {"2026-01-01": 100, "2026-01-02": 200}


def test_merge_force_keys_overrides_max_with_ours():
    disk = {"unlocked": {}, "stats": {"k": 100}}
    ours = {"unlocked": {}, "stats": {"k": 40}}
    # Without force_keys, max() would keep 100 — this is the deliberate
    # rollback escape hatch, so `ours` must win instead.
    merged = AchievementStorage._merge(disk, ours, force_keys={"k"})
    assert merged["stats"]["k"] == 40


def test_merge_opaque_stat_is_last_writer_wins_not_maxed():
    disk = {"unlocked": {}, "stats": {"last_session": {"seconds": 999}}}
    ours = {"unlocked": {}, "stats": {"last_session": {"seconds": 5}}}
    merged = AchievementStorage._merge(disk, ours)
    assert merged["stats"]["last_session"] == {"seconds": 5}


def test_sanitize_day_map_drops_malformed_entries():
    dirty = {
        "2026-01-01": 100,      # valid
        "not-a-date": 50,       # dash not at position 4/7 -> dropped
        "2026-01-02": -5,       # negative -> dropped
        "2026-01-03": True,     # bool -> dropped (bool is a subclass of int)
        "2026-01-04": "oops",   # non-numeric -> dropped
        123: 10,                 # non-string key -> dropped
    }
    assert _sanitize_day_map(dirty) == {"2026-01-01": 100}


def test_sanitize_day_map_rejects_non_dict_input():
    assert _sanitize_day_map(None) == {}
    assert _sanitize_day_map([("2026-01-01", 100)]) == {}


def test_migrate_v1_to_v2_adds_empty_days_without_touching_other_stats():
    data = {"version": 1, "unlocked": {}, "stats": {"launches": 5}}
    migrated = _migrate(data, from_version=1)
    assert migrated["stats"]["days"] == {}
    assert migrated["stats"]["launches"] == 5


def test_migrate_is_noop_for_already_current_schema():
    data = {"version": 2, "unlocked": {}, "stats": {"days": {"2026-01-01": 10}}}
    migrated = _migrate(data, from_version=2)
    assert migrated["stats"]["days"] == {"2026-01-01": 10}

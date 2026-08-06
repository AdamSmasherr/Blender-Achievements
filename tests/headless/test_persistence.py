"""
Storage roundtrips against the real filesystem and real bpy — the part
tests/unit/test_storage_merge.py can't cover, since that only exercises the
in-memory merge logic directly. This checks the same guarantees end to end:
real file writes, real cross-process-style locking (msvcrt/fcntl), a second
AchievementStorage instance racing the first, and schema migration from a
hand-written v1 file.
"""

import json
import os
import tempfile

from achievements.storage import AchievementStorage, SCHEMA_VERSION
from common import expect


def _tmp_path(name):
    return os.path.join(tempfile.gettempdir(), f"ach_headless_{name}.json")


def test_fresh_file_has_documented_default_shape():
    path = _tmp_path("fresh")
    if os.path.exists(path):
        os.remove(path)
    state = AchievementStorage(filepath=path).load_state()
    expect(state == {"version": SCHEMA_VERSION, "unlocked": {}, "stats": {}},
           f"unexpected default shape: {state}")


def test_save_then_load_roundtrips_data():
    path = _tmp_path("roundtrip")
    if os.path.exists(path):
        os.remove(path)
    storage = AchievementStorage(filepath=path)
    ok = storage.save_state({"unlocked": {"A": {"unlocked_at": "t1"}}, "stats": {"launches": 3}})
    expect(ok, "save_state reported failure")

    reloaded = AchievementStorage(filepath=path).load_state()
    expect(reloaded["unlocked"] == {"A": {"unlocked_at": "t1"}}, "unlocked did not roundtrip")
    expect(reloaded["stats"]["launches"] == 3, "stats did not roundtrip")


def test_two_instances_merge_on_disk_instead_of_overwriting():
    """Simulates two Blender processes sharing one progress file: the second
    save (a lower counter, as if it loaded before the first one wrote) must
    not roll the on-disk counter backwards."""
    path = _tmp_path("merge")
    if os.path.exists(path):
        os.remove(path)

    a = AchievementStorage(filepath=path)
    b = AchievementStorage(filepath=path)

    expect(a.save_state({"unlocked": {"A": {"unlocked_at": "t1"}}, "stats": {"launches": 5}}),
           "a.save_state reported failure")
    ok = b.save_state({"unlocked": {"B": {"unlocked_at": "t2"}}, "stats": {"launches": 3}})
    expect(ok, "b.save_state reported failure")

    final = AchievementStorage(filepath=path).load_state()
    expect(set(final["unlocked"]) == {"A", "B"}, f"unlocked not unioned: {final['unlocked']}")
    expect(final["stats"]["launches"] == 5,
           f"lower-counter save rolled launches back: {final['stats']}")


def test_schema_v1_file_migrates_on_load():
    path = _tmp_path("migrate")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "unlocked": {}, "stats": {"launches": 7}}, f)

    state = AchievementStorage(filepath=path).load_state()
    expect(state["version"] == SCHEMA_VERSION, f"did not migrate to current schema: {state['version']}")
    expect(state["stats"].get("days") == {}, "migration did not add an empty 'days' map")
    expect(state["stats"]["launches"] == 7, "migration touched an unrelated stat")


def test_reset_all_wipes_file_without_merging_old_values_back():
    path = _tmp_path("reset")
    storage = AchievementStorage(filepath=path)
    storage.save_state({"unlocked": {"A": {"unlocked_at": "t1"}}, "stats": {"launches": 9}})

    ok = storage.reset_all()
    expect(ok, "reset_all reported failure")

    state = AchievementStorage(filepath=path).load_state()
    expect(state["unlocked"] == {}, "reset_all left unlocked achievements behind")
    expect(state["stats"] == {}, "reset_all left stats behind")


def tests():
    return [
        ("fresh storage file has the documented default shape",
         test_fresh_file_has_documented_default_shape),
        ("save_state -> load_state roundtrips unlocked + stats",
         test_save_then_load_roundtrips_data),
        ("two instances merge instead of overwriting on save",
         test_two_instances_merge_on_disk_instead_of_overwriting),
        ("a v1 file migrates to the current schema on load",
         test_schema_v1_file_migrates_on_load),
        ("reset_all wipes the file instead of merging old values back",
         test_reset_all_wipes_file_without_merging_old_values_back),
    ]

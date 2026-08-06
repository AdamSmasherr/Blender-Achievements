"""Unit tests for achievements.achievements.SessionState / reset_tracking_state.

Session tracking used to be ~50 separate module-level `global` variables.
They're now fields on a single `state` singleton instance
(`achievements.achievements.state`), and `reset_tracking_state()` restores
each of them to a clean default without needing any `global` declarations
(mutating attributes of a module-level object doesn't rebind the name)."""

import pytest

from achievements import achievements as ach


@pytest.fixture(autouse=True)
def _restore_state():
    """Every test gets a clean session state and leaves a clean one behind."""
    ach.reset_tracking_state()
    yield
    ach.reset_tracking_state()


def test_state_is_a_single_shared_singleton():
    assert ach.state is ach.state
    assert isinstance(ach.state, ach.SessionState)


def test_reset_tracking_state_clears_counters_set_by_record_helpers():
    ach.record_object_join(count=50)
    ach.record_knife_cut(3)
    ach.record_merge_by_distance(20)
    ach.record_graph_tweak(2)
    ach.record_transform_apply(4)
    ach.record_undo()
    ach.record_shortcut_used("x")

    assert ach.state.max_join_count == 50
    assert ach.state.knife_cut_count == 3
    assert ach.state.max_merge_count == 20
    assert ach.state.graph_tweaks == 2
    assert ach.state.applied_objects_count == 4
    assert ach.state.undo_timestamps
    assert ach.state.shortcut_timestamps

    ach.reset_tracking_state()

    assert ach.state.max_join_count == 0
    assert ach.state.knife_cut_count == 0
    assert ach.state.max_merge_count == 0
    assert ach.state.graph_tweaks == 0
    assert ach.state.applied_objects_count == 0
    assert ach.state.undo_timestamps == []
    assert ach.state.shortcut_timestamps == []


def test_reset_tracking_state_clears_baseline_and_scan_caches():
    ach.state.baseline = {"objects": {"Cube"}}
    ach.state.known_objects = {"Cube": {}}
    ach.state.op_mesh_counts = {"Cube": (8, 12)}
    ach.state.delta_last["polygons_total"] = 42
    ach.state.ngon_cache["Cube"] = (6, False)
    ach.state.progress_cache = {"SUZANNES_BLESSING": 1}

    ach.reset_tracking_state()

    assert ach.state.baseline is None
    assert ach.state.known_objects is None
    assert ach.state.op_mesh_counts == {}
    assert ach.state.delta_last == {}
    assert ach.state.ngon_cache == {}
    assert ach.state.progress_cache == {}


def test_reset_tracking_state_does_not_touch_watcher_lifecycle_flags():
    """watcher_running / watcher_heartbeat / cap_* / kf_buf / msgbus_owners
    track live OS-level resources (a running modal operator, a redirected
    stdout, a numpy buffer, msgbus subscriptions) that outlive a progress
    reset — reset_tracking_state() must not reach in and clear them."""
    ach.state.watcher_running = True
    ach.state.watcher_heartbeat = 123.0
    ach.state.cap_active = True
    ach.state.kf_buf = object()
    marker = object()
    ach.state.msgbus_owners.append(marker)

    ach.reset_tracking_state()

    assert ach.state.watcher_running is True
    assert ach.state.watcher_heartbeat == 123.0
    assert ach.state.cap_active is True
    assert ach.state.kf_buf is not None
    assert marker in ach.state.msgbus_owners

    # cleanup so the fixture's final reset doesn't leak a fake watcher flag
    ach.state.watcher_running = False
    ach.state.cap_active = False
    ach.state.kf_buf = None
    ach.state.msgbus_owners.clear()

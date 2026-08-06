"""
Compatibility facade for the achievement tracking framework.

The 2900-line module that used to live here has been split up:

    registry.py     — AchievementDefinition (id/title/… plus the declarative
                      rule fields trigger/check/progress/target) and the table
                      of every achievement
    session.py      — SessionState, the `state` singleton, reset_tracking_state
    rules/          — the rule engine (`evaluate`, progress) and the rules
                      themselves, one module per category, plus `operations.py`
                      for everything recognised from a diff between passes
    handlers.py     — Blender's callbacks, the 5-second timer, the keyboard
                      watcher, stdout capture, register/unregister

This module re-exports the names the rest of the addon (and the test suite,
`tools/`, and the Dev Tools addon) already import as
`achievements.achievements.*`, so the split didn't have to touch any of them.
New code should import from the module that owns the name instead.
"""

from .registry import ACHIEVEMENTS, AchievementDefinition  # noqa: F401
from .session import SessionState, reset_tracking_state, state  # noqa: F401

from .rules import get_achievement_progress  # noqa: F401
from .rules.operations import (  # noqa: F401
    is_normal_flip as _is_normal_flip,
    prune_caches as _prune_op_caches,
    record_bake,
    record_graph_tweak,
    record_knife_cut,
    record_merge_by_distance,
    record_normals_flipped,
    record_object_join,
    record_shortcut_used,
    record_transform_apply,
    record_undo,
    trigger_vram_error,
)
from .rules.probes import (  # noqa: F401
    capture_baseline as _capture_baseline,
    ensure_baseline as _ensure_baseline,
    ensure_snapshot,
    is_new as _is_new,
    snapshot_baseline as _snapshot_baseline,
    snapshot_objects,
)
from .rules.workflow import is_crash_recovery_file as _is_crash_recovery_file  # noqa: F401
from .handlers import (  # noqa: F401
    achievement_timer_callback,
    is_watcher_running,
    on_blend_import_post,
    on_depsgraph_update,
    on_frame_change_post,
    on_load_post,
    on_render_cancel,
    on_render_complete,
    on_render_init,
    on_render_post,
    on_save_post,
    on_undo_post,
    oom_capture_start,
    oom_capture_stop,
    register_listeners,
    register_msgbus_subscribers,
    start_watcher,
    stop_watcher,
    unregister_listeners,
    watcher_heartbeat,
    watcher_instance_start,
    watcher_instance_stop,
    watcher_is_stale,
    watcher_key_event,
    watcher_needs_launch,
)

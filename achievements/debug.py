"""
Optional debug-logging helper for Achievements.

The addon deliberately swallows most internal exceptions (a failed viewport
draw or a missed achievement check must never crash Blender), but that meant
failures were completely invisible. `log()` prints the context message and
full traceback to Blender's system console only when the companion
"Achievements — Dev Tools" addon is installed, enabled, and has its "Debug
Logging" preference turned on — there is no switch for this in the main
addon itself: debug tooling lives entirely in Dev Tools, so it never ships
in front of end users.

Independent of that: every call site is tracked, and a call site that keeps
failing prints one plain warning — regardless of Dev Tools state — after
`_WARN_THRESHOLD` occurrences. A detector that starts throwing on every tick
used to fail in complete silence unless someone thought to enable Dev Tools
and go looking for it; the only symptom was an achievement nobody could
explain never unlocking.
"""

import contextlib
import time
import traceback

import bpy

# Dev Tools can live under different module paths depending on how it was
# installed: as a user-installed extension, from extensions.blender.org, or
# as a legacy add-on. Try the known ones, then fall back to scanning.
_DEVTOOLS_PATHS = (
    "bl_ext.user_default.achievements_devtools",
    "bl_ext.blender_org.achievements_devtools",
    "achievements_devtools",
)

# is_enabled() used to re-walk context.preferences.addons on every single
# call — cheap once, but log() is called from hot draw/depsgraph paths, so
# with debug logging on that's dozens of identical lookups per frame for an
# answer that only changes when someone flips a checkbox in Preferences.
_ENABLED_CACHE_TTL = 3.0
_enabled_cache = None
_enabled_cache_time = 0.0


def _resolve_enabled() -> bool:
    try:
        addons = bpy.context.preferences.addons
        for path in _DEVTOOLS_PATHS:
            entry = addons.get(path)
            if entry is not None:
                return bool(getattr(entry.preferences, "enable_debug_logging", False))
        for name, entry in addons.items():
            if name.rsplit(".", 1)[-1] == "achievements_devtools":
                return bool(getattr(entry.preferences, "enable_debug_logging", False))
    except Exception:  # noqa: BLE001
        pass
    return False


def is_enabled() -> bool:
    global _enabled_cache, _enabled_cache_time
    now = time.monotonic()
    if _enabled_cache is None or (now - _enabled_cache_time) >= _ENABLED_CACHE_TTL:
        _enabled_cache = _resolve_enabled()
        _enabled_cache_time = now
    return _enabled_cache


# --- Per-call-site failure tracking ------------------------------------

_WARN_THRESHOLD = 20
_error_counts = {}
_warned_sites = set()


def _track_failure(context_msg: str) -> None:
    count = _error_counts.get(context_msg, 0) + 1
    _error_counts[context_msg] = count
    if count == _WARN_THRESHOLD and context_msg not in _warned_sites:
        _warned_sites.add(context_msg)
        print(f"[BlenderAchievement] Warning: '{context_msg}' has failed "
              f"{_WARN_THRESHOLD} times this session and may be silently "
              f"broken. Enable Achievements Dev Tools > Debug Logging for "
              f"full tracebacks.")


def reset_error_counts() -> None:
    """Clears per-call-site failure counters — called alongside
    reset_tracking_state() so a fresh session (or an explicit progress
    reset) doesn't inherit warnings already printed for a previous run."""
    _error_counts.clear()
    _warned_sites.clear()


def log(context_msg: str, err: BaseException = None) -> None:
    """Prints a diagnostic line + traceback when debug logging is enabled.
    Safe to call from any handler/draw callback: never raises.

    Failure tracking (and the threshold warning it can print) happens
    unconditionally, before the Dev Tools gate — that's the whole point:
    it's the one signal that reaches the console even when nobody has
    Dev Tools open.
    """
    try:
        if err is not None:
            _track_failure(context_msg)
        if not is_enabled():
            return
        if err is not None:
            print(f"[BlenderAchievement][DEBUG] {context_msg}: {err!r}")
            traceback.print_exc()
        else:
            print(f"[BlenderAchievement][DEBUG] {context_msg}")
    except Exception:  # noqa: BLE001
        pass


@contextlib.contextmanager
def guarded(context_msg: str):
    """Runs the block; on any exception, logs it via `log()` and swallows it.

    Replaces the addon's former copy-pasted

        try:
            ...
        except Exception as _dbg_err:
            debug.log("some.py:location", _dbg_err)
            pass

    with

        with debug.guarded("some.py:location"):
            ...

    Only fits call sites that swallow-and-continue on failure (the common
    case for detector code, which must never crash Blender). A call site
    that needs to return a fallback value on failure should use
    `guarded_value()` instead.
    """
    try:
        yield
    except Exception as err:  # noqa: BLE001
        log(context_msg, err)


def guarded_value(context_msg: str, fn, default=None):
    """Calls `fn()`, returning `default` and logging via `log()` if it raises.

    For the "return a fallback on failure" shape that `guarded()` can't
    express (a context manager can't inject a `return` into its caller).
    """
    try:
        return fn()
    except Exception as err:  # noqa: BLE001
        log(context_msg, err)
        return default

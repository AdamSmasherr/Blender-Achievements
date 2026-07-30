"""
Achievement persistence layer for Blender Achievements.
Handles saving and loading achievement unlock states to a JSON file.
"""

import contextlib
import itertools
import json
import os
import time
import bpy

from . import debug

try:
    import msvcrt
    _HAS_MSVCRT = True
except ImportError:
    _HAS_MSVCRT = False

try:
    import fcntl
    _HAS_FCNTL = True
except ImportError:
    _HAS_FCNTL = False


# Робить ім'я тимчасового файлу унікальним у межах процесу; разом з PID цього
# досить, щоб два екземпляри Blender не перетерли тимчасовий файл один одному.
_TMP_COUNTER = itertools.count()


@contextlib.contextmanager
def _file_lock(lock_fp, timeout=3.0):
    """Cross-process advisory lock so two Blender instances writing the same
    state file don't race each other. Best-effort: if the platform has
    neither msvcrt nor fcntl, or the lock can't be acquired within
    `timeout`, proceeds unlocked rather than hanging or failing the save.
    """
    if not (_HAS_MSVCRT or _HAS_FCNTL):
        yield
        return
    f = None
    locked = False
    try:
        f = open(lock_fp, "a+")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if _HAS_MSVCRT:
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except OSError:
                time.sleep(0.02)
        yield
    finally:
        if f is not None:
            if locked:
                try:
                    if _HAS_MSVCRT:
                        f.seek(0)
                        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
            f.close()


# Bumped whenever the on-disk schema changes (e.g. an achievement id is
# renamed, or the shape of a "stats" entry changes) in a way that needs a
# migration step. `_migrate()` below is the place to add per-version
# upgrade logic once that first happens.
SCHEMA_VERSION = 1


def _migrate(data: dict, from_version: int) -> dict:
    """Upgrades a loaded state dict from `from_version` to SCHEMA_VERSION.
    No-op today (schema 1 is the baseline); add `if from_version < N:` steps
    here as the schema evolves so old saved files keep working."""
    return data


class AchievementStorage:
    """Handles persistent storage of achievement states to JSON file."""

    def __init__(self, filepath=None):
        self._filepath = filepath

    @property
    def filepath(self) -> str:
        if self._filepath:
            return self._filepath
        config_dir = bpy.utils.user_resource('CONFIG')
        return os.path.join(config_dir, "blender_achievements.json")

    @property
    def _lock_filepath(self) -> str:
        return f"{self.filepath}.lock"

    def load_state(self) -> dict:
        """Loads state from JSON file. Returns dictionary with unlocked + stats data.

        Each top-level section is salvaged independently: a malformed
        `unlocked` section must not discard a valid `stats` section (or vice
        versa), otherwise a single corrupted field would wipe cumulative
        progress that has nothing to do with it.

        Files written before the "version" field existed are treated as
        schema version 0 and passed through `_migrate()`.
        """
        fp = self.filepath
        if not os.path.exists(fp):
            return {"version": SCHEMA_VERSION, "unlocked": {}, "stats": {}}
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {"version": SCHEMA_VERSION, "unlocked": {}, "stats": {}}
            unlocked = data.get("unlocked")
            stats = data.get("stats")
            from_version = data.get("version", 0)
            if not isinstance(from_version, int):
                from_version = 0
            result = {
                "version": from_version,
                "unlocked": unlocked if isinstance(unlocked, dict) else {},
                "stats": stats if isinstance(stats, dict) else {},
            }
            if from_version < SCHEMA_VERSION:
                result = _migrate(result, from_version)
                result["version"] = SCHEMA_VERSION
            return result
        except Exception as err:
            print(f"[BlenderAchievement] Error loading storage state: {err}")
            return {"version": SCHEMA_VERSION, "unlocked": {}, "stats": {}}

    @staticmethod
    def _merge(disk: dict, ours: dict) -> dict:
        """Combines on-disk state with our in-memory state instead of blindly
        overwriting, so a second Blender instance flushing later doesn't erase
        progress the first instance already persisted. `unlocked` entries are
        unioned (an achievement, once unlocked, stays unlocked); numeric
        `stats` counters take the max of the two sides, since they are
        cumulative/monotonic by design.
        """
        unlocked = dict(disk.get("unlocked") or {})
        unlocked.update(ours.get("unlocked") or {})

        stats = dict(disk.get("stats") or {})
        for k, v in (ours.get("stats") or {}).items():
            dv = stats.get(k)
            if isinstance(v, (int, float)) and isinstance(dv, (int, float)):
                stats[k] = max(v, dv)
            else:
                stats[k] = v
        return {"version": SCHEMA_VERSION, "unlocked": unlocked, "stats": stats}

    def save_state(self, data: dict) -> bool:
        """Merges with on-disk state under a cross-process lock, then saves
        atomically. Use this for normal incremental saves."""
        with _file_lock(self._lock_filepath):
            merged = self._merge(self.load_state(), data)
            return self._raw_save(merged)

    def _raw_save(self, data: dict) -> bool:
        """Writes `data` verbatim (no merge) with retry logic for transient
        lock contention on the final rename. Caller is responsible for
        holding `_file_lock` if merge-safety is needed."""
        fp = self.filepath
        temp_fp = None
        try:
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            temp_fp = f"{fp}.{os.getpid()}_{next(_TMP_COUNTER)}.tmp"
            with open(temp_fp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            max_retries = 5
            delay = 0.01
            for attempt in range(max_retries):
                try:
                    os.replace(temp_fp, fp)
                    return True
                except (PermissionError, OSError):
                    if attempt == max_retries - 1:
                        raise
                    time.sleep(delay)
                    delay *= 2
            return False
        except Exception as err:
            print(f"[BlenderAchievement] Error saving storage state: {err}")
            return False
        finally:
            if temp_fp and os.path.exists(temp_fp):
                try:
                    os.remove(temp_fp)
                except Exception as _dbg_err:
                    debug.log("storage.py:168", _dbg_err)
                    pass

    def reset_all(self) -> bool:
        """Resets all achievement data to default empty state.

        Bypasses the merge in save_state() on purpose: a reset must actually
        clear the file, not get unioned back to the old values.
        """
        with _file_lock(self._lock_filepath):
            return self._raw_save({"version": SCHEMA_VERSION, "unlocked": {}, "stats": {}})


_default_storage = AchievementStorage()


def load_state() -> dict:
    """Convenience module-level function to load state."""
    return _default_storage.load_state()


def save_state(data: dict) -> bool:
    """Convenience module-level function to save state."""
    return _default_storage.save_state(data)


def reset_all() -> bool:
    """Convenience module-level function to reset state."""
    return _default_storage.reset_all()

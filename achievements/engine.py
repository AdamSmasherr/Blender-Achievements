"""
Core achievement manager for Blender Achievements.
Coordinates persistence, event tracking, and viewport notifications.
"""

import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from .storage import AchievementStorage
from .achievements import ACHIEVEMENTS, AchievementDefinition
from . import toast
from . import debug

_ADDON_DIR = os.path.dirname(__file__)
# Legacy: залишено для сумісності. Звук тепер обирає система схем (sounds.py)
# за слотами unlock / rare_unlock / end / rare_end.
SOUND_PATH = os.path.join(_ADDON_DIR, "assets", "standart.wav")
ICON_DIR = os.path.join(_ADDON_DIR, "icons")


def _resolve_icon_path(ach_def) -> Optional[str]:
    """Returns the icon file for an achievement (icons/<icon or title>.png) or None."""
    if not ach_def:
        return None
    fname = getattr(ach_def, "icon", None) or f"{ach_def.title}.png"
    candidate = os.path.join(ICON_DIR, fname)
    return candidate if os.path.exists(candidate) else None


class AchievementEngine:
    """Singleton manager for achievement tracking, unlocking, and persistence."""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(AchievementEngine, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, storage: Optional[AchievementStorage] = None):
        if self._initialized:
            if storage is not None:
                self.storage = storage
            return
        self.storage = storage if storage is not None else AchievementStorage()
        self._unlocked: Dict[str, dict] = {}
        self._stats: Dict[str, Any] = {}       # persistent cumulative counters/dates
        self._stats_dirty = False
        self._load_state()
        self._initialized = True

    def _load_state(self):
        """Loads state from persistence layer."""
        data = self.storage.load_state()
        unlocked = data.get("unlocked", {}) if isinstance(data, dict) else {}
        self._unlocked = unlocked if isinstance(unlocked, dict) else {}
        stats = data.get("stats", {}) if isinstance(data, dict) else {}
        self._stats = stats if isinstance(stats, dict) else {}
        self._stats_dirty = False

    def _persist(self) -> bool:
        """Writes unlocked + stats to disk and clears the dirty flag."""
        ok = self.storage.save_state({"unlocked": self._unlocked, "stats": self._stats})
        self._stats_dirty = False
        return ok

    def load_state(self, filepath: Optional[str] = None):
        """Loads state from custom filepath if provided, or storage filepath."""
        if filepath:
            self.storage._filepath = filepath
        self._load_state()

    def save_state(self, filepath: Optional[str] = None) -> bool:
        """Saves current unlocked state to custom filepath if provided, or storage filepath."""
        if filepath:
            self.storage._filepath = filepath
        return self.storage.save_state({"unlocked": self._unlocked, "stats": self._stats})

    # ----------------- Persistent cumulative stats (global achievements) -----------------

    def get_stat(self, key: str, default=0):
        try:
            return self._stats.get(key, default)
        except Exception as _dbg_err:
            debug.log("engine.py:85", _dbg_err)
            return default

    def add_stat(self, key: str, amount: int = 1):
        """Increments a persistent counter (kept in RAM, flushed periodically) and
        checks any global achievements bound to that counter."""
        if not key or amount == 0:
            return
        try:
            self._stats[key] = int(self._stats.get(key, 0)) + amount
        except Exception as _dbg_err:
            debug.log("engine.py:95", _dbg_err)
            self._stats[key] = amount
        self._stats_dirty = True
        self._check_counter_achievements(key)

    def set_stat_max(self, key: str, value):
        """Stores value only if greater than the current stored value."""
        try:
            if value > self._stats.get(key, 0):
                self._stats[key] = value
                self._stats_dirty = True
                self._check_counter_achievements(key)
        except Exception as _dbg_err:
            debug.log("engine.py:107", _dbg_err)
            pass

    def flush_stats(self):
        """Persists dirty counters to disk (called periodically / on save / on unregister)."""
        if self._stats_dirty:
            self._persist()

    def _check_counter_achievements(self, counter_key: str):
        """Unlocks any global achievement whose counter has reached its threshold."""
        try:
            val = self._stats.get(counter_key, 0)
        except Exception as _dbg_err:
            debug.log("engine.py:119", _dbg_err)
            return
        for aid, d in ACHIEVEMENTS.items():
            if getattr(d, "counter", None) == counter_key and not self.is_unlocked(aid):
                if val >= getattr(d, "threshold", 0):
                    self.unlock(aid)

    def record_session_day(self):
        """Updates distinct-day count and consecutive-day streak; checks date achievements."""
        from datetime import date, timedelta
        today = date.today().isoformat()
        last = self._stats.get("last_day")
        if last == today:
            return
        self._stats["distinct_days"] = int(self._stats.get("distinct_days", 0)) + 1
        if last and last == (date.today() - timedelta(days=1)).isoformat():
            self._stats["streak"] = int(self._stats.get("streak", 0)) + 1
        else:
            self._stats["streak"] = 1
        self._stats["last_day"] = today
        self._stats_dirty = True
        self._check_counter_achievements("streak")
        self._check_counter_achievements("distinct_days")
        self._persist()

    def is_unlocked(self, ach_id: str) -> bool:
        """Returns True if the specified achievement is unlocked."""
        if not ach_id or not isinstance(ach_id, str):
            return False
        return isinstance(self._unlocked, dict) and ach_id in self._unlocked

    def unlock(self, ach_id: str) -> bool:
        """Unlocks an achievement if not already unlocked, saving state and triggering toast notification."""
        if not ach_id or not isinstance(ach_id, str):
            return False

        if self.is_unlocked(ach_id):
            return False

        ach_def = ACHIEVEMENTS.get(ach_id)
        if ach_def:
            title = ach_def.title
            desc = ach_def.description
            rare = ach_def.rare
        else:
            title = ach_id
            desc = "Achievement unlocked!"
            rare = False

        timestamp = datetime.now(timezone.utc).isoformat()
        if not isinstance(self._unlocked, dict):
            self._unlocked = {}
        self._unlocked[ach_id] = {
            "unlocked_at": timestamp,
        }

        # Save persistent state (unlocked + cumulative stats)
        saved = self._persist()
        if not saved:
            print(f"[BlenderAchievement] Warning: Failed to save achievement state for {ach_id}")

        # Trigger viewport toast notification.
        # sound_path не передаємо — звук обере система схем за слотом
        # (unlock / rare_unlock), відповідно до пресету/профілю користувача.
        icon_path = _resolve_icon_path(ach_def)
        toast.show(title, desc, rare=rare, icon_path=icon_path)

        print(f"[BlenderAchievement] Achievement unlocked: {ach_id} ('{title}')")
        return True

    def reset_all(self) -> bool:
        """Resets all achievement progress and event tracking state."""
        from .achievements import reset_tracking_state
        reset_tracking_state()
        self._unlocked.clear()
        self._stats.clear()
        self._stats_dirty = False
        res = self.storage.reset_all()
        print("[BlenderAchievement] All achievements reset.")
        return res

    def get_stats(self) -> Dict[str, Any]:
        """Returns statistics on achievement completion including category breakdown."""
        total = len(ACHIEVEMENTS)
        unlocked_count = sum(1 for ach_id in ACHIEVEMENTS if self.is_unlocked(ach_id))
        percentage = (unlocked_count / total * 100.0) if total > 0 else 0.0

        categories = {}
        for ach_id, ach_def in ACHIEVEMENTS.items():
            cat = ach_def.category
            if cat not in categories:
                categories[cat] = {"total": 0, "unlocked": 0, "percentage": 0.0}
            categories[cat]["total"] += 1
            if self.is_unlocked(ach_id):
                categories[cat]["unlocked"] += 1

        for cat, data in categories.items():
            t = data["total"]
            u = data["unlocked"]
            data["percentage"] = round((u / t * 100.0) if t > 0 else 0.0, 1)

        return {
            "total": total,
            "unlocked": unlocked_count,
            "percentage": round(percentage, 1),
            "categories": categories,
        }

    def get_category_stats(self, category: str) -> Dict[str, Any]:
        """Returns stats for a specific category."""
        stats = self.get_stats()
        return stats["categories"].get(category, {"total": 0, "unlocked": 0, "percentage": 0.0})

    def get_unlocked_ids(self) -> list:
        """Returns list of unlocked achievement IDs."""
        return [ach_id for ach_id in ACHIEVEMENTS if self.is_unlocked(ach_id)]


def get_engine(storage: Optional[AchievementStorage] = None) -> AchievementEngine:
    """Returns the singleton instance of AchievementEngine."""
    return AchievementEngine(storage)


def reset_engine():
    """Resets the AchievementEngine singleton instance to None."""
    AchievementEngine._instance = None

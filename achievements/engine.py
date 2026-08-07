"""
Core achievement manager for Blender Achievements.
Coordinates persistence, event tracking, and viewport notifications.
"""

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from .storage import AchievementStorage
from .registry import ACHIEVEMENTS, NO_ICON, AchievementDefinition
from . import toast
from . import debug

_ADDON_DIR = os.path.dirname(__file__)
# Legacy: залишено для сумісності. Звук тепер обирає система схем (sounds.py)
# за слотами unlock / rare_unlock / end / rare_end.
SOUND_PATH = os.path.join(_ADDON_DIR, "assets", "standart.wav")
ICON_DIR = os.path.join(_ADDON_DIR, "icons")


# Іконки лежать як "<stem>_.webp" — webp заради розміру (весь набір важить
# менше, ніж раніше десяток png) і заради прозорості: фон і відтінок картинки
# малює код, а не сам файл. Підкреслення в кінці — частина імен, з якими
# експортувався набір; тримаємо конвенцію в одному місці, а не в 79 полях.
ICON_SUFFIX = "_.webp"


def _resolve_icon_path(ach_def) -> Optional[str]:
    """Шлях до картинки ачивки (icons/<stem>_.webp), або None.

    None означає «малюємо без картинки»: або її свідомо немає
    (`icon=registry.NO_ICON`), або файл не знайшовся.
    """
    if not ach_def:
        return None
    stem = getattr(ach_def, "icon", None)
    if stem == NO_ICON:
        return None
    candidate = os.path.join(ICON_DIR, f"{stem or ach_def.title}{ICON_SUFFIX}")
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
        self._previous_session: Optional[dict] = None
        self._session_snapshot: Optional[dict] = None
        self._session_seconds = 0
        # Ключі, зменшені навмисно (відкат Delete+Undo). Storage._merge бере
        # max() з диском, тож без цього списку зменшення не переживе флаш.
        self._stats_forced: set = set()
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
        self._stats_forced = set()
        # Прочитати підсумок минулої сесії ТРЕБА тут, до першого запису: далі
        # той самий ключ переписується цифрами поточної сесії.
        prev = self._stats.get("last_session")
        self._previous_session = dict(prev) if isinstance(prev, dict) else None
        self._session_snapshot = None
        self._session_seconds = 0

    def _persist(self) -> bool:
        """Writes unlocked + stats to disk and clears the dirty flag."""
        forced = set(self._stats_forced)
        ok = self.storage.save_state(
            {"unlocked": self._unlocked, "stats": self._stats}, force_keys=forced
        )
        self._stats_dirty = False
        if ok:
            # Зменшення доїхало на диск — далі знову працює звичайний max().
            self._stats_forced -= forced
        return ok

    @contextmanager
    def _using_filepath(self, filepath: str):
        """Тимчасово перемикає storage на інший файл і ГАРАНТОВАНО повертає назад.

        Раніше `filepath` писався в `storage._filepath` назавжди: один разовий
        експорт мовчки перенаправляв туди всі подальші записи, і решта сесії
        зберігалась повз основний файл прогресу.
        """
        prev = self.storage._filepath
        self.storage._filepath = filepath
        try:
            yield
        finally:
            self.storage._filepath = prev

    # Публічне ім'я для зовнішнього коду (test-support helpers тощо), яким не
    # місце читати приватний storage._filepath напряму.
    using_filepath = _using_filepath

    def load_state(self, filepath: Optional[str] = None):
        """Loads state from custom filepath if provided, or storage filepath.
        A custom filepath applies to this call only."""
        if not filepath:
            self._load_state()
            return
        with self._using_filepath(filepath):
            self._load_state()

    def save_state(self, filepath: Optional[str] = None) -> bool:
        """Saves current unlocked state to custom filepath if provided, or storage
        filepath. A custom filepath applies to this call only."""
        if not filepath:
            return self._persist()
        # Експорт не має вважатись «збереженням» основного стану: _persist()
        # чистить прапорці незбережених змін, і після експорту вони б не
        # доїхали до справжнього файлу прогресу.
        dirty = self._stats_dirty
        forced = set(self._stats_forced)
        try:
            with self._using_filepath(filepath):
                return self._persist()
        finally:
            self._stats_dirty = dirty
            self._stats_forced = forced

    # ----------------- Persistent cumulative stats (global achievements) -----------------

    def get_stat(self, key: str, default=0):
        return debug.guarded_value("engine.py:get_stat", lambda: self._stats.get(key, default), default)

    def add_stat(self, key: str, amount: int = 1):
        """Increments a persistent counter (kept in RAM, flushed periodically) and
        checks any global achievements bound to that counter."""
        if not key or amount == 0:
            return
        self._stats[key] = debug.guarded_value(
            "engine.py:add_stat", lambda: int(self._stats.get(key, 0)) + amount, amount
        )
        if amount < 0:
            # Навмисне зменшення має перебити більше значення на диску.
            self._stats_forced.add(key)
        self._stats_dirty = True
        self._check_counter_achievements(key)

    def set_stat_max(self, key: str, value):
        """Stores value only if greater than the current stored value."""
        with debug.guarded("engine.py:set_stat_max"):
            if value > self._stats.get(key, 0):
                self._stats[key] = value
                self._stats_dirty = True
                self._check_counter_achievements(key)

    def flush_stats(self):
        """Persists dirty counters to disk (called periodically / on save / on unregister)."""
        if self._stats_dirty:
            self._persist()

    def _check_counter_achievements(self, counter_key: str):
        """Unlocks any global achievement whose counter has reached its threshold."""
        val = debug.guarded_value(
            "engine.py:_check_counter_achievements", lambda: self._stats.get(counter_key, 0), None
        )
        if val is None:
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

    # ----------------- Per-day journal & session recap -----------------

    # Лічильники, дельту яких за сесію показує підсумок.
    SESSION_COUNTERS = ("renders_total", "saves_total", "frames_total", "polygons_total")

    @staticmethod
    def _num(value) -> int:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return 0
        return int(value)

    @staticmethod
    def _today() -> str:
        from datetime import date
        return date.today().isoformat()

    def get_days(self) -> Dict[str, int]:
        """Журнал `"YYYY-MM-DD" -> секунди роботи`. Порожній словник, якщо
        його ще немає (свіже встановлення або щойно мігрований файл)."""
        days = self._stats.get("days")
        return days if isinstance(days, dict) else {}

    def add_day_seconds(self, seconds: int):
        """Доливає відпрацьований час у сьогоднішній запис журналу.

        Свідомо не залежить від жодної ачивки. `uptime_seconds` перестає
        рахуватись, щойно відкрито UNEMPLOYED_3 — для ачивки це розумна
        економія, але календар після цього застигав би назавжди.
        """
        if seconds <= 0:
            return
        with debug.guarded("engine.py:add_day_seconds"):
            days = self._stats.get("days")
            if not isinstance(days, dict):
                days = {}
                self._stats["days"] = days
            today = self._today()
            days[today] = self._num(days.get(today)) + int(seconds)
            self._stats_dirty = True

    def begin_session(self):
        """Знімає зріз лічильників, щоб підсумок міг показувати дельти.

        Сесія — це процес Blender, а не файл: перемикання .blend нічого не
        завершує. Значення минулої сесії вже підняті в пам'ять у _load_state.
        """
        snap = {k: self._num(self._stats.get(k)) for k in self.SESSION_COUNTERS}
        snap["unlocked"] = len(self._unlocked) if isinstance(self._unlocked, dict) else 0
        self._session_snapshot = snap
        self._session_seconds = 0
        self._stats["last_session"] = self.session_recap()
        self._stats_dirty = True

    def record_worked_seconds(self, seconds: int):
        """Один тік відпрацьованого часу: годує і журнал днів, і підсумок.

        Підсумок поточної сесії осідає в `stats["last_session"]` при кожному
        тіку саме тому, що зловити момент виходу з Blender неможливо — API не
        має хука на закриття. Наступний запуск просто читає те, що встигло
        лягти на диск, і показує його як «минулу сесію».
        """
        if seconds <= 0:
            return
        self.add_day_seconds(seconds)
        self._session_seconds += int(seconds)
        if self._session_snapshot is not None:
            self._stats["last_session"] = self.session_recap()
        self._stats_dirty = True

    def session_recap(self) -> Dict[str, int]:
        """Скільки зроблено від початку цієї сесії. Усі нулі, поки сесія не
        почалась — краще за від'ємні або гігантські дельти від порожнього зрізу."""
        snap = self._session_snapshot
        recap = {"seconds": int(self._session_seconds) if snap is not None else 0}
        for k in self.SESSION_COUNTERS:
            if snap is None:
                recap[k] = 0
            else:
                recap[k] = max(0, self._num(self._stats.get(k)) - self._num(snap.get(k)))
        if snap is None:
            recap["unlocked"] = 0
        else:
            cur = len(self._unlocked) if isinstance(self._unlocked, dict) else 0
            recap["unlocked"] = max(0, cur - self._num(snap.get("unlocked")))
        return recap

    def previous_session(self) -> Optional[Dict[str, int]]:
        """Підсумок попереднього запуску Blender, або None якщо його немає."""
        return self._previous_session

    def is_unlocked(self, ach_id: str) -> bool:
        """Returns True if the specified achievement is unlocked."""
        if not ach_id or not isinstance(ach_id, str):
            return False
        return isinstance(self._unlocked, dict) and ach_id in self._unlocked

    def get_unlocked_at(self, ach_id: str) -> str:
        """ISO-час розблокування ачивки, або "" якщо вона ще закрита.

        Публічна заміна прямому читанню `engine._unlocked` з UI: формат запису
        (сьогодні — dict з "unlocked_at") лишається деталлю реалізації.
        """
        if not isinstance(self._unlocked, dict):
            return ""
        info = self._unlocked.get(ach_id)
        if not isinstance(info, dict):
            return ""
        return str(info.get("unlocked_at", ""))

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
        from .session import reset_tracking_state
        reset_tracking_state()
        self._unlocked.clear()
        self._stats.clear()
        self._stats_dirty = False
        self._stats_forced.clear()
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

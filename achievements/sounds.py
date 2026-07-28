"""
Система звукових схем для Blender Achievements.

Чотири слоти звуку:
    unlock       — звичайна ачивка розблокована
    rare_unlock  — рідкісна ачивка розблокована
    end          — тост звичайної ачивки починає зникати
    rare_end     — тост рідкісної ачивки починає зникати

Пресети (Steam / Xbox / PlayStation) задають файли для слотів; користувач може
створювати власні профілі з будь-якими файлами. Гучність регулюється окремо для
кожного слоту та глобальним майстер-повзунком.

Публічний API:
    sounds.resolve(slot, prefs)      -> (filepath | None, volume 0..1)
    sounds.play_slot(slot, prefs)    — програти звук слоту (з урахуванням гучності)
    sounds.stop_all()                — зупинити всі активні відтворення
"""

import os

import bpy

from . import debug

try:
    import aud
    _HAS_AUD = True
except Exception as _dbg_err:  # noqa: BLE001
    debug.log("sounds.py:27", _dbg_err)
    _HAS_AUD = False


SOUND_DIR = os.path.join(os.path.dirname(__file__), "assets")

# Слоти у стабільному порядку відображення в UI
SLOTS = ("unlock", "rare_unlock", "end", "rare_end")

SLOT_LABELS = {
    "unlock": "Achievement Unlocked",
    "rare_unlock": "Rare Achievement Unlocked",
    "end": "Achievement Notification Ends",
    "rare_end": "Rare Achievement Notification Ends",
}

# ------------------------------------------------------------------ пресети
# Значення — імена файлів усередині папки assets/ ("" = без звуку).
# standart.wav / rare.wav: "Game Pickup" by IENBA (freesound.org/s/698768),
# ліцензія CC0 — вільні для будь-якого використання без атрибуції.
PRESETS = {
    'STEAM': {
        "unlock": "standart.wav",
        "rare_unlock": "rare.wav",
        "end": "",
        "rare_end": "",
    },
    'XBOX': {
        "unlock": "standart.wav",
        "rare_unlock": "rare.wav",
        "end": "",
        "rare_end": "",
    },
    'PS': {
        "unlock": "standart.wav",
        "rare_unlock": "rare.wav",
        "end": "",
        "rare_end": "",
    },
}

PRESET_ITEMS = (
    ('STEAM', "Steam", "Steam achievement sounds"),
    ('XBOX', "Xbox", "Xbox achievement sounds"),
    ('PS', "PlayStation", "PlayStation achievement sounds"),
    ('CUSTOM', "Custom", "Use your own custom sound profile"),
)

# аудіо-стан (тримаємо посилання, щоб GC не обірвав відтворення)
_device = None
_handles = []


def preset_path(preset: str, slot: str):
    """Абсолютний шлях до файлу пресету для слоту або None."""
    fname = PRESETS.get(preset, {}).get(slot, "")
    if not fname:
        return None
    p = os.path.join(SOUND_DIR, fname)
    return p if os.path.exists(p) else None


def preset_override_attr(preset: str, slot: str) -> str:
    """Ім'я властивості в AddonPreferences, що зберігає власний файл звуку
    для слоту вбудованого пресету (порожньо → використати файл пресету)."""
    return f"{preset.lower()}_{slot}_sound"


def ensure_preset_defaults(prefs):
    """Заповнює поля файлів вбудованих пресетів шляхами до бандлених звуків.

    Так користувач одразу бачить, що саме грає, і може підмінити файл, не
    вгадуючи. Заодно самолікування: якщо збережений шлях зник (аддон
    переставили в іншу теку), він замінюється на актуальний бандлений.
    Слоти, для яких пресет звуку не має (end / rare_end), лишаються порожні.
    """
    if prefs is None:
        return
    for preset in ('STEAM', 'XBOX', 'PS'):
        for slot in SLOTS:
            default = preset_path(preset, slot)
            if not default:
                continue
            attr = preset_override_attr(preset, slot)
            try:
                cur = getattr(prefs, attr, "") or ""
                if not cur or not os.path.exists(bpy.path.abspath(cur)):
                    setattr(prefs, attr, default)
            except Exception as _dbg_err:  # noqa: BLE001
                debug.log("sounds.py:ensure_preset_defaults", _dbg_err)


def raw_slot_path(slot: str, prefs, profile=None):
    """Сирий (незваліджований) шлях, який користувач призначив слоту, або "".

    Для CUSTOM береться з профілю, для вбудованих пресетів — з поля-заміни;
    порожній рядок означає «використовується стандартний файл пресету».
    Потрібно UI, щоб відрізнити «нічого не задано» від «задано, але файл
    зник» і показати попередження саме в другому випадку.
    """
    try:
        if profile is not None:
            return getattr(profile, f"{slot}_sound", "") or ""
        preset = getattr(prefs, "sound_preset", 'STEAM')
        if preset == 'CUSTOM':
            return ""
        return getattr(prefs, preset_override_attr(preset, slot), "") or ""
    except Exception as _dbg_err:  # noqa: BLE001
        debug.log("sounds.py:raw_slot_path", _dbg_err)
        return ""


def is_missing(raw_path: str) -> bool:
    """True, якщо шлях задано, але файлу за ним немає."""
    if not raw_path:
        return False
    try:
        return not os.path.exists(bpy.path.abspath(raw_path))
    except Exception as _dbg_err:  # noqa: BLE001
        debug.log("sounds.py:is_missing", _dbg_err)
        return False


def get_active_profile(prefs):
    """Активний користувацький профіль або None."""
    if prefs is None:
        return None
    try:
        profiles = prefs.sound_profiles
        idx = prefs.active_profile_index
        if 0 <= idx < len(profiles):
            return profiles[idx]
    except Exception as _dbg_err:  # noqa: BLE001
        debug.log("sounds.py:98", _dbg_err)
        pass
    return None


def resolve(slot: str, prefs=None):
    """(шлях або None, гучність 0..1) для слоту з урахуванням пресету/профілю,
    гучності слоту та майстер-гучності."""
    if prefs is None:
        prefs = _get_prefs()
    if prefs is None:
        return (preset_path('STEAM', slot), 1.0)

    if not getattr(prefs, "enable_sound", True):
        return (None, 0.0)

    preset = getattr(prefs, "sound_preset", 'STEAM')
    master = float(getattr(prefs, "master_volume", 1.0))

    if preset == 'CUSTOM':
        prof = get_active_profile(prefs)
        if prof is None:
            return (None, 0.0)
        raw = getattr(prof, f"{slot}_sound", "") or ""
        path = bpy.path.abspath(raw) if raw else ""
        path = path if (path and os.path.exists(path)) else None
        vol = float(getattr(prof, f"{slot}_volume", 1.0))
    else:
        # власний файл користувача має пріоритет над файлом пресету
        raw = getattr(prefs, preset_override_attr(preset, slot), "") or ""
        if raw:
            p = bpy.path.abspath(raw)
            path = p if os.path.exists(p) else None
        else:
            path = preset_path(preset, slot)
        vol = float(getattr(prefs, f"{slot}_volume", 1.0))

    return (path, max(0.0, min(1.0, vol * master)))


_preview = {}   # slot -> aud handle (для кнопки Play/Stop у налаштуваннях)


def play(path, volume=1.0, slot=None):
    """Програти файл із заданою гучністю. Тихо ігнорує помилки.

    slot — якщо вказано, хендл запам'ятовується, щоб UI міг показати Stop
    і зупинити саме це прослуховування.
    """
    global _device, _handles
    if not _HAS_AUD or not path or volume <= 0.0:
        return None
    try:
        if _device is None:
            _device = aud.Device()
        snd = aud.Sound(path)
        handle = _device.play(snd)
        try:
            handle.volume = volume
        except Exception as _dbg_err:  # noqa: BLE001
            debug.log("sounds.py:151", _dbg_err)
            pass
        # тримаємо лише активні хендли, щоб список не ріс
        _handles = [h for h in _handles if _is_playing(h)]
        _handles.append(handle)
        if slot:
            _preview[slot] = handle
        return handle
    except Exception as _dbg_err:  # noqa: BLE001
        debug.log("sounds.py:159", _dbg_err)
        return None


def is_previewing(slot):
    """True, якщо саме зараз програється прев'ю цього слоту."""
    h = _preview.get(slot)
    if h is None:
        return False
    if not _is_playing(h):
        _preview.pop(slot, None)
        return False
    return True


def stop_preview(slot):
    """Зупиняє прев'ю конкретного слоту."""
    h = _preview.pop(slot, None)
    if h is not None:
        try:
            h.stop()
        except Exception as _dbg_err:  # noqa: BLE001
            debug.log("sounds.py:180", _dbg_err)
            pass


def play_slot(slot: str, prefs=None):
    """Розв'язати слот і програти його звук."""
    path, vol = resolve(slot, prefs)
    if path:
        play(path, vol)


def _is_playing(handle):
    try:
        return bool(getattr(handle, "status", False))
    except Exception as _dbg_err:  # noqa: BLE001
        debug.log("sounds.py:194", _dbg_err)
        return False


def stop_all():
    """Зупиняє всі активні відтворення та звільняє пристрій."""
    global _device, _handles
    for h in _handles:
        try:
            h.stop()
        except Exception as _dbg_err:  # noqa: BLE001
            debug.log("sounds.py:204", _dbg_err)
            pass
    _handles = []
    _preview.clear()
    _device = None


def _get_prefs():
    try:
        addon = __package__.split('.')[0] if __package__ else "achievements"
        prefs = getattr(bpy.context, "preferences", None)
        if prefs and hasattr(prefs, "addons") and addon in prefs.addons:
            return prefs.addons[addon].preferences
    except Exception as _dbg_err:  # noqa: BLE001
        debug.log("sounds.py:217", _dbg_err)
        pass
    return None

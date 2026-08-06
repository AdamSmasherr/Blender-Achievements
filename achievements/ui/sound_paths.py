"""
Portable sound-path packing and profile (de)serialization used by the
Export/Import Profiles operators (achievements/ui/operators.py).
"""

import os

import bpy

from .. import sounds

# Токен, яким у експортованому JSON позначається файл із папки assets/
# самого аддона. Абсолютні шляхи на іншій машині не існують, тож бандлені
# звуки записуються відносно addon-каталогу і розгортаються при імпорті.
_ASSET_TOKEN = "<assets>/"

DEFAULT_PROFILE_FILE = "Profile.json"


def _pack_sound_path(raw: str) -> str:
    """Абсолютний шлях → портативний вигляд для експорту."""
    if not raw:
        return ""
    try:
        full = os.path.abspath(bpy.path.abspath(raw))
        assets = os.path.abspath(sounds.SOUND_DIR)
        if os.path.commonpath([full, assets]) == assets:
            return _ASSET_TOKEN + os.path.relpath(full, assets).replace(os.sep, "/")
    except (ValueError, OSError):
        pass
    return raw


def _unpack_sound_path(stored: str) -> str:
    """Портативний вигляд → шлях на цій машині."""
    if stored.startswith(_ASSET_TOKEN):
        rel = stored[len(_ASSET_TOKEN):].replace("/", os.sep)
        return os.path.join(sounds.SOUND_DIR, rel)
    return stored


def _validated_json_path(raw: str):
    """Абсолютний шлях до .json або None, якщо ім'я файлу не задано.

    Файловий браузер Blender дозволяє підтвердити вибір із порожнім полем
    імені — тоді filepath це просто тека, і open() падає з Errno 2. Ловимо
    це тут і повертаємо зрозумілу помилку в UI замість трейсбеку в консолі.
    """
    if not raw:
        return None
    path = bpy.path.abspath(raw)
    if not os.path.basename(path) or os.path.isdir(path):
        return None
    if not path.lower().endswith(".json"):
        path += ".json"
    return path


def _profile_to_dict(p) -> dict:
    d = {"name": p.name, "animation_style": p.animation_style}
    for slot in sounds.SLOTS:
        d[f"{slot}_sound"] = _pack_sound_path(getattr(p, f"{slot}_sound", ""))
        d[f"{slot}_volume"] = getattr(p, f"{slot}_volume", 1.0)
    return d


def _dict_to_profile(prefs, d: dict):
    p = prefs.sound_profiles.add()
    p.name = str(d.get("name", "Imported Profile"))
    style = d.get("animation_style", "STEAM")
    if style in ('STEAM', 'XBOX', 'PS'):
        p.animation_style = style
    for slot in sounds.SLOTS:
        setattr(p, f"{slot}_sound",
                _unpack_sound_path(str(d.get(f"{slot}_sound", "") or "")))
        try:
            setattr(p, f"{slot}_volume", float(d.get(f"{slot}_volume", 1.0)))
        except (TypeError, ValueError):
            pass
    return p

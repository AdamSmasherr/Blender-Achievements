"""
Lazily-built bpy.utils.previews collection holding one custom icon per
achievement, used by the achievements list (achievements/ui/panels.py).

The artwork files are transparent, white-and-grey webp: the background fill
and the icon colour are settings, not part of the file. The pop-up card does
that with a shader (see toast._icon_burn_shader); `UILayout` has no shader,
so here the same arithmetic runs once per icon over the pixels and the result
is handed to Blender as a finished preview.

Both paths use `toast.linear_burn()`, so the list and the card can't drift
apart.
"""

import os

import bpy

from .. import debug
from .. import engine
from .. import registry
from .. import toast
from .helpers import _tag_redraw_all

_custom_icons = None

# Прев'юшки печемо у 128px: у списку іконка займає щонайбільше ~70px навіть
# при найбільшому масштабі, а 256px коштували б учетверо більше пам'яті й часу
# на кожну зміну кольору.
_PREVIEW_PX = 128

# Перемальовування після зміни кольору навмисно відкладене: колірний пікер
# шле update на КОЖЕН рух миші, а перепікання всіх іконок — це десяті долі
# секунди. Без затримки перетягування повзунка йшло б ривками. Поки таймер
# не спрацював, список показує попередні (ще правильні) прев'юшки.
_REBUILD_DELAY = 0.3
_rebuild_pending = False


def _load_pixels(path):
    """RGBA-пікселі файлу як numpy-масив (h, w, 4), або None.

    'Non-Color' — щоб Blender віддав значення як вони лежать у файлі, без
    лінеаризації: прев'ю зберігає їх у тому ж вигляді (перевірено —
    pcoll.load() дає ті самі числа з точністю до 8-бітного квантування).
    """
    import numpy as np
    img = None
    try:
        img = bpy.data.images.load(path)
        img.colorspace_settings.name = 'Non-Color'
        w, h = img.size
        if w <= 0 or h <= 0:
            return None
        buf = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(buf)
        return buf.reshape(h, w, 4)
    finally:
        if img is not None:
            try:
                bpy.data.images.remove(img, do_unlink=True)
            except Exception as _dbg_err:  # noqa: BLE001
                debug.log("ui/icons.py:_load_pixels/cleanup", _dbg_err)


def _downsample(px, target=_PREVIEW_PX):
    """Зменшує зображення цілим кратним, усереднюючи блоки 2x2 і далі.

    Кольори усереднюються З ВАГОЮ АЛЬФИ: без цього повністю прозорі пікселі
    (у них RGB довільний) підмішувались би у краї й давали облямівку.
    """
    import numpy as np
    h, w = px.shape[:2]
    k = min(h // target, w // target) if target else 1
    if k < 2:
        return px
    h2, w2 = (h // k) * k, (w // k) * k
    blocks = px[:h2, :w2].reshape(h2 // k, k, w2 // k, k, 4)
    a = blocks[..., 3:4]
    a_sum = a.sum(axis=(1, 3))
    rgb = (blocks[..., :3] * a).sum(axis=(1, 3))
    out = np.empty((h2 // k, w2 // k, 4), dtype=np.float32)
    out[..., :3] = np.divide(rgb, a_sum, out=np.zeros_like(rgb), where=a_sum > 1e-6)
    out[..., 3] = a.mean(axis=(1, 3))[..., 0]
    return out


def _composite(px, bg, tint):
    """Іконка, зафарбована Linear Burn і покладена на суцільний фон.

    Повертає непрозору плитку: у списку ачивок прев'ю малюється поверх теми
    Blender, і напівпрозорі краї інакше змішувались би з нею, а не з фоном,
    який користувач обрав.
    """
    import numpy as np
    a = px[..., 3:4]
    burned = np.clip(px[..., :3] + np.asarray(tint[:3], dtype=np.float32) - 1.0, 0.0, 1.0)
    out = np.empty_like(px)
    out[..., :3] = burned * a + np.asarray(bg[:3], dtype=np.float32) * (1.0 - a)
    out[..., 3] = 1.0
    return out


def _flat_tile(bg):
    """Плитка самого фону — для ачивки, яка навмисно без картинки."""
    import numpy as np
    out = np.empty((8, 8, 4), dtype=np.float32)
    out[..., :3] = np.asarray(bg[:3], dtype=np.float32)
    out[..., 3] = 1.0
    return out


def _build_preview(pcoll, ach_id, path, bg, tint):
    """Пече одну прев'юшку. True, якщо вдалось."""
    def _work():
        px = _load_pixels(path) if path else None
        tile = _composite(_downsample(px), bg, tint) if px is not None else _flat_tile(bg)
        prev = pcoll.new(ach_id)
        prev.image_size = (tile.shape[1], tile.shape[0])
        prev.image_pixels_float.foreach_set(tile.ravel())
        return True
    return bool(debug.guarded_value(f"ui/icons.py:_build_preview/{ach_id}", _work, False))


def get_custom_icons():
    global _custom_icons
    if _custom_icons is None:
        try:
            import bpy.utils.previews
            pcoll = bpy.utils.previews.new()
            bg = toast.icon_color("bg")
            tint = toast.icon_color("tint")
            for ach_id, ach_def in registry.ACHIEVEMENTS.items():
                icon_path = engine._resolve_icon_path(ach_def)
                if icon_path and not os.path.exists(icon_path):
                    icon_path = None
                # Ачивка без картинки (Out of Memory) все одно отримує плитку —
                # порожня плитка і є її «іконкою».
                if not _build_preview(pcoll, ach_id, icon_path, bg, tint):
                    # Запасний шлях: без numpy лишається хоч нефарбована,
                    # але жива іконка.
                    if icon_path:
                        try:
                            pcoll.load(ach_id, icon_path, 'IMAGE')
                        except Exception:
                            pass
            _custom_icons = pcoll
        except Exception:
            _custom_icons = None
    return _custom_icons


def clear_custom_icons():
    global _custom_icons
    if _custom_icons is not None:
        try:
            import bpy.utils.previews
            bpy.utils.previews.remove(_custom_icons)
        except Exception:
            pass
        _custom_icons = None


def _rebuild_now():
    global _rebuild_pending
    _rebuild_pending = False
    clear_custom_icons()
    _tag_redraw_all()
    return None      # одноразовий таймер


def request_rebuild():
    """Перепекти іконки, коли користувач відпустить колірний пікер.

    Прев'юшки лишаються старими до спрацювання таймера — це навмисно: краще
    показати колір, що відстає на третину секунди, ніж підвісити інтерфейс на
    кожному русі миші.
    """
    global _rebuild_pending
    if _rebuild_pending:
        return
    _rebuild_pending = True
    with debug.guarded("ui/icons.py:request_rebuild"):
        if not bpy.app.timers.is_registered(_rebuild_now):
            bpy.app.timers.register(_rebuild_now, first_interval=_REBUILD_DELAY)

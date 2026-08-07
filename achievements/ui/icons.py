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
_baked_colors = None      # кольори, у яких спечена поточна колекція


def _current_colors():
    """Кольори, які визначають вигляд іконок — ключ кешу прев'юшок."""
    return (tuple(toast.icon_color("bg")[:3]), tuple(toast.icon_color("tint")[:3]))


def _load_pixels(path, target=_PREVIEW_PX):
    """RGBA-пікселі файлу як numpy-масив (h, w, 4), зменшені до `target`.

    Зменшує сам Blender (`Image.scale`), а не numpy: те саме усереднення в
    C коштує вдвічі менше, ніж найакуратніший numpy-варіант, і заразом
    учетверо скорочує `foreach_get` — читаємо 128², а не 256². Різниця в
    результаті — 2/255 у середньому, тобто непомітна.

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
        if target and max(w, h) > target:
            k = target / float(max(w, h))          # пропорції зберігаємо
            img.scale(max(1, int(round(w * k))), max(1, int(round(h * k))))
            w, h = img.size
        buf = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(buf)
        return buf.reshape(h, w, 4)
    finally:
        if img is not None:
            try:
                bpy.data.images.remove(img, do_unlink=True)
            except Exception as _dbg_err:  # noqa: BLE001
                debug.log("ui/icons.py:_load_pixels/cleanup", _dbg_err)


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
        tile = _composite(px, bg, tint) if px is not None else _flat_tile(bg)
        prev = pcoll.new(ach_id)
        prev.image_size = (tile.shape[1], tile.shape[0])
        prev.image_pixels_float.foreach_set(tile.ravel())
        return True
    return bool(debug.guarded_value(f"ui/icons.py:_build_preview/{ach_id}", _work, False))


def _bake_all():
    """Збирає нову колекцію прев'юшок у поточних кольорах, або None."""
    try:
        import bpy.utils.previews
        pcoll = bpy.utils.previews.new()
    except Exception as _dbg_err:  # noqa: BLE001
        debug.log("ui/icons.py:_bake_all/new", _dbg_err)
        return None

    bg = toast.icon_color("bg")
    tint = toast.icon_color("tint")
    for ach_id, ach_def in registry.ACHIEVEMENTS.items():
        icon_path = engine._resolve_icon_path(ach_def)
        if icon_path and not os.path.exists(icon_path):
            icon_path = None
        # Ачивка без картинки (Out of Memory) все одно отримує плитку —
        # порожня плитка і є її «іконкою».
        if not _build_preview(pcoll, ach_id, icon_path, bg, tint) and icon_path:
            # Запасний шлях: краще нефарбована, але жива іконка, ніж жодної.
            with debug.guarded(f"ui/icons.py:_bake_all/load/{ach_id}"):
                pcoll.load(ach_id, icon_path, 'IMAGE')
    return pcoll


def get_custom_icons():
    """Колекція прев'юшок, або None поки вона ще не спечена.

    САМА НІЧОГО НЕ ПЕЧЕ. Пекти доводиться з файлів — це читання й запис у
    bpy.data, — а викликається ця функція з `draw()` панелі. У частині
    контекстів (старт Blender, завантаження файлу, скасування дії) такий
    доступ там не дозволений: випікання тихо падало, спрацьовував запасний
    `pcoll.load()`, і в кеші назавжди осідали НЕфарбовані іконки — рівно та
    поведінка, через яку колір у списку не змінювався.

    Тепер випікання йде з таймера, тобто в безпечному контексті, а панель
    один кадр малює стандартну іконку замість власної.
    """
    if _custom_icons is None:
        request_rebuild(delay=0.0)
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
    """Пече нову колекцію і підміняє нею стару. Викликається лише з таймера."""
    global _custom_icons, _rebuild_pending, _baked_colors
    _rebuild_pending = False
    colors = _current_colors()
    if _custom_icons is not None and colors == _baked_colors:
        return None                    # кольори ті самі — пекти нема чого
    fresh = debug.guarded_value("ui/icons.py:_rebuild_now", _bake_all, None)
    if fresh is None:
        return None
    # Стару колекцію прибираємо ТІЛЬКИ коли нова готова: інакше між цими
    # двома моментами панель малювалась би без іконок.
    clear_custom_icons()
    _custom_icons = fresh
    _baked_colors = colors
    _tag_redraw_all()
    return None      # одноразовий таймер


def request_rebuild(delay=_REBUILD_DELAY):
    """Перепекти іконки поза малюванням панелі.

    Кожен виклик ПЕРЕЗАПУСКАЄ відлік. Колірний пікер шле update на кожен рух
    миші, а перепікання всіх іконок — сотня з гаком мілісекунд; якби відлік
    не перезапускався, воно спрацьовувало б раз за раз посеред перетягування
    і смикало б інтерфейс. Так воно чекає, поки користувач зупиниться, і
    пече рівно один раз. Доки чекає — список показує попередні прев'юшки.

    `delay=0` для найпершої побудови, коли показувати ще нічого.
    """
    global _rebuild_pending
    with debug.guarded("ui/icons.py:request_rebuild"):
        if bpy.app.timers.is_registered(_rebuild_now):
            bpy.app.timers.unregister(_rebuild_now)
        bpy.app.timers.register(_rebuild_now, first_interval=delay)
        _rebuild_pending = True

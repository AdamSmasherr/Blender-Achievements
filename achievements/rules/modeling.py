"""Modeling & sculpting rules that read the scene directly.

The diff-based ones from this category (Frankenstein, Singularity, Surgical
Precision, Up is Down) live in `operations.py` with the detector that feeds
them.
"""

import bpy

from ..registry import DEPSGRAPH, TIMER, bind
from ..session import TIMER_TICK, state
from . import probes

POLYGON_KING_TARGET = 10_000_000
UV_DWELL_SECONDS = 1800          # 30 хвилин у UV Editing


def _polygon_king(ctx) -> int:
    return probes.object_scan(ctx).get("polys", 0)


def _uv_editing_now(ctx) -> bool:
    """Чи користувач саме зараз розгортає UV.

    IMAGE_EDITOR — це не лише UV-редактор: та сама область у режимі VIEW
    обслуговує вкладку Rendering, у PAINT — текстурне малювання. Раніше
    зараховувався будь-який з них, тож півгодини з відкритим рендер-результатом
    видавали «Flat Earth». Потрібен саме UV-режим (`ui_mode`; у частині
    версій — `mode`).
    """
    ws = getattr(bpy.context, "workspace", None)
    if ws and ws.name == "UV Editing":
        return True
    screen = getattr(bpy.context, "screen", None)
    if not screen:
        return False
    for area in screen.areas:
        if area.type != 'IMAGE_EDITOR':
            continue
        space = getattr(area, "spaces", None)
        space = getattr(space, "active", None) if space else None
        if space is None:
            continue
        if 'UV' in (getattr(space, "ui_mode", None), getattr(space, "mode", None)):
            return True
    return False


def _uv_dwell_tick(ctx) -> bool:
    """Секунди БЕЗПЕРЕРВНОГО перебування в UV-редакторі.

    Це правило веде власний лічильник: «30 хвилин поспіль» не читається зі
    стану сцени, його можна лише накопичити. Тік живе в перевірці, бо вона
    біжить рівно раз на тік таймера — `progress` нижче лише ЧИТАЄ лічильник,
    інакше кожна перемальовка панелі накручувала б час.
    """
    if _uv_editing_now(ctx):
        state.uv_editing_seconds += TIMER_TICK
    else:
        state.uv_editing_seconds = 0
    return state.uv_editing_seconds >= UV_DWELL_SECONDS


def _subdiv_overkill(ctx) -> bool:
    for ob in bpy.data.objects:
        if ob.type != 'MESH' or not ctx.is_new('objects', ob.name):
            continue
        for mod in ob.modifiers:
            if mod.type == 'SUBSURF' and (mod.levels >= 6 or mod.render_levels >= 6):
                return True
    return False


def _n_gon_criminal(ctx) -> bool:
    """Грань на 10+ сторін — серед щойно змінених мешів або серед створених
    цієї сесії."""
    changed = ctx.extra.get("changed_meshes")
    if changed and probes.scan_changed_for_ngon(changed):
        return True
    return probes.has_ngon_new_mesh()


bind("POLYGON_KING", TIMER, progress=_polygon_king, target=POLYGON_KING_TARGET,
     check=lambda ctx: _polygon_king(ctx) > POLYGON_KING_TARGET, scan=True)
# Без `progress`: смужка «900 / 1800 секунд» у списку ачивок читається як
# лічильник дій, а не як «посидь ще пів години», тож цю навмисно лишаємо
# без прогресу — як було й до переходу на декларативні правила.
bind("UV_UNWRAPPING_PAIN", TIMER, check=_uv_dwell_tick)
bind("SUBDIV_OVERKILL", DEPSGRAPH, check=_subdiv_overkill)
bind("N_GON_CRIMINAL", DEPSGRAPH, check=_n_gon_criminal, interval=1.5)

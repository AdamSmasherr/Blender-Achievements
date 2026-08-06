"""Workflow & disaster rules: saving, add-ons, crashes, idling."""

import os
import time

import bpy

from .. import debug
from ..registry import LOAD, SAVE, TIMER, bind
from ..session import state
from . import probes

IDLE_SECONDS = 14400            # 4 години безділля
UNSAVED_SECONDS = 7200          # 2 години без Ctrl+S
ADDON_TARGET = 25
OUTLINER_TARGET = 47
SAVE_MASHER_TARGET = 50


def is_crash_recovery_file() -> bool:
    """Чи відкритий файл справді прийшов з відновлення після краху.

    Раніше сюди зараховувались `.blend1` / `.blend2` — а це звичайні
    інкрементні бекапи, які Blender робить при КОЖНОМУ збереженні. Відкрити
    `model.blend1`, щоб глянути попередню версію, — буденна дія, а не
    повернення з того світу; вона ж накручувала лічильник `recoveries`.

    Справжніх шляхів відновлення два, і обидва ведуть у тимчасовий каталог:
      * File > Recover Last Session -> `quit.blend`;
      * File > Recover Auto Save    -> автозбереження з temp-каталогу.
    `bpy.app.tempdir` — це підкаталог сесії всередині системного temp, а
    автозбереження лежать поруч із ним, тож звіряємось із батьківським.
    """
    fp = bpy.data.filepath
    if not fp:
        return False
    norm = os.path.normcase(os.path.normpath(fp))
    base = os.path.basename(norm)
    if base == "quit.blend" or "autosave" in base:
        return True
    with debug.guarded("rules.workflow:is_crash_recovery_file"):
        tmp_root = os.path.dirname(os.path.normcase(os.path.normpath(bpy.app.tempdir)))
        if tmp_root and norm.startswith(tmp_root + os.sep):
            return True
    return False


def _living_on_the_edge(ctx) -> bool:
    return (getattr(bpy.data, "is_dirty", False)
            and (time.time() - state.last_save_time) >= UNSAVED_SECONDS)


def _addon_collector(ctx) -> bool:
    """25+ увімкнених аддонів, з яких хоча б один увімкнено цієї сесії."""
    if ctx.baseline is None:
        return False
    current = probes.addons(ctx)
    return current >= ADDON_TARGET and current > ctx.baseline_count('addon_count')


bind("THE_SURVIVOR", LOAD, check=lambda ctx: is_crash_recovery_file())

bind("SAVE_BUTTON_MASHER", SAVE, target=SAVE_MASHER_TARGET,
     progress=lambda ctx: state.session_save_count)

bind("LIVING_ON_THE_EDGE", TIMER, check=_living_on_the_edge)

bind("ADDON_COLLECTOR", TIMER, check=_addon_collector, target=ADDON_TARGET,
     progress=probes.addons, scan=True)

bind("OUTLINER_CHAOS", TIMER, target=OUTLINER_TARGET, scan=True,
     progress=lambda ctx: probes.object_scan(ctx).get("autonamed", 0))

# Append/Link ловить і штатний blend_import_post (див. handlers.py) — це
# резервний шлях для випадків, коли хендлер не спрацював.
bind("APPEND_ICITIS", TIMER, check=lambda ctx: probes.detect_appended_this_session())

# Лічильник безділля крутить таймер у handlers.py: скидати його має КОЖНА
# активність (клавіша, зміна сцени, кадр, рендер), а не лише цей тік.
bind("WHAT_AM_I_DOING", TIMER, check=lambda ctx: state.idle_seconds >= IDLE_SECONDS)

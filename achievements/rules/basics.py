"""
Basics: the cube, the monkey, the donut.

The two object-diff rules here read facts produced by
`operations.detect_object_changes()` earlier in the same depsgraph pass — a
predicate over the current scene genuinely cannot see "a cube was deleted",
only "no cube is here now", which is also true for a session that never had
one.
"""

import time

from ..registry import DEPSGRAPH, RENDER_COMPLETE, bind
from ..session import state

# Скільки секунд після старту сесії видалення куба ще зараховується.
GOODBYE_CUBE_WINDOW = 30.0


def _deleted_cube_in_time(ctx) -> bool:
    if not ctx.extra.get("deleted_cubes"):
        return False
    return (time.time() - state.launch_time) <= GOODBYE_CUBE_WINDOW


def _added_monkey(ctx) -> bool:
    return bool(ctx.extra.get("new_monkeys"))


def _pristine_default_cube(ctx) -> bool:
    """Фабричний куб, якого цієї сесії ніхто не чіпав.

    Лише у сесії, що стартувала з фабричного/нового файлу (`respect_cube_armed`),
    і лише для об'єкта, який був тут ДО сесії — доданий Shift+D дубль або куб з
    чужого .blend не рахується.
    """
    if not state.respect_cube_armed:
        return False
    scene = ctx.scene
    if scene is None:
        return False
    for ob in scene.objects:
        if ctx.is_new('objects', ob.name):
            continue
        if ob.name != "Cube" or ob.type != 'MESH' or not ob.data:
            continue
        if not ob.data.name.startswith("Cube"):
            continue
        if len(ob.data.vertices) != 8 or len(ob.data.polygons) != 6:
            continue
        loc, scale, rot = ob.location, ob.scale, ob.rotation_euler
        if (abs(loc.x) < 1e-4 and abs(loc.y) < 1e-4 and abs(loc.z) < 1e-4 and
                abs(scale.x - 1.0) < 1e-4 and abs(scale.y - 1.0) < 1e-4 and
                abs(scale.z - 1.0) < 1e-4 and
                abs(rot.x) < 1e-4 and abs(rot.y) < 1e-4 and abs(rot.z) < 1e-4):
            return True
    return False


def _glazed_torus(ctx) -> bool:
    scene = ctx.scene
    if scene is None:
        return False
    for ob in scene.objects:
        if ob.type != 'MESH' or not ob.data:
            continue
        if "torus" not in ob.name.lower() and "torus" not in ob.data.name.lower():
            continue
        for slot in ob.material_slots:
            if slot.material:
                mname = slot.material.name.lower()
                if "glaze" in mname or "donut" in mname:
                    return True
    return False


bind("GOODBYE_CUBE", DEPSGRAPH, check=_deleted_cube_in_time)
bind("SUZANNES_BLESSING", DEPSGRAPH, check=_added_monkey)
bind("RESPECT_THE_CUBE", RENDER_COMPLETE, check=_pristine_default_cube)
bind("DONUT_MASTER", RENDER_COMPLETE, check=_glazed_torus)

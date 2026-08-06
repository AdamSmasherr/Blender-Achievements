"""Animation & physics rules.

Graph Editor tweaks and finished bakes are recognised from a difference
between depsgraph passes, so those live in `operations.py`; what's left here
reads the scene.
"""

import bpy

from ..registry import DEPSGRAPH, FRAME_CHANGE, TIMER, bind
from . import probes

# Квадрат відстані, далі якої вершина тканини вважається «вибухнутою»
# (100 одиниць з опису ачивки).
CLOTH_BLOWUP_DIST_SQ = 10000.0


def _bone_collector(ctx) -> bool:
    """100+ кісток у ригу, СТВОРЕНОМУ цієї сесії.

    Окремо від `progress` нижче, бо в Edit Mode кістки живуть в `edit_bones`,
    а `data.bones` там ще порожній — для смужки прогресу ця різниця не варта
    обходу, для видачі ачивки варта.
    """
    for ob in bpy.data.objects:
        if ob.type != 'ARMATURE' or not ob.data or not ctx.is_new('objects', ob.name):
            continue
        if len(ob.data.bones) >= 100:
            return True
        if (getattr(ob, "mode", "") == 'EDIT' and hasattr(ob.data, "edit_bones")
                and len(ob.data.edit_bones) >= 100):
            return True
    return False


def _new_particle_max(ctx) -> int:
    return max((getattr(ps, "count", 0) for ps in bpy.data.particles
                if ctx.is_new('particles', ps.name)), default=0)


def _rigidbody_objects(ctx) -> int:
    scene = ctx.scene
    rbw = getattr(scene, "rigidbody_world", None) if scene else None
    if not rbw:
        return 0
    coll = getattr(rbw, "collection", None) or getattr(rbw, "group", None)
    return len(coll.objects) if coll else 0


def _cloth_explosion(ctx) -> bool:
    """Вершина тканини, що відлетіла на 100+ одиниць від вихідної геометрії."""
    scene = ctx.scene
    if scene is None:
        return False
    dg = ctx.depsgraph if ctx.depsgraph is not None else bpy.context.evaluated_depsgraph_get()
    import numpy as np
    for ob in scene.objects:
        if ob.type != 'MESH' or not any(mod.type == 'CLOTH' for mod in ob.modifiers):
            continue
        # Модифікатор Cloth деформує лише evaluated-меш (через depsgraph), а не
        # ob.data напряму — тому координати треба брати з ob.evaluated_get(dg).data,
        # інакше вершини завжди залишаються у недеформованому "сирому" стані.
        me_eval = ob.evaluated_get(dg).data
        me_orig = ob.data
        if not (me_eval and me_orig):
            continue
        n = len(me_eval.vertices)
        if n == 0 or n != len(me_orig.vertices):
            continue
        # Саме відхилення (displacement) від початкової геометрії, а не
        # абсолютні координати (які можуть бути великими просто через розмір
        # меша). foreach_get + numpy замість циклу по вершинах: це кожен кадр
        # плейбеку, а тканина на 50k вершин у Python-циклі з'їдала плейбек цілком.
        co_eval = np.empty(n * 3, dtype=np.float32)
        co_orig = np.empty(n * 3, dtype=np.float32)
        me_eval.vertices.foreach_get("co", co_eval)
        me_orig.vertices.foreach_get("co", co_orig)
        d = (co_eval - co_orig).reshape(n, 3)
        if float(np.max(np.einsum('ij,ij->i', d, d))) > CLOTH_BLOWUP_DIST_SQ:
            return True
    return False


def _ouroboros(ctx) -> bool:
    """Самопосилальний драйвер, доданий цієї сесії.

    Спершу дешева перевірка «драйверів побільшало», і лише потім обхід усіх
    драйверів у пошуках циклу.
    """
    if ctx.baseline is None:
        return False
    if probes.drivers(ctx) <= ctx.baseline_count('driver_count'):
        return False
    return probes.has_self_referencing_driver()


bind("BONE_COLLECTOR", DEPSGRAPH, check=_bone_collector, target=100, scan=True,
     progress=lambda ctx: probes.object_scan(ctx).get("bones", 0))

bind("PARTICLE_STORM", DEPSGRAPH, progress=_new_particle_max, target=100000, scan=True)

bind("GRAVITY_MASTER", FRAME_CHANGE, progress=_rigidbody_objects, target=100, scan=True,
     check=lambda ctx: _rigidbody_objects(ctx) > 100)

bind("CLOTH_EXPLOSION", FRAME_CHANGE, check=_cloth_explosion)

bind("OUROBOROS", TIMER, check=_ouroboros)

# Дельта понад baseline: драйвери з відкритого файлу не рахуються.
bind("DRIVER_SPECIALIST", TIMER, target=5, scan=True,
     progress=lambda ctx: ctx.baseline_delta(probes.drivers(ctx), 'driver_count'))

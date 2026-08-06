"""
Scene readers shared by the rules.

Two layers here, on purpose:

  * plain functions (`count_drivers()`, `snapshot_objects()`, …) — a fresh
    read of `bpy.data`, callable from anywhere including the handlers that
    take the session baseline;
  * `@probe`-wrapped versions taking a `RuleContext` — the same read, but
    computed at most once per evaluation pass.

Rules should reach for the probe layer; handlers and one-shot bookkeeping
use the plain functions.
"""

import time

import bpy

from .. import debug
from ..session import state
from .context import guarded_probe, probe


# --- Object snapshot ------------------------------------------------------

def snapshot_objects() -> dict:
    """Returns a dict mapping object name -> metadata for MESH objects in bpy.data.objects."""
    res = {}
    for ob in bpy.data.objects:
        if getattr(ob, "type", None) == 'MESH':
            mesh_name = getattr(ob.data, "name", "") if getattr(ob, "data", None) else ""
            res[ob.name] = {
                "name": ob.name,
                "type": ob.type,
                "mesh_name": mesh_name,
            }
    return res


def ensure_snapshot() -> bool:
    """Lazy initialization of object snapshot (bpy.data is restricted during register)."""
    if state.known_objects is None:
        snapshot = debug.guarded_value("rules.probes:ensure_snapshot", snapshot_objects, None)
        if snapshot is None:
            return False
        state.known_objects = snapshot
        return True
    return False


# --- Session baseline -----------------------------------------------------

def snapshot_baseline() -> dict:
    """Зліпок стану на старті сесії / відкритті файлу: імена наявних датаблоків
    (щоб відрізнити створене цієї сесії) + деякі лічильники для дельт."""
    return {
        'objects': set(o.name for o in bpy.data.objects),
        'materials': set(m.name for m in bpy.data.materials),
        'node_groups': set(ng.name for ng in bpy.data.node_groups),
        'particles': set(p.name for p in bpy.data.particles),
        'lights': set(l.name for l in bpy.data.lights),
        'actions': set(a.name for a in bpy.data.actions),
        'driver_count': count_drivers(),
        'fake_user_count': count_fake_users(),
        'addon_count': len(getattr(getattr(bpy.context, "preferences", None), "addons", []) or []),
        'compositor_nodes': count_compositor_nodes(),
    }


def capture_baseline():
    """Знімає baseline та зводить прапорець Respect the Cube (фабрична сесія)."""
    state.baseline = None
    with debug.guarded("rules.probes:capture_baseline"):
        state.baseline = snapshot_baseline()
        # Куб зараховуємо лише у сесії, що стартувала з фабричного/нового файлу
        # (не з відкритого користувачем .blend).
        state.respect_cube_armed = (bpy.data.filepath == "")


def ensure_baseline():
    """Лінива ініціалізація baseline (bpy.data недоступний під час register)."""
    if state.baseline is None:
        capture_baseline()


def is_new(kind: str, name: str) -> bool:
    """True, якщо датаблок `name` створено цієї сесії (немає у baseline `kind`)."""
    if state.baseline is None:
        return False
    return name not in state.baseline.get(kind, ())


# --- Datablock counters ---------------------------------------------------

def count_drivers() -> int:
    """К-сть драйверів у сцені (objects/materials/shape_keys)."""
    n = 0
    for db_list in (bpy.data.objects, bpy.data.materials, bpy.data.shape_keys):
        for item in db_list:
            ad = getattr(item, "animation_data", None)
            if ad and hasattr(ad, "drivers"):
                n += len(ad.drivers)
    return n


def count_fake_users() -> int:
    """К-сть датаблоків із увімкненим Fake User (Shield).

    Не фільтруємо за кількістю users: вибір датаблоку в браузері (щоб
    натиснути щит) сам по собі додає йому реального користувача, тож вимога
    "0 інших users" робить ачівку недосяжною для звичайного воркфлоу. Від
    датаблоків, які вже мали fake user до старту сесії (напр. відкритий
    файл), захищає порівняння з baseline у виклику нижче — рахуються лише
    ті, кому щит призначили цієї сесії.
    """
    n = 0
    for collection in (bpy.data.materials, bpy.data.textures, bpy.data.node_groups,
                       bpy.data.actions, bpy.data.armatures):
        for db in collection:
            if getattr(db, "use_fake_user", False):
                n += 1
    return n


def count_total_polys() -> int:
    return sum(len(ob.data.polygons) for ob in bpy.data.objects
               if ob.type == 'MESH' and ob.data)


def count_total_node_links() -> int:
    n = 0
    for mat in bpy.data.materials:
        nt = getattr(mat, "node_tree", None)
        if nt:
            n += len(nt.links)
    for ng in bpy.data.node_groups:
        n += len(ng.links)
    for sc in bpy.data.scenes:
        nt = getattr(sc, "node_tree", None)
        if nt:
            n += len(nt.links)
    return n


def count_total_shapekeys() -> int:
    return sum(len(sk.key_blocks) for sk in bpy.data.shape_keys)


def count_compositor_nodes() -> int:
    """К-сть нод компоузера в усіх сценах.

    У Blender 5.x дерево компоузера переїхало з scene.node_tree у
    scene.compositing_node_group (scene.node_tree там уже не існує, а
    scene.use_nodes позначено deprecated до 6.0). Перевіряємо обидва, щоб
    працювало і на 4.4, і на 5.x.
    """
    total = 0
    for sc in bpy.data.scenes:
        tree = getattr(sc, "compositing_node_group", None) or getattr(sc, "node_tree", None)
        if tree is not None:
            total += len(tree.nodes)
    return total


def count_addons() -> int:
    prefs = getattr(bpy.context, "preferences", None)
    if prefs is None or not hasattr(prefs, "addons"):
        return 0
    return len(prefs.addons)


# --- Actions & keyframes --------------------------------------------------

def iter_action_fcurves(action):
    """Усі fcurves екшена: і legacy `action.fcurves`, і слот-екшени 4.4+
    (`layers[*].strips[*].channelbags[*].fcurves`).

    Обидва шляхи потрібні й не дублюються: у 4.4+ шаровий екшен віддає
    порожній `fcurves`, а вся анімація лежить у channelbag'ах; у legacy-екшенах
    навпаки. Перевірено в 5.2: 0 ключів у `fcurves` проти 9 у channelbag.
    """
    yield from getattr(action, "fcurves", ()) or ()
    for layer in getattr(action, "layers", ()) or ():
        for strip in getattr(layer, "strips", ()) or ():
            for cbag in getattr(strip, "channelbags", ()) or ():
                yield from getattr(cbag, "fcurves", ()) or ()


def count_keyframes(only_new: bool = False) -> int:
    """Загальна к-сть ключів у всіх екшенах.

    Рахує і legacy `action.fcurves`, і слот-екшени Blender 4.4+
    (`action.layers[*].strips[*].channelbags[*].fcurves`), інакше ключі,
    поставлені автокіфреймом у 5.2, не враховувались би.

    only_new=True → рахуємо лише в екшенах, створених цієї сесії (не з baseline).
    """
    base = state.baseline.get('actions') if (only_new and state.baseline is not None) else None
    total = 0
    for action in bpy.data.actions:
        if base is not None and action.name in base:
            continue
        for fc in iter_action_fcurves(action):
            total += len(fc.keyframe_points)
    return total


# --- Drivers --------------------------------------------------------------

def _norm_prop(path: str, index: int) -> str:
    """Нормалізує property-шлях до вигляду 'base[index]' для порівняння."""
    axis = {'.x': 0, '.y': 1, '.z': 2, '.w': 3, '.r': 0, '.g': 1, '.b': 2, '.a': 3}
    for suf, i in axis.items():
        if path.endswith(suf):
            return f"{path[:-2]}[{i}]"
    if path.endswith(']'):
        return path
    return f"{path}[{max(index, 0)}]"


def has_self_referencing_driver() -> bool:
    """True, якщо існує драйвер, змінна якого вказує на ту саму властивість (цикл)."""
    for db_list in (bpy.data.objects, bpy.data.materials, bpy.data.shape_keys,
                    bpy.data.node_groups, bpy.data.scenes):
        for item in db_list:
            ad = getattr(item, "animation_data", None)
            drivers = getattr(ad, "drivers", None) if ad else None
            if not drivers:
                continue
            for fc in drivers:
                drv = getattr(fc, "driver", None)
                if not drv:
                    continue
                driven = _norm_prop(fc.data_path, fc.array_index)
                for var in drv.variables:
                    for tgt in var.targets:
                        if getattr(tgt, "id", None) == item:
                            tpath = getattr(tgt, "data_path", "") or ""
                            if tpath and _norm_prop(tpath, 0) == driven:
                                return True
    return False


def detect_appended_this_session() -> bool:
    """True, якщо цієї сесії з'явився датаблок з бібліотеки (append/link)."""
    for kind, coll in (('objects', bpy.data.objects),
                       ('materials', bpy.data.materials),
                       ('node_groups', bpy.data.node_groups)):
        for db in coll:
            if is_new(kind, db.name) and (
                getattr(db, "library", None) is not None or
                getattr(db, "library_weak_reference", None) is not None):
                return True
    return False


# --- N-gons ---------------------------------------------------------------

# Межі для пошуку n-gon-ів у меші, який щойно змінили. Перевірка n-gon-а
# принципово вимагає подивитись на КОЖЕН полігон, тож на важких сценах вона
# може коштувати помітно. Обмежуємо двома способами: скануємо лише меші, які
# depsgraph позначив зміненими, і не частіше ніж раз на секунду.
NGON_MAX_POLYS_OBJECT = 5_000_000   # numpy-шлях, ~10 мс на мільйон
NGON_MAX_FACES_EDIT = 200_000       # bmesh значно повільніший за numpy


def mesh_has_ngon(mesh) -> bool:
    """Чи є в мешу грань із 10+ сторонами. numpy-шлях + кеш за к-стю полігонів."""
    polys = mesh.polygons
    n = len(polys)
    if not n:
        return False

    # Кеш: повторно скануємо лише якщо змінилася к-сть полігонів.
    cached = state.ngon_cache.get(mesh.name)
    if cached is not None and cached[0] == n:
        return cached[1]

    def _numpy_path():
        import numpy as np
        buf = np.empty(n, dtype=np.int32)
        polys.foreach_get("loop_total", buf)
        return bool((buf >= 10).any())

    def _pure_python_path():
        # Без numpy: дешевий ранній вихід, без матеріалізації всього меша.
        for p in polys:
            if p.loop_total >= 10:
                return True
        return False

    missing = object()
    verdict = debug.guarded_value("rules.probes:mesh_has_ngon/numpy", _numpy_path, missing)
    if verdict is missing:
        verdict = debug.guarded_value("rules.probes:mesh_has_ngon/pure", _pure_python_path, False)

    state.ngon_cache[mesh.name] = (n, verdict)
    return verdict


def has_ngon_new_mesh() -> bool:
    """True, якщо на мешу, створеному цієї сесії, є грань із 10+ сторонами."""
    for ob in bpy.data.objects:
        if ob.type == 'MESH' and ob.data and is_new('objects', ob.name):
            if mesh_has_ngon(ob.data):
                return True
    return False


def edit_mesh_has_ngon(me) -> bool:
    """N-gon у меші, який зараз редагується (me.polygons там застарілий)."""
    with debug.guarded("rules.probes:edit_mesh_has_ngon"):
        import bmesh
        bm = bmesh.from_edit_mesh(me)
        if len(bm.faces) > NGON_MAX_FACES_EDIT:
            return False
        for f in bm.faces:
            if len(f.verts) >= 10:
                return True
    return False


def scan_changed_for_ngon(meshes) -> bool:
    """N-gon серед щойно змінених мешів — працює і для вже наявних об'єктів.

    Раніше перевірялись лише меші, СТВОРЕНІ цієї сесії, тому грань на 10+
    вершин, зроблена всередині наявного меша, не зараховувалась.
    """
    now_t = time.time()
    if now_t - state.ngon_last_scan < 1.0:
        return False
    state.ngon_last_scan = now_t

    ob = bpy.context.active_object
    editing = ob.data if (ob is not None and ob.type == 'MESH'
                          and ob.mode == 'EDIT' and ob.data) else None
    for me in meshes:
        if me is editing:
            if edit_mesh_has_ngon(me):
                return True
        elif len(me.polygons) <= NGON_MAX_POLYS_OBJECT and mesh_has_ngon(me):
            return True
    return False


# --- Probe layer (memoized per evaluation pass) ---------------------------

@guarded_probe(0)
def drivers(ctx) -> int:
    return count_drivers()


@guarded_probe(0)
def fake_users(ctx) -> int:
    return count_fake_users()


@guarded_probe(0)
def addons(ctx) -> int:
    return count_addons()


@guarded_probe(0)
def compositor_nodes(ctx) -> int:
    return count_compositor_nodes()


@guarded_probe(0)
def materials_count(ctx) -> int:
    return len(bpy.data.materials)


@guarded_probe({})
def object_scan(ctx) -> dict:
    """Один прохід по bpy.data.objects, з якого живе кілька правил.

    Раніше це був зрощений вручну цикл у `_compute_scene_progress`, куди
    доводилось складати все, що інакше коштувало б окремого обходу сцени.
    Тепер зрощення робить кеш контексту, а правила лишаються окремими.

    polys      — сума полігонів усієї сцени (Polygon King: "in a single scene")
    bones      — найбільший риг, СТВОРЕНИЙ цієї сесії (панель інакше показувала
                 «120 / 100» на чужому ригу, який ніколи не дасть ачивку)
    autonamed  — авто-іменовані (`.001`) об'єкти цієї сесії
    """
    import re
    polys = bones = autonamed = 0
    auto_re = re.compile(r".*\.\d{3}$")
    for ob in bpy.data.objects:
        t = getattr(ob, "type", None)
        new = is_new('objects', ob.name)
        if t == 'MESH' and ob.data:
            polys += len(ob.data.polygons)
        elif t == 'ARMATURE' and ob.data and new:
            bones = max(bones, len(ob.data.bones))
        if new and auto_re.match(ob.name):
            autonamed += 1
    return {"polys": polys, "bones": bones, "autonamed": autonamed}


@guarded_probe({})
def material_scan(ctx) -> dict:
    """Один прохід по матеріалах, створених цієї сесії: найбільше дерево та
    найбільша к-сть Color Ramp у ньому."""
    max_nodes = max_ramps = 0
    for mat in bpy.data.materials:
        if not is_new('materials', mat.name):
            continue
        nt = getattr(mat, "node_tree", None)
        if nt:
            max_nodes = max(max_nodes, len(nt.nodes))
            max_ramps = max(max_ramps, sum(1 for n in nt.nodes
                                           if getattr(n, "type", "") == 'VALTORGB'))
    return {"max_nodes": max_nodes, "max_ramps": max_ramps}


@guarded_probe({})
def node_group_scan(ctx) -> dict:
    """Один прохід по нод-групах цієї сесії: найбільше дерево та найглибше
    вкладення груп."""
    max_nodes = max_nested = 0
    for ng in bpy.data.node_groups:
        if not is_new('node_groups', ng.name):
            continue
        max_nodes = max(max_nodes, len(ng.nodes))
        max_nested = max(max_nested, sum(1 for n in ng.nodes
                                         if getattr(n, "type", "") == 'GROUP'))
    return {"max_nodes": max_nodes, "max_nested": max_nested}


@probe
def biggest_node_tree(ctx) -> int:
    """Найбільше дерево цієї сесії — матеріал або нод-група (Node Spaghetti)."""
    return max(material_scan(ctx).get("max_nodes", 0),
               node_group_scan(ctx).get("max_nodes", 0))

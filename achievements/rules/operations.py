"""
The imperative half: achievements recognised from a *difference* between two
depsgraph passes, or from an event that leaves no trace in the scene at all.

No predicate over the current scene can see "100 objects were just joined" —
only "there is one object here now", which is equally true of a scene that
never had a hundred. So these are detected by diffing state across passes and
unlocked directly through `record_*`; they bind with `trigger=MANUAL` and
declare only `progress`, so the panel treats them like every other rule.

УВАГА: раніше тут жив опитувач `bpy.context.window_manager.operators`, який
мав ловити виклики операторів. Він не працює і працювати не може:
wm_operator_register() у Blender обмежує цей список константою
MAX_OP_REGISTERED і ЗВІЛЬНЯЄ найстаріші записи з голови, додаючи нові в
хвіст. Тобто довжина списку перестає рости після перших ~10 операторів
сесії, а вся логіка будувалась на "len() виріс — значить є нові".

Перевірено в Blender 5.2 наживо: `wm.operators` порожній (len == 0) навіть
після роботи в сесії, і ні EXEC-, ні INVOKE-виклики зі скрипта туди нічого
не додають. Тому `last_op` нижче — лише ДОДАТКОВЕ підтвердження там, де воно
випадково є; жодна ачивка не має залежати від нього одноосібно.

Кожна операція впізнається за характерним «слідом», який лишає:

    join            к-сть об'єктів впала, а СУМА вершин збереглась
    delete (Purge)  к-сть об'єктів впала РАЗОМ із сумою вершин
    merge           у меша впала к-сть вершин без видалення об'єктів
    cut             у меша в Edit Mode зросли і вершини, і ребра
    apply transform трансформ об'єкта став одиничним, а меш змінився
    flip normals    змінився знак орієнтації полігонів меша

Розрізнення join і delete за сумою вершин — принципове: раніше об'єднання
100 об'єктів через Ctrl+J зараховувало The Purge замість Frankenstein.
"""

import time

import bpy

from .. import debug
from ..registry import MANUAL, bind
from ..session import state
from . import probes

# depsgraph_update_post приходить десятки разів за секунду (одне перетягування
# об'єкта = злива оновлень), а частина перевірок детектора обходить усю сцену:
# сума вершин, скан бейк-кешів усіх модифікаторів, перевірка трансформів. Ці
# проходи не зобов'язані бути миттєвими — стан, який вони ловлять (запечений
# кеш, застосований трансформ), нікуди не дінеться до наступного тику, — тож
# крутимо їх не частіше ніж раз на _OP_FULL_SCAN_INTERVAL. Дешеві перевірки
# (лічильник об'єктів, змінені depsgraph'ом меші) лишаються на кожному оновленні.
_OP_FULL_SCAN_INTERVAL = 1.0   # с
_OP_GRAPH_CHECK_INTERVAL = 0.35  # с; рівно стільки ж триває вікно кредиту нижче,
                                 # тож частіші перевірки не додали б жодного бала

# Час останнього натискання K у Edit Mode. Ніж модальний: клавішу бачимо на
# початку, а зміна геометрії приходить лише після підтвердження різу, тож
# тримаємо вікно. Прапорець «згорає» після першого зарахування, щоб одне
# натискання не приписало ножу всі наступні правки.
_KNIFE_ARM_WINDOW = 120.0

JOIN_TARGET = 100
KNIFE_TARGET = 20
MERGE_TARGET = 100
GRAPH_TWEAK_TARGET = 100
APPLY_TARGET = 20
UNDO_TARGET = 30
SHORTCUT_TARGET = 15
BAKE_FRAMES_TARGET = 250
PURGE_TARGET = 100


# --- Operator / manual event tracking API ---------------------------------

def _engine():
    # Імпорт усередині функції: engine.py тягне registry, а не rules, тож
    # модульний імпорт замкнув би коло на етапі завантаження аддона.
    from ..engine import get_engine
    return get_engine()


def record_object_join(count: int = 100):
    eng = _engine()
    if count > state.max_join_count:
        state.max_join_count = count
    if not eng.is_unlocked("FATAL_CTRL_J") and count >= JOIN_TARGET:
        eng.unlock("FATAL_CTRL_J")


def record_normals_flipped():
    eng = _engine()
    if not eng.is_unlocked("INVERTED_REALITY"):
        eng.unlock("INVERTED_REALITY")


def record_knife_cut(count: int = 1):
    eng = _engine()
    if not eng.is_unlocked("KNIFE_MASTER"):
        state.knife_cut_count += count
        if state.knife_cut_count >= KNIFE_TARGET:
            eng.unlock("KNIFE_MASTER")


def record_merge_by_distance(delta_vertices: int):
    eng = _engine()
    if delta_vertices > state.max_merge_count:
        state.max_merge_count = delta_vertices
    if not eng.is_unlocked("MERGE_MASTER") and delta_vertices >= MERGE_TARGET:
        eng.unlock("MERGE_MASTER")


def record_graph_tweak(count: int = 1):
    eng = _engine()
    if not eng.is_unlocked("GRAPH_EDITOR_TWEAKER"):
        state.graph_tweaks += count
        if state.graph_tweaks >= GRAPH_TWEAK_TARGET:
            eng.unlock("GRAPH_EDITOR_TWEAKER")


def record_bake(frame_count: int):
    eng = _engine()
    eng.add_stat("bakes_total", 1)          # Bake Sale (global)
    if not eng.is_unlocked("THE_BIG_BAKE") and frame_count > BAKE_FRAMES_TARGET:
        eng.unlock("THE_BIG_BAKE")


def record_undo():
    eng = _engine()
    eng.add_stat("undos_total", 1)          # Un Un Un Undo (global)
    if not eng.is_unlocked("CTRL_Z_HERO"):
        now = time.time()
        state.undo_timestamps.append(now)
        state.undo_timestamps = [t for t in state.undo_timestamps if now - t <= 60.0]
        # Поріг 30, а не круглі 50: типовий ліміт Blender (Edit > Preferences >
        # System > Undo Steps) — 32 кроки. Поріг вище цього значення довелось
        # би тримати одразу кілька дій в undo-стеку одночасно, чого одинока
        # серія Ctrl+Z фізично не дає — ачивка була недосяжна за замовчуванням.
        if len(state.undo_timestamps) >= UNDO_TARGET:
            eng.unlock("CTRL_Z_HERO")


def record_shortcut_used(shortcut_id: str):
    eng = _engine()
    if not eng.is_unlocked("SHORTCUT_NINJA"):
        now = time.time()
        state.shortcut_timestamps.append((now, shortcut_id))
        state.shortcut_timestamps = [(t, sid) for t, sid in state.shortcut_timestamps
                                     if now - t <= 60.0]
        if len({sid for _, sid in state.shortcut_timestamps}) >= SHORTCUT_TARGET:
            eng.unlock("SHORTCUT_NINJA")


def record_transform_apply(count: int = 1):
    eng = _engine()
    if not eng.is_unlocked("APPLY_ALL"):
        state.applied_objects_count += count
        if state.applied_objects_count >= APPLY_TARGET:
            eng.unlock("APPLY_ALL")


def trigger_vram_error():
    eng = _engine()
    if not eng.is_unlocked("VRAM_VICTIM"):
        eng.unlock("VRAM_VICTIM")


# --- Mesh / action measurement helpers ------------------------------------

def _action_signature(act):
    """Підпис одного екшена — (к-сть ключів, сума координат) — або None.

    Кількість ключів + сума їхніх координат: цього досить, щоб побачити
    зсув ключа, і не треба обходити кожен хендл окремо.

    Буфер один на всі виклики: на ригу це тисячі f-curve, і окреме
    np.empty() під кожну давало тисячі аллокацій за прохід.
    """
    import numpy as np
    total = 0
    acc = 0.0
    for fc in probes.iter_action_fcurves(act):
        n = len(fc.keyframe_points)
        if not n:
            continue
        need = n * 2
        if state.kf_buf is None or state.kf_buf.size < need:
            state.kf_buf = np.empty(need, dtype=np.float32)
        buf = state.kf_buf[:need]
        fc.keyframe_points.foreach_get("co", buf)
        total += n
        acc += float(buf.sum())
    if total == 0:
        return None
    return (total, round(acc, 4))


def _updated_actions(depsgraph):
    """Екшени, яких могло торкнутись саме це оновлення depsgraph.

    Обходити bpy.data.actions цілком не можна: у файлі аніматора їх десятки
    (кожен дубль пози — окремий екшен із fake user), а перетягування ключа
    чіпає рівно один. Виміряно: 10 екшенів на 60-кістковому ригу — 20 мс на
    прохід, тобто ~100 мс/с при перевірці 5 разів на секунду. Саме через це
    Graph Editor лагав на G. Беремо лише ті екшени, чиї власники прийшли в
    updates.
    """
    acts = []
    seen = set()

    def add(ad):
        act = getattr(ad, "action", None)
        if act is not None and act.name not in seen:
            seen.add(act.name)
            acts.append(act)

    with debug.guarded("rules.operations:_updated_actions"):
        for upd in getattr(depsgraph, "updates", ()) or ():
            idp = getattr(upd, "id", None)
            if idp is None:
                continue
            orig = getattr(idp, "original", idp)
            add(getattr(orig, "animation_data", None))
            data = getattr(orig, "data", None)
            if data is not None:
                add(getattr(data, "animation_data", None))
                keys = getattr(data, "shape_keys", None)
                if keys is not None:
                    add(getattr(keys, "animation_data", None))
    return acts


def _graph_editor_open() -> bool:
    try:
        for w in bpy.context.window_manager.windows:
            for a in w.screen.areas:
                if a.type == 'GRAPH_EDITOR':
                    return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _total_mesh_verts() -> int:
    """Сума вершин мешів, ПРИВ'ЯЗАНИХ до об'єктів.

    Свідомо не рахуємо bpy.data.meshes: після видалення об'єктів їхні меші
    ще лишаються осиротілими в файлі, сума не падає — і видалення виглядало
    б як join (геометрія ніби збереглась). Рахунок по об'єктах падає одразу.
    """
    return sum(len(ob.data.vertices) for ob in bpy.data.objects
               if ob.type == 'MESH' and ob.data)


def _mesh_counts(me):
    """(verts, edges, polys) меша; в Edit Mode читаємо живий bmesh, бо
    me.vertices там ще не оновлений.

    Полігони потрібні, щоб відрізнити Merge by Distance від видалення вершин:
    зварювання суміщених вершин грані здебільшого зберігає, видалення — забирає
    разом з вершинами.
    """
    def _compute():
        ob = bpy.context.active_object
        if (ob is not None and ob.mode == 'EDIT' and ob.type == 'MESH'
                and ob.data is me):
            import bmesh
            bm = bmesh.from_edit_mesh(me)
            return (len(bm.verts), len(bm.edges), len(bm.faces))
        return (len(me.vertices), len(me.edges), len(me.polygons))
    return debug.guarded_value("rules.operations:_mesh_counts", _compute, None)


def _editing_mesh():
    """Меш, який зараз у режимі редагування, або None."""
    try:
        ob = bpy.context.active_object
        if ob is not None and ob.type == 'MESH' and ob.mode == 'EDIT':
            return ob.data
    except Exception:  # noqa: BLE001
        pass
    return None


def _mesh_orientation(me):
    """Сума dot(нормаль, центр) по полігонах, або None.

    Перевертання нормалей міняє напрямок обходу петель, а отже й знак цієї
    суми. Дає дешевий спосіб побачити Shift+N / flip без доступу до самого
    оператора.

    Повертаємо саме число, а не лише знак: справжній flip перевертає КОЖНУ
    нормаль, тож сума міняється на майже точно протилежну. Зміна знака сама
    по собі надто слабкий сигнал — його дає й звичайне посування вершин.
    """
    def _compute():
        n = len(me.polygons)
        if n == 0:
            return None
        import numpy as np
        nor = np.empty(n * 3, dtype=np.float32)
        cen = np.empty(n * 3, dtype=np.float32)
        me.polygons.foreach_get("normal", nor)
        me.polygons.foreach_get("center", cen)
        s = float(np.dot(nor, cen))
        if abs(s) < 1e-6:
            return None
        return s
    return debug.guarded_value("rules.operations:_mesh_orientation", _compute, None)


def is_normal_flip(prev_s, cur_s) -> bool:
    """Чи виглядає пара замірів як перевертання нормалей.

    Вимагаємо, щоб нова сума була майже точно протилежною до старої: flip
    інвертує кожну нормаль, тож |s_new + s_old| мізерна проти |s_old|.
    Посування вершин теж міняє суму, але випадково потрапити в дзеркальне
    значення з допуском 2% практично неможливо.
    """
    if prev_s is None or cur_s is None:
        return False
    if (prev_s > 0) == (cur_s > 0):
        return False
    return abs(cur_s + prev_s) <= 0.02 * abs(prev_s)


def _is_identity_transform(ob) -> bool:
    try:
        return (tuple(round(v, 4) for v in ob.location) == (0.0, 0.0, 0.0)
                and tuple(round(v, 4) for v in ob.scale) == (1.0, 1.0, 1.0)
                and all(abs(v) < 1e-4 for v in ob.rotation_euler))
    except Exception:  # noqa: BLE001
        return False


# --- Object add/remove diff (cubes, monkeys) ------------------------------

_NON_CUBE_MESH_PREFIXES = ("sphere", "plane", "cylinder", "monkey", "torus",
                           "cone", "circle", "icosphere")


def detect_object_changes(ctx):
    """Порівнює знімок об'єктів із попереднім проходом.

    Кладе в `ctx.extra` факти, які самі по собі зі стану сцени не читаються
    (`deleted_cubes`, `new_monkeys`) — їх споживають правила в `basics.py`, —
    і одразу доливає глобальні лічильники, бо ті ростуть незалежно від того,
    чи відповідні ачивки вже відкриті.
    """
    if probes.ensure_snapshot():
        return      # перший знімок цієї сесії: порівнювати ще нема з чим

    with debug.guarded("rules.operations:detect_object_changes"):
        eng = ctx.eng
        current = probes.snapshot_objects()
        prev_names = set(state.known_objects.keys())
        cur_names = set(current.keys())
        removed_names = prev_names - cur_names
        added_names = cur_names - prev_names
        current_mesh_names = {info["mesh_name"] for info in current.values()}

        # Deleted default cubes → GOODBYE_CUBE (session) + Cube Genocide (global)
        deleted_cubes = 0
        for name in removed_names:
            info = state.known_objects.get(name)
            if not info or info.get("type") != 'MESH':
                continue
            mesh_name = info.get("mesh_name", "")
            if mesh_name in current_mesh_names:
                continue
            obj_name = info.get("name", "")
            is_cube = mesh_name.lower().startswith("cube") or (
                obj_name.lower().startswith("cube") and not any(
                    mesh_name.lower().startswith(other)
                    for other in _NON_CUBE_MESH_PREFIXES
                )
            )
            if is_cube:
                deleted_cubes += 1
        if deleted_cubes:
            eng.add_stat("cubes_deleted", deleted_cubes)

        # Newly added monkeys → SUZANNES_BLESSING (session) + Monkey Business (global)
        new_monkeys = 0
        for name in added_names:
            ob = bpy.data.objects.get(name)
            if ob and getattr(ob, "type", None) == 'MESH' and ob.data:
                n_low = ob.name.lower()
                m_low = ob.data.name.lower()
                if ("suzanne" in n_low or "monkey" in n_low
                        or "suzanne" in m_low or "monkey" in m_low):
                    new_monkeys += 1
        if new_monkeys:
            eng.add_stat("suzannes_added", new_monkeys)

        ctx.extra["deleted_cubes"] = deleted_cubes
        ctx.extra["new_monkeys"] = new_monkeys
        state.known_objects = current


# --- Scene-diff operation detector ----------------------------------------

def detect_operations(ctx):
    """Впізнає виконані операції за різницею стану. Викликається з
    depsgraph_update_post. Сканує лише меші, які depsgraph позначив
    зміненими, тож вартість не залежить від розміру сцени.

    Публікує список змінених мешів у `ctx.extra["changed_meshes"]` — на ньому
    працює правило N-gon Criminal.
    """
    eng = ctx.eng
    scene = ctx.scene
    depsgraph = ctx.depsgraph
    if scene is None:
        return

    # Чи дозволені цього разу проходи по всій сцені (див. _OP_FULL_SCAN_INTERVAL).
    # Після undo/redo ресинк робимо повним, інакше база лишиться від старого стану.
    now_mono = time.monotonic()
    full_scan = state.op_resync or (now_mono - state.op_last_full_scan) >= _OP_FULL_SCAN_INTERVAL
    if full_scan:
        state.op_last_full_scan = now_mono

    # Після undo/redo сцена стрибає назад, і різниця стану виглядає як
    # справжня операція: скасований Ctrl+J зменшує к-сть вершин рівно так
    # само, як Merge by Distance. Тому перший прохід після скасування лише
    # перезаписує базу, нічого не зараховуючи.
    resync = state.op_resync
    state.op_resync = False

    # Вихід з Edit Mode. Нормалі перевертають саме там, а меш під редагуванням
    # для заміру орієнтації пропускається, тож момент виходу — єдина точка, де
    # flip взагалі можна побачити. Чекати на періодичний повний скан не можна:
    # після виходу оновлення depsgraph припиняються, і скан може не настати.
    editing_now = _editing_mesh()
    left_edit = state.op_prev_editing if state.op_prev_editing is not editing_now else None
    state.op_prev_editing = editing_now

    last_op = ""
    try:
        ops = bpy.context.window_manager.operators
        if ops:
            last_op = ops[-1].bl_idname
    except Exception:
        pass

    # ---- об'єкти: join проти масового видалення
    # len(bpy.data.objects) дешевий, а сума вершин — прохід по всій сцені. Поки
    # к-сть об'єктів не змінилась, ані join, ані видалення статися не могло, тож
    # суму перераховуємо лише на зміні лічильника або на періодичному повному
    # скані (щоб база не застоювалась після правок геометрії).
    with debug.guarded("rules.operations:detect/objects"):
        cur_objs = len(bpy.data.objects)
        if state.op_prev_obj_count is None or cur_objs != state.op_prev_obj_count or full_scan:
            cur_meshes = sum(1 for ob in bpy.data.objects if ob.type == 'MESH')
            cur_verts = _total_mesh_verts()
            if state.op_prev_obj_count is not None:
                gone = state.op_prev_obj_count - cur_objs
                if gone > 0 and not resync:
                    lost = (state.op_prev_total_verts or 0) - cur_verts
                    meshes_gone = (state.op_prev_mesh_count or 0) - cur_meshes
                    # join зберігає геометрію (втрати < 5% від наявної),
                    # видалення забирає її разом з об'єктами.
                    # Важливо: якщо серед зниклих об'єктів НЕМАЄ мешів
                    # (meshes_gone <= 0 — видалили Empties, камери, світло),
                    # це точно НЕ join.
                    # Перевірки на last_op тут НЕМАЄ свідомо: wm.operators
                    # порожній завжди (див. шапку модуля), тож умова була
                    # тотожно хибною — join не зараховувався ніколи, а Ctrl+J
                    # на 100+ об'єктах натомість видавав The Purge.
                    joined = (meshes_gone > 0
                              and lost <= max(8, int(cur_verts * 0.05)))
                    if joined:
                        record_object_join(count=gone + 1)
                    elif gone >= PURGE_TARGET and not eng.is_unlocked("THE_PURGE"):
                        eng.unlock("THE_PURGE")
            state.op_prev_obj_count = cur_objs
            state.op_prev_mesh_count = cur_meshes
            state.op_prev_total_verts = cur_verts

    # ---- меші: merge / cut / flip normals
    # Список живе поза try: ним користується ще й детектор Ctrl+A нижче, і
    # виняток тут не повинен лишати його невизначеним.
    changed = []
    with debug.guarded("rules.operations:detect/meshes"):
        for upd in getattr(depsgraph, "updates", ()):
            idp = getattr(upd, "id", None)
            if idp is None or not getattr(upd, "is_updated_geometry", False):
                continue
            orig = getattr(idp, "original", idp)
            if isinstance(orig, bpy.types.Mesh):
                changed.append(orig)
            elif isinstance(orig, bpy.types.Object) and orig.type == 'MESH' and orig.data:
                changed.append(orig.data)

        for me in changed:
            cur = _mesh_counts(me)
            if cur is None:
                continue
            prev = state.op_mesh_counts.get(me.name)
            state.op_mesh_counts[me.name] = cur

            if prev is not None and not resync:
                d_v = cur[0] - prev[0]
                d_e = cur[1] - prev[1]
                # Злиття вершин: вершин поменшало, об'єкти не зникали.
                #
                # Кількість граней у ролі розрізняча не годиться: зварювання
                # двох суміщених копій прибирає і здубльовані грані, тож втрата
                # граней там навіть більша, ніж при видаленні. Тому лишаємо
                # правило зі старої реалізації (менше вершин при незмінній
                # кількості об'єктів) і додаємо дві дешеві межі:
                #  • Merge by Distance живе лише в Edit Mode — це відсікає
                #    падіння лічильника від застосованих модифікаторів;
                #  • після зварювання меш лишається мешем, а не порожнечею —
                #    «виділити все й видалити» сюди більше не потрапляє.
                if (d_v < 0 and cur[0] > 0 and cur[2] > 0
                        and (me is editing_now or me is left_edit)
                        and state.op_prev_obj_count == len(bpy.data.objects)):
                    record_merge_by_distance(delta_vertices=-d_v)
                # розріз: додались і вершини, і ребра.
                # Сама по собі ця сигнатура збігається і з extrude, і з loop
                # cut, і з subdivide, тому потрібне підтвердження, що це
                # справді ніж: або ім'я оператора (якщо воно раптом є), або
                # свіже натискання K у Edit Mode.
                elif d_v > 0 and d_e > 0:
                    if last_op in ("MESH_OT_knife_tool", "MESH_OT_knife_project"):
                        record_knife_cut(count=1)
                    elif (state.knife_armed_at
                          and time.time() - state.knife_armed_at <= _KNIFE_ARM_WINDOW):
                        state.knife_armed_at = 0.0      # одне натискання = один різ
                        record_knife_cut(count=1)

            # Орієнтацію міряємо ЛИШЕ поза Edit Mode: me.polygons під час
            # редагування застарілий, тож у едіті ми бачили стан ДО правки, а
            # після виходу — після неї. Два такі заміри з однаковими
            # лічильниками виглядали як перевертання нормалей, і extrude з
            # наступним merge by distance хибно давав ачивку.
            # Сам замір орієнтації — numpy-прохід по ВСІХ полігонах меша (на
            # 20k полігонів це ~3 мс). Меш, деформований арматурою, приходить
            # у depsgraph.updates із is_updated_geometry на КОЖНОМУ обчисленні
            # анімації, тож без фільтра перетягування одного ключа в Graph
            # Editor коштувало 60 таких проходів за секунду — саме через це
            # редактор лагав. Тому міряємо лише тоді, коли замір може щось
            # означати: на виході з Edit Mode (там і перевертають), на зміні
            # топології та раз на _OP_FULL_SCAN_INTERVAL, щоб база не старіла.
            counts_changed = (prev is None or prev != cur)
            if (not eng.is_unlocked("INVERTED_REALITY") and not resync
                    and me is not editing_now
                    and (full_scan or counts_changed or me is left_edit)):
                sign = _mesh_orientation(me)
                if sign is not None:
                    # Запам'ятовуємо орієнтацію РАЗОМ із лічильниками того ж
                    # заміру. Лічильники оновлюються і в Edit Mode, а
                    # орієнтація — ні, тож порівняння з "поточними" даними
                    # зіставляло різні моменти часу.
                    prev_rec = state.op_mesh_orient.get(me.name)
                    state.op_mesh_orient[me.name] = (sign, cur)
                    prev_sign = prev_rec[0] if prev_rec else None
                    prev_counts = prev_rec[1] if prev_rec else None
                    # Дві умови разом, і кожна потрібна:
                    #  • is_normal_flip — нова сума майже точно протилежна до
                    #    старої, тобто перевернулась КОЖНА нормаль. Саме лише
                    #    змінення знака давало хибні спрацювання від посування
                    #    вершин.
                    #  • лічильники збіглися — flip не додає й не прибирає
                    #    геометрію, а extrude з наступним merge by distance
                    #    інакше проходив би як перевертання.
                    if is_normal_flip(prev_sign, sign) and prev_counts == cur:
                        record_normals_flipped()

    # Змінені меші потрібні правилу N-gon Criminal (див. rules/modeling.py).
    ctx.extra["changed_meshes"] = changed

    # ---- правки кривих у Graph Editor
    # Рахуємо ЗМІНУ САМИХ КЛЮЧІВ, а не оновлення depsgraph: за одне
    # перетягування ключа depsgraph шле десятки оновлень, і лічильник
    # стрибав на +21 за один рух. Запікання симуляції теж штовхає depsgraph,
    # але ключів не чіпає — тому воно більше сюди не зараховується.
    with debug.guarded("rules.operations:detect/graph"):
        if (not eng.is_unlocked("GRAPH_EDITOR_TWEAKER")
                and (now_mono - state.op_graph_checked) >= _OP_GRAPH_CHECK_INTERVAL
                and _graph_editor_open()):
            state.op_graph_checked = now_mono
            # Підпис тримаємо ОКРЕМО ПО КОЖНОМУ екшену, а не одним числом на
            # весь файл: рахується лише те, що прийшло в updates, і набір
            # екшенів різниться між проходами — спільна сума стрибала б від
            # самої зміни набору й давала хибні зарахування.
            moved = False
            for act in _updated_actions(depsgraph):
                sig = _action_signature(act)
                if sig is None:
                    continue
                prev_sig = state.op_graph_sig.get(act.name)
                if prev_sig is not None and prev_sig != sig and not resync:
                    moved = True
                state.op_graph_sig[act.name] = sig
            if moved:
                now_t = time.time()
                if now_t - state.op_graph_last >= 0.35:   # один рух = один бал
                    state.op_graph_last = now_t
                    record_graph_tweak(count=1)

    # ---- завершені бейки фізики (Let it cook / Bake Sale)
    # Прохід по всіх модифікаторах сцени: робимо його лише на повному скані і
    # лише поки є що вигравати. Запечений кеш не «розпікається» сам, тож
    # перехід False -> True не загубиться від затримки в секунду.
    bake_done = eng.is_unlocked("THE_BIG_BAKE") and eng.is_unlocked("BAKE_SALE")
    with debug.guarded("rules.operations:detect/bake"):
        if full_scan and not bake_done:
            for ob in scene.objects:
                for mod in getattr(ob, "modifiers", ()):
                    key = f"{ob.name}/{mod.name}"
                    ds = getattr(mod, "domain_settings", None)
                    if ds is not None:
                        # Fluid-домен НЕ має point_cache — у нього власний кеш
                        # (has_cache_baked_data / cache_frame_start / _end), тому
                        # запікання води раніше не зараховувалось узагалі.
                        baked = bool(getattr(ds, "has_cache_baked_data", False) or
                                     getattr(ds, "has_cache_baked_mesh", False))
                        f0 = int(getattr(ds, "cache_frame_start", scene.frame_start))
                        f1 = int(getattr(ds, "cache_frame_end", scene.frame_end))
                    else:
                        cache = getattr(mod, "point_cache", None)   # cloth, softbody
                        if cache is None:
                            continue
                        baked = bool(getattr(cache, "is_baked", False))
                        f0 = int(getattr(cache, "frame_start", scene.frame_start))
                        f1 = int(getattr(cache, "frame_end", scene.frame_end))
                    was = state.op_bake_state.get(key)
                    state.op_bake_state[key] = baked
                    if baked and was is False:
                        record_bake(frame_count=max(0, f1 - f0))

    # ---- бейк ригід-боді (кеш живе у сцені, а не в модифікаторі)
    with debug.guarded("rules.operations:detect/rbbake"):
        rbw = getattr(scene, "rigidbody_world", None)
        pc = getattr(rbw, "point_cache", None) if (rbw and not bake_done) else None
        if pc is not None:
            baked = bool(getattr(pc, "is_baked", False))
            was = state.op_bake_state.get("__rigidbody__")
            state.op_bake_state["__rigidbody__"] = baked
            if baked and was is False:
                record_bake(frame_count=max(0, int(pc.frame_end) - int(pc.frame_start)))

    # ---- застосування трансформу (Ctrl+A)
    # Ще один прохід по всій сцені, тож у спокійному стані крутимо його раз на
    # _OP_FULL_SCAN_INTERVAL, аби тримати базу «чи був трансформ одиничним»
    # свіжою; коли ж прийшли оновлення геометрії — рахуємо одразу.
    #
    # Умови last_op == "OBJECT_OT_transform_apply" тут НЕМАЄ: вона тотожно
    # хибна (wm.operators завжди порожній), через що ачивка не видавалась
    # ніколи. Замість неї — точніший сигнал: Ctrl+A ВПІКАЄ трансформ у
    # координати вершин, тож меш приходить у depsgraph.updates із
    # is_updated_geometry. Alt+G / Alt+R / Alt+S просто обнуляють трансформ,
    # не чіпаючи меш, — і сюди більше не потрапляють.
    with debug.guarded("rules.operations:detect/xform"):
        if not eng.is_unlocked("APPLY_ALL") and (full_scan or changed):
            changed_meshes = {m.name for m in changed}
            applied = 0
            for ob in scene.objects:
                if ob.type != 'MESH':
                    continue
                now_id = _is_identity_transform(ob)
                was_id = state.op_xform_identity.get(ob.name)
                state.op_xform_identity[ob.name] = now_id
                if was_id is False and now_id and not resync:
                    if ob.data is not None and ob.data.name in changed_meshes:
                        applied += 1
            if applied:
                record_transform_apply(count=applied)


# --- Cache pruning --------------------------------------------------------

# Кеші детектора ключуються ІМЕНАМИ датаблоків і самі про видалення не
# дізнаються. Довга сесія з масовим створенням/видаленням об'єктів роздувала б
# їх без меж, а повторно використане ім'я ("Cube" після видалення старого
# "Cube") ще й порівнювалося б із чужими лічильниками. Прибираємо записи, яким
# більше не відповідає жоден датаблок.
_OP_CACHE_PRUNE_THRESHOLD = 256   # нижче цього чистити нема сенсу


def prune_caches():
    """Викидає з кешів детектора записи неіснуючих мешів/об'єктів."""
    with debug.guarded("rules.operations:prune_caches"):
        total = (len(state.op_mesh_counts) + len(state.op_mesh_orient)
                 + len(state.op_xform_identity) + len(state.op_bake_state)
                 + len(state.ngon_cache))
        if total < _OP_CACHE_PRUNE_THRESHOLD:
            return
        mesh_names = {me.name for me in bpy.data.meshes}
        obj_names = {ob.name for ob in bpy.data.objects}
        for cache, live in ((state.op_mesh_counts, mesh_names),
                            (state.op_mesh_orient, mesh_names),
                            (state.ngon_cache, mesh_names),
                            (state.op_xform_identity, obj_names)):
            for key in [k for k in cache if k not in live]:
                del cache[key]
        # ключі виду "<object>/<modifier>" (+ службовий "__rigidbody__")
        for key in [k for k in state.op_bake_state
                    if not k.startswith("__") and k.split("/", 1)[0] not in obj_names]:
            del state.op_bake_state[key]


# --- Bindings -------------------------------------------------------------
# MANUAL: розблоковують `record_*` вище. `progress` тут — щоб панель показувала
# ті самі числа, з якими працює детектор.

bind("FATAL_CTRL_J", MANUAL, target=JOIN_TARGET,
     progress=lambda ctx: state.max_join_count)
bind("MERGE_MASTER", MANUAL, target=MERGE_TARGET,
     progress=lambda ctx: state.max_merge_count)
bind("KNIFE_MASTER", MANUAL, target=KNIFE_TARGET,
     progress=lambda ctx: state.knife_cut_count)
bind("GRAPH_EDITOR_TWEAKER", MANUAL, target=GRAPH_TWEAK_TARGET,
     progress=lambda ctx: state.graph_tweaks)
bind("APPLY_ALL", MANUAL, target=APPLY_TARGET,
     progress=lambda ctx: state.applied_objects_count)
bind("CTRL_Z_HERO", MANUAL, target=UNDO_TARGET,
     progress=lambda ctx: sum(1 for t in state.undo_timestamps
                              if time.time() - t <= 60.0))
bind("SHORTCUT_NINJA", MANUAL, target=SHORTCUT_TARGET,
     progress=lambda ctx: len({sid for t, sid in state.shortcut_timestamps
                               if time.time() - t <= 60.0}))
bind("INVERTED_REALITY", MANUAL)
bind("THE_PURGE", MANUAL)
bind("THE_BIG_BAKE", MANUAL)
bind("VRAM_VICTIM", MANUAL)

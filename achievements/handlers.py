"""
Event plumbing: Blender's callbacks in, rule evaluations out.

Every handler here does the same three things — refresh whatever bookkeeping
its event implies, build a `RuleContext`, and fire one trigger. Which
achievements that trigger reaches is not this module's business; that lives in
`registry.py` (the table) and `rules/` (the checks). The old version of this
file had to be edited in three places to add one achievement — a definition, a
check inside the right handler, and the id in the right short-circuit set.

Also here, because they're plumbing rather than rules: the keyboard watcher's
state, the stdout capture that catches Cycles' out-of-VRAM error, the periodic
timer's global counters, and register/unregister.
"""

import os
import re
import tempfile
import time

import bpy
from bpy.app.handlers import persistent

from . import debug
from . import registry
from . import rules
from .rules import operations, probes
from .rules.context import RuleContext
from .session import TIMER_INTERVAL, TIMER_TICK, reset_tracking_state, state


def _engine():
    from .engine import get_engine
    return get_engine()


def _context(scene=None, depsgraph=None, **extra) -> RuleContext:
    return RuleContext(_engine(), scene=scene, depsgraph=depsgraph, **extra)


# --- Background keyboard watcher ------------------------------------------
# Модальний оператор лишився виключно заради клавіатури — там події справжні.
# Усе інше визначається за зміною стану сцени (див. rules/operations.py).

# Якщо модальна копія гине не через _stop() (перезавантаження файлу, виняток
# у Blender), прапорець лишався б True назавжди — і watcher_instance_start()
# блокував би будь-який новий запуск. Тому вважаємо копію мертвою, якщо вона
# давно не бачила подій, і дозволяємо перезапуск.
_WATCHER_STALE_AFTER = 15.0

_SHORTCUT_IGNORE_TYPES = {
    'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE', 'NONE', 'WINDOW_DEACTIVATE',
    'LEFTMOUSE', 'RIGHTMOUSE', 'MIDDLEMOUSE',
    'BUTTON4MOUSE', 'BUTTON5MOUSE', 'BUTTON6MOUSE', 'BUTTON7MOUSE',
    'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'WHEELINMOUSE', 'WHEELOUTMOUSE',
    'TIMER', 'TIMER0', 'TIMER1', 'TIMER2', 'TIMER_JOBS', 'TIMER_AUTOSAVE', 'TIMER_REPORT',
}


def start_watcher():
    state.watcher_running = True


def stop_watcher():
    state.watcher_running = False
    # Не скидаємо state.watcher_instance_active тут: жива modal-копія сама зробить
    # це в _stop(), коли побачить state.watcher_running=False на наступній події.


def is_watcher_running() -> bool:
    return state.watcher_running


def watcher_is_stale() -> bool:
    """True, якщо позначена активною копія давно не подавала ознак життя."""
    if not state.watcher_instance_active:
        return False
    return (time.time() - state.watcher_heartbeat) > _WATCHER_STALE_AFTER


def watcher_instance_start() -> bool:
    """Захист від подвійного запуску modal-оператора (напр. швидке
    вимкнути/увімкнути аддон). True — можна стартувати; False — вже є жива копія."""
    if state.watcher_instance_active and not watcher_is_stale():
        return False
    state.watcher_instance_active = True
    state.watcher_heartbeat = time.time()
    return True


def watcher_needs_launch() -> bool:
    """Чи треба піднімати нову модальну копію."""
    return (not state.watcher_instance_active) or watcher_is_stale()


def watcher_instance_stop():
    state.watcher_instance_active = False


def watcher_heartbeat():
    """Позначка, що модальна копія жива (шлеться раз на секунду)."""
    state.watcher_heartbeat = time.time()


def watcher_key_event(event):
    """Реєструє клавіатурний шорткат для Shortcut Ninja (лише клавіатура,
    без відкриття мишею меню — тому клавіші миші й колесо виключені), а заодно
    «зводить» детектор ножа на натисканні K у Edit Mode."""
    state.watcher_heartbeat = time.time()
    if not state.watcher_running:
        return
    # Будь-яке натискання (клавіша, кнопка миші, колесо) = людина за кермом.
    # Раніше безділля скидали лише depsgraph / зміна кадру / рендер, тож
    # орбіта в'юпорта, зміна режиму й гортання меню рахувались як 4 години
    # нічогонероблення і видавали "What am I doing?" посеред роботи.
    # MOUSEMOVE сюди не доходить (у нього value == 'NOTHING'), і це навмисне:
    # зсунута мишею не вважається активністю.
    state.idle_seconds = 0
    with debug.guarded("handlers.py:watcher_key_event"):
        if event.value != 'PRESS' or event.type in _SHORTCUT_IGNORE_TYPES:
            return
        # Ніж модальний, тож у wm.operators не потрапляє ніколи (див. шапку
        # rules/operations.py). Реальна подія клавіатури — єдиний доступний нам
        # сигнал, що ніж узагалі викликали. Саме зарахування робить детектор,
        # коли побачить характерну зміну геометрії.
        if event.type == 'K' and not (event.ctrl or event.alt or event.oskey):
            try:
                if bpy.context.mode == 'EDIT_MESH':
                    state.knife_armed_at = time.time()
            except Exception:  # noqa: BLE001
                pass
        mods = ''.join(m for m, flag in (
            ('C', event.ctrl), ('A', event.alt), ('S', event.shift), ('O', event.oskey)
        ) if flag)
        operations.record_shortcut_used(f"{mods}:{event.type}")


# --- Depsgraph ------------------------------------------------------------

@persistent
def on_depsgraph_update(scene, depsgraph):
    """Об'єкти, модифікатори, ноди, скелети, частинки й світло — усе, що
    змінює сцену."""
    probes.ensure_baseline()   # зафіксувати стан сесії, щоб рахувати лише нове
    state.idle_seconds = 0     # будь-яка зміна сцени = активність
    # Сцена змінилась -> сканувальна частина прогресу для панелі застаріла.
    state.progress_scene_dirty = True

    ctx = _context(scene, depsgraph)
    # Детектори першими: вони кладуть у ctx.extra факти (видалені куби, додані
    # мавпи, змінені меші), яких у самому стані сцени вже/ще немає.
    operations.detect_object_changes(ctx)
    operations.detect_operations(ctx)
    rules.evaluate(registry.DEPSGRAPH, ctx)


# --- Frame change ---------------------------------------------------------

@persistent
def on_frame_change_post(scene, depsgraph=None):
    state.idle_seconds = 0    # відтворення/зміна кадру = активність
    rules.evaluate(registry.FRAME_CHANGE, _context(scene, depsgraph))


# --- Render ---------------------------------------------------------------

@persistent
def on_render_init(scene):
    state.render_start_time = time.time()
    state.rendered_frames_count = 0
    state.motion_blur_active_at_render_start = getattr(scene.render, "use_motion_blur", False)
    state.idle_seconds = 0    # рендер = активність
    oom_capture_start()  # слухаємо консоль на предмет браку відеопам'яті


@persistent
def on_render_post(scene):
    state.rendered_frames_count += 1


@persistent
def on_render_complete(scene):
    """Рендер завершився успішно → видаємо всі виконані рендер-ачивки."""
    oom_capture_stop()
    # Глобальні лічильники рендерів/кадрів (просто числа, без відкладання)
    with debug.guarded("handlers.py:on_render_complete/stats"):
        eng = _engine()
        eng.add_stat("renders_total", 1)                        # NASA Computer
        if state.rendered_frames_count > 0:
            eng.add_stat("frames_total", state.rendered_frames_count)  # Feature Film
        eng.flush_stats()

    rules.evaluate(registry.RENDER_COMPLETE, _context(scene))

    # Рендер закінчився: годинник зупиняємо ЗАРАЗ, ПІСЛЯ перевірки правил.
    # Інакше 5-секундний таймер і далі міряв би time.time() - старт і видав би
    # NIGHT_SHIFT через 4 години простою після рендеру на три секунди.
    state.render_start_time = None


@persistent
def on_render_cancel(scene):
    """Рендер скасовано (у т.ч. через помилку — Cycles на set_error теж ставить
    cancel). Рендер-ачивки не видаємо: вони перевіряються лише в
    on_render_complete. Але саме тут закривається перехоплення консолі, бо
    аварійний рендер до render_complete не доходить."""
    oom_capture_stop()
    state.render_start_time = None   # див. on_render_complete: годинник має стати


# ---------------- VRAM_VICTIM: перехоплення консолі рендеру ----------------
#
# УВАГА: НЕ підключати bpy.app.handlers.render_stats. Текст помилки туди
# справді доходить, але сама наявність обробника роняє Blender 5.2 рівно на
# аварійному рендері: image_renderinfo_cb передає rs->infostr у
# BKE_callback_exec_string без перевірки на NULL, далі PyC_UnicodeFromBytes
# викликає strlen(NULL) -> EXCEPTION_ACCESS_VIOLATION. Падіння стається в
# C-коді ДО виклику нашої функції, тож із Python його не обійти.
#
# Робочий шлях — консоль. Cycles повідомляє помилку через
# RE_engine_report(RPT_ERROR, ...) -> BKE_report(), який робить
# printf("%s: %s\n") + fflush(stdout). Тобто рядок
# "Error: System is out of GPU and shared host memory" іде у ФАЙЛОВИЙ
# ДЕСКРИПТОР 1, а не через Python-обгортку sys.stdout. Перехоплюємо його
# на час рендеру через os.dup2.
#
# Щоб користувач не втрачав вивід консолі, захоплене щосекунди зливається
# назад у справжній stdout — тобто це не «крадіжка» виводу, а «трійник» із
# затримкою до 1 с.
#
# Свідомо НЕ ловимо "Out of memory on allocating triangles/vertices" — це
# системна RAM, а не відеопам'ять.
_VRAM_OOM_RE = re.compile(
    r"out\s+of\s+(?:gpu|device)(?:\s+and\s+(?:shared\s+)?host)?\s+memory",
    re.IGNORECASE,
)


def _oom_drain():
    """Зливає нові байти з файлу-приймача у справжній stdout і шукає в них
    повідомлення про брак відеопам'яті."""
    if state.cap_path is None or state.cap_saved_fd is None:
        return
    with debug.guarded("handlers.py:_oom_drain"):
        with open(state.cap_path, "rb") as r:
            r.seek(state.cap_offset)
            chunk = r.read()
        if not chunk:
            return
        state.cap_offset += len(chunk)
        try:
            os.write(state.cap_saved_fd, chunk)      # віддаємо користувачу назад
        except OSError as _dbg_err:
            debug.log("handlers.py:_oom_drain/write", _dbg_err)
        if _VRAM_OOM_RE.search(chunk.decode("utf-8", "replace")):
            operations.trigger_vram_error()


def _oom_timer():
    if not state.cap_active:
        return None
    _oom_drain()
    return 1.0


def oom_capture_start():
    """Перенаправляє stdout у тимчасовий файл на час рендеру.

    Будь-яка помилка на цьому шляху означає просто відмову від детекції
    (напр. GUI-збірка Windows без консолі, де fd 1 невалідний) — рендер від
    цього не страждає.

    У фоновому режимі (`blender -b`) не перехоплюємо взагалі. Злив назад у
    справжній stdout тримається на bpy.app.timers, а вони під час рендеру в
    headless надійно не крутяться: увесь прогрес рендеру мовчав би до кінця й
    вивалювався одним блоком. Для рендер-ферм і CI це гірше, ніж відсутність
    однієї ачивки — VRAM_VICTIM там просто не видається.
    """
    if state.cap_active:
        return
    if getattr(bpy.app, "background", False):
        return
    f = path = saved = None
    try:
        fd, path = tempfile.mkstemp(prefix="bl_achievements_render_", suffix=".log")
        os.close(fd)
        f = open(path, "wb", buffering=0)
        saved = os.dup(1)
        os.dup2(f.fileno(), 1)
    except Exception as _dbg_err:
        debug.log("handlers.py:oom_capture_start", _dbg_err)
        for closer in (lambda: f and f.close(),
                       lambda: saved is not None and os.close(saved),
                       lambda: path and os.path.exists(path) and os.remove(path)):
            try:
                closer()
            except Exception:
                pass
        return

    state.cap_file, state.cap_path, state.cap_saved_fd, state.cap_offset = f, path, saved, 0
    state.cap_active = True
    with debug.guarded("handlers.py:oom_capture_start/timer"):
        bpy.app.timers.register(_oom_timer, first_interval=1.0)


def oom_capture_stop():
    """Повертає stdout на місце, доливає залишок і прибирає тимчасовий файл."""
    if not state.cap_active:
        return
    state.cap_active = False                      # зупиняє таймер на наступному тіку
    with debug.guarded("handlers.py:oom_capture_stop/restore"):
        os.dup2(state.cap_saved_fd, 1)            # спершу віддаємо справжній stdout
    with debug.guarded("handlers.py:oom_capture_stop/close"):
        if state.cap_file is not None:
            state.cap_file.close()

    _oom_drain()                             # останній залишок + перевірка

    try:
        if state.cap_saved_fd is not None:
            os.close(state.cap_saved_fd)
    except Exception:
        pass
    try:
        if state.cap_path and os.path.exists(state.cap_path):
            os.remove(state.cap_path)
    except Exception:
        pass
    state.cap_file = state.cap_path = state.cap_saved_fd = None
    state.cap_offset = 0


# --- Save / load / undo / import ------------------------------------------

@persistent
def on_save_post(dummy):
    state.last_save_time = time.time()
    state.session_save_count += 1

    eng = _engine()
    eng.add_stat("saves_total", 1)          # Good Habit (global)
    rules.evaluate(registry.SAVE, _context())
    eng.flush_stats()


@persistent
def on_load_post(dummy):
    state.launch_time = time.time()
    state.last_save_time = time.time()
    state.known_objects = debug.guarded_value(
        "handlers.py:on_load_post", probes.snapshot_objects, None)

    # Новий baseline для відкритого файлу: усе наявне вважаємо «не цієї сесії».
    probes.capture_baseline()
    # Дельта-лічильники перебазовуємо на вміст відкритого файлу (щоб готовий
    # вміст не рахувався як «створене»).
    state.delta_last.clear()
    state.ngon_cache.clear()          # імена мешів у новому файлі можуть збігатися
    state.progress_cache.clear()
    state.progress_scene_dirty = True   # прогрес рахувався по попередньому файлу
    state.rule_last_eval.clear()

    # База детектора операцій належала попередньому файлу. Без скидання перший
    # depsgraph_update_post порівнює дві різні сцени: файл на 150 об'єктів,
    # відкритий після файлу на 10, дає gone = 140 і хибний THE_PURGE. Словники
    # ключуються ІМЕНАМИ датаблоків, тож "Cube" зі старого файлу так само
    # порівнявся б із "Cube" нового -> фантомні merge / knife / flip normals.
    state.op_prev_obj_count = None
    state.op_prev_mesh_count = None
    state.op_prev_total_verts = None
    state.op_mesh_counts.clear()
    state.op_mesh_orient.clear()
    state.op_xform_identity.clear()
    state.op_bake_state.clear()
    state.op_resync = True     # перший прохід після завантаження — лише ресинк бази

    # GPU-текстури тостів прив'язані до bpy.data.images попереднього файлу.
    with debug.guarded("handlers.py:on_load_post/invalidate_textures"):
        from . import toast
        toast.invalidate_textures()

    eng = _engine()
    with debug.guarded("handlers.py:on_load_post/recovery"):
        from .rules.workflow import is_crash_recovery_file
        if is_crash_recovery_file():
            # Лічильник поза перевіркою is_unlocked: інакше після першої ж
            # ачивки він переставав рости, і милстоун на 10 відновлень
            # («Live to Die Another Day») був недосяжний у принципі.
            eng.add_stat("recoveries", 1)   # Live to Die Another Day (global)

    rules.evaluate(registry.LOAD, _context())


@persistent
def on_undo_post(scene, _extra=None):
    """Штатний хендлер скасування дії.

    Раніше undo намагався ловити опитувач wm.operators, куди ed.undo взагалі
    не потрапляє (оператор не має прапорця REGISTER — скасування не можна
    «повторити»). bpy.app.handlers.undo_post дає це напряму.
    """
    state.op_resync = True     # наступний прохід детектора — лише ресинк бази
    with debug.guarded("handlers.py:on_undo_post/reconcile"):
        _reconcile_accum_deltas(_engine())
    with debug.guarded("handlers.py:on_undo_post"):
        operations.record_undo()


@persistent
def on_blend_import_post(_a=None, _b=None):
    """Append / Link даних з іншого .blend.

    Точний хендлер замість самопального пошуку датаблоків з бібліотекою:
    той спрацьовував лише на Link (append копіює дані й посилання на
    бібліотеку не лишає), тому Append не зараховувався взагалі.
    """
    with debug.guarded("handlers.py:on_blend_import_post"):
        eng = _engine()
        if not eng.is_unlocked("APPEND_ICITIS"):
            eng.unlock("APPEND_ICITIS")


# --- Global cumulative counters -------------------------------------------

def _accum_delta(eng, stat_key: str, current: int):
    """Додає до глобального лічильника лише додатний приріст сумарного значення.
    Перший замір (або після відкриття файлу) лише запам'ятовує baseline."""
    last = state.delta_last.get(stat_key)
    if last is None:
        state.delta_last[stat_key] = current
        return
    if current > last:
        eng.add_stat(stat_key, current - last)
    state.delta_last[stat_key] = current


# Накопичувальні лічильники, що живуть із різниці «скільки стало» проти
# «скільки було»: ключ у stats, ачивка, після якої рахувати вже нема сенсу,
# джерело живого значення, і чи це важкий скан (тоді — лише раз на флаш-тік,
# а не щоп'ять секунд).
_ACCUM_COUNTERS = (
    ("polygons_total", "POLYGON_TYCOON", probes.count_total_polys, False),
    ("node_links_total", "NODE_ARCHITECT", probes.count_total_node_links, False),
    ("materials_total", "MATERIAL_WORLD", lambda: len(bpy.data.materials), False),
    ("shapekeys_total", "SHAPE_SHIFTER_3", probes.count_total_shapekeys, False),
    ("keyframes_total", "PUPPETEER", probes.count_keyframes, True),
)


def _reconcile_accum_deltas(eng):
    """Синхронізує state.delta_last із реальним станом сцени після Ctrl+Z.

    Якщо undo повернув лічильник НИЖЧЕ за last — відкочуємо щойно
    нараховану дельту (від'ємний add_stat).
    Якщо undo повернув лічильник ВИЩЕ за last (скасування видалення) —
    просто вирівнюємо baseline, щоб наступний _accum_delta не зарахував
    відновлені об'єкти як "нові" (Delete+Undo exploit)."""
    missing = object()
    for stat_key, _gate, counter_fn, _slow in _ACCUM_COUNTERS:
        last = state.delta_last.get(stat_key)
        if last is None:
            continue
        current = debug.guarded_value("handlers.py:_reconcile_accum_deltas", counter_fn, missing)
        if current is missing:
            continue
        if current < last:
            eng.add_stat(stat_key, current - last)   # від'ємна дельта
        # Завжди вирівнюємо baseline — і при current < last, і при
        # current > last (скасування видалення), щоб _accum_delta
        # не побачив хибний приріст на наступному тіку таймера.
        state.delta_last[stat_key] = current


# --- Periodic low-frequency timer -----------------------------------------

def achievement_timer_callback():
    eng = _engine()

    probes.ensure_baseline()
    operations.prune_caches()

    # ---- бухгалтерія сесії: біжить кожен тік, незалежно від того, чи
    #      лишились невідкриті ачивки ----

    if not state.session_started:
        state.session_started = True
        with debug.guarded("handlers.py:timer/session_start"):
            eng.add_stat("launches", 1)          # Loyalty
            eng.record_session_day()             # Consistency / Dedicated / Year of the Donut
            eng.begin_session()                  # зріз лічильників для підсумку сесії

    # Журнал днів і підсумок сесії. Окремою гілкою від uptime_seconds нижче:
    # той перестає рахуватись після UNEMPLOYED_3, а календар має заповнюватись
    # завжди.
    with debug.guarded("handlers.py:timer/worked_seconds"):
        eng.record_worked_seconds(TIMER_TICK)

    # Безділля: лічильник крутиться тут, скидає його будь-яка активність
    # (клавіша, depsgraph, кадр, рендер). Саму ачивку видає правило
    # WHAT_AM_I_DOING на цьому ж тіку.
    if not eng.is_unlocked("WHAT_AM_I_DOING"):
        state.idle_seconds += TIMER_TICK

    with debug.guarded("handlers.py:timer/uptime"):
        if not eng.is_unlocked("UNEMPLOYED_3"):
            eng.add_stat("uptime_seconds", TIMER_TICK)    # Unemployed

    with debug.guarded("handlers.py:timer/sculpt"):
        if not eng.is_unlocked("SCULPT_SANCTUARY") and getattr(bpy.context, "mode", "") == 'SCULPT':
            eng.add_stat("sculpt_seconds", TIMER_TICK)    # Sculpt Sanctuary

    # Флаш stats на диск ~кожні 30 с; на тому ж тіку крутиться і важкий
    # keyframes-скан (див. `slow` у _ACCUM_COUNTERS).
    state.flush_tick = (state.flush_tick + 1) % 6

    if state.baseline is not None:
        with debug.guarded("handlers.py:timer/deltas"):
            for stat_key, ach_id, source, slow in _ACCUM_COUNTERS:
                if slow and state.flush_tick != 0:
                    continue
                if not eng.is_unlocked(ach_id):
                    _accum_delta(eng, stat_key, source())

    if state.flush_tick == 0:
        with debug.guarded("handlers.py:timer/flush"):
            eng.flush_stats()

    rules.evaluate(registry.TIMER, _context())
    return TIMER_INTERVAL


# --- msgbus ---------------------------------------------------------------

def _on_msgbus_notify(*args):
    """Msgbus callback triggering depsgraph check."""
    with debug.guarded("handlers.py:_on_msgbus_notify"):
        if hasattr(bpy.context, "scene") and hasattr(bpy.context, "evaluated_depsgraph_get"):
            on_depsgraph_update(bpy.context.scene, bpy.context.evaluated_depsgraph_get())


def register_msgbus_subscribers():
    with debug.guarded("handlers.py:register_msgbus_subscribers"):
        owner = object()
        state.msgbus_owners.append(owner)
        bpy.msgbus.subscribe_rna(
            key=(bpy.types.Light, "energy"),
            owner=owner,
            args=(),
            notify=_on_msgbus_notify,
        )


# --- Listener lifecycle ---------------------------------------------------

_HANDLER_BINDINGS = (
    (on_depsgraph_update, "depsgraph_update_post"),
    (on_load_post, "load_post"),
    (on_save_post, "save_post"),
    (on_render_init, "render_init"),
    (on_render_post, "render_post"),
    (on_render_complete, "render_complete"),
    (on_render_cancel, "render_cancel"),
    (on_frame_change_post, "frame_change_post"),
    (on_undo_post, "undo_post"),
    (on_blend_import_post, "blend_import_post"),
)


def _app_list(name):
    return getattr(bpy.app.handlers, name)


def register_listeners():
    """Registers event handlers, low-frequency timers, and msgbus subscribers."""
    reset_tracking_state()

    for handler, list_name in _HANDLER_BINDINGS:
        app_list = _app_list(list_name)
        if handler not in app_list:
            app_list.append(handler)

    if hasattr(bpy.app.timers, "is_registered"):
        if not bpy.app.timers.is_registered(achievement_timer_callback):
            bpy.app.timers.register(achievement_timer_callback, persistent=True)
    else:
        try:
            bpy.app.timers.register(achievement_timer_callback, persistent=True)
        except (ValueError, RuntimeError):
            pass

    register_msgbus_subscribers()

    # Дозволяємо фоновому оператору-спостерігачу (__init__.py) працювати;
    # сам modal-оператор запускається окремо через одноразовий bpy.app.timers,
    # бо invoke() потребує готового UI-контексту, якого немає під час register().
    start_watcher()


def unregister_listeners():
    """Unregisters event handlers, low-frequency timers, and msgbus subscribers cleanly."""
    stop_watcher()
    oom_capture_stop()   # ніколи не лишати stdout перенаправленим
    # Зберегти накопичені глобальні лічильники (uptime тощо) перед скиданням стану.
    with debug.guarded("handlers.py:unregister_listeners/flush"):
        _engine().flush_stats()

    reset_tracking_state()

    for handler, list_name in _HANDLER_BINDINGS:
        app_list = _app_list(list_name)
        if handler in app_list:
            app_list.remove(handler)

    if hasattr(bpy.app.timers, "is_registered"):
        if bpy.app.timers.is_registered(achievement_timer_callback):
            bpy.app.timers.unregister(achievement_timer_callback)
    else:
        try:
            bpy.app.timers.unregister(achievement_timer_callback)
        except (ValueError, RuntimeError):
            pass

    for owner in state.msgbus_owners:
        with debug.guarded("handlers.py:unregister_listeners/msgbus"):
            bpy.msgbus.clear_by_owner(owner)
    state.msgbus_owners.clear()

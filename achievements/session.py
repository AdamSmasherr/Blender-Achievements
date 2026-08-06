"""
Per-session tracking state for Blender Achievements.

Everything a detector needs to remember *within* one Blender run lives here:
baselines, per-mesh caches, timestamps, the watcher's liveness flags. Nothing
persistent — that's `storage.py` — and nothing Blender-specific beyond
`time.time()`, so this module stays importable from both `rules/` and
`handlers.py` without a cycle between them.
"""

import time
from dataclasses import dataclass, field
from typing import List, Tuple

from . import debug

# Крок низькочастотного таймера. Живе тут, а не в handlers.py, бо на нього
# спираються і хендлер (скільки секунд долити), і правила, що міряють час
# перебування (скільки секунд минуло між двома перевірками) — двом копіям
# п'ятірки нема як лишитись узгодженими.
TIMER_INTERVAL = 5.0
TIMER_TICK = int(TIMER_INTERVAL)


# --- Event Tracking State Variables ---
# (baseline: щоб зараховувати лише зроблене цієї сесії, а не вміст уже
#  відкритого файлу; знімається на старті сесії / відкритті файлу)

@dataclass
class SessionState:
    """Всі внутрішньосесійні лічильники/кеші детекторів подій.

    Раніше це були ~50 окремих module-level `global`-змінних; тепер це поля
    одного інстансу (`state`, singleton нижче), а `reset_tracking_state()`
    просто перестворює його заново.
    """
    known_objects: object = None
    launch_time: float = field(default_factory=time.time)
    last_save_time: float = field(default_factory=time.time)
    session_save_count: int = 0
    uv_editing_seconds: int = 0
    render_start_time: object = None
    rendered_frames_count: int = 0
    motion_blur_active_at_render_start: bool = False
    baseline: object = None  # dict з множинами імен та лічильниками або None
    respect_cube_armed: bool = False  # True лише якщо сесія стартувала з фабричного файлу
    undo_timestamps: List[float] = field(default_factory=list)
    shortcut_timestamps: List[Tuple[float, str]] = field(default_factory=list)
    knife_cut_count: int = 0
    graph_tweaks: int = 0
    applied_objects_count: int = 0
    msgbus_owners: List[object] = field(default_factory=list)
    watcher_running: bool = False
    watcher_instance_active: bool = False  # True, поки жива МОДАЛЬНА копія оператора
    watcher_heartbeat: float = 0.0  # час останньої побаченої події
    op_prev_obj_count: object = None  # к-сть об'єктів на попередньому оновленні
    op_prev_mesh_count: object = None  # к-сть MESH-об'єктів на попередньому оновленні
    op_prev_total_verts: object = None  # сума вершин по всіх мешах
    op_mesh_counts: dict = field(default_factory=dict)  # mesh.name -> (verts, edges)
    op_mesh_orient: dict = field(default_factory=dict)  # mesh.name -> знак орієнтації (+1/-1)
    op_xform_identity: dict = field(default_factory=dict)  # ob.name -> чи був трансформ одиничним
    op_bake_state: dict = field(default_factory=dict)  # "object/modifier" -> чи був кеш запечений
    op_resync: bool = False  # True -> наступний прохід лише перезаписує базу
    op_graph_sig: dict = field(default_factory=dict)  # ім'я екшена -> підпис його ключів (Graph Editor Tweaker)
    op_graph_last: float = 0.0  # час останнього зарахованого руху ключа
    op_graph_checked: float = 0.0  # час останнього ОБЧИСЛЕННЯ підпису ключів
    op_last_full_scan: float = 0.0
    op_prev_editing: object = None  # меш, що редагувався на попередньому оновленні
    knife_armed_at: float = 0.0
    kf_buf: object = None  # спільний numpy-буфер під foreach_get (див. _action_signature)
    delta_last: dict = field(default_factory=dict)  # останні бачені сумарні значення для дельта-лічильників
    session_started: bool = False  # чи вже нарахували запуск/день цієї сесії
    flush_tick: int = 0  # лічильник тіків для періодичного флашу stats на диск
    idle_seconds: int = 0  # секунди без активності (What am I doing?)
    max_join_count: int = 0  # найбільше об'єднання за раз (для прогресу Frankenstein)
    max_merge_count: int = 0  # найбільше злиття вершин за раз (для прогресу Singularity)
    ngon_cache: dict = field(default_factory=dict)  # mesh_name -> (poly_count, verdict) — щоб не сканувати те саме двічі
    ngon_last_scan: float = 0.0
    cap_active: bool = False
    cap_file: object = None  # відкритий файловий об'єкт-приймач
    cap_path: object = None
    cap_saved_fd: object = None  # dup() справжнього stdout
    cap_offset: int = 0
    # Коли кожне правило з `interval` востаннє оцінювалось (rule id -> monotonic).
    # Замінює окремі глобальні "last scan time" на кожен важкий детектор.
    rule_last_eval: dict = field(default_factory=dict)
    progress_cache: dict = field(default_factory=dict)  # ach_id -> current value
    progress_cache_time: float = 0.0  # monotonic-час останнього перерахунку
    progress_scene_cache: dict = field(default_factory=dict)
    progress_scene_time: float = 0.0
    progress_scene_dirty: bool = True


# Singleton — інстанс, а не модуль-глобали: reset_tracking_state() просто
# перестворює його, і всі функції бачать нове порожнє state без жодного
# `global` (мутація атрибутів не потребує оголошення).
state = SessionState()


def reset_tracking_state():
    """Resets all session tracking state to clean defaults."""

    state.known_objects = None
    state.launch_time = time.time()
    state.last_save_time = time.time()
    state.session_save_count = 0
    state.uv_editing_seconds = 0

    state.render_start_time = None
    state.rendered_frames_count = 0
    state.motion_blur_active_at_render_start = False
    state.baseline = None
    state.respect_cube_armed = False
    state.session_started = False
    state.flush_tick = 0
    state.idle_seconds = 0
    state.max_join_count = 0
    state.max_merge_count = 0
    state.progress_cache = {}
    state.progress_cache_time = 0.0
    state.delta_last.clear()
    state.ngon_cache.clear()
    state.rule_last_eval.clear()

    state.op_prev_obj_count = None
    state.op_prev_mesh_count = None
    state.op_prev_total_verts = None
    state.op_mesh_counts = {}
    state.op_mesh_orient = {}
    state.op_xform_identity = {}
    state.op_bake_state = {}
    state.op_last_full_scan = 0.0
    state.op_graph_checked = 0.0
    state.op_graph_sig = {}
    state.op_prev_editing = None
    state.progress_scene_dirty = True

    state.knife_cut_count = 0
    state.graph_tweaks = 0
    state.applied_objects_count = 0

    state.undo_timestamps.clear()
    state.shortcut_timestamps.clear()
    # Позначку «модальна копія жива» скидаємо ЛИШЕ коли watcher і так зупинено
    # (register_listeners робить це до start_watcher, unregister_listeners —
    # після stop_watcher). Якщо ж скидання прогресу викликали при живому
    # watcher'і, обнулення прапорця змусило б _launch_watcher підняти ДРУГУ
    # копію поверх наявної, і кожне натискання клавіші рахувалося б двічі.
    if not state.watcher_running:
        state.watcher_instance_active = False

    # Нова сесія (або явний reset прогресу) не повинна успадковувати
    # попереджень про поламані детектори з минулого разу.
    debug.reset_error_counts()

"""
Blender Achievements

Native zero-dependency achievement tracking and custom GPU viewport notifications for Blender.
"""

import bpy

from . import toast
from . import storage
from . import achievements  # noqa: F401  (compat facade; see its docstring)
from . import handlers
from . import engine
from . import sounds
from . import debug
from . import ui

# Re-exported so `import achievements as addon; addon.format_duration(...)`
# and friends keep working — these used to live directly in this file,
# before the UI layer was split out into achievements/ui/.
from .ui import (
    get_preferences,
    format_duration,
    calendar_level,
    calendar_days,
    format_unlock_date,
    _split_description,
    _pack_sound_path,
    _unpack_sound_path,
)


# ----------------- Background Operator Watcher -----------------

class ACHIEVEMENT_OT_watcher(bpy.types.Operator):
    """Invisible always-on modal operator. Never consumes input (always
    PASS_THROUGH) — it exists solely to see key presses, which is the one
    thing no handler exposes. Everything else (joins, cuts, merges, undo,
    applied transforms) is recognised from scene state or dedicated
    handlers — see rules/operations.py."""
    bl_idname = "achievement.watcher"
    bl_label = "Achievement Background Watcher"
    bl_options = {'INTERNAL'}

    _timer = None

    def modal(self, context, event):
        if not handlers.is_watcher_running():
            return self._stop(context)

        if event.type == 'TIMER':
            # Пульс: доводить, що копія жива. Без нього "живість" мірялась
            # натисканнями клавіш, і після 90 с тиші watcher вважався мертвим —
            # запускалась ДРУГА копія, далі третя, і кожна рахувала ті самі
            # натискання повторно.
            handlers.watcher_heartbeat()
        elif event.value == 'PRESS':
            handlers.watcher_key_event(event)

        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        if not handlers.watcher_instance_start():
            return {'CANCELLED'}   # інша копія вже працює
        wm = context.window_manager
        win = context.window or (wm.windows[0] if wm.windows else None)
        if win is None:
            handlers.watcher_instance_stop()
            return {'CANCELLED'}
        self._timer = wm.event_timer_add(1.0, window=win)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _stop(self, context):
        wm = context.window_manager
        if self._timer is not None:
            try:
                wm.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None
        handlers.watcher_instance_stop()
        return {'CANCELLED'}


def _launch_watcher():
    """Періодичний bpy.app.timers callback: тримає модальний watcher живим.

    invoke() модального оператора потребує готового UI-контексту (вікна),
    якого немає під час register() — тому старт відкладається на трохи
    пізніше через таймер, з повторною спробою, якщо контекст ще не готовий.
    """
    try:
        if not handlers.is_watcher_running():
            return None
        # Модальна копія може загинути не через _stop() — наприклад при
        # перезавантаженні файлу. Тому таймер не одноразовий: він періодично
        # перевіряє, чи копія жива, і за потреби піднімає нову.
        if handlers.watcher_needs_launch():
            # Запуск обов'язково у контексті вікна: у callback таймера
            # context.window буває None, і тоді modal_handler_add чіпляє
            # обробник у нікуди — клавіші до нього не доходять.
            wm = bpy.context.window_manager
            if wm.windows:
                with bpy.context.temp_override(window=wm.windows[0]):
                    bpy.ops.achievement.watcher('INVOKE_DEFAULT')
    except Exception:
        pass
    return 30.0


def _init_preset_sound_paths():
    """Одноразовий callback: підставляє шляхи бандлених звуків у поля пресетів.

    Робиться через таймер, а не в register(): на момент реєстрації
    AddonPreferences ще може бути недоступним, а писати у властивості
    під час draw() не можна.
    """
    try:
        sounds.ensure_preset_defaults(get_preferences())
    except Exception:
        return 0.5
    return None


def register():
    if not hasattr(bpy.types, ACHIEVEMENT_OT_watcher.__name__):
        try:
            bpy.utils.register_class(ACHIEVEMENT_OT_watcher)
        except (ValueError, RuntimeError):
            pass

    ui.register()

    # Initialize engine singleton
    engine.get_engine()

    # Register event tracking handlers safely
    handlers.register_listeners()

    # Запускаємо фоновий watcher трохи пізніше, коли UI-контекст буде готовий.
    # is_registered обов'язковий: швидкий цикл вимкнути/увімкнути аддон інакше
    # лишає кілька копій того самого таймера.
    for cb in (_launch_watcher, _init_preset_sound_paths):
        try:
            if bpy.app.timers.is_registered(cb):
                continue
        except AttributeError:
            pass
        try:
            bpy.app.timers.register(cb, first_interval=0.3)
        except (ValueError, RuntimeError):
            pass


def unregister():
    # Знімаємо власні таймери в парі до register(). _launch_watcher
    # самоліквідується лише на наступному тику (через 30 с), і весь цей час
    # тримає посилання на вивантажений модуль.
    for cb in (_launch_watcher, _init_preset_sound_paths):
        try:
            if bpy.app.timers.is_registered(cb):
                bpy.app.timers.unregister(cb)
        except (AttributeError, ValueError, RuntimeError):
            pass

    # Remove viewport draw handler if active
    toast.remove_handler()

    # Stop any playing achievement/preview sounds
    sounds.stop_all()

    # Unregister event tracking handlers
    handlers.unregister_listeners()

    ui.unregister()

    # Reset engine singleton
    engine.reset_engine()

    if hasattr(bpy.types, ACHIEVEMENT_OT_watcher.__name__):
        try:
            bpy.utils.unregister_class(ACHIEVEMENT_OT_watcher)
        except (ValueError, RuntimeError):
            pass


if __name__ == "__main__":
    register()

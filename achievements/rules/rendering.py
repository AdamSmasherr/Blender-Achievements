"""Lighting & rendering rules.

Two families here. Scene-state ones (samples, denoising, transparent film) are
checked when a render *finishes* — that's what makes them mean "you rendered
like this", not "you once ticked this box". Timing ones read the clock started
by `render_init`; they are checked before it is cleared, so `elapsed()` is
only ever None outside a render.
"""

import time

import bpy

from ..registry import DEPSGRAPH, RENDER_COMPLETE, TIMER, bind
from ..session import state
from . import probes

NIGHT_SHIFT_SECONDS = 14400      # 4 години
LONG_HAUL_SECONDS = 86400        # доба
SPEEDSTER_SECONDS = 60.0
SPEEDSTER_FRAMES = 100
# Мінімум відрендерених кадрів, щоб рендер вважався анімацією, а не стіллом.
SPEED_BLUR_MIN_FRAMES = 2
SUN_ENERGY_LIMIT = 1000.0
CYCLES_SAMPLES_LIMIT = 10000


def _elapsed(ctx):
    """Скільки триває поточний рендер, або None якщо рендер не йде."""
    if state.render_start_time is None:
        return None
    return time.time() - state.render_start_time


def _render_seconds(ctx, minimum: int) -> bool:
    elapsed = _elapsed(ctx)
    return elapsed is not None and elapsed >= minimum


def _cycles(ctx):
    scene = ctx.scene
    return getattr(scene, "cycles", None) if scene else None


def _cycles_samples(ctx) -> int:
    cycles = _cycles(ctx)
    return getattr(cycles, "samples", 0) if cycles else 0


def _denoise_magic(ctx) -> bool:
    cycles = _cycles(ctx)
    return bool(cycles and cycles.samples < 32 and getattr(cycles, "use_denoising", False))


def _alpha_translucency(ctx) -> bool:
    scene = ctx.scene
    return bool(getattr(getattr(scene, "render", None), "film_transparent", False))


def _eevee_speedster(ctx) -> bool:
    elapsed = _elapsed(ctx)
    return (elapsed is not None
            and state.rendered_frames_count >= SPEEDSTER_FRAMES
            and elapsed < SPEEDSTER_SECONDS)


def _speed_blur(ctx) -> bool:
    """Саме анімація, а не один кадр: опис обіцяє "animation sequence", а на
    одному кадрі мо-блюр здебільшого й не видно."""
    return (state.motion_blur_active_at_render_start
            and state.rendered_frames_count >= SPEED_BLUR_MIN_FRAMES)


def _sun_god(ctx) -> bool:
    for light in bpy.data.lights:
        if (ctx.is_new('lights', light.name)
                and getattr(light, "type", "") == 'SUN'
                and getattr(light, "energy", 0.0) > SUN_ENERGY_LIMIT):
            return True
    return False


def _compositor_cook(ctx) -> bool:
    """10+ нод у компоузері, і хоча б одна з них додана цієї сесії."""
    if ctx.baseline is None:
        return False
    current = probes.compositor_nodes(ctx)
    return current >= 10 and current > ctx.baseline_count('compositor_nodes')


bind("CYCLES_ENTHUSIAST", RENDER_COMPLETE, progress=_cycles_samples,
     target=CYCLES_SAMPLES_LIMIT, scan=True,
     check=lambda ctx: _cycles_samples(ctx) > CYCLES_SAMPLES_LIMIT)

bind("DENOISE_MAGIC", RENDER_COMPLETE, check=_denoise_magic)
bind("ALPHA_TRANSLUCENCY", RENDER_COMPLETE, check=_alpha_translucency)
bind("SPEED_BLUR", RENDER_COMPLETE, check=_speed_blur)
bind("EEVEE_SPEEDSTER", RENDER_COMPLETE, check=_eevee_speedster,
     progress=lambda ctx: state.rendered_frames_count, target=SPEEDSTER_FRAMES)
bind("THE_LONG_HAUL", RENDER_COMPLETE,
     check=lambda ctx: _render_seconds(ctx, LONG_HAUL_SECONDS))

# Чотиригодинний рендер має зарахуватись і посеред нього (таймер), і на
# фініші — між двома тіками таймера рендер цілком може завершитись.
bind("NIGHT_SHIFT", (TIMER, RENDER_COMPLETE),
     check=lambda ctx: _render_seconds(ctx, NIGHT_SHIFT_SECONDS))

bind("SUN_GOD", DEPSGRAPH, check=_sun_god)
bind("COMPOSITOR_COOK", TIMER, check=_compositor_cook)

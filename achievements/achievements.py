"""
Achievement registry definitions and event tracking framework for Blender Achievements.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Set, List, Tuple
import os
import tempfile
import time
import re
import bpy
from bpy.app.handlers import persistent

from . import debug


@dataclass
class AchievementDefinition:
    """Represents a single achievement definition."""
    id: str
    title: str
    description: str
    rare: bool = False
    category: str = "Basics"
    icon: Optional[str] = None
    # Global (persistent, cross-session) achievements bind to a cumulative counter.
    counter: Optional[str] = None   # ключ у engine stats; None → звичайна (сесійна)
    threshold: int = 0              # поріг лічильника для розблокування


# Registry of all 42 available achievements across 6 categories
ACHIEVEMENTS: Dict[str, AchievementDefinition] = {
    # --- Category 1: Basics ---
    "GOODBYE_CUBE": AchievementDefinition(
        id="GOODBYE_CUBE",
        title="Goodbye, Cube!",
        description="Delete the default cube within 30 seconds of launching Blender.",
        rare=False,
        category="Basics",
    ),
    "RESPECT_THE_CUBE": AchievementDefinition(
        id="RESPECT_THE_CUBE",
        title="Respect the Cube",
        description="Render a scene without deleting or modifying the default cube.",
        rare=True,
        category="Basics",
    ),
    "DONUT_MASTER": AchievementDefinition(
        id="DONUT_MASTER",
        title="Donut Master",
        description="Render a torus with a glaze material.",
        rare=False,
        category="Basics",
    ),
    "SUZANNES_BLESSING": AchievementDefinition(
        id="SUZANNES_BLESSING",
        title="Suzanne's Blessing",
        description="Add a monkey mesh (Suzanne) to the scene.",
        rare=False,
        category="Basics",
    ),

    # --- Category 2: Modeling & Sculpting ---
    "POLYGON_KING": AchievementDefinition(
        id="POLYGON_KING",
        title="Polygon King",
        description="Reach over 10,000,000 polygons in a single scene or mesh.",
        rare=True,
        category="Modeling & Sculpting",
    ),
    "FATAL_CTRL_J": AchievementDefinition(
        id="FATAL_CTRL_J",
        title="Frankenstein",
        description="Join over 100 separate objects into a single mesh.",
        rare=True,
        category="Modeling & Sculpting",
    ),
    "UV_UNWRAPPING_PAIN": AchievementDefinition(
        id="UV_UNWRAPPING_PAIN",
        title="Flat Earth",
        description="Work in the UV Editing tab for over 30 minutes straight.",
        rare=False,
        category="Modeling & Sculpting",
    ),
    "SUBDIV_OVERKILL": AchievementDefinition(
        id="SUBDIV_OVERKILL",
        title="Subdiv Overkill",
        description="Set Subdivision Surface viewport/render level to 6 or higher.",
        rare=False,
        category="Modeling & Sculpting",
    ),
    "INVERTED_REALITY": AchievementDefinition(
        id="INVERTED_REALITY",
        title="Up is Down",
        description="Recalculate or flip inverted normals on a mesh.",
        rare=False,
        category="Modeling & Sculpting",
    ),
    "KNIFE_MASTER": AchievementDefinition(
        id="KNIFE_MASTER",
        title="Surgical Precision",
        description="Make over 50 manual cuts using the Knife tool in one session.",
        rare=False,
        category="Modeling & Sculpting",
    ),
    "MERGE_MASTER": AchievementDefinition(
        id="MERGE_MASTER",
        title="Singularity",
        description="Merge over 100 overlapping vertices using Merge by Distance.",
        rare=False,
        category="Modeling & Sculpting",
    ),

    # --- Category 3: Nodes & Materials ---
    "NODE_SPAGHETTI": AchievementDefinition(
        id="NODE_SPAGHETTI",
        title="Node Spaghetti",
        description="Connect over 50 nodes in Shader or Geometry Nodes.",
        rare=True,
        category="Nodes & Materials",
    ),
    "PURE_PROCEDURAL": AchievementDefinition(
        id="PURE_PROCEDURAL",
        title="Pure Procedural",
        description="Create a material without using any external image textures.",
        rare=False,
        category="Nodes & Materials",
    ),
    "GEOMETRY_NODES_GURU": AchievementDefinition(
        id="GEOMETRY_NODES_GURU",
        title="Geometry Nodes Guru",
        description="Create a node tree with 5+ nested Node Groups.",
        rare=True,
        category="Nodes & Materials",
    ),
    "MATERIAL_HOARDER": AchievementDefinition(
        id="MATERIAL_HOARDER",
        title="Material Hoarder",
        description="Accumulate 30 or more materials in a single project file.",
        rare=False,
        category="Nodes & Materials",
    ),
    "SAVED_BY_SHIELD": AchievementDefinition(
        id="SAVED_BY_SHIELD",
        title="Devine Shield",
        description="Assign Fake User (Shield icon) to 10 unused datablocks.",
        rare=False,
        category="Nodes & Materials",
    ),
    "EMISSION_OVERDRIVE": AchievementDefinition(
        id="EMISSION_OVERDRIVE",
        title="Flashbang",
        description="Set an Emission node strength above 10,000.",
        rare=False,
        category="Nodes & Materials",
    ),
    "COLOR_RAMP_ADDICT": AchievementDefinition(
        id="COLOR_RAMP_ADDICT",
        title="Color Ramp Addict",
        description="Use 5 or more Color Ramp nodes in a single shader tree.",
        rare=False,
        category="Nodes & Materials",
    ),

    # --- Category 4: Animation & Physics ---
    "GRAPH_EDITOR_TWEAKER": AchievementDefinition(
        id="GRAPH_EDITOR_TWEAKER",
        title="Graph Editor Tweaker",
        description="Adjust over 100 keyframe interpolation handles in the Graph Editor.",
        rare=False,
        category="Animation & Physics",
    ),
    "BONE_COLLECTOR": AchievementDefinition(
        id="BONE_COLLECTOR",
        title="Exoskeleton",
        description="Build an armature rig containing over 50 bones.",
        rare=False,
        category="Animation & Physics",
    ),
    "DRIVER_SPECIALIST": AchievementDefinition(
        id="DRIVER_SPECIALIST",
        title="Driver Specialist",
        description="Create 5 custom Python drivers linking object properties.",
        rare=False,
        category="Animation & Physics",
    ),
    "GRAVITY_MASTER": AchievementDefinition(
        id="GRAVITY_MASTER",
        title="Domino Effect",
        description="Run a Rigid Body simulation with over 100 objects.",
        rare=True,
        category="Animation & Physics",
    ),
    "THE_BIG_BAKE": AchievementDefinition(
        id="THE_BIG_BAKE",
        title="Let it cook",
        description="Bake a fluid or smoke simulation longer than 250 frames.",
        rare=False,
        category="Animation & Physics",
    ),
    "PARTICLE_STORM": AchievementDefinition(
        id="PARTICLE_STORM",
        title="Particle Storm",
        description="Emit over 100,000 particles from a single emitter setup.",
        rare=False,
        category="Animation & Physics",
    ),
    "CLOTH_EXPLOSION": AchievementDefinition(
        id="CLOTH_EXPLOSION",
        title="Rip and Tear",
        description="Run a Cloth simulation where mesh vertices travel over 100 units away instantly.",
        rare=True,
        category="Animation & Physics",
    ),

    # --- Category 5: Lighting & Rendering ---
    "NIGHT_SHIFT": AchievementDefinition(
        id="NIGHT_SHIFT",
        title="Night Shift",
        description="Keep a render process running for over 4 consecutive hours.",
        rare=True,
        category="Lighting & Rendering",
    ),
    "CYCLES_ENTHUSIAST": AchievementDefinition(
        id="CYCLES_ENTHUSIAST",
        title="Cinema Quality",
        description="Set render samples above 10,000.",
        rare=False,
        category="Lighting & Rendering",
    ),
    "EEVEE_SPEEDSTER": AchievementDefinition(
        id="EEVEE_SPEEDSTER",
        title="Warp Speed",
        description="Render 100+ animation frames in under 1 minute.",
        rare=False,
        category="Lighting & Rendering",
    ),
    "VRAM_VICTIM": AchievementDefinition(
        id="VRAM_VICTIM",
        title="Out of Memory",
        description="Trigger a render error due to running out of GPU memory.",
        rare=True,
        category="Lighting & Rendering",
    ),
    "SPEED_BLUR": AchievementDefinition(
        id="SPEED_BLUR",
        title="Motion Blur",
        description="Render an animation sequence with Motion Blur enabled.",
        rare=False,
        category="Lighting & Rendering",
    ),
    "SUN_GOD": AchievementDefinition(
        id="SUN_GOD",
        title="Now I become death",
        description="Set Sun Light strength to over 1,000.",
        rare=False,
        category="Lighting & Rendering",
    ),
    "DENOISE_MAGIC": AchievementDefinition(
        id="DENOISE_MAGIC",
        title="Denoise Magic",
        description="Render an image with under 32 samples using AI denoising.",
        rare=False,
        category="Lighting & Rendering",
    ),
    "ALPHA_TRANSLUCENCY": AchievementDefinition(
        id="ALPHA_TRANSLUCENCY",
        title="Ghost in the Shell",
        description="Render a scene with transparent background enabled.",
        rare=False,
        category="Lighting & Rendering",
    ),

    # --- Category 6: Workflow & Disasters ---
    "CTRL_Z_HERO": AchievementDefinition(
        id="CTRL_Z_HERO",
        title="Time Traveler",
        description="Undo actions 50+ times in a row within one minute.",
        rare=False,
        category="Workflow & Disasters",
    ),
    "THE_SURVIVOR": AchievementDefinition(
        id="THE_SURVIVOR",
        title="Back from the dead",
        description="Successfully restore a project via Recover Auto Save after a crash.",
        rare=True,
        category="Workflow & Disasters",
    ),
    "LIVING_ON_THE_EDGE": AchievementDefinition(
        id="LIVING_ON_THE_EDGE",
        title="Living on the Edge",
        description="Work on a complex scene for over 2 hours without saving (Ctrl+S).",
        rare=False,
        category="Workflow & Disasters",
    ),
    "ADDON_COLLECTOR": AchievementDefinition(
        id="ADDON_COLLECTOR",
        title="Add-on Collector",
        description="Enable over 25 add-ons in the preferences.",
        rare=False,
        category="Workflow & Disasters",
    ),
    "SHORTCUT_NINJA": AchievementDefinition(
        id="SHORTCUT_NINJA",
        title="Shortcut Ninja",
        description="Use 30 different keyboard shortcuts in a minute without opening mouse menus.",
        rare=True,
        category="Workflow & Disasters",
    ),
    "APPLY_ALL": AchievementDefinition(
        id="APPLY_ALL",
        title="Know your Place",
        description="Apply scale, rotation, and location (Ctrl+A) on 20+ objects in a scene.",
        rare=False,
        category="Workflow & Disasters",
    ),
    "OUTLINER_CHAOS": AchievementDefinition(
        id="OUTLINER_CHAOS",
        title="Outliner Chaos",
        description="Maintain 47+ auto-named objects (Cube.001, Cube.002) without renaming.",
        rare=False,
        category="Workflow & Disasters",
    ),
    "SAVE_BUTTON_MASHER": AchievementDefinition(
        id="SAVE_BUTTON_MASHER",
        title="Paranoia",
        description="Save your project manually over 50 times in a single session.",
        rare=False,
        category="Workflow & Disasters",
    ),

    # ============================ NEW SESSION ACHIEVEMENTS ============================
    "N_GON_CRIMINAL": AchievementDefinition(
        id="N_GON_CRIMINAL",
        title="N-gon Criminal",
        description="Create a single face with 10 or more sides.",
        rare=False,
        category="Modeling & Sculpting",
    ),
    "COMPOSITOR_COOK": AchievementDefinition(
        id="COMPOSITOR_COOK",
        title="Compositor Cook",
        description="Build a compositor node tree with 10 or more nodes.",
        rare=False,
        category="Lighting & Rendering",
    ),
    "OUROBOROS": AchievementDefinition(
        id="OUROBOROS",
        title="Ouroboros",
        description="Create a driver that references its own property (a cyclic dependency).",
        rare=True,
        category="Animation & Physics",
    ),
    "THE_PURGE": AchievementDefinition(
        id="THE_PURGE",
        title="The Purge",
        description="Delete 100 or more objects in a single operation.",
        rare=True,
        category="Workflow & Disasters",
    ),
    "APPEND_ICITIS": AchievementDefinition(
        id="APPEND_ICITIS",
        title="Append-icitis",
        description="Append or link data from another .blend file.",
        rare=False,
        category="Workflow & Disasters",
    ),
    "WHAT_AM_I_DOING": AchievementDefinition(
        id="WHAT_AM_I_DOING",
        title="What am I doing?",
        description="Leave Blender running for 4 hours without doing anything.",
        rare=True,
        category="Workflow & Disasters",
        icon="What am I doing.png",
    ),

    # ============================ GLOBAL (CUMULATIVE) ACHIEVEMENTS ============================
    # Shape Shifter — global tiers (total shape keys created across all sessions)
    "SHAPE_SHIFTER_1": AchievementDefinition(
        id="SHAPE_SHIFTER_1", title="Shape Shifter I",
        description="Create 5 shape keys in total.",
        category="Milestones", counter="shapekeys_total", threshold=5,
        icon="Shape Shifter.png"),
    "SHAPE_SHIFTER_2": AchievementDefinition(
        id="SHAPE_SHIFTER_2", title="Shape Shifter II",
        description="Create 25 shape keys in total.",
        category="Milestones", counter="shapekeys_total", threshold=25,
        icon="Shape Shifter.png"),
    "SHAPE_SHIFTER_3": AchievementDefinition(
        id="SHAPE_SHIFTER_3", title="Shape Shifter III",
        description="Create 50 shape keys in total.",
        rare=True, category="Milestones", counter="shapekeys_total", threshold=50,
        icon="Shape Shifter.png"),

    # Good Habit — total manual saves
    "GOOD_HABIT_1": AchievementDefinition(
        id="GOOD_HABIT_1", title="Good Habit I",
        description="Save your project 100 times in total.",
        category="Milestones", counter="saves_total", threshold=100,
        icon="Good Habit.png"),
    "GOOD_HABIT_2": AchievementDefinition(
        id="GOOD_HABIT_2", title="Good Habit II",
        description="Save your project 1,000 times in total.",
        category="Milestones", counter="saves_total", threshold=1000,
        icon="Good Habit.png"),
    "GOOD_HABIT_3": AchievementDefinition(
        id="GOOD_HABIT_3", title="Good Habit III",
        description="Save your project 10,000 times in total.",
        rare=True, category="Milestones", counter="saves_total", threshold=10000,
        icon="Good Habit.png"),

    # NASA Computer — total completed renders
    "NASA_COMPUTER_1": AchievementDefinition(
        id="NASA_COMPUTER_1", title="NASA Computer I",
        description="Complete 100 renders in total.",
        category="Milestones", counter="renders_total", threshold=100,
        icon="NASA Computer.png"),
    "NASA_COMPUTER_2": AchievementDefinition(
        id="NASA_COMPUTER_2", title="NASA Computer II",
        description="Complete 1,000 renders in total.",
        category="Milestones", counter="renders_total", threshold=1000,
        icon="NASA Computer.png"),
    "NASA_COMPUTER_3": AchievementDefinition(
        id="NASA_COMPUTER_3", title="NASA Computer III",
        description="Complete 10,000 renders in total.",
        rare=True, category="Milestones", counter="renders_total", threshold=10000,
        icon="NASA Computer.png"),

    # Feature Film — total rendered frames
    "FEATURE_FILM": AchievementDefinition(
        id="FEATURE_FILM", title="Feature Film",
        description="Render 100,000 frames in total.",
        rare=True, category="Milestones", counter="frames_total", threshold=100000),

    # Cube Genocide — total default cubes deleted
    "CUBE_GENOCIDE_1": AchievementDefinition(
        id="CUBE_GENOCIDE_1", title="Cube Genocide I",
        description="Delete the default cube 10 times in total.",
        category="Milestones", counter="cubes_deleted", threshold=10,
        icon="Cube Genocide.png"),
    "CUBE_GENOCIDE_2": AchievementDefinition(
        id="CUBE_GENOCIDE_2", title="Cube Genocide II",
        description="Delete the default cube 100 times in total.",
        category="Milestones", counter="cubes_deleted", threshold=100,
        icon="Cube Genocide.png"),
    "CUBE_GENOCIDE_3": AchievementDefinition(
        id="CUBE_GENOCIDE_3", title="Cube Genocide III",
        description="Delete the default cube 1,000 times in total.",
        rare=True, category="Milestones", counter="cubes_deleted", threshold=1000,
        icon="Cube Genocide.png"),

    # Monkey Business — total Suzannes added
    "MONKEY_BUSINESS": AchievementDefinition(
        id="MONKEY_BUSINESS", title="Monkey Business",
        description="Add Suzanne to a scene 50 times in total.",
        category="Milestones", counter="suzannes_added", threshold=50),

    # Puppeteer — total keyframes set
    "PUPPETEER": AchievementDefinition(
        id="PUPPETEER", title="Puppeteer",
        description="Set 100,000 keyframes in total.",
        rare=True, category="Milestones", counter="keyframes_total", threshold=100000),

    # Polygon Tycoon — total polygons created
    "POLYGON_TYCOON": AchievementDefinition(
        id="POLYGON_TYCOON", title="Polygon Tycoon",
        description="Create one billion polygons in total.",
        rare=True, category="Milestones", counter="polygons_total", threshold=1000000000),

    # Material World — total materials created
    "MATERIAL_WORLD": AchievementDefinition(
        id="MATERIAL_WORLD", title="Material World",
        description="Create 1,000 materials in total.",
        category="Milestones", counter="materials_total", threshold=1000),

    # Node Architect — total node links connected
    "NODE_ARCHITECT": AchievementDefinition(
        id="NODE_ARCHITECT", title="Node Architect",
        description="Connect 10,000 node links in total.",
        category="Milestones", counter="node_links_total", threshold=10000),

    # Un Un Un Undo — total undos
    "UN_UN_UN_UNDO": AchievementDefinition(
        id="UN_UN_UN_UNDO", title="Un Un Un Undo",
        description="Undo 10,000 times in total.",
        category="Milestones", counter="undos_total", threshold=10000),

    # Bake Sale — total simulations baked
    "BAKE_SALE": AchievementDefinition(
        id="BAKE_SALE", title="Bake Sale",
        description="Bake 50 simulations in total.",
        category="Milestones", counter="bakes_total", threshold=50),

    # Unemployed — total Blender uptime (seconds)
    "UNEMPLOYED_1": AchievementDefinition(
        id="UNEMPLOYED_1", title="Unemployed I",
        description="Spend 10 hours in Blender in total.",
        category="Milestones", counter="uptime_seconds", threshold=36000,
        icon="Unemployed.png"),
    "UNEMPLOYED_2": AchievementDefinition(
        id="UNEMPLOYED_2", title="Unemployed II",
        description="Spend 100 hours in Blender in total.",
        category="Milestones", counter="uptime_seconds", threshold=360000,
        icon="Unemployed.png"),
    "UNEMPLOYED_3": AchievementDefinition(
        id="UNEMPLOYED_3", title="Unemployed III",
        description="Spend 1,000 hours in Blender in total.",
        rare=True, category="Milestones", counter="uptime_seconds", threshold=3600000,
        icon="Unemployed.png"),

    # Sculpt Sanctuary — total time in Sculpt Mode (seconds)
    "SCULPT_SANCTUARY": AchievementDefinition(
        id="SCULPT_SANCTUARY", title="Sculpt Sanctuary",
        description="Spend 20 hours in Sculpt Mode in total.",
        category="Milestones", counter="sculpt_seconds", threshold=72000),

    # Loyalty — total Blender launches
    "LOYALTY_1": AchievementDefinition(
        id="LOYALTY_1", title="Loyalty I",
        description="Launch Blender 100 times.",
        category="Milestones", counter="launches", threshold=100,
        icon="Loyalty.png"),
    "LOYALTY_2": AchievementDefinition(
        id="LOYALTY_2", title="Loyalty II",
        description="Launch Blender 500 times.",
        category="Milestones", counter="launches", threshold=500,
        icon="Loyalty.png"),
    "LOYALTY_3": AchievementDefinition(
        id="LOYALTY_3", title="Loyalty III",
        description="Launch Blender 1,000 times.",
        rare=True, category="Milestones", counter="launches", threshold=1000,
        icon="Loyalty.png"),

    # The Long Haul — a single render longer than 24 hours (event, not counter)
    "THE_LONG_HAUL": AchievementDefinition(
        id="THE_LONG_HAUL", title="The Long Haul",
        description="Keep a single render running for over 24 hours.",
        rare=True, category="Milestones"),

    # Live to Die Another Day — total crash recoveries
    "LIVE_TO_DIE_ANOTHER_DAY": AchievementDefinition(
        id="LIVE_TO_DIE_ANOTHER_DAY", title="Live to Die Another Day",
        description="Recover from a crash 10 times in total.",
        category="Milestones", counter="recoveries", threshold=10),

    # Streaks / distinct days
    "CONSISTENCY": AchievementDefinition(
        id="CONSISTENCY", title="Consistency",
        description="Open Blender 7 days in a row.",
        category="Milestones", counter="streak", threshold=7),
    "DEDICATED": AchievementDefinition(
        id="DEDICATED", title="Dedicated",
        description="Open Blender 30 days in a row.",
        rare=True, category="Milestones", counter="streak", threshold=30),
    "YEAR_OF_THE_DONUT": AchievementDefinition(
        id="YEAR_OF_THE_DONUT", title="Year of the Donut",
        description="Use Blender on 365 different days.",
        rare=True, category="Milestones", counter="distinct_days", threshold=365),
}


# --- Achievement Category Sets for Handler Short-Circuiting ---
DEPSGRAPH_ACHIEVEMENT_IDS = {
    "GOODBYE_CUBE", "SUZANNES_BLESSING", "SUBDIV_OVERKILL", "NODE_SPAGHETTI",
    "GEOMETRY_NODES_GURU", "COLOR_RAMP_ADDICT", "BONE_COLLECTOR",
    "PARTICLE_STORM", "SUN_GOD", "MATERIAL_HOARDER", "EMISSION_OVERDRIVE"
}

FRAME_CHANGE_ACHIEVEMENT_IDS = {
    "GRAVITY_MASTER", "CLOTH_EXPLOSION"
}

RENDER_PRE_ACHIEVEMENT_IDS = {
    "RESPECT_THE_CUBE", "DONUT_MASTER", "PURE_PROCEDURAL",
    "DENOISE_MAGIC", "CYCLES_ENTHUSIAST", "ALPHA_TRANSLUCENCY"
}

TIMER_ACHIEVEMENT_IDS = {
    "POLYGON_KING", "UV_UNWRAPPING_PAIN", "SAVED_BY_SHIELD",
    "DRIVER_SPECIALIST", "LIVING_ON_THE_EDGE",
    "ADDON_COLLECTOR", "OUTLINER_CHAOS", "NIGHT_SHIFT"
}

HEAVY_NODE_ACHIEVEMENT_IDS = {
    "NODE_SPAGHETTI", "GEOMETRY_NODES_GURU", "COLOR_RAMP_ADDICT", "EMISSION_OVERDRIVE"
}

# --- Event Tracking State Variables ---
_known_objects = None
_launch_time = time.time()
_last_save_time = time.time()
_session_save_count = 0
_uv_editing_seconds = 0
_render_start_time = None
_rendered_frames_count = 0
_motion_blur_active_at_render_start = False
_pending_render_ids: Set[str] = set()   # рендер-ачивки, що чекають на видачу після завершення
RENDER_REWARD_DELAY = 2.0               # затримка (сек) перед видачею після рендера

# --- Session baseline (щоб зараховувати лише зроблене цієї сесії, а не вміст
#     уже відкритого файлу). Знімається на старті сесії / відкритті файлу. ---
_baseline = None                        # dict з множинами імен та лічильниками або None
_respect_cube_armed = False             # True лише якщо сесія стартувала з фабричного файлу
_undo_timestamps: List[float] = []
_shortcut_timestamps: List[Tuple[float, str]] = []
_knife_cut_count = 0
_graph_tweaks = 0
_applied_objects_count = 0
_msgbus_owners: List[object] = []
_last_depsgraph_heavy_scan_time = 0.0
_last_depsgraph_node_sig = None



# --- Operator / Manual Event Tracking API Hooks ---

def record_object_join(count: int = 100):
    global _max_join_count
    from .engine import get_engine
    eng = get_engine()
    if count > _max_join_count:
        _max_join_count = count
    if not eng.is_unlocked("FATAL_CTRL_J") and count >= 100:
        eng.unlock("FATAL_CTRL_J")


def record_normals_flipped():
    from .engine import get_engine
    eng = get_engine()
    if not eng.is_unlocked("INVERTED_REALITY"):
        eng.unlock("INVERTED_REALITY")


def record_knife_cut(count: int = 1):
    global _knife_cut_count
    from .engine import get_engine
    eng = get_engine()
    if not eng.is_unlocked("KNIFE_MASTER"):
        _knife_cut_count += count
        if _knife_cut_count >= 50:
            eng.unlock("KNIFE_MASTER")


def record_merge_by_distance(delta_vertices: int):
    global _max_merge_count
    from .engine import get_engine
    eng = get_engine()
    if delta_vertices > _max_merge_count:
        _max_merge_count = delta_vertices
    if not eng.is_unlocked("MERGE_MASTER") and delta_vertices >= 100:
        eng.unlock("MERGE_MASTER")


def record_graph_tweak(count: int = 1):
    global _graph_tweaks
    from .engine import get_engine
    eng = get_engine()
    if not eng.is_unlocked("GRAPH_EDITOR_TWEAKER"):
        _graph_tweaks += count
        if _graph_tweaks >= 100:
            eng.unlock("GRAPH_EDITOR_TWEAKER")


def record_bake(frame_count: int):
    from .engine import get_engine
    eng = get_engine()
    eng.add_stat("bakes_total", 1)          # Bake Sale (global)
    if not eng.is_unlocked("THE_BIG_BAKE") and frame_count > 250:
        eng.unlock("THE_BIG_BAKE")


def record_undo():
    global _undo_timestamps
    from .engine import get_engine
    eng = get_engine()
    eng.add_stat("undos_total", 1)          # Un Un Un Undo (global)
    if not eng.is_unlocked("CTRL_Z_HERO"):
        now = time.time()
        _undo_timestamps.append(now)
        _undo_timestamps = [t for t in _undo_timestamps if now - t <= 60.0]
        if len(_undo_timestamps) >= 50:
            eng.unlock("CTRL_Z_HERO")


def record_shortcut_used(shortcut_id: str):
    global _shortcut_timestamps
    from .engine import get_engine
    eng = get_engine()
    if not eng.is_unlocked("SHORTCUT_NINJA"):
        now = time.time()
        _shortcut_timestamps.append((now, shortcut_id))
        _shortcut_timestamps = [(t, sid) for t, sid in _shortcut_timestamps if now - t <= 60.0]
        unique_shortcuts = {sid for _, sid in _shortcut_timestamps}
        if len(unique_shortcuts) >= 30:
            eng.unlock("SHORTCUT_NINJA")


def record_transform_apply(count: int = 1):
    global _applied_objects_count
    from .engine import get_engine
    eng = get_engine()
    if not eng.is_unlocked("APPLY_ALL"):
        _applied_objects_count += count
        if _applied_objects_count >= 20:
            eng.unlock("APPLY_ALL")


def trigger_vram_error():
    from .engine import get_engine
    eng = get_engine()
    if not eng.is_unlocked("VRAM_VICTIM"):
        eng.unlock("VRAM_VICTIM")


# --- Background Operator Watcher ---
# Деякі ачивки (Frankenstein/join, Surgical Precision/knife, Singularity/
# merge by distance, Time Traveler/undo, Shortcut Ninja, Know your Place/
# apply transform, Graph Editor Tweaker, Let it cook/bake, Up is Down/normals)
# неможливо визначити зі стану сцени — потрібно бачити САМІ оператори.
# Blender не дає прямого "оператор виконано" хендлера в стабільному API,
# тож користуємось `bpy.context.window_manager.operators` — це список усіх
# операторів, викликаних за сесію (те саме джерело, що живить F6/Redo-панель).
# Невидимий модальний оператор (ACHIEVEMENT_OT_watcher, __init__.py) щотік
# викликає watcher_tick(), а на кожен PRESS — watcher_key_event().

_watcher_running = False
_watcher_instance_active = False  # True, поки жива МОДАЛЬНА копія оператора
_watcher_last_op_count = None    # None = baseline ще не зафіксовано
_watcher_prev_obj_count = None
_watcher_mesh_stats = {}         # ob.name -> (vert_count, edge_count)

_SHORTCUT_IGNORE_TYPES = {
    'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE', 'NONE', 'WINDOW_DEACTIVATE',
    'LEFTMOUSE', 'RIGHTMOUSE', 'MIDDLEMOUSE',
    'BUTTON4MOUSE', 'BUTTON5MOUSE', 'BUTTON6MOUSE', 'BUTTON7MOUSE',
    'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'WHEELINMOUSE', 'WHEELOUTMOUSE',
    'TIMER', 'TIMER0', 'TIMER1', 'TIMER2', 'TIMER_JOBS', 'TIMER_AUTOSAVE', 'TIMER_REPORT',
}

_BAKE_OP_IDS = {'ptcache.bake_all', 'ptcache.bake', 'fluid.bake_all', 'fluid.bake_data'}
_GRAPH_TRANSFORM_OP_IDS = {'transform.translate', 'transform.transform',
                          'transform.rotate', 'transform.resize'}


def start_watcher():
    global _watcher_running
    _watcher_running = True


def stop_watcher():
    global _watcher_running
    _watcher_running = False
    # Не скидаємо _watcher_instance_active тут: жива modal-копія сама зробить
    # це в _stop(), коли побачить _watcher_running=False на наступній події.


def is_watcher_running() -> bool:
    return _watcher_running


def watcher_instance_start() -> bool:
    """Захист від подвійного запуску modal-оператора (напр. швидке
    вимкнути/увімкнути аддон). True — можна стартувати; False — вже є жива копія."""
    global _watcher_instance_active
    if _watcher_instance_active:
        return False
    _watcher_instance_active = True
    return True


def watcher_instance_stop():
    global _watcher_instance_active
    _watcher_instance_active = False


def watcher_key_event(event):
    """Реєструє клавіатурний шорткат для Shortcut Ninja (лише клавіатура,
    без відкриття мишею меню — тому клавіші миші й колесо виключені)."""
    if not _watcher_running:
        return
    try:
        if event.value != 'PRESS' or event.type in _SHORTCUT_IGNORE_TYPES:
            return
        mods = ''.join(m for m, flag in (
            ('C', event.ctrl), ('A', event.alt), ('S', event.shift), ('O', event.oskey)
        ) if flag)
        record_shortcut_used(f"{mods}:{event.type}")
    except Exception as _dbg_err:
        debug.log("achievements.py:792", _dbg_err)
        pass


def _mesh_edit_stats(ob):
    """(vert_count, edge_count) активного меша (edit або object mode) або None."""
    try:
        me = ob.data
        if ob.mode == 'EDIT':
            import bmesh
            bm = bmesh.from_edit_mesh(me)
            return (len(bm.verts), len(bm.edges))
        return (len(me.vertices), len(me.edges))
    except Exception as _dbg_err:
        debug.log("achievements.py:805", _dbg_err)
        return None


def _is_graph_editor_context(context) -> bool:
    try:
        screen = getattr(context, "screen", None)
        areas = getattr(screen, "areas", None) if screen else None
        return bool(areas) and any(getattr(a, "type", None) == 'GRAPH_EDITOR' for a in areas)
    except Exception as _dbg_err:
        debug.log("achievements.py:814", _dbg_err)
        return False


def _scene_has_fluid_domain(scene) -> bool:
    """Чи є в сцені FLUID-модифікатор типу Domain (щоб не плутати з cloth/rigid bake)."""
    try:
        for ob in scene.objects:
            if ob.type != 'MESH':
                continue
            for mod in ob.modifiers:
                if getattr(mod, "type", "") == 'FLUID' and getattr(mod, "fluid_type", "") == 'DOMAIN':
                    return True
    except Exception as _dbg_err:
        debug.log("achievements.py:827", _dbg_err)
        pass
    return False


def _dispatch_watched_operator(idname, context, cur_obj_count, cur_mesh_stats, ob):
    global _watcher_prev_obj_count
    try:
        if idname == 'object.join':
            # object.join зводить N виділених об'єктів до 1 — дельта загальної
            # к-сті об'єктів у сцені = N-1, тож N = delta+1.
            delta = _watcher_prev_obj_count - cur_obj_count
            if delta > 0:
                record_object_join(count=delta + 1)

        elif idname in ('mesh.flip_normals', 'mesh.normals_make_consistent'):
            record_normals_flipped()

        elif idname == 'mesh.knife_tool':
            if ob is not None and cur_mesh_stats is not None:
                prev = _watcher_mesh_stats.get(ob.name)
                if prev is not None:
                    d_edges = cur_mesh_stats[1] - prev[1]
                    if d_edges > 0:
                        record_knife_cut(count=d_edges)

        elif idname == 'mesh.remove_doubles':
            if ob is not None and cur_mesh_stats is not None:
                prev = _watcher_mesh_stats.get(ob.name)
                if prev is not None:
                    d_verts = prev[0] - cur_mesh_stats[0]
                    if d_verts > 0:
                        record_merge_by_distance(delta_vertices=d_verts)

        elif idname in _GRAPH_TRANSFORM_OP_IDS:
            if _is_graph_editor_context(context):
                record_graph_tweak(count=1)

        elif idname == 'object.transform_apply':
            count = len(getattr(context, "selected_objects", None) or [])
            if count > 0:
                record_transform_apply(count=count)

        elif idname in _BAKE_OP_IDS:
            scene = context.scene
            if scene is not None and _scene_has_fluid_domain(scene):
                frame_count = int(scene.frame_end) - int(scene.frame_start)
                if frame_count > 0:
                    record_bake(frame_count=frame_count)

        elif idname == 'ed.undo':
            record_undo()
    except Exception as _dbg_err:
        debug.log("achievements.py:879", _dbg_err)
        pass


def watcher_tick(context):
    """Періодична (TIMER, ~5 Гц) перевірка нових операторів та стану меша.

    Перший виклик лише фіксує baseline (щоб уся операторська історія
    ДО старту сесії не була раптово оброблена як "нова" і не зарахувала
    ачивки заднім числом).
    """
    global _watcher_last_op_count, _watcher_prev_obj_count, _watcher_mesh_stats
    if not _watcher_running:
        return
    try:
        wm = context.window_manager
        ops = wm.operators
        n = len(ops)

        cur_obj_count = len(bpy.data.objects)
        if _watcher_prev_obj_count is None:
            _watcher_prev_obj_count = cur_obj_count

        ob = context.active_object
        cur_mesh_stats = _mesh_edit_stats(ob) if ob is not None and ob.type == 'MESH' else None

        if _watcher_last_op_count is None:
            _watcher_last_op_count = n
        elif n > _watcher_last_op_count:
            for op in ops[_watcher_last_op_count:n]:
                idname = getattr(op, "bl_idname", "") or ""
                _dispatch_watched_operator(idname, context, cur_obj_count, cur_mesh_stats, ob)
            _watcher_last_op_count = n
        elif n < _watcher_last_op_count:
            # список могли обрізати/скинути (напр. новий файл) — просто ребазуємось
            _watcher_last_op_count = n

        _watcher_prev_obj_count = cur_obj_count
        if ob is not None and cur_mesh_stats is not None:
            _watcher_mesh_stats[ob.name] = cur_mesh_stats
    except Exception as _dbg_err:
        debug.log("achievements.py:919", _dbg_err)
        pass


# --- Object Snapshot Utilities ---

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


def ensure_snapshot():
    """Lazy initialization of object snapshot (bpy.data is restricted during register)."""
    global _known_objects
    if _known_objects is None:
        try:
            _known_objects = snapshot_objects()
            return True
        except Exception as _dbg_err:
            debug.log("achievements.py:946", _dbg_err)
            return False
    return False


# --- Session baseline utilities ---

def _count_drivers() -> int:
    """К-сть драйверів у сцені (objects/materials/shape_keys)."""
    n = 0
    for db_list in (bpy.data.objects, bpy.data.materials, bpy.data.shape_keys):
        for item in db_list:
            ad = getattr(item, "animation_data", None)
            if ad and hasattr(ad, "drivers"):
                n += len(ad.drivers)
    return n


def _count_fake_users() -> int:
    """К-сть датаблоків із увімкненим Fake User (Shield) та без інших користувачів."""
    n = 0
    for collection in (bpy.data.materials, bpy.data.textures, bpy.data.node_groups,
                       bpy.data.actions, bpy.data.armatures):
        for db in collection:
            if getattr(db, "use_fake_user", False) and getattr(db, "users", 0) <= 1:
                n += 1
    return n


def _snapshot_baseline() -> dict:
    """Зліпок стану на старті сесії / відкритті файлу: імена наявних датаблоків
    (щоб відрізнити створене цієї сесії) + деякі лічильники для дельт."""
    return {
        'objects': set(o.name for o in bpy.data.objects),
        'materials': set(m.name for m in bpy.data.materials),
        'node_groups': set(ng.name for ng in bpy.data.node_groups),
        'particles': set(p.name for p in bpy.data.particles),
        'lights': set(l.name for l in bpy.data.lights),
        'actions': set(a.name for a in bpy.data.actions),
        'driver_count': _count_drivers(),
        'fake_user_count': _count_fake_users(),
        'addon_count': len(getattr(getattr(bpy.context, "preferences", None), "addons", []) or []),
        'compositor_nodes': _count_compositor_nodes(),
    }


def _capture_baseline():
    """Знімає baseline та зводить прапорець Respect the Cube (фабрична сесія)."""
    global _baseline, _respect_cube_armed
    try:
        _baseline = _snapshot_baseline()
        # Куб зараховуємо лише у сесії, що стартувала з фабричного/нового файлу
        # (не з відкритого користувачем .blend).
        _respect_cube_armed = (bpy.data.filepath == "")
    except Exception as _dbg_err:
        debug.log("achievements.py:1000", _dbg_err)
        _baseline = None


def _ensure_baseline():
    """Лінива ініціалізація baseline (bpy.data недоступний під час register)."""
    if _baseline is None:
        _capture_baseline()


def _is_new(kind: str, name: str) -> bool:
    """True, якщо датаблок `name` створено цієї сесії (немає у baseline `kind`)."""
    if _baseline is None:
        return False
    return name not in _baseline.get(kind, ())


# --- Global cumulative-counter helpers ---

_delta_last = {}          # останні бачені сумарні значення для дельта-лічильників
_session_started = False  # чи вже нарахували запуск/день цієї сесії
_prev_object_count = None # для детекції масового видалення (The Purge)
_flush_tick = 0           # лічильник тіків для періодичного флашу stats на диск
_idle_seconds = 0         # секунди без активності (What am I doing?)
_max_join_count = 0       # найбільше об'єднання за раз (для прогресу Frankenstein)
_max_merge_count = 0      # найбільше злиття вершин за раз (для прогресу Singularity)


def _count_total_polys() -> int:
    return sum(len(ob.data.polygons) for ob in bpy.data.objects
              if ob.type == 'MESH' and ob.data)


def _count_total_node_links() -> int:
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


def _count_total_shapekeys() -> int:
    return sum(len(sk.key_blocks) for sk in bpy.data.shape_keys)


def _count_compositor_nodes() -> int:
    return sum(len(sc.node_tree.nodes) for sc in bpy.data.scenes
              if getattr(sc, "node_tree", None))


def _accum_delta(eng, stat_key: str, current: int):
    """Додає до глобального лічильника лише додатний приріст сумарного значення.
    Перший замір (або після відкриття файлу) лише запам'ятовує baseline."""
    last = _delta_last.get(stat_key)
    if last is None:
        _delta_last[stat_key] = current
        return
    if current > last:
        eng.add_stat(stat_key, current - last)
    _delta_last[stat_key] = current


_ngon_cache = {}   # mesh_name -> (poly_count, verdict) — щоб не сканувати те саме двічі


def _mesh_has_ngon(mesh) -> bool:
    """Чи є в мешу грань із 10+ сторонами. numpy-шлях + кеш за к-стю полігонів."""
    polys = mesh.polygons
    n = len(polys)
    if not n:
        return False

    # Кеш: повторно скануємо лише якщо змінилася к-сть полігонів.
    cached = _ngon_cache.get(mesh.name)
    if cached is not None and cached[0] == n:
        return cached[1]

    verdict = False
    try:
        import numpy as np
        buf = np.empty(n, dtype=np.int32)
        polys.foreach_get("loop_total", buf)
        verdict = bool((buf >= 10).any())
    except Exception as _dbg_err:
        debug.log("achievements.py:1090", _dbg_err)
        try:
            # Без numpy: дешевий ранній вихід, без матеріалізації всього меша.
            for p in polys:
                if p.loop_total >= 10:
                    verdict = True
                    break
        except Exception as _dbg_err:
            debug.log("achievements.py:1097", _dbg_err)
            verdict = False

    _ngon_cache[mesh.name] = (n, verdict)
    return verdict


def _has_ngon_new_mesh() -> bool:
    """True, якщо на мешу, створеному цієї сесії, є грань із 10+ сторонами."""
    for ob in bpy.data.objects:
        if ob.type == 'MESH' and ob.data and _is_new('objects', ob.name):
            if _mesh_has_ngon(ob.data):
                return True
    return False


def _norm_prop(path: str, index: int) -> str:
    """Нормалізує property-шлях до вигляду 'base[index]' для порівняння."""
    axis = {'.x': 0, '.y': 1, '.z': 2, '.w': 3, '.r': 0, '.g': 1, '.b': 2, '.a': 3}
    for suf, i in axis.items():
        if path.endswith(suf):
            return f"{path[:-2]}[{i}]"
    if path.endswith(']'):
        return path
    return f"{path}[{max(index, 0)}]"


def _has_self_referencing_driver() -> bool:
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


def _detect_appended_this_session() -> bool:
    """True, якщо цієї сесії з'явився датаблок з бібліотеки (append/link)."""
    for kind, coll in (('objects', bpy.data.objects),
                       ('materials', bpy.data.materials),
                       ('node_groups', bpy.data.node_groups)):
        for db in coll:
            if _is_new(kind, db.name) and (
                getattr(db, "library", None) is not None or
                getattr(db, "library_weak_reference", None) is not None):
                return True
    return False


# --- App Handler Callbacks ---

@persistent
def on_depsgraph_update(scene, depsgraph):
    """Tracks object creation/deletion, modifiers, nodes, armatures, particles, and lights."""
    from .engine import get_engine
    eng = get_engine()

    _ensure_baseline()   # зафіксувати стан сесії, щоб рахувати лише нове
    global _prev_object_count, _idle_seconds
    _idle_seconds = 0    # будь-яка зміна сцени = активність (скидає таймер безділля)

    # Top-level short-circuit коли все, що дає depsgraph (включно з глобальними
    # лічильниками кубів/мавп та The Purge / N-gon), вже отримано.
    if (all(eng.is_unlocked(aid) for aid in DEPSGRAPH_ACHIEVEMENT_IDS) and
            all(eng.is_unlocked(aid) for aid in (
                "CUBE_GENOCIDE_1", "CUBE_GENOCIDE_2", "CUBE_GENOCIDE_3",
                "MONKEY_BUSINESS", "THE_PURGE", "N_GON_CRIMINAL"))):
        return

    # 1. Object changes: GOODBYE_CUBE, SUZANNES_BLESSING + global Cube Genocide / Monkey Business
    global _known_objects
    if not ensure_snapshot():
        try:
            current = snapshot_objects()
            prev_names = set(_known_objects.keys())
            cur_names = set(current.keys())
            removed_names = prev_names - cur_names
            added_names = cur_names - prev_names
            current_mesh_names = {info["mesh_name"] for info in current.values()}

            # Deleted default cubes → GOODBYE_CUBE (session) + Cube Genocide (global)
            deleted_cubes = 0
            for name in removed_names:
                info = _known_objects.get(name)
                if not info or info.get("type") != 'MESH':
                    continue
                mesh_name = info.get("mesh_name", "")
                if mesh_name in current_mesh_names:
                    continue
                obj_name = info.get("name", "")
                is_cube = mesh_name.lower().startswith("cube") or (
                    obj_name.lower().startswith("cube") and not any(
                        mesh_name.lower().startswith(other) for other in (
                            "sphere", "plane", "cylinder", "monkey", "torus", "cone", "circle", "icosphere"
                        )
                    )
                )
                if is_cube:
                    deleted_cubes += 1
            if deleted_cubes:
                eng.add_stat("cubes_deleted", deleted_cubes)
                if not eng.is_unlocked("GOODBYE_CUBE"):
                    eng.unlock("GOODBYE_CUBE")

            # Newly added monkeys → SUZANNES_BLESSING (session) + Monkey Business (global)
            new_monkeys = 0
            for name in added_names:
                ob = bpy.data.objects.get(name)
                if ob and getattr(ob, "type", None) == 'MESH' and ob.data:
                    n_low = ob.name.lower()
                    m_low = ob.data.name.lower()
                    if "suzanne" in n_low or "monkey" in n_low or "suzanne" in m_low or "monkey" in m_low:
                        new_monkeys += 1
            if new_monkeys:
                eng.add_stat("suzannes_added", new_monkeys)
                if not eng.is_unlocked("SUZANNES_BLESSING"):
                    eng.unlock("SUZANNES_BLESSING")

            _known_objects = current

        except Exception as _dbg_err:
            debug.log("achievements.py:1231", _dbg_err)
            pass

    # 1b. THE_PURGE — масове видалення 100+ об'єктів за одну операцію
    try:
        cur_obj_count = len(bpy.data.objects)
        if not eng.is_unlocked("THE_PURGE"):
            if _prev_object_count is not None and (_prev_object_count - cur_obj_count) >= 100:
                eng.unlock("THE_PURGE")
        _prev_object_count = cur_obj_count
    except Exception as _dbg_err:
        debug.log("achievements.py:1241", _dbg_err)
        pass


    # 2. SUBDIV_OVERKILL check — лише на об'єктах, доданих цієї сесії
    if not eng.is_unlocked("SUBDIV_OVERKILL"):
        try:
            for ob in bpy.data.objects:
                if ob.type == 'MESH' and _is_new('objects', ob.name):
                    for mod in ob.modifiers:
                        if mod.type == 'SUBSURF' and (mod.levels >= 6 or mod.render_levels >= 6):
                            eng.unlock("SUBDIV_OVERKILL")
                            break
        except Exception as _dbg_err:
            debug.log("achievements.py:1254", _dbg_err)
            pass

    # Debounce heavy node tree scans (NODE_SPAGHETTI, GEOMETRY_NODES_GURU, COLOR_RAMP_ADDICT, EMISSION_OVERDRIVE)
    global _last_depsgraph_heavy_scan_time
    now = time.monotonic()
    should_scan_heavy = False
    if (not all(eng.is_unlocked(aid) for aid in HEAVY_NODE_ACHIEVEMENT_IDS)
            or not eng.is_unlocked("N_GON_CRIMINAL")):
        if depsgraph is None or (now - _last_depsgraph_heavy_scan_time) >= 1.5:
            should_scan_heavy = True
            if depsgraph is not None:
                _last_depsgraph_heavy_scan_time = now

    if should_scan_heavy:
        # 2b. N_GON_CRIMINAL — грань із 10+ сторонами на мешу цієї сесії (debounced)
        if not eng.is_unlocked("N_GON_CRIMINAL"):
            try:
                if _has_ngon_new_mesh():
                    eng.unlock("N_GON_CRIMINAL")
            except Exception as _dbg_err:
                debug.log("achievements.py:1274", _dbg_err)
                pass

        # 3. NODE_SPAGHETTI check — лише матеріали/групи, створені цієї сесії
        if not eng.is_unlocked("NODE_SPAGHETTI"):
            try:
                for mat in bpy.data.materials:
                    if _is_new('materials', mat.name) and getattr(mat, "node_tree", None):
                        if len(mat.node_tree.nodes) >= 50 and len(mat.node_tree.links) >= 49:
                            eng.unlock("NODE_SPAGHETTI")
                            break
                if not eng.is_unlocked("NODE_SPAGHETTI"):
                    for ng in bpy.data.node_groups:
                        if _is_new('node_groups', ng.name) and len(ng.nodes) >= 50 and len(ng.links) >= 49:
                            eng.unlock("NODE_SPAGHETTI")
                            break
            except Exception as _dbg_err:
                debug.log("achievements.py:1290", _dbg_err)
                pass

        # 4. GEOMETRY_NODES_GURU check — лише групи, створені цієї сесії
        if not eng.is_unlocked("GEOMETRY_NODES_GURU"):
            try:
                for ng in bpy.data.node_groups:
                    if _is_new('node_groups', ng.name) and sum(1 for n in ng.nodes if getattr(n, "type", "") == 'GROUP') >= 5:
                        eng.unlock("GEOMETRY_NODES_GURU")
                        break
            except Exception as _dbg_err:
                debug.log("achievements.py:1300", _dbg_err)
                pass

        # 5. COLOR_RAMP_ADDICT check — лише матеріали, створені цієї сесії
        if not eng.is_unlocked("COLOR_RAMP_ADDICT"):
            try:
                for mat in bpy.data.materials:
                    if _is_new('materials', mat.name) and getattr(mat, "node_tree", None):
                        if sum(1 for n in mat.node_tree.nodes if getattr(n, "type", "") == 'VALTORGB') >= 5:
                            eng.unlock("COLOR_RAMP_ADDICT")
                            break
            except Exception as _dbg_err:
                debug.log("achievements.py:1311", _dbg_err)
                pass

        # 10. EMISSION_OVERDRIVE check — лише матеріали, створені цієї сесії
        if not eng.is_unlocked("EMISSION_OVERDRIVE"):
            try:
                for mat in bpy.data.materials:
                    if _is_new('materials', mat.name) and getattr(mat, "node_tree", None):
                        for node in mat.node_tree.nodes:
                            if node.type == 'EMISSION':
                                strength = node.inputs['Strength'].default_value if 'Strength' in node.inputs else 0
                                if strength > 10000:
                                    eng.unlock("EMISSION_OVERDRIVE")
                                    break
                            elif node.type == 'BSDF_PRINCIPLED':
                                if 'Emission Strength' in node.inputs:
                                    if node.inputs['Emission Strength'].default_value > 10000:
                                        eng.unlock("EMISSION_OVERDRIVE")
                                        break
            except Exception as _dbg_err:
                debug.log("achievements.py:1330", _dbg_err)
                pass

    # 6. BONE_COLLECTOR check — лише скелети, створені цієї сесії
    if not eng.is_unlocked("BONE_COLLECTOR"):
        try:
            for ob in bpy.data.objects:
                if ob.type == 'ARMATURE' and ob.data and _is_new('objects', ob.name):
                    if len(ob.data.bones) > 50 or (getattr(ob, "mode", "") == 'EDIT' and hasattr(ob.data, "edit_bones") and len(ob.data.edit_bones) > 50):
                        eng.unlock("BONE_COLLECTOR")
                        break
        except Exception as _dbg_err:
            debug.log("achievements.py:1341", _dbg_err)
            pass

    # 7. PARTICLE_STORM check — лише системи, створені цієї сесії
    if not eng.is_unlocked("PARTICLE_STORM"):
        try:
            for ps in bpy.data.particles:
                if _is_new('particles', ps.name) and getattr(ps, "count", 0) >= 100000:
                    eng.unlock("PARTICLE_STORM")
                    break
        except Exception as _dbg_err:
            debug.log("achievements.py:1351", _dbg_err)
            pass

    # 8. SUN_GOD check — лише світла, додані цієї сесії
    if not eng.is_unlocked("SUN_GOD"):
        try:
            for light in bpy.data.lights:
                if _is_new('lights', light.name) and getattr(light, "type", "") == 'SUN' and getattr(light, "energy", 0.0) > 1000.0:
                    eng.unlock("SUN_GOD")
                    break
        except Exception as _dbg_err:
            debug.log("achievements.py:1361", _dbg_err)
            pass

    # 9. MATERIAL_HOARDER check — лише матеріали, створені цієї сесії
    if not eng.is_unlocked("MATERIAL_HOARDER") and _baseline is not None:
        try:
            new_materials = sum(1 for m in bpy.data.materials if _is_new('materials', m.name))
            if new_materials >= 30:
                eng.unlock("MATERIAL_HOARDER")
        except Exception as _dbg_err:
            debug.log("achievements.py:1370", _dbg_err)
            pass


@persistent
def on_render_pre(scene):
    """Викликається перед початком рендеру. Рендер-ачивки тут НЕ видаються,
    щоб не зараховувати скасовані або недорендерені кадри."""
    pass


def _scene_render_candidates(scene):
    """set рендер-ачивок за станом сцени, які виконані, але ще не отримані."""
    from .engine import get_engine
    eng = get_engine()
    ids = set()

    # RESPECT_THE_CUBE — лише фабричний дефолтний куб у сесії, що стартувала з
    # фабричного/нового файлу (не доданий Shift+D і не з відкритого користувачем .blend).
    if not eng.is_unlocked("RESPECT_THE_CUBE") and _respect_cube_armed:
        try:
            for ob in scene.objects:
                # має бути присутнім із початку сесії (не створений цієї сесії)
                if _is_new('objects', ob.name):
                    continue
                if ob.name == "Cube" and ob.type == 'MESH' and ob.data and ob.data.name.startswith("Cube"):
                    if len(ob.data.vertices) == 8 and len(ob.data.polygons) == 6:
                        loc = ob.location
                        scale = ob.scale
                        rot = ob.rotation_euler
                        if (abs(loc.x) < 1e-4 and abs(loc.y) < 1e-4 and abs(loc.z) < 1e-4 and
                            abs(scale.x - 1.0) < 1e-4 and abs(scale.y - 1.0) < 1e-4 and abs(scale.z - 1.0) < 1e-4 and
                            abs(rot.x) < 1e-4 and abs(rot.y) < 1e-4 and abs(rot.z) < 1e-4):
                            ids.add("RESPECT_THE_CUBE")
                            break
        except Exception as _dbg_err:
            debug.log("achievements.py:1405", _dbg_err)
            pass

    # DONUT_MASTER
    if not eng.is_unlocked("DONUT_MASTER"):
        try:
            for ob in scene.objects:
                if ob.type == 'MESH' and ob.data:
                    if "torus" in ob.name.lower() or "torus" in ob.data.name.lower():
                        for mat_slot in ob.material_slots:
                            if mat_slot.material:
                                mname = mat_slot.material.name.lower()
                                if "glaze" in mname or "donut" in mname:
                                    ids.add("DONUT_MASTER")
                                    break
        except Exception as _dbg_err:
            debug.log("achievements.py:1420", _dbg_err)
            pass

    # PURE_PROCEDURAL
    if not eng.is_unlocked("PURE_PROCEDURAL"):
        try:
            for ob in scene.objects:
                if ob.type == 'MESH' and ob.data:
                    for slot in ob.material_slots:
                        mat = slot.material
                        if mat and getattr(mat, "node_tree", None):
                            nodes = mat.node_tree.nodes
                            if len(nodes) >= 10:
                                if not any(n.type == 'TEX_IMAGE' for n in nodes):
                                    ids.add("PURE_PROCEDURAL")
                                    break
        except Exception as _dbg_err:
            debug.log("achievements.py:1436", _dbg_err)
            pass

    # DENOISE_MAGIC
    if not eng.is_unlocked("DENOISE_MAGIC"):
        try:
            cycles = getattr(scene, "cycles", None)
            if cycles and cycles.samples < 32 and getattr(cycles, "use_denoising", False):
                ids.add("DENOISE_MAGIC")
        except Exception as _dbg_err:
            debug.log("achievements.py:1445", _dbg_err)
            pass

    # CYCLES_ENTHUSIAST
    if not eng.is_unlocked("CYCLES_ENTHUSIAST"):
        try:
            cycles = getattr(scene, "cycles", None)
            if cycles and cycles.samples > 10000:
                ids.add("CYCLES_ENTHUSIAST")
        except Exception as _dbg_err:
            debug.log("achievements.py:1454", _dbg_err)
            pass

    # ALPHA_TRANSLUCENCY
    if not eng.is_unlocked("ALPHA_TRANSLUCENCY"):
        try:
            if getattr(getattr(scene, "render", None), "film_transparent", False):
                ids.add("ALPHA_TRANSLUCENCY")
        except Exception as _dbg_err:
            debug.log("achievements.py:1462", _dbg_err)
            pass

    return ids


def _timing_render_candidates(scene):
    """set рендер-ачивок за таймінгом (тривалість/кадри/мо-блюр)."""
    from .engine import get_engine
    eng = get_engine()
    ids = set()
    if _render_start_time is None:
        return ids
    elapsed = time.time() - _render_start_time

    # EEVEE_SPEEDSTER
    if not eng.is_unlocked("EEVEE_SPEEDSTER") and _rendered_frames_count >= 100 and elapsed < 60.0:
        ids.add("EEVEE_SPEEDSTER")
    # SPEED_BLUR
    if not eng.is_unlocked("SPEED_BLUR") and _motion_blur_active_at_render_start:
        ids.add("SPEED_BLUR")
    # NIGHT_SHIFT
    if not eng.is_unlocked("NIGHT_SHIFT") and elapsed >= 14400:
        ids.add("NIGHT_SHIFT")
    # THE_LONG_HAUL — один рендер понад 24 години (global milestone)
    if not eng.is_unlocked("THE_LONG_HAUL") and elapsed >= 86400:
        ids.add("THE_LONG_HAUL")
    return ids


def _reward_pending_render():
    """Одноразовий таймер: видає відкладені рендер-ачивки через RENDER_REWARD_DELAY с."""
    global _pending_render_ids
    from .engine import get_engine
    eng = get_engine()
    ids = list(_pending_render_ids)
    _pending_render_ids = set()
    for aid in ids:
        if not eng.is_unlocked(aid):
            eng.unlock(aid)
    return None   # одноразово


def _schedule_render_reward(delay=RENDER_REWARD_DELAY):
    try:
        if bpy.app.timers.is_registered(_reward_pending_render):
            return
    except Exception as _dbg_err:
        debug.log("achievements.py:1509", _dbg_err)
        pass
    try:
        bpy.app.timers.register(_reward_pending_render, first_interval=delay)
    except (ValueError, RuntimeError):
        pass


@persistent
def on_render_init(scene):
    global _render_start_time, _rendered_frames_count, _motion_blur_active_at_render_start, _idle_seconds
    _render_start_time = time.time()
    _rendered_frames_count = 0
    _motion_blur_active_at_render_start = getattr(scene.render, "use_motion_blur", False)
    _idle_seconds = 0    # рендер = активність
    oom_capture_start()  # слухаємо консоль на предмет браку відеопам'яті


@persistent
def on_render_post(scene):
    global _rendered_frames_count
    _rendered_frames_count += 1


@persistent
def on_render_complete(scene):
    """Рендер завершився успішно → видаємо всі виконані рендер-ачивки."""
    global _pending_render_ids
    oom_capture_stop()
    # Глобальні лічильники рендерів/кадрів (просто числа, без відкладання)
    try:
        from .engine import get_engine
        _eng = get_engine()
        _eng.add_stat("renders_total", 1)                        # NASA Computer
        if _rendered_frames_count > 0:
            _eng.add_stat("frames_total", _rendered_frames_count)  # Feature Film
        _eng.flush_stats()
    except Exception as _dbg_err:
        debug.log("achievements.py:1544", _dbg_err)
        pass
    try:
        ids = _scene_render_candidates(scene) | _timing_render_candidates(scene)
    except Exception as _dbg_err:
        debug.log("achievements.py:1548", _dbg_err)
        ids = set()
    if ids:
        from .engine import get_engine
        eng = get_engine()
        for aid in ids:
            eng.unlock(aid)
        _pending_render_ids |= ids
        _schedule_render_reward(RENDER_REWARD_DELAY)
        _reward_pending_render()


@persistent
def on_render_cancel(scene):
    """Рендер скасовано (у т.ч. через помилку — Cycles на set_error теж ставить
    cancel). Рендер-ачивки не видаємо: вони додаються до черги лише в
    on_render_complete. Але саме тут закривається перехоплення консолі, бо
    аварійний рендер до render_complete не доходить."""
    oom_capture_stop()


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

_cap_active = False
_cap_file = None        # відкритий файловий об'єкт-приймач
_cap_path = None
_cap_saved_fd = None    # dup() справжнього stdout
_cap_offset = 0


def _oom_drain():
    """Зливає нові байти з файлу-приймача у справжній stdout і шукає в них
    повідомлення про брак відеопам'яті."""
    global _cap_offset
    if _cap_path is None or _cap_saved_fd is None:
        return
    try:
        with open(_cap_path, "rb") as r:
            r.seek(_cap_offset)
            chunk = r.read()
        if not chunk:
            return
        _cap_offset += len(chunk)
        try:
            os.write(_cap_saved_fd, chunk)      # віддаємо користувачу назад
        except OSError as _dbg_err:
            debug.log("achievements.py:_oom_drain/write", _dbg_err)
        if _VRAM_OOM_RE.search(chunk.decode("utf-8", "replace")):
            trigger_vram_error()
    except Exception as _dbg_err:
        debug.log("achievements.py:_oom_drain", _dbg_err)


def _oom_timer():
    if not _cap_active:
        return None
    _oom_drain()
    return 1.0


def oom_capture_start():
    """Перенаправляє stdout у тимчасовий файл на час рендеру.

    Будь-яка помилка на цьому шляху означає просто відмову від детекції
    (напр. GUI-збірка Windows без консолі, де fd 1 невалідний) — рендер від
    цього не страждає.
    """
    global _cap_active, _cap_file, _cap_path, _cap_saved_fd, _cap_offset
    if _cap_active:
        return
    f = path = saved = None
    try:
        fd, path = tempfile.mkstemp(prefix="bl_achievements_render_", suffix=".log")
        os.close(fd)
        f = open(path, "wb", buffering=0)
        saved = os.dup(1)
        os.dup2(f.fileno(), 1)
    except Exception as _dbg_err:
        debug.log("achievements.py:oom_capture_start", _dbg_err)
        for closer in (lambda: f and f.close(),
                       lambda: saved is not None and os.close(saved),
                       lambda: path and os.path.exists(path) and os.remove(path)):
            try:
                closer()
            except Exception:
                pass
        return

    _cap_file, _cap_path, _cap_saved_fd, _cap_offset = f, path, saved, 0
    _cap_active = True
    try:
        bpy.app.timers.register(_oom_timer, first_interval=1.0)
    except Exception as _dbg_err:
        debug.log("achievements.py:oom_capture_start/timer", _dbg_err)


def oom_capture_stop():
    """Повертає stdout на місце, доливає залишок і прибирає тимчасовий файл."""
    global _cap_active, _cap_file, _cap_path, _cap_saved_fd, _cap_offset
    if not _cap_active:
        return
    _cap_active = False                      # зупиняє таймер на наступному тіку
    try:
        os.dup2(_cap_saved_fd, 1)            # спершу віддаємо справжній stdout
    except Exception as _dbg_err:
        debug.log("achievements.py:oom_capture_stop/restore", _dbg_err)
    try:
        if _cap_file is not None:
            _cap_file.close()
    except Exception as _dbg_err:
        debug.log("achievements.py:oom_capture_stop/close", _dbg_err)

    _oom_drain()                             # останній залишок + перевірка

    try:
        if _cap_saved_fd is not None:
            os.close(_cap_saved_fd)
    except Exception:
        pass
    try:
        if _cap_path and os.path.exists(_cap_path):
            os.remove(_cap_path)
    except Exception:
        pass
    _cap_file = _cap_path = _cap_saved_fd = None
    _cap_offset = 0


@persistent
def on_save_post(dummy):
    global _last_save_time, _session_save_count
    _last_save_time = time.time()
    _session_save_count += 1

    from .engine import get_engine
    eng = get_engine()
    eng.add_stat("saves_total", 1)          # Good Habit (global)
    if not eng.is_unlocked("SAVE_BUTTON_MASHER") and _session_save_count >= 50:
        eng.unlock("SAVE_BUTTON_MASHER")
    eng.flush_stats()


@persistent
def on_load_post(dummy):
    global _known_objects, _launch_time, _last_save_time, _prev_object_count
    _launch_time = time.time()
    _last_save_time = time.time()
    try:
        _known_objects = snapshot_objects()
    except Exception as _dbg_err:
        debug.log("achievements.py:1589", _dbg_err)
        _known_objects = None

    # Новий baseline для відкритого файлу: усе наявне вважаємо «не цієї сесії».
    _capture_baseline()
    # Дельта-лічильники перебазовуємо на вміст відкритого файлу (щоб готовий
    # вміст не рахувався як «створене»).
    _delta_last.clear()
    _ngon_cache.clear()          # імена мешів у новому файлі можуть збігатися
    _progress_cache.clear()
    _prev_object_count = None

    from .engine import get_engine
    eng = get_engine()
    if not eng.is_unlocked("THE_SURVIVOR"):
        try:
            fp = bpy.data.filepath.lower()
            if "autosave" in fp or fp.endswith(".blend1") or fp.endswith(".blend2") or "quit.blend" in fp:
                eng.unlock("THE_SURVIVOR")
                eng.add_stat("recoveries", 1)   # Live to Die Another Day (global)
        except Exception as _dbg_err:
            debug.log("achievements.py:1609", _dbg_err)
            pass


@persistent
def on_frame_change_post(scene):
    global _idle_seconds
    _idle_seconds = 0    # відтворення/зміна кадру = активність

    from .engine import get_engine
    eng = get_engine()

    if all(eng.is_unlocked(aid) for aid in FRAME_CHANGE_ACHIEVEMENT_IDS):
        return

    # GRAVITY_MASTER
    if not eng.is_unlocked("GRAVITY_MASTER"):
        try:
            rbw = getattr(scene, "rigidbody_world", None)
            if rbw:
                coll = getattr(rbw, "collection", None) or getattr(rbw, "group", None)
                if coll and len(coll.objects) > 100:
                    eng.unlock("GRAVITY_MASTER")
        except Exception as _dbg_err:
            debug.log("achievements.py:1632", _dbg_err)
            pass

    # CLOTH_EXPLOSION
    if not eng.is_unlocked("CLOTH_EXPLOSION"):
        try:
            for ob in scene.objects:
                if ob.type == 'MESH':
                    for mod in ob.modifiers:
                        if mod.type == 'CLOTH':
                            if ob.data and len(ob.data.vertices) > 0:
                                from mathutils import Vector
                                bb_max = max(Vector(pt).length for pt in ob.bound_box) if hasattr(ob, "bound_box") and ob.bound_box else 0.0
                                v0_max = Vector(ob.data.vertices[0].co).length
                                if bb_max <= 100.0 and v0_max <= 100.0:
                                    continue
                                max_co = max(v.co.length for v in ob.data.vertices)
                                if max_co > 100.0:
                                    eng.unlock("CLOTH_EXPLOSION")
                                    break
        except Exception as _dbg_err:
            debug.log("achievements.py:1652", _dbg_err)
            pass


# --- Periodic Low-Frequency Timer Callback ---

def _count_keyframes(only_new: bool = False) -> int:
    """Загальна к-сть ключів у всіх екшенах.

    Рахує і legacy `action.fcurves`, і слот-екшени Blender 4.4+
    (`action.layers[*].strips[*].channelbags[*].fcurves`), інакше ключі,
    поставлені автокіфреймом у 5.2, не враховувались би.

    only_new=True → рахуємо лише в екшенах, створених цієї сесії (не з baseline).
    """
    base = _baseline.get('actions') if (only_new and _baseline is not None) else None
    total = 0
    for action in bpy.data.actions:
        if base is not None and action.name in base:
            continue
        fcurves = getattr(action, "fcurves", None)
        if fcurves:
            for fc in fcurves:
                total += len(fc.keyframe_points)
        for layer in getattr(action, "layers", []):
            for strip in getattr(layer, "strips", []):
                for cbag in getattr(strip, "channelbags", []):
                    for fc in getattr(cbag, "fcurves", []):
                        total += len(fc.keyframe_points)
    return total


def achievement_timer_callback():
    from .engine import get_engine
    eng = get_engine()

    _ensure_baseline()

    # ---- Global cumulative counters + new session detectors (run every tick,
    #      незалежно від того, чи всі сесійні timer-ачивки вже отримано) ----
    global _session_started, _flush_tick, _idle_seconds

    if not _session_started:
        _session_started = True
        try:
            eng.add_stat("launches", 1)          # Loyalty
            eng.record_session_day()             # Consistency / Dedicated / Year of the Donut
        except Exception as _dbg_err:
            debug.log("achievements.py:1699", _dbg_err)
            pass

    # What am I doing? — 4 години безперервного безділля (скидається будь-якою активністю)
    if not eng.is_unlocked("WHAT_AM_I_DOING"):
        _idle_seconds += 5
        if _idle_seconds >= 14400:
            eng.unlock("WHAT_AM_I_DOING")

    try:
        if not eng.is_unlocked("UNEMPLOYED_3"):
            eng.add_stat("uptime_seconds", 5)    # Unemployed
    except Exception as _dbg_err:
        debug.log("achievements.py:1711", _dbg_err)
        pass

    try:
        if not eng.is_unlocked("SCULPT_SANCTUARY") and getattr(bpy.context, "mode", "") == 'SCULPT':
            eng.add_stat("sculpt_seconds", 5)    # Sculpt Sanctuary
    except Exception as _dbg_err:
        debug.log("achievements.py:1717", _dbg_err)
        pass

    if _baseline is not None:
        # дешеві дельти (len — O(1)) щотіку; keyframes-скан — рідше (див. нижче)
        try:
            if not eng.is_unlocked("POLYGON_TYCOON"):
                _accum_delta(eng, "polygons_total", _count_total_polys())
            if not eng.is_unlocked("NODE_ARCHITECT"):
                _accum_delta(eng, "node_links_total", _count_total_node_links())
            if not eng.is_unlocked("MATERIAL_WORLD"):
                _accum_delta(eng, "materials_total", len(bpy.data.materials))
            if not eng.is_unlocked("SHAPE_SHIFTER_3"):
                _accum_delta(eng, "shapekeys_total", _count_total_shapekeys())
        except Exception as _dbg_err:
            debug.log("achievements.py:1731", _dbg_err)
            pass

    # Compositor Cook (session)
    if not eng.is_unlocked("COMPOSITOR_COOK") and _baseline is not None:
        try:
            cur = _count_compositor_nodes()
            if cur >= 10 and cur > _baseline.get('compositor_nodes', 0):
                eng.unlock("COMPOSITOR_COOK")
        except Exception as _dbg_err:
            debug.log("achievements.py:1740", _dbg_err)
            pass

    # Ouroboros (session) — самопосилальний драйвер, доданий цієї сесії
    if not eng.is_unlocked("OUROBOROS") and _baseline is not None:
        try:
            if _count_drivers() > _baseline['driver_count'] and _has_self_referencing_driver():
                eng.unlock("OUROBOROS")
        except Exception as _dbg_err:
            debug.log("achievements.py:1748", _dbg_err)
            pass

    # Append-icitis (session)
    if not eng.is_unlocked("APPEND_ICITIS"):
        try:
            if _detect_appended_this_session():
                eng.unlock("APPEND_ICITIS")
        except Exception as _dbg_err:
            debug.log("achievements.py:1756", _dbg_err)
            pass

    # Періодичний флаш stats на диск (~кожні 30с) + рідший важкий keyframes-скан
    _flush_tick = (_flush_tick + 1) % 6
    if _flush_tick == 0:
        if _baseline is not None and not eng.is_unlocked("PUPPETEER"):
            try:
                _accum_delta(eng, "keyframes_total", _count_keyframes())   # Puppeteer
            except Exception as _dbg_err:
                debug.log("achievements.py:1765", _dbg_err)
                pass
        try:
            eng.flush_stats()
        except Exception as _dbg_err:
            debug.log("achievements.py:1769", _dbg_err)
            pass

    if all(eng.is_unlocked(aid) for aid in TIMER_ACHIEVEMENT_IDS):
        return 5.0

    # 1. POLYGON_KING — лише меші, додані цієї сесії
    if not eng.is_unlocked("POLYGON_KING"):
        try:
            total_polys = sum(len(ob.data.polygons) for ob in bpy.data.objects
                              if ob.type == 'MESH' and ob.data and _is_new('objects', ob.name))
            if total_polys > 10000000:
                eng.unlock("POLYGON_KING")
        except Exception as _dbg_err:
            debug.log("achievements.py:1782", _dbg_err)
            pass

    # 2. UV_UNWRAPPING_PAIN
    if not eng.is_unlocked("UV_UNWRAPPING_PAIN"):
        try:
            global _uv_editing_seconds
            is_uv = False
            ws = getattr(bpy.context, "workspace", None)
            if ws and ws.name == "UV Editing":
                is_uv = True
            else:
                screen = getattr(bpy.context, "screen", None)
                if screen:
                    for area in screen.areas:
                        if area.type == 'IMAGE_EDITOR':
                            is_uv = True
                            break
            if is_uv:
                _uv_editing_seconds += 5
                if _uv_editing_seconds >= 1800:
                    eng.unlock("UV_UNWRAPPING_PAIN")
        except Exception as _dbg_err:
            debug.log("achievements.py:1804", _dbg_err)
            pass

    # 3. SAVED_BY_SHIELD — дельта fake-user понад baseline (призначено цієї сесії)
    if not eng.is_unlocked("SAVED_BY_SHIELD") and _baseline is not None:
        try:
            if _count_fake_users() - _baseline['fake_user_count'] >= 10:
                eng.unlock("SAVED_BY_SHIELD")
        except Exception as _dbg_err:
            debug.log("achievements.py:1828", _dbg_err)
            pass


    # 6. DRIVER_SPECIALIST — дельта драйверів понад baseline (створено цієї сесії)
    if not eng.is_unlocked("DRIVER_SPECIALIST") and _baseline is not None:
        try:
            if _count_drivers() - _baseline['driver_count'] >= 5:
                eng.unlock("DRIVER_SPECIALIST")
        except Exception as _dbg_err:
            debug.log("achievements.py:1837", _dbg_err)
            pass

    # 7. LIVING_ON_THE_EDGE
    if not eng.is_unlocked("LIVING_ON_THE_EDGE"):
        try:
            if getattr(bpy.data, "is_dirty", False) and (time.time() - _last_save_time) >= 7200:
                eng.unlock("LIVING_ON_THE_EDGE")
        except Exception as _dbg_err:
            debug.log("achievements.py:1845", _dbg_err)
            pass

    # 8. ADDON_COLLECTOR — увімкнено >=25 і принаймні один цієї сесії (понад baseline)
    if not eng.is_unlocked("ADDON_COLLECTOR") and _baseline is not None:
        try:
            prefs = getattr(bpy.context, "preferences", None)
            if prefs and hasattr(prefs, "addons"):
                current = len(prefs.addons)
                if current >= 25 and current > _baseline['addon_count']:
                    eng.unlock("ADDON_COLLECTOR")
        except Exception as _dbg_err:
            debug.log("achievements.py:1856", _dbg_err)
            pass

    # 9. OUTLINER_CHAOS — лише авто-іменовані об'єкти, створені цієї сесії
    if not eng.is_unlocked("OUTLINER_CHAOS") and _baseline is not None:
        try:
            auto_named_count = sum(1 for ob in bpy.data.objects
                                   if _is_new('objects', ob.name) and re.match(r".*\.\d{3}$", ob.name))
            if auto_named_count >= 47:
                eng.unlock("OUTLINER_CHAOS")
        except Exception as _dbg_err:
            debug.log("achievements.py:1866", _dbg_err)
            pass

    # 10. NIGHT_SHIFT
    if not eng.is_unlocked("NIGHT_SHIFT"):
        try:
            if _render_start_time is not None and (time.time() - _render_start_time) >= 14400:
                eng.unlock("NIGHT_SHIFT")
        except Exception as _dbg_err:
            debug.log("achievements.py:1874", _dbg_err)
            pass

    return 5.0


def _on_msgbus_notify(*args):
    """Msgbus callback triggering depsgraph check."""
    try:
        if hasattr(bpy.context, "scene") and hasattr(bpy.context, "evaluated_depsgraph_get"):
            on_depsgraph_update(bpy.context.scene, bpy.context.evaluated_depsgraph_get())
    except Exception as _dbg_err:
        debug.log("achievements.py:1885", _dbg_err)
        pass


def register_msgbus_subscribers():
    global _msgbus_owners
    try:
        owner = object()
        _msgbus_owners.append(owner)
        bpy.msgbus.subscribe_rna(
            key=(bpy.types.Light, "energy"),
            owner=owner,
            args=(),
            notify=_on_msgbus_notify,
        )
    except Exception as _dbg_err:
        debug.log("achievements.py:1900", _dbg_err)
        pass


# --- Listener Lifecycle Registration & Unregistration ---

def reset_tracking_state():
    """Resets all module-level tracking state variables to clean defaults."""
    global _known_objects, _launch_time, _last_save_time, _session_save_count
    global _uv_editing_seconds
    global _render_start_time, _rendered_frames_count, _motion_blur_active_at_render_start
    global _pending_render_ids, _baseline, _respect_cube_armed
    global _session_started, _prev_object_count, _flush_tick, _idle_seconds
    global _max_join_count, _max_merge_count, _progress_cache, _progress_cache_time
    global _knife_cut_count, _graph_tweaks, _applied_objects_count
    global _last_depsgraph_heavy_scan_time, _last_depsgraph_node_sig
    global _watcher_last_op_count, _watcher_prev_obj_count, _watcher_mesh_stats

    _known_objects = None
    _launch_time = time.time()
    _last_save_time = time.time()
    _session_save_count = 0
    _uv_editing_seconds = 0

    _render_start_time = None
    _rendered_frames_count = 0
    _motion_blur_active_at_render_start = False
    _pending_render_ids = set()
    _baseline = None
    _respect_cube_armed = False
    _session_started = False
    _prev_object_count = None
    _flush_tick = 0
    _idle_seconds = 0
    _max_join_count = 0
    _max_merge_count = 0
    _progress_cache = {}
    _progress_cache_time = 0.0
    _delta_last.clear()
    _ngon_cache.clear()

    _watcher_last_op_count = None
    _watcher_prev_obj_count = None
    _watcher_mesh_stats = {}

    _knife_cut_count = 0
    _graph_tweaks = 0
    _applied_objects_count = 0
    _last_depsgraph_heavy_scan_time = 0.0
    _last_depsgraph_node_sig = None

    _undo_timestamps.clear()
    _shortcut_timestamps.clear()


def register_listeners():
    """Registers event handlers, low-frequency timers, and msgbus subscribers."""
    reset_tracking_state()

    for handler, app_list in (
        (on_depsgraph_update, bpy.app.handlers.depsgraph_update_post),
        (on_load_post, bpy.app.handlers.load_post),
        (on_save_post, bpy.app.handlers.save_post),
        (on_render_pre, bpy.app.handlers.render_pre),
        (on_render_init, bpy.app.handlers.render_init),
        (on_render_post, bpy.app.handlers.render_post),
        (on_render_complete, bpy.app.handlers.render_complete),
        (on_render_cancel, bpy.app.handlers.render_cancel),
        (on_frame_change_post, bpy.app.handlers.frame_change_post),
    ):
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
    try:
        from .engine import get_engine
        get_engine().flush_stats()
    except Exception as _dbg_err:
        debug.log("achievements.py:1998", _dbg_err)
        pass

    reset_tracking_state()

    for handler, app_list in (
        (on_depsgraph_update, bpy.app.handlers.depsgraph_update_post),
        (on_load_post, bpy.app.handlers.load_post),
        (on_save_post, bpy.app.handlers.save_post),
        (on_render_pre, bpy.app.handlers.render_pre),
        (on_render_init, bpy.app.handlers.render_init),
        (on_render_post, bpy.app.handlers.render_post),
        (on_render_complete, bpy.app.handlers.render_complete),
        (on_render_cancel, bpy.app.handlers.render_cancel),
        (on_frame_change_post, bpy.app.handlers.frame_change_post),
    ):
        if handler in app_list:
            app_list.remove(handler)

    if hasattr(bpy.app.timers, "is_registered"):
        if bpy.app.timers.is_registered(achievement_timer_callback):
            bpy.app.timers.unregister(achievement_timer_callback)
        if bpy.app.timers.is_registered(_reward_pending_render):
            bpy.app.timers.unregister(_reward_pending_render)
    else:
        try:
            bpy.app.timers.unregister(achievement_timer_callback)
        except (ValueError, RuntimeError):
            pass
        try:
            bpy.app.timers.unregister(_reward_pending_render)
        except (ValueError, RuntimeError):
            pass

    for owner in _msgbus_owners:
        try:
            bpy.msgbus.clear_by_owner(owner)
        except Exception as _dbg_err:
            debug.log("achievements.py:2035", _dbg_err)
            pass
    _msgbus_owners.clear()


PROGRESSIVE_TARGETS = {
    "SAVED_BY_SHIELD": 10,
    "ADDON_COLLECTOR": 25,
    "POLYGON_KING": 10000000,
    "FATAL_CTRL_J": 100,
    "KNIFE_MASTER": 50,
    "MERGE_MASTER": 100,
    "NODE_SPAGHETTI": 50,
    "GEOMETRY_NODES_GURU": 5,
    "MATERIAL_HOARDER": 30,
    "COLOR_RAMP_ADDICT": 5,
    "GRAPH_EDITOR_TWEAKER": 100,
    "BONE_COLLECTOR": 50,
    "DRIVER_SPECIALIST": 5,
    "GRAVITY_MASTER": 100,
    "PARTICLE_STORM": 100000,
    "CYCLES_ENTHUSIAST": 10000,
    "EEVEE_SPEEDSTER": 100,
    "CTRL_Z_HERO": 50,
    "SHORTCUT_NINJA": 30,
    "APPLY_ALL": 20,
    "OUTLINER_CHAOS": 47,
    "SAVE_BUTTON_MASHER": 50,
}


_progress_cache = {}          # ach_id -> current value
_progress_cache_time = 0.0    # monotonic-час останнього перерахунку
PROGRESS_CACHE_TTL = 1.0      # с; UI перемальовується десятки разів на секунду


def _compute_all_progress() -> dict:
    """Один прохід по сцені → значення прогресу для всіх ачивок.

    Важливо: значення рахуються за тими самими правилами, що й розблокування
    (baseline-обмежені там, де unlock baseline-обмежений), інакше прогрес
    показував би те, що ніколи не приведе до ачивки.
    """
    from .engine import get_engine
    eng = get_engine()
    p = {}

    # --- глобальні (накопичувальні) ачивки: просто читання лічильників ---
    for aid, d in ACHIEVEMENTS.items():
        ckey = getattr(d, "counter", None)
        if ckey:
            p[aid] = int(eng.get_stat(ckey, 0))

    # --- прості лічильники сесії (без сканування) ---
    p["KNIFE_MASTER"] = _knife_cut_count
    p["GRAPH_EDITOR_TWEAKER"] = _graph_tweaks
    p["APPLY_ALL"] = _applied_objects_count
    p["SAVE_BUTTON_MASHER"] = _session_save_count
    p["EEVEE_SPEEDSTER"] = _rendered_frames_count
    p["FATAL_CTRL_J"] = _max_join_count
    p["MERGE_MASTER"] = _max_merge_count
    now_t = time.time()
    p["CTRL_Z_HERO"] = sum(1 for t in _undo_timestamps if now_t - t <= 60.0)
    p["SHORTCUT_NINJA"] = len({sid for t, sid in _shortcut_timestamps if now_t - t <= 60.0})

    if _baseline is None:
        return p

    # --- дельти понад baseline (як в unlock-логіці) ---
    try:
        p["DRIVER_SPECIALIST"] = max(0, _count_drivers() - _baseline['driver_count'])
        p["SAVED_BY_SHIELD"] = max(0, _count_fake_users() - _baseline['fake_user_count'])
    except Exception as _dbg_err:
        debug.log("achievements.py:2107", _dbg_err)
        pass
    try:
        prefs = getattr(bpy.context, "preferences", None)
        p["ADDON_COLLECTOR"] = len(prefs.addons) if prefs and hasattr(prefs, "addons") else 0
    except Exception as _dbg_err:
        debug.log("achievements.py:2112", _dbg_err)
        pass


    # --- один прохід по об'єктах: полігони / скелети / авто-імена ---
    polys = bones = autonamed = 0
    try:
        for ob in bpy.data.objects:
            if not _is_new('objects', ob.name):
                continue
            t = getattr(ob, "type", None)
            if t == 'MESH' and ob.data:
                polys += len(ob.data.polygons)
                if re.match(r".*\.\d{3}$", ob.name):
                    autonamed += 1
            elif t == 'ARMATURE' and ob.data:
                bones = max(bones, len(ob.data.bones))
            elif re.match(r".*\.\d{3}$", ob.name):
                autonamed += 1
    except Exception as _dbg_err:
        debug.log("achievements.py:2131", _dbg_err)
        pass
    p["POLYGON_KING"] = polys
    p["BONE_COLLECTOR"] = bones
    p["OUTLINER_CHAOS"] = autonamed

    # --- один прохід по матеріалах: к-сть / ноди / color ramps ---
    new_mats = max_nodes = max_cr = 0
    try:
        for mat in bpy.data.materials:
            if not _is_new('materials', mat.name):
                continue
            new_mats += 1
            nt = getattr(mat, "node_tree", None)
            if nt:
                max_nodes = max(max_nodes, len(nt.nodes))
                max_cr = max(max_cr, sum(1 for n in nt.nodes if getattr(n, "type", "") == 'VALTORGB'))
    except Exception as _dbg_err:
        debug.log("achievements.py:2148", _dbg_err)
        pass
    p["MATERIAL_HOARDER"] = new_mats
    p["COLOR_RAMP_ADDICT"] = max_cr

    # --- один прохід по нод-групах: spaghetti / вкладені групи ---
    max_nested = 0
    try:
        for ng in bpy.data.node_groups:
            if not _is_new('node_groups', ng.name):
                continue
            max_nodes = max(max_nodes, len(ng.nodes))
            max_nested = max(max_nested, sum(1 for n in ng.nodes if getattr(n, "type", "") == 'GROUP'))
    except Exception as _dbg_err:
        debug.log("achievements.py:2161", _dbg_err)
        pass
    p["NODE_SPAGHETTI"] = max_nodes
    p["GEOMETRY_NODES_GURU"] = max_nested

    # --- частинки / rigid body / семпли ---
    try:
        p["PARTICLE_STORM"] = max((getattr(ps, "count", 0) for ps in bpy.data.particles
                                   if _is_new('particles', ps.name)), default=0)
    except Exception as _dbg_err:
        debug.log("achievements.py:2170", _dbg_err)
        pass
    try:
        scene = getattr(bpy.context, "scene", None)
        cycles = getattr(scene, "cycles", None) if scene else None
        p["CYCLES_ENTHUSIAST"] = getattr(cycles, "samples", 0) if cycles else 0
        rbw = getattr(scene, "rigidbody_world", None) if scene else None
        coll = (getattr(rbw, "collection", None) or getattr(rbw, "group", None)) if rbw else None
        p["GRAVITY_MASTER"] = len(coll.objects) if coll else 0
    except Exception as _dbg_err:
        debug.log("achievements.py:2179", _dbg_err)
        pass

    return p


def get_achievement_progress(ach_id: str) -> Optional[Tuple[int, int]]:
    """(поточне, ціль) для ачивки або None. Кешується на PROGRESS_CACHE_TTL,
    бо викликається для кожної ачивки на кожній перемальовці панелі."""
    global _progress_cache, _progress_cache_time

    target = PROGRESSIVE_TARGETS.get(ach_id)
    if not target:
        d = ACHIEVEMENTS.get(ach_id)
        target = getattr(d, "threshold", 0) if d else 0
        if not target:
            return None

    now = time.monotonic()
    if not _progress_cache or (now - _progress_cache_time) >= PROGRESS_CACHE_TTL:
        try:
            _progress_cache = _compute_all_progress()
        except Exception as _dbg_err:
            debug.log("achievements.py:2201", _dbg_err)
            _progress_cache = {}
        _progress_cache_time = now

    curr = _progress_cache.get(ach_id, 0)
    return (min(curr, target), target)


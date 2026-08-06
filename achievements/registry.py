"""
Achievement registry: the definition record and the table of every achievement.

This module is deliberately pure data — it imports nothing from Blender and
nothing from the detector code, so `engine.py`, the UI and the Dev Tools addon
can read titles, categories and thresholds without dragging in scene-scanning
logic.

The *rules* (what unlocks an achievement, and what number the panel shows as
progress) live in `achievements.rules` and are attached onto the definitions
at import time via `bind()`. Keeping the two apart means a definition can be
listed, counted and rendered before any rule module has been imported, while
the rule engine still only ever walks one table.
"""

from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Tuple, Union


# --- Triggers -------------------------------------------------------------
# Which event drives a rule's evaluation. A rule is only ever checked when its
# trigger fires, which is what replaced the hand-maintained
# DEPSGRAPH_ACHIEVEMENT_IDS / FRAME_CHANGE_ACHIEVEMENT_IDS / TIMER_ACHIEVEMENT_IDS
# sets: the sets and the checks they guarded could (and did) drift apart.

DEPSGRAPH = "depsgraph"            # bpy.app.handlers.depsgraph_update_post
TIMER = "timer"                    # the addon's 5-second low-frequency timer
FRAME_CHANGE = "frame_change"      # frame_change_post (playback / render walk)
RENDER_COMPLETE = "render_complete"
SAVE = "save"
LOAD = "load"
COUNTER = "counter"                # cumulative stat crossing its threshold
MANUAL = "manual"                  # unlocked imperatively (see rules/operations.py)

TRIGGERS = (DEPSGRAPH, TIMER, FRAME_CHANGE, RENDER_COMPLETE, SAVE, LOAD,
            COUNTER, MANUAL)


@dataclass
class AchievementDefinition:
    """One achievement: what it is, and — once `bind()` has run — how it is won.

    Metadata half (`id` … `threshold`) is static and safe to read anywhere.

    Rule half:
      trigger   — the events that check this rule, as a tuple of the constants
                  above; empty until a rule is bound. Almost every rule has
                  exactly one, and `bind(trigger=DEPSGRAPH)` normalises a bare
                  string into a one-element tuple.
      check     — `(ctx) -> bool`; True means "unlock now".
      progress  — `(ctx) -> int`; the current value for the progress bar.
      target    — the value `progress` must reach. When `check` is absent, the
                  rule *is* `progress(ctx) >= target`, which is the shape most
                  achievements have and the reason the old PROGRESSIVE_TARGETS
                  table is gone.
      interval  — minimum seconds between two evaluations of this rule; for
                  checks whose scan is too heavy to run on every event.
      scan      — this rule's `progress` walks bpy.data broadly, so the panel
                  should recompute it only when the scene actually changed
                  (see rules.progress).
    """
    id: str
    title: str
    description: str
    rare: bool = False
    category: str = "Basics"
    icon: Optional[str] = None
    # Global (persistent, cross-session) achievements bind to a cumulative counter.
    counter: Optional[str] = None   # ключ у engine stats; None → звичайна (сесійна)
    threshold: int = 0              # поріг лічильника для розблокування

    # --- declarative rule, filled in by achievements.rules ---
    trigger: Tuple[str, ...] = ()
    check: Optional[Callable] = None
    progress: Optional[Callable] = None
    target: int = 0
    interval: float = 0.0
    scan: bool = False

    @property
    def goal(self) -> int:
        """The number progress counts up to: the rule's target, or — for global
        cumulative achievements, whose target *is* their counter threshold —
        the threshold."""
        return self.target or self.threshold

    def evaluate(self, ctx) -> bool:
        """True if this achievement is earned right now.

        `check` wins when present; otherwise the numeric rule applies. A rule
        with neither (a purely imperative one, e.g. Frankenstein) never
        unlocks itself — something calls `engine.unlock()` for it directly.
        """
        if self.check is not None:
            return bool(self.check(ctx))
        if self.progress is not None and self.goal:
            return self.progress(ctx) >= self.goal
        return False

    def current(self, ctx) -> Optional[int]:
        """Current progress value, or None if this achievement doesn't track one."""
        if self.progress is None:
            return None
        return self.progress(ctx)


# Registry of all available achievements across 8 categories
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
        description="Make 20 cuts with the Knife tool in one session.",
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
        description="Build a material from 10+ nodes without a single image texture.",
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
        description="Build an armature rig containing 100 or more bones.",
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
        description="Finish a render with the sample count set above 10,000.",
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
        description="Undo actions 30+ times in a row within one minute.",
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
        description="Use 15 different keyboard shortcuts within one minute.",
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
        icon="Shape Shifter_I.png"),
    "SHAPE_SHIFTER_2": AchievementDefinition(
        id="SHAPE_SHIFTER_2", title="Shape Shifter II",
        description="Create 25 shape keys in total.",
        category="Milestones", counter="shapekeys_total", threshold=25,
        icon="Shape Shifter_II.png"),
    "SHAPE_SHIFTER_3": AchievementDefinition(
        id="SHAPE_SHIFTER_3", title="Shape Shifter III",
        description="Create 50 shape keys in total.",
        rare=True, category="Milestones", counter="shapekeys_total", threshold=50,
        icon="Shape Shifter_III.png"),

    # Good Habit — total manual saves
    "GOOD_HABIT_1": AchievementDefinition(
        id="GOOD_HABIT_1", title="Good Habit I",
        description="Save your project 100 times in total.",
        category="Milestones", counter="saves_total", threshold=100,
        icon="Good Habit_I.png"),
    "GOOD_HABIT_2": AchievementDefinition(
        id="GOOD_HABIT_2", title="Good Habit II",
        description="Save your project 1,000 times in total.",
        category="Milestones", counter="saves_total", threshold=1000,
        icon="Good Habit_II.png"),
    "GOOD_HABIT_3": AchievementDefinition(
        id="GOOD_HABIT_3", title="Good Habit III",
        description="Save your project 10,000 times in total.",
        rare=True, category="Milestones", counter="saves_total", threshold=10000,
        icon="Good Habit_III.png"),

    # NASA Computer — total completed renders
    "NASA_COMPUTER_1": AchievementDefinition(
        id="NASA_COMPUTER_1", title="NASA Computer I",
        description="Complete 100 renders in total.",
        category="Milestones", counter="renders_total", threshold=100,
        icon="NASA Computer_I.png"),
    "NASA_COMPUTER_2": AchievementDefinition(
        id="NASA_COMPUTER_2", title="NASA Computer II",
        description="Complete 1,000 renders in total.",
        category="Milestones", counter="renders_total", threshold=1000,
        icon="NASA Computer_II.png"),
    "NASA_COMPUTER_3": AchievementDefinition(
        id="NASA_COMPUTER_3", title="NASA Computer III",
        description="Complete 10,000 renders in total.",
        rare=True, category="Milestones", counter="renders_total", threshold=10000,
        icon="NASA Computer_III.png"),

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
        icon="Cube Genocide_I.png"),
    "CUBE_GENOCIDE_2": AchievementDefinition(
        id="CUBE_GENOCIDE_2", title="Cube Genocide II",
        description="Delete the default cube 100 times in total.",
        category="Milestones", counter="cubes_deleted", threshold=100,
        icon="Cube Genocide_II.png"),
    "CUBE_GENOCIDE_3": AchievementDefinition(
        id="CUBE_GENOCIDE_3", title="Cube Genocide III",
        description="Delete the default cube 1,000 times in total.",
        rare=True, category="Milestones", counter="cubes_deleted", threshold=1000,
        icon="Cube Genocide_III.png"),

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
        icon="Unemployed_I.png"),
    "UNEMPLOYED_2": AchievementDefinition(
        id="UNEMPLOYED_2", title="Unemployed II",
        description="Spend 100 hours in Blender in total.",
        category="Milestones", counter="uptime_seconds", threshold=360000,
        icon="Unemployed_II.png"),
    "UNEMPLOYED_3": AchievementDefinition(
        id="UNEMPLOYED_3", title="Unemployed III",
        description="Spend 1,000 hours in Blender in total.",
        rare=True, category="Milestones", counter="uptime_seconds", threshold=3600000,
        icon="Unemployed_III.png"),

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
        icon="Loyalty_I.png"),
    "LOYALTY_2": AchievementDefinition(
        id="LOYALTY_2", title="Loyalty II",
        description="Launch Blender 500 times.",
        category="Milestones", counter="launches", threshold=500,
        icon="Loyalty_II.png"),
    "LOYALTY_3": AchievementDefinition(
        id="LOYALTY_3", title="Loyalty III",
        description="Launch Blender 1,000 times.",
        rare=True, category="Milestones", counter="launches", threshold=1000,
        icon="Loyalty_III.png"),

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


# --- Rule binding ---------------------------------------------------------

# trigger -> definitions, built as rules bind themselves. Handlers walk these
# lists instead of a hand-written set of ids.
_BY_TRIGGER: Dict[str, List[AchievementDefinition]] = {t: [] for t in TRIGGERS}


def bind(ach_id: str, trigger: Union[str, Iterable[str], None] = None, *,
         check: Optional[Callable] = None, progress: Optional[Callable] = None,
         target: int = 0, interval: float = 0.0,
         scan: bool = False) -> AchievementDefinition:
    """Attaches a rule to a definition and files it under its trigger(s).

    Raises on an unknown id or trigger: a typo here would otherwise produce an
    achievement that is simply never checked — the exact failure mode this
    refactor set out to make impossible.
    """
    d = ACHIEVEMENTS.get(ach_id)
    if d is None:
        raise KeyError(f"bind(): no achievement with id {ach_id!r}")

    triggers = (trigger,) if isinstance(trigger, str) else tuple(trigger or ())
    for t in triggers:
        if t not in _BY_TRIGGER:
            raise ValueError(f"bind({ach_id!r}): unknown trigger {t!r}")

    if check is not None:
        d.check = check
    if progress is not None:
        d.progress = progress
    if target:
        d.target = target
    if interval:
        d.interval = interval
    if scan:
        d.scan = True

    for t in triggers:
        if t not in d.trigger:
            d.trigger += (t,)
        if d not in _BY_TRIGGER[t]:
            _BY_TRIGGER[t].append(d)
    return d


def rules_for(trigger: str) -> List[AchievementDefinition]:
    """Definitions whose rule runs on `trigger`, in registration order."""
    return _BY_TRIGGER.get(trigger, [])


def unbound_ids() -> List[str]:
    """Ids with no trigger at all — useful to Dev Tools / tests as a guard
    against an achievement silently dropping out of every event path."""
    return [aid for aid, d in ACHIEVEMENTS.items() if not d.trigger]

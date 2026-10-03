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


# --- Icons ----------------------------------------------------------------
# `icon` names the artwork file's stem; the extension and the file naming
# convention live in one place (engine._resolve_icon_path). Left as None, the
# stem is the achievement's title, which is how most of them are named.
#
# NO_ICON is different from None: it means "this achievement is deliberately
# drawn without artwork", and the pop-up shows the bare tinted background —
# see "Out of Memory", whose joke is an icon that looks like it failed to load.
NO_ICON = ""


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

    # Display metadata lives with the condition, not in a second UI lookup.
    progress_unit: str = "COUNT"
    hint: str = ""

    @property
    def tracking_hint(self) -> str:
        if self.hint:
            return self.hint
        if self.counter == "streak":
            return "Consecutive calendar days across Blender sessions. Missing a day resets the streak; earned achievements stay unlocked."
        if self.counter == "distinct_days":
            return "Different calendar days across Blender sessions. Days do not need to be consecutive."
        if self.counter == "uptime_seconds":
            return "Total time with Blender open across sessions, including idle time. Progress is saved automatically."
        if self.counter == "sculpt_seconds":
            return "Total time in Sculpt Mode across Blender sessions. Leaving Sculpt Mode pauses this count."
        if self.counter:
            return "Cumulative total across all Blender sessions. Progress is saved automatically."
        return "Complete the condition in the current file. Earned achievements stay unlocked across Blender sessions."

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
        hint="Delete the default cube within 30 seconds of starting Blender. Opening another file starts the window again.",
        title="Goodbye, Cube!",
        description="Delete the default cube within 30 seconds of launching Blender.",
        rare=False,
        category="Basics",
    ),
    "RESPECT_THE_CUBE": AchievementDefinition(
        id="RESPECT_THE_CUBE",
        hint="Use the original Cube in a new or startup file. Do not delete, move, rotate, or scale it before the render finishes.",
        title="Respect the Cube",
        description="Render a scene without deleting or modifying the default cube.",
        rare=True,
        category="Basics",
    ),
    "DONUT_MASTER": AchievementDefinition(
        id="DONUT_MASTER",
        hint="Give a torus a material whose name includes ‘donut’ or ‘glaze’, then finish a render.",
        title="Donut Master",
        description="Render a torus with a glaze material.",
        rare=False,
        category="Basics",
    ),
    "SUZANNES_BLESSING": AchievementDefinition(
        id="SUZANNES_BLESSING",
        hint="Add the built-in Monkey mesh (Suzanne) to the scene.",
        title="Suzanne's Blessing",
        description="Add a monkey mesh (Suzanne) to the scene.",
        rare=False,
        category="Basics",
    ),

    # --- Category 2: Modeling & Sculpting ---
    "POLYGON_KING": AchievementDefinition(
        id="POLYGON_KING",
        hint="Reach more than 10,000,000 polygons across the current scene. The progress bar shows the scene total.",
        title="Polygon King",
        description="Reach over 10,000,000 polygons in a single scene.",
        rare=True,
        category="Modeling & Sculpting",
    ),
    "FATAL_CTRL_J": AchievementDefinition(
        id="FATAL_CTRL_J",
        hint="Join 100 or more objects in one operation. The bar shows your largest join during this Blender session.",
        title="Frankenstein",
        description="Join over 100 separate objects into a single mesh.",
        rare=True,
        category="Modeling & Sculpting",
    ),
    "UV_UNWRAPPING_PAIN": AchievementDefinition(
        id="UV_UNWRAPPING_PAIN",
        hint="Stay in the UV Editing workspace or an active UV Editor for 30 minutes continuously. Leaving both resets the timer.",
        title="Flat Earth",
        description="Work in the UV Editing tab for over 30 minutes straight.",
        rare=False,
        category="Modeling & Sculpting",
    ),
    "SUBDIV_OVERKILL": AchievementDefinition(
        id="SUBDIV_OVERKILL",
        hint="Add a mesh after opening the file or enabling the add-on, then set Subdivision Surface viewport or render level to 6 or higher.",
        title="Subdiv Overkill",
        description="Set Subdivision Surface viewport/render level to 6 or higher.",
        rare=False,
        category="Modeling & Sculpting",
    ),
    "INVERTED_REALITY": AchievementDefinition(
        id="INVERTED_REALITY",
        hint="Use Recalculate Outside/Inside or Flip in Edit Mode on a mesh.",
        title="Up is Down",
        description="Recalculate or flip inverted normals on a mesh.",
        rare=False,
        category="Modeling & Sculpting",
    ),
    "KNIFE_MASTER": AchievementDefinition(
        id="KNIFE_MASTER",
        hint="Make 20 Knife cuts during this Blender session, including across file changes. Restarting Blender or re-enabling the add-on resets the count.",
        title="Surgical Precision",
        description="Make 20 cuts with the Knife tool in one session.",
        rare=False,
        category="Modeling & Sculpting",
    ),
    "MERGE_MASTER": AchievementDefinition(
        id="MERGE_MASTER",
        hint="Merge 100 or more vertices in one Merge by Distance operation. The bar shows your largest merge during this Blender session.",
        title="Singularity",
        description="Merge over 100 overlapping vertices using Merge by Distance.",
        rare=False,
        category="Modeling & Sculpting",
    ),

    # --- Category 3: Nodes & Materials ---
    "NODE_SPAGHETTI": AchievementDefinition(
        id="NODE_SPAGHETTI",
        hint="In a material or node group created after opening the file, connect at least 50 nodes with 49 or more links. The bar counts nodes.",
        title="Node Spaghetti",
        description="Connect 50 or more nodes in Shader or Geometry Nodes.",
        rare=True,
        category="Nodes & Materials",
    ),
    "PURE_PROCEDURAL": AchievementDefinition(
        id="PURE_PROCEDURAL",
        hint="Build one material with at least 10 nodes and 8 links, without Image Texture or Environment Texture nodes. Rendering is not required.",
        title="Pure Procedural",
        description="Build a material from 10+ nodes without a single image texture.",
        rare=False,
        category="Nodes & Materials",
    ),
    "GEOMETRY_NODES_GURU": AchievementDefinition(
        id="GEOMETRY_NODES_GURU",
        hint="Put at least 5 Node Group nodes in one Geometry Nodes tree.",
        title="Geometry Nodes Guru",
        description="Create a Geometry Nodes tree containing 5 or more Node Group nodes.",
        rare=True,
        category="Nodes & Materials",
    ),
    "MATERIAL_HOARDER": AchievementDefinition(
        id="MATERIAL_HOARDER",
        hint="Keep at least 30 materials in the current project file.",
        title="Material Hoarder",
        description="Accumulate 30 or more materials in a single project file.",
        rare=False,
        category="Nodes & Materials",
    ),
    "SAVED_BY_SHIELD": AchievementDefinition(
        id="SAVED_BY_SHIELD",
        hint="Enable the Fake User shield on 10 previously unprotected items. Shields that were already on when the file opened do not count.",
        title="Devine Shield",
        description="Protect 10 unused data items with Fake User (the shield icon).",
        rare=False,
        category="Nodes & Materials",
    ),
    "EMISSION_OVERDRIVE": AchievementDefinition(
        id="EMISSION_OVERDRIVE",
        hint="Create the material after opening the file or enabling the add-on, then set an Emission strength above 10,000.",
        title="Flashbang",
        description="Set an Emission node strength above 10,000.",
        rare=False,
        category="Nodes & Materials",
    ),
    "COLOR_RAMP_ADDICT": AchievementDefinition(
        id="COLOR_RAMP_ADDICT",
        hint="Use at least 5 Color Ramp nodes in one material shader tree.",
        title="Color Ramp Addict",
        description="Use 5 or more Color Ramp nodes in a single shader tree.",
        rare=False,
        category="Nodes & Materials",
    ),

    # --- Category 4: Animation & Physics ---
    "GRAPH_EDITOR_TWEAKER": AchievementDefinition(
        id="GRAPH_EDITOR_TWEAKER",
        hint="Change interpolation handles for 100 or more keyframes during this Blender session. Restarting Blender or re-enabling the add-on resets the count.",
        title="Graph Editor Tweaker",
        description="Adjust over 100 keyframe interpolation handles in the Graph Editor.",
        rare=False,
        category="Animation & Physics",
    ),
    "BONE_COLLECTOR": AchievementDefinition(
        id="BONE_COLLECTOR",
        hint="Create one armature with 100 or more bones after opening the file. Bones in other rigs do not combine with it.",
        title="Exoskeleton",
        description="Build an armature rig containing 100 or more bones.",
        rare=False,
        category="Animation & Physics",
    ),
    "DRIVER_SPECIALIST": AchievementDefinition(
        id="DRIVER_SPECIALIST",
        hint="Add 5 drivers after opening the file. Drivers that were already present do not count.",
        title="Driver Specialist",
        description="Create 5 drivers that link object properties with Python expressions.",
        rare=False,
        category="Animation & Physics",
    ),
    "GRAVITY_MASTER": AchievementDefinition(
        id="GRAVITY_MASTER",
        hint="Run a Rigid Body simulation with more than 100 objects in its collection.",
        title="Domino Effect",
        description="Run a Rigid Body simulation with over 100 objects.",
        rare=True,
        category="Animation & Physics",
    ),
    "THE_BIG_BAKE": AchievementDefinition(
        id="THE_BIG_BAKE",
        hint="Bake a fluid, smoke, cloth, soft body, or rigid body simulation for more than 250 frames.",
        title="Let it cook",
        description="Bake a fluid or smoke simulation longer than 250 frames.",
        rare=False,
        category="Animation & Physics",
    ),
    "PARTICLE_STORM": AchievementDefinition(
        id="PARTICLE_STORM",
        hint="Create particle settings after opening the file or enabling the add-on, then set one emitter to more than 100,000 particles.",
        title="Particle Storm",
        description="Emit over 100,000 particles from a single emitter setup.",
        rare=False,
        category="Animation & Physics",
    ),
    "CLOTH_EXPLOSION": AchievementDefinition(
        id="CLOTH_EXPLOSION",
        hint="During a Cloth simulation, let one vertex move at least 100 Blender units from its starting position.",
        title="Rip and Tear",
        description="Run a Cloth simulation where mesh vertices travel over 100 units away instantly.",
        rare=True,
        category="Animation & Physics",
    ),

    # --- Category 5: Lighting & Rendering ---
    "NIGHT_SHIFT": AchievementDefinition(
        id="NIGHT_SHIFT",
        hint="One uninterrupted render must last more than 4 hours. Separate renders are not added together.",
        title="Night Shift",
        description="Keep a render process running for over 4 consecutive hours.",
        rare=True,
        category="Lighting & Rendering",
    ),
    "CYCLES_ENTHUSIAST": AchievementDefinition(
        id="CYCLES_ENTHUSIAST",
        hint="Finish a render in Cycles with more than 10,000 samples. Changing the sample setting alone does not unlock it.",
        title="Cinema Quality",
        description="Finish a render with the sample count set above 10,000.",
        rare=False,
        category="Lighting & Rendering",
    ),
    "EEVEE_SPEEDSTER": AchievementDefinition(
        id="EEVEE_SPEEDSTER",
        hint="Finish at least 100 frames in one animation render before that render reaches one minute.",
        title="Warp Speed",
        description="Render 100+ animation frames in under 1 minute.",
        rare=False,
        category="Lighting & Rendering",
    ),
    "VRAM_VICTIM": AchievementDefinition(
        id="VRAM_VICTIM",
        hint="Finish a render that fails because the GPU runs out of memory.",
        title="Out of Memory",
        description="Trigger a render error due to running out of GPU memory.",
        rare=True,
        category="Lighting & Rendering",
        # Навмисно без картинки: ачивка про брак пам'яті показує порожню
        # плитку, ніби іконка не завантажилась. У цьому й жарт.
        icon=NO_ICON,
    ),
    "SPEED_BLUR": AchievementDefinition(
        id="SPEED_BLUR",
        hint="Render at least 2 animation frames with Motion Blur enabled.",
        title="Motion Blur",
        description="Render an animation sequence with Motion Blur enabled.",
        rare=False,
        category="Lighting & Rendering",
    ),
    "SUN_GOD": AchievementDefinition(
        id="SUN_GOD",
        hint="Add a Sun light during this session and set its strength above 1,000.",
        title="Now I become death",
        description="Set Sun Light strength to over 1,000.",
        rare=False,
        category="Lighting & Rendering",
    ),
    "DENOISE_MAGIC": AchievementDefinition(
        id="DENOISE_MAGIC",
        hint="Finish an image render with fewer than 32 Cycles samples and denoising enabled.",
        title="Denoise Magic",
        description="Render an image with fewer than 32 samples and denoising enabled.",
        rare=False,
        category="Lighting & Rendering",
    ),
    "ALPHA_TRANSLUCENCY": AchievementDefinition(
        id="ALPHA_TRANSLUCENCY",
        hint="Finish a render with Render Properties > Film > Transparent enabled.",
        title="Ghost in the Shell",
        description="Render a scene with transparent background enabled.",
        rare=False,
        category="Lighting & Rendering",
    ),

    # --- Category 6: Workflow & Disasters ---
    "CTRL_Z_HERO": AchievementDefinition(
        id="CTRL_Z_HERO",
        hint="Make 30 Undo actions within a rolling 60 seconds. Older actions drop out of the bar.",
        title="Time Traveler",
        description="Undo 30 or more times within one minute.",
        rare=False,
        category="Workflow & Disasters",
    ),
    "THE_SURVIVOR": AchievementDefinition(
        id="THE_SURVIVOR",
        hint="Open a project through Recover Last Session or Recover Auto Save after a crash.",
        title="Back from the dead",
        description="Restore a project with Recover Last Session or Recover Auto Save after a crash.",
        rare=True,
        category="Workflow & Disasters",
    ),
    "LIVING_ON_THE_EDGE": AchievementDefinition(
        id="LIVING_ON_THE_EDGE",
        hint="Keep unsaved changes for 2 hours. Saving or opening a file restarts the waiting period.",
        title="Living on the Edge",
        description="Keep unsaved changes for more than 2 hours.",
        rare=False,
        category="Workflow & Disasters",
    ),
    "ADDON_COLLECTOR": AchievementDefinition(
        id="ADDON_COLLECTOR",
        hint="Enable at least 25 add-ons, including one enabled after opening the file or enabling Achievements.",
        title="Add-on Collector",
        description="Enable 25 or more add-ons in the preferences.",
        rare=False,
        category="Workflow & Disasters",
    ),
    "SHORTCUT_NINJA": AchievementDefinition(
        id="SHORTCUT_NINJA",
        hint="Use 15 different keyboard shortcuts within a rolling 60 seconds. Repeating one does not add to the count.",
        title="Shortcut Ninja",
        description="Use 15 different keyboard shortcuts within one minute.",
        rare=True,
        category="Workflow & Disasters",
    ),
    "APPLY_ALL": AchievementDefinition(
        id="APPLY_ALL",
        hint="Apply a transform to 20 or more objects during this Blender session. Restarting Blender or re-enabling the add-on resets the count.",
        title="Know your Place",
        description="Apply scale, rotation, and location (Ctrl+A) on 20+ objects in a scene.",
        rare=False,
        category="Workflow & Disasters",
    ),
    "OUTLINER_CHAOS": AchievementDefinition(
        id="OUTLINER_CHAOS",
        hint="Create and keep at least 47 auto-named objects (for example, Cube.001). Objects already in the file do not count.",
        title="Outliner Chaos",
        description="Create 47 or more auto-named objects (Cube.001, Cube.002) without renaming them.",
        rare=False,
        category="Workflow & Disasters",
    ),
    "SAVE_BUTTON_MASHER": AchievementDefinition(
        id="SAVE_BUTTON_MASHER",
        hint="Save manually 50 times during this Blender session, including across file changes. Restarting Blender or re-enabling the add-on resets the count.",
        title="Paranoia",
        description="Save your project manually over 50 times in a single session.",
        rare=False,
        category="Workflow & Disasters",
    ),

    # ============================ NEW SESSION ACHIEVEMENTS ============================
    "N_GON_CRIMINAL": AchievementDefinition(
        id="N_GON_CRIMINAL",
        hint="Create or edit a mesh during this session so one face has 10 or more sides.",
        title="N-gon Criminal",
        description="Create a single face with 10 or more sides.",
        rare=False,
        category="Modeling & Sculpting",
    ),
    "COMPOSITOR_COOK": AchievementDefinition(
        id="COMPOSITOR_COOK",
        hint="Add compositor nodes until the tree has at least 10, with at least one added after opening the file.",
        title="Compositor Cook",
        description="Build a compositor node tree with 10 or more nodes.",
        rare=False,
        category="Lighting & Rendering",
    ),
    "OUROBOROS": AchievementDefinition(
        id="OUROBOROS",
        hint="After opening the file, add a driver that points back to the same property and creates a cycle.",
        title="Ouroboros",
        description="Create a driver that references its own property (a cyclic dependency).",
        rare=True,
        category="Animation & Physics",
    ),
    "THE_PURGE": AchievementDefinition(
        id="THE_PURGE",
        hint="Delete 100 or more objects in one operation. Separate deletions are not added together.",
        title="The Purge",
        description="Delete 100 or more objects at once.",
        rare=True,
        category="Workflow & Disasters",
    ),
    "APPEND_ICITIS": AchievementDefinition(
        id="APPEND_ICITIS",
        hint="Append or link at least one object, material, or node group from another .blend file.",
        title="Append-icitis",
        description="Append or link data from another .blend file.",
        rare=False,
        category="Workflow & Disasters",
    ),
    "WHAT_AM_I_DOING": AchievementDefinition(
        id="WHAT_AM_I_DOING",
        hint="Leave Blender without input or scene activity for 4 continuous hours. Keyboard input, scene or frame changes, and renders reset the timer.",
        title="What am I doing?",
        description="Leave Blender running for 4 hours without doing anything.",
        rare=True,
        category="Workflow & Disasters",
        icon="What am I doing",
    ),

    # ============================ GLOBAL (CUMULATIVE) ACHIEVEMENTS ============================
    # Shape Shifter — global tiers (total shape keys created across all sessions)
    "SHAPE_SHIFTER_1": AchievementDefinition(
        id="SHAPE_SHIFTER_1", title="Shape Shifter I",
        description="Create 5 shape keys in total.",
        category="Milestones", counter="shapekeys_total", threshold=5,
        icon="Shape Shifter_I"),
    "SHAPE_SHIFTER_2": AchievementDefinition(
        id="SHAPE_SHIFTER_2", title="Shape Shifter II",
        description="Create 25 shape keys in total.",
        category="Milestones", counter="shapekeys_total", threshold=25,
        icon="Shape Shifter_II"),
    "SHAPE_SHIFTER_3": AchievementDefinition(
        id="SHAPE_SHIFTER_3", title="Shape Shifter III",
        description="Create 50 shape keys in total.",
        rare=True, category="Milestones", counter="shapekeys_total", threshold=50,
        icon="Shape Shifter_III"),

    # Good Habit — total manual saves
    "GOOD_HABIT_1": AchievementDefinition(
        id="GOOD_HABIT_1", title="Good Habit I",
        description="Save your project 100 times in total.",
        category="Milestones", counter="saves_total", threshold=100,
        icon="Good Habit_I"),
    "GOOD_HABIT_2": AchievementDefinition(
        id="GOOD_HABIT_2", title="Good Habit II",
        description="Save your project 1,000 times in total.",
        category="Milestones", counter="saves_total", threshold=1000,
        icon="Good Habit_II"),
    "GOOD_HABIT_3": AchievementDefinition(
        id="GOOD_HABIT_3", title="Good Habit III",
        description="Save your project 10,000 times in total.",
        rare=True, category="Milestones", counter="saves_total", threshold=10000,
        icon="Good Habit_III"),

    # NASA Computer — total completed renders
    "NASA_COMPUTER_1": AchievementDefinition(
        id="NASA_COMPUTER_1", title="NASA Computer I",
        description="Complete 100 renders in total.",
        category="Milestones", counter="renders_total", threshold=100,
        icon="NASA Computer_I"),
    "NASA_COMPUTER_2": AchievementDefinition(
        id="NASA_COMPUTER_2", title="NASA Computer II",
        description="Complete 1,000 renders in total.",
        category="Milestones", counter="renders_total", threshold=1000,
        icon="NASA Computer_II"),
    "NASA_COMPUTER_3": AchievementDefinition(
        id="NASA_COMPUTER_3", title="NASA Computer III",
        description="Complete 10,000 renders in total.",
        rare=True, category="Milestones", counter="renders_total", threshold=10000,
        icon="NASA Computer_III"),

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
        icon="Cube Genocide_I"),
    "CUBE_GENOCIDE_2": AchievementDefinition(
        id="CUBE_GENOCIDE_2", title="Cube Genocide II",
        description="Delete the default cube 100 times in total.",
        category="Milestones", counter="cubes_deleted", threshold=100,
        icon="Cube Genocide_II"),
    "CUBE_GENOCIDE_3": AchievementDefinition(
        id="CUBE_GENOCIDE_3", title="Cube Genocide III",
        description="Delete the default cube 1,000 times in total.",
        rare=True, category="Milestones", counter="cubes_deleted", threshold=1000,
        icon="Cube Genocide_III"),

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
        progress_unit="SECONDS",
        description="Spend 10 hours in Blender in total.",
        category="Milestones", counter="uptime_seconds", threshold=36000,
        icon="Unemployed_I"),
    "UNEMPLOYED_2": AchievementDefinition(
        id="UNEMPLOYED_2", title="Unemployed II",
        progress_unit="SECONDS",
        description="Spend 100 hours in Blender in total.",
        category="Milestones", counter="uptime_seconds", threshold=360000,
        icon="Unemployed_II"),
    "UNEMPLOYED_3": AchievementDefinition(
        id="UNEMPLOYED_3", title="Unemployed III",
        progress_unit="SECONDS",
        description="Spend 1,000 hours in Blender in total.",
        rare=True, category="Milestones", counter="uptime_seconds", threshold=3600000,
        icon="Unemployed_III"),

    # Sculpt Sanctuary — total time in Sculpt Mode (seconds)
    "SCULPT_SANCTUARY": AchievementDefinition(
        id="SCULPT_SANCTUARY", title="Sculpt Sanctuary",
        progress_unit="SECONDS",
        description="Spend 20 hours in Sculpt Mode in total.",
        category="Milestones", counter="sculpt_seconds", threshold=72000),

    # Loyalty — total Blender launches
    "LOYALTY_1": AchievementDefinition(
        id="LOYALTY_1", title="Loyalty I",
        description="Launch Blender 100 times.",
        category="Milestones", counter="launches", threshold=100,
        icon="Loyalty_I"),
    "LOYALTY_2": AchievementDefinition(
        id="LOYALTY_2", title="Loyalty II",
        description="Launch Blender 500 times.",
        category="Milestones", counter="launches", threshold=500,
        icon="Loyalty_II"),
    "LOYALTY_3": AchievementDefinition(
        id="LOYALTY_3", title="Loyalty III",
        description="Launch Blender 1,000 times.",
        rare=True, category="Milestones", counter="launches", threshold=1000,
        icon="Loyalty_III"),

    # The Long Haul — a single render longer than 24 hours (event, not counter)
    "THE_LONG_HAUL": AchievementDefinition(
        id="THE_LONG_HAUL", title="The Long Haul",
        hint="Finish one continuous render lasting at least 24 hours. Separate renders are not added together.",
        description="Finish a single render lasting at least 24 hours.",
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

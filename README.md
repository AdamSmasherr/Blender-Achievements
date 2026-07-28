# Blender Achievements

A native Blender addon that gamifies your workflow with achievements. 79 achievements from “delete the default cube” to “render one billion polygons in total” - some fire instantly within a session, others accumulate across every session you’ve ever had.

## Features

- **79 achievements**  - session-scoped (things you do
*this* session) and global/cumulative (persisted totals across all time).
- **Three pop-up animation styles**, each with its own sound profile:
Steam, Xbox, and PlayStation.

<!-- The screenshots below are hosted on GitHub's CDN rather than committed to
     this repo. To (re)generate the links: open any issue on this repository,
     drag the PNG into the comment box, wait for the upload, then copy the
     generated https://github.com/user-attachments/... URL and paste it here.
     Close the issue draft without submitting — the upload stays valid. -->

![Xbox-style notification: a green banner with a trophy icon reading "Achievement unlocked — Donut Master"](<img width="342" height="74" alt="Image" src="https://github.com/user-attachments/assets/e5f7c3ef-df63-45e3-aa80-07cedf59b13c" />)

![Steam-style notification for a rare achievement: a dark card with a gold glowing icon reading "Domino Effect — Run a Rigid Body simulation with over 100 objects."]<img width="557" height="133" alt="Image" src="https://github.com/user-attachments/assets/690936d6-e532-452d-95fe-68e4b1f4aefd" />)

![PlayStation-style notification: a dark gradient card reading "Know your Place — Trophy earned!"](<img width="673" height="134" alt="Image" src="https://github.com/user-attachments/assets/76b9aa5f-aad4-419c-8be5-c7a9e9333c5d" />)
- **Сustomization**: mix any animation style with your own sound files,
per-slot and master volume control. Export/import profiles as JSON to move them between machines.
- Runs entirely off Blender’s own Python API — no external dependencies,
no network access, no telemetry.

## Installation

1. Download the latest `blender_achievements_vX_Y_Z.zip` from
[Releases](../../releases) (or build it yourself — see below).
2. In Blender: **Edit > Preferences > Add-ons > Install…**, pick the zip.
3. Enable “Blender Achievements”.
4. Open the **Achievements** tab in the 3D Viewport sidebar (press `N`) to
see your progress, or find the same list under the addon’s preferences.

Requires **Blender 4.4+**.

## Building from source

```bash
python build.py
```

## Configuring sounds & animation

Addon preferences → **Profiles**: pick Steam / Xbox / PlayStation for the
built-in look, or switch to **Custom** to build your own profile (any
animation style + your own sound files per slot). Use **Export Profiles** /
**Import Profiles** to carry your custom profiles to another machine.

## Achievement list

⭐ marks a **rare** achievement (drawn with the gold glow / diamond variant).

### Basics

| Achievement | Description |
| --- | --- |
| **Goodbye, Cube!**  | Delete the default cube within 30 seconds of launching Blender. |
| **Respect the Cube** ⭐ | Render a scene without deleting or modifying the default cube. |
| **Donut Master** | Render a torus with a glaze material. |
| **Suzanne’s Blessing** | Add a monkey mesh (Suzanne) to the scene. |

### Modeling & Sculpting

| Achievement | Description |
| --- | --- |
| **Polygon King** ⭐ | Reach over 10,000,000 polygons in a single scene or mesh. |
| **Frankenstein** ⭐ | Join over 100 separate objects into a single mesh. |
| **Flat Earth** | Work in the UV Editing tab for over 30 minutes straight. |
| **Subdiv Overkill** | Set Subdivision Surface viewport/render level to 6 or higher. |
| **Up is Down** | Recalculate or flip inverted normals on a mesh. |
| **Surgical Precision** | Make over 50 manual cuts using the Knife tool in one session. |
| **Singularity** | Merge over 100 overlapping vertices using Merge by Distance. |
| **N-gon Criminal** | Create a single face with 10 or more sides. |

### Nodes & Materials

| Achievement | Description |
| --- | --- |
| **Node Spaghetti** ⭐ | Connect over 50 nodes in Shader or Geometry Nodes. |
| **Pure Procedural** | Create a material without using any external image textures. |
| **Geometry Nodes Guru** ⭐ | Create a node tree with 5+ nested Node Groups. |
| **Material Hoarder** | Accumulate 30 or more materials in a single project file. |
| **Devine Shield** | Assign Fake User (Shield icon) to 10 unused datablocks. |
| **Flashbang** | Set an Emission node strength above 10,000. |
| **Color Ramp Addict** | Use 5 or more Color Ramp nodes in a single shader tree. |

### Animation & Physics

| Achievement | Description |
| --- | --- |
| **Graph Editor Tweaker** | Adjust over 100 keyframe interpolation handles in the Graph Editor. |
| **Exoskeleton** | Build an armature rig containing over 50 bones. |
| **Driver Specialist** | Create 5 custom Python drivers linking object properties. |
| **Domino Effect** ⭐ | Run a Rigid Body simulation with over 100 objects. |
| **Let it cook** | Bake a fluid or smoke simulation longer than 250 frames. |
| **Particle Storm** | Emit over 100,000 particles from a single emitter setup. |
| **Rip and Tear** ⭐ | Run a Cloth simulation where mesh vertices travel over 100 units away instantly. |
| **Ouroboros** ⭐ | Create a driver that references its own property (a cyclic dependency). |

### Lighting & Rendering

| Achievement | Description |
| --- | --- |
| **Night Shift** ⭐ | Keep a render process running for over 4 consecutive hours. |
| **Cinema Quality** | Set render samples above 10,000. |
| **Warp Speed** | Render 100+ animation frames in under 1 minute. |
| **Out of Memory** ⭐ | Trigger a render error due to running out of GPU memory. |
| **Motion Blur** | Render an animation sequence with Motion Blur enabled. |
| **Now I become death** | Set Sun Light strength to over 1,000. |
| **Denoise Magic** | Render an image with under 32 samples using AI denoising. |
| **Ghost in the Shell** | Render a scene with transparent background enabled. |
| **Compositor Cook** | Build a compositor node tree with 10 or more nodes. |

### Workflow & Disasters

| Achievement | Description |
| --- | --- |
| **Time Traveler** | Undo actions 50+ times in a row within one minute. |
| **Back from the dead** ⭐ | Successfully restore a project via Recover Auto Save after a crash. |
| **Living on the Edge** | Work on a complex scene for over 2 hours without saving (Ctrl+S). |
| **Add-on Collector** | Enable over 25 add-ons in the preferences. |
| **Shortcut Ninja** ⭐ | Use 30 different keyboard shortcuts in a minute without opening mouse menus. |
| **Know your Place** | Apply scale, rotation, and location (Ctrl+A) on 20+ objects in a scene. |
| **Outliner Chaos** | Maintain 47+ auto-named objects (Cube.001, Cube.002) without renaming. |
| **Paranoia** | Save your project manually over 50 times in a single session. |
| **The Purge** ⭐ | Delete 100 or more objects in a single operation. |
| **Append-icitis** | Append or link data from another .blend file. |
| **What am I doing?** ⭐ | Leave Blender running for 4 hours without doing anything. |

### Milestones

| Achievement | Description |
| --- | --- |
| **Shape Shifter I** | Create 5 shape keys in total. |
| **Shape Shifter II** | Create 25 shape keys in total. |
| **Shape Shifter III** ⭐ | Create 50 shape keys in total. |
| **Good Habit I** | Save your project 100 times in total. |
| **Good Habit II** | Save your project 1,000 times in total. |
| **Good Habit III** ⭐ | Save your project 10,000 times in total. |
| **NASA Computer I** | Complete 100 renders in total. |
| **NASA Computer II** | Complete 1,000 renders in total. |
| **NASA Computer III** ⭐ | Complete 10,000 renders in total. |
| **Feature Film** ⭐ | Render 100,000 frames in total. |
| **Cube Genocide I** | Delete the default cube 10 times in total. |
| **Cube Genocide II** | Delete the default cube 100 times in total. |
| **Cube Genocide III** ⭐ | Delete the default cube 1,000 times in total. |
| **Monkey Business** | Add Suzanne to a scene 50 times in total. |
| **Puppeteer** ⭐ | Set 100,000 keyframes in total. |
| **Polygon Tycoon** ⭐ | Create one billion polygons in total. |
| **Material World** | Create 1,000 materials in total. |
| **Node Architect** | Connect 10,000 node links in total. |
| **Un Un Un Undo** | Undo 10,000 times in total. |
| **Bake Sale**  | Bake 50 simulations in total. |
| **Unemployed I** | Spend 10 hours in Blender in total. |
| **Unemployed II** | Spend 100 hours in Blender in total. |
| **Unemployed III** ⭐ | Spend 1,000 hours in Blender in total. |
| **Sculpt Sanctuary** | Spend 20 hours in Sculpt Mode in total. |
| **Loyalty I** | Launch Blender 100 times. |
| **Loyalty II** | Launch Blender 500 times. |
| **Loyalty III** ⭐ | Launch Blender 1,000 times. |
| **The Long Haul** ⭐ | Keep a single render running for over 24 hours. |
| **Live to Die Another Day** | Recover from a crash 10 times in total. |
| **Consistency** | Open Blender 7 days in a row. |
| **Dedicated** ⭐ | Open Blender 30 days in a row. |
| **Year of the Donut** ⭐ | Use Blender on 365 different days. |

## Privacy

Everything runs locally. The only file written to disk is the state JSON
in your Blender config folder — no network requests, no analytics.

## License

Code: GPL-3.0-or-later, see [LICENSE](LICENSE).
Bundled fonts and sounds carry their own open licenses — see
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

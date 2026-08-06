"""
Scene-state achievement detectors, driven against real bpy.data/bpy.ops —
the thing tests/unit fundamentally can't touch (no real scene, no real
depsgraph) and the reason this addon's trickiest bugs kept slipping through
(see the "last_op was always empty" comments throughout achievements.py:
several of these detectors were silently dead for a long time because
nothing exercised them against a real scene).

Every test uses achievements.testing.sandbox() (redirects storage, silences
toast.show, resets tracking state) and scene_guard() (removes any
object/mesh/material/node-group left behind), so a failure here never
touches the tester's real progress file or leaves scene debris.

Object-mode Python API calls (bpy.data.objects.new/remove, bmesh) are
preferred over bpy.ops wherever the two are equivalent, since operators tied
to a 3D viewport context can behave differently — or refuse to run at all —
in true `--background` mode. Where bpy.ops is used below (primitive_*_add,
object.join), those are EXEC-context operators that don't need a window.
"""

import math

import bmesh
import bpy

from achievements.testing import sandbox, scene_guard, run_depsgraph_update
from common import expect


def _tmp_path(name):
    """A fresh sandbox state file for this test — fresh meaning actually
    empty, not just uniquely named: the temp file from a previous headless
    run (a separate `blender --background` process) would otherwise still
    be sitting on disk, and sandbox() would happily load its leftover
    unlocked achievements as this run's starting state."""
    import os
    import tempfile
    path = os.path.join(tempfile.gettempdir(), f"ach_headless_detect_{name}.json")
    if os.path.exists(path):
        os.remove(path)
    return path


def test_adding_monkey_unlocks_suzannes_blessing():
    with sandbox(_tmp_path("suzanne")) as eng, scene_guard():
        expect(not eng.is_unlocked("SUZANNES_BLESSING"), "precondition: should start locked")
        bpy.ops.mesh.primitive_monkey_add()
        run_depsgraph_update()
        expect(eng.is_unlocked("SUZANNES_BLESSING"),
               "adding a Suzanne mesh did not unlock SUZANNES_BLESSING")
        expect(eng.get_stat("suzannes_added") == 1,
               f"suzannes_added stat wrong: {eng.get_stat('suzannes_added')}")


def test_deleting_fresh_cube_unlocks_goodbye_cube():
    with sandbox(_tmp_path("goodbye_cube")) as eng, scene_guard():
        bpy.ops.mesh.primitive_cube_add()
        run_depsgraph_update()   # let the addon register the cube as "known" first
        cube = bpy.data.objects.get("Cube")
        expect(cube is not None, "primitive_cube_add did not create an object named 'Cube'")

        bpy.data.objects.remove(cube, do_unlink=True)
        run_depsgraph_update()

        expect(eng.is_unlocked("GOODBYE_CUBE"),
               "deleting a freshly-added cube did not unlock GOODBYE_CUBE "
               "(note: this achievement requires the delete to happen within "
               "30s of the tracked session/launch time, which sandbox() resets)")


def _make_cube_object(name):
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(mesh)
    bm.free()
    ob = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def test_joining_over_100_objects_unlocks_fatal_ctrl_j():
    with sandbox(_tmp_path("join")) as eng, scene_guard():
        objs = [_make_cube_object(f"JoinCube_{i}") for i in range(101)]
        run_depsgraph_update()   # baseline: register all 101 as "known" before joining

        bpy.context.view_layer.objects.active = objs[0]
        for ob in objs:
            ob.select_set(True)
        bpy.ops.object.join()
        run_depsgraph_update()

        expect(eng.is_unlocked("FATAL_CTRL_J"),
               "joining 101 objects (preserving their vertices) did not unlock FATAL_CTRL_J")


def _make_empty(name):
    ob = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def test_mass_deleting_100_empties_unlocks_the_purge_not_join():
    """100+ objects vanishing at once with none of them mesh objects can't be
    a join (join needs mesh geometry to preserve) — it must register as
    THE_PURGE instead. Empties specifically avoid the join heuristic, which
    only looks at whether any *mesh* objects were among the ones removed."""
    with sandbox(_tmp_path("purge")) as eng, scene_guard():
        empties = [_make_empty(f"PurgeEmpty_{i}") for i in range(100)]
        run_depsgraph_update()

        for ob in empties:
            bpy.data.objects.remove(ob, do_unlink=True)
        run_depsgraph_update()

        expect(eng.is_unlocked("THE_PURGE"),
               "deleting 100 non-mesh objects at once did not unlock THE_PURGE")
        expect(not eng.is_unlocked("FATAL_CTRL_J"),
               "deleting empties was misclassified as a join (FATAL_CTRL_J unlocked)")


def _make_ngon_object(name, sides=10):
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    verts = [
        bm.verts.new((math.cos(2 * math.pi * i / sides), math.sin(2 * math.pi * i / sides), 0.0))
        for i in range(sides)
    ]
    bm.faces.new(verts)
    bm.to_mesh(mesh)
    bm.free()
    ob = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def test_ngon_face_on_new_mesh_unlocks_n_gon_criminal():
    with sandbox(_tmp_path("ngon")) as eng, scene_guard():
        _make_ngon_object("NgonTest", sides=10)
        run_depsgraph_update()
        expect(eng.is_unlocked("N_GON_CRIMINAL"),
               "a 10-sided face on a mesh created this session did not unlock N_GON_CRIMINAL")


def test_30_materials_unlocks_material_hoarder():
    with sandbox(_tmp_path("materials")) as eng, scene_guard():
        # Add on top of whatever's already there rather than assuming a
        # starting count of 0 — the check is len(bpy.data.materials) >= 30,
        # a total, not a session delta.
        needed = max(0, 30 - len(bpy.data.materials))
        for i in range(needed + 2):
            bpy.data.materials.new(f"HoarderMat_{i}")
        run_depsgraph_update()
        expect(eng.is_unlocked("MATERIAL_HOARDER"),
               f"{len(bpy.data.materials)} total materials did not unlock MATERIAL_HOARDER")


def tests():
    return [
        ("adding a Suzanne mesh unlocks SUZANNES_BLESSING",
         test_adding_monkey_unlocks_suzannes_blessing),
        ("deleting a fresh cube unlocks GOODBYE_CUBE",
         test_deleting_fresh_cube_unlocks_goodbye_cube),
        ("joining 101 objects unlocks FATAL_CTRL_J",
         test_joining_over_100_objects_unlocks_fatal_ctrl_j),
        ("mass-deleting 100 empties unlocks THE_PURGE, not FATAL_CTRL_J",
         test_mass_deleting_100_empties_unlocks_the_purge_not_join),
        ("a 10-sided n-gon on a new mesh unlocks N_GON_CRIMINAL",
         test_ngon_face_on_new_mesh_unlocks_n_gon_criminal),
        ("30+ total materials unlocks MATERIAL_HOARDER",
         test_30_materials_unlocks_material_hoarder),
    ]

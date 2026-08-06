"""Nodes & materials rules.

Everything that walks a node tree is bound with an `interval`: a node tree
walk is O(nodes) and depsgraph updates arrive dozens of times a second while
dragging, so these ran behind a hand-rolled debounce before. The debounce is
now the rule's own declared property.
"""

import bpy

from ..registry import DEPSGRAPH, TIMER, bind
from . import probes

NODE_SCAN_INTERVAL = 1.5     # с між важкими обходами дерев
EMISSION_LIMIT = 10000.0


def _node_spaghetti(ctx) -> bool:
    """50+ нод, реально з'єднаних (>=49 лінків), у дереві цієї сесії."""
    for mat in bpy.data.materials:
        nt = getattr(mat, "node_tree", None)
        if nt and ctx.is_new('materials', mat.name):
            if len(nt.nodes) >= 50 and len(nt.links) >= 49:
                return True
    for ng in bpy.data.node_groups:
        if ctx.is_new('node_groups', ng.name) and len(ng.nodes) >= 50 and len(ng.links) >= 49:
            return True
    return False


def _pure_procedural(ctx) -> bool:
    """Матеріал із 10+ нод і без жодної image-текстури.

    Перевіряється з таймера, а не з рендеру: раніше ачивку не можна було
    отримати без F12 взагалі.
    """
    for mat in bpy.data.materials:
        tree = getattr(mat, "node_tree", None)
        if tree is None or len(tree.nodes) < 10 or len(tree.links) < 8:
            continue
        if not any(n.type in {'TEX_IMAGE', 'TEX_ENVIRONMENT'} for n in tree.nodes):
            return True
    return False


def _emission_overdrive(ctx) -> bool:
    for mat in bpy.data.materials:
        tree = getattr(mat, "node_tree", None)
        if tree is None or not ctx.is_new('materials', mat.name):
            continue
        for node in tree.nodes:
            if node.type == 'EMISSION':
                if 'Strength' in node.inputs and node.inputs['Strength'].default_value > EMISSION_LIMIT:
                    return True
            elif node.type == 'BSDF_PRINCIPLED':
                if ('Emission Strength' in node.inputs
                        and node.inputs['Emission Strength'].default_value > EMISSION_LIMIT):
                    return True
    return False


bind("NODE_SPAGHETTI", DEPSGRAPH, check=_node_spaghetti,
     progress=probes.biggest_node_tree, target=50,
     interval=NODE_SCAN_INTERVAL, scan=True)

bind("GEOMETRY_NODES_GURU", DEPSGRAPH, target=5, interval=NODE_SCAN_INTERVAL, scan=True,
     progress=lambda ctx: probes.node_group_scan(ctx).get("max_nested", 0))

bind("COLOR_RAMP_ADDICT", DEPSGRAPH, target=5, interval=NODE_SCAN_INTERVAL, scan=True,
     progress=lambda ctx: probes.material_scan(ctx).get("max_ramps", 0))

bind("EMISSION_OVERDRIVE", DEPSGRAPH, check=_emission_overdrive,
     interval=NODE_SCAN_INTERVAL)

# «in a single project file» — усі матеріали сцени, не лише створені цієї сесії.
bind("MATERIAL_HOARDER", DEPSGRAPH, progress=probes.materials_count, target=30, scan=True)

bind("PURE_PROCEDURAL", TIMER, check=_pure_procedural)

# Дельта понад baseline: щити, які вже стояли у відкритому файлі, не рахуються.
bind("SAVED_BY_SHIELD", TIMER, target=10, scan=True,
     progress=lambda ctx: ctx.baseline_delta(probes.fake_users(ctx), 'fake_user_count'))

"""
Lazily-built bpy.utils.previews collection holding one custom icon per
achievement, used by the achievements list (achievements/ui/panels.py).
"""

import os

from .. import registry
from .. import engine

_custom_icons = None


def get_custom_icons():
    global _custom_icons
    if _custom_icons is None:
        try:
            import bpy.utils.previews
            _custom_icons = bpy.utils.previews.new()
            for ach_id, ach_def in registry.ACHIEVEMENTS.items():
                icon_path = engine._resolve_icon_path(ach_def)
                if icon_path and os.path.exists(icon_path):
                    try:
                        _custom_icons.load(ach_id, icon_path, 'IMAGE')
                    except Exception:
                        pass
        except Exception:
            _custom_icons = None
    return _custom_icons


def clear_custom_icons():
    global _custom_icons
    if _custom_icons is not None:
        try:
            import bpy.utils.previews
            bpy.utils.previews.remove(_custom_icons)
        except Exception:
            pass
        _custom_icons = None

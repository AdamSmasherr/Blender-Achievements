"""Shared, temporary browsing state for the sidebar and Preferences."""

import bpy

from ..registry import ACHIEVEMENTS
from .helpers import _tag_redraw_all


CATEGORY_ITEMS = (
    ('ALL', "All Categories", "Show every achievement category"),
    *((category, category, f"Show {category} achievements")
      for category in dict.fromkeys(d.category for d in ACHIEVEMENTS.values())),
)


def _filters_changed(self, context):
    _tag_redraw_all()


class ACHIEVEMENT_PG_browser(bpy.types.PropertyGroup):
    query: bpy.props.StringProperty(
        name="Search Achievements", default="",
        description="Search achievement names and conditions",
        options={'SKIP_SAVE', 'TEXTEDIT_UPDATE'}, update=_filters_changed)
    status: bpy.props.EnumProperty(
        name="Status", default='ALL', options={'SKIP_SAVE'},
        items=(('ALL', "All", "Show unlocked and locked achievements"),
               ('UNLOCKED', "Unlocked", "Show earned achievements, newest first"),
               ('LOCKED', "Locked", "Show achievements still to earn")),
        update=_filters_changed)
    category: bpy.props.EnumProperty(
        name="Category", default='ALL', items=CATEGORY_ITEMS,
        options={'SKIP_SAVE'}, update=_filters_changed)


def get_browser(context):
    wm = getattr(context, "window_manager", None)
    return getattr(wm, "achievement_browser", None)


def filter_achievements(definitions, unlocked_ids, query="", status='ALL', category='ALL'):
    """Filter metadata only; browsing never evaluates achievement rules."""
    query = query.strip().casefold()
    return [d for d in definitions
            if (category == 'ALL' or d.category == category)
            and (status == 'ALL' or (d.id in unlocked_ids) == (status == 'UNLOCKED'))
            and (not query or query in d.title.casefold() or query in d.description.casefold())]


class ACHIEVEMENT_OT_clear_filters(bpy.types.Operator):
    bl_idname = "achievement.clear_filters"
    bl_label = "Clear Filters"
    bl_description = "Clear the search and show all statuses and categories"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        browser = get_browser(context)
        if browser is None:
            return {'CANCELLED'}
        browser.query = ""
        browser.status = 'ALL'
        browser.category = 'ALL'
        _tag_redraw_all()
        return {'FINISHED'}

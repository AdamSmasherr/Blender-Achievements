"""Exercise browsing with real Blender RNA and operators, without tracking."""

import bpy

from achievements import ui
from achievements.ui.catalog import get_browser
from common import expect


def test_browser_registration_and_reset():
    dirty = bpy.data.is_dirty
    ui.register()
    try:
        browser = get_browser(bpy.context)
        expect(browser is not None, "browser property was not registered")
        expect((browser.query, browser.status, browser.category) == ('', 'ALL', 'ALL'),
               "a fresh browser should show the entire catalog")
        browser.query = 'cube'
        browser.status = 'LOCKED'
        browser.category = 'Basics'
        expect(get_browser(bpy.context).query == 'cube', "browser state is not shared")
        expect(bpy.data.is_dirty == dirty, "browsing marked the project as modified")
        expect(bpy.ops.achievement.clear_filters() == {'FINISHED'}, "clear filters failed")
        expect((browser.query, browser.status, browser.category) == ('', 'ALL', 'ALL'),
               "clear filters did not restore the full catalog")
        expect(bpy.ops.achievement.details(achievement_id='GOODBYE_CUBE') == {'FINISHED'},
               "read-only details operator was not registered")
    finally:
        ui.unregister()
    expect(not hasattr(bpy.types.WindowManager, 'achievement_browser'),
           "browser property survived unregister")


def tests():
    return [("native browser state, operators and cleanup", test_browser_registration_and_reset)]

# Changelog

## 1.3.1

**Fixed**
- Prevented a Blender crash when a new `.blend` file is opened while an achievement notification is animating.
- Cleared cached viewport redraw targets before and after file-load transitions while preserving queued notifications.
- Credit: [erispe](https://github.com/erispe) for reporting the file-switch crash in [Issue #1](https://github.com/AdamSmasherr/Blender-Achievements/issues/1).

## 1.3.0

**New**
- Search achievements by name or condition, and filter by category or status: All, Unlocked or Locked. Clear all filters with one click.
- Each achievement now has a details pop-up. Click the info icon next to its name to see the full condition, how progress is counted, and your current progress or unlock date.
- Compact mode can be switched on directly in the sidebar.
- Notification style, sound, master volume and preview buttons are now together at the top of the add-on preferences.

**Fixed**
- Time-based achievements now show hours and minutes instead of raw seconds: 5 h / 10 h instead of 18000 / 36000.
- Achievement explanations are clearer about what counts, what resets, and whether progress carries over between Blender sessions.
- Achievement names line up consistently in both full and compact lists, including rows without a progress bar.
- Unlock dates have their own line in the full list, so they no longer squeeze achievement names.
- Duplicating a custom sound profile now preserves its notification animation style.

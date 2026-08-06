"""
Reusable draw helpers for the sound-slot grid, shared by AddonPreferences
(preset slots) and custom Profiles (per-profile slots).
"""

from .. import sounds


def _draw_sound_slot(layout, prefs, slot, profile=None):
    """One slot cell: label, file picker, volume, play/stop toggle."""
    box = layout.box()
    header = box.row(align=True)
    header.label(text=sounds.SLOT_LABELS.get(slot, slot))
    playing = sounds.is_previewing(slot)
    op = header.operator("achievement.preview_sound", text="",
                         icon='SNAP_FACE' if playing else 'PLAY')
    op.slot = slot

    raw = sounds.raw_slot_path(slot, prefs, profile=profile)

    if profile is not None:
        box.prop(profile, f"{slot}_sound", text="")
        vol_owner, vol_attr = profile, f"{slot}_volume"
    else:
        preset = getattr(prefs, "sound_preset", 'STEAM')
        box.prop(prefs, sounds.preset_override_attr(preset, slot), text="")
        vol_owner, vol_attr = prefs, f"{slot}_volume"

    if sounds.is_missing(raw):
        warn = box.row()
        warn.alert = True
        warn.label(text="missing sound file, please check file path", icon='ERROR')

    box.prop(vol_owner, vol_attr, text="Volume", slider=True)


def _draw_sound_slots_grid(layout, prefs, profile=None):
    """Слоти сіткою 2x2: звичайні зверху, рідкісні знизу; unlock зліва,
    end справа."""
    for left, right in (("unlock", "end"), ("rare_unlock", "rare_end")):
        row = layout.row(align=True)
        _draw_sound_slot(row.column(align=True), prefs, left, profile=profile)
        _draw_sound_slot(row.column(align=True), prefs, right, profile=profile)

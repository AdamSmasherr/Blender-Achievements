"""Unit tests for icon resolution and the Linear Burn tint.

The artwork is transparent white-and-grey webp; the tile behind it and the
colour burned into it are settings. Two things must hold for that to look
right, and both are cheap to state as tests: every achievement resolves to a
file that actually exists (except the one deliberately without artwork), and
the burn shifts colours without eating the contrast between light and grey.
"""

import os

import pytest

from achievements import engine, registry, toast


# --- Icon resolution ------------------------------------------------------

def test_every_achievement_resolves_to_an_existing_file_except_the_iconless_one():
    """A renamed or missing icon shows up here rather than as a blank tile
    in the pop-up."""
    missing = []
    for aid, d in registry.ACHIEVEMENTS.items():
        if d.icon == registry.NO_ICON:
            continue
        path = engine._resolve_icon_path(d)
        if not path or not os.path.exists(path):
            missing.append(aid)
    assert missing == []


def test_out_of_memory_has_no_icon_on_purpose():
    """Its joke is a tile that looks like the icon failed to load, so the
    pop-up must get None rather than a file."""
    d = registry.ACHIEVEMENTS["VRAM_VICTIM"]
    assert d.icon == registry.NO_ICON
    assert engine._resolve_icon_path(d) is None


def test_icon_stem_falls_back_to_the_title():
    d = registry.ACHIEVEMENTS["DONUT_MASTER"]
    assert d.icon is None
    assert os.path.basename(engine._resolve_icon_path(d)) == f"Donut Master{engine.ICON_SUFFIX}"


def test_explicit_stem_is_used_when_the_title_does_not_match_the_file():
    d = registry.ACHIEVEMENTS["LOYALTY_2"]
    assert os.path.basename(engine._resolve_icon_path(d)) == f"Loyalty_II{engine.ICON_SUFFIX}"


# --- Linear burn ----------------------------------------------------------

def test_white_tint_leaves_the_artwork_untouched():
    """The default has to be a no-op, or every icon would change the moment
    the setting existed."""
    for value in (0.0, 0.25, 0.6, 1.0):
        assert toast.linear_burn((value,) * 3, (1.0, 1.0, 1.0)) == pytest.approx((value,) * 3)


def test_white_pixels_take_the_tint_exactly():
    assert toast.linear_burn((1.0, 1.0, 1.0), (0.2, 0.6, 0.9)) == pytest.approx((0.2, 0.6, 0.9))


def test_burn_preserves_contrast_between_light_and_grey():
    """This is the whole reason for Linear Burn over a 50%-opacity blend: it
    shifts every channel by the same amount, so the gap between a light and a
    grey area survives untouched. A blend would pull both ends toward the
    tint and flatten the artwork into a silhouette."""
    tint = (0.80, 0.85, 0.95)
    light = toast.linear_burn((1.00, 1.00, 1.00), tint)
    grey = toast.linear_burn((0.60, 0.60, 0.60), tint)
    for i in range(3):
        assert light[i] - grey[i] == pytest.approx(0.40, abs=1e-6)


def test_a_dark_tint_crushes_the_darkest_shades_to_black():
    """Linear Burn clamps at zero — same as Photoshop. With a dark tint the
    deepest greys bottom out, which is the mode working as intended and not
    something to "fix" by rescaling: rescaling would stop white from landing
    exactly on the chosen colour.
    """
    dark_tint = (0.35, 0.35, 0.35)
    assert toast.linear_burn((1.0,) * 3, dark_tint) == pytest.approx((0.35,) * 3)
    assert toast.linear_burn((0.6,) * 3, dark_tint) == pytest.approx((0.0,) * 3)


def test_burn_clamps_instead_of_wrapping_into_negative():
    assert toast.linear_burn((0.1, 0.1, 0.1), (0.2, 0.2, 0.2)) == pytest.approx((0.0, 0.0, 0.0))


# --- Rare glow ------------------------------------------------------------

def test_playstation_has_no_glow_and_no_accent_colour():
    """PS trophies never had a golden burst, so neither the shader nor a
    colour field for it should exist there."""
    assert 'PS' not in toast.GLOW_STYLES
    assert toast.rare_glow_enabled('PS') is False
    assert "accent" not in toast.STYLE_COLOR_KEYS['PS']
    assert "accent" not in toast.STYLE_COLOR_DEFAULTS['PS']


def test_steam_is_the_style_that_glows():
    assert toast.GLOW_STYLES == ('STEAM',)
    assert "accent" in toast.STYLE_COLOR_KEYS['STEAM']


def test_icon_colour_defaults_exist_for_every_key():
    for key in toast.ICON_COLOR_KEYS:
        assert key in toast.ICON_COLOR_DEFAULTS
        assert key in toast.ICON_COLOR_LABELS
        assert len(toast.ICON_COLOR_DEFAULTS[key]) == 3

"""Unit tests for the portable sound-path packing used by profile export/import
(achievements/__init__.py: _pack_sound_path / _unpack_sound_path).

Pure path-string logic — no file needs to actually exist on disk, since
os.path.commonpath/relpath/abspath only manipulate strings.
"""

import os
import tempfile

import achievements as addon
from achievements import sounds


def test_pack_sound_path_inside_assets_dir_becomes_portable_token():
    inside = os.path.join(sounds.SOUND_DIR, "steam", "unlock.wav")
    packed = addon._pack_sound_path(inside)
    assert packed == "<assets>/steam/unlock.wav"


def test_pack_sound_path_outside_assets_dir_is_unchanged():
    outside = os.path.join(tempfile.gettempdir(), "my_custom_sound.wav")
    assert addon._pack_sound_path(outside) == outside


def test_pack_sound_path_empty_string():
    assert addon._pack_sound_path("") == ""


def test_unpack_sound_path_expands_asset_token():
    unpacked = addon._unpack_sound_path("<assets>/xbox/end.wav")
    assert unpacked == os.path.join(sounds.SOUND_DIR, "xbox", "end.wav")


def test_unpack_sound_path_leaves_non_token_paths_untouched():
    absolute = os.path.join(tempfile.gettempdir(), "custom.wav")
    assert addon._unpack_sound_path(absolute) == absolute


def test_pack_unpack_roundtrip_for_bundled_asset():
    inside = os.path.join(sounds.SOUND_DIR, "ps", "rare_unlock.wav")
    roundtripped = addon._unpack_sound_path(addon._pack_sound_path(inside))
    assert os.path.normpath(roundtripped) == os.path.normpath(inside)

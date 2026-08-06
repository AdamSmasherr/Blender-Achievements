"""Regression guard for the bpy.data.images leak fixed in toast.py:
_ensure_icon_tex / _asset / _get_mask_tex must remove the Image datablock
right after handing it to gpu.texture.from_image(), not leave it sitting in
bpy.data.images forever.

This only checks the *contract* (remove() gets called with the loaded
datablock) using the test-stub's MagicMock bpy.data.images — it can't verify
the GPU texture keeps working after removal, since the stub has no real GPU
behind it. That was verified empirically against a live Blender instead (see
the toast.py comments next to each fix); this test exists so a future edit
that accidentally drops the cleanup call gets caught here, without needing
a live Blender to notice.
"""

from unittest.mock import MagicMock

from achievements import toast


def test_ensure_icon_tex_removes_image_datablock_after_texture_creation(monkeypatch):
    img = MagicMock(name="loaded_image")
    load = MagicMock(return_value=img)
    remove = MagicMock()
    monkeypatch.setattr(toast.bpy.data, "images", MagicMock(load=load, remove=remove))
    monkeypatch.setattr(toast.gpu.texture, "from_image", MagicMock(return_value=MagicMock()))

    item = {"icon_path": "C:/fake/icon.png", "icon_img": None, "icon_tex": None, "icon_done": False}
    toast._ensure_icon_tex(item)

    remove.assert_called_once_with(img, do_unlink=True)
    assert item["icon_img"] is None
    assert item["icon_done"] is True


def test_ensure_icon_tex_removes_image_even_if_texture_creation_fails(monkeypatch):
    img = MagicMock(name="loaded_image")
    load = MagicMock(return_value=img)
    remove = MagicMock()
    monkeypatch.setattr(toast.bpy.data, "images", MagicMock(load=load, remove=remove))
    monkeypatch.setattr(toast.gpu.texture, "from_image",
                         MagicMock(side_effect=RuntimeError("GPU unavailable")))

    item = {"icon_path": "C:/fake/icon.png", "icon_img": None, "icon_tex": None, "icon_done": False}
    toast._ensure_icon_tex(item)

    remove.assert_called_once_with(img, do_unlink=True)
    assert item["icon_tex"] is None
    assert item["icon_img"] is None


def test_asset_removes_image_datablock_after_texture_creation(monkeypatch, tmp_path):
    fake_png = tmp_path / "fake.png"
    fake_png.write_bytes(b"\x89PNG\r\n")
    monkeypatch.setattr(toast, "ASSET_DIR", str(tmp_path))
    monkeypatch.setattr(toast, "_asset_tex", {})

    img = MagicMock(name="loaded_asset_image")
    load = MagicMock(return_value=img)
    remove = MagicMock()
    monkeypatch.setattr(toast.bpy.data, "images", MagicMock(load=load, remove=remove))
    monkeypatch.setattr(toast.gpu.texture, "from_image", MagicMock(return_value=MagicMock()))

    toast._asset("fake.png")

    remove.assert_called_once_with(img, do_unlink=True)

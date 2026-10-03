"""Regression tests for the toast/file-load lifecycle boundary.

Blender invalidates ``Area`` RNA wrappers while replacing a .blend file.  The
pre-load callback must drop the cached redraw target before the timer can call
``Area.tag_redraw`` again.
"""

from achievements import handlers
from achievements import toast


def test_load_pre_clears_cached_redraw_area_without_dropping_toasts():
    sentinel = object()
    toast._last_redraw_area = sentinel
    toast._pending[:] = [{"title": "queued"}]
    toast._toasts[:] = [{"title": "active"}]
    try:
        handlers.on_load_pre(None)

        assert toast._last_redraw_area is None
        assert toast._pending == [{"title": "queued"}]
        assert toast._toasts == [{"title": "active"}]
    finally:
        # Keep module state isolated from the other unit tests.
        toast._pending.clear()
        toast._toasts.clear()
        toast._last_redraw_area = None


def test_post_load_texture_invalidation_also_clears_redraw_area():
    toast._last_redraw_area = object()
    try:
        toast.invalidate_textures()
        assert toast._last_redraw_area is None
    finally:
        toast._last_redraw_area = None


def test_redraw_after_load_pre_never_touches_stale_area(monkeypatch):
    class FakeArea:
        def __init__(self):
            self.redraws = 0

        def tag_redraw(self):
            self.redraws += 1

    stale = FakeArea()
    current = FakeArea()
    toast._last_redraw_area = stale
    monkeypatch.setattr(toast, "_preferred_target", lambda: (current, None))
    try:
        handlers.on_load_pre(None)
        toast._redraw_all()

        assert stale.redraws == 0
        assert current.redraws == 1
        assert toast._last_redraw_area is current
    finally:
        toast._last_redraw_area = None

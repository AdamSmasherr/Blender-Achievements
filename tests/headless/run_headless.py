"""
Entry point for the headless test layer: register/unregister lifecycle,
real-filesystem storage, and scene-state achievement detectors — everything
that needs a real bpy but not a window (see tests/live for what does).

Usage:
    blender --background --python tests/headless/run_headless.py

Exits non-zero if any test failed, so it plugs into CI or a pre-release
checklist the same way a normal test runner would.
"""

import os
import sys

_HEADLESS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HEADLESS_DIR))

# Flat imports (not a package): a script handed to `blender --python` has no
# reliable __package__, so plain `import common` / `import test_lifecycle`
# from this directory is more robust than relative imports here.
for _p in (_REPO_ROOT, _HEADLESS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import common
import test_lifecycle
import test_persistence
import test_detectors


def main():
    total_failed = 0
    total_failed += common.run_suite("Lifecycle", test_lifecycle.tests())
    total_failed += common.run_suite("Persistence", test_persistence.tests())
    total_failed += common.run_suite("Detectors", test_detectors.tests())

    print("\n" + "=" * 60)
    if total_failed:
        print(f"HEADLESS SUITE: {total_failed} failure(s)")
    else:
        print("HEADLESS SUITE: all tests passed")
    print("=" * 60)

    sys.exit(1 if total_failed else 0)


if __name__ == "__main__":
    main()

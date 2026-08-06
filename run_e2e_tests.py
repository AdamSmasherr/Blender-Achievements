"""
Runs the headless test layer (tests/headless/): register/unregister
lifecycle, real-filesystem storage, and scene-state achievement detectors —
everything that needs a real bpy but not a window.

This is one of three test layers in the repo:
  - `pytest tests/unit` — pure logic, no Blender at all.
  - this script            — real bpy, `blender --background`, no window.
  - tests/live/            — needs a real window (viewport draw, watcher
                              key events); driven through an MCP-connected
                              Blender, not from here.

Usage:
  1. From terminal / external Python:
     python run_e2e_tests.py

  2. From inside Blender background:
     blender --background --python run_e2e_tests.py
"""

import sys
import os
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
TEST_RUNNER_SCRIPT = os.path.join(PROJECT_ROOT, "tests", "headless", "run_headless.py")

BLENDER_POSSIBLE_PATHS = [
    r"D:\GOG\steamapps\common\Blender\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender\blender.exe",
    "blender",
]


def find_blender():
    """Locate blender executable on system."""
    for path in BLENDER_POSSIBLE_PATHS:
        if os.path.isabs(path) and os.path.exists(path):
            return path
    # Try PATH
    try:
        res = subprocess.run(["where", "blender"], capture_output=True, text=True, check=False)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip().splitlines()[0]
    except Exception:
        pass
    return None


def main():
    # Check if already running inside Blender
    try:
        import bpy
        in_blender = True
    except ImportError:
        in_blender = False

    if in_blender:
        # Run tests directly inside this Blender process. tests/headless/
        # isn't a package (see run_headless.py's own sys.path handling —
        # scripts handed to `blender --python` have no reliable
        # __package__), so exec it rather than importing it.
        with open(TEST_RUNNER_SCRIPT, "r", encoding="utf-8") as f:
            code_text = f.read()
        try:
            exec(compile(code_text, TEST_RUNNER_SCRIPT, "exec"),
                 {"__name__": "__main__", "__file__": TEST_RUNNER_SCRIPT})
        except SystemExit:
            raise
        except Exception:
            # A real crash in the suite itself (not a normal sys.exit from
            # run_headless.main()) must still fail the process — Blender
            # doesn't turn an uncaught exception from --python into a
            # non-zero exit code on its own.
            import traceback
            traceback.print_exc()
            sys.exit(1)
    else:
        # External runner: find Blender and launch test runner script in background mode
        blender_bin = find_blender()
        if not blender_bin:
            print("[ERROR] Could not locate blender executable on system.")
            sys.exit(1)

        print(f"[*] Found Blender binary at: {blender_bin}")
        print(f"[*] Executing E2E test runner: {TEST_RUNNER_SCRIPT}")

        cmd = [blender_bin, "--background", "--python", TEST_RUNNER_SCRIPT]
        result = subprocess.run(cmd, capture_output=False)
        print(f"\n[*] Test runner finished with exit code: {result.returncode}")
        sys.exit(result.returncode)


if __name__ == "__main__":
    main()

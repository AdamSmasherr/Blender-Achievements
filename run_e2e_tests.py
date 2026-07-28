"""
Automated Top-Level Test Runner for Blender Achievements E2E Test Suite.

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
TEST_RUNNER_SCRIPT = os.path.join(PROJECT_ROOT, "tests", "run_tests.py")

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
        # Run tests directly inside Blender environment
        if PROJECT_ROOT not in sys.path:
            sys.path.insert(0, PROJECT_ROOT)
        from tests.run_tests import run_all_tests
        code = run_all_tests()
        sys.exit(code)
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

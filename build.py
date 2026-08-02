"""
Build script for Blender Achievements.

Packages the `achievements/` folder into a distributable zip,
reading the version from blender_manifest.toml so the output filename and
package contents can't drift out of sync with what's declared.

Usage:
    python build.py
"""

import os
import re
import zipfile

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
PACKAGE_DIR = os.path.join(REPO_ROOT, "achievements")
MANIFEST_PATH = os.path.join(PACKAGE_DIR, "blender_manifest.toml")

EXCLUDE_DIRS = {"ref", "example", "__pycache__"}
EXCLUDE_SUFFIXES = (".pyc", ".eot", ".woff", ".woff2", ".svg", ".lock")
EXCLUDE_PREFIXES = ("test_",)


def _read_version() -> str:
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        raise RuntimeError(f"Could not find version in {MANIFEST_PATH}")
    return m.group(1)


def _should_include(filename: str) -> bool:
    if filename.startswith(EXCLUDE_PREFIXES):
        return False
    if filename.endswith(EXCLUDE_SUFFIXES):
        return False
    return True


def build() -> str:
    if not os.path.isdir(PACKAGE_DIR):
        raise RuntimeError(f"Package directory not found: {PACKAGE_DIR}")

    version = _read_version()
    out_name = f"blender_achievements_v{version.replace('.', '_')}.zip"
    out_path = os.path.join(REPO_ROOT, out_name)

    package_name = os.path.basename(PACKAGE_DIR)
    file_count = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(PACKAGE_DIR):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for fname in files:
                if not _should_include(fname):
                    continue
                abs_path = os.path.join(root, fname)
                rel_path = os.path.join(
                    package_name, os.path.relpath(abs_path, PACKAGE_DIR)
                )
                z.write(abs_path, rel_path)
                file_count += 1

    print(f"Built {out_path}")
    print(f"Files: {file_count}")
    return out_path


if __name__ == "__main__":
    build()

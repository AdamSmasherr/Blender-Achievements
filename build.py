"""
Build script for Blender Achievements.

Packages `achievements/` and `achievements_devtools/` into distributable
zips, reading each one's version from its own blender_manifest.toml so the
output filename and package contents can't drift out of sync with what's
declared.

Usage:
    python build.py
"""

import os
import re
import zipfile

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))

EXCLUDE_DIRS = {"ref", "example", "__pycache__"}
EXCLUDE_SUFFIXES = (".pyc", ".eot", ".woff", ".woff2", ".svg", ".lock")
EXCLUDE_PREFIXES = ("test_",)


def _read_version(manifest_path: str) -> str:
    with open(manifest_path, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        raise RuntimeError(f"Could not find version in {manifest_path}")
    return m.group(1)


def _should_include(filename: str) -> bool:
    if filename.startswith(EXCLUDE_PREFIXES):
        return False
    if filename.endswith(EXCLUDE_SUFFIXES):
        return False
    return True


def _build_package(package_dir: str, out_name_prefix: str) -> str:
    if not os.path.isdir(package_dir):
        raise RuntimeError(f"Package directory not found: {package_dir}")

    manifest_path = os.path.join(package_dir, "blender_manifest.toml")
    version = _read_version(manifest_path)
    out_name = f"{out_name_prefix}_v{version.replace('.', '_')}.zip"
    out_path = os.path.join(REPO_ROOT, out_name)

    package_name = os.path.basename(package_dir)
    file_count = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(package_dir):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for fname in files:
                if not _should_include(fname):
                    continue
                abs_path = os.path.join(root, fname)
                rel_path = os.path.join(
                    package_name, os.path.relpath(abs_path, package_dir)
                )
                z.write(abs_path, rel_path)
                file_count += 1

    print(f"Built {out_path}")
    print(f"Files: {file_count}")
    return out_path


def build() -> str:
    """Packages the main achievements/ addon. Kept as the public entry point
    other scripts/CI already call by this name."""
    return _build_package(os.path.join(REPO_ROOT, "achievements"), "blender_achievements")


def build_devtools() -> str:
    """Packages the achievements_devtools/ companion addon."""
    return _build_package(os.path.join(REPO_ROOT, "achievements_devtools"),
                           "blender_achievements_devtools")


if __name__ == "__main__":
    build()
    build_devtools()

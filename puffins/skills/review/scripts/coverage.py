#!/usr/bin/env python3
"""Check OUT_DIR/projects.yaml covers every code file of the repo, and lists no stale or non-code paths.

Usage: coverage.py [OUT_DIR=.puffins] [--untracked] [--all-files]   (run inside the repo)
Files are `git ls-files` (every file outside build/vendor dirs without git), code only:
no images, media, binaries, archives, logs, data, lockfiles or licenses.
--untracked  also untracked, non-ignored files.
--all-files  every file, code or not.
A listed `dir/*` (or `dir/*.ext`) covers everything matching under it. OUT_DIR is never listed.
Adds OUT_DIR/ to the repo .gitignore if missing.
Exit 1 if any file is unrepresented or a listed path is not code.
"""
import argparse
import fnmatch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import ensure_gitignored, is_code, load_projects, repo_files, repo_root  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("out_dir", nargs="?", default=".puffins")
ap.add_argument("--untracked", action="store_true")
ap.add_argument("--all-files", action="store_true")
a = ap.parse_args()

out_dir = a.out_dir.strip("/")
root = repo_root()
ensure_gitignored(root, out_dir)
listed = {f["path"] for p in load_projects(root / out_dir / "projects.yaml") for f in p["files"]}
globs = [t for t in listed if "*" in t]

files = repo_files(root, out_dir, a.untracked, a.all_files)

missing = [f for f in files if f not in listed and not any(fnmatch.fnmatch(f, g) for g in globs)]
stale = sorted(
    t for t in listed
    if "*" not in t and not (root / t).exists() and not (root / t).is_symlink()
)
non_code = [] if a.all_files else sorted(
    t for t in listed if "*" not in t and (root / t).is_file() and not is_code(root, t)
)

print(f"{len(files)} files, {len(missing)} unrepresented")
for f in missing:
    print(f"  MISSING  {f}")
for t in stale:
    print(f"  STALE?   {t}")
for t in non_code:
    print(f"  NOT CODE {t}")
sys.exit(1 if missing or non_code else 0)

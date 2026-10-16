#!/usr/bin/env python3
"""Check OUT_DIR/projects.yaml covers every repo file, and lists no stale paths.

Usage: coverage.py [OUT_DIR=.puffins]   (run inside the repo)
A listed `dir/*` (or `dir/*.ext`) covers everything matching under it. OUT_DIR is never listed.
Adds OUT_DIR/ to the repo .gitignore if missing.
Exit 1 if any file is unrepresented.
"""
import fnmatch
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import ensure_gitignored, load_projects, repo_root  # noqa: E402

out_dir = (sys.argv[1] if len(sys.argv) > 1 else ".puffins").strip("/")
root = repo_root()
ensure_gitignored(root, out_dir)
listed = {f["path"] for p in load_projects(root / out_dir / "projects.yaml") for f in p["files"]}
globs = [t for t in listed if "*" in t]

files = subprocess.run(
    ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
    cwd=root, capture_output=True, text=True, check=True,
).stdout.split()

missing = [
    f for f in files
    if not f.startswith(out_dir + "/")
    and f not in listed and not any(fnmatch.fnmatch(f, g) for g in globs)
]
stale = sorted(
    t for t in listed
    if "*" not in t and not (root / t).exists() and not (root / t).is_symlink()
)

print(f"{len(files)} files, {len(missing)} unrepresented")
for f in missing:
    print(f"  MISSING {f}")
for t in stale:
    print(f"  STALE?  {t}")
sys.exit(1 if missing else 0)

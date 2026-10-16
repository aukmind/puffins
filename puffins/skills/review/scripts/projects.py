#!/usr/bin/env python3
"""Turn OUT_DIR/projects.yaml into review work items: [{"name", "out", "description", "files"}].

Usage: projects.py [--out-dir .puffins] [--project NAME ...] [--skip-existing] [--archive-fixes]   (run inside the repo)
`out` is relative to the repo root: <out-dir>/<a>/<b>/<c>.review.yaml for `a:b:c`.
--project        keeps only NAME and the projects under it (`app` matches `app:ui`),
                 repeatable or comma-separated.
--skip-existing  drops projects whose review yaml already validates.
--archive-fixes  for each selected project that already has a review, moves its
                 fix-*.yaml rows to fix-archive.yaml: a re-review renumbers the
                 findings, so old chats/statuses would attach to the wrong ones.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import dump_row, ensure_gitignored, load_projects, load_row, out_path, repo_root  # noqa: E402
from validate import validate_file  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--out-dir", default=".puffins")
ap.add_argument("--project", action="append", default=[])
ap.add_argument("--skip-existing", action="store_true")
ap.add_argument("--archive-fixes", action="store_true")
a = ap.parse_args()
if Path(a.out_dir).is_absolute() or ".." in Path(a.out_dir).parts:
    sys.exit("--out-dir must be relative to the repo root, inside it")

root = repo_root()
ensure_gitignored(root, a.out_dir)
projects = load_projects(root / a.out_dir / "projects.yaml")
wanted = [w.strip().strip(":") for arg in a.project for w in arg.split(",") if w.strip()]
if wanted:
    def under(name, w):
        return name == w or name.startswith(w + ":")
    unknown = [w for w in wanted if not any(under(p["name"], w) for p in projects)]
    if unknown:
        sys.exit(f"no project matches {', '.join(unknown)}; known: " + ", ".join(p["name"] for p in projects))
    projects = [p for p in projects if any(under(p["name"], w) for w in wanted)]

items = []
for p in projects:
    out = out_path(a.out_dir, p["name"])
    if a.skip_existing and (root / out).exists() and not validate_file(root / out):
        continue
    items.append({**p, "out": out})

if a.archive_fixes:
    out_root = root / a.out_dir
    redo = {i["name"] for i in items if (root / i["out"]).exists()}
    moved = 0
    for name in ("queue", "status", "chat", "agents"):
        f = out_root / f"fix-{name}.yaml"
        if not f.exists():
            continue
        keep, archive = [], []
        for line in f.read_text().splitlines(True):
            try:
                row = load_row(line)
                project = row["key"].rsplit("#", 1)[0]
            except (ValueError, KeyError, TypeError, AttributeError):
                keep.append(line)
                continue
            if project in redo:
                archive.append(row)
            else:
                keep.append(line)
        if archive:
            with open(out_root / "fix-archive.yaml", "a") as fa:
                fa.writelines(dump_row({"from": name, "row": r}) for r in archive)
            f.write_text("".join(keep))
            moved += len(archive)
    print(f"archived {moved} fix rows for {len(redo)} re-reviewed projects", file=sys.stderr)

json.dump(items, sys.stdout)
print(f"\n{len(items)} projects", file=sys.stderr)

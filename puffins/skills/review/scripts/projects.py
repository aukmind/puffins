#!/usr/bin/env python3
"""Turn OUT_DIR/projects.yaml into review work items: [{"name", "out", "description", "files"}].

Usage: projects.py [--out-dir .puffins] [--project NAME ...] [--skip-existing | --changed] [--archive-fixes]   (run inside the repo)
`out` is relative to the repo root: <out-dir>/<a>/<b>/<c>.review.yaml for `a:b:c`.
--project        keeps only NAME and the projects under it (`app` matches `app:ui`),
                 repeatable or comma-separated.
--skip-existing  drops projects whose review yaml already validates.
--changed        like --skip-existing, but keeps reviewed projects whose files changed
                 since their review, with `since` (that commit) so the reviewer focuses
                 on the diff.
Each item carries `head` (the commit it is reviewed at) and, when a review exists,
`history`: what was found before and what became of it (fixed, skipped, decided),
so a re-review does not report it again.
--archive-fixes  for each selected project that already has a review, moves its
                 fix-*.yaml rows to fix-archive.yaml: a re-review renumbers the
                 findings, so old chats/statuses would attach to the wrong ones.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import yaml  # noqa: E402
from common import (changed_since, dump_row, ensure_gitignored, head_sha, in_scope, load_projects,  # noqa: E402
                    load_row, out_path, read_rows, repo_root, review_base)
from validate import validate_file  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--out-dir", default=".puffins")
ap.add_argument("--project", action="append", default=[])
ap.add_argument("--skip-existing", action="store_true")
ap.add_argument("--changed", action="store_true")
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

out_root = root / a.out_dir
head = head_sha(root)
status = {}
for r in read_rows(out_root / "fix-status.yaml"):
    status[r.get("key")] = r
decisions = read_rows(out_root / "decisions.yaml")


def history(name, doc):
    """One line per earlier finding and its outcome, plus recorded decisions."""
    lines = []
    for f in (doc or {}).get("findings") or []:
        row = status.get(f"{name}#{f.get('id')}") or {}
        outcome = row.get("status") or "open"
        note = f": {row['note']}" if row.get("note") else ""
        lines.append(f"[{f.get('severity')}] {f.get('title')} ({f.get('location', f.get('file', ''))}) -> {outcome}{note}")
    for d in decisions:
        if d.get("project") == name or str(d.get("key", "")).rsplit("#", 1)[0] == name:
            lines.append(f"DECIDED: {d.get('title') or d.get('key')}: {d.get('decision')}")
    return lines


items = []
for p in projects:
    out = out_path(a.out_dir, p["name"])
    item = {**p, "out": out, "head": head}
    review = root / out
    if review.exists() and not validate_file(review):
        doc = yaml.safe_load(review.read_text()) or {}
        if a.changed:
            base = review_base(root, review, doc)
            touched = base and [f for f in changed_since(root, base) if in_scope(p["files"], f)]
            if not touched:
                continue
            item["since"] = base
        elif a.skip_existing:
            continue
        item["history"] = history(p["name"], doc)
    items.append(item)

if a.archive_fixes:
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

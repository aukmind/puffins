#!/usr/bin/env python3
"""Plan the `fix` verb: list open findings in file clusters, then check OUT_DIR/plan.yaml.

Usage: fix_plan.py list OUT_DIR [--project NAME ...]
         one line per open finding, in clusters of findings that share a file
       fix_plan.py check OUT_DIR [--project NAME ...]
         validates plan.yaml, prints its groups as JSON for fix-workflow.js
Open: no fix status yet, or last status `failed`. Run inside the repo.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import read_rows, repo_root  # noqa: E402

GROUP = re.compile(r"^[\w.-]+$")

ap = argparse.ArgumentParser()
ap.add_argument("cmd", choices=["list", "check"])
ap.add_argument("out_dir")
ap.add_argument("--project", action="append", default=[])
a = ap.parse_args()

root = repo_root()
out = Path(a.out_dir).resolve()
wanted = [w.strip().strip(":") for arg in a.project for w in arg.split(",") if w.strip()]


def selected(name):
    return not wanted or any(name == w or name.startswith(w + ":") for w in wanted)


last = {}
for r in read_rows(out / "fix-status.yaml"):
    last[r.get("key")] = r.get("status")

findings = {}
for p in sorted(out.rglob("*.review.yaml")):
    try:
        doc = yaml.safe_load(p.read_text()) or {}
    except yaml.YAMLError:
        continue
    project = doc.get("project")
    if not isinstance(project, str) or not selected(project):
        continue
    for f in doc.get("findings") or []:
        key = f"{project}#{f.get('id')}"
        if last.get(key) not in (None, "failed"):
            continue
        file = f.get("file") or str(f.get("location", "")).split(":")[0].strip()
        findings[key] = {**f, "key": key, "file": file, "review": os.path.relpath(p, root)}

if a.cmd == "list":
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for k, f in findings.items():
        if f["file"]:
            parent[find(k)] = find("file:" + f["file"])
    clusters = {}
    for k in findings:
        clusters.setdefault(find(k), []).append(findings[k])
    for i, fs in enumerate(sorted(clusters.values(), key=lambda fs: (-len(fs), fs[0]["file"])), 1):
        print(f"cluster {i}: {', '.join(sorted({f['file'] for f in fs if f['file']})) or '(no file)'}")
        for f in fs:
            loc = f"{f['file']}:{f['line']}" if f.get("line") else f["file"]
            print(f"  {f['key']} [{f.get('severity')}] {loc} {f.get('title')}")
    print(f"{len(findings)} open findings in {len(clusters)} clusters", file=sys.stderr)
    sys.exit(0)

try:
    plan = yaml.safe_load((out / "plan.yaml").read_text()) or {}
except FileNotFoundError:
    sys.exit(f"{out}/plan.yaml: not found")
except yaml.YAMLError as e:
    sys.exit(f"{out}/plan.yaml: unparseable: {e}")

errs, seen, owner, groups = [], {}, {}, []
for i, g in enumerate(plan.get("groups") or []):
    name = g.get("name") if isinstance(g, dict) else None
    if not isinstance(name, str) or not GROUP.match(name):
        errs.append(f"groups[{i}]: bad or missing `name` {name!r}")
        continue
    files = [str(x) for x in g.get("files") or []]
    keys = [str(x) for x in g.get("findings") or []]
    dups = {str(k): str(v) for k, v in (g.get("duplicates") or {}).items()}
    if not keys:
        errs.append(f"{name}: no `findings`")
    for k in keys + list(dups):
        if k not in findings:
            errs.append(f"{name}: {k} is not an open finding")
        elif k in seen:
            errs.append(f"{k}: in both {seen[k]} and {name}")
        else:
            seen[k] = name
            if findings[k]["file"] and findings[k]["file"] not in files:
                errs.append(f"{name}: `files` misses {findings[k]['file']} ({k})")
    for k, v in dups.items():
        if v not in keys:
            errs.append(f"{name}: duplicate {k} points to {v}, not one of this group's `findings`")
    for f in files:
        if f in owner:
            errs.append(f"{f}: in both {owner[f]} and {name}, merge them")
        owner.setdefault(f, name)
    groups.append({
        "name": name,
        "summary": g.get("summary", ""),
        "files": files,
        "findings": [{"key": k, "review": findings[k]["review"]} for k in keys if k in findings],
        "duplicates": [{"key": k, "of": v, "review": findings[k]["review"]} for k, v in dups.items() if k in findings],
    })
errs += [f"{k}: open but in no group" for k in findings if k not in seen]
if errs:
    sys.exit("plan.yaml:\n  " + "\n  ".join(errs))
json.dump(groups, sys.stdout)
print(f"\n{len(groups)} groups, {len(findings)} findings", file=sys.stderr)

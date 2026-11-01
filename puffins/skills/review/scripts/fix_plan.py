#!/usr/bin/env python3
"""Plan the `fix` verb: list open findings in file clusters, then check OUT_DIR/plan.yaml.

Usage: fix_plan.py list OUT_DIR [--project NAME ...] [--severity S]
         one line per open finding, in clusters of findings that share a file
       fix_plan.py auto OUT_DIR [--project NAME ...] [--severity S]
         writes a default plan.yaml: clusters sharing a file or a project form one group
       fix_plan.py count OUT_DIR [--project NAME ...] [--severity S]
         prints the number of open findings
       fix_plan.py check OUT_DIR [--project NAME ...] [--severity S]
         validates plan.yaml, prints its groups as JSON for fix-workflow.js
Open: no fix status yet, or last status `failed`, and at least --severity (default low). Run inside the repo.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import at_least, read_rows, repo_root, severity_floor  # noqa: E402

GROUP = re.compile(r"^[\w.-]+$")

ap = argparse.ArgumentParser()
ap.add_argument("cmd", choices=["list", "auto", "count", "check"])
ap.add_argument("out_dir")
ap.add_argument("--project", action="append", default=[])
ap.add_argument("--severity", default="low")
a = ap.parse_args()
floor = severity_floor(a.severity)

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
        if last.get(key) not in (None, "failed") or not at_least(f.get("severity"), floor):
            continue
        file = f.get("file") or str(f.get("location", "")).split(":")[0].strip()
        findings[key] = {**f, "key": key, "file": file, "review": os.path.relpath(p, root)}

if a.cmd == "count":
    print(len(findings))
    sys.exit(0)

parent = {}


def find(x):
    while parent.setdefault(x, x) != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def clusters_by(*links):
    for k, f in findings.items():
        for link in links:
            if link(f):
                parent[find(k)] = find(link(f))
    out = {}
    for k in findings:
        out.setdefault(find(k), []).append(findings[k])
    return sorted(out.values(), key=lambda fs: (-len(fs), fs[0]["file"]))


if a.cmd == "auto":
    groups = []
    for fs in clusters_by(lambda f: f["file"] and "file:" + f["file"], lambda f: "project:" + f["key"].rsplit("#", 1)[0]):
        projects = sorted({f["key"].rsplit("#", 1)[0] for f in fs})
        groups.append({
            "name": "-".join(p.replace(":", "-") for p in projects)[:60],
            "summary": "Fix review findings in " + ", ".join(projects),
            "files": sorted({f["file"] for f in fs if f["file"]}),
            "findings": [f["key"] for f in fs],
        })
    (out / "plan.yaml").write_text(yaml.safe_dump({"groups": groups}, sort_keys=False, width=200))
    print(f"wrote {out / 'plan.yaml'}: {len(groups)} groups, {len(findings)} findings", file=sys.stderr)
    sys.exit(0)

if a.cmd == "list":
    clusters = clusters_by(lambda f: f["file"] and "file:" + f["file"])
    for i, fs in enumerate(clusters, 1):
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

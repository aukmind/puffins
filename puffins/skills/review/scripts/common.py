"""Shared helpers: OUT_DIR/projects.yaml and the append-only fix-*.yaml logs.

A log row is one `- {json}` line: JSON is valid YAML flow, so the file stays a YAML
list while each append stays a single atomic line.
"""
import json
import re
import subprocess
from pathlib import Path

import yaml

NAME = re.compile(r"^[\w.-]+(:[\w.-]+)*$")


def dump_row(row):
    return "- " + json.dumps(row) + "\n"


def load_row(line):
    line = line.strip()
    return json.loads(line[2:] if line.startswith("- ") else line)


def read_rows(path):
    try:
        lines = Path(path).read_text().splitlines()
    except FileNotFoundError:
        return []
    rows = []
    for line in lines:
        try:
            rows.append(load_row(line))
        except ValueError:
            continue
    return rows


def repo_root():
    return Path(subprocess.run(["git", "rev-parse", "--show-toplevel"],
                               capture_output=True, text=True, check=True).stdout.strip())


def ensure_gitignored(root, out_dir):
    """Append `<out_dir>/` to the repo's .gitignore if missing. Never staged or committed."""
    entry = out_dir.strip("/") + "/"
    gi = Path(root) / ".gitignore"
    text = gi.read_text() if gi.exists() else ""
    if entry in {line.strip() for line in text.splitlines()}:
        return
    gi.write_text(text + ("\n" if text and not text.endswith("\n") else "") + entry + "\n")


def out_path(out_dir, name):
    return f"{out_dir.strip('/')}/{'/'.join(name.split(':'))}.review.yaml"


def load_projects(path):
    """[{name, description, files: [{path, region?}]}], or SystemExit naming every problem."""
    try:
        doc = yaml.safe_load(Path(path).read_text())
    except FileNotFoundError:
        raise SystemExit(f"{path}: not found, run `list` first")
    except yaml.YAMLError as e:
        raise SystemExit(f"{path}: unparseable: {e}")
    items = (doc or {}).get("projects") if isinstance(doc, dict) else None
    if not isinstance(items, list):
        raise SystemExit(f"{path}: top level must be `projects:` with a list")
    errs, seen, out = [], set(), []
    for i, p in enumerate(items):
        name = p.get("name") if isinstance(p, dict) else None
        if not isinstance(name, str) or not NAME.match(name):
            errs.append(f"projects[{i}]: bad or missing `name` {name!r}")
            continue
        if name in seen:
            errs.append(f"{name}: duplicate name")
        seen.add(name)
        files = []
        for j, f in enumerate(p.get("files") or []):
            if isinstance(f, str):
                files.append({"path": f})
            elif isinstance(f, dict) and isinstance(f.get("path"), str):
                files.append({k: f[k] for k in ("path", "region") if f.get(k)})
            else:
                errs.append(f"{name}: files[{j}] must be a path or {{path, region}}")
        if not files:
            errs.append(f"{name}: no `files`")
        out.append({"name": name, "description": p.get("description", ""), "files": files})
    if errs:
        raise SystemExit(f"{path}:\n  " + "\n  ".join(errs))
    return out


def project_info(doc, out_dir):
    """(description, files) of a review doc, falling back to projects.yaml for reviews written before they were stamped in."""
    if doc.get("files"):
        return doc.get("description", ""), doc["files"]
    p = next((p for p in load_projects(Path(out_dir) / "projects.yaml") if p["name"] == doc.get("project")), {})
    return p.get("description", ""), p.get("files", [])

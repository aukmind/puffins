"""Shared helpers: OUT_DIR/projects.yaml and the append-only fix-*.yaml logs.

A log row is one `- {json}` line: JSON is valid YAML flow, so the file stays a YAML
list while each append stays a single atomic line.
"""
import fnmatch
import json
import os
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


NON_CODE_EXT = {
    # images, media, fonts
    "png", "jpg", "jpeg", "gif", "bmp", "ico", "icns", "svg", "webp", "tif", "tiff", "psd", "xcf", "heic",
    "mp3", "wav", "ogg", "flac", "m4a", "mp4", "mov", "avi", "mkv", "webm",
    "ttf", "otf", "woff", "woff2", "eot",
    # archives, binaries, documents
    "zip", "tar", "gz", "tgz", "bz2", "xz", "7z", "rar", "jar", "war", "aar", "apk", "ipa", "deb", "rpm", "dmg", "iso",
    "exe", "dll", "so", "dylib", "a", "o", "obj", "lib", "bin", "class", "pyc", "pyo", "wasm",
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "odp",
    # logs, data, models
    "log", "csv", "tsv", "parquet", "feather", "arrow", "avro", "sqlite", "sqlite3", "db", "pcap", "pcapng",
    "bag", "mcap", "db3", "npy", "npz", "pkl", "pickle", "h5", "hdf5", "onnx", "pt", "pth", "ckpt",
    "safetensors", "tflite", "pb", "stl", "fbx", "glb", "gltf", "blend", "ply", "pcd", "dae",
    # generated
    "map", "lock", "sum",
}
NON_CODE_NAMES = {
    "package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "LICENSE", "LICENSE.txt", "LICENSE.md",
    "COPYING", "NOTICE", ".DS_Store",
}
NON_CODE_SUFFIXES = (".min.js", ".min.css")
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".dart_tool", ".gradle", ".idea",
             "build", "dist", "target", ".next", ".cache", ".tox", ".mypy_cache", ".pytest_cache"}


def git_root():
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return Path(r.stdout.strip()) if r.returncode == 0 else None


def repo_root():
    """The git root, or the current dir when there is no repo."""
    return git_root() or Path.cwd()


def is_code(root, path):
    """Source, config and other reviewable text: no media, binaries, logs, data, lockfiles or licenses."""
    name = path.rsplit("/", 1)[-1]
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext in NON_CODE_EXT or name in NON_CODE_NAMES or name.endswith(NON_CODE_SUFFIXES) or ".log." in name:
        return False
    try:
        with open(Path(root) / path, "rb") as f:
            return b"\0" not in f.read(8192)
    except OSError:
        return True


def repo_files(root, out_dir, untracked=False, all_files=False):
    """Files to review: git-tracked (plus untracked if asked, or every file outside SKIP_DIRS without git), code only unless all_files."""
    out_dir = out_dir.strip("/")
    if git_root():
        cmd = ["git", "ls-files", "--cached"] + (["--others", "--exclude-standard"] if untracked else [])
        files = subprocess.run(cmd, cwd=root, capture_output=True, text=True, check=True).stdout.splitlines()
    else:
        files = []
        for d, dirs, names in os.walk(root):
            dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS)
            rel = Path(d).relative_to(root)
            files += [(rel / n).as_posix() for n in sorted(names)]
    return [
        f for f in files
        if not f.startswith(out_dir + "/") and (all_files or is_code(root, f))
    ]


def ensure_gitignored(root, out_dir):
    """Append `<out_dir>/` to the repo's .gitignore if missing. Never staged or committed. No-op outside git."""
    if not git_root():
        return
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


SEVERITIES = ("critical", "high", "medium", "low", "nit")


def severity_floor(value):
    """Validated --severity value: the lowest severity still reported."""
    if value not in SEVERITIES:
        raise SystemExit(f"--severity must be one of {', '.join(SEVERITIES)}, not {value!r}")
    return value


def at_least(severity, floor):
    """True when `severity` is `floor` or worse. Unknown severities pass, so validation can name them."""
    if severity not in SEVERITIES or floor not in SEVERITIES:
        return True
    return SEVERITIES.index(severity) <= SEVERITIES.index(floor)


def git(root, *args):
    r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def head_sha(root):
    return git(root, "rev-parse", "HEAD") if git_root() else None


def review_base(root, review_path, doc):
    """Commit a review was made at: its `reviewed_at`, else the last commit before the file was written."""
    sha = doc.get("reviewed_at")
    if sha and git(root, "cat-file", "-e", f"{sha}^{{commit}}") is not None:
        return sha
    mtime = int(Path(review_path).stat().st_mtime)
    return git(root, "rev-list", "-1", f"--before={mtime}", "HEAD") or None


def changed_since(root, base):
    """Paths changed between `base` and the working tree."""
    out = git(root, "diff", "--name-only", base)
    return set(out.splitlines()) if out else set()


def in_scope(files, path):
    """Whether `path` falls under a project's files (paths or globs)."""
    return any(path == f["path"] or fnmatch.fnmatchcase(path, f["path"]) for f in files)

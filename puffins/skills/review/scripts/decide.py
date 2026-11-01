#!/usr/bin/env python3
"""Record a decision so later reviews stop reporting it.

Usage: decide.py OUT_DIR KEY_OR_PROJECT "decision"
  KEY_OR_PROJECT: a finding key (<project>#<id>) or a project name.
Appends to OUT_DIR/decisions.yaml; projects.py hands it to the project's next review.
"""
import os
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import dump_row, out_path  # noqa: E402

if len(sys.argv) != 4:
    sys.exit(__doc__)
out, target, decision = sys.argv[1:4]
project, _, fid = target.partition("#")
title = ""
if fid:
    review = Path(out).parent / out_path(Path(out).name, project)
    try:
        doc = yaml.safe_load(review.read_text()) or {}
        title = next((f.get("title", "") for f in doc.get("findings") or [] if str(f.get("id")) == fid), "")
    except (OSError, yaml.YAMLError):
        pass
row = {"key": target if fid else None, "project": project, "title": title, "decision": decision, "ts": time.time()}
with open(Path(out) / "decisions.yaml", "a") as f:
    f.write(dump_row(row))
print(f"recorded for {project}: {title or target}")

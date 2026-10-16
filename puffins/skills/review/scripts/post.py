#!/usr/bin/env python3
"""Claude's side of a finding's thread in the viewer.

Usage: post.py OUT_DIR KEY [--status S] [--note N] [--say TEXT] [--option "Label::description"]... [--agent ID]
  --status  working | needs-input | fixed | skipped | failed   (fix-status.yaml)
  --say     a chat message shown under the finding (fix-chat.yaml); markdown-ish, newlines kept
  --option  answer buttons for --say; the first one is shown as recommended
  --agent   record the subagent id handling KEY (fix-agents.yaml), so replies resume it
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import dump_row  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("out_dir")
ap.add_argument("key")
ap.add_argument("--status", choices=["working", "needs-input", "fixed", "skipped", "failed"])
ap.add_argument("--note", default="")
ap.add_argument("--say")
ap.add_argument("--option", action="append", default=[])
ap.add_argument("--agent")
a = ap.parse_args()


def append(name, row):
    with open(os.path.join(a.out_dir, f"fix-{name}.yaml"), "a") as f:
        f.write(dump_row(row))


now = time.time()
if a.say:
    msg = {"key": a.key, "from": "claude", "text": a.say, "ts": now}
    if a.option:
        msg["options"] = [dict(zip(("label", "description"), (o.split("::", 1) + [""])[:2])) for o in a.option]
    append("chat", msg)
if a.status:
    append("status", {"key": a.key, "status": a.status, "note": a.note, "ts": now})
if a.agent:
    append("agents", {"key": a.key, "agent": a.agent, "ts": now})

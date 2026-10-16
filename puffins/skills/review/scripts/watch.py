#!/usr/bin/env python3
"""Fix listener for the Monitor tool: one stdout line per thing to act on.

Usage: watch.py OUT_DIR
  FIX <mode> <key> <review yaml> [agent]   a finding was sent; mode = autofix | propose | instruct;
                                           agent = the project's last fix agent, if any
  REPLY <key> <json-encoded text>  the user answered in the finding's chat
Every emitted event is logged to OUT_DIR/.watch-emitted.yaml, so a re-armed
watcher only replays what no listener has seen yet.
Touches OUT_DIR/.listener every second so the viewer can show "Claude listening".
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import dump_row, load_row  # noqa: E402

out = os.path.abspath(sys.argv[1])
paths = {n: os.path.join(out, f"fix-{n}.yaml") for n in ("queue", "chat")}
heartbeat = os.path.join(out, ".listener")
emitted_log = os.path.join(out, ".watch-emitted.yaml")
KEY = re.compile(r"^[\w.:-]+#\d+$")
MODES = {"autofix", "propose", "instruct"}


def parse(data):
    rows = []
    for line in data.decode(errors="replace").splitlines():
        try:
            row = load_row(line)
        except ValueError:
            continue
        if isinstance(row, dict) and KEY.match(str(row.get("key", ""))):
            rows.append(row)
    return rows


def read_all(path):
    try:
        with open(path, "rb") as f:
            data = f.read()
    except FileNotFoundError:
        return [], 0
    data = data[: data.rfind(b"\n") + 1]
    return parse(data), len(data)


def tail(name, offset):
    try:
        with open(paths[name], "rb") as f:
            # File was rewritten shorter: resume at its end rather than mid-line.
            offset = min(offset, os.fstat(f.fileno()).st_size)
            f.seek(offset)
            chunk = f.read()
    except FileNotFoundError:
        return [], offset
    # Leave a half-written last line for the next poll.
    chunk = chunk[: chunk.rfind(b"\n") + 1]
    return parse(chunk), offset + len(chunk)


# First run on existing data: treat what already got a status / Claude reply as seen.
if not os.path.exists(emitted_log):
    status = read_all(os.path.join(out, "fix-status.yaml"))[0]
    chat = read_all(paths["chat"])[0]
    last = {}
    for r in status + [m for m in chat if m.get("from") == "claude"]:
        last[r["key"]] = max(last.get(r["key"], 0), r.get("ts") or 0)
    done = [r for r in read_all(paths["queue"])[0] + [m for m in chat if m.get("from") == "user"]
            if (r.get("ts") or 0) <= last.get(r["key"], -1)]
    with open(emitted_log, "w") as f:
        f.writelines(dump_row({"key": r["key"], "ts": r.get("ts")}) for r in done)

seen = {(e["key"], e.get("ts")) for e in read_all(emitted_log)[0]}


def emit(row, line):
    ident = (row["key"], row.get("ts"))
    if ident in seen:
        return
    seen.add(ident)
    with open(emitted_log, "a") as f:
        f.write(dump_row({"key": row["key"], "ts": row.get("ts")}))
    print(line, flush=True)


def project_agent(key):
    project = key.rsplit("#", 1)[0]
    rows = [r for r in read_all(os.path.join(out, "fix-agents.yaml"))[0] if r["key"].rsplit("#", 1)[0] == project]
    return rows[-1]["agent"] if rows else ""


def handle(name, row):
    if name == "queue":
        mode = row.get("mode", "autofix")
        path = os.path.normpath(os.path.join(out, str(row.get("path", ""))))
        if mode in MODES and path.startswith(out + os.sep) and path.endswith(".review.yaml"):
            emit(row, " ".join(filter(None, ["FIX", mode, row["key"], path, project_agent(row["key"])])))
    elif row.get("from") == "user":
        emit(row, f"REPLY {row['key']} {json.dumps(str(row.get('text', '')))}")


offsets = {}
for name in paths:
    rows, offsets[name] = read_all(paths[name])
    for row in rows:
        handle(name, row)

while True:
    with open(heartbeat, "w"):
        pass
    for name in paths:
        rows, offsets[name] = tail(name, offsets[name])
        for row in rows:
            handle(name, row)
    time.sleep(1)

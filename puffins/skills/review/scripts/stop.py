#!/usr/bin/env python3
"""Stop the viewer server and fix listener serving OUT_DIR (any session started them).

Usage: stop.py OUT_DIR
Killing watch.py also ends the Monitor that wraps it.
"""
import os
import signal
import sys

out = os.path.abspath(sys.argv[1])
targets = {"assets/serve.py", "scripts/watch.py"}
killed = []
for pid in filter(str.isdigit, os.listdir("/proc")):
    try:
        argv = open(f"/proc/{pid}/cmdline", "rb").read().decode().split("\0")
    except OSError:
        continue
    script = next((a for a in argv if any(a.endswith("skills/review/" + t) for t in targets)), None)
    if not script or int(pid) == os.getpid():
        continue
    # Match this OUT_DIR only, so other repos' viewers keep running.
    rest = argv[argv.index(script) + 1:]
    if not rest or os.path.abspath(rest[0]) != out:
        continue
    try:
        os.kill(int(pid), signal.SIGTERM)
        killed.append(f"{pid} {os.path.basename(script)}")
    except ProcessLookupError:
        pass

try:
    os.remove(os.path.join(out, ".listener"))
except FileNotFoundError:
    pass
print("stopped: " + (", ".join(killed) if killed else "nothing was running"))

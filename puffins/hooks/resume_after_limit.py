#!/usr/bin/env python3
"""StopFailure (rate_limit) hook: resume a headless (`claude -p`) session right after the usage limit resets.

Interactive sessions are left alone: Claude Code's own wait-for-reset (`autoContinueAtUsageLimit`)
continues them in place, and a second `-p` run would only spend tokens re-reading the conversation.

Reads the hook JSON on stdin, finds the reset time in the error text or the transcript
("resets 5:50pm (Europe/Brussels)", "resets Nov 1, 10:50pm"), then detaches a waiter that runs
`claude --resume <session> -p "<prompt>"` two minutes after the reset, in the same permission
mode. If the session was already continued (the transcript changed after the reset, e.g. by
the built-in auto-continue), the waiter does nothing. Log: $CLAUDE_PLUGIN_DATA/resume.log.

Off by default. `resume_after_limit.py --set on|off|status` flips it (the /puffin:autoresume skill);
the switch lives in $CLAUDE_CONFIG_DIR (or ~/.claude)/puffin/autoresume.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

GRACE = 120
FALLBACK = 3600
PROMPT = ("The usage limit has reset. Continue the task you were doing before it was hit. "
          "Resume any workflow or subagent that failed on the limit, with the same arguments.")
RESET = re.compile(
    r"resets\s+(?:(?P<mon>[A-Z][a-z]{2})\s+(?P<day>\d{1,2}),?\s+)?(?:at\s+)?"
    r"(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ap>[ap]m)(?:\s*\((?P<tz>[^)]+)\))?",
    re.I,
)
MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
CONFIG = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "puffin"
SWITCH = CONFIG / "autoresume"
DATA = Path(os.environ.get("CLAUDE_PLUGIN_DATA") or CONFIG)


def enabled():
    try:
        return SWITCH.read_text().strip() == "on"
    except OSError:
        return False


def set_switch(value):
    if value in ("on", "off"):
        CONFIG.mkdir(parents=True, exist_ok=True)
        SWITCH.write_text(value + "\n")
    print(f"puffin autoresume: {'on' if enabled() else 'off'} ({SWITCH})")


def log(msg):
    DATA.mkdir(parents=True, exist_ok=True)
    with open(DATA / "resume.log", "a") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")


def reset_epoch(text, now):
    """Epoch of the latest 'resets ...' mention in text, or None."""
    matches = list(RESET.finditer(text or ""))
    if not matches:
        return None
    m = matches[-1]
    tz = None
    if m["tz"] and ZoneInfo:
        try:
            tz = ZoneInfo(m["tz"].strip())
        except Exception:
            tz = None
    base = datetime.fromtimestamp(now, tz) if tz else datetime.fromtimestamp(now)
    hour = int(m["h"]) % 12 + (12 if m["ap"].lower() == "pm" else 0)
    at = base.replace(hour=hour, minute=int(m["m"] or 0), second=0, microsecond=0)
    if m["mon"] and m["mon"].lower() in MONTHS:
        at = at.replace(month=MONTHS.index(m["mon"].lower()) + 1, day=int(m["day"]))
        if at.timestamp() < now - 86400:
            at = at.replace(year=at.year + 1)
    elif at.timestamp() <= now:
        at += timedelta(days=1)
    return at.timestamp()


def transcript_tail(path, lines=200):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 200_000))
            return b"\n".join(f.read().splitlines()[-lines:]).decode("utf-8", "replace")
    except OSError:
        return ""


def wait_and_resume(sid, cwd, mode, transcript, at):
    time.sleep(max(0, at - time.time()))
    try:
        if transcript and os.path.getmtime(transcript) > at - GRACE:
            log(f"{sid}: already continued after the reset, nothing to do")
            return
    except OSError:
        pass
    claude = shutil.which("claude") or "claude"
    cmd = [claude, "--resume", sid, "-p", PROMPT]
    if mode and mode != "default":
        cmd[1:1] = ["--permission-mode", mode]
    log(f"{sid}: resuming in {cwd}: {' '.join(cmd[:-1])} <prompt>")
    with open(DATA / f"resume-{sid}.out", "a") as out:
        r = subprocess.run(cmd, cwd=cwd or None, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    log(f"{sid}: resume exited {r.returncode}")


def headless():
    """True when the Claude Code process running this hook was started with -p/--print."""
    pid = os.getppid()
    for _ in range(4):
        try:
            args = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
            stat = Path(f"/proc/{pid}/stat").read_text()
        except OSError:
            return False
        if any(os.path.basename(a) == b"claude" for a in args[:2]):
            return any(a in (b"-p", b"--print") for a in args)
        pid = int(stat.rsplit(")", 1)[1].split()[1])
    return False


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--set":
        if sys.argv[2] not in ("on", "off", "status"):
            sys.exit("usage: resume_after_limit.py --set on|off|status")
        set_switch(sys.argv[2])
        return
    if len(sys.argv) == 7 and sys.argv[1] == "--wait":
        _, _, sid, cwd, mode, transcript, at = sys.argv
        wait_and_resume(sid, cwd, mode, transcript, float(at))
        return
    data = json.load(sys.stdin)
    if data.get("error") not in (None, "rate_limit"):
        return
    sid = data.get("session_id")
    if not sid or not enabled() or os.environ.get("PUFFIN_NO_RESUME"):
        return
    if not headless():
        log(f"{sid}: interactive, left to Claude Code's own wait-for-reset")
        return
    now = time.time()
    transcript = data.get("transcript_path") or ""
    text = "\n".join(str(data.get(k) or "") for k in ("last_assistant_message", "error_details"))
    at = reset_epoch(text, now) or reset_epoch(transcript_tail(transcript), now)
    at = (at + GRACE) if at and at > now else now + FALLBACK
    marker = DATA / f"pending-{sid}"
    DATA.mkdir(parents=True, exist_ok=True)
    if marker.exists() and abs(float(marker.read_text() or 0) - at) < GRACE:
        return
    marker.write_text(str(at))
    subprocess.Popen(
        [sys.executable, __file__, "--wait", sid, data.get("cwd") or os.getcwd(),
         data.get("permission_mode") or "", transcript, str(at)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    log(f"{sid}: limit hit, resume at {datetime.fromtimestamp(at).isoformat(timespec='minutes')}")


if __name__ == "__main__":
    main()

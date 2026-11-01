---
name: autoresume
argument-hint: "<on|off|status>"
description: Turn puffin's auto-resume after a usage limit on or off (off by default), or show its state. `/puffin:autoresume on|off|status`. When on, a headless `claude -p` session stopped by the 5-hour limit is resumed right after the reset.
---

# Puffin autoresume

Arguments: `on`, `off`, or `status` (none given: `status`). Run, with this skill's base directory as `B`:

    python3 B/../../hooks/resume_after_limit.py --set <on|off|status>

Then tell the user the state it printed, in one line, and what it means:

- on: when a headless `claude -p` run stops on the usage limit, the plugin's StopFailure hook resumes it (`claude --resume <session> -p`) two minutes after the reset, in the same permission mode. Interactive sessions are left to Claude Code's own wait-for-reset (`autoContinueAtUsageLimit`), so no extra session is started for them.
- off: nothing is scheduled; a stopped headless run stays stopped.

The log is `resume.log` in the plugin's data folder.

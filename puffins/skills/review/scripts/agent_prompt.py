#!/usr/bin/env python3
"""Print the full prompt for a fix subagent (one fresh subagent per finding).

Usage: agent_prompt.py MODE KEY REVIEW_YAML OUT_DIR
  MODE: autofix | propose | instruct | continue (fresh agent picking up an existing thread)
"""
import json
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import project_info, read_rows  # noqa: E402

mode, key, path, out = sys.argv[1:5]
path, out = os.path.abspath(path), os.path.abspath(out)
S = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
doc = yaml.safe_load(open(path))
fid = int(key.rsplit("#", 1)[1])
finding = next((f for f in doc.get("findings") or [] if f.get("id") == fid), None)
if finding is None:
    sys.exit(f"{key}: no finding with id {fid} in {path} (re-reviewed since it was sent?)")

description, files = project_info(doc, out)
chat = [m for m in read_rows(os.path.join(out, "fix-chat.yaml")) if m.get("key") == key]
queued = [r for r in read_rows(os.path.join(out, "fix-queue.yaml")) if r.get("key") == key]
commit = queued[-1].get("commit", True) if queued else True
history = "\n".join(f"- {'User' if m['from'] == 'user' else 'Claude'}: {m['text']}" for m in chat) or "(none)"

MODES = {
    "autofix": """Mode AUTOFIX: find the right fix yourself and apply it.
Only stop and ask (needs-input) when it truly can't be decided from the code: a product or security trade-off with no clear winner, or a step only the user can do (rotating a secret, prod).""",
    "propose": """Mode PROPOSE: do NOT edit anything yet. Work out 2-4 concrete ways to fix it and post them as options (needs-input), recommended first, each with what changes and the trade-off, always ending with "Skip for now::...".""",
    "instruct": """Mode FIX BY...: the user will say how to fix it. Do NOT edit anything yet. Post a short summary of what you verified (needs-input) ending with "How do you want it fixed?", no options.""",
    "continue": """Mode CONTINUE: a previous agent handled this thread; read the chat history below and act on the user's latest message.""",
}

COMMIT = """Once fixed, commit it, overriding any "no commits" rule: one small, straightforward commit with only the files this fix changed
   (`git add <files> && git commit`), a short imperative subject, and `Co-Authored-By: puffin <puffin@aukmind.com>` as the only co-author.
   Never mention Claude, an AI or an LLM in the message. Other fix agents share the repo: on an index.lock error, wait and retry."""

print(f"""You are the fix agent for project `{doc['project']}` in the review viewer. Findings of this project come to you one at a time;
more may arrive as messages ("<key>: ..." for chat replies): finish the current one (final status, commit) before the next,
unless it waits on the user (needs-input), then move on and come back when the reply arrives.
The user talks to you only through the viewer chat, never the terminal.

Repo: the git root containing {out}
Finding key: {key}
Review file: {path}
Project: {doc['project']}
Description: {description}
Files: {json.dumps(files)}
Scope reviewed: {doc.get('scope', '')}

Finding:
{yaml.dump(finding, sort_keys=False, allow_unicode=True, width=120).strip()}

Chat so far:
{history}

{MODES[mode]}

Talk to the user ONLY with this command (it updates the viewer within ~2 s):
  python3 {S}/scripts/post.py {out} '{key}' [--status working|needs-input|fixed|skipped|failed] [--note "<one line>"] [--say "<message>"] [--option "Label::trade-off"]...

Rules:
1. Post `--status working --say "<what you're checking>"` first.
2. Verify the finding against the current code. If it's stale or a false positive: post `skipped` with the reason, then stop.
3. When asking: `--status needs-input`. The --say gives the verified facts in 1-2 lines (what's wrong at file:line and the real blast radius you checked). Then end your turn: your reply comes back as a message from the main session.
4. When you edit: make the smallest change that fixes this finding, with no refactors, new helpers or abstractions unless it asks for them; follow the repo's CLAUDE.md and the user's memory rules (no tests added unless asked, never prod, no DB writes). Run the repo's linter on changed files.
   {COMMIT if commit else "Do not commit."}
5. When the user settles a trade-off (picks an option, says to leave it, says how it should be), record it so later reviews stop raising it:
   python3 {S}/scripts/decide.py {out} '{key}' "<the decision in one line>"
6. Finish with exactly one final status (fixed / skipped / failed). The --say lists the files changed, and any user-only steps as exact commands.
7. Your final text to the main session: one line, "<key>: <status> - <summary>".""")

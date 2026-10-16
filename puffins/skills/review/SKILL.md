---
name: review
description: Review the whole repo split into projects, one /code-review agent each, then fix the findings from a web viewer.
argument-hint: "<list|review|listen|stop> [low|medium|high|xhigh|max] [--agents N] [--project NAME]"
---

# Puffin review

Commands: `list` maps every file to a project in .puffins/projects.yaml, `review` reviews them in parallel, `listen` opens the viewer and runs each fix you click, `stop` shuts it down. No command: `listen` if reviews exist, else `review`. Run from the repo root, `S=${CLAUDE_SKILL_DIR}`.

Options:

- Effort `low|medium|high|xhigh|max`: passed to /code-review. None given: pass none, so /code-review uses its own level.
- `--max-findings <n|all|default>`: passed to /code-review, default `all`.
- `--agents N`: review agents in flight, default 24.
- `--project NAME`: review only that project and everything under it (`app` covers `app:ui:*`). Repeatable or comma-separated. Still skips finished reviews unless `review all`.
- `--out-dir`, default `.puffins/`. `--port`, default 8099.

The web app stays in `$S/assets`. `coverage.py` and `projects.py` add the output dir to the repo `.gitignore`; leave that change uncommitted. Everything in the output dir is YAML: `projects.yaml`, `*.review.yaml`, and the append-only `fix-*.yaml` logs (one `- {json}` row per line), plus the `.listener` heartbeat. Each `*.review.yaml` starts with its project's `description` and `files`, so review and fix agents never read `projects.yaml`. Finding key: `<project>#<id>`.

## list

Write `.puffins/projects.yaml`, or refresh it: add new files, drop deleted paths, fix drifted descriptions. Never rename a project; its name is its output path. Shape:

    projects:
      - name: <area>:<group>:<project>   # or <area>:<project>
        description: <1-3 sentences>
        files:
          - lib/main.dart
          - android/*                     # generated or huge folders
          - {path: crud.py, region: "get_devices*"}
          - {path: docker-compose.yml, region: service x}

- Group projects of one area together; the area is the name's first segment.
- `a:b:c` → `.puffins/a/b/c.review.yaml`.
- The output dir itself is never listed.

Loop until this exits 0, fixing any `STALE?` path:

    python3 $S/scripts/coverage.py .puffins

## review

1. No `.puffins/projects.yaml`: run `list` first.
2. Build the work list. `review all` drops `--skip-existing`. Pass each `--project` through as is. Tell the user how many fix-history rows were archived.

       python3 $S/scripts/projects.py --out-dir .puffins --skip-existing --archive-fixes

3. Launch (this skill is the Workflow opt-in). A workflow runs at most `min(16, CPUs-2)` agents, so with N = min(`--agents`, project count): `shards = ceil(N / cap)`, `workers = ceil(N / shards)`. Read `$S/assets/review-workflow.js` and pass its full text inline as `script`. Never use `scriptPath`: the skill dir is outside the project, so Workflow refuses it even after a Read. Send all shards in one message:

       Workflow({script: <review-workflow.js text>, args: {root, skillDir: S, outDir: ".puffins", projects, shard: i, shards, workers, effort, maxFindings}})

   `projects` is step 2's JSON array, as a real array. Omit `effort` if none given. Tell the user `shards × workers` are in flight.
4. When done, run `python3 $S/scripts/validate.py .puffins` and redo step 2 for invalid or missing reviews.

If RAM is tight (`free -h`), warn before going above ~24 agents.

## listen

1. Unless `curl -s localhost:8099/api/info` answers, start `python3 $S/assets/serve.py .puffins 8099` with Bash `run_in_background`. Give the user http://localhost:8099/.
2. Arm the listener, re-arming on every expiry until stopped:

       Monitor({command: "python3 $S/scripts/watch.py .puffins", description: "review fix queue", timeout_ms: 1800000})

Events (each emitted once ever, so re-arming is safe):

- `FIX <mode> <key> <review yaml> [agent]`: the prompt is the verbatim output of `python3 $S/scripts/agent_prompt.py <mode> <key> <review yaml> .puffins`. One fix agent per project (`<key>` minus `#<id>`), so findings of a project run in order, never in parallel: `SendMessage` the prompt to the project's agent (the `agent` field, or one you spawned this session); if there is none or it's gone, start a background general-purpose `Agent` (description `fix <project>`). Then `python3 $S/scripts/post.py .puffins <key> --agent <agentId>`.
- `REPLY <key> "<json text>"`: `SendMessage` the text, prefixed with `<key>: `, to the project's agent. None: spawn one with mode `continue`.

Fix agents commit each fix on its own (co-author `puffin <puffin@aukmind.com>`) unless the viewer's "Commit fixes" box was off when it was queued.

This session only dispatches: never verify, edit or discuss a finding itself. At most 4 project agents at once, never two on the same file; queue the rest. Report only failed agents or ones that ended without a final status. Pasted "Copy fix prompt" text gets one subagent per project.

## stop

    python3 $S/scripts/stop.py .puffins

`TaskStop` this session's serve/watch tasks and stop re-arming. Say how many fix agents are still running.

---
name: review
description: Review the whole repo split into projects, one /code-review agent each, then fix the findings from a web viewer or all at once in deduplicated, file-disjoint groups.
argument-hint: "<list|review|fix|listen|stop> [low|medium|high|xhigh|max] [--agents N] [--project NAME] [--no-commit] [extra context]"
---

# Puffin review

Commands: `list` maps every file to a project in .puffins/projects.yaml, `review` reviews them in parallel, `fix` fixes every open finding in parallel groups, `loopfix` fixes and re-reviews until nothing is left, `listen` opens the viewer and runs each fix you click, `stop` shuts it down. No command: `listen` if reviews exist, else `review`. Run from the repo root, `S=${CLAUDE_SKILL_DIR}`.

Options:

- Effort `low|medium|high|xhigh|max`: passed to /code-review. None given: pass none, so /code-review uses its own level.
- `--max-findings <n|all|default>`: passed to /code-review, default `all`.
- `--severity <critical|high|medium|low|nit>`: the lowest severity `fix` and `loopfix` work on, default `low` (so nits stay recorded but unfixed). Reviews always record every finding at every severity, so nothing has to be found twice.
- `--loops N`: `loopfix` rounds, default 3.
- `--agents N`: agents in flight, default 24 for `review`, 8 for `fix`.
- `--project NAME`: review or fix only that project and everything under it (`app` covers `app:ui:*`). Repeatable or comma-separated. Still skips finished reviews unless `review all`.
- `--no-commit`: `fix` leaves its changes uncommitted.
- Extra context: any other free text, e.g. "focus on thread safety" or "include untracked files and the images". Pass it verbatim as `context` to the review workflow. Scope defaults to tracked code only (`git ls-files`, or every file outside build/vendor dirs without git; no images, media, fonts, binaries, archives, logs, data dumps, lockfiles, minified files or licenses). If the context asks for untracked or non-code files, run `coverage.py` with `--untracked` / `--all-files` and `list` again.
- `--out-dir`, default `.puffins/`. `--port`, default 8099.

The web app stays in `$S/assets`. `coverage.py` and `projects.py` add the output dir to the repo `.gitignore`; leave that change uncommitted. Everything in the output dir is YAML: `projects.yaml`, `*.review.yaml`, `plan.yaml`, and the append-only `fix-*.yaml` logs (one `- {json}` row per line), plus the `.listener` heartbeat. Each `*.review.yaml` starts with its project's `description`, `files` and `reviewed_at` (the commit), so review and fix agents never read `projects.yaml`. Finding key: `<project>#<id>`. `decisions.yaml` holds settled trade-offs (`scripts/decide.py`); every re-review gets them, plus the project's earlier findings and what became of each, and does not report those again.

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
- Only list what `coverage.py` reports. Never open a file to classify it if its name is enough; never read images or binaries.

Loop until this exits 0, fixing any `STALE?` path and dropping any `NOT CODE` one. Add `--untracked` / `--all-files` only when the extra context asks for them:

    python3 $S/scripts/coverage.py .puffins

## review

1. No `.puffins/projects.yaml`, or the extra context widens the file scope: run `list` first.
2. Build the work list: projects never reviewed, plus reviewed ones whose files changed since their review (those carry `since`, and the reviewer focuses on that diff). `review all` drops `--changed` and re-reviews everything, still with each project's history. Pass each `--project` through as is. Tell the user how many fix-history rows were archived.

       python3 $S/scripts/projects.py --out-dir .puffins --changed --archive-fixes

3. Launch (this skill is the Workflow opt-in). A workflow runs at most `min(16, CPUs-2)` agents, so with N = min(`--agents`, project count): `shards = ceil(N / cap)`, `workers = ceil(N / shards)`. Read `$S/assets/review-workflow.js` and pass its full text inline as `script`. Never use `scriptPath`: the skill dir is outside the project, so Workflow refuses it even after a Read. Send all shards in one message:

       Workflow({script: <review-workflow.js text>, args: {root, skillDir: S, outDir: ".puffins", projects, shard: i, shards, workers, effort, maxFindings, context}})

   `projects` is step 2's JSON array, as a real array. Omit `effort` if none given. Omit `context` if none given. Tell the user `shards × workers` are in flight. Empty array: nothing to review, skip to step 4.
4. When done, run `python3 $S/scripts/validate.py .puffins` and redo step 2 for invalid or missing reviews.

If RAM is tight (`free -h`), warn before going above ~24 agents.

## fix

Fixes every open finding (no fix status yet, or `failed`) without the viewer. Never re-reviews afterwards unless asked.

1. Review what has no review yet, with the same effort and `--project`: step 2 of `review` with `--skip-existing` in place of `--changed`, then steps 3-4.
2. List the open findings at or above `--severity`, clustered by shared file. Nothing open: say so and stop.

       python3 $S/scripts/fix_plan.py list .puffins --severity low [--project NAME]

   `fix_plan.py auto` writes a starting plan.yaml (clusters sharing a file or a project form one group); refine it in step 3 rather than writing it from scratch.

3. Merge, dedup and group into `.puffins/plan.yaml`:
   - Duplicates: findings with one root cause or one fix. Keep the most severe, most precise one in `findings`; map the others to it under `duplicates`.
   - Groups: a cluster never splits, since its findings share a file. Merge clusters of one subsystem when they make one coherent commit. Add to `files` any file a suggested fix needs beyond the finding's own.
   - Each group is one meaningful commit. Prefer more, smaller groups: they are the parallelism.

   Shape:

       groups:
         - name: auth-session            # [\w.-]+
           summary: <one line, the commit's intent>
           files: [lib/auth.py, lib/session.py]
           findings: ["app:auth#3", "app:api#1"]
           duplicates: {"app:api#4": "app:auth#3"}

   Loop until this exits 0; its stdout is the groups JSON:

       python3 $S/scripts/fix_plan.py check .puffins --severity low [--project NAME]

4. Launch, with `workers = min(--agents, groups, min(16, CPUs-2))`. Read `$S/assets/fix-workflow.js` and pass its full text inline as `script` (never `scriptPath`):

       Workflow({script: <fix-workflow.js text>, args: {root, skillDir: S, outDir: ".puffins", groups, workers, commit}})

   `groups` is step 3's JSON, as a real array; `commit` is false on `--no-commit`. Tell the user `groups × workers`.
5. When done, report one line per group, then the `failed` and `needs-input` keys with their notes. For `needs-input`, point to `listen`, where replies continue the thread. When the user answers one in this session, record it: `python3 $S/scripts/decide.py .puffins <key> "<decision>"`.

## loopfix

Fix, re-review what the fixes touched, and repeat until no open finding at or above `--severity` is left, or `--loops` rounds (default 3) are done. Takes the same effort, `--severity`, `--project`, `--agents` and `--no-commit` as `fix`.

1. Run `review` (incremental: new projects and changed ones).
2. Each round:
   1. `python3 $S/scripts/fix_plan.py count .puffins --severity S [--project NAME]`. 0: stop, the code is clean at that severity.
   2. `fix_plan.py auto`, then refine and `check` it as in `fix` step 3, and launch the fix workflow as in `fix` step 4. Wait for it.
   3. Re-review only what the fixes changed: `review` steps 2-4 (`projects.py --changed --archive-fixes`, same effort and `--project`). Each reviewer gets its diff and the project's history, so it checks the fixes and reports only new problems.
3. Report one line per round (open before, fixed, skipped, failed, new findings), then what is still open, and the `needs-input` keys as in `fix` step 5. `failed` findings are retried next round; `needs-input` ones wait for the user.

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

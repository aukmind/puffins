<p align="center"><img src="puffins/assets/logo.svg" alt="Puffin" width="128"></p>

# Puffin skills

Claude Code skills so Puffins come to your aid.

## Quick start

```
/plugin marketplace add aukmind/puffins
/plugin install puffin@aukmind

/puffin:review review medium --agents 20
/puffin:review listen      # pick fixes one by one in the viewer
/puffin:review fix         # or fix everything at once
/puffin:review loopfix high --severity medium --loops 3   # fix, re-review the changes, repeat until clean
```

## Skills

- `/puffin:review <list|review|fix|loopfix|listen|stop> [low|medium|high|xhigh|max] [--severity critical|high|medium|low|nit] [--loops N] [--agents N] [--project NAME] [--no-commit] [extra context]`
- - `/puffin:review`: VERY fast full repo review with fixes from a web viewer. [review skill](puffins/skills/review/SKILL.md).
- - `list`: List projects and subprojects of your repo. Only tracked code files (`git ls-files`, no images, binaries, logs, data or lockfiles); ask in the extra context to widen it
- - `review`: Reviews each subproject with `/code-review` using N agents (runs list if needed). Only new projects and those changed since their last review, focused on the diff; `review all` redoes everything. Every finding is recorded at every severity, and a re-review is told what was already found, fixed, skipped or decided, so it does not report it again.
- - `fix`: Fixes all open findings (runs review if needed): dedups them, groups them by file set and subsystem, then fixes the groups in parallel, one commit per group (`--no-commit` to skip). Only findings at or above `--severity` (default `low`). No re-review afterwards.
- - `loopfix`: `fix`, then re-review only what the fixes changed, until nothing at or above `--severity` is left or after `--loops` rounds (default 3).
- - `listen`: Starts a web page and integration to review the changes from it (runs review if needed)
- - `stop`: Stops the server and monitoring

Fix statuses from `fix` show up in the viewer, and `needs-input` findings continue there with `listen`. Settled trade-offs go to `.puffins/decisions.yaml` (`scripts/decide.py`) and are passed to every later review.

![project-review](docs/project-review.png)

## Local hacking

    ln -s "$PWD/puffins/skills/review" "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/review"

## License

MIT, see [LICENSE](LICENSE).

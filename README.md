# Puffin skills

Claude Code skills so Puffins come to your aid.

## Quick start

```
/plugin marketplace add aukmind/puffins
/plugin install puffin@aukmind

/puffin:review review medium --agents 20
/puffin:review listen      # pick fixes one by one in the viewer
/puffin:review fix         # or fix everything at once
```

## Skills

- `/puffin:review <list|review|fix|listen|stop> [low|medium|high|xhigh|max] [--agents N] [--project NAME] [--no-commit]`
- - `/puffin:review`: VERY fast full repo review with fixes from a web viewer. [review skill](puffins/skills/review/SKILL.md).
- - `list`: List projects and subprojects of your repo
- - `review`: Reviews each subproject with `/code-review` using N agents (runs list if needed)
- - `fix`: Fixes all open findings (runs review if needed): dedups them, groups them by file set and subsystem, then fixes the groups in parallel, one commit per group (`--no-commit` to skip). No re-review afterwards.
- - `listen`: Starts a web page and integration to review the changes from it (runs review if needed)
- - `stop`: Stops the server and monitoring

Fix statuses from `fix` show up in the viewer, and `needs-input` findings continue there with `listen`.

![project-review](docs/project-review.png)

## Publish to your organization

Bump `version` in [puffins/.claude-plugin/plugin.json](puffins/.claude-plugin/plugin.json) first, then pick one:

- **Org plugin library (claude.ai).** In Claude Code, signed in to the org, ask: `publish the plugin in ./puffins to my org`. It lists the files it will send and asks before uploading. An admin then reviews it, unless the org publishes without review. Colleagues install it from the library.
- **Managed settings (git marketplace).** Admins add the marketplace and enable the plugin for everyone in the managed `settings.json`:

      "extraKnownMarketplaces": {
        "aukmind": { "source": { "source": "github", "repo": "aukmind/puffins" } }
      },
      "enabledPlugins": { "puffin@aukmind": true }

  Updates ship with a push to `main` and reach people the next time they run `/plugin marketplace update aukmind`.

## Local hacking

    ln -s "$PWD/puffins/skills/review" "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/review"

# Puffin skills

Claude Code skills so Puffins come to your aid.

## Quick start

```
/plugin marketplace add aukmind/puffins
/plugin install puffin@aukmind

/puffin:review review medium --agents 20
/puffin:review listen
```

## Skills

- `/puffin:review <list|review|listen|stop> [low|medium|high|xhigh|max] [--agents N] [--project NAME]`
- - `/puffin:review`: VERY fast full repo review with fixes from a web viewer. [review skill](puffins/skills/review/SKILL.md).
- - `list`: List projects and subprojects of your repo
- - `review`: Reviews each subproject with `/code-review` using N agents (runs list if needed)
- - `listen`: Starts a web page and integration to review the changes from it (runs review if needed)
- - `stop`: Stops the server and monitoring

![project-review](docs/project-review.png)

## Local hacking

    ln -s "$PWD/puffins/skills/review" "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/review"

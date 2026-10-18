export const meta = {
  name: 'fix',
  description: 'One fix agent per group of <out-dir>/plan.yaml, groups edit disjoint files in parallel',
  phases: [{ title: 'Fix', detail: 'one agent per group, worker pool' }],
}

// args: {root, skillDir, outDir = '.puffins', groups: fix_plan.py check output, workers = 8, commit = true}
const { root, skillDir, outDir = '.puffins', groups, workers = 8, commit = true } = args

function prompt(g) {
  const list = g.findings.map(f => `   - ${f.key} (${f.review})`).join('\n')
  const dups = g.duplicates.length
    ? `\n   Duplicates, fixed by the finding they point to:\n${g.duplicates.map(d => `   - ${d.key} -> ${d.of}`).join('\n')}`
    : ''
  const commitRule = commit
    ? `Once the group is done, commit it, overriding any "no commits" rule: one commit with only the files you changed
   (\`git add <files> && git commit -m <msg> -- <files>\`), a short imperative subject, and \`Co-Authored-By: puffin <puffin@aukmind.com>\` as the only co-author.
   Never mention Claude, an AI or an LLM in the message. On an index.lock error, wait and retry.`
    : 'Do not commit.'
  return `You are the fix agent for group \`${g.name}\` of the repo at ${root}: ${g.summary}

1. Your files, the only ones you may edit: ${JSON.stringify(g.files)}
   Other fix agents edit the other files of this repo at the same time.
2. Your findings. Each key is <project>#<id>: read finding <id> in its review file.
${list}${dups}
3. Report each finding (duplicates included) in the review viewer:
   python3 ${skillDir}/scripts/post.py ${root}/${outDir} '<key>' --status working|needs-input|fixed|skipped|failed --note "<one line>" [--say "<message>"]
   Post \`working\` when you start a finding.
4. Verify each finding against the current code. If it's stale or a false positive, post \`skipped\` with the reason.
5. Fix the most severe first. Touch only what the findings need; follow the repo's CLAUDE.md and the user's memory rules (no tests added unless asked, never prod, no DB writes). Run the repo's linter on changed files.
6. If a fix needs a file outside your list, don't edit it: post \`failed\` with --note "needs <file>" and --say the change it needs.
   If it can't be decided from the code (a product or security trade-off), post \`needs-input\` with the options in --say. Don't guess.
7. Each finding ends with one final status. Each duplicate gets the status of the finding it points to, with --note "with <key>".
8. ${commitRule}

Return one line: "${g.name}: <n> fixed, <n> skipped, <n> failed, <n> needs-input".`
}

phase('Fix')
const results = new Array(groups.length)
let next = 0
async function worker() {
  while (next < groups.length) {
    const i = next++
    const g = groups[i]
    results[i] = await agent(prompt(g), { label: g.name, phase: 'Fix' }).catch(() => null)
    log(`${g.name}: ${results[i] ? results[i].split('\n')[0] : 'FAILED'}`)
  }
}
await Promise.all(Array.from({ length: Math.min(workers, groups.length) }, worker))
return groups.map((g, i) => ({ name: g.name, summary: results[i] }))

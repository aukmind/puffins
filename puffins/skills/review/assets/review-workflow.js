export const meta = {
  name: 'review',
  description: 'One /code-review agent per project in <out-dir>/projects.yaml, writing <out-dir>/<a>/<b>/<c>.review.yaml',
  phases: [{ title: 'Review', detail: 'one agent per project, worker pool' }],
}

// args: {root, skillDir, outDir = '.puffins', projects: [{name, out, description, files}], shard = 0, shards = 1, workers = 12, effort, maxFindings = 'all', context = ''}
// effort omitted -> /code-review uses its own last level
const { root, skillDir, outDir = '.puffins', effort = '', maxFindings = 'all', shard = 0, shards = 1, workers = 12, context = '' } = args
const SCOPE_RULE = 'Review code only: source, scripts, config, build files. Never open images, media, fonts, binaries, archives, logs, data dumps, lockfiles, minified or generated files, even when a glob in your scope matches them, unless the extra context says otherwise.'
const CONTEXT = context ? `\n\nExtra context from the user, it wins over the rules above:\n${context}` : ''
const projects = args.projects.filter((_, i) => i % shards === shard)

const SCHEMA = `project: <name>
description: <given below>
files: <given below>
scope: <one line: files/regions reviewed>
findings:            # most severe first; [] if nothing survived verification
  - id: 1            # 1..N, unique in this file
    title: <one-line claim>
    severity: critical | high | medium | low | nit
    category: correctness | security | efficiency | robustness | reuse | simplification | docs | test-correctness | ...
    location: <path:line as written, may add context>
    file: <repo-relative path>
    line: <int or null>
    summary: <the defect, 1-3 sentences>
    failure_scenario: <concrete inputs/state -> wrong outcome>
    suggested_fix: <prose; a short snippet only if essential>
    severity_note: <optional, e.g. "plausible">
notes:               # optional: dropped-during-verification, caveats
  - title: <heading>
    body: <text>`

function prompt(p) {
  return `You are reviewing ONE project of the repo at ${root}: \`${p.name}\`.

1. Your project, from ${outDir}/projects.yaml (no need to read it):
   ${p.description}
   Files, your scope: paths, globs, and \`region\`s naming code inside a shared file (e.g. specific functions, or a docker-compose service):
   ${JSON.stringify(p.files)}
2. Run the code-review skill via the Skill tool: skill "code-review", args "${[effort, `--max-findings ${maxFindings}`].filter(Boolean).join(' ')}" plus your scope as path targets (files, not a diff). Never pass --fix or --comment.
3. ${SCOPE_RULE} Only report findings anchored in your scope. You may read anything else in the repo to verify a finding or suggest reuse.
4. NO FIXES. Do not edit, create or delete any file except your output file. No state-changing git, docker, DB or network commands. Never touch prod.
5. Write your result as YAML to ${root}/${p.out} (mkdir -p its directory), exactly this shape, using block scalars (|) for multi-line text. Its first three lines must be exactly:

project: ${p.name}
description: ${JSON.stringify(p.description)}
files: ${JSON.stringify(p.files)}

then:

${SCHEMA}

If the skill tells you to call ReportFindings, still write the same findings to the file.
6. Validate: python3 ${skillDir}/scripts/validate.py $(dirname ${root}/${p.out}) — fix your file until it reports no error for it.

Return one line: "<name>: <N> findings (<highest severity>)".${CONTEXT}`
}

phase('Review')
const results = new Array(projects.length)
let next = 0
async function worker() {
  while (next < projects.length) {
    const i = next++
    const p = projects[i]
    results[i] = await agent(prompt(p), { label: p.name, phase: 'Review' }).catch(() => null)
    log(`${p.name}: ${results[i] ? results[i].split('\n')[0] : 'FAILED'}`)
  }
}
await Promise.all(Array.from({ length: Math.min(workers, projects.length) }, worker))
return projects.map((p, i) => ({ name: p.name, out: p.out, summary: results[i] }))

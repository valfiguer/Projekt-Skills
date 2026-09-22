# What the pr-* skills do NOT do

One page instead of a "What it does NOT do" section repeated in every skill.

## Boundaries between the skills

| Want to… | Skill |
|---|---|
| create / assign / move tasks, log time, drive the timer | `pr` |
| estimates, plan-vs-actual, workload, sprint stats, roadmap | `pr-informes` |
| documents, a task's activity feed, the AI-context store | `pr-docs` |
| measure and cut what a Claude Code session costs | `pr-tokens` |

## Things no pr-* skill does

- **Delete anything in bulk without asking.** `op=delete` exists on `tasks/bulk`; no script
  exposes it. Deletions go through `pj_req` with an explicit confirmation from the user.
- **Touch finance, payroll or org admin.** Those paths exist (`spec_lookup.sh --search invoice`)
  and the guard hook blocks them without `--admit`. Reach them deliberately, never as a
  side effect of a task or time operation.
- **Invent estimates.** There is no AI estimator on `/api/v1`. `pr-informes` derives hours from
  points a human set, or the median of sibling tasks, and labels which.
- **Write a roadmap.** `GET /organizations/{org}/roadmap` has no POST counterpart.
- **Export tasks to PDF.** The API makes PDFs for quotes and invoices only; the org-wide
  artifact is a ZIP at `GET /organizations/{org}/export`.
- **Regenerate a bitácora with AI.** "Bitácora" now means a task's read-only activity feed.
- **Delete stale documents.** `pr-docs contexto sync` is one-way: a removed local file leaves
  its document behind. The dry-run lists those so you can archive them deliberately.
- **Load the full spec into context.** Ever. Use `spec_lookup.sh`.

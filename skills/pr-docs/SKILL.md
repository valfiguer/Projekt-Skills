---
name: pr-docs
description: >-
  Write and read Projekt Republic documents idempotently (title-keyed UPSERT of plain
  markdown, nested pages), read a task's activity feed, download the org export, and use
  Projekt as an AI-context store — mirror a repo's memory .md files into documents and load
  them back as one markdown bundle. Use for project docs, a runbook, sprint notes, a wiki
  page, or saving/loading AI memories. Requires the `pr` skill's connect step first.
allowed-tools: Read, Grep, Bash(python3:*), Bash(bash:*), Bash(jq:*)
---

# pr-docs — documents & AI-context store

`SK="${CLAUDE_SKILL_DIR}/scripts"`. Connect first with the `pr` skill:

```bash
PR="${CLAUDE_SKILL_DIR}/../pr/scripts"
bash "$PR/auth_check.sh" && bash "$PR/context_sync.sh"
```

## Documents are org-scoped plain markdown

Two facts that overturn the pre-rewrite notes:

1. `GET·POST /organizations/{org}/documents` — the **project is a field** (`project_id`), not a
   path segment.
2. `content` is **plain markdown**. No EditorJS, no `blocks`, no `?format=markdown`. What you
   write is what you read back. (`content` is always `null` when `kind` is `file`.)

```bash
python3 "$SK/docs.py" upsert --title "Runbook — Deploy" --project WEB --body-file ./runbook.md
python3 "$SK/docs.py" upsert --title "Runbook — Deploy" --project WEB --body-file ./runbook.md --apply
python3 "$SK/docs.py" upsert --title "Rollback" --parent "Runbook — Deploy" --body - --apply
python3 "$SK/docs.py" list --project WEB          # tree
python3 "$SK/docs.py" get "Runbook — Deploy" --out ./runbook.md
python3 "$SK/docs.py" activity <task-uuid> --project WEB    # the bitácora
python3 "$SK/docs.py" export --out org.zip --apply          # org-wide ZIP
```

**Title is the idempotency key** — trimmed, case-insensitive, within the chosen
project + parent scope. Re-running UPSERT PATCHes the same document; it never creates a
second one. Two real documents sharing a title is ambiguous: the first wins and a warning
prints. A `--parent` must already exist.

## AI-context store (memories ↔ documents)

Keep a codebase's context memories as documents so any AI reads them over the API instead of
crawling the repo.

```bash
python3 "$SK/contexto.py" diff --memory-dir ~/.claude/…/memory --project WEB
python3 "$SK/contexto.py" sync --memory-dir ~/.claude/…/memory --project WEB --apply
python3 "$SK/contexto.py" load --project WEB --out ctx.md
```

- Title = the **filename stem** (the stable key). A renamed file creates a second document.
- `--index MEMORY.md` makes that file the **parent's** body instead of a child.
- YAML frontmatter is not stored: `description` and `type` are surfaced as a lead blockquote,
  the rest is dropped. Put anything that must survive in the body.
- `sync` compares content and prints `unchanged` rows, so a re-run writes only what differs.
- **One direction only.** A deleted local file leaves its document behind; the dry-run lists
  those as stale so you archive them deliberately.

## What is gone

There is no AI "bitácora regenerate" and no issues→PDF export. **Bitácora** now means a task's
read-only activity feed (`…/tasks/{id}/activity`). The only PDFs the API builds are for quotes
and invoices; the org-wide artifact is a ZIP from `GET /organizations/{org}/export` — hand the
user the saved path, never read it into the model.

Shared: `../pr/references/endpoints.md` · `errors.md` · `limits.md`.

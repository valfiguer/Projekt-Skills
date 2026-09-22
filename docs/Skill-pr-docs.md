# Skill: `pr-docs` — documents & AI-context store

Idempotent writes and reads over Projekt Republic documents, plus a Serena-style context
store. Requires the [`pr`](Skill-pr.md) connect step.

```bash
SK="$CLAUDE_PLUGIN_ROOT/skills/pr-docs/scripts"
```

## Documents are org-scoped plain markdown

Two facts that overturn anything written before the API rewrite:

1. Documents live at `GET·POST /organizations/{org}/documents`. The **project is a field**
   (`project_id`), not a path segment.
2. `content` is **plain markdown**. There is no EditorJS block format, no `blocks` field and
   no `?format=markdown` round-trip — what is written is what is read back. `content` is
   always `null` when `kind` is `file`.

```bash
python3 "$SK/docs.py" upsert --title "Runbook — Deploy" --project WEB --body-file ./runbook.md
python3 "$SK/docs.py" upsert --title "Runbook — Deploy" --project WEB --body-file ./runbook.md --apply
python3 "$SK/docs.py" upsert --title "Rollback" --parent "Runbook — Deploy" --body - --apply
python3 "$SK/docs.py" list --project WEB
python3 "$SK/docs.py" get "Runbook — Deploy" --out ./runbook.md
python3 "$SK/docs.py" activity <task-uuid> --project WEB
python3 "$SK/docs.py" export --out org.zip --apply
```

**Title is the idempotency key**, matched trimmed and case-insensitively within the chosen
project + parent scope. Re-running UPSERT PATCHes the same document and never creates a
second one. Two real documents sharing a title is ambiguous: the first wins, with a warning.
A `--parent` must already exist — the script stops and lists the available titles otherwise.

## AI-context store

```bash
python3 "$SK/contexto.py" diff --memory-dir ~/.claude/…/memory --project WEB
python3 "$SK/contexto.py" sync --memory-dir ~/.claude/…/memory --project WEB --apply
python3 "$SK/contexto.py" load --project WEB --out ctx.md
```

- Title = the **filename stem**, the stable key. A renamed file creates a second document;
  keep filenames stable.
- `--index MEMORY.md` makes that file the **parent's** body rather than a child.
- Frontmatter is not stored: `description` and `type` become a lead blockquote, the rest is
  dropped. Anything that must survive belongs in the body.
- `sync` compares content and reports `unchanged` rows, so a re-run writes only differences.
- **One direction.** A deleted local file leaves its document behind; the dry-run lists those
  as stale so they are archived deliberately, never silently.

## What is gone

No AI "bitácora regenerate" and no issues→PDF export. **Bitácora** now means a task's
read-only activity feed (`GET …/tasks/{id}/activity`). The API builds PDFs only for quotes
and invoices; the org-wide artifact is a ZIP from `GET /organizations/{org}/export` — hand
the user the saved path rather than reading it into the model.

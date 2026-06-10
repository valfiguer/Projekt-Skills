# Skill: `projekt-docs`

UPSERT project docs by title (create-or-update, never duplicate), regenerate issue bitácoras (AI logbook), and export issues to PDF/markdown — all idempotent and dry-run-first. Covers the **DOCUMENT** pipeline phase. One script, three subcommands: `upsert`, `bitacora`, `pdf`.

Soporta español: documentación, página de proyecto, runbook, notas de sprint, bitácora, historia de usuario, exportar incidencias a PDF.

## Prerequisite — connect once

```bash
bash skills/projekt/scripts/auth_check.sh
bash skills/projekt/scripts/context_sync.sh
```

Read `.projekt-run/context.json` to resolve a project name → its `id`. No token? → [Configuration](Configuration.md).

## 1 — UPSERT a project doc (title-keyed, idempotent)

Markdown / plain text → minimal EditorJS blocks, then create-or-update by **title**:

```bash
# dry-run (shows CREATE vs UPDATE, parent, block counts)
python3 skills/projekt-docs/scripts/doc_generator.py upsert \
  --project <PID|KEY|name> --title "Runbook — Deploy" --body-file ./runbook.md

# apply
python3 skills/projekt-docs/scripts/doc_generator.py upsert \
  --project <PID|KEY|name> --title "Runbook — Deploy" --body-file ./runbook.md --apply
```

- Body source: `--body "## text"`, `--body -` (stdin), or `--body-file path.md`.
- Nest a page: `--parent "Runbook — Deploy"` (a title **or** UUID, resolved from the doc list).
- `--icon 📘` is applied on **CREATE only**.
- Re-running with the **same title** PATCHes the existing doc — never creates a second one.

Markdown supported: `#`..`######` headers, `-`/`*`/`+` bullets, `1.`/`1)` ordered lists, blank-line paragraphs. Other lines become paragraphs (no inline-formatting parsing).

## 2 — Regenerate issue bitácora (AI logbook / HdU)

```bash
python3 skills/projekt-docs/scripts/doc_generator.py bitacora --issue-ids <IID1>,<IID2>                 # dry-run
python3 skills/projekt-docs/scripts/doc_generator.py bitacora --issue-ids <IID1>,<IID2> --locale es --apply
```

**503 (AI quota / model unavailable) = SOFT-SKIP**: the prior bitácora is left intact and reported as skipped — never overwritten with an error. The run still exits 0 if the only failures were 503s.

## 3 — Export issues to PDF/markdown (artifact, not in-model)

```bash
python3 skills/projekt-docs/scripts/doc_generator.py pdf --issue-ids <IID1>,<IID2>                 # dry-run
python3 skills/projekt-docs/scripts/doc_generator.py pdf --issue-ids <IID1>,<IID2> \
  --format pdf --title "Sprint 12 report" --out ./sprint12.pdf --apply
```

Saves the **binary stream** to a file (`--out`, default `issues-export.<format>`). Do **not** render the PDF in the model — point the user at the saved path. `--format md`, `--mode claude`, `--no-comments`, `--no-attachments` available.

## EditorJS body shape

The wire format is EditorJS `OutputData`:

```json
{ "time": 1700000000000, "version": "2.30.6",
  "blocks": [ { "type": "header", "data": { "text": "Title", "level": 2 } },
              { "type": "paragraph", "data": { "text": "Body." } },
              { "type": "list", "data": { "style": "unordered", "items": ["a", "b"] } } ] }
```

Both POST and PATCH accept `blocks` as `oneOf: [object, string]`; this script sends the object form. PATCH leaves untouched any field not in the body.

## Gotchas

- **Title is the idempotency key.** Match is trimmed + case-insensitive. Two real docs sharing a title is ambiguous — the first listed wins; rename one.
- **Parent must already exist** in the same project. Unknown parent → the script stops and prints available titles. Circular nesting → API 400.
- **export-pdf is POST, not GET.** Despite the cheatsheet's shorthand, the spec defines `POST` with a required `issue_ids` body that streams `application/pdf`/`text/markdown`. This script uses POST and reads raw bytes.
- **403** = no write permission or cross-org token — not retryable. **429** handled by backoff.
- Archived docs are included when matching by title (`include_archived=1`) so an UPSERT updates a doc you archived rather than duplicating it.

## What it does NOT do

No hard delete (API only soft-archives via `PATCH is_archived`; not exposed). No doc versions/backlinks/move-by-position, no rich inline formatting, no image/embed/table/callout blocks (only header/paragraph/list). Doesn't author bitácora text itself (the server's AI does) — only triggers regeneration.

See also: [API Endpoints → Docs](API-Endpoints.md#docs) · [Errors & Troubleshooting](Errors-and-Troubleshooting.md).

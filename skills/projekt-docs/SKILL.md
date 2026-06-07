---
name: projekt-docs
description: >-
  Write and maintain Projekt project documentation (projekt.3xa.es) idempotently: title-keyed UPSERT of
  project/sprint docs from markdown into EditorJS blocks (create-or-update, never duplicate), nest pages
  under a parent, regenerate per-issue AI bitácora (logbook), and export issues to a PDF/markdown artifact.
  Use whenever the user asks to write/update project docs, a runbook, sprint notes, a wiki page, the
  bitácora / HdU of an issue, or to export issues as a PDF. Soporta español: documentación, página de
  proyecto, runbook, notas de sprint, bitácora, historia de usuario, exportar incidencias a PDF.
allowed-tools: Read, Grep, Bash(python3:*), Bash(bash:*), Bash(jq:*)
---

# projekt-docs — docs, bitácora & PDF export

UPSERT project docs by title (create-or-update), regenerate issue bitácoras, and export issues to PDF —
all idempotent and dry-run-first. This is the **DOCUMENT** step of the `projekt` pipeline.

`SK="${CLAUDE_SKILL_DIR}/scripts"` — use it for every command below.

## Prerequisite — connect first

Run the orchestrator's connect steps so the token + org + `.projekt-run/context.json` exist:

```bash
bash "${CLAUDE_SKILL_DIR}/../projekt/scripts/auth_check.sh"
bash "${CLAUDE_SKILL_DIR}/../projekt/scripts/context_sync.sh"
```

Read `.projekt-run/context.json` to resolve a project name → its `id` (and members). Never re-query.
No token? → `projekt/references/auth-setup.md`.

## Commands

All three are **dry-run by default**: they print a plan and write nothing until you add `--apply`.

### 1. UPSERT a project doc (title-keyed, idempotent)

Markdown/plain text → minimal EditorJS blocks, then create-or-update by **title**:

```bash
# dry-run (shows CREATE vs UPDATE, parent, block counts)
python3 "$SK/doc_generator.py" upsert \
  --project <PID|KEY|name> --title "Runbook — Deploy" --body-file ./runbook.md

# apply
python3 "$SK/doc_generator.py" upsert \
  --project <PID|KEY|name> --title "Runbook — Deploy" --body-file ./runbook.md --apply
```

- Body source: `--body "## text"`, `--body -` (stdin), or `--body-file path.md`.
- Nest a page: `--parent "Runbook — Deploy"` (a title **or** a UUID, resolved from the doc list).
- `--icon 📘` is applied on CREATE only.
- Re-running with the **same title** PATCHes the existing doc — it never creates a second one.

Markdown supported: `#`..`######` headers, `-`/`*`/`+` bullets, `1.`/`1)` ordered lists, blank-line
paragraphs. Other lines become paragraphs (no inline-formatting parsing — EditorJS keeps the raw text).

### 2. Regenerate issue bitácora (AI logbook / HdU)

```bash
python3 "$SK/doc_generator.py" bitacora --issue-ids <IID1>,<IID2>                  # dry-run
python3 "$SK/doc_generator.py" bitacora --issue-ids <IID1>,<IID2> --locale es --apply
```

**503 (AI quota / model unavailable) = SOFT-SKIP**: the prior bitácora is left intact and reported as
skipped — never overwritten with an error. The run still exits 0 if the only failures were 503s.

### 3. Export issues to PDF/markdown (artifact, not in-model)

```bash
python3 "$SK/doc_generator.py" pdf --issue-ids <IID1>,<IID2>                  # dry-run
python3 "$SK/doc_generator.py" pdf --issue-ids <IID1>,<IID2> \
  --format pdf --title "Sprint 12 report" --out ./sprint12.pdf --apply
```

Saves the **binary stream** to a file (`--out`, default `issues-export.<format>`). Do NOT try to render
the PDF in the model — point the user at the saved path. `--format md`, `--mode claude`,
`--no-comments`, `--no-attachments` available.

## EditorJS body shape (confirmed against the spec)

Verified the accepted body with `bash projekt/scripts/spec_lookup.sh "/projects/{projectId}/docs" post`
(schemas `ProjectDoc.blocks` and `EditorJsBlock`). The wire format is EditorJS `OutputData`:

```json
{ "time": 1700000000000, "version": "2.30.6",
  "blocks": [ { "type": "header", "data": { "text": "Title", "level": 2 } },
              { "type": "paragraph", "data": { "text": "Body." } },
              { "type": "list", "data": { "style": "unordered", "items": ["a", "b"] } } ] }
```

Both POST and PATCH accept `blocks` as **`oneOf: [object, string]`** — a parsed object or a JSON-encoded
string; reads always return the parsed object. This script sends the object form. PATCH leaves any field
not in the body untouched (so we send `title` + `blocks`, plus `parent_doc_id` only when `--parent` is given).

## Gotchas

- **Title is the idempotency key.** Match is trimmed + case-insensitive. Two real docs sharing a title is
  ambiguous — the first listed wins; rename one if that's not intended.
- **Parent must already exist** in the same project (resolved from the listing). Unknown parent → the
  script stops and prints the available titles; create the parent doc first. Circular nesting → API 400.
- **export-pdf is POST, not GET.** The endpoint cheatsheet says `GET /issues/export-pdf`, but the spec
  defines it as `POST` with a required `issue_ids` body that streams `application/pdf`/`text/markdown`.
  This script uses POST and reads raw bytes (the shared client decodes text, which would corrupt a PDF).
- **403** = no write permission on the project or a cross-org token — not retryable; switch token/org.
  **429** is handled by the client's backoff. See `projekt/references/errors.md`.
- Archived docs are included when matching by title (`include_archived=1`) so an UPSERT updates a doc you
  archived rather than creating a duplicate.

## What it does NOT do

- No hard delete (the API only soft-archives via `PATCH is_archived`; not exposed here).
- No doc versions/backlinks/move-by-position, no rich inline formatting, no image/embed/table/callout
  blocks (only header/paragraph/list) — discover those with `projekt/scripts/spec_lookup.sh` if needed.
- Does not author bitácora text itself (the server's AI does); this only triggers regeneration.

## Shared references

`projekt/references/endpoints.md` (Docs section) · `errors.md` (422/429/503/403) · `auth-setup.md`.
Slim projections + ledger come from the shared `projekt_api` client; `.projekt-run/*.jsonl` is the resume log.

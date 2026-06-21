---
name: projekt-context
description: >-
  Use Projekt as an AI-context store (Serena-style): mirror a codebase's memory/context .md files
  into a Projekt project's docs (one doc per file, idempotent UPSERT) and load them back as ONE
  markdown bundle, so Claude Code / Codex / any AI reads repo context cheaply over the API instead
  of crawling the whole codebase. Use whenever the user wants to save Claude/Serena memories into
  Projekt, sync a memory directory, or load project context for an agent. Soporta español:
  memorias, contexto de proyecto, sincronizar memorias, cargar contexto.
allowed-tools: Read, Grep, Bash(bash:*), Bash(python3:*)
---

# projekt-context — AI-context store (memories ↔ docs)

Keep a codebase's **context memories** (architecture, gotchas, conventions, runbooks, decisions) as
Projekt docs so any AI provider reads them over the API — `?format=markdown`, cheap — instead of
re-deriving them by crawling the repo and burning tokens. Same idea as Serena's `.serena/memories/`,
but stored in Projekt and shared across providers and machines.

`CS="${CLAUDE_SKILL_DIR}/scripts/context_store.py"` — use it for every command below.

## Prerequisite — connect first

Run the orchestrator's connect steps so the token + org + `.projekt-run/context.json` exist:

```bash
bash "${CLAUDE_SKILL_DIR}/../projekt/scripts/auth_check.sh"
bash "${CLAUDE_SKILL_DIR}/../projekt/scripts/context_sync.sh"
```

No token? → `projekt/references/auth-setup.md`. Wrong org (cross-org token 403s)? export the right
`TREXA_API_TOKEN` before connecting.

## Commands

### 1. sync — mirror a memory dir into Projekt docs (idempotent, DRY-RUN first)

UPSERT every `*.md` in a directory as a doc under a parent (default **"Claude Memory"**), one doc per
file, title = the **filename stem** (the stable idempotency key). Re-running PATCHes the same titles —
never duplicates. The body is sent as **Markdown** (the server converts it to rich EditorJS blocks —
tables, code, callouts); YAML frontmatter is parsed and rendered as a clean lead blockquote
(`> description _(type)_`) instead of being flattened into the doc.

```bash
# dry-run (counts files, shows parent + index)
python3 "$CS" sync --project <PID|KEY|name> --memory-dir ~/.claude/.../memory

# apply
python3 "$CS" sync --project <PID|KEY|name> --memory-dir ~/.claude/.../memory --apply
```

- `--parent "Claude Memory"` — parent doc title the memories nest under (created if missing).
- `--index MEMORY.md` — this file becomes the **parent body** (the index) instead of a child.
- `--icon 🧠` — parent icon, on CREATE only.
- **Title = filename stem**, NOT the frontmatter `name:` slug — keep filenames stable or a rename
  creates a new doc (the old one lingers; archive it).

### 2. load — read the store back as one markdown bundle (cheap onboarding)

Concatenate the parent's child docs (each fetched with `?format=markdown`) into a single Markdown
blob — the one call an agent makes at session start to skip crawling the repo.

```bash
python3 "$CS" load --project <PID|KEY|name>                 # → stdout
python3 "$CS" load --project <PID|KEY|name> --out ctx.md    # → file
```

- `--parent "Claude Memory"` — which tree to bundle.
- Output: `# <parent> — AI context bundle`, the index, then one `## <title>` section per memory.

## How it pairs with the API

- **Write:** docs accept a `markdown` field on POST and PATCH (the server runs
  `EditorJsMarkdownConverter::fromMarkdown`), so this skill never hand-builds EditorJS JSON.
- **Read:** `GET /projects/{pid}/docs/{id}?format=markdown` returns compact Markdown (~half the
  tokens of the raw EditorJS blocks) — what `load` uses.

## Gotchas

- **Idempotency key is the filename stem.** Two files with the same stem collide; a renamed file
  creates a second doc.
- **`sync` writes; `load` is read-only.** `sync` is dry-run until `--apply`; `load` always runs.
- **Frontmatter is stripped, not stored.** Only `description` + `type` are surfaced (as a lead
  blockquote). Put anything you need preserved in the body.
- **Cross-org / no write permission → 403** on `sync`; switch token/org. See `projekt/references/errors.md`.

## What it does NOT do

- No delete/prune of stale docs (a removed memory file leaves its doc behind — archive it manually).
- No bidirectional sync (Projekt → local). One direction: local memories → Projekt docs.
- No auth/setup of its own — it reuses the `projekt` orchestrator's connect + shared API client.

## Shared references

`projekt/references/endpoints.md` (Docs section) · `errors.md` · `auth-setup.md`. Shared API client +
slim projections live in `projekt/scripts/lib/projekt_api.py`.

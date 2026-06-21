# Changelog

All notable changes to **projekt-skills** are documented here.
This project adheres to [Semantic Versioning](https://semver.org/).

## [0.3.0] — 2026-06-21

AI-friendly Markdown round-trip + the AI-context store.

### Added
- **`projekt-context` skill** — use Projekt as a Serena-style AI-context store. `sync` mirrors a memory directory (`*.md`) into a project's docs (one doc per file, title = filename stem, idempotent UPSERT, YAML frontmatter rendered as a clean lead blockquote instead of flattened); `load` reads the tree back as ONE `?format=markdown` bundle, so an agent onboards a codebase in a single cheap call instead of crawling it.

### Changed
- **`projekt-docs` is now Markdown-native.** `upsert` sends the body as a `markdown` field and the server's `EditorJsMarkdownConverter::fromMarkdown` builds the blocks — tables, fenced code, callouts and inline formatting now round-trip (previously only header/paragraph/list via a local builder). Read any doc back as Markdown with `?format=markdown` (~half the tokens of raw EditorJS). Requires the Projekt API's doc-create Markdown support (shipped alongside).

## [0.2.1] — 2026-06-07

### Changed
- **Calibrated `points_hours.json`** to the 3XA org's real estimate distribution (428 estimated issues across all projects: median 3 h, p90 10 h — mostly small tasks). The previous Fibonacci defaults (1 pt = 2 h … 21 pt = 96 h) ran ~3× high. New map: 1→1, 2→2, 3→4, 5→8, 8→13, 13→20, 21→40; `default_hours` 8→3. The org records estimates in **hours, not story points** (0 issues carry points), so the table maps AI-suggested points onto that real hours scale; `units.md` documents how to recalibrate. No code change.

## [0.2.0] — 2026-06-07

Hardening after end-to-end write verification.

### Changed
- **Consistent CLI across skills:** every project argument is now `--project` (accepts id / key / name), and `--apply` is always placed **after** the sub-command. Previously `projekt-estimate` took a positional `project` and `projekt-docs` used `--project-id` (UUID-only) with a top-level `--apply` — an inconsistency that was easy to get wrong.

### Verified
- Live `--apply` writes confirmed against the API for every path (issue create, bulk assign+move, estimate PUT, time-entry POST, doc create/update) on a throwaway project, then hard-deleted. No real data touched.

## [0.1.0] — 2026-06-07

Initial public release.

### Added
- Claude Code plugin (`projekt-skills`) distributed via the `3xa-projekt` marketplace.
- Primary orchestration skill **`projekt`**: the `CONNECT → DISCOVER → PLAN → CREATE → ASSIGN → ESTIMATE → TIME → DOCUMENT → REPORT` pipeline, endpoint cheatsheet, full-surface spec discovery, and safety guardrails (dry-run default, ledger, destructive-action confirmation, fingerprint-only token logging).
- Task skills: **`projekt-issues`**, **`projekt-estimate`**, **`projekt-workload`**, **`projekt-time`**, **`projekt-docs`**.
- Shared contract: `lib/http.sh` (dual-auth headers + `X-Org-Id` + rate-limit backoff), `auth_check.sh`, `context_sync.sh`, `spec_lookup.sh` / `spec_index.sh` (the OpenAPI spec never enters context), `run_ledger.sh`, `slim.jq`.
- `spec-drift-check` CI to keep the endpoint cheatsheet in sync with the live spec.

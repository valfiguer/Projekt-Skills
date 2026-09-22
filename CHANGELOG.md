# Changelog

All notable changes to **projekt-skills** are documented here.
This project adheres to [Semantic Versioning](https://semver.org/).

## [0.5.0] — 2026-09-22

### Added — `projekt-tokens`: medir lo que cuesta una sesión, y bajarlo

Skill nueva más dos hooks. Nace de una medición, no de una intuición: sobre **18 sesiones
reales de Claude Code (30.319 turnos)**, el reparto de tokens es

```
entrada                 106.209   0,0 %
escritura de caché  293.100.824   2,0 %
LECTURA DE CACHÉ 14.537.908.034  97,8 %
salida               34.913.098   0,2 %
```

O sea que **lo que se paga no es lo que entra, sino lo que entra multiplicado por los
turnos que quedan**: la conversación entera se reenvía en cada turno. En las sesiones
grandes eso son 489k-550k tokens de lectura *por turno*. De los 16,77 M de caracteres que
devolvieron las herramientas, el 82,6 % los devolvió `Bash` (sed 17,4 · grep 10,2 · cat
4,2), y los resultados de ≥10.000 caracteres son el 0,7 % de las llamadas y solo el 12,8 %
de los bytes: no hay un monstruo, son mil cortes. Por eso el catálogo del MCP —que viaja
una vez por sesión y va cacheado— es el tercer comando de la skill y no el primero.

- **`skills/projekt-tokens/scripts/medir.py`** — los cuatro cubos que se facturan, la
  lectura por turno, la peor sesión, qué herramienta llenó el contexto, las familias de
  comando dentro de `Bash` y los tres volcados más gordos con su comando. Sale todo de
  `~/.claude/projects/<proyecto>/*.jsonl`: **no llama a ninguna API ni gasta un token**.
  `--breve`, `--json`, `--todas`, `--proyecto`, `--max-mb`.
- **`skills/projekt-tokens/scripts/instalar.py`** — mete las ocho reglas de contexto en el
  `CLAUDE.md` del repo, entre marcas e idempotente (dry-run por defecto, `--apply` para
  escribir, `--quitar` para retirarlas). Es la pieza que hace que la disciplina dure más
  que la invocación de la skill: una skill solo está en contexto cuando se la llama, y
  esto se decide en cada llamada.
- **`skills/projekt-tokens/scripts/perfil_mcp.py`** — de una tarea a `?tools=<dominios>`
  del conector, con bytes y tokens de cada perfil. Dice cuándo pedir dominios sale **más
  caro** que `core`, que es la mitad que nadie cuenta.
- **`skills/projekt-tokens/tarifas.json`** — tarjeta de tarifas fechada ($/MTok) con los
  multiplicadores de caché (escritura 1,25x, lectura 0,1x). Rotulada como equivalencia:
  una suscripción paga en límite de uso, no en dólares.
- **`hooks/presupuesto_al_arrancar.sh`** (`SessionStart`) — dos líneas al arrancar con la
  lectura por turno de la sesión anterior, y un aviso al pasar de 200.000. ~0,1 s.
- **`hooks/aviso_de_tokens.sh`** (`PreToolUse` sobre `Bash`) — caza `cat` sin tope,
  búsquedas recursivas sin `-l`/`-c`, `git log` sin `-n`, `git diff` entero y `find`/`ls -R`
  sueltos. **Por defecto solo APUNTA** a un registro y deja pasar: bloquear cuesta un
  turno, y un turno en una sesión cargada cuesta más que el volcado que evita.
  `PROJEKT_TOKENS_ESTRICTO=1` lo endurece; `PROJEKT_TOKENS_SIN_AVISO=1` apaga los dos.
- **`docs/Skill-projekt-tokens.md`** — la página de la skill, con la tabla de la medición.

### Fixed

- Los dos README decían «seis skills» y ya eran siete: faltaba `projekt-context`. Ahora
  son ocho y están las dos que faltaban.

## [0.4.0] — 2026-07-13

Port to the rewritten **`/api/v1`** org-scoped API. `projekt.3xa.es` replaced its legacy flat PHP API
with a contract-first rewrite: base is now `https://projekt.3xa.es/api/v1`, **org + project live in the
URL path** (no more `X-Org-Id`-header + `project_id` query param), and the core resource is **`tasks`**
instead of `issues`. The old skill broke entirely; this restores **CONNECT + REGISTER TASKS** end-to-end.

### Changed
- **Base URL** `…/api` → `…/api/v1` everywhere (`lib/http.sh`, `lib/projekt_api.py`, `references/auth-setup.md`, `references/endpoints.md`).
- **Auth / self-discovery.** `auth_check.sh` now calls `GET /auth/me` and reads the PAT's own scope from
  the response `api_key` object (`{id, name, organization_id, project_id}`) to self-discover the org **and**
  project — a project-scoped key needs no config. Falls back to `GET /organizations` for the org when
  `api_key` is absent (cookie/older key). `context.json` gains `project_id` + `key_name`.
- **Context sync.** `context_sync.sh` uses `GET /organizations/{org}/projects` and
  `GET /organizations/{org}/members`; a project-scoped key (which gets 403 listing projects) falls back to
  a single-project context from the self-discovered `project_id`.
- **Task creation (`projekt-issues`).** `bulk_issue_create.py` now `POST`s to
  `/organizations/{org}/projects/{proj}/tasks` and sweeps `GET …/tasks` for dedupe. Because the rewrite's
  create body has **no `assignee_id`** (a task is born `todo`), assignee + any working status are applied
  via a follow-up `PATCH …/tasks/{id}`. Statuses normalized to `todo|in_progress|done|cancelled`; the
  assignee-required rule now means "can't advance out of `todo` without an owner".
- **Terminology** issues → tasks across the ported skill + endpoint cheatsheet.

### Not yet ported (base URL fixed, endpoint paths still legacy — flagged with a TODO in each SKILL.md)
- `projekt-estimate`, `projekt-time`, `projekt-workload`, `projekt-docs`, `projekt-context`, and
  `projekt-issues`'s `assign_and_move.py` still call legacy flat paths (`/issues`, `/workload`,
  `/projects/{pid}/docs`, `/ai/suggest-estimation`, …) and will 404 until re-pathed to the org-scoped
  surface. Each SKILL.md documents the exact rewrite target + the `spec_lookup.sh` term to rediscover it.

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

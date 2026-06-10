# Safety & Security

Projekt-Skills is built to be safe to run against a live organization. Five layers.

## 1 — Dry-run by default

Every mutating action **prints a plan and writes nothing** until you pass `--apply`.

- Bulk create / assign / move / estimate / time-log / doc-upsert all show a table (create/skip, assign→move, proposed hours, etc.) on the first run.
- Re-run with `--apply` to execute.
- Re-run again → dedupe (creates 0). See the [ledger](Architecture.md#idempotency--resume-the-ledger).

Read-only skills (`projekt-workload`, `summary`, `rollup`, roadmap `list`) take no `--apply` and are always safe.

## 2 — Second confirmation for destructive / sensitive paths

Beyond `--apply`, these require an explicit **second confirmation** (`--admit`):

- HTTP `DELETE`
- anything under `admin/*`, `finance/*`, `payroll/*`, `tax-multi`, `gl/*`, `consolidation`, `gdpr`

State the **blast radius** to the user before applying. The skills surface this; the guard hook enforces it.

## 3 — The PreToolUse guard hook

`hooks/guard.sh` (registered in `hooks/hooks.json` on `Bash`) is an independent backstop. It reads the pending Bash command and:

- ignores anything that isn't Projekt API traffic (`projekt.3xa.es/api`, `pj_req`, or a `DELETE` request);
- lets it through if it already carries `--admit`;
- otherwise **blocks** (exit 2) any command matching the sensitive regex — DELETE / `admin` / `finance` / `payroll` / `tax-multi` / `gl/` / `consolidation` / `gdpr` — with a message telling you to state the blast radius and re-run with `--admit`.

This is belt-and-suspenders: even if a script's own check were bypassed, the hook still stops a sensitive write.

## 4 — Your token never leaks

- Sent **only** in request headers (`Authorization` / `X-Auth-Token`), never in URLs or bodies.
- Logged **only as a fingerprint** (`pjk_live_…abcd`) — never printed in full, never written to the ledger.
- **`.gitignore` blocks** `auth.json`, `*.token`, `*.pat`, `.env*`, and the whole `.projekt-run/` working dir.
- The PAT is **never bundled** with the plugin and **never committed**.

See [Configuration](Configuration.md) for where the token lives.

## 5 — Org-scoped writes

- Every write is pinned to one `X-Org-Id`. A PAT is bound to **one** organization.
- Cross-org **reads** (via `?include_shared=true`) stay **read-only** — a shared resource never becomes a write target.
- Touching another org's resource returns **403**, and the client does **not** retry it (it's not a transient error). See [Errors & Troubleshooting](Errors-and-Troubleshooting.md).

## The assignee-required rule

Not security, but a safety invariant worth knowing: an issue **cannot leave `Backlog`/`To Do`** for a working column without an `assignee_id` (API returns **422 / `blocked_unassigned`**). The skills **assign first, then move**, and surface un-assignable items as **"needs owner"** rather than dropping them or failing the whole batch. See [projekt-issues](Skill-projekt-issues.md).

## What to do if something looks off

- A run reports `blocked > 0`? Don't treat it as green — fix owners and re-run (it dedupes).
- A `403`? You're hitting another org. Switch org/token; don't retry.
- A `503` on an AI call? It's a soft-skip — prior content is kept, the pipeline continues. Re-run later.

Full matrix: **[Errors & Troubleshooting](Errors-and-Troubleshooting.md)**.

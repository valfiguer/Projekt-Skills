# FAQ

**Is it safe to run against my live org?**
Yes. Every mutation is **dry-run by default** — it prints a plan and writes nothing until you pass `--apply`. Destructive/sensitive paths need a second `--admit`, and a [guard hook](Safety-and-Security.md#3--the-pretooluse-guard-hook) blocks them belt-and-suspenders. See [Safety & Security](Safety-and-Security.md).

**Where does my token live? Can it leak?**
In `TREXA_API_TOKEN` or `~/.config/3xa-projekt/auth.json` — never bundled, never committed. It's sent only in request headers and logged only as a fingerprint. See [Configuration](Configuration.md).

**Do I need the OpenAPI spec?**
No. The 1.3 MB spec never enters context. The [cheatsheet](API-Endpoints.md) covers ~90% of calls; the rest is reached with `spec_lookup.sh` on demand.

**Why did my import create fewer issues than rows in the CSV?**
Dedupe. Rows already present (by `(project_id,title)` or `external_ref`) are skipped. Check the dry-run table — it shows create vs skip per row. Give every row a stable `external_ref`.

**Why won't my issue move to "In Progress"?**
The assignee-required rule: an issue can't leave `Backlog`/`To Do` without an `assignee_id` (422). Assign first — [projekt-issues](Skill-projekt-issues.md) does assign-then-move automatically.

**The AI estimator gave story points but issues store hours — what happens?**
[projekt-estimate](Skill-projekt-estimate.md) converts points→hours via `points_hours.json` and flags the value `ai-estimated`. On AI 503 it falls back to the median of sibling issues. See [Estimation Units](Estimation-Units.md).

**I got a 403 on a call I expected to work.**
Cross-org. A PAT is bound to one organization; the resource belongs to another. Switch org/token. It's not retried by design. See [Errors & Troubleshooting](Errors-and-Troubleshooting.md).

**Can I edit or delete time entries / hard-delete issues / docs?**
No. The plugin logs time, drives timers, and reads roll-ups; it doesn't edit/delete entries. Issues and docs are **soft-archived** (`/archive`, `PATCH is_archived`), never hard-deleted.

**Does it cost a lot of tokens?**
It's built to be cheap: spec stays out of context, reads are slimmed with `jq`, identity resolves once and caches, and all arithmetic is done by scripts. See [Architecture → token-cheap](Architecture.md#how-it-stays-token-cheap).

**Can I run it in CI / headless?**
Yes — set `TREXA_API_TOKEN` (and `TREXA_ORG_ID`) as env vars. Env wins over the file.

**Does it work in Spanish?**
Yes. Every skill is bilingual (EN/ES). See [Guía rápida (Español)](Guia-rapida-Espanol.md) and the bundled `recetas-es.md`.

**How do I reach an endpoint the cheatsheet doesn't list?**
`bash skills/projekt/scripts/spec_lookup.sh --search "<term>"` to find it, then `spec_lookup.sh "/path" <method>` to read one block. Domain map on [API Endpoints](API-Endpoints.md#full-surface-domain-map).

Still stuck? → [Errors & Troubleshooting](Errors-and-Troubleshooting.md).

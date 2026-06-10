# Projekt-Skills

> A [Claude Code](https://code.claude.com) plugin that lets you connect your **[Projekt](https://projekt.3xa.es)** organization and automate **issues, documentation, workloads, estimations and time tracking** through the Projekt REST API — sequentially, professionally, and with maximum token efficiency.
>
> _Un plugin de Claude Code para conectar tu organización de Projekt y automatizar incidencias, documentación, cargas de trabajo, estimaciones y tiempos vía la API REST — secuencial, profesional y con el mínimo gasto de tokens._

---

## What you get

One plugin, six skills (namespaced `projekt-skills:*`):

| Skill | Does |
| --- | --- |
| **`projekt`** | The orchestrator. Owns the full `CONNECT → DISCOVER → PLAN → CREATE → ASSIGN → ESTIMATE → TIME → DOCUMENT → REPORT` pipeline. The default entry point — start here. |
| **`projekt-issues`** | Bulk-create and update issues (CSV/sheet/text → backlog), assign, batch status moves. |
| **`projekt-estimate`** | Fill estimates, story-points→hours, roadmap & dependencies, plan-vs-actual. |
| **`projekt-workload`** | Team capacity & workload reports (who's overloaded, utilization %). |
| **`projekt-time`** | Batch-log time entries, timers, time roll-ups. |
| **`projekt-docs`** | Create/maintain project docs, regenerate issue logbooks, export PDFs. |

## Install

```text
/plugin marketplace add valfiguer/Projekt-Skills
/plugin install projekt-skills@3xa-projekt
```

Then just ask Claude, e.g. _"Connect my Projekt org and plan a sprint from this backlog"_ — the `projekt` skill auto-activates.

## Setup — your Personal Access Token (PAT)

This plugin talks to Projekt **as you**, using your own PAT. It is never bundled and never committed.

1. In Projekt, go to **Organization → Settings → General → Integraciones** and click **Create API key**. You get a `pjk_live_…` token (copy it — shown once).
2. Provide it to the skill in **one** of two ways (env wins):
   - **Environment:** `export TREXA_API_TOKEN="pjk_live_…"`
   - **File** (shared with the Projekt MCP): `~/.config/3xa-projekt/auth.json`
     ```json
     { "token": "pjk_live_…", "api_base": "https://projekt.3xa.es/api" }
     ```
3. (Optional) Pin an org: `export TREXA_ORG_ID="<uuid>"`. Otherwise the skill uses your current organization from `/me`.

A PAT carries **your full role** in **one** organization (no per-endpoint scoping). Treat it like a password — see _Safety_.

## Requirements

`bash`, `curl`, `jq`, and `python3` (3.10+) on PATH. No other dependencies (pure stdlib; no `yq`/`pyyaml` needed).

## Safety (read this)

- **Dry-run by default.** Every mutating action prints a payload/diff table and writes nothing until you pass `--apply`.
- **Destructive & sensitive actions** (DELETE, `admin/*`, `finance/*`, `payroll/*`) require a **second explicit confirmation** beyond `--apply`.
- **Your token never leaks.** It is sent only in request headers and logged only as a fingerprint — never printed, never written to the ledger, never committed (`.gitignore` blocks `auth.json`, `*.token`, `.projekt-run/`).
- **Idempotent & resumable.** Bulk runs dedupe and can resume from an append-only ledger in `.projekt-run/`.
- **Org-scoped.** Writes are pinned to one `X-Org-Id`; cross-org shared reads never become write targets.

## How it stays token-cheap

- The **1.3 MB OpenAPI spec never enters context.** A bundled `spec_lookup.sh` prints a single endpoint block on demand; the 90% case is covered by a hand-curated cheatsheet.
- **Connect once:** auth + org + project/member roster resolve a single time and cache to `.projekt-run/context.json` for all name→id resolution.
- **Slim at the edge:** API responses are projected down to a few fields with `jq` before Claude ever sees them.
- **Math is deterministic:** roll-ups, reports and docs are built by bundled scripts; the model is spent only on genuinely new narrative.

## Links

- Projekt developer docs: <https://projekt.3xa.es/developers/>
- API reference (Scalar): <https://projekt.3xa.es/developers/reference.html>
- OpenAPI spec: <https://projekt.3xa.es/openapi.yaml>

## License

MIT © 3XA Design — see [LICENSE](LICENSE).

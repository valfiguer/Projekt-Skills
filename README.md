# Projekt-Skills

**English** · [Español](README.es.md)

> A [Claude Code](https://code.claude.com) plugin that lets you connect your **[Projekt](https://projekt.3xa.es)** organization and automate **issues, documentation, workloads, estimations and time tracking** through the Projekt REST API — sequentially, professionally, and with maximum token efficiency.

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

---

## Install

> **Requirements first:** `bash`, `curl`, `jq` and `python3` (3.10+) on your `PATH`. No other dependencies (pure stdlib; no `yq`/`pyyaml` needed). Check with `command -v bash curl jq python3`.

### 1 — Add the marketplace and install

Open Claude Code (terminal, desktop app, or IDE extension). In the **prompt box**, type a slash — `/` — to bring up commands, then run these **two lines one at a time** (press Enter after each; wait for the first to finish before the second):

```text
/plugin marketplace add valfiguer/Projekt-Skills
/plugin install projekt-skills@3xa-projekt
```

> These are **Claude Code slash-commands**, typed in the chat prompt — *not* shell commands, so don't paste them into a terminal/bash.

Prefer clicking? Type `/plugin` alone to open the plugin browser, pick **3xa-projekt → projekt-skills**, and hit install.

What each piece means:

- `valfiguer/Projekt-Skills` — the **GitHub repo** that hosts the marketplace (the `add` step).
- `projekt-skills` — the **plugin** name.
- `3xa-projekt` — the **marketplace** name (defined in `.claude-plugin/marketplace.json`). The `plugin@marketplace` syntax is required for the `install` step.

### 2 — Verify it loaded

```text
/plugin
```

You should see **`projekt-skills`** (v0.2.1) listed and enabled, exposing the six `projekt-skills:*` skills. If it's not there, see [Troubleshooting](#troubleshooting-install).

### 3 — Set your token

The plugin needs **your** Projekt Personal Access Token before it can do anything — see [Setup](#setup--your-personal-access-token-pat) below.

### 4 — Use it

Ask Claude in plain language, e.g.:

> _"Connect my Projekt org and plan a sprint from this backlog."_

The `projekt` skill auto-activates and walks the pipeline. Everything is **dry-run by default** — nothing is written until you confirm.

### Update / remove

```text
/plugin marketplace update 3xa-projekt        # pull the latest version
/plugin uninstall projekt-skills@3xa-projekt  # remove the plugin
```

### Troubleshooting (install)

| Symptom | Fix |
| --- | --- |
| `/plugin install` says the marketplace is unknown | Run `/plugin marketplace add valfiguer/Projekt-Skills` first; the install uses `@3xa-projekt`, the **marketplace** name, not the repo. |
| Plugin installed but skills never trigger | Confirm it shows **enabled** in `/plugin`. Then check your token resolves: `bash skills/projekt/scripts/auth_check.sh` (or just ask Claude to "connect my Projekt org"). |
| `jq: command not found` / `python3: command not found` | Install the missing tool (`brew install jq` / `brew install python` on macOS) and reopen Claude Code so the new `PATH` is picked up. |
| `401 Unauthorized` on first call | Token missing, expired, or malformed. Re-check [Setup](#setup--your-personal-access-token-pat); a valid token starts with `pjk_live_`. |

---

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

---

## Safety (read this)

- **Dry-run by default.** Every mutating action prints a payload/diff table and writes nothing until you pass `--apply`.
- **Destructive & sensitive actions** (DELETE, `admin/*`, `finance/*`, `payroll/*`) require a **second explicit confirmation** beyond `--apply`.
- **Your token never leaks.** It is sent only in request headers and logged only as a fingerprint — never printed, never written to the ledger, never committed (`.gitignore` blocks `auth.json`, `*.token`, `.projekt-run/`).
- **Idempotent & resumable.** Bulk runs dedupe and can resume from an append-only ledger in `.projekt-run/`.
- **Org-scoped.** Writes are pinned to one `X-Org-Id`; cross-org shared reads never become write targets.

---

## How it stays token-cheap

- The **1.3 MB OpenAPI spec never enters context.** A bundled `spec_lookup.sh` prints a single endpoint block on demand; the 90% case is covered by a hand-curated cheatsheet.
- **Connect once:** auth + org + project/member roster resolve a single time and cache to `.projekt-run/context.json` for all name→id resolution.
- **Slim at the edge:** API responses are projected down to a few fields with `jq` before Claude ever sees them.
- **Math is deterministic:** roll-ups, reports and docs are built by bundled scripts; the model is spent only on genuinely new narrative.

---

## 📚 Documentation

Full project wiki under [`docs/`](docs/README.md) — installation, configuration, architecture, a page per skill, the API cheatsheet, safety model, troubleshooting and a Spanish quick-guide. Start at [`docs/README.md`](docs/README.md).

## Links

- Projekt developer docs: <https://projekt.3xa.es/developers/>
- OpenAPI spec: <https://projekt.3xa.es/openapi.yaml>
- Spanish recipes / recetas: [`skills/projekt/references/recetas-es.md`](skills/projekt/references/recetas-es.md)

## License

MIT © 3XA Design — see [LICENSE](LICENSE).

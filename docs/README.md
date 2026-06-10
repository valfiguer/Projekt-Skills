# Projekt-Skills Wiki

**Projekt-Skills** is a [Claude Code](https://code.claude.com) plugin that connects your **[Projekt](https://projekt.3xa.es)** organization and automates **issues, documentation, workloads, estimations and time tracking** through the Projekt REST API — sequentially, professionally, and with maximum token efficiency.

One plugin, six skills (namespaced `projekt-skills:*`), driven by your own Personal Access Token. **Dry-run by default**: nothing is written until you confirm with `--apply`.

> 🇪🇸 ¿Prefieres español? → **[Guía rápida (Español)](Guia-rapida-Espanol.md)**

---

## Start here

| If you want to… | Go to |
| --- | --- |
| Install the plugin in Claude Code | **[Installation](Installation.md)** |
| Set up your token (PAT) | **[Configuration](Configuration.md)** |
| Understand how it works internally | **[Architecture](Architecture.md)** |
| Stay safe (dry-run, guard hook, secrets) | **[Safety & Security](Safety-and-Security.md)** |
| Fix an error / read the retry policy | **[Errors & Troubleshooting](Errors-and-Troubleshooting.md)** |

## The six skills

| Skill | Page | Does |
| --- | --- | --- |
| **`projekt`** | [projekt (orchestrator)](Skill-projekt.md) | Owns the `CONNECT → DISCOVER → PLAN → CREATE → ASSIGN → ESTIMATE → TIME → DOCUMENT → REPORT` pipeline. Start here. |
| **`projekt-issues`** | [projekt-issues](Skill-projekt-issues.md) | Bulk-create issues from CSV/text, assign owners, batch status moves. |
| **`projekt-estimate`** | [projekt-estimate](Skill-projekt-estimate.md) | Fill estimates (points→hours), roadmap, plan-vs-actual roll-ups. |
| **`projekt-workload`** | [projekt-workload](Skill-projekt-workload.md) | Read-only team capacity & workload reports. |
| **`projekt-time`** | [projekt-time](Skill-projekt-time.md) | Batch-log time, drive timers, time roll-ups. |
| **`projekt-docs`** | [projekt-docs](Skill-projekt-docs.md) | UPSERT project docs, regenerate issue logbooks, export PDFs. |

## Reference

- [API Endpoints](API-Endpoints.md) — the automation-core cheatsheet + full-surface lookup.
- [Estimation Units](Estimation-Units.md) — story-points → hours, AI flagging.
- [Contributing](Contributing.md) — repo layout, the spec-drift CI, local dev.
- [FAQ](FAQ.md) — quick answers.
- [Changelog](Changelog.md) — version history.

## At a glance

- **Token-cheap by design.** The 1.3 MB OpenAPI spec never enters context; API reads are slimmed with `jq` before Claude sees them; math is done by bundled scripts. See [Architecture](Architecture.md).
- **Safe by default.** Every mutation is a dry-run until `--apply`; destructive/sensitive paths need a second `--admit`; a `PreToolUse` hook blocks them belt-and-suspenders. See [Safety & Security](Safety-and-Security.md).
- **Idempotent & resumable.** Bulk runs dedupe and resume from an append-only ledger in `.projekt-run/`.

---

_Current version: **0.2.1** · MIT © 3XA Design · [GitHub repo](https://github.com/valfiguer/Projekt-Skills)_

# Projekt-Skills Wiki

**Projekt-Skills** is a [Claude Code](https://code.claude.com) plugin that connects your **[Projekt](https://app.projektrepublic.com)** organization and automates **issues, documentation, workloads, estimations and time tracking** through the Projekt REST API — sequentially, professionally, and with maximum token efficiency.

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

## The skill pages

(One page per skill. `pr-docs` ships in the plugin but has no page yet — its `SKILL.md` documents it.)

| Skill | Page | Does |
| --- | --- | --- |
| **`pr`** | [pr (orchestrator)](Skill-pr.md) | Connect, cache the context, then create/assign/move tasks in bulk, log time and drive the timer. Start here. |
| **`pr-informes`** | [pr-informes](Skill-pr-informes.md) | Workload & capacity, planned-vs-actual, sprint stats, roadmap, and filling missing estimates. Read-only except `estimate --apply`. |
| **`pr-docs`** | [pr-docs](Skill-pr-docs.md) | Documents (markdown UPSERT by title), a task's activity feed, the org export, and the AI-context store. |
| **`pr-tokens`** | [pr-tokens](Skill-pr-tokens.md) | Measure a session's real token cost from the local transcripts, install the context rules, size the MCP catalogue. |

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

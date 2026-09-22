# Projekt-Skills

**English** · [Español](README.es.md)

> A [Claude Code](https://code.claude.com) plugin that lets you connect your **[Projekt](https://app.projektrepublic.com)** organization and automate **issues, documentation, workloads, estimations and time tracking** through the Projekt REST API — sequentially, professionally, and with maximum token efficiency.

---

## What you get

One plugin, four skills (namespaced `projekt-skills:*`):

| Skill | Does |
| --- | --- |
| **`pr`** | The orchestrator: connect, cache the context, then create/assign/move tasks in bulk and log time or drive the timer. The default entry point — start here. |
| **`pr-informes`** | Read-only reports: per-member workload and capacity, planned-vs-actual hours, sprint stats and burndown, the org roadmap — plus filling missing estimates. |
| **`pr-docs`** | Documents (title-keyed UPSERT of plain markdown, nested pages), a task's activity feed, the org export, and Projekt as an AI-context store: mirror the repo's memories into documents and load them back as one bundle. |
| **`pr-tokens`** | Measure what a session really costs (from the local transcripts — no API call), install the context rules into `CLAUDE.md`, and size the MCP catalogue by domain. |

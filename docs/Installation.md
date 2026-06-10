# Installation

Installing Projekt-Skills is two commands typed **inside Claude Code**. It takes under a minute.

## Requirements

These must be on your `PATH` (everything else is pure stdlib — no `yq`/`pyyaml` needed):

| Tool | Why |
| --- | --- |
| `bash` | runs the shell helpers (`auth_check.sh`, `context_sync.sh`, `spec_lookup.sh`, the HTTP layer) |
| `curl` | makes the HTTPS calls to the Projekt API |
| `jq` | slims API responses before they reach the model |
| `python3` (3.10+) | runs the per-skill task scripts |

Check them all at once:

```bash
command -v bash curl jq python3
```

Missing one? On macOS: `brew install jq` / `brew install python`. On Debian/Ubuntu: `sudo apt install jq python3 curl`.

## 1 — Add the marketplace and install

Open Claude Code (terminal, desktop app, or IDE extension). In the **prompt box**, type a slash — `/` — to bring up commands, then run these **two lines one at a time** (press Enter after each; let the first finish before the second):

```text
/plugin marketplace add valfiguer/Projekt-Skills
/plugin install projekt-skills@3xa-projekt
```

> ⚠️ These are **Claude Code slash-commands**, typed in the chat prompt — *not* shell commands. Don't paste them into a terminal/bash.

Prefer clicking? Type `/plugin` on its own to open the plugin browser, pick **3xa-projekt → projekt-skills**, and hit install.

### What each piece means

| Token | Meaning |
| --- | --- |
| `valfiguer/Projekt-Skills` | the **GitHub repo** that hosts the marketplace (used by the `add` step) |
| `projekt-skills` | the **plugin** name |
| `3xa-projekt` | the **marketplace** name (defined in `.claude-plugin/marketplace.json`) |

The `plugin@marketplace` syntax (`projekt-skills@3xa-projekt`) is required for the `install` step.

## 2 — Verify it loaded

```text
/plugin
```

You should see **`projekt-skills`** (v0.2.1) listed and **enabled**, exposing the six `projekt-skills:*` skills. If it isn't there, see [Troubleshooting](#troubleshooting) below.

## 3 — Set your token

The plugin does nothing until it has **your** Projekt Personal Access Token. → **[Configuration](Configuration.md)**.

## 4 — Use it

Ask Claude in plain language:

> _"Connect my Projekt org and plan a sprint from this backlog."_

The `projekt` skill auto-activates and walks the [pipeline](Skill-projekt.md#the-pipeline). Everything is **dry-run by default** — nothing is written until you confirm.

## Update / remove

```text
/plugin marketplace update 3xa-projekt        # pull the latest version
/plugin uninstall projekt-skills@3xa-projekt  # remove the plugin
```

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `/plugin install` says the marketplace is unknown | Run `/plugin marketplace add valfiguer/Projekt-Skills` first; install uses `@3xa-projekt`, the **marketplace** name, not the repo. |
| Plugin installed but skills never trigger | Confirm it shows **enabled** in `/plugin`. Then check your token resolves — ask Claude to "connect my Projekt org", or run `bash skills/projekt/scripts/auth_check.sh`. |
| `jq: command not found` / `python3: command not found` | Install the missing tool, then reopen Claude Code so the new `PATH` is picked up. |
| `401 Unauthorized` on first call | Token missing, expired, or malformed. See [Configuration](Configuration.md); a valid token starts with `pjk_live_`. |
| `403` on a call you expected to work | Cross-org: a PAT is bound to one organization. See [Errors & Troubleshooting](Errors-and-Troubleshooting.md). |

Next: **[Configuration](Configuration.md)** →

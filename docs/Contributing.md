# Contributing

## Repo layout

```
Projekt-Skills/
├─ .claude-plugin/
│  ├─ marketplace.json     # marketplace "3xa-projekt" → plugin entry
│  └─ plugin.json          # plugin "projekt-skills" metadata (v0.2.1)
├─ skills/
│  ├─ projekt/             # orchestrator: SKILL.md + scripts/ + references/ + assets/
│  │  ├─ scripts/          # auth_check, context_sync, spec_lookup, lib/http.sh, lib/projekt_api.py, …
│  │  ├─ references/       # endpoints.md, domains.md, errors.md, units.md, auth-setup.md, recetas-es.md
│  │  └─ assets/           # slim.jq, points_hours.json, import_template.csv
│  ├─ projekt-issues/      # SKILL.md + scripts/{bulk_issue_create,assign_and_move}.py
│  ├─ projekt-estimate/    # SKILL.md + scripts/estimate_rollup.py
│  ├─ projekt-workload/    # SKILL.md + scripts/workload_report.py
│  ├─ projekt-time/        # SKILL.md + scripts/time_log.py
│  └─ projekt-docs/        # SKILL.md + scripts/doc_generator.py
├─ hooks/
│  ├─ hooks.json           # PreToolUse(Bash) → guard.sh
│  └─ guard.sh             # blocks sensitive API writes without --admit
├─ scripts/check_drift.sh  # CI: asserts cheatsheet core paths still exist in the live spec
├─ .github/workflows/spec-drift-check.yml
├─ api-spec/               # spec is fetched on demand here; .gitignored (never committed)
├─ README.md / README.es.md
├─ CHANGELOG.md
└─ LICENSE
```

## Design invariants (don't break these)

- **The 1.3 MB spec never enters context.** Use `spec_lookup.sh`; never `cat` the spec into a prompt. The spec and its index are git-ignored.
- **Dry-run by default.** Any new mutating path must print a plan and require `--apply`; sensitive paths require `--admit`.
- **Connect once.** Read `.projekt-run/context.json` for name→id; never re-query identity mid-run.
- **Slim at the edge.** New reads go through `slim.jq` (add a view if needed) — full objects don't reach the transcript.
- **Math is deterministic.** Roll-ups/reports are computed by scripts, not the model.
- **Secrets never leak.** Token only in headers, logged as a fingerprint. Keep `.gitignore` covering `auth.json`, `*.token`, `*.pat`, `.env*`, `.projekt-run/`.

## Spec-drift CI

`.github/workflows/spec-drift-check.yml` runs `scripts/check_drift.sh`, which:

1. Fetches the live spec (`PROJEKT_SPEC_URL`, default `https://projekt.3xa.es/openapi.yaml`).
2. Asserts each **core path** (the 16 the cheatsheet relies on — `/me`, `/projects`, `/issues`, `/issues/bulk`, `/workload`, `/ai/suggest-estimation`, the time-entry/summary paths, etc.) still exists.
3. Exits non-zero (listing missing paths) on drift, so `references/endpoints.md` never silently rots.

Run it locally before a PR that touches endpoints:

```bash
bash scripts/check_drift.sh
```

## Adding / changing endpoints

1. Confirm the real shape: `bash skills/projekt/scripts/spec_lookup.sh "/the/path" <method>`.
2. Update `skills/projekt/references/endpoints.md` (and [API Endpoints](API-Endpoints.md) here if you keep the wiki in sync).
3. If it's a core path the cheatsheet depends on, add it to `CORE_PATHS` in `scripts/check_drift.sh`.

## Versioning & releases

- Semantic Versioning. Bump `version` in **both** `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`.
- Add a `CHANGELOG.md` entry (and mirror it on the [Changelog](Changelog.md) wiki page).
- Commit convention: `type(scope): description` (e.g. `fix(cli): …`, `chore(estimate): …`).

## Local testing tips

- All write paths are dry-run first — verify the printed plan before `--apply`.
- Use a throwaway project for live `--apply` checks, then hard-delete it (that's how 0.2.0 was verified — see [Changelog](Changelog.md)).
- The ledger (`.projekt-run/*.jsonl`) lets you interrupt and resume; delete it to force a clean run.

See also: [Architecture](Architecture.md).

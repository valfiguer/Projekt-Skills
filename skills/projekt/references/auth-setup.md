# Auth setup — your Personal Access Token

The plugin acts **as you** in **one** organization using a Projekt PAT. Never bundled, never committed.

## 1. Mint a key
Projekt → **Organization → Settings → General → Integraciones** → **Create API key**.
- Format: `pjk_live_` + 32 chars. Shown once — copy it.
- Carries your full role (owner/admin/manager/member/viewer). **No per-endpoint scoping** — treat it
  like a password. Max 20 active keys/user/org; revoke instantly from the same screen.
- Docs: <https://projekt.3xa.es/developers/auth.html#pat>

## 2. Provide it (precedence: env > file)
```bash
# Option A — environment (best for CI / multiple accounts)
export TREXA_API_TOKEN="pjk_live_…"
export TREXA_API_BASE="https://projekt.3xa.es/api/v1"  # optional, this is the default
export TREXA_ORG_ID="<uuid>"                            # optional; else self-discovered from /auth/me
export TREXA_PROJECT_ID="<uuid>"                        # optional; else the key's own project scope
```
```jsonc
// Option B — ~/.config/3xa-projekt/auth.json  (shared with the Projekt MCP)
{ "token": "pjk_live_…", "api_base": "https://projekt.3xa.es/api/v1" }
```

The API is the **rewritten `/api/v1`**: org + project live in the URL path, and a PAT
**self-discovers** its org + project from `GET /auth/me` (`api_key.organization_id` /
`api_key.project_id`). A project-scoped key is limited to that one project.

## 3. Verify
```bash
bash "${CLAUDE_SKILL_DIR}/scripts/auth_check.sh"
```
Calls `GET /auth/me`, prints your user + the key's discovered org (and project scope if the key is
project-scoped), writes `.projekt-run/context.json`, and shows only a token **fingerprint**
(`pjk_live_…abcd`) — never the secret.

## Headers (handled for you by `lib/http.sh`)
`Authorization: Bearer <pat>` + `X-Auth-Token: <pat>` (proxy fallback) + `X-Org-Id: <org>`. On the
rewrite the server reads org + project from the **URL path**, so `X-Org-Id` is a harmless no-op; the
scripts put org + project in the path.

## If it fails
- *No token* → set env or create the file above.
- *No org resolved* → the PAT's `/auth/me` returned no `api_key` scope; set `TREXA_ORG_ID`, or mint a
  fresh key (the rewrite attaches org/project scope to every PAT).
- *401/403* → token invalid/expired/revoked, or the key isn't scoped to the org/project you're hitting.
  Mint a fresh key.

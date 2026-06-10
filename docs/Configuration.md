# Configuration — your Personal Access Token (PAT)

The plugin talks to Projekt **as you**, in **one** organization, using your own PAT. The token is **never bundled** with the plugin and **never committed** to git.

## 1 — Mint a key

In Projekt, go to **Organization → Settings → General → Integraciones** and click **Create API key**.

- Format: `pjk_live_` + 32 characters. **Shown once** — copy it immediately.
- It carries your **full role** (owner / admin / manager / member / viewer). There is **no per-endpoint scoping** — treat it like a password.
- Max **20 active keys** per user per org. Revoke instantly from the same screen.
- Docs: <https://projekt.3xa.es/developers/auth.html#pat>

## 2 — Provide it to the plugin

Two ways. **Environment wins over file** if both are present.

### Option A — Environment (best for CI / multiple accounts)

```bash
export TREXA_API_TOKEN="pjk_live_…"
export TREXA_API_BASE="https://projekt.3xa.es/api"   # optional — this is the default
export TREXA_ORG_ID="<uuid>"                          # optional — else current org from /me
```

### Option B — File (shared with the Projekt MCP)

`~/.config/3xa-projekt/auth.json`:

```json
{ "token": "pjk_live_…", "api_base": "https://projekt.3xa.es/api" }
```

## 3 — Verify

```bash
bash skills/projekt/scripts/auth_check.sh
```

It prints your user, org and role, writes `.projekt-run/context.json`, and shows only a token **fingerprint** (`pjk_live_…abcd`) — never the secret. Or just ask Claude to *"connect my Projekt org"* and the `projekt` skill runs this for you.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `TREXA_API_TOKEN` | — | Your PAT. Highest-precedence source. |
| `TREXA_API_BASE` | `https://projekt.3xa.es/api` | API base URL. Override only for staging/self-host. |
| `TREXA_ORG_ID` | current org from `/me` | Pin a specific organization (UUID). |

## Headers (handled for you)

`lib/http.sh` injects every authenticated call with:

- `Authorization: Bearer <pat>`
- `X-Auth-Token: <pat>` — LiteSpeed/proxy fallback
- `X-Org-Id: <org>`

You never set these yourself.

## Pinning an organization

A PAT is bound to **one** organization. By default the plugin uses your *current* org from `GET /me`. To pin a different one, set `TREXA_ORG_ID="<uuid>"`. Calling a resource that belongs to another org returns **403** — that's expected, not a bug (see [Errors & Troubleshooting](Errors-and-Troubleshooting.md)).

## If it fails

| Problem | Fix |
| --- | --- |
| *No token* | Set `TREXA_API_TOKEN` or create `~/.config/3xa-projekt/auth.json`. |
| *No org resolved* | Set `TREXA_ORG_ID`, or switch your current org in Projekt. |
| *401 / 403* | Token invalid / expired / revoked, or wrong org. Mint a fresh key. |

See also: [Safety & Security](Safety-and-Security.md) for how the token is protected.

Next: **[Architecture](Architecture.md)** →

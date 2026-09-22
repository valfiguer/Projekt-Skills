# Full-surface domain map

The Projekt API exposes **800+ paths**. The automation core lives in `endpoints.md`; everything else is
reachable via `spec_lookup.sh`. This map tells you which search term to use — then read ONE block:

```bash
bash "$SK/spec_lookup.sh" --search "<term>"     # list matching paths from the index
bash "$SK/spec_lookup.sh" "/exact/path" [method] # print that block only
```

⚠️ Anything under **admin / finance / payroll / tax / gl / consolidation / gdpr** is sensitive: state the
blast radius and require a second confirmation before any write (see `errors.md` + the SKILL guardrails).

| Domain (search term) | What's there |
|---|---|
| `projects` | Projects, board columns, sprints, roadmap, members, settings (51 paths). |
| `issues` | Issues, comments, bitácora, dependencies, attachments, export. |
| `me` · `team` · `org` · `orgs` | Identity, roster, org settings, invites, switching. |
| `mywork` · `timesheets` · `time-reports` · `schedules` | Personal queue, timesheets, schedules. |
| `workforce` · `capacity` · `dashboard` | Capacity per member (`/workforce/capacity`) and org counters (`/dashboard/stats`). The old flat `/workload` and `/capacity` are gone. |
| `docs` (under `projects`) · `doc-archive` | Project docs (EditorJS) + archived document store. |
| `clients` · `crm` · `crossorg` | Clients, CRM pipeline, cross-org sharing. |
| `invoices` · `arap` · `finance` · `gl` · `budgets` | Invoicing, AR/AP, finance, general ledger, budgets. 🔒 |
| `expenses` · `approvals` · `purchase-orders` | Expenses, approval flows, POs. 🔒 |
| `payroll` · `payroll-v2` · `leave` · `employees` | Payroll, leave, employee records. 🔒 PII |
| `contracts` · `compliance` · `gdpr` | Contracts, compliance, GDPR/data requests. 🔒 |
| `tax-multi` · `consolidation` · `finint` | Multi-jurisdiction tax, consolidation, finance integrations. 🔒 |
| `inventory` · `assets` | Inventory, fixed assets. |
| `supplier-portal` · `addons` · `webhooks` | Supplier portal, add-ons, webhooks. |
| `bi` · `ai` | BI/analytics, AI endpoints (rate bucket `ai`, daily quota). |
| `admin` | Org administration (44 paths). 🔒 highest privilege. |
| `auth` · `push` · `github` · `settings` · `integrations` | Auth, push, GitHub, settings, integrations. |

Counts drift as the API grows — `spec_lookup.sh --search <term>` is always the source of truth.
If the cheatsheet and a lookup disagree, trust the lookup (and the CI drift check will flag it).

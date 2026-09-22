# Changelog

All notable changes to **projekt-skills** are documented here.
This project adheres to [Semantic Versioning](https://semver.org/).

## [1.1.0] — 2026-09-22

### Added — el catálogo completo, generado

El plugin ya no cubre «una parte del API y el resto búscatelo». Ahora hay un mapa de todo,
y una forma segura de llamar a cualquier cosa del mapa.

- **`skills/pr/references/catalogo.md`** — **685 paths · 917 operaciones · 16 dominios**, con
  cuántas son sensibles y cuántas cubre ya un script `pr-*` (80). Lo **genera**
  `scripts/catalogo.py` desde el spec: no se teclea, así que no se pudre. La doc anterior sí
  se pudrió, hasta el punto de que cinco de las ocho skills apuntaban a endpoints muertos.
- **`scripts/llamar.py`** — llama a cualquiera de las 917. Valida ruta y método contra el spec
  **antes de enviar** (una ruta mal escrita falla en local, con sugerencias, en vez de dar un
  404 que luego hay que depurar), es dry-run para todo lo que no sea GET, **rechaza las
  operaciones sensibles y todo `DELETE` sin `--admit`**, y trunca la respuesta a 4.000
  caracteres porque un listado volcado en la transcripción se paga en cada turno posterior.
- **`spec_lookup.sh` gana filtros**: `--domains`, `--domain <d>`, `--tag <t>`, `--sensitive`,
  `--uncovered`. El índice pasa de 3 a 8 columnas (método, ruta, dominio, perfil, sensible,
  tags, script que la cubre, resumen): 917 líneas, 84 kB, para grepear, nunca para leer.

De las 917 operaciones, **358 llevan `x-tool`** (las que el conector MCP puede exponer) y
**128 están marcadas sensibles**. Las otras **559 no tienen `x-tool`**: funcionan por HTTP
igual que el resto, pero son invisibles para el catálogo del MCP, para la selección por perfil
y para Kern. El catálogo las lista aparte, por tag, para que se vea qué falta anotar.

### Fixed

- `llamar.py` construía `/api/v1/api/v1/…`: los paths del spec ya traen el prefijo y la base
  del cliente también. Daba un 404 que se leía como «ese endpoint no existe».
- `references/domains.md`, escrito a mano y ya desfasado, se retira: lo sustituye el catálogo
  generado.

### Nota sobre de dónde sale el `x-tool`

`fetch_spec.sh` descarga de `developers.projektrepublic.com/openapi.json` **a propósito**. El
spec que sirve FastAPI (`api.projektrepublic.com/api/openapi.json`) tiene los mismos 685 paths
pero **cero `x-tool`** — FastAPI descarta la extensión. Un catálogo construido desde ahí no
tendría dominios ni sensibilidad: 16 columnas vacías.

## [1.0.0] — 2026-09-22

Dos cambios que rompen: el host y los nombres de las skills. Y un tercero que no rompe pero
importa más: **cinco de las ocho skills apuntaban a endpoints que ya no existen**.

### Changed — el host es Projekt Republic

`projekt.3xa.es` ya no es el producto. Las 44 referencias del repo pasan a los hosts reales,
verificados uno a uno contra producción:

| Para | Antes | Ahora |
| --- | --- | --- |
| API | `https://projekt.3xa.es/api/v1` | `https://api.projektrepublic.com/api/v1` (`/health` → 200) |
| Spec | `…/openapi.yaml` | `https://developers.projektrepublic.com/openapi.json` (685 paths) |
| Portal | `…/developers/` | `https://developers.projektrepublic.com/developers` |
| UI | `https://projekt.3xa.es` | `https://app.projektrepublic.com` |
| MCP | `https://mcp.projektrepublic.com/mcp` | `https://app.projektrepublic.com/mcp` — el anterior **no resolvía** (DNS, código 000) |

### Changed — ocho skills pasan a cuatro, con prefijo `pr-`

`pr` (antes `projekt` + `projekt-issues` + `projekt-time`) · `pr-informes` (antes
`projekt-workload` + `projekt-estimate`) · `pr-docs` (antes `projekt-docs` +
`projekt-context`) · `pr-tokens`.

El motivo es medible. La descripción de cada skill vive en el contexto **en cada turno**; el
cuerpo solo se carga al invocarla. Ocho entradas para una sola API se pagaban 8 veces por turno:

| | Antes | Ahora | |
| --- | --- | --- | --- |
| Frontmatter (cada turno) | 5.382 B · ~1.345 tok | **2.177 B · ~544 tok** | −60 % |
| Cuerpos (al invocar) | 48.700 B | **17.567 B** | −64 % |

Lo que se fue: el `Soporta español:` de las ocho descripciones (1.344 B, el 25 % del
frontmatter — el emparejador ya dispara en español por el cuerpo), el bloque
`What it does NOT do` repetido en seis skills (7.565 B → `references/limits.md`) y el párrafo
`Prerequisite` repetido en seis variantes (2.638 B → una línea).

### Fixed — lo que las skills afirmaban y el API no hacía

Verificado contra el contrato y el servicio, no contra las notas anteriores:

- **`POST …/tasks` sí acepta `assignee_id`** (y `story_points`, `estimated_hours`, `sprint_id`,
  las fechas). El baile «crear y luego PATCH del responsable» sobraba. `status` es el único
  campo ausente del create.
- **No existe la regla «una tarea necesita responsable para salir de `todo`»**. Era una
  invención heredada: no está ni en el contrato ni en `tasks/service.py`. El 422 real de un
  movimiento es el **`wip_limit`** de la columna destino, y solo en columnas que lo fijan.
- **`Document.content` es markdown plano.** No hay EditorJS, ni campo `blocks`, ni
  `?format=markdown`. Toda la prosa sobre bloques se ha ido.
- **Los documentos son de ORGANIZACIÓN**, no de proyecto: el proyecto es un campo.
- **Las imputaciones de tiempo son de ORGANIZACIÓN**, con `minutes` y `entry_date` (no
  `duration_minutes`/`date`), y hay **un solo temporizador por usuario**: el segundo `start`
  devuelve `409 timer_already_running`.
- **No existe `/ai/suggest-estimation`.** `pr-informes estimate` ya no pide puntos a un
  modelo: convierte los que puso una persona y, si no hay, usa la mediana de las tareas
  hermanas — diciendo siempre cuál de las dos usó.
- **`/workload`, `/capacity` y `/capacity/threshold` no existen.** Los sustituyen
  `/workforce/capacity`, `/dashboard/stats` y `/time-entries/summary`.
- **`roadmap` es de solo lectura**: `GET /organizations/{org}/roadmap` no tiene POST.
- **No hay export a PDF de tareas**, ni «bitácora» regenerable por IA: bitácora es ahora el
  feed de actividad de una tarea, en solo lectura.
- **`spec_index.sh` y `spec_lookup.sh` parseaban YAML con awk.** El spec servido es JSON, así
  que devolvían vacío en silencio. Reescritos sobre JSON: 685 paths indexados y verificados.
- **El hook de arranque apuntaba a `skills/projekt-tokens/`** y se habría quedado mudo tras el
  renombrado.

### El trampantojo del rango (nuevo, documentado en `pr-informes`)

De los tres agregados del informe de cargas, **solo uno acepta fechas**:
`/workforce/capacity` no tiene parámetros y siempre responde por la semana en curso;
`/dashboard/stats` tampoco los tiene y sus contadores son de **todo el histórico**; solo
`/time-entries/summary` honra `from`/`to`. El informe rotula cada columna con el periodo que
de verdad cubre y marca con `*` las que son históricas.

### Nota sobre el marcador de `pr-tokens`

`<!-- projekt-tokens:inicio -->` **no cambia** con el renombrado. Es un contrato con los
`CLAUDE.md` que ya lo tienen instalado: renombrarlo dejaría el bloque viejo huérfano y
añadiría uno nuevo debajo.

## [0.5.0] — 2026-09-22

### Added — `pr-tokens`: medir lo que cuesta una sesión, y bajarlo

Skill nueva más dos hooks. Nace de una medición, no de una intuición: sobre **18 sesiones
reales de Claude Code (30.319 turnos)**, el reparto de tokens es

```
entrada                 106.209   0,0 %
escritura de caché  293.100.824   2,0 %
LECTURA DE CACHÉ 14.537.908.034  97,8 %
salida               34.913.098   0,2 %
```

O sea que **lo que se paga no es lo que entra, sino lo que entra multiplicado por los
turnos que quedan**: la conversación entera se reenvía en cada turno. En las sesiones
grandes eso son 489k-550k tokens de lectura *por turno*. De los 16,77 M de caracteres que
devolvieron las herramientas, el 82,6 % los devolvió `Bash` (sed 17,4 · grep 10,2 · cat
4,2), y los resultados de ≥10.000 caracteres son el 0,7 % de las llamadas y solo el 12,8 %
de los bytes: no hay un monstruo, son mil cortes. Por eso el catálogo del MCP —que viaja
una vez por sesión y va cacheado— es el tercer comando de la skill y no el primero.

- **`skills/pr-tokens/scripts/medir.py`** — los cuatro cubos que se facturan, la
  lectura por turno, la peor sesión, qué herramienta llenó el contexto, las familias de
  comando dentro de `Bash` y los tres volcados más gordos con su comando. Sale todo de
  `~/.claude/projects/<proyecto>/*.jsonl`: **no llama a ninguna API ni gasta un token**.
  `--breve`, `--json`, `--todas`, `--proyecto`, `--max-mb`.
- **`skills/pr-tokens/scripts/instalar.py`** — mete las ocho reglas de contexto en el
  `CLAUDE.md` del repo, entre marcas e idempotente (dry-run por defecto, `--apply` para
  escribir, `--quitar` para retirarlas). Es la pieza que hace que la disciplina dure más
  que la invocación de la skill: una skill solo está en contexto cuando se la llama, y
  esto se decide en cada llamada.
- **`skills/pr-tokens/scripts/perfil_mcp.py`** — de una tarea a `?tools=<dominios>`
  del conector, con bytes y tokens de cada perfil. Dice cuándo pedir dominios sale **más
  caro** que `core`, que es la mitad que nadie cuenta.
- **`skills/pr-tokens/tarifas.json`** — tarjeta de tarifas fechada ($/MTok) con los
  multiplicadores de caché (escritura 1,25x, lectura 0,1x). Rotulada como equivalencia:
  una suscripción paga en límite de uso, no en dólares.
- **`hooks/presupuesto_al_arrancar.sh`** (`SessionStart`) — dos líneas al arrancar con la
  lectura por turno de la sesión anterior, y un aviso al pasar de 200.000. ~0,1 s.
- **`hooks/aviso_de_tokens.sh`** (`PreToolUse` sobre `Bash`) — caza `cat` sin tope,
  búsquedas recursivas sin `-l`/`-c`, `git log` sin `-n`, `git diff` entero y `find`/`ls -R`
  sueltos. **Por defecto solo APUNTA** a un registro y deja pasar: bloquear cuesta un
  turno, y un turno en una sesión cargada cuesta más que el volcado que evita.
  `PROJEKT_TOKENS_ESTRICTO=1` lo endurece; `PROJEKT_TOKENS_SIN_AVISO=1` apaga los dos.
- **`docs/Skill-pr-tokens.md`** — la página de la skill, con la tabla de la medición.

### Fixed

- Los dos README decían «seis skills» y ya eran siete: faltaba `pr-docs`. Ahora
  son ocho y están las dos que faltaban.

## [0.4.0] — 2026-07-13

Port to the rewritten **`/api/v1`** org-scoped API. `projektrepublic.com` replaced its legacy flat PHP API
with a contract-first rewrite: base is now `https://api.projektrepublic.com/api/v1`, **org + project live in the
URL path** (no more `X-Org-Id`-header + `project_id` query param), and the core resource is **`tasks`**
instead of `issues`. The old skill broke entirely; this restores **CONNECT + REGISTER TASKS** end-to-end.

### Changed
- **Base URL** `…/api` → `…/api/v1` everywhere (`lib/http.sh`, `lib/projekt_api.py`, `references/auth-setup.md`, `references/endpoints.md`).
- **Auth / self-discovery.** `auth_check.sh` now calls `GET /auth/me` and reads the PAT's own scope from
  the response `api_key` object (`{id, name, organization_id, project_id}`) to self-discover the org **and**
  project — a project-scoped key needs no config. Falls back to `GET /organizations` for the org when
  `api_key` is absent (cookie/older key). `context.json` gains `project_id` + `key_name`.
- **Context sync.** `context_sync.sh` uses `GET /organizations/{org}/projects` and
  `GET /organizations/{org}/members`; a project-scoped key (which gets 403 listing projects) falls back to
  a single-project context from the self-discovered `project_id`.
- **Task creation (`pr`).** `bulk_issue_create.py` now `POST`s to
  `/organizations/{org}/projects/{proj}/tasks` and sweeps `GET …/tasks` for dedupe. Because the rewrite's
  create body has **no `assignee_id`** (a task is born `todo`), assignee + any working status are applied
  via a follow-up `PATCH …/tasks/{id}`. Statuses normalized to `todo|in_progress|done|cancelled`; the
  assignee-required rule now means "can't advance out of `todo` without an owner".
- **Terminology** issues → tasks across the ported skill + endpoint cheatsheet.

### Not yet ported (base URL fixed, endpoint paths still legacy — flagged with a TODO in each SKILL.md)
- `pr-informes`, `pr`, `pr-informes`, `pr-docs`, `pr-docs`, and
  `pr`'s `assign_and_move.py` still call legacy flat paths (`/issues`, `/workload`,
  `/projects/{pid}/docs`, `/ai/suggest-estimation`, …) and will 404 until re-pathed to the org-scoped
  surface. Each SKILL.md documents the exact rewrite target + the `spec_lookup.sh` term to rediscover it.

## [0.3.0] — 2026-06-21

AI-friendly Markdown round-trip + the AI-context store.

### Added
- **`pr-docs` skill** — use Projekt as a Serena-style AI-context store. `sync` mirrors a memory directory (`*.md`) into a project's docs (one doc per file, title = filename stem, idempotent UPSERT, YAML frontmatter rendered as a clean lead blockquote instead of flattened); `load` reads the tree back as ONE `?format=markdown` bundle, so an agent onboards a codebase in a single cheap call instead of crawling it.

### Changed
- **`pr-docs` is now Markdown-native.** `upsert` sends the body as a `markdown` field and the server's `EditorJsMarkdownConverter::fromMarkdown` builds the blocks — tables, fenced code, callouts and inline formatting now round-trip (previously only header/paragraph/list via a local builder). Read any doc back as Markdown with `?format=markdown` (~half the tokens of raw EditorJS). Requires the Projekt API's doc-create Markdown support (shipped alongside).

## [0.2.1] — 2026-06-07

### Changed
- **Calibrated `points_hours.json`** to the 3XA org's real estimate distribution (428 estimated issues across all projects: median 3 h, p90 10 h — mostly small tasks). The previous Fibonacci defaults (1 pt = 2 h … 21 pt = 96 h) ran ~3× high. New map: 1→1, 2→2, 3→4, 5→8, 8→13, 13→20, 21→40; `default_hours` 8→3. The org records estimates in **hours, not story points** (0 issues carry points), so the table maps AI-suggested points onto that real hours scale; `units.md` documents how to recalibrate. No code change.

## [0.2.0] — 2026-06-07

Hardening after end-to-end write verification.

### Changed
- **Consistent CLI across skills:** every project argument is now `--project` (accepts id / key / name), and `--apply` is always placed **after** the sub-command. Previously `pr-informes` took a positional `project` and `pr-docs` used `--project-id` (UUID-only) with a top-level `--apply` — an inconsistency that was easy to get wrong.

### Verified
- Live `--apply` writes confirmed against the API for every path (issue create, bulk assign+move, estimate PUT, time-entry POST, doc create/update) on a throwaway project, then hard-deleted. No real data touched.

## [0.1.0] — 2026-06-07

Initial public release.

### Added
- Claude Code plugin (`projekt-skills`) distributed via the `3xa-projekt` marketplace.
- Primary orchestration skill **`pr`**: the `CONNECT → DISCOVER → PLAN → CREATE → ASSIGN → ESTIMATE → TIME → DOCUMENT → REPORT` pipeline, endpoint cheatsheet, full-surface spec discovery, and safety guardrails (dry-run default, ledger, destructive-action confirmation, fingerprint-only token logging).
- Task skills: **`pr`**, **`pr-informes`**, **`pr-informes`**, **`pr`**, **`pr-docs`**.
- Shared contract: `lib/http.sh` (dual-auth headers + `X-Org-Id` + rate-limit backoff), `auth_check.sh`, `context_sync.sh`, `spec_lookup.sh` / `spec_index.sh` (the OpenAPI spec never enters context), `run_ledger.sh`, `slim.jq`.
- `spec-drift-check` CI to keep the endpoint cheatsheet in sync with the live spec.

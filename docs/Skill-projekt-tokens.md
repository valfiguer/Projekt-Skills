# Skill: `projekt-tokens`

Measure what a Claude Code session really costs in tokens — from the transcripts already on
your disk, with **no API call and no tokens spent** — then install the rules that cut it and
size the Projekt MCP catalogue by domain. Three scripts: `medir.py`, `instalar.py`, `perfil_mcp.py`.

Soporta español: gasto de tokens, presupuesto de contexto, por qué esta sesión cuesta tanto,
recortar el catálogo del MCP.

No prerequisite: these three commands never touch the Projekt API, so you don't need a PAT or
`projekt/scripts/auth_check.sh` for them.

## The measurement this is built on

Claude Code writes one JSONL per session under `~/.claude/projects/<project>/`, and every
assistant turn carries the exact `usage`. Summed over **18 real sessions, 30,319 turns**
(22/09/2026):

| Bucket | Tokens | Share | Priced at |
| --- | ---: | ---: | --- |
| input | 106,209 | 0.0 % | 1× |
| cache write | 293,100,824 | 2.0 % | 1.25× |
| **cache read** | **14,537,908,034** | **97.8 %** | 0.1× |
| output | 34,913,098 | 0.2 % | its own |

**You don't pay for what enters the context; you pay for what enters it multiplied by the turns
that follow.** The whole conversation is re-sent every turn, so an 8,000-character result at
turn 40 of a 400-turn session is paid 360 times. In the five big sessions that came to
489k–550k cache-read tokens *per turn*.

Who fills it, over 16.77 M characters of tool results: **`Bash` 82.6 %** (sed 17.4 · grep 10.2 ·
cat 4.2), `Read` 2.4 %, MCP ≈ 6 %. And there is no single monster — results of ≥10,000 characters
are 0.7 % of calls and only 12.8 % of the bytes. Death by a thousand cuts.

Two consequences worth stating plainly:

- The MCP tool catalogue travels **once per session** and is cached. It is not the problem it
  looks like — which is why `perfil_mcp.py` is the third command here, not the first.
- The biggest single lever is **fewer turns carrying less context**, and the second is starting a
  fresh session before the per-turn read grows.

## 1. `medir.py` — the baseline

```bash
python3 skills/projekt-tokens/scripts/medir.py                     # current repo, last 10 sessions
python3 skills/projekt-tokens/scripts/medir.py --todas             # whole history
python3 skills/projekt-tokens/scripts/medir.py --proyecto ~/dev/x  # another repo
python3 skills/projekt-tokens/scripts/medir.py --breve             # three lines (what the hook prints)
python3 skills/projekt-tokens/scripts/medir.py --json              # for another program
```

Prints the four buckets with their share, **cache read per turn**, the worst session, the dollar
equivalence at API rates (`tarifas.json`, dated), the five tools that fed the context most, the
command families inside `Bash`, and the three fattest dumps with their command.

`--max-mb N` skips transcripts bigger than N MB (the `SessionStart` hook uses it so startup never
waits). Above **200,000 cache-read per turn** a session costs more per turn than the work it does:
close and reopen, or `/compact`, before starting anything long.

## 2. `instalar.py` — the rules where they are always read

A skill is only in context when invoked; spend is decided on every call. So the eight measured
rules go into the repo's `CLAUDE.md`, between markers, idempotently.

```bash
python3 skills/projekt-tokens/scripts/instalar.py --repo .            # DRY-RUN, shows the diff
python3 skills/projekt-tokens/scripts/instalar.py --repo . --apply
python3 skills/projekt-tokens/scripts/instalar.py --repo . --quitar --apply
```

The block lives in `skills/projekt-tokens/reglas-del-proyecto.md` — read it before installing.
Running twice changes nothing: it replaces between `<!-- projekt-tokens:inicio -->` and `:fin`.

## 3. `perfil_mcp.py` — only the catalogue you need

The Projekt MCP server already exposes a subset: `?tools=finance,crm` on the connector URL, or
`MCP_TOOLS=finance,crm` on stdio. `org` and `search` are always included.

```bash
python3 skills/projekt-tokens/scripts/perfil_mcp.py --tarea "registrar una factura de proveedor"
python3 skills/projekt-tokens/scripts/perfil_mcp.py --dominios finance,crm
python3 skills/projekt-tokens/scripts/perfil_mcp.py --dominios pm --desde-contrato <path>/openapi.json
```

`all` is ~140,000 estimated tokens per `tools/list`; `core` ~31,000. **Two fat domains can cost
more than `core`** — the script says so when it happens, which is the half nobody counts.
Changing the profile needs a client restart so the catalogue is requested again.

## The hooks

| Hook | Event | What it does |
| --- | --- | --- |
| `presupuesto_al_arrancar.sh` | `SessionStart` | Two lines: last session's cache-read per turn and what filled the context; warns above the threshold. ~0.1 s. |
| `aviso_de_tokens.sh` | `PreToolUse` (Bash) | Catches unbounded `cat`, recursive searches without `-l`/`-c`, `git log` without `-n`, whole `git diff`, bare `find`/`ls -R`. |

`aviso_de_tokens.sh` **only takes notes by default** — one line per hit in
`$TMPDIR/projekt-tokens-<user>/incumplimientos.log` — and lets the command through. Blocking costs
a turn, and a turn in a loaded session costs more than the dump it prevents. Let it accumulate for
a few days, read the log (`cut -f2 … | sort | uniq -c`), and only then decide.

| Variable | Effect |
| --- | --- |
| `PROJEKT_TOKENS_ESTRICTO=1` | Blocks (exit 2) instead of noting, with the cheap form in the reason |
| `PROJEKT_TOKENS_SIN_AVISO=1` | Turns both hooks off |
| `PROJEKT_TOKENS_AVISO=<n>` | Moves the cache-read-per-turn warning threshold (default 200,000) |

## What this skill does not do

- **It promises no percentage.** The verdict is a second `medir` a week later, written down even
  when it says nothing went down.
- **It does not measure quality.** The most effective way to spend fewer tokens is to answer
  worse; a cut that forces asking twice cost a turn and saved nothing.
- **It is not an invoice.** On a subscription, tokens are paid in usage limits — the dollar figure
  only orders magnitudes and compares weeks.
- **The numbers above are one repo and one person.** Reproducible here, not a claim about anyone
  else. That is why the first command is `medir`, not `instalar`.

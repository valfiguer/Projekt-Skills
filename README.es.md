# Projekt-Skills

[English](README.md) · **Español**

> Un plugin de [Claude Code](https://code.claude.com) para conectar tu organización de **[Projekt](https://projekt.3xa.es)** y automatizar **incidencias, documentación, cargas de trabajo, estimaciones y tiempos** a través de la API REST de Projekt — de forma secuencial, profesional y con el mínimo gasto de tokens.

---

## Qué incluye

Un plugin, seis skills (con espacio de nombres `projekt-skills:*`):

| Skill | Qué hace |
| --- | --- |
| **`projekt`** | El orquestador. Gobierna todo el flujo `CONECTAR → DESCUBRIR → PLANIFICAR → CREAR → ASIGNAR → ESTIMAR → TIEMPO → DOCUMENTAR → INFORMAR`. Punto de entrada por defecto — empieza aquí. |
| **`projekt-issues`** | Crea y actualiza incidencias en lote (CSV/hoja/texto → backlog), asigna y mueve estados en bloque. |
| **`projekt-estimate`** | Rellena estimaciones, puntos→horas, roadmap y dependencias, plan vs. real. |
| **`projekt-workload`** | Informes de capacidad y carga del equipo (quién está sobrecargado, % de utilización). |
| **`projekt-time`** | Registra tiempos en lote, temporizadores y agregados de tiempo. |
| **`projekt-docs`** | Crea/mantiene documentos del proyecto, regenera bitácoras de incidencias, exporta PDFs. |

---

## Instalación

> **Requisitos primero:** `bash`, `curl`, `jq` y `python3` (3.10+) en tu `PATH`. Sin más dependencias (solo stdlib; no hace falta `yq`/`pyyaml`). Comprueba con `command -v bash curl jq python3`.

### 1 — Añade el marketplace e instala

Abre Claude Code (terminal, app de escritorio o extensión del IDE). En el **cuadro de texto**, escribe una barra — `/` — para ver los comandos, y ejecuta estas **dos líneas de una en una** (pulsa Enter tras cada una; espera a que termine la primera antes de la segunda):

```text
/plugin marketplace add valfiguer/Projekt-Skills
/plugin install projekt-skills@3xa-projekt
```

> Son **slash-commands de Claude Code**, escritos en el chat — *no* son comandos de shell, así que no los pegues en una terminal/bash.

¿Prefieres hacer clic? Escribe solo `/plugin` para abrir el explorador de plugins, elige **3xa-projekt → projekt-skills** y pulsa instalar.

Qué significa cada parte:

- `valfiguer/Projekt-Skills` — el **repo de GitHub** que aloja el marketplace (paso `add`).
- `projekt-skills` — el nombre del **plugin**.
- `3xa-projekt` — el nombre del **marketplace** (definido en `.claude-plugin/marketplace.json`). La sintaxis `plugin@marketplace` es obligatoria en el paso `install`.

### 2 — Verifica que cargó

```text
/plugin
```

Deberías ver **`projekt-skills`** (v0.2.1) en la lista y habilitado, exponiendo las seis skills `projekt-skills:*`. Si no aparece, mira [Resolución de problemas](#resolución-de-problemas-instalación).

### 3 — Configura tu token

El plugin necesita **tu** Token de Acceso Personal de Projekt antes de poder hacer nada — mira [Configuración](#configuración--tu-token-de-acceso-personal-pat) abajo.

### 4 — Úsalo

Pídele a Claude en lenguaje natural, por ejemplo:

> _«Conecta mi organización de Projekt y planifica un sprint a partir de este backlog.»_

La skill `projekt` se activa sola y recorre el flujo. Todo es **dry-run por defecto** — no se escribe nada hasta que lo confirmas.

### Actualizar / eliminar

```text
/plugin marketplace update 3xa-projekt        # trae la última versión
/plugin uninstall projekt-skills@3xa-projekt  # elimina el plugin
```

### Resolución de problemas (instalación)

| Síntoma | Solución |
| --- | --- |
| `/plugin install` dice que el marketplace es desconocido | Ejecuta primero `/plugin marketplace add valfiguer/Projekt-Skills`; la instalación usa `@3xa-projekt`, el nombre del **marketplace**, no del repo. |
| Plugin instalado pero las skills no se activan | Confirma que aparece **habilitado** en `/plugin`. Luego comprueba que tu token resuelve: `bash skills/projekt/scripts/auth_check.sh` (o pídele a Claude «conecta mi organización de Projekt»). |
| `jq: command not found` / `python3: command not found` | Instala la herramienta que falte (`brew install jq` / `brew install python` en macOS) y reabre Claude Code para que tome el nuevo `PATH`. |
| `401 Unauthorized` en la primera llamada | Token ausente, caducado o mal formado. Revisa [Configuración](#configuración--tu-token-de-acceso-personal-pat); un token válido empieza por `pjk_live_`. |

---

## Configuración — tu Token de Acceso Personal (PAT)

El plugin habla con Projekt **como tú**, usando tu propio PAT. Nunca se empaqueta ni se commitea.

1. En Projekt, ve a **Organización → Ajustes → General → Integraciones** y pulsa **Crear API key**. Obtienes un token `pjk_live_…` (cópialo — se muestra una sola vez).
2. Entrégaselo a la skill de **una** de estas dos formas (la variable de entorno tiene prioridad):
   - **Entorno:** `export TREXA_API_TOKEN="pjk_live_…"`
   - **Archivo** (compartido con el MCP de Projekt): `~/.config/3xa-projekt/auth.json`
     ```json
     { "token": "pjk_live_…", "api_base": "https://projekt.3xa.es/api" }
     ```
3. (Opcional) Fija una organización: `export TREXA_ORG_ID="<uuid>"`. Si no, la skill usa tu organización actual según `/me`.

Un PAT lleva **tu rol completo** en **una** organización (sin acotar por endpoint). Trátalo como una contraseña — mira _Seguridad_.

---

## Seguridad (léelo)

- **Dry-run por defecto.** Toda acción que escribe imprime una tabla de payload/diff y no escribe nada hasta que pasas `--apply`.
- **Acciones destructivas y sensibles** (DELETE, `admin/*`, `finance/*`, `payroll/*`) exigen una **segunda confirmación explícita** además de `--apply`.
- **Tu token no se filtra.** Se envía solo en cabeceras de petición y se registra solo como huella (fingerprint) — nunca se imprime, ni se escribe en el ledger, ni se commitea (`.gitignore` bloquea `auth.json`, `*.token`, `.projekt-run/`).
- **Idempotente y reanudable.** Las ejecuciones en lote deduplican y pueden reanudarse desde un ledger de solo-añadir en `.projekt-run/`.
- **Acotado a la organización.** Las escrituras se fijan a un único `X-Org-Id`; las lecturas compartidas entre organizaciones nunca se convierten en destinos de escritura.

---

## Cómo mantiene el gasto de tokens bajo

- El **spec OpenAPI de 1,3 MB nunca entra en contexto.** Un `spec_lookup.sh` incluido imprime un solo bloque de endpoint bajo demanda; el 90% de los casos lo cubre una chuleta curada a mano.
- **Conecta una vez:** auth + organización + lista de proyectos/miembros se resuelven una sola vez y se cachean en `.projekt-run/context.json` para toda resolución nombre→id.
- **Adelgaza en el borde:** las respuestas de la API se proyectan a unos pocos campos con `jq` antes de que Claude las vea.
- **Las cuentas son deterministas:** agregados, informes y documentos los construyen scripts incluidos; el modelo solo se gasta en narrativa genuinamente nueva.

---

## 📚 Documentación

Wiki completa del proyecto en [`docs/`](docs/README.md) — instalación, configuración, arquitectura, una página por skill, la chuleta de la API, modelo de seguridad, resolución de problemas y una guía rápida en español. Empieza por [`docs/README.md`](docs/README.md) (en inglés; página ES: [`Guia-rapida-Espanol`](docs/Guia-rapida-Espanol.md)).

## Enlaces

- Documentación para desarrolladores de Projekt: <https://projekt.3xa.es/developers/>
- Spec OpenAPI: <https://projekt.3xa.es/openapi.yaml>
- Recetas en español: [`skills/projekt/references/recetas-es.md`](skills/projekt/references/recetas-es.md)

## Licencia

MIT © 3XA Design — mira [LICENSE](LICENSE).

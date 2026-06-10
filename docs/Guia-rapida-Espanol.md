# Guía rápida (Español)

**Projekt-Skills** es un plugin de [Claude Code](https://code.claude.com) que conecta tu organización de **[Projekt](https://projekt.3xa.es)** y automatiza **incidencias, documentación, cargas de trabajo, estimaciones y tiempos** vía la API REST — de forma secuencial, profesional y con el mínimo gasto de tokens.

Un plugin, seis skills (`projekt-skills:*`), con tu propio Token de Acceso Personal (PAT). **Dry-run por defecto**: no se escribe nada hasta confirmar con `--apply`.

> 🇬🇧 The full wiki is in English — start at **[Home](README.md)**. Esta página resume lo esencial en castellano.

## Instalación (en 4 pasos)

**Requisitos:** `bash`, `curl`, `jq`, `python3` (3.10+) en el `PATH`. Comprueba: `command -v bash curl jq python3`.

1. **Añade el marketplace e instala** — escribe estas dos líneas **dentro de Claude Code** (en el chat, no en la terminal), una a una:
   ```text
   /plugin marketplace add valfiguer/Projekt-Skills
   /plugin install projekt-skills@3xa-projekt
   ```
2. **Verifica:** `/plugin` → debe aparecer **`projekt-skills`** (v0.2.1) habilitado.
3. **Configura tu token** (ver abajo).
4. **Úsalo:** pídele a Claude _«Conecta mi organización de Projekt y planifica un sprint con este backlog»_. La skill `projekt` se activa sola.

Detalle completo: [Installation](Installation.md).

## Tu token (PAT)

1. En Projekt: **Organización → Ajustes → General → Integraciones → Crear API key**. Token `pjk_live_…` (se muestra una sola vez — cópialo).
2. Entrégaselo de **una** de dos formas (la variable de entorno tiene prioridad):
   - **Entorno:** `export TREXA_API_TOKEN="pjk_live_…"`
   - **Archivo:** `~/.config/3xa-projekt/auth.json` → `{ "token": "pjk_live_…", "api_base": "https://projekt.3xa.es/api" }`
3. (Opcional) Fija organización: `export TREXA_ORG_ID="<uuid>"`.

Trátalo como una contraseña: lleva tu rol completo en una organización. Detalle: [Configuration](Configuration.md).

## Las seis skills

| Skill | Para qué |
| --- | --- |
| **`projekt`** | Orquestador. Flujo `CONECTAR → DESCUBRIR → PLANIFICAR → CREAR → ASIGNAR → ESTIMAR → TIEMPO → DOCUMENTAR → INFORMAR`. Empieza aquí. → [Skill: projekt](Skill-projekt.md) |
| **`projekt-issues`** | Crear incidencias en lote (CSV/texto), asignar, mover de columna. → [projekt-issues](Skill-projekt-issues.md) |
| **`projekt-estimate`** | Estimaciones (puntos→horas), hoja de ruta, planificado vs real. → [projekt-estimate](Skill-projekt-estimate.md) |
| **`projekt-workload`** | Informes de carga/capacidad del equipo (solo lectura). → [projekt-workload](Skill-projekt-workload.md) |
| **`projekt-time`** | Registrar tiempos en lote, temporizadores, resúmenes. → [projekt-time](Skill-projekt-time.md) |
| **`projekt-docs`** | Documentación de proyecto, bitácoras, exportar PDF. → [projekt-docs](Skill-projekt-docs.md) |

## Seguridad (lo esencial)

- **Dry-run por defecto:** revisa el plan; añade `--apply` para escribir; reejecuta → deduplica (crea 0).
- **Acciones destructivas/sensibles** (DELETE, `admin`/`finance`/`payroll`/`tax`/`gdpr`): exigen segunda confirmación (`--admit`). Un hook las bloquea por si acaso.
- **Tu token no se filtra:** solo en cabeceras, registrado como huella; nunca se commitea.
- **Acotado a una organización:** las escrituras se fijan a un `X-Org-Id`.

Detalle: [Safety & Security](Safety-and-Security.md).

## Recetas paso a paso

Flujos completos (sembrar backlog desde CSV, planificar un sprint, equilibrar carga, cargar tiempos, documentar, llegar a cualquier endpoint) en el repo:

📄 [`skills/projekt/references/recetas-es.md`](https://github.com/valfiguer/Projekt-Skills/blob/main/skills/projekt/references/recetas-es.md)

## Más (en inglés)

[Architecture](Architecture.md) · [API Endpoints](API-Endpoints.md) · [Estimation Units](Estimation-Units.md) · [Errors & Troubleshooting](Errors-and-Troubleshooting.md) · [FAQ](FAQ.md) · [Contributing](Contributing.md) · [Changelog](Changelog.md)

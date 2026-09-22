# Projekt-Skills

[English](README.md) · **Español**

> Un plugin de [Claude Code](https://code.claude.com) para conectar tu organización de **[Projekt](https://app.projektrepublic.com)** y automatizar **incidencias, documentación, cargas de trabajo, estimaciones y tiempos** a través de la API REST de Projekt — de forma secuencial, profesional y con el mínimo gasto de tokens.

---

## Qué incluye

Un plugin, cuatro skills (con espacio de nombres `projekt-skills:*`):

| Skill | Qué hace |
| --- | --- |
| **`pr`** | El orquestador: conecta, cachea el contexto y luego crea, asigna y mueve tareas en lote, registra tiempos y gobierna el temporizador. Punto de entrada por defecto — empieza aquí. |
| **`pr-informes`** | Informes de solo lectura: carga y capacidad por miembro, horas planificadas frente a reales, estadísticas y burndown de sprint, hoja de ruta de la organización — y el relleno de estimaciones que faltan. |
| **`pr-docs`** | Documentos (UPSERT idempotente por título, markdown plano, páginas anidadas), el feed de actividad de una tarea, la exportación de la organización, y Projekt como almacén de contexto para IA: espeja las memorias del repo como documentos y las carga de una vez. |
| **`pr-tokens`** | Mide lo que cuesta de verdad una sesión (desde las transcripciones locales, sin llamar a la API), instala las reglas de contexto en el `CLAUDE.md` y dimensiona el catálogo del MCP por dominios. |

### El catálogo

Todo lo que ofrece el API está mapeado en [`skills/pr/references/catalogo.md`](skills/pr/references/catalogo.md):
**685 rutas · 917 operaciones · 16 dominios**, con cuántas son sensibles y cuántas cubre ya un
script `pr-*`. Lo **genera** `scripts/catalogo.py` desde el spec, así que sus cifras nunca son
más viejas que el último `fetch_spec.sh`.

Las cuatro skills envuelven las 80 operaciones del día a día. Las otras 837 están a una llamada
con red de seguridad — sin envoltorio que escribir ni nada a mano que se pueda quedar viejo:

```bash
bash skills/pr/scripts/spec_lookup.sh --domain crm        # qué existe
bash skills/pr/scripts/spec_lookup.sh "«O»/crm/deals" post   # su forma exacta
python3 skills/pr/scripts/llamar.py POST "«O»/crm/deals" --body @deal.json --apply
```

`llamar.py` valida contra el spec antes de enviar, es dry-run para escrituras, rechaza las
operaciones sensibles y todo `DELETE` sin `--admit`, y trunca la respuesta que imprime.

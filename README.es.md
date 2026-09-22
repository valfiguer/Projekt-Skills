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

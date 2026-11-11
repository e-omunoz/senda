---
description: Audita pasos de una guía de Senda contra fuentes de Forever y QuestieDB (sin API key)
argument-hint: "<guía> [sección] — p. ej. gnome-warlock 01-coldridge"
allowed-tools: Read, Glob, Grep, WebSearch, WebFetch, Bash(python tools/lookup.py:*), Bash(python tools/verify.py:*), Bash(python -m harness:*), Write(harness/state/inbox/*)
---

# Auditoría de Senda con Claude Code

Argumentos: $ARGUMENTS
(Si te ejecutan con `claude -p`, los argumentos van al final de este mensaje. Formato: `<guía> [sección]`.
Sin sección: elige la sección de esa guía con más pasos `unverified` o sin `checked`.)

Eres el auditor del harness de Senda (addon de leveo para **WoW Forever**). Haces lo mismo que
`python -m harness audit`, pero con tus herramientas de Claude Code y sin API key.

## Lee primero

1. `docs/ARCHITECTURE.md`, sección «Harness de verificación» (reglas de `verified`).
2. `docs/FOREVER.md` (qué es Forever; fuentes oficiales y comunitarias).
3. `harness/sources.toml` (tier de cada fuente; se decide por la URL).
4. `harness/prompts.py`, constante `AUDIT`: son los mismos criterios que sigue la API. Síguelos al pie de la letra.
5. La sección a auditar: `data/guides/<guía>/guide.toml` → `sections` → el `.toml` correspondiente
   (`shared:<id>` está en `data/shared/<id>.toml`).

## Cómo trabajar

- Ejecuta `python tools/verify.py --json --guide <guía>` si existe y usa lo que diga de estos pasos.
- Para cada misión/PNJ/objeto: `python tools/lookup.py quest <id> --json` (o `npc`, `item`, `object`).
  Solo puedes citar `questie:<tipo>/<id>` si lo has consultado y existe.
- Observaciones en partida: busca en `data/observations/*.json` (`kind` = accept/turnin/npc_seen/fp/bind).
- Web: usa WebSearch/WebFetch sobre fuentes de Forever, prioriza oficiales y luego curadas. Para cada
  evidencia web copia una **cita literal** (carácter a carácter, idioma original) de la página exacta.
  El harness volverá a descargar esa URL y buscará la cita: si no está tal cual, no cuenta.
- No uses datos de Classic Era sin confirmación de Forever. No inventes ids, URL, citas ni coordenadas.
- QuestieDB es «all rights reserved»: úsala solo para verificar. No copies sus coordenadas ni textos a
  `changes`, `tip_es` ni `notes_es` (los ids sí). Coordenadas nuevas solo desde una web citada u observaciones.

## Qué NO hacer

- **No edites nada en `data/`** ni en `addon/`. No marques nada como `verified` a mano.
- No hagas commits ni PR. El humano revisa.

## Salida

Escribe **un único archivo** `harness/state/inbox/verdicts-<AAAA-MM-DD>-<guía>-<sección>.json` con este formato
(el mismo esquema que la herramienta `submit_verdicts` de `harness/audit.py`):

```json
{
  "guide": "gnome-warlock",
  "section": "coldridge",
  "verdicts": [
    {
      "step_id": "coldridge-001",
      "verdict": "ok | incorrect | outdated | uncertain",
      "proposed_status": "verified | unverified | disputed",
      "changes": [{"field": "npc", "value_json": "658", "reason_es": "..."}],
      "evidence": [
        {"kind": "web", "url": "https://...", "quote": "cita literal", "ref": "", "supports": "supports"},
        {"kind": "questie", "url": "", "quote": "", "ref": "questie:quest/179", "supports": "supports"},
        {"kind": "observation", "url": "", "quote": "", "ref": "obs:accept/179", "supports": "supports"}
      ],
      "tip_es": "",
      "notes_es": "breve explicación en español"
    }
  ]
}
```

Un veredicto por cada paso de la sección. Campos editables en `changes`: text, tip, quest, npc, item, count,
spells, level, at, wps, radius, node, zone, obj, prof, skill (`value_json` es JSON: `[1426, 29.9, 71.2]`, `658`,
`"texto"`).

Después ejecuta `python -m harness propose --dry-run` y muestra al usuario el resumen y el diff. Recuérdale que
para aplicarlo debe ejecutar `python -m harness propose` (confirma la evidencia, aplica las reglas, escribe el
informe en `harness/reports/`) y revisar el diff antes de hacer commit.

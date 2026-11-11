---
description: Revisa novedades de Forever (hotfixes, azules, wiki) y extrae afirmaciones con cita (sin API key)
argument-hint: "[días hacia atrás, por defecto 7]"
allowed-tools: Read, Glob, Grep, WebSearch, WebFetch, Bash(python -m harness:*), Write(harness/state/inbox/*)
---

# Vigilancia de fuentes de Senda con Claude Code

Argumentos: $ARGUMENTS (número de días hacia atrás; por defecto 7).

Haces lo mismo que `python -m harness watch`, pero con WebFetch/WebSearch y sin API key.

1. Lee `docs/FOREVER.md`, `harness/sources.toml` y la constante `WATCH` de `harness/prompts.py`
   (criterios de qué es relevante para el leveo). Lee `harness/state/claims.json` si existe, para no repetir.
2. Recorre las fuentes con tier `official` y luego `community_curated` de `sources.toml` (ignora `reference`).
   Para listados, abre solo las entradas publicadas en el periodo pedido.
3. Extrae solo afirmaciones relevantes para subir de nivel en Forever (hotfixes, experiencia, misiones, PNJ,
   clases/talentos, profesiones, zonas, mazmorras de leveo, trucos, API de addons).
4. Cada afirmación: URL exacta + **cita literal** de esa página (el harness la volverá a descargar y comprobar;
   el tier lo decide el harness por la URL, no tú). Ids solo si aparecen en el texto.

**No edites `data/`.** Escribe un único archivo `harness/state/inbox/claims-<AAAA-MM-DD>.json`:

```json
{"claims": [
  {"category": "hotfix", "summary_es": "Resumen en español.", "quote": "literal text", "url": "https://...",
   "date": "2026-11-10", "classes": ["WARLOCK"], "races": [], "zones": [], "quest_ids": [], "npc_ids": [],
   "item_ids": [], "spell_ids": [], "levels": [], "confidence": "high"}
]}
```

`category` ∈ hotfix, xp_change, quest_change, npc_move, class_change, talent_change, profession_change,
zone_change, dungeon_change, item_change, new_trick, addon_api, other.

Al terminar ejecuta `python -m harness propose --dry-run` y resume al usuario las novedades y qué pasos de las
guías afectan. Para registrarlas: `python -m harness propose`.

---
description: Investiga trucos de leveo de Forever para una raza/clase y los propone como conocimiento (sin API key)
argument-hint: "<Raza> <CLASE> — p. ej. Gnome WARLOCK"
allowed-tools: Read, Glob, Grep, WebSearch, WebFetch, Bash(python -m harness:*), Write(harness/state/inbox/*)
---

# Trucos de leveo con Claude Code

Argumentos: $ARGUMENTS (raza y clase; sin argumentos, todas las de `data/guides/*/guide.toml`).

Haces lo mismo que `python -m harness tips`.

1. Lee `docs/FOREVER.md`, `harness/sources.toml`, la constante `TIPS` de `harness/prompts.py` y, si existen,
   `data/knowledge/<clase>/*.toml` y `harness/state/tips.json` (para no repetir consejos).
2. Busca trucos y estrategias **específicos de Forever**: rutas, misiones eficientes, hechizos/talentos clave por
   tramo, macros, mascotas/demonios, profesiones útiles, cambios recientes aprovechables, errores comunes.
   Prioriza fuentes oficiales y curadas. Nada de Classic Era sin confirmación de Forever.
3. Cada consejo: `title_es`, `body_es` (2-5 frases, español, accionable), `levels` [min, max], `category`
   (route, quests, spells, talents, macros, pet, professions, gear, group, mistakes, other) y `citations`
   (url + **cita literal** de esa página; el harness la comprobará y descartará el consejo si no aparece).

**No edites `data/`.** Escribe `harness/state/inbox/tips-<AAAA-MM-DD>-<clase>.json`:

```json
{"class": "WARLOCK", "race": "Gnome", "guide": "gnome-warlock", "tips": [
  {"title_es": "...", "body_es": "...", "levels": [10, 20], "category": "pet",
   "citations": [{"url": "https://...", "quote": "literal text"}]}
]}
```

Luego ejecuta `python -m harness propose --dry-run` y enseña al usuario qué se añadiría a
`data/knowledge/<clase>/harness-tips.toml`. Para aplicarlo: `python -m harness propose`.

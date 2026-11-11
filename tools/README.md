# Herramientas de Senda

Todo es **Python 3.11+ solo con la biblioteca estándar** (`tomllib`, `json`, `zipfile`...). No hace falta
instalar nada con `pip`. Funciona igual en Windows y en Linux (CI). Los archivos se escriben en UTF-8 con LF.

| Archivo | Para qué |
|---|---|
| `common.py` | Utilidades compartidas: raíz del repo, carga de TOML, serializador Lua, escritura UTF-8/LF |
| `validate.py` | Validación de `data/` contra `schema/*.json` y reglas semánticas |
| `build.py` | Compila `data/` a `addon/Senda/Guides` y `addon/Senda/Knowledge`; estampa la versión en el `.toc` |
| `package.py` | Crea `dist/Senda-<versión>.zip`, extrae notas del CHANGELOG e instala en modo desarrollo |
| `dev.ps1` / `dev.sh` | Atajos para todo lo anterior |

## Atajos

```powershell
# Windows (PowerShell)
.\tools\dev.ps1 validate            # tabla de resumen + errores; -Json para JSON, -Strict para fallar con avisos
.\tools\dev.ps1 build               # valida y genera el Lua
.\tools\dev.ps1 check               # como build pero sin escribir: falla si lo generado no está al día
.\tools\dev.ps1 test                # tests unitarios (tests/)
.\tools\dev.ps1 package             # dist/Senda-<versión>.zip
.\tools\dev.ps1 all                 # validate + build + package
.\tools\dev.ps1 install-dev -Target "C:\...\World of Warcraft\_forever_\Interface\AddOns"
```

```sh
# Linux / macOS / Git Bash
tools/dev.sh validate [--json] [--strict]
tools/dev.sh build
tools/dev.sh check
tools/dev.sh test
tools/dev.sh package
tools/dev.sh all
tools/dev.sh install-dev --target "/ruta/a/_forever_/Interface/AddOns"
```

Se puede elegir el intérprete con la variable de entorno `PYTHON`. Si la directiva de ejecución de
PowerShell bloquea scripts, lánzalo solo para esa ejecución con
`powershell -ExecutionPolicy Bypass -File tools\dev.ps1 <comando>` (no cambia la configuración del sistema).

## validate.py

```
python tools/validate.py [--json] [--strict] [--root RUTA]
```

Comprueba:

- **Esquema** (`schema/guide.schema.json`, `section.schema.json`, `knowledge.schema.json`) con un validador
  propio que cubre el subconjunto usado: `type`, `enum`, `const`, `required`, `properties`,
  `additionalProperties`, `pattern`, `minLength`, `minimum`/`maximum`, `minItems`/`maxItems`, `items`,
  `prefixItems` y `$ref` a `#/$defs`.
- Ids de paso **únicos en todo el repo**; ids de sección, guía y página de conocimiento únicos.
- Cada entrada de `sections` de `guide.toml` existe (`"01-coldridge"` = archivo de la carpeta de la guía,
  `"shared:<id>"` = `data/shared/<id>.toml`). El `id` de la guía coincide con su carpeta.
- Niveles: `levels = [min, max]` con `min <= max`; si una guía baja de nivel entre secciones, **aviso**.
- Procedencia: `status = "verified"` exige `sources` no vacío (error); `disputed` sin fuentes, aviso.
- Coordenadas de `at` / `wps` entre 0 y 100.
- Campos según `do`: `accept`/`turnin`/`complete` → `quest`; `train` → `spells`; `buy`/`have`/`loot` → `item`;
  `level` → `level`; `skill` → `prof` + `skill`; `goto` → `at`; `getfp` → `node`; `hearth`/`fly` → `zone`;
  `learn_prof` → `prof`.
- Conocimiento: los `kind` conocidos (`page`, `talents`, `spells`, `macros`, `professions`, `rotation`) exigen su
  lista (`[[block]]`, `[[pick]]`, `[[train]]`, `[[macro]]`, `[[route]]`, `[[phase]]`). Se admiten campos extra.
- Secciones que ninguna guía usa: aviso.

Los mensajes indican archivo, paso y campo:

```
ERROR data/guides/gnome-warlock/01-coldridge.toml [paso coldridge-001 · campo 'quest']: do = "accept" exige 'quest'
```

Al final imprime una tabla con pasos por guía y % verificado / sin verificar / en disputa. Con `--json` imprime
`{ ok, errors, warnings, issues[], guides[], totals, knowledge[] }` (lo usan la CI y la web).
Código de salida: `0` sin errores, `1` con errores (o con avisos si `--strict`).

## build.py

```
python tools/build.py [--check] [--quiet] [--root RUTA]
```

1. Ejecuta la validación; si hay errores, no genera nada y sale con `1`.
2. Genera (cabecera `-- GENERADO por tools/build.py — no editar`):
   - `addon/Senda/Guides/<guide-id>.lua`: `Senda.Guides:RegisterSection(...)` de las secciones propias de la guía
     y `Senda.Guides:RegisterGuide(...)` con la lista de ids de sección.
   - `addon/Senda/Guides/Shared.lua`: las secciones de `data/shared/` que usa alguna guía, **una sola vez**.
   - `addon/Senda/Guides/Guides.xml` (primero `Shared.lua`, luego las guías por orden alfabético).
   - `addon/Senda/Knowledge/<carpeta>.lua`: una por carpeta de `data/knowledge/` (`warlock.lua`, `mage.lua`,
     `general.lua`...) con `Senda.Knowledge:Register(...)` por página, ordenadas por `order` e `id`.
   - `addon/Senda/Knowledge/Knowledge.xml`.
3. Copia la versión de `VERSION` a la línea `## Version:` de `addon/Senda/Senda.toc` (solo esa línea).
4. Borra los `.lua`/`.xml` generados que ya no corresponden a nada (solo los que llevan la cabecera de generado).

Detalles del Lua:

- No se incluyen `sources`, `checked` ni `note` en guías y secciones. En conocimiento solo se quitan `sources` y
  `checked` (`note` es texto visible: talentos, macros...).
- La lista `[[step]]` del TOML se llama `steps` en el Lua.
- Salida determinista: claves de paso en orden fijo (`id`, `do`, `quest`, ..., `text`, `tip`, `status`), un paso
  por línea (diffs limpios), resto en el orden del archivo.
- Cadenas entre comillas dobles con escapes (`\"`, `\\`, `\n`, `\t`, `\ddd`); el UTF-8 (ñ, tildes, «») se deja tal
  cual. Las palabras reservadas de Lua como clave se escriben `["do"]`, `["if"]`.

`--check` no escribe nada y falla si algún archivo generado (o la línea de versión del `.toc`) no está al día.

## package.py

```
python tools/package.py [--out CARPETA] [--root RUTA]       # dist/Senda-<versión>.zip
python tools/package.py --changelog 0.1.0                   # sección de CHANGELOG.md (notas del release)
python tools/package.py --install-dev --target RUTA_ADDONS [--allow-any-dir]
```

- El zip contiene una única carpeta `Senda/` en la raíz (formato que esperan CurseForge, Wago y la instalación
  manual). Excluye archivos de desarrollo (ocultos, `tests/`, `*.bak`, `*.py`, `Thumbs.db`...). Las entradas
  van ordenadas y con fecha fija: el zip es reproducible.
- Falla si falta el `.toc`, `Guides.xml` o `Knowledge.xml`, o si la versión del `.toc` no coincide con `VERSION`
  (ejecuta antes `build.py`).

### install-dev (seguridad)

Copia `addon/Senda` a `<target>/Senda` para probar en el juego. Reglas:

- **`--target` es obligatorio** y debe ser una ruta absoluta existente. **No hay ruta por defecto.**
- El destino debe llamarse `AddOns` (o pasar `--allow-any-dir`); si apuntas a la propia carpeta `Senda`, se niega.
- **Solo toca `<target>/Senda`.** Nunca lee, modifica ni borra otras carpetas de `AddOns` (Questie, etc.).
- Si `<target>/Senda` existe pero no tiene `Senda.toc`, o es un enlace simbólico/unión, se niega.

## CI y releases

- `.github/workflows/ci.yml` (push y PR): tests, `validate.py`, `build.py`, comprueba que lo generado está
  commiteado (`git diff --exit-code addon/Senda/Guides addon/Senda/Knowledge`), `luac -p` y `luacheck`
  (configuración en `.luacheckrc`), y sube el zip y `validate-report.json` como artefacto.
- `.github/workflows/release.yml` (etiqueta `v*`): exige que la etiqueta coincida con `VERSION`, valida,
  `build.py --check`, empaqueta y crea el release de GitHub con el zip y la sección del `CHANGELOG.md`.

Para publicar: sube `VERSION`, ejecuta `python tools/build.py`, añade la sección `## [x.y.z]` al `CHANGELOG.md`,
commitea y crea la etiqueta `vx.y.z`.

## Tests

```
python -m unittest discover -s tests -p "test_*.py" -v
```

`tests/test_build.py` usa el fixture `tests/fixtures/repo/` (copiado a una carpeta temporal; nunca se escribe en
él) y cubre el escapado Lua, el validador de esquemas, los errores semánticos, el build completo, el zip e
`install-dev`.

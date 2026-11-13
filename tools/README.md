# Herramientas de Senda

Todo es **Python 3.11+ solo con la biblioteca estándar** (`tomllib`, `json`, `zipfile`...). No hace falta
instalar nada con `pip`. Funciona igual en Windows y en Linux (CI). Los archivos se escriben en UTF-8 con LF.

| Archivo | Para qué |
|---|---|
| `common.py` | Utilidades compartidas: raíz del repo, carga de TOML, serializador Lua, escritura UTF-8/LF |
| `validate.py` | Validación de `data/` contra `schema/*.json` y reglas semánticas |
| `build.py` | Compila `data/` a `addon/Senda/Guides`, `addon/Senda/Knowledge` y `addon/Senda/Locale` (nombres de respaldo de `data/locale/`); estampa la versión en el `.toc` |
| `package.py` | Crea `dist/Senda-<versión>.zip`, extrae notas del CHANGELOG e instala en modo desarrollo |
| `dev.ps1` / `dev.sh` | Atajos para todo lo anterior |
| `questiedb/` | Lector de la QuestieDB instalada en local (solo verificar; «all rights reserved») |
| `foreverdb/` | Adaptador de forever-db (datos abiertos de Polestar, GPL-3) con la misma interfaz, y el selector de fuente |
| `fetch_foreverdb.py` | Descarga y comprueba la forever-db fijada en `foreverdb/PIN` |
| `enrich.py` / `verify.py` / `lookup.py` | Rellenan, comprueban y consultan datos de misiones con QuestieDB o forever-db |
| `import_polestar.py` (+ `polestar/`) | Importa una guía compilada de Polestar a `data/guides/<id>/` (pasos `unverified`, guía solo a mano); ver `docs/IMPORT.md` |
| `import_names.py` (+ `localenames.py`) | Pasa a `data/locale/<idioma>/*.json` los nombres que el cliente dio con `/senda volcar` (lee `SendaNamesDB` del archivo de SavedVariables que se le pasa) e informa de los cambios de nombre entre parches; ver «Nombres del juego» abajo |
| `route_score.py` (+ `routescore/`) | Filtro de eficiencia: puntúa cada misión de una ruta (`data/scores/`) |
| `gen_travel.py` / `gen_dungeons.py` / `gen_rares.py` / `gen_lookup.py` | Generan `data/travel/`, `data/dungeons/`, `data/rares/` y `data/lookup/` desde Polestar, forever-db y tablas del cliente (ver `docs/TRAVEL.md`, `DUNGEONS.md`, `RARES.md`, `LOOKUP.md`) |
| `gen_gathering.py` / `fetch_wago.py` | `gen_gathering.py` genera las rutas de Herboristería, Minería, Desuello y Pesca y `gathering-route.toml` (docs/PROFESSIONS.md, «Recolección»); `fetch_wago.py` baja a `.cache/wago` las tablas del cliente de Forever con la build fijada |

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
python tools/build.py [--check] [--quiet] [--root RUTA] [--refresh-prereq]
python tools/build.py --refresh-reserve [--reserve-from RAIZ] [--foreverdb DIR]
```

1. Ejecuta la validación; si hay errores, no genera nada y sale con `1`.
2. Genera (cabecera `-- GENERADO por tools/build.py — no editar`):
   - `addon/Senda/Guides/<guide-id>.lua`: `Senda.Guides:RegisterSection(...)` de las secciones propias de la guía
     y `Senda.Guides:RegisterGuide(...)` con la lista de ids de sección.
   - `addon/Senda/Guides/Shared.lua`: las secciones de `data/shared/` que usa alguna guía, **una sola vez**.
   - `addon/Senda/Guides/Followups.lua`: índice misión -> misiones de las guías que dependen de ella (cierre
     transitivo), para «Saltar esta misión». Sale de `data/prereq.json` (instantánea de los requisitos duros de
     forever-db: `all` sin migas de pan y `any` con una sola previa); si no existe, de `.cache/foreverdb`; y si
     tampoco, del orden de las guías (coger B justo después de entregar A al mismo PNJ, o el mismo `chain`).
     `python tools/build.py --refresh-prereq` regenera la instantánea desde forever-db.
   - `addon/Senda/Guides/Reserve.lua`: la Reserva de XP de la pestaña «Aparte» (una cadena por zona), desde la
     instantánea `data/reserve.json`. `--refresh-reserve` (`tools/reserve.py`) la rehace con las puntuaciones de
     `tools/route_score.py` (`data/scores/*.json`: decisión, XP y minutos), los PNJ y coordenadas de los pasos de las
     guías, las rutas importadas de Polestar que tengas en local (`ps-*`, `*-ps`, `*-ps-full`, en la raíz de
     `--reserve-from`) y forever-db (nivel mínimo, XP, razas y clases, requisitos, objetivos); solo guarda lo que
     pueden coger el gnomo brujo, el humano mago y el elfo druida.
   - `addon/Senda/Guides/Guides.xml` (primero `Followups.lua`, `Reserve.lua` y `Shared.lua`, luego las guías por
     orden alfabético).
   - `addon/Senda/Knowledge/<carpeta>.lua`: una por carpeta de `data/knowledge/` (`warlock.lua`, `mage.lua`,
     `general.lua`...) con `Senda.Knowledge:Register(...)` por página, ordenadas por `order` e `id`.
   - `addon/Senda/Knowledge/Knowledge.xml`.
   - `addon/Senda/Locale/Names_<idioma>.lua`: una por carpeta de `data/locale/` con entradas, con una cadena
     `"<id>\t<nombre>"` por tipo (`Senda.Names:AddFallback`); solo la carga el cliente de ese idioma (y la de
     `enUS` como último recurso). `addon/Senda/Locale/Locale.xml` se genera siempre (el `.toc` lo carga).
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

## Nombres del juego: /senda volcar e import_names.py

Los textos de las guías llevan fichas que el addon resuelve con el cliente (`Core/Names.lua`):
`{quest:N}` misión, `{npc:N}` PNJ, `{item:N}` objeto, `{spell:N}` hechizo, `{map:N}` zona (uiMapID) y `{obj:N}`
objeto del mundo (este solo con el respaldo: el cliente no lo nombra por id). `validate.py` da error con una ficha
de otro tipo o sin id numérico.

El respaldo vive en `data/locale/<idioma>/{quests,npcs,items,spells,maps,objects}.json`, una entrada por id con su
fuente (`tools/localenames.py`):

| Fuente | Quién la escribe | Prioridad |
|---|---|---|
| `ingame:<build>:<fecha>` | `import_names.py` desde `/senda volcar` | 3 (la verdad) |
| `senda` | tablas propias comprobadas (`tools/polestar/spanish.py`) vía el importador | 2 |
| `polestar-esES` / `polestar-enUS` | nombres de Polestar vía `import_polestar.py` | 1 |

Una entrada solo la sustituye otra de prioridad igual o mayor.

```
# en el juego: /senda volcar   (espera a «Volcado terminado» y sal del juego o /reload)
python tools/import_names.py "RUTA/WTF/Account/<cuenta>/SavedVariables/Senda.lua" [--dry-run] [--report r.md]
python tools/build.py
```

`import_names.py` nunca adivina la cuenta: la ruta del archivo se pasa siempre. Lee `SendaNamesDB` sin ejecutar
Lua (`polestar/luaparse.py`), escribe un archivo por tipo con la fuente `ingame:<build>:<fecha>` e informa de los
nombres nuevos, de los que **cambian entre parches** (una entrada `ingame` anterior con otro nombre) y de los
respaldos que no coincidían con el cliente.

## package.py

```
python tools/package.py [--out CARPETA] [--root RUTA]       # dist/Senda-<versión>.zip
python tools/package.py --changelog 0.1.0                   # sección de CHANGELOG.md (notas del release)
python tools/package.py --install-dev --target RUTA_ADDONS [--allow-any-dir]
```

- El zip contiene cuatro carpetas en la raíz: `Senda/`, `Senda_Nav/`, `Senda_Nav_EK/` y `Senda_Nav_Kalimdor/`
  (formato que esperan CurseForge, Wago y la instalación manual), cada una con `LICENSE` y `THIRD_PARTY.md`. Excluye archivos de desarrollo (ocultos, `tests/`, `*.bak`, `*.py`, `Thumbs.db`...). Las entradas
  van ordenadas y con fecha fija: el zip es reproducible.
- Falla si falta el `.toc` de alguno de los cuatro, `Guides.xml` o `Knowledge.xml`, o si la versión del `.toc` no coincide con `VERSION`
  (ejecuta antes `build.py`).

### install-dev (seguridad)

Copia `addon/Senda`, `addon/Senda_Nav`, `addon/Senda_Nav_EK` y `addon/Senda_Nav_Kalimdor` a `<target>/<addon>`
para probar en el juego. Reglas:

- **`--target` es obligatorio** y debe ser una ruta absoluta existente. **No hay ruta por defecto.**
- El destino debe llamarse `AddOns` (o pasar `--allow-any-dir`); si apuntas a la carpeta de uno de los addons, se niega.
- **Solo toca esas cuatro carpetas.** Nunca lee, modifica ni borra otras carpetas de `AddOns` (Questie, etc.).
- Si alguna existe pero no tiene su `.toc`, o es un enlace simbólico/unión, se niega sin instalar ninguna.

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
`install-dev`. `tests/test_gen_bis.py` cubre `tools/gen_bis.py` y las comprobaciones de `weights.toml`.

## gen_bis.py

Genera `data/knowledge/<clase>/bis-forever.toml` (mejor pieza conocida por tramo y ranura) desde el `Forever.lua` de
Polestar (ForeverLevelingBiS v0.12.0-beta, MIT) y los pesos de `weights.toml`:
`python tools/gen_bis.py --polestar RUTA/polestar [--check]`. Detalle y fuentes: [docs/GEAR.md](../docs/GEAR.md).

## ingest_recording.py y route_report.py

```
python tools/ingest_recording.py WTF/Account/<cuenta>/SavedVariables/Senda.lua   # -> data/recordings/<fecha>-<hash>.json
python tools/route_report.py [--guide ID] [--check]                              # medido frente a data/scores/<guía>.json
```

Detalle del formato, la privacidad y las reglas de tiempo en [docs/RECORDING.md](../docs/RECORDING.md). Tests:
`python -m unittest tests.test_recording -v` y los escenarios `rec1 rec2 recpriv reccap` del simulador.

## enrich.py

Añade a los datos hechos del juego que el cliente no puede consultar. Hoy rellena `reqlevel` (nivel mínimo para coger la misión) en los pasos `accept`, y `reqskill` (profesión requerida), leyendo la QuestieDB local o, si no está, forever-db (ver abajo). Ejecútalo después de añadir o cambiar rutas:

```bash
python tools/enrich.py           # aplica
python tools/enrich.py --check   # solo comprueba
```

Con forever-db no se toca `reqskill` (no tiene ese dato) y algún `reqlevel` puede diferir de QuestieDB
(en la 2026.11.1, 6 pasos): el valor que cuenta es el de QuestieDB, así que aplica los cambios solo con ella.

## Datos de misiones: QuestieDB y forever-db

`enrich.py`, `verify.py` y `lookup.py` leen una de dos fuentes con la misma interfaz (`QuestDB`):

| | QuestieDB (`questiedb/`) | forever-db (`foreverdb/`) |
|---|---|---|
| Licencia | Todos los derechos reservados: solo en local | GPL-3.0 (tablas) y CC BY 4.0 (su capa propia) |
| Dónde | La instalada en el juego (`--questiedb`, `SENDA_QUESTIEDB`) | `.cache/foreverdb` (`--foreverdb`, `SENDA_FOREVERDB`), descargada por `fetch_foreverdb.py` |
| Tiene | Todo lo que usan las herramientas | Nivel mínimo, prerrequisitos y «breadcrumbs», quién da y recoge, objetivos, apariciones, XP, recompensas, botín |
| No tiene | | `exclusiveTo`, `requiredSkill`, `npcFlags` (rol del PNJ), vendedores, rutas de patrulla, nombres de zona |

`--db auto` (por defecto, o `SENDA_DB`) usa QuestieDB si está instalada, igual que antes, y si no forever-db
(así funciona en CI). `--db questiedb` o `--db foreverdb` fuerzan una. Lo que falta en forever-db sale como
`None`: `verify.py` da «unknown» en el rol del PNJ y `enrich.py` deja `reqskill` como esté. QuestieDB sigue
siendo la fuente local de esos datos, que guardamos como hechos en los TOML (`reqlevel`, `reqskill`).

```bash
python tools/fetch_foreverdb.py                 # descarga la versión de foreverdb/PIN (no hace nada si ya está)
python tools/fetch_foreverdb.py --check         # comprueba los sha256 de .cache/foreverdb
python tools/fetch_foreverdb.py --latest        # versión fijada y última publicada
python tools/fetch_foreverdb.py --from RUTA     # copia una carpeta forever-db/ (o su .zip) local
python tools/foreverdb                          # resumen: 3 misiones y 3 PNJ con coordenadas convertidas
python tools/lookup.py --db foreverdb npc 234   # cualquier consulta de lookup con forever-db
python tools/verify.py --db foreverdb --no-report
```

`fetch_foreverdb.py` baja `forever-db-<versión>.zip` de la release `data-v<versión>` de `fitzforge/polestar`,
comprueba su sha256 contra `SHA256SUMS` y el de cada tabla contra `datapackage.json`, y lo extrae en
`.cache/foreverdb` (ignorada por git). Sin red no falla: avisa y sigue con la copia que haya.

**Coordenadas.** forever-db guarda las apariciones en yardas de mundo (x norte, y oeste) sobre el mapa del
cliente, y `ui_map` da los bordes de cada mapa en yardas: `x% = (y - left) / (right - left) * 100`,
`y% = (x - top) / (bottom - top) * 100` (como `LibForeverData.ToUiMap` de Polestar). Los marcos de zona se
solapan en los bordes; el adaptador elige ciudad > zona donde el punto queda más centrado > continente
(coincide con la zona de QuestieDB en el 88% de los PNJ) y guarda el punto también en los demás marcos
(`altSpawns`), así que `verify.py` acepta una coordenada en la zona vecina. Contra QuestieDB, la distancia
mediana es 0,01 puntos de mapa (p90 0,13); Gryan Stoutmantle (234) sale en 56,33, 47,53 (QuestieDB y la guía:
56,33, 47,52). Las apariciones en mazmorras no tienen marco: quedan solo en `world`.

**Versiones.** `.github/workflows/foreverdb.yml` mira cada semana si hay una `data-v*` más nueva que la de
`PIN` y abre una incidencia con su CHANGELOG (no cambia nada). Para subir: lee el CHANGELOG, cambia `version`
en `foreverdb/PIN`, ejecuta `fetch_foreverdb.py` y `verify.py --db foreverdb`, actualiza `THIRD_PARTY.md` y
commitea. El workflow del harness descarga la versión fijada antes de ejecutarse.

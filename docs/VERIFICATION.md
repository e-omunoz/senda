# Verificación de datos

Cómo se comprueba que un paso de guía es correcto y qué herramientas lo hacen. Las reglas de fondo están en
`ARCHITECTURE.md`, en la sección «Harness de verificación». Este documento explica cómo se aplican.

## Niveles de confianza

Cada paso lleva `status`:

| `status` | Significado |
|---|---|
| `unverified` | Valor por defecto. Puede ser correcto, pero nada independiente lo respalda todavía. |
| `verified` | Cumple una de estas reglas: **(a)** una fuente oficial de Blizzard, **(b)** una observación en juego que coincide, o **(c)** QuestieDB local más una cita comprobada por el harness en una fuente independiente. Una URL de guía genérica no basta. |
| `disputed` | Hay fuentes confirmadas que se contradicen. Lo resuelve una persona. |

Capas de comprobación, de la más barata a la más fiable:

1. **Estática** (`tools/validate.py`): esquema, ids únicos y referencias.
2. **Base de datos local** (`tools/verify.py`): se cruza cada paso con QuestieDB (Forever) instalada en el equipo.
3. **Observaciones de juego** (`tools/ingest.py` → `data/observations/`): lo que el grabador del addon vio en partida.
4. **IA** (`harness/`): fuentes web con cita literal.

## Qué comprueba `verify.py`

Para cada paso, dentro del contexto de cada guía que lo incluye (raza, clase y facción de la guía, más los filtros
`if` de sección y paso):

| Comprobación | Pasos | Regla |
|---|---|---|
| `quest_exists` | con `quest`/`quests` | La misión existe en QuestieDB. |
| `npc_exists`, `item_exists` | con `npc` / `item` | El PNJ o el objeto existen. Los objetos que no tienen que ver con misiones pueden faltar; en ese caso el resultado es `unknown`. |
| `starter` / `finisher` | `accept` / `turnin` | El `npc` inicia o termina la misión. Se usan los datos de la misión y el índice inverso del PNJ. |
| `coords` | con `at` | `at` está a menos de la tolerancia (2,0 % del mapa por defecto) de una aparición o punto de ruta del PNJ en el **mismo uiMapID**. Si el paso no tiene `npc`, se compara con quien da o recibe la misión. |
| `race_class` | misiones | Todas las combinaciones raza×clase del paso pueden coger la misión. |
| `prereqs` | `accept` | `preQuestGroup` (todas) y `preQuestSingle` (alguna) se han entregado antes en la ruta. Se ignoran las previas que esa raza o clase no puede hacer. |
| `route_order` | `turnin`/`complete` | Hay un `accept` anterior, salvo en misiones que empiezan con un objeto. |
| `level` | misiones | El nivel requerido no supera el máximo de la sección y el nivel de la misión no se pasa de rango. |
| `npc_role` | `sethearth`, `getfp`, `fly`, `train`, `learn_prof`, `buy` | El PNJ tiene la marca de posadero, maestro de vuelo, instructor o vendedor. |
| `vendor` | `buy` | El PNJ aparece entre los vendedores del objeto. |
| `spells` | `train` | Siempre `unknown`: QuestieDB no tiene datos de hechizos. |
| `observation` | `accept`, `turnin`, `getfp`, `sethearth`, pasos con `npc` | Una observación en juego del mismo tipo coincide en misión, PNJ, mapa y posición, con la misma tolerancia. |

Veredicto del paso:

- `conflict` si alguna comprobación falla.
- `confirm` si alguna confirma y ninguna falla.
- `unknown` en el resto de casos.

`--apply-status` solo cambia `unverified` a `verified`, y solo si el paso es `confirm` en todas las guías que lo
usan y además se cumple una de estas condiciones:

- **(b)** Hay una observación que coincide. Se añade `ingame:obs` a `sources`.
- **(c)** Todas las comprobaciones principales confirman (existencia, inicia/termina, coordenadas, rol del PNJ) y
  `sources` incluye una fuente oficial o una cita ya comprobada por el harness (entrada `harness:...`). Una URL
  de una guía de leveo genérica **no** cuenta: no confirma cada misión ni cada coordenada. Se añade `questie:quest/<id>`, o `questie:npc/<id>` si
  el paso no es de misión.

En los dos casos se escribe `checked = "AAAA-MM-DD"`.

La regla (a), una fuente oficial por sí sola, la aplica el harness de IA, que comprueba la cita. `verify.py` no la
aplica.

La herramienta nunca rebaja un estado. Si un paso `verified` entra en conflicto, aparece como sugerencia en el
informe. `disputed` no se toca.

La edición del TOML es línea a línea: cambia `status`, amplía `sources` (sea de una línea o de varias) e inserta o
actualiza `checked`. Los comentarios y el formato se conservan. Antes de escribir, el resultado se vuelve a leer con
`tomllib`; si algo no cuadra, ese paso se salta y se avisa.

## Comandos

```sh
# Consultas (rápidas: la primera vez se crea la caché en .cache/questiedb/)
python tools/lookup.py quest 179
python tools/lookup.py npc 658
python tools/lookup.py search "Coldridge"
python tools/lookup.py zone-quests 1426 --race Gnome --class WARLOCK --max-level 12
python tools/lookup.py chain 179
python tools/lookup.py item 750 --json        # --json para agentes
python tools/lookup.py info                   # build de QuestieDB y correcciones aplicadas

# Verificación
python tools/verify.py                         # informe en harness/reports/verify-latest.md y .json
python tools/verify.py --guide gnome-warlock --json
python tools/verify.py --apply-status --dry-run
python tools/verify.py --apply-status --tolerance 1.5

# Observaciones de juego (la ruta de WTF se pasa siempre de forma explícita)
python tools/ingest.py "E:/World of Warcraft/_forever_/WTF"
python tools/ingest.py ruta/a/SavedVariables/Senda.lua --dry-run

# Tests
python -m unittest tests.test_questiedb -v
```

Ruta de QuestieDB, por orden de prioridad:

1. `--questiedb <carpeta>`.
2. La variable de entorno `SENDA_QUESTIEDB`.
3. `E:\World of Warcraft\_forever_\Interface\AddOns\QuestieDB`.

La caché se regenera sola cuando cambia el `.toc`, las correcciones o las tablas de zonas. Para forzarla, usa
`lookup.py --rebuild info`.

## Cómo se lee QuestieDB

- **Datos.** Están «horneados» en `QuestieDB_Forever.toc` como líneas `## X-<Tipo>-<id>-<campo>: <base64>`.
  - Cada valor es CBOR. La lista de ids va además comprimida con zlib.
  - Los valores largos se trocean: la clave lleva `~N~` y las partes van en `<clave>-1..N`.
  - La fila `-S` lleva los campos escalares y una máscara `p` con los campos tabla presentes.
  - La numeración de campos se lee de `src/meta/*Meta.lua`.
- **Zonas.** Las apariciones vienen por **areaId** y se convierten a **uiMapID** con
  `support/Forever/Zones/areaIdToUiMapId.lua`. Las subzonas suben al padre con `subZoneToParentZone.lua`. Las
  coordenadas no se reproyectan.
- **Correcciones:**
  - *Estáticas*: ya vienen incluidas en el `.toc` al generarlo.
  - *Dinámicas* (`LoadDynamic`/`LoadFactionFixes`): se evalúan sus tablas literales para la facción de la guía
    (por defecto, Alianza). Los campos que dependen de la clase del jugador (`({...})[playerClass]`) no se aplican;
    se listan en `lookup.py info`, en `skipped_corrections`.
  - *Lista negra de Questie* (`Questie/Database/Corrections/QuestieQuestBlacklist.lua`): las misiones ocultas se
    marcan como `hidden` y `zone-quests` las omite salvo con `--include-hidden`.
  - Las *correcciones de política* de Questie (Feria de la Luna Negra, nodos de recolección, fases de TBC) no se
    aplican porque no afectan al leveo en Forever.
- **Lectura segura.** Nada de Lua se ejecuta. Un analizador de datos en Python lee las tablas literales y las
  SavedVariables.

## Observaciones de juego

`ingest.py` lee `SendaRecorderDB` y guarda solo estos campos:

- `kind`, `quest`, `npc`, `map`, `x`, `y`, `level`, `race`, `class`, `build`.
- El día de la observación (`t` redondeado a las 00:00 UTC).
- Un contador `n`.

Las coordenadas se pasan a porcentaje (0-100) si el grabador las guarda como fracción.

Los nombres de personaje, reino y cuenta nunca salen de la carpeta WTF. Las observaciones repetidas se fusionan.
El resultado va a `data/observations/<build>.json`, que sí se commitea.

## Licencia

QuestieDB es **«all rights reserved»**:

- Se lee solo en local.
- Los datos descodificados se guardan **solo** en `.cache/questiedb/`, que está en `.gitignore`.
- **Nunca** se copian a otra parte del repositorio ni se commitean.

Los informes de `verify.py` solo incluyen ids, veredictos, distancias y, como mucho, la coordenada más cercana
para corregir un conflicto. No llevan nombres ni textos de misión.

Las referencias como `questie:quest/179` en `sources` son punteros, no datos copiados. La salida de `lookup.py`
es para consultarla, no para pegarla en `data/`. Las coordenadas de una guía se verifican, no se transcriben en
bloque.

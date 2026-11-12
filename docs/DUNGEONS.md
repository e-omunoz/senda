# Diario de mazmorras (datos)

Conjunto de datos `data/dungeons/` para el diario de mazmorras de Senda (plan 6b, «Diario de mazmorras»).
Lo genera `tools/gen_dungeons.py`; esta página dice de dónde sale cada dato, con qué licencia, qué forma tiene
y qué cobertura real tiene. El coordinador lo compilará después a Lua compacto; dentro del juego no se lee JSON.

## Qué contiene

| Fichero | Contenido |
|---|---|
| `data/dungeons/dungeons.json` | Una ficha por mazmorra: mapa, nombre, niveles, alas, jefes en orden, entrada, facción del buscador y recuento de misiones |
| `data/dungeons/quests.json` | Misiones por mazmorra (una por línea): quién la da, dónde, requisitos, nivel, facción, si empieza dentro |
| `data/dungeons/meta.json` | Fuentes y versiones, métricas, mapas excluidos (con motivo), misiones de mazmorra sin colocar, misiones con dador sin aparición |

Reproducir (imprime los recuentos por mazmorra; `--check` no escribe y falla si lo guardado difiere):

```
python tools/fetch_foreverdb.py                       # forever-db fijada (o --foreverdb / SENDA_FOREVERDB)
python tools/gen_dungeons.py --client-tables <carpeta con los .csv del cliente>   # o SENDA_CLIENT_TABLES
python tools/gen_dungeons.py --check ...
```

Las tablas del cliente son CSV de wago.tools del build **1.60.1.70450** de Forever: `Map`, `LFGDungeons`, `ContentTuning`,
`MapDifficulty`, `DungeonEncounter`, `AreaTable` (filas tal cual las publica el cliente). Esta ejecución usó las copias
literales que trae la carpeta de pruebas del repositorio de Polestar (`rust/tests/golden/codex/input/sources/wago/1.60.1.70450`);
también sirven las exportaciones de `https://wago.tools/db2/<Tabla>/csv?build=1.60.1.70450`. Del cliente solo se guardan hechos
derivados, nunca las tablas.

## Fuentes y licencias

| Dato | Fuente | Licencia |
|---|---|---|
| Misiones, dadores, PNJ, objetos, apariciones, requisitos, marcos de mapa | forever-db 2026.11.1 (cliente 1.60.1.70532) | GPL-3.0 (tablas) |
| Texto de notas que sitúa algunas misiones (`via: text`) | forever-db `step`/`mechanic` | CC BY 4.0 (capa propia de forever-db); solo se usa para decidir en qué mazmorra va una misión, no se copia |
| Lista de mazmorras, nombres, nivel de entrada, nivel recomendado, jefes, punto de entrada | Tablas del cliente de Forever (`Map`, `LFGDungeons`, `MapDifficulty`, `ContentTuning`, `DungeonEncounter`) | Hechos del cliente |

Los créditos de forever-db (EG Link, CMaNGOS classic-db, ForeverTDB, pfQuest...) están en su `NOTICE.md` y pasan a
`THIRD_PARTY.md` cuando el coordinador lo cierre. No se usa nada de: QuestieDB, DingDB, AtlasLoot, RareScanner,
DungeonJournal, el Codex de Polestar, ni mapas de Leffe. Las entradas del Codex de Polestar salen todas de QuestieDB (salvo
una de Dalaran, de una web), así que no se han tocado; solo se usaron para validar (más abajo) sin copiar ningún valor.

## Forma de los datos

`dungeons.json`, cada elemento:

- `key` (slug en inglés), `map` (id de mapa de instancia), `name`, `directory`, `max_players`, `forever_only` (mapas nuevos de Forever).
- `levels.entry`: nivel mínimo para entrar (mensaje de `MapDifficulty`: «You must be at least level N»), o `null`.
  `levels.recommended`: nivel de `LFGDungeons` -> `ContentTuning.MinLevelSquish` (un solo nivel; el cliente no trae rango).
  `levels.quest_range`: nivel mínimo y máximo de las misiones de la propia mazmorra. Un rango de PNJ no es posible
  (ver «Límites»).
- `lfg_faction`: `["A"]`, `["H"]` o `["AH"]` según el buscador del cliente (la Cárcel de Ventormenta sale `A`, Ragefire Chasm `H`
  y el resto `AH`). Es lo que dice el buscador, no una restricción de entrada.
- `wings`: alas del buscador cuando hay más de una fila (Dire Maul Este/Oeste/Norte; Cumbre de Roca Negra Inferior/Superior).
- `area_ids`: ids de AreaTable cuyo `ContinentID` es la instancia (las usa la asignación de misiones).
- `encounters`: jefes del cliente en orden (`DungeonEncounter`), con su id de encuentro.
- `entrance`: `{ uiMapId, x, y, world, other_frames, ambiguous_frame, source, kind }` o `null` (con `entrance_status`).
  El punto es el **punto de cadáver del cliente** (`Map.CorpseMapID/Corpse_0/Corpse_1`: donde reaparece el fantasma,
  cerca de la puerta), pasado a porcentaje de mapa con los marcos `ui_map` de forever-db. `world` guarda el punto exacto en
  yardas del continente para resolverlo en el juego con la API de mapas. `other_frames` y `ambiguous_frame` avisan de que
  otro mapa de zona contiene también el punto (los marcos de zona se solapan).
- `quest_stats`: recuentos (abajo).

`quests.json` -> `quests[key][]`, cada misión:

- `id`, `title` (inglés de forever-db; el nombre en español se pide al cliente con `{quest:id}`), `level`, `min_level`
  (nivel requerido), `faction` (`A`, `H`, `AH`; de `side` y, si es 0, de la máscara de razas), `classes` y `races` (máscaras
  si están restringidas), `type` (81 = misión de mazmorra del cliente), `xp`, `zone_area`.
- `scope` y `via`: por qué la misión está en esa mazmorra:
  - `zone`: su `zone_area` es la zona de la instancia (AreaTable con `ContinentID` = mapa de la instancia) o una zona de
    clasificación antigua confirmada por los títulos (133 Gnomeregan, 978 Zul'Farrak, 1517 Uldaman, 1717 Razorfen Kraul).
  - `objective`: mata a un jefe, o necesita un objeto que solo sueltan jefes (a lo sumo 4 fuentes, todas jefes de esa mazmorra),
    donde el jefe es un PNJ de forever-db sin apariciones cuyo nombre coincide con un encuentro del cliente de esa mazmorra.
  - `text`: una nota de forever-db dice «dentro de / en» la mazmorra (con dungeon, jefe, élite o grupo; nunca «raid»). Si cita
    más de dos mazmorras se descarta (queda en `unplaced_dungeon_quests` con candidatas); con dos se anota en ambas con `multi_dungeon`.
  - `chain`: antecesora (sin límite) o sucesora (hasta 2 pasos) de una misión ya colocada, sin cruzar misiones de otra
    mazmorra, de nivel <= 60 y que no sea de banda (tipo 62).
- `giver` y `turnin` (listas): `{ kind (npc|object|item), id, name, pos [uiMapId, x, y] | null, spawns, where, basis }`. Para un
  objeto que empieza la misión: `dropped_by` con quién lo suelta y si ese PNJ tiene aparición.
  `where`: `outside` (tiene aparición en un continente), `inside` (sin aparición y la zona de la misión es la propia instancia)
  o `unknown` (sin aparición y sin más pistas). `basis` dice por qué.
- `started`: `inside`, `outside`, `unknown` o `null` (sin dador). `inside` solo si todos los dadores son `inside`.
- `requires`: `{ all, any, breadcrumb_of }` (ids de forever-db). `all`: hacen falta todas; `any`: basta una; `breadcrumb_of`:
  misiones previas que solo llevan a esta (no son obligatorias). La cadena completa se obtiene siguiendo `requires`.
- `objectives`: `{ kind (kill|item|object|event|talk), target, name, count }`.

## Cobertura y métricas (forever-db 2026.11.1, cliente 1.60.1.70450)

- **Mazmorras: 23.** 19 clásicas (Shadowfang, Cárcel de Ventormenta, Deadmines, Wailing Caverns, Razorfen Kraul, Blackfathom,
  Uldaman, Gnomeregan, Sunken Temple, Razorfen Downs, Scarlet Monastery, Zul'Farrak, Blackrock Spire, Blackrock Depths,
  Scholomance, Stratholme, Maraudon, Ragefire, Dire Maul) y 4 solo de Forever (City of Dalaran, Excavation Site: Wetlands,
  Ruins of Lordaeron, The Hall of Thanes). Criterio: mapa de instancia tipo mazmorra con fila de `LFGDungeons` (tipo 0) o nivel
  de entrada en `MapDifficulty`. Excluidos (14, con motivo en `meta.json`): mapas de prueba, el Monasterio sin usar, Cavernas
  del Tiempo (entrada 65), y 10 mapas de Forever sin fila de buscador ni misiones en forever-db (Demon Fall Canyon, Karazhan
  Crypts, Shadow Hold, Naxxramas de 5 jugadores, etc.). Las bandas (Zul'Gurub, MC, BWL, Onyxia, AQ, Naxx) quedan fuera: no son de subida.
- **Entradas: 19 de 23** (todas las clásicas). Las 4 de Forever no tienen punto de cadáver en el cliente (`CorpseMapID = -1`) y
  su entrada solo la dan QuestieDB y webs: queda `null`. Cuando el coordinador tenga la entrada comprobada en el juego (o de
  una fuente abierta) se rellena a mano en esas 4.
- **Niveles:** `entry` para las 19 clásicas (no para las 4 de Forever, que no tienen mensaje de `MapDifficulty`);
  `recommended` para las 23 (de `ContentTuning`); `quest_range` para las 23.
- **Misiones: 766 filas, 671 misiones distintas** (una misión puede salir en dos mazmorras). Por motivo: 332 `zone`, 89
  `objective`, 11 `text`, 334 `chain`. Las 432 que no son `chain` son las que están en la propia mazmorra.
- Por mazmorra (total / de la mazmorra, sin cadena; Alianza / Horda; dador sin aparición; empieza dentro):

| Mazmorra | Nivel entrada / recomendado | Misiones | Propias | A / H | Dador sin aparición | Empieza dentro |
|---|---|---|---|---|---|---|
| Shadowfang Keep | 11 / 18 | 3 | 3 | 0 / 3 | 0 | 0 |
| Cárcel de Ventormenta | 15 / 23 | 10 | 6 | 10 / 0 | 0 | 0 |
| Deadmines | 10 / 16 | 24 | 8 | 24 / 0 | 0 | 0 |
| Wailing Caverns | 10 / 17 | 17 | 10 | 8 / 16 | 0 | 1 |
| Razorfen Kraul | 25 / 24 | 32 | 11 | 17 / 17 | 2 | 0 |
| Blackfathom Deeps | 15 / 22 | 15 | 13 | 7 / 10 | 2 | 3 |
| Uldaman | 30 / 35 | 56 | 30 | 40 / 25 | 7 | 0 |
| Gnomeregan | 19 / 25 | 29 | 27 | 24 / 16 | 12 | 0 |
| Sunken Temple | 45 / 45 | 55 | 15 | 46 / 47 | 1 | 2 |
| Razorfen Downs | 35 / 34 | 7 | 7 | 4 / 6 | 2 | 3 |
| Scarlet Monastery | 20 / 30 | 20 | 8 | 6 / 14 | 1 | 1 |
| Zul'Farrak | 39 / 42 | 23 | 10 | 17 / 16 | 0 | 0 |
| Blackrock Spire | 48 / 53 | 133 | 69 | 87 / 94 | 10 | 0 |
| Blackrock Depths | 42 / 48 | 68 | 44 | 49 / 44 | 15 | 0 |
| Scholomance | 33 / 57 | 49 | 32 | 37 / 37 | 1 | 1 |
| Stratholme | 37 / 55 | 110 | 43 | 79 / 84 | 4 | 3 |
| Maraudon | 25 / 42 | 11 | 11 | 8 / 8 | 2 | 2 |
| Ragefire Chasm | 10 / 13 | 10 | 6 | 0 / 10 | 1 | 1 |
| Dire Maul | 31 / 54 | 54 | 40 | 48 / 50 | 21 | 26 |
| City of Dalaran | - / 28 | 8 | 8 | 4 / 4 | 1 | 1 |
| Excavation Site: Wetlands | - / 26 | 14 | 14 | 9 / 5 | 3 | 3 |
| Ruins of Lordaeron | - / 15 | 13 | 13 | 4 / 9 | 1 | 1 |
| The Hall of Thanes | - / 13 | 5 | 4 | 5 / 1 | 1 | 1 |

(Las columnas A y H cuentan las misiones que puede coger esa facción; las de ambas facciones suman en las dos.
«Nivel entrada» y «recomendado» son hechos del cliente: no son un rango «15-25» de guía, el cliente no trae rango.)

- **Misiones cuyo dador no tiene aparición: 85** (de 671; 79 entre las propias). Es el síntoma de que las instancias no están
  en las apariciones de forever-db (solo hay continentes y campos de batalla). Dire Maul (21), Profundidades (15), Gnomeregan
  (12) y Cumbre (10) concentran la mayoría: son dadores dentro de la instancia (Dire Maul, 26 misiones empiezan dentro) o
  PNJ que forever-db no sitúa. 5 misiones no tienen dador y 3 no tienen entregador en forever-db.
- **Empiezan dentro: 49**; fuera: 640; sin saber: 72; sin dador: 5. `inside` es una inferencia (sin aparición + zona de la
  propia instancia), no una observación: por eso el campo `basis`.
- **Misiones de tipo «mazmorra» (81) de nivel <= 60 sin colocar: 55** (`unplaced_dungeon_quests` en `meta.json`). Son sobre todo
  unas 40 misiones de set de nivel 60 de Anthion («An Earnest Proposition», «Just Compensation»... que citan Scholomance,
  Stratholme y Cumbre a la vez), las de Montaña Roca Negra (zona 25: Profundidades o Cumbre), misiones de llave, de montura o
  de banda de nivel 60, y unas pocas de subida cuyo dador está en el exterior y cuyos objetos o jefes forever-db no liga a una
  instancia (p. ej. «Haze of Evil», 4143, de Sunken Temple).

## Validación

1. **Integridad** (la hace el generador, 0 errores): todos los `requires` apuntan a misiones que existen; ningún nivel
   requerido supera en más de 5 al de la misión; todas las misiones salen de forever-db y todas las mazmorras de las
   tablas del cliente.
2. **Reproducible:** dos ejecuciones dan los mismos bytes (`--check` -> «coincide»).
3. **Entradas, contra una referencia independiente** (el Codex de Polestar; solo para comparar, no se copia nada): de las 25
   mazmorras y bandas clásicas con punto de cadáver, el mapa de zona elegido (el de mayor distancia a su borde entre los que
   contienen el punto) coincide en 19. Las otras 6 (Blackfathom Deeps, Razorfen Downs, Razorfen Kraul, Uldaman, Cumbre de Roca
   Negra y la banda Molten Core) caen en el solape de dos zonas: el punto es el mismo, el mapa de zona elegido es el que difiere. Por eso se guardan `other_frames`,
   `ambiguous_frame` (13 mazmorras tienen otro mapa de zona que contiene también el punto) y el punto del mundo en `world`. El
   punto de cadáver no siempre es la puerta: a entre 7 y 19 puntos de mapa en Deadmines, Dire Maul y Sunken Temple, por ejemplo (el cliente
   lo coloca donde el fantasma sale, no en la entrada). Antes de mostrarlo como «entrada» en la interfaz hay que comprobar las 3 que
   el plan pide recorrer en el juego.
4. **Misiones previas en orden:** el plan pide «misiones previas en el orden correcto antes de cada paso `dungeon`»:
   `requires` trae ese orden; falta cruzarlo con los pasos `dungeon` de las guías cuando se compile.

## Botín por clase (no incluido)

El plan lo toma de ForeverLevelingBiS (MIT). No se ha podido obtener sin conexión una copia con su licencia: no está
instalada en `Interface/AddOns` y se distribuye por CurseForge, donde Polestar solo acepta versiones con licencia MIT
verificable. Descargarla requiere aprobación expresa, así que **el botín queda fuera**; este conjunto no inventa ni estima
ningún objeto. Hace falta: (1) descargar la versión, (2) leer su `LICENSE` y anotar versión y fecha de datos,
(3) añadirlo como segunda fuente en `gen_dungeons.py`, con los pesos de clase de Senda. Hasta entonces `encounters` trae
los jefes sin botín. AtlasLoot (GPL-2.0, solo local en Polestar) y DungeonJournal (sin licencia) quedan descartados.

## Límites conocidos

- forever-db no tiene apariciones dentro de instancias: sin rango de nivel de PNJ, sin posición de dadores internos, y las
  misiones cuyo objetivo es un jefe solo se detectan cuando forever-db enlaza esa muerte (Arugal, p. ej., no aparece como
  objetivo de ninguna misión: Shadowfang Keep sale con solo 3 misiones). Cobertura real de una mazmorra = lo que forever-db sabe.
- Los títulos y nombres van en inglés; en español salen del cliente (`{quest:id}`, `{npc:id}`).
- Sin `zone_area` conocido para unas 1.370 misiones de forever-db: las que no entran por jefe o texto quedan fuera.
- Los ids de zona antiguos 133, 978, 1517 y 1717 no están en la rebanada de `AreaTable` (que trae solo las zonas
  principales y las de la rebanada); se confirmaron por el título de sus misiones y se anotan como tales en `via`.
- Las 4 mazmorras exclusivas de Forever no tienen entrada. No hay botín (ver arriba).

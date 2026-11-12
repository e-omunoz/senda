# Auditoría de datos de las guías

> Que la guía nunca mande al jugador a una misión que no está. Auditoría sistemática de las tres guías de personaje
> (`gnome-warlock`, `human-mage`, `nightelf-druid`, con las secciones compartidas de `data/shared/`) contra forever-db
> 2026.11.1 y sus correcciones. Herramienta: `tools/audit_guides.py`; corre en `python -m unittest`
> (`tests/test_audit_guides.py`): falla con cualquier error y escribe los avisos en stderr.

Origen: el brujo gnomo llevaba ya «Devourer of Souls» (1716) y la guía lo mandó a Forjaz, a Lago Blackwrench (6120,
47.6, 9.3), a por «Gakin's Summons» (1717). Desde 0.6.1 el motor da un paso por hecho si ya tienes una misión posterior
de la cadena (`Engine/Conditions.lua`, `Superseded`); esta auditoría busca el resto de fallos de datos del mismo tipo.

## 1. Qué se comprueba

`python tools/audit_guides.py [--guide ID] [--warnings] [--json]`. Recorre cada guía en el orden en que la juega cada
personaje (filtros `if` de sección y de paso aplicados; los de profesión quedan fuera, como en `tools/route_score.py`),
con el nivel estimado en cada paso (interpolado en el rango de la sección, sin bajar de un `do = "level"` anterior):

| Código | Nivel | Qué |
|---|---|---|
| `npc-missing`, `quest-missing` | error | el PNJ o la misión no están en forever-db (o una corrección `remove` la quita: no existe en Forever) |
| `wrong-giver`, `wrong-ender` | error | en `accept` el `npc` no da la misión (quest_start); en `turnin`, no la recibe (quest_end) |
| `at-far`, `at-other-map` | error | `at` a más de 1,0 de mapa de toda aparición del PNJ en ese uiMap (marcos de `ui_map`, apariciones corregidas incluidas) |
| `race`, `class` | error | la misión no se ofrece a la raza o clase del personaje (máscaras de forever-db) |
| `needs-race-filter`, `needs-class-filter` | error | paso de una sección compartida con misión solo para ciertas razas o clases y sin su `if` |
| `pre-missing`, `pre-order` | error (aviso si el paso es opcional) | una previa (modo `all`, o alguna de las `any` que el personaje puede coger) no se entrega antes en la guía |
| `pre-optional` | error | paso obligatorio cuya previa solo se entrega en pasos opcionales (con «Saltar los pasos opcionales» el PNJ no la ofrece) |
| `crumb-late`, `exclusive` | error | una miga de pan cogida después de la misión a la que lleva; dos misiones que se excluyen |
| `level` | error | la misión pide más nivel del que se lleva en ese punto y el paso no tiene `reqlevel` para esperarlo |
| `dup-accept`, `dup-turnin`, `turnin-before-accept`, `turnin-no-accept`, `complete-after-turnin`, `complete-before-accept` | error | orden y duplicados (un `dungeon` cuenta como coger las misiones que empiezan dentro) |
| `reqlevel-differs`, `level-section`, `class-late`, `never-turned-in`, `no-giver-data`, `no-ender-data`, `npc-no-spawn`, `at-unnamed-far`, `at-unnamed-map` | aviso | dudas: revisar a mano |

Las dudas revisadas van en `REVIEWED` (en la propia herramienta) con su motivo y salen como «revisado».

**Correcciones de forever-db.** forever-db publica `corrections/{quests,npcs,objects}.json` (441 misiones, 67 PNJ y 12
objetos corregidos a mano, con grabaciones de jugadores y comprobaciones en el juego), y muchas no están aún en sus tablas:
de las 111 con `pre`, 104 no lo estaban. `tools/foreverdb/corrections.py` las aplica al cargar (reglas de Polestar,
`forge-data/src/corrections.rs` y `publish/tables.rs`: `set` reemplaza campos, `remove` quita la misión y sus enlaces,
`addSpawns` reemplaza las apariciones de un mapa, `preAll` > `preAny` > `pre`, `breadcrumbs` y `breadcrumbFor`), y
después las de Senda, en el mismo formato, de `data/corrections/quests.json`. Las usan `tools/foreverdb/db.py` (y con él
`audit_guides.py`, `route_score.py`, `lookup.py --db foreverdb`, `verify.py --db foreverdb`) y `build.py --refresh-prereq`.

**Migas de pan.** `data/prereq.json` (regenerado: 2.710 requisitos duros y 213 migas) y `Guides/Followups.lua` separan
ahora las migas de pan: `RegisterFollowups` sigue siendo el índice de dependientes («Saltar esta misión», «Para después»)
y `RegisterBreadcrumbs("miga>misión;...")` dice a qué lleva cada miga (24 en las guías). El motor
(`Guides:BreadcrumbTargets`, `Conditions.lua`) da por hecho el paso de una miga cuando ya tienes o has entregado la misión a
la que lleva y la miga no está en el registro (el PNJ deja de ofrecerla); saltar la miga ya no salta su destino.

## 2. Resultado

| Personaje | Pasos | Coger | Entregar | Pasos con `npc` y `at` | Misiones |
|---|---:|---:|---:|---:|---:|
| Brujo gnomo | 1.152 | 367 | 358 | 774 | 382 |
| Mago humano | 1.188 | 381 | 372 | 811 | 396 |
| Druida elfo de la noche | 1.127 | 363 | 354 | 736 | 376 |

Antes (ya con las correcciones aplicadas): 16 errores y 24 avisos (8 de ellos `pre-optional`, que ahora es error).
Después: **0 errores, 0 avisos, 11 revisados**. Leyendo las tablas sin ninguna corrección
(`ForeverDB.open(corrections=False)`), las guías ya arregladas darían 11 errores: 8 de coordenadas (el felino y Kadrell,
cuyas apariciones corrige `npcs.json`), los de 935 y 97286 (que corrige Senda) y el que originó esta
auditoría: 1716 obligatoria detrás del aviso opcional de Lago (`pre-optional` en `wl-succubus-003`).

## 3. Arreglos

### 3.1 La cadena del súcubo (1717 / 1716) y el abisario (1715 / 1688)

- **Quién da qué.** forever-db: 1717 «Gakin's Summons» la da Lago Blackwrench (6120, Forjaz) y la recibe Gakin (6122);
  1716 «Devourer of Souls» la da Gakin y la recibe Takar (6244). Las dos son de humano y gnomo (`races` 65) y brujo. La
  guía filtra 1717 a gnomos (`if = { race = ["Gnome"] }`) y es opcional; 1716 se coge de Gakin para las dos razas.
- **El fallo de datos.** forever-db publica 1717 como requisito duro de 1716 (`quest_prereq`: `mode all`). No lo es: un
  humano coge 1716 directamente de Gakin (Polestar, `class/warlock/incubus-alliance.guide`: «turnin 1717 only Gnome»), y
  el jugador tenía 1716 sin haber hecho 1717 (si no, la guía no le habría mandado a Lago). Con ese requisito, el índice
  de dependientes decía que saltar el aviso saltaba toda la cadena del súcubo, y la auditoría marcaba 1716 obligatoria
  detrás de una previa opcional. Corrección de Senda `data/corrections/quests.json` 1716: sin requisitos, 1717 como miga.
  Mismo caso en el abisario: forever-db marca 1685 (Remen Marcot, humanos) como miga de 1688 «Surena Caledon» pero 1715
  «The Slaughtered Lamb» (Lago, gnomos) como requisito duro; Polestar (`voidwalker-alliance.guide`): «si Lago no te la
  ofrece, ve a Gakin igualmente». Corrección 1688: 1685 y 1715 como migas.
- **Dónde está Lago.** forever-db (`spawn.jsonl`): Lago en z 501,5, a la altura del suelo de la Caverna Abandonada
  (Ransin Donner 501,4; Murky 501,3), y a 13-22 yardas de Alexander Calder (5173) y Grimnur Stonebrand (5161), que
  están en z 511,7: un piso más arriba. Los pasos `wl-succubus-001` y `wl-voidwalker-001` dicen ahora «está abajo, a ras
  del suelo de la caverna, no en el piso alto de {npc:5173}». Gakin (6122) está en z 101,5 con los instructores de brujo;
  las sillas de la posada de El Cordero Degollado, en z 122: el «sótano» de los textos es correcto.
- `wl-succubus-001` explica que con 1716 en el registro Lago ya no ofrece el aviso y la guía lo pasa sola;
  `wl-voidwalker-001`, que si Lago no ofrece 1715 se va a Gakin igualmente.

### 3.2 Correcciones de Senda a forever-db (`data/corrections/quests.json`)

| Misión | Cambio | Pruebas |
|---|---|---|
| 1716 Devourer of Souls | `pre: []`, `breadcrumbs: [1717]` | arriba (3.1) |
| 1688 Surena Caledon | `pre: []`, `breadcrumbs: [1685, 1715]` | arriba (3.1) |
| 935 Crown of the Earth | `pre: []`, `preAny: [7383]` | forever-db pedía también 934, la versión antigua de la misión del pozo de la luna (650 XP, mismo PNJ que 7383), que no se ofrece: QuestieDB (Forever) la tiene en su lista de ocultas y la guía de Teldrassil de Polestar va de 7383 a 935 sin ella. Error `pre-missing` en `netd-126` |
| 97286 Research Access | `end: { npc: [211033] }` | forever-db da como único receptor a Owen Thadd (211022), bibliotecario de Entrañas (`faction_template` 68, solo aparece en el uiMap 1458); la misión es solo de Alianza (`races` 4294967361). QuestieDB (Forever) la hace entregar a Garion Wendell, que la da. Error `wrong-ender` en `mg-20-library-004` |

Las cuatro son candidatas a enviar a forever-db (`corrections/quests.json`).

### 3.3 Guías

| Pasos | Problema | Arreglo | Pruebas |
|---|---|---|---|
| `dr-20-cat-005`, `-006`, `-009`, `-010` | `at` 1450, 58.39, 73.52: a 4,16 del Gran Espíritu del Felino (11957) | `at = [1450, 54.5, 75.0]`, «en la colina sobre el puente» | forever-db `corrections/npcs.json` 11957: grabación (entregas en 54,30/54,69, 75,01) y comprobación en el juego (#1003, 54,60, 75,07); los datos antiguos estaban unas 90 yardas al este. Polestar `cat-form.guide` usa 54.5,75.0 |
| `a12lm-020`, `-021`, `-037` | `at` 1432, 32.6, 49.7: a 2,43 de Kadrell (1340) | `at = [1432, 34.2, 47.8]` y truco: patrulla por el centro de Thelsamar | forever-db `npcs.json` 1340: aparición de CMaNGOS en 34,17, 47,84 y 35 jugadores grabados (mediana de las ventanas de misión en 34,3, 47,8) |
| `a12lm-002` a `-006`, `-008` | el gnomo coge, completa y entrega otra vez «Farsen's Watch» (96392) y «Nip 'Em in the Bud» (96390), que ya hizo en Dun Morogh (`dun-morogh-093` a `-117`): `dup-accept`, `dup-turnin`, `complete-after-turnin` | `if = { race = ["Human", "NightElf", "Skyborne"] }` (gnomos y enanos las hacen en Dun Morogh); el mapa Hierro Negro (96391, `a12lm-007`, `-009`) sigue para todos | orden de las guías |
| nuevo `a12lm-020a` | el gnomo coge «Stout to Kadrell» (414) en `dun-morogh-116` y la guía nunca la entrega (`never-turned-in`) | entrega a Kadrell en Thelsamar, solo gnomos y enanos | forever-db: 414 la recibe 1340 |
| `mg-20-library-001` (+ nuevo `-001b`) | `accept` de 79092 en la Torre de Azora, sin PNJ: forever-db dice que la da Garion Wendell (211033), a 52 de mapa, en Ventormenta. El paso esperaba un `QUEST_ACCEPTED` que en la torre no llega | `-001` pasa a `do = "loot"` del Diario de investigación (203755) en la torre; `-001b` coge 79092 de Garion (se marca solo si la misión ya salió al coger el libro) | forever-db `quest_start` 79092: npc 211033; `quest_objective`: objeto 203755 |
| `dun-morogh-073`, `-121` (291) | «The Reports» obligatoria; su previa «Frostmane Hold» (287) es opcional | 291 opcional («Solo si hiciste «{quest:287}»…») | forever-db `quest_prereq` 291 ← 287 |
| `hmage-northshire-036`, `-037` (3905) | «Grape Manifest» obligatoria; «Milly's Harvest» (3904) opcional | 3905 opcional | 3905 ← 3904 |
| `hmage-elwynn-036`, `-039` (106) | «Speak with Gramma» (111, abre 107, 112 y 114) obligatoria; «Young Lovers» (106) opcional | 106 obligatoria (`why`: desbloquea «{quest:111}» y 3 más) | 111 ← 106 |
| `netd-056`, `-084` (922) | «Tumors» (923, abre 2498 y 2499) obligatoria; «Rellian Greenspyre» (922) opcional | 922 obligatoria | 923 ← 922 |
| `neds-030`, `-031` (4761) | «The Cliffspring River» (4762, abre 4763) obligatoria; «Thundris Windweaver» (4761, 110 XP, <1 min) opcional | 4761 obligatoria | 4762 ← 4761 |
| `a17wf-049`, `-052`, `-060` (14) | «The People's Militia» (14) obligatoria; la anterior (13) opcional | 14 opcional | 14 ← 13 |
| `a58-eastern-plaguelands-026` a `-032` (5742, 5781) | «Redemption» (5742) obligatoria; pide las tres opcionales de Tirion (5542, 5543, 5544) | 5742 y «Of Forgotten Memories» (5781) opcionales | 5742 ← 5542 + 5543 + 5544 (`all`); QuestieDB igual |

Regla para `pre-optional`: si la misión dependiente abre más misiones obligatorias, la previa pasa a obligatoria (106,
922, 4761); si no, la dependiente pasa a opcional, con su línea de XP en `tip` (las opcionales no llevan `why`,
ROUTE-CHANGES.md §8).

## 4. Dudas revisadas (`REVIEWED`)

| Paso | Duda | Por qué se deja |
|---|---|---|
| `mg-20-library-003` | misión de clase de nivel 1 cogida al 21 | pide antes un libro de biblioteca (cualquiera de la lista `preAny`); la ruta pasa por la Torre de Azora al 20 |
| `mg-40-needles-005`, `mg-42-wand-005` | misiones de clase de nivel 30 cogidas al 41-44 | la cadena de Tabetha (1947) empieza en Marjal Revolcafango, adonde la ruta llega al 38 |
| `mg-45-celestial-005` | nivel 35 cogida al 46 | sigue a 1956 y 1957, que la ruta hace tras Uldaman |
| `dr-11-lunaclaw-001` | forever-db no tiene apariciones del Espíritu de Lunaclaw (12144) | aparece al vencer a Lunaclaw; el `at` es de QuestieDB (Forever) |
| `a38-valle-de-huesos-001`, `-003` a `-005` | `reqlevel = 30`; forever-db dice 35 | QuestieDB (Forever) dice 30 (`enrich.py --check` lo exige); la sección es del 38-40: se llega con nivel de sobra |
| `a50-ungoro-046`, `-047` | forever-db no dice quién recibe «Lost!» (4492) ni quién da «A Little Help From My Friends» (4491) | escolta de Ringo (9999); el PNJ del paso es el de QuestieDB (Forever) |

## 5. Pendiente

- **«The Reports» (291)**: QuestieDB (Forever) le pone además como requisito «Secure the Mountain» (98323), que la ruta
  quitó (ROUTE-CHANGES.md §2); forever-db no. 291 queda opcional, así que como mucho se salta; confirmarlo en el juego.
- `data/scores/` no se ha recalculado con las correcciones: `route_score.py` las lee ya (ver ROUTE-CHANGES.md §9).
- Las correcciones de Senda (3.2) están sin comprobar en el juego, salvo la de 1716 (vista por el jugador).
- La auditoría usa las tres guías de personaje; `--guide` sirve para las importadas de Polestar (`ps-*`), que no se
  publican.

Pruebas en el simulador: `tests/wowsim/scenarios_audit.js` (`audit-crumb-skip`, `audit-crumb-held`,
`audit-voidwalker-crumb`, `audit-farsen-gnome`, `audit-farsen-human`, `audit-library-book`, `audit-cat-spirit`).

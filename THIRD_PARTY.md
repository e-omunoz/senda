# Material de terceros

Senda es GPL-3.0 desde la 0.4.0 ([LICENSE](LICENSE)); hasta la 0.3.5 fue MIT. Aquí está todo lo que Senda
usa o va a importar de otros proyectos: su licencia, de dónde sale, qué versión está fijada y qué se
publica. Plan y motivos: [docs/PLAN-POLESTAR.md](docs/PLAN-POLESTAR.md), sección 3.

## Lo que usamos

| Componente | Para qué | Licencia | Origen y versión fijada | ¿Se publica? |
|---|---|---|---|---|
| [Polestar](https://github.com/fitzforge/polestar) (The Polestar authors) | Código adaptado (cada parte lo dice en un comentario «Adaptado de Polestar, `<archivo>`») y, desde la fase 1, rutas y textos de sus guías importados por `tools/import_polestar.py` | GPL-3.0 | `fitzforge/polestar`, commit `19bd636e7d6f33231770f6029c76d2d4dfc63798` (12-nov-2026). Cada paso importado lo cita en `sources = ["polestar:<commit>/<guía>#<paso>"]` | Sí, con atribución |
| [forever-db](https://github.com/fitzforge/polestar/tree/main/forever-db) (de Polestar): tablas `quest*`, `npc`, `object`, `spawn`, `item`, `item_source`, `ui_map` | Nivel mínimo, prerrequisitos, quién da y recoge cada misión, objetivos, XP, recompensas y apariciones (en yardas de mundo, que `tools/foreverdb` pasa a % de mapa con los marcos de `ui_map`). La leen `tools/verify.py`, `tools/enrich.py` y `tools/lookup.py` cuando no hay QuestieDB (CI) | GPL-3.0 (`forever-db/LICENSE`) | Release `data-v2026.11.1` de `fitzforge/polestar` (`forever-db-2026.11.1.zip`; cliente 1.60.1.70532, `producerCommit` `6d0de256e66674512e453a2990076d84f7e979bb`). Fijada en `tools/foreverdb/PIN`; `tools/fetch_foreverdb.py` comprueba el sha256 de cada tabla contra su `datapackage.json` | Los datos no se commitean (`.cache/foreverdb`, ignorada); los hechos que pasen a `data/` citan `foreverdb:` |
| Requisitos de misión de forever-db (`quest_prereq`), instantánea `data/prereq.json` | Qué misiones dependen de cuáles, para «Saltar esta misión» (`Guides/Followups.lua`, lo compila `tools/build.py`) | GPL-3.0 (`forever-db/LICENSE`) | La misma release de forever-db | `python tools/build.py --refresh-prereq` la regenera desde `.cache/foreverdb`; solo guarda pares de ids |
| Datos de viaje de Polestar (`addon/Polestar/Nav/TravelData.lua`, `Nav/Transit.lua`) y, a través de ellos, Shortest Path Forever (Cillian Berragan) | `data/travel/` (vuelos, barcos, zepelines, tranvía, ascensores, portales, posadas, horarios), generado por `tools/gen_travel.py`; el modelo de costes adapta `Nav/Travel.lua` | GPL-3.0-or-later («Portions Copyright (C) 2026 Polestar contributors»; «Portions Copyright (C) 2026 Cillian Berragan», usado por Polestar con su permiso) | El mismo commit de Polestar; detalle y avisos completos en [docs/TRAVEL.md](docs/TRAVEL.md) | Sí, con atribución |
| Grabador de partidas de Polestar (`addon/Polestar_Recorder/Recorder.lua`, `docs/RECORDING.md`, `tools/lib/recording/report.js`) | Formato de fragmentos de texto con tope de tamaño (`addon/Senda/Recorder/Session.lua`) y el método de tiempos por paso: AFK a cero, huecos recortados a 5 min, frontera de pasadas (`tools/ingest_recording.py`, `tools/route_report.py`) | GPL-3.0 | El mismo commit de Polestar | Sí, con atribución («Adaptado de Polestar, `<archivo>`») |
| Crates de Rust de Polestar `forge-gamedata`, `forge-navbuild`, `forge-core` (solo `jsnum`) | `nav/`: canal de navegación fuera del juego (lee el terreno del cliente instalado y genera celdas transitables) | GPL-3.0-only (`nav/LICENSE-POLESTAR`) | El mismo commit de Polestar | El código sí; nada del cliente (solo celdas derivadas; `nav/out` y `nav/target` no se commitean) |
| Listas de entrenamiento de clase de Forever: `addon/Polestar/QoL/ClassSpells.lua` de Polestar, que las genera de la base de datos de TrinityCore para Forever (advocaite/TrinityCore, rama `forever`, listas capturadas del servidor) y de las tablas `SpellName`, `Spell` y `SkillLineAbility` del cliente | `data/knowledge/trainer/<clase>.json` (nivel, hechizo, coste, rango, rango anterior, máscara de razas), generado por `tools/gen_trainer.py`, y de ahí los `[[train]]` de `data/knowledge/<clase>/spells.toml` ([docs/TRAINER.md](docs/TRAINER.md)) | Hechos de TrinityCore (GPL-2.0) usados como hechos, a través de Polestar (GPL-3.0) | El mismo commit de Polestar; cada JSON lo cita en `source` y cada `[[train]]` generado en `sources = ["trainer:polestar-19bd636e", ...]` | Sí, con atribución |
| Nombres esES de hechizos (`SpellName.Name_lang`, `Spell.NameSubtext_lang`) y nivel de aprendizaje (`SpellLevels.SpellLevel`) del cliente de Forever instalado (con su caché de hotfixes), leídos en local por `nav/crates/senda-spellnames` | `data/knowledge/trainer/names.esES.json` y los `names` de los `[[train]]` | Hechos del juego (© Blizzard Entertainment), usados para interoperabilidad | Build 1.60.1.70888 (`source = "ingame-client:<build>"`) | Solo nombres y niveles de los hechizos que usamos, nunca las tablas |
| Tablas del cliente de WoW: Forever (`Map`, `LFGDungeons`, `ContentTuning`, `MapDifficulty`, `DungeonEncounter`, `AreaTable`), leídas en CSV de wago.tools | `data/dungeons/` (`tools/gen_dungeons.py`) y comprobaciones de `data/travel/` | Hechos del juego (© Blizzard Entertainment), usados para interoperabilidad | Build 1.60.1.70450 / 1.60.1.70532 | Solo hechos derivados, nunca las tablas |
| forever-db: capa propia (`mechanic`, `step`, `note`), esquemas y documentación | Cómo se hace cada misión, en palabras de Polestar (posible apoyo para los trucos de Senda) | CC BY 4.0 (`forever-db/LICENSE-CC-BY-4.0.txt`) | La misma release | Solo con atribución: «Polestar, forever-db (CC BY 4.0)» |

### Créditos de forever-db

forever-db reúne solo valores que tiene al menos una fuente independiente. Su `NOTICE.md` acredita a:

- **EG Link** (salida de World of Warcraft: Forever, de Efficient Games), CC BY 4.0.
- **CMaNGOS classic-db**, GPL-3.0.
- **VMaNGOS** (a través de pfQuest) y **Factoruide**, GPL-2.0 o posterior.
- **ForeverTDB**, la base de datos del mundo de TrinityCore para Forever, GPL-2.0.
- **QuestieDB** (equipo de Questie), acreditada según su mantenedor.
- Las **tablas del cliente** de World of Warcraft: Forever.
- **pfQuest** de Shagu, MIT («Copyright (c) 2017-2021 Eric Mauser (Shagu)»; el texto completo de la
  licencia está en el `NOTICE.md` de forever-db, que `tools/fetch_foreverdb.py` descarga junto a los datos).

## Lo que solo se lee en local

| Componente | Licencia | Cómo lo usamos |
|---|---|---|
| [QuestieDB](https://github.com/Questie) (flavor `Forever`), instalada por el usuario | Todos los derechos reservados (sin licencia de datos) | `tools/questiedb` la lee del disco y guarda su caché en `.cache/questiedb` (ignorada). Solo sirve para verificar y para hechos sueltos que forever-db no tiene (`exclusiveTo`, `requiredSkill` → `reqskill`, `npcFlags`, vendedores). **Nunca se publica ni se sube a GitHub**; los informes llevan solo ids, veredictos y distancias |

## Lo que no entra

Estas fuentes alimentan a Polestar con permisos personales o sin licencia que lo permita. Senda no las
copia ni las importa, aunque lleguen dentro de los archivos de Polestar:

| Componente | Por qué no |
|---|---|
| Mapas de navegación de Leffe y lo derivado de ellos (los tramos `legs`, `Legs.lua`, las rutas `walks/store-leffe-*`) | Leffe dio permiso personal a Polestar, no a Senda. El importador descarta los tramos |
| Datos que solo vienen de DingDB / Ding! (por ejemplo, nombres esES que no confirme otra fuente) | GPL-3.0 con permiso de Yendi a Polestar; DingDB sale además de QuestieDB. Solo entra lo que también dé otra fuente (el cliente, pfQuest...) |
| AtlasLoot | GPL-2.0, que una obra GPL-3.0 solo no puede incorporar (el mismo criterio de Polestar) |
| RareScanner | Todos los derechos reservados |
| DungeonJournal (ForeverDungeonJournal) | Sin licencia publicada |

World of Warcraft y Blizzard Entertainment son marcas de Blizzard Entertainment, Inc. Los nombres e ids del
juego describen el juego para los jugadores; Senda no está afiliada a Blizzard.

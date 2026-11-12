# Informe de importación de Polestar: las tres rutas completas (1-60)

Entrada de la fase de fusión. Generado con `tools/import_polestar.py` (sin cambios) sobre el clon de Polestar en el commit
`19bd636e7d6f33231770f6029c76d2d4dfc63798`, y comparado con las guías actuales de Senda (`data/guides/<clase>/` + `data/shared/`).
Los números salen de un script de análisis de una sola vez (no está en el repositorio); se repite con los TOML importados.

## 1. Qué se ha importado

| Carpeta | Personaje | Secciones | Pasos | Misiones distintas | Cadena |
|---|---|---:|---:|---:|---|
| `data/guides/gnome-warlock-ps/` | Brujo gnomo (Gnome WARLOCK) | 30 | 3310 | 960 | `gnome/01-dun-morogh` + cadena Alianza |
| `data/guides/human-mage-ps/` | Mago humano (Human MAGE) | 30 | 3268 | 941 | `human/01-elwynn-forest` + cadena Alianza |
| `data/guides/nightelf-druid-ps-full/` | Druida elfo de la noche (NightElf DRUID) | 31 | 3354 | 959 | `nightelf/01-teldrassil` + `nightelf/02-darkshore` + cadena Alianza |

La cadena Alianza son las 29 guías que enlazan con `next`, de `02-westfall` a `50-60/06-silithus`, en el orden de Polestar:
Westfall, Darkshore, Loch Modan, Darkshore (vuelta), Ashenvale, Redridge, Duskwood, Humedales, Millares, Hillsbrad, Ashenvale,
Cardo, Desolace, Cardo (b), Tierras Altas de Arathi, Tierras Inhóspitas, Cardo, Tierras Inhóspitas, Feralas, Tanaris, Tierras del Interior,
Garganta de Fuego, Un'Goro, Estepas Ardientes, Frondavil, Cuna del Invierno, Tierras de la Peste del Oeste (con la del Este),
Silithus y Silithus. Cada guía de Polestar es una sección (`NN-nombre.toml`).

Las tres guías son como `nightelf-druid-ps`: `order = -1` (nunca se eligen solas, salen en el desplegable), `status = "unverified"`,
`races`/`classes` de un solo valor y todos los pasos con `sources = ["polestar:<commit>/<guía>#<paso>"]`. Los ids de paso llevan un prefijo por
carpeta y guía (`gw00-001`, `hm00-001`, `nd00-001`...) porque `validate.py` exige ids de paso y de sección únicos en todo el repositorio.
`python tools/validate.py`: **0 errores** (15 avisos; el único nuevo es «los niveles bajan» en `nd`: `ps-westfall` (11) tras `ps-darkshore` (12),
que es el orden real de Polestar para el elfo de la noche). No se ha ejecutado `build.py`.

### Fallos del importador y cómo se montó

El importador (no se ha tocado) escribe **una guía de Polestar por ejecución** en una carpeta con su `guide.toml`. Para la cadena entera se ha
ejecutado 30-31 veces por personaje con `--out` en un directorio temporal y un montaje posterior copió los TOML a la carpeta final y escribió el
`guide.toml`. En el montaje se hicieron tres retoques que el importador debería hacer solo:

1. **`fly` sin `zone` (bug).** Cuando un paso `fly` es el último de la guía de Polestar, `zone_for()` no encuentra un objetivo siguiente con
   coordenadas y no escribe `zone`; `validate.py` lo rechaza («do = "fly" exige 'zone'»). Entrada que falla: `forever/alliance/07-thousand-needles`,
   paso 17 «Fly to Menethil Harbor», objetivo 2; y `forever/alliance/30-40/06-badlands`, paso 44 «Fly to Theramore», objetivo 1 (con `tip`
   «La siguiente guía empieza en Theramore»). Se parcheó a mano en el montaje: `zone = 1437` (Menethil, Humedales) y `zone = 1445`
   (Theramore, Marjal Revolcafango). Arreglo propuesto: tomar el mapa de la ruta de vuelo (`getfp`/nodo) del destino o de `AREA_ZONE`.
2. **Ids de sección y de paso por defecto colisionan** entre guías y entre carpetas: `sec_id = "ps-" + nombre sin el número` repite `ps-darkshore`,
   `ps-ashenvale`, `ps-stranglethorn-vale`, `ps-badlands`, `ps-silithus` dentro de una cadena, y el prefijo por defecto `ps-teld` repite los ids de paso
   entre ejecuciones. Se resolvió con `--prefix` distinto por guía y reescribiendo `id = "..."` de la sección a `<prefijo>-<nombre>`. El importador
   necesita un modo «cadena» (`--guide` repetible o `--chain`) que haga esto y escriba un único `guide.toml`.
3. **Textos fijos de prototipo.** `title`/`summary` de cada sección dicen «(ruta de Polestar)» y «Prototipo: ... importada sin verificar»; el `title` de la guía
   solo se personaliza para druida elfo de la noche. En las tres guías nuevas el `guide.toml` lo escribió el montaje (títulos «... 1-60 (ruta de Polestar)»).

Limitaciones conocidas que se ven en la salida (no son fallos nuevos, ver `docs/IMPORT.md`):

- **Marcos de mapa sin transformar:** 8 pasos `goto` por guía llevan coordenadas de Era sin convertir (nota «SIN convertir»): 4 en Tierras de la Peste del Este
  (1423) y 1 paso en Crestagrana, la guía de Redridge (1433). Mulgore no aparece en la cadena Alianza.
- **Textos sin traducir:** unos 810-830 pasos por guía (25 %) llevan la marca `[EN]` en `text` o `tip`; Polestar solo trae esES para parte de los tips.
- **Condiciones vivas perdidas:** unos 330-350 pasos por guía salen `optional = true` porque dependen de un `when` (dinero, grupo, misión lista, arma).
- **Entrenar la clase** sale como `note` manual (sin `spells`).

## 2. Resumen de las diferencias

Polestar y Senda son rutas de objetivos distintos. **Polestar limpia cada zona** (≈ 950 misiones y ≈ 3300 pasos de 1 a 60); **Senda es una ruta
filtrada por eficiencia** (≈ 410 misiones y ≈ 1200 pasos, saltándose zonas y misiones flojas). La fusión no puede ser «sustituir», sino
«Polestar como universo de candidatos + filtro de eficiencia (`route_score.py`) + capa de clase de Senda».

| | Polestar | Senda | Polestar / Senda |
|---|---:|---:|---:|
| **Brujo gnomo** pasos | 3310 | 1223 | 2.7x |
| misiones distintas | 960 | 408 | 2.4x |
| misiones en las dos | 313 | | |
| solo en Polestar / solo en Senda | 647 | 95 | |
| cogidas+entregas comunes / fuera de orden | 618 | 284 (45 %) | |
| tiempo estimado (ver 8) | 67 h | 24 h | 2.7x |
| **Mago humano** pasos | 3268 | 1239 | 2.6x |
| misiones distintas | 941 | 416 | 2.3x |
| misiones en las dos | 306 | | |
| solo en Polestar / solo en Senda | 635 | 110 | |
| cogidas+entregas comunes / fuera de orden | 605 | 277 (45 %) | |
| tiempo estimado (ver 8) | 66 h | 24 h | 2.7x |
| **Druida elfo de la noche** pasos | 3354 | 1199 | 2.8x |
| misiones distintas | 959 | 403 | 2.4x |
| misiones en las dos | 343 | | |
| solo en Polestar / solo en Senda | 616 | 60 | |
| cogidas+entregas comunes / fuera de orden | 679 | 355 (52 %) | |
| tiempo estimado (ver 8) | 68 h | 23 h | 2.9x |

Qué significa para la fusión:

- Entre el 74 % y el 85 % de las misiones de Senda ya están en Polestar (306-343 de ≈ 410). De las que no, unas 40-64 por personaje **no están en ninguna guía de Polestar**
  (Polestar es más selectivo ahí); el resto cuelgan de sus guías de clase, de reputación o de coleccionables (sección 4).
- Lo de Polestar que falta en Senda son zonas enteras que Senda recorta: Darkshore para humano/gnomo (0 de 39 misiones en común, y 1 de 26 en la vuelta), Arathi (0/50),
  Cardo 40-43 (0/71), Ashenvale 2 (0/25), Hillsbrad (4/50), Tierras del Interior (2/29). Tabla por zona en la sección 3.
- El **orden** difiere en un 45-52 % de las cogidas y entregas comunes (sección 5).

## 3. Pasos y misiones por tramo de nivel

Tramo = nivel inicial de la sección (`levels[0]`), no el nivel real de cada paso, así que las secciones que cruzan un tramo cuentan en el inicial. Cada celda es
«pasos / misiones distintas».

**Brujo gnomo**

| Tramo | Polestar | Senda | Diferencia en pasos |
|---|---:|---:|---:|
| 1-10 | 251 / 82 | 179 / 62 | +72 |
| 11-20 | 376 / 118 | 279 / 96 | +97 |
| 21-30 | 668 / 224 | 203 / 70 | +465 |
| 31-40 | 691 / 217 | 68 / 22 | +623 |
| 41-50 | 638 / 176 | 262 / 82 | +376 |
| 51-60 | 686 / 198 | 232 / 81 | +454 |

**Mago humano**

| Tramo | Polestar | Senda | Diferencia en pasos |
|---|---:|---:|---:|
| 1-10 | 221 / 76 | 182 / 66 | +39 |
| 11-20 | 361 / 113 | 269 / 90 | +92 |
| 21-30 | 666 / 223 | 202 / 69 | +464 |
| 31-40 | 683 / 212 | 92 / 30 | +591 |
| 41-50 | 651 / 177 | 260 / 83 | +391 |
| 51-60 | 686 / 198 | 234 / 83 | +452 |

**Druida elfo de la noche**

| Tramo | Polestar | Senda | Diferencia en pasos |
|---|---:|---:|---:|
| 1-10 | 265 / 90 | 211 / 80 | +54 |
| 11-20 | 377 / 116 | 254 / 82 | +123 |
| 21-30 | 710 / 233 | 190 / 66 | +520 |
| 31-40 | 684 / 212 | 61 / 20 | +623 |
| 41-50 | 632 / 174 | 260 / 83 | +372 |
| 51-60 | 686 / 198 | 223 / 80 | +463 |

Lectura: hasta el 20 las dos rutas son comparables (Senda es entre un 25 y un 45 % más corta en pasos). **Del 21 al 40 Polestar es entre 3 y 10 veces más larga** (668/203 y 691/68 en el brujo):
Senda salta Hillsbrad, Arathi, Ashenvale 2 y parte de Cardo. De 41 a 60 son 2,4-3x. Lo de 31-40 en Senda (61-92 pasos) es poco porque declara pocas secciones en ese tramo.

Por zona de Polestar: pasos, misiones y cuántas de esas misiones están también en la guía de Senda. Muestro la guía del mago; el brujo y el druida difieren en 1-3 misiones por zona.

| Sección importada | Niveles | Pasos | Misiones | Ya en Senda |
|---|---|---:|---:|---:|
| `01-elwynn-forest` | 1-11 | 221 | 76 | 66 |
| `02-westfall` | 11-17 | 96 | 29 | 18 |
| `03-darkshore` | 15-19 | 118 | 39 | 0 |
| `04-loch-modan` | 17-21 | 147 | 49 | 34 |
| `05-darkshore-return` | 21-23 | 66 | 26 | 1 |
| `06-ashenvale` | 22-25 | 134 | 45 | 12 |
| `07-redridge-mountains` | 25-27 | 96 | 34 | 19 |
| `08-duskwood` | 27-28 | 46 | 22 | 4 |
| `09-wetlands` | 27-30 | 156 | 59 | 15 |
| `10-thousand-needles` | 29-31 | 53 | 21 | 3 |
| `11-hillsbrad-foothills` | 30-33 | 115 | 50 | 4 |
| `12-ashenvale` | 32-33 | 66 | 25 | 0 |
| `13-stranglethorn-vale` | 33-35 | 93 | 35 | 12 |
| `14-desolace` | 35-36 | 51 | 16 | 7 |
| `15-stranglethorn-vale` | 35-36 | 53 | 25 | 6 |
| `16-arathi-highlands` | 36-38 | 147 | 50 | 0 |
| `17-badlands` | 38-39 | 93 | 34 | 8 |
| `18-stranglethorn-vale` | 40-43 | 180 | 71 | 0 |
| `19-badlands` | 43-43 | 50 | 18 | 3 |
| `20-feralas` | 43-45 | 87 | 28 | 21 |
| `21-tanaris` | 45-47 | 91 | 32 | 10 |
| `22-the-hinterlands` | 47-48 | 95 | 29 | 2 |
| `23-searing-gorge` | 48-49 | 90 | 27 | 10 |
| `24-un-goro-crater` | 49-50 | 92 | 26 | 19 |
| `25-burning-steppes` | 50-53 | 146 | 37 | 11 |
| `26-felwood` | 53-53 | 69 | 17 | 8 |
| `27-winterspring` | 53-56 | 95 | 32 | 16 |
| `28-western-plaguelands` | 56-58 | 264 | 95 | 29 |
| `29-silithus` | 58-58 | 34 | 18 | 1 |
| `30-silithus` | 58-60 | 224 | 84 | 9 |

## 4. Misiones solo en una de las rutas

### Brujo gnomo

**Solo en Senda: 95 misiones**, por sección de Senda:

- `shared/a55-burning-steppes` (13): Dragonkin Menace (4182); The True Masters (4183); The True Masters (4184); The True Masters (4185); The True Masters (4186); The True Masters (4223) ...
- `shared/a12-loch-modan` (10): In Defense of the King's Lands (217); In Defense of the King's Lands (237); In Defense of the King's Lands (263); Resupplying the Excavation (273); Powder to Ironband (302); Protecting the Shipment (309) ...
- `shared/a26-los-humedales` (8): The Algaz Gauntlet (455); Report to Mountaineer Rockgar (468); Report to Captain Stoutfist (473); Horrors in the Highland (95646); Lost in the Thicket Things (95647); Crimson Crate Delivery (98240) ...
- `shared/a60-endgame` (8): Abandoned Hope (4242); A Crumpled Up Note (4264); A Shred of Hope (4282); Jail Break! (4322); Stormwind Rendezvous (6402); The Great Masquerade (6403) ...
- `shared/a21-minas-de-la-muerte` (7): The Defias Brotherhood (166); Oh Brother. . . (167); Collecting Memories (168); Red Silk Bandanas (214); Underground Assault (2040); Destruction in Deadmines (92753) ...
- `shared/a17-paramos-de-poniente` (6): Thunderbrew (117); ... and that note you found (79008); A Dynamite Plan (92749); Detonation at a Distance (92750); Detonation at a Distance (92751); Explosive Consultation (92752)
- `30-felhunter` (5): Tome of the Cabal (1758); The Binding (1795); Seeking Strahad (1798); Tome of the Cabal (1802); Tome of the Cabal (1804)
- `shared/a34-desolace` (4): Mythology of the Titans (1050); Stealing Supplies (1370); Strange Alliance (1382); Raid on the Kolkar (1384)
- `60-doomguard-dreadsteed` (4): Mor'zul Bloodbringer (7562); The Prison's Bindings (7581); The Prison's Casing (7582); Suppression (7583)
- `shared/a38-valle-de-huesos` (4): Valley of Bones (93034); Ravaging Ravagers (93035); Outing Outcasts (93037); Facing the Truth (93041)
- `shared/a16-hall-of-thanes` (4): The Restless Dead (96394); An Ancient Grudge (96395); Important Heirlooms (96403); The Treaty of Understanding (98423)
- `shared/a44-badlands` (3): A Sign of Hope (721); Amulet of Secrets (722); Power Stones (2418)
- `shared/a47-tanaris` (3): Divino-matic Rod (2768); Scarab Shells (2865); Troll Temper (3042)
- `50-inferno` (3): What Niby Commands (7601); Flawless Fel Essence (7602); Kroshius' Infernal Core (7603)
- `02-dun-morogh` (3): Data Hoarders (95041); Camping 101: Tailoring (96057); Camping 101: Enchanting (96059)
- `shared/a40-ciudad` (2): Reclaimed Treasures (1360); The Lost Dwarves (2398)
- `20-succubus` (2): Gakin's Summons (1717); The Orb of Soran'ruk (1740)
- `shared/a22-bosque-del-ocaso` (1): Crime and Punishment (377)
- `shared/a40-monasterio` (1): In the Name of the Light (1053)
- `40-felsteed` (1): Summon Felsteed (4487)
- `shared/a57-western-plaguelands` (1): Little Pamela (5142)
- `shared/a50-ungoro` (1): Dadanga is Hungry! (5150)
- `shared/a52-felwood` (1): To Winterspring! (5249)

**Solo en Polestar: 647 misiones**, por sección importada (conteo y 4 ejemplos):

- `01-dun-morogh` (12): Distracting Jarven (308); Bitter Rivals (310); Return to Marleth (311); Humble Beginnings (399) ...
- `02-westfall` (17): Further Concerns (35); Find the Lost Guards (37); Westfall Stew (38); Deliver Thomas' Report (39) ...
- `03-darkshore` (38): Cave Mushrooms (947); Onu (948); The Fall of Ameth'Aran (953); Bashal'Aran (954) ...
- `04-loch-modan` (14): The Coastal Menace (104); The Price of Shoes (118); Return to Verner (119); Messenger to Stormwind (120) ...
- `05-darkshore-return` (23): The Absent Minded Prospector (729); The Absent Minded Prospector (731); The Master's Glaive (944); Therylune's Escape (945) ...
- `06-ashenvale` (27): Digging Through the Ooze (470); The Tower of Althalaxx (970); The Tower of Althalaxx (973); Raene's Cleansing (991) ...
- `07-redridge-mountains` (15): An Unwelcome Guest (34); The Legend of Stalvan (66); Dusky Crab Cakes (93); A Watchful Eye (94) ...
- `08-duskwood` (14): Ghoulish Effigy (133); Ogre Thieves (134); Gather Rot Blossoms (156); Deliver the Thread (157) ...
- `09-wetlands` (40): The Cursed Crew (289); Lifting the Curse (290); The Eye of Paleth (292); Cleansing the Eye (293) ...
- `10-thousand-needles` (14): The Night Watch (58); Note to the Mayor (160); Look To The Stars (181); Worgen in the Woods (222) ...
- `11-hillsbrad-foothills` (38): The Doomed Fleet (270); Defeat Nek'rosh (474); Syndicate Assassins (505); Foreboding Plans (510) ...
- `12-ashenvale` (19): Lightforge Iron (321); Blessed Arm (322); The Lost Ingots (324); Salt Flat Venom (1104) ...
- `13-stranglethorn-vale` (19): Tiger Mastery (187); Tiger Mastery (188); Bloodscalp Ears (189); Raptor Mastery (195) ...
- `14-desolace` (9): Vahlarriel's Search (1437); Vahlarriel's Search (1438); Search for Tyranis (1439); Return to Vahlarriel (1440) ...
- `15-stranglethorn-vale` (10): Panther Mastery (192); Panther Mastery (193); Raptor Mastery (196); Troll Witchery (205) ...
- `16-arathi-highlands` (39): Crushridge Bounty (500); Assassin's Contract (522); Baron's Demise (523); Dark Council (537) ...
- `17-badlands` (19): Barbecued Buzzard Wings (703); Pearl Diving (705); Study of the Elements: Rock (710); Study of the Elements: Rock (711) ...
- `18-stranglethorn-vale` (54): Uldaman Reagent Run (17); Raptor Mastery (197); Big Game Hunter (208); Skullsplitter Tusks (209) ...
- `19-badlands` (5): Agmond's Fate (704); ? (1288); Gryphon Master Talonaxe (1450); Rhapsody Shindigger (1451) ...
- `20-feralas` (6): In Search of Knowledge (2939); Doling Justice (2972); Rise of the Silithid (4267); Thalanaar Delivery (4281) ...
- `21-tanaris` (17): Insect Part Analysis (110); Insect Part Analysis (113); Rise of the Silithid (162); Rhapsody's Tale (1469) ...
- `22-the-hinterlands` (17): The Bloodsail Buccaneers (608); Supplies for Nethergarde (1395); Snickerfang Jowls (2581); A Boar's Vitality (2583) ...
- `23-searing-gorge` (17): The Horn of the Beast (3181); Suntara Stones (3367); Suntara Stones (3368); Prayer to Elune (3377) ...
- `24-un-goro-crater` (5): The Super Snapper FX (2944); Williden's Journal (3884); Muigin and Larion (4141); A Visit to Gregan (4142) ...
- `25-burning-steppes` (21): Moontouched Wildkin (978); Petty Squabbles (2783); A Tale of Sorrow (2801); Return to Troyas (2943) ...
- `26-felwood` (8): Flute of Xavaric (939); Cleansing Felwood (4101); Felbound Ancients (4441); Further Corruption (4906) ...
- `27-winterspring` (14): Are We There, Yeti? (977); The Videre Elixir (3909); Chillwind Horns (4809); Winterfall Firewater (5083) ...
- `28-western-plaguelands` (57): Alas, Andorhal (211); Find Ranshalla (979); The New Frontier (1047); Wasteland (1124) ...
- `29-silithus` (10): A Little Slime Goes a Long Way (4513); Good Natured Emma (5048); Good Luck Charm (5050); Marauders of Darrowshire (5206) ...
- `30-silithus` (49): Under the Chitin Was... (1185); Linken's Adventure (3961); Aquementas (4005); Silver Heart (4084) ...

### Mago humano

**Solo en Senda: 110 misiones**, por sección de Senda:

- `shared/a12-loch-modan` (18): In Defense of the King's Lands (217); In Defense of the King's Lands (224); In Defense of the King's Lands (237); In Defense of the King's Lands (263); The Trogg Threat (267); Resupplying the Excavation (273) ...
- `shared/a55-burning-steppes` (13): Dragonkin Menace (4182); The True Masters (4183); The True Masters (4184); The True Masters (4185); The True Masters (4186); The True Masters (4223) ...
- `shared/a26-los-humedales` (8): The Algaz Gauntlet (455); Report to Mountaineer Rockgar (468); Report to Captain Stoutfist (473); Horrors in the Highland (95646); Lost in the Thicket Things (95647); Crimson Crate Delivery (98240) ...
- `shared/a60-endgame` (8): Abandoned Hope (4242); A Crumpled Up Note (4264); A Shred of Hope (4282); Jail Break! (4322); Stormwind Rendezvous (6402); The Great Masquerade (6403) ...
- `shared/a21-minas-de-la-muerte` (7): The Defias Brotherhood (166); Oh Brother. . . (167); Collecting Memories (168); Red Silk Bandanas (214); Underground Assault (2040); Destruction in Deadmines (92753) ...
- `shared/a17-paramos-de-poniente` (6): Thunderbrew (117); ... and that note you found (79008); A Dynamite Plan (92749); Detonation at a Distance (92750); Detonation at a Distance (92751); Explosive Consultation (92752)
- `shared/a34-desolace` (4): Mythology of the Titans (1050); Stealing Supplies (1370); Strange Alliance (1382); Raid on the Kolkar (1384)
- `shared/a38-valle-de-huesos` (4): Valley of Bones (93034); Ravaging Ravagers (93035); Outing Outcasts (93037); Facing the Truth (93041)
- `shared/a16-hall-of-thanes` (4): The Restless Dead (96394); An Ancient Grudge (96395); Important Heirlooms (96403); The Treaty of Understanding (98423)
- `shared/a44-badlands` (3): A Sign of Hope (721); Amulet of Secrets (722); Power Stones (2418)
- `mg-38-tabetha` (3): Items of Power (1948); Hidden Secrets (1949); The Infernal Orb (1954)
- `mg-42-wand` (3): Mage's Wand (1952); The Exorcism (1955); Power in Uldaman (1956)
- `shared/a47-tanaris` (3): Divino-matic Rod (2768); Scarab Shells (2865); Troll Temper (3042)
- `shared/a40-ciudad` (2): Reclaimed Treasures (1360); The Lost Dwarves (2398)
- `mg-15-blue-recluse` (2): Investigate the Blue Recluse (1920); Gathering Materials (1921)
- `mg-26-andromath` (2): Ur's Treatise on Shadow Magic (1938); High Sorcerer Andromath (1939)
- `mg-38-train` (2): Journey to the Marsh (1947); Return to the Marsh (1953)
- `mg-40-needles` (2): Get the Scoop (1950); Rituals of Power (1951)
- `mg-45-celestial` (2): Mana Surges (1957); Celestial Power (1958)
- `mg-60-krellian` (2): Warlord Krellian (9362); Fragmented Magic (9364)
- `mg-20-library` (2): Archmage Theocritus' Research Journal (79092); Research Access (97286)
- `shared/a22-bosque-del-ocaso` (1): Crime and Punishment (377)
- `shared/a40-monasterio` (1): In the Name of the Light (1053)
- `mg-28-astral` (1): Pristine Spider Silk (1940)
- `mg-16-manaweave` (1): Manaweave Robe (1941)
- `mg-30-astral-knot` (1): Astral Knot Garment (1942)
- `shared/a57-western-plaguelands` (1): Little Pamela (5142)
- `shared/a50-ungoro` (1): Dadanga is Hungry! (5150)
- `shared/a52-felwood` (1): To Winterspring! (5249)
- `mg-52-azshara` (1): Destroy Morphaz (8253)
- `02-elwynn` (1): Camping 101: Enchanting (97917)

**Solo en Polestar: 635 misiones**, por sección importada (conteo y 4 ejemplos):

- `01-elwynn-forest` (10): Furlbrow's Deed (184); Elmore's Task (1097); Delicate Instruments (91724); Applejack Still (91736) ...
- `02-westfall` (9): Westfall Stew (38); Stormpike's Delivery (353); Humble Beginnings (399); A Swift Message (6181) ...
- `03-darkshore` (38): Cave Mushrooms (947); Onu (948); The Fall of Ameth'Aran (953); Bashal'Aran (954) ...
- `04-loch-modan` (13): The Coastal Menace (104); The Price of Shoes (118); Return to Verner (119); Messenger to Stormwind (120) ...
- `05-darkshore-return` (23): The Absent Minded Prospector (729); The Absent Minded Prospector (731); The Master's Glaive (944); Therylune's Escape (945) ...
- `06-ashenvale` (27): Digging Through the Ooze (470); The Tower of Althalaxx (970); The Tower of Althalaxx (973); Raene's Cleansing (991) ...
- `07-redridge-mountains` (15): An Unwelcome Guest (34); The Legend of Stalvan (66); Dusky Crab Cakes (93); A Watchful Eye (94) ...
- `08-duskwood` (14): Ghoulish Effigy (133); Ogre Thieves (134); Gather Rot Blossoms (156); Deliver the Thread (157) ...
- `09-wetlands` (40): The Cursed Crew (289); Lifting the Curse (290); The Eye of Paleth (292); Cleansing the Eye (293) ...
- `10-thousand-needles` (14): The Night Watch (58); Note to the Mayor (160); Look To The Stars (181); Worgen in the Woods (222) ...
- `11-hillsbrad-foothills` (38): The Doomed Fleet (270); Defeat Nek'rosh (474); Syndicate Assassins (505); Foreboding Plans (510) ...
- `12-ashenvale` (19): Lightforge Iron (321); Blessed Arm (322); The Lost Ingots (324); Salt Flat Venom (1104) ...
- `13-stranglethorn-vale` (19): Tiger Mastery (187); Tiger Mastery (188); Bloodscalp Ears (189); Raptor Mastery (195) ...
- `14-desolace` (9): Vahlarriel's Search (1437); Vahlarriel's Search (1438); Search for Tyranis (1439); Return to Vahlarriel (1440) ...
- `15-stranglethorn-vale` (10): Panther Mastery (192); Panther Mastery (193); Raptor Mastery (196); Troll Witchery (205) ...
- `16-arathi-highlands` (39): Crushridge Bounty (500); Assassin's Contract (522); Baron's Demise (523); Dark Council (537) ...
- `17-badlands` (19): Barbecued Buzzard Wings (703); Pearl Diving (705); Study of the Elements: Rock (710); Study of the Elements: Rock (711) ...
- `18-stranglethorn-vale` (54): Uldaman Reagent Run (17); Raptor Mastery (197); Big Game Hunter (208); Skullsplitter Tusks (209) ...
- `19-badlands` (4): Agmond's Fate (704); Gryphon Master Talonaxe (1450); Rhapsody Shindigger (1451); Rhapsody's Kalimdor Kocktail (1452)
- `20-feralas` (6): In Search of Knowledge (2939); Doling Justice (2972); Rise of the Silithid (4267); Thalanaar Delivery (4281) ...
- `21-tanaris` (17): Insect Part Analysis (110); Insect Part Analysis (113); Rise of the Silithid (162); Rhapsody's Tale (1469) ...
- `22-the-hinterlands` (17): The Bloodsail Buccaneers (608); Supplies for Nethergarde (1395); Snickerfang Jowls (2581); A Boar's Vitality (2583) ...
- `23-searing-gorge` (17): The Horn of the Beast (3181); Suntara Stones (3367); Suntara Stones (3368); Prayer to Elune (3377) ...
- `24-un-goro-crater` (5): The Super Snapper FX (2944); Williden's Journal (3884); Muigin and Larion (4141); A Visit to Gregan (4142) ...
- `25-burning-steppes` (21): Moontouched Wildkin (978); Petty Squabbles (2783); A Tale of Sorrow (2801); Return to Troyas (2943) ...
- `26-felwood` (8): Flute of Xavaric (939); Cleansing Felwood (4101); Felbound Ancients (4441); Further Corruption (4906) ...
- `27-winterspring` (14): Are We There, Yeti? (977); The Videre Elixir (3909); Chillwind Horns (4809); Winterfall Firewater (5083) ...
- `28-western-plaguelands` (57): Alas, Andorhal (211); Find Ranshalla (979); The New Frontier (1047); Wasteland (1124) ...
- `29-silithus` (10): A Little Slime Goes a Long Way (4513); Good Natured Emma (5048); Good Luck Charm (5050); Marauders of Darrowshire (5206) ...
- `30-silithus` (49): Under the Chitin Was... (1185); Linken's Adventure (3961); Aquementas (4005); Silver Heart (4084) ...

### Druida elfo de la noche

**Solo en Senda: 60 misiones**, por sección de Senda:

- `shared/a55-burning-steppes` (13): Dragonkin Menace (4182); The True Masters (4183); The True Masters (4184); The True Masters (4185); The True Masters (4186); The True Masters (4223) ...
- `shared/a26-los-humedales` (8): The Algaz Gauntlet (455); Report to Mountaineer Rockgar (468); Report to Captain Stoutfist (473); Horrors in the Highland (95646); Lost in the Thicket Things (95647); Crimson Crate Delivery (98240) ...
- `shared/a60-endgame` (8): Abandoned Hope (4242); A Crumpled Up Note (4264); A Shred of Hope (4282); Jail Break! (4322); Stormwind Rendezvous (6402); The Great Masquerade (6403) ...
- `shared/a34-desolace` (4): Mythology of the Titans (1050); Stealing Supplies (1370); Strange Alliance (1382); Raid on the Kolkar (1384)
- `dr-52-torwa` (4): Toxic Test (9051); Bloodpetal Poison (9052); A Better Ingredient (9053); Torwa Pathfinder (9063)
- `shared/a38-valle-de-huesos` (4): Valley of Bones (93034); Ravaging Ravagers (93035); Outing Outcasts (93037); Facing the Truth (93041)
- `shared/a44-badlands` (3): A Sign of Hope (721); Amulet of Secrets (722); Power Stones (2418)
- `02-teldrassil` (3): Elixirs for the Bladeleafs (1581); Return to Denalan (2498); Oakenscowl (2499)
- `shared/a47-tanaris` (3): Divino-matic Rod (2768); Scarab Shells (2865); Troll Temper (3042)
- `shared/a40-ciudad` (2): Reclaimed Treasures (1360); The Lost Dwarves (2398)
- `dr-60-endgame` (2): The Emerald Dream... (7506); Enchanted South Seas Kelp (8110)
- `shared/a22-bosque-del-ocaso` (1): Crime and Punishment (377)
- `shared/a40-monasterio` (1): In the Name of the Light (1053)
- `shared/a57-western-plaguelands` (1): Little Pamela (5142)
- `shared/a50-ungoro` (1): Dadanga is Hungry! (5150)
- `shared/a52-felwood` (1): To Winterspring! (5249)
- `03-darkshore` (1): Baron Marinous (98028)

**Solo en Polestar: 616 misiones**, por sección importada (conteo y 4 ejemplos):

- `01-teldrassil` (5): The Family and the Fishing Pole (1141); Verdant Sigil (3120); Return to Nessa (6343); Camping 101: Leatherworking (97946) ...
- `02-darkshore` (5): Further Concerns (35); A Fishy Peril (40); Humble Beginnings (399); Philmor's Favor (97220) ...
- `03-westfall` (20): The Killing Fields (9); The People's Militia (12); The People's Militia (13); Goretusk Liver Pie (22) ...
- `04-darkshore` (2): The Tower of Althalaxx (967); Expanding Horizons (97914)
- `05-loch-modan` (35): The People's Militia (14); Keeper of the Flame (103); The Coastal Menace (104); The Price of Shoes (118) ...
- `06-darkshore-return` (7): Therylune's Escape (945); The Powers Below (968); A Lost Master (986); Trek to Ashenvale (990) ...
- `07-ashenvale` (27): Digging Through the Ooze (470); The Tower of Althalaxx (970); The Tower of Althalaxx (973); Raene's Cleansing (991) ...
- `08-redridge-mountains` (15): An Unwelcome Guest (34); The Legend of Stalvan (66); Dusky Crab Cakes (93); A Watchful Eye (94) ...
- `09-duskwood` (14): Ghoulish Effigy (133); Ogre Thieves (134); Gather Rot Blossoms (156); Deliver the Thread (157) ...
- `10-wetlands` (40): The Cursed Crew (289); Lifting the Curse (290); The Eye of Paleth (292); Cleansing the Eye (293) ...
- `11-thousand-needles` (14): The Night Watch (58); Note to the Mayor (160); Look To The Stars (181); Worgen in the Woods (222) ...
- `12-hillsbrad-foothills` (38): The Doomed Fleet (270); Defeat Nek'rosh (474); Syndicate Assassins (505); Foreboding Plans (510) ...
- `13-ashenvale` (19): Lightforge Iron (321); Blessed Arm (322); The Lost Ingots (324); Salt Flat Venom (1104) ...
- `14-stranglethorn-vale` (19): Tiger Mastery (187); Tiger Mastery (188); Bloodscalp Ears (189); Raptor Mastery (195) ...
- `15-desolace` (9): Vahlarriel's Search (1437); Vahlarriel's Search (1438); Search for Tyranis (1439); Return to Vahlarriel (1440) ...
- `16-stranglethorn-vale` (10): Panther Mastery (192); Panther Mastery (193); Raptor Mastery (196); Troll Witchery (205) ...
- `17-arathi-highlands` (39): Crushridge Bounty (500); Assassin's Contract (522); Baron's Demise (523); Dark Council (537) ...
- `18-badlands` (19): Barbecued Buzzard Wings (703); Pearl Diving (705); Study of the Elements: Rock (710); Study of the Elements: Rock (711) ...
- `19-stranglethorn-vale` (53): Uldaman Reagent Run (17); Raptor Mastery (197); Big Game Hunter (208); Skullsplitter Tusks (209) ...
- `20-badlands` (5): Agmond's Fate (704); ? (1288); Gryphon Master Talonaxe (1450); Rhapsody Shindigger (1451) ...
- `21-feralas` (6): In Search of Knowledge (2939); Doling Justice (2972); Rise of the Silithid (4267); Thalanaar Delivery (4281) ...
- `22-tanaris` (17): Insect Part Analysis (110); Insect Part Analysis (113); Rise of the Silithid (162); Rhapsody's Tale (1469) ...
- `23-the-hinterlands` (17): The Bloodsail Buccaneers (608); Supplies for Nethergarde (1395); Snickerfang Jowls (2581); A Boar's Vitality (2583) ...
- `24-searing-gorge` (17): The Horn of the Beast (3181); Suntara Stones (3367); Suntara Stones (3368); Prayer to Elune (3377) ...
- `25-un-goro-crater` (5): The Super Snapper FX (2944); Williden's Journal (3884); Muigin and Larion (4141); A Visit to Gregan (4142) ...
- `26-burning-steppes` (21): Moontouched Wildkin (978); Petty Squabbles (2783); A Tale of Sorrow (2801); Return to Troyas (2943) ...
- `27-felwood` (8): Flute of Xavaric (939); Cleansing Felwood (4101); Felbound Ancients (4441); Further Corruption (4906) ...
- `28-winterspring` (14): Are We There, Yeti? (977); The Videre Elixir (3909); Chillwind Horns (4809); Winterfall Firewater (5083) ...
- `29-western-plaguelands` (57): Alas, Andorhal (211); Find Ranshalla (979); The New Frontier (1047); Wasteland (1124) ...
- `30-silithus` (10): A Little Slime Goes a Long Way (4513); Good Natured Emma (5048); Good Luck Charm (5050); Marauders of Darrowshire (5206) ...
- `31-silithus` (49): Under the Chitin Was... (1185); Linken's Adventure (3961); Aquementas (4005); Silver Heart (4084) ...

Observaciones comunes:

De las misiones solo-Senda, dónde las tiene Polestar (fuera de la cadena importada):

- Brujo gnomo: en ninguna guía: 64, reputation: 13, class: 13, collectibles: 4, miscellaneous: 1.
- Mago humano: en ninguna guía: 62, class: 22, reputation: 13, alliance-otra: 7, collectibles: 2, miscellaneous: 2, alliance-otra,reputation: 2.
- Druida elfo de la noche: en ninguna guía: 40, reputation: 14, class: 4, collectibles: 2.

- **Guías de clase de Polestar sin importar** (`guides/forever/class/<clase>/`). Brujo: `imp-alliance` (1-4), `voidwalker-alliance` (10-12), `incubus-alliance` (20-25), `felhunter-alliance` (30-33),
  `impsys-request` (50-54), `orb-of-soranruk`, `orb-of-orahil`, `tome-of-sacrifice`, `dread-mage-hat`, `enchanted-gold-bloodrobe`, `shard-of-the-green-flame`; el Corcel Vil está en `collectibles/mounts/neutral/warlock-felsteed.guide`.
  Mago: `staff-or-orb-alliance` (10-15), `teleports-alliance` (20-50), `manaweave-robe`, `astral-knot-garment`, `mages-wand`, `celestial-orb`, `polymorph-pig`, `ju-ju-heaps`, `arcane-refreshment`,
  `nether-lace-garment`, `spellfire-robes`, `atiesh`, `destroy-morphaz`. Druida: `bear-form` (10-12), `aquatic-form` (16-22), `cat-form` (20-22), `cure-poison` (14-20), `bloodpetal-poison` (50-54).
  Se corresponden con las secciones `10-voidwalker`, `20-succubus`, `30-felhunter`, `mg-*` y `dr-*` de Senda: importarlas es el primer paso de la fusión de clase.
- Otras solo-Senda de nivel alto (Estepas Ardientes, Valle de Huesos, Silithus 60) están en las guías de reputación de Polestar (Darnassus, Ventormenta, clanes centauro).
- **Casi todo lo «solo en Polestar»** es relleno de zona que Senda descarta por XP/min: candidatas a `optional` con `why` tras `route_score.py`.

## 5. Orden

Medido sobre las cogidas y entregas comunes (primera aparición de cada pareja acción+misión, subsecuencia común más larga; lo que queda fuera es «en otro momento»).

### Brujo gnomo: 284 de 618 fuera de orden

Dónde se desplazan más (sección de Senda → sección de Polestar):

- 26: `02-dun-morogh` → `01-dun-morogh`
- 22: `shared/a12-loch-modan` → `04-loch-modan`
- 20: `shared/a26-los-humedales` → `06-ashenvale`
- 13: `shared/a45-feralas` → `20-feralas`
- 11: `shared/a19-crestagrana` → `04-loch-modan`
- 11: `shared/a50-ungoro` → `28-western-plaguelands`
- 11: `shared/a54-winterspring` → `30-silithus`
- 10: `shared/a50-ungoro` → `24-un-goro-crater`

Mayores saltos (porcentaje del largo de la ruta):

- 24 %: turnin «In Search of The Excavation Team» (306); Senda `shared/a26-los-humedales`, Polestar `06-ashenvale`
- 24 %: turnin «Alchemical Hazards» (98282); Senda `shared/a26-los-humedales`, Polestar `06-ashenvale`
- 23 %: accept «Fire Taboo» (277); Senda `shared/a26-los-humedales`, Polestar `06-ashenvale`
- 23 %: turnin «Tramping Paws» (276); Senda `shared/a26-los-humedales`, Polestar `06-ashenvale`
- 22 %: accept «The Giant Guardian» (2844); Senda `shared/a45-feralas`, Polestar `28-western-plaguelands`
- 22 %: turnin «The Giant Guardian» (2844); Senda `shared/a45-feralas`, Polestar `28-western-plaguelands`

### Mago humano: 277 de 605 fuera de orden

Dónde se desplazan más (sección de Senda → sección de Polestar):

- 28: `02-elwynn` → `01-elwynn-forest`
- 24: `shared/a12-loch-modan` → `04-loch-modan`
- 20: `shared/a26-los-humedales` → `06-ashenvale`
- 13: `shared/a45-feralas` → `20-feralas`
- 11: `shared/a19-crestagrana` → `04-loch-modan`
- 11: `shared/a50-ungoro` → `28-western-plaguelands`
- 11: `shared/a54-winterspring` → `30-silithus`
- 10: `shared/a50-ungoro` → `24-un-goro-crater`

Mayores saltos (porcentaje del largo de la ruta):

- 24 %: turnin «In Search of The Excavation Team» (306); Senda `shared/a26-los-humedales`, Polestar `06-ashenvale`
- 24 %: turnin «Alchemical Hazards» (98282); Senda `shared/a26-los-humedales`, Polestar `06-ashenvale`
- 23 %: accept «Fire Taboo» (277); Senda `shared/a26-los-humedales`, Polestar `06-ashenvale`
- 23 %: turnin «Tramping Paws» (276); Senda `shared/a26-los-humedales`, Polestar `06-ashenvale`
- 23 %: accept «Tramping Paws» (276); Senda `shared/a26-los-humedales`, Polestar `06-ashenvale`
- 22 %: turnin «The Greenwarden» (463); Senda `shared/a26-los-humedales`, Polestar `06-ashenvale`

### Druida elfo de la noche: 355 de 679 fuera de orden

Dónde se desplazan más (sección de Senda → sección de Polestar):

- 52: `02-teldrassil` → `01-teldrassil`
- 21: `03-darkshore` → `02-darkshore`
- 21: `shared/a26-los-humedales` → `07-ashenvale`
- 20: `03-darkshore` → `04-darkshore`
- 20: `shared/a19-crestagrana` → `05-loch-modan`
- 16: `03-darkshore` → `06-darkshore-return`
- 13: `shared/a45-feralas` → `21-feralas`
- 11: `03-darkshore` → `01-teldrassil`

Mayores saltos (porcentaje del largo de la ruta):

- 24 %: turnin «In Search of The Excavation Team» (306); Senda `shared/a26-los-humedales`, Polestar `07-ashenvale`
- 24 %: turnin «Alchemical Hazards» (98282); Senda `shared/a26-los-humedales`, Polestar `07-ashenvale`
- 23 %: accept «Fire Taboo» (277); Senda `shared/a26-los-humedales`, Polestar `07-ashenvale`
- 23 %: turnin «Tramping Paws» (276); Senda `shared/a26-los-humedales`, Polestar `07-ashenvale`
- 22 %: accept «Tramping Paws» (276); Senda `shared/a26-los-humedales`, Polestar `07-ashenvale`
- 22 %: turnin «The Greenwarden» (463); Senda `shared/a26-los-humedales`, Polestar `07-ashenvale`

Diferencias de ruta comprobadas en las listas de secciones:

1. **Darkshore:** Polestar vuelve dos veces (15-19 y 21-23). Humano y gnomo en Senda no pisan Darkshore (0 y 1 misiones en común); el druida elfo sí lo hace en `03-darkshore` y `05-viaje-reinos-del-este`.
2. **Loch Modan:** Senda lo hace en `a12` (nivel 12); Polestar lo hace en 17-21, tras Darkshore.
3. **Humedales y Ashenvale:** Senda hace Humedales en `a26` (26-30), con quests (306, 98282, 276, 277, 463...) que Polestar toma en Ashenvale (22-25); Polestar hace Redridge y Duskwood antes de Humedales.
4. **Tierras del Interior, Garganta de Fuego, Un'Goro:** Senda va Tanaris → Garganta → Interior → Un'Goro (`a47`-`a50`); Polestar va Tanaris → Interior → Garganta → Un'Goro.
5. **Felwood y Cuna del Invierno:** Senda los hace antes de las Estepas Ardientes (`a52`, `a54`, `a55`); Polestar tras ellas (50-53 primero).
6. **Inicio de raza:** la mayor diferencia en pares (26-52 misiones) está en la propia zona inicial: Polestar hace 1-14 de una vez y Senda la parte en dos secciones (`01-`, `02-`).

## 6. Coordenadas que difieren más de 1.0

Solo se comparan `accept`/`turnin` de la misma misión y mapa. El veredicto compara cada coordenada con el spawn del PNJ en forever-db (`python tools/lookup.py npc <id>`).

### Brujo gnomo: 4 desacuerdos

| Acción | Misión | Mapa | Polestar | Senda | Dist. | Probablemente acierta |
|---|---|---:|---|---|---:|---|
| accept | Rat Catching (416) | 1432 | 33.8, 48.3 | 32.6, 49.7 | 1.8 | Senda (spawn en la base: Polestar a 1.9, Senda a 0.1) |
| accept | Mountaineer Stormpike's Task (1339) | 1432 | 33.8, 48.3 | 32.6, 49.7 | 1.8 | Senda (spawn en la base: Polestar a 1.9, Senda a 0.1) |
| turnin | Rat Catching (416) | 1432 | 33.8, 48.3 | 32.6, 49.7 | 1.8 | Senda (spawn en la base: Polestar a 1.9, Senda a 0.1) |
| accept | Silver of the Waves (86614) | 1432 | 48.06, 39.7 | 45.7, 43.3 | 4.3 | ambos válidos: la misión tiene varios iniciadores (Polestar objeto, Senda objeto) |

### Mago humano: 2 desacuerdos

| Acción | Misión | Mapa | Polestar | Senda | Dist. | Probablemente acierta |
|---|---|---:|---|---|---:|---|
| accept | Report to Gryan Stoutmantle (109) | 1429 | 24.23, 74.45 | 42.1, 65.9 | 19.8 | ambos válidos: la misión tiene varios iniciadores (Polestar 963, Senda 240) |
| accept | Silver of the Waves (86614) | 1432 | 48.06, 39.7 | 45.7, 43.3 | 4.3 | ambos válidos: la misión tiene varios iniciadores (Polestar objeto, Senda objeto) |

### Druida elfo de la noche: 7 desacuerdos

| Acción | Misión | Mapa | Polestar | Senda | Dist. | Probablemente acierta |
|---|---|---:|---|---|---:|---|
| accept | Seek Redemption! (489) | 1438 | 56.0, 59.52 | 56.08, 57.72 | 1.8 | ambos válidos: la misión tiene varios iniciadores (Polestar 2081, Senda 2083) |
| accept | Bounty: Gnarlpine Furbolg (490) | 1438 | 42.22, 51.27 | 40.46, 50.73 | 1.8 | Senda (spawn en la base: Polestar a 1.8, Senda a 0.0) |
| turnin | Bounty: Gnarlpine Furbolg (490) | 1438 | 42.22, 51.27 | 40.46, 50.73 | 1.8 | Senda (spawn en la base: Polestar a 1.8, Senda a 0.0) |
| turnin | The Great Cat Spirit (98394) | 1450 | 54.5, 75.0 | 58.39, 73.52 | 4.2 | Senda (spawn en la base: Polestar a 4.2, Senda a 0.0) |
| accept | The Great Cat Spirit (98396) | 1450 | 54.5, 75.0 | 58.39, 73.52 | 4.2 | Senda (spawn en la base: Polestar a 4.2, Senda a 0.0) |
| turnin | The Great Cat Spirit (98396) | 1450 | 54.5, 75.0 | 58.39, 73.52 | 4.2 | Senda (spawn en la base: Polestar a 4.2, Senda a 0.0) |
| accept | Blessings of the Great Cat Spirit (98731) | 1450 | 54.5, 75.0 | 58.39, 73.52 | 4.2 | Senda (spawn en la base: Polestar a 4.2, Senda a 0.0) |

**Conclusión:** los dos mapas coinciden: de las coordenadas comunes solo se separan más de 1.0 entre 2 y 7 (según el personaje). Cuando es el mismo PNJ, acierta Senda (su punto es el spawn de la base `questie:quest/<id>`;
Polestar guarda el punto donde el PNJ camina: Shayla en Dolanaar, el Gran Espíritu Gato en Claro de la Luna). Cuando el PNJ es distinto, **ambos son válidos**: la misión tiene varios
iniciadores (p. ej. «Informa a Gryan Stoutmantle» (109) la da el Alguacil Dughan en Senda y el Ayudante Rainer en Polestar; «¡Busca redención!» (489) la dan Kyra Starsong o Syral Bladeleaf). La ruta
de Polestar elige el iniciador más cercano a su itinerario. «Plata de las olas» (86614) es un objeto del mundo y a Senda y Polestar les separan 4.3.
Los pasos con marcos no convertidos (Tierras de la Peste del Este, 1423) no entran en esta comparación porque Senda no tiene esos pasos en el mismo marco.

## 7. Pasos de clase que Senda tiene y Polestar no

Polestar no mete en la cadena Alianza ni los entrenamientos de clase como pasos detectables (solo notas «entrena con el instructor»), ni los demonios del brujo, ni las formas del druida, ni los
teletransportes del mago (viven en las guías de clase aparte, sección 4). Recuento de pasos con `if.class` de la clase:

| Personaje | Senda (por `do`) | Polestar importado (por `do`) |
|---|---|---|
| Brujo gnomo | train 21, note 5 | note 19, accept 12, turnin 12, complete 7, goto 6, fly 2, level 1, getfp 1 |
| Mago humano | train 23, note 4, goto 1 | note 19, goto 9, accept 6, turnin 6, complete 3, fly 3, level 1 |
| Druida elfo de la noche | train 20, note 1 | turnin 22, accept 21, goto 17, note 14, fly 13, complete 11, loot 3, getfp 2, use 2, level 2, buy 1 |

Y los pasos `do = "train"` (detectados por hechizo con `spells`): Brujo gnomo 35, Mago humano 40, Druida elfo de la noche 29. Polestar no tiene ninguno equivalente (sus 18-24 notas de entrenamiento son manuales).

### Brujo gnomo: pasos de clase de Senda sin misión

- `shared/a12-loch-modan` (train): Brujo: entrena en la Caverna Abandonada (niveles 12 y 14): Cauce de salud, Maldición de temeridad y Drenar vid
- `shared/a16-hall-of-thanes` (note): Brujo: entrena lo del 16 en la Caverna Abandonada (y lo del 14 si te faltaba).
- `shared/a17-paramos-de-poniente` (train): Brujo: entrena Crear piedra de alma (nivel 18) en el sótano de El Cordero Degollado.
- `shared/a19-crestagrana` (train): Brujo: entrena lo del 20 (Maldición de los elementos, Armadura demoníaca, Ritual de invocación, Lluvia de fueg
- `shared/a19-crestagrana` (note): Brujo: aprende Bastones con Woo Ping (10 de plata). Lo necesitas para el Bastón de Soran'ruk.
- `shared/a22-bosque-del-ocaso` (train): Brujo: en Ventormenta, entrena lo del 22 (Ojo de Kilrogg).
- `shared/a22-bosque-del-ocaso` (train): Brujo: entrena lo del 24 (Drenar maná, Captar demonios).
- `shared/a26-los-humedales` (train): Brujo: entrena lo del 26 (Maldición de la lengua, Detectar invisibilidad).
- `shared/a26-los-humedales` (train): Brujo: entrena lo del 28 (Desterrar, Crear pirorroca).
- `shared/a26-los-humedales` (train): Brujo: entrena lo del 30 (Subyugar demonio, Piroinferno).
- `shared/a30-stv-norte` (train): Entrena el 30 con Ursula Deline, en la Taberna del Cordero Degollado (Ventormenta).
- `shared/a34-desolace` (train): Entrena el 32-34 con Briarthorn, en la Caverna Desolada de Forjaz.
- `shared/a34-desolace` (note): Brujo: vuela a Menethil, barco a Auberdine y vuela al Pico del Espolón; baja a pie hasta Punta de Nijel.
- `shared/a40-ciudad` (train): Entrena del 36 al 40 con Briarthorn: piedra de hechizos y Aullido de terror.
- `shared/a40-ciudad` (note): Brujo: tu instructor te manda a por el Corcel nefasto, que incluye la equitación. Síguelo en la guía de clase.
- `shared/a44-badlands` (train): Brujo al 42: entrena Espiral mortal en Forjaz cuando pases (por Thelsamar).
- `shared/a48-searing-gorge` (train): Brujo: entrena los hechizos del nivel 46.
- `shared/a48-searing-gorge` (train): Brujo: entrena los hechizos del nivel 48.
- `shared/a50-ungoro` (train): Brujo: entrena los hechizos del nivel 50.
- `shared/a50-ungoro` (train): Brujo: entrena los hechizos del nivel 52.
- `shared/a52-felwood` (note): Brujo: Niby el Todopoderoso, en el centro de Frondavil, empieza la cadena del Inferno (la cubre la sección de 
- `shared/a55-burning-steppes` (train): Brujo: entrena los hechizos del nivel 52.
- `shared/a55-burning-steppes` (train): Brujo: entrena los hechizos del nivel 54.
- `shared/a55-burning-steppes` (train): Brujo: entrena los hechizos del nivel 56.
- `shared/a57-western-plaguelands` (train): Brujo: entrena los hechizos del nivel 58.
- `shared/a60-endgame` (train): Brujo: entrena los hechizos del nivel 60.

### Mago humano: pasos de clase de Senda sin misión

- `shared/a12-loch-modan` (train): Mago: entrena en la Sala Mística (niveles 12 y 14): Empapar magia, Caída lenta y Deflagración Arcana.
- `shared/a16-hall-of-thanes` (train): Mago: entrena Fogonazo en la Sala Mística (y lo del 14 si te faltaba).
- `shared/a17-paramos-de-poniente` (train): Mago: entrena lo del 18 (Amplificar magia, Deshacer maldición inferior) en el Sagrario de los Magos.
- `shared/a19-crestagrana` (train): Mago: entrena lo del 20 (Traslación, Evocación, Escudo de maná, Custodia de Fuego, Ventisca).
- `shared/a19-crestagrana` (train): Mago: aprende Teletransporte a Ventormenta y a Forjaz con Larimaine Purdue, la instructora de portales.
- `shared/a22-bosque-del-ocaso` (train): Mago: en Ventormenta, entrena lo del 22 (Chamuscar, Custodia de Escarcha).
- `shared/a22-bosque-del-ocaso` (train): Mago: entrena lo del 24 (Contrahechizo).
- `shared/a26-los-humedales` (train): Mago: entrena lo del 26 (Cono de frío).
- `shared/a26-los-humedales` (train): Mago: entrena lo del 28 (Conjurar ágata de maná).
- `shared/a26-los-humedales` (train): Mago: entrena lo del 30 (Armadura de hielo). Teletransporte a Darnassus con el instructor de portales.
- `shared/a30-stv-norte` (train): Entrena el 30 con Jennea Cannon, en el Barrio de los Magos de Ventormenta.
- `shared/a30-stv-norte` (note): Al 32 y al 34 toca entrenar. Mago: Teletransporte a Ventormenta, entrena y vuelve volando.
- `shared/a34-desolace` (train): Entrena el 32-34 con Bink, en el Distrito Místico de Forjaz.
- `shared/a34-desolace` (note): Mago: Teletransporte a Darnassus, vuela al Pico del Espolón y baja a pie hasta Punta de Nijel.
- `shared/a34-desolace` (train): Mago al 36-38: Teletransporte a Ventormenta, entrena con Jennea y vuelve con la piedra de hogar.
- `shared/a40-ciudad` (train): Entrena el 40 con Bink: portales a Ventormenta y Forjaz.
- `shared/a40-ciudad` (goto): Mago humano: coge el tranvía a Ventormenta y ve al este del Bosque de Elwynn, al Campamento Maderero.
- `shared/a40-ciudad` (note): Aprende Equitación con Randal Hunter (100 de oro) y compra el caballo a Katie Hunter (20 de oro).
- `shared/a44-badlands` (note): Al 42 y al 44 toca entrenar. Mago: Teletransporte a Forjaz y vuelve con la piedra de hogar.
- `shared/a48-searing-gorge` (train): Mago: entrena los hechizos del nivel 46.
- `shared/a48-searing-gorge` (train): Mago: entrena los hechizos del nivel 48.
- `shared/a50-ungoro` (train): Mago: entrena los hechizos del nivel 50.
- `shared/a50-ungoro` (train): Mago: entrena los hechizos del nivel 52.
- `shared/a55-burning-steppes` (train): Mago: entrena los hechizos del nivel 52.
- `shared/a55-burning-steppes` (train): Mago: entrena los hechizos del nivel 54.
- `shared/a55-burning-steppes` (train): Mago: entrena los hechizos del nivel 56.
- `shared/a57-western-plaguelands` (train): Mago: entrena los hechizos del nivel 58.
- `shared/a60-endgame` (train): Mago: entrena los hechizos del nivel 60.

### Druida elfo de la noche: pasos de clase de Senda sin misión

- `shared/a19-crestagrana` (train): Druida: entrena lo del 20 (Fuego estelar, Renacer) con Sheldras Moontree, en El Parque de Ventormenta.
- `shared/a22-bosque-del-ocaso` (train): Druida: en Ventormenta, entrena lo del 22 (Calmar animal) en El Parque.
- `shared/a22-bosque-del-ocaso` (train): Druida: entrena lo del 24 (Eliminar maldición y las técnicas felinas nuevas) en El Parque.
- `shared/a26-los-humedales` (train): Druida: entrena lo del 26 (Carrerilla, Suprimir veneno) en El Parque de Ventormenta.
- `shared/a26-los-humedales` (train): Druida: en Forjaz no hay instructor. Lanza Teletransporte: Claro de la Luna y entrena lo del 28 (Rugido desafi
- `shared/a26-los-humedales` (train): Druida: entrena lo del 30 (Forma de viaje, Tranquilidad) con Loganaar en el Claro de la Luna.
- `shared/a30-stv-norte` (train): Entrena el 30 con Sheldras Moontree, en El Parque de Ventormenta: Forma de viaje y Tranquilidad.
- `shared/a30-stv-norte` (note): Al 32 y al 34 toca entrenar. Druida: Teletransporte: Claro de la Luna, entrena con Loganaar y vuelve con la pi
- `shared/a34-desolace` (train): Druida: lanza Teletransporte: Claro de la Luna y entrena el 32-34 con Loganaar (Rastrear humanoides, Devastar)
- `shared/a34-desolace` (train): Druida al 36-38: Teletransporte: Claro de la Luna, entrena con Loganaar (Abalanzarse, Regeneración frenética) 
- `shared/a40-ciudad` (train): Druida: lanza Teletransporte: Claro de la Luna y entrena el 40 con Loganaar: Forma de oso temible, Estimular y
- `shared/a44-badlands` (train): Druida al 42 y al 44: Teletransporte: Claro de la Luna, entrena con Loganaar (Piel de corteza al 44) y vuelve 
- `shared/a48-searing-gorge` (train): Druida: entrena los hechizos del nivel 46 con Loganaar (Teletransporte: Claro de la Luna).
- `shared/a48-searing-gorge` (train): Druida: entrena los hechizos del nivel 48 con Loganaar (Teletransporte: Claro de la Luna).
- `shared/a50-ungoro` (train): Druida: lanza Teletransporte: Claro de la Luna y entrena los hechizos del nivel 50 con Loganaar (Don de lo Sal
- `shared/a50-ungoro` (train): Druida: entrena los hechizos del nivel 52 en El Parque de Ventormenta.
- `shared/a55-burning-steppes` (train): Druida: entrena los hechizos del nivel 52 en El Parque de Ventormenta.
- `shared/a55-burning-steppes` (train): Druida: entrena los hechizos del nivel 54 en El Parque de Ventormenta.
- `shared/a55-burning-steppes` (train): Druida: entrena los hechizos del nivel 56 en El Parque de Ventormenta.
- `shared/a57-western-plaguelands` (train): Druida: lanza Teletransporte: Claro de la Luna y entrena los hechizos del nivel 58 con Loganaar.
- `shared/a60-endgame` (train): Druida: entrena los hechizos del nivel 60 en El Parque de Ventormenta.

Qué hay que conservar de Senda en la fusión (todo lo anterior más lo que sigue, que no está en la guía importada):

- **Brujo:** `10-voidwalker`, `20-succubus`, `30-felhunter`, `40-felsteed`, `50-inferno`, `60-doomguard-dreadsteed` y los `train` por nivel.
- **Mago:** las secciones `mg-*` (15-60), con los teletransportes (`mg-20-teleport`) y los `train` de `mg-38-train` y `mg-40-train`.
- **Druida:** `dr-10-bear`, `dr-11-lunaclaw`, `dr-14-poison`, `dr-16-aquatic`, `dr-18-sea-lion`, `dr-20-cat`, `dr-52-torwa`, `dr-60-endgame` y los `train`.

## 8. Longitud estimada

No hay tiempos en ninguna de las dos fuentes, así que es una estimación **relativa** con una heurística fija: coste por acción (coger/entregar 0,4 min, matar/recoger 3 min, `goto` 0,6, vuelo 3,
`train`/`buy` 0,5-0,8, pasos encadenados 0,15) más el recorrido entre pasos consecutivos del mismo mapa (1 % del mapa ≈ 1,7 s a pie). No cuenta repetir muertes, grupos ni colas de mazmorra.
Sirve para comparar rutas, no para prometer horas.

| Personaje | Polestar: acciones + recorrido | Senda: acciones + recorrido | Ratio |
|---|---|---|---:|
| Brujo gnomo | 57 h + 10 h = **67 h** | 20 h + 4 h = **24 h** | 2.7x |
| Mago humano | 56 h + 10 h = **66 h** | 20 h + 4 h = **24 h** | 2.7x |
| Druida elfo de la noche | 58 h + 10 h = **68 h** | 19 h + 4 h = **23 h** | 2.9x |

Polestar es entre 2,7 y 3x más larga que Senda: la ruta de Senda sigue siendo la razón de ser del proyecto (1-60 con menos de la mitad de las misiones y del recorrido), y el filtro de eficiencia de la fase 5.2
del plan debe **quitar** a Polestar tres de cada cuatro pasos, no añadir a Senda.

## 9. Qué debe hacer la fase de fusión con esto

1. Arreglar los dos fallos del importador de la sección 1 (modo cadena con ids únicos; `fly` final sin `zone`) y repetir; las carpetas actuales se pueden regenerar.
2. Importar las guías de clase de Polestar (sección 4) y fusionarlas con `10-voidwalker`/`mg-*`/`dr-*`: son la mayor parte de lo «solo en Senda».
3. Decidir por zona con `route_score.py`: la lista «solo en Polestar» son candidatas, no obligaciones; en especial Hillsbrad, Arathi, Ashenvale 2, Cardo y Tierras de la Peste.
4. Fijar el orden por bloques (sección 5): Loch Modan/Crestagrana y Humedales/Ashenvale son decisiones de ruta, no de datos; el resto se resuelve con las reglas de «lo hecho a mano gana».
5. Coordenadas: usar la base (spawn del PNJ) cuando difieran; ninguna de las 2-7 diferencias bloquea nada.
6. Traducir (`[EN]` en ≈ 25 % de los pasos) y expresar las condiciones vivas (`optional` en ≈ 10 %) antes de promover algo de `unverified`.

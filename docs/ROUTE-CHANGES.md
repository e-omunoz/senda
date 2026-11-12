# Fusión de rutas: cambios en las guías de los tres personajes

> Fase de fusión del [plan](PLAN-POLESTAR.md) (§5): la ruta filtrada de Senda sigue siendo la base; de Polestar se toman
> orden, coordenadas y misiones que puntúan alto y caen en el camino; del filtro de eficiencia
> ([EFFICIENCY.md](EFFICIENCY.md), `tools/route_score.py`) se aplican sus decisiones keep/optional/drop.
> Guías: `gnome-warlock`, `human-mage`, `nightelf-druid` y las secciones compartidas de la Alianza (`data/shared/`), que
> usan las tres y se han cambiado una sola vez. Entrada: [IMPORT-REPORT.md](IMPORT-REPORT.md), `data/scores/` del 12-nov-2026,
> rutas importadas de Polestar (`*-ps`, commit `19bd636e`) y forever-db 2026.11.1 (con su `corrections/quests.json`).

## 1. Antes y después

`tools/route_score.py --report` antes de tocar nada y después de todos los cambios (bandas recalculadas con todas las guías).
«Misiones» cuenta las que la guía completa; «minutos» suma el tiempo estimado de las misiones más el gasto de ruta
(viajes entre zonas, vuelos, piedra); «XP» es la de las misiones más sus muertes. «Ruta sin opcionales» deja fuera
las misiones con algún paso `optional` (lo que hace quien activa «Saltar los pasos opcionales»).

| Personaje | | Misiones | Minutos | XP | Ruta sin opcionales: misiones | minutos | XP | drop que quedan |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Brujo gnomo | antes | 395 | 3.027 (50 h 27 min) | 1.204.122 | 348 | 2.879 (47 h 59 min) | 1.088.640 | 35 |
|  | después | 369 | 2.703 (45 h 03 min) | 1.100.769 | 282 | 1.901 (31 h 41 min) | 770.028 | 12 |
| Mago humano | antes | 403 | 3.087 (51 h 27 min) | 1.215.092 | 358 | 2.802 (46 h 42 min) | 1.105.002 | 29 |
|  | después | 383 | 2.788 (46 h 28 min) | 1.114.510 | 297 | 1.852 (30 h 52 min) | 789.910 | 11 |
| Druida elfo de la noche | antes | 390 | 3.104 (51 h 44 min) | 1.164.510 | 360 | 2.932 (48 h 52 min) | 1.076.459 | 37 |
|  | después | 364 | 2.742 (45 h 42 min) | 1.054.264 | 283 | 1.908 (31 h 48 min) | 751.753 | 11 |

Lectura:

- **Brujo gnomo:** 26 misiones menos y **324 min menos** (103.353 XP menos) con todo; sin opcionales, 1.901 min frente a 2.879 y 770.028 XP frente a 1.088.640.
- **Mago humano:** 20 misiones menos y **299 min menos** (100.582 XP menos) con todo; sin opcionales, 1.852 min frente a 2.802 y 789.910 XP frente a 1.105.002.
- **Druida elfo de la noche:** 26 misiones menos y **362 min menos** (110.246 XP menos) con todo; sin opcionales, 1.908 min frente a 2.932 y 751.753 XP frente a 1.076.459.

La XP que sale de la ruta obligatoria (las opcionales de 50-60 son las que más pesan: «Shizzle's Flyer», «Winterfall
Activity», «Demon Dogs»...) se recupera haciendo las opcionales o matando enemigos: los pasos `do = "level"` de cada zona
ya lo dicen. Las «drop que quedan» son las excepciones de la sección 4: el modelo las sigue marcando y la ruta las conserva
por un motivo que el modelo no ve.

Los números son estimaciones del modelo (EFFICIENCY.md §4), no tiempos medidos: sirven para comparar, no para prometer horas.

## 2. Misiones quitadas (43 + 2 por hechos equivocados)

Decisión `drop` del filtro. En una sección compartida cuenta la decisión **más favorable** de las guías que la ven
(keep > optional > drop), para que la sección sea la misma para los tres. La segunda tanda (marcada «2.ª») son las que
bajaron a `drop` al recalcular tras la primera: al quitar una misión, el viaje que compartía pasa a las que quedan.
El registro de cada paso quitado va comentado debajo de la tabla para poder volver a ponerlo.

| Misión | Personajes | Sección | XP · tiempo | Motivo |
|---|---|---|---|---|
| Return the Comb (154) | brujo, mago, druida | a22-bosque-del-ocaso | +200 XP · 1,5 min | lenta: 33% de la mediana del 21-25 |
| Blisters on the Land (275) | brujo, mago, druida | a26-los-humedales | +3.730 XP · 19,4 min | requiere «Fire Taboo», que sale de la ruta |
| Tramping Paws (276) | brujo, mago, druida | a26-los-humedales | +500 XP · 15,0 min | lenta: 6% de la mediana del 26-30 |
| Fire Taboo (277) | brujo, mago, druida | a26-los-humedales | +2.280 XP · 9,2 min | requiere «Tramping Paws», que sale de la ruta |
| In Search of the Excavation Team (306) | brujo, mago, druida | a26-los-humedales | +490 XP · 2,5 min | lenta: 37% de la mediana del 26-30 |
| Protecting the Shipment (309) | brujo, mago | a12-loch-modan | +1.050 XP · 8,2 min | requiere «After the Ambush», que sale de la ruta |
| A Favor for Evershine (319) | brujo | 02-dun-morogh | +1.979 XP · 21,1 min | lenta: 34% de la mediana del 6-10 |
| Return to Bellowfiz (320) | brujo | 02-dun-morogh | +875 XP · 0,7 min | requiere «A Favor for Evershine», que sale de la ruta |
| After the Ambush (454) | brujo, mago | a12-loch-modan | +110 XP · 1,0 min | lenta: 30% de la mediana del 11-15 |
| Report to Mountaineer Rockgar (468) | brujo, mago, druida | a26-los-humedales | +170 XP · 1,3 min | lenta: 31% de la mediana del 26-30 |
| Buzzbox 323 (1002) | druida | 03-darkshore | +3.188 XP · 30,1 min | lenta: 30% de la mediana del 11-15 |
| Buzzbox 525 (1003) | druida | 03-darkshore | +2.260 XP · 7,2 min | requiere «Buzzbox 323», que sale de la ruta |
| Reagents for Reclaimers Inc. (1459) | brujo, mago, druida | a34-desolace, a38-valle-de-huesos | +3.098 XP · 14,3 min | lenta: 32% de la mediana del 36-40 |
| Plagued Lands (2118) | druida | 03-darkshore | +975 XP · 7,3 min | lenta: 48% de la mediana del 11-15 |
| Cleansing of the Infected (2138) | druida | 03-darkshore | +3.170 XP · 24,6 min | requiere «Plagued Lands», que sale de la ruta |
| Tharnariun's Hope (2139) | druida | 03-darkshore | +1.470 XP · 6,9 min | requiere «Cleansing of the Infected», que sale de la ruta |
| The Temple of the Moon (2519) | druida | 02-teldrassil | +85 XP · 1,1 min | lenta: 29% de la mediana del 6-10 |
| A Refugee's Quandary (3361) | brujo | 01-coldridge | +250 XP · 2,9 min | lenta: 28% de la mediana del 1-5 |
| Are We There, Yeti? (3783) | brujo, mago, druida | a54-winterspring | +13.438 XP · 32,0 min | lenta: 26% de la mediana del 56-60 |
| Milly Osworth (3903) | mago | 01-northshire | +35 XP · 0,6 min | lenta: 27% de la mediana del 1-5 |
| FIFTY! YEP! (4283) | brujo, mago, druida | a55-burning-steppes | +51.775 XP · 114,0 min | lenta: 29% de la mediana del 56-60 |
| Threat of the Winterfall (5082) | brujo, mago, druida | a54-winterspring | +13.616 XP · 34,5 min | lenta: 25% de la mediana del 56-60 |
| Defenders of Darrowshire (5211) | brujo, mago, druida | a58-eastern-plaguelands | +5.650 XP · 25,6 min | lenta: 12% de la mediana del 56-60 |
| To Winterspring! (5249) | brujo, mago, druida | a52-felwood, a54-winterspring | +580 XP · 1,2 min | lenta: 35% de la mediana del 51-55 |
| A Bundle of Trouble (5545) | mago | 02-elwynn | +775 XP · 5,2 min | lenta: 47% de la mediana del 6-10 |
| Beads for Salfa (8469) | brujo, mago, druida | a54-winterspring | +6.250 XP · 15,9 min | lenta: 25% de la mediana del 56-60 |
| Destruction in Deadmines (92819) | brujo, mago | a21-minas-de-la-muerte | +140 XP · 2,6 min | lenta: 17% de la mediana del 21-25 |
| Camping 101: Tailoring (96057) | brujo | 02-dun-morogh | +216 XP · 2,0 min | lenta: 45% de la mediana del 11-15 |
| The Goddess Provides (97979) | druida | 01-shadowglen | +40 XP · 2,4 min | lenta: 17% de la mediana del 1-5 |
| Crown of the Earth (98046) | druida | 02-teldrassil | +90 XP · 1,0 min | lenta: 36% de la mediana del 11-15 |
| Crown of the Earth (98065) | druida | 02-teldrassil | +90 XP · 1,2 min | lenta: 32% de la mediana del 11-15 |
| Return the Statuette (98189) | brujo, mago, druida | a26-los-humedales | +200 XP · 1,4 min | lenta: 29% de la mediana del 26-30 |
| Secure the Mountain (98319) | brujo | 02-dun-morogh | +180 XP · 2,4 min | lenta: 33% de la mediana del 6-10 |
| Secure the Mountain (98323) | brujo | 02-dun-morogh | +70 XP · 0,9 min | lenta: 34% de la mediana del 6-10 |
| Alther's Mill (98386) | brujo, mago, druida | a19-crestagrana | +3.390 XP · 34,7 min | lenta: 32% de la mediana del 21-25 |
| The Sisterhood of Elune (98391) | druida | 02-teldrassil | +85 XP · 1,1 min | lenta: 27% de la mediana del 6-10 |
| Unrequited Love (98461) | druida | 03-darkshore, a26-los-humedales | +136 XP · 2,0 min | lenta: 15% de la mediana del 26-30 |
| Easing Suffering (99073) | druida | 02-teldrassil | +85 XP · 4,8 min | lenta: 7% de la mediana del 11-15 |
| Dawn in the Mountains (99158) | brujo | 02-dun-morogh | +70 XP · 0,8 min | lenta: 28% de la mediana del 6-10 |
| Secure the Mountain (98322) (2.ª) | brujo | 02-dun-morogh | +70 XP · 0,8 min | lenta: 44% de la mediana del 6-10 — sola (70 XP) tras quitar 98319 y 98323 |
| Resupplying the Excavation (273) (2.ª) | brujo, mago | a12-loch-modan | +270 XP · 2,6 min | lenta: 27% de la mediana del 11-15 — sin la escolta de Miran (309, fuera) queda en 27% de la mediana del 11-15 |
| The Greenwarden (463) (2.ª) | brujo, mago, druida | a26-los-humedales | +330 XP · 2,9 min | lenta: 22% de la mediana del 26-30 — sin «Tramping Paws» (276) la subida al Cinturón Verde es solo para ella: 22% de la mediana del 26-30 |
| In Search of the Excavation Team (305) (2.ª) | brujo, mago, druida | a26-los-humedales | +975 XP · 4,6 min | lenta: 44% de la mediana del 26-30 — sin «In Search of the Excavation Team» (306) el desvío a Tarrel es solo para ella: 44% de la mediana del 26-30 |

### Hechos equivocados: el PNJ no ofrece la misión en ese momento

forever-db trae estos requisitos solo en `corrections/quests.json` (grabaciones de jugadores y comprobaciones en el juego,
las mismas que usa Polestar); `data/prereq.json` y `route_score.py` no los leen. Senda cogía las dos en la primera visita a
Menethil, y nadie las ha visto ofrecidas así.

- **This Land Was Their Land (98230)**, a26-los-humedales: corrections/quests.json (#1299): Stoutfist solo la ofrece tras entregar «Defeat Nek'rosh» (474), que no está en la ruta.
- **Crimson Crate Delivery (98240)**, a26-los-humedales: corrections/quests.json (#1134): Halloran solo la ofrece tras «Crocs of the Sky» (98072, cadena 484-471-98072), que no está en la ruta.

<details><summary>Pasos quitados (TOML comentado)</summary>

```toml
# ---- 154 Return the Comb
# data/shared/a22-bosque-del-ocaso.toml
# [[step]]
# id = "a22dw-038"
# do = "accept"
# quest = 154
# reqlevel = 20
# npc = 302
# at = [1431, 82.0, 59.1]
# text = "Coge la vuelta para Madame Eva."
# status = "unverified"
# sources = ["questie:quest/154"]
#
# data/shared/a22-bosque-del-ocaso.toml
# [[step]]
# id = "a22dw-039"
# do = "turnin"
# quest = 154
# npc = 265
# at = [1431, 75.8, 45.3]
# text = "Entrega el peine a Madame Eva."
# status = "unverified"
# sources = ["questie:quest/154"]
#
# ---- 275 Blisters on the Land
# data/shared/a26-los-humedales.toml
# [[step]]
# id = "a26wl-075"
# do = "accept"
# quest = 275
# reqlevel = 20
# npc = 1244
# at = [1437, 56.4, 40.4]
# text = "Coge la de las enredaderas de la ciénaga."
# status = "unverified"
# sources = ["questie:quest/275"]
#
# data/shared/a26-los-humedales.toml
# [[step]]
# id = "a26wl-076"
# do = "complete"
# quest = 275
# at = [1437, 33.0, 33.0]
# text = "Mata 12 trepadoras de la ciénaga camino de Menethil."
# status = "unverified"
# sources = ["questie:quest/275"]
#
# data/shared/a26-los-humedales.toml
# [[step]]
# id = "a26wl-088"
# do = "turnin"
# quest = 275
# npc = 1244
# at = [1437, 56.4, 40.4]
# text = "Vuelve al Cinturón Verde y entrega las trepadoras a Rethiel."
# status = "unverified"
# sources = ["questie:quest/275"]
#
# ---- 276 Tramping Paws
# data/shared/a26-los-humedales.toml
# [[step]]
# id = "a26wl-055"
# do = "accept"
# quest = 276
# reqlevel = 20
# npc = 1244
# at = [1437, 56.4, 40.4]
# text = "Coge la misión de los gnolls Pellejomusgo."
# status = "unverified"
# sources = ["questie:quest/276"]
#
# data/shared/a26-los-humedales.toml
# [[step]]
# id = "a26wl-063"
# do = "complete"
# quest = 276
# at = [1437, 61.8, 68.0]
# text = "Al sur, mata 15 gnolls y 10 chuchos Pellejomusgo."
# tip = "De paso, en la Roca Thelgen (50, 62) consigue la glándula de acechador para Caitlin."
# status = "unverified"
# sources = ["questie:quest/276"]
#
# data/shared/a26-los-humedales.toml
# [[step]]
# id = "a26wl-065"
# do = "turnin"
# quest = 276
# npc = 1244
# at = [1437, 56.4, 40.4]
# text = "Vuelve con Rethiel y entrega los gnolls."
# status = "unverified"
# sources = ["questie:quest/276"]
#
# ---- 277 Fire Taboo
# data/shared/a26-los-humedales.toml
# [[step]]
# id = "a26wl-066"
# do = "accept"
# quest = 277
# reqlevel = 20
# npc = 1244
# at = [1437, 56.4, 40.4]
# text = "Coge la del pedernal."
# status = "unverified"
# sources = ["questie:quest/277"]
#
# data/shared/a26-los-humedales.toml
# [[step]]
# id = "a26wl-070"
# do = "complete"
# quest = 277
# at = [1437, 40.0, 32.0]
# text = "Al oeste del Cinturón Verde, mata gnolls Pellejomusgo hasta tener 9 pedernales."
# status = "unverified"
# sources = ["questie:quest/277"]
#
# data/shared/a26-los-humedales.toml
# [[step]]
# id = "a26wl-074"
# do = "turnin"
# quest = 277
# npc = 1244
# at = [1437, 56.4, 40.4]
# text = "Entrega el pedernal a Rethiel."
# status = "unverified"
# sources = ["questie:quest/277"]
#
# ---- 306 In Search of the Excavation Team
# data/shared/a26-los-humedales.toml
# [[step]]
# id = "a26wl-043"
# do = "accept"
# quest = 306
# reqlevel = 21
# npc = 1076
# at = [1437, 38.9, 52.3]
# text = "Coge la nota de Merrin para Tarrel."
# status = "unverified"
# sources = ["questie:quest/306"]
#
# data/shared/a26-los-humedales.toml
# [[step]]
# id = "a26wl-081"
# do = "turnin"
# quest = 306
# npc = 2096
# at = [1437, 11.5, 52.2]
# text = "Entrega la nota de Merrin a Tarrel Rockweaver."
# status = "unverified"
# sources = ["questie:quest/306"]
#
# ---- 309 Protecting the Shipment
# data/shared/a12-loch-modan.toml
# [[step]]
# id = "a12lm-080"
# do = "accept"
# quest = 309
# reqlevel = 10
# npc = 1379
# at = [1432, 52.2, 69.4]
# escort = true
# text = "Escolta a Miran y el cargamento hasta la excavación."
# status = "unverified"
# sources = ["questie:quest/309"]
#
# data/shared/a12-loch-modan.toml
# [[step]]
# id = "a12lm-081"
# do = "turnin"
# quest = 309
# npc = 1344
# at = [1432, 65.9, 65.6]
# text = "Al llegar, informa al Prospector Ironband."
# status = "unverified"
# sources = ["questie:quest/309"]
#
# ---- 319 A Favor for Evershine
# data/guides/gnome-warlock/02-dun-morogh.toml
# [[step]]
# id = "dun-morogh-056"
# do = "accept"
# quest = 319
# reqlevel = 2
# npc = 1374
# at = [1426, 30.2, 45.7]
# text = "Coge el favor de Rejold: osos, jabalíes y leopardos."
# status = "unverified"
# sources = ["questie:quest/319", "questie:npc/1374"]
#
# data/guides/gnome-warlock/02-dun-morogh.toml
# [[step]]
# id = "dun-morogh-065"
# do = "complete"
# quest = 319
# at = [1426, 36.0, 47.0]
# text = "Termina los osos, jabalíes y leopardos que te falten para Rejold."
# status = "unverified"
# sources = ["questie:quest/319", "questie:npc/1196", "questie:npc/1127", "questie:npc/1201"]
#
# data/guides/gnome-warlock/02-dun-morogh.toml
# [[step]]
# id = "dun-morogh-070"
# do = "turnin"
# quest = 319
# npc = 1374
# at = [1426, 30.2, 45.7]
# text = "Entrega el favor a Rejold."
# status = "unverified"
# sources = ["questie:quest/319", "questie:npc/1374"]
#
# ---- 320 Return to Bellowfiz
# data/guides/gnome-warlock/02-dun-morogh.toml
# [[step]]
# id = "dun-morogh-071"
# do = "accept"
# quest = 320
# reqlevel = 2
# npc = 1374
# at = [1426, 30.2, 45.7]
# text = "Coge la vuelta con Bellowfiz."
# status = "unverified"
# sources = ["questie:quest/320", "questie:npc/1374"]
#
# data/guides/gnome-warlock/02-dun-morogh.toml
# [[step]]
# id = "dun-morogh-075"
# do = "turnin"
# quest = 320
# npc = 1378
# at = [1426, 49.4, 48.4]
# text = "Entrega a Bellowfiz."
# status = "unverified"
# sources = ["questie:quest/320", "questie:npc/1378"]
#
# ---- 454 After the Ambush
# data/shared/a12-loch-modan.toml
# [[step]]
# id = "a12lm-078"
# do = "accept"
# quest = 454
# reqlevel = 10
# npc = 2057
# at = [1432, 52.2, 69.3]
# text = "Coge la misión de Huldar."
# tip = "Al aceptarla aparecen enanos Hierro Negro que atacan el carro: mátalos."
# status = "unverified"
# sources = ["questie:quest/454"]
#
# data/shared/a12-loch-modan.toml
# [[step]]
# id = "a12lm-079"
# do = "turnin"
# quest = 454
# npc = 1379
# at = [1432, 52.2, 69.4]
# text = "Habla con Miran."
# status = "unverified"
# sources = ["questie:quest/454", "questie:npc/1379"]
#
# ---- 468 Report to Mountaineer Rockgar
# data/shared/a26-los-humedales.toml
# [[step]]
# id = "a26wl-005"
# do = "accept"
# quest = 468
# reqlevel = 19
# npc = 1340
# at = [1432, 32.6, 49.7]
# text = "En Thelsamar, coge con el Montañero Kadrell el aviso para el Montañero Rockgar."
# status = "unverified"
# sources = ["questie:quest/468", "questie:npc/1340"]
#
# data/shared/a26-los-humedales.toml
# [[step]]
# id = "a26wl-006"
# do = "turnin"
# quest = 468
# npc = 1342
# at = [1432, 25.4, 10.4]
# text = "Sigue el camino al norte hasta Dun Algaz y habla con Rockgar."
# status = "unverified"
# sources = ["questie:quest/468", "questie:npc/1342"]
#
# ---- 1002 Buzzbox 323
# data/guides/nightelf-druid/03-darkshore.toml
# [[step]]
# id = "neds-048"
# do = "accept"
# quest = 1002
# reqlevel = 7
# at = [1439, 41.96, 28.62]
# text = "Coge del buzón la siguiente: colmillos de acechaluna."
# tip = "Los acechalunas salen por todo el norte: mátalos de camino."
# status = "unverified"
# sources = ["questie:quest/1002", "questie:object/17183"]
#
# data/guides/nightelf-druid/03-darkshore.toml
# [[step]]
# id = "neds-060"
# do = "complete"
# quest = 1002
# at = [1439, 48.0, 30.0]
# text = "Termina los colmillos de acechaluna."
# status = "unverified"
# sources = ["questie:quest/1002"]
#
# data/guides/nightelf-druid/03-darkshore.toml
# [[step]]
# id = "neds-061"
# do = "turnin"
# quest = 1002
# at = [1439, 51.29, 24.57]
# text = "Echa los colmillos en el Buzón 323, junto al puente."
# status = "unverified"
# sources = ["questie:quest/1002", "questie:object/17184"]
#
# ---- 1003 Buzzbox 525
# data/guides/nightelf-druid/03-darkshore.toml
# [[step]]
# id = "neds-062"
# do = "accept"
# quest = 1003
# reqlevel = 7
# at = [1439, 51.29, 24.57]
# text = "Coge del buzón la última: cabelleras de oso canoso (al sur)."
# status = "unverified"
# sources = ["questie:quest/1003", "questie:object/17184"]
#
# data/guides/nightelf-druid/03-darkshore.toml
# [[step]]
# id = "neds-096"
# do = "complete"
# quest = 1003
# at = [1439, 40.0, 79.5]
# text = "Mata osos de cardo canosos al suroeste de Onu para las cabelleras."
# status = "unverified"
# sources = ["questie:quest/1003"]
#
# data/guides/nightelf-druid/03-darkshore.toml
# [[step]]
# id = "neds-097"
# do = "turnin"
# quest = 1003
# at = [1439, 41.39, 80.56]
# text = "Echa las cabelleras en el Buzón 525."
# status = "unverified"
# sources = ["questie:quest/1003", "questie:object/17185"]
#
# ---- 1459 Reagents for Reclaimers Inc.
# data/shared/a34-desolace.toml
# [[step]]
# id = "a34-desolace-018"
# do = "accept"
# quest = 1459
# reqlevel = 30
# npc = 5638
# at = [1443, 66.2, 9.63]
# text = "Coge el segundo encargo: veneno de escórpido y piel de kodo vieja."
# tip = "Escórpidos y kodos están por toda la zona: complétala de paso."
# status = "unverified"
# sources = ["questie:quest/1459", "questie:npc/5638"]
#
# data/shared/a38-valle-de-huesos.toml
# [[step]]
# id = "a38-valle-de-huesos-018"
# do = "turnin"
# quest = 1459
# npc = 5638
# at = [1443, 66.2, 9.63]
# text = "Entrega el veneno y la piel a Kreldig."
# tip = "Las siguientes de Kreldig mandan al pecio Karnitol: sáltalas."
# status = "unverified"
# sources = ["questie:quest/1459", "questie:npc/5638"]
#
# ---- 2118 Plagued Lands
# data/guides/nightelf-druid/03-darkshore.toml
# [[step]]
# id = "neds-010"
# do = "accept"
# quest = 2118
# reqlevel = 10
# npc = 3701
# at = [1439, 38.84, 43.42]
# text = "Coge la misión de los osos de Tharnariun Treetender."
# tip = "Te da una trampa: si la pierdes, pide otra a Tharnariun."
# status = "unverified"
# sources = ["questie:quest/2118", "questie:npc/3701"]
#
# data/guides/nightelf-druid/03-darkshore.toml
# [[step]]
# id = "neds-018"
# do = "complete"
# quest = 2118
# at = [1439, 41.0, 48.0]
# text = "Busca un oso de cardo rabioso al este del camino y atrápalo con la trampa."
# tip = "Pon la trampa, atrae al oso encima y espera a que quede atrapado."
# status = "unverified"
# sources = ["questie:quest/2118"]
#
# data/guides/nightelf-druid/03-darkshore.toml
# [[step]]
# id = "neds-026"
# do = "turnin"
# quest = 2118
# npc = 3701
# at = [1439, 38.84, 43.42]
# text = "Vuelve a Auberdine. Entrega el oso a Tharnariun."
# status = "unverified"
# sources = ["questie:quest/2118", "questie:npc/3701"]
#
# ---- 2138 Cleansing of the Infected
# data/guides/nightelf-druid/03-darkshore.toml
# [[step]]
# id = "neds-027"
# do = "accept"
# quest = 2138
# reqlevel = 10
# npc = 3701
# at = [1439, 38.84, 43.42]
# text = "Coge la siguiente: mata osos rabiosos."
# status = "unverified"
# sources = ["questie:quest/2138", "questie:npc/3701"]
#
# data/guides/nightelf-druid/03-darkshore.toml
# [[step]]
# id = "neds-058"
# do = "complete"
# quest = 2138
# at = [1439, 44.0, 40.0]
# text = "Mata osos rabiosos por el camino hasta tener los que pide Tharnariun."
# status = "unverified"
# sources = ["questie:quest/2138"]
#
# data/guides/nightelf-druid/03-darkshore.toml
# [[step]]
# id = "neds-074"
# do = "turnin"
# quest = 2138
# npc = 3701
# at = [1439, 38.84, 43.42]
# text = "Entrega los osos a Tharnariun."
# status = "unverified"
# sources = ["questie:quest/2138", "questie:npc/3701"]
#
# ---- 2139 Tharnariun's Hope
# data/guides/nightelf-druid/03-darkshore.toml
# [[step]]
# id = "neds-075"
# do = "accept"
# quest = 2139
# reqlevel = 10
# npc = 3701
# at = [1439, 38.84, 43.42]
# text = "Coge la misión de la Madre de la guarida (al noreste; para el 18-19)."
# status = "unverified"
# sources = ["questie:quest/2139", "questie:npc/3701"]
#
# data/guides/nightelf-druid/03-darkshore.toml
# [[step]]
# id = "neds-129"
# do = "complete"
# quest = 2139
# at = [1439, 51.5, 38.3]
# text = "Mata a la Madre de la guarida, en su cueva al este."
# tip = "Tiene cachorros: llévalos de uno en uno y guarda pociones."
# status = "unverified"
# sources = ["questie:quest/2139"]
#
# data/guides/nightelf-druid/03-darkshore.toml
# [[step]]
# id = "neds-139"
# do = "turnin"
# quest = 2139
# npc = 3701
# at = [1439, 38.84, 43.42]
# text = "Entrega la Madre de la guarida a Tharnariun."
# status = "unverified"
# sources = ["questie:quest/2139", "questie:npc/3701"]
#
# ---- 2519 The Temple of the Moon
# data/guides/nightelf-druid/02-teldrassil.toml
# [[step]]
# id = "netd-088"
# do = "accept"
# quest = 2519
# reqlevel = 5
# npc = 7316
# at = [1457, 28.94, 45.8]
# text = "Coge su misión para el Templo de la Luna."
# status = "unverified"
# sources = ["questie:quest/2519", "questie:npc/7316"]
#
# data/guides/nightelf-druid/02-teldrassil.toml
# [[step]]
# id = "netd-089"
# do = "turnin"
# quest = 2519
# npc = 7313
# at = [1457, 36.65, 85.93]
# text = "Entra en el Templo de la Luna y entrega a la Sacerdotisa A'moora."
# status = "unverified"
# sources = ["questie:quest/2519", "questie:npc/7313"]
#
# ---- 3361 A Refugee's Quandary
# data/guides/gnome-warlock/01-coldridge.toml
# [[step]]
# id = "coldridge-021"
# do = "accept"
# quest = 3361
# reqlevel = 3
# npc = 8416
# at = [1426, 28.6, 67.6]
# text = "Coge la misión de Felix Whindlebolt, dentro de Yunquemar."
# status = "unverified"
# sources = ["questie:quest/3361", "questie:npc/8416"]
#
# data/guides/gnome-warlock/01-coldridge.toml
# [[step]]
# id = "coldridge-027"
# do = "complete"
# quest = 3361
# at = [1426, 22.8, 80.0]
# wps = [[1426, 20.9, 76.1, "Caja de Felix"], [1426, 22.8, 80.0, "Cofre de Felix"], [1426, 26.3, 79.3, "Cubo de tornillos de Felix"]]
# text = "Recoge las tres cosas de Felix en el campamento trol: caja, cofre y cubo de tornillos."
# status = "unverified"
# sources = ["questie:quest/3361", "questie:object/148499", "questie:object/178084", "questie:object/178085"]
#
# data/guides/gnome-warlock/01-coldridge.toml
# [[step]]
# id = "coldridge-037"
# do = "turnin"
# quest = 3361
# npc = 8416
# at = [1426, 28.6, 67.6]
# text = "Entrega las cosas a Felix Whindlebolt."
# status = "unverified"
# sources = ["questie:quest/3361", "questie:npc/8416"]
#
# ---- 3783 Are We There, Yeti?
# data/shared/a54-winterspring.toml
# [[step]]
# id = "a54-winterspring-010"
# do = "accept"
# quest = 3783
# reqlevel = 52
# npc = 10305
# at = [1452, 60.9, 37.6]
# text = "Coge la misión de las pieles de yeti de Umi."
# status = "unverified"
# sources = ["questie:quest/3783", "questie:npc/10305", "https://www.warcrafttavern.com/forever/guides/leveling/", "https://expcarry.com/wow-forever-leveling-guide-alliance"]
# checked = "2026-11-11"
#
# data/shared/a54-winterspring.toml
# [[step]]
# id = "a54-winterspring-016"
# do = "complete"
# quest = 3783
# at = [1452, 43.6, 39.4]
# text = "De camino al oeste, mata yetis Cardo de Hielo errantes del centro hasta tener 10 pieles gruesas."
# status = "unverified"
# sources = ["questie:quest/3783", "https://www.warcrafttavern.com/forever/guides/leveling/", "https://expcarry.com/wow-forever-leveling-guide-alliance"]
# checked = "2026-11-11"
#
# data/shared/a54-winterspring.toml
# [[step]]
# id = "a54-winterspring-037"
# do = "turnin"
# quest = 3783
# npc = 10305
# at = [1452, 60.9, 37.6]
# text = "Entrega las pieles de yeti a Umi."
# status = "unverified"
# sources = ["questie:quest/3783", "questie:npc/10305", "https://www.warcrafttavern.com/forever/guides/leveling/", "https://expcarry.com/wow-forever-leveling-guide-alliance"]
# checked = "2026-11-11"
#
# ---- 3903 Milly Osworth
# data/guides/human-mage/01-northshire.toml
# [[step]]
# id = "hmage-northshire-029"
# do = "accept"
# quest = 3903
# reqlevel = 2
# npc = 823
# at = [1429, 48.2, 42.9]
# text = "Coge la misión que te manda con Milly Osworth."
# status = "unverified"
# sources = ["questie:quest/3903", "questie:npc/823"]
# checked = "2026-11-11"
#
# data/guides/human-mage/01-northshire.toml
# [[step]]
# id = "hmage-northshire-031"
# do = "turnin"
# quest = 3903
# npc = 9296
# at = [1429, 50.7, 39.4]
# text = "Habla con Milly Osworth, junto al establo detrás de la abadía."
# status = "unverified"
# sources = ["questie:quest/3903", "questie:npc/9296"]
# checked = "2026-11-11"
#
# ---- 4283 FIFTY! YEP!
# data/shared/a55-burning-steppes.toml
# [[step]]
# id = "a55-burning-steppes-012"
# do = "accept"
# quest = 4283
# reqlevel = 50
# npc = 9177
# at = [1428, 84.6, 68.7]
# text = "Coge también la de los 50 medallones Roca Negra."
# tip = "Los medallones caen de cualquier orco Roca Negra: ve sumando mientras haces lo demás."
# status = "unverified"
# sources = ["questie:quest/4283", "questie:npc/9177", "https://www.warcrafttavern.com/forever/guides/leveling/", "https://expcarry.com/wow-forever-leveling-guide-alliance", "https://www.warcrafttavern.com/forever/news/onyxias-lair-raid-will-still-require-attunement-in-wow-forever/"]
# checked = "2026-11-11"
#
# data/shared/a55-burning-steppes.toml
# [[step]]
# id = "a55-burning-steppes-017"
# do = "complete"
# quest = 4283
# at = [1428, 46.8, 54.6]
# text = "Mata orcos Roca Negra hasta reunir 50 medallones."
# status = "unverified"
# sources = ["questie:quest/4283", "https://www.warcrafttavern.com/forever/guides/leveling/", "https://expcarry.com/wow-forever-leveling-guide-alliance", "https://www.warcrafttavern.com/forever/news/onyxias-lair-raid-will-still-require-attunement-in-wow-forever/"]
# checked = "2026-11-11"
#
# data/shared/a55-burning-steppes.toml
# [[step]]
# id = "a55-burning-steppes-022"
# do = "turnin"
# quest = 4283
# npc = 9177
# at = [1428, 84.6, 68.7]
# text = "Entrega los medallones a Oralius."
# status = "unverified"
# sources = ["questie:quest/4283", "questie:npc/9177", "https://www.warcrafttavern.com/forever/guides/leveling/", "https://expcarry.com/wow-forever-leveling-guide-alliance", "https://www.warcrafttavern.com/forever/news/onyxias-lair-raid-will-still-require-attunement-in-wow-forever/"]
# checked = "2026-11-11"
#
# ---- 5082 Threat of the Winterfall
# data/shared/a54-winterspring.toml
# [[step]]
# id = "a54-winterspring-005"
# do = "accept"
# quest = 5082
# reqlevel = 52
# npc = 9298
# at = [1452, 31.3, 45.2]
# text = "Coge la misión de Donova contra los Winterfall."
# status = "unverified"
# sources = ["questie:quest/5082", "questie:npc/9298", "https://www.warcrafttavern.com/forever/guides/leveling/", "https://expcarry.com/wow-forever-leveling-guide-alliance"]
# checked = "2026-11-11"
#
# data/shared/a54-winterspring.toml
# [[step]]
# id = "a54-winterspring-006"
# do = "complete"
# quest = 5082
# at = [1452, 36.4, 40.0]
# text = "En las Aguas Termales Fuego Frío, al este de Donova, mata exploradores y totémicos Winterfall (8 de cada)."
# tip = "Los vigías de guarida salen en el Poblado Winterfall, al este: termínalos allí."
# status = "unverified"
# sources = ["questie:quest/5082", "https://www.warcrafttavern.com/forever/guides/leveling/", "https://expcarry.com/wow-forever-leveling-guide-alliance"]
# checked = "2026-11-11"
#
# data/shared/a54-winterspring.toml
# [[step]]
# id = "a54-winterspring-014"
# do = "complete"
# quest = 5082
# at = [1452, 68.0, 37.5]
# text = "En el Poblado Winterfall, al este de Vista Eterna, mata 8 vigías de guarida."
# status = "unverified"
# sources = ["questie:quest/5082", "https://www.warcrafttavern.com/forever/guides/leveling/", "https://expcarry.com/wow-forever-leveling-guide-alliance"]
# checked = "2026-11-11"
#
# data/shared/a54-winterspring.toml
# [[step]]
# id = "a54-winterspring-032"
# do = "turnin"
# quest = 5082
# npc = 9298
# at = [1452, 31.3, 45.2]
# text = "Entrega los Winterfall a Donova."
# status = "unverified"
# sources = ["questie:quest/5082", "questie:npc/9298", "https://www.warcrafttavern.com/forever/guides/leveling/", "https://expcarry.com/wow-forever-leveling-guide-alliance"]
# checked = "2026-11-11"
#
# ---- 5211 Defenders of Darrowshire
# data/shared/a58-eastern-plaguelands.toml
# [[step]]
# id = "a58-eastern-plaguelands-018"
# do = "accept"
# quest = 5211
# reqlevel = 50
# npc = 11063
# at = [1423, 71.7, 50.0]
# text = "Coge la misión de liberar a los espíritus de Darrowshire."
# status = "unverified"
# sources = ["questie:quest/5211", "questie:npc/11063", "https://www.warcrafttavern.com/forever/guides/leveling/", "https://expcarry.com/wow-forever-leveling-guide-alliance", "https://www.warcrafttavern.com/forever/guides/dungeons/"]
# checked = "2026-11-11"
#
# data/shared/a58-eastern-plaguelands.toml
# [[step]]
# id = "a58-eastern-plaguelands-021"
# do = "complete"
# quest = 5211
# at = [1423, 30.0, 30.0]
# text = "Mata a la Plaga de la zona y libera 15 espíritus de Darrowshire; hay muchos en el norte y el oeste."
# status = "unverified"
# sources = ["questie:quest/5211", "https://www.warcrafttavern.com/forever/guides/leveling/", "https://expcarry.com/wow-forever-leveling-guide-alliance", "https://www.warcrafttavern.com/forever/guides/dungeons/"]
# checked = "2026-11-11"
# note = "Los espíritus aparecen por toda la zona: coordenada orientativa."
#
# data/shared/a58-eastern-plaguelands.toml
# [[step]]
# id = "a58-eastern-plaguelands-037"
# do = "turnin"
# quest = 5211
# npc = 11063
# at = [1423, 71.7, 50.0]
# text = "Entrega los espíritus a Carlin."
# status = "unverified"
# sources = ["questie:quest/5211", "questie:npc/11063", "https://www.warcrafttavern.com/forever/guides/leveling/", "https://expcarry.com/wow-forever-leveling-guide-alliance", "https://www.warcrafttavern.com/forever/guides/dungeons/"]
# checked = "2026-11-11"
#
# ---- 5249 To Winterspring!
# data/shared/a52-felwood.toml
# [[step]]
# id = "a52-felwood-016"
# do = "accept"
# quest = 5249
# reqlevel = 53
# npc = 10924
# at = [1448, 51.0, 81.6]
# text = "Coge la misión hacia Cuna del Invierno (Aldea Caída Estelar). Guárdala."
# status = "unverified"
# sources = ["questie:quest/5249", "questie:npc/10924", "https://www.warcrafttavern.com/forever/guides/leveling/", "https://expcarry.com/wow-forever-leveling-guide-alliance"]
# checked = "2026-11-11"
#
# data/shared/a54-winterspring.toml
# [[step]]
# id = "a54-winterspring-018"
# do = "turnin"
# quest = 5249
# npc = 11079
# at = [1452, 52.0, 30.4]
# text = "Entrega la misión a Wynd Nightchaser."
# status = "unverified"
# sources = ["questie:quest/5249", "questie:npc/11079", "https://www.warcrafttavern.com/forever/guides/leveling/", "https://expcarry.com/wow-forever-leveling-guide-alliance"]
# checked = "2026-11-11"
#
# ---- 5545 A Bundle of Trouble
# data/guides/human-mage/02-elwynn.toml
# [[step]]
# id = "hmage-elwynn-082"
# do = "accept"
# quest = 5545
# reqlevel = 5
# npc = 10616
# at = [1429, 81.4, 66.1]
# text = "Coge la misión de la madera del Supervisor Raelen."
# status = "unverified"
# sources = ["questie:quest/5545", "questie:npc/10616"]
# checked = "2026-11-11"
#
# data/guides/human-mage/02-elwynn.toml
# [[step]]
# id = "hmage-elwynn-084"
# do = "complete"
# quest = 5545
# at = [1429, 80.3, 59.7]
# text = "Recoge los haces de leña en el bosque al norte del campamento."
# status = "unverified"
# sources = ["questie:quest/5545"]
# checked = "2026-11-11"
#
# data/guides/human-mage/02-elwynn.toml
# [[step]]
# id = "hmage-elwynn-095"
# do = "turnin"
# quest = 5545
# npc = 10616
# at = [1429, 81.4, 66.1]
# text = "Vuelve al campamento y entrega la madera al Supervisor Raelen."
# status = "unverified"
# sources = ["questie:quest/5545", "questie:npc/10616"]
# checked = "2026-11-11"
#
# ---- 8469 Beads for Salfa
# data/shared/a54-winterspring.toml
# [[step]]
# id = "a54-winterspring-034"
# do = "accept"
# quest = 8469
# reqlevel = 50
# npc = 11556
# at = [1452, 27.7, 34.5]
# text = "Opcional: entrega las cuentas de espíritu a Salfa."
# optional = true
# status = "unverified"
# sources = ["questie:quest/8469", "questie:npc/11556", "https://www.warcrafttavern.com/forever/guides/leveling/", "https://expcarry.com/wow-forever-leveling-guide-alliance"]
# checked = "2026-11-11"
#
# data/shared/a54-winterspring.toml
# [[step]]
# id = "a54-winterspring-035"
# do = "turnin"
# quest = 8469
# npc = 11556
# at = [1452, 27.7, 34.5]
# text = "Entrega las cuentas."
# optional = true
# status = "unverified"
# sources = ["questie:quest/8469", "questie:npc/11556", "https://www.warcrafttavern.com/forever/guides/leveling/", "https://expcarry.com/wow-forever-leveling-guide-alliance"]
# checked = "2026-11-11"
#
# ---- 92819 Destruction in Deadmines
# data/shared/a21-minas-de-la-muerte.toml
# [[step]]
# id = "a21dm-024"
# do = "accept"
# quest = 92819
# reqlevel = 9
# npc = 253279
# at = [1436, 38.7, 83.7]
# text = "Coge la misión del detonador."
# optional = true
# status = "unverified"
# sources = ["questie:quest/92819"]
#
# data/shared/a21-minas-de-la-muerte.toml
# [[step]]
# id = "a21dm-025"
# do = "complete"
# quest = 92819
# at = [1436, 38.7, 83.6]
# text = "Usa el detonador, al lado de Alba."
# optional = true
# status = "unverified"
# sources = ["questie:quest/92819", "questie:object/581792"]
#
# data/shared/a21-minas-de-la-muerte.toml
# [[step]]
# id = "a21dm-026"
# do = "turnin"
# quest = 92819
# npc = 253279
# at = [1436, 38.7, 83.7]
# text = "Entrega a Alba."
# optional = true
# status = "unverified"
# sources = ["questie:quest/92819"]
#
# ---- 96057 Camping 101: Tailoring
# data/guides/gnome-warlock/02-dun-morogh.toml
# [[step]]
# id = "dun-morogh-011"
# do = "accept"
# quest = 96057
# reqlevel = 4
# reqskill = [197, 1]
# npc = 265813
# at = [1426, 46.6, 53.9]
# text = "Ya con Sastrería, coge la lección de Sastrería de Eric, junto a la hoguera: se entrega en Forjaz."
# status = "unverified"
# sources = ["questie:quest/96057", "questie:npc/265813"]
#
# data/guides/gnome-warlock/02-dun-morogh.toml
# [[step]]
# id = "dun-morogh-048"
# do = "turnin"
# quest = 96057
# npc = 1703
# at = [1455, 43.8, 27.9]
# text = "Ve a la Gran Fundición y entrega la lección de Sastrería a Uthrar Threx."
# status = "unverified"
# sources = ["questie:quest/96057", "questie:npc/1703"]
#
# ---- 97979 The Goddess Provides
# data/guides/nightelf-druid/01-shadowglen.toml
# [[step]]
# id = "nesg-006"
# do = "accept"
# quest = 97979
# npc = 3595
# at = [1438, 59.17, 40.44]
# text = "Sube a Aldrassil y coge la misión de Shanda (nueva de Forever)."
# status = "unverified"
# sources = ["questie:quest/97979", "questie:npc/3595"]
#
# data/guides/nightelf-druid/01-shadowglen.toml
# [[step]]
# id = "nesg-007"
# do = "complete"
# quest = 97979
# at = [1438, 59.17, 40.44]
# text = "Lanza Luz de Elune y Fusión de las sombras para completar la misión."
# tip = "Son habilidades raciales: arrástralas a la barra. Fusión de las sombras te sirve luego para beber sin que te ataquen."
# status = "unverified"
# sources = ["questie:quest/97979"]
#
# data/guides/nightelf-druid/01-shadowglen.toml
# [[step]]
# id = "nesg-008"
# do = "turnin"
# quest = 97979
# npc = 3595
# at = [1438, 59.17, 40.44]
# text = "Entrega la misión a Shanda."
# status = "unverified"
# sources = ["questie:quest/97979", "questie:npc/3595"]
#
# ---- 98046 Crown of the Earth
# data/guides/nightelf-druid/02-teldrassil.toml
# [[step]]
# id = "netd-145"
# do = "accept"
# quest = 98046
# npc = 3516
# at = [1457, 34.81, 9.26]
# text = "Coge la continuación (nueva de Forever): para Lariia, en el Templo de la Luna."
# status = "unverified"
# sources = ["questie:quest/98046", "questie:npc/3516"]
#
# data/guides/nightelf-druid/02-teldrassil.toml
# [[step]]
# id = "netd-146"
# do = "turnin"
# quest = 98046
# npc = 4092
# at = [1457, 40.35, 88.68]
# text = "En el Templo de la Luna, entrega a Lariia."
# status = "unverified"
# sources = ["questie:quest/98046", "questie:npc/4092"]
#
# ---- 98065 Crown of the Earth
# data/guides/nightelf-druid/02-teldrassil.toml
# [[step]]
# id = "netd-147"
# do = "accept"
# quest = 98065
# npc = 4092
# at = [1457, 40.35, 88.68]
# text = "Coge la última parte: para Tyrande Whisperwind."
# status = "unverified"
# sources = ["questie:quest/98065", "questie:npc/4092"]
#
# data/guides/nightelf-druid/02-teldrassil.toml
# [[step]]
# id = "netd-148"
# do = "turnin"
# quest = 98065
# npc = 7999
# at = [1457, 39.1, 81.59]
# text = "Sube al balcón del Templo y entrega a Tyrande Whisperwind."
# status = "unverified"
# sources = ["questie:quest/98065", "questie:npc/7999"]
#
# ---- 98189 Return the Statuette
# data/shared/a26-los-humedales.toml
# [[step]]
# id = "a26wl-040"
# do = "accept"
# quest = 98189
# reqlevel = 20
# npc = 1242
# at = [1437, 8.3, 58.6]
# text = "Coge la entrega de la estatuilla al Capitán Stoutfist."
# status = "unverified"
# sources = ["questie:quest/98189"]
#
# data/shared/a26-los-humedales.toml
# [[step]]
# id = "a26wl-041"
# do = "turnin"
# quest = 98189
# npc = 2104
# at = [1437, 9.9, 57.5]
# text = "Entrega la estatuilla a Stoutfist."
# tip = "Después te ofrece llevarla al Alto Señor Bolvar en Ventormenta: cógela solo si vas a pasar por allí."
# status = "unverified"
# sources = ["questie:quest/98189"]
#
# ---- 98319 Secure the Mountain
# data/guides/gnome-warlock/02-dun-morogh.toml
# [[step]]
# id = "dun-morogh-027"
# do = "accept"
# quest = 98319
# reqlevel = 4
# npc = 271546
# at = [1426, 44.1, 57.1]
# text = "Coge la siguiente de Gretchen: buscar a un montañero en la Guarida Grizzled."
# status = "unverified"
# sources = ["questie:quest/98319", "questie:npc/271546"]
#
# data/guides/gnome-warlock/02-dun-morogh.toml
# [[step]]
# id = "dun-morogh-032"
# do = "complete"
# quest = 98319
# at = [1426, 43.0, 49.6]
# text = "Encuentra al montañero Cornelius en la Guarida Grizzled y habla con él."
# status = "unverified"
# sources = ["questie:quest/98319", "questie:npc/278166"]
#
# data/guides/gnome-warlock/02-dun-morogh.toml
# [[step]]
# id = "dun-morogh-035"
# do = "turnin"
# quest = 98319
# npc = 271546
# at = [1426, 44.1, 57.1]
# text = "Vuelve con Gretchen y entrégale."
# status = "unverified"
# sources = ["questie:quest/98319", "questie:npc/271546"]
#
# ---- 98323 Secure the Mountain
# data/guides/gnome-warlock/02-dun-morogh.toml
# [[step]]
# id = "dun-morogh-036"
# do = "accept"
# quest = 98323
# reqlevel = 4
# npc = 271546
# at = [1426, 44.1, 57.1]
# text = "Coge la última de Gretchen: el informe vuelve a Senir."
# status = "unverified"
# sources = ["questie:quest/98323", "questie:npc/271546"]
#
# data/guides/gnome-warlock/02-dun-morogh.toml
# [[step]]
# id = "dun-morogh-037"
# do = "turnin"
# quest = 98323
# npc = 1252
# at = [1426, 46.7, 53.8]
# text = "Entrega a Senir Whitebeard en Kharanos."
# status = "unverified"
# sources = ["questie:quest/98323", "questie:npc/1252"]
#
# ---- 98386 Alther's Mill
# data/shared/a19-crestagrana.toml
# [[step]]
# id = "a19rr-038"
# do = "accept"
# quest = 98386
# reqlevel = 15
# npc = 341
# at = [1433, 27.1, 48.6]
# text = "Coge la del Molino de Alther (tarántulas y huevos)."
# status = "unverified"
# sources = ["questie:quest/98386"]
#
# data/shared/a19-crestagrana.toml
# [[step]]
# id = "a19rr-039"
# do = "complete"
# quest = 98386
# at = [1433, 48.3, 40.8]
# text = "En el Molino de Alther, mata 12 tarántulas mayores y rompe 6 huevos."
# status = "unverified"
# sources = ["questie:quest/98386"]
#
# data/shared/a19-crestagrana.toml
# [[step]]
# id = "a19rr-046"
# do = "turnin"
# quest = 98386
# npc = 341
# at = [1433, 27.1, 48.6]
# text = "Entrega el Molino a Oslow."
# status = "unverified"
# sources = ["questie:quest/98386"]
#
# ---- 98391 The Sisterhood of Elune
# data/guides/nightelf-druid/02-teldrassil.toml
# [[step]]
# id = "netd-083"
# do = "accept"
# quest = 98391
# reqlevel = 5
# npc = 3600
# at = [1438, 55.56, 56.75]
# text = "Coge la misión de Laurna Morninglight para el Templo de la Luna."
# status = "unverified"
# sources = ["questie:quest/98391", "questie:npc/3600"]
#
# data/guides/nightelf-druid/02-teldrassil.toml
# [[step]]
# id = "netd-087"
# do = "turnin"
# quest = 98391
# npc = 7316
# at = [1457, 28.94, 45.8]
# text = "Entrega la carta de Laurna a la Hermana Aquinne, en el jardín del Templo."
# status = "unverified"
# sources = ["questie:quest/98391", "questie:npc/7316"]
#
# ---- 98461 Unrequited Love
# data/shared/a26-los-humedales.toml
# [[step]]
# id = "a26wl-ne-03"
# do = "turnin"
# quest = 98461
# npc = 2096
# at = [1437, 11.5, 52.2]
# text = "Si la cogiste en Costa Oscura, entrega la nota de Hollee a Tarrel Rockweaver, junto a Menethil."
# if = { race = ["NightElf"] }
# optional = true
# status = "unverified"
# sources = ["questie:quest/98461", "questie:npc/2096"]
#
# data/guides/nightelf-druid/03-darkshore.toml
# [[step]]
# id = "neds-142"
# do = "accept"
# quest = 98461
# reqlevel = 18
# npc = 2913
# at = [1439, 37.44, 41.84]
# text = "Coge con Hollee el amor no correspondido (nueva de Forever): se entrega en Menethil."
# tip = "La entregas en Puerto de Menethil (Los Humedales) hacia el 26: déjala en el registro."
# optional = true
# status = "unverified"
# sources = ["questie:quest/98461", "questie:npc/2913"]
#
# ---- 99073 Easing Suffering
# data/guides/nightelf-druid/02-teldrassil.toml
# [[step]]
# id = "netd-137"
# do = "accept"
# quest = 99073
# reqlevel = 4
# npc = 6094
# at = [1438, 55.29, 56.82]
# text = "Coge su siguiente misión: llévale el remedio a Eralya."
# status = "unverified"
# sources = ["questie:quest/99073", "questie:npc/6094"]
#
# data/guides/nightelf-druid/02-teldrassil.toml
# [[step]]
# id = "netd-143"
# do = "turnin"
# quest = 99073
# npc = 275683
# at = [1438, 37.54, 36.81]
# text = "Ve al Claro del Oráculo y entrega el remedio a Eralya."
# status = "unverified"
# sources = ["questie:quest/99073", "questie:npc/275683"]
#
# ---- 99158 Dawn in the Mountains
# data/guides/gnome-warlock/02-dun-morogh.toml
# [[step]]
# id = "dun-morogh-005"
# do = "accept"
# quest = 99158
# reqlevel = 5
# npc = 1226
# at = [1426, 47.3, 52.2]
# text = "Coge la misión del instructor de sacerdote Maxan Anvol (nueva de Forever): se entrega al padre Gavin, al noreste."
# tip = "La entregarás hacia el 9: guárdala en el registro."
# status = "unverified"
# sources = ["questie:quest/99158", "questie:npc/1226"]
#
# data/guides/gnome-warlock/02-dun-morogh.toml
# [[step]]
# id = "dun-morogh-077"
# do = "turnin"
# quest = 99158
# npc = 1253
# at = [1426, 57.7, 44.9]
# text = "Ve al noreste de Kharanos y entrega la misión de Maxan al padre Gavin."
# status = "unverified"
# sources = ["questie:quest/99158", "questie:npc/1253"]
#
# ---- 98322 Secure the Mountain
# data/guides/gnome-warlock/02-dun-morogh.toml
# [[step]]
# id = "dun-morogh-019"
# do = "accept"
# quest = 98322
# reqlevel = 4
# npc = 1252
# at = [1426, 46.7, 53.8]
# text = "Coge la primera misión de asegurar la montaña de Senir (nueva de Forever)."
# tip = "+70 XP · <1 min: por debajo de la media del tramo."
# optional = true
# status = "unverified"
# sources = ["questie:quest/98322", "questie:npc/1252"]
#
# data/guides/gnome-warlock/02-dun-morogh.toml
# [[step]]
# id = "dun-morogh-026"
# do = "turnin"
# quest = 98322
# npc = 271546
# at = [1426, 44.1, 57.1]
# text = "Baja al suroeste del pueblo y entrega a Mountaineer Gretchen."
# optional = true
# status = "unverified"
# sources = ["questie:quest/98322", "questie:npc/271546"]
#
# ---- 273 Resupplying the Excavation
# data/shared/a12-loch-modan.toml
# [[step]]
# id = "a12lm-076"
# do = "accept"
# quest = 273
# reqlevel = 10
# npc = 1105
# at = [1432, 37.2, 47.4]
# text = "Coge el reabastecimiento de la excavación."
# tip = "+270 XP · ~1,4 min: por debajo de la media del tramo."
# optional = true
# status = "unverified"
# sources = ["questie:quest/273"]
#
# data/shared/a12-loch-modan.toml
# [[step]]
# id = "a12lm-077"
# do = "turnin"
# quest = 273
# npc = 2057
# at = [1432, 52.2, 69.3]
# text = "Ve al sur del lago y habla con Huldar junto al carro emboscado."
# optional = true
# status = "unverified"
# sources = ["questie:quest/273", "questie:npc/2057"]
#
# ---- 463 The Greenwarden
# data/shared/a26-los-humedales.toml
# [[step]]
# id = "a26wl-022"
# do = "accept"
# quest = 463
# reqlevel = 20
# npc = 1239
# at = [1437, 10.9, 59.6]
# text = "Coge con el Primer Oficial Fitzsimmons la misión para el Guardaverde."
# status = "unverified"
# sources = ["questie:quest/463", "questie:npc/1239"]
#
# data/shared/a26-los-humedales.toml
# [[step]]
# id = "a26wl-054"
# do = "turnin"
# quest = 463
# npc = 1244
# at = [1437, 56.4, 40.4]
# text = "Sigue el camino al este y sube al Cinturón Verde: entrega a Rethiel el Guardaverde."
# status = "unverified"
# sources = ["questie:quest/463", "questie:npc/1244"]
#
# ---- 305 In Search of the Excavation Team
# data/shared/a26-los-humedales.toml
# [[step]]
# id = "a26wl-023"
# do = "accept"
# quest = 305
# reqlevel = 21
# npc = 2096
# at = [1437, 11.5, 52.2]
# text = "Al norte del pueblo, coge con Tarrel Rockweaver la misión para el equipo de excavación."
# status = "unverified"
# sources = ["questie:quest/305", "questie:npc/2096"]
#
# data/shared/a26-los-humedales.toml
# [[step]]
# id = "a26wl-042"
# do = "turnin"
# quest = 305
# npc = 1076
# at = [1437, 38.9, 52.3]
# text = "Ve al este por el camino hasta la Excavación de Whelgar. Habla con Merrin Rockweaver."
# status = "unverified"
# sources = ["questie:quest/305", "questie:npc/1076"]
#
# ---- 98230 This Land Was Their Land
# data/shared/a26-los-humedales.toml
# [[step]]
# id = "a26wl-017"
# do = "accept"
# quest = 98230
# reqlevel = 22
# npc = 2104
# at = [1437, 9.9, 57.5]
# text = "Y la que te manda con Howin Kindfeather, al este por el camino."
# status = "unverified"
# sources = ["questie:quest/98230"]
#
# data/shared/a26-los-humedales.toml
# [[step]]
# id = "a26wl-056"
# do = "turnin"
# quest = 98230
# npc = 270637
# at = [1437, 49.4, 42.1]
# text = "Baja al camino y habla con Howin Kindfeather."
# status = "unverified"
# sources = ["questie:quest/98230", "questie:npc/270637"]
#
# ---- 98240 Crimson Crate Delivery
# data/shared/a26-los-humedales.toml
# [[step]]
# id = "a26wl-019"
# do = "accept"
# quest = 98240
# reqlevel = 19
# npc = 2094
# at = [1437, 8.6, 55.7]
# text = "Coge también la caja carmesí para Howin."
# status = "unverified"
# sources = ["questie:quest/98240"]
#
# data/shared/a26-los-humedales.toml
# [[step]]
# id = "a26wl-057"
# do = "turnin"
# quest = 98240
# npc = 270637
# at = [1437, 49.4, 42.1]
# text = "Entrégale también la caja carmesí."
# status = "unverified"
# sources = ["questie:quest/98240"]
#
```

</details>

## 3. Misiones opcionales (73)

Decisión `optional`: todos sus pasos llevan `optional = true` y el primero, un `tip` con el motivo. Si el paso ya tenía
truco, el motivo se añade detrás sin tocar el texto. «Tramo» es la banda de 5 niveles del filtro.

| Misión | Personajes | Motivo (tip) | Pasos |
|---|---|---|---|
| The Killing Fields (9) | brujo, mago | +2.590 XP · ~14 min: por debajo de la media del tramo. | a17wf-009, a17wf-022, a17wf-034 |
| The Scrimshank Redemption (10) | brujo, mago, druida | +4.400 XP · ~8 min: por debajo de la media del tramo. | a47-tanaris-026, a47-tanaris-027, a47-tanaris-028 |
| The People's Militia (12) | brujo, mago | +2.310 XP · ~18 min: por debajo de la media del tramo. | a17wf-012, a17wf-024, a17wf-037 |
| The People's Militia (13) | brujo, mago | +2.895 XP · ~18 min: por debajo de la media del tramo. | a17wf-038, a17wf-044, a17wf-048 |
| Goretusk Liver Pie (22) | brujo, mago | +2.341 XP · ~16 min: por debajo de la media del tramo. | a17wf-008, a17wf-032, a17wf-033 |
| Noxious Lair Investigation (82) | brujo, mago, druida | +7.863 XP · ~15 min: por debajo de la media del tramo. | a47-tanaris-017, a47-tanaris-024, a47-tanaris-025 |
| Keeper of the Flame (103) | brujo, mago | +2.089 XP · ~10 min: por debajo de la media del tramo. | a17wf-046, a17wf-056, a17wf-058 |
| Young Lovers (106) | mago | +140 XP · ~2 min: por debajo de la media del tramo. | hmage-elwynn-036, hmage-elwynn-039 |
| Poor Old Blanchy (151) | brujo, mago | +1.250 XP · ~8 min: por debajo de la media del tramo. | a17wf-006, a17wf-029, a17wf-031 |
| A New Threat (170) | brujo | +830 XP · ~7,3 min: por debajo de la media del tramo; hazla si te interesa la recompensa. | coldridge-006, coldridge-011, coldridge-025 |
| Tiger Mastery (186) | brujo, mago, druida | +3.350 XP · ~11 min: por debajo de la media del tramo. | a30-stv-norte-019, a30-stv-norte-021, a30-stv-norte-024 |
| Wolves at Our Heels (226) | brujo, mago, druida | +3.090 XP · ~15 min: por debajo de la media del tramo. | a22dw-023, a22dw-026, a22dw-027 |
| Westbrook Garrison Needs Help! (239) | mago | +210 XP · ~1,6 min: por debajo de la media del tramo. | hmage-elwynn-109, hmage-elwynn-118 |
| Eight-Legged Menaces (245) | brujo, mago, druida | +2.165 XP · ~19 min: por debajo de la media del tramo; hazla si te interesa la recompensa. | a22dw-016, a22dw-028, a22dw-029 |
| Assessing the Threat (246) | brujo, mago, druida | +2.230 XP · ~11 min: por debajo de la media del tramo. | a19rr-008, a19rr-026, a19rr-029 |
| Resupplying the Excavation (273) | brujo, mago | +270 XP · ~1,4 min: por debajo de la media del tramo. | a12lm-076, a12lm-077 |
| The Balance of Nature (457) | druida | +866 XP · ~8,4 min: por debajo de la media del tramo; hazla si te interesa la recompensa. | nesg-005, nesg-018, nesg-022 |
| Young Crocolisk Skins (484) | brujo, mago, druida | +3.450 XP · ~25 min: por debajo de la media del tramo; hazla si vas a Excavation Site: abre «{quest:98815}». (corrections/quests.json: «Highland Hides» (98815, mazmorra Excavation Site) exige 484) | a26wl-018, a26wl-029, a26wl-032 |
| The Road to Darnassus (487) | druida | +1.000 XP · ~6 min: por debajo de la media del tramo. | netd-061, netd-062, netd-077 |
| Zenn's Bidding (488) | druida | +2.269 XP · ~24 min: por debajo de la media del tramo; hazla si te interesa la recompensa. | netd-028, netd-046 |
| Seek Redemption! (489) | druida | +625 XP · ~4 min: por debajo de la media del tramo. | netd-047, netd-053, netd-057 |
| A Dwarf and His Tools (719) | brujo, mago, druida | +2.206 XP · ~6 min: por debajo de la media del tramo; hazla si te interesa la recompensa. | a44-badlands-004, a44-badlands-008, a44-badlands-012 |
| Rellian Greenspyre (922) | druida | +708 XP · ~9 min: por debajo de la media del tramo. | netd-056, netd-084 |
| Mist (938) | druida | +900 XP · ~8 min: por debajo de la media del tramo; hazla si te interesa la recompensa. | netd-107, netd-108, netd-109 |
| Bashal'Aran (957) | druida | +540 XP · ~4 min: por debajo de la media del tramo; hazla si te interesa la recompensa. | neds-057, neds-087, neds-128 |
| Fruit of the Sea (1138) | druida | +3.133 XP · ~18 min: por debajo de la media del tramo. | neds-083, neds-091, neds-117 |
| Stealing Supplies (1370) | brujo, mago, druida | +1.350 XP · ~11 min: por debajo de la media del tramo; hazla si te interesa la recompensa. | a34-desolace-029, a34-desolace-030, a34-desolace-032 |
| Raid on the Kolkar (1384) | brujo, mago, druida | +7.406 XP · ~23 min: por debajo de la media del tramo. | a34-desolace-023, a34-desolace-024, a34-desolace-028 |
| Centaur Bounty (1387) | brujo, mago, druida | +6.070 XP · ~40 min: por debajo de la media del tramo; hazla si te interesa la recompensa. | a34-desolace-012, a38-valle-de-huesos-016 |
| Power Stones (2418) | brujo, mago, druida | +4.180 XP · ~19 min: por debajo de la media del tramo; hazla si te interesa la recompensa. | a44-badlands-007, a44-badlands-010, a44-badlands-024 |
| Doling Justice (2970) | brujo, mago, druida | +8.006 XP · ~15 min: por debajo de la media del tramo. | a45-feralas-047, a45-feralas-048, a45-feralas-049 |
| The High Wilderness (2982) | brujo, mago, druida | +8.838 XP · ~21 min: por debajo de la media del tramo. | a45-feralas-009, a45-feralas-037, a45-feralas-059 |
| The Altar of Zul (2989) | brujo, mago, druida | +4.400 XP · ~8 min: por debajo de la media del tramo. | a49-hinterlands-012, a49-hinterlands-015, a49-hinterlands-016 |
| A Friend in Need (3519) | druida | +90 XP · <1 min: por debajo de la media del tramo según el cálculo, pendiente de cronometrar en el juego. (miga de pan de «Iverron's Antidote» (3521), que EFFICIENCY.md §6 marca como el primer caso a cronometrar) | nesg-020, nesg-023 |
| Iverron's Antidote (3521) | druida | +441 XP · ~5,5 min: por debajo de la media del tramo según el cálculo, pendiente de cronometrar en el juego. (EFFICIENCY.md §6: la cadena que todas las guías hacen; el modelo puede sobreestimar los jacintos y lirios) | nesg-024, nesg-027, nesg-030 |
| Iverron's Antidote (3522) | druida | +450 XP · ~2,3 min: por debajo de la media del tramo según el cálculo, pendiente de cronometrar en el juego. (sigue a 3521 (opcional)) | nesg-031, nesg-032 |
| Expedition Salvation (3881) | brujo, mago, druida | +3.950 XP · ~7,5 min: por debajo de la media del tramo, aunque rinde más que matar bichos. | a50-ungoro-018, a50-ungoro-026, a50-ungoro-039, a50-ungoro-054 |
| Milly's Harvest (3904) | mago | +180 XP · ~2,6 min: por debajo de la media del tramo. | hmage-northshire-032, hmage-northshire-033, hmage-northshire-035 |
| Making Sense of It (4321) | brujo, mago, druida | +530 XP · ~1,3 min: por debajo de la media del tramo; hazla si te interesa la recompensa. | a50-ungoro-068, a50-ungoro-069 |
| The Corruption of the Jadefire (4421) | brujo, mago, druida | +13.061 XP · ~25 min: por debajo de la media del tramo, aunque rinde más que matar bichos. | a52-felwood-004, a52-felwood-009, a52-felwood-013 |
| Beware of Pterrordax (4501) | brujo, mago, druida | +13.600 XP · ~32 min: por debajo de la media del tramo; hazla si te interesa la recompensa. | a50-ungoro-020, a50-ungoro-025, a50-ungoro-050 |
| Shizzle's Flyer (4503) | brujo, mago, druida | +27.502 XP · ~75 min: por debajo de la media del tramo; hazla si te interesa la recompensa. | a50-ungoro-016, a50-ungoro-024, a50-ungoro-052 |
| Beached Sea Turtle (4722) | druida | +368 XP · ~3,3 min: por debajo de la media del tramo según el cálculo, pendiente de cronometrar en el juego. (EFFICIENCY.md §6: sobreestimada (area_moved): el caparazón está en la playa por la que pasa la ruta) | neds-089, neds-121 |
| Beached Sea Turtle (4727) | druida | +550 XP · ~4 min: por debajo de la media del tramo según el cálculo, pendiente de cronometrar en el juego. (misma playa que 4722: sobreestimada por el mismo motivo) | neds-067, neds-082 |
| Beached Sea Creature (4728) | druida | +490 XP · ~2,4 min: por debajo de la media del tramo. | neds-090, neds-122 |
| Beached Sea Creature (4730) | druida | +575 XP · ~3 min: por debajo de la media del tramo. | neds-098, neds-123 |
| Demon Dogs (5542) | brujo, mago, druida | +13.615 XP · ~30 min: por debajo de la media del tramo, aunque rinde más que matar bichos. | a58-eastern-plaguelands-002, a58-eastern-plaguelands-006, a58-eastern-plaguelands-023 |
| Blood Tinged Skies (5543) | brujo, mago, druida | +12.880 XP · ~27 min: por debajo de la media del tramo, aunque rinde más que matar bichos. | a58-eastern-plaguelands-003, a58-eastern-plaguelands-005, a58-eastern-plaguelands-024 |
| Carrion Grubbage (5544) | brujo, mago, druida | +10.552 XP · ~18 min: por debajo de la media del tramo, aunque rinde más que matar bichos. | a58-eastern-plaguelands-004, a58-eastern-plaguelands-007, a58-eastern-plaguelands-025 |
| Kodo Roundup (5561) | brujo, mago, druida | +2.000 XP · ~8,7 min: por debajo de la media del tramo; hazla si te interesa la recompensa. | a34-desolace-025, a34-desolace-026, a34-desolace-027 |
| Of Lost Honor (5845) | brujo, mago, druida | +6.200 XP · ~11 min: por debajo de la media del tramo, aunque rinde más que matar bichos. | a58-eastern-plaguelands-033, a58-eastern-plaguelands-034, a58-eastern-plaguelands-035 |
| Nessa Shadowsong (6344) | druida | +210 XP · ~1,5 min: por debajo de la media del tramo. | netd-094, netd-150 |
| Zapped Giants (7003) | brujo, mago, druida | +8.927 XP · ~18 min: por debajo de la media del tramo. | a45-feralas-025, a45-feralas-050, a45-feralas-056 |
| Fuel for the Zapping (7721) | brujo, mago, druida | +10.460 XP · ~21 min: por debajo de la media del tramo. | a45-feralas-026, a45-feralas-027, a45-feralas-057 |
| Speak to Nafien (8462) | brujo, mago, druida | +560 XP · ~1 min: por debajo de la media del tramo, aunque rinde más que matar bichos. | a52-felwood-008, a52-felwood-019 |
| Winterfall Activity (8464) | brujo, mago, druida | +14.520 XP · ~21 min: por debajo de la media del tramo, aunque rinde más que matar bichos. | a54-winterspring-002, a54-winterspring-015, a54-winterspring-033 |
| Feathers for Nafien (8467) | brujo, mago, druida | +3.738 XP · ~7 min: por debajo de la media del tramo, aunque rinde más que matar bichos. | a52-felwood-023, a52-felwood-024 |
| Valley of Bones (93034) | brujo, mago, druida | +290 XP · <1 min: por debajo de la media del tramo. | a38-valle-de-huesos-001, a38-valle-de-huesos-002 |
| Facing the Truth (93041) | brujo, mago, druida | +700 XP · ~4 min: por debajo de la media del tramo según el cálculo, pendiente de cronometrar en el juego. (EFFICIENCY.md §6: «a revisar en el juego») | a38-valle-de-huesos-004, a38-valle-de-huesos-008, a38-valle-de-huesos-012 |
| Camping 101: Enchanting (97917) | mago | +216 XP · ~1,6 min: por debajo de la media del tramo. | hmage-elwynn-016, hmage-elwynn-125 |
| Eyes of the Sentinels (98067) | druida | +650 XP · ~9,4 min: por debajo de la media del tramo según el cálculo, pendiente de cronometrar en el juego. (EFFICIENCY.md §6: «a revisar en el juego») | netd-091, netd-092, netd-093 |
| Secure the Mountain (98322) | brujo | +70 XP · <1 min: por debajo de la media del tramo. | dun-morogh-019, dun-morogh-026 |
| The Lost Runner (99046) | druida | +80 XP · <1 min: por debajo de la media del tramo. | netd-060, netd-095 |
| Escaping Ban'ethil (99053) | druida | +850 XP · ~8,5 min: por debajo de la media del tramo según el cálculo, pendiente de cronometrar en el juego. (única escolta de Teldrassil; el escenario «escort» del simulador la usa (netd-065)) | netd-065, netd-073, netd-078 |
| Rime's Wrath (99160) | brujo | +700 XP · ~10 min: por debajo de la media del tramo según el cálculo, pendiente de cronometrar en el juego. (EFFICIENCY.md §6: «a revisar en el juego») | dun-morogh-081, dun-morogh-083, dun-morogh-085 |
| Rime's Wrath (99161) | brujo | +700 XP · ~1 min: por debajo de la media del tramo según el cálculo, pendiente de cronometrar en el juego. (sigue a 99160 (opcional)) | dun-morogh-087, dun-morogh-088, dun-morogh-089 |
| Frostmane Hold (287) | brujo | +955 XP · ~6,7 min: por debajo de la media del tramo. | dun-morogh-038, dun-morogh-061, dun-morogh-072 |
| Crocolisk Hunting (385) | brujo, mago | +2.453 XP · ~11 min: por debajo de la media del tramo. | a12lm-043, a12lm-054, a12lm-057 |
| Jitters' Growling Gut (5) | brujo, mago, druida | +390 XP · ~1,5 min: por debajo de la media del tramo. | a22dw-018, a22dw-034 |
| Protect the Frontier (52) | mago | +1.690 XP · ~12 min: por debajo de la media del tramo; hazla si te interesa la recompensa. | hmage-elwynn-077, hmage-elwynn-085, hmage-elwynn-099 |
| Thundris Windweaver (4761) | druida | +110 XP · <1 min: por debajo de la media del tramo. | neds-030, neds-031 |
| Buzzbox 411 (1001) | druida | +1.772 XP · ~7,5 min: por debajo de la media del tramo. | neds-017, neds-046, neds-047 |
| The Blackwood Corrupted (4763) | druida | +1.700 XP · ~7,5 min: por debajo de la media del tramo. | neds-077, neds-130, neds-140 |

## 4. Excepciones al filtro

Donde se ha corregido la decisión del modelo, con su motivo. Todas son revisables con el Grabador.

**Se quedan (keep) aunque el modelo diga drop:**

- Testing the Wells (92742): corrections/quests.json: «The State of the Mines» (92745) exige 92742 y 92744; abre la cadena de Alba hasta Minas de la Muerte.
- The State of the Mines (92745): corrections/quests.json: «Moonbrook Espionage» (92747, keep) exige 92745.
- Detonation at a Distance (92750): a17wf-074: 92752 pide las dos partes (92749 y la cadena 92750-92751); 92752 abre «Destruction in Deadmines» (92753).
- Detonation at a Distance (92751): igual que 92750.
- The Algaz Gauntlet (455): el paso de Dun Algaz es el camino a Los Humedales: el viaje que el modelo le carga no se ahorra quitándola.
- Report to Captain Stoutfist (473): requiere 455 (que se queda).

**Opcionales en vez de quitadas:** las de la tabla 3 con nota entre paréntesis (casos que EFFICIENCY.md §6 marca como
dudosos o sobreestimados, la escolta de Teldrassil y «Young Crocolisk Skins» (484), que abre «Highland Hides» (98815)
para Excavation Site según `corrections/quests.json`). También «Beached Sea Creature» (4730), que tras recalcular cae a
`drop` por poco (49% de la mediana) y está en la misma playa que 4722 y 4727. «Raid on the Kolkar» (1384), «Stealing
Supplies» (1370) y «Valley of Bones» (93034) son `drop` para unos personajes y `optional` para otros: en la sección
compartida se quedan opcionales.

## 5. Orden

Con los requisitos de forever-db (`data/prereq.json` y `corrections/quests.json`), las tres guías no tienen ninguna
misión que se coja antes de entregar su previa salvo tres, todas en Los Humedales (`a26`): las dos de la sección 2 y:

- `a26wl-020` (coger 98815) pasa detrás de `a26wl-032`: corrections/quests.json (#533): Halloran ofrece «Highland Hides» (98815) solo tras entregar 484; antes se cogía en la primera visita. Lleva un truco que lo explica.

El resto de diferencias de orden con Polestar (45-52% de las cogidas y entregas comunes, IMPORT-REPORT.md §5) son de
diseño de ruta (qué zona va antes), no errores: Senda conserva su orden. Las pistas de viaje que estaban en un paso quitado
(«Sigue el camino al norte hasta Dun Algaz...») pasan como `tip` al siguiente paso que va a ese sitio, con el PNJ como
ficha: `a26wl-007`, `a26wl-044`, `a26wl-058`, `dun-morogh-028`, `dun-morogh-038`, `dun-morogh-078`,
`hmage-northshire-032`, `netd-090`, `coldridge-022`.

## 6. Coordenadas

Todos los pasos con `npc` y `at` de las tres guías y de `data/shared/` se han comparado con las apariciones del PNJ en
forever-db (incluidas las alternativas). Solo dos estaban a más de 1,0 y se ponen en la aparición:

- `netd-063`: [1438, 40.46, 50.73] → [1438, 42.22, 51.26] (forever-db: Centinela Shayla Nightbreeze (2155) aparece en 42.22, 51.26 (a 1,84 del paso); Polestar usa el mismo punto).
- `netd-076`: [1438, 40.46, 50.73] → [1438, 42.22, 51.26] (forever-db: Centinela Shayla Nightbreeze (2155) aparece en 42.22, 51.26 (a 1,84 del paso); Polestar usa el mismo punto).

IMPORT-REPORT.md §6 daba la razón a Senda en este caso comparando con QuestieDB; forever-db (la base del plan) y Polestar
coinciden en 42.22, 51.26. El resto de desacuerdos de esa tabla tienen varios iniciadores (los dos puntos valen) o ya
estaban a menos de 1,0 de la aparición.

## 7. Misiones añadidas de Polestar

Candidatas: misiones de las rutas de Polestar importadas (`data/scores/*-ps.json`) con decisión `keep` por tasa o cadena,
en el cuartil alto de su banda (percentil ≥ 75), que no están en Senda, con todos sus requisitos ya en la ruta y con cada
paso a ≤ 5% de mapa de un paso de Senda del mismo mapa y ±3 niveles. De las 15-19 candidatas por personaje entran estas
(en secciones compartidas, así que las tres guías las tienen):

| Misión | Pasos | Puntuación tras añadirla | Por qué cabe |
|---|---|---|---|
| A Free Lunch (129) | a19rr-012b, a19rr-027b | +550 XP · <1 min · 2,5× la mediana del 16-20 | Polestar la coge en la posada de Villa del Lago y la entrega en Tres Caminos; la ruta de Senda pasa por los dos sitios |
| Bloom of the Heavens (98208) | a26wl-018b, a26wl-025b, a26wl-032b | +1.750 XP · ~1 min · 3,2× la mediana del 26-30 | Polestar: misión de Forever en el muelle de Menethil; el objeto está en la orilla al sur del pueblo |
| Ormer's Revenge (296) | a26wl-052b, a26wl-052c, a26wl-052d | +3.144 XP · ~2,2 min · 2,8× la mediana del 26-30 | Polestar: tercera parte de la cadena de Ormer que Senda ya hace (294, 295); Sarltooth está junto a la excavación |
| The Karnitol Shipwreck (1454, 1455) | a34-desolace-017b, a34-desolace-019b, a34-desolace-019c, a38-valle-de-huesos-017b | +3.000 XP · ~1 min · desbloquea «The Karnitol Shipwreck»; 1455: +1.500 XP · <1 min · 4,4× la mediana del 36-40 | Polestar: el cofre está junto a la torre de Azore, por donde pasa la ruta; la segunda parte se entrega al volver a Punta de Nijel |

Los textos son de Senda, en español y con fichas (`{npc:N}`, `{item:N}`); las coordenadas, de forever-db (PNJ y objetos)
o del paso de Polestar cuando el objetivo no tiene aparición («Nord'el», 12.2, 63.8). Cada paso cita
`polestar:19bd636e…/<guía>#<paso>` y `foreverdb:` en `sources` (Polestar, GPL-3.0: ver THIRD_PARTY.md).

**Candidatas que no entran:**

- *Sven's Camp* (230), *The Shadowy Figure* (262) y su cadena, Bosque del Ocaso: Senda visita a Sven antes de pasar por
  el montón de tierra; cogerlas obliga a volver al oeste de la zona.
- *The Price of Shoes* (118): se entrega en Villadorada, que la ruta ya ha dejado atrás.
- *Bitter Rivals* (310) y *Return to Marleth* (311), Dun Morogh: piden antes *Distracting Jarven* (308) y comprar Cerveza
  del Trueno; tres misiones por 765 XP.
- *An Apple Treat* (91738), Elwynn (mago): pide la sidra de una misión que la ruta no hace.
- *Auntie Marlene* (5152) y la cadena de Darrowshire (5153, 5154, 5210): empieza en las Tierras de la Peste del Este y
  vuelve al Oeste; Senda hace el Oeste antes.
- *Alas, Andorhal* (211): Polestar la marca opcional (Araj el Invocador, élite de nivel 61).
- *Lightforge Iron* (321), *Vahlarriel's Search* (1438), *Further Mysteries* (525), *The Torch of Retribution* (3454):
  sus requisitos (270, 1465, 514, 3453) no están en la ruta. *Furlbrow's Deed* (184) empieza con un objeto que cae.

## 8. El porqué de cada misión (`why`)

Campo nuevo de paso, `why` (string, solo para mostrar; `schema/section.schema.json`, ARCHITECTURE.md). Va en el **primer
paso** (en el orden de la ruta) de cada misión que se queda, con la línea del filtro recalculado:

- tasa: `+1.750 XP · ~1 min · 3,3× la media del tramo` (la «media» es la mediana de la banda de 5 niveles);
- cadena: `+625 XP · <1 min · desbloquea «{quest:951}» y 3 más`;
- clase: `+390 XP · <1 min · misión de clase`; mazmorra: `+2.300 XP · mazmorra: Hall of Thanes`;
- botín sin datos: solo `+700 XP` (el tiempo no es fiable); las que se entregan fuera de la guía o dan 0 XP no lo llevan;
- las excepciones de la sección 4 llevan el motivo de la fusión (`desbloquea la cadena de {npc:253092} hasta Minas de la Muerte`).

En una sección compartida, la línea es la del primer personaje que pasa por ese paso (brujo, mago, druida): la XP y los
minutos cambian poco entre ellos. Las opcionales no llevan `why`: su motivo está en `tip`. El HUD lo mostrará más adelante
(fuera de esta fase); hoy solo viaja en los datos.

## 9. Pendiente

- `tools/route_score.py` y `data/prereq.json` no leen `corrections/quests.json` de forever-db: con ellos, «Young
  Crocolisk Skins» (484), «Testing the Wells» (92742) y «The State of the Mines» (92745) saldrían `keep` por cadena sin
  excepción a mano, y los dos hechos equivocados de la sección 2 no habrían entrado. Arreglo propuesto: aplicar `set.pre`,
  `preAll` y `preAny` de las correcciones al cargar forever-db (`tools/foreverdb/db.py`) y regenerar `prereq.json`.
- La cadena de Alba (92742 → 92745 → 92747 → 92748 → 92749/92750-92751 → 92752 → 92753) no tiene requisitos en
  forever-db más allá de 92745 y 92747; que 92752 pida las dos partes sale del texto de Senda (`a17wf-074`). Confirmar en
  el juego.
- El filtro no es estable al quitar misiones (el viaje compartido se reparte de nuevo): han hecho falta dos pasadas, y
  «The Algaz Gauntlet» (455) cae a `drop` por cargar con el camino de Dun Algaz, que no se ahorra. Puntuar por zona
  (EFFICIENCY.md §5) lo resolvería.
- Cronometrar con el Grabador las opcionales «pendientes de cronometrar» (tabla 3) y las nuevas de Polestar.
- Los pasos nuevos están `unverified`; los textos son de Senda pero sin revisar en el juego.


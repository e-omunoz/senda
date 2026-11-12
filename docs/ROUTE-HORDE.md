# Rutas de la Horda (fase 4)

> Fase 4 del [plan](PLAN-POLESTAR.md): la Horda con la misma identidad que la Alianza. Generado por
> `tools/gen_horde.py` desde Polestar (GPL-3.0, commit `19bd636e`), forever-db 2026.11.1 (con
> `corrections/quests.json`) y las listas del instructor de `data/knowledge/trainer/`. Para regenerar:
>
> ```sh
> python tools/gen_horde.py --polestar RUTA/polestar --foreverdb .cache/foreverdb
> python tools/validate.py && python tools/build.py
> ```

## 1. Qué hay

| Guía | Raza (`races`) | Salida de raza | Secciones |
|---|---|---|---|
| `orc-horde` (Orco 1-60) | Orc | `01-durotar` (Valle de los Retos, 1-12) | 1 + 25 compartidas |
| `troll-horde` (Trol 1-60) | Troll | `01-durotar` (Valle de los Retos, 1-12) | 1 + 25 |
| `tauren-horde` (Tauren 1-60) | Tauren | `01-mulgore` (Campamento Narache, 1-12) | 1 + 25 |
| `undead-horde` (No-muerto 1-60) | Scourge | `01-claros-de-tirisfal` (Camposanto, 1-13) | 1 + 25 |
| `skyborne-horde` (Skyborne 1-60) | Skyborne | `01-isla-de-zephras` (1-14) | 1 + 25 |

- **Una guía por raza, para cualquier clase** (`classes` = las nueve; `Guides:Score` la elige sola para cualquier
  personaje de esa raza en la Horda). Skyborne tiene salida propia en la Horda en Forever (Polestar
  `forever/horde/skyborne/01-zephras-isle`); la guía lleva `faction = "Horde"`, así que un Skyborne de la Alianza no la ve.
- **Ruta común 12-60** en `data/shared/h*.toml` (25 secciones, `if = { faction = "Horde" }`), en el orden de `next` de
  Polestar: Bosque de Argénteos, Los Baldíos, Vallefresno, Trabalomas, Baldíos y Sierra Espolón, Vallefresno y Mil
  Agujas, Trabalomas y Arathi, Mil Agujas y Desolace, Tuercespina, Revolcafango, Alterac y Arathi, Tierras Inhóspitas,
  Tuercespina y Pantano de las Penas, Feralas y Tanaris (dos veces), Tanaris y La Garganta de Fuego, Tierras del
  Interior, Azshara, Un'Goro, Frondavil, Cuna del Invierno, Azshara, Tierras de la Peste del Este, Silithus, Frondavil.
- Todos los pasos llevan `status = "unverified"` y `sources` (`polestar:<commit>/<guía>#<paso>`, y `trainer:<clase>`
  en los de entrenamiento). Las guías se publican (no llevan `ship = false`).
- **Clases solo de la Horda (chamán):** sin páginas de conocimiento; el chamán tiene sus pasos de entrenamiento como
  todas las clases (lista del instructor de `data/knowledge/trainer/shaman.json`).

## 2. Lo que se completa sobre el importador

| Qué | Cómo | Cuántos |
|---|---|---:|
| «Entrena tu clase» (manual en el importador) | Un paso `train` por clase con `if.class`: los hechizos que vende el instructor entre el entrenamiento anterior de esa clase y el nivel de ese punto de la ruta (interpolado en la sección, o el último paso `level`), `reqlevel` = el nivel más alto de la lista (el motor lo aplaza si aún no lo tienes) y el instructor más cercano de esa clase entre los candidatos de Polestar. Los rangos cuyo primer rango no vende el instructor (talentos, misiones) no se piden. Los hechizos de una sola raza van en un paso aparte con `if.race` | 107 puntos, 291 pasos |
| Objetivo «hablar» de una misión | `complete` con `obj` (el importador lo dejaba como nota «Talk.») | 22 |
| «Vendedor», «morir» | Notas en español, opcionales | 17, 4 |
| Destinos de `goto` en inglés | Fichas `{area:N}` (subzona; ficha nueva, `C_Map.GetAreaInfo`), nombres esES de los nodos de vuelo de Polestar y patrones («X flight master» » «Ve al maestro de vuelo de X»...). Lo que no se puede traducir queda «Ve al punto marcado.» con el inglés en `note` | 19 genéricos |
| Notas de Polestar sin traducción | Traducidas por Senda (`EN_NOTES`); las que no aportan, fuera | 18 / 5 |
| Consejos sin traducción (`[EN]` en `tip`, del objetivo o del paso de Polestar) | Fuera del texto visible; quedan en `note` | 1.063 |
| Coordenadas del marco de Era sin transformación (Mulgore, Tierras de la Peste del Este) | Centro de las apariciones del objetivo en forever-db; si no hay, el `goto` sale y el resto se queda sin `at` | 1 / 10 / 14 |
| Dinero, reputación y habilidad de monta | Fuera (no son pasos de ruta) | |

## 3. Antes y después (filtro de eficiencia)

Mismo método que la Alianza ([ROUTE-CHANGES.md](ROUTE-CHANGES.md) §1): «antes» es la ruta de Polestar importada con
lo anterior; «después», tras el filtro. Las bandas salen **solo de las guías de la Horda**
(`data/scores/bands-horde.json`; `tools/route_score.py` ahora separa las bandas por facción, así que las de la Alianza
no se mueven). Las guías se puntúan sin los pasos de clase (ruta común). Los requisitos de `corrections/quests.json`
se aplican antes de decidir (lo que ROUTE-CHANGES.md §9 dejaba pendiente para la Alianza).

| Guía | | Misiones | Minutos | XP | Sin opcionales: misiones | minutos | XP | drop que quedan |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Orco (`orc-horde`) | antes | 803 | 7.480 (124 h 40 min) | 3.468.037 | 688 | 6.504 (108 h 24 min) | 2.919.374 | |
|  | después | 707 | 6.137 (102 h 17 min) | 3.059.834 | 507 | 2.989 (49 h 49 min) | 1.696.675 | 2 |
| Trol (`troll-horde`) | antes | 803 | 7.488 (124 h 48 min) | 3.468.037 | 688 | 6.511 (108 h 31 min) | 2.919.374 | |
|  | después | 707 | 6.144 (102 h 24 min) | 3.059.834 | 507 | 2.997 (49 h 57 min) | 1.696.675 | 2 |
| Tauren (`tauren-horde`) | antes | 806 | 7.569 (126 h 09 min) | 3.472.321 | 694 | 6.607 (110 h 07 min) | 2.926.514 | |
|  | después | 707 | 6.195 (103 h 15 min) | 3.058.474 | 506 | 2.982 (49 h 42 min) | 1.690.580 | 1 |
| No-muerto (`undead-horde`) | antes | 807 | 7.502 (125 h 02 min) | 3.470.740 | 696 | 6.540 (109 h 00 min) | 2.925.663 | |
|  | después | 704 | 6.123 (102 h 03 min) | 3.056.107 | 508 | 2.972 (49 h 32 min) | 1.694.133 | 1 |
| Skyborne (`skyborne-horde`) | antes | 845 | 7.611 (126 h 51 min) | 3.484.819 | 731 | 6.566 (109 h 26 min) | 2.937.444 | |
|  | después | 753 | 6.303 (105 h 03 min) | 3.080.198 | 553 | 3.043 (50 h 43 min) | 1.714.510 | 1 |

Lectura:

- La ruta de Polestar para la Horda es mucho más completa que la de la Alianza de Senda (unas 800 misiones y 3,5 M de
  XP frente a unas 370 y 1,1 M): sube a 60 casi solo con misiones. El filtro quita unas 100 misiones y **unos 1.345 min
  (22 h)** con todo; sin opcionales, la ruta obligatoria baja de ~6.500 a **~2.990 min (unas 50 h)** con 1,7 M de XP.
- Como referencia, la Alianza (brujo gnomo) queda en 2.703 min con todo y 1.901 sin opcionales, con mucha menos XP de
  misiones: el resto se sube matando (los pasos `level`).
- Son estimaciones del modelo (EFFICIENCY.md §4), no tiempos medidos.

Decisiones: `drop` sale (dos pasadas, como en la Alianza); `optional` lleva `optional = true` en todos sus pasos y el
motivo en el `tip` del primero («+X XP · ~N min: por debajo de la media del tramo...»); `keep` lleva `why` en su primer
paso. En una sección compartida cuenta la decisión más favorable de las cinco guías (keep > optional > drop). Pasos
marcados opcionales por el filtro: 325 en la 1.ª pasada y 148 en la 2.ª (más los que el importador ya marca por
condiciones de Polestar que Senda no expresa). Las «drop que quedan» son misiones que el modelo marca `drop` en la
puntuación final pero que se quedan porque otra guía las ve como `keep` u `optional`.

## 4. Misiones quitadas (120)

| Misión | Sección | Pasada | Pasos | Motivo (filtro) |
|---|---|---|---:|---|
| Plainstrider Menace (844) | h14-los-baldios | 1.ª | 5 | +1.478 XP · ~10 min · lenta: 38% de la mediana del 11-15 |
| The Zhevra (845) | h14-los-baldios | 1.ª | 3 | +1.565 XP · ~9,7 min · requiere «Plainstrider Menace», que sale de la ruta |
| Disrupt the Attacks (871) | h14-los-baldios | 1.ª | 9 | +1.674 XP · ~10 min · lenta: 43% de la mediana del 11-15 |
| The Disruption Ends (872) | h14-los-baldios | 1.ª | 5 | +2.085 XP · ~14 min · requiere «Disrupt the Attacks», que sale de la ruta |
| Echeyakee (881) | h14-los-baldios | 1.ª | 3 | +1.575 XP · ~5,3 min · requiere «Prowlers of the Barrens», que sale de la ruta |
| Ishamuhale (882) | h14-los-baldios | 1.ª | 3 | +1.940 XP · ~5,4 min · requiere «Jorn Skyseer», que sale de la ruta |
| Southsea Freebooters (887) | h14-los-baldios | 1.ª | 4 | +2.148 XP · ~13 min · lenta: 43% de la mediana del 11-15 |
| Stolen Booty (888) | h14-los-baldios | 1.ª | 4 | +1.150 XP · ~3,3 min · requiere «The Missing Shipment», que sale de la ruta |
| The Missing Shipment (890) | h14-los-baldios | 1.ª | 2 | +100 XP · <1 min · requiere «Southsea Freebooters», que sale de la ruta |
| The Missing Shipment (892) | h14-los-baldios | 1.ª | 2 | +100 XP · <1 min · requiere «The Missing Shipment», que sale de la ruta |
| Prowlers of the Barrens (903) | h14-los-baldios | 1.ª | 3 | +1.829 XP · ~11 min · requiere «The Zhevra», que sale de la ruta |
| The Angry Scytheclaws (905) | h14-los-baldios | 1.ª | 5 | +1.250 XP · ~5,4 min · requiere «Echeyakee», que sale de la ruta |
| Enraged Thunder Lizards (907) | h14-los-baldios | 1.ª | 3 | +2.150 XP · ~7 min · requiere «Ishamuhale», que sale de la ruta |
| Cry of the Thunderhawk (913) | h14-los-baldios | 1.ª | 3 | +2.102 XP · ~3,5 min · requiere «Enraged Thunder Lizards», que sale de la ruta |
| Jorn Skyseer (3261) | h14-los-baldios | 1.ª | 2 | +140 XP · <1 min · requiere «The Angry Scytheclaws», que sale de la ruta |
| Nugget Slugs (3922) | h14-los-baldios | 1.ª | 3 | +1.050 XP · ~7,5 min · lenta: 47% de la mediana del 16-20 |
| Rilli Greasygob (3923) | h14-los-baldios | 1.ª | 2 | +340 XP · ~8 min · lenta: 13% de la mediana del 16-20 |
| Meats to Orgrimmar (6365) | h14-los-baldios | 1.ª | 2 | +210 XP · ~4 min · lenta: 16% de la mediana del 11-15 |
| The Ashenvale Hunt (6382) | h14-los-baldios, h21-vallefresno-argenteos | 1.ª | 2 | +390 XP · <1 min · requiere «Ishamuhale», que sale de la ruta |
| Blood Feeders (6461) | h14-los-baldios | 1.ª | 4 | +2.816 XP · ~24 min · lenta: 38% de la mediana del 21-25 |
| Battle of Hillsbrad (527) | h22-trabalomas, h29-trabalomas-arathi | 1.ª | 12 | +3.742 XP · ~19 min · lenta: 37% de la mediana del 26-30 |
| Battle of Hillsbrad (528) | h22-trabalomas, h29-trabalomas-arathi | 1.ª | 6 | +3.833 XP · ~15 min · requiere «Battle of Hillsbrad», que sale de la ruta |
| Battle of Hillsbrad (529) | h22-trabalomas, h29-trabalomas-arathi | 1.ª | 10 | +2.942 XP · ~15 min · requiere «Battle of Hillsbrad», que sale de la ruta |
| Souvenirs of Death (546) | h22-trabalomas | 1.ª | 3 | +7.389 XP · ~17 min · requiere «Battle of Hillsbrad», que sale de la ruta |
| Scout Support (98094) | h22-trabalomas | 1.ª | 2 | +1.000 XP · ~2 min · requiere «Battle of Hillsbrad», que sale de la ruta |
| Valuable Vantages (98095) | h22-trabalomas | 1.ª | 5 | +2.000 XP · ~13 min · lenta: 40% de la mediana del 21-25 |
| Isha Awak (873) | h24-baldios-espolon | 1.ª | 3 | +2.934 XP · ~3 min · requiere «Mahren Skyseer», que sale de la ruta |
| Mahren Skyseer (874) | h24-baldios-espolon | 1.ª | 2 | +550 XP · ~1 min · requiere «Cry of the Thunderhawk», que sale de la ruta |
| Cycle of Rebirth (6301) | h24-baldios-espolon | 1.ª | 3 | +1.400 XP · ~8 min · lenta: 42% de la mediana del 21-25 |
| New Life (6381) | h24-baldios-espolon | 1.ª | 3 | +2.000 XP · ~8,3 min · requiere «Cycle of Rebirth», que sale de la ruta |
| Je'neu of the Earthen Ring (824) | h26-vallefresno-mil-agujas | 1.ª | 2 | +2.290 XP · ~15 min · requiere «The Befouled Element», que sale de la ruta |
| The Befouled Element (1918) | h26-vallefresno-mil-agujas | 1.ª | 2 | +640 XP · ~10 min · lenta: 14% de la mediana del 26-30 |
| The Essence of Aku'Mai (6563) | h26-vallefresno-mil-agujas | 1.ª | 3 | +1.750 XP · ~8,6 min · lenta: 49% de la mediana del 26-30 |
| Battle of Hillsbrad (532) | h29-trabalomas-arathi | 1.ª | 6 | +2.789 XP · ~7,5 min · requiere «Battle of Hillsbrad», que sale de la ruta |
| Battle of Hillsbrad (539) | h29-trabalomas-arathi | 1.ª | 4 | +3.499 XP · ~6,6 min · requiere «Battle of Hillsbrad», que sale de la ruta |
| Battle of Hillsbrad (541) | h29-trabalomas-arathi | 1.ª | 6 | +6.805 XP · ~21 min · requiere «Battle of Hillsbrad», que sale de la ruta |
| Battle of Hillsbrad (550) | h29-trabalomas-arathi | 1.ª | 2 | +2.550 XP · ~2 min · requiere «Battle of Hillsbrad», que sale de la ruta |
| Hammerfall (655) | h29-trabalomas-arathi | 1.ª | 2 | +270 XP · ~2,4 min · lenta: 26% de la mediana del 31-35 |
| Raising Spirits (672) | h29-trabalomas-arathi | 1.ª | 3 | +7.722 XP · ~36 min · lenta: 46% de la mediana del 31-35 |
| Raising Spirits (674) | h29-trabalomas-arathi | 1.ª | 2 | +270 XP · <1 min · requiere «Raising Spirits», que sale de la ruta |
| Raising Spirits (675) | h29-trabalomas-arathi | 1.ª | 2 | +270 XP · <1 min · requiere «Raising Spirits», que sale de la ruta |
| The Corrupter (1480) | h32-mil-agujas-desolace | 1.ª | 2 | +6.460 XP · ~29 min · lenta: 44% de la mediana del 31-35 |
| Investigate the Camp (201) | h34-tuercespina | 1.ª | 3 | +260 XP · ~1,3 min · lenta: 36% de la mediana del 31-35 |
| Mok'thardin's Enchantment (572) | h34-tuercespina, h40-tuercespina-penas | 1.ª | 3 | +12.530 XP · ~51 min · lenta: 36% de la mediana del 36-40 |
| Get Me Out of Here! (6132) | h36-revolcafango-desolace | 1.ª | 3 | +2.250 XP · ~11 min · lenta: 33% de la mediana del 36-40 |
| Sigil of Strom (639) | h38-alterac-arathi | 1.ª | 3 | +17.858 XP · ~57 min · lenta: 46% de la mediana del 36-40 |
| Stones of Binding (651) | h38-alterac-arathi | 1.ª | 5 | +2.850 XP · ~20 min · lenta: 21% de la mediana del 36-40 |
| Guile of the Raptor (701) | h38-alterac-arathi | 1.ª | 3 | +8.995 XP · ~25 min · requiere «Raising Spirits», que sale de la ruta |
| Guile of the Raptor (702) | h38-alterac-arathi | 1.ª | 2 | +290 XP · <1 min · requiere «Guile of the Raptor», que sale de la ruta |
| Guile of the Raptor (847) | h38-alterac-arathi | 1.ª | 2 | +2.850 XP · <1 min · requiere «Guile of the Raptor», que sale de la ruta |
| Coyote Thieves (1419) | h39-tierras-inhospitas | 1.ª | 3 | +11.527 XP · ~32 min · lenta: 49% de la mediana del 36-40 |
| Badlands Reagent Run (2258) | h39-tierras-inhospitas | 1.ª | 7 | +16.227 XP · ~60 min · lenta: 37% de la mediana del 36-40 |
| Mok'thardin's Enchantment (571) | h40-tuercespina-penas | 1.ª | 3 | +7.350 XP · ~17 min · requiere «Mok'thardin's Enchantment», que sale de la ruta |
| Mok'thardin's Enchantment (573) | h40-tuercespina-penas | 1.ª | 4 | +6.865 XP · ~9 min · requiere «Mok'thardin's Enchantment», que sale de la ruta |
| The Ogres of Feralas (2980) | h43-feralas-tanaris | 1.ª | 5 | +9.900 XP · ~25 min · lenta: 49% de la mediana del 41-45 |
| The Gordunni Orb (3002) | h43-feralas-tanaris | 1.ª | 2 | +2.384 XP · ~35 min · lenta: 8% de la mediana del 41-45 |
| Natural Materials (3128) | h45-feralas-revolcafango | 1.ª | 6 | +23.172 XP · ~148 min · lenta: 21% de la mediana del 46-50 |
| Perfect Yeti Hide (7738) | h45-feralas-revolcafango | 1.ª | 2 | +4.945 XP · ~13 min · lenta: 49% de la mediana del 46-50 |
| Venom Bottles (2933) | h48-interior-devastadas, h51-ungoro-estepas | 1.ª | 2 | +360 XP · ~1 min · lenta: 29% de la mediana del 51-55 |
| Stalking the Stalkers (7828) | h48-interior-devastadas | 1.ª | 4 | +11.615 XP · ~29 min · lenta: 49% de la mediana del 46-50 |
| Cannibalistic Cousins (7844) | h48-interior-devastadas | 1.ª | 6 | +14.120 XP · ~45 min · lenta: 38% de la mediana del 46-50 |
| Weapons of Spirit (3129) | h50-azshara-feralas | 1.ª | 2 | +4.700 XP · ~2,7 min · requiere «Natural Materials», que sale de la ruta |
| Delivery to Magatha (3518) | h50-azshara-feralas | 1.ª | 2 | +2.550 XP · ~26 min · lenta: 9% de la mediana del 51-55 |
| Magatha's Payment to Jediga (3562) | h50-azshara-feralas, h56-azshara-baldios | 1.ª | 2 | +3.800 XP · <1 min · requiere «Delivery to Magatha», que sale de la ruta |
| The Strength of Corruption (4120) | h50-azshara-feralas, h53-frondavil-peste-oeste, h55-cuna-del-invierno | 1.ª | 4 | +11.436 XP · ~25 min · lenta: 24% de la mediana del 56-60 |
| Again With the Zapped Giants (7725) | h50-azshara-feralas | 1.ª | 3 | +2.917 XP · ~9,5 min · lenta: 27% de la mediana del 51-55 |
| Refuel for the Zapping (7726) | h50-azshara-feralas | 1.ª | 3 | +3.296 XP · ~9,5 min · lenta: 31% de la mediana del 51-55 |
| The Rise of the Machines (4061) | h51-ungoro-estepas | 1.ª | 3 | +12.361 XP · ~27 min · lenta: 38% de la mediana del 51-55 |
| A Plague Upon Thee (5901) | h51-ungoro-estepas, h53-frondavil-peste-oeste | 1.ª | 3 | +5.650 XP · ~58 min · lenta: 8% de la mediana del 51-55 |
| Wild Guardians (4521) | h53-frondavil-peste-oeste, h55-cuna-del-invierno, h56-peste-del-este | 1.ª | 4 | +15.025 XP · ~39 min · lenta: 20% de la mediana del 56-60 |
| A Plague Upon Thee (5902) | h53-frondavil-peste-oeste, h57-silithus-pestes | 1.ª | 2 | +2.800 XP · <1 min · requiere «A Plague Upon Thee», que sale de la ruta |
| Feathers for Grazle (8466) | h53-frondavil-peste-oeste | 1.ª | 1 | +4.194 XP · ~9,6 min · lenta: 34% de la mediana del 51-55 |
| Chillwind Horns (4809) | h55-cuna-del-invierno | 1.ª | 3 | +19.050 XP · ~44 min · lenta: 23% de la mediana del 56-60 |
| The Apothecary's Metaphysical Primer (79095) | h56-azshara-baldios | 1.ª | 2 | +16 XP · <1 min · lenta: 2% de la mediana del 56-60 |
| Wild Guardians (4741) | h56-peste-del-este, h59-frondavil-claro | 1.ª | 3 | +10.711 XP · ~20 min · requiere «Wild Guardians», que sale de la ruta |
| Defenders of Darrowshire (5211) | h56-peste-del-este | 1.ª | 3 | +5.650 XP · ~26 min · lenta: 11% de la mediana del 56-60 |
| A Plague Upon Thee (6390) | h57-silithus-pestes | 1.ª | 2 | +5.650 XP · <1 min · requiere «A Plague Upon Thee», que sale de la ruta |
| Umber, Archivist (6844) | h57-silithus-pestes, h59-frondavil-claro | 1.ª | 2 | +3.264 XP · ~59 min · lenta: 3% de la mediana del 56-60 |
| Stepping Up Security (8281) | h57-silithus-pestes | 1.ª | 3 | +12.940 XP · ~27 min · lenta: 23% de la mediana del 56-60 |
| Under the Chitin Was... (1185) | h59-frondavil-claro | 1.ª | 1 | +3.000 XP · <1 min · requiere «Uncovering Past Secrets», que sale de la ruta |
| Uncovering Past Secrets (6845) | h59-frondavil-claro | 1.ª | 2 | +7.550 XP · <1 min · requiere «Umber, Archivist», que sale de la ruta |
| Beads for Salfa (8469) | h59-frondavil-claro | 1.ª | 1 | +4.627 XP · ~11 min · lenta: 21% de la mediana del 56-60 |
| Encroachment (837) | orc-durotar, trl-durotar | 1.ª | 12 | +1.621 XP · ~13 min · lenta: 44% de la mediana del 6-10 |
| Legging It (96821) | orc-durotar, trl-durotar | 1.ª | 8 | +550 XP · ~14 min · lenta: 12% de la mediana del 1-5 |
| Lost in the Shadows (99123) | orc-durotar, trl-durotar | 1.ª | 6 | +700 XP · ~7,6 min · lenta: 47% de la mediana del 6-10 |
| A Grand Adventure (92708) | sky-isla-de-zephras | 1.ª | 3 | +90 XP · ~2,6 min · lenta: 21% de la mediana del 6-10 |
| The Earthen Ring (95349) | sky-isla-de-zephras | 1.ª | 2 | +90 XP · <1 min · lenta: 47% de la mediana del 11-15 |
| Poison Water (748) | tau-mulgore | 1.ª | 4 | +1.360 XP · ~13 min · lenta: 31% de la mediana del 1-5 |
| Winterhoof Cleansing (754) | tau-mulgore | 1.ª | 3 | +550 XP · ~2,6 min · requiere «Poison Water», que sale de la ruta |
| Thunderhorn Totem (756) | tau-mulgore | 1.ª | 4 | +2.889 XP · ~31 min · requiere «Winterhoof Cleansing», que sale de la ruta |
| Thunderhorn Cleansing (758) | tau-mulgore | 1.ª | 3 | +700 XP · ~2,4 min · requiere «Thunderhorn Totem», que sale de la ruta |
| Wildmane Totem (759) | tau-mulgore | 1.ª | 3 | +2.894 XP · ~22 min · requiere «Thunderhorn Cleansing», que sale de la ruta |
| Wildmane Cleansing (760) | tau-mulgore | 1.ª | 3 | +1.050 XP · ~2 min · requiere «Wildmane Totem», que sale de la ruta |
| The Barrens Oases (886) | tau-mulgore | 1.ª | 2 | +85 XP · ~1 min · lenta: 30% de la mediana del 11-15 |
| Grace of An'she and Mu'sha (95805) | tau-mulgore | 1.ª | 2 | +180 XP · ~4 min · lenta: 43% de la mediana del 1-5 |
| The Longwalkers (98430) | tau-mulgore | 1.ª | 3 | +700 XP · ~6 min · lenta: 48% de la mediana del 6-10 |
| At War With The Scarlet Crusade (370) | und-claros-de-tirisfal | 1.ª | 5 | +1.176 XP · ~5,3 min · requiere «At War With The Scarlet Crusade», que sale de la ruta |
| At War With The Scarlet Crusade (371) | und-claros-de-tirisfal | 1.ª | 4 | +1.355 XP · ~5,5 min · requiere «At War With The Scarlet Crusade», que sale de la ruta |
| Proof of Demise (374) | und-claros-de-tirisfal | 1.ª | 3 | +2.001 XP · ~14 min · requiere «At War With The Scarlet Crusade», que sale de la ruta |
| Vital Intelligence (383) | und-claros-de-tirisfal | 1.ª | 2 | +410 XP · ~8 min · lenta: 15% de la mediana del 1-5 |
| At War With The Scarlet Crusade (427) | und-claros-de-tirisfal | 1.ª | 3 | +1.300 XP · ~5,4 min · requiere «Vital Intelligence», que sale de la ruta |
| A Rogue's Deal (590) | und-claros-de-tirisfal | 1.ª | 3 | +110 XP · ~3 min · lenta: 22% de la mediana del 6-10 |
| Gordo's Task (5481) | und-claros-de-tirisfal | 1.ª | 3 | +230 XP · ~2 min · lenta: 40% de la mediana del 1-5 |
| Doom Weed (5482) | und-claros-de-tirisfal | 1.ª | 3 | +550 XP · ~4,5 min · requiere «Gordo's Task», que sale de la ruta |
| A Righteous Cause (96896) | und-claros-de-tirisfal | 1.ª | 2 | +90 XP · ~3,4 min · lenta: 10% de la mediana del 11-15 |
| Discipline (99134) | und-claros-de-tirisfal | 1.ª | 3 | +830 XP · ~21 min · lenta: 11% de la mediana del 1-5 |
| Tomb Weed (99142) | und-claros-de-tirisfal | 1.ª | 3 | +875 XP · ~2 min · requiere «Doom Weed», que sale de la ruta |
| The Spirits of Stonetalon (1061) | h12-argenteos, h14-los-baldios | 2.ª | 2 | +320 XP · ~1,5 min · lenta: 49% de la mediana del 16-20 |
| Raptor Thieves (869) | h14-los-baldios | 2.ª | 5 | +2.383 XP · ~22 min · lenta: 36% de la mediana del 16-20 |
| Stolen Silver (3281) | h14-los-baldios | 2.ª | 3 | +1.350 XP · ~3,5 min · requiere «Raptor Thieves», que sale de la ruta |
| Supplies for the Crossroads (5041) | h14-los-baldios | 2.ª | 5 | +975 XP · ~5,4 min · lenta: 46% de la mediana del 11-15 |
| Goblin Sponsorship (1181) | h34-tuercespina, h40-tuercespina-penas | 2.ª | 4 | +290 XP · <1 min · lenta: 49% de la mediana del 36-40 |
| Goblin Sponsorship (1182) | h34-tuercespina | 2.ª | 3 | +2.850 XP · <1 min · requiere «Goblin Sponsorship», que sale de la ruta |
| Goblin Sponsorship (1183) | h34-tuercespina, h43-feralas-tanaris | 2.ª | 2 | +420 XP · <1 min · requiere «Goblin Sponsorship», que sale de la ruta |
| Up to Snuff (587) | h40-tuercespina-penas | 2.ª | 3 | +13.992 XP · ~38 min · lenta: 50% de la mediana del 36-40 |
| The Eighteenth Pilot (1186) | h43-feralas-tanaris | 2.ª | 2 | +174 XP · <1 min · requiere «Goblin Sponsorship», que sale de la ruta |
| The Great Outdoors (96604) | orc-durotar, trl-durotar | 2.ª | 6 | +410 XP · ~3,4 min · lenta: 46% de la mediana del 1-5 |
| Camping 101: Cooking (96655) | orc-durotar, trl-durotar | 2.ª | 6 | +270 XP · ~1,6 min · requiere «The Great Outdoors», que sale de la ruta |
| Bandarion Keep (96899) | und-claros-de-tirisfal | 2.ª | 2 | +460 XP · ~6 min · lenta: 27% de la mediana del 11-15 |
| Seeking Refuge (99144) | und-claros-de-tirisfal | 2.ª | 3 | +625 XP · ~9 min · lenta: 42% de la mediana del 6-10 |

## 5. Facción: la Alianza no cambia

- Las guías de la Horda y `SharedHorde.lua` (las secciones que solo usan ellas) llevan una guarda en el Lua generado:
  un personaje de otra facción no registra nada de la Horda (`tools/build.py`, `GATED_FACTIONS`). `Shared.lua` y las
  guías de la Alianza se generan igual que antes, byte a byte.
- `Guides:Score` ya daba 0 a una guía de otra facción; la guarda además ahorra la memoria (~1 MB de Lua).
- Simulador (`tests/wowsim/scenarios_horde.js`): `horde-c` comprueba con el brujo gnomo que no existe ninguna guía ni
  sección de la Horda, que la guía y el primer paso no cambian y que `/senda guide orc-horde` no hace nada.

## 6. Pruebas

| Escenario | Qué |
|---|---|
| `horde-a` | Guerrero orco de nivel 1: `orc-horde` elegida sola, primer paso, HUD, flecha en Durotar, las cinco guías registradas con ids únicos y `at` válidos, ninguna guía de la Alianza ofrecida |
| `horde-b` | Coger misión; paso de entrenamiento del guerrero (hechizos, instructor, aplazado por nivel y completado al aprenderlos); fichas resueltas en el HUD |
| `horde-c` | Alianza intacta (brujo gnomo) |
| `horde-d` a `horde-h` | Guía entera con 0 pasos atascados: guerrero orco, mago no-muerto, druida tauren, chamán trol, cazador Skyborne |

El simulador ganó razas y clases de la Horda, los mapas de las salidas y una bolsa que apila y tira lo más viejo
cuando se llena (una ruta 1-60 recoge más de 16 objetos).

## 7. Pendiente

- Verificar en el juego (todo es `unverified`): sobre todo los puntos de entrenamiento (nivel estimado por posición) y
  las misiones del Skyborne en la isla de Zephras.
- Reserva de XP («Aparte»): `data/reserve.json` solo trae misiones para los tres personajes de la Alianza; la Horda no
  tiene reserva todavía.
- Cronometrar con el Grabador las opcionales y las del cuartil bajo; puntuar por zona (EFFICIENCY.md §5).
- 19 destinos de `goto` genéricos y 14 pasos sin punto en Mulgore y las Tierras de la Peste del Este (marco de Era sin
  transformación).
- Nombres de objetos del mundo sin esES (`{obj:N}` cae al inglés de Polestar).
- `data/scores/<raza>-horde.json` los escribe `gen_horde.py` (con las correcciones de forever-db); `route_score.py` a
  secas no las aplica y da cifras algo distintas.

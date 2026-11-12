# Filtro de eficiencia: «ninguna misión porque sí»

Plan: [PLAN-POLESTAR.md §5.2](PLAN-POLESTAR.md). Herramienta: `tools/route_score.py` (paquete
`tools/routescore/`). Resultado: `data/scores/<guía>.json`, `data/scores/bands.json` y, con `--report`,
`data/scores/<guía>.report.md`.

Todo se calcula **fuera del juego**, en Python, al compilar. El addon no hace nada de esto: cuando se
integre, solo leerá `why`, `xp` y `mins` ya calculados (§5.2: «el resultado se guarda en el TOML»). Esta
primera versión **no escribe en las guías**: deja las puntuaciones por id de paso y de misión para que otro
paso las lleve al TOML.

```
python tools/route_score.py --report                 # todas las guías
python tools/route_score.py --guide human-mage       # solo escribe esa (las bandas salen de todas)
python tools/route_score.py --foreverdb <carpeta>    # o env SENDA_FOREVERDB; por defecto .cache/foreverdb
python tests/test_route_score.py                     # 23 pruebas sintéticas, sin forever-db
```

Tarda ~12 s para las 16 guías actuales (carga de forever-db incluida).

## 1. Datos y de dónde salen

| Dato | Fuente | Tipo |
|---|---|---|
| Pasos, orden, coordenadas, niveles de sección, condiciones (`if`), pasos `level`, `dungeon`, `escort` | Guías de Senda (`data/guides/*/`, `data/shared/*.toml`), leídas con `tomllib` | Real |
| XP de cada misión (a su nivel), nivel, objetivos (matar, objeto, objeto del mundo, evento), requisitos (`all`/`any`, migas de pan), recompensas | forever-db 2026.11.1 (cliente 1.60.1.70532) vía `tools/foreverdb` (solo lectura) | Real |
| Apariciones de enemigos y objetos (yardas de mundo), nivel y rango del enemigo | forever-db `spawn`, `npc`, `object` | Real |
| Probabilidad de botín de cada objeto de misión por enemigo/objeto | forever-db `item_source.chance` (leído directamente; el adaptador no lo expone) | Real («designed loot chance») |
| Mecánicas: escolta, élite/grupo, con tiempo, objeto de otra misión, comprar, fabricar | forever-db `mechanic` | Real |
| Marcos de mapa (de `[uiMap, x%, y%]` a yardas) | forever-db `ui_map` | Real. Comprobado: mediana 0,3 yd y p90 2,2 yd entre el `at` de 785 pasos con PNJ y la aparición de ese PNJ (druida) |
| Tabla de XP por nivel (1.12) | Polestar `tools/lib/game/xp.js` / `rust/crates/forge-guide/src/xp.rs` (GPL-3.0): «Forever has not published a different one; recordings will show if it changed» | Real (1.12); sin confirmar en Forever |
| Reparto de XP de misión por diferencia de nivel (100% hasta +5, luego 80/60/40/20/10%), XP por muerte, nivel gris, regla de Forever (#30) para enemigos por debajo | Polestar `forge-guide/src/xp.rs`, portado a `tools/routescore/model.py` | Real (reglas de Classic) |
| Correr 7 yd/s; montura +60% a 40; épica +100% a 60; Forma de viaje del druida +40% a 30 | cMaNGOS mangos-classic `baseMoveSpeed` y hechizos de Classic/Forever, citados en Polestar `tools/lib/nav/move.js` | Real |
| Nodos de vuelo, vuelos directos (yardas), 30 yd/s + 2 s por salto; barcos, zepelines, tranvía (viaje y espera), portales; piedra 15 s | Polestar `addon/Polestar/Nav/TravelData.lua` y `Nav/Travel.lua` (de las tablas del cliente, CMaNGOS classic-db y Shortest Path Forever), extraídos a `tools/routescore/travel_facts.json` con `tools/routescore/extract_travel.py` | Real. Solo hechos: nada de los mapas de navegación (ni de Leffe ni de Polestar) |
| Desvío de andar 1,25 × línea recta | Polestar `Nav/Travel.lua` (`WALK_DETOUR`) | Aproximación de Polestar |

## 2. Modelo

### Coste (minutos)

`est_minutes = objetivo + viaje + diálogo`

- **Viaje.** Se recorre la ruta en orden. Cada tramo entre pasos se mide en yardas (línea recta × 1,25)
  a la velocidad de ese nivel; si el tramo pasa de 800 yd se prueba también *andar al maestro de vuelo
  más cercano + vuelo (Dijkstra sobre los vuelos de la facción) + andar*; si cambia de continente, el
  mejor barco/zepelín/tranvía/portal (media espera + viaje). Los pasos `fly` usan el nodo de su `node`;
  `hearth` lleva al último `sethearth`.
  - Los pasos a menos de 40 yd forman una **parada**; el tramo que llega a una parada se reparte a partes
    iguales entre sus pasos (entregar 3 misiones a un mismo PNJ reparte el camino entre las 3). Los `goto`
    pasan su tramo a la parada siguiente.
  - Son **gasto de ruta** (no se cargan a ninguna misión): cambiar de zona o de sección, vuelos,
    transportes, piedra y el primer tramo tras un vuelo o la piedra. El informe da su total por guía.
  - **Coste marginal:** también se calcula cuánto viaje se ahorra quitando los pasos de la misión
    (`travel_saved_s`). El viaje de la misión es `max(reparto, marginal)`: así una misión que obliga a un
    desvío lo paga aunque el desvío cruce una zona.
- **Objetivo.** Por cada objetivo de forever-db:
  - *Matar N:* apariciones del enemigo a ≤ 250 yd del paso `complete` (si no hay, las más cercanas y el
    camino de ida y vuelta: bandera `area_moved`); si hacen falta más que las que hay, el área crece a
    400, 600 y 900 yd. Tiempo = N × (segundos por muerte + recorrido entre enemigos). El recorrido es el de
    Beardwood-Halton-Hammersley, 0,7124·√(k·A) para k puntos en el área A. Si aún faltan apariciones, el
    ritmo lo marca la reaparición (300 s / apariciones).
  - *Objeto que sueltan enemigos:* muertes necesarias = N / probabilidad media de botín (ponderada por
    las apariciones de cada enemigo en el área). Sin probabilidad: **desconocido** (`drop_rate_unknown`).
  - *Objeto del mundo:* clics = N / probabilidad (100% si forever-db no la da: `object_chance_assumed_100`).
  - *Créditos* (objetivos «matar» que son un punto a visitar, un PNJ amistoso o un `Credit`/`Trigger`/`DNT`):
    45 s por punto más el recorrido.
  - *Evento / hablar:* 45 s. *Escolta* (mecánica o `escort = true` en el paso): 300 s.
  - Objetivos sobre **los mismos enemigos** (de la misma misión, o de otras cuyos pasos estén a ≤ 8
    posiciones y en la misma área) se hacen a la vez: cuentan el máximo, no la suma, y cada misión paga su
    parte.
  - *Desconocido* (no se filtra): botín sin probabilidad, objetos de bolsa (tela y botín común: no son de
    misión y los sueltan más de 25 enemigos, `inventory_item`), varios objetos sin fuente
    (`item_no_source`), fabricados, contenedores, enemigos sin apariciones, misiones sin XP en forever-db.
- **Diálogo:** 5 s por aceptar o entregar.

### Beneficio

`xp = XP de la misión × reparto por nivel (al entregar) + XP de las muertes que pide`

El nivel del personaje en cada paso sale de la guía: interpolación lineal del `levels` de su sección y,
como suelo, los pasos `do = "level"`.

### Tasa comparable y bandas

La XP por minuto (`xp_per_min`) crece con el nivel, así que para comparar se usa
**`rate` = % del nivel por hora** (XP / XP que pide el nivel / minutos × 60 × 100). Las misiones se
agrupan en **bandas de 5 niveles** (por el nivel al entregar), con todas las guías juntas y sin repetir una
misión que esté en varias. No cuentan para la distribución las de clase, las de mazmorra, las
desconocidas ni las de 0 XP. Si una banda tuviera menos de 8 misiones se juntaría con sus vecinas.

### Decisión (umbrales sacados de los datos)

1. Misión de clase (máscara de clase en forever-db, `if.class` en el paso o sección de clase `mg-`,
   `dr-`, `wl-`…) → **keep**. Mazmorra (en un paso `dungeon`) → **keep** (se decide con la mazmorra).
   Desconocida → **keep** («no se filtra»).
2. `rate` ≥ **p25 de su banda** → **keep**.
3. **Cadena:** la tasa de la misión más las subcadenas que desbloquea en la guía (cada subcadena entra si
   sube la tasa del conjunto) ≥ p25 → **keep** («desbloquea …»). Lo que abre una mazmorra de la guía se
   queda siempre («desbloquea Minas de la Muerte»).
4. Si no: ≥ **50% de la mediana** de su banda → **optional** («floja»). Por debajo pero mejor que **matar
   bichos** a ese nivel (referencia: campamento de 10 enemigos de tu nivel en 150 yd con el mismo modelo)
   → **optional** (quitarla obligaría a ganar esa XP más despacio). Con recompensa de objeto → **optional**
   («solo por la recompensa»).
5. Si no → **drop**. Y todo lo que **requiere** una misión descartada (todas las `all`, o todas las
   alternativas `any` que estén en la guía) → **drop** («requiere «X», que sale de la ruta»).

El motivo en español va en `why`, con las misiones como fichas `{quest:ID}` que el HUD convierte al nombre
del cliente (§6c); `why_plain` lleva el título inglés de forever-db para leerlo fuera del juego. Ejemplos:
`+695 XP · <1 min · desbloquea Minas de la Muerte`, `+500 XP · ~15 min · lenta: 6% de la mediana del 26-30`.

### Distribución (16 guías, 2026-11-12)

`rate` en % del nivel por hora. «Bichos» es la referencia de matar enemigos al nivel central de la banda.

| banda | n | p10 | p25 (keep) | mediana | ½ mediana (drop) | p75 | p90 | bichos |
|---|---|---|---|---|---|---|---|---|
| 1-5 | 147 | 198 | 393 | 658 | 329 | 1256 | 2156 | 566 |
| 6-10 | 232 | 92 | 164 | 254 | 127 | 439 | 783 | 196 |
| 11-15 | 206 | 57 | 95 | 146 | 73 | 314 | 524 | 114 |
| 16-20 | 163 | 47 | 64 | 96 | 48 | 161 | 322 | 78 |
| 21-25 | 130 | 30 | 45 | 72 | 36 | 167 | 342 | 58 |
| 26-30 | 172 | 24 | 41 | 71 | 36 | 136 | 250 | 45 |
| 31-35 | 134 | 25 | 41 | 64 | 32 | 132 | 209 | 35 |
| 36-40 | 155 | 18 | 27 | 46 | 23 | 115 | 282 | 27 |
| 41-45 | 146 | 22 | 30 | 44 | 22 | 120 | 254 | 24 |
| 46-50 | 164 | 19 | 26 | 36 | 18 | 88 | 191 | 20 |
| 51-55 | 119 | 15 | 22 | 45 | 22 | 95 | 179 | 17 |
| 56-60 | 217 | 13 | 22 | 51 | 25 | 146 | 304 | 14 |

Comprobación de coherencia: la referencia de «matar bichos» cae entre el p10 y el p25 de las misiones en
casi todas las bandas (salvo 1-5, donde matar es casi tan rápido como misionar). Es lo que dice la
experiencia: casi todas las misiones rinden más que matar, y las peores rinden como matar.

Las bandas se recalculan en cada ejecución con todas las guías de `data/guides` (hoy incluyen las rutas
importadas de Polestar): si cambia el conjunto de guías, cambian un poco los umbrales.

### Resultado por guía

| guía | misiones | keep | optional | drop | desconocidas | clase | mazmorra | por cadena | min en misiones | min descartables | XP descartada | min de gasto de ruta |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| nightelf-druid | 390 | 311 | 42 | 37 | 20 | 24 | 3 | 15 | 2346 | 476 | 124.880 | 735 |
| human-mage | 403 | 334 | 40 | 29 | 30 | 29 | 13 | 17 | 2504 | 432 | 122.155 | 541 |
| gnome-warlock | 395 | 321 | 39 | 35 | 27 | 25 | 13 | 15 | 2408 | 464 | 126.095 | 573 |
| nightelf-druid-ps | 83 | 69 | 9 | 5 | 4 | 8 | 0 | 3 | 265 | 19 | 955 | 55 |

Lectura: en las tres guías 1-60 de Senda, **el 7-9% de las misiones** se podrían quitar y ahorran **~7-8 h**
de las ~40 h estimadas en misiones a cambio de ~120.000 XP (menos de un nivel 50). Esos números son
estimaciones (sección 4).

## 3. Formato de salida

`data/scores/<guía>.json`:

- `quests["<id>"]`: `xp` (misión + muertes), `xp_quest`, `xp_kills`, `xp_full`, `xp_share`, `kills`,
  `est_minutes`, `objective_s`, `travel_s`, `travel_share_s`, `travel_saved_s`, `dialog_s`, `xp_per_min`,
  `rate`, `grind_rate`, `band`, `percentile` (dentro de su banda), `rel_median`, `chain_rate`, `unlocks`
  (misiones de la guía que dependen de ella), `decision` (`keep`/`optional`/`drop`), `reason`
  (`rate`/`chain`/`class`/`dungeon`/`unknown`/`weak`/`grind`/`reward`/`slow`/`requires`/`not_turned_in`),
  `why`, `why_plain`, `blocked_by`, `objectives` (cada demanda: enemigos u objetos, cuántos, apariciones,
  radio, segundos), `flags`, `estimated` (qué constantes estimadas usa), `guide_optional` (si la guía ya la
  marca opcional), `steps` (ids de sus pasos).
- `steps["<id de paso>"]`: `idx`, `do`, `quest`, `level`, `travel_s` (su parte del viaje), `action_s`
  (vuelo o piedra), `mode` (`walk`, `taxi`, `fly`, id del barco…).
- `bands`, `thresholds`, `estimates`, `sources`, `summary` (incluye el gasto de ruta: viajes entre zonas,
  vuelos y piedra).

## 4. Qué es estimación y qué lo sustituirá

Todo número estimado lleva el prefijo `EST_` en `tools/routescore/model.py` y sale en `estimates` y en el
campo `estimated` de cada misión.

| Estimación | Valor | Lo sustituirá |
|---|---|---|
| Segundos por muerte de un enemigo de tu nivel (combate, botín y su parte de descanso) | (12 + 0,25·nivel) × 1,3 s; +15%/nivel por encima, −8%/nivel por debajo (mín. 50%); élite ×3, jefe ×5, raro ×1,5 | Tiempos por paso del Grabador (§6b) por clase y nivel |
| Reaparición | 300 s | Tiempos del Grabador; `respawn` de classic-db si se incorpora |
| Clic en objeto, evento, crédito | 6 s, 45 s, 45 s | Grabador |
| Escolta | 300 s | Grabador (o la longitud de su camino en classic-db) |
| Diálogo | 5 s por aceptar/entregar | Grabador |
| Distancias | línea recta × 1,25 | Malla de navegación (§6a), con caminos reales y alturas |
| Vuelos | todos los de la facción conocidos | Planificador de viaje con los nodos aprendidos en la ruta |
| Área del objetivo | 250 yd alrededor del paso `complete` (hasta 900 si faltan apariciones) | Rastros de posición del Grabador |
| Nivel del personaje en cada paso | `levels` de la sección interpolado, con los pasos `level` como suelo | XP real del Grabador |
| Referencia de «matar bichos» | 10 enemigos de tu nivel en 150 yd | Grabador |

Criterio de cambio: cuando el Grabador dé tiempos reales por paso, `est_minutes` se calibra con la mediana
del error por tipo de paso (objetivo del plan: error mediano ≤ 30%).

## 5. Límites conocidos

- **Viajes largos que justifica una sola misión.** Un vuelo a otra zona solo para entregar cuenta como
  gasto de ruta: las misiones de mensajero entre zonas (p. ej. «The True Masters» entre Ventormenta y las
  Estepas) salen más baratas de lo que son. El coste marginal no lo corrige porque el paso `fly` no es de
  la misión.
- **Varias misiones en una zona remota.** Cada una paga su parte del viaje dentro de la zona, pero el
  viaje de entrada en la zona es gasto de ruta. Para decidir si compensa ir a una zona hace falta evaluar
  la zona entera (siguiente paso: puntuar secciones).
- **Recompensas.** Solo se sabe si hay objeto de recompensa, no si mejora el equipo de la clase: falta
  cruzarlo con los pesos de Senda y ForeverLevelingBiS (§6b).
- **Migas de pan.** forever-db las marca como no obligatorias; por eso una miga de pan floja no «desbloquea»
  nada aunque lleve al jugador a la zona (p. ej. «Valley of Bones»).
- **Botín común** (tela, carne de cocina con muchos enemigos) y objetos sin fuente: «desconocido».
- **Competencia** con otros jugadores por los mismos enemigos: no se modela.

## 6. Revisión de experto (informe de las 20 peores y 20 mejores por guía)

Fichero: `data/scores/<guía>.report.md`. Ordenado por percentil dentro de la banda. Notas a 2026-11-12
sobre las tres guías 1-60 de Senda (casi todas las misiones bajas se repiten porque comparten secciones):

**Las de menos rendimiento: cuadran con lo que se sabe de subir de nivel.**

- *Tramping Paws* (276, Humedales, 29): 25 gnolls Mosshide de nivel 21-23, **grises a 29** (0 XP por
  muerte), 15 min por 500 XP → drop. Correcto; el problema es de orden: la ruta llega a los Humedales a
  26-30. Hecha a 22-25 sí compensa.
- *Centaur Bounty* (1387, Desolace, 40): 15 orejas con ~20% de botín, ~75 muertes, ~40 min → optional
  (recompensa). Es la clásica misión de «grindeo» que las guías rápidas dejan para cuando sobra tiempo.
- *Power Stones* (2418, Tierras Inhóspitas, 45): dos objetos de los mismos enanos (cuenta el máximo, no la
  suma), ~19 min → optional. Conocida por lenta.
- *Buzzbox 323* (1002, Costa Oscura, 15): pellejos de acechadores lunares, pocos y dispersos, ~30 min →
  drop. Conocida por lenta.
- *Defenders of Darrowshire* (5211, Tierras de la Peste del Este, 60): 30 muertes en tres sitios a nivel 60
  → drop. Las rutas rápidas la saltan.
- *After the Ambush* (454, Loch Modan, 110 XP) y la escolta que abre, *Protecting the Shipment* (309,
  1.050 XP, ~8 min): ni sumando la cadena llega al umbral → drop las dos (la escolta, por requisito).
  Coincide con «escolta larga y poca XP, abajo».
- *Detonation at a Distance* (92750/92751), *Destruction in Deadmines* (92819), *Easing Suffering*
  (99073), *The Goddess Provides* (97979), *Milly Osworth* (3903, miga de pan de 35 XP): XP mínima → drop.
- *Eight-Legged Menaces* (245, Montañas Crestagrana, 24): optional. **Posible sobreestimación:** las
  tarántulas salen en un área de 800 yd porque el paso `complete` está en un extremo; en el juego se hacen
  de camino. Revisar con el Grabador.
- *Beached Sea Turtle* (4722, Costa Oscura): drop por `area_moved`; en la práctica el caparazón está en la
  playa por la que pasa la ruta. **Sobreestimado**: revisar.
- *Valley of Bones* (93034, Forever, 38): miga de pan de 290 XP → drop por XP; revisar si hace falta para
  que aparezcan las misiones de la zona (forever-db dice que no).
- **Débiles que se quedan por la cadena** (lo que pedía el plan): *Boat Wreckage* (4127) y *The Knife
  Revealed* (4129), 375 XP cada una, abren *A Hero's Welcome* (6.050 XP); *A Sign of Hope* (720/721) abre
  *Amulet of Secrets*; *The True Masters* (4224) abre Profundidades de Roca Negra (Windsor); *Tenaron's
  Summons* (920) abre la cadena de *Crown of the Earth*.

**Las de más rendimiento: entregas en el centro de misiones.**

- *Report to Doren*, *Return to Brock*, *Shipment to Stormwind*, *The Defias Brotherhood* (desbloquea Minas
  de la Muerte), *Crown of the Earth* (935), *A Hero's Welcome*, *What the Flux?*, *It's a Secret to
  Everybody*, *Krazek's Cookery*, *Crimson Crate Delivery*: entregas o cadenas de diálogo en un mismo pueblo,
  <1 min por miles de XP. Coincide con «coge siempre las entregas».
- *The True Masters* (4183/4184/4186): arriba por el límite de la sección 5 (el vuelo entre Ventormenta y
  las Estepas es gasto de ruta). La decisión (keep) es correcta; el número está inflado.
- *Webwood Venom* (916) y *Webwood Egg* (917): matar-recoger en la cueva densa de arañas → keep en buen
  percentil, como se espera de «matar-recoger barato en campamento denso».

**A revisar en el juego** (decisión del modelo dudosa): *Eyes of the Sentinels* (98067, Darnassus),
*The State of the Mines* (92745, Páramos de Poniente), *Rime's Wrath* (99160, Dun Morogh), *Facing the
Truth* (93041) y sobre todo *Iverron's Antidote* (3521/3522, Cañada Umbría, 4-5): el modelo descarta la
cadena (891 XP en ~8 min, el 43% de la mediana de 1-5, por debajo de matar bichos a ese nivel), pero es
una cadena que todas las guías hacen: o el modelo sobreestima recoger 7 jacintos y 4 lirios, o subestima lo
que tarda matar a nivel 4. Es el primer caso que hay que cronometrar con el Grabador.

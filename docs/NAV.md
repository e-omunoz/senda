# Navegación: malla real desde el cliente de Forever

Senda calcula los caminos a pie con datos sacados del **terreno real del cliente de WoW: Forever** (ADT, WMO y
colisión de M2), nunca con mapas de navegación ajenos (ni los de Leffe ni nada derivado de ellos). Todo lo
pesado se hace fuera del juego, en Rust (`nav/`); en el juego solo corre Lua 5.1 sobre paquetes de cadenas
compactas. Este documento es la especificación: la tubería, el formato de los paquetes, el router de Lua y lo
medido.

Plan aprobado: [PLAN-POLESTAR.md](PLAN-POLESTAR.md), secciones 6a y 6b.

## 1. Tubería

```
cliente Forever (CASC, solo lectura)
   │  senda-nav grid   (forge-navbuild de Polestar: ADT + WMO + M2 + agua -> rejilla fina multicapa)
   ▼
nav/out/grid/          rejilla fina: 256 columnas por ADT (2,08 yd), varias superficies por columna,
   │                   enlaces entre vecinas, caídas, ascensores (no se publica: 0,9 GB)
   │  senda-nav bake   (Senda: rejilla gruesa por capas + HPA* + paquetes)
   ▼
nav/out/SendaNav_<mapa>_graph.lua   grafo de sectores (HPA*), ascensores y teletransportes
nav/out/SendaNav_<mapa>_cells.lua   celdas de cada sector
nav/out/ref/<mapa>.bin.gz           referencia fina para el evaluador (no se publica)
   │  senda-nav eval / senda-nav-lua
   ▼
nav/eval/report.md, nav/eval/report-lua.md
```

Órdenes (desde `nav/`, con `cargo build --release`):

```sh
# 0. forever-db en .cache/foreverdb (python tools/fetch_foreverdb.py) y una copia de WoWDBDefs
#    (github.com/wowdev/WoWDBDefs: solo las definiciones de columnas, sin datos de Blizzard).
target/release/senda-nav prep --foreverdb ../.cache/foreverdb --out out/data
target/release/senda-nav grid --wow "E:/World of Warcraft" --product wowf --defs <WoWDBDefs> \
    --data out/data --out out/grid --continents 0,1          # ~5 min, 16 hilos
target/release/senda-nav bake --grid out/grid --out out --continents 0,1 --teleports data/teleports.json   # ~30 s
python -I eval/make_routes.py                                 # regenera eval/routes.json (opcional)
target/release/senda-nav eval --packs out --frames out/data --routes eval/routes.json --report eval/report.md
target/release/senda-nav-lua --packs out --frames out/data --routes eval/routes.json \
    --lua lua/SendaNavRouter.lua --report eval/report-lua.md --budget 1.5
```

Depuración: `senda-nav probe --packs out --map 0 --wx X --wy Y [--sz Z] [--tx X --ty Y --tz Z]` enseña las
celdas de alrededor y si hay camino; `SENDA_DUMP=<id de ruta> senda-nav eval ...` imprime la línea de una ruta y
`senda-nav zprof --grid out/grid --map 0 --file <volcado>` da, por cada punto del volcado, el área del trozo de terreno y
las superficies finas (z, banderas, pendiente) de su columna.

El planificador de viaje no usa estos paquetes sino un **grafo de andar** propio (`senda-nav bake ... --skip climb --block
data/walk_blocks.json` a `out/walk`, `senda-nav walkgraph` y `tools/walk_zones.py`, que quita los pasos entre zonas
sin camino con `zprof`): ver [TRAVEL.md](TRAVEL.md), «Andar». `--skip <clases>` deja
fuera enlaces finos de esas clases (`climb`, `steep`...) y `--block <fichero>` el suelo de unos polígonos revisados; sin
ellas el horneado es el de siempre.

### 1.1 Extracción (`grid`)

- **Fuente:** la instalación local de Forever (`E:/World of Warcraft`, producto `wowf`, build 1.60.1.70888),
  leída en solo lectura con el lector CASC/BLTE/DB2 de Polestar (`nav/crates/forge-gamedata`). Nada se descarga
  de internet salvo WoWDBDefs (definiciones de columnas, CC BY-SA 4.0 / BSD-3) y nada del cliente se publica.
- **Tablas del cliente:** Map, LiquidType, LiquidMaterial, LiquidObject, TransportAnimation, WMOAreaTable y
  AreaTable, leídas en esES (el cliente no trae enUS; es el único cambio sobre el código de Polestar).
- **Geometría:** `forge-navbuild` (Polestar, GPL-3) rasteriza triángulos de terreno, WMO (interior/exterior),
  M2 de colisión, MH2O y líquidos de WMO en columnas de 2,08 yd; por columna, superficies con altura y techo,
  enlaces a vecinas según pendiente (andar ≤ 50°, empinado ≤ 60°, trepar con escalón ≤ 1 yd, salto 1,6 yd),
  altura del personaje 1,6 yd, caídas seguras hasta 14,6 yd y ascensores (objetos de transporte de forever-db
  con su TransportAnimation). No es Recast/Detour: es una heightfield multicapa equivalente (voxelizado por
  columnas, filtro de altura libre y de escalón, regiones por componentes) y es lo que ya mide Polestar; la
  reutilizamos tal cual porque ya lee el cliente de Forever y su salida es determinista.
- **Medido:** Reinos del Este 736 ADT (55,3 M entradas, 31,8 M superficies andables) en 131 s; Kalimdor
  988 ADT (74,1 M entradas, 43,3 M superficies) en 171 s. Ascensores encontrados: en los Reinos del Este los tres de
  Entrañas, el «Vator» de Gnomeregan y los dos andamios del Caldero (Garganta de Fuego); en Kalimdor, 12
  «Mesa Elevator» (Cima del Trueno y Mil Agujas).

### 1.2 Horneado (`bake`)

1. **Suelo alcanzable.** Union-find sobre todas las superficies andables (sin `BLOCKED`, con algún enlace),
   unidas por sus enlaces a vecinas y por los ascensores. Se quitan antes el **terreno enterrado** bajo un
   suelo de WMO interior (el terreno bajo las calles de Ventormenta o bajo el suelo de una casa) y después los
   componentes de menos de 4000 superficies (~17 000 yd²: tejados, repisas, huecos dentro de rocas), salvo
   los que tocan un ascensor.
2. **Celdas gruesas por capas.** Cada bloque de 2×2 columnas finas es una celda de **4,17 yd** (128 por ADT).
   Las superficies conservadas del bloque unidas entre sí forman una **capa**; máximo 7 por celda (las mayores),
   ordenadas de abajo arriba. Clase de la capa: nado si todas sus superficies son agua, interior si alguna es
   interior, si no, andar. Altura: la media.
3. **Enlaces gruesos.** Un enlace fino que sale del bloque hacia el bloque vecino en una de las 8 direcciones
   enciende, en la capa de origen y esa dirección, el bit de la capa de destino (máscara de 7 bits).
4. **Sectores HPA\*.** 64×64 celdas (un cuarto de ADT, 267 yd). En cada lado de cada sector, los cruces
   (enlace de una celda del borde a una celda del sector vecino) forman tramos mientras sigan en el mismo suelo
   (la celda anterior enlaza con la siguiente a lo largo del borde); por tramo: 1 entrada si mide ≤ 16 celdas,
   2 (a un cuarto de cada extremo) si ≤ 48, 3 si más. Cada entrada crea un nodo a cada lado. Los extremos de
   ascensores y teletransportes también son nodos.
5. **Costes dentro del sector.** Dijkstra desde cada nodo, sin salir del sector: matriz n×n de yardas (dirigida).
   Coste de un paso: 4,17 yd (√2 en diagonal) × 3 si la celda de destino es agua.
6. **Componentes.** Componentes no dirigidos del grafo de nodos: si los nodos que alcanza el inicio y los que
   alcanzan la meta no comparten ninguno, la ruta no existe y se sabe sin buscar.
7. **Ascensores y teletransportes.** Ascensores de la rejilla fina, en ambos sentidos, coste 175 yd (25 s a
   7 yd/s, la cifra de Polestar). Teletransportes de un sentido desde `nav/data/teleports.json` (hoy los dos
   portales Darnassus ↔ Rut'theran, de `TravelData.lua` de Polestar), coste segundos × 7.

## 2. Coordenadas

Senda guarda puntos como `uiMapId` + porcentaje. La conversión usa los marcos de `ui_map.jsonl` de forever-db
(las tablas UiMap/UiMapAssignment del cliente de Forever, publicadas por Polestar, CC BY 4.0), con la misma
fórmula que `tools/foreverdb/db.py`:

```
mundo -> mapa:  x% = (wy - left) / (right - left) * 100      y% = (wx - top) / (bottom - top) * 100
mapa -> mundo:  wy = left + (right - left) * x% / 100       wx = top + (bottom - top) * y% / 100
mundo -> celda: gx = floor((32·ADT - wy) / CELL)            gy = floor((32·ADT - wx) / CELL)
celda -> mundo (centro): wx = 32·ADT - (gy + 0,5)·CELL      wy = 32·ADT - (gx + 0,5)·CELL
ADT = 1600/3 yd, CELL = ADT/128 = 4,1667 yd; wx = norte, wy = oeste (UnitPosition: y, x).
sector: sid = floor(gy/64)·128 + floor(gx/64); celda local k = (gy mod 64)·64 + (gx mod 64)
```

Los marcos son los de Forever, no los de Classic Era: Ventormenta (1453), Crestagrana (1433), Mulgore (1412) y
Tierras de la Peste del Este (1423) ya llevan sus límites propios (ver [FOREVER.md](FOREVER.md)); comprobado:
Gakin (forever-db, mundo −8983, 1041,5) sale en 39,22, 85,22 de Ventormenta, el valor de Forever.

## 3. Formato de los paquetes (versión 1)

Por continente (`map` = 0 Reinos del Este, 1 Kalimdor), dos ficheros Lua:

```lua
-- SendaNav_<map>_graph.lua
SendaNavData = SendaNavData or {}
local D = SendaNavData[<map>] or {}
SendaNavData[<map>] = D
D.v = 1; D.map = <map>; D.cell = 4.1666666667; D.sec = 64; D.swim = 3
D.G = { [sid] = "<base64(zlib(grafo del sector))>", ... }
D.L = { {ax, ay, ali, bx, by, bli, coste, unSentido(0|1), "nombre"}, ... }   -- ascensores y teletransportes
-- SendaNav_<map>_cells.lua
D.C = { [sid] = "<base64(zlib(celdas del sector))>", ... }
```

Cada blob se lee con `C_EncodingUtil.DecompressString(C_EncodingUtil.DecodeBase64(s), Enum.CompressionMethod.Zlib)`
y se recorre con `string.byte` (nada por celda en tablas). Enteros little-endian; índices desde 0.

**Celdas de un sector** (`D.C[sid]`):

| desplazamiento | tamaño | contenido |
|---|---|---|
| 0 | 1 | versión (1) |
| 1 | 4096 | capas de cada celda local k (0-7) |
| 4097 | 8·L | por capa (ordinal o, en orden de celdas y de capa) y dirección d = 0..7 (E, SE, S, SO, O, NO, N, NE; x al este, y al sur): máscara de capas de la celda vecina a las que enlaza (bit li; 0 = sin paso) |
| 4097 + 8L | L | clase por capa: 0 andar, 1 agua, 2 interior |
| 4097 + 9L | 2 por capa de celdas con 2+ capas | altura (int16, yardas), solo para elegir la capa con una z |

`L` = suma de las capas; el primer ordinal de cada celda es la suma de las capas de las anteriores.

**Grafo de un sector** (`D.G[sid]`):

| desplazamiento | tamaño | contenido |
|---|---|---|
| 0 | 1 | n nodos (≤ 255) |
| 1 + 6i | 6 | nodo i: celda local (u16), capa (u8), máscara de direcciones de cruce (u8), componente (u16) |
| 1 + 6n | 2·n² | coste de i a j en yardas (u16; 65535 = no se llega sin salir del sector) |
| 1 + 6n + 2n² | 2 | m cruces |
| … | 4·m | cruce: nodo origen (u8), dirección (u8), nodo destino en el sector vecino en esa dirección (u8), coste en décimas de yarda (u8) |

## 4. El router de Lua (`nav/lua/SendaNavRouter.lua`)

Implementación de referencia, probada en Lua 5.1 (sección 5). La llevará el coordinador al addon.

```lua
local job = SendaNavRouter.Find(map, { sx = wx, sy = wy, sz = z|nil, tx = wx, ty = wy, tz = z|nil },
    function(points, costOrReason, job) end)   -- points = { {x, y, lift = true|nil}, ... } en yardas de mundo
SendaNavRouter.Step(ms)    -- una vez por fotograma (OnUpdate), fuera de combate; por defecto 1,5 ms
SendaNavRouter.Cancel(job); SendaNavRouter.Busy(); SendaNavRouter.Idle()  -- Idle suelta lo decodificado
```

Razones de fallo: `nodata` (paquete no cargado), `offmesh` (ningún suelo a 8 celdas), `unreachable`
(componentes distintos o búsqueda agotada), `error: …`.

Algoritmo: (1) ajusta cada extremo a la celda con capas más cercana (la capa por z si hay varias y se conoce z;
si no, todas como orígenes); (2) Dijkstra en el sector del inicio hasta sus nodos y Dijkstra inverso en el de
la meta; (3) corta si no comparten componente; (4) A\* sobre los nodos (costes del sector, cruces, ascensores),
heurística octil admisible; (5) refina cada salto dentro de su sector con A\* sobre celdas; (6) estira la línea
(string pulling) con un trazado DDA que sigue las máscaras de capa, sin cruzar nunca un ascensor. Todo dentro de
una corrutina que cede cada 16 operaciones si el fotograma ya gastó su presupuesto; las decodificaciones también
ceden. Caché: 24 sectores de celdas (LRU) y los grafos que toque la búsqueda, hasta `Idle`.

Para el juego: cargar el paquete del continente del jugador bajo demanda, fuera de combate (`LoadOnDemand`), y
refinar solo los primeros saltos cerca del jugador (el banco de pruebas refina la ruta entera, el peor caso).

## 5. Medido (2026-11-12, este equipo)

Corpus: `nav/eval/routes.json`, 60 rutas (`make_routes.py`): entrada de las Minas de la Muerte desde la Colina
del Centinela, Dun Algaz y Thandol, túnel Dun Morogh–Loch Modan, puertas de Forjaz, ascensor de Gnomeregan,
Darnassus–Rut'theran, costa de Costa Oscura, canales de Ventormenta, puente de Crestagrana, Bosque del
Ocaso–Páramos de Poniente, Entrañas (ascensores, barrios), Mil Agujas (puentes, ascensor de Poste del Viento
Libre), ascensores y puentes de Cima del Trueno, Orgrimmar, Los Baldíos, Tanaris, rutas largas de continente y
9 rutas maestro de vuelo → objetivo de las guías de Senda. Extremos: PNJ de forever-db, puntos de las guías de
Senda y coordenadas (solo los hechos) del corpus de aceptación de Polestar.

| | Reinos del Este | Kalimdor |
|---|---|---|
| sectores / capas / nodos | 1924 / 7,35 M / 62 435 | 2652 / 9,95 M / 81 752 |
| ficheros (grafo + celdas) | 3,92 + 5,33 = 9,26 MB | 4,93 + 6,72 = 11,66 MB |
| memoria Lua del paquete cargado | 9,1 MB | 11,6 MB |

- **Evaluador en Rust** (`report.md`): 60/60 encontradas; **0** tramos de la línea fuera de los enlaces; 0,67 %
  de muestras (cada yarda) sobre columnas finas sin suelo alcanzable (sobre todo al rozar muros y esquinas); línea /
  recta: mediana 1,11; búsqueda abstracta: mediana 46 µs, máximo 2,1 ms.
- **Router de Lua 5.1** (`report-lua.md`, cada ruta en frío): 60/60; con `Step(1,5)`: percentil 99 del
  fotograma 2,08 ms, el más largo 3,1 ms (recolector de basura y decodificación); la ruta más larga
  (Lakeshire → Bahía del Botín, 6081 yd) son 180 fotogramas (≈ 3 s a 60 fps, 278 ms de CPU en total); las
  habituales (< 1500 yd) entre 5 y 40 fotogramas.
- **Memoria:** un continente cargado, 11,6 MB como máximo; con los dos y las cachés de una búsqueda larga,
  29,5 MB tras recolectar (las cachés suman hasta ~9 MB y `Idle` las suelta). En el juego solo se carga el
  continente del jugador: unos 21 MB como mucho (estimado: 11,6 + cachés), por debajo de los ~26 MB de Polestar.

## 6. Límites conocidos

- Las celdas gruesas (4,17 yd) pueden cerrar puertas de menos de ~3 yd que la rejilla fina sí abre, y la línea
  roza muros (0,67 % de las muestras caen en columnas finas sin suelo). Se nota en interiores pequeños.
- Máximo 7 capas por celda: en pilas de más pisos (zonas de Entrañas) se pierden las capas más pequeñas.
- Sin z del jugador, el inicio se ajusta a todas las capas de su celda: en una celda con varios pisos puede
  empezar en el piso equivocado si este también lleva a la meta.
- Los barcos, zepelines, tranvía y vuelos no son caminos a pie: son del planificador de viaje.
- Ríos y lagos se cruzan nadando (×3): no hay datos de profundidad para preferir puentes de otra forma.
- La validación compara contra la rejilla fina de referencia, no aún contra rastros grabados en el juego
  (plan 6b: ≤ 1,3 veces un paseo real): queda para cuando el grabador dé rastros.

## 7. Licencias y créditos

- `nav/crates/forge-gamedata`, `nav/crates/forge-navbuild` y `nav/crates/forge-core/src/jsnum.rs`: copiados de
  Polestar (https://github.com/fitzforge/polestar, commit 19bd636e, GPL-3.0-only, `nav/LICENSE-POLESTAR`); único
  cambio, el respaldo esES de las tablas en `forge-navbuild/src/build.rs`. Sus listas revisadas
  `geom/walkways.json` y `geom/openings.json` (puentes y puertas comprobados) vienen con ellos.
- `nav/data/teleports.json`: los dos portales de Darnassus, de `addon/Polestar/Nav/TravelData.lua` (GPL-3; sus
  datos de viaje llevan el aviso de Shortest Path Forever, de Cillian Berragan).
- `nav/eval/routes.json`: coordenadas tomadas como hechos de `tools/lib/nav/eval/acceptance.json` y `routes.json`
  de Polestar (GPL-3).
- Marcos de mapa y PNJ: forever-db (Polestar, CC BY 4.0). Definiciones de tablas: WoWDBDefs (CC BY-SA 4.0 /
  BSD-3), solo en la compilación.
- El resto de `nav/` (senda-nav, senda-nav-lua, el router de Lua) es de Senda, GPL-3.0.
- No se usa nada de los mapas de navegación de Leffe ni de los paquetes `Polestar_Nav_*` / `legs.json`.

## 8. En el juego: `Senda_Nav` (runtime)

Tres addons propios, sin dependencias de Senda ni entre ellos, todos `## Interface: 16001` y `## LoadOnDemand: 1`:

| addon | contenido | tamaño |
|---|---|---|
| `addon/Senda_Nav` | `Router.lua` (HPA\* por fotogramas, adaptado de `nav/lua/SendaNavRouter.lua`) y `SendaNav.lua` (API, coordenadas, conductor OnUpdate) | 35 KB |
| `addon/Senda_Nav_EK` | `SendaNav_0_graph.lua` + `SendaNav_0_cells.lua` (copiados de `nav/out/`) | 9,26 MB |
| `addon/Senda_Nav_Kalimdor` | `SendaNav_1_graph.lua` + `SendaNav_1_cells.lua` | 11,66 MB |

Al regenerar los paquetes (`senda-nav bake`) hay que volver a copiarlos de `nav/out/` a esas dos carpetas.

### 8.1 API (global `SendaNav`)

```lua
C_AddOns.LoadAddOn("Senda_Nav")                -- el que lo use (Senda) carga el runtime
SendaNav.Load(continente) -> ok, motivo         -- 0 | "EK" | 1 | "Kalimdor"; solo fuera de combate:
                                                --  en combate devuelve false, "combat" y carga al acabar
local job = SendaNav.Route(deMapa, dx, dy, aMapa, ax, ay, function(path, costeOMotivo, job) end [, opts])
SendaNav.Next(path, mapa, x, y [, z]) -> waypoint, índice, yardas, fueraDeRuta, llegado
SendaNav.Cancel(job); SendaNav.Busy(); SendaNav.IsLoaded(c); SendaNav.Unload(c)
SendaNav.ToWorld(mapa, x, y) -> continente, wx, wy;  SendaNav.ToMap(continente, wx, wy, mapas...) -> mapa, x, y
```

- Extremos y puntos en `uiMapId` + porcentaje (0-100), como Senda. `path[i] = { map, x, y, wx, wy, z?, lift }`
  más `path.continent`, `path.cost` (yardas de la búsqueda); el primero es el inicio; un punto con `lift`
  (nombre del ascensor o portal) es donde empieza el viaje y el siguiente, donde acaba. Cada punto lleva el
  mapa de destino o de origen si lo contiene; si no, el que da `C_Map.GetMapPosFromWorldPos`.
- `opts = { fz, tz }`: alturas de los extremos para elegir piso (la capa más cercana). Sin altura:
  `fhint` / `thint = "top"` (el piso más alto: fuera) o `"under"` (los que tienen otro encima: bajo techo), y
  `tnear = true` (sin `tz`, el piso de llegada más cercano a `fz`). Sin nada, todos los pisos de la celda
  (la búsqueda se queda con el más barato). Ver 8.6.
- Fallos (`callback(nil, motivo)`): `map` (mapa sin posición de mundo), `continent` (extremos en dos
  continentes: eso es del planificador de viaje), `nodata` (paquete sin cargar, p. ej. en combate),
  `offmesh`, `unreachable`, `error: …`. Los de entrada (`map`, `continent`, `nodata`) llaman al momento.
- Si el paquete no está cargado y no hay combate, `Route` lo carga (un tirón de ~40 ms medido aquí); lo
  normal es llamar a `Load` antes, al entrar en el continente.
- `Next` guarda el avance en `path.idx` y solo avanza: llega a un punto a `SendaNav.radius` (4 yd; con z
  en ambos lados, además a menos de 6 yd de altura), salta a un tramo posterior (hasta 6, nunca más allá de
  un viaje) si está más cerca, y en un tramo de viaje espera en su inicio. `fueraDeRuta` a más de
  `SendaNav.offRoute` (30 yd) del tramo: toca pedir otra ruta.
- `Unload(c)` suelta el paquete (`SendaNavData[c] = nil`); el cliente solo carga un addon una vez por
  sesión, así que después `Load(c)` responde `false, "unloaded"` hasta `/reload`. Por eso Senda (desde la 0.6.1)
  nunca llama a `Unload`: un paquete cargado se queda toda la sesión y cambiar de continente no pide `/reload`.

### 8.2 Coordenadas en el juego

Los marcos de cada `uiMapId` salen del propio cliente: `C_Map.GetWorldPosFromMapPos` en las esquinas
(0, 0) y (1, 1), una vez por mapa; luego la fórmula de la sección 2. Son las mismas tablas UiMap del cliente
que publica forever-db (`ui_map.jsonl`), así que el juego y las herramientas dan el mismo punto.

### 8.3 Tiempo por fotograma

Un marco con OnUpdate solo mientras hay trabajo: cada fotograma da a la búsqueda `SendaNav.budget` = 1,2 ms
(0,5 ms en combate, `combatBudget`). Las búsquedas se reparten en fotogramas con corrutinas; lo que no se puede
cortar se acota así:

- **Comprobación del reloj con peso** (`tick(w)`): cada expansión de celda pesa 1, cada expansión del grafo
  abstracto (lee hasta 255 costes) y cada bloque de 128 celdas al decodificar un sector pesan 16; el reloj se
  mira cada 16 unidades.
- **Decodificar empieza en fotograma nuevo**: antes de `DecodeBase64` + `DecompressString` (no se pueden
  partir) cede si lo que queda del fotograma no llega a lo que tardó la decodificación más lenta reciente.
- **Menos basura**: al salir un sector de la caché de celdas (24, LRU), sus tablas se reutilizan para el
  siguiente; el recolector da pasos más cortos.
- Tras `idleAfter` (30 s) sin búsquedas suelta todo lo decodificado y apaga el OnUpdate.

### 8.4 Validación sin cliente (`tests/navsim`)

`cd tests/navsim && cargo run --release -- [--budgets 1.0,1.5]` (Lua 5.1 oficial vía mlua; necesita
`nav/out/data/ui_map.jsonl` y, para las muestras finas, `nav/out/ref/`). Carga los tres addons como el cliente
(`C_AddOns.LoadAddOn` sobre cada .toc, simulado en `tests/navsim/wow.lua`), pide cada ruta de
`nav/eval/routes.json` con `SendaNav.Route` en frío, un fotograma cada vez con el OnUpdate del addon, y la
compara con la consulta del evaluador en Rust (`hpa.rs` y `pack.rs` compilados tal cual) sobre los mismos
ficheros publicados. Después sigue cada camino con `SendaNav.Next` (`walk.lua`). Escribe
`tests/navsim/report.md`; sale con error si falla una comprobación, una ruta o hay cruces.
`NAVSIM_TRACE=1` lista los fotogramas de más de 1,8 ms; `--only <id>` corre una ruta.

Medido (2026-11-12, este equipo, `tests/navsim/report.md`):

- 60/60 rutas, **mismo coste que Rust en las 60** (diferencia máxima 0,00 yd); **0** tramos fuera de los
  enlaces (`hpa::sight`); 0,65 % de muestras sobre columnas finas sin suelo (Rust: 0,67 %). Longitud de la
  línea Lua/Rust: mediana 1,000 (0,979-1,033). Las líneas pueden ir por caminos paralelos de igual coste
  (desempates y la mirada del estirado: 200 celdas en Lua, 400 en Rust): distancia máxima mediana 4 yd,
  máxima 101 yd.
- Fotograma completo (rebanada + decodificación + recolector), 2125 fotogramas: con 1,2 ms, mediana
  1,21 ms, p99 1,26 ms, **máximo 1,33 ms, ninguno por encima de 2 ms**; con 1,5 ms, máximo 1,74 ms; en
  combate (0,5 ms) máximo 1,14 ms. Antes de los tres cambios de 8.3 el router de referencia llegaba a
  3,1-3,9 ms. Fotogramas por ruta: la más larga (Lakeshire → Bahía del Botín, 6081 yd) unos 210 (3,5 s a
  60 fps); CPU total mediana por ruta 31 ms.
- Carga: el runtime 106 KB; Reinos del Este 31 ms y +9,1 MB; Kalimdor 37 ms y +11,6 MB (análisis de Lua en
  este intérprete; el cliente suma su lectura de disco). Tras una ruta, las cachés suman ~1 MB; el pico con
  basura, 35,5 MB con los dos continentes cargados; tras `Unload(0)`, 12,4 MB.
- `Next`: 60/60 caminos seguidos sin retroceder, sin quedarse atrás, sin falsos «fuera de ruta» y llegando;
  1,4 µs por llamada de media.
- No probado en el cliente real; las cifras de tiempo son de un procesador de escritorio.

### 8.5 En Senda: la flecha (`addon/Senda/UI/ArrowNav.lua`)

`UI/Arrow.lua` pregunta en cada medida a `Senda.ArrowNav:Waypoint(objetivo, mapa, x, y)`; si responde, la flecha
apunta a ese punto y la distancia es la que queda por el camino; si no, va recta como siempre.

- **Cuándo:** opción «Seguir caminos reales» (`navPaths`, activada por defecto) y objetivo en el continente del
  jugador (0 o 1). Nunca volando (`IsFlying`), en taxi (`UnitOnTaxi`) ni en instancias. En barco no hay API que lo
  diga: el barco va por agua lejos de la orilla, la ruta sale `offmesh` y la flecha va recta.
- **Carga:** `C_AddOns.LoadAddOn("Senda_Nav")` la primera vez que hace falta y, en otro fotograma,
  `SendaNav.Load(continente)`. **Nunca en combate**: se apunta y se carga con `PLAYER_REGEN_ENABLED`. Si
  `Senda_Nav` no está instalado o no carga, se intenta una vez por sesión y la flecha sigue recta.
- **Memoria:** un paquete cargado se queda cargado toda la sesión; al cambiar de continente no se suelta nada
  (Senda nunca llama a `SendaNav.Unload`). El cliente no vuelve a cargar un addon en la misma sesión: soltarlo
  obligaría a hacer `/reload` al volver a ese continente. Con los dos paquetes cargados son unos 21 MB; la
  memoria solo vuelve con `/reload` y la opción apagada (lo dice la ayuda de la opción).
- **Rutas:** una al cambiar el objetivo (mapa y coordenadas; el modo cadáver, que repite el mismo objetivo,
  no pide otra) y otra cuando `SendaNav.Next` dice «fuera de ruta», como mucho una cada 5 s. Mientras se
  calcula la primera, la flecha va recta; al recalcular sigue el camino anterior salvo a más de 120 yd de él.
  Una ruta que falla (`offmesh`, `unreachable`...) no se vuelve a pedir hasta pasados 20 s y 30 yd de
  movimiento. Las respuestas de rutas ya sustituidas se descartan.
- **En pantalla:** «120 m a pie · 1:05» (la distancia por el camino, `path.rest` + lo que queda hasta el
  punto) y la marca pequeña «ruta» junto a la flecha; la ayuda de la flecha dice «punto i de n» o «Calculando».
  En el último tramo, con menos de 5 yd de camino, la flecha deja el camino y apunta recta al objetivo
  («Línea recta», «fin del camino»): un objetivo fuera de la malla (sobre una roca, en un edificio sin datos)
  queda más allá del final del camino y apuntar a ese final daba «0 m» girando sobre uno mismo.
- **Llegada:** «Has llegado» exige estar dentro del radio en línea recta **y**, si hay camino hacia ese objetivo y
  el jugador va por él, que lo que queda de camino también quepa en el radio (el destino puede estar justo
  debajo, en una mina). Fuera del camino cuenta solo la línea recta. La llegada, el paso de un punto de ruta
  (`wps`) al siguiente y el borrado de los objetivos manuales los lleva un temporizador de 0,2 s
  (`Arrow:Tick`) que corre aunque la flecha esté oculta (opción apagada, oculta en combate o por las reglas de visibilidad).
- **Pisos:** ver 8.6.
- **Simulador:** `tests/wowsim/scenarios_nav.js` carga el `Senda_Nav` real (Router y SendaNav) en el
  simulador con paquetes sintéticos en el formato de la sección 3 (`tests/wowsim/mock/nav.lua`: un sector de
  64×64 celdas con un muro que obliga a rodearlo; base64 y zlib de verdad). Escenarios: ruta pedida y seguida
  punto a punto (`nav-route`), fuera de ruta con espera y cambio de objetivo (`nav-reroute`), combate que
  aplaza la carga y modo cadáver (`nav-combat`, mago humano), sin `Senda_Nav` (`nav-missing`), volando, en
  taxi, en instancia y sin ruta (`nav-fallback`), y cambio de continente con los dos paquetes cargados, sin
  `/reload` para volver (`nav-continent`, druida elfo de la noche). `tests/wowsim/scenarios_arrow.js`: pistas de
  piso, reintento sin ellas, llegada medida por el camino y final de camino (`arrow-floor`,
  `arrow-arrive-path`, `arrow-pathend`), y los objetivos y puntos de ruta de la flecha (`arrow-prio`,
  `arrow-wps`, `arrow-wps-reload`).

### 8.6 Pisos (celdas con varias capas)

Una celda de la malla puede tener varios pisos: la colina y la Mina Abisal de debajo, la cima de la montaña y
Forjaz dentro, las Ruinas de Lordaeron y Entrañas. `SendaNav.Route` escoge el piso de cada extremo con la altura
(`fz`, `tz`: la capa más cercana); sin altura sembraba **todos** los pisos de la celda de salida y aceptaba todos
los de la de llegada, y la búsqueda se quedaba con el más barato: desde el maestro de vuelo de Forjaz salía de
la cima (z 771 en vez de 502) en línea recta por la roca, desde las Ruinas salía bajo tierra, y hacia la Mina
Abisal acababa en la colina de encima (y la llegada en línea recta saltaba allí). `navsim` siempre pasaba la z
del corpus, así que no se veía.

El cliente no da la altura del jugador (`UnitPosition` devuelve 0 o nada), así que `UI/ArrowNav.lua` pasa lo que
sabe, en este orden:

1. **Salida:** la altura del cliente si la da (`Compat.PlayerZ`, un 0 exacto cuenta como desconocida); si no, la
   del camino que venía siguiendo (los puntos de un camino en celdas de varios pisos llevan `z`; se anota la del
   punto con altura a menos de 20 yd y vale mientras el jugador no se aleje 40 yd de donde se anotó); si no,
   `IsIndoors()` (`Compat.IsIndoors`): fuera, `fhint = "top"` (el piso más alto); bajo techo, `fhint = "under"`
   (los pisos que tienen otro encima). Sin nada de eso, todos.
2. **Llegada:** la `z` del objetivo (`tz`). Los pasos de guía la llevan desde `tools/build.py`: la del TOML del
   paso si alguien la escribió (`z`, esquema `section.schema.json`) o la de `data/heights.json`, una instantánea
   de las apariciones de forever-db (las mismas que dan las coordenadas): la z de la aparición más cercana del
   PNJ u objeto que el paso nombra (el `npc`, quien da o recibe la misión, o los objetivos de `complete` y quién
   suelta sus objetos), a menos de 25 yd (PNJ) o 50 yd (objetivos). Unos 4500 de los 6200 pasos con `at`. Se
   regenera con `python tools/build.py --refresh-heights`; `tools/validate.py` avisa de las filas cuyo `at` ya
   cambió (no se usan). Sin `tz`, con `tnear` y una altura de salida conocida, el piso de llegada más cercano a
   ella; si no, todos (el más barato).
3. **Reintento:** si con esas pistas la ruta sale `unreachable`, se pide otra sin ninguna.

`tests/navsim` comprueba los tres casos con los paquetes reales y sin alturas del corpus (`floor: ...` en las
comprobaciones de la API): Forjaz sale del piso 502 con `fhint = "under"`, las Ruinas salen de la superficie
(z 63) con `"top"` y llegan a Entrañas (z -43), y la Mina Abisal acaba dentro (z 23) con la altura del paso.

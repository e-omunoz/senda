# LOOKUP: de dónde sale cada objeto

Conjunto de datos `data/lookup/` y su generador `tools/gen_lookup.py`. Alimenta la línea de descripción
«Senda: lo suelta ... en ...» y el buscador de objetos (`/senda objeto`, pestaña «Objetos»; PLAN-POLESTAR 6b). Todo lo pesado se
calcula fuera del juego (principio 6a): en el juego solo hay Lua compacto, cargado bajo demanda.

## Fuentes y licencia

| Dato | Fuente | Licencia |
|---|---|---|
| Botín por PNJ y objeto, con probabilidad (`item_source`) | forever-db 2026.11.1 (cliente 1.60.1.70532) | GPL-3.0 (capa propia CC BY 4.0) |
| Objetos de recompensa y de objetivo de misión (`quest_reward`, `quest_objective`) | forever-db | ídem |
| Posición (`spawn`, `ui_map`) | forever-db; conversión a porcentaje de mapa con `tools/foreverdb/db.py` (adaptado de Polestar) | GPL-3.0 |
| Correcciones a mano (`corrections/items.json`: quitar y añadir botín) | forever-db | ídem |
| Vendedores (`v`) y lugar en la ruta (`g`) | pasos `buy`/`loot`/`use` de las guías de Senda que citan `polestar:` como fuente | GPL-3.0 |

Créditos de forever-db (EG Link, CMaNGOS classic-db, VMaNGOS/pfQuest, ForeverTDB, tablas del
cliente): ver `forever-db/NOTICE.md` y `THIRD_PARTY.md`. Cada fichero generado lleva en `meta` la
versión de forever-db y la compilación del cliente.

Lo que **no** entra: nada de Leffe (mapas, tramos), nada de DingDB, AtlasLoot, RareScanner ni Diario de
mazmorras, ningún dato de QuestieDB. Los pasos de guía que solo citan `questie:` no generan filas
(hoy: 3 `buy`, 3 `accept`, 4 `complete`).

## Esquema

`data/lookup/items.json`: `{meta, items: {itemId: entrada}}` y la entrada puede tener:

| Clave | Significado |
|---|---|
| `s` | botín: `[["n"\|"o"\|"i", id, probabilidad%?], ...]` (PNJ, objeto, objeto contenedor). Hasta 8, la mejor probabilidad primero |
| `n` | total real de fuentes si se cortó la lista (el objeto 159 tiene 257) |
| `v` | vendedores: `[[npcId], ...]` (solo los de las guías con fuente Polestar) |
| `g` | sin PNJ conocido: `[[uiMap, x%, y%], ...]` el sitio donde la guía recoge/usa el objeto (máx. 2) |
| `q` | recompensa de misión: `[[questId, 1 si es a elegir], ...]` (hasta 6; `nq` = total) |
| `o` | solo un enlace: `[questId, ...]` misiones que lo piden como objetivo, cuando no hay nada mejor (hasta 3; `no` = total) |

`data/lookup/places.json`: `{meta, places: {n: {npcId: lugar}, o: {objectId: lugar}}}` con
`lugar = [uiMap, x%, y%, mapId, nSpawns]`. Es **un** punto representativo: el spawn más cercano al
centroide en el mapa donde más aparece (un punto real, nunca una media dentro de una pared).
`uiMap = 0` significa sin marco de mapa (mazmorra): x e y en yardas del mundo. `mapId = -1` es un
vendedor sin spawn cuyo sitio sale de un paso de guía. Los nombres no se guardan: los pone el cliente
(6c, `{npc:id}` / `C_Item`).

`data/lookup/coverage.json`: cobertura medida y lista de fallos (regenerada con cada ejecución).

`data/lookup/locale/<idioma>/items.json`: nombres de los objetos del buscador (formato de `tools/localenames.py`, con la fuente de cada nombre): `forever-db` en inglés (de `gen_lookup.py`) y `ingame:<build>:<fecha>` (de `/senda volcar` + `import_names.py`).

## Reproducir

```
python -I tools/gen_lookup.py [--foreverdb DIR] [--out DIR] [--check]
```

forever-db: `--foreverdb`, o la variable `SENDA_FOREVERDB`, o `.cache/foreverdb`
(`tools/fetch_foreverdb.py`). Es determinista para la misma forever-db y las mismas guías (la cobertura
depende de las guías: cambia cuando se editan). `--check` sale con error si la cobertura es < 95%.

## Tamaños (forever-db 2026.11.1)

5.623 objetos: 1.775 con botín, 2.305 con recompensa de misión, 20 con vendedor, 33 con lugar de
ruta, 1.519 solo con enlace de objetivo. Botín: 5.056 filas de PNJ y 696 de objeto.

| Fichero | JSON | gzip |
|---|---|---|
| items.json | 207 KB | 52 KB |
| places.json | 68 KB | 22 KB |

Compilado a Lua será del orden de 150-200 KB en total (dentro del 0,3-0,5 MB previsto para el buscador).
Faltan lugares para 582 PNJ y 98 objetos de botín que forever-db no tiene en `spawn`: sus objetos
salen igual, solo que sin coordenada.

## Cobertura medida (guías de `data/guides` y `data/shared`: 430 ficheros, 2.277 misiones, 2.420 objetos)

Objetos considerados: los `item =` de los pasos, los objetos de objetivo y los de recompensa de las
misiones que usan las guías.

| Conjunto | Con fuente real | % |
|---|---|---|
| Recompensas de misión | 992 / 992 | 100 |
| `item =` de los pasos | 129 / 136 | 94,9 |
| Objetos de objetivo | 804 / 1.384 | 58,1 |
| **Todos** | **1.836 / 2.420** | **75,9** |
| Todos, contando el enlace «objetivo de la misión X» | 2.416 / 2.420 | 99,8 |

**El objetivo del plan (>= 95% con fuente real) no se cumple: 75,9%.** No lo he forzado. El hueco son
584 objetos de objetivo para los que forever-db no tiene ninguna fuente de verdad. Por qué, según las
mecánicas que forever-db anota en esas misiones:

- 433 no tienen mecánica anotada: casi todo son cartas, documentos y paquetes que te da el
  que da la misión al aceptarla («Documentos del Mariscal McBride», «Carta de Verner»). forever-db no
  registra los objetos entregados al aceptar, así que no se puede afirmar con datos.
- ~74 con «object-click» (se recogen de un objeto del mundo que forever-db no enlaza al objeto),
  ~20 de grupo/élite, ~26 de fabricación o compra (`crafted`, `vendor-buy`) y el resto de uso/temporizadas.
- Los vendedores no existen en forever-db (solo `removeVendors` en sus correcciones). Los 20 vendedores
  que hay vienen de pasos `buy` de las guías.

Por eso la línea de tooltip tiene dos niveles y el generador mide los dos por separado: **nivel 1**,
fuente real (botín, objeto, vendedor, recompensa, lugar de ruta); **nivel 2**, «Objetivo de «misión»»
(real, pero no dice dónde conseguirlo). Nunca se mezclan en el porcentaje del nivel 1.

Cómo cerrar el hueco con datos reales, no con suposiciones (todo en otros paquetes, sin tocar este):
1. Vendedores y objetos entregados al aceptar: `/senda volcar` o el Grabador leen en el juego los
   vendedores abiertos (`GetMerchantItemLink`) y lo que entra al aceptar; una herramienta los pasa a
   `data/lookup/`. Datos verificados en el juego.
2. Las 74 de objeto: cruzar con los objetivos `object` de la misma misión cuando solo hay uno
   (pendiente; sería inferencia y se marcaría como tal).
3. Recetas y fabricación: tablas del cliente (SkillLineAbility) vía wago.tools.

### Fallos del nivel 1 + 2 (4 objetos sin ninguna línea)

15826 Curative Animal Salve, 15844 Empty Cliffspring Falls Sampler, 17031 Rune of Teleportation,
22432 Devilsaur Barb. La lista completa de fallos del nivel 1 (584) está en `coverage.json`
(`any_source.all.misses`, con nombre en inglés de forever-db).

## Diseño dentro del juego (implementado)

Objetivos: ninguna espera, consulta < 2 ms por fotograma, memoria solo mientras se usa. Código:
`addon/Senda/Modules/Lookup.lua` (datos, línea de descripción, `/senda objeto`, «Señalar», búsqueda),
`addon/Senda/UI/LookupTab.lua` (pestaña «Objetos») y la parte de objetos de `Core/NamesDump.lua`.

**Paquete bajo demanda.** Addon aparte `Senda_Lookup` (`LoadOnDemand: 1`), generado por `tools/build.py` desde
`data/lookup/` (`Items.lua`, `Places.lua`, `Names_<idioma>.lua` y el `.toc` que los lista; el zip y `install-dev`
llevan ya cinco carpetas). No se carga al arrancar: `Lookup.Load()` llama a `C_AddOns.LoadAddOn` la primera vez que
se mira un objeto o se busca, siempre fuera de combate (`InCombatLockdown()`): en combate la línea simplemente no
sale y el comando avisa. Son ~0,4 MB de Lua (180 KB de objetos, 87 KB de lugares, 156 KB de nombres): unos
milisegundos, una sola vez por sesión. Si faltara la carpeta, todo se apaga sin error («Falta la carpeta
Senda_Lookup»).

**Formato compacto.** Una cadena por objeto, desempaquetada solo al consultarlo (caché de 200 entradas):

```
Senda_Lookup.items  = { [159] = "s=n3577:100,o3658:100,n3141:10.4;N=257;v=6736;q=8c,381;Q=7", ... }
Senda_Lookup.places = { n = { [3577] = "1421,62.6,65,0,1" }, o = { ... } }   -- uiMapa,x%,y%,mapa,apariciones
Senda_Lookup.names  = { enUS = "159\tRefreshing Spring Water\n...", esES = "..." }
```

Campos: `s` botín (`n` PNJ, `o` objeto del mundo, `i` objeto contenedor, `:probabilidad`), `N` total real de fuentes,
`v` vendedores, `g` sitio de la ruta (`mapa:x:y`), `q` recompensa de misión (`c` = a elegir) y `Q` total, `o`
objetivo de misión y `O` total. Los nombres son una cadena por idioma (lo de forever-db en inglés, lo que da el
cliente en el idioma del jugador): al cargar se registran como respaldo de `{item:N}` en `Senda.Names` y el addon
no guarda otra copia.

**Línea de la descripción** (`TooltipDataProcessor.AddTooltipPostCall` sobre objetos, `GameTooltip` e
`ItemRefTooltip`; opción «Decir en la descripción de los objetos de dónde salen», activada, sección Objetos). Una
sola línea, de verde Senda, con fichas que resuelve `Senda.Names`; una sola fuente, la mejor:

```
Senda: lo sueltan {npc:1211} (80%) y {npc:8503} (80%) en {map:1426}   botín de PNJ; los de tu zona primero (+N más)
Senda: se saca de un objeto del mundo en {map:1426}                     objeto del mundo (el cliente no los nombra por id)
Senda: sale de {item:159}                                               objeto contenedor
Senda: lo vende {npc:1247} en {map:1426}                                vendedor (de los pasos «buy» de las guías)
Senda: recógelo en {map:1446}                                           sitio de la ruta donde la guía lo recoge
Senda: recompensa de {quest:46}                                         recompensa de misión
Senda: para {quest:3181}                                                objetivo de misión (nivel 2: real, no dice dónde)
```

Orden de preferencia: botín de PNJ > objeto del mundo > contenedor > vendedor > sitio de la ruta > recompensa >
objetivo. Si el nombre de un PNJ o misión aún no está en caché, sale «PNJ #N» y se pide al cliente; cuando llega
(`SENDA_NAMES_UPDATED`) la descripción que se está viendo se rehace una vez (`RefreshData`). Una mazmorra (`uiMapa`
0) dice «en una mazmorra». No se promete lo que forever-db no da: sin `%` si no hay dato.

**`/senda objeto <nombre, número o enlace>`** busca y, si hay un único resultado o un nombre exacto, enseña de dónde
sale (botín con zona y probabilidad, objetos del mundo, contenedor, vendedores, sitio de la ruta, recompensas y
objetivos); si hay varios, lista hasta 8 y pide el número. `/senda objeto señalar <objeto>` (sin objeto, el último
mirado) apunta la flecha a la fuente más cercana; `/senda objeto borrar` la quita. La pestaña «Objetos» del panel
hace lo mismo con una caja de búsqueda (busca sola al dejar de escribir 0,4 s), una lista con «Señalar» por fila y
el detalle debajo.

**Fuente más cercana.** Entre las fuentes con sitio en un mapa real (botín de PNJ y de objeto, vendedores, sitio de
la ruta; los contenedores cuentan por los PNJ que los sueltan) se elige la de menor distancia en yardas
(`Compat.WorldDistance`) desde el jugador. Si ninguna es medible (otro continente, sin posición) se queda la
primera, la de mejor probabilidad, y el planificador de viaje de la flecha se encarga del camino. Las mazmorras
(`uiMapa` 0) no se pueden señalar y lo dice; lo que solo es recompensa u objetivo de misión no tiene sitio que
señalar. La fuente de la flecha es `lookup`: va por delante de la guía y por detrás de un punto manual y del
cadáver; al llegar se quita sola como los demás.

**Búsqueda.** Nada se construye hasta la primera búsqueda. Entonces una corrutina, a razón de 500 operaciones o
1,5 ms por fotograma (en combate espera), recorre los nombres compilados (`Senda.Names:PackStrings("item")`) y
arma el índice: por objeto, sus nombres normalizados (minúsculas, sin tildes) del cliente (solo los que ya tiene en
caché: `C_Item.IsItemDataCachedByID`), del volcado (`SendaNamesDB`) y del respaldo en el idioma del cliente y en
inglés, de modo que «canon» encuentra «Cañón» y se puede buscar en inglés. Coinciden los objetos cuyo nombre contiene
todas las palabras; se ordena por exacto, empieza por, palabra que empieza y contiene, luego por número, y se
devuelven 20. El índice se suelta a los 90 s sin buscar. Una búsqueda nueva sustituye a la anterior.

**Nombres del juego para el buscador.** forever-db da el nombre en inglés de 5.606 de los 5.623 objetos
(`data/lookup/locale/enUS/items.json`, fuente `forever-db`, la prioridad más baja). Para tener los nombres reales en
tu idioma, `/senda volcar` apunta en `SendaNamesDB.locales.<idioma>.litem` los objetos del buscador (los que no
usan las guías) que el cliente **ya tiene en caché**: no pide nada al servidor. `/senda volcar objetos` pide además
los que faltan, al ritmo de siempre (20 por fotograma, 40 a la vez, parado en combate). `tools/import_names.py` lee
`litem` y lo escribe en `data/lookup/locale/<idioma>/items.json` con fuente `ingame:<build>:<fecha>` (lo de las
guías sigue yendo a `data/locale/`), e informa de la cobertura de nombres del buscador en ese idioma;
`tools/build.py` compila ambos en `addon/Senda_Lookup/Names_<idioma>.lua`. Nada de QuestieDB entra en este camino.
Para poner los nombres en inglés de forever-db a objetos nuevos sin regenerar todo:
`python -I tools/gen_lookup.py --names-only`.

**Qué no hace.** No promete probabilidades que forever-db no da (sin `%` si no hay dato); no muestra el
botín con probabilidad 0; no mezcla nivel 1 y 2 en la misma línea; no pide al servidor los nombres de 5.600
objetos por su cuenta (solo con `/senda volcar objetos`); no tiene todos los spawns (un punto representativo por
fuente, ver «Esquema»).

## Validación

- `python -I tools/gen_lookup.py --check` falla si la cobertura baja de 95%. Hoy falla (75,9%) y el
  motivo está documentado arriba; no se ha rebajado el criterio.
- Comprobado a mano: 159 (agua), 5359 y 20519 (las correcciones de forever-db quitan 2 fuentes erróneas),
  254432 (13 fuentes añadidas), 2894 (Malta rapsódica: vendedor Belm 1247 con lugar de guía).
- Pendiente para el simulador: 20 objetos conocidos (PLAN 6b) y 10 monturas/mascotas en el juego
  (estas dos últimas no están en este paquete: necesitan las tablas del cliente).

## Reutilizado

- forever-db 2026.11.1 completo (lectura): `item_source`, `quest_reward`, `quest_objective`, `spawn`,
  `ui_map`, `item`, `quest`, `corrections/items.json`. GPL-3.0, créditos arriba.
- `tools/foreverdb/db.py` de Senda (`Frames`, `read_jsonl`, `resolve_foreverdb`), adaptado de Polestar.

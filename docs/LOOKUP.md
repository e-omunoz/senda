# LOOKUP: de dónde sale cada objeto

Conjunto de datos `data/lookup/` y su generador `tools/gen_lookup.py`. Alimenta la línea de tooltip
«Se consigue en: ...» y, más adelante, el buscador de objetos (PLAN-POLESTAR 6b). Todo lo pesado se
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

## Diseño dentro del juego

Objetivos: ninguna espera, consulta < 2 ms por fotograma, memoria solo mientras se usa.

**Paquete bajo demanda.** Addon aparte `Senda_Lookup` (`LoadOnDemand: 1` en el `.toc`), que no se
carga al arrancar. Se carga con `C_AddOns.LoadAddOn` la primera vez que se pide, siempre fuera de
combate (`InCombatLockdown()`); en combate la línea simplemente no aparece y se reintenta al salir.
Es un único fichero porque 200 KB de Lua tardan unos milisegundos en analizarse; si el tamaño crece, se
parte por rango de id (`itemId // 4096`) y cada trozo se carga al primer uso.

**Formato compacto.** Una cadena por objeto, analizada solo al consultar y guardada en una caché pequeña:

```
Senda_Lookup_Items = { [159] = "n3577:100,n3662:100,o3658:100|v6736|q8c", ... }
Senda_Lookup_Places = { n = { [3577] = "1429,52.4,61.2" }, o = { ... } }
```

Claves del trozo: `n`/`o`/`i` + id + `:` + prob.; `v` vendedores; `g` lugar de ruta; `q` recompensa
(`c` = a elegir); `o` objetivo. Solo se desempaqueta la entrada pedida; nada de tablas anidadas para
5.600 objetos al cargar.

**Tooltip.** Gancho `TooltipDataProcessor.AddTooltipPostCall(Enum.TooltipDataType.Item, fn)`:
lee el id del objeto, busca la entrada y añade **una sola** línea (o dos con Mayús pulsado):

```
Se consigue en: Cerdo Jabalí 12%, Grunt Rotacuernos 8% (+3)   -- botín: mejor probabilidad primero
Se consigue en: comprado a Belm, Tabernero (Dun Morogh)       -- vendedor
Se consigue en: recompensa de «Costillas para Ragnar»         -- misión
Objetivo de «Costillas para Ragnar»                           -- nivel 2
```

Los nombres salen del cliente (`C_QuestLog.GetTitleForQuestID`, tooltip de criatura por id; si no están
en caché se piden y la línea se refresca al llegar), el sitio de `C_Map.GetMapInfo(uiMap).name`. Solo se
muestran fuentes de la zona del jugador primero y la facción correcta; el resto, tras «+N». Se
limita a una vez por objeto y tooltip y se salta si la línea ya está.

**Buscador (`/senda buscar <objeto>`).** La misma tabla al revés (nombre -> id) se construye bajo
demanda, repartida en varios fotogramas con una corrutina. Al elegir una fuente, la flecha apunta a su
lugar (`places`), con el mismo punto representativo; ese punto puede no ser el PNJ más cercano al
jugador, por eso se muestran todos los spawns solo en el mapa de zona cuando se amplíe el paquete.

**Qué no hace.** No promete probabilidades que forever-db no da (sin `%` si no hay dato); no muestra el
botín con probabilidad 0; no mezcla nivel 1 y 2 en la misma línea.

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

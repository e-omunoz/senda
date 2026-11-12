# Alertas de raros: datos y diseño de detección

Estado: dataset generado, detección sin implementar. Este documento fija los datos (`data/rares/`),
cómo se generan (`tools/gen_rares.py`) y el diseño de detección en el juego, adaptado de la lógica de
Polestar (GPL-3). Corresponde a la fila «Alertas de raros» de `docs/PLAN-POLESTAR.md` 6b.

## 1. Datos

### Fuente y licencia

- **forever-db** (datos de Polestar para WoW: Forever), versión `2026.11.1`, cliente `1.60.1.70532`,
  commit del productor `6d0de256e66674512e453a2990076d84f7e979bb`. Tablas usadas: `npc`, `spawn`, `ui_map`.
- Licencia: GPL-3.0-only para las tablas y CC BY 4.0 para la capa propia de forever-db (ver su `NOTICE.md`
  y `THIRD_PARTY.md`). Senda es GPL-3: compatible.
- La conversión de yardas del mundo a `[uiMapId, x%, y%]` usa `tools/foreverdb` (`Frames`), que a su vez
  adapta `lib.ToUiMap` de Polestar. No se usa ningún dato de Leffe, DingDB, AtlasLoot, RareScanner,
  DungeonJournal ni QuestieDB.
- Todo dato recibe su procedencia en `data/rares/meta.json` (dataset, versión, build, commit).

### Regeneración

```
python tools/gen_rares.py [--foreverdb RUTA] [--out data/rares]
```

Sin `--foreverdb` usa `SENDA_FOREVERDB` o `.cache/foreverdb`. Solo lee forever-db. Es reproducible (dos
ejecuciones dan los mismos bytes) e imprime los recuentos.

### Ficheros

| Fichero | Contenido |
|---|---|
| `data/rares/rares.json` | Lista plana, ordenada por id. Un objeto por raro. |
| `data/rares/by_zone.json` | `uimapId -> { name, bands: { "21-30": [ids] } }`, solo raros con aparición. |
| `data/rares/no_spawns.json` | Raros sin aparición conocida (id, nombre, rango, nivel). |
| `data/rares/meta.json` | Fuente, versión, recuentos y métricas. |

Esquema de `rares.json`:

```
{ "id": 5851, "name": "Captain Gerogg Hammertoe", "rank": "rare" | "rareelite",
  "level": [min, max], "faction_template": 35, "map": 0|1|<otro>|null, "uimap": 1426|null,
  "spawns": [[uiMapId, x, y], ...], "spawns_unframed": n (opcional), "subname": "..." (opcional) }
```

- `rank`: forever-db `npc.rank` 4 (raro) o 2 (raro élite). Los de rango 1 (élite) y 3 (jefe) no entran.
- `name`: nombre en inglés de forever-db. El nombre en español sale del cliente en el juego
  (`UnitName` / viñeta), igual que el resto de fichas (plan 6c).
- `map`: mapa del cliente donde aparece (0 Reinos del Este, 1 Kalimdor, otro id si es una instancia o un
  mapa propio de Forever). `uimap`: zona con más puntos.
- `spawns`: puntos deduplicados con una décima de precisión (x, y en % del mapa de la zona). Un punto
  elegido por `Frames.to_uimap`, que elige el marco de zona donde el punto cae más cerca del centro; esto
  coincide con la zona real el 88% de las veces (medido en `tools/foreverdb/db.py` contra QuestieDB), así
  que en un borde de zona un punto puede caer en la zona vecina. La detección por viñeta no depende de
  esto (la posición la da el cliente); solo lo usa la vista de mapa.
- Nivel: forever-db da mínimo y máximo. Ocho raros traen nivel 1 (marcador o nivel escalado: Priestess of Elune,
  Gash'nak the Cannibal, Ushalac the Gloomdweller, Rezrelek, Tatterhide, Lumbering Horror, Snapbeak the Quick,
  Coldrasp); no se corrige, se avisa con el nivel que da el cliente al verlo.
- Amistad de facción: **no disponible**. forever-db solo trae `faction_template` (id del cliente) y
  Senda no tiene fuente de la tabla FactionTemplate; no se inventa. `faction_template` se guarda en bruto,
  para que una futura tabla verificada en el juego (`/senda volcar`) o de wago.tools lo resuelva. Mientras
  tanto, ningún raro se filtra por facción: el aviso es útil aunque el raro sea hostil o neutral.
- Banda de nivel: tramos de 10 por el nivel máximo (1-10, 11-20, ..., 61-70), solo en `by_zone.json`.

### Métricas (versión 2026.11.1)

| Métrica | Valor |
|---|---|
| Raros totales | 411 (276 raros, 135 raros élite) |
| Con aparición conocida | 346 (84,2%) |
| Sin aparición | 65 (12 raros, 53 raros élite) |
| Puntos de aparición | 964 |
| Zonas (uiMap) con raros | 43 |

Por continente (mapa del cliente de la primera aparición):

| Continente | Raros | Con aparición |
|---|---|---|
| Reinos del Este (mapa 0) | 178 | 178 |
| Kalimdor (mapa 1) | 165 | 165 |
| Otros mapas del cliente | 68 | 3 |

Los 3 «otros» con aparición están en el mapa 2991 / uiMap 2521 (un mapa propio de Forever: Tel'daeor the
Stormspeaker 259385, Mystmane 259388, Snapbeak the Quick 259394). Los 65 restantes no tienen ni una fila en `spawn` (ninguno con `spawns_unframed`): mayoritariamente élites
que forever-db no ubica (por nombre, muchos parecen de mazmorra o de evento; no se ha comprobado mazmorra por
mazmorra) y 6 con nivel 1 como marcador. Para los 346 con aparición se cumple el
objetivo del plan (346 de 411).

Por zona y banda: ver `data/rares/by_zone.json`. Las más pobladas son Los Baldíos (27), Vallefresno (14),
Marjal Revolcafango (14), Claros de Tirisfal (13), Páramos de Poniente (12), Feralas (12), Tanaris (12) y
Las Estepas Ardientes (12). Dos uiMap (2521 y 2548) son mapas propios de Forever y no tienen nombre en
`tools/site.py`; salen como «mapa <id>».

### Validación

- Recuentos por rango contra el esquema de forever-db: 276 + 135 = 411, igual que el plan.
- Todo punto convertido cae dentro de [0, 100] en un marco del `ui_map` de forever-db (lo garantiza
  `Frames.all`).
- Reproducibilidad: dos ejecuciones seguidas dan ficheros idénticos.
- Pendiente (necesita el juego): 5 raros conocidos comprobados en el cliente (Mother Fang, Thuros Lightfingers...).

### Raros sin aparición conocida (65)

Mother Fang (471, Elwynn) y Thuros Lightfingers (61, Elwynn) no están aquí: sí tienen aparición.

Raros (12): Dreadwhisper 1849, Dreamwatcher Forktongue 5348, Wep 10236, Yor 10237, Staggon 10238,
Death Knight Soulbearer 10818, Duke Ragereaver 10820, Kelemis the Lifeless 11580, Felendor the Accuser 14341,
Lumbering Horror 14697, Spirit of the Damned 16379, Bone Witch 16380.

Raros élite (53): Capo the Mean 601, Edwin VanCleef 639, Bruegal Ironknuckle 1720, Miner Johnson 3586,
Deathsworn Captain 3872, Blind Hunter 4425, Razorfen Spearhide 4438, Earthcaller Halmgar 4842,
Scillia Daggerquil 5367, Serra Mountainhome 5789, Lizzle Sprysprocket 5790, Captain Armistice 5793,
Thurmonde the Devout 5794, Grash Thunderbrew 5795, Ben 5796, Deviate Faerie Dragon 5912,
Dark Iron Ambassador 6228, Fallen Champion 6488, Ironspine 6489, Azshir the Sleepless 6490,
Soul of Tanaris 8206, Panzor the Invincible 8923, Pyromancer Loregrain 9024, Lord Roccor 9025,
Warder Stilgiss 9041, Verek 9042, Spirestone Lord Magus 9217, Spirestone Battle Lord 9218,
Spirestone Butcher 9219, Sleeping Dragon 9417, Bannok Grimaxe 9596, Ghok Bashguud 9718,
Quartermaster Zigris 9736, Sandarr Dunereaver 10080, Dustwraith 10081, Zerillis 10082, Berylgos 10203,
Tepolar 10239, Burning Felguard 10263, Crystal Fang 10376, Skul 10393, Jed Runewatcher 10509,
Hearthsinger Forresten 10558, Urok Doomhowl 10584, Timmy the Cruel 10808, Stonespine 10809,
Meshlok the Harvester 12237, Priestess of Elune 12116, Gash'nak the Cannibal 13977,
Ushalac the Gloomdweller 14016, Rezrelek 14018, Tatterhide 14019, Sandworm 17075.

(La lista completa y siempre al día está en `data/rares/no_spawns.json`.)

## 2. Diseño de detección en Senda

Adaptado de `addon/Polestar/Rares/Detect.lua` y `Rares.lua` (GPL-3, Polestar). Si se copia código, se
mantiene el aviso de copyright y se anota en `THIRD_PARTY.md`. Idea central: **gastar solo lo que el
cliente entrega ya hecho** (cargas de eventos), nada de recorrer listas por fotograma.

### Caminos de detección

Cada camino es un ajuste independiente; si está apagado no se registra su evento.

1. **Viñetas del minimapa** (camino principal): `VIGNETTE_MINIMAP_UPDATED(vignetteGUID, onMinimap)` y
   `VIGNETTES_UPDATED`. Con `C_VignetteInfo.GetVignetteInfo(guid)` se leen `objectGUID`, `name`, `isDead`,
   `onMinimap`. Un GUID `Creature-` / `Vehicle-` es un raro (por palabra del cliente); `GameObject-` es un
   tesoro y no entra en este alcance. Posición: `C_VignetteInfo.GetVignettePosition(guid, uiMapId)` (x, y
   en 0-1), probando el mapa del jugador y hasta 3 mapas padre (una subzona puede no tenerla y la zona sí).
2. **Placas de nombre:** `NAME_PLATE_UNIT_ADDED(unit)` con `UnitClassification(unit)` igual a `rare` o
   `rareelite`.
3. **Objetivo y ratón encima:** `PLAYER_TARGET_CHANGED` y `UPDATE_MOUSEOVER_UNIT`, con la misma
   clasificación.
4. En 2-3, un id que está en `data/rares/` también cuenta aunque la clasificación no lo diga. El id sale del
   GUID: `Creature-0-<server>-<map>-<instance>-<npcId>-<spawn>`, séptimo campo.

Excluir siempre: jugadores y unidades controladas por jugadores (`UnitIsPlayer`,
`UnitPlayerControlled`), instancias (`IsInInstance`, también bandas de PvP), y los ids ignorados por el
usuario.

### Valores secretos

El cliente puede devolver valores «secretos» (`GUID`, nombre, tipo) cuando la identidad está restringida.
Se envuelve cada lectura en un `readable()` (en `Compat`): un valor secreto equivale a desconocido y la
unidad se salta. Todo `C_VignetteInfo.*` va en `pcall`.

### Rebote (debounce)

- Una unidad o viñeta se mira **una vez por GUID cada 3 s** (`DEBOUNCE`), salvo la transición confirmada
  vivo a muerto, que se deja pasar.
- Tabla `recent[guid] = hora`; se barre cuando pasa de 200 entradas (se borran las de más de 3 s).
- El barrido completo de viñetas (`GetVignettes`) como mucho cada **2 s** (`SCAN_EVERY`, un temporizador
  `C_Timer.After`), y nunca en combate. Se vuelve a pedir tras `PLAYER_ENTERING_WORLD` y
  `PLAYER_REGEN_ENABLED`.

### Decisión (pura, comprobable)

`Decide(sighting, ctx) -> accion, motivo`, con `accion` en `alert | hold | record | skip`:

1. `skip` si está apagado, en instancia, camino apagado, es jugador, id ignorado, o no es raro (en placas,
   objetivo y ratón hace falta clasificación de raro o id conocido).
2. `record` (se anota en el historial, sin aviso) si está muerto, si los avisos están apagados, o si ese
   raro ya se avisó hace menos del **enfriamiento** (por defecto 10 min por raro).
3. `hold` si estás en combate y `combatAlerts` está apagado (por defecto).
4. `alert` en cualquier otro caso.

La clave del historial es `rare:<npcId>`, o `name:<nombre>` cuando no hay id legible.

### Retención en combate (combat hold)

- En combate no se muestra nada ni se pesa nada: el aviso queda en `held` (solo el último).
- En `PLAYER_REGEN_ENABLED` se llama a `Release()`: si el aviso tiene menos de **60 s** (`HOLD_FOR`) y
  `Decide` sigue dando `alert` con el contexto de ese momento (puede haber muerto, enfriarse, o haber
  pasado a instancia), se dispara. Si no, se descarta.
- El barrido de viñetas pendiente (`scanPending`) también se lanza al salir de combate.

### Aviso e historial

- Aviso: toast con nombre, nivel, élite o no, distancia al punto más cercano de `spawns` en la zona y
  flecha/pin a ese punto; un sonido opcional. El nombre sale en el idioma del cliente.
- Historial por reino y por cuenta: `{ kind, id, name, level, t (último visto), first, n, map, x, y,
  alerted }`, podado a un tope fijo. Sin nombres de personajes ni reinos fuera de la clave de reino.
- Ajustes: `rares.enabled`, `vignettes`, `nameplates`, `target`, `mouseover`, `alerts`, `sound`,
  `cooldown`, `combatAlerts`, `ignored`.

### Qué es de Senda y qué se deja

- **Se adapta:** los caminos de detección, el rebote por GUID, la decisión pura y la retención en combate.
- **No se copia:** el «fundador» (aviso de un jugador concreto), el Codex de Polestar y la vista de hub;
  los tesoros (objetos de juego) quedan fuera del alcance de esta fase.
- **Datos en el juego:** `data/rares/` se compila a Lua compacto (id, nivel, rango y puntos por zona; ~25 KB
  según el plan) y se carga bajo demanda por continente, fuera de combate. Sin el dato, la detección sigue
  funcionando por viñeta, con nombre y posición del cliente.

### Pruebas previstas (simulador `tests/wowsim`)

- `Decide`: rebote, combate (hold y release con y sin enfriamiento), muerto, instancia, ignorado, jugador.
- El GUID de un raro conocido sale como id correcto; un valor secreto se salta sin error.
- Cobertura de datos: 346 de 411 con aparición (se comprueba en el generador y en la compilación).

# Senda — arquitectura

Senda es un addon de guía de leveo paso a paso para **WoW Forever** (cliente `_forever_`,
`## Interface: 16001`). Empieza con **brujo gnomo** y **mago humano** (1 → nivel máximo), pero
todo está pensado para añadir cualquier raza/clase sin tocar el motor.

Principios:

1. **Los datos no son código.** Las guías viven en `data/` (TOML) y se compilan a Lua.
   El motor no sabe nada de brujos ni de magos.
2. **Cada dato tiene procedencia.** Todo paso lleva `status` (`verified` / `unverified` /
   `disputed`) y `sources`. Solo se publica como verificado lo que pasa el harness.
3. **El juego es la fuente de verdad final.** El addon registra observaciones reales
   (misiones aceptadas/entregadas, posición, id del PNJ) que el harness usa para verificar.
4. **Nombres por id, no por texto.** Misiones, PNJ, objetos y hechizos se referencian por id;
   el nombre se resuelve en el cliente (así coincide con el idioma del jugador). Dentro de `text` y `tip` se
   escriben como fichas (`Coge «{quest:155}» de {npc:467}.`): ver «Nombres del juego» abajo.
5. **No se copian datos de terceros con licencia restrictiva.** QuestieDB es "all rights
   reserved": solo se lee en local para verificar (`.cache/`, ignorado por git) o en tiempo de
   ejecución si el usuario tiene Questie instalado. Nunca se commitea.

## Estructura del repositorio

```
addon/Senda/              Addon (esta carpeta se copia a Interface/AddOns/Senda)
  Senda.toc
  Core/                   Init, utilidades, eventos, base de datos guardada, locales
  Engine/                 Registro de guías, condiciones, progreso, detección de pasos
  UI/                     HUD, flecha, panel principal, opciones, botón de minimapa
  Recorder/               Observaciones en juego para el harness
  Knowledge/              Paneles de conocimiento (rotaciones, talentos, macros...) generados
  Locale/                 GENERADO: nombres de respaldo por idioma (Names_<locale>.lua) desde data/locale/
  Data/                   GENERADO: Travel.lua (datos de viaje en cadenas compactas, desde data/travel/)
  Guides/                 GENERADO por tools/build.py desde data/ (sí se commitea)
data/
  guides/<guide-id>/      Secciones TOML de cada guía (orden por prefijo numérico)
  guides/<guide-id>/guide.toml   Metadatos de la guía (raza/clase/facción, secciones)
  shared/                 Secciones compartidas (rutas de Alianza, etc.)
  knowledge/<class>/      Conocimiento por clase (talentos, rotación, macros, profesiones)
  observations/           Observaciones ingeridas desde SavedVariables (JSON, sin datos personales)
  locale/<locale>/        Nombres del cliente por tipo (quests, npcs, items, spells, maps, objects .json) con fuente
schema/                   JSON Schema de los TOML (fuente de verdad del formato)
tools/                    Python stdlib: build, validate, verify, ingest, site, package
harness/                  Harness de IA: fuentes, agentes de investigación, informes
site/                     Plantillas de la web (GitHub Pages); la salida va a _site/ (ignorada)
.github/workflows/        CI, release, Pages, verificación programada
```

## Formato de guía (TOML)

`data/guides/<guide-id>/guide.toml`:

```toml
id = "gnome-warlock"
title = "Brujo gnomo 1-60"
faction = "Alliance"
races = ["Gnome"]
classes = ["WARLOCK"]
# Lista ordenada de secciones; "shared:<id>" apunta a data/shared/<id>.toml
sections = ["01-coldridge", "02-dun-morogh", "shared:alliance-12-20-loch-modan", "..."]
```

Sección (`data/guides/<guide-id>/01-coldridge.toml` o `data/shared/<id>.toml`):

```toml
id = "coldridge"
title = "Valle de Crestanevada"
levels = [1, 6]
map = 1426                # uiMapID principal
summary = "Texto corto que se muestra al entrar en la sección."

[[step]]
id = "coldridge-001"       # único en todo el repo, estable (lo usa el progreso guardado)
do = "accept"              # ver tipos abajo
quest = 179
npc = 658
at = [1426, 29.9, 71.2]    # [uiMapID, x, y] en porcentaje 0-100
text = "Habla con Sten Stoutarm y coge la misión."
tip = "Opcional: consejo de experto."
status = "unverified"      # verified | unverified | disputed
sources = ["questie:quest/179"]
```

### Campos de paso

| Campo | Tipo | Uso |
|---|---|---|
| `id` | string | Obligatorio, único global, `[a-z0-9-]+` |
| `do` | enum | Obligatorio. Tipo de paso |
| `text` | string | Obligatorio. Instrucción en español, imperativo, breve |
| `tip` | string | Consejo opcional (expertos) |
| `quest` | int | Misión (accept/turnin/complete) |
| `obj` | int | Índice de objetivo (complete parcial), opcional |
| `npc` | int | PNJ relacionado |
| `item` | int | Objeto (buy/have/use/loot) |
| `count` | int | Cantidad (have/buy/loot) |
| `spells` | int[] | Hechizos (train) — completa cuando se conocen todos |
| `level` | int | Nivel (do = "level") |
| `prof` | string | Profesión (`tailoring`, `enchanting`...) para learn_prof / skill |
| `skill` | int | Rango de profesión objetivo |
| `at` | [map, x, y] | Destino principal |
| `wps` | [[map, x, y, "etiqueta"], ...] | Puntos adicionales |
| `radius` | number | Metros para `goto` (por defecto 12) |
| `node` | string | Nombre/id de nodo de vuelo (getfp/fly) |
| `zone` | int | uiMapID de llegada (hearth/fly) |
| `if` | tabla | Filtros: `class`, `race`, `faction`, `prof`, `minlevel`, `maxlevel` |
| `optional` | bool | Se puede saltar sin penalización |
| `escort` | bool | Misión de escolta: el HUD añade «Escolta: si el PNJ no está, alguien la está haciendo; espera a que reaparezca.» |
| `chain` | string | Pasos que se completan juntos |
| `link` | string | Ruta en la web (GitHub Pages) para leer más |
| `status` | enum | Obligatorio: `verified`, `unverified`, `disputed` |
| `sources` | string[] | Obligatorio (vacío solo si `unverified`) |
| `checked` | date | Fecha de la última verificación |

### Tipos de paso (`do`) y detección automática

| `do` | Se completa cuando |
|---|---|
| `goto` | El jugador está a menos de `radius` metros de `at` |
| `accept` | `QUEST_ACCEPTED` con `quest`, o la misión ya está en el registro / completada |
| `complete` | Todos (u `obj`) los objetivos de `quest` están cumplidos, o ya entregada |
| `turnin` | `QUEST_TURNED_IN` con `quest` o `IsQuestFlaggedCompleted(quest)` |
| `train` | Se conocen todos los `spells` |
| `learn_prof` | Se tiene la profesión `prof` |
| `skill` | Rango de `prof` ≥ `skill` |
| `buy` / `have` / `loot` | `GetItemCount(item) >= count` |
| `use` | Uso de `item` detectado o paso manual |
| `sethearth` | Evento de vincular piedra de hogar (`HEARTHSTONE_BOUND`) en la zona del paso |
| `hearth` | Cambio a `zone` tras lanzar Piedra de hogar |
| `getfp` | Se descubre el nodo `node` (`TAXIMAP_OPENED`) |
| `fly` | Llegada a `zone` |
| `level` | Nivel del jugador ≥ `level` |
| `dungeon` | Manual (o todas las `quest` asociadas entregadas) |
| `note` | Manual (botón "Hecho") |

Todo paso se puede marcar manualmente (Hecho / Saltar / Atrás).

## Contrato Lua (generado)

`tools/build.py` genera `addon/Senda/Guides/<guide-id>.lua` y `addon/Senda/Guides/Shared.lua`:

```lua
local _, Senda = ...
Senda.Guides:RegisterSection({ id = "coldridge", title = "...", levels = {1, 6}, map = 1426,
  steps = { { id = "coldridge-001", ["do"] = "accept", quest = 179, npc = 658,
              at = {1426, 29.9, 71.2}, text = "...", status = "unverified" }, ... } })
Senda.Guides:RegisterGuide({ id = "gnome-warlock", title = "...", faction = "Alliance",
  races = {"Gnome"}, classes = {"WARLOCK"}, sections = {"coldridge", ...} })
```

`sources` y `checked` **no** se incluyen en el Lua (solo `status`), para no inflar el addon.
El `.toc` incluye `Guides\Guides.xml`, que también genera el build.

## SavedVariables

- `SendaDB` (por personaje): guía activa, índice/estado de pasos, posiciones de marcos, opciones.
- `SendaRecorderDB` (cuenta): observaciones `{ t, kind, quest, npc, map, x, y, level, race, class, build }`.
  `kind` ∈ `accept`, `turnin`, `npc_seen` (trainer/vendor/gossip), `fp`, `bind`. Sin nombres de
  personaje ni de reino.
- `SendaNamesDB` (cuenta): lo que guarda `/senda volcar`.
  `{ version = 1, locales = { esES = { build, date, done, quest = { [id] = nombre }, npc, item, spell, map,
  missing = { quest = { [id] = true }, ... } } } }`. Un build nuevo empieza de cero. Solo nombres del juego.

## Nombres del juego (fichas)

`text` y `tip` pueden llevar fichas que `Core/Names.lua` resuelve al mostrarlas, con el nombre exacto del idioma
del cliente:

| Ficha | Qué | Cómo lo pide al cliente |
|---|---|---|
| `{quest:N}` | misión | `C_QuestLog.GetTitleForQuestID`; si no está en caché, `RequestLoadQuestByID` y `QUEST_DATA_LOAD_RESULT` |
| `{npc:N}` | PNJ | `C_TooltipInfo.GetHyperlink("unit:Creature-0-0-0-0-N-0")`, primera línea (reintentos cortos) |
| `{item:N}` | objeto | `C_Item.GetItemNameByID`; si no, `Item:CreateFromItemID(N):ContinueOnItemLoad` |
| `{spell:N}` | hechizo | `C_Spell.GetSpellName` |
| `{map:N}` | zona (uiMapID) | `C_Map.GetMapInfo(N).name` |
| `{obj:N}` | objeto del mundo | no se puede: solo el respaldo |

Nunca bloquea: lo que el cliente aún no sabe se le pide y, mientras, se muestra el volcado guardado
(`SendaNamesDB`, mismo idioma), el respaldo compilado (`Locale/Names_<locale>.lua` desde `data/locale/<locale>/`;
el inglés como último recurso) o «Misión #N». Los nombres que llegan y se están mostrando lanzan un único
`SENDA_NAMES_UPDATED` agrupado y el HUD se redibuja una vez. Los valores secretos (combate) cuentan como «sin
respuesta». Caché por sesión.

`/senda volcar` (`Core/NamesDump.lua`) recorre en una corrutina todas las secciones registradas, las páginas de
conocimiento y, si existen, `Senda.Rares`, `Senda.Dungeons` y `Senda.Travel` (claves `quest`, `npc`, `item`,
`spell`, `map`, `zone`, `quests`, `spells`, `at`, `wps`, `craft`, `mats` y las fichas de los textos), pide los
nombres de 20 en 20 por fotograma (máximo 40 esperando), se para en combate y guarda el resultado con el idioma y
el build en `SendaNamesDB`. Se puede parar (`/senda volcar parar`) y retomar; `/senda volcar reiniciar` empieza de
cero. `tools/import_names.py` lo pasa a `data/locale/` (ver `tools/README.md`).

## Automatización y estado de las misiones

Funciones tomadas de Polestar (GPL-3), adaptadas a la arquitectura de Senda y a la API de Forever (Midnight 12.x;
nada de acciones protegidas en combate):

- **Automatización** (`Engine/Automation.lua`, opción `autoQuests`, activa por defecto). Con `QUEST_DETAIL`,
  `QUEST_PROGRESS`, `QUEST_COMPLETE`, `QUEST_GREETING` y `GOSSIP_SHOW` (con `C_GossipInfo`) acepta las misiones
  que el paso actual o los 6 pasos pendientes siguientes aceptan, y entrega las del paso actual (y su `chain`;
  si el actual es un `goto`, también el siguiente). Nunca acepta lo que la guía no lista, no actúa en combate ni
  con Mayús pulsado, y si la entrega tiene varias recompensas a elegir deja la ventana abierta.
- **Misiones con tiempo** (`Engine/Quests.lua`). `C_QuestLog.GetTimeAllowed` da el tiempo; el HUD muestra la
  cuenta atrás `M:SS` de las misiones del paso actual y el chat avisa a los 5 y a 1 minuto (opción
  `questTimerAlerts`). El evento interno `SENDA_QUEST_TIMER` se lanza cada segundo mientras corre alguna.
- **Fallidas y abandonadas.** `Engine:Problem()` devuelve `failed` (`C_QuestLog.IsFailed`) o `abandoned`
  (`QUEST_REMOVED` sin entrega de una misión ya cogida por la guía; se guarda en `progress.abandoned`) cuando el
  paso actual es un `complete`/`turnin` de esa misión. El motor no salta esos pasos en silencio: el HUD los
  atenúa, explica el motivo y ofrece «Volver a cogerla» (vuelve al paso `accept`) y «Saltar misión»; la flecha
  apunta al `at` del paso `accept`.
- **Saltar una misión y sus dependientes** (`Engine/Skip.lua`, `Guides:Followups`). Clic derecho en un paso de
  misión del HUD: «Saltar esta misión». `SendaDB.skippedQuests[q] = true` (por personaje) guarda la misión y las
  que dependen de ella y aún no tienes (índice compilado en `Guides/Followups.lua` por `tools/build.py`); el motor
  trata esos pasos como saltados (`DoneMark` devuelve `"s"`, también un `goto` justo antes) en todas las guías, sin
  tocar el progreso de cada una. El HUD enseña «Saltada «X» y N misiones que dependen de ella · Deshacer»
  (`Engine:LastSkip()`, evento `SENDA_SKIPPED`); el menú ofrece restaurar todas (`Engine:UnskipAll()`).
- **Informe de errores** (`UI/Report.lua`, `Core/Events.lua`). `Senda.Errors` guarda los últimos 20 errores que
  Senda captura (`Senda:ReportError`, sin rutas ni el nombre del personaje o del reino). `/senda informe` y el botón
  del bicho del HUD abren la ventana: texto libre + contexto (guía, paso, posición, nivel/raza/clase, versiones,
  addons, estado de las misiones del paso, errores) en una caja de solo lectura que «Copiar» selecciona, y el enlace
  `https://github.com/e-omunoz/senda/issues/new?title=…&body=…` (cuerpo corto, siempre < 2000 caracteres).
- **Visibilidad** (`UI/Visibility.lua`). Opción `hideInInstance` (por defecto sí): HUD y flecha se ocultan en
  mazmorras, bandas, campos de batalla y arenas (`IsInInstance`) y vuelven al salir. «Ocultar todo»
  (`db.hideAll`): clic en el botón del minimapa o `/senda hide`; el clic derecho del botón abre un menú con panel,
  HUD, flecha y ocultar todo.
- **Tarjetas de hechizos** (`Modules/SpellCards.lua`, opciones `mod_card_level` y `mod_card_rank`). Al subir de
  nivel, los hechizos que ya puedes entrenar con su coste, si te llega el dinero y dónde entrenar (botón
  «Señalar»); tras aprender hechizos, los rangos antiguos que quedan en tus barras con «Renovar» (`PickupSpell` +
  `PlaceAction`, nunca en combate: espera a `PLAYER_REGEN_ENABLED`; nunca toca macros ni objetos). `/senda renovar`.
- **Seguimiento por objetivo.** En los pasos `complete` (y `accept`/`turnin`) el HUD lista los objetivos de
  `C_QuestLog.GetQuestObjectives` con el texto del propio cliente (ya traducido; si no trae la cuenta, se añade
  `6/8`) y en verde los cumplidos; con `obj = N` solo ese objetivo, y el paso se da por hecho en cuanto ese
  objetivo se cumple aunque la misión siga abierta. `QUEST_LOG_UPDATE` y `UNIT_QUEST_LOG_CHANGED` piden una
  evaluación agrupada (`Engine:RequestEvaluate`: una sola pasada por ráfaga). En combate el motor no avanza, pero
  compara la firma de los contadores del paso actual (`Engine:ObjectiveSignature`) y, si cambió, lanza
  `SENDA_OBJECTIVES_UPDATED` para que el HUD se redibuje: los contadores se ven al momento. Nunca se recorre la
  guía por fotograma.
- **Colocación desde el registro de misiones** (`Engine:Place`, idea de Polestar; código propio). Al iniciar
  sesión o recargar (cuando el registro ya se puede leer, y otra vez a los 5 s), al cambiar de guía y al
  reiniciarla, el paso actual se recalcula con lo que sabe el juego: misiones entregadas
  (`C_QuestLog.IsQuestFlaggedCompleted`), misiones en el registro y sus objetivos, nivel, hechizos y profesiones
  (las mismas comprobaciones de cada paso). El **ancla** es el último paso de misión con progreso (entregada, en el
  registro, objetivos empezados); no cuentan los pasos de clase o raza, los opcionales ni los saltados. Antes del
  ancla, los pasos sin misión (ir a, piedra de hogar, instructor, profesión, notas) y los opcionales se dan por
  pasados si la siguiente misión de la ruta ya está hecha o en curso; un paso de misión pendiente siempre retiene.
  Solo adelanta: nunca vuelve antes del paso guardado, respeta las marcas a mano (hechas o saltadas) y no mueve un
  paso al que volviste con Atrás o desde la lista (`progress.held`). Lo pasado se marca `a` y el chat lo dice. El
  cálculo va en una corrutina, 120 pasos por fotograma, y espera fuera de combate. `Engine:ResumeIndex()` da el
  mismo resultado sin repartir. Así, si se pierden las SavedVariables o juegas sin el addon, la guía no te deja
  atrás.
- **Guías solo a mano.** Una guía con `order` negativo en `guide.toml` (los prototipos y las rutas importadas de
  Polestar) sale en la lista y se elige con `/senda guide <id>`, pero `Engine:AutoSelect()` nunca la coge
  (`Guides:IsManualOnly`).

## Harness de verificación

1. **Estático** (`tools/validate.py`): esquema, ids únicos, orden de niveles, referencias.
2. **Base de datos local** (`tools/verify.py`): cruza con QuestieDB (Forever) leído en local:
   existe la misión, el PNJ inicia/termina la misión, coordenadas dentro de tolerancia,
   prerrequisitos antes en la ruta, raza/clase pueden coger la misión.
3. **Observaciones de juego** (`tools/ingest.py`): lo registrado en partida confirma o refuta.
4. **IA** (`harness/`): agentes que leen fuentes oficiales y comunitarias (`harness/sources.toml`),
   extraen afirmaciones con cita, las comparan con `data/` y proponen cambios en un PR con informe.
   Regla: `verified` exige una de estas tres cosas:
   - (a) una fuente oficial;
   - (b) una observación en el juego;
   - (c) que la base de datos local coincida **y** el harness haya encontrado la cita literal en una fuente
     independiente.

   Citar una guía de leveo genérica (por ejemplo, la página de rutas de un sitio) no basta para dar por
   verificado un paso concreto. El resto entra como `unverified` o `disputed`.

   Confirmar los ids y las coordenadas contra QuestieDB se muestra como evidencia en los informes, pero por sí
   solo no da el estado de verificado.

## Versionado

SemVer. `CHANGELOG.md` en español. El build escribe la versión en el `.toc`.
Los releases empaquetan `Senda-<versión>.zip` (carpeta `Senda/`) desde GitHub Actions.

## Pareja sincronizada (`Modules/Party.lua`)

Protocolo propio inspirado en el de Polestar (`Quests/Party.lua`), con el prefijo `Senda`,
`C_ChatInfo.RegisterAddonMessagePrefix` y `C_ChatInfo.SendAddonMessage` al canal `PARTY` (nunca en banda):

| Mensaje | Cuándo | Qué lleva |
|---|---|---|
| `1H|<ver>` | Al entrar en un grupo, al iniciar sesión en uno o cuando entra alguien que aún no ha hablado Senda | Saludo. Hasta que alguien contesta no sale nada más |
| `1R|…` / `1S|…` | Al oír un saludo (`R`: pide la tuya) o a alguien nuevo | Instantánea del registro: `33:5/8,0/1;60:` |
| `1|…` | 2 s después del último cambio del registro | Solo las misiones que cambiaron (`60:-`: salió del registro) |
| `1P|<índice>|<ver>|<guía>` | Con la instantánea | Informativo (versión) |
| `2P|<paso>|<guía>` | Al cambiar de paso (2 s) | El paso por su `id`, no por su número |
| `2D|<q>,…` | Con el paso | Misiones entregadas de los pasos cerca del tuyo |
| `2U|<nivel>|<CLASE>|<Raza>|<ver>` | Con la instantánea y al subir de nivel | Para saber qué pasos son de los dos |
| `2G|<paso>|<guía>` / `2A|<y,n,x,=,p>` | «Pedir que salte a mi paso» | Petición y respuesta (acepta, rechaza, no puede, ya está, ya va por delante) |

- Todo mensaje cabe en 255 bytes; el registro (hasta 40 misiones) se parte por misiones enteras.
- Los envíos van por una cola en orden: lo que el cliente rechaza (`Enum.SendAddonMessageResult` distinto de
  `Success`, o `false` en clientes antiguos) se reintenta cada 3 s, hasta 6 veces. En combate no se lee el registro
  (los valores pueden ser secretos): se envía al salir.
- **Delante/detrás:** se cuentan los pasos de la guía completa (sin filtrar) entre tu paso y el suyo que son de los
  dos (`if.class`, `if.race` de cada uno); los de una sola clase no cuentan.
- **Espera:** en un paso `complete`, `Engine:Evaluate` pregunta a `Party.Holds(entry)` antes de dar el paso por
  hecho, y `Engine:WantsQuest("turnin")` a `Party.HoldsQuest(q)`. Se deja de esperar con «Seguir sin él»
  (`Party.GoOn`, hasta que termine el grupo), cuando el compañero termina, deja el grupo o lleva 120 s
  desconectado.
- **Saltar a su paso:** al aceptar se marcan como saltados los pasos hasta el suyo, salvo los que él no tiene (los
  de tu clase) y los de coger misiones que su paso necesita.
- Los nombres de los compañeros solo viven en memoria (nunca en `SendaDB`).

## Convivencia con otros addons

- **Questie se mantiene instalado** (lo usa el jugador). Senda no dibuja iconos de misión en el mapa ni duplica
  su seguimiento de misiones. Si Questie está cargado, Senda puede consultar su base de datos en tiempo de
  ejecución (opcional, protegido con `pcall`) para completar las coordenadas que falten.
- **TomTom se sustituye.** Senda trae su propia flecha (`UI/Arrow.lua`):
  - Muestra distancia, tiempo estimado y giro.
  - Tiene **modo cadáver**: al morir apunta automáticamente a tu cuerpo usando
    `C_DeathInfo.GetCorpseMapPosition` y vuelve a la guía al resucitar.
  - Puede apuntar a cualquier punto con `/senda way <x> <y> [texto]`.
  - Si TomTom está instalado, se puede usar como alternativa (opción), pero no hace falta.

## API interna del núcleo (contrato entre módulos)

Todo vive en la tabla de espacio de nombres del addon (`local ADDON, Senda = ...`) y se expone también como
`_G.Senda` para depurar.

```lua
Senda.VERSION                          -- desde el .toc
Senda.L                                -- tabla de cadenas localizadas (esES por defecto, enUS de reserva)
Senda.db                               -- SendaDB (por personaje), listo tras PLAYER_LOGIN
Senda.recorder                         -- SendaRecorderDB (cuenta)
Senda:Print(msg)                       -- mensaje con prefijo en el chat
Senda:Debug(msg)                       -- solo si db.opts.debug
Senda.Events:On(event, fn)             -- varios suscriptores por evento; fn(event, ...)
Senda.Events:Fire(name, ...)           -- eventos internos: "SENDA_STEP_CHANGED", "SENDA_GUIDE_CHANGED",
                                       --   "SENDA_STEP_COMPLETED", "SENDA_READY", "SENDA_NAMES_UPDATED"
Senda.Compat.*                         -- capa sobre la API moderna con fallbacks:
                                       --   QuestTitle(id), IsQuestDone(id), IsOnQuest(id), QuestObjectives(id),
                                       --   SpellName(id), SpellIcon(id), IsSpellKnown(id), ItemName(id),
                                       --   ItemIcon(id), ItemCount(id), PlayerMapPos() -> map, x, y (0-1),
                                       --   WorldDistance(map1,x1,y1, map2,x2,y2) -> metros, angulo
                                       --   NpcIdFromGUID(guid) -> id o nil, ProfessionRank(key) -> rango, max
Senda.Names:Resolve(text), :Get(kind, id) -> nombre, origen, :Request(kind, id, fn), :Cached(kind, id)
Senda.Names.Dump:Start(reset), :Stop(), :Running(), :Progress()   -- /senda volcar
Senda.Guides:RegisterSection(t), :RegisterGuide(t), :Get(id), :AllSections(), :ForPlayer() -> lista de guías válidas
Senda.Engine:CurrentStep(), :Advance(), :Back(), :Skip(), :Complete(stepId), :SetGuide(id)
Senda.Engine:WantsQuest("accept"|"turnin", questId)  -- ¿la guía quiere esa acción ahora? (Engine/Automation.lua)
Senda.Engine:Problem([entry]) -> { kind = "failed"|"abandoned", quest, accept }   -- Engine/Quests.lua
Senda.Engine:StepTimers(step) -> { { quest, left }, ... }, :RetakeQuest(q), :SkipQuest(q), :IsAbandoned(q)
Senda.Engine:SkipQuestTree(q) -> info, :UndoSkip([info]), :UnskipAll(), :LastSkip(), :IsQuestSkipped(q)   -- Engine/Skip.lua
Senda.Guides:Followups(q) -> misiones que dependen de q (índice de Guides/Followups.lua)
Senda.Report:Open(), :Context(), :Text(desc), :IssueURL(desc); Senda.Errors:Add(err), .list   -- informe de errores
Senda.Visibility:Hidden(), :SetHidden(b), :Toggle()  -- ocultar HUD y flecha (instancias o a mano)
Senda.Party.Members(), .StepsApart(m), .Holds(entry), .HoldsQuest(q), .GoOn(), .RequestSync()  -- pareja
                                       --   (Modules/Party.lua; evento interno SENDA_PARTY_UPDATED)
Senda.Arrow:SetTarget(map, x, y, label, source), :Clear(source), :Has(source), :Destination() -> target, source
                                       --   (el objetivo sin el tramo "travel"; evento SENDA_ARROW_DEST)
Senda.Modules.Travel.HudLine(), .GetPlan(), .Context(), .PlanSync(ctx, inicio, destino), .HighlightTaxi()
                                       --   planificador de viaje (Modules/Travel.lua; evento SENDA_TRAVEL_UPDATED)
Senda.Knowledge:Register(t), :ForClass(class) -> lista de páginas
Senda.UI:RegisterTab({ key, title, icon, order, build = function(parent) end, refresh = function() end })
Senda.UI:Frame / :Button / :ScrollText / :Backdrop       -- helpers de estilo común
Senda.Options:Register({ key, label, type = "toggle"|"slider", default, min, max, onChange })
```

Propietarios de carpetas del addon:
- `Core/`, `Engine/`, `UI/`, `Recorder/` y `Senda.toc`: equipo del motor.
- `Modules/`: utilidades portadas (equipo, vendedores, instructores, desencantar, macros, barras, análisis,
  asesor, pareja y planificador de viaje).
- `Guides/` y `Knowledge/`: los genera `tools/build.py`.

Cada carpeta tiene su `<Carpeta>.xml` y el `.toc` solo incluye esos XML, en este orden:
`Core\Core.xml`, `Locale\Locale.xml`, `Engine\Engine.xml`, `Recorder\Recorder.xml`, `UI\UI.xml`, `Knowledge\Knowledge.xml`,
`Data\Travel.lua` (un solo archivo, sin XML), `Guides\Guides.xml`, `Modules\Modules.xml`.

## Planificador de viaje (`Modules/Travel.lua`)

Cuando el destino de la flecha (fuente `guide` o `manual`) está en otro continente o a más de 800 yardas, el módulo calcula
el camino más rápido con lo que el personaje sabe y lleva, y lo enseña. Datos y modelo de costes en
[TRAVEL.md](TRAVEL.md); aquí, cómo encaja en el motor:

- **Datos bajo demanda.** `Data/Travel.lua` (generado por `tools/build.py` desde `data/travel/`) solo contiene cadenas
  compactas (`Senda.TravelData`); no se decodifican al cargar, sino la primera vez que hay un destino lejano y fuera de combate.
- **Dijkstra en una corrutina.** Estado (nodo, ¿llegado volando?) para cobrar el despegue una vez por tramo. A pie en línea
  recta ×1,25 a 7 yd/s (más rápido con corcel de brujo, forma de viaje o una montura en las bolsas), vuelos **solo entre
  nodos descubiertos** de tu facción y clase, barcos, zepelines y tranvía con su espera media, portales, teletransportes de
  clase (hechizo conocido, reactivo en las bolsas y sin enfriamiento) y la piedra de hogar (objeto en las bolsas, enfriamiento
  leído con `C_Container.GetItemCooldown`, posada vinculada). Se calcula sin atajos, con la piedra y con los teletransportes, y
  gana lo más rápido que cumpla sus márgenes (piedra: viaje de 3 min o más que ahorre 2 min; teletransporte: ahorra 60 s o el 20 %).
  La corrutina cede cada 700 operaciones o 1 ms (el presupuesto del addon es de 2 ms por fotograma), se pausa en combate y no usa `pcall`
  (Lua 5.1 no deja ceder a través de él).
- **Nodos descubiertos.** Los del motor (`db.char.fps`, al abrir un maestro de vuelo) y los que lee `C_TaxiMap.GetTaxiNodesForMap`
  (`isUndiscovered`) sin abrir nada, guardados en `db.char.travel`. Un cliente que no marca ningún nodo como no descubierto no se
  da por bueno.
- **Piedra de hogar.** La posada vinculada se aprende al vincular (`HEARTHSTONE_BOUND`: el posadero del paso `sethearth`, la unidad
  «npc» o la posada a menos de 60 yardas), se reconoce por el nombre de zona del cliente (`C_Map.GetAreaInfo`) o por el
  nombre inglés de los datos, y como último recurso por el último paso `sethearth` hecho de la guía.
- **Salida.** Una línea del HUD, «Camino más rápido: vuela a X (3 min) → barco a Y → a pie», y la fuente `travel` de la flecha
  (justo por delante del destino al que sustituye) apuntando al embarque del primer tramo. Sin flecha si ya estás allí o si el
  primer tramo es la piedra o un teletransporte. Clic derecho en la flecha la descarta hasta que cambie el destino.
- **Mapa de vuelo.** Con `TAXIMAP_OPENED` marca con un resplandor el nodo al que lleva el primer vuelo (`FlightMapFrame` o los
  botones del marco clásico) y lo dice en el chat. Nunca vuela por ti: no hay ninguna acción protegida.
- Solo Reinos del Este y Kalimdor (continentes 0 y 1): el continente nuevo de Forever no tiene yardas fiables. No se usan los
  ascensores ni los horarios reales de barcos y zepelines (esperas medias). `/senda viaje [recalcular]` y la opción
  `mod_travel`.

## Formato de conocimiento (TOML)

`data/knowledge/<class>/*.toml` (o `data/knowledge/general/*.toml`) se compila a Lua **tal cual**: el build hace
un volcado genérico de TOML a una tabla Lua y quita `sources` y `checked`. Cada archivo:

```toml
id = "warlock-bracket-10-19"
class = "WARLOCK"            # o "ANY"
kind = "page"                # page | talents | spells | macros | professions | rotation
title = "Niveles 10-19: el Abisario"
levels = [10, 19]            # opcional
order = 20
status = "verified"
sources = ["..."]

[[block]]                    # kind = "page"
heading = "Zonas"
body = "Texto. Admite **negrita**, listas con '- ' y enlaces [texto](https://...)."
```

Tipos estructurados (los usa el módulo correspondiente):
- `talents`: `[[pick]] level, talent, tree, note`
- `spells`: `[[train]] level, spells = [ids], note`
- `macros`: `[[macro]] name, icon, minlevel, body, note`
- `professions`: `[[route]] prof, from, to, craft (id), mats = [[id, n]], trainer = [map, x, y, "nombre"]`
- `rotation`: `[[phase]] from, to, text, spells = [ids]`

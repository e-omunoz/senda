# Senda 1.0: incorporar Polestar sin dejar de ser Senda

> Plan de incorporación de los datos, rutas e ideas de [Polestar](https://github.com/fitzforge/polestar)
> (GPL-3) a Senda. Objetivo: **superar a Polestar** como guía para subir del 1 al 60 en WoW: Forever,
> con rutas más eficientes, más fiables y mejor explicadas, en español nativo.
>
> Estado: propuesta aprobada para empezar · 12-nov-2026 · fuentes: código de Polestar
> (commit del 12-nov-2026), forever-db 2026.11.1 y el estado actual de Senda 0.3.5.

## 1. De dónde partimos

| | Senda 0.3.5 | Polestar (beta) |
|---|---|---|
| Rutas 1-60 | 3 personajes (gnomo brujo, humano mago, elfo druida), ~2.030 pasos | Todas las razas de las dos facciones: 35 guías de Alianza, ~1.950 pasos con ~5.100 objetivos |
| Cómo se hacen | A mano, migradas de BrujoGnomoGuia y ampliadas | Generadas: búsqueda de ruta sobre datos del juego y un simulador que juega cada guía hasta el 60 |
| Texto | Español escrito a mano, con trucos | Inglés generado; el español cubre ~48% de los textos de Alianza (los nombres los pone el cliente) |
| Seguimiento | Por paso | Por objetivo (mata 6/8, recoge 3/5), y la posición se recalcula del registro de misiones |
| Conocimiento de clase | Talentos, rotación, macros que se crean solas, barras que se colocan solas, plan de profesiones, asesor «Qué hago», equipo | Planes de talentos en pausa («Coming soon») |
| Verificación | Estado por paso (verificado/sin verificar/en disputa) con fuentes; arnés de IA | Correcciones de jugadores que la siguiente compilación conserva |
| Navegación | Flecha 2D con distancia, ETA y modo cadáver | Flecha 3D por caminos reales (mapas de navegación de ~38 MB), planificador de viaje, líneas de ruta |
| Tamaño | ~13.900 líneas de Lua | Núcleo de 17 MB más ~14 MB de guías y 2-4 MB por idioma |

**Conclusión honesta:** en cobertura y fiabilidad de rutas Polestar va muy por delante. Senda gana en lo que
un jugador experto valora una vez tiene la ruta: saber *por qué* hace cada cosa, qué entrenar, qué
llevar en las barras, qué profesiones, qué truco ahorra 10 minutos, todo en su idioma y verificado.

## 2. La identidad de Senda

Senda no va a ser «Polestar en español». Va a ser **la guía del jugador experto**:

1. **Ninguna misión porque sí.** Cada paso se justifica: experiencia por minuto, una recompensa que mejora
   tu equipo, o porque desbloquea una cadena que sí compensa. Lo que no compensa, fuera (o marcado como
   opcional con su motivo). El HUD lo dice en una línea: «+1.150 XP · 3 min · desbloquea Minas de la Muerte».
2. **Rutas optimizadas de verdad.** Partimos de la ruta de Polestar (ya optimizada por simulación) y le
   aplicamos nuestro filtro de eficiencia, nuestros atajos (piedra de hogar, vuelos, barcos con horario) y
   nuestra capa de clase.
3. **Fiable y al día.** Cada dato tiene fuente y estado. Los datos abiertos se sincronizan solos; los
   cambios de Forever (parches, notas de Blizzard) entran por el arnés de IA con su cita.
4. **Tu clase, resuelta.** Talentos, rotación, macros, barras, profesiones, equipo y qué entrenar a cada
   nivel, como hasta ahora: es lo que Polestar no tiene.
5. **Español nativo.** Textos escritos para jugadores hispanohablantes, no traducidos. Términos del cliente
   esES («Alguacil», no «Marshal»).
6. **Juego en pareja.** El modo dúo ya existe y crece: misiones compartidas, capas, quién va por delante.

## 3. Licencia: Senda pasa a GPL-3

Para incorporar código, rutas o datos de Polestar, Senda tiene que ser GPL-3 (su licencia). Senda tiene un
solo autor, así que el cambio es directo:

- `LICENSE` pasa a GPL-3; las versiones hasta la 0.3.5 siguen siendo MIT para quien ya las tenga.
- Un `THIRD_PARTY.md` lista cada componente importado, su licencia y su origen (commit de Polestar,
  versión de forever-db).

**Qué podemos traer y qué no:**

| Componente | Licencia | ¿Entra en Senda? |
|---|---|---|
| Código del addon Polestar | GPL-3 | Sí, con atribución |
| Rutas y textos de guías | GPL-3 | Sí, con atribución |
| forever-db: misiones, PNJ, objetos, apariciones, mapas | GPL-3 | Sí |
| forever-db: capa propia (mecánicas, pasos, notas) | CC BY 4.0 | Sí, con atribución |
| Datos de viaje: vuelos, barcos, zepelines, tranvías con horarios | GPL-3 (en parte de Shortest Path Forever, GPL-3+) | Sí |
| Router de caminos (código de Shortest Path Forever) | GPL-3+ | Legalmente sí; por cortesía, avisar al autor |
| Mapas de navegación de Leffe y los tramos derivados (`legs`) | Permiso personal a Polestar | **No** sin permiso propio |
| DingDB y textos esES que vienen de ella | GPL-3 con permiso a Polestar | Solo lo que también salga de otra fuente |
| AtlasLoot, RareScanner, DungeonJournal | Restringidas o sin licencia | **No** |
| QuestieDB | Todos los derechos reservados | Seguimos leyéndola en local, nunca se publica |

## 4. Datos: forever-db como base abierta

Hoy el arnés depende de la QuestieDB instalada en tu disco, que no se puede publicar ni usar en GitHub.
forever-db es abierta y cubre casi todo:

- **Lo que da:** nivel mínimo, prerrequisitos (incluidos los «breadcrumb»), quién da y recoge cada misión,
  objetivos (tipo, objetivo, cantidad), apariciones en coordenadas de mundo con 59 marcos de mapa para
  pasarlas a porcentaje, XP de cada misión y recompensas.
- **Lo que le falta:** misiones excluyentes (`exclusiveTo`) y profesión requerida (`requiredSkill`).
  Para eso seguimos con QuestieDB en local y lo guardamos como hechos en nuestros TOML (como ya hacemos
  con `reqlevel` y `reqskill`).
- **Sincronización:** fijamos una versión publicada (`data-v*`), comprobamos sus sha256, y una tarea
  semanal de GitHub Actions avisa cuando sale una nueva con el resumen de su CHANGELOG.

## 5. Rutas: importar, filtrar y mejorar

### 5.1 Importador

`tools/import_polestar.py` lee las **guías compiladas** de Polestar (`Polestar_Guides*/Guides.lua`), no
los `.guide`: los fuentes casi no llevan coordenadas, las compiladas sí (PNJ, mapa, x, y, objetivo).

- Cada paso de Polestar tiene ~2,6 objetivos; en Senda cada paso es una acción. El importador los parte y
  los agrupa con `chain` para que el HUD los muestre juntos («Habla con X: entrega A, coge B y C»).
- `only` pasa a `if.class/race/faction`; `optional` y `group` se conservan; `when level` pasa a
  `if.minlevel`.
- Lo que Senda aún no sabe expresar (condiciones vivas como «si llevas X», `skipto`, misiones de grupo con
  alternativa en solitario) se importa como nota y se apunta en la lista de mejoras del motor.
- Cada paso importado lleva su origen: `sources = ["polestar:<commit>/<guía>#<paso>"]`.
- **Lo hecho a mano gana.** Si un paso de Senda ya existe (misma misión y acción), se conservan su texto,
  sus trucos y su estado; el importador solo actualiza orden, coordenadas y datos.

### 5.2 Filtro de eficiencia (lo que nos diferencia)

`tools/route_score.py` puntúa cada misión de la ruta:

- **Coste:** tiempo estimado = desplazamiento (distancias entre pasos, vuelos, barcos) + objetivo (cuántos
  enemigos, densidad de apariciones, tasa de botín) + entrega.
- **Beneficio:** XP de la misión (forever-db) en relación con la XP de tu nivel, recompensa (¿mejora tu
  equipo para tu clase?), y qué desbloquea.
- **Decisión:** por debajo de un umbral de XP/min, la misión sale de la ruta o queda como opcional con el
  motivo. Las cadenas se evalúan enteras (una misión floja que abre una cadena buena se queda).
- El resultado se guarda en el TOML (`why = "..."`, `xp`, `mins`) y el HUD lo muestra.

### 5.3 Capa Senda

Sobre la ruta importada y filtrada:

- Textos en español escritos por el arnés de IA (con los nombres del cliente esES y las traducciones de
  Polestar como apoyo) y revisados en el juego.
- Trucos de experto por zona: dónde poner la piedra, qué vuelo coger, qué grindear entre misiones, qué
  mazmorra compensa (con el +50% de XP en mazmorras desde el 8-nov).
- Pasos de clase (entrenar, misiones de clase, demonios del brujo, formas del druida, teletransportes del
  mago), enlazados con el conocimiento de clase.

### 5.4 Cobertura

1. Prototipo: **Teldrassil** (druida), comparado en el juego con nuestra guía actual.
2. Las 3 guías actuales completas (1-60).
3. Todas las razas y clases de Alianza.
4. Horda.

## 6. Funciones del motor: qué traemos y en qué orden

Ordenadas por valor para quien sube de nivel frente al esfuerzo.

| # | Función | Esfuerzo | Senda hoy |
|---|---|---|---|
| 1 | Aceptar y entregar solo las misiones del paso actual (Mayús lo evita) | Bajo | No |
| 2 | Misiones con tiempo: cuenta atrás; fallidas o abandonadas: la flecha vuelve a quien te la dio | Bajo-medio | No |
| 3 | Tarjeta al subir de nivel: hechizos, coste total, si te llega y dónde; actualizar rangos en las barras | Bajo | En parte (instructor y barras) |
| 4 | Seguimiento por objetivo (6/8) y posición recalculada del registro de misiones | Medio | Por paso |
| 5 | Saltar una misión y todas las que dependen de ella, con Deshacer | Bajo-medio | En parte (`chain`) |
| 6 | Avisos de escolta («si no está, alguien la está haciendo: espera») | Bajo | No |
| 7 | Ocultar en mazmorras; botón «ocultar todo» | Bajo | En parte |
| 8 | Ventana de informe de errores con todo el contexto y enlace a GitHub | Bajo | En parte |
| 9 | Planificador de viaje: vuelos conocidos, barcos y zepelines con horario, piedra de hogar | Medio | Sí, fase 3 (`Modules/Travel.lua`; esperas medias, sin horario real) |
| 10 | «Mientras estás aquí»: entregas y recogidas cercanas primero, objetivos después | Medio-alto | No |
| 11 | Alertas de raros (viñetas del minimapa) | Bajo-medio | No |

## 6a. Principios técnicos

- **Dentro del juego solo hay Lua 5.1.** Un addon no puede ejecutar Rust, ni programas externos, ni abrir
  red, ni leer ficheros: solo Lua y sus SavedVariables, que se escriben al salir. Un programa externo no
  puede hablar con el juego en directo (leer la pantalla o inyectar va contra las condiciones de Blizzard).
- **Por eso, todo lo pesado se calcula fuera, en Rust, al compilar.** En el juego solo se consultan datos
  ya calculados. Herramientas en Rust (y Python para lo ligero) generan los paquetes de datos; el addon los
  lee como cadenas compactas.
- **Ninguna espera en el juego:** cada consulta cabe en menos de 2 ms por fotograma; lo que no quepa se
  reparte en varios fotogramas con corrutinas, nunca se bloquea. Los paquetes grandes se cargan bajo
  demanda, por continente, fuera de combate, y se descargan de memoria cuando no hacen falta.
- **Datos reales y objetivos:** terreno y tablas del cliente, forever-db, partidas grabadas en el juego.
  Nada estimado a ojo: si un dato no tiene fuente, no entra.

**Navegación (decisión):** malla de navegación real generada desde el terreno del cliente de Forever, sin
pasar por un grafo hecho a mano:

1. Extracción del terreno y los edificios del cliente (CASC) y malla con Recast, en Rust. Shortest Path
   Forever y Polestar ya lo hacen (el constructor en Rust de Polestar, `forge-navbuild`, es GPL-3 y lo
   podemos reutilizar). Nunca se publica nada del cliente, solo las celdas transitables derivadas.
2. Precálculo jerárquico (HPA*): la malla se divide en sectores con sus pasos entre sectores y los caminos
   entre pasos ya resueltos. En el juego, una ruta de continente es un A* sobre unos pocos cientos de nodos
   y el detalle se resuelve solo cerca del jugador.
3. Paquetes por continente comprimidos, con objetivo de memoria por debajo de Polestar (~26 MB cargados).
4. Validación con las 50 rutas de prueba, comparando con rastros reales del grabador.

## 6b. Lo que Polestar hace y no podemos copiar: alternativas abiertas

No copiamos los mapas de navegación de Leffe ni el Codex de Polestar (permisos personales). Para cada una
de esas funciones hay una vía abierta o propia, con su forma de comprobar que cumple su objetivo.

| Función | Cómo la hacemos | Licencia | Tamaño | Esfuerzo |
|---|---|---|---|---|
| Caminos reales | Malla real desde el terreno del cliente (Recast en Rust) con precálculo jerárquico; en el juego, A* sobre el grafo de sectores y detalle solo cerca (ver 6a) | Propia + GPL-3 (SPF, `forge-navbuild`) | Por continente, bajo demanda; objetivo < 26 MB cargados | Alto |
| Planificador de viaje | Datos de vuelos, barcos, zepelines, tranvías y portales de Polestar (GPL-3, con el aviso de Shortest Path Forever), nodos conocidos con `C_TaxiMap`, Dijkstra con andar/volar/barco/piedra de hogar. Después, los regeneramos nosotros desde wago.tools, classic-db e InFlight | GPL-3 / MIT | ~70 KB | Medio |
| Buscador de objetos | forever-db (objetos de misión) + ForeverLevelingBiS (MIT: botín de mazmorra y equipo de subida) + tablas del cliente para monturas y mascotas, en un addon aparte que se carga al usarlo | GPL-3 + MIT + datos del cliente | 0,3-0,5 MB | Medio |
| Diario de mazmorras | El cliente de Forever no trae Diario de encuentros: misiones de cada mazmorra desde forever-db, niveles desde las tablas del cliente, entradas comprobadas, botín útil por clase desde ForeverLevelingBiS con los pesos de Senda. **Hecho** (rama `fase4-mazmorras`): pestaña «Mazmorras», ver [DUNGEONS.md](DUNGEONS.md) | GPL-3 + MIT | ~85 KB | Medio |
| Alertas de raros | Detección por viñetas del minimapa (`C_VignetteInfo`, comprobado en el cliente de Forever), placas de nombre y objetivo; lista de 411 raros con sus apariciones desde forever-db | GPL-3 (lógica adaptada de Polestar) | ~25 KB | Bajo-medio |
| Grupo y pareja | Protocolo propio por `C_ChatInfo.SendAddonMessage` inspirado en Polestar: saludo, progreso por misión con contadores, quién va por delante, pedir al compañero que salte a tu paso, esperar al compañero. Sin librerías | Propia | Pequeño | Medio |
| Grabador | Ampliar el `Recorder` de Senda: pasos, XP, combate, ausencia, muertes y rastro de posición opcional, sin nombres. Herramientas que calculan el tiempo real de cada paso y lo comparan con el filtro de eficiencia; los rastros alimentan el grafo de caminos | Propia | — | Medio-alto |

**Cómo validamos cada una:**

- **Caminos:** 40-60 rutas de prueba (entrada de Minas de la Muerte, ascensores de Cima del Trueno, Entrañas,
  túnel Humedal-Dun Morogh, puentes de Mil Agujas) en el simulador. La línea nunca cruza celdas imposibles
  (comprobado contra una malla de referencia que no se publica); la ruta mide como mucho 1,3 veces lo que
  mide un paseo real grabado; cero atascos donde la flecha recta sí se atasca; menos de 2 ms por fotograma.
  En el juego: las mismas 10 caminatas con flecha recta y con la nuestra, cronometradas.
- **Viaje:** respuestas esperadas en el simulador (Ventormenta → Costa Oscura por el barco de Menethil;
  «andando es más rápido» por debajo de 400 m; nunca un nodo desconocido o de la otra facción). En el juego:
  error mediano del tiempo previsto frente al real ≤ 15% en 20 viajes.
- **Buscador:** ≥ 95% de los objetos de las listas de subida con al menos una fuente; 20 objetos conocidos
  comprobados en el simulador; 10 monturas y mascotas en el juego.
- **Mazmorras:** misiones previas en el orden correcto antes de cada paso `dungeon`; 3 entradas recorridas
  en el juego.
- **Raros:** pruebas de la lógica de decisión (rebote, combate, muerto); cobertura 346 de 411 con
  aparición conocida; 5 raros conocidos comprobados en el juego (Madre Colmillo, Thuros).
- **Pareja:** modo de dos jugadores en el simulador (los mensajes de uno llegan al otro, con fallos de
  envío simulados); en el juego, contadores iguales a los del compañero, menos de 10 mensajes por minuto
  y ningún aviso de límite en una hora.
- **Grabador:** sesiones grabadas reproducidas en el simulador con tiempos exactos; prueba de privacidad
  (falla si se guarda un nombre o un reino); error mediano entre tiempo medido y estimado ≤ 30% por paso.

## 6c. Nombres en español sacados del juego

Los nombres oficiales en español (misiones, PNJ, objetos, hechizos, zonas) los pone el propio cliente:

- **Fichas en el texto:** los pasos se escriben como `Coge «{quest:155}» de {npc:467}` y Senda pone el
  nombre al mostrarlo (`C_QuestLog.GetTitleForQuestID`, tooltip de criatura por id, `C_Item`, `C_Spell`,
  `C_Map`). Siempre sale el nombre exacto del idioma del cliente; si aún no está en caché, se pide al
  servidor y el HUD se actualiza al llegar.
- **Volcado desde el cliente:** `/senda volcar` pide al juego los nombres de todos los ids de las guías y
  los guarda; una herramienta los pasa a `data/locale/esES/`. Sirven de respaldo, para la web y como dato
  **verificado en el juego**. Un nuevo volcado detecta los cambios de nombre de cada parche.
- Las explicaciones, los trucos y el porqué de cada paso los seguimos escribiendo nosotros.

## 6d. Pedidos del jugador (pendientes)

- **Pestaña «Aparte»** (fuera de la guía principal), con tres bloques coordinados:
  - **Para después:** botón en el HUD y en el clic derecho de un paso; aparca la misión y sus
    dependientes (o la cadena de clase entera, p. ej. la súcubo) sin darla por hecha ni saltada.
    Recordatorio discreto al entrar en el mapa de alguno de sus pasos o cuando la ruta pasa cerca;
    las cadenas de clase llevan una pista del mejor momento («cuando la ruta vaya a Vallefresno»).
  - **Reserva de XP:** misiones opcionales, las que el filtro de eficiencia quitó y las de Polestar
    que no van en la ruta, ordenadas por XP/min y cercanía, solo las que puedes coger ya. Se ofrece
    si te falta nivel para el siguiente paso, si acabas una zona antes de tiempo o con «Más misiones
    aquí».
  - **Desvío activo:** lo que haces fuera de la ruta, con su progreso; al acabar, vuelta a la ruta
    donde la dejaste. Lo hecho en un desvío cuenta para la ruta.
  La flecha sigue o la ruta o el desvío, nunca los dos; el HUD solo añade una línea cuando hay algo
  útil justo ahí.
- **Evaluación de equipo según la build y la clase:** hoy `Modules/Gear.lua` compara mejoras de forma
  general. Debe usar pesos de estadísticas por clase y build (Aflicción del brujo, Escarcha del mago,
  Feral del druida; pesos con fuente, p. ej. wowsims, MIT), respetar lo que la build prefiere (tipo de
  arma y armadura que puede llevar, bastón frente a varita y orbe, Espíritu frente a Intelecto según el
  tramo de nivel), y aplicarlo en recompensas de misión, bolsas, tooltips y la lista de equipo.
  ForeverLevelingBiS (MIT) como referencia de piezas por tramo.
  **Hecho** (rama `fase3-equipo`): ver [GEAR.md](GEAR.md). ForeverLevelingBiS se usa en su versión MIT v0.12.0-beta
  a través de Polestar; las versiones actuales de CurseForge son «All Rights Reserved».

## 7. Calidad: cómo sabremos que somos mejores

- **Simulador** (`tests/wowsim`): cada guía importada se juega entera en cada raza y clase, como ahora.
- **Comprobador de ruta:** puerto de la idea de Polestar; rechaza pasos imposibles (misión no disponible,
  nivel insuficiente, profesión que falta, PNJ en otra facción).
- **Grabador en el juego:** Senda ya tiene `Recorder`; sus partidas alimentan coordenadas reales y tiempos.
- **Métricas publicadas en la web:** tiempo estimado 1-60 por personaje, XP/min media, % de pasos
  verificados, misiones descartadas por ineficientes y por qué, errores abiertos.

## 8. Cómo lo vamos a construir

Con flujos de trabajo de varios agentes (*workflows*), por fases. **Opus** diseña y hace lo difícil (motor,
importador, puntuación de rutas, revisiones); **Sonnet** hace lo mecánico (conversión de datos, funciones
pequeñas, textos, pruebas). Cada fase termina con el simulador en verde y una versión publicada.

| Fase | Contenido | Versión |
|---|---|---|
| 0 | Licencia GPL-3, `THIRD_PARTY.md`, forever-db fijada y adaptador en `tools/` | 0.4.0 |
| 1 | Importador + prototipo Teldrassil + funciones 1, 2, 3, 6 y 7 | 0.4.x |
| 2 | Nombres desde el juego (fichas y volcado), filtro de eficiencia, grabador ampliado, las 3 guías actuales completas, seguimiento por objetivo, saltar con Deshacer, informe de errores, pareja sincronizada | 0.5.0 |
| 3 | Todas las razas de Alianza, planificador de viaje, grafo de caminos, «Mientras estás aquí», alertas de raros | 0.6.0 |
| 4 | Horda, diario de mazmorras, buscador de objetos (hecho en la rama `fase4-objetos`: línea en la descripción, `/senda objeto`, pestaña «Objetos», «Señalar» y nombres del juego; [LOOKUP.md](LOOKUP.md)), métricas en la web | 1.0.0 |

Fase 4, Horda: rama `fase4-horda`, [ROUTE-HORDE.md](ROUTE-HORDE.md) (cinco salidas de raza, ruta común 12-60,
filtro de eficiencia con bandas propias, entrenamiento de clase de `data/knowledge/trainer`).

## 9. Riesgos

- **Divergencia con Polestar:** sus rutas cambian casi a diario. El importador se vuelve a ejecutar y
  enseña las diferencias; lo hecho a mano nunca se pisa.
- **Calidad de texto:** miles de pasos nuevos sin texto en español. El arnés los escribe, pero hasta que
  se revisen en el juego quedan como «sin verificar».
- **Memoria y tamaño:** las guías se cargan por raza (como hace Polestar) para no cargar las 35 a la vez.
- **Nombre:** ya existe «SendaFH» en CurseForge (Polestar en español). Si publicamos ahí, conviene un nombre
  que no se confunda.
- **Permisos personales:** nada que dependa de permisos dados solo a Polestar (mapas de Leffe, DingDB).

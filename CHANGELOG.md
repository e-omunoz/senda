# Registro de cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Versionado [SemVer](https://semver.org/lang/es/).

## [Sin publicar]

## [0.8.1] - 2026-11-14

### Corregido
- **La flecha de viaje sigue al plan nuevo.** Si el plan cambiaba (te movías, aprendías un nodo, la piedra volvía a estar
  lista), el HUD decía el tramo nuevo pero la flecha seguía apuntando al primer tramo viejo.
- **La flecha de viaje ya no parpadea a ~40 yd del embarque.** El radio de llegada iba en yardas y la flecha lo
  comparaba en metros.
- **El planificador de viaje ya no anda en línea recta por encima de montañas, mar y murallas.** Andaba ×1,25 en línea recta
  entre dos puntos cualesquiera del mismo continente: a un brujo gnomo en Villa Oscura le mandaba volar a Forjaz y andar
  1095 yd «recto» hasta el Puerto de Menethil, cruzando las montañas de Dun Morogh, y la flecha no podía seguir ese tramo.
  Ahora anda por un grafo de andar con las yardas reales de la malla propia de Senda: de Forjaz a Menethil son 5739 yd
  (túnel, Loch Modan, Dun Algaz), así que el camino más rápido es vuelo a Ventormenta, barco a Auberdine y barco a
  Menethil. En línea recta solo se anda hasta 300 yd del grafo; un punto fuera de la malla (en el mar) anda recto
  con penalización. Ver [docs/TRAVEL.md](docs/TRAVEL.md), «Andar».
- **Ni por las sierras entre zonas.** La malla deja subir casi cualquier ladera, y el grafo de andar cruzaba de Elwynn a
  Las Estepas Ardientes, de Dun Morogh a La Garganta de Fuego o de Mulgore a Desolace: con la guía arreglada, el brujo
  gnomo de Villa Oscura recibía «anda 6005 yd a Thelsamar» por las Estepas, La Garganta y la puerta cerrada de Loch Modan.
  `tools/walk_zones.py` quita del grafo las aristas entre dos zonas sin camino de verdad (revisión propia de Classic en
  `nav/data/walk_zones.json`; 1032 aristas en los Reinos del Este y 767 en Kalimdor). Ahora: «vuela a Forjaz » a pie»
  (2929 yd por el túnel). El norte y el sur de los Reinos del Este ya no se tocan a pie (tranvía o vuelo).
- **Un maestro de vuelo sin descubrir al lado sirve para despegar.** En Villa Oscura sin ese nodo, el planificador mandaba
  andar 1602 yd hasta Lakeshire para volar; ahora, a menos de 400 yd de la salida, cuenta con hablarle (se aprende) y volar
  desde él a los nodos conocidos. Nunca se vuela hacia un nodo desconocido. El caso del jugador hacia Menethil: 888 s
  (antes 1142 s).
- **La guía ya no te manda a volar a un nodo que no tienes.** Un brujo gnomo del 21 que se había saltado Thelsamar veía
  «Vuela a Thelsamar» al llegar a Los Humedales (y de ahí a Menethil por Forjaz). Ahora los pasos de la guía pueden llevar
  los filtros `if = { fp = ["8"] }` (solo con ese nodo de vuelo conocido) y `if = { nofp = ["8"] }` (solo sin él); el motor
  los reevalúa al abrir un maestro de vuelo. Los pasos de ir a pie y coger Forjaz y Thelsamar son ahora para todas las
  razas (se dan por hechos solos si ya los tienes).
- Mismo arreglo en Costasur (Monasterio), Gadgetzan, el Nido Aguileño y la Vigilia de Morgan, con su camino a pie.
- **La flecha ya no te saca por el piso equivocado.** Sin la altura del jugador (el cliente no la da), los caminos a
  pie salían de cualquier piso de la celda y llegaban a cualquiera: desde el maestro de vuelo de Forjaz la ruta salía
  de la cima de la montaña y cruzaba la roca en línea recta, desde las Ruinas de Lordaeron salía bajo tierra y hacia la
  Mina Abisal acababa en la colina de encima (y «Has llegado» saltaba allí). Ahora la salida usa el piso del camino que
  venías siguiendo o, si no, si estás bajo techo (`IsIndoors`): fuera, el piso de arriba; dentro, los de debajo. La
  llegada usa la altura del paso de guía (nueva `data/heights.json`, de las apariciones de forever-db; campo opcional
  `z` en los pasos). Si con esas pistas no hay camino, se pide otro sin ellas.
- **«Has llegado» mide por el camino:** con un camino a pie, solo llegas cuando lo que queda de camino cabe en el radio,
  no cuando estás encima en línea recta (la mina de debajo, el otro lado de un muro).
- **Al final de un camino que no llega al objetivo** (objetivo fuera de la malla) la flecha apunta recta a él con el
  motivo «fin del camino», en vez de «Ruta a pie 0 m» girando sobre ti.
- **Varios objetivos de módulos a la vez** (buscador, raros, mazmorras, profesiones, instructor): gana el último que
  pusiste, no uno al azar. Refrescar el mismo punto no le quita la flecha a otro.
- **Puntos de ruta (`wps`):** si llegas a uno posterior por otro lado, la flecha salta a él; avanzan aunque la flecha esté
  oculta (opción apagada, oculta en combate o por las reglas de visibilidad), y el punto por el que ibas se guarda por paso: un `/reload`,
  un desvío o un recálculo de la guía ya no la devuelven al primero. Los puntos manuales también se borran al llegar con
  la flecha oculta.
- Documentación: `docs/NAV.md` decía que se soltaba el paquete de caminos del otro continente al cambiar de continente;
  no es así (se quedan los dos cargados, sin `/reload`). Nueva sección 8.6 sobre los pisos.

### Añadido
- `addon/Senda/Data/TravelWalk.lua` (222 KB): el grafo de andar de Reinos del Este y Kalimdor (nodos por región de sector,
  cada lugar del planificador, aristas con yardas reales y la matriz exacta entre lugares), desde `data/travel/walk_<c>.json`.
- `senda-nav walkgraph` (lo genera desde los paquetes HPA\*), `senda-nav bake --skip <clases> --block <fichero>` (malla de
  andar sin trepar paredes y sin el suelo revisado de `nav/data/walk_blocks.json`: la sierra norte de Dun Morogh) y
  `senda-nav zprof` (depuración).
- `tools/walk_zones.py` y `nav/data/walk_zones.json` (zonas y caminos entre ellas, por continente); cada nodo del grafo de
  andar guarda su zona (`zone`) y `tests/test_travel.py` comprueba que no queda ninguna arista entre zonas sin camino.
- Simulador: `travel-focus` (los tres personajes de referencia a Auberdine, Theramore y Costasur) y `fpf-e2e` (el caso del
  jugador con la guía y los marcos de mapa reales de forever-db).
- Simulador: escenario `travel-walk` (el caso del brujo gnomo, el túnel de Loch Modan, Elwynn - Páramos de Poniente, sin
  andar por el mar, fuera de la malla, rebanadas). Cambian con las yardas reales: Ventormenta - Auberdine 428 → 457 s y dos
  casos de la piedra de hogar (docs/TRAVEL.md).
- `tools/audit_guides.py` comprueba que cada paso `fly` de las tres guías va a un nodo ya conocido en ese punto
  (`fly-unknown-node`; aviso en las de la Horda). Filtros `fp` / `nofp` en `schema/section.schema.json`,
  `tools/validate.py`, `docs/ARCHITECTURE.md` y `docs/ROUTE-AUTHORING.md`. Simulador: escenarios `fpf-a`, `fpf-b`, `fpf-c`.
- `python tools/build.py --refresh-heights` (`tools/heights.py`) y comprobación de `data/heights.json` en
  `tools/validate.py`.
- Simulador: escenarios `arrow-prio`, `arrow-wps`, `arrow-wps-reload`, `arrow-floor`, `arrow-arrive-path` y
  `arrow-pathend`; `tests/navsim` comprueba los tres casos de pisos con los paquetes reales y sin alturas.

## [0.8.0] - 2026-11-13

### Añadido
- **Profesiones reales:** la pestaña Profesiones enseña todas las profesiones que tu personaje tiene aprendidas
  (principales, secundarias y de recolección), cada una con su tramo, qué fabricar, las fabricaciones esperadas que
  quedan, el material que falta (bolsas + banco), los colores de la receta, dónde se aprende, el rango siguiente y el
  instructor de tu facción que lo enseña (el más cercano, con flecha). Si te falta una principal, recuerda la de tu
  clase y por qué (brujo y mago: Sastrería + Encantamiento; druida: Herboristería + Alquimia, con los números).
- **Rutas calculadas con datos reales** para Alquimia, Herrería, Encantamiento, Ingeniería, Peletería, Sastrería, Cocina y
  Primeros auxilios (`tools/gen_professions.py`, [docs/PROFESSIONS.md](docs/PROFESSIONS.md)): recetas, colores, materiales
  y nombres de las tablas del cliente de Forever; habilidad de aprendizaje de las listas de instructor de Forever;
  instructores por rango y bando con coordenadas; la ruta de menor esfuerzo esperado de 1 a 300 con los pasos «entrena
  el rango siguiente». Frente a Polestar: 49 fabricaciones menos en Sastrería, 108 en Ingeniería, y menos esfuerzo en
  todas.
- La ventana del instructor resalta las recetas de tu ruta que ya puedes aprender.
- `tools/fetch_wago.py` (tablas del cliente con build fijado) y comprobaciones de rutas de profesión en `tools/validate.py`.
- Simulador: escenarios `prof-warlock`, `prof-mining`, `prof-druid`, `prof-cap`, `prof-none` y `prof-trainer`.
- **Recolección y pesca en tu ruta.** La pestaña Profesiones enseña, para Herboristería, Minería, Desuello y Pesca (las que
  hayas aprendido), en qué zonas de tu guía sigue subiendo la profesión desde donde estás, con su estado: «sube bien»,
  «va lento», «ya no sube nada: cambia de zona», «los nodos están en rojo (pide N)» y, en la pesca, «pierdes peces».
  Además, la mejor zona para tu banda de habilidad con flecha, y el aviso del rango siguiente.
- Rutas de Minería, Desuello y Pesca (no existían) y de Herboristería rehecha: un tramo por 25 de habilidad con las
  zonas de mayor densidad de nodos que aún suben (reglas de Classic: naranja/amarillo/verde/gris) y las recogidas
  esperadas. Todo generado por `tools/gen_gathering.py` desde el cliente de Forever, forever-db y los datos de
  Polestar (`tools/fetch_wago.py` baja las tablas del cliente con la build fijada). Método y comparación con Polestar en
  docs/PROFESSIONS.md, «Recolección».
- Instructores de recolección y pesca de cada bando, con coordenadas (de las listas de Forever vía Polestar).
- docs/TESTING-INGAME.md: lista de profesiones para el brujo gnomo (instructores de Forjaz, pestaña, instructor, flecha).

### Corregido
- Las rutas de Sastrería, Encantamiento y Alquimia venían de guías de Classic: Forever bajó unos 25 puntos los colores
  de casi todas las recetas y había tramos con recetas ya grises (30 puntos sin cubrir en Alquimia, 18 en
  Encantamiento).
- Aprendiz se entrena a cualquier nivel en Forever (no a 5). El Artesano de Alquimia del druida es Kylanna Windwhisper
  (Feralas), no Ainethil.
- Herboristería, Minería y Desuello ya no avisan de «pide nivel 10/20/35» para Oficial, Experto y Artesano: en Forever esos
  rangos piden solo habilidad (50, 125, 200).

## [0.7.0] - 2026-11-13

### Añadido
- **Auditoría de datos de las guías** (`tools/audit_guides.py`, en `python -m unittest`): cada paso de las guías del
  brujo gnomo, el mago humano y el druida elfo de la noche contra forever-db y sus correcciones (PNJ, quién da y
  recibe, coordenadas, raza y clase, requisitos, niveles, orden). Informe en [docs/AUDIT.md](docs/AUDIT.md).
- forever-db se lee con sus correcciones (`corrections/*.json`) y las de Senda (`data/corrections/`).
- **Por qué toca cada paso:** la descripción del paso (pasa el ratón por encima) dice la experiencia, el tiempo y lo que
  desbloquea (por ejemplo «+3.144 XP · ~2,2 min · 2,8× la media del tramo»). Con la opción «Mostrar por qué bajo el
  paso» (apagada por defecto, para no cargar el HUD) sale además en una línea tenue bajo el texto.
- Pareja: «va por delante» ya no cuenta los pasos de misiones que alguno de los dos ha saltado (mensaje nuevo `2K`).
- Prueba sin luacheck: `tests/test_lua_syntax.py` compila el Lua con luac/luajit si están, y si no usa un analizador
  léxico propio que comprueba bloques y cadenas.
- **Métricas en la web** (`metricas/`, `tools/site_metrics.py`): por guía, misiones, horas estimadas, XP por hora,
  pasos verificados y sin verificar, cobertura de fuentes y opcionales/descartadas; estadísticas de la malla de
  navegación (rutas halladas, tiempo de fotograma); cobertura de nombres del juego y de búsqueda; y los últimos cambios.
  En español con interruptor a inglés, tema claro/oscuro y sin recursos externos.
- **Diario de mazmorras:** pestaña «Mazmorras» con las mazmorras de tu bando por nivel. Para cada una: niveles (entrada,
  recomendado y de sus misiones), dónde está la entrada y la piedra de encuentro con un botón para la flecha (el
  planificador de viaje calcula el camino más rápido y la ficha lo enseña), los jefes, sus misiones para tu personaje
  (las de tu guía primero y marcadas, las hechas, las que llevas y las previas que te faltan; clic para ir a quien la da)
  y el botín que mejora a tu build (felino u oso del druida, Aflicción del brujo, Escarcha del mago), con lo que gana
  frente a lo que llevas. Datos: forever-db, tablas del cliente y ForeverLevelingBiS (MIT). `/senda mazmorra [nombre]`.
- En un paso de mazmorra de la guía, el texto del HUD termina en «Ver en Mazmorras »»: un clic en el paso abre su ficha
  (sin línea nueva en el HUD). Al entrar en la instancia la flecha a la mazmorra se quita.
- `tools/gen_dungeon_journal.py` (`data/dungeons/journal.json`) y `Data/Dungeons.lua` (~85 KB, se descodifica al abrir el
  diario y fuera de combate). Simulador: escenarios `dungeons-tab`, `dungeons-druid`, `dungeons-arrow` y `dungeons-hud`.
- **Buscador de objetos** ([docs/LOOKUP.md](docs/LOOKUP.md)). Los datos (5.623 objetos de las guías: botín, vendedores,
  recompensas y objetivos de misión) viven en un addon aparte, `Senda_Lookup`, que no se carga hasta que lo necesitas y
  nunca en combate. Esto lo aprovecha en tres sitios:
  - **Una línea en la descripción** de los objetos de las guías: «Senda: lo sueltan X y Y en Dun Morogh», «Senda: lo vende
    X en...», «Senda: recompensa de «misión»», «Senda: para «misión»». Una sola línea y solo si se sabe; se apaga en
    Opciones > Objetos.
  - **`/senda objeto <nombre, número o enlace>`:** de dónde sale (botín con zona y probabilidad, vendedores, recompensas y
    objetivos). `/senda objeto señalar <objeto>` apunta la flecha a la fuente más cercana y `/senda objeto borrar` la quita.
    Busca sin tildes ni mayúsculas y también por el nombre en inglés.
  - **Pestaña «Objetos»** del panel: caja de búsqueda, resultados con «Señalar» y el detalle de cada uno.
- **`/senda volcar` también guarda los nombres de los objetos del buscador** (`litem`): los que el cliente ya conoce, sin
  pedir nada al servidor, y con `/senda volcar objetos` los que faltan. `tools/import_names.py` los pasa a
  `data/lookup/locale/<idioma>/` y dice cuántos objetos del buscador tienen ya nombre en tu idioma.
- El paquete lleva cinco carpetas (`Senda_Lookup` es la nueva); `install-dev` copia las cinco.
- Simulador: escenarios `lookup-tip`, `lookup-slash`, `lookup-point`, `lookup-search`, `lookup-tab`, `lookup-en` y
  `lookup-dump` (este último pasa lo guardado por la herramienta de importación real). Tests de Python en `tests/test_lookup.py`.
- **La Horda:** una guía 1-60 por raza para cualquier clase (orco y trol en Durotar, tauren en Mulgore, no-muerto en
  Claros de Tirisfal y Skyborne en la isla de Zephras) con la ruta común 12-60 de Polestar pasada por el filtro de
  eficiencia de Senda: unas 100 misiones menos y unas 22 h estimadas menos; textos en español con fichas, `why` en las
  misiones que se quedan y el motivo en las opcionales. Pasos de entrenamiento por clase con los hechizos del
  instructor de Forever. Ver docs/ROUTE-HORDE.md.
- Ficha `{area:N}` en los textos: el cliente pone el nombre de la subzona («El Cruce», «Rémol»).
- `tests/test_locale_keys.py`: cada cadena de `Core/Locale.lua` en español y en inglés, cada `L.CLAVE` del código
  definida y ningún carácter que las fuentes del juego no tienen en el Lua escrito a mano.
- [docs/TESTING-INGAME.md](docs/TESTING-INGAME.md): lista corta para probar la versión en el juego y cómo informar.

### Corregido
- «Saltar esta misión» en un aviso como el de Lago Blackwrench (1717) saltaba toda la cadena del súcubo: los avisos
  son migas de pan, no requisitos, y van aparte en `Guides/Followups.lua`. Igual con «The Slaughtered Lamb» (1715).
- El druida pedía una versión antigua de «Crown of the Earth» (934) que no existe; el Gran Espíritu del Felino estaba
  4 puntos de mapa al este de donde aparece; el mago se quedaba esperando a coger en la Torre de Azora la misión del
  libro, que da Garion Wendell.
- El gnomo repetía la cadena de Farsen en Loch Modan y nunca entregaba la cerveza a Kadrell; Kadrell (patrulla) se
  marca en su aparición de forever-db.
- Misiones obligatorias detrás de una previa opcional (291, 3905, 14, 5742, 5781 pasan a opcionales; 106, 922 y
  4761 a obligatorias).
- Lago Blackwrench: el paso dice que está abajo, a ras del suelo de la Caverna Abandonada.
- Tras subir al tranvía o al barco (un salto de más de 400 yardas) la flecha vuelve a pedir ruta a pie al momento, sin
  esperar los 20 s de reintento de la ruta que había fallado.
- `tools/enrich.py` borraba el nivel de los pasos de entrenamiento de la Horda de las clases sin
  `data/knowledge/<clase>/spells.toml` (guerrero, cazador, pícaro...): ahora lo toma del consejo del paso («hasta el
  nivel 12»). Las guías de la Horda pasan `enrich --check` (niveles de QuestieDB y `reqskill` de las misiones de oficio).
- La línea del buscador de objetos ya no escribe campos en `GameTooltip` (podía contaminarlo): usa una tabla aparte.
- Métricas de la web: faltaba el tipo de nombre «Lugares» (`{area:N}` de la Horda) y la página no se generaba.

### Cambiado
- La barra de pestañas del panel junta un poco los botones cuando hay muchas, para que siempre quepan.
- Los archivos de la Horda solo se cargan para personajes de la Horda; la Alianza no cambia.
- `tools/route_score.py` calcula las bandas por facción.

## [0.6.1] - 2026-11-12

### Añadido
- **Ruta en el minimapa:** una línea verde con el camino a pie que sigue la flecha (opción «Dibujar la ruta en el
  minimapa», activada). Respeta el minimapa giratorio y los cuadrados. En el suelo del mundo no se puede dibujar: el
  juego no da esa función a los addons.
- **La flecha dice siempre qué está haciendo:** «Ruta a pie» (verde) o «Línea recta» (gris) delante de la distancia y,
  si va recta, el motivo debajo (calculando la ruta, volando, en una instancia, en combate, sin caminos...). Con ruta,
  una flechita dorada en el borde marca la línea recta al destino.
- En el Tranvía subterráneo la flecha dice «Tranvía: súbete y baja en Forjaz/Ventormenta» en vez de «Posición no
  disponible aquí».

### Cambiado
- **Flecha más suave:** apunta a un punto 15 yardas por delante en el camino (no salta en cada recodo) y el giro se
  suaviza; girar el personaje sigue siendo inmediato.
- **Cambiar de continente ya no pide /reload:** los datos de caminos de un continente se quedan cargados toda la sesión.
- El viaje nombra dónde embarcar: «ve al tranvía de Ciudad de Ventormenta», «ve al maestro de vuelo de...», etc.

### Corregido
- La línea «Camino más rápido» del HUD pisaba el consejo del paso: las líneas del paso se colocan ahora por posición
  y los iconos en línea miden lo mismo que el texto.
- La flecha «→» salía como un cuadro (las fuentes del juego no la tienen): ahora «»» en todo el addon.
- Un paso de una cadena se da por hecho si ya tienes una misión posterior de esa cadena (por ejemplo, el aviso de
  Lago Blackwrench cuando ya llevas «Devoradora de almas» de Gakin).

## [0.6.0] - 2026-11-12

### Añadido
- **La flecha sigue caminos reales.** Si el objetivo está en tu continente, la flecha apunta al siguiente punto de
  un camino a pie calculado sobre el terreno del cliente de Forever (`Senda_Nav`, docs/NAV.md) y enseña la
  distancia «a pie» con una marca «ruta». Recalcula si te sales del camino (como mucho cada 5 s) o cambia el
  objetivo, también en modo cadáver. Va recta mientras calcula, sin datos, volando, en taxi, en barco y en
  mazmorras. Los datos se cargan fuera de combate, solo los de tu continente, y se suelta el otro al cambiar.
  Opción «Seguir caminos reales» (activada).
- El paquete de la versión lleva cuatro carpetas (`Senda`, `Senda_Nav`, `Senda_Nav_EK`, `Senda_Nav_Kalimdor`), cada
  una con su licencia; `install-dev` copia las cuatro.
- Simulador: escenarios `nav-*` con el `Senda_Nav` real y paquetes sintéticos.
- **Planificador de viaje** (`Modules/Travel.lua`, datos de `data/travel/` compilados a `Data/Travel.lua`). Si el destino de la flecha está en otro continente o a más de 800 yardas, el HUD enseña una línea «Camino más rápido: vuela a X (3 min) → barco a Y → a pie» y la flecha apunta al embarque del primer tramo. Usa solo lo que ya conoces: vuelos descubiertos de tu facción, barcos, zepelines, el tranvía, portales, teletransportes de clase (con su reactivo) y la piedra de hogar (con su enfriamiento y la posada vinculada). En un maestro de vuelo marca en el mapa el nodo al que hay que volar, sin volar por ti. `/senda viaje [recalcular]` y una opción para apagarlo.
- Simulador: escenarios `travel`, `travel-hud`, `travel-taxi`, `travel-lock`, `travel-druid` y `travel-mage`; el mock ya tiene `C_TaxiMap.GetTaxiNodesForMap`, enfriamientos de objetos y hechizos y `C_Map.GetAreaInfo`.
- **Alertas de raros** (`Modules/Rares.lua`, datos de `data/rares/` compilados a `Data/Rares.lua`, 346 raros con aparición): una línea en el HUD, «Raro cerca: {npc:N} (nivel A-B) · Señalar», que apunta la flecha al raro. Detecta por viñetas del minimapa (barrido como mucho cada 2 s, en tandas, nunca en combate), placas de nombre, objetivo y ratón encima; rebote de 3 s por unidad, enfriamiento por raro, ignora muertos, retiene el aviso en combate y lo suelta al salir si sigue vivo; nada en mazmorras ni con todo oculto. Opciones en la sección «Raros» (activar, solo ±3 niveles, sonido) y `/senda raros`. Ver `docs/RARES.md`.
- **Equipo según tu build** ([docs/GEAR.md](docs/GEAR.md)). Pesos por build y tramo de nivel con fuente
  (`data/knowledge/<clase>/weights.toml`): Aflicción, Escarcha y Feral (felino para subir, oso para élites; se cambia en
  la pestaña Equipo o con `/senda equipo oso | felino`). Se aplican en la recompensa de misión recomendada, en el aviso
  de las bolsas («Ponte X: mejora un 12% para tu build»), en una línea de la descripción de los objetos («Senda: +12%
  para tu build») y en la pestaña Equipo. Nunca recomienda lo que tu clase no puede llevar; un arma que aún no sabes
  usar solo se propone si no hay nada que ponerte ya, y con el motivo.
- **Mejor pieza conocida para tu tramo** en la pestaña Equipo (`bis-forever.toml`, generado por `tools/gen_bis.py` desde
  ForeverLevelingBiS v0.12.0-beta, MIT, a través de Polestar).
- **Pestaña «Aparte»** con tres bloques coordinados; la flecha sigue la ruta o el desvío, nunca los dos, y el HUD solo añade una línea cuando hay algo útil justo ahí.
  - **Para después:** el reloj del HUD y el clic derecho en un paso («Dejar para después») aparcan la misión y las que dependen de ella, o la cadena de clase entera (súcubo, manáfago, corcel nefasto e inferno del brujo; misiones y teletransportes del mago; formas del druida), sin darla por hecha ni saltada. Te la recuerda («Pendiente aquí: X · Retomar») cuando estás en el mapa de alguno de sus pasos, cerca del siguiente o al llegar al nivel de su pista («cuando la ruta vaya a Vallefresno (22-26): desde Astranaar se baja a Los Baldíos»).
  - **Reserva de XP:** misiones que puedes coger ya en tu mapa y en los vecinos (las opcionales, las que el filtro de eficiencia quitó y las de las rutas de Polestar que no van en la tuya), por XP por minuto y cercanía. Se ofrece cuando el siguiente paso te pide más nivel («Te faltan N XP para el siguiente paso: estas misiones te los dan en ~M min»), cuando la ruta no tiene nada para ti en ese mapa o con «Más misiones aquí».
  - **Desvío activo:** lo que coges de la reserva y lo aparcado que retomas se convierte en una sub-ruta (coger, completar, entregar) que siguen el HUD y la flecha; al acabar o cancelar vuelves a la ruta donde la dejaste, y lo hecho cuenta para la ruta. Sobrevive a una recarga.
- `python tools/build.py --refresh-reserve` (`tools/reserve.py`) genera `data/reserve.json` y el build lo compila en `Guides/Reserve.lua`. Campos de sección nuevos: `parkable`, `later_hint`, `later_level`, `later_map`.
- Simulador: escenarios `park`, `park-reload`, `park-quest`, `park-druid`, `reserve`, `detour-route` y `detour-reload`.

### Cambiado
- **El HUD enseña como mucho una línea extra.** Raro cerca, camino más rápido y Aparte comparten un hueco, por
  prioridad (raro > viaje > Aparte); la ruta principal se queda limpia. Escenario `hud-slot` del simulador.
- El planificador de viaje también propone camino hacia el instructor que señala la pestaña de hechizos.
- La reserva de XP (`data/reserve.json`) se rehízo sobre las rutas fusionadas del brujo, el mago y el druida.

## [0.5.0] - 2026-11-12

### Añadido
- **Nombres en español sacados del juego.** Los textos de las guías pueden llevar fichas (`{quest:155}`, `{npc:467}`, `{item:N}`, `{spell:N}`, `{map:N}`, `{obj:N}`) y Senda pone el nombre exacto del cliente al mostrarlas; mientras el juego no responde usa un respaldo compilado de `data/locale/`. El prototipo de Teldrassil ya las usa.
- **Seguimiento por objetivo:** el HUD muestra los contadores de cada objetivo («Sable de la noche joven muerto: 6/7») con el texto del juego y los actualiza al momento, también en combate. Un paso con `obj` se completa en cuanto se cumple su objetivo, aunque la misión siga abierta.
- **Colocación desde el registro de misiones:** al entrar, al recargar y al cambiar de guía, Senda mira qué misiones has entregado, cuáles llevas y cómo van, y te sitúa en el paso que toca. Si pierdes las SavedVariables o juegas un rato sin el addon, la guía ya no se queda atrás. Solo adelanta, respeta lo que saltaste y no mueve un paso al que volviste a propósito.
- **Saltar una misión y todas las que dependen de ella:** clic derecho en un paso de misión del HUD, «Saltar esta misión». Se saltan sus pasos y los de las misiones que la necesitan (requisitos de forever-db, compilados en `Guides/Followups.lua`), en todas tus guías, con un aviso «Saltada «X» y N misiones que dependen de ella · Deshacer». El menú también restaura todas las saltadas.
- **Informe de errores:** el botón del bicho del HUD y `/senda informe` abren una ventana con tu texto libre y el contexto (guía, paso, posición, nivel, raza y clase, versión de Senda, build y idioma del cliente, otros addons, estado de las misiones del paso y los últimos 20 errores de Lua de Senda), sin nombre de personaje ni de reino. «Copiar» selecciona el informe y sale un enlace de GitHub con título y cuerpo corto (menos de 2000 caracteres).
- **`/senda volcar`:** pide al juego los nombres de todas las misiones, PNJ, objetos, hechizos y zonas de las guías y los guarda en `SendaNamesDB` (poco a poco, nunca en combate; se puede parar y retomar). `tools/import_names.py` los pasa a `data/locale/` y avisa de los nombres que cambian entre parches.
- **Pareja sincronizada** (`Modules/Party.lua`). Si tu compañero de grupo también usa Senda, vuestros addons se hablan por mensajes ocultos (solo al grupo, nunca en banda, y nada hasta que el otro contesta al saludo): cuentas de cada objetivo, en qué paso va cada uno y qué misiones ha entregado cerca de tu paso.
  - Línea de pareja en el HUD: «Lunaria va 2 pasos por delante». Se cuentan solo los pasos de los dos: un paso solo de brujo entre medias no descuadra.
  - **Esperar al compañero:** si terminas un objetivo que a él le falta, el paso no avanza ni la misión se entrega sola: «Espera a Lunaria: le falta 3/8», con el botón «Seguir sin él». Si se desconecta más de 2 minutos, se deja de esperar.
  - **Pedir que salte a mi paso** (pestaña «En pareja» o `/senda pareja saltar`): al otro le sale una ventana para aceptar o rechazar; sus pasos de clase no se saltan.
  - `/senda pareja` (dónde va), `/senda pareja seguir` y `/senda pareja debug` (envíos, último resultado y mensajes oídos). Dos opciones nuevas en la sección «Pareja».
  - Los nombres de los compañeros solo se muestran: nunca se guardan.
- Simulador: modo de dos jugadores (`duo` en `tests/wowsim/run.js`) con dos clientes que se pasan los mensajes de addon y fallos de envío simulados (`Sim.addonFault`).
- **Grabador de partidas (esquema 2),** apagado por defecto (Opciones o `/senda grabar on|off|estado|limpiar|rastro on|off`): pasos con su motivo, XP, combate, ausencias, muertes, misiones y un rastro de posición opcional, en fragmentos compactos con tope de 4 MiB. No guarda nombres de personaje ni de reino, chat ni compañeros de grupo (solo si vas en pareja o no). Ver `docs/RECORDING.md`.
- `tools/ingest_recording.py` (tiempo activo por paso con AFK a cero y huecos de 5 min como máximo, XP/hora, yardas, muertes) y `tools/route_report.py` (medido frente a estimado por paso, pasos a más del doble, error mediano; exporta rastros a `data/recordings/traces/`).

## [0.4.1] - 2026-11-12

### Corregido
- **Listas del instructor de brujo, mago y druida regeneradas con los datos reales de Forever:** niveles, rangos y costes de los instructores de Forever (vía Polestar, GPL-3) y nombres en español leídos del propio cliente esES. Faltaban las subidas de rango (p. ej. al 20 el brujo entrena Descarga de las Sombras rango 4, Inmolar rango 3 y Cauce de salud rango 2).
- Ids de Classic que tu cliente no reconoce: Maldición de los elementos ya no sale como «#1490» (en Forever es 440892); Revivir del druida en las barras usaba el rango 5 desde el nivel 12.
- **Hechizos que tu build no usa, marcados como opcionales** con su motivo, y fuera de los pasos de entrenar: brujo (Lluvia de fuego, Maldición de los elementos, de debilidad y de temeridad, Drenar maná, Captar demonios, Detectar invisibilidad, piedras de fuego y de hechizos, Subyugar demonio, Llamas infernales, Fuego de alma, Custodia de las Sombras, Terror de fatalidad, Ritual de condena), mago (Empapar y Amplificar magia, custodias, portales salvo el de Ventormenta, Polimorfia: vaca, Resplandor Arcano) y druida (Calmar animal, Tranquilidad, Huracán).
- La pestaña de hechizos ya no dice «entrena ya» en los opcionales ni en los de mascota o misión.
- La tarjeta de nivel muestra el coste real de lo que toca entrenar.

## [0.4.0] - 2026-11-12

### Cambiado
- **Licencia GPL-3.0.** Senda pasa de MIT a GPL-3 para poder incorporar datos y código de Polestar. Las versiones hasta la 0.3.5 siguen siendo MIT. Créditos en `THIRD_PARTY.md`, que viaja dentro del paquete junto con la licencia.
- Botón del minimapa: clic, panel; clic derecho, menú (panel, HUD, flecha, ocultar todo); Mayús+clic, flecha; Ctrl+clic, ocultar o mostrar todo.

### Añadido
- **Aceptar y entregar solo** las misiones que pide la guía (las del paso actual y los siguientes). Mayús lo evita; si hay que elegir recompensa, la ventana se queda abierta. Se puede apagar en Opciones.
- **Misiones con tiempo:** cuenta atrás en el HUD y avisos a los 5 y 1 minutos.
- **Misiones fallidas o abandonadas:** el HUD lo dice, la flecha vuelve a quien te la dio y puedes volver a cogerla o saltarla.
- **Avisos de escolta:** «si el PNJ no está, alguien la está haciendo; espera a que reaparezca» (p. ej. el Traidor Defias).
- **Ocultar en mazmorras** (activado por defecto) y `/senda hide` para ocultar todo.
- **Tarjeta al subir de nivel:** hechizos nuevos, coste total, si te llega el dinero y dónde entrenar, con botón para la flecha.
- **Renovar rangos en las barras:** cuando aprendes un rango nuevo, un botón cambia los rangos viejos de tus barras (nunca en combate; no toca macros ni objetos).
- **Prototipo de Teldrassil importado de Polestar** para compararlo con nuestra guía: `/senda guide nightelf-druid-ps`. Nunca se elige solo.
- Herramientas: base de datos abierta forever-db (`tools/foreverdb`, `tools/fetch_foreverdb.py`) como alternativa a QuestieDB, también en GitHub Actions; importador de rutas de Polestar (`tools/import_polestar.py`); datos de viaje, raros, mazmorras y objetos (`data/travel`, `data/rares`, `data/dungeons`, `data/lookup`) para las próximas versiones.

## [0.3.5] - 2026-11-12

### Cambiado
- Brujo: Dolor abrasador pasa a opcional. La build de Aflicción no lo usa (es de Fuego, gasta mucho maná y le quita el enemigo al Abisario), así que el paso del 18 solo pide Crear piedra de alma, y ni el asesor ni el instructor lo cuentan como pendiente.
- Nuevo campo `optional` en los `[[train]]` del conocimiento.

## [0.3.4] - 2026-11-11

### Corregido
- Lecciones de campamento «Camping 101» de oficio (Herboristería, Alquimia, Primeros auxilios, Sastrería, Encantamiento): el PNJ solo las ofrece si ya sabes la profesión. Las tres guías aprenden ahora el oficio antes de coger la lección. Brujo: la de Sastrería se coge al volver a Kharanos y se entrega en la segunda visita a Forjaz. Mago: la de Encantamiento se coge al volver a Villadorada; la de Sastrería sale de la ruta, porque no se vuelve a Vega del Este.
- Nuevo campo `reqskill` (lo rellena `tools/enrich.py` desde QuestieDB): si no tienes la profesión al rango pedido, el paso de coger se pasa solo en vez de quedarse atascado.

## [0.3.3] - 2026-11-11

### Corregido
- Las macros con condiciones (`#showtooltip`, `[mod:alt]`, `[@mouseover]`) se guardan con el icono de interrogación para que el juego muestre el icono del hechizo que se lanzaría en cada momento. Las macros SND_ ya creadas se corrigen solas al actualizarse.
- Brujo: Fuerza inmortal (16) confirmada en el juego; es respirar bajo el agua y queda como opcional.
- Coordenadas de Ventormenta de Woo Ping y Gakin en el conocimiento, en el marco de Forever.

## [0.3.2] - 2026-11-11

### Corregido
- «Qué hago» ya no recomienda Herboristería y Alquimia al brujo ni al mago: cada clase tiene su plan de profesiones (`prof_plan`); el del druida es Herboristería + Alquimia y el resto sigue con Sastrería + Encantamiento. Si aprendes otra profesión por tu cuenta, también se tiene en cuenta.
- El asesor y el instructor ya no cuentan como «sin entrenar» habilidades de la mascota (Sacrificio del Abisario) ni hechizos que se consiguen con misiones.
- El dinero se muestra con los iconos de oro, plata y cobre.

## [0.3.1] - 2026-11-11

### Corregido
- Los pasos de entrenamiento («Brujo: entrena lo del 18») ya no aparecen antes de tener el nivel: se aplazan como las misiones, el HUD muestra «Al nivel N» y al subir avisa «Ya puedes entrenar…» con un clic para ir al paso. `tools/enrich.py` calcula el nivel de cada visita al instructor a partir de los hechizos de la clase.

## [0.3.0] - 2026-11-11

### Añadido
- Guía **druida elfo de la noche 1-60**: Cañada Umbría, Teldrassil y Costa Oscura (1-20); viaje a los Reinos del Este, y ruta compartida de la Alianza desde Crestagrana.
- Misiones de clase del druida: forma de oso, Lunazarpa, Curar veneno, forma acuática, la cadena nueva de la forma felina de Forever (nivel 20), Torwa y las del final.
- Visitas al instructor de druida en toda la ruta compartida (Ventormenta o Claro de la Luna).
- Conocimiento de druida: tramos de nivel, talentos feral, hechizos, rotación por forma, macros, barras por forma, equipo, oro y profesiones (Herboristería y Alquimia, con rutas nuevas para ambas).
- Escenario del simulador: un druida elfo de la noche juega la guía completa.

### Corregido
- Ruta compartida: los pasos que solo tienen sentido si vienes de los Reinos del Este (cadena Defias, rutas de vuelo de Thelsamar) quedan filtrados por raza; el elfo de la noche tiene sus propios pasos para coger las rutas de vuelo de Forjaz y Thelsamar.
- `verify.py` ya no comprueba pasos que el filtro de raza o clase excluye de la guía.

## [0.2.0] - 2026-11-11

### Añadido
- Las misiones que piden más nivel del que tienes (exclamación plateada) se aplazan solas: la guía sigue con lo que puedes hacer y el HUD muestra «Al nivel N: misión».
- Al subir al nivel necesario, aviso en el chat y línea verde en el HUD «Ya puedes coger: …»; un clic te lleva a ese paso.
- Si saltas a mano una misión sin tener nivel, también se recuerda.
- La guía ya no te pide completar ni entregar una misión que no cogiste.
- `tools/enrich.py`: añade a los pasos el nivel mínimo de cada misión (`reqlevel`) desde la QuestieDB local.

### Corregido
- esES: «Marshal» se traduce «Alguacil» (Marris, McBride, Dughan).
- Crestagrana: los cazadores furtivos están en sus campamentos reales; aviso de que Evaluar la amenaza requiere el aviso del Guardia Parker.

## [0.1.0] - 2026-11-11

### Añadido
- Motor de guías paso a paso con detección automática (misiones, objetivos, hechizos, profesiones, objetos, piedra de hogar, rutas de vuelo, nivel, posición).
- HUD con paso actual, siguientes pasos, progreso de objetivos e indicador de verificación de datos.
- Flecha propia con distancia, tiempo estimado y modo cadáver (sustituye a TomTom).
- Grabador de observaciones en partida para verificar datos.
- Guías de brujo gnomo y mago humano; conocimiento de clase migrado de BrujoGnomoGuia 4.1.0.
- Módulos: conocimiento, macros, profesiones, equipo, vendedores, instructores, desencantar, asesor, análisis, pareja y barras.
- Herramientas: validación, compilación de TOML a Lua, empaquetado y verificación con QuestieDB local.
- Harness de IA para vigilar fuentes, auditar los datos y proponer cambios mediante PR.
- Web de la guía en GitHub Pages.

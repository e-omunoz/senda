# Registro de cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Versionado [SemVer](https://semver.org/lang/es/).

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

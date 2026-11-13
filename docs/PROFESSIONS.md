# Profesiones

Cómo calcula y muestra Senda las rutas de profesión. Este archivo tiene una sección por tema; la de fabricación
(Sastrería, Encantamiento, Alquimia...) la escribe la rama de profesiones de fabricación. La de abajo,
**Recolección**, es autónoma.

## Recolección

Herboristería, Minería, Desuello y Pesca. Lo que las distingue de la fabricación: no gastan material, así que el
coste de una ruta es **dónde andas** y **cuántos nodos recoges**. El valor de Senda aquí es que te dice dónde
recolectar *en la ruta de tu guía* (donde ya vas a estar de todos modos) y te avisa cuando esa zona se queda atrás
(nodos en rojo) o te queda pequeña (todo gris).

### Archivos

| Archivo | Qué es |
|---|---|
| `tools/gen_gathering.py` | Genera todo lo de abajo. `python tools/gen_gathering.py` escribe; `--check` falla si algo está desactualizado; `--report` imprime la tabla de comparación. Mismas entradas, mismos bytes. |
| `tools/fetch_wago.py` | Baja del sitio wago.tools las tablas del cliente de Forever (build `1.60.1.70888`, producto `wowf`) a `.cache/wago` (ignorada por git). |
| `tools/gathering/node-abundance.json`, `beasts.json` | Datos de Polestar (GPL-3, ver THIRD_PARTY.md): nodos que mantiene cada zona a la vez y bestias desollables por zona. |
| `data/knowledge/general/professions-{herbalism,mining,skinning,fishing}.toml` | `[[route]]` (un tramo por 25 de habilidad, lo lee `Professions.lua`), `[[zone]]` (nodos por zona), `[[bracket]]` (mejores zonas por banda) y `[[trainer]]` (instructores por bando, con coordenadas). |
| `data/knowledge/general/gathering-route.toml` | `[[stop]]`: por guía y sección, nivel y mapas con nodos. |
| `addon/Senda/Modules/Gathering.lua` | La sección de solo lectura de la pestaña Profesiones. Una línea en `Professions.lua` (`P.ExtraNodes`) la engancha. |

### Modelo

- **Subida por nodo** (fórmula de Classic, que Forever no cambia que se sepa: todo queda `unverified`):
  un nodo de habilidad mínima `req` sube siempre mientras `habilidad < req + 25` (naranja, 100 %), el 75 % hasta
  `req + 50` (amarillo), el 25 % hasta `req + 100` (verde) y nunca después (gris). Por debajo de `req` está en
  rojo: no se puede recoger.
- **Habilidades mínimas**: las de Classic (Peacebloom/Silverleaf 1, Earthroot 15, Mageroyal 50 ... Black Lotus 300;
  Copper 1, Tin 65, Silver 75, Iron 125, Gold 155, Mithril 175, Truesilver 230, Thorium 245, Rich Thorium 275).
  Cada una de esas cifras existe en la tabla `Lock` del cliente de Forever (herboristería = cerradura 2, minería = 3;
  lo comprueba `tests/test_gen_gathering.py`). El cliente no dice qué objeto usa qué cerradura (esa tabla es del
  servidor), así que la asignación nodo a habilidad es de Classic. Forever añade `Poor Copper Vein`, `Wilted
  Peacebloom`, `Stunted Silverleaf` (habilidad 1) y, en Teldrassil, `Chunk of Amber` (sin cifras de cantidad:
  7 puntos de la ruta de Polestar, habilidad 1). Las hierbas nuevas (Marefoil, Demonsage, Death Lotus) no tienen
  datos: no entran.
- **Desuello**: una bestia de nivel `L` pide habilidad 1 (L <= 10), `(L-10)*10` (11-20) o `L*5` (>20). forever-db
  no trae el tipo de criatura: las bestias desollables por zona son la lista curada de Polestar; los niveles y
  las apariciones, de forever-db.
- **Pesca**: cada captura sube la habilidad por debajo de 75; después, una de cada `(habilidad - 50) / 25`
  (unas 1.300 capturas hasta 300). Una captura cuenta igual en cualquier agua: lo que cambia es que el agua pierde
  peces hasta la habilidad `full` de la zona (25 zonas de inicio, 75 las siguientes, 150, 225, 300; base de Classic
  + 95, tabla de Polestar). Oficial: instructor a habilidad 50 y nivel 10. Experto: libro (Old Man Heming, Bahía del
  Botín). Artesano: misión de Nat Pagle (Marjal Revolcafango). Todo sin verificar en Forever.
- **Rangos sin nivel de personaje**: Herboristería, Minería y Desuello piden solo habilidad para Oficial (50),
  Experto (125) y Artesano (200): las listas de instructor que Polestar capturó del servidor de Forever traen nivel 0
  y hay jugadores que entrenan Experto de Minería a 15 y Artesano de Desuello a 29. La tabla genérica de
  `Professions.lua` (niveles 10, 20, 35) valía para la fabricación y daba avisos falsos de «pide nivel»:
  `Gathering.lua` envuelve `Professions.State` para estas tres y deja la pesca como estaba.
- **Qué zona vale para una habilidad** `s`: `W(s)` = suma de (nodos a la vez x probabilidad de subida). Se ordenan
  por densidad `W / área del marco del mapa` (por cada 10^6 yardas^2) y se exige `W >= 6` subidas por barrido (si no
  llega ninguna, se listan las mejores). «Nodos a la vez» son las reservas de aparición de la base de datos de
  Forever (`up` en `node-abundance.json`), no todos los puntos donde un nodo puede salir. Solo cuentan zonas
  cuyo nivel mínimo no pasa de `habilidad/5 + 8`, y no se listan por banda las de Isla de Zephras (razas nuevas de
  Forever, y sus datos son apariciones sin reserva).
- **Coordenada central**: el punto del grupo más denso de nodos útiles (rejilla del 5 % de mapa, bloque 3x3,
  centroide ponderado). Las yardas de forever-db pasan a % de mapa con `tools/foreverdb`.
- **Recogidas esperadas** de un tramo `[a, b)`: suma, para cada punto de habilidad, de `1 / p`, con `p` la
  probabilidad media de subir de los nodos de la mejor zona que aún suben (se saltan grises y rojos).

### En tu ruta

`gathering-route.toml` toma de cada sección de cada guía su mapa y los mapas de sus pasos con coordenadas (los que
tienen al menos dos pasos). `Gathering.lua` cruza eso con los nodos de cada zona y tu habilidad actual:

- Lista, desde tu sección actual hacia delante, hasta cuatro zonas de tu guía con datos de esa profesión, cada una
  con su estado: **sube bien** (naranja + amarillo suficientes), **va lento** (casi todo verde), **ya no sube
  nada** (gris: cambia de zona), **los nodos están en rojo** (te falta habilidad; dice cuánta) y, en la pesca,
  **pierdes peces** hasta qué habilidad.
- «Mejor zona para tu banda» con botón de flecha (la coordenada central), filtrada por tu bando.
- Aviso de rango: «Entrena Oficial ya» a partir de la habilidad que pide, sin nivel de personaje.
- Solo para las profesiones que has aprendido; sin ninguna, la pestaña no cambia. No toca nada protegido y no
  dibuja en combate.

Resumen de lo que sale para las tres guías (habilidad prevista = `5 x nivel`; «rinde hasta» = el final del
amarillo del mejor nodo que la zona mantiene en cantidad):

**Druida elfo de la noche** (Herboristería): Teldrassil (nivel 1, rinde hasta 100), Costa Oscura (11, hasta 150),
Páramos de Poniente (17, 150), Montañas Crestagrana (19, 150), Bosque del Ocaso (22, 175), Los Humedales (26, 200).
Minería: Teldrassil (Chunk of Amber, hasta 51), Costa Oscura (115), Bosque del Ocaso (175). Desuello: Teldrassil (51),
Costa Oscura (90), Páramos de Poniente (110), Bosque del Ocaso (150).

**Mago humano** (Herboristería): Bosque de Elwynn (nivel 1, hasta 65), Loch Modan (12, 150), Páramos de Poniente
(16, 150), Montañas Crestagrana (19, 150), Bosque del Ocaso (22, 175), Los Humedales (26, 200).

**Brujo gnomo** (Herboristería): Dun Morogh (nivel 1, hasta 65), Loch Modan (12, 150), Páramos de Poniente (16, 150),
Montañas Crestagrana (19, 150), Los Baldíos (20, 175), Vallefresno (20, 260).

Lo que esto dice en la práctica: en las zonas de inicio y Costa Oscura/Loch Modan ya ibas a estar, y rinden bien
hasta ~65-150; a partir del nivel 20 (habilidad ~100) la propia ruta te lleva a zonas que siguen rindiendo. Donde la
guía te saca a zonas sin nodos útiles (viajes, ciudades, mazmorras) no se lista nada: ahí ve a la «mejor zona».

### Comparación con Polestar y con la ruta anterior de Senda

Recogidas esperadas de 1 a 300 (Polestar: suma de los «Expect about N nodes» de sus pasos para el grupo del
elfo de la noche; Senda anterior: la suma de `n` de `professions-herbalism.toml`, que era una estimación del
autor sobre una guía de Classic; antes no había rutas de Minería, Desuello ni Pesca).

| Profesión | Senda ahora | Polestar | Senda antes |
|---|---:|---:|---:|
| Herboristería | 445 | 550 | 315 |
| Minería | 551 | 620 | sin ruta |
| Desuello | 447 | 440 | sin ruta |
| Pesca (capturas) | 1307 | 1300 | sin ruta |

Por qué difiere:

- **Herboristería**. Polestar pondera naranja 1, amarillo 0,6, verde 0,15 (pesos relativos, no probabilidades) y
  manda a una zona por tramo con nodos concretos; nosotros usamos las probabilidades de Classic (1; 0,75; 0,25) y
  la densidad de nodos a la vez de cada zona, y escogemos la mejor zona por banda de 25. Salen menos recogidas
  porque la zona elegida tiene más nodos que aún suben. La ruta anterior contaba 315 con tramos de 40-55 puntos y
  una `n` por tramo sin modelo detrás: las hierbas de 70 a 115 (Marregal, Brezospina, Alga estranguladora) se
  quedaban cortas en Costa Oscura y Loch Modan en cuanto se miran las cantidades.
- **Minería**. Igual criterio. Nuestro tramo más caro es 50-75 (80 recogidas): el cobre ya está en verde y el
  estaño no se puede recoger hasta 65, así que hay pocos nodos que suban de verdad; Polestar reparte esos puntos en
  tramos distintos y sale a 620 en total frente a nuestros 551.
- **Desuello**. Casi igual (447 frente a 440) porque ambos usan la misma lista de bestias y la misma regla de nivel.
- **Pesca**. Es la fórmula de Classic en los dos; no hay elección de zona que cambie las capturas (una captura
  cuenta igual en cualquier agua): solo qué agua no pierde peces.

Mejor zona por banda según el modelo (Alianza, herboristería): 1-50 Bosque de Elwynn; 50-125 Montañas Crestagrana;
125-150 Bosque del Ocaso; 150-225 Pantano de las Penas; 225-250 Tierras del Interior; 250-300 Pantano de las
Penas y Cráter de Un'Goro. Las demás profesiones y la Horda: `[[bracket]]` en cada archivo.

### Qué no se sabe (abierto)

- Todo `unverified`: probabilidades de subida, habilidades de los nodos y, sobre todo, las tablas de pesca. Una
  sesión grabada con el Grabador de Senda (docs/RECORDING.md) con skill-ups y nodos recogidos las confirmaría.
- Teldrassil: la cantidad de `Chunk of Amber` no se conoce (se usan los 7 puntos de la ruta de Polestar).
- Las hierbas nuevas de Forever (Marefoil, Demonsage, Death Lotus) y los nombres en español de los instructores
  (aquí van en inglés, como en el resto de Senda hasta que haya nombres traducidos).
- El desuello depende de una lista curada de bestias: si falta una bestia, esa zona rinde algo más de lo que dice.
- Los rangos sin nivel vienen de listas de instructor capturadas y de jugadores; si Forever los cambia, basta
  quitar el envoltorio de `Professions.State` en `Gathering.lua`.

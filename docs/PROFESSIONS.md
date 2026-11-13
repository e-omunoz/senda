# Profesiones: rutas calculadas con datos reales

La pestaña **Profesiones** sigue las profesiones que el personaje **tiene de verdad** (todas: principales,
secundarias y de recolección, leídas del cliente) y, para cada una, enseña el tramo actual, qué fabricar, cuántas
fabricaciones esperadas quedan, el material que falta (bolsas + banco), el rango siguiente y qué instructor de tu
facción lo enseña (el más cercano; botón de flecha). Si aún te falta una profesión principal, recuerda la de tu clase
con el porqué.

Las rutas de **Alquimia, Herrería, Encantamiento, Ingeniería, Peletería, Sastrería, Cocina y Primeros auxilios** no
se escriben a mano: las calcula `tools/gen_professions.py` con las tablas del cliente de Forever y las escribe en
`data/knowledge/general/professions-<prof>.toml`. Las de recolección (Herboristería, Minería, Desuello, Pesca) van
aparte; sin ruta, la pestaña enseña igual su progreso, el rango siguiente y el instructor.

## Por qué se rehicieron

Las rutas anteriores (Sastrería, Encantamiento y Alquimia) venían de un addon viejo y de guías de Classic
(Method.gg, wow-professions). **Forever bajó unos 25 puntos los colores de casi todas las recetas**: la Madeja de paño
de seda es amarilla a 110 y gris a 120 (Classic: 135 y 145); la de paño rúnico, 210 y 215 (Classic: 255 y 260). Con
los tramos de Classic había recetas ya grises en su tramo: la ruta anterior de Alquimia dejaba 30 puntos sin cubrir y
la de Encantamiento 18.

## Fuentes

| Qué | De dónde | Estado |
|---|---|---|
| Recetas, colores (amarillo = `TrivialSkillLineRankLow`, gris = `TrivialSkillLineRankHigh`, verde = la media), puntos por fabricación (`NumSkillUps`), materiales, herramientas, sitio exigido (yunque, forja, fuego; **rueca, telar o pozo lunar: fuera**), nombres esES, precios de vendedor | Tablas del cliente de Forever 1.60.1.70888 (wago.tools; `tools/fetch_wago.py` las baja a `.cache/wago`) | verificado |
| Habilidad a la que el instructor enseña cada receta y su precio | Listas de instructor capturadas del servidor de Forever (TrinityCore `forever`, release `forever-tdb-2026-10-14`), tal como las guarda Polestar | verificado |
| Habilidad vista en el juego o en grabaciones (Thick Leather 175, conjuntos de cuero 75...) y la corrección oficial del Tanning Rack (125) | `CHECKED_LEARN` y `HOTFIXES` de Polestar (`forge-data/src/professions/extract.rs`) | verificado |
| Receta de vendedor: habilidad del objeto de receta (`RequiredSkillRank`) | Tablas del cliente; que la vende un vendedor de la Alianza por oro: listas capturadas o compras de las guías de Polestar | verificado |
| Recetas que solo enseña la lista de instructor «de Classic» del servidor | Su habilidad se estima moviendo la de Classic tanto como Forever movió el amarillo (método de Polestar, que en 126 de 129 recetas comprobadas acierta) | **sin verificar**: el tramo lo dice («comprueba en el instructor») |
| Instructores por profesión, rango y bando (quién enseña Experto y Artesano) | Lista curada de Polestar (`trainers.rs`), comprobada contra forever-db | verificado |
| Coordenadas de los instructores | forever-db (`npc`, `spawn`, `ui_map`) | verificado |
| Nivel de los rangos: Aprendiz 1 (Classic: 5), Oficial 10 (Cocina y Primeros auxilios: sin nivel) | Listas capturadas de Forever (Polestar) | verificado |
| Nivel de Experto (20) y Artesano (35) | Los de Classic | sin verificar |

Fuera de la ruta (nunca obligatorio): patrones por **Favor del mercader**, recetas de **botín**, recetas sin origen
conocido, especializaciones, recetas de otra clase o raza, las que piden reputación o un sitio concreto, y las de la
**Rueca** (campamento, patrón que cae en Dalaran) o el **Telar**.

## Modelo de eficiencia

1. **Probabilidad de subir** con habilidad `s`: naranja (de la habilidad de aprendizaje hasta amarillo - 1) = 1;
   entre amarillo y gris, `p = (gris - s) / (gris - amarillo)`; gris = 0. Si la receta da varios puntos
   (`NumSkillUps`), se multiplica. **Fabricaciones esperadas** de un tramo = suma de `1/p` punto a punto.
2. **Disponibilidad**: una receta sirve desde su habilidad de aprendizaje y solo si un personaje de la Alianza la
   consigue (instructor o vendedor por oro). Los topes 75/150/225/300 parten los tramos; la ruta lleva sus pasos
   «entrena Oficial / Experto / Artesano» (o el libro y la misión de Cocina y Primeros auxilios) con la habilidad y el
   nivel que piden.
3. **Esfuerzo por fabricación** (cobre equivalente): material de vendedor por su precio (`BuyPrice /
   VendorStackCount`; lo que los vendedores tienen en cantidad limitada, como el Polvo extraño, no cuenta como de
   vendedor); material recolectado o de botín por `max(4 × precio de venta, 2 × nivel del objeto^1,5)`, **la mitad**
   si el personaje lo consigue solo mientras sube (paño para todos, hierbas para el alquimista herborista, metal para
   herreros e ingenieros mineros, cuero para el peletero desollador, carne para la cocina, polvos y esencias para el
   encantador que desencanta; el pescado no, salvo que pesques). Los intermedios de la misma profesión (madejas, cuero
   curtido) cuentan su propio material y **sus propios puntos** mientras no son grises. Lo útil (bolsas, equipo verde
   que se usa o se desencanta, consumibles, encantamientos) pesa un 8 % menos: solo desempata.
4. **Programación dinámica** sobre la habilidad 1..300 con estado (habilidad, receta actual): seguir con la misma
   receta cuesta su esfuerzo / probabilidad; cambiar suma 60 c (un viaje, otra pila de material) y lo que cuesta una
   vez (aprenderla, su herramienta, como las varas rúnicas de Encantamiento). Así no alterna recetas casi iguales; y un
   tramo de 1-2 puntos entre dos recetas lo hace la de al lado si también da puntos ahí.

Las cifras de esfuerzo sirven para comparar rutas entre sí, no son un precio de la subasta.

## Resultado: Senda frente a Polestar y la ruta anterior

Con el mismo modelo para las tres (fabricaciones esperadas de 1 a 300; esfuerzo en oro equivalente, con aprender
y cambiar de receta). Se rehace con `python tools/gen_professions.py --compare --old <carpeta con las rutas antiguas>`.

| Profesión | Senda (nueva) | Polestar | Senda anterior |
|---|---|---|---|
| Alquimia | 345 (13,7 o) | 345 (15,0 o) | 288 (11,6 o), **30 puntos sin cubrir** |
| Herrería | 438 (101,6 o) | 499 (315,3 o) | no había |
| Encantamiento | 384 (8,6 o) | 359 (20,6 o) | 303 (22,1 o), **18 puntos sin cubrir** |
| Ingeniería | 331 (29,3 o) | 439 (32,9 o) | no había |
| Peletería | 367 (156,2 o) | 365 (209,6 o) | no había |
| Sastrería | 336 (423,1 o) | 385 (500,5 o) | 412 (467,8 o) |
| Cocina | 352 (6,5 o) | 349 (10,9 o) | no había |
| Primeros auxilios | 482 (14,7 o) | 404 (15,6 o) | no había |

Material de las rutas nuevas (lo más gordo, de 1 a 300):

- **Alquimia:** 178 Vial vacío, 108 Flor de paz, 100 Marregal, 97 Brezospina, 97 Vial con plomo, 71 Vial de cristal, 66 Hojaplata, 51 Espina de oro.
- **Herrería:** 1389 Lingote de torio, 549 Lingote de acero, 492 Lingote de bronce, 257 Piedra basta, 231 Piedra pesada, 181 Cristal de poder azul.
- **Encantamiento:** 120 Esencia mágica inferior, 74 Esencia mística inferior, 64 Esencia eterna inferior, 61 Esencia abisal superior, 44 Esencia astral superior, 29 Polvo extraño.
- **Ingeniería:** 197 Piedra sólida, 170 Lingote de torio, 111 Lingote de mitril, 108 Lingote de bronce, 90 Piedra basta, 75 Lingote de cobre.
- **Peletería:** 824 Cuero basto, 435 Cuero ligero, 304 Cuero grueso, 252 Cuero pesado, 227 Sal, 159 Hilo burdo.
- **Sastrería:** 3038 Paño rúnico, 623 Paño de lana, 476 Paño de seda, 307 Tela de paño mágico, 177 Hilo refinado, 139 Lejía, 130 Cuero basto.
- **Cocina:** 112 Especias picantes, 79 Carne de raptor, 72 Pata de araña pequeña, 54 Costillas de jabalí, 36 Carne de coyote, 35 Pargo nocturno crudo.
- **Primeros auxilios:** 405 Paño de lana, 89 Tela de paño mágico, 82 Paño de seda, 63 Paño rúnico, 49 Flor de paz, 47 Paño de lino.

### Por qué la nuestra es distinta

- **Alquimia:** Polestar va con Elixir de defensa menor de 1 a 75; la nuestra empieza con Elixir Arcano menor (naranja
  hasta 13) y usa pociones de sanación descoloridas (nuevas de Forever) en 135-142 y 175-195, que salen más baratas
  para un herborista. Mismo número de fabricaciones, un 9 % menos de esfuerzo. La anterior de Senda tenía recetas
  grises en su tramo (30 puntos sin cubrir).
- **Herrería:** la gran diferencia está de 235 a 300: Polestar usa el Hacha de batalla enorme de torio y las Botas
  imperiales de placas; la nuestra, Brazales, Botas y Leotardos de torio (lingotes de torio + cristales de poder de
  Un'Goro), con un tercio del esfuerzo. Antes, Leotardos de bronce férreos en lugar del Cinturón de cobre rúnico.
- **Encantamiento:** con un encantador que desencanta lo suyo, las esencias pesan poco; la nuestra se queda más
  tramos con la misma receta (Absorción menor 40-120, Intelecto e Intelecto superior en torso 145-235, Agilidad en
  botas 235-281) y evita el Aceite inferior de maná. Más fabricaciones esperadas (+25) pero la mitad de esfuerzo.
- **Ingeniería:** Contacto de plata (94-125) y Oveja explosiva / Granada de hierro en lugar de Practicar abrir
  cerradura y las bombas grandes: 108 fabricaciones menos.
- **Peletería:** Hombreras del montañero y Pellejo curado pesado en 108-142 y la línea de cuero maligno de 240 a 300
  (Brazales, Cinta, Pantalones y Cinturón) en vez de los Guanteletes de cuero maligno y la Cinta de cuero rúnico: un
  25 % menos de esfuerzo, con el cuero que sacas desollando.
- **Sastrería:** 49 fabricaciones menos que Polestar y 76 menos que la anterior: Vestido blanco de lana en vez de la
  Camisa roja estilosa, la línea de seda carmesí y tejido mágico negro por tramos cortos, y de 228 a 300 Guantes
  tejescarcha, Capa de paño brillante, Cinta de paño rúnico, Toga de tejido zahorí y Hombreras de paño rúnico (todas de
  instructor según la lista del servidor; aprendizaje estimado). Polestar compra el patrón de las Hombreras en la
  subasta.
- **Cocina:** Kebab de araña Kaldorei (19-76) y recetas de vendedor baratas; de 241 a 300, Serviola moteada y Sopa de
  pargo nocturno (pescado comprado: no supone Pesca) en vez de la Mezcolanza de monstruo. Menos de dos tercios del
  esfuerzo.
- **Primeros auxilios:** pasa por las pociones de sanación menores de Forever (44-80) y aguanta el Vendaje pesado de
  lana hasta 180 en vez de la Venda de seda: más fabricaciones esperadas (+78), pero vendas más baratas; si prefieres
  menos fabricaciones, la de Polestar cuesta un 6 % más.

### Elección del druida

Con estos números, **Herboristería + Alquimia** (345 fabricaciones, ~14 o de esfuerzo) gana con mucho a **Desuello
+ Peletería** (367 fabricaciones, ~156 o): el cuero grueso y basto pesa más que las hierbas, y Alquimia da las
pociones de maná y los elixires que el druida usa. Peletería queda como alternativa si quieres fabricarte el cuero de
feral. Es lo que dice el `[[recommend]]` de `professions-guide.toml`.

## Formato de los datos

`data/knowledge/general/professions-<prof>.toml` (`kind = "professions"`, generado: no editar):

- Cabecera: `prof`, `prof_kind` (`primary` | `secondary`), `assumes` (qué recolección supone), `crafts`, `reach`.
- `[[rank]]` `name`, `max`, `skill`, `level`, `how` (`trainer` | `book` | `quest`), `item` (libro).
- `[[trainer]]` `prof`, `npc`, `name`, `faction` (`Alliance` | `Horde`), `ranks` (los que enseña), `at = [uiMap, x, y,
  "etiqueta"]` o `text`; `book`/`quest` en los de Cocina y Primeros auxilios. Alianza primero: Ventormenta, Forjaz,
  Darnassus.
- `[[route]]` de rango: `from` (habilidad que pide), `to` (tope del rango actual), `train`, `level`, `note`.
- `[[route]]` de fabricación: `from`, `to`, `craft` (objeto) o `craft_spell` (encantamiento), `spell`, `name` (esES),
  `n` (fabricaciones esperadas), `mats = [[id, n]]` o `[[madeja, n, paño, paños por madeja]]`, `colors = [aprende,
  amarillo, verde, gris]`, `learn` (dónde y desde cuándo), `learn_skill`, `recipe_item`, `note`, `status`, `sources`.

`professions-materials.toml` (también generado): los rangos por defecto y los materiales de las rutas con su nombre,
precio de vendedor y de dónde salen. `professions-guide.toml` es a mano: plan por clase (`[[recommend]] class, profs,
why`), rangos, objetos de campamento, Legacy.

`tools/validate.py` comprueba las rutas con `prof`: sin huecos ni solapes, sin cruzar un tope, colores ordenados, la
receta aprendida antes de su tramo y `train` con su `[[rank]]`.

## En el juego (`Modules/Professions.lua`)

- **Qué se enseña:** todas las profesiones aprendidas (`M.Professions`, `M.ProfRank`: `GetProfessions`,
  `GetProfessionInfo`, líneas de habilidad y `C_TradeSkillUI`), las principales primero; si tienes menos de dos
  principales, las del plan de tu clase que te faltan, con el porqué. Una profesión fuera del plan (Minería en un
  brujo) sale igual, con su progreso.
- **Instructor:** el de tu facción que enseña el rango que toca, el más cercano (`Compat.WorldDistance`); si no se puede
  medir, el de tu ciudad de inicio y luego Ventormenta, Forjaz, Darnassus.
- **Ventana del instructor** (`Modules/Trainer.lua`): resalta las recetas de tu ruta que ya puedes aprender y aún dan
  puntos («receta de tu ruta de Sastrería (15-70)»).
- El HUD no cambia (su hueco único de línea extra sigue igual).

## Regenerar

```sh
python tools/fetch_wago.py                                   # tablas del cliente a .cache/wago (build fijado)
python tools/fetch_foreverdb.py                              # forever-db a .cache/foreverdb
SENDA_POLESTAR=/ruta/a/polestar python tools/gen_professions.py
python tools/gen_professions.py --check                      # CI: sale con 1 si cambiaría algo (sin fuentes, avisa y sale con 0)
python tools/build.py
```

## Pendiente

- Comprobar en el instructor las habilidades estimadas (marcadas «sin verificar» en cada tramo), sobre todo de 150 a
  300, y el nivel de Experto y Artesano.
- Las rutas suponen la recolección compañera (Alquimia con Herboristería...). Un alquimista sin Herboristería
  sigue la misma ruta pagando las hierbas.
- Los patrones por Favor del mercader y los de la Rueca no entran: si los tienes, pueden ser mejores para tu equipo.

# Importar rutas de Polestar

> Fase 1 del [plan de Polestar](PLAN-POLESTAR.md): el importador `tools/import_polestar.py` y el prototipo de
> Teldrassil `data/guides/nightelf-druid-ps`. Polestar es GPL-3: todo lo importado lleva su origen
> (`polestar:<commit>/<guía>#<paso>`) y el código adaptado lo dice en un comentario.

## Uso

```sh
python tools/import_polestar.py --polestar RUTA/AL/CLON/polestar \
    --guide forever/alliance/nightelf/01-teldrassil \
    --out data/guides/nightelf-druid-ps --race NightElf --class DRUID
python tools/validate.py     # 0 errores
python tools/build.py
cd tests/wowsim && node run.js ps j
```

| Opción | Por defecto | Para qué |
|---|---|---|
| `--polestar` | (obligatoria) | Clon de Polestar. Solo se lee; nunca se ejecuta su código ni sus scripts |
| `--guide` | (obligatoria) | Id de la guía de Polestar (el `id` de su `RegisterGuide`) |
| `--out` | (obligatoria) | Carpeta de la guía de Senda que se escribe (`guide.toml`, la sección y `REPORT.md`) |
| `--race`, `--class` | todas | Filtra los objetivos con `only` de otra raza o clase (se cuentan en el informe) |
| `--id` | nombre de `--out` | Id de la guía de Senda |
| `--prefix` | `ps-teld` | Prefijo de los ids de paso (`ps-teld-001`...) |
| `--compare` | `nightelf-druid` | Guía de Senda con la que se fusiona y compara |
| `--compare-sections` | `01-shadowglen,02-teldrassil` | Secciones de esa guía que entran en el informe de diferencias |
| `--report` | `<out>/REPORT.md` | Informe en Markdown |
| `--dry-run` | | No escribe nada; imprime el informe |

Lo generado no se edita a mano: se vuelve a importar. Lo que haya que escribir a mano va a la guía de Senda
(`data/guides/nightelf-druid`), y la regla de fusión lo respeta en la siguiente importación.

## Cómo funciona

1. **Lee la guía compilada**, no el `.guide`: `addon/Polestar_Guides*/Guides.lua` (la de Teldrassil está en
   `Polestar_Guides_Alliance`). Los fuentes casi no llevan coordenadas; los compilados sí (PNJ, mapa, x, y,
   altura, camps de aparición). `tools/polestar/source.py` localiza el bloque `-- Source: <guía>.guide` y
   `tools/polestar/luaparse.py` lo lee con un **analizador de literales Lua propio**: tablas, cadenas, números y
   las referencias a locales del bloque (`candidateRecords[6]`, `candidateLists[1]`). No ejecuta Lua.
2. **Nombres en español:** `addon/Polestar_esES/Names.lua` (`<id>\t<nombre>` por tipo: misión, PNJ, objeto,
   objeto del mundo, ruta de vuelo). Las subzonas y algunos hechizos no están ahí (los pone el cliente): van en
   una tabla propia (`tools/polestar/spanish.py`) solo con nombres comprobados; el resto se queda en inglés y
   el informe los lista.
3. **Notas traducidas:** `guides/locales/esES/<guía>.lua` (`{ ["inglés"] = "español" }`). La nota del paso de
   Polestar pasa al `tip` del primer paso de Senda que genera; la del objetivo, al `tip` de su paso, o al final
   del `text` cuando solo describe al PNJ («Coge «X» de Melithar Staghelm, junto al sendero.»). Lo que no tiene
   traducción se queda en inglés con la marca `[EN]` y sale en el informe.
4. **Un objetivo, un paso.** Cada paso de Polestar tiene ~2,6 objetivos; en Senda cada paso es una acción.
   Las cogidas y entregas seguidas en el mismo PNJ de un paso de Polestar se agrupan con `chain` (una sola
   conversación: «Hecho» o «Saltar» en una marca las demás, que es lo que hace `Engine:Mark`). Los objetivos
   de matar o recoger **no** se encadenan: en Senda la cadena se marca entera a mano y cada objetivo debe
   detectarse por separado.
5. **Fusión («lo hecho a mano gana»):** `merge_with_senda()` busca en la guía de `--compare` un paso con la misma
   misión y acción (`accept`, `turnin`, `complete`).
   - Mismo objetivo (`obj`): se usan el `text` y el `tip` de Senda.
   - Senda hace la misión entera en un paso y Polestar la parte por objetivos: se queda el texto generado y el
     truco de Senda va en el primero.
   - En los dos casos la `note` interna dice `ya en Senda: <id>`. La guía de Senda nunca se modifica.
6. **Informe** (`REPORT.md`): misiones solo en Polestar (y si están en otra sección de Senda), solo en Senda,
   diferencias de orden (cogidas y entregas comunes fuera de la subsecuencia común más larga), coordenadas que
   difieren más de 1.0, condiciones perdidas, marcas (escolta, élite, tiempo), pasos manuales, textos sin
   traducir y nombres sin versión esES.

Todos los pasos importados salen con `status = "unverified"` y
`sources = ["polestar:<commit>/<guía>#<paso de Polestar>"]`. La `note` (interna, el build no la copia al Lua)
dice de qué paso y objetivo de Polestar viene cada uno.

### Coordenadas y marcos de mapa

Polestar marca con `f = "e"` las coordenadas del marco de Classic Era. En Forever solo cambian cuatro zonas
([FOREVER.md](FOREVER.md)): Ventormenta (1453), Crestagrana (1433), Mulgore (1412) y Tierras de la Peste del
Este (1423). El importador convierte Ventormenta (`x*0.7737+19.68`, `y*0.7738+24.43`); en las otras tres aún no
tenemos la transformación, así que las deja como vienen, lo anota en la `note` del paso («SIN convertir») y en el
informe. Teldrassil, Darnassus, Costa Oscura y Claro de la Luna comparten marco: no hay nada que convertir.
Las coordenadas de Ventormenta que Polestar ya da en el marco de Forever no llevan `f` y no se tocan.

## Correspondencia de campos

| Polestar | Senda | Notas |
|---|---|---|
| goal `accept` | `do = "accept"`, `quest`, `npc`, `at` | `minLevel` > 1 → `reqlevel`. Desde un objeto: el nombre del objeto en el texto. Desde un objeto del inventario: «Usa X para empezar «Q».» |
| goal `turnin` | `do = "turnin"`, `quest`, `npc`, `at` | |
| goal `kill` | `do = "complete"`, `quest`, `obj = oi`, `at`, `wps` | Sin misión: `note` |
| goal `collect` | `do = "complete"`, `quest`, `obj = oi`, `at`, `wps` | Sin misión: `do = "loot"`, `item`, `count` |
| goal `complete` / `interact` | `do = "complete"`, `quest` (`obj`) | Objetivos (`objs`) en inglés en la `note` |
| goal `use` | con misión y `oi`: `do = "complete"`, `obj`; sin ella: `do = "use"`, `item` | `use` es manual si el cliente no da el hechizo del objeto |
| goal `goto` | `do = "goto"`, `at` | |
| goal `getfp` | `do = "getfp"`, `node` (id del nodo), `npc`, `at` | |
| goal `fly` | `do = "fly"`, `zone` | `zone` = mapa de la subzona (`AREA_ZONE`) o el del siguiente objetivo con coordenadas |
| goal `sethome` | `do = "sethearth"`, `npc`, `zone`, `at` | |
| goal `hearth` | `do = "hearth"`, `zone` | |
| goal `train` (profesión) | `do = "learn_prof"`, `prof` | `skillLine` → clave de Senda (`alchemy`, `firstaid`...) |
| goal `train class` | `do = "note"`, `npc` y `at` del instructor de la clase más cercano | Senda necesita `spells` para detectarlo: queda manual |
| goal `buy` | `do = "buy"`, `item`, `count`, `npc` | |
| goal `level` | `do = "level"`, `level` | |
| goal `note` | `do = "note"` | Texto traducido si existe |
| `spotsPacked` | `wps` | Hasta 3 camps principales (no alternativos), sin repetir el punto de `at` |
| `only = { classes, races, factions }` (paso y objetivo) | `if.class`, `if.race`, `if.faction` | Polestar ya compila las negaciones como listas. Con `--class/--race` lo de otras clases o razas se descarta |
| `profLine` del objetivo | `if.prof` | Misiones que piden profesión |
| `optional` | `optional = true` | |
| `when { k = "level" }` | `if.minlevel` / `if.maxlevel` | `>=`, `>`, `<`, `<=` |
| `when { k = "skill" }` (profesión) | `if.prof` | |
| `when { k = "onquest" }` de la misma misión del paso | (implícita) | El paso ya depende de esa misión |
| `when { k = "knows", neg }` | (se pierde) | Si ya sabes el hechizo, la misión ya está hecha y el paso se cumple solo |
| Otras `when` (dinero, grupo, misión lista, arma) | `optional = true` + `note` | Senda aún no tiene condiciones vivas |
| `escort` | `escort = true` en los pasos `accept` y `complete` (el HUD pone la nota de escolta); en otros pasos, aviso en `tip` | Función 6 del plan |
| `limit` (misión con tiempo) | `tip`: «Misión con tiempo: N min» | Función 2 del plan |
| `group` (élite) | `tip`: «Élite: mejor en grupo.» | |
| `along`, `label`, `skipto` | `note` + informe | |
| `pre`, `preAll`, `closedBy`, `parent` | `note` («datos no importados») | Los prerrequisitos ya los comprueba `tools/verify.py` contra la base de datos |
| `rewards` | informe | |

## Lo que se pierde

- **Recuentos por objetivo.** Polestar sigue «mata 6/8»; Senda detecta el objetivo entero (`obj`) o la misión
  entera. El número va en el texto («Mata Sable de la Noche joven (7)...»). Función 4 del plan.
- **Condiciones vivas** (`when`): dinero, ir en grupo, tener lista otra misión, saber un hechizo, no tener una
  habilidad de arma. Los pasos con una condición que Senda no sabe expresar quedan opcionales y su `note` la
  explica. En Teldrassil: el instructor de armas (bastones, si llevas 10 platas), Xethorr (en grupo) y la
  entrega de Tallonkai cuando «Odio enraizado» está lista.
- **Grupo y élite:** solo un aviso en el `tip`; no hay alternativa en solitario.
- **Escoltas y misiones con tiempo:** la escolta pasa al campo `escort`; el límite de tiempo queda como aviso en el `tip`
  (el motor ya muestra la cuenta atrás leyéndola del cliente).
- **Recompensas a elegir** (`rewards.choices`): no se importan (el módulo de equipo de Senda decide).
- **Varios puntos de aparición:** Polestar guarda todos los camps y alternativos; Senda se queda con el punto
  principal y hasta 3 camps.
- **Entrenar la clase:** Polestar lo detecta al abrir la ventana del instructor; Senda necesita la lista de
  hechizos (`spells`). Hasta que el importador la saque del conocimiento de clase (`data/knowledge/druid`),
  es un paso manual.
- **Altura (`z`)** y la flecha 3D por caminos: Senda usa flecha 2D.

## Prototipo: `nightelf-druid-ps`

La guía `forever/alliance/nightelf/01-teldrassil` de Polestar (niveles 1-12) importada para druida elfo de la noche:
265 pasos en una sección (`ps-teldrassil`). Incluye, como Polestar, las misiones de clase del druida que salen de
Teldrassil (Claro de la Luna y la Piedra de lechúcico lunar de Costa Oscura) y las primeras misiones de Auberdine.

**Nunca se elige sola.** `guide.toml` lleva `order = -1` (campo que ya existía en el esquema de guía y no usaba
nadie). `Guides:IsManualOnly(g)` es `order < 0`; `Guides:ForPlayer()` pone esas guías al final y
`Engine:AutoSelect()` no las coge aunque fueran las únicas válidas. Sí salen en el desplegable de guías y se
eligen con `/senda guide nightelf-druid-ps`; esa elección se guarda como cualquier otra.

**Simulador** (`node run.js ps`): comprueba que la elección automática sigue siendo `nightelf-druid`, carga el
prototipo a mano y lo juega entero. Resultado: 223 pasos automáticos, 6 manuales, 0 atascados. Los manuales:

| Paso | Por qué |
|---|---|
| `ps-teld-017` | «La diosa provee»: lanzar Luz de Elune y Fusión de las Sombras (en Senda, `nesg-007` es `complete`) |
| `ps-teld-031`, `-079`, `-114`, `-192` | Entrenar la clase (sin `spells`) |
| `ps-teld-260` | Usar el Polvo lunar Cenarion en la Piedra de lechúcico lunar |

### Comparación con `nightelf-druid` (resumen de `REPORT.md`, commit `19bd636`)

- Misiones: 90 en Polestar, 75 en nuestras secciones 01-02, 72 en las dos. 217 de los 265 pasos ya estaban en
  Senda (167 con el mismo objetivo: conservan nuestro texto).
- **Solo en Polestar (18):** casi todas están en otra sección nuestra (Costa Oscura y `dr-10-bear`: Polestar
  mete en Teldrassil el viaje del druida a Claro de la Luna y las primeras de Auberdine). Faltan de verdad en
  Senda: «El sigilo verde» (3120, el sigilo del druida), «Vuelve con Nessa» (6343), «La familia y la caña de
  pescar» (1141, solo pescadores) y las lecciones de Desuello y Peletería (97949, 97946), que Senda no hace
  porque el druida lleva Herboristería y Alquimia.
- **Solo en Senda (3):** los elixires de Syral (1581, alquimistas), «Coge la misión de vuelta con Denalan» (2498)
  y Robleceño (2499, élite).
- **Orden:** 62 de 141 cogidas y entregas comunes van en otro momento. Lo más visible: Polestar entrega «El
  equilibrio de la naturaleza» después de las misiones de Tarindrella, y hace «La corona de la Tierra» y el envío
  a Dolanaar más tarde. La tabla completa está en `REPORT.md`.
- **Coordenadas > 1.0:** solo 3 (cogida de 489 en Dolanaar y la cogida y entrega de 490, Shayla, que camina).

## Siguientes pasos

1. **Probarla en el juego** con un druida nuevo frente a `nightelf-druid` (tiempo al 12, pasos que fallan) y
   decidir, misión a misión, qué orden se queda en nuestra guía.
2. **Entrenar la clase con `spells`:** sacar los hechizos de cada nivel de `data/knowledge/druid` para que esos
   pasos se detecten solos.
3. **Condiciones vivas en el motor** (`when`: dinero, grupo, misión lista, saber un hechizo) para que esos pasos
   dejen de ser opcionales; y `skipto`/`along`.
4. **Seguimiento por objetivo** (6/8) y la cuenta atrás de misiones con tiempo y el aviso de escolta
   (funciones 2, 4 y 6 del plan), para dejar de meter eso en el `tip`.
5. **Transformaciones de marco** de Crestagrana, Mulgore y Tierras de la Peste del Este (de los límites DBC) para
   importar las guías que pasan por ellas.
6. **Más nombres esES** de subzonas (Shadowthread Cave, Gnarlpine Hold, Nighthaven, Wellspring River...) comprobados
   en el cliente, y textos escritos por el arnés para los 72 `[EN]` que deja Polestar.
7. **Secciones:** partir la guía importada por zonas/niveles en vez de una sola sección.
8. **Importar las demás guías** (Costa Oscura y las tres rutas actuales) y, con `route_score.py`, el filtro de
   eficiencia del plan.

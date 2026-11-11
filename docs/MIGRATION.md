# Migración de BrujoGnomoGuia 4.1.0 a Senda

Origen (solo lectura): `Interface/AddOns/BrujoGnomoGuia` del cliente `_forever_`, versión 4.1.0 (Brujo gnomo y mago humano).
Fecha de la migración: 11-nov-2026. Todo el contenido pasa a `data/knowledge/**` (paneles de conocimiento) y
`data/legacy/**` (pasos antiguos, solo como entrada para escribir las rutas detalladas).

## Correspondencia origen → destino

| Origen | Destino |
|---|---|
| `Data.lua` `ns.STEPS` (26 pasos) | `data/legacy/steps-warlock.toml` (`legacy-wl-001` … `026`) |
| `Data.lua` `ns.TRAIN` | `data/knowledge/warlock/spells.toml` (`[[train]]`) |
| `Data.lua` `ns.TALENTS` (rangos de nivel) | `data/knowledge/warlock/talents.toml` (51 `[[pick]]`, uno por nivel 10-60) |
| `Data.lua` `ns.ROTATION` | `data/knowledge/warlock/rotation.toml` (`[[phase]]`) |
| `Data.lua` `ns.MAPS` | Ids de mapa usados en `at`/`wps`/`trainer.at` (sin archivo propio) |
| `Brackets.lua` `ns.BRACKETS` (6 tramos) | `data/knowledge/warlock/bracket-*.toml` (un archivo por tramo, un `[[block]]` por encabezado) |
| `Texts.lua` `combate` | `data/knowledge/warlock/combat.toml` |
| `Texts.lua` `grupo` | `data/knowledge/warlock/group.toml` |
| `Texts.lua` `profesiones` | `data/knowledge/general/professions-guide.toml` |
| `Texts.lua` `oro` | `data/knowledge/general/gold.toml` |
| `Macros.lua` `ns.MACROS` (14) | `data/knowledge/warlock/macros.toml` (`BG_*` → `SND_*`) |
| `Bars.lua` `ns.BARS`, `ns.BAR_BINDINGS` | `data/knowledge/warlock/bars.toml` |
| `Crafting.lua` `PROFS.tailor` | `data/knowledge/general/professions-tailoring.toml` |
| `Crafting.lua` `PROFS.ench` | `data/knowledge/general/professions-enchanting.toml` |
| `Crafting.lua` `RANKS`, `MATS`, `SELLABLE`, `ORDER` | `data/knowledge/general/professions-materials.toml` |
| `Gear.lua` `WEIGHTS.WARLOCK` / `WEIGHTS.MAGE` | `[weights]` de `warlock/gear.toml` / `mage/gear.toml` |
| `Gear.lua` `WHERE` (48 objetos), `NOTES` | `data/knowledge/general/gear-items.toml` (`[[item]]`); notas repartidas en los `gear.toml` |
| `Duo.lua` `INTRO` + 9 tramos | `data/knowledge/general/duo-00-intro.toml` y `duo-01-01-10.toml` … `duo-09-50-60.toml` (ids `duo-*`) |
| `MageData.lua` `MG.STEPS` (24) | `data/legacy/steps-mage.toml` (`legacy-mg-001` … `024`) |
| `MageData.lua` `MG.TRAIN`, `MG.MAGE_CHECKS` | `data/knowledge/mage/spells.toml` (`[[train]]`, `[[check]]`) |
| `MageData.lua` `MG.TALENTS` | `data/knowledge/mage/talents.toml` |
| `MageData.lua` `MG.ROTATION` | `data/knowledge/mage/rotation.toml` |
| `MageData.lua` `MG.BRACKETS` | `data/knowledge/mage/bracket-*.toml` |
| `MageData.lua` `MG.TEXTS.combate` / `grupo` | `data/knowledge/mage/combat.toml` / `group.toml` |
| `MageData.lua` `MG.TEXTS.profesiones` (añadido) | `data/knowledge/mage/professions-extra.toml` |
| `MageData.lua` `MG.TEXTS.oro` (añadido) | `data/knowledge/mage/gold.toml` |
| `MageData.lua` `MG.MACROS` (8) | `data/knowledge/mage/macros.toml` (`MG_*` → `SND_*`) |
| `MageData.lua` `MG.BARS` | `data/knowledge/mage/bars.toml` |
| `MageData.lua` `MG.CRAFT_TRAINERS` | `[[trainer]]` con `for_class = "MAGE"` en los archivos de profesión |
| `BrujoGnomoGuia.lua` `SPELL_NAMES` | `[[alias]]` en `warlock/spells.toml` |
| `BrujoGnomoGuia.lua` `SPELL`, `HEALTHSTONES`, `SOUL_SHARD`, `MSPELL`, `MAGE_ARMORS`, `MAGE_INTELLECT`, `CONJ_WATER`, `MANA_GEMS` | `[ids]` de `warlock/spells.toml` y `mage/spells.toml` |
| `BrujoGnomoGuia.lua` `Suggest` / `MageSuggest` (HUD) | `[[hud]]` en los `rotation.toml` |
| `BrujoGnomoGuia.lua` `Warnings` / `MageWarnings` | `[[warning]]` en los `rotation.toml` |
| `BrujoGnomoGuia.lua` `Analyze`, `FocusAdvice`, `ProfAdvice`, `SellAdvice`, entrenador | `data/knowledge/general/advisor.toml` (`[[rule]]`) |
| `BrujoGnomoGuia.lua` consejos de barras y textos de ayuda | `[[block]]` «Consejos de barras» en los `bars.toml` |

Macros renombradas: `BG_Abrir, BG_Varita, BG_Miedo, BG_Drenar, BG_Piedra, BG_Sacrificio, BG_Corr_MO, BG_Agonia_MO,
BG_Lenguas, BG_Desterrar, BG_Interrumpir, BG_Succion_MO, BG_Aullido, BG_Espiral` y `MG_Varita, MG_Conjurar, MG_Poli,
MG_Lanza, MG_Contra, MG_Bloque, MG_Gema, MG_Piedra` pasan a `SND_<mismo sufijo>`. Cada macro guarda su nombre antiguo
en `legacy`. `SND_Piedra` existe para las dos clases (son archivos de clase distintos). Las referencias a macros en
los textos (brackets, combate, barras) también usan ya los nombres `SND_*`.

## Convenciones nuevas (extensiones del formato de conocimiento)

El build vuelca el TOML tal cual, así que estos campos llegan al Lua; los módulos que los usen deben conocerlos.

- **`sources`**: URL cuando la fuente original citaba un sitio (`https://conquestcapped.com/`,
  `https://www.warcrafttavern.com/forever/`, `https://warcraft.wiki.gg/wiki/Patch_1.60`, `https://www.method.gg/`,
  `https://www.wowhead.com/forever`, `https://www.wow-professions.com/`, `https://timesaver.gg/`). Son las portadas del
  sitio: la fuente no daba la página exacta y el harness debe localizarla. Si no hay URL conocida, `cita:<descripción>`
  (p. ej. `cita:wowprofs`, `cita:Manual del Mago Gnomo (sección «En pareja»)`, `cita:Blizzard, notas de desarrollo de la beta (24-sep-2026)`).
  Siempre va también `legacy:BrujoGnomoGuia 4.1.0`. `checked` = fecha que daba la fuente (2026-11-04 … 2026-11-10).
- **`status`**: todo entra como `unverified` (ninguna afirmación cumple la regla de `verified`: las guías comunitarias
  no bastan y las correcciones de Blizzard se citaban sin enlace). Lo que tiene fuentes en conflicto va como `disputed`.
  Bloques, picks, rutas y pasos llevan `status`/`note` propios cuando difieren del archivo.
- **`note`** (archivo, bloque o elemento): matices de la fuente, nombres marcados «(?)» y dudas.
- **`kind = "page"`** con tablas extra: `[weights]` (gear), `[[item]]` (gear-items).
- **`kind = "spells"`**: `[[train]]` con `names` (nombres esES de la fuente, en orden), `spells` (ids), `ids_added`
  (ids que **no** venían en la fuente: los añadió la migración desde Classic), `no_id` (nombres sin id conocido),
  `pet`/`talent`; `[[alias]]` (nombres alternativos del cliente); `[[check]]` (hechizos clave del análisis); `[ids]`.
- **`kind = "talents"`**: `[[pick]]` con `rank` (rango que alcanza ese punto) y `max`.
- **`kind = "macros"`**: `body` + `fallbacks` (alternativas en orden), `pet`, `legacy`, `icon` (`spell:<id>`,
  `item:<id>` o `name:<nombre>`). Marcadores: `{<id>}` nombre del hechizo, `{hs}` piedra de salud actual,
  `{n:<nombre>}` nombre literal.
- **`kind = "rotation"`**: `[[phase]]` con `note` opcional; `[[hud]]` (`when`, `suggest`, `spell`) en orden de
  prioridad; `[[warning]]` (`text`, `when`).
- **`kind = "professions"`**: `[[route]]` con `craft` (objeto) o `craft_spell` (encantamiento), `name`, `n`
  (fabricaciones), `src` (origen de la receta); `[[trainer]]` (`prof`, `ranks`, `for_class`, `name`, `at`, `text`);
  `[[rank]]`; `[[material]]` (`vendor` en cobre, `where`, `sell`, `min`, `made_from`); `sellable`, `order_profs`.
  El instructor no va dentro de cada ruta (como sugería el formato) porque depende de la raza y del rango.
- **`kind = "bars"`** (nuevo): `[[bar]]` + `[[bar.slot]]` (`slot`, `key`, `spell`, `alt`, `alt2`, `spell_name`,
  `macro`, `icon`, `level`) y `[bindings]`.
- **`kind = "rules"`** (nuevo): `[[rule]]` (`id`, `class`, `when`, `say`, `priority`). Heurísticas del asesor; no
  es texto para el jugador.
- **Pasos legacy**: `do = "train"` si el paso tenía hechizo (se completaba al conocerlo), `goto` si solo tenía
  puntos, `note` en otro caso. `at` = primer punto, `wps` = el resto; `chain` se conserva. El título original y el
  nivel recomendado van en `note`. La fuente no tenía ids de misión ni de PNJ.

## Correcciones aplicadas al migrar

- «lago de Ironforge» → «lago de Forjaz» (bracket 1-9 del brujo).
- «Maldición de Temeridad» → «Maldición de temeridad».
- «Santuario de los Magos» → «Sagrario de los Magos» (paso de la biblioteca del mago; el resto de la fuente dice Sagrario).
- «Silito» → «Silithus» (fórmula de Kania).
- «Agonía» suelta → «Terror de agonía»; «worgen» → «huargen»; «kobolds» → «kóbolds».
- Listas «·» y «1 X · 4 Y» convertidas a listas `- ` y `**negrita**`; los marcadores «(?)» salen del texto y pasan a `note`.
- Texto común de profesiones: «Fabrica el de Sombras para ti» → «si eres brujo» (lo leían las dos clases).

## Lo que no se migra (código o datos de la interfaz)

- Interfaz: ventana, pestañas, HUD, botón de minimapa, ScrollText, popups, comandos `/bgg …`, TomTom, «Exportar para
  Claude», botón Desencantar, compra automática en vendedores y aprendizaje en instructores. Las reglas que usaban
  están en `general/advisor.toml` y en los `[[hud]]`/`[[warning]]`.
- `Select.lua`: elegía los datos por clase; en Senda lo hace `class` de cada archivo.
- Enlaces a la guía web antigua: `ns.WEB_URL = https://claude.ai/artifact/GpoYGCu9Ui2Y6ee66yX6bz` (brujo) y
  `MG.WEB_URL = https://claude.ai/artifact/7wzsfWZnndkFSdqm7ovn4c` (mago). No se enlazan desde Senda.
- Tablas técnicas de equipo (`SLOTS`, `SLOT_ORDER`, `LOC`, `WEAPON_SKILL`, `NOT_DE_LOC`, `SKIP_LOC`, `PROF_KEYS`):
  son lógica del módulo de equipo. Datos útiles que contenían:
  - En el cliente esES, Sastrería aparece como «Costura» en unas API y como «Sastrería» en otras; Herboristería, como «Botánica».
  - Forever marca lo no equipable como `INVTYPE_NON_EQUIP_IGNORE` (no cadena vacía).
  - Subclases de arma: 15 Dagas, 10 Bastones, 7 Espadas de una mano.
  - La lista de equipo se mostraba desde `from - 3` hasta `to`.

## Datos dudosos (para el harness de verificación)

Hechizos e ids
1. **«Fuerza inmortal» (nivel 16 del brujo)**: no existe en Classic; al 16 se aprende Aliento inagotable (5697). Sin id.
2. **«Terror de agonía»**: nombre marcado «(?)»; alias Maldición de agonía / Agonía. Id 980 de Classic.
3. **«Maldición de la lengua»** en los textos frente a **«Maldición de las lenguas»** en la tabla de nombres del addon (1714).
4. **«Terror de fatalidad» (60)**: probablemente Maldición de fatalidad (603).
5. **Maldición de los elementos al 20** (Classic: 32) y «cubre toda la magia; la de las Sombras ya no existe»: sin fuente.
6. **Ids añadidos por la migración** (`ids_added`): 702, 707, 755, 704, 5676, 5740, 5138, 5500, 132, 1098, 1949, 6229,
   6353, 603 (brujo); 5143, 604, 130, 1008, 475, 1463, 543, 3562, 2948, 6143, 3565, 3552, 11416, 10053, 11419, 10054,
   28270 (mago). Todos de Classic: comprobar que existen en Forever.
7. **Sin id**: Descarga de Pirofrío (40), Teletransporte a: Dalaran (50), Lanza de hielo, Barrera de hielo/Mordedura
   helada (se usan por nombre). Ids de piedras de salud y gemas de maná: los de Classic.
8. **Teletransporte a: Ventormenta y Forjaz** al 20 en la tabla de entrenamiento; el tramo solo menciona Ventormenta.

Talentos
9. **Brujo 20-27** (`disputed`): ConquestCapped frente a Warcraft Tavern (Poder profano y Energías demoníacas hacia el 20-26).
10. **Brujo 31-60**: orientativo. Nombres «(?)»: Drenajes mejorados, Pandemia, Terror de agonía mejorado, Malevolencia,
    Succión de alma, Estragos. **Mago**: Recuperación Arcana, Impacto Arcano.
11. **Mago, build 33-60 al reiniciar**: suma 23 puntos y al 33 hay 24.
12. **Succionar vida**: la rotación y la macro SND_Succion_MO dicen «desde el 35»; la build lo coge al 36.
13. **Mordedura helada**: la barra la coloca desde el 32; la build la coge al reiniciar al 33.

Coordenadas y PNJ
14. **Larimaine Purdue** (`disputed`, legacy-mg-013): nombre «(?)», 39.6, 79.6 frente a 49, 84; y dudoso que el
    Teletransporte lo enseñe la instructora de portales.
15. **Cascada del Lago Espejo** (`disputed`, legacy-mg-007): 32.1, 58.2 frente a 28, 61.
16. **Círculo de Ventormenta**: 25.3, 78.2 (mapa clásico) frente a 39.0, 84.5 de ConquestCapped/Warcraft Tavern
    (mapa moderno). El autor lo resolvió a favor del clásico.
17. Coordenadas sin fuente explícita: Gimrizz Shadowcog (Kharanos 47.2, 53.6), Farholde Keep (Riverglades 60.6, 81.6),
    Sellandus/Georgio Bolero («hacia» 42.0, 76.2), Kitta Firewind (Elwynn 64.8, 70.6), Timothy Worthington
    (Marjal Revolcafango 66.2, 51.6, uiMapID 1445 asumido), Earthseer Farsen (Dun Morogh 64.8, 58.5).
18. Nombres «(?)» de misiones/objetos: La vinculación, gargantilla de sangre, Devorador de almas, ¿Qué es el amor?,
    Shadowfang Darksoul. «Lago Blackwrench (Forjaz) te da El Cordero Degollado»: PNJ sin comprobar.
19. Datos marcados «(Classic)» en `Duo.lua` (Old Murk-Eye, mina Jangolode, Villa del Lago, misiones de Minas de la Muerte).

Profesiones
20. **Sastrería 225-300**: ruta especulativa de Method (sin probar en la beta). Origen de Hombreras de paño rúnico y
    del Telar sin confirmar; Guantes de paño rúnico (Qia) y cinturón «se aprende a 210», cinta «a 250».
21. **Nombres frente a ids de encantamientos**: 7420 es «Encantar torso: salud menor» en Classic (la fuente dice
    «aguante menor»); 13858 es «salud excelente» en Classic (la fuente dice «aguante excelente»).
22. **Cantidades de materiales distintas de Classic** (¿cambio de Forever?): 7457 (2 Polvo extraño; Classic 3),
    7863 (4; Classic 8), 13501 y 13536 (1 Polvo de alma; Classic 2), 13858 (3 Polvo de visión; Classic 6),
    20017 (6 Polvo onírico; Classic 10), 20747 Aceite de maná inferior (1/1/1; Classic 3 Polvo onírico, 2 Loto morado, 1 Vial).
23. **Varita brillante**: habilidad 275 o 220 según la guía (`note` en professions-guide).
24. «Tela de paño mágico» (4338): nombre esES probable «Paño de tejido mágico».
25. Nombres en inglés sin traducción confirmada: Arcane Salvager, Soulstaff, Orb of Souls, Filigreed, Nether,
    Demonheart, puntos de Legacy (Thrill of Adventure, Working Overtime, Reagent Economy, Permanence, Field Guide)
    y 19 objetos de `gear-items.toml`.
26. Requisitos de Favor/reputación (Azeroth Commerce Authority: 60 Favor + Amistoso, 120 + Amistoso, 180 + Honorable),
    hogueras del campamento (3/5/10 objetos con Cocina 140/220), Working Overtime +4% por rango: sin fuente concreta.

Cambios de Blizzard citados sin enlace (buscar la nota oficial)
27. 4-nov: menos probabilidad de Fragmento de alma por tick de Drenar alma; coeficiente de Estragos doblado (ajuste el 10-nov).
28. 8-nov: +50% de experiencia de enemigos de mazmorra (no las misiones).
29. 9-nov: la equitación del 40 viene con la misión del Corcel nefasto (gratis para el brujo; el mago paga ~100 de oro).
30. Notas de la beta del 24-sep: las varitas no escalan con el poder con hechizos.
31. Misiones de mazmorra ×2,4 respecto a Classic; máximo 5 mazmorras por hora; descanso solo para enemigos.

Otros
32. Bandas del 9-dic (Barrow Deeps 10, Hyjal Summit 20, Guarida de Onyxia 40 con Amuleto de Fuego de Dragón; sin
    Núcleo de Magma): solo la fecha tiene fuente (Warcraft Wiki).
33. Cifras sin fuente: entrenar 1-60 cuesta ~207 de oro; ~81 de oro el paño e hilo hasta Sastrería 225 (precios del 9-nov);
    Bastones con Woo Ping por 10 de plata; Transfusión de vida rango 3 = 140 + Espíritu.
34. Mago: Armadura de mago 50% (`disputed` frente a 30%); Despiadado 1-2%; espíritu humano 5% o 10%; Cono de frío
    40% durante 6 s; Barrera de hielo +15% de daño de Escarcha.
35. Niveles de mazmorras nuevas (Hall of Thanes 13-18 o 14-17 según el archivo, Ruins of Lordaeron 15-20, Excavation
    Site 24-29, City of Dalaran 28-33, The Drowned City 35-40, Krol'dok 40-45, Alcaz Prison 48-53, Blackmaw Hold 55-60,
    Shaper's Terrace 58-60).

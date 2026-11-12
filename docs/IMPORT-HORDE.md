# Importación de Polestar: guías de la Horda (1-60)

Cuatro guías nuevas, una por raza de la Horda con inicio propio, importadas con `tools/import_polestar.py` (sin cambios) del clon de
Polestar (GPL-3) en el commit `19bd636e7d6f33231770f6029c76d2d4dfc63798`. Mismo mecanismo que `nightelf-druid-ps-full`
(`docs/IMPORT.md`, `docs/IMPORT-REPORT.md`): `order = -1` (nunca se elige sola; sale en el desplegable y se elige con
`/senda guide ps-horde-<raza>`), `status = "unverified"`, y cada paso con `sources = ["polestar:<commit>/<guía>#<paso>"]`.

| Carpeta | Raza (`races`) | Clases (`classes`) | Inicio | Secciones |
|---|---|---|---|---|
| `data/guides/ps-horde-orc/` | Orc | WARRIOR HUNTER ROGUE SHAMAN WARLOCK | `horde/orc/01-durotar` | 26 |
| `data/guides/ps-horde-troll/` | Troll | WARRIOR HUNTER ROGUE PRIEST SHAMAN MAGE | `horde/troll/01-durotar` | 26 |
| `data/guides/ps-horde-tauren/` | Tauren | WARRIOR HUNTER SHAMAN DRUID | `horde/tauren/01-mulgore` | 26 |
| `data/guides/ps-horde-undead/` | Scourge (no-muerto) | WARRIOR ROGUE PRIEST MAGE WARLOCK | `horde/undead/01-tirisfal-glades` | 26 |

La lista de clases por raza es la de Classic Era (Polestar no la declara); los pasos específicos de una clase llevan `if.class`
tal como los trae Polestar (`only.classes`) y los de otra raza se descartan (`--race`). Skyborne queda fuera (no se pidió).

## Cómo se montó

El importador escribe una guía de Polestar por ejecución. Por raza se ejecuta 26 veces (inicio de raza + 25 guías de la cadena
Horda) con `--race <raza> --compare none --prefix <px>NN` y un montaje posterior copia cada TOML a `NN-<zona>.toml`, cambia el
`id` de sección a `<px>NN-<zona>` (si no, `ps-the-barrens` etc. se repiten) y escribe `guide.toml`. No se tocó el importador ni
ningún otro fichero. `--compare none` evita comparar con la guía de Alianza por defecto. El script de montaje no está en el
repositorio (vive fuera, en el espacio de trabajo temporal); se repite con las órdenes de arriba.

Cadena Horda (orden de `next` de Polestar, igual para las cuatro razas): 03 Argénteos (Silverpine), 02 Los Baldíos, 05 Sierra
Espolón, 06 Trampas de Hillsbrad, 04 Los Baldíos, 07 Vallefresno, 30-40/01 Hillsbrad, Mil Agujas, Tierra de Espinas, Marjal
Revolcafango, Arathi, Tierras Inhóspitas; 40-50/01 Tierra de Espinas, Feralas (x2), Tanaris, Tierras del Interior, Azshara;
50-60/01 Un'Goro, Frondavil, Cuna del Invierno, Azshara, Tierras de la Peste del Este, Silithus, Frondavil.

Prefijos de id de paso: `orc`, `trl`, `tau`, `und` + número de guía (`orc00-001`...), únicos en todo el repositorio.

## Recuentos por guía

| Guía | Secciones | Pasos | Misiones distintas | Pasos con `if.class` | Opcionales (`when` perdido) |
|---|---:|---:|---:|---:|---:|
| `ps-horde-orc` | 26 | 3321 | 879 | 324 | 322 |
| `ps-horde-troll` | 26 | 3329 | 884 | 334 | 322 |
| `ps-horde-tauren` | 26 | 3359 | 897 | 362 | 322 |
| `ps-horde-undead` | 26 | 3278 | 875 | 284 | 306 |

Pasos por tipo (`do`), orco / trol / tauren / no-muerto:

| `do` | Orc | Troll | Tauren | Undead |
|---|---:|---:|---:|---:|
| turnin | 903 | 908 | 920 | 894 |
| accept | 863 | 867 | 876 | 856 |
| complete | 837 | 838 | 834 | 830 |
| goto | 266 | 265 | 263 | 258 |
| fly | 102 | 102 | 109 | 102 |
| loot | 57 | 57 | 60 | 56 |
| level | 36 | 36 | 36 | 35 |
| getfp | 34 | 34 | 36 | 32 |
| sethearth | 28 | 28 | 29 | 28 |
| use / buy / learn_prof | 12 | 12 | 18 | 14 |
| note (manuales) | 183 | 182 | 178 | 173 |

### Pasos por franja de nivel

Cada sección cuenta en la franja donde empieza (las guías de Polestar solapan 1-3 niveles).

| Franja | Orc | Troll | Tauren | Undead |
|---|---:|---:|---:|---:|
| 1-9 (inicio de raza: 1-12, no-muerto 1-13) | 260 | 266 | 265 | 278 |
| 10-19 | 475 | 477 | 496 | 412 |
| 20-29 | 569 | 569 | 576 | 571 |
| 30-39 | 624 | 624 | 624 | 624 |
| 40-49 | 469 | 469 | 474 | 469 |
| 50-60 | 924 | 924 | 924 | 924 |

## Pasos que no se pudieron mapear del todo

Salen como `do = "note"` (manuales: «Hecho» o «Saltar»), con la causa en `note`. Orc / Troll / Tauren / Undead:

| Causa | Orc | Troll | Tauren | Undead |
|---|---:|---:|---:|---:|
| Entrenar la clase: Senda necesita `spells` para detectarlo | 65 | 65 | 61 | 58 |
| Entrenar armas con condición de dinero (`when` no expresable) | 14 | 14 | 14 | 8 |
| Tipos de objetivo de Polestar sin equivalente (`vendor`, `talk`, `die`): texto genérico («Vendor.», «Talk.», «Die.») | 25 | 24 | 24 | 27 |
| Notas de Polestar (consejos, «la siguiente guía empieza en...») | 71 | 71 | 71 | 72 |
| Otros (condición de mazmorra, objetivo `kill` sin misión...) | 8 | 8 | 8 | 8 |

Además:

- **Condiciones vivas perdidas:** 306-322 pasos por guía salen `optional = true` (dinero, grupo, misión lista, arma).
- **Marcos de mapa sin convertir (Era a Forever):** 11 pasos en orco, trol y no-muerto y 23 en tauren llevan la nota «SIN convertir»:
  Tierras de la Peste del Este (1423: 9 pasos, en Frondavil, Tierras de la Peste del Este y Silithus) y Mulgore (1412: 2 pasos en
  Vallefresno y, solo en tauren, 12 más en el inicio de raza `01-mulgore`). La transformación de esas zonas aún no existe (ver `docs/IMPORT.md`, «Coordenadas y marcos»).
- **Entradas que fallaron:** ninguna. El error de `fly` sin `zone` visto en la cadena de la Alianza no aparece en estas 104 ejecuciones.
- **Recuentos por objetivo, escoltas, élite, altura `z`:** limitaciones de `docs/IMPORT.md`.

## Cobertura del español

- **Textos de plantilla (`text`):** en español en todos los pasos salvo 21-22 por guía (0,6 %), que son notas de Polestar sin traducción y llevan `[EN]`.
- **Consejos (`tip`):** Polestar solo trae esES de una parte: 800-815 de ~1300 pasos con consejo (62 %) llevan `[EN]` (en total, 820-836 pasos
  por guía = 24,5-25,5 % de los pasos tienen algún texto en inglés).
- **Nombres (misiones, PNJ, objetos) con la versión esES de Polestar** (`addon/Polestar_esES/Names.lua`): faltan 675-691 nombres distintos por guía,
  casi todos subzonas (279-284), PNJ (271-292), mapas (39), misiones (42-49) y hechizos (15-18); salen en inglés. Se cubrirán con el
  volcado del cliente (`/senda volcar`, plan 6c) y las fichas `{npc:id}`.

## Validación

`python tools/validate.py`: **0 errores** con las cuatro guías (los 16 avisos son anteriores y ajenos: talentos «disputed» sin `sources`).
No se ejecutó `build.py`, ni el simulador. Todo el contenido nuevo es GPL-3 derivado de Polestar con su origen en cada paso; sin datos de Leffe,
DingDB, AtlasLoot, RareScanner, DungeonJournal ni QuestieDB.

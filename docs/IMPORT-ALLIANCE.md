# Importación de Polestar: las cinco rutas de Alianza (sin filtro de clase)

Generado con `tools/import_polestar.py` (sin cambios) sobre el clon de Polestar en el commit
`19bd636e7d6f33231770f6029c76d2d4dfc63798` (GPL-3; cada paso lleva `sources = ["polestar:<commit>/<guía>#<paso>"]`).
`python tools/validate.py`: **0 errores** (no se ha ejecutado `build.py`). Complementa a `docs/IMPORT.md` e `docs/IMPORT-REPORT.md`
(rutas por clase de la ronda anterior).

## Qué se ha importado

Una carpeta por raza, `data/guides/ps-alliance-<raza>/`, con el inicio de la raza y después la cadena Alianza que enlaza con `next`
(de `02-westfall` a `50-60/06-silithus`, 29 guías). Cada guía de Polestar es una sección `NN-nombre.toml`.

| Carpeta | Raza | Cadena de inicio | Guías (secciones) | Pasos | Misiones distintas |
|---|---|---|---:|---:|---:|
| `ps-alliance-human` | Human | `human/01-elwynn-forest` | 30 | 3462 | 993 |
| `ps-alliance-dwarf` | Dwarf | `dwarf/01-dun-morogh` | 30 | 3520 | 1011 |
| `ps-alliance-gnome` | Gnome | `gnome/01-dun-morogh` | 30 | 3483 | 997 |
| `ps-alliance-nightelf` | NightElf | `nightelf/01-teldrassil` + `nightelf/02-darkshore` | 31 | 3531 | 996 |
| `ps-alliance-skyborne` | Skyborne | `skyborne/01-zephras-isle` | 30 | 3560 | 1014 |

Skyborne existe en los compilados de Polestar y el esquema ya lo admite.

Mecanismo (igual que `nightelf-druid-ps`): `order = -1` (nunca se elige sola; solo con `/senda guide ps-alliance-<raza>`),
`status = "unverified"`, `faction = "Alliance"`, `races` de un solo valor. **`classes` lleva las nueve clases**: no se pasó `--class`, así que
los `only` de clase de Polestar se conservan como `if.class` y una guía sirve a cualquier clase. Los objetivos de otras razas sí se descartan
(`--race`): 171-216 por guía. Se pasó `--compare` a una guía inexistente: no hay fusión con textos de Senda, todo es salida pura de Polestar.

Ids únicos en todo el repositorio: pasos `ahu|adw|agn|ane|asb` + número de guía + `-NNN` (p. ej. `ahu09-053`); secciones `<tag>-NN-<nombre>`.
Los TOML se generaron con una ejecución del importador por guía de Polestar en un directorio temporal y un montaje posterior (script de una sola vez,
fuera del repositorio) que copia las secciones, reescribe el id de sección y escribe `guide.toml`.

## Pasos por franja de nivel

Por nivel de entrada de la sección de Polestar (las secciones solapan niveles).

| Franja | Human | Dwarf | Gnome | NightElf | Skyborne |
|---|---:|---:|---:|---:|---:|
| 1-10 | 265 | 349 | 315 | 304 | 369 |
| 11-20 | 406 | 385 | 386 | 392 | 371 |
| 21-30 | 725 | 718 | 718 | 762 | 756 |
| 31-40 | 708 | 710 | 706 | 715 | 706 |
| 41-50 | 670 | 670 | 670 | 670 | 670 |
| 51-60 | 688 | 688 | 688 | 688 | 688 |
| **Total** | 3462 | 3520 | 3483 | 3531 | 3560 |

## Pasos por acción (`do`)

| do | Human | Dwarf | Gnome | NightElf | Skyborne |
|---|---:|---:|---:|---:|---:|
| accept | 977 | 986 | 972 | 978 | 991 |
| turnin | 1013 | 1024 | 1010 | 1015 | 1027 |
| complete | 772 | 796 | 791 | 794 | 798 |
| goto | 296 | 300 | 298 | 317 | 302 |
| fly | 94 | 92 | 92 | 108 | 95 |
| getfp | 37 | 39 | 39 | 40 | 39 |
| loot / buy / use | 79 | 79 | 79 | 84 | 80 |
| level / sethearth / learn_prof | 73 | 75 | 74 | 70 | 71 |
| note (manual) | 121 | 129 | 128 | 125 | 157 |

## Pasos que no se pudieron mapear del todo

Ninguna guía falló al importar (150 ejecuciones del importador, 0 fallos). Lo que queda sin expresar, por guía (Human; las otras razas, ±5 %):

- **Condiciones vivas perdidas:** 215 pasos salen `optional = true` (389 `optional` en total) por un `when` de dinero, grupo, misión lista o
  arma; la condición va a la `note`. Senda aún no tiene condiciones vivas.
- **Pasos manuales (`do = "note"`):** 121, de ellos 50 «entrenar la clase» (Senda necesita `spells` por clase; al no haber filtro de clase aquí
  tampoco se puede inferir) y 71 de otro tipo (objetivos `complete`/`interact` sin misión, marcas). Skyborne tiene 157 por su isla de inicio.
- **Sin coordenadas (`at`):** 59 pasos accept/complete/goto sin `at` (Polestar no da punto para ellos).
- **Marcos de mapa sin convertir:** 8 `goto` por guía llevan coordenadas de Era (nota «SIN convertir»): Tierras de la Peste del Este (1423) y
  Crestagrana (1433, Montañas Crestagrana). Falta la transformación (ver `docs/FOREVER.md`).
- **`fly` sin `zone` (fallo del importador, parcheado en el montaje):** si el paso `fly` es el último de la guía, `zone_for()` no halla destino.
  Entradas: `forever/alliance/07-thousand-needles` (`<tag>09/10-053`, `zone = 1437` Menethil) y `forever/alliance/30-40/06-badlands`
  (`<tag>16/17-093`, `zone = 1445` Theramore). Sin el parche `validate.py` rechaza la guía. Arreglo propuesto: tomar el mapa del nodo de destino.
- **Marcas de escolta, élite y tiempo:** 120-142 pasos por guía solo con aviso en `tip`; **datos no importados** (`pre`, `preAll`, `closedBy`,
  `parent`, recompensas) quedan en la `note`.
- **Los ids de misión no se han verificado contra la base de datos:** todo `status = "unverified"`.

## Cobertura de texto en español

Polestar trae esES para los nombres y solo para parte de las notas. El texto de los pasos se genera en español con plantilla; lo que no tiene
traducción queda en inglés con la marca `[EN]`.

| | Human | Dwarf | Gnome | NightElf | Skyborne |
|---|---:|---:|---:|---:|---:|
| Pasos con `tip` | 1408 | 1437 | 1430 | 1434 | 1403 |
| `tip` con `[EN]` | 861 | 887 | 883 | 880 | 859 |
| `text` con `[EN]` | 11 | 11 | 11 | 11 | 13 |
| Pasos con `[EN]` en `text` o `tip` | 872 | 898 | 894 | 891 | 871 |
| % de pasos con algún `[EN]` | 25,2 | 25,5 | 25,7 | 25,2 | 24,5 |
| Pasos con `if.class` (clases de Polestar) | 241 | 270 | 233 | 285 | 267 |

Es decir, ~75 % de los pasos están en español completo; el `text` (lo que ve el jugador en cada paso) está en español salvo 11-13 pasos, y la
cola en inglés está casi toda en los `tip`. Los importes de nombres sin versión esES (subzonas, algunos hechizos) siguen en inglés y el informe
del importador los lista (≈ 1100-1150 apariciones por raza, muchas repetidas).

## Validación

`python tools/validate.py` → 0 errores, 16 avisos (todos de otras guías existentes). No se ha tocado nada fuera de `data/guides/ps-alliance-*`
ni de este documento.

## Reutilización de terceros

Polestar (GPL-3, commit `19bd636e`): rutas, coordenadas, PNJ, ids y notas esES, vía el importador existente. Cada paso conserva su `sources`.

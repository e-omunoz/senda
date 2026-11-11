# Druida elfo de la noche: ruta de inicio (1-20) y entrada en la ruta compartida

Secciones propias de la ruta de raza (sin nada de clase). Las misiones y visitas de druida (`dr-*`) las intercala el
integrador.

| # | Sección | Niveles | Zona | Pasos | Notas |
|---|---|---|---|---|---|
| 1 | `01-shadowglen` | 1-6 | Cañada Umbría | 43 | Aldrassil, antídoto de Iverron, cueva de arañas (Githyiss), Corona de la Tierra. Nuevas: 97979, 97977, 97236, 96630. |
| 2 | `02-teldrassil` | 6-12 | Dolanaar, Darnassus, Teldrassil | 155 | Hogar en Dolanaar. **Herboristería, Alquimia, Primeros auxilios y Cocina** en Dolanaar (lecciones de campamento de Lyreena). Villa Brisa Estelar, Roca Vil, lago de Denalan, Ban'ethil, Darnassus, Claro del Oráculo. Vuelo gratis a Auberdine (6344 → 6341 → 6342). |
| 3 | `03-darkshore` | 12-20 | Costa Oscura | 143 | Hogar y vuelo en Auberdine. Tres bucles: sur (Ameth'Aran), norte (Bashal'Aran, cascada, torre), sur lejano (Onu, Guja del Maestro) y final en las nagas del norte. Nuevas: 98025, 98042, 98013, 98028, 87760, 98461. |
| 4 | `05-viaje-reinos-del-este` | 20 | Auberdine → Ventormenta | 6 | Barco de Auberdine al puerto de Ventormenta, ruta de vuelo de Ventormenta, rango Experto de Herboristería/Alquimia, salida hacia Elwynn. |

No hay sección `04-`: Vallefresno no compensa porque la ruta compartida sigue en los Reinos del Este. Las misiones de
Costa Oscura que acaban en Vallefresno (Torre de Althalaxx 967+, Therylune, Aynasha, Kerlonian, Volcor) se saltan.

## Punto de unión: `shared:a19-crestagrana`

- El elfo sale de Costa Oscura con nivel 20. Crestagrana (19-21) le queda justa y verde. Además, `a19` empieza en
  Ventormenta («cruza Elwynn hasta Tres Caminos»), que es donde deja el barco, y pone el hogar en Villa del Lago, que
  es lo que `a22` da por hecho («usa la piedra para ir a Villa del Lago»).
- `a11`, `a12`, `a16` y `a17` (10-19) se saltan: son el contenido que el elfo hace en Teldrassil y Costa Oscura.
- **`a21-minas-de-la-muerte` se salta.** Su cadena de La Hermandad Defias empieza en Páramos de Poniente (`a17`):
  sin ella, verify.py da conflicto (92752 sin 92749/92751) y en el juego Wiley no da la misión. Al 21-22 se pasa
  directo al Bosque del Ocaso. Las Minas siguen disponibles en grupo, fuera de la guía.

## Secciones compartidas tras las propias (en orden)

```toml
"shared:a19-crestagrana",
"shared:a22-bosque-del-ocaso",
"shared:a26-los-humedales",
"shared:a30-stv-norte",
"shared:a34-desolace",
"shared:a38-valle-de-huesos",
"shared:a40-ciudad",
"shared:a40-monasterio",
"shared:a41-riverglades",
"shared:a44-badlands",
"shared:a45-feralas",
"shared:a47-tanaris",
"shared:a48-searing-gorge",
"shared:a49-hinterlands",
"shared:a50-ungoro",
"shared:a52-felwood",
"shared:a54-winterspring",
"shared:a55-burning-steppes",
"shared:a57-western-plaguelands",
"shared:a58-eastern-plaguelands",
"shared:a60-endgame",
```

Comprobado en una copia temporal del repo con `guide.toml` provisional: `verify.py` da 0 conflictos en las secciones
propias. Queda un único conflicto en una sección compartida (ver abajo).

## Pendiente para el integrador (archivos compartidos)

- `a19rr-011` (entrega de 65 a Wiley el Negro): el elfo no tiene la misión (viene de Páramos de Poniente). Ponerle
  `optional = true` o un `if` que excluya a `NightElf`.
- `a26wl-004` vuela a Thelsamar y `a26` vuela después a Forjaz: el elfo no tiene esas rutas de vuelo. Añadir para
  `if = { race = ["NightElf"] }` un tramo Ventormenta → tranvía → Forjaz (ruta de vuelo) → Loch Modan (Thelsamar), o
  ir en barco Auberdine–Menethil.
- 98461 Unrequited Love (opcional, cogida en Costa Oscura) se entrega a Tarrel Rockweaver (PNJ 2096, Menethil 11.5,
  52.2): falta un paso `turnin` en `a26` con `if = { race = ["NightElf"] }`.
- 6343 Return to Nessa (Auberdine → Rut'theran) no está en la ruta. Si el viaje de druida a Darnassus del 12-14
  (`dr-11-lunaclaw`) pasa por Rut'theran, se puede coger en Auberdine y entregar allí.

## Pendiente de verificar en el juego

- **Barco Auberdine → puerto de Ventormenta.** Solo lo da games.gg. Si no existe, se usa el barco a Menethil
  (el paso lo avisa en `tip`). Las coordenadas de los dos muelles son aproximadas.
- Coordenada del portal de Darnassus a Rut'theran (aproximada, 88, 40 del mapa de Darnassus).
- Si Lyreena deja coger las cuatro lecciones de campamento a la vez.
- Nombres en esES de las misiones y PNJ nuevos de Forever (los textos los describen sin nombre propio cuando hay dudas).
- Ids de nodo de vuelo (Rut'theran 27, Auberdine 26, Ventormenta 2): son los de Classic.

Fuentes del orden: https://games.gg/world-of-warcraft/guides/wow-forever-teldrassil-leveling/ y
https://games.gg/world-of-warcraft/guides/wow-forever-darkshore-leveling-guide/. Ids y coordenadas: QuestieDB de
Forever (local).

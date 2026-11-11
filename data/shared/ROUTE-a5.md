# Ruta compartida de la Alianza 45-60 (brujo gnomo y mago humano)

Orden de las secciones (`shared:<id>`). Sigue a `a44-badlands` (tramo 30-45, ver `ROUTE-a3.md`).

| # | Sección | Niveles | Zona | Notas |
|---|---|---|---|---|
| 1 | `a45-feralas` | 45-47 | Feralas (Bastión Plumaluna) | Llegada desde Forjaz por Theramore y Punta de Nijel. Piedra en Plumaluna. Solarsal, mensajero perdido, gordunni, Grimtotem, Zorbin, Shay. |
| 2 | `a47-tanaris` | 47-48 | Tanaris (Gadgetzan) | Piedra en Gadgetzan (se mantiene hasta el 50). Zul'Farrak y Prisión de la Isla de Alcaz opcionales. |
| 3 | `a48-searing-gorge` | 48-49 | Forjaz / La Garganta de Fuego | Entrenar 46-48 en Forjaz. Puesto del Torio y Kalaran. |
| 4 | `a49-hinterlands` | 49-50 | Tierras del Interior (Nido Aguileño) | Trols Witherbark, Roca Skulk, tragan de Sprinkle. |
| 5 | `a50-ungoro` | 50-52 | Forjaz / Cráter de Un'Goro | Entrenar el 50 en Forjaz, piedra a Gadgetzan, Noggenfogger, Refugio de Marshal. Entrenamiento opcional del 52 (portal del mago). |
| 6 | `a52-felwood` | 52-54 | Frondavil | Santuario Esmeralda, Jaedenar, Fauces de Madera. |
| 7 | `a54-winterspring` | 54-56 | Cuna del Invierno | Túnel de Fauces de Madera, Donova, Caída Estelar. Piedra en Vista Eterna. |
| 8 | `a55-burning-steppes` | 55-57 | Ventormenta / Las Estepas Ardientes | Entrenar 52-56 en Ventormenta, piedra en Ventormenta. Inicio de la armonización de Onyxia (Los verdaderos amos). PRN y CRNI opcionales. |
| 9 | `a57-western-plaguelands` | 57-58 | Tierras de la Peste del Oeste | Calderos, Andorhal (Cromi), Darrowshire. Entrenamiento opcional del 58 en Forjaz. |
| 10 | `a58-eastern-plaguelands` | 58-60 | Tierras de la Peste del Este | Tirion, Pamela, Esperanza de la Luz (piedra). Scholomance, Stratholme, Blackmaw Hold y Terraza del Modelador opcionales. |
| 11 | `a60-endgame` | 60 | Ventormenta | Entrenar el 60, armonización de Onyxia, bandas del 9-dic-2026 (Barrow Deeps, Cumbre Hyjal, Onyxia), Monte Hyjal. |

Para la guía:

```toml
"shared:a45-feralas", "shared:a47-tanaris", "shared:a48-searing-gorge", "shared:a49-hinterlands",
"shared:a50-ungoro", "shared:a52-felwood", "shared:a54-winterspring", "shared:a55-burning-steppes",
"shared:a57-western-plaguelands", "shared:a58-eastern-plaguelands", "shared:a60-endgame",
```

Entrenamiento: pasos `train` por clase con `if = { class = [...], minlevel = N }` (instructores de Forjaz al 48/50/58 y de
Ventormenta al 52-56 y 60). Los ids de hechizo son los rangos de Classic: si Forever los cambió, el paso se marca a mano.
Las misiones de clase (Inferno, corcel de la muerte, etc.) no están aquí.

Decisiones:
- Las zonas nuevas no son ruta de leveo en este tramo: Monte Hyjal es contenido de nivel 60, Shen'dralas y Riverglades
  quedan por debajo del 45 y QuestieDB no tiene misiones de Hyjal.
- Se saltan cadenas con viajes largos: Linken (elixir de Feralas), la purificación del agua de Jaedenar (Los Baldíos),
  el agua de fuego Winterfall (dos viajes a Frondavil), Thadius (Las Tierras Devastadas) y las entregas en Darnassus.

Pendiente de verificar en el juego:
- Coordenadas aproximadas (sin dato en QuestieDB): Altar de Zul, ruinas de Kel'Theril, carro de Jaron, casas de
  Darrowshire, Northdale, y las entradas de Zul'Farrak, Alcaz, Scholomance y Stratholme.
- Entradas de Blackmaw Hold y Terraza del Modelador; misiones de esas mazmorras.
- Si el túnel de Fauces de Madera es transitable sin reputación y si el vuelo al Puesto del Torio está disponible.
- Ids de hechizos de entrenamiento en Forever.

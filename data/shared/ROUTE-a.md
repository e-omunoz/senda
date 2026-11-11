# Ruta compartida de la Alianza 10-30 (brujo gnomo y mago humano)

Las dos guías se juntan en **Loch Modan** al 12. El gnomo llega desde Dun Morogh/Forjaz. El humano sale de
Ventormenta en el Tranvía subterráneo con una sección corta propia. A partir de ahí la ruta es la misma.
Acaba en Forjaz al 30. Sigue con `ROUTE-a3.md` (`a30-stv-norte`).

| # | Sección | Niveles | Zona | Notas |
|---|---|---|---|---|
| 0 | `a11-humano-tranvia` | 10-12 | Ventormenta → Forjaz | **Solo humanos** (`if race = Human`). Ruta de vuelo de Ventormenta, tranvía y ruta de vuelo de Forjaz. |
| 1 | `a12-loch-modan` | 12-16 | Dun Morogh (Earthseer Farsen) y Loch Modan | **Aquí entra el gnomo.** Cadena de Farsen (llave de Hall of Thanes), Thelsamar (vuelo y hogar), viaje a Forjaz al 14 para entrenar (12 y 14). Misiones de Brock solo para gnomos y enanos. |
| 2 | `a16-hall-of-thanes` | 16-17 | Forjaz | Entrenar el 16. Hall of Thanes (mazmorra nueva, 5 misiones, opcional). Tranvía a Ventormenta. |
| 3 | `a17-paramos-de-poniente` | 16-19 | Páramos de Poniente | Colina del Centinela (vuelo y hogar), misiones nuevas de Alba Fairmoon y Ozwin. **Saco de dormir acogedor** (granja Alexston, opcional). Entrenar el 18 en Ventormenta. |
| 4 | `a19-crestagrana` | 19-21 | Montañas Crestagrana | **Favor de mercader** en Tres Caminos (Marcy Baker, Mivin Shadowweave). Villa del Lago (vuelo y hogar). Entrenar el 20 en Ventormenta; Bastones (brujo) y rango Experto de profesiones. |
| 5 | `a21-minas-de-la-muerte` | 20-22 | Ventormenta / Páramos de Poniente | Cadena de La Hermandad Defias y Minas de la Muerte (opcional, en grupo). |
| 6 | `a22-bosque-del-ocaso` | 22-26 | Bosque del Ocaso | Entrenar el 22, Tres Caminos otra vez, Villa Oscura (vuelo y hogar). Entrenar el 24. Las Mazmorras opcional. |
| 7 | `a26-los-humedales` | 26-30 | Los Humedales | Entrenar el 26 en Ventormenta, Dun Algaz, Menethil (vuelo y hogar), hub nuevo de Howin Kindfeather, Excavation Site: Wetlands (opcional). Entrenar el 28 y el 30 en Forjaz. |

Para las guías:

```toml
# gnome-warlock (después de 02-dun-morogh y 10-voidwalker)
"shared:a12-loch-modan", "shared:a16-hall-of-thanes", "shared:a17-paramos-de-poniente",
"shared:a19-crestagrana", "shared:a21-minas-de-la-muerte", "shared:a22-bosque-del-ocaso",
"shared:a26-los-humedales",

# human-mage (después de 02-elwynn): igual, con la entrada humana delante
"shared:a11-humano-tranvia", "shared:a12-loch-modan", ...
```

Las secciones de clase (Íncubo/Súcubo al 20, Jennea al 15-16, Andromath al 26, etc.) las intercala el integrador.
Las visitas a instructores de clase de esta ruta llevan `if = { class = [...] }`. Si una guía ya tiene su propia
sección de entrenamiento al mismo nivel (`mg-XX-train`), el paso se completa solo al conocer los hechizos.

## Piedra de hogar

Thelsamar (12-16) → Colina del Centinela (16-19) → Villa del Lago (19-22) → Villa Oscura (22-26) → Menethil (26-30).

## Rutas de vuelo (`node` = id de nodo de vuelo)

Ventormenta (2), Colina del Centinela (4), Villa del Lago (5), Forjaz (6), Puerto de Menethil (7), Thelsamar (8),
Villa Oscura (12).

## Saco de dormir acogedor

En QuestieDB (Alianza): nota en la granja Alexston (Páramos, 37.4, 50.7, misión 79008) → restos quemados en
Los Baldíos (46.4, 73.9) → Sierra Espolón (40.8, 52.6; 39.6, 49.8) → presa de Loch Modan (49.4, 12.9) → Arathi
(22.5, 24.1). Esta ruta solo recoge la nota (paso opcional). Los pasos de Kalimdor y Arathi quedan para las
secciones de nivel 30+ que pasen por allí.

## Mazmorras

- **Hall of Thanes** (13-18): `a16-hall-of-thanes`. Old Ironforge Incursion viene de la cadena de Farsen (Dun Morogh).
- **Minas de la Muerte** (18-22): `a21-minas-de-la-muerte`. La misión de Alba (92753) exige 10 Dinamita gruesa.
- **Las Mazmorras** (24-27): paso opcional en `a22-bosque-del-ocaso`.
- **Excavation Site: Wetlands** (26-29): `a26-los-humedales`.
- **Ruins of Lordaeron** (15-20) se descarta: está sobre Entrañas y no compensa el viaje. **Cavernas de Brazanegra** y
  **City of Dalaran** quedan fuera (Kalimdor y 30+).

## Pendiente de verificar en el juego

- **Coordenadas de Ventormenta.** QuestieDB de Forever da coordenadas del mapa **moderno** (Dungar Longdrink 71.3, 72.2;
  Ursula Deline 39.9, 84.2; Woo Ping 63.9, 69.1). Las notas antiguas (`data/legacy`) dicen que Forever usa el mapa
  clásico (Cordero Degollado 25.3, 78.2; Woo Ping 57.1, 57.7). La ruta usa QuestieDB; hay que confirmarlo en el juego.
- Entrada del tranvía en Ventormenta (69.0, 31.0) y de Las Mazmorras (41.0, 58.0): aproximadas.
- Entrada de Excavation Site: Wetlands (la fuente dice «sobre la Excavación de Whelgar»).
- Hechizo de brujo del 16 (sin id).
- Ids de nodo de vuelo: son los de Classic.

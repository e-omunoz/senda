# WoW Forever: datos técnicos de referencia

Investigación inicial: 11-nov-2026. Cada dato lleva su fuente. Lo que no está confirmado se marca así.
Lo mantiene al día el harness (`harness/`).

## Qué es

- Juego oficial de Blizzard anunciado en la BlizzCon 2026: una versión permanente de WoW en una Azeroth original
  reimaginada. Nivel máximo **60**. Lanzamiento: **4-nov-2026**. Va incluido en la suscripción.
  Fuente: https://worldofwarcraft.blizzard.com/en-us/news/24302093
- La comunidad lo llama «Classic+». No es Classic Era, Anniversary ni progresión por fases.
  Fuente: https://warcraft.wiki.gg/wiki/Patch_1.60
- **Clases y razas:**
  - Las 9 clases clásicas, con habilidades y talentos nuevos o cambiados.
  - Las 8 razas clásicas, más **Skyborne** (Alianza: mago; Horda: chamán), que es de pago.
- **Contenido y sistemas nuevos:**
  - Más de 1000 misiones nuevas.
  - Zonas nuevas: Mount Hyjal, Riverglades, Shen'dralas y Zephras Isle.
  - Zonas originales ampliadas.
  - Mazmorras nuevas: Hall of Thanes, Ruins of Lordaeron, Excavation Site: Wetlands, City of Dalaran…
  - Doble especialización al 40, progresión «Legacy», campamento, Favor de mercader y cambios de profesiones.
- **Calendario (según la wiki):**
  - 9-dic-2026: banda.
  - Invierno 2026/27: modo Hardcore.
  - Primavera y verano de 2027: más contenido.

## Cliente y API (importante para el addon)

- Usa el **cliente moderno (Midnight)**. `## Interface: 16001`.
- Según las notas de API de Blizzard, Forever comparte la arquitectura de interfaz de Mainline: la gran mayoría
  de las API de 12.1.5 están disponibles.
  Fuente: https://warcraft.wiki.gg/wiki/Patch_1.60.1/API_changes/notes
  - Usar `C_QuestLog`, `C_Map`, `C_Timer`, `C_Item`, `C_Spell`, `C_TaxiMap`, `C_Container`.
  - **No** contar con las globales clásicas (`GetQuestLogTitle`, `GetSpellInfo` global, etc.). Usar siempre una
    capa de compatibilidad con comprobación de existencia.
- **Restricciones de Midnight:**
  - El registro de combate está cerrado a los addons.
  - Hay «valores secretos» en ciertas API durante el combate.
  - Los GUID de criaturas y objetos ofuscan el servidor y el id de aparición.
  - **Sin confirmar:** si el id de criatura sigue siendo legible. El grabador debe tolerar que no lo sea.
- **Mapas:**
  - Forever usa **uiMapID de estilo Classic**: Kalimdor 1414, Reinos del Este 1415, Dun Morogh 1426,
    Forjaz 1455, Ventormenta 1453, Elwynn 1429.
  - Fuente: tablas de zonas de QuestieDB para Forever, build 1.60.1.70291. Ventormenta usa el mapa clásico.
  - **Cuatro zonas tienen otros límites de mapa que en Classic Era:**

    | Zona | uiMapID | areaId |
    |---|---|---|
    | Ventormenta | 1453 | 1519 |
    | Montañas Crestagrana | 1433 | 44 |
    | Mulgore | 1412 | 215 |
    | Tierras de la Peste del Este | 1423 | 139 |

    En esas zonas, una coordenada de Classic Era hay que transformarla: `forever = era * escala + desplazamiento`.
    En Ventormenta, por ejemplo: `x * 0.7737 + 19.68`, `y * 0.7738 + 24.43`.
    Fuente: `QuestieDB/src/support/eraToForever.lua`, límites DBC 1.15.9 → 1.60.1.
  - Comprobación: Gakin vale 25.3, 78.2 en Era y 39.2, 85.2 en Forever. Este segundo valor coincide con
    QuestieDB y con las guías de Forever (ConquestCapped y Warcraft Tavern dan unos 39, 84.5).
  - Por eso las coordenadas de Ventormenta de BrujoGnomoGuia 4.1.0 (Gakin 25.3, 78.2; Woo Ping 57.1, 57.7) son
    del marco de Era y hay que convertirlas. Las equivalentes en Forever son 39.2, 85.2 y 63.9, 69.1.
  - **Comprobado en el juego el 11 de noviembre de 2026:** en Crestagrana, el jugador estaba junto al Alguacil
    Marris en 28.3, 48.x, y QuestieDB da 28.4, 49.0. Las coordenadas de QuestieDB para Forever ya están en el marco de
    Forever, así que no hay que transformarlas. Solo hay que transformar las que vengan de guías de Classic Era.
  - **Nombres en el cliente esES:** «Marshal» se traduce «Alguacil» (Alguacil Marris, Alguacil McBride, Alguacil Dughan).
  - El resto de zonas comparte coordenadas con Era. Aun así, nunca se copian coordenadas de guías de Classic sin
    verificarlas.

## Fuentes

Oficiales:
- https://worldofwarcraft.blizzard.com/forever
- Foros EE. UU.: https://us.forums.blizzard.com/en/wow/c/wow-forever/347
- Foros UE: https://eu.forums.blizzard.com/en/wow/c/wow-forever/359
- Notas de desarrollo: https://us.forums.blizzard.com/en/wow/t/2360696
- Seguimiento de mensajes azules (Wowhead): https://www.wowhead.com/forever/blue-tracker

Comunitarias:
- https://warcraft.wiki.gg/wiki/Patch_1.60
- https://www.warcrafttavern.com/forever/
- https://www.icy-veins.com/wow-forever/class-guides
- https://mobalytics.gg/wow-forever
- https://gamer-guides.com/wiki/wow-forever/
- https://kami-labs.fr/en/addons-wow-forever/

Base de datos local:
- QuestieDB (flavor `Forever`) instalada por el usuario. Licencia «all rights reserved»: se usa solo para
  verificar en local y **no se redistribuye**.

## Competencia

| Addon | Cobertura en Forever |
|---|---|
| RestedXP | Rutas 1-35 |
| Guidelime | Rutas Forever 1-30; después usa la ruta vanilla, que no encaja con las zonas rehechas |
| Questie | Base de datos de misiones |

Fuente: https://kami-labs.fr/en/addons-wow-forever/ y las incidencias de Guidelime en GitHub.

Senda quiere cubrir **1-60 completo, con rutas específicas de Forever y datos verificados**.

# Cómo escribir rutas de Senda

Guía para quien escriba rutas, sea persona o agente de IA.

## Antes de empezar, lee

- `docs/ARCHITECTURE.md`: formato de guía, sección y paso, tipos de `do` y filtros `if`.
- `schema/section.schema.json`: fuente de verdad del formato.
- `docs/FOREVER.md`: Forever **no es Classic**. Tiene zonas rehechas, más de 1000 misiones nuevas, mazmorras
  nuevas (Hall of Thanes, Ruins of Lordaeron, Excavation Site: Wetlands, City of Dalaran…), Favor de mercader,
  el saco de dormir acogedor, etc.
- `data/legacy/*.toml` y `data/knowledge/**`: lo que el jugador ya verificó jugando. Son datos valiosos.

## Herramienta principal: `tools/lookup.py` (QuestieDB de Forever, en local)

```bash
python tools/lookup.py zone-quests 1426 --race Gnome --class WARLOCK --max-level 12 --json
python tools/lookup.py quest 179 --json
python tools/lookup.py npc 658 --json
python tools/lookup.py chain 179
python tools/lookup.py search "Kharanos"
```

**Licencia:** los datos de QuestieDB son «all rights reserved».

- Sí se pueden escribir **ids y coordenadas** en los pasos: son hechos del juego.
- **No** se copian textos de misiones ni descripciones. Los textos de los pasos se escriben con palabras propias.

## Reglas de las rutas

1. **Orden real y eficiente**, como lo haría un jugador experto:
   - Agrupa recogidas y entregas.
   - Encadena objetivos por cercanía.
   - Sube de nivel sin moler.
   - Pon la piedra de hogar en el sitio útil.
   - Coge las rutas de vuelo.
   - Entrena en los niveles pares (los de entrenamiento de clase).
   - Avisa de élites y de las misiones que conviene saltarse.
2. **Cada misión, en su sitio:**
   - `accept`: en el PNJ que la inicia, con `npc` y `at` sacados de lookup.
   - `complete`: en la zona del objetivo, con `at` en el centro de la zona de objetivos y `wps` si hay
     varios puntos.
   - `turnin`: en el PNJ que la termina.
   - Respeta las misiones previas (`chain` en lookup).
3. **Textos en español**, imperativos y breves (máximo unas 140 letras). En `tip`, el consejo de experto: cómo
   hacerlo más rápido, peligros y qué objetos guardar.
   - El nombre de la misión no hace falta: el HUD lo muestra en el idioma del cliente a partir del id.
   - Si nombras un PNJ o un lugar, usa el nombre en español si lo conoces con seguridad. Si no, describe el
     sitio («la cueva al sur del lago»).
4. **Ids únicos** con el prefijo de la sección: `coldridge-001`, `coldridge-002`…
5. **`status`:**
   - Usa `unverified` salvo que tengas la base de datos y además otra fuente independiente (URL oficial o
     comunitaria de confianza).
   - Pon en `sources` lo que usaste: `"questie:quest/179"`, `"questie:npc/658"`, URLs.
   - El verificador (`tools/verify.py --apply-status`) sube a `verified` lo que cumpla las reglas.
6. **Contenido de Forever**: incluye las misiones nuevas cuando sean eficientes (los ids altos, como 96608 o
   99158, son de Forever). Busca en la web guías de leveo de Forever (Warcraft Tavern, Icy Veins, Mobalytics,
   warcraft.wiki.gg) para conocer el orden recomendado y los trucos. Cita las URL.
7. **Comprueba siempre** tus archivos:
   ```bash
   python tools/validate.py
   python tools/verify.py --guide <id>
   ```
   Corrige todos los `conflict` que sean tuyos.

## Vuelos: nunca mandes volar a un nodo que el jugador puede no tener

En Forever, como en Classic, solo se vuela a nodos que ya se han visitado. Un paso `do = "fly"` a un nodo que ningún
`getfp` anterior de la ruta da por conocido deja al jugador que se lo saltó con un «Vuela a X» imposible (y el
planificador de viajes lo manda por donde puede). Dos filtros dinámicos del `if` lo resuelven:

- `if = { fp = ["8"] }`: el paso solo se ve si el nodo 8 se conoce (también acepta el nombre, como el `node` de getfp).
- `if = { nofp = ["8"] }`: el paso solo se ve si el nodo 8 NO se conoce.

Patrón: el `fly` lleva `fp`, y justo después va la alternativa a pie con `nofp` (un `goto` o un `getfp` del nodo, con
el camino explicado); el `getfp` normal que ya había se da por hecho solo si el nodo ya se conoce.

```toml
[[step]]
id = "a26wl-004"
do = "fly"
zone = 1432
text = "Vuela a Thelsamar (Loch Modan)."
if = { fp = ["8"] }

[[step]]
id = "a26wl-ne-02"
do = "getfp"
node = "8"
npc = 1572
at = [1432, 33.9, 51.0]
text = "Sal por la puerta de Forjaz, ve al este por Dun Morogh y entra en Loch Modan por el túnel. Coge la ruta de vuelo de Thelsamar."
```

`python tools/audit_guides.py` falla (`fly-unknown-node`) con cualquier `fly` de las tres guías de personaje cuyo destino no
sea un nodo ya conocido en ese punto (un `getfp` anterior no opcional, o `if.fp` en el propio paso). Ver `docs/AUDIT.md`.
Los dos filtros se validan en `tools/validate.py` (lista no vacía; no el mismo nodo en `fp` y `nofp`) y se compilan tal cual
en el Lua de la guía.

## Composición de las guías

Cada guía (`data/guides/<id>/guide.toml`) lista sus secciones en orden. Las secciones compartidas se escriben
`shared:<id>` y viven en `data/shared/<id>.toml`. Los pasos específicos de una clase dentro de una sección
compartida llevan `if = { class = ["MAGE"] }`.

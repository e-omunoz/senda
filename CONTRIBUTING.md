# Cómo contribuir

1. Las guías se editan en `data/` (TOML). No edites `addon/Senda/Guides` ni `addon/Senda/Knowledge`: los genera `tools/build.py`.
2. Todo paso nuevo lleva `status` y `sources`. Si no tienes fuente, usa `status = "unverified"`.
3. Antes de abrir un PR:
   ```bash
   python tools/validate.py
   python tools/build.py
   ```
4. Usa referencias por id (misión, PNJ, objeto, hechizo), no por nombre: el cliente traduce los nombres.
5. Las coordenadas son las del mapa de **Forever** (uiMapID de estilo Classic). No copies coordenadas de guías de Classic Era sin verificarlas en el juego (`/senda map`).
6. Nunca subas datos extraídos de QuestieDB: su licencia no lo permite.

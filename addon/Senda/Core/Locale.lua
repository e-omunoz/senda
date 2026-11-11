-- Cadenas de la interfaz. Español (esES/esMX) es el idioma principal; el resto de clientes usa inglés.
-- Las claves que falten en inglés se quedan en español. Senda.L guarda las cadenas como claves reales
-- (los módulos las leen con rawget); si una clave no existe, el índice devuelve nil
-- (los módulos usan `L.X or "literal"`).
-- Otros módulos pueden añadir cadenas con Senda:AddLocale(tablaES, tablaEN).
local _, Senda = ...

local esES = {
  -- General
  NO_GUIDE = "Sin guía",
  NO_GUIDE_HINT = "No hay ninguna guía para este personaje. Abre /senda para elegir una.",
  GUIDE_SELECTED = "Guía activa: %s",
  GUIDE_FINISHED = "¡Guía completada!",
  GUIDE_FINISHED_SHORT = "Completada",
  GUIDE_FINISHED_HINT = "Has terminado todos los pasos. Elige otra guía en /senda.",
  GUIDE_NOT_FOR_YOU = "(no es para tu personaje)",
  QUEST_FALLBACK = "Misión #%s",
  ITEM_FALLBACK = "Objeto #%s",
  LEVEL_N = "Nivel %d",
  OPTIONAL_TAG = "(opcional)",
  NOT_APPLICABLE = "(no aplica a tu nivel)",
  COPY_HINT = "Ctrl+C para copiar · Esc para cerrar",
  LINK_TITLE = "Leer más en la web",

  -- Tipos de paso
  DO_goto = "Ve a",
  DO_accept = "Acepta",
  DO_complete = "Completa",
  DO_turnin = "Entrega",
  DO_train = "Aprende",
  DO_learn_prof = "Aprende la profesión",
  DO_skill = "Sube",
  DO_buy = "Compra",
  DO_have = "Consigue",
  DO_loot = "Recoge",
  DO_use = "Usa",
  DO_sethearth = "Vincula la piedra de hogar",
  DO_hearth = "Usa la piedra de hogar",
  DO_getfp = "Descubre el vuelo",
  DO_fly = "Vuela a",
  DO_level = "Objetivo",
  DO_dungeon = "Mazmorra",
  DO_note = "Nota",
  DO_unknown = "Paso",

  -- Profesiones
  PROF_alchemy = "Alquimia", PROF_blacksmithing = "Herrería", PROF_enchanting = "Encantamiento",
  PROF_engineering = "Ingeniería", PROF_herbalism = "Herboristería", PROF_leatherworking = "Peletería",
  PROF_mining = "Minería", PROF_skinning = "Desuello", PROF_tailoring = "Sastrería", PROF_cooking = "Cocina",
  PROF_fishing = "Pesca", PROF_firstaid = "Primeros auxilios", PROF_first_aid = "Primeros auxilios",
  PROF_jewelcrafting = "Joyería", PROF_inscription = "Inscripción",

  -- HUD
  HUD_DONE = "Hecho",
  HUD_SKIP = "Saltar",
  HUD_BACK = "Paso anterior",
  HUD_MORE = "Leer más",
  HUD_PANEL = "Guía",
  HUD_OPEN_PANEL = "Abrir el panel de Senda",
  HUD_COLLAPSE = "Plegar / desplegar",
  HUD_MANUAL_HINT = "Pulsa «Hecho» cuando termines este paso.",
  STATUS_VERIFIED = "Verificado",
  STATUS_VERIFIED_TIP = "Este paso está confirmado por una fuente oficial, por observaciones en el juego o por dos fuentes independientes.",
  STATUS_UNVERIFIED = "Sin verificar",
  STATUS_UNVERIFIED_TIP = "Este paso aún no se ha comprobado. Puede tener coordenadas o datos inexactos.",
  STATUS_DISPUTED = "En disputa",
  STATUS_DISPUTED_TIP = "Las fuentes no coinciden sobre este paso. Revísalo con cuidado y, si puedes, cuéntanos qué has visto.",

  -- Flecha
  ARROW_ARRIVED = "Has llegado",
  ARROW_NO_POSITION = "Posición no disponible aquí",
  ARROW_OTHER_CONTINENT = "Está en otro continente",
  ARROW_TOOLTIP = "Arrastra para mover. Clic derecho: borrar el punto manual.",
  CORPSE = "Tu cadáver",
  CORPSE_IN_RANGE = "Tu cadáver (al alcance: resucita)",

  -- Panel
  TAB_GUIDE = "Guía",
  TAB_OPTIONS = "Opciones",
  GUIDE_TAB_CURRENT = "Paso actual",
  GUIDE_TAB_PROGRESS = "Progreso: %d de %d pasos (%d %%)",
  GUIDE_TAB_EMPTY = "Esta guía no tiene pasos para tu personaje.",
  GUIDE_TAB_ROW_HINT = "Clic: ir a este paso · Clic derecho: marcar / desmarcar",

  -- Opciones
  OPT_SECTION_GENERAL = "General",
  OPT_SECTION_HUD = "HUD",
  OPT_SECTION_ARROW = "Flecha y mapa",
  OPT_DEBUG = "Modo depuración (mensajes en el chat)",
  OPT_SKIP_OPTIONAL = "Saltar los pasos opcionales",
  OPT_SKIP_OPTIONAL_TIP = "Los pasos marcados como opcionales se saltan solos.",
  OPT_MINIMAP = "Botón en el minimapa",
  OPT_RECORD = "Registrar observaciones para mejorar la guía",
  OPT_RECORD_TIP = "Guarda misiones aceptadas/entregadas, PNJ y posiciones (sin nombres de personaje ni de reino) en SendaRecorderDB. Sirve para verificar los datos.",
  OPT_HUD = "Mostrar el HUD",
  OPT_HUD_LOCKED = "Bloquear el HUD",
  OPT_HUD_PREVIEW = "Mostrar los dos pasos siguientes",
  OPT_HUD_COMBAT = "Ocultar el HUD en combate",
  OPT_SCALE = "Escala",
  OPT_ALPHA = "Opacidad",
  OPT_ARROW = "Mostrar la flecha",
  OPT_ARROW_LOCKED = "Bloquear la flecha",
  OPT_ARROW_COMBAT = "Ocultar la flecha en combate",
  OPT_METRES = "Distancias en metros (si no, en yardas)",
  OPT_CORPSE = "Modo cadáver",
  OPT_CORPSE_TIP = "Al morir, la flecha apunta a tu cuerpo y vuelve a la guía al resucitar.",
  OPT_MAP_PIN = "Marcar el destino en el mapa del mundo",
  OPT_TOMTOM = "Enviar también los puntos a TomTom",
  OPT_TOMTOM_TIP = "Solo si TomTom está instalado. La flecha de Senda sigue funcionando.",
  OPT_RESET_PROGRESS = "Reiniciar el progreso",
  OPT_RESET_CONFIRM = "Pulsa otra vez para confirmar",
  OPT_RESET_POSITIONS = "Restablecer posiciones",
  OPT_RESET_POSITIONS_DONE = "Posiciones restablecidas.",
  OPT_EXPORT = "Exportar observaciones",

  -- Grabador
  RECORDER_COUNT = "Observaciones guardadas: %d",
  RECORDER_EXPORT_TITLE = "Observaciones (%d)",
  RECORDER_EXPORT_HINT = "Ctrl+C para copiar. También están en WTF/Account/<cuenta>/SavedVariables/Senda.lua",

  -- Minimapa
  MINIMAP_TIP_LINES = {
    "Clic: abrir o cerrar el panel",
    "Clic derecho: mostrar u ocultar el HUD",
    "Mayús+clic: mostrar u ocultar la flecha",
    "Arrastrar: mover el botón",
  },

  -- Comandos
  SLASH_UNKNOWN = "Comando desconocido: %s",
  SLASH_HELP_HEADER = "Senda %s — comandos:",
  SLASH_HELP_LINES = {
    "/senda — abrir o cerrar el panel",
    "/senda hud — mostrar u ocultar el HUD",
    "/senda guide [id] — listar guías o elegir una",
    "/senda way <x> <y> [texto] — flecha a un punto del mapa actual (/senda way: borrar)",
    "/senda map — mapa y coordenadas actuales",
    "/senda reset — reiniciar el progreso de la guía",
    "/senda export — exportar observaciones",
    "/senda debug — modo depuración",
  },
  SLASH_RESET_CONFIRM = "Escribe /senda reset otra vez en 10 s para reiniciar el progreso de la guía.",
  SLASH_RESET_DONE = "Progreso reiniciado.",
  SLASH_GUIDES_HEADER = "Guías disponibles:",
  SLASH_GUIDE_UNKNOWN = "No existe la guía «%s». Escribe /senda guide para ver la lista.",
  SLASH_WAY_USAGE = "Uso: /senda way <x> <y> [texto]  (coordenadas 0-100 del mapa actual)",
  SLASH_WAY_SET = "Flecha: %s — %s (%.1f, %.1f)",
  SLASH_WAY_CLEARED = "Punto manual borrado.",
  SLASH_MAP_NOPOS = "No se puede leer la posición aquí (mapa: %s).",
  SLASH_DEBUG_ON = "Depuración activada.",
  SLASH_DEBUG_OFF = "Depuración desactivada.",
}

local enUS = {
  NO_GUIDE = "No guide",
  NO_GUIDE_HINT = "There is no guide for this character. Open /senda to choose one.",
  GUIDE_SELECTED = "Active guide: %s",
  GUIDE_FINISHED = "Guide complete!",
  GUIDE_FINISHED_SHORT = "Complete",
  GUIDE_FINISHED_HINT = "You have finished every step. Pick another guide in /senda.",
  GUIDE_NOT_FOR_YOU = "(not for your character)",
  QUEST_FALLBACK = "Quest #%s",
  ITEM_FALLBACK = "Item #%s",
  LEVEL_N = "Level %d",
  OPTIONAL_TAG = "(optional)",
  NOT_APPLICABLE = "(not for your level)",
  COPY_HINT = "Ctrl+C to copy · Esc to close",
  LINK_TITLE = "Read more on the website",

  DO_goto = "Go to", DO_accept = "Accept", DO_complete = "Complete", DO_turnin = "Turn in", DO_train = "Train",
  DO_learn_prof = "Learn profession", DO_skill = "Level", DO_buy = "Buy", DO_have = "Get", DO_loot = "Loot",
  DO_use = "Use", DO_sethearth = "Set hearthstone", DO_hearth = "Hearth", DO_getfp = "Get flight path",
  DO_fly = "Fly to", DO_level = "Goal", DO_dungeon = "Dungeon", DO_note = "Note", DO_unknown = "Step",

  PROF_alchemy = "Alchemy", PROF_blacksmithing = "Blacksmithing", PROF_enchanting = "Enchanting",
  PROF_engineering = "Engineering", PROF_herbalism = "Herbalism", PROF_leatherworking = "Leatherworking",
  PROF_mining = "Mining", PROF_skinning = "Skinning", PROF_tailoring = "Tailoring", PROF_cooking = "Cooking",
  PROF_fishing = "Fishing", PROF_firstaid = "First Aid", PROF_first_aid = "First Aid",
  PROF_jewelcrafting = "Jewelcrafting", PROF_inscription = "Inscription",

  HUD_DONE = "Done", HUD_SKIP = "Skip", HUD_BACK = "Previous step", HUD_MORE = "Read more", HUD_PANEL = "Guide",
  HUD_OPEN_PANEL = "Open the Senda panel", HUD_COLLAPSE = "Collapse / expand",
  HUD_MANUAL_HINT = "Press “Done” when you finish this step.",
  STATUS_VERIFIED = "Verified",
  STATUS_VERIFIED_TIP = "Confirmed by an official source, in-game observations or two independent sources.",
  STATUS_UNVERIFIED = "Unverified",
  STATUS_UNVERIFIED_TIP = "This step has not been checked yet. Coordinates or data may be inaccurate.",
  STATUS_DISPUTED = "Disputed",
  STATUS_DISPUTED_TIP = "Sources disagree about this step. Double-check it and tell us what you saw.",

  ARROW_ARRIVED = "You have arrived",
  ARROW_NO_POSITION = "Position unavailable here",
  ARROW_OTHER_CONTINENT = "On another continent",
  ARROW_TOOLTIP = "Drag to move. Right-click: clear the manual waypoint.",
  CORPSE = "Your corpse",
  CORPSE_IN_RANGE = "Your corpse (in range: resurrect)",

  TAB_GUIDE = "Guide", TAB_OPTIONS = "Options",
  GUIDE_TAB_CURRENT = "Current step",
  GUIDE_TAB_PROGRESS = "Progress: %d of %d steps (%d %%)",
  GUIDE_TAB_EMPTY = "This guide has no steps for your character.",
  GUIDE_TAB_ROW_HINT = "Click: go to this step · Right-click: mark / unmark",

  OPT_SECTION_GENERAL = "General", OPT_SECTION_HUD = "HUD", OPT_SECTION_ARROW = "Arrow and map",
  OPT_DEBUG = "Debug mode (chat messages)",
  OPT_SKIP_OPTIONAL = "Skip optional steps",
  OPT_SKIP_OPTIONAL_TIP = "Steps marked as optional are skipped automatically.",
  OPT_MINIMAP = "Minimap button",
  OPT_RECORD = "Record observations to improve the guide",
  OPT_RECORD_TIP = "Stores accepted/turned-in quests, NPCs and positions (no character or realm names) in SendaRecorderDB to verify the data.",
  OPT_HUD = "Show the HUD", OPT_HUD_LOCKED = "Lock the HUD", OPT_HUD_PREVIEW = "Show the next two steps",
  OPT_HUD_COMBAT = "Hide the HUD in combat", OPT_SCALE = "Scale", OPT_ALPHA = "Opacity",
  OPT_ARROW = "Show the arrow", OPT_ARROW_LOCKED = "Lock the arrow", OPT_ARROW_COMBAT = "Hide the arrow in combat",
  OPT_METRES = "Distances in metres (otherwise yards)",
  OPT_CORPSE = "Corpse mode",
  OPT_CORPSE_TIP = "When you die, the arrow points to your body and returns to the guide after resurrecting.",
  OPT_MAP_PIN = "Mark the destination on the world map",
  OPT_TOMTOM = "Also send waypoints to TomTom",
  OPT_TOMTOM_TIP = "Only if TomTom is installed. Senda's arrow keeps working.",
  OPT_RESET_PROGRESS = "Reset progress", OPT_RESET_CONFIRM = "Click again to confirm",
  OPT_RESET_POSITIONS = "Reset positions", OPT_RESET_POSITIONS_DONE = "Positions reset.",
  OPT_EXPORT = "Export observations",

  RECORDER_COUNT = "Stored observations: %d",
  RECORDER_EXPORT_TITLE = "Observations (%d)",
  RECORDER_EXPORT_HINT = "Ctrl+C to copy. Also in WTF/Account/<account>/SavedVariables/Senda.lua",

  MINIMAP_TIP_LINES = {
    "Click: open or close the panel",
    "Right-click: show or hide the HUD",
    "Shift-click: show or hide the arrow",
    "Drag: move the button",
  },

  SLASH_UNKNOWN = "Unknown command: %s",
  SLASH_HELP_HEADER = "Senda %s — commands:",
  SLASH_HELP_LINES = {
    "/senda — open or close the panel",
    "/senda hud — show or hide the HUD",
    "/senda guide [id] — list guides or choose one",
    "/senda way <x> <y> [text] — arrow to a point on the current map (/senda way: clear)",
    "/senda map — current map and coordinates",
    "/senda reset — reset guide progress",
    "/senda export — export observations",
    "/senda debug — debug mode",
  },
  SLASH_RESET_CONFIRM = "Type /senda reset again within 10 s to reset the guide progress.",
  SLASH_RESET_DONE = "Progress reset.",
  SLASH_GUIDES_HEADER = "Available guides:",
  SLASH_GUIDE_UNKNOWN = "Guide “%s” does not exist. Type /senda guide to list them.",
  SLASH_WAY_USAGE = "Usage: /senda way <x> <y> [text]  (0-100 coordinates on the current map)",
  SLASH_WAY_SET = "Arrow: %s — %s (%.1f, %.1f)",
  SLASH_WAY_CLEARED = "Manual waypoint cleared.",
  SLASH_MAP_NOPOS = "Position cannot be read here (map: %s).",
  SLASH_DEBUG_ON = "Debug enabled.",
  SLASH_DEBUG_OFF = "Debug disabled.",
}

local locale = GetLocale and GetLocale() or "esES"
local spanish = (locale == "esES" or locale == "esMX")

local L = {}
Senda.L = L
Senda.LOCALE = locale

-- Añade cadenas: español como base y, si el cliente no es español, la versión inglesa encima.
function Senda:AddLocale(es, en)
  if type(es) == "table" then
    for k, v in pairs(es) do rawset(L, k, v) end
  end
  if not spanish and type(en) == "table" then
    for k, v in pairs(en) do rawset(L, k, v) end
  end
end

Senda:AddLocale(esES, enUS)

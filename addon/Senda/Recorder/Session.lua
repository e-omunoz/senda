-- Grabador de partidas (esquema 2): mide cuánto tarda de verdad cada paso de una guía.
-- Apagado por defecto (opción "recordSession" o /senda grabar on). Las herramientas de tools/ leen el
-- fichero SavedVariables (tools/ingest_recording.py) y comparan con el tiempo estimado (tools/route_report.py).
--
-- Fragmentos de texto compactos con tope de tamaño: Adaptado de Polestar, addon/Polestar_Recorder/Recorder.lua (ver docs/RECORDING.md).
--
-- Se guarda en SendaRecorderDB (por cuenta), junto a las observaciones del Recorder:
--   chunks = { [seq] = "registro\nregistro\n..." }   registros separados por \t, de 5 min o 16 KiB
--   seq, install (id aleatorio de la cuenta), dropped (fragmentos descartados por el tope), maps[uiMapID] = { w, h } yardas
-- Registros (campo 1 = tipo, campo 2 = dt en décimas de segundo desde el "epoch" de la sesión):
--   c  0  seq  epoch  charId  schema  build      cabecera del fragmento (el reloj sigue entre fragmentos de una sesión)
--   l  dt                                         inicio de sesión (login, /reload o activar la grabación)
--   o  dt                                         fin de sesión (logout, /reload o desactivar)
--   s  dt  guía  paso  motivo  nivel  xp  índice   paso actual; motivo = next|skip|back|pick|auto|guide|login|end
--                                                 (índice = posición del paso en la guía del jugador; "end" = guía terminada)
--   x  dt  ganancia  nivel                        experiencia ganada
--   k  dt  1|0                                    combate sí/no
--   a  dt  1|0                                    ausente (AFK) sí/no
--   d  dt                                         muerte
--   q  dt  a|t|c  misiónId                        misión aceptada / entregada / objetivos completos
--   u  dt  1|0                                    ¿vas en pareja? (grupo de exactamente 2). Nunca se guarda quién
--   p  dt  mapa  x  y                             rastro (x, y en 1/10000 del mapa), cada ~2 s o 10 yd
--   t  dt  1|0                                    rastro reanudado / detenido por 30 min sin moverte
-- Nunca se guardan nombres de personaje ni de reino, chat ni miembros del grupo: solo ids numéricos y de guía.
-- Coste: una lectura de posición y unas pocas comprobaciones por segundo; los fragmentos se refrescan cada 60 s.
local _, Senda = ...
local Compat, Events = Senda.Compat, Senda.Events
local L = Senda.L

local Session = {}
Senda.Session = Session

local SCHEMA = 2
local MAX_BYTES = 4 * 1024 * 1024     -- tope total de fragmentos; se descartan los más antiguos
local CHUNK_SECS, CHUNK_BYTES = 300, 16384
local FLUSH_SECS = 60                  -- el fragmento abierto se refresca así (un cuelgue pierde como mucho esto)
local TICK = 1
local SAMPLE_SECS, SAMPLE_YARDS, MOVE_YARDS = 2, 10, 1
local TRAIL_IDLE = 30 * 60             -- sin moverte tanto rato, el rastro se detiene hasta que vuelvas a moverte
local FALLBACK_W, FALLBACK_H = 3500, 2333

local floor = math.floor
local Num, Try = Compat.Num, Compat.Try

local running = false   -- hay sesión abierta
local gen = 0           -- generación del ticker (para cancelar el anterior)
local buf, bufBytes     -- registros del fragmento abierto
local seq, epoch, base  -- número del fragmento; reloj de la sesión
local chunkStart, lastFlush = 0, 0
local pendingReason
local needLogin = false   -- la sesión empezó antes de que el motor eligiera guía: el primer paso es "login"

local lastGuide, lastStep
local lastXp, lastMax, lastLvl
local afk, duo = false, nil
local questDirty, completeSeen, questBase = false, {}, false
local trail = { map = nil, x = nil, y = nil, t = 0, moveT = 0, on = true }
local sizes = {}        -- uiMapID -> { w, h } en yardas

local function DB() return Senda.recorder end
local function Opt(key) return Senda.db and Senda.db.opts and Senda.db.opts[key] end
local function Enabled() return Opt("recordSession") == true end

------------------------------------------------------------------------------
-- Fragmentos
------------------------------------------------------------------------------

local ALNUM = "0123456789abcdefghijklmnopqrstuvwxyz"

local function RandomId(n)
  local id = {}
  for i = 1, n do
    local k = math.random(1, #ALNUM)
    id[i] = ALNUM:sub(k, k)
  end
  return table.concat(id)
end

-- Id aleatorio por personaje (no sale de su nombre): une sus sesiones sin saber quién es.
local function CharId()
  local db = Senda.db
  if not db then return "0" end
  if type(db.recId) ~= "string" or #db.recId < 6 then db.recId = RandomId(10) end
  return db.recId
end

local function Prepare(db)
  if type(db.chunks) ~= "table" then db.chunks = {} end
  if type(db.maps) ~= "table" then db.maps = {} end
  if type(db.seq) ~= "number" then db.seq = 0 end
  if type(db.dropped) ~= "number" then db.dropped = 0 end
  if type(db.install) ~= "string" or #db.install < 6 then db.install = RandomId(12) end
  db.schema = SCHEMA
end

-- Descarta los fragmentos más antiguos (nunca el abierto) hasta caber en el tope.
local function Trim(db)
  local total = 0
  for _, s in pairs(db.chunks) do total = total + #s end
  if total <= MAX_BYTES then return end
  local keys = {}
  for k in pairs(db.chunks) do keys[#keys + 1] = k end
  table.sort(keys)
  for _, k in ipairs(keys) do
    if total <= MAX_BYTES then break end
    if not (running and k == seq) then
      total = total - #db.chunks[k]
      db.chunks[k] = nil
      db.dropped = db.dropped + 1
    end
  end
end

local function Flush()
  local db = DB()
  if not (db and buf and seq) then return end
  db.chunks[seq] = table.concat(buf, "\n")
  Trim(db)
  lastFlush = GetTime()
end

local function CloseChunk()
  Flush()
  buf, bufBytes = nil, 0
end

local function OpenChunk()
  local db = DB()
  if not db then return false end
  Prepare(db)
  db.seq = db.seq + 1
  seq = db.seq
  local line = table.concat({ "c", 0, seq, epoch, CharId(), SCHEMA, Compat.Build() }, "\t")
  buf, bufBytes = { line }, #line + 1
  chunkStart = GetTime()
  Flush()
  return true
end

local function Clean(v)
  if type(v) == "number" then
    if v == floor(v) then return string.format("%d", v) end
    return string.format("%.1f", v)
  end
  return (tostring(v):gsub("%c", " "))
end

local function Emit(kind, ...)
  if not running then return end
  if not buf and not OpenChunk() then return end
  if GetTime() - chunkStart >= CHUNK_SECS or bufBytes >= CHUNK_BYTES then
    CloseChunk()
    if not OpenChunk() then return end
  end
  local parts = { kind, floor((GetTime() - base) * 10 + 0.5) }
  for i = 1, select("#", ...) do parts[#parts + 1] = Clean((select(i, ...))) end
  local line = table.concat(parts, "\t")
  buf[#buf + 1] = line
  bufBytes = bufBytes + #line + 1
end

------------------------------------------------------------------------------
-- Lecturas
------------------------------------------------------------------------------

local function MapSize(map)
  local s = sizes[map]
  if s then return s end
  local w, h = Try(C_Map and C_Map.GetMapWorldSize, map)
  w, h = Num(w), Num(h)
  if w and h and w > 0 and h > 0 then
    s = { floor(w + 0.5), floor(h + 0.5) }
    local db = DB()
    if db then Prepare(db); db.maps[map] = s end
  else
    s = { FALLBACK_W, FALLBACK_H }
  end
  sizes[map] = s
  return s
end

local function ReadXp()
  return Num(Try(UnitXP, "player")), Num(Try(UnitXPMax, "player")), Compat.PlayerLevel()
end

local function StepSnapshot(reason)
  local E = Senda.Engine
  if not E then return end
  local guide = E:GuideId()
  if not guide then needLogin = true return end
  if needLogin then reason, needLogin = "login", false end
  local entry = E:Entry()
  local id = entry and entry.step and entry.step.id
  if not id and not E:IsFinished() then return end
  if id == lastStep and guide == lastGuide and reason ~= "login" then return end
  lastGuide, lastStep = guide, id
  local xp, _, lvl = ReadXp()
  Emit("s", guide, id or "-", id and reason or "end", lvl or 0, xp or 0, E:Index() or 0)
end

local function CheckDuo()
  local n = Num(Try(GetNumGroupMembers))
  local d = (Try(IsInGroup) and n == 2) and 1 or 0
  if d ~= duo then
    duo = d
    Emit("u", d)
  end
end

local function CheckAfk()
  local a = Try(UnitIsAFK, "player") and true or false
  if a ~= afk then
    afk = a
    Emit("a", a and 1 or 0)
  end
end

-- Misiones con los objetivos completos (registro "q c"): se mira una vez por segundo si el registro cambió.
local function ScanQuests()
  local QL = C_QuestLog
  if not (QL and QL.GetNumQuestLogEntries and QL.GetInfo) then return end
  local n = Num(Try(QL.GetNumQuestLogEntries)) or 0
  local now = {}
  for i = 1, n do
    local info = Try(QL.GetInfo, i)
    local id = type(info) == "table" and Num(info.questID)
    if id and not info.isHeader then
      now[id] = true
      if Compat.IsQuestComplete(id) then
        if not completeSeen[id] then
          completeSeen[id] = true
          if questBase then Emit("q", "c", id) end
        end
      else
        completeSeen[id] = nil
      end
    end
  end
  for id in pairs(completeSeen) do
    if not now[id] then completeSeen[id] = nil end
  end
  questBase = true
end

------------------------------------------------------------------------------
-- Rastro
------------------------------------------------------------------------------

local function YardsBetween(map, x1, y1, x2, y2)
  local s = MapSize(map)
  return math.sqrt(((x2 - x1) * s[1]) ^ 2 + ((y2 - y1) * s[2]) ^ 2)
end

local function SampleTrail(now)
  if Opt("recordTrail") == false then return end
  local map, x, y = Compat.PlayerMapPos()
  if not map then return end
  local sameMap = trail.map == map and trail.x ~= nil
  local moved = sameMap and YardsBetween(map, trail.x, trail.y, x, y) or 0
  if not sameMap or moved >= MOVE_YARDS then trail.moveT = now end
  if trail.on and now - trail.moveT >= TRAIL_IDLE then
    trail.on = false
    Emit("t", 0)
  elseif not trail.on and trail.moveT == now then
    trail.on = true
    Emit("t", 1)
  end
  if not trail.on then return end
  local due = not sameMap or moved >= SAMPLE_YARDS or (now - trail.t >= SAMPLE_SECS and moved >= MOVE_YARDS)
  if not due then return end
  MapSize(map)
  Emit("p", map, floor(x * 10000 + 0.5), floor(y * 10000 + 0.5))
  trail.map, trail.x, trail.y, trail.t = map, x, y, now
end

------------------------------------------------------------------------------
-- Ciclo
------------------------------------------------------------------------------

local function Tick(token)
  if token ~= gen or not running then return end
  local now = GetTime()
  if questDirty then
    questDirty = false
    ScanQuests()
  end
  CheckAfk()
  SampleTrail(now)
  if buf then
    if now - chunkStart >= CHUNK_SECS then
      CloseChunk()
    elseif now - lastFlush >= FLUSH_SECS and not Compat.InCombat() then
      Flush()
    end
  end
  Compat.After(TICK, function() Tick(token) end)
end

function Session:IsRunning() return running end

-- Escribe ya el fragmento abierto en SendaRecorderDB (se hace solo cada 60 s y al cerrar).
function Session:Flush() Flush() end

function Session:Start()
  if running or not DB() then return end
  Prepare(DB())
  running = true
  gen = gen + 1
  epoch, base = time(), GetTime()
  buf, bufBytes = nil, 0
  lastGuide, lastStep, duo, afk, questBase, needLogin = nil, nil, nil, false, false, false
  completeSeen = {}
  trail.map, trail.x, trail.y, trail.t, trail.moveT, trail.on = nil, nil, nil, 0, base, true
  questDirty = false
  lastXp, lastMax, lastLvl = ReadXp()
  OpenChunk()
  Emit("l")
  if Compat.InCombat() then Emit("k", 1) end
  CheckDuo()
  CheckAfk()
  StepSnapshot("login")
  ScanQuests()
  local token = gen
  Compat.After(TICK, function() Tick(token) end)
end

function Session:Stop()
  if not running then return end
  Emit("o")
  CloseChunk()
  running = false
  gen = gen + 1
end

function Session:SetEnabled(on)
  if on then self:Start() else self:Stop() end
end

function Session:Clear()
  local db = DB()
  if not db then return end
  db.chunks, db.maps, db.dropped = {}, {}, 0
  sizes = {}
  buf, bufBytes = nil, 0 -- si hay sesión, el siguiente registro abre un fragmento nuevo
end

function Session:Stats()
  local db = DB()
  local n, bytes = 0, 0
  if db and type(db.chunks) == "table" then
    for _, s in pairs(db.chunks) do n = n + 1; bytes = bytes + #s end
  end
  return n, bytes
end

------------------------------------------------------------------------------
-- Eventos
------------------------------------------------------------------------------

local function OnStepChanged()
  if not running then return end
  StepSnapshot(pendingReason or "auto")
end

local function OnXp()
  if not running then return end
  local xp, mx, lvl = ReadXp()
  if not xp then return end
  if lastXp and lastLvl then
    local gain
    if lvl > lastLvl then gain = (lastMax or 0) - lastXp + xp
    elseif lvl == lastLvl then gain = xp - lastXp end
    if gain and gain > 0 then Emit("x", gain, lvl) end
  end
  lastXp, lastMax, lastLvl = xp, mx, lvl
end

-- Envuelve un método del motor para saber por qué cambia el paso (el resto de cambios son "auto").
local function Wrap(E, name, reason)
  local orig = E[name]
  if type(orig) ~= "function" then return end
  E[name] = function(...)
    local outer = pendingReason == nil
    if outer then pendingReason = reason end
    local res = { pcall(orig, ...) }
    if outer then pendingReason = nil end
    if not res[1] then error(res[2], 0) end
    return unpack(res, 2, table.maxn(res))
  end
end

Senda.Options:Register({ key = "recordSession", label = L.OPT_RECORD_SESSION, tooltip = L.OPT_RECORD_SESSION_TIP,
  type = "toggle", default = false, section = L.OPT_SECTION_GENERAL, order = 91,
  onChange = function(v) Session:SetEnabled(v == true) end })
Senda.Options:Register({ key = "recordTrail", label = L.OPT_RECORD_TRAIL, tooltip = L.OPT_RECORD_TRAIL_TIP,
  type = "toggle", default = true, section = L.OPT_SECTION_GENERAL, order = 92 })

local function Status()
  local n, bytes = Session:Stats()
  Senda:Print(L.SESSION_STATUS, Enabled() and L.SESSION_STATE_ON or L.SESSION_STATE_OFF, n,
    string.format("%.1f KiB", bytes / 1024), Opt("recordTrail") == false and L.SESSION_STATE_OFF or L.SESSION_STATE_ON)
end

local function Switch(v)
  if v == "on" or v == "si" or v == "sí" or v == "yes" then return true end
  if v == "off" or v == "no" then return false end
end

local function Slash(_, args)
  local sub = (args[2] or ""):lower()
  local arg = (args[3] or ""):lower()
  if sub == "" or sub == "estado" or sub == "status" then
    Status()
  elseif Switch(sub) ~= nil then
    Senda.Options:Set("recordSession", Switch(sub))
    Senda:Print(Switch(sub) and L.SESSION_ON or L.SESSION_OFF)
  elseif sub == "rastro" or sub == "trail" then
    local v = Switch(arg)
    if v == nil then Senda:Print(L.SESSION_USAGE) return end
    Senda.Options:Set("recordTrail", v)
    Status()
  elseif sub == "limpiar" or sub == "clear" then
    Session:Clear()
    Senda:Print(L.SESSION_CLEARED)
  else
    Senda:Print(L.SESSION_USAGE)
  end
end

Events:On("SENDA_READY", function()
  local E = Senda.Engine
  if E then
    Wrap(E, "Advance", "next")
    Wrap(E, "Skip", "skip")
    Wrap(E, "Back", "back")
    Wrap(E, "JumpTo", "pick")
    Wrap(E, "SetGuide", "guide")
    Wrap(E, "Reset", "guide")
    Wrap(E, "Evaluate", "auto")
    -- Saltos que no son completar el paso (si no, contarían como "auto"): saltar una misión con las que
    -- dependen de ella, deshacerlo, la colocación desde el registro de misiones y «saltar a su paso».
    Wrap(E, "SkipQuestTree", "skip")
    Wrap(E, "UndoSkip", "pick")
    Wrap(E, "UnskipAll", "pick")
    Wrap(E, "ApplyPlacement", "pick")
  end
  if Senda.Party then Wrap(Senda.Party, "AcceptSync", "skip") end
  if Senda.Slash then
    Senda.Slash:Register("grabar", Slash, L.SESSION_HELP)
    Senda.Slash:Register("record", Slash)
  end
  Events:On("SENDA_STEP_CHANGED", OnStepChanged)
  Events:On("PLAYER_XP_UPDATE", OnXp)
  Events:On("PLAYER_REGEN_DISABLED", function() if running then Emit("k", 1) end end)
  Events:On("PLAYER_REGEN_ENABLED", function() if running then Emit("k", 0) end end)
  Events:On("PLAYER_DEAD", function() if running then Emit("d") end end)
  Events:On("PLAYER_FLAGS_CHANGED", function(_, unit) if running and unit == "player" then CheckAfk() end end)
  Events:On("GROUP_ROSTER_UPDATE", function() if running then CheckDuo() end end)
  Events:On("QUEST_LOG_UPDATE", function() questDirty = true end)
  Events:On("QUEST_ACCEPTED", function(_, a, b)
    local q = Num(b) or Num(a)
    if running and q then Emit("q", "a", q); questDirty = true end
  end)
  Events:On("QUEST_TURNED_IN", function(_, q)
    q = Num(q)
    if running and q then Emit("q", "t", q); completeSeen[q] = nil; questDirty = true end
  end)
  Events:On("PLAYER_LOGOUT", function()
    if running then Emit("o"); CloseChunk(); running = false; gen = gen + 1 end
  end)
  if Enabled() then Session:Start() end
end)

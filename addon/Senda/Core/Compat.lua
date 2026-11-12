-- Capa de compatibilidad sobre la API moderna (Midnight / Forever 1.60).
-- Reglas:
--   * Nunca se llama a una función de Blizzard sin comprobar que existe.
--   * Toda llamada va protegida con pcall: si falla, se devuelve nil y el llamador degrada.
--   * Los "valores secretos" (en combate) se tratan como "desconocido" (nil).
-- Coordenadas: PlayerMapPos devuelve x, y en 0-1. WorldDistance recibe 0-1 y devuelve metros.
local _, Senda = ...

local Compat = {}
Senda.Compat = Compat

local type, pcall, tonumber, select = type, pcall, tonumber, select

-- Llama a fn(...) protegido; devuelve todos los resultados o nada si falla / no existe.
local function Try(fn, ...)
  if type(fn) ~= "function" then return end
  local r = { pcall(fn, ...) }
  if not r[1] then return end
  return select(2, unpack(r, 1, table.maxn(r)))
end
Compat.Try = Try

-- ¿Es un valor secreto de Midnight? (en ese caso no se puede comparar ni operar).
local issecret = _G.issecretvalue
function Compat.IsSecret(v)
  if not issecret then return false end
  local ok, r = pcall(issecret, v)
  return ok and r and true or false
end
local IsSecret = Compat.IsSecret

-- Número utilizable o nil.
local function Num(v)
  if v == nil or IsSecret(v) then return nil end
  if type(v) ~= "number" then return nil end
  if v ~= v then return nil end -- NaN
  return v
end
Compat.Num = Num

------------------------------------------------------------------------------
-- Jugador
------------------------------------------------------------------------------

function Compat.InCombat()
  return (InCombatLockdown and InCombatLockdown()) or false
end

function Compat.PlayerLevel()
  return Num(Try(UnitLevel, "player")) or 1
end

-- Raza en inglés sin espacios ("Gnome", "Human", "NightElf", "Scourge", "Skyborne"...).
function Compat.PlayerRace()
  local _, race = Try(UnitRace, "player")
  return race
end

-- Clase en mayúsculas ("WARLOCK").
function Compat.PlayerClass()
  local _, class = Try(UnitClass, "player")
  return class
end

-- "Alliance" / "Horde" / "Neutral".
function Compat.PlayerFaction()
  return (Try(UnitFactionGroup, "player"))
end

function Compat.IsGhost()
  return (Try(UnitIsGhost, "player")) and true or false
end

function Compat.IsDead()
  return (Try(UnitIsDeadOrGhost, "player")) and true or false
end

function Compat.OnTaxi()
  return (Try(UnitOnTaxi, "player")) and true or false
end

-- Orientación del jugador en radianes (0 = norte, sentido antihorario) o nil si no se puede leer.
function Compat.PlayerFacing()
  return Num(Try(GetPlayerFacing))
end

-- Velocidad actual en yardas/s (o nil).
function Compat.PlayerSpeed()
  local cur, run = Try(GetUnitSpeed, "player")
  cur, run = Num(cur), Num(run)
  if cur and cur > 0 then return cur end
  return run
end

-- Build del cliente: "1.60.1.70291".
function Compat.Build()
  local version, build = Try(GetBuildInfo)
  if not version then return "?" end
  if build and not IsSecret(build) then return tostring(version) .. "." .. tostring(build) end
  return tostring(version)
end

function Compat.IsAddOnLoaded(name)
  local f = (C_AddOns and C_AddOns.IsAddOnLoaded) or _G.IsAddOnLoaded
  local r = Try(f, name)
  return r and true or false
end

-- Nombres de los addons cargados (sin los de Blizzard), para la ventana de informe. Como mucho `max`.
function Compat.LoadedAddons(max)
  local out = {}
  local ns = C_AddOns or _G
  local count = Try(ns.GetNumAddOns or _G.GetNumAddOns)
  local info = ns.GetAddOnInfo or _G.GetAddOnInfo
  local loaded = ns.IsAddOnLoaded or _G.IsAddOnLoaded
  if type(count) ~= "number" or not info or not loaded then return out end
  for i = 1, count do
    local name = Try(info, i)
    if type(name) == "table" then name = name.name end
    if type(name) == "string" and not name:find("^Blizzard_") and Try(loaded, i) then
      out[#out + 1] = name
      if #out >= (max or 40) then break end
    end
  end
  return out
end

------------------------------------------------------------------------------
-- Misiones
------------------------------------------------------------------------------

local QL = C_QuestLog

-- Título de la misión en el idioma del cliente (o nil si aún no está en caché; se pide al servidor).
function Compat.QuestTitle(id)
  id = tonumber(id)
  if not id then return nil end
  local title
  if QL then
    title = Try(QL.GetTitleForQuestID, id)
    if not title and QL.GetQuestInfo then title = Try(QL.GetQuestInfo, id) end
  end
  if not title and _G.C_QuestLog == nil and _G.GetQuestInfo then title = Try(_G.GetQuestInfo, id) end
  if IsSecret(title) then return nil end
  if type(title) == "string" and title ~= "" then return title end
  if QL and QL.RequestLoadQuestByID then Try(QL.RequestLoadQuestByID, id) end
  return nil
end

-- ¿Entregada alguna vez (flag de completada)?
function Compat.IsQuestDone(id)
  id = tonumber(id)
  if not id then return false end
  local r
  if QL and QL.IsQuestFlaggedCompleted then
    r = Try(QL.IsQuestFlaggedCompleted, id)
  elseif _G.IsQuestFlaggedCompleted then
    r = Try(_G.IsQuestFlaggedCompleted, id)
  end
  if IsSecret(r) then return false end
  return r and true or false
end

-- ¿Está en el registro de misiones?
function Compat.IsOnQuest(id)
  id = tonumber(id)
  if not id or not QL then return false end
  if QL.IsOnQuest then
    local r = Try(QL.IsOnQuest, id)
    if r ~= nil and not IsSecret(r) then return r and true or false end
  end
  if QL.GetLogIndexForQuestID then
    local idx = Try(QL.GetLogIndexForQuestID, id)
    return (Num(idx) or 0) > 0
  end
  return false
end

-- ¿Objetivos cumplidos (lista para entregar)?
function Compat.IsQuestComplete(id)
  id = tonumber(id)
  if not id or not QL then return false end
  local r
  if QL.ReadyForTurnIn then r = Try(QL.ReadyForTurnIn, id) end
  if not r and QL.IsComplete then r = Try(QL.IsComplete, id) end
  if IsSecret(r) then return false end
  return r and true or false
end

-- Objetivos: lista de { text, finished, have, need, kind }.
function Compat.QuestObjectives(id)
  id = tonumber(id)
  local out = {}
  if not id or not QL or not QL.GetQuestObjectives then return out end
  local list = Try(QL.GetQuestObjectives, id)
  if type(list) ~= "table" then return out end
  for i, o in ipairs(list) do
    if type(o) == "table" then
      local text = o.text
      if IsSecret(text) or type(text) ~= "string" then text = nil end
      out[i] = {
        text = text,
        finished = (not IsSecret(o.finished)) and o.finished and true or false,
        have = Num(o.numFulfilled),
        need = Num(o.numRequired),
        kind = (not IsSecret(o.type)) and o.type or nil,
      }
    end
  end
  return out
end

------------------------------------------------------------------------------
-- Hechizos
------------------------------------------------------------------------------

local CS = C_Spell
local legacyGetSpellInfo = _G.GetSpellInfo

local function SpellInfo(id)
  if CS and CS.GetSpellInfo then
    local info = Try(CS.GetSpellInfo, id)
    if type(info) == "table" then return info.name, info.iconID or info.originalIconID end
  end
  if legacyGetSpellInfo then
    local name, _, icon = Try(legacyGetSpellInfo, id)
    return name, icon
  end
end

function Compat.SpellName(id)
  local name = SpellInfo(id)
  if IsSecret(name) then return nil end
  return name
end

function Compat.SpellIcon(id)
  local _, icon = SpellInfo(id)
  if not icon and CS and CS.GetSpellTexture then icon = Try(CS.GetSpellTexture, id) end
  if IsSecret(icon) then return nil end
  return icon
end

-- ¿Conoce el jugador el hechizo? Se prueban todas las variantes disponibles.
function Compat.IsSpellKnown(id)
  id = tonumber(id)
  if not id then return false end
  local SB = C_SpellBook
  local checks = {
    SB and SB.IsSpellKnown,
    _G.IsPlayerSpell,
    _G.IsSpellKnown,
    _G.IsSpellKnownOrOverridesKnown,
    SB and SB.IsSpellInSpellBook,
  }
  for i = 1, 5 do
    local f = checks[i]
    if f then
      local r = Try(f, id)
      if r and not IsSecret(r) then return true end
    end
  end
  return false
end

------------------------------------------------------------------------------
-- Objetos
------------------------------------------------------------------------------

local CI = C_Item

function Compat.ItemName(id)
  id = tonumber(id)
  if not id then return nil end
  local name
  if CI and CI.GetItemNameByID then name = Try(CI.GetItemNameByID, id) end
  if not name then
    local f = (CI and CI.GetItemInfo) or _G.GetItemInfo
    name = Try(f, id)
  end
  if IsSecret(name) then name = nil end
  if not name and CI and CI.RequestLoadItemDataByID then Try(CI.RequestLoadItemDataByID, id) end
  return name
end

function Compat.ItemIcon(id)
  id = tonumber(id)
  if not id then return nil end
  local icon
  if CI and CI.GetItemIconByID then icon = Try(CI.GetItemIconByID, id) end
  if not icon then
    local f = (CI and CI.GetItemInfoInstant) or _G.GetItemInfoInstant
    if f then icon = select(5, Try(f, id)) end
  end
  if IsSecret(icon) then return nil end
  return icon
end

-- Unidades en bolsas (sin banco).
function Compat.ItemCount(id)
  id = tonumber(id)
  if not id then return 0 end
  local f = (CI and CI.GetItemCount) or _G.GetItemCount
  return Num(Try(f, id)) or 0
end

-- Id del hechizo que lanza un objeto al usarse (para pasos "use").
function Compat.ItemSpell(id)
  local f = (CI and CI.GetItemSpell) or _G.GetItemSpell
  local _, spellID = Try(f, id)
  return Num(spellID)
end

------------------------------------------------------------------------------
-- Mapas y posición
------------------------------------------------------------------------------

local CM = C_Map

function Compat.BestMap()
  if not CM or not CM.GetBestMapForUnit then return nil end
  return Num(Try(CM.GetBestMapForUnit, "player"))
end

-- Mapa y posición del jugador: map, x, y (0-1). nil en instancias o si no se puede leer.
function Compat.PlayerMapPos()
  local map = Compat.BestMap()
  if not map or not CM.GetPlayerMapPosition then return nil end
  local pos = Try(CM.GetPlayerMapPosition, map, "player")
  if not pos or not pos.GetXY then return nil end
  local x, y = Try(pos.GetXY, pos)
  x, y = Num(x), Num(y)
  if not x or not y or (x == 0 and y == 0) then return nil end
  return map, x, y
end

function Compat.MapInfo(map)
  if not CM or not CM.GetMapInfo or not map then return nil end
  local info = Try(CM.GetMapInfo, map)
  if type(info) == "table" then return info end
end

function Compat.MapName(map)
  local info = Compat.MapInfo(map)
  return info and info.name or nil
end

-- ¿Es `target` el mapa `map` o uno de sus padres?
function Compat.MapContains(map, target)
  local guard = 0
  while map and guard < 10 do
    if map == target then return true end
    local info = Compat.MapInfo(map)
    map = info and info.parentMapID
    if map == 0 then map = nil end
    guard = guard + 1
  end
  return false
end

local function Vec(x, y)
  if _G.CreateVector2D then return CreateVector2D(x, y) end
  return { x = x, y = y, GetXY = function(self) return self.x, self.y end }
end
Compat.Vector = Vec

-- Posición de mundo de (map, x, y en 0-1): continente, norte, oeste (yardas).
function Compat.WorldPos(map, x, y)
  if not CM or not CM.GetWorldPosFromMapPos or not map then return nil end
  local continent, pos = Try(CM.GetWorldPosFromMapPos, map, Vec(x, y))
  if not pos or not pos.GetXY then return nil end
  local wx, wy = Try(pos.GetXY, pos)
  wx, wy = Num(wx), Num(wy)
  if not wx or not wy then return nil end
  return Num(continent) or 0, wx, wy
end

-- Convierte una posición de mundo a coordenadas (0-1) del mapa `map`.
function Compat.MapPosFromWorld(continent, wx, wy, map)
  if not CM or not CM.GetMapPosFromWorldPos then return nil end
  local _, pos = Try(CM.GetMapPosFromWorldPos, continent, Vec(wx, wy), map)
  if not pos or not pos.GetXY then return nil end
  local x, y = Try(pos.GetXY, pos)
  return Num(x), Num(y)
end

local YARD_TO_M = 0.9144

-- Distancia entre dos puntos (x, y en 0-1). Devuelve metros, ángulo, yardas.
-- El ángulo es el rumbo hacia el punto 2 en radianes, medido desde el norte en sentido antihorario
-- (la misma convención que GetPlayerFacing), así que (ángulo - orientación) es el giro relativo.
function Compat.WorldDistance(map1, x1, y1, map2, x2, y2)
  if not (map1 and x1 and y1 and map2 and x2 and y2) then return nil end
  local dN, dW
  local c1, n1, w1 = Compat.WorldPos(map1, x1, y1)
  local c2, n2, w2 = Compat.WorldPos(map2, x2, y2)
  if c1 and c2 then
    if c1 ~= c2 then return nil end -- otro continente: no hay distancia útil
    dN, dW = n2 - n1, w2 - w1
  elseif map1 == map2 and CM and CM.GetMapWorldSize then
    -- Reserva: mismo mapa, usando el tamaño del mapa en yardas.
    local width, height = Try(CM.GetMapWorldSize, map1)
    width, height = Num(width), Num(height)
    if not width or not height or width == 0 then return nil end
    dN = -(y2 - y1) * height
    dW = -(x2 - x1) * width
  else
    return nil
  end
  local yards = math.sqrt(dN * dN + dW * dW)
  local angle = math.atan2(dW, dN)
  return yards * YARD_TO_M, angle, yards
end

-- Posición del cadáver (0-1) en el mapa dado o en sus padres: map, x, y.
function Compat.CorpsePos(map)
  local DI = C_DeathInfo
  if not DI or not DI.GetCorpseMapPosition then return nil end
  local guard = 0
  while map and guard < 6 do
    local pos = Try(DI.GetCorpseMapPosition, map)
    if pos and pos.GetXY then
      local x, y = Try(pos.GetXY, pos)
      x, y = Num(x), Num(y)
      if x and y and (x > 0 or y > 0) then return map, x, y end
    end
    local info = Compat.MapInfo(map)
    map = info and info.parentMapID
    if map == 0 then map = nil end
    guard = guard + 1
  end
end

------------------------------------------------------------------------------
-- Unidades / PNJ
------------------------------------------------------------------------------

-- "Creature-0-1234-0-5678-658-0000ABCDEF" -> 658. Tolera GUID ofuscados o secretos (nil).
function Compat.NpcIdFromGUID(guid)
  if not guid or IsSecret(guid) or type(guid) ~= "string" then return nil end
  local kind, _, _, _, _, id = strsplit("-", guid)
  if kind ~= "Creature" and kind ~= "Vehicle" then return nil end
  id = tonumber(id)
  if id and id > 0 and id < 10000000 then return id end
  return nil
end

function Compat.UnitNpcId(unit)
  local guid = Try(UnitGUID, unit)
  return Compat.NpcIdFromGUID(guid)
end

------------------------------------------------------------------------------
-- Profesiones
------------------------------------------------------------------------------

-- Clave en inglés -> id de línea de habilidad.
Compat.PROF_SKILLLINE = {
  alchemy = 171, blacksmithing = 164, enchanting = 333, engineering = 202, herbalism = 182,
  leatherworking = 165, mining = 186, skinning = 393, tailoring = 197, cooking = 185,
  fishing = 356, firstaid = 129, ["first_aid"] = 129, ["first-aid"] = 129,
  jewelcrafting = 755, inscription = 773,
}

local function NormKey(key)
  return type(key) == "string" and key:lower():gsub("[%s_%-]", "") or key
end

-- Rango actual y máximo de la profesión `key` (o nil, nil si no la tiene).
function Compat.ProfessionRank(key)
  local k = NormKey(key)
  local line = Compat.PROF_SKILLLINE[k] or tonumber(key)
  if not line then return nil end
  -- API moderna: GetProfessions -> índices para GetProfessionInfo (el 7.º valor es la línea).
  if _G.GetProfessions and _G.GetProfessionInfo then
    local idx = { Try(GetProfessions) }
    for i = 1, 6 do
      local p = idx[i]
      if p then
        local name, _, rank, maxRank, _, _, skillLine = Try(GetProfessionInfo, p)
        if name and (skillLine == line) then return Num(rank), Num(maxRank) end
      end
    end
  end
  -- Reserva: líneas de habilidad clásicas, comparando por nombre localizado.
  if _G.GetNumSkillLines and _G.GetSkillLineInfo then
    local wanted
    if C_TradeSkillUI and C_TradeSkillUI.GetTradeSkillDisplayName then
      wanted = Try(C_TradeSkillUI.GetTradeSkillDisplayName, line)
    end
    if wanted then
      for i = 1, (Num(Try(GetNumSkillLines)) or 0) do
        local name, isHeader, _, rank, _, _, maxRank = Try(GetSkillLineInfo, i)
        if not isHeader and name == wanted then return Num(rank), Num(maxRank) end
      end
    end
  end
  return nil
end

------------------------------------------------------------------------------
-- Rutas de vuelo
------------------------------------------------------------------------------

-- Nodos del mapa de vuelo abierto: lista de { id, name, known }.
function Compat.TaxiNodes()
  local out = {}
  local TM = C_TaxiMap
  if not TM or not TM.GetAllTaxiNodes then return out end
  local map = (_G.GetTaxiMapID and Num(Try(GetTaxiMapID))) or Compat.BestMap()
  if not map then return out end
  local nodes = Try(TM.GetAllTaxiNodes, map)
  if type(nodes) ~= "table" then return out end
  local unreachable = Enum and Enum.FlightPathState and Enum.FlightPathState.Unreachable or 2
  for _, n in ipairs(nodes) do
    if type(n) == "table" then
      out[#out + 1] = { id = n.nodeID, name = n.name, known = n.state ~= unreachable }
    end
  end
  return out
end

-- Nombre del lugar donde está vinculada la piedra de hogar.
function Compat.BindLocation()
  local r = Try(_G.GetBindLocation)
  if IsSecret(r) then return nil end
  return r
end

------------------------------------------------------------------------------
-- Temporizadores
------------------------------------------------------------------------------

function Compat.After(sec, fn)
  if C_Timer and C_Timer.After then
    C_Timer.After(sec, fn)
  else
    fn()
  end
end

function Compat.NewTicker(sec, fn)
  if C_Timer and C_Timer.NewTicker then return C_Timer.NewTicker(sec, fn) end
end

------------------------------------------------------------------------------
-- Misiones fallidas y con tiempo
------------------------------------------------------------------------------

-- ¿Está la misión en el registro y fallida (escolta perdida, tiempo agotado)?
-- Adaptado de Polestar, Core/Compat.lua (IsQuestFailed).
function Compat.IsQuestFailed(id)
  id = tonumber(id)
  local QLg = _G.C_QuestLog
  if not id or not (QLg and QLg.IsFailed) or not Compat.IsOnQuest(id) then return false end
  local r = Try(QLg.IsFailed, id)
  if IsSecret(r) then return false end
  return r and true or false
end

-- Segundos que le quedan a una misión con tiempo, o nil si no lo tiene (o ya terminó/falló).
-- C_QuestLog.GetTimeAllowed(id) -> total, transcurrido.
function Compat.QuestTimeLeft(id)
  id = tonumber(id)
  local QLg = _G.C_QuestLog
  if not id or not (QLg and QLg.GetTimeAllowed) then return nil end
  local total, elapsed = Try(QLg.GetTimeAllowed, id)
  total, elapsed = Num(total), Num(elapsed)
  if not total or total <= 0 then return nil end
  local left = total - (elapsed or 0)
  if left <= 0 then return nil end
  return left
end

-- Ids de las misiones del registro que tienen cuenta atrás, con sus segundos restantes: { [id] = left }.
function Compat.TimedQuests()
  local out = {}
  local QLg = _G.C_QuestLog
  if not (QLg and QLg.GetNumQuestLogEntries and QLg.GetInfo and QLg.GetTimeAllowed) then return out end
  local n = Num(Try(QLg.GetNumQuestLogEntries)) or 0
  for i = 1, n do
    local info = Try(QLg.GetInfo, i)
    local q = type(info) == "table" and not info.isHeader and Num(info.questID)
    if q and q > 0 and not Compat.IsQuestFailed(q) then
      local left = Compat.QuestTimeLeft(q)
      if left then out[q] = left end
    end
  end
  return out
end

------------------------------------------------------------------------------
-- Instancias y teclas
------------------------------------------------------------------------------

-- Tipo de instancia ("party", "raid", "pvp", "arena", "scenario", "none") o nil.
function Compat.InstanceType()
  local inst, kind = Try(_G.IsInInstance)
  if IsSecret(inst) or IsSecret(kind) then return nil end
  if not inst then return "none" end
  return type(kind) == "string" and kind or "party"
end

function Compat.ShiftDown()
  local r = Try(_G.IsShiftKeyDown)
  return (not IsSecret(r)) and r and true or false
end

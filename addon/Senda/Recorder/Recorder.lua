-- Grabador de observaciones para el harness (SendaRecorderDB, por cuenta).
-- Cada entrada: { t, kind, quest, npc, map, x, y, level, race, class, build [, role, node, place, n] }
--   kind ∈ accept | turnin | npc_seen | fp | bind
-- Sin nombres de personaje ni de reino. Coordenadas en porcentaje redondeadas a 0.1.
-- Búfer circular de MAX entradas con deduplicación (las repeticiones suben el contador `n`).
local _, Senda = ...
local Compat, Events, Util = Senda.Compat, Senda.Events, Senda.Util

local Recorder = {}
Senda.Recorder = Recorder

local SCHEMA = 2 -- 2: añade los fragmentos de partidas (Session.lua); las observaciones se conservan
local MAX = 5000

local keys = {} -- clave de deduplicación -> entrada

local function Enabled()
  return Senda.db and Senda.db.opts.record ~= false
end

local function R1(v) return v and Util.Round(v, 0.1) or nil end

local function KeyOf(e)
  local fx = e.x and math.floor(e.x) or "-"
  local fy = e.y and math.floor(e.y) or "-"
  return table.concat({ e.kind, tostring(e.quest or "-"), tostring(e.npc or "-"), tostring(e.role or "-"),
    tostring(e.node or "-"), tostring(e.map or "-"), fx, fy }, "|")
end

local function DB()
  local db = Senda.recorder
  if not db then return nil end
  if db.schema ~= SCHEMA or type(db.entries) ~= "table" then
    db.schema = SCHEMA
    db.entries = type(db.entries) == "table" and db.entries or {}
  end
  return db
end

local function RebuildKeys()
  wipe(keys)
  local db = DB()
  if not db then return end
  for _, e in ipairs(db.entries) do keys[KeyOf(e)] = e end
end

-- PNJ con el que se interactúa: "npc" (diálogo/misión) o el objetivo.
local function InteractNpc()
  return Compat.UnitNpcId("npc") or Compat.UnitNpcId("questnpc") or Compat.UnitNpcId("target")
end

-- Añade una observación. `fields` incluye kind y los datos específicos.
function Recorder:Add(fields)
  if not Enabled() then return end
  local db = DB()
  if not db then return end
  local e = fields
  e.t = time and time() or 0
  local map, x, y = Compat.PlayerMapPos()
  if map then
    e.map, e.x, e.y = map, R1(x * 100), R1(y * 100)
  else
    e.map = Compat.BestMap()
  end
  e.level = Compat.PlayerLevel()
  e.race = Compat.PlayerRace()
  e.class = Compat.PlayerClass()
  e.build = Compat.Build()

  local key = KeyOf(e)
  local old = keys[key]
  if old then
    old.n = (old.n or 1) + 1
    old.t = e.t
    return
  end
  local list = db.entries
  list[#list + 1] = e
  keys[key] = e
  while #list > MAX do
    local gone = table.remove(list, 1)
    if gone then keys[KeyOf(gone)] = nil end
  end
  Senda:Debug("Observación: %s %s", e.kind, tostring(e.quest or e.npc or ""))
end

function Recorder:Count()
  local db = DB()
  return db and #db.entries or 0
end

function Recorder:Clear()
  local db = DB()
  if db then wipe(db.entries) end
  wipe(keys)
end

------------------------------------------------------------------------------
-- Exportación (JSON compacto, una observación por línea)
------------------------------------------------------------------------------

local FIELDS = { "t", "kind", "quest", "npc", "map", "x", "y", "level", "race", "class", "build", "role", "node",
  "place", "n" }

local function JsonValue(v)
  if type(v) == "number" then
    if v == math.floor(v) then return string.format("%d", v) end
    return string.format("%.1f", v)
  elseif type(v) == "boolean" then
    return v and "true" or "false"
  end
  local s = tostring(v):gsub('[%c"\\]', function(c)
    if c == '"' then return '\\"' elseif c == "\\" then return "\\\\" end
    return string.format("\\u%04x", c:byte())
  end)
  return '"' .. s .. '"'
end

function Recorder:ExportText()
  local db = DB()
  if not db then return "[]" end
  local lines = {}
  for _, e in ipairs(db.entries) do
    local parts = {}
    for _, f in ipairs(FIELDS) do
      if e[f] ~= nil then parts[#parts + 1] = '"' .. f .. '":' .. JsonValue(e[f]) end
    end
    lines[#lines + 1] = "{" .. table.concat(parts, ",") .. "}"
  end
  return "[\n" .. table.concat(lines, ",\n") .. "\n]"
end

function Recorder:ShowExport()
  local n = self:Count()
  Senda:Print(Senda.L.RECORDER_COUNT, n)
  if Senda.UI and Senda.UI.CopyDialog then
    Senda.UI:CopyDialog(Senda.L.RECORDER_EXPORT_TITLE:format(n), self:ExportText(), Senda.L.RECORDER_EXPORT_HINT)
  end
end

------------------------------------------------------------------------------
-- Eventos
------------------------------------------------------------------------------

local function OnAccepted(_, a, b)
  -- Moderno: (questID). Antiguo: (logIndex, questID).
  local q = Compat.Num(b) or Compat.Num(a)
  if not q then return end
  Recorder:Add({ kind = "accept", quest = q, npc = InteractNpc() })
end

local function OnTurnedIn(_, questID)
  local q = Compat.Num(questID)
  if not q then return end
  Recorder:Add({ kind = "turnin", quest = q, npc = InteractNpc() })
end

local function SeenNpc(role)
  if Compat.InCombat() then return end
  local npc = Compat.UnitNpcId("npc")
  Recorder:Add({ kind = "npc_seen", npc = npc, role = role })
end

local function CurrentTaxiNode()
  local TM = C_TaxiMap
  if not TM or not TM.GetAllTaxiNodes then return nil end
  local map = (_G.GetTaxiMapID and Compat.Num(Compat.Try(GetTaxiMapID))) or Compat.BestMap()
  local nodes = map and Compat.Try(TM.GetAllTaxiNodes, map)
  if type(nodes) ~= "table" then return nil end
  local current = Enum and Enum.FlightPathState and Enum.FlightPathState.Current or 0
  for _, n in ipairs(nodes) do
    if type(n) == "table" and n.state == current then return n.nodeID, n.name end
  end
end

local function OnTaxi()
  local nodeID = CurrentTaxiNode()
  Recorder:Add({ kind = "fp", npc = Compat.UnitNpcId("npc"), node = nodeID })
end

local function OnBound()
  Recorder:Add({ kind = "bind", npc = Compat.UnitNpcId("npc"), place = Compat.BindLocation() })
end

-- Tipos de interacción modernos -> rol.
local function InteractionRoles()
  local roles = {}
  local PIT = Enum and Enum.PlayerInteractionType
  if not PIT then return roles end
  local map = {
    Merchant = "vendor", Trainer = "trainer", ProfessionsTrainer = "trainer", TaxiNode = "flightmaster",
    Binder = "innkeeper", Gossip = "gossip", Banker = "banker", Auctioneer = "auctioneer",
    QuestGiver = "questgiver", StableMaster = "stablemaster",
  }
  for name, role in pairs(map) do
    local v = PIT[name]
    if v ~= nil then roles[v] = role end
  end
  return roles
end

Senda.Options:Register({ key = "record", label = Senda.L.OPT_RECORD, tooltip = Senda.L.OPT_RECORD_TIP,
  type = "toggle", default = true, section = Senda.L.OPT_SECTION_GENERAL, order = 90 })

Events:On("SENDA_READY", function()
  DB()
  RebuildKeys()
  local roles = InteractionRoles()
  Events:On("QUEST_ACCEPTED", OnAccepted)
  Events:On("QUEST_TURNED_IN", OnTurnedIn)
  Events:On("TAXIMAP_OPENED", OnTaxi)
  Events:On("HEARTHSTONE_BOUND", OnBound)
  local hasPIM = Events:On("PLAYER_INTERACTION_MANAGER_FRAME_SHOW", function(_, kind)
    local role = roles[kind]
    if role and role ~= "flightmaster" then SeenNpc(role) end
  end)
  if not hasPIM then
    Events:On("MERCHANT_SHOW", function() SeenNpc("vendor") end)
    Events:On("TRAINER_SHOW", function() SeenNpc("trainer") end)
    Events:On("GOSSIP_SHOW", function() SeenNpc("gossip") end)
  end
end)

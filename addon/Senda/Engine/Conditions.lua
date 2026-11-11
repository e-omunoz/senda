-- Condiciones: filtros `if` y detección de cada tipo de paso (`do`).
--   Cond:StaticFilter(f)      -> clase / raza / facción / profesión (se evalúa al resolver la guía)
--   Cond:LevelFilter(f)       -> minlevel / maxlevel (dinámico, lo usa el motor al avanzar)
--   Cond:Check(step, state)   -> true (cumplido), false (aún no), nil (solo manual)
--   Cond:NeedsPosition(step)  -> el motor activa el temporizador de posición
--   Cond:CanFastForward(step) -> se puede dar por hecho al iniciar sesión si ya se cumple
-- Un tipo desconocido nunca da error: se trata como paso manual.
local _, Senda = ...
local Util, Compat = Senda.Util, Senda.Compat

local Cond = {}
Senda.Conditions = Cond

local DEFAULT_RADIUS = 12 -- metros

-- Metadatos por tipo: icono y comportamiento.
-- ff = se puede adelantar al iniciar sesión; pos = necesita la posición del jugador.
Cond.TYPES = {
  ["goto"]     = { icon = "Interface\\Icons\\INV_Misc_Map_01", pos = true },
  accept       = { icon = "Interface\\GossipFrame\\AvailableQuestIcon", ff = true },
  complete     = { icon = "Interface\\Icons\\Ability_DualWield", ff = true },
  turnin       = { icon = "Interface\\GossipFrame\\ActiveQuestIcon", ff = true },
  train        = { icon = "Interface\\Icons\\INV_Misc_Book_11", ff = true },
  learn_prof   = { icon = "Interface\\Icons\\INV_Misc_Book_09", ff = true },
  skill        = { icon = "Interface\\Icons\\INV_Misc_Note_01", ff = true },
  buy          = { icon = "Interface\\Icons\\INV_Misc_Coin_02", ff = true },
  have         = { icon = "Interface\\Icons\\INV_Misc_Bag_08", ff = true },
  loot         = { icon = "Interface\\Icons\\INV_Misc_Bag_10", ff = true },
  use          = { icon = "Interface\\Icons\\INV_Misc_Gear_01" },
  sethearth    = { icon = "Interface\\Icons\\INV_Misc_Rune_01" },
  hearth       = { icon = "Interface\\Icons\\Spell_Arcane_TeleportIronForge" },
  getfp        = { icon = "Interface\\Icons\\Ability_Hunter_EagleEye", ff = true },
  fly          = { icon = "Interface\\Icons\\Ability_Mount_Gryphon_01" },
  level        = { icon = "Interface\\Icons\\Spell_ChargePositive", ff = true },
  dungeon      = { icon = "Interface\\Icons\\INV_Misc_Key_03", ff = true },
  note         = { icon = "Interface\\Icons\\INV_Misc_Note_01" },
}
Cond.UNKNOWN_ICON = "Interface\\Icons\\INV_Misc_QuestionMark"

function Cond:Icon(step)
  local t = step and self.TYPES[step["do"]]
  return t and t.icon or self.UNKNOWN_ICON
end

------------------------------------------------------------------------------
-- Filtros
------------------------------------------------------------------------------

local function HasAnyProf(list)
  if type(list) ~= "table" then list = { list } end
  for _, p in ipairs(list) do
    if Compat.ProfessionRank(p) then return true end
  end
  return false
end

-- Filtros estáticos (no cambian durante la sesión salvo la profesión).
function Cond:StaticFilter(f)
  if type(f) ~= "table" then return true end
  if f.class and not Util.Contains(f.class, Compat.PlayerClass()) then return false end
  if f.race and not Util.Contains(f.race, Compat.PlayerRace()) then return false end
  if f.faction and f.faction ~= Compat.PlayerFaction() then return false end
  if f.prof and not HasAnyProf(f.prof) then return false end
  return true
end

-- Filtros de nivel: un paso fuera de rango se salta al llegar a él.
function Cond:LevelFilter(f)
  if type(f) ~= "table" then return true end
  local lvl = Compat.PlayerLevel()
  if f.minlevel and lvl < f.minlevel then return false end
  if f.maxlevel and lvl > f.maxlevel then return false end
  return true
end

------------------------------------------------------------------------------
-- Detección
------------------------------------------------------------------------------

-- Misiones de un paso: `quests` (lista) o `quest`.
function Cond:Quests(step)
  if type(step.quests) == "table" and #step.quests > 0 then return step.quests end
  if step.quest then return { step.quest } end
  return nil
end

local function TurnedIn(q, state)
  return (state and state.turnedIn and state.turnedIn[q]) or Compat.IsQuestDone(q)
end

local function AllQuests(step, state, fn)
  local qs = Cond:Quests(step)
  if not qs then return nil end
  for _, q in ipairs(qs) do
    if not fn(q, state) then return false end
  end
  return true
end

local function Accepted(q, state)
  return Compat.IsOnQuest(q) or TurnedIn(q, state)
end

local function Completed(q, state, obj)
  if TurnedIn(q, state) then return true end
  if not Compat.IsOnQuest(q) then return false end
  local objs = Compat.QuestObjectives(q)
  if obj then
    local o = objs[obj]
    if o then return o.finished end
    return Compat.IsQuestComplete(q)
  end
  if Compat.IsQuestComplete(q) then return true end
  if #objs == 0 then return false end
  for _, o in ipairs(objs) do
    if not o.finished then return false end
  end
  return true
end

-- Distancia (metros) del jugador a un punto [map, x, y] en porcentaje.
function Cond:DistanceTo(at)
  if type(at) ~= "table" or not at[1] then return nil end
  local map, x, y = Compat.PlayerMapPos()
  if not map then return nil end
  return (Compat.WorldDistance(map, x, y, at[1], (at[2] or 0) / 100, (at[3] or 0) / 100))
end

local function InZone(zone)
  return zone and Compat.MapContains(Compat.BestMap(), zone) or false
end
Cond.InZone = InZone

local function FpKnown(step)
  local node = step.node
  if not node then return false end
  local fps = Senda.db and Senda.db.char and Senda.db.char.fps
  if not fps then return false end
  local nid = tonumber(node)
  for id, name in pairs(fps) do
    if (nid and id == nid) or (type(name) == "string" and name:lower() == tostring(node):lower()) then
      return true
    end
    -- coincidencia parcial ("Thelsamar" dentro de "Thelsamar, Loch Modan")
    if type(name) == "string" and not nid and name:lower():find(tostring(node):lower(), 1, true) then
      return true
    end
  end
  return false
end
Cond.FpKnown = FpKnown

local checks = {}

checks["goto"] = function(step)
  if not step.at then return nil end
  local d = Cond:DistanceTo(step.at)
  if not d then return false end
  return d <= (step.radius or DEFAULT_RADIUS)
end

checks.accept = function(step, state) return AllQuests(step, state, Accepted) end

checks.complete = function(step, state)
  local qs = Cond:Quests(step)
  if not qs then return nil end
  for _, q in ipairs(qs) do
    if not Completed(q, state, step.obj) then return false end
  end
  return true
end

checks.turnin = function(step, state) return AllQuests(step, state, TurnedIn) end

checks.train = function(step)
  if type(step.spells) ~= "table" or #step.spells == 0 then return nil end
  for _, id in ipairs(step.spells) do
    if not Compat.IsSpellKnown(id) then return false end
  end
  return true
end

checks.learn_prof = function(step)
  if not step.prof then return nil end
  return Compat.ProfessionRank(step.prof) ~= nil
end

checks.skill = function(step)
  if not step.prof or not step.skill then return nil end
  local rank = Compat.ProfessionRank(step.prof)
  return rank ~= nil and rank >= step.skill
end

local function ItemCheck(step)
  if not step.item then return nil end
  return Compat.ItemCount(step.item) >= (step.count or 1)
end
checks.buy, checks.have, checks.loot = ItemCheck, ItemCheck, ItemCheck

checks.use = function(step, state)
  if state and state.used then return true end
  return nil
end

checks.sethearth = function(step, state)
  if state and state.bound then return true end
  return nil
end

checks.hearth = function(step, state)
  state = state or {}
  if step.zone then
    if not InZone(step.zone) then return false end
    return (not state.startedInZone) or state.hearthCast or false
  end
  if state.hearthCast and state.zoneChanged then return true end
  return nil
end

checks.getfp = function(step, state)
  if state and state.fpFound then return true end
  if FpKnown(step) then return true end
  if not step.node then return nil end
  return false
end

checks.fly = function(step, state)
  if not step.zone then return nil end
  state = state or {}
  if Compat.OnTaxi() or not InZone(step.zone) then return false end
  return (not state.startedInZone) or state.sawTaxi or false
end

checks.level = function(step)
  if not step.level then return nil end
  return Compat.PlayerLevel() >= step.level
end

checks.dungeon = function(step, state)
  local r = AllQuests(step, state, TurnedIn)
  if r then return true end
  return nil
end

checks.note = function() return nil end

-- true / false / nil (manual). Nunca lanza error.
function Cond:Check(step, state)
  if type(step) ~= "table" then return nil end
  local fn = checks[step["do"]]
  if not fn then return nil end
  local ok, r = pcall(fn, step, state)
  if not ok then
    Senda:Debug("Error al comprobar %s: %s", tostring(step.id), tostring(r))
    return nil
  end
  return r
end

-- ¿Puede completarse solo? (false = solo manual)
function Cond:IsAuto(step)
  if type(step) ~= "table" then return false end
  local d = step["do"]
  if d == "note" or not checks[d] then return false end
  if d == "goto" then return step.at ~= nil end
  if d == "accept" or d == "turnin" or d == "complete" or d == "dungeon" then return self:Quests(step) ~= nil end
  if d == "train" then return type(step.spells) == "table" and #step.spells > 0 end
  if d == "buy" or d == "have" or d == "loot" then return step.item ~= nil end
  if d == "level" then return step.level ~= nil end
  if d == "learn_prof" or d == "skill" then return step.prof ~= nil end
  if d == "fly" then return step.zone ~= nil end
  return true
end

function Cond:NeedsPosition(step)
  if type(step) ~= "table" then return false end
  local t = self.TYPES[step["do"]]
  return (t and t.pos and step.at ~= nil) or false
end

function Cond:CanFastForward(step)
  local t = step and self.TYPES[step["do"]]
  return (t and t.ff) or false
end

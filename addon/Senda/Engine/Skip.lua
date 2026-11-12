-- Saltar una misión y todas las que dependen de ella, con Deshacer.
--   Engine:SkipQuestTree(q)   -> info { quest, list = {ids}, count } (count: dependientes de esta guía) o nil
--   Engine:UndoSkip([info])   -> devuelve las misiones al camino (por defecto, la última saltada)
--   Engine:UnskipAll()        -> devuelve todas las saltadas del personaje
--   Engine:LastSkip()         -> info del último salto de esta sesión (para el aviso del HUD) o nil
--   Engine:SkippedCount()     -> cuántas misiones tiene saltadas el personaje
-- Las misiones saltadas se guardan por personaje en SendaDB.skippedQuests y valen para todas las guías:
-- Engine.lua trata sus pasos como saltados (marca "s") sin tocar el progreso de cada guía, así que deshacer
-- es quitarlas del conjunto. Las dependientes salen del índice que compila tools/build.py (requisitos de
-- forever-db, o el orden de las guías): Senda.Guides:Followups(q).
-- Idea tomada de Polestar (Core/Engine.lua, SkipQuest y SkipLoses); el código es propio.
local _, Senda = ...
local Events = Senda.Events
local Engine = Senda.Engine

local function Set()
  local db = Senda.db
  if not db then return nil end
  db.skippedQuests = db.skippedQuests or {}
  return db.skippedQuests
end

function Engine:SkippedCount()
  local n = 0
  for _ in pairs(Set() or {}) do n = n + 1 end
  return n
end

function Engine:IsQuestSkipped(q)
  local set = Set()
  return set ~= nil and set[q] == true
end

function Engine:LastSkip() return self.lastSkip end

-- Misiones que saltar con `q`: las que dependen de ella y aún no tienes en el registro ni entregadas.
function Engine:SkipPlan(q)
  local set = Set()
  local list, count = {}, 0
  if not set or type(q) ~= "number" or set[q] then return list, count end
  list[1] = q
  for _, d in ipairs(Senda.Guides:Followups(q) or {}) do
    if not set[d] and not self:QuestTaken(d) then
      list[#list + 1] = d
      if self.acceptIndex and self.acceptIndex[d] then count = count + 1 end
    end
  end
  return list, count
end

-- Primer paso (índice) de la guía actual que tiene alguna de estas misiones.
local function FirstIndex(list)
  local want = {}
  for _, q in ipairs(list) do want[q] = true end
  for i, e in ipairs(Engine.steps) do
    for _, q in ipairs(Senda.Conditions:Quests(e.step) or {}) do
      if want[q] then return i end
    end
  end
  return nil
end

local function Reposition(self, reason)
  self.held = nil
  self:MoveTo(self:NextPending(self.index))
  self:RequestEvaluate(0.1, reason)
end

function Engine:SkipQuestTree(q)
  local set = Set()
  if not set or type(q) ~= "number" or set[q] then return nil end
  local list, count = self:SkipPlan(q)
  for _, id in ipairs(list) do set[id] = true end
  local info = { quest = q, list = list, count = count }
  self.lastSkip = info
  Reposition(self, "skiptree")
  Events:Fire("SENDA_SKIPPED", info)
  Events:Fire("SENDA_STEP_UPDATED", self.steps[self.index])
  return info
end

local function Restore(self, list)
  local set = Set()
  if not set then return end
  for _, id in ipairs(list) do set[id] = nil end
  -- Con las misiones de vuelta, el camino puede volver a un paso anterior: se recoloca en el primero.
  local first = FirstIndex(list)
  self.held = nil
  if first and first < self.index then
    self:MoveTo(self:NextPending(first))
  else
    self:MoveTo(self:NextPending(self.index))
  end
  self:RequestEvaluate(0.1, "unskip")
  Events:Fire("SENDA_SKIPPED", nil)
  Events:Fire("SENDA_STEP_UPDATED", self.steps[self.index])
end

function Engine:UndoSkip(info)
  info = info or self.lastSkip
  if not info then return false end
  if self.lastSkip == info then self.lastSkip = nil end
  Restore(self, info.list)
  return true
end

function Engine:UnskipAll()
  local set = Set()
  if not set or not next(set) then return 0 end
  local list = {}
  for id in pairs(set) do list[#list + 1] = id end
  table.sort(list)
  self.lastSkip = nil
  Restore(self, list)
  return #list
end

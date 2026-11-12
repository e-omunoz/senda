-- Misiones con tiempo, fallidas y abandonadas (lado del motor).
--   Engine:StepTimers(step)   -> { { quest, left }, ... } cuentas atrás de las misiones del paso
--   Engine:Problem([entry])   -> { kind = "failed"|"abandoned", quest, accept = entrada } o nil
--   Engine:IsAbandoned(q)     -> true si abandonaste una misión de la guía sin entregarla
--   Engine:RetakeQuest(q)     -> vuelve al paso en que se cogía
--   Engine:SkipQuest(q)       -> salta los pasos que quedan de esa misión
--   Quests.Clock(secs)        -> "M:SS"
-- Evento interno: SENDA_QUEST_TIMER (cada segundo mientras corre una cuenta atrás).
-- Adaptado de Polestar, Quests/Timed.lua, Core/Engine.lua (Own.failedQuest, lostGoal) y Core/Compat.lua.
local _, Senda = ...
local Compat, Events = Senda.Compat, Senda.Events
local Engine = Senda.Engine
local Cond = Senda.Conditions
local L = Senda.L

local Quests = {}
Senda.Quests = Quests

local ALERTS = { 300, 60 } -- segundos que avisan en el chat al pasarlos
local READ_EVERY = 5       -- segundos entre lecturas del registro mientras corre una cuenta atrás

local deadline = {}  -- misión -> GetTime() en que termina (solo se adelanta, nunca se estira)
local prev = {}      -- misión -> segundos restantes en el tick anterior
local notified = {}  -- misión -> true: ya se avisó de que falló
local known = {}     -- misiones que tuvieron cuenta atrás: se vigila si fallan
local ticker, ticks = nil, 0

function Quests.Clock(secs)
  secs = math.max(0, math.floor((secs or 0) + 0.5))
  if secs >= 3600 then
    return string.format("%d:%02d:%02d", math.floor(secs / 3600), math.floor(secs / 60) % 60, secs % 60)
  end
  return string.format("%d:%02d", math.floor(secs / 60), secs % 60)
end

local function Name(q)
  return Compat.QuestTitle(q) or string.format(L.QUEST_FALLBACK, tostring(q))
end

local function Alerts()
  return Senda.Options:Get("questTimerAlerts") ~= false
end

function Quests.Left(q)
  local d = deadline[q]
  if not d then return nil end
  return math.max(0, d - GetTime())
end

------------------------------------------------------------------------------
-- Cuentas atrás
------------------------------------------------------------------------------

local function Expire(q)
  deadline[q], prev[q] = nil, nil
end

-- Avisa (una vez) de las misiones con tiempo que han fallado; olvida las que ya no están en el registro.
local function CheckFailed()
  for q in pairs(known) do
    if Compat.IsQuestFailed(q) then
      if not notified[q] then
        notified[q] = true
        if Alerts() then Senda:Print(L.QUEST_TIMER_FAILED, Name(q)) end
      end
    elseif not Compat.IsOnQuest(q) then
      known[q], notified[q] = nil, nil
    end
  end
end

local function Scan()
  local timed = Compat.TimedQuests()
  local now = GetTime()
  for q, left in pairs(timed) do
    local d = now + left
    if not deadline[q] or d < deadline[q] then deadline[q] = d end
    known[q] = true
  end
  for q in pairs(deadline) do
    if not timed[q] then Expire(q) end
  end
  CheckFailed()
  if next(deadline) then
    if not ticker then
      ticker = Compat.NewTicker(1, function() Quests.Tick() end)
    end
  elseif ticker then
    ticker:Cancel(); ticker = nil
  end
end
Quests.Scan = Scan

function Quests.Tick()
  ticks = ticks + 1
  if ticks % READ_EVERY == 0 then Scan() end
  local now = GetTime()
  local rescan
  for q, d in pairs(deadline) do
    local left = d - now
    if left <= 0 then
      rescan = true
    else
      local before = prev[q]
      if before and Alerts() then
        for _, mark in ipairs(ALERTS) do
          if before > mark and left <= mark then
            Senda:Print(L.QUEST_TIMER_WARN, Name(q), Quests.Clock(left))
          end
        end
      end
      prev[q] = left
    end
  end
  if rescan then Scan() end
  if not next(deadline) and ticker then ticker:Cancel(); ticker = nil end
  Events:Fire("SENDA_QUEST_TIMER")
end

function Engine:StepTimers(step)
  local out = {}
  if not step then return out end
  for _, q in ipairs(Cond:Quests(step) or {}) do
    local left = Quests.Left(q)
    if left then out[#out + 1] = { quest = q, left = left } end
  end
  table.sort(out, function(a, b) return a.left < b.left end)
  return out
end

------------------------------------------------------------------------------
-- Fallidas y abandonadas
------------------------------------------------------------------------------

function Engine:IsAbandoned(q)
  local p = Senda:GuideProgress(self.guideId)
  return (p and p.abandoned and p.abandoned[q]) and true or false
end

local function SetAbandoned(q, v)
  local p = Senda:GuideProgress(Engine.guideId)
  if not p then return end
  if v then
    p.abandoned = p.abandoned or {}
    p.abandoned[q] = true
  elseif p.abandoned then
    p.abandoned[q] = nil
    if not next(p.abandoned) then p.abandoned = nil end
  end
end

-- Problema de la misión del paso actual: fallida (sigue en el registro) o abandonada.
function Engine:Problem(entry)
  entry = entry or self.steps[self.index]
  local s = entry and entry.step
  if not s or not self.guideId then return nil end
  local d = s["do"]
  if d ~= "complete" and d ~= "turnin" then return nil end
  for _, q in ipairs(Cond:Quests(s) or {}) do
    local kind
    if Compat.IsQuestFailed(q) then
      kind = "failed"
    elseif self:IsAbandoned(q) and not self:QuestTaken(q) then
      kind = "abandoned"
    end
    if kind then
      local i = self.acceptIndex and self.acceptIndex[q]
      return { kind = kind, quest = q, accept = i and self.steps[i] or nil }
    end
  end
  return nil
end

-- Clave estable del problema actual (la flecha solo se recalcula si cambia).
function Engine:ProblemKey()
  local pr = self:Problem()
  return pr and (pr.kind .. ":" .. pr.quest) or ""
end

function Engine:RetakeQuest(q)
  local i = self.acceptIndex and self.acceptIndex[q]
  if i then self:JumpTo(i) end
end

function Engine:SkipQuest(q)
  for _, e in ipairs(self.steps) do
    local d = e.step["do"]
    if (d == "complete" or d == "turnin") and not self:IsMarked(e) then
      for _, x in ipairs(Cond:Quests(e.step) or {}) do
        if x == q then self:Mark(e, "s"); break end
      end
    end
  end
  SetAbandoned(q, false)
  self.held = nil
  self:MoveTo(self:NextPending(self.index))
  self:RequestEvaluate(0.1, "skipquest")
end

-- QUEST_REMOVED sin entrega: si la guía ya la había cogido, queda "abandonada".
local function OnRemoved(_, questID)
  questID = Compat.Num(questID)
  if not questID then return end
  Compat.After(0.1, function()
    local idx = Engine.acceptIndex and Engine.acceptIndex[questID]
    local e = idx and Engine.steps[idx]
    if not e or not Engine:IsMarked(e) or Engine:IsMarked(e) == "s" then return end
    if Engine.turnedIn[questID] or Compat.IsQuestDone(questID) or Compat.IsOnQuest(questID) then return end
    if not Engine:IsAbandoned(questID) then
      SetAbandoned(questID, true)
      Events:Fire("SENDA_STEP_UPDATED", Engine.steps[Engine.index])
    end
  end)
end

local function OnAccepted(_, questID)
  questID = Compat.Num(questID)
  if questID and Engine:IsAbandoned(questID) then
    SetAbandoned(questID, false)
    notified[questID] = nil
  end
  Compat.After(0.3, Scan)
end

Events:On("SENDA_READY", function()
  Events:On("QUEST_REMOVED", OnRemoved)
  Events:On("QUEST_ACCEPTED", OnAccepted)
  local scanPending = false
  Events:On("QUEST_LOG_UPDATE", function()
    if scanPending then return end
    scanPending = true
    Compat.After(0.5, function() scanPending = false; Scan() end)
  end)
  Compat.After(3, Scan)
end)

Senda.Options:Register({ key = "questTimerAlerts", label = L.OPT_TIMER_ALERTS, type = "toggle", default = true,
  section = L.OPT_SECTION_QUESTS, order = 20 })

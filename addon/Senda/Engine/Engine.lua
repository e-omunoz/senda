-- Motor de la guía: guía activa, paso actual, progreso guardado y detección automática.
--   Senda.Engine:CurrentStep() -> step, entry
--   Senda.Engine:Advance()      -- "Hecho": marca el paso (y su cadena) y avanza
--   Senda.Engine:Skip()         -- "Saltar"
--   Senda.Engine:Back()         -- vuelve al paso aplicable anterior
--   Senda.Engine:Complete(id)   -- marca un paso por id (si es el actual, avanza)
--   Senda.Engine:SetGuide(id), :JumpTo(index), :Reset()
-- El progreso se guarda por id de paso (estable entre versiones de la guía).
-- Eventos internos: SENDA_GUIDE_CHANGED, SENDA_STEP_CHANGED, SENDA_STEP_COMPLETED, SENDA_STEP_UPDATED.
local _, Senda = ...
local Compat, Events = Senda.Compat, Senda.Events

local Engine = {}
Senda.Engine = Engine

local Cond = Senda.Conditions -- Conditions.lua se carga antes que este archivo

Engine.guideId = nil
Engine.steps = {}       -- lista plana de entradas { step, section, secIndex, index }
Engine.index = 1
Engine.state = {}       -- estado transitorio del paso actual (hearthCast, bound, fpFound...)
Engine.turnedIn = {}    -- misiones entregadas en esta sesión (el flag del servidor puede tardar)
Engine.held = nil       -- { id, wasDone }: paso al que se volvió a mano (no se auto-completa si ya se cumplía)

local MAX_LOOP = 400
local HEARTHSTONE_SPELLS = { [8690] = true, [556] = true } -- Piedra de hogar, Llamada astral

local pending, dirty = false, false
local ticker

------------------------------------------------------------------------------
-- Utilidades internas
------------------------------------------------------------------------------

local function Progress()
  return Senda:GuideProgress(Engine.guideId)
end

local function DoneMark(entry)
  local p = Progress()
  return p and entry and p.done[entry.step.id]
end

-- Una misión cuenta como "cogida" si está en el registro o ya se entregó.
local function QuestTaken(q)
  return q and (Compat.IsOnQuest(q) or Compat.IsQuestDone(q) or (Engine.turnedIn and Engine.turnedIn[q])) and true or false
end

-- Nivel que falta para poder hacer este paso, o nil si se puede hacer ya.
-- * accept con `reqlevel`: la misión pide más nivel (exclamación plateada en el juego).
-- * complete / turnin de una misión aplazada por nivel que aún no tienes: se aplazan con ella.
function Engine:WaitLevel(entry)
  local s = entry and entry.step
  if not s then return nil end
  local d = s["do"]
  if d == "train" then
    -- El instructor no enseña esos hechizos hasta el nivel: si aún no lo tienes, se aplaza.
    local req = s.reqlevel
    if not req or (Compat.PlayerLevel() or 1) >= req then return nil end
    if Cond:Check(s, {}) == true then return nil end -- ya los conoces
    return req
  end
  if not s.quest then return nil end
  local req
  if d == "accept" then
    req = s.reqlevel
  elseif d == "complete" or d == "turnin" then
    req = self.questWait and self.questWait[s.quest]
  end
  if not req or (Compat.PlayerLevel() or 1) >= req then return nil end
  if QuestTaken(s.quest) then return nil end
  return req
end

-- Completar o entregar una misión que no tienes (la saltaste o no la cogiste) no tiene sentido:
-- si la ruta tiene antes su paso de coger y la misión no está en el registro ni entregada, se pasa.
-- Solo cuando el registro de misiones ya cargó (al iniciar sesión tarda unos segundos).
function Engine:NotTaken(entry)
  local s = entry and entry.step
  if not s or not s.quest or not self.logReady then return false end
  local d = s["do"]
  if d ~= "complete" and d ~= "turnin" then return false end
  local acc = self.acceptIndex and self.acceptIndex[s.quest]
  if not acc or not entry.index or acc >= entry.index then return false end
  return not QuestTaken(s.quest)
end

-- Coger una misión que pide una profesión (`reqskill = {línea, rango}`, p. ej. las lecciones
-- «Camping 101» de oficio) sin tenerla al rango pedido: el PNJ no la ofrece, así que se pasa.
function Engine:NoSkill(entry)
  local s = entry and entry.step
  local rs = s and s.reqskill
  if not rs or s["do"] ~= "accept" or type(rs) ~= "table" then return false end
  if QuestTaken(s.quest) then return false end
  local rank = Compat.ProfessionRank(rs[1])
  return not rank or rank < (rs[2] or 1)
end

local function Applicable(entry)
  return entry and Cond:LevelFilter(entry.step["if"]) and not Engine:WaitLevel(entry)
    and not Engine:NotTaken(entry) and not Engine:NoSkill(entry)
end

-- Índice misión -> nivel requerido (de los pasos accept con reqlevel).
local function BuildQuestWait(steps)
  local w, acc, idx = {}, {}, {}
  for i, e in ipairs(steps or {}) do
    local s = e.step
    e.index = i
    idx[e.step.id] = i
    if s["do"] == "accept" and s.quest then
      if s.reqlevel then w[s.quest] = s.reqlevel end
      if not acc[s.quest] then acc[s.quest] = i end
    end
  end
  Engine.acceptIndex = acc
  Engine.idIndex = idx
  return w
end

-- Recuerda un paso de coger misión aplazado por nivel (lo pasó el motor o lo saltaste sin tener nivel).
function Engine:RememberGated(entry)
  local p = Progress()
  local s = entry and entry.step
  if not p or not s or (s["do"] ~= "accept" and s["do"] ~= "train") or not s.reqlevel then return end
  p.gated = p.gated or {}
  p.gated[s.id] = s.reqlevel
end

-- Misiones aplazadas por nivel que siguen sin coger.
-- Devuelve { { entry, index, level, ready }, ... } en el orden de la ruta.
function Engine:LevelGated()
  local out = {}
  local p = Progress()
  if not p or not p.gated or not self.idIndex then return out end
  local lvl = Compat.PlayerLevel() or 1
  for id, req in pairs(p.gated) do
    local i = self.idIndex[id]
    local e = i and self.steps[i]
    local mark = e and DoneMark(e)
    local finished
    if e and e.step["do"] == "train" then
      finished = Cond:Check(e.step, {}) == true
    else
      finished = e and QuestTaken(e.step.quest)
    end
    if not e or mark == "a" or mark == "d" or finished then
      p.gated[id] = nil -- ya cogida, hecha o fuera de la guía: se olvida
    else
      out[#out + 1] = { entry = e, index = i, level = req, ready = lvl >= req }
    end
  end
  table.sort(out, function(a, b) return a.index < b.index end)
  return out
end

function Engine:GuideId() return self.guideId end
function Engine:Guide() return Senda.Guides:Get(self.guideId) end
function Engine:Steps() return self.steps end
function Engine:Index() return self.index end
function Engine:Entry(i) return self.steps[i or self.index] end

function Engine:CurrentStep()
  local e = self.steps[self.index]
  if e then return e.step, e end
  return nil
end

function Engine:CurrentSection()
  local e = self.steps[self.index]
  return e and e.section
end

function Engine:IsDone(entryOrIndex)
  local e = type(entryOrIndex) == "number" and self.steps[entryOrIndex] or entryOrIndex
  return DoneMark(e)
end

function Engine:IsFinished()
  return self.guideId ~= nil and self.index > #self.steps
end

-- Pasos realizados / total aplicables.
function Engine:Progress()
  local done, total = 0, 0
  local p = Progress()
  for _, e in ipairs(self.steps) do
    total = total + 1
    if p and p.done[e.step.id] then done = done + 1 end
  end
  return done, total
end

-- Próximos `n` pasos aplicables y pendientes tras el actual.
function Engine:NextSteps(n)
  local out = {}
  local i = self.index + 1
  while #out < (n or 2) and i <= #self.steps do
    local e = self.steps[i]
    if Applicable(e) and not DoneMark(e) then out[#out + 1] = e end
    i = i + 1
  end
  return out
end

------------------------------------------------------------------------------
-- Cambio de paso
------------------------------------------------------------------------------

local function StopTicker()
  if ticker then ticker:Cancel(); ticker = nil end
end

local function StartTicker()
  if ticker then return end
  ticker = Compat.NewTicker(0.5, function()
    if Compat.InCombat() then return end
    Engine:Evaluate("pos")
  end)
end

-- Prepara el estado transitorio del paso actual.
function Engine:EnterStep()
  local step = self:CurrentStep()
  self.state = { turnedIn = self.turnedIn }
  if step then
    if step.zone then self.state.startedInZone = Cond.InZone(step.zone) end
    if Compat.OnTaxi() then self.state.sawTaxi = true end
  end
  if step and Cond:NeedsPosition(step) then StartTicker() else StopTicker() end
end

function Engine:Save()
  local p = Progress()
  if not p then return end
  local e = self.steps[self.index]
  p.current = e and e.step.id or nil
  p.index = self.index
end

-- Mueve el puntero a `i` (sin marcar nada).
function Engine:MoveTo(i, silent)
  if i < 1 then i = 1 end
  self.index = i
  if self.held and (not self.steps[i] or self.steps[i].step.id ~= self.held.id) then self.held = nil end
  self:EnterStep()
  self:Save()
  if not silent then
    Events:Fire("SENDA_STEP_CHANGED", self.steps[i])
  end
end

-- Marca un paso. kind: "a" (auto), "d" (hecho a mano), "s" (saltado). Con cadena marca también sus pasos.
function Engine:Mark(entry, kind, withChain)
  local p = Progress()
  if not p or not entry then return end
  p.done[entry.step.id] = kind
  Events:Fire("SENDA_STEP_COMPLETED", entry.step, kind)
  local chain = withChain and entry.step.chain
  if chain then
    for _, e in ipairs(self.steps) do
      if e.step.chain == chain and not p.done[e.step.id] then
        p.done[e.step.id] = kind
        Events:Fire("SENDA_STEP_COMPLETED", e.step, kind)
      end
    end
  end
end

-- Siguiente índice pendiente y aplicable a partir de `from`.
function Engine:NextPending(from)
  local i = from
  while i <= #self.steps do
    local e = self.steps[i]
    if Applicable(e) and not DoneMark(e) then return i end
    if e and not DoneMark(e) and self:WaitLevel(e) then self:RememberGated(e) end
    i = i + 1
  end
  return #self.steps + 1
end

------------------------------------------------------------------------------
-- Evaluación (detección automática)
------------------------------------------------------------------------------

-- Un "goto" se da por hecho si el paso siguiente (adelantable) ya se cumple: p. ej. ir a un PNJ
-- para entregar una misión que ya está entregada.
function Engine:GotoObsolete(i)
  local nextI = self:NextPending(i + 1)
  local e = self.steps[nextI]
  if not e or e.secIndex ~= self.steps[i].secIndex then return false end
  if e.step["do"] == "goto" or not Cond:CanFastForward(e.step) then return false end
  return Cond:Check(e.step, { turnedIn = self.turnedIn }) == true
end

function Engine:Evaluate(reason)
  if not self.guideId then return end
  if Compat.InCombat() then dirty = true; return end
  dirty = false
  local start = self.index
  local loops = 0
  while loops < MAX_LOOP do
    loops = loops + 1
    local e = self.steps[self.index]
    if not e then break end
    local step = e.step
    if DoneMark(e) or not Applicable(e) then
      if not DoneMark(e) and self:WaitLevel(e) then self:RememberGated(e) end
      self.index = self.index + 1
      self:EnterStep()
    else
      local r = Cond:Check(step, self.state)
      if r ~= true and step["do"] == "goto" and self:GotoObsolete(self.index) then r = true end
      if r == true and self.held and self.held.id == step.id and self.held.wasDone then
        r = false -- el usuario volvió a este paso a propósito: se queda hasta "Hecho"
      end
      if r == true then
        Senda:Debug("Paso completado (%s): %s", tostring(reason), step.id)
        self:Mark(e, "a")
        self.index = self.index + 1
        self:EnterStep()
      elseif step.optional and Senda.db.opts.skipOptional then
        self:Mark(e, "s")
        self.index = self.index + 1
        self:EnterStep()
      else
        break
      end
    end
  end
  if self.index ~= start then
    self:Save()
    Events:Fire("SENDA_STEP_CHANGED", self.steps[self.index])
    if self:IsFinished() then Senda:Print(Senda.L.GUIDE_FINISHED) end
  else
    Events:Fire("SENDA_STEP_UPDATED", self.steps[self.index])
  end
end

-- Evaluación diferida y agrupada (muchos eventos seguidos -> una sola evaluación).
function Engine:RequestEvaluate(delay, reason)
  if pending then return end
  pending = true
  Compat.After(delay or 0.25, function()
    pending = false
    Engine:Evaluate(reason)
  end)
end

------------------------------------------------------------------------------
-- Acciones manuales
------------------------------------------------------------------------------

function Engine:Advance()
  local e = self.steps[self.index]
  if not e then return end
  self:Mark(e, "d", true)
  self.held = nil
  self:MoveTo(self:NextPending(self.index + 1))
  self:RequestEvaluate(0.1, "advance")
end

function Engine:Skip()
  local e = self.steps[self.index]
  if not e then return end
  local s = e.step
  if s.reqlevel and (Compat.PlayerLevel() or 1) < s.reqlevel then
    if (s["do"] == "accept" and not QuestTaken(s.quest)) or s["do"] == "train" then
      self:RememberGated(e)
    end
  end
  self:Mark(e, "s", true)
  self.held = nil
  self:MoveTo(self:NextPending(self.index + 1))
  self:RequestEvaluate(0.1, "skip")
end

-- Vuelve al paso aplicable anterior y lo desmarca.
function Engine:Back()
  local i = math.min(self.index, #self.steps + 1) - 1
  while i >= 1 and not Applicable(self.steps[i]) do i = i - 1 end
  if i < 1 then return end
  self:JumpTo(i)
end

-- Salta a un índice concreto. El paso queda "retenido": si ya se cumplía, espera a "Hecho".
function Engine:JumpTo(i)
  local e = self.steps[i]
  if not e then return end
  local p = Progress()
  if p then p.done[e.step.id] = nil end
  local was = Cond:Check(e.step, { turnedIn = self.turnedIn }) == true
  self:MoveTo(i, true)
  self.held = { id = e.step.id, wasDone = was }
  Events:Fire("SENDA_STEP_CHANGED", e)
end

-- Marca un paso por id. Si es el actual, avanza.
function Engine:Complete(stepId)
  for i, e in ipairs(self.steps) do
    if e.step.id == stepId then
      if i == self.index then
        self:Advance()
      else
        self:Mark(e, "d")
        Events:Fire("SENDA_STEP_UPDATED", self.steps[self.index])
      end
      return true
    end
  end
  return false
end

-- Desmarca un paso (lista de la guía).
function Engine:Unmark(stepId)
  local p = Progress()
  if p then p.done[stepId] = nil end
  Events:Fire("SENDA_STEP_UPDATED", self.steps[self.index])
end

------------------------------------------------------------------------------
-- Guía activa
------------------------------------------------------------------------------

-- Índice donde reanudar si no hay progreso: tras la última misión ya entregada de la ruta.
function Engine:ResumeIndex()
  local best = 0
  for i, e in ipairs(self.steps) do
    if e.step["do"] == "turnin" and Cond:Check(e.step, { turnedIn = self.turnedIn }) == true then
      best = i
    end
  end
  return math.max(1, best)
end

-- Reconstruye la lista plana (al cambiar de guía o de profesión) conservando el paso actual.
function Engine:Rebuild()
  local p = Progress()
  self.steps = Senda.Guides:Resolve(self.guideId)
  self.questWait = BuildQuestWait(self.steps)
  local idx
  if p and p.current then
    for i, e in ipairs(self.steps) do
      if e.step.id == p.current then idx = i; break end
    end
  end
  if not idx and p and next(p.done) then
    -- El paso guardado ya no existe (guía actualizada): tras el último paso marcado.
    local last = 0
    for i, e in ipairs(self.steps) do
      if p.done[e.step.id] then last = i end
    end
    idx = self:NextPending(last + 1)
  end
  if not idx then idx = self:ResumeIndex() end
  self:MoveTo(idx, true)
end

function Engine:SetGuide(id, silent)
  if not Senda.Guides:Get(id) then
    Senda:Debug("Guía desconocida: %s", tostring(id))
    return false
  end
  self.guideId = id
  Senda.db.guide = id
  self.held = nil
  self:Rebuild()
  Events:Fire("SENDA_GUIDE_CHANGED", id)
  Events:Fire("SENDA_STEP_CHANGED", self.steps[self.index])
  if not silent then
    local g = Senda.Guides:Get(id)
    Senda:Print(Senda.L.GUIDE_SELECTED, g.title or id)
  end
  self:RequestEvaluate(0.5, "guide")
  return true
end

function Engine:Reset()
  if not self.guideId then return end
  Senda.db.progress[self.guideId] = { done = {} }
  self.held = nil
  self:Rebuild()
  Events:Fire("SENDA_STEP_CHANGED", self.steps[self.index])
  self:RequestEvaluate(0.3, "reset")
end

-- Elige la guía guardada o la mejor para el jugador.
function Engine:AutoSelect()
  local id = Senda.db.guide
  if id and Senda.Guides:Get(id) then
    self:SetGuide(id, true)
    return
  end
  local list = Senda.Guides:ForPlayer()
  if list[1] then
    self:SetGuide(list[1].id)
  else
    Senda:Debug("No hay guías para este personaje")
    Events:Fire("SENDA_GUIDE_CHANGED", nil)
  end
end

------------------------------------------------------------------------------
-- Eventos
------------------------------------------------------------------------------

local function CurrentDo()
  local s = Engine:CurrentStep()
  return s and s["do"], s
end

local function Req(reason, delay)
  return function() Engine:RequestEvaluate(delay, reason) end
end

local function OnTurnedIn(_, questID)
  questID = Compat.Num(questID)
  if questID then Engine.turnedIn[questID] = true end
  Engine:RequestEvaluate(0.2, "turnin")
end

local function OnAccepted()
  Engine:RequestEvaluate(0.2, "accept")
end

local skillTimer = false
local function OnSkills()
  -- Las profesiones pueden cambiar los filtros `if.prof`: se reconstruye (agrupado).
  if skillTimer then return end
  skillTimer = true
  Compat.After(1, function()
    skillTimer = false
    if Engine.guideId and not Compat.InCombat() then
      local before = Engine:CurrentStep()
      local n = #Engine.steps
      Engine.steps = Senda.Guides:Resolve(Engine.guideId)
      Engine.questWait = BuildQuestWait(Engine.steps)
      if #Engine.steps ~= n then
        -- reubica el puntero en el mismo paso
        for i, e in ipairs(Engine.steps) do
          if e.step == before then Engine.index = i; break end
        end
        Events:Fire("SENDA_STEP_CHANGED", Engine.steps[Engine.index])
      end
    end
    Engine:RequestEvaluate(0.1, "skill")
  end)
end

local function OnBound()
  local d = CurrentDo()
  if d == "sethearth" then Engine.state.bound = true end
  Engine:RequestEvaluate(0.2, "bind")
end

local function OnTaxiOpened()
  local fps = Senda.db.char.fps
  for _, n in ipairs(Compat.TaxiNodes()) do
    if n.known and n.id then fps[n.id] = n.name end
  end
  local d, step = CurrentDo()
  if d == "getfp" then
    if not step.node then
      Engine.state.fpFound = true
    elseif Cond.FpKnown(step) then
      Engine.state.fpFound = true
    elseif step.at then
      -- Nodo con nombre no reconocido: si estamos junto al maestro de vuelo, se da por bueno.
      local dist = Cond:DistanceTo(step.at)
      if dist and dist < 40 then Engine.state.fpFound = true end
    end
  end
  Engine:RequestEvaluate(0.2, "taxi")
end

local function OnZone()
  Engine.state.zoneChanged = true
  if Compat.OnTaxi() then Engine.state.sawTaxi = true end
  Engine:RequestEvaluate(0.5, "zone")
end

local function OnControl()
  if Compat.OnTaxi() then Engine.state.sawTaxi = true end
  Engine:RequestEvaluate(1, "control")
end

-- UNIT_SPELLCAST_SUCCEEDED solo del jugador, en un marco aparte (RegisterUnitEvent) y barato.
local castFrame = CreateFrame("Frame")
castFrame:SetScript("OnEvent", function(_, _, unit, _, spellID)
  local d, step = CurrentDo()
  if d ~= "hearth" and d ~= "use" then return end
  spellID = Compat.Num(spellID)
  if not spellID then return end
  if d == "hearth" and HEARTHSTONE_SPELLS[spellID] then
    Engine.state.hearthCast = true
    Engine:RequestEvaluate(2, "hearth")
  elseif d == "use" and step.item and Compat.ItemSpell(step.item) == spellID then
    Engine.state.used = true
    Engine:RequestEvaluate(0.2, "use")
  end
end)

Events:On("SENDA_READY", function()
  if castFrame.RegisterUnitEvent then
    pcall(castFrame.RegisterUnitEvent, castFrame, "UNIT_SPELLCAST_SUCCEEDED", "player")
  end
  Events:On("QUEST_ACCEPTED", OnAccepted)
  Events:On("QUEST_TURNED_IN", OnTurnedIn)
  Events:On("QUEST_REMOVED", Req("removed", 0.3))
  Events:On("QUEST_LOG_UPDATE", function()
    Engine.logReady = true
    Engine:RequestEvaluate(0.4, "log")
  end)
  Events:On("UNIT_QUEST_LOG_CHANGED", Req("log", 0.4))
  Events:On("PLAYER_LEVEL_UP", function(_, level)
    -- Aviso de las misiones que ya se pueden coger con el nuevo nivel.
    level = Compat.Num(level)
    if level then
      for _, g in ipairs(Engine:LevelGated()) do
        if g.level == level then
          local s = g.entry.step
          local name = (Senda.HUD and Senda.HUD.StepTitle and Senda.HUD:StepTitle(s)) or ""
          if name == "" then name = "#" .. tostring(s.quest) end
          local key = s["do"] == "train" and "LEVEL_GATE_READY_TRAIN" or "LEVEL_GATE_READY"
          Senda:Print(string.format(Senda.L[key] or Senda.L.LEVEL_GATE_READY, name))
        end
      end
    end
    Engine:RequestEvaluate(0.5, "level")
    Events:Fire("SENDA_STEP_UPDATED", Engine.steps and Engine.steps[Engine.index])
  end)
  Events:On("SPELLS_CHANGED", Req("spells", 0.5))
  Events:On("LEARNED_SPELL_IN_TAB", Req("spells", 0.3))
  Events:On("LEARNED_SPELL_IN_SKILL_LINE", Req("spells", 0.3))
  Events:On("SKILL_LINES_CHANGED", OnSkills)
  Events:On("TRADE_SKILL_LIST_UPDATE", OnSkills)
  Events:On("BAG_UPDATE_DELAYED", Req("bags", 0.3))
  Events:On("HEARTHSTONE_BOUND", OnBound)
  Events:On("TAXIMAP_OPENED", OnTaxiOpened)
  Events:On("ZONE_CHANGED_NEW_AREA", OnZone)
  Events:On("ZONE_CHANGED", Req("subzone", 0.5))
  Events:On("PLAYER_ENTERING_WORLD", OnZone)
  Events:On("PLAYER_CONTROL_LOST", OnControl)
  Events:On("PLAYER_CONTROL_GAINED", OnControl)
  Events:On("PLAYER_REGEN_ENABLED", function()
    if dirty then Engine:RequestEvaluate(0.3, "regen") end
  end)
  Events:On("SENDA_GUIDES_UPDATED", function()
    if not Engine.guideId then Engine:AutoSelect() end
  end)

  Engine:AutoSelect()
  -- Al iniciar sesión, la caché de misiones puede tardar: se reevalúa un par de veces.
  Engine:RequestEvaluate(1, "login")
  Compat.After(5, function()
    Engine.logReady = true
    Engine:RequestEvaluate(0, "login2")
  end)
end)

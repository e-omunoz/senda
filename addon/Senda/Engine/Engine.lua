-- Motor de la guía: guía activa, paso actual, progreso guardado y detección automática.
--   Senda.Engine:CurrentStep() -> step, entry
--   Senda.Engine:Advance()      -- "Hecho": marca el paso (y su cadena) y avanza
--   Senda.Engine:Skip()         -- "Saltar"
--   Senda.Engine:Back()         -- vuelve al paso aplicable anterior
--   Senda.Engine:Complete(id)   -- marca un paso por id (si es el actual, avanza)
--   Senda.Engine:SetGuide(id), :JumpTo(index), :Reset()
--   Senda.Engine:Place(reason)  -- recalcula el paso actual con lo que sabe el juego (solo adelanta)
-- El progreso se guarda por id de paso (estable entre versiones de la guía).
-- Eventos internos: SENDA_GUIDE_CHANGED, SENDA_STEP_CHANGED, SENDA_STEP_COMPLETED, SENDA_STEP_UPDATED,
-- SENDA_OBJECTIVES_UPDATED (cambian los contadores del paso actual; también en combate).
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

-- Pasos de misión: los que "Saltar esta misión" deja fuera junto con la misión (Engine:SkipQuestTree).
local QUESTY = { accept = true, complete = true, turnin = true, dungeon = true }

local function SkipSet()
  local t = Senda.db and Senda.db.skippedQuests
  if t and next(t) then return t end
  return nil
end

-- ¿Salta este paso una misión saltada? Vale para todas las guías: el conjunto es del personaje, no de la
-- guía. Un `goto` justo antes de un paso saltado (en la misma sección) se salta con él.
function Engine:StepSkipped(entry, depth)
  local set = SkipSet()
  if not set or not entry then return false end
  local s = entry.step
  local qs = Cond:Quests(s)
  if qs and QUESTY[s["do"]] then
    for _, q in ipairs(qs) do
      if not set[q] then return false end
    end
    return true
  end
  depth = depth or 0
  if s["do"] == "goto" and depth < 3 and entry.index then
    local nxt = Engine.steps[entry.index + 1]
    if nxt and nxt.secIndex == entry.secIndex then return Engine:StepSkipped(nxt, depth + 1) end
  end
  return false
end

local function DoneMark(entry)
  local p = Progress()
  if not p or not entry then return nil end
  return p.done[entry.step.id] or (Engine:StepSkipped(entry) and "s" or nil)
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
  -- Abandonada o fallida: no se salta en silencio; el HUD avisa y la flecha vuelve a quien la daba.
  if self.IsAbandoned and self:IsAbandoned(s.quest) then return false end
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
    and not (Engine.StepParked and Engine:StepParked(entry)) -- «Para después» (Engine/Aside.lua)
end

-- Las siguientes funciones las usan Quests.lua y Automation.lua.
function Engine:IsApplicable(entry) return Applicable(entry) and true or false end
function Engine:QuestTaken(q) return QuestTaken(q) end
function Engine:IsMarked(entry) return DoneMark(entry) end

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
    if not e or mark == "a" or mark == "d" or finished or self:StepSkipped(e) then
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
    if p and DoneMark(e) then done = done + 1 end
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
  -- Paso al que se volvió a mano: la colocación al iniciar sesión lo respeta (no adelanta).
  p.held = (e and self.held and self.held.id == e.step.id) and e.step.id or nil
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
  if Compat.InCombat() then
    dirty = true
    -- En combate no se avanza, pero los contadores (6/8) se ven al momento.
    self:CheckObjectives()
    return
  end
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
      -- En un desvío (Engine/Aside.lua) pasar cerca de un «ve a» de la ruta no lo da por hecho: al volver, la
      -- ruta sigue donde la dejaste.
      if r == true and step["do"] == "goto" and Senda.Aside and Senda.Aside:Active() then r = false end
      if r ~= true and step["do"] == "goto" and self:GotoObsolete(self.index) then r = true end
      if r == true and Senda.Party and Senda.Party.Holds and Senda.Party.Holds(e) then
        r = false -- en pareja: tu compañero aún necesita objetivos de este paso (Modules/Party.lua)
      end
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
  self.objSig = self:ObjectiveSignature() -- el HUD ya se redibuja con el evento anterior
  if Senda.Aside and Senda.Aside:Active() then Senda.Aside:Evaluate(reason) end
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
  while i >= 1 and (not Applicable(self.steps[i]) or self:StepSkipped(self.steps[i])) do i = i - 1 end
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
  self:Save()
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

------------------------------------------------------------------------------
-- Contadores de objetivos del paso actual
------------------------------------------------------------------------------

-- Firma de los objetivos de las misiones del paso actual ("" si no es un paso de misión).
-- Es barata: solo mira el paso actual, nunca la guía entera.
function Engine:ObjectiveSignature()
  local s = self:CurrentStep()
  if not s or not s.quest and not s.quests then return "" end
  local d = s["do"]
  if d ~= "complete" and d ~= "turnin" and d ~= "accept" then return "" end
  local parts = {}
  for _, q in ipairs(Cond:Quests(s) or {}) do
    parts[#parts + 1] = tostring(q)
    for _, o in ipairs(Compat.QuestObjectives(q)) do
      parts[#parts + 1] = string.format("%s/%s%s", tostring(o.have), tostring(o.need), o.finished and "+" or "")
    end
  end
  return table.concat(parts, ",")
end

-- Si cambiaron los contadores del paso actual, avisa al HUD (sin evaluar ni mover el puntero).
function Engine:CheckObjectives()
  local sig = self:ObjectiveSignature()
  if sig == self.objSig then return false end
  self.objSig = sig
  Events:Fire("SENDA_OBJECTIVES_UPDATED", self.steps[self.index])
  return true
end

------------------------------------------------------------------------------
-- Colocación desde el registro de misiones
------------------------------------------------------------------------------
-- Al iniciar sesión, al recargar y al cambiar de guía, el puntero se recalcula con lo que sabe el juego
-- (misiones entregadas, misiones en el registro y sus objetivos, nivel, hechizos conocidos), no solo con el
-- índice guardado: si se pierden las SavedVariables o juegas sin el addon, la guía no te deja atrás.
-- Idea tomada de Polestar (Core/Engine.lua, place/anchorStep/leadsToDone); el código es propio.
--
-- * Ancla: el último paso de misión con progreso en el juego (entregada, en el registro, objetivos
--   empezados). Los pasos de clase o raza, los opcionales y los que saltaste no cuentan: no demuestran
--   por dónde va la ruta.
-- * Antes del ancla, un paso sin misión (ir a, piedra de hogar, instructor, profesión, nota...) se da por
--   pasado si la siguiente misión de la ruta ya está hecha o en curso; un paso opcional, también.
-- * Un paso de misión pendiente (sin coger, objetivos a medias, sin entregar) siempre retiene: es trabajo
--   que falta. Los pasos marcados (hechos o saltados a mano) siempre pasan.
-- * Solo adelanta: nunca te devuelve a un paso anterior al guardado, ni mueve un paso al que volviste a
--   mano (Atrás o la lista de la guía).

local QUEST_DO = { accept = true, complete = true, turnin = true }
local PLACE_SLICE = 120 -- pasos por fotograma (cada paso: unas pocas llamadas a C_QuestLog)

local function ClassOrRace(f)
  return type(f) == "table" and (f.class ~= nil or f.race ~= nil)
end

local function IsQuestStep(s)
  return QUEST_DO[s["do"]] and (s.quest ~= nil or s.quests ~= nil)
end

local function TurnedInNow(q)
  return (Engine.turnedIn and Engine.turnedIn[q]) or Compat.IsQuestDone(q)
end

-- ¿Algún objetivo con avance (o la misión lista para entregar)?
local function ObjectivesStarted(q, obj)
  if Compat.IsQuestComplete(q) then return true end
  for i, o in ipairs(Compat.QuestObjectives(q)) do
    if (not obj or obj == i) and (o.finished or (o.have and o.have > 0)) then return true end
  end
  return false
end

-- Progreso en el juego que demuestra que la ruta llegó a este paso.
local function QuestEvidence(s)
  local d = s["do"]
  for _, q in ipairs(Cond:Quests(s) or {}) do
    if TurnedInNow(q) then return true end
    if Compat.IsOnQuest(q) and (d == "accept" or (d == "complete" and ObjectivesStarted(q, s.obj))) then
      return true
    end
  end
  return false
end

-- La misión del paso está hecha o en curso (para saber si los pasos sin misión anteriores ya se pasaron).
local function QuestUnderWay(s)
  local d = s["do"]
  for _, q in ipairs(Cond:Quests(s) or {}) do
    if TurnedInNow(q) or (d ~= "turnin" and Compat.IsOnQuest(q)) then return true end
  end
  return false
end

-- Núcleo de la colocación. Devuelve el índice donde situarse y el ancla (0 si no hay progreso).
-- `tick` (opcional) se llama una vez por paso mirado: la versión repartida en fotogramas cede ahí.
function Engine:PlaceCore(tick)
  local steps = self.steps
  local n = #steps
  local lead, anchor, nextQ = {}, 0, true
  -- 1) Hacia atrás: ancla y "la siguiente misión ya está hecha o en curso" para cada paso.
  for i = n, 1, -1 do
    if tick then tick() end
    local e = steps[i]
    local s = e.step
    lead[i] = nextQ
    if IsQuestStep(s) then
      local mark = DoneMark(e)
      if mark ~= "s" and Cond:LevelFilter(s["if"]) and not self:WaitLevel(e) then
        nextQ = QuestUnderWay(s) or mark == "a" or mark == "d"
        if anchor == 0 and not s.optional and not ClassOrRace(s["if"]) and not ClassOrRace(e.section and e.section["if"])
          and QuestEvidence(s) then
          anchor = i
        end
      end
    end
  end
  -- 2) Hacia delante: el primer paso que retiene.
  local state = { turnedIn = self.turnedIn }
  local i = 1
  while i <= n do
    if tick then tick() end
    local e = steps[i]
    local s = e.step
    local passes = DoneMark(e) or not Applicable(e) or Cond:Check(s, state) == true
    if not passes and i < anchor and lead[i] then
      passes = s.optional or not IsQuestStep(s)
    end
    if not passes then break end
    i = i + 1
  end
  return i, anchor
end

-- Índice donde reanudar según el juego (versión directa, sin repartir en fotogramas).
function Engine:ResumeIndex()
  local i = self:PlaceCore()
  return math.max(1, math.min(i, #self.steps + 1))
end

local placeCo, placeFrame, placeJob

-- Aplica el resultado: adelanta el puntero (nunca lo retrasa) y marca lo pasado como hecho por el juego.
function Engine:ApplyPlacement(job, target, anchor)
  if job.guideId ~= self.guideId or job.steps ~= self.steps then
    self:Place(job.reason) -- la guía cambió mientras se calculaba: otra vez
    return
  end
  local from = self.index
  Senda:Debug("Colocación (%s): ancla %d, paso %d (guardado %d)", tostring(job.reason), anchor, target, from)
  if self.held or target <= from then return end
  local p = Progress()
  if not p then return end
  local passed = 0
  for i = from, math.min(target, #self.steps + 1) - 1 do
    local e = self.steps[i]
    if not DoneMark(e) then
      if Applicable(e) then
        p.done[e.step.id] = "a"
        passed = passed + 1
      elseif self:WaitLevel(e) then
        self:RememberGated(e)
      end
    end
  end
  self:MoveTo(target)
  if passed > 0 then Senda:Print(Senda.L.PLACED_FROM_LOG, passed) end
  if self:IsFinished() then Senda:Print(Senda.L.GUIDE_FINISHED) end
  self:RequestEvaluate(0.1, "placed")
end

local function PlaceStep()
  if not placeCo then
    if placeFrame then placeFrame:Hide() end
    return
  end
  if Compat.InCombat() then return end -- los valores pueden ser secretos en combate: espera
  local ok, target, anchor = coroutine.resume(placeCo)
  if not ok then
    placeCo = nil
    placeFrame:Hide()
    Senda:Debug("Error en la colocación: %s", tostring(target))
    return
  end
  if coroutine.status(placeCo) == "dead" then
    placeCo = nil
    placeFrame:Hide()
    Engine:ApplyPlacement(placeJob, target, anchor)
  end
end

-- Recalcula el paso actual con lo que sabe el juego, repartido en fotogramas (PLACE_SLICE pasos por
-- fotograma). Si el registro de misiones aún no cargó, espera a que cargue.
function Engine:Place(reason)
  if not self.guideId or #self.steps == 0 then return end
  if not self.logReady then
    self.placeWanted = reason or "log"
    return
  end
  self.placeWanted = nil
  placeJob = { guideId = self.guideId, steps = self.steps, reason = reason }
  local k = 0
  placeCo = coroutine.create(function()
    return Engine:PlaceCore(function()
      k = k + 1
      if k % PLACE_SLICE == 0 then coroutine.yield() end
    end)
  end)
  if not placeFrame then
    placeFrame = CreateFrame("Frame")
    placeFrame:SetScript("OnUpdate", PlaceStep)
  end
  placeFrame:Show()
end

function Engine:Placing() return placeCo ~= nil end

-- El registro de misiones ya se puede leer: lanza la colocación que esperaba.
function Engine:SetLogReady()
  if self.logReady then return end
  self.logReady = true
  if self.placeWanted then self:Place(self.placeWanted) end
end

-- Reconstruye la lista plana (al cambiar de guía o de profesión) conservando el paso actual.
function Engine:Rebuild(placeReason)
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
  -- Sin progreso guardado se empieza por el principio; la colocación (abajo) adelanta según el juego.
  local heldId = p and p.held
  self:MoveTo(idx or 1, true)
  local cur = self.steps[self.index]
  if heldId and cur and cur.step.id == heldId then
    self.held = { id = heldId, wasDone = Cond:Check(cur.step, { turnedIn = self.turnedIn }) == true }
    self:Save()
  end
  self.objSig = nil
  self:Place(placeReason or "rebuild")
end

function Engine:SetGuide(id, silent)
  if not Senda.Guides:Get(id) then
    Senda:Debug("Guía desconocida: %s", tostring(id))
    return false
  end
  self.guideId = id
  Senda.db.guide = id
  self.held = nil
  self:Rebuild("guide")
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
  self:Rebuild("reset")
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
  if list[1] and not Senda.Guides:IsManualOnly(list[1]) then
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
    Engine:SetLogReady()
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
    if Engine.logReady then
      -- La caché de misiones ya debería estar completa: segunda colocación (solo adelanta).
      Engine:Place("login2")
    else
      Engine:SetLogReady()
    end
    Engine:RequestEvaluate(0, "login2")
  end)
end)

-- «Aparte»: lo que haces fuera de la ruta principal, coordinado en tres bloques (pestaña UI/AsideTab.lua).
--
-- Para después (por guía, en progress.parked):
--   Engine:ParkInfo(entry) -> { kind = "quest"|"section", key, quest, list, section, title, hint } o nil
--   Engine:Park(entry) -> info     Engine:Unpark(key)  -- de vuelta a la ruta, en su sitio
--   Engine:StepParked(entry) -> bool  (el motor pasa por encima, como si estuviera saltado, sin marcarlo)
--   Engine:Parked() -> { { key, kind, title, when, level, map, x, y, hint, hintLevel, hintMap, steps = {entradas} } }
--   Un paso aparcado no está hecho ni saltado: sigue pendiente en progress.parked con cuándo y dónde lo dejaste.
--   Una misión aparca con las que dependen de ella (Guides:Followups) que aún no tienes; un paso de una sección
--   de clase (`parkable = true`, p. ej. la súcubo del brujo) aparca la sección entera, con su pista
--   (`later_hint`, `later_level`, `later_map`).
--
-- Desvío activo (por personaje, en SendaDB.aside):
--   Aside:Start(items) -- items = { { kind = "reserve", quest = q } | { kind = "parked", key = k }, ... }
--   Aside:Active(), :CurrentStep() -> step, dEntry, :Steps(), :Index(), :Advance(), :Skip(), :Back(), :Cancel()
--   Aside:NextSteps(n), :Progress() -> hechos, total
--   Sub-ruta temporal: coger → completar → entregar (misiones de la reserva, con los datos de Guides/Reserve.lua)
--   y los pasos pendientes de lo aparcado (los mismos pasos de la guía: al hacerlos se marcan en la ruta). El HUD
--   y la flecha la siguen hasta acabar o cancelar y después vuelven a la ruta donde la dejaste. Lo que hagas en el
--   desvío cuenta para la ruta (las misiones entregadas ya se detectan solas).
--
-- Recordatorio: Aside:Reminder() -> { key, item, reason = "map"|"near"|"level" } o nil
--   Una línea discreta en el HUD («Pendiente aquí: X · Retomar») si estás en el mapa de algún paso aparcado, a
--   menos de `parkRemindDistance` metros del siguiente o si llegas al nivel de su pista.
-- Eventos internos: SENDA_PARKED (cambia lo aparcado), SENDA_ASIDE_CHANGED (empieza, avanza o acaba un desvío).
local _, Senda = ...
local Compat, Events = Senda.Compat, Senda.Events
local Engine = Senda.Engine
local Cond = Senda.Conditions
local L = Senda.L

local Aside = {}
Senda.Aside = Aside

local QUESTY = { accept = true, complete = true, turnin = true, dungeon = true }

------------------------------------------------------------------------------
-- Para después
------------------------------------------------------------------------------

local function Progress()
  return Engine.guideId and Senda:GuideProgress(Engine.guideId) or nil
end

local function ParkedTable(create)
  local p = Progress()
  if not p then return nil end
  if create and not p.parked then p.parked = {} end
  return p.parked
end

-- Conjuntos en caché (misiones y secciones aparcadas de la guía activa).
local cacheP, parkedQ, parkedSec, anyParked

local function Sets()
  local t = ParkedTable(false)
  if t ~= cacheP then cacheP = t end
  if parkedQ then return end
  parkedQ, parkedSec, anyParked = {}, {}, false
  for _, it in pairs(t or {}) do
    anyParked = true
    if it.kind == "section" then
      for _, sid in ipairs(it.sections or { it.section }) do parkedSec[sid] = true end
    end
    for _, q in ipairs(it.list or {}) do parkedQ[q] = true end
  end
end

local function Invalidate() parkedQ = nil end
Aside.InvalidateParked = Invalidate

-- ¿Aparcado este paso? Barato: sin nada aparcado sale enseguida.
function Engine:StepParked(entry, depth)
  if not entry then return false end
  if ParkedTable(false) ~= cacheP then Invalidate() end
  Sets()
  if not anyParked then return false end
  local s = entry.step
  local sec = entry.section
  if sec and sec.id and parkedSec[sec.id] then return true end
  local qs = Cond:Quests(s)
  if qs and QUESTY[s["do"]] then
    for _, q in ipairs(qs) do
      if not parkedQ[q] then return false end
    end
    return true
  end
  depth = depth or 0
  if s["do"] == "goto" and depth < 3 and entry.index then
    local nxt = self.steps[entry.index + 1]
    if nxt and nxt.secIndex == entry.secIndex then return self:StepParked(nxt, depth + 1) end
  end
  return false
end

-- Misión del paso que se puede aparcar (la primera de sus misiones).
local function StepQuest(s)
  local qs = s and QUESTY[s["do"]] and Cond:Quests(s)
  return qs and qs[1] or nil
end

function Engine:ParkInfo(entry)
  if not entry or not entry.step then return nil end
  local sec = entry.section
  if sec and sec.parkable and sec.id then
    -- La sección, las secciones de clase que siguen la cadena (tienen misiones que dependen de las suyas) y
    -- todas esas misiones con sus dependientes (que pueden estar en secciones normales).
    local secs, inSec, quests, seenQ = { sec.id }, { [sec.id] = true }, {}, {}
    local function AddQuest(q)
      if not seenQ[q] and not self:QuestTaken(q) then
        seenQ[q] = true
        quests[#quests + 1] = q
      end
    end
    local function QuestsOf(sid)
      for _, e in ipairs(self.steps) do
        if e.section and e.section.id == sid and QUESTY[e.step["do"]] then
          for _, q in ipairs(Cond:Quests(e.step) or {}) do AddQuest(q) end
        end
      end
    end
    QuestsOf(sec.id)
    local changed = true
    while changed do
      changed = false
      local deps = {}
      for _, q in ipairs(quests) do
        for _, d in ipairs(Senda.Guides:Followups(q) or {}) do deps[d] = true end
      end
      for _, e in ipairs(self.steps) do
        local s2 = e.section
        if s2 and s2.parkable and s2.id and not inSec[s2.id] and QUESTY[e.step["do"]] then
          for _, q in ipairs(Cond:Quests(e.step) or {}) do
            if deps[q] and not inSec[s2.id] then
              inSec[s2.id] = true
              secs[#secs + 1] = s2.id
              QuestsOf(s2.id)
              changed = true
            end
          end
        end
      end
      for q in pairs(deps) do AddQuest(q) end
    end
    return { kind = "section", key = "s:" .. sec.id, section = sec.id, sections = secs, title = sec.title or sec.id,
      hint = sec.later_hint, hintLevel = sec.later_level, hintMap = sec.later_map, list = quests }
  end
  local q = StepQuest(entry.step)
  if not q then return nil end
  local list, count = { q }, 0
  for _, d in ipairs(Senda.Guides:Followups(q) or {}) do
    if not self:QuestTaken(d) then
      list[#list + 1] = d
      if self.acceptIndex and self.acceptIndex[d] then count = count + 1 end -- las de esta guía
    end
  end
  return { kind = "quest", key = "q:" .. q, quest = q, list = list, count = count }
end

local function Reposition(reason)
  Engine.held = nil
  Engine:MoveTo(Engine:NextPending(Engine.index))
  Engine:RequestEvaluate(0.1, reason)
end

function Engine:Park(entry)
  entry = entry or self.steps[self.index]
  local info = self:ParkInfo(entry)
  if not info then return nil end
  local t = ParkedTable(true)
  if not t then return nil end
  if t[info.key] then return t[info.key] end
  local map, x, y = Compat.PlayerMapPos()
  info.when = time()
  info.level = Compat.PlayerLevel()
  info.map = map
  info.x = x and math.floor(x * 1000 + 0.5) / 10 or nil
  info.y = y and math.floor(y * 1000 + 0.5) / 10 or nil
  info.from = entry.step.id
  t[info.key] = info
  Invalidate()
  Reposition("park")
  Events:Fire("SENDA_PARKED", info)
  Events:Fire("SENDA_STEP_UPDATED", self.steps[self.index])
  return info
end

local function Want(it)
  local want, secs = {}, {}
  for _, q in ipairs(it.list or {}) do want[q] = true end
  if it.kind == "section" then
    for _, sid in ipairs(it.sections or { it.section }) do secs[sid] = true end
  end
  return want, secs
end

-- ¿Es este paso de este aparcado? Sus secciones; los pasos de sus misiones (todas aparcadas); y el «ve a»
-- justo antes de uno de ellos.
local function ItemHas(e, want, secs)
  if e.section and secs[e.section.id] then return true end
  local s = e.step
  local qs = QUESTY[s["do"]] and Cond:Quests(s)
  if qs then
    for _, q in ipairs(qs) do if not want[q] then return false end end
    return true
  end
  if s["do"] == "goto" and e.index then
    local nxt = Engine.steps[e.index + 1]
    local nq = nxt and nxt.secIndex == e.secIndex and QUESTY[nxt.step["do"]] and Cond:Quests(nxt.step)
    if nq then
      for _, q in ipairs(nq) do if not want[q] then return false end end
      return true
    end
  end
  return false
end

-- Primer índice de la guía con un paso de este aparcado.
local function FirstIndexOf(it)
  local want, secs = Want(it)
  for i, e in ipairs(Engine.steps) do
    if ItemHas(e, want, secs) then return i end
  end
  return nil
end

-- Lo devuelve a la ruta. `stay`: no recolocar el puntero (al terminarlo en un desvío).
function Engine:Unpark(key, stay)
  local t = ParkedTable(false)
  local it = t and t[key]
  if not it then return false end
  t[key] = nil
  Invalidate()
  if not stay then
    local first = FirstIndexOf(it)
    self.held = nil
    if first and first < self.index then
      self:MoveTo(self:NextPending(first))
    else
      self:MoveTo(self:NextPending(self.index))
    end
    self:RequestEvaluate(0.1, "unpark")
  end
  Events:Fire("SENDA_PARKED", nil)
  Events:Fire("SENDA_STEP_UPDATED", self.steps[self.index])
  return true
end

-- Pasos pendientes de un aparcado (en orden de la guía).
function Engine:ParkedSteps(it)
  local out = {}
  local want, secs = Want(it)
  for _, e in ipairs(self.steps) do
    if ItemHas(e, want, secs) and not self:IsMarked(e) and Cond:LevelFilter(e.step["if"]) then
      local done = Cond:Check(e.step, { turnedIn = self.turnedIn }) == true and Cond:CanFastForward(e.step)
      if not done then out[#out + 1] = e end
    end
  end
  return out
end

-- Lo aparcado de la guía activa, del más antiguo al más reciente. Lo que ya está hecho (lo terminaste por tu
-- cuenta) se marca en la ruta y se olvida.
function Engine:Parked()
  local t = ParkedTable(false)
  local out = {}
  if not t then return out end
  local gone = {}
  for key, it in pairs(t) do
    local steps = self:ParkedSteps(it)
    if #steps == 0 then
      gone[#gone + 1] = key
    else
      local copy = {}
      for k, v in pairs(it) do copy[k] = v end
      copy.key = key
      copy.steps = steps
      out[#out + 1] = copy
    end
  end
  if #gone > 0 and not (Aside:Active()) then
    for _, key in ipairs(gone) do
      local it = t[key]
      -- Sus pasos quedaron hechos fuera de la ruta: se marcan como hechos por el juego.
      local p = Progress()
      local want, secs = Want(it)
      for _, e in ipairs(self.steps) do
        if ItemHas(e, want, secs) and p and not p.done[e.step.id] and Cond:LevelFilter(e.step["if"]) then p.done[e.step.id] = "a" end
      end
      t[key] = nil
    end
    Invalidate()
    Events:Fire("SENDA_PARKED", nil)
  end
  table.sort(out, function(a, b)
    if (a.when or 0) ~= (b.when or 0) then return (a.when or 0) < (b.when or 0) end
    return a.key < b.key
  end)
  return out
end

function Engine:ParkedCount()
  local n = 0
  for _ in pairs(ParkedTable(false) or {}) do n = n + 1 end
  return n
end

-- Nombre corto de un aparcado: la misión o la sección.
function Aside:ItemName(it)
  if not it then return "" end
  if it.kind == "section" then return it.title or it.section or "" end
  return Senda.Names:Get("quest", it.quest) or Senda.Names:Placeholder("quest", it.quest)
end

------------------------------------------------------------------------------
-- Recordatorio
------------------------------------------------------------------------------

local dismissed = {} -- en memoria: clave del aparcado .. mapa (o "lvl") -> true

function Aside:Dismiss(rem)
  if not rem then return end
  dismissed[rem.key .. ":" .. tostring(rem.dkey)] = true
  Events:Fire("SENDA_PARKED", nil)
end

function Aside:Reminder()
  if self:Active() then return nil end
  local list = Engine:Parked()
  if #list == 0 then return nil end
  local map, x, y = Compat.PlayerMapPos()
  local level = Compat.PlayerLevel() or 1
  local radius = Senda.Options:Get("parkRemindDistance") or 300
  for _, it in ipairs(list) do
    local onMap = map and it.hintMap == map
    for _, e in ipairs(it.steps) do
      local at = e.step.at
      if map and type(at) == "table" and at[1] == map then onMap = true end
    end
    if onMap and not dismissed[it.key .. ":" .. tostring(map)] then
      return { key = it.key, item = it, reason = "map", dkey = map }
    end
    local nxt = it.steps[1] and it.steps[1].step.at
    if map and type(nxt) == "table" and nxt[1] then
      local d = Compat.WorldDistance(map, x, y, nxt[1], (nxt[2] or 0) / 100, (nxt[3] or 0) / 100)
      if d and d <= radius and not dismissed[it.key .. ":near"] then
        return { key = it.key, item = it, reason = "near", dkey = "near" }
      end
    end
    if it.hintLevel and level >= it.hintLevel and not dismissed[it.key .. ":lvl"] then
      return { key = it.key, item = it, reason = "level", dkey = "lvl" }
    end
  end
  return nil
end

------------------------------------------------------------------------------
-- Desvío activo
------------------------------------------------------------------------------

local detour -- { items, steps = { dEntry... }, index, returnTo, guide }
local ticker

local function Saved()
  local db = Senda.db
  if not db then return nil end
  db.aside = db.aside or {}
  return db.aside
end

function Aside:Active() return detour ~= nil end
function Aside:Steps() return detour and detour.steps or {} end
function Aside:Index() return detour and detour.index or 0 end
function Aside:Items() return detour and detour.items or {} end
function Aside:ReturnTo() return detour and detour.returnTo end

function Aside:CurrentStep()
  if not detour then return nil end
  local d = detour.steps[detour.index]
  if d then return d.step, d end
  return nil
end

local function Fmt(key, ...)
  return string.format(L[key] or key, ...)
end

-- Objetivos en texto con fichas: «mata 8 {npc:N}, consigue 5 {item:M}».
function Aside:ObjectivesText(e)
  local parts = {}
  for _, o in ipairs(e.objectives or {}) do
    if o.kind == "c" then parts[#parts + 1] = Fmt("ASIDE_OBJ_KILL", o.count or 1, o.id)
    elseif o.kind == "i" then parts[#parts + 1] = Fmt("ASIDE_OBJ_ITEM", o.count or 1, o.id)
    elseif o.kind == "o" then parts[#parts + 1] = Fmt("ASIDE_OBJ_OBJECT", o.id)
    elseif o.kind == "t" then parts[#parts + 1] = Fmt("ASIDE_OBJ_TALK", o.id)
    elseif o.kind == "e" then parts[#parts + 1] = L.ASIDE_OBJ_EVENT end
  end
  return table.concat(parts, ", ")
end

local function Who(w)
  if not w then return "?" end
  return w.kind == "o" and ("{obj:" .. w.id .. "}") or ("{npc:" .. w.id .. "}")
end

-- Pasos coger / completar / entregar de una misión de la reserva.
local function ReserveSteps(e)
  local q = e.quest
  local g, t = e.giver, e.turnin
  local acc = { id = "aside-" .. q .. "-a", ["do"] = "accept", quest = q, npc = g.kind == "n" and g.id or nil,
    at = { g.at[1], g.at[2], g.at[3] }, text = Fmt("ASIDE_STEP_ACCEPT", q, Who(g)), status = "unverified" }
  local obj = Aside:ObjectivesText(e)
  local cpt = e.point or g.at
  local com = { id = "aside-" .. q .. "-c", ["do"] = "complete", quest = q, at = { cpt[1], cpt[2], cpt[3] },
    text = obj ~= "" and Fmt("ASIDE_STEP_COMPLETE_OBJ", q, obj) or Fmt("ASIDE_STEP_COMPLETE", q), status = "unverified" }
  local tin = { id = "aside-" .. q .. "-t", ["do"] = "turnin", quest = q, npc = t.kind == "n" and t.id or nil,
    at = { t.at[1], t.at[2], t.at[3] }, text = Fmt("ASIDE_STEP_TURNIN", q, Who(t)), status = "unverified" }
  return acc, com, tin
end

-- Ordena por cercanía encadenada (el más cercano primero, luego el más cercano a ese...).
local function Nearest(list, from)
  local out, left = {}, {}
  for i, d in ipairs(list) do left[i] = d end
  local cur = from
  while #left > 0 do
    local bi, bd = 1, nil
    for i, d in ipairs(left) do
      local at = d.step.at
      local dist
      if cur and at then dist = Compat.WorldDistance(cur[1], cur[2] / 100, cur[3] / 100, at[1], at[2] / 100, at[3] / 100) end
      dist = dist or ((cur and at and cur[1] == at[1]) and 0 or 1e9)
      if not bd or dist < bd then bi, bd = i, dist end
    end
    local d = table.remove(left, bi)
    out[#out + 1] = d
    cur = d.step.at or cur
  end
  return out
end

local function Build(items)
  local steps = {}
  local acc, com, tin = {}, {}, {}
  for _, it in ipairs(items) do
    if it.kind == "parked" then
      local p = (ParkedTable(false) or {})[it.key]
      if p then
        for _, e in ipairs(Engine:ParkedSteps(p)) do
          steps[#steps + 1] = { step = e.step, origin = e, item = it }
        end
      end
    elseif it.kind == "reserve" then
      local e = Senda.Reserve:Get(it.quest)
      if e then
        local a, c, t = ReserveSteps(e)
        acc[#acc + 1] = { step = a, item = it }
        com[#com + 1] = { step = c, item = it }
        tin[#tin + 1] = { step = t, item = it }
      end
    end
  end
  local map, x, y = Compat.PlayerMapPos()
  local here = map and { map, x * 100, y * 100 } or nil
  local la = Nearest(acc, here)
  local last = la[#la] and la[#la].step.at or here
  local lc = Nearest(com, last)
  last = lc[#lc] and lc[#lc].step.at or last
  local lt = Nearest(tin, last)
  for _, l in ipairs({ la, lc, lt }) do
    for _, d in ipairs(l) do steps[#steps + 1] = d end
  end
  for i, d in ipairs(steps) do d.index = i end
  return steps
end

local function Persist()
  local sv = Saved()
  if not sv then return end
  if not detour then sv.detour = nil; return end
  local done = {}
  for _, d in ipairs(detour.steps) do if d.mark then done[d.step.id] = d.mark end end
  sv.detour = { items = detour.items, done = done, returnTo = detour.returnTo, guide = detour.guide,
    started = detour.started }
end

local function StopTicker()
  if ticker then ticker:Cancel(); ticker = nil end
end

local function SyncTicker()
  local s = Aside:CurrentStep()
  if s and Cond:NeedsPosition(s) then
    if not ticker then
      ticker = Compat.NewTicker(0.5, function()
        if not Compat.InCombat() then Aside:Evaluate("pos") end
      end)
    end
  else
    StopTicker()
  end
end

local function Changed()
  Persist()
  SyncTicker()
  Events:Fire("SENDA_ASIDE_CHANGED")
end

-- Empieza un desvío (sustituye al que hubiera). Las misiones de la reserva necesitan la reserva cargada.
function Aside:Start(items)
  if type(items) ~= "table" or #items == 0 then return false end
  local steps = Build(items)
  if #steps == 0 then return false end
  local cur = Engine:CurrentStep()
  detour = { items = items, steps = steps, index = 1, returnTo = cur and cur.id, guide = Engine.guideId,
    started = time(), state = {} }
  Changed()
  self:Evaluate("start")
  Senda:Print(L.ASIDE_STARTED, #steps)
  return true
end

-- Añade más cosas al desvío activo (o lo empieza).
function Aside:Add(items)
  if not detour then return self:Start(items) end
  local all = {}
  for _, it in ipairs(detour.items) do all[#all + 1] = it end
  for _, it in ipairs(items) do all[#all + 1] = it end
  local marks = {}
  for _, d in ipairs(detour.steps) do marks[d.step.id] = d.mark end
  detour.items = all
  detour.steps = Build(all)
  for _, d in ipairs(detour.steps) do d.mark = marks[d.step.id] end
  detour.index = 1
  Changed()
  self:Evaluate("add")
  return true
end

local function Finish(cancelled)
  if not detour then return end
  local items = detour.items
  detour = nil
  StopTicker()
  -- Lo aparcado que quedó hecho deja de estar aparcado (Engine:Parked lo marca en la ruta).
  Engine:Parked()
  Persist()
  Events:Fire("SENDA_ASIDE_CHANGED")
  Senda:Print(cancelled and L.ASIDE_CANCELLED or L.ASIDE_FINISHED)
  Engine:RequestEvaluate(0.1, "aside")
  Events:Fire("SENDA_STEP_CHANGED", Engine.steps[Engine.index])
  return items
end

function Aside:Cancel() return Finish(true) end

-- Un paso de completar/entregar de una misión que no tienes y cuyo paso de coger ya pasó (lo saltaste): fuera.
local function NotTaken(d)
  local s = d.step
  if (s["do"] ~= "complete" and s["do"] ~= "turnin") or not s.quest then return false end
  if Engine:QuestTaken(s.quest) then return false end
  for i = 1, d.index - 1 do
    local o = detour.steps[i]
    if o.step["do"] == "accept" and o.step.quest == s.quest then return true end
  end
  if d.origin then return Engine:NotTaken(d.origin) end
  return false
end

local function Passable(d)
  if d.mark then return true end
  local s = d.step
  if not Cond:LevelFilter(s["if"]) then return true end
  if d.origin and (Engine:WaitLevel(d.origin) or Engine:NoSkill(d.origin)) then return true end
  return NotTaken(d)
end

local function MarkOrigin(d, kind)
  d.mark = kind
  if d.origin then
    local p = Progress()
    if p and Engine.guideId == detour.guide then
      p.done[d.step.id] = kind == "s" and "s" or "a"
      Events:Fire("SENDA_STEP_COMPLETED", d.step, p.done[d.step.id])
    end
  end
end

function Aside:Evaluate(reason)
  if not detour or Compat.InCombat() then return end
  local start = detour.index
  local loops = 0
  while loops < 200 do
    loops = loops + 1
    local d = detour.steps[detour.index]
    if not d then break end
    if Passable(d) then
      detour.index = detour.index + 1
      detour.state = {}
    else
      local r = Cond:Check(d.step, { turnedIn = Engine.turnedIn, startedInZone = detour.state.startedInZone })
      if r == true then
        MarkOrigin(d, "a")
        detour.index = detour.index + 1
        detour.state = {}
      else
        break
      end
    end
  end
  if detour.index > #detour.steps then
    Finish(false)
    return
  end
  if detour.index ~= start then
    Changed()
  end
end

function Aside:Advance()
  local d = detour and detour.steps[detour.index]
  if not d then return end
  MarkOrigin(d, "d")
  detour.index = detour.index + 1
  Changed()
  self:Evaluate("advance")
end

function Aside:Skip()
  local d = detour and detour.steps[detour.index]
  if not d then return end
  d.mark = "s" -- saltar dentro del desvío no salta el paso de la ruta
  detour.index = detour.index + 1
  Changed()
  self:Evaluate("skip")
end

function Aside:Back()
  if not detour or detour.index <= 1 then return end
  local i = detour.index - 1
  detour.steps[i].mark = nil
  detour.index = i
  Changed()
end

function Aside:NextSteps(n)
  local out = {}
  if not detour then return out end
  for i = detour.index + 1, #detour.steps do
    local d = detour.steps[i]
    if not d.mark then out[#out + 1] = d end
    if #out >= (n or 2) then break end
  end
  return out
end

function Aside:Progress()
  if not detour then return 0, 0 end
  local done = 0
  for i, d in ipairs(detour.steps) do if d.mark or i < detour.index then done = done + 1 end end
  return done, #detour.steps
end

-- La guía quiere coger o entregar esta misión: también si es del paso actual del desvío (Engine/Automation.lua).
local baseWants = Engine.WantsQuest
function Engine:WantsQuest(kind, q)
  if baseWants and baseWants(self, kind, q) then return true end
  local s = Aside:CurrentStep()
  q = Compat.Num(q)
  if not s or not q or s.quest ~= q then return false end
  if kind == "accept" then
    return s["do"] == "accept" and not Compat.IsOnQuest(q) and not Compat.IsQuestDone(q)
  end
  if kind == "turnin" then
    if Senda.Party and Senda.Party.HoldsQuest and Senda.Party.HoldsQuest(q) then return false end
    return s["do"] == "turnin"
  end
  return false
end

-- Restaura el desvío guardado (tras recargar). Lo de la reserva espera a que la reserva cargue.
function Aside:Restore()
  local sv = Saved()
  local saved = sv and sv.detour
  if not saved or type(saved.items) ~= "table" then return end
  if saved.guide and saved.guide ~= Engine.guideId then sv.detour = nil; return end
  local needsPool = false
  for _, it in ipairs(saved.items) do if it.kind == "reserve" then needsPool = true end end
  local function go()
    local steps = Build(saved.items)
    if #steps == 0 then sv.detour = nil; return end
    for _, d in ipairs(steps) do d.mark = saved.done and saved.done[d.step.id] or nil end
    detour = { items = saved.items, steps = steps, index = 1, returnTo = saved.returnTo, guide = saved.guide,
      started = saved.started, state = {} }
    Changed()
    Aside:Evaluate("restore")
  end
  if needsPool and Senda.Reserve and not Senda.Reserve:Ready() then
    Senda.Reserve:Load(go)
  else
    go()
  end
end

------------------------------------------------------------------------------
-- Opciones y eventos
------------------------------------------------------------------------------

local SEC = L.OPT_SECTION_ASIDE
Senda.Options:Register({ key = "parkRemindDistance", label = L.OPT_PARK_DISTANCE, tooltip = L.OPT_PARK_DISTANCE_TIP,
  type = "slider", default = 300, min = 50, max = 2000, step = 50, section = SEC, order = 1 })
Senda.Options:Register({ key = "reserveRadius", label = L.OPT_RESERVE_RADIUS, tooltip = L.OPT_RESERVE_RADIUS_TIP,
  type = "slider", default = 1500, min = 300, max = 5000, step = 100, section = SEC, order = 2 })
Senda.Options:Register({ key = "reserveHint", label = L.OPT_RESERVE_HINT, tooltip = L.OPT_RESERVE_HINT_TIP,
  type = "toggle", default = true, section = SEC, order = 3 })

Events:On("SENDA_READY", function()
  Events:On("SENDA_GUIDE_CHANGED", function()
    Invalidate()
    if detour and detour.guide ~= Engine.guideId then
      detour = nil
      StopTicker()
      Persist()
      Events:Fire("SENDA_ASIDE_CHANGED")
    end
  end)
  Events:On("ZONE_CHANGED_NEW_AREA", function()
    if detour then detour.state.zoneChanged = true end
  end)
  Compat.After(1.5, function() Aside:Restore() end)
end)

-- Reserva de XP (pestaña «Aparte»): misiones que puedes coger ya cerca de ti y que la ruta no te pide ahora,
-- ordenadas por XP por minuto contando el camino hasta quien las da.
--   Senda.Reserve:RegisterZone(map, texto)  -- lo llama Guides/Reserve.lua (GENERADO desde data/reserve.json)
--   Senda.Reserve:Ready() -> ¿ya descodificada?    :Load([fn])  -- descodifica bajo demanda (corrutina)
--   Senda.Reserve:Get(q) -> entrada o nil          :Count() -> misiones en la reserva
--   Senda.Reserve:Offers(opts) -> { { e, xp, mins, dist, rate }, ... }  (opts.limit, opts.map, opts.radius)
--   Senda.Reserve:Need() -> { level, xp, entry, reason } o nil: XP que falta para el siguiente paso de la ruta
--   Senda.Reserve:Plan(offers, xp) -> lista, minutos: las primeras ofertas que dan esa XP
--   Senda.Reserve:QuestXP(e[, nivel]) -> XP que da la misión a tu nivel
-- Datos: tools/reserve.py (puntuaciones de tools/route_score.py, forever-db y las guías; ver THIRD_PARTY.md).
-- Las cadenas se descodifican fuera de combate, 150 misiones por fotograma, y solo al usarse por primera vez.
local _, Senda = ...
local Compat, Events = Senda.Compat, Senda.Events

local Reserve = {}
Senda.Reserve = Reserve

local raw = {}         -- map -> texto
local rawOrder = {}
local entries          -- lista descodificada (nil hasta Load)
local byQuest = {}
local loadCo, loadFrame, loadWaiters
local SLICE = 150

Reserve.WALK_SPEED = 7     -- m/s a pie (con montura el camino cuesta menos: es una cota alta)
Reserve.RADIUS = 1500      -- metros: «este mapa y los vecinos»

-- XP para pasar del nivel L al L+1 (tabla 1.12; la misma que usa tools/route_score.py, de Polestar
-- tools/lib/game/xp.js).
local LEVEL_XP = {
  [0] = 0, 400, 900, 1400, 2100, 2800, 3600, 4500, 5400, 6500, 7600,
  8800, 10100, 11400, 12900, 14400, 16000, 17700, 19400, 21300, 23200,
  25200, 27300, 29400, 31700, 34000, 36400, 38900, 41400, 44300, 47400,
  50800, 54500, 58600, 62800, 67100, 71600, 76100, 80800, 85700, 90700,
  95800, 101000, 106300, 111800, 117500, 123200, 129100, 135100, 141200, 147500,
  153900, 160400, 167100, 173900, 180800, 187900, 195000, 202300, 209800,
}
Reserve.LEVEL_XP = LEVEL_XP

local RACE_BIT = { Human = 0, Orc = 1, Dwarf = 2, NightElf = 3, Scourge = 4, Tauren = 5, Gnome = 6, Troll = 7 }
local CLASS_BIT = { WARRIOR = 0, PALADIN = 1, HUNTER = 2, ROGUE = 3, PRIEST = 4, SHAMAN = 6, MAGE = 7, WARLOCK = 8,
  DRUID = 10 }

local function HasBit(mask, bit)
  if not mask or mask == 0 then return true end
  if not bit then return false end
  return math.floor(mask / 2 ^ bit) % 2 == 1
end

function Reserve:RegisterZone(map, text)
  map = tonumber(map)
  if not map or type(text) ~= "string" then return end
  if not raw[map] then rawOrder[#rawOrder + 1] = map end
  raw[map] = text
  entries = nil
end

------------------------------------------------------------------------------
-- Descodificación
------------------------------------------------------------------------------

local function Who(s)
  if not s or s == "" then return nil end
  local kind, id, m, x, y = s:match("^(%a)(%d+)@(%d+):([%d.]+),([%d.]+)$")
  if not kind then return nil end
  return { kind = kind, id = tonumber(id), at = { tonumber(m), tonumber(x), tonumber(y) } }
end

local function Ids(s)
  local t = {}
  for d in (s or ""):gmatch("%d+") do t[#t + 1] = tonumber(d) end
  return t
end

local function Objectives(s)
  local t = {}
  for part in (s or ""):gmatch("[^,]+") do
    local k, id, n = part:match("^(%a)(%d+)x(%d+)$")
    if k then
      t[#t + 1] = { kind = k, id = tonumber(id), count = tonumber(n) }
    else
      k, id = part:match("^(%a)(%d*)$")
      if k then t[#t + 1] = { kind = k, id = tonumber(id) } end
    end
  end
  return t
end

local function Split(line)
  local f, start = {}, 1
  while true do
    local i = line:find("|", start, true)
    if not i then f[#f + 1] = line:sub(start); break end
    f[#f + 1] = line:sub(start, i - 1)
    start = i + 1
  end
  return f
end

local DEC = { k = "keep", o = "optional", d = "drop" }

function Reserve:Decode(line)
  local f = Split(line)
  local q = tonumber(f[1])
  if not q then return nil end
  local pt
  if f[14] and f[14] ~= "" then
    local m, x, y = f[14]:match("^(%d+):([%d.]+),([%d.]+)$")
    if m then pt = { tonumber(m), tonumber(x), tonumber(y) } end
  end
  return {
    quest = q, reqlevel = tonumber(f[2]) or 1, level = tonumber(f[3]) or 1, xp = tonumber(f[4]) or 0,
    mins = (tonumber(f[5]) or 0) / 10, decision = DEC[f[6]] or "keep",
    races = tonumber(f[7]) or 0, classes = tonumber(f[8]) or 0,
    giver = Who(f[9]), turnin = Who(f[10]), preAll = Ids(f[11]), preAny = Ids(f[12]),
    objectives = Objectives(f[13]), point = pt,
  }
end

local function DecodeAll(tick)
  local list, index = {}, {}
  for _, map in ipairs(rawOrder) do
    for line in raw[map]:gmatch("[^\n]+") do
      local e = Reserve:Decode(line)
      if e and e.giver and e.turnin then
        -- Posición de mundo de quien la da, ya aquí (repartido en fotogramas): las ofertas solo restan.
        local g = e.giver.at
        e.wc, e.wn, e.ww = Compat.WorldPos(g[1], g[2] / 100, g[3] / 100)
        e.wc = e.wc or false
        list[#list + 1] = e
        index[e.quest] = e
      end
      if tick then tick() end
    end
  end
  return list, index
end

function Reserve:Ready() return entries ~= nil end

function Reserve:Count()
  if entries then return #entries end
  local n = 0
  for _, map in ipairs(rawOrder) do
    for _ in raw[map]:gmatch("[^\n]+") do n = n + 1 end
  end
  return n
end

-- Descodificación inmediata (pruebas, o si ya se pidió y hace falta ya).
function Reserve:LoadNow()
  if not entries then entries, byQuest = DecodeAll() end
  return entries
end

local function LoadStep()
  if not loadCo then
    if loadFrame then loadFrame:Hide() end
    return
  end
  if Compat.InCombat() then return end
  local ok, list, index = coroutine.resume(loadCo)
  if not ok then
    loadCo = nil
    loadFrame:Hide()
    Senda:Debug("Error al cargar la reserva: %s", tostring(list))
    return
  end
  if coroutine.status(loadCo) == "dead" then
    loadCo = nil
    loadFrame:Hide()
    entries, byQuest = list, index
    local waiters = loadWaiters or {}
    loadWaiters = nil
    for _, fn in ipairs(waiters) do pcall(fn) end
    Events:Fire("SENDA_RESERVE_READY")
  end
end

-- Descodifica la reserva repartida en fotogramas, fuera de combate. `fn` se llama al terminar.
function Reserve:Load(fn)
  if entries then
    if fn then fn() end
    return
  end
  loadWaiters = loadWaiters or {}
  if fn then loadWaiters[#loadWaiters + 1] = fn end
  if loadCo then return end
  local k = 0
  loadCo = coroutine.create(function()
    return DecodeAll(function()
      k = k + 1
      if k % SLICE == 0 then coroutine.yield() end
    end)
  end)
  if not loadFrame then
    loadFrame = CreateFrame("Frame")
    loadFrame:SetScript("OnUpdate", LoadStep)
  end
  loadFrame:Show()
end

function Reserve:Get(q)
  return entries and byQuest[q] or nil
end

------------------------------------------------------------------------------
-- Disponibilidad y puntuación
------------------------------------------------------------------------------

-- XP de la misión a tu nivel: completa hasta 5 niveles por encima de la misión, luego 80/60/40/20/10%
-- (adaptado de Polestar, tools/lib/game/xp.js, GPL-3), redondeada a 5.
local REDUCE = { [6] = 0.8, [7] = 0.6, [8] = 0.4, [9] = 0.2 }
function Reserve:QuestXP(e, level)
  if not e then return 0 end
  level = level or Compat.PlayerLevel() or 1
  local diff = level - (e.level or level)
  local f = 1
  if diff >= 10 then f = 0.1 elseif diff > 5 then f = REDUCE[diff] or 0.1 end
  return math.floor(e.xp * f / 5 + 0.5) * 5
end

local function Done(q)
  return Compat.IsQuestDone(q) or (Senda.Engine and Senda.Engine.turnedIn and Senda.Engine.turnedIn[q]) or false
end

-- ¿La puede coger el jugador ahora? (raza, clase, nivel, requisitos entregados, no en el registro ni hecha)
function Reserve:Available(e, level)
  if not e then return false end
  level = level or Compat.PlayerLevel() or 1
  if e.reqlevel > level then return false end
  if Compat.PlayerFaction() ~= "Alliance" then return false end -- la reserva solo trae la Alianza
  if not HasBit(e.races, RACE_BIT[Compat.PlayerRace() or ""]) then return false end
  if not HasBit(e.classes, CLASS_BIT[Compat.PlayerClass() or ""]) then return false end
  local q = e.quest
  if Done(q) or Compat.IsOnQuest(q) then return false end
  local E = Senda.Engine
  if E and E.IsQuestSkipped and E:IsQuestSkipped(q) then return false end
  for _, p in ipairs(e.preAll) do
    if not Done(p) then return false end
  end
  if #e.preAny > 0 then
    local any = false
    for _, p in ipairs(e.preAny) do if Done(p) then any = true; break end end
    if not any then return false end
  end
  return true
end

-- Misiones que la ruta activa te pide más adelante (no hace falta ofrecerlas: ya irás).
function Reserve:RouteQuests()
  local E = Senda.Engine
  local out = {}
  if not E or not E.Steps then return out end
  local steps = E:Steps()
  for i = E:Index(), #steps do
    local e = steps[i]
    local s = e.step
    if s["do"] == "accept" and s.quest and not s.optional and not E:IsMarked(e)
      and not (E.StepParked and E:StepParked(e)) then
      out[s.quest] = true
    end
  end
  return out
end

-- Ofertas: misiones disponibles en tu mapa o a menos de `radius` metros, ordenadas por XP por minuto contando
-- el camino hasta quien la da.
function Reserve:Offers(opts)
  opts = opts or {}
  if not entries then return {}, false end
  local map, x, y = Compat.PlayerMapPos()
  map = opts.map or map
  local level = Compat.PlayerLevel() or 1
  local radius = opts.radius or (Senda.Options and Senda.Options:Get("reserveRadius")) or self.RADIUS
  local route = opts.includeRoute and {} or self:RouteQuests()
  local exclude = opts.exclude or {}
  local out = {}
  local pc, pn, pw
  if map and x then pc, pn, pw = Compat.WorldPos(map, x, y) end
  for _, e in ipairs(entries) do
    -- Primero lo barato (nivel y distancia, con la posición de mundo de quien la da en caché), después el
    -- registro de misiones.
    if e.reqlevel <= level and not route[e.quest] and not exclude[e.quest] then
      local g = e.giver.at
      if e.wc == nil then
        e.wc, e.wn, e.ww = Compat.WorldPos(g[1], g[2] / 100, g[3] / 100)
        e.wc = e.wc or false
      end
      local dist
      if pc and e.wc and e.wc == pc then
        local dn, dw = e.wn - pn, e.ww - pw
        dist = math.sqrt(dn * dn + dw * dw) * 0.9144
      elseif map and x and g[1] == map then
        dist = Compat.WorldDistance(map, x, y, g[1], g[2] / 100, g[3] / 100)
      end
      local near = (g[1] == map) or (dist and dist <= radius)
      if near and self:Available(e, level) then
        local xp = self:QuestXP(e, level)
        if xp > 0 then
          local walk = dist and (dist / self.WALK_SPEED / 60) or 0
          local mins = e.mins + walk
          out[#out + 1] = { e = e, xp = xp, mins = mins, dist = dist, rate = xp / math.max(mins, 0.5) }
        end
      end
    end
  end
  table.sort(out, function(a, b)
    if a.rate ~= b.rate then return a.rate > b.rate end
    if (a.dist or 0) ~= (b.dist or 0) then return (a.dist or 0) < (b.dist or 0) end
    return a.e.quest < b.e.quest
  end)
  if opts.limit and #out > opts.limit then
    for i = #out, opts.limit + 1, -1 do out[i] = nil end
  end
  return out, true
end

-- XP que falta hasta el nivel `target` (desde la XP actual).
function Reserve:XPTo(target)
  local level = Compat.PlayerLevel() or 1
  if not target or target <= level then return 0 end
  local cur = Compat.Num(Compat.Try(UnitXP, "player")) or 0
  local max = Compat.Num(Compat.Try(UnitXPMax, "player")) or LEVEL_XP[level] or 0
  local need = math.max(0, max - cur)
  for l = level + 1, target - 1 do need = need + (LEVEL_XP[l] or 0) end
  return need
end

-- ¿Te falta nivel para lo que sigue en la ruta? Mira las misiones aplazadas por nivel cerca de tu paso
-- (Engine:LevelGated: Engine:WaitLevel las pasó) y el paso actual. Devuelve { level, xp, entry } o nil.
local NEAR_STEPS = 40
function Reserve:Need()
  local E = Senda.Engine
  if not E or not E.LevelGated then return nil end
  local level = Compat.PlayerLevel() or 1
  local best
  for _, g in ipairs(E:LevelGated()) do
    if not g.ready and g.index and g.index <= (E:Index() + NEAR_STEPS) and (not best or g.level < best.level) then
      best = g
    end
  end
  local cur = E:Entry()
  if cur and E.WaitLevel then
    local w = E:WaitLevel(cur)
    if w and w > level and (not best or w < best.level) then best = { entry = cur, level = w } end
  end
  if not best then return nil end
  return { level = best.level, xp = self:XPTo(best.level), entry = best.entry, reason = "gate" }
end

-- ¿Se acabó la ruta en este mapa para tu nivel? (ningún paso pendiente cerca en tu mapa)
function Reserve:RouteEmptyHere()
  local E = Senda.Engine
  if not E or not E.Steps or not E:GuideId() then return false end
  local map = Compat.BestMap()
  if not map then return false end
  -- De viaje (el paso actual es ir, volar o usar la piedra de hogar): ya te vas de aquí.
  local cur = E:CurrentStep()
  local d = cur and cur["do"]
  if d == "goto" or d == "fly" or d == "hearth" or d == "getfp" then return false end
  local steps = E:Steps()
  local seen = 0
  for i = E:Index(), #steps do
    local e = steps[i]
    if E:IsApplicable(e) and not E:IsMarked(e) and not (E.StepParked and E:StepParked(e)) then
      local at = e.step.at
      if type(at) == "table" and at[1] == map then return false end
      seen = seen + 1
      if seen >= NEAR_STEPS then break end
    end
  end
  return true
end

-- Las primeras ofertas (en su orden) que juntas dan `xp`. Devuelve lista, minutos, xp que suman.
function Reserve:Plan(offers, xp)
  local list, mins, sum = {}, 0, 0
  for _, o in ipairs(offers or {}) do
    if xp and sum >= xp then break end
    list[#list + 1] = o
    mins = mins + o.mins
    sum = sum + o.xp
  end
  return list, mins, sum
end

------------------------------------------------------------------------------
-- Estado para el HUD y la pestaña (en caché; se rehace con los eventos)
------------------------------------------------------------------------------
-- Reserve:State() -> { reason = "gate"|"empty"|"manual"|nil, need, offers, plan, planMins, planXP, loading }
-- Se ofrece si te falta nivel para el siguiente paso de la ruta (Need), si la ruta no tiene nada para ti en este
-- mapa (RouteEmptyHere) o si lo pides con «Más misiones aquí» (Reserve:Ask()).

local state, dirtyState = nil, true
local askedMap

function Reserve:Invalidate()
  dirtyState = true
  Events:Fire("SENDA_RESERVE_UPDATED")
end

-- «Más misiones aquí»: ofrece la reserva en este mapa aunque la ruta no la necesite.
function Reserve:Ask()
  askedMap = Compat.BestMap() or true
  dirtyState = true
  if not entries then self:Load(function() Reserve:Invalidate() end) end
  Events:Fire("SENDA_RESERVE_UPDATED")
end

function Reserve:Asked()
  return askedMap ~= nil and (askedMap == true or askedMap == Compat.BestMap())
end

function Reserve:State()
  if not dirtyState and state then return state end
  local s = {}
  local E = Senda.Engine
  if E and E:GuideId() then
    s.need = self:Need()
    if s.need and s.need.xp > 0 then
      s.reason = "gate"
    elseif self:RouteEmptyHere() then
      s.reason = "empty"
    end
  end
  if not s.reason and self:Asked() then s.reason = "manual" end
  if s.reason then
    if not entries then
      s.loading = true
      if not Compat.InCombat() then self:Load(function() Reserve:Invalidate() end) end
      state = s
      return s -- no queda limpio: al cargar se rehace
    end
    s.offers = self:Offers({ limit = 15 })
    if s.reason == "gate" then
      s.plan, s.planMins, s.planXP = self:Plan(s.offers, s.need.xp)
    end
  end
  state, dirtyState = s, false
  return s
end

Events:On("SENDA_READY", function()
  local inv = function() Reserve:Invalidate() end
  for _, ev in ipairs({ "QUEST_TURNED_IN", "QUEST_ACCEPTED", "QUEST_REMOVED", "PLAYER_LEVEL_UP", "PLAYER_XP_UPDATE",
    "SENDA_STEP_CHANGED", "SENDA_GUIDE_CHANGED", "SENDA_PARKED", "SENDA_SKIPPED" }) do
    Events:On(ev, inv)
  end
  Events:On("ZONE_CHANGED_NEW_AREA", function()
    if askedMap and askedMap ~= true and askedMap ~= Compat.BestMap() then askedMap = nil end
    inv()
  end)
end)

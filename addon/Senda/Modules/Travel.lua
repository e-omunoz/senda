-- Senda / Modules / Travel
-- Planificador de viaje: cuando el destino de la flecha está en otro continente o a más de 800 yardas, calcula el
-- camino más rápido con lo que el personaje sabe y tiene (vuelos descubiertos, barcos, zepelines, el tranvía, portales,
-- teletransportes de clase, piedra de hogar) y lo enseña en una línea del HUD, con la flecha hacia el primer tramo.
-- En un maestro de vuelo marca en el mapa el nodo al que hay que volar (sin volar por ti).
--
--   Senda.Modules.Travel.HudLine() -> "Camino más rápido: vuela a X (3 min) → barco a Y → a pie" | nil
--   Senda.Modules.Travel.GetPlan() -> plan = { legs, secs, line, dest } | nil
--   Senda.Modules.Travel.Context() -> contexto del personaje (facción, clase, nodos conocidos, velocidad, hogar...)
--   Senda.Modules.Travel.PlanSync(ctx, inicio, destino) -> { secs, legs } | nil     (inicio/destino = { c, wx, wy })
--   Senda.Modules.Travel.HighlightTaxi() -> nº de nodos marcados en el mapa de vuelo abierto
--
-- Datos: Data/Travel.lua (generado desde data/travel por tools/build.py): cadenas compactas que se decodifican la
-- primera vez que hacen falta y fuera de combate. El Dijkstra corre en una corrutina por rebanadas (un máximo de
-- operaciones y de milisegundos por fotograma) y se pausa en combate. Sin pcall dentro de la corrutina (Lua 5.1 no
-- deja ceder a través de pcall).
--
-- Adaptado de Polestar (GPL-3.0-or-later, Portions Copyright (C) 2026 Polestar contributors), Nav/Travel.lua: el
-- modelo de costes (andar en línea recta x1,25 a 7 yd/s, despegue una vez por tramo de vuelo, esperas medias de
-- barcos, piedra de hogar y teletransportes solo desde la salida y con sus márgenes), la lectura de los nodos descubiertos
-- (RecordWorldTaxi) y de la posada vinculada (bindInn, onBound). Los datos y los horarios vienen, a través de Polestar, de
-- Shortest Path Forever (Portions Copyright (C) 2026 Cillian Berragan, GPL-3.0-or-later). El Dijkstra es el de la
-- comprobación de tools/gen_travel.py. Ver docs/TRAVEL.md y THIRD_PARTY.md.
local ADDON, Senda = ...
local M = Senda.Mod
if not M then return end
local L = M.L
local Compat, Events = Senda.Compat, Senda.Events

local T = {}
Senda.Modules.Travel = T

local format, floor, sqrt = string.format, math.floor, math.sqrt

local FAR_YARDS = 800        -- por encima de esta distancia (o en otro continente) se planifica
local NEAR_BOARD = 40        -- yardas: ya estás en el punto de embarque; no hace falta flecha
local SKIP_WALK = 15         -- yardas: un paseo más corto que esto no es un tramo del camino
local REPLAN_MOVED = 200     -- yardas que te alejas del punto donde se calculó: se calcula de nuevo
local REPLAN_AGE = 60        -- segundos de vida del plan
local REPLAN_MIN = 8         -- segundos mínimos entre dos cálculos (salvo cambio de destino)
local OPS_SLICE = 700        -- operaciones del Dijkstra por fotograma
local BUDGET_MS = 1.0        -- milisegundos por fotograma (la regla del addon es < 2 ms)
local TELE_LOAD = 5          -- segundos de pantalla de carga tras un teletransporte
local MOUNT_ITEM_CLASS, MOUNT_ITEM_SUB = 15, 5

local function Debug(...) M.Debug(...) end

------------------------------------------------------------------------------
-- Datos (decodificados bajo demanda)
------------------------------------------------------------------------------

local D -- tablas decodificadas

local function Split(s, sep)
  local t, n, i = {}, 0, 1
  while true do
    local j = s:find(sep, i, true)
    n = n + 1
    if not j then t[n] = s:sub(i); break end
    t[n] = s:sub(i, j - 1)
    i = j + 1
  end
  return t
end

-- "continente,wx,wy,mapa,x,y,zona" -> punto. wx es norte-sur y wy este-oeste (yardas de mundo).
local function Point(s, name)
  local f = Split(s, ",")
  return { c = tonumber(f[1]), wx = tonumber(f[2]), wy = tonumber(f[3]), map = tonumber(f[4]), x = tonumber(f[5]),
    y = tonumber(f[6]), area = tonumber(f[7]), name = name }
end

local function Lines(blob)
  local out = {}
  if type(blob) ~= "string" then return out end
  for line in blob:gmatch("[^\n]+") do out[#out + 1] = Split(line, "|") end
  return out
end

local function Decode(raw)
  local d = { k = raw.consts or {}, nodes = {}, nodeList = {}, flights = {}, rides = {}, portals = {}, inns = {},
    innByNpc = {}, innByName = {}, teleports = {}, maps = {} }
  for _, f in ipairs(Lines(raw.nodes)) do
    local p = Point(f[4], f[5])
    p.id, p.mask, p.class, p.fp = tonumber(f[1]), tonumber(f[2]), f[3] ~= "" and f[3] or nil, tonumber(f[1])
    d.nodes[p.id] = p
    d.nodeList[#d.nodeList + 1] = p
  end
  local seen = {}
  for _, p in ipairs(d.nodeList) do
    if p.map and not seen[p.map] then seen[p.map] = true; d.maps[#d.maps + 1] = p.map end
  end
  for _, f in ipairs(Lines(raw.flights)) do
    d.flights[#d.flights + 1] = { from = tonumber(f[1]), to = tonumber(f[2]), secs = tonumber(f[3]) }
  end
  for _, f in ipairs(Lines(raw.rides)) do
    local function End(pt, board, name)
      local p = Point(pt, name)
      if board ~= "" then
        local b = Split(board, ",")
        p.bwx, p.bwy = tonumber(b[1]), tonumber(b[2])
      end
      return p
    end
    d.rides[#d.rides + 1] = { id = f[1], kind = f[2], mask = tonumber(f[3]), abSecs = tonumber(f[4]), baSecs = tonumber(f[5]),
      waitA = tonumber(f[6]), waitB = tonumber(f[7]), extra = tonumber(f[8]), a = End(f[9], f[10], f[11]),
      b = End(f[12], f[13], f[14]) }
  end
  for _, f in ipairs(Lines(raw.portals)) do
    d.portals[#d.portals + 1] = { id = f[1], mask = tonumber(f[2]), secs = tonumber(f[3]), a = Point(f[4], f[5]),
      b = Point(f[6], f[7]) }
  end
  for _, f in ipairs(Lines(raw.inns)) do
    local inn = { area = tonumber(f[1]), npc = tonumber(f[2]), p = Point(f[3]), names = Split(f[4] or "", ";") }
    inn.p.name = inn.names[#inn.names]
    d.inns[#d.inns + 1] = inn
    d.innByNpc[inn.npc] = inn
    for _, n in ipairs(inn.names) do d.innByName[n:lower()] = inn end
  end
  for _, f in ipairs(Lines(raw.teleports)) do
    local reagents = {}
    if f[5] ~= "" then
      for _, r in ipairs(Split(f[5], ";")) do
        local item, count = r:match("^(%d+):(%d+)$")
        if item then reagents[#reagents + 1] = { item = tonumber(item), count = tonumber(count) } end
      end
    end
    d.teleports[#d.teleports + 1] = { spell = tonumber(f[1]), class = f[2], mask = tonumber(f[3]), cast = tonumber(f[4]),
      reagents = reagents, to = f[6] ~= "bind" and Point(f[6], f[7]) or "bind", name = f[7] }
  end
  return d
end

-- Los datos, o nil si el módulo de datos no está o aún no se pueden cargar (no se decodifica en combate).
function T.Data()
  if D then return D end
  local raw = Senda.TravelData
  if type(raw) ~= "table" or M.InCombat() then return nil end
  local ok, d = pcall(Decode, raw)
  if not ok then
    Senda:ReportError("Travel: datos ilegibles: " .. tostring(d))
    return nil
  end
  D = d
  return D
end

------------------------------------------------------------------------------
-- Datos guardados del personaje
------------------------------------------------------------------------------

-- SendaDB.char.travel = { taxi = { [nodo] = true }, names = { [nodo] = nombre del cliente }, inn = { [lugar en minúsculas] = pnj } }
local scratch = { taxi = {}, names = {}, inn = {} }
local function Store()
  local db = Senda.db
  if type(db) ~= "table" or type(db.char) ~= "table" then return scratch end
  local t = db.char.travel
  if type(t) ~= "table" then t = {}; db.char.travel = t end
  t.taxi = type(t.taxi) == "table" and t.taxi or {}
  t.names = type(t.names) == "table" and t.names or {}
  t.inn = type(t.inn) == "table" and t.inn or {}
  return t
end

-- Nodos de vuelo conocidos: los del mapa del mundo (Store) y los que el motor guarda al abrir un maestro de vuelo.
function T.KnownNodes()
  local known = {}
  for id in pairs(Store().taxi) do known[id] = true end
  local fps = Senda.db and Senda.db.char and Senda.db.char.fps
  if type(fps) == "table" then
    for id in pairs(fps) do
      if type(id) == "number" then known[id] = true end
    end
  end
  return known
end

------------------------------------------------------------------------------
-- Nombres de lugares
------------------------------------------------------------------------------

local function FirstPart(name) return (name:match("^([^,]+)")) or name end

-- Nombre de un punto en el idioma del cliente: el del nodo de vuelo (como lo da el cliente), el de la zona
-- (AreaTable) o, si no, el del dato (en inglés).
function T.PlaceName(p)
  if not p then return "?" end
  if p.fp then
    local fps = Senda.db and Senda.db.char and Senda.db.char.fps
    local n = Store().names[p.fp] or (type(fps) == "table" and fps[p.fp])
    if type(n) == "string" and n ~= "" then return FirstPart(n) end
  end
  if p.area then
    local n = Compat.AreaName(p.area)
    if n and n ~= "" then return n end
  end
  return p.name and FirstPart(p.name) or "?"
end

------------------------------------------------------------------------------
-- Piedra de hogar: dónde está vinculada
------------------------------------------------------------------------------

local bindCache -- { loc, inn }

local function DoneSethearthInn()
  -- Último paso «sethearth» hecho de la guía activa con un posadero conocido.
  local E = Senda.Engine
  if not (E and E.Steps and E.GuideId and Senda.GuideProgress) then return nil end
  local gid = E:GuideId()
  local prog = gid and Senda:GuideProgress(gid)
  if not prog then return nil end
  local found
  for _, e in ipairs(E:Steps() or {}) do
    local st = e.step
    if st and st["do"] == "sethearth" and st.npc and prog.done[st.id] and D.innByNpc[st.npc] then found = D.innByNpc[st.npc] end
  end
  return found
end

-- La posada donde está vinculada la piedra, o nil: la que se aprendió al vincular (posadero o posada más cercana), la
-- que el cliente llama así en su idioma (AreaTable), la de ese nombre en inglés y, por último, el último paso «sethearth»
-- hecho de la guía. Adaptado de Polestar, Nav/Travel.lua (bindInn).
function T.BoundInn()
  local data = T.Data()
  if not data then return nil end
  local loc = Compat.BindLocation()
  if not loc or loc == "" then return nil end
  local key = loc:lower()
  if bindCache and bindCache.loc == key then return bindCache.inn, loc end
  local inn
  local npc = Store().inn[key]
  if npc then inn = data.innByNpc[npc] end
  if not inn then
    for _, candidate in ipairs(data.inns) do
      local name = Compat.AreaName(candidate.area)
      if name and name:lower() == key then inn = candidate; break end
    end
  end
  inn = inn or data.innByName[key] or DoneSethearthInn()
  bindCache = { loc = key, inn = inn }
  return inn, loc
end

local function Dist(ax, ay, bx, by)
  local dx, dy = ax - bx, ay - by
  return sqrt(dx * dx + dy * dy)
end

local function OnBound()
  local data = T.Data()
  if not data then return end
  local function Learn()
    local loc = Compat.BindLocation()
    if not loc or loc == "" then return false end
    local inn
    -- 1. el posadero con el que se vinculó (paso de la guía o unidad «npc»)
    local E = Senda.Engine
    local step = E and E.CurrentStep and E:CurrentStep()
    if step and step["do"] == "sethearth" and step.npc then inn = data.innByNpc[step.npc] end
    if not inn then
      local npc = Compat.UnitNpcId("npc")
      inn = npc and data.innByNpc[npc]
    end
    -- 2. la posada más cercana a donde estás (a menos de 60 yardas)
    if not inn then
      local pc, pn, pw = Compat.PlayerWorldPos()
      if pc then
        local best = 60
        for _, candidate in ipairs(data.inns) do
          if candidate.p.c == pc then
            local d = Dist(pn, pw, candidate.p.wx, candidate.p.wy)
            if d <= best then best, inn = d, candidate end
          end
        end
      end
    end
    if inn then
      Store().inn[loc:lower()] = inn.npc
      bindCache = nil
      T.MarkDirty("bind")
      return true
    end
    return false
  end
  bindCache = nil
  if not Learn() then M.After(0.6, function() Learn() end) end
  T.MarkDirty("bind")
end

------------------------------------------------------------------------------
-- Velocidad al andar
------------------------------------------------------------------------------

local SPELL_DREADSTEED, SPELL_FELSTEED, SPELL_TRAVEL_FORM = 23161, 5784, 783
local mountItems = {}

local function HasMountItem()
  for _, it in ipairs(M.ScanBags()) do
    local known = mountItems[it.id]
    if known == nil then
      local _, _, class, sub = M.ItemInstant(it.id)
      known = (class == MOUNT_ITEM_CLASS and sub == MOUNT_ITEM_SUB) and true or false
      mountItems[it.id] = known
    end
    if known then return true end
  end
  return false
end

-- Factor sobre la carrera base (7 yd/s): corcel de Brujo (60 % / 100 %), forma de viaje (+40 %) o una montura en las
-- bolsas a partir del nivel 40 (60 %). Sin nada de eso, 1.
function T.SpeedFactor()
  if Compat.IsSpellKnown(SPELL_DREADSTEED) then return 2.0 end
  if Compat.IsSpellKnown(SPELL_FELSTEED) then return 1.6 end
  local f = 1
  if Compat.PlayerLevel() >= 40 and HasMountItem() then f = 1.6 end
  if f < 1.4 and Compat.IsSpellKnown(SPELL_TRAVEL_FORM) then f = 1.4 end
  return f
end

------------------------------------------------------------------------------
-- Contexto del personaje
------------------------------------------------------------------------------

local function UsableTeleports(data, mask, class, bind)
  local out = {}
  for _, t in ipairs(data.teleports) do
    if (t.mask == 3 or t.mask == mask) and t.class == class and Compat.IsSpellKnown(t.spell) then
      local ok = (t.to ~= "bind") or bind ~= nil
      for _, r in ipairs(t.reagents) do
        if Compat.ItemCount(r.item) < r.count then ok = false end
      end
      if ok then
        out[#out + 1] = { spell = t.spell, name = t.name, cast = t.cast, to = (t.to == "bind") and bind or t.to,
          wait = Compat.SpellCooldownLeft(t.spell) }
      end
    end
  end
  return out
end

-- Lo que el planificador necesita saber del personaje.
function T.Context()
  local data = T.Data()
  if not data then return nil end
  local faction = Compat.PlayerFaction()
  local mask = (faction == "Alliance" and 1) or (faction == "Horde" and 2) or nil
  if not mask then return nil end
  local class = Compat.PlayerClass()
  local ctx = { mask = mask, class = class, known = T.KnownNodes(), speed = T.SpeedFactor() }
  local inn = T.BoundInn()
  ctx.bind = inn and inn.p or nil
  if ctx.bind and Compat.ItemCount(data.k.hearthItem or 6948) > 0 then
    ctx.hearthWait = Compat.ItemCooldownLeft(data.k.hearthItem or 6948)
  end
  ctx.teleports = UsableTeleports(data, mask, class, ctx.bind)
  return ctx
end

------------------------------------------------------------------------------
-- Dijkstra
------------------------------------------------------------------------------

-- Cesión por rebanadas: solo dentro de la corrutina del trabajo (Pump). En PlanSync no cede nunca.
local sliced, ops, sliceStart = false, 0, 0
local function Tick()
  if not sliced then return end
  ops = ops + 1
  if ops >= OPS_SLICE or (ops % 64 == 0 and (debugprofilestop() - sliceStart) > BUDGET_MS) then
    coroutine.yield()
  end
end

local function HeapPush(h, key, val)
  local n = h.n + 1
  h.n = n
  local k, v = h.k, h.v
  local i = n
  while i > 1 do
    local p = floor(i / 2)
    if k[p] <= key then break end
    k[i], v[i] = k[p], v[p]
    i = p
  end
  k[i], v[i] = key, val
end

local function HeapPop(h)
  local n = h.n
  local k, v = h.k, h.v
  local topK, topV = k[1], v[1]
  local lastK, lastV = k[n], v[n]
  k[n], v[n] = nil, nil
  n = n - 1
  h.n = n
  if n > 0 then
    local i = 1
    while true do
      local c = i * 2
      if c > n then break end
      if c < n and k[c + 1] < k[c] then c = c + 1 end
      if k[c] >= lastK then break end
      k[i], v[i] = k[c], v[c]
      i = c
    end
    k[i], v[i] = lastK, lastV
  end
  return topK, topV
end

-- Grafo de un cálculo. `mode`: nil (solo con los pies, vuelos y transportes), "hearth" (añade la piedra de hogar) o
-- "tele" (añade los teletransportes de clase). start / target = { c, wx, wy }.
local function BuildGraph(data, ctx, start, target, mode)
  local g = { n = 0, c = {}, x = {}, y = {}, info = {}, edges = {}, byFp = {} }
  local function add(c, wx, wy, info)
    local i = g.n + 1
    g.n = i
    g.c[i], g.x[i], g.y[i], g.info[i], g.edges[i] = c, wx, wy, info, {}
    return i
  end
  local function link(a, b, secs, how, ref, extra)
    local e = g.edges[a]
    e[#e + 1] = { b, secs, how, ref, extra }
  end
  g.start = add(start.c, start.wx, start.wy, { kind = "start", p = start })
  g.target = add(target.c, target.wx, target.wy, { kind = "target", p = target })
  local known = ctx.known or {}
  for _, p in ipairs(data.nodeList) do
    if (p.mask == 3 or p.mask == ctx.mask) and known[p.id] and (not p.class or p.class == ctx.class) then
      g.byFp[p.id] = add(p.c, p.wx, p.wy, { kind = "fp", p = p, id = p.id })
    end
  end
  local k = data.k
  for _, f in ipairs(data.flights) do
    local a, b = g.byFp[f.from], g.byFp[f.to]
    if a and b then link(a, b, f.secs, "fly", f) end
  end
  for _, r in ipairs(data.rides) do
    if (r.mask == 3 or r.mask == ctx.mask) and not (ctx.noRide and ctx.noRide[r.id]) then
      local pa, pb = r.a, r.b
      local a = add(pa.c, pa.bwx or pa.wx, pa.bwy or pa.wy, { kind = "dock", p = pa, ride = r })
      local b = add(pb.c, pb.bwx or pb.wx, pb.bwy or pb.wy, { kind = "dock", p = pb, ride = r })
      link(a, b, r.waitA + r.abSecs + r.extra, "ride", r)
      link(b, a, r.waitB + r.baSecs + r.extra, "ride", r)
    end
  end
  for _, p in ipairs(data.portals) do
    if p.mask == 3 or p.mask == ctx.mask then
      local a = add(p.a.c, p.a.wx, p.a.wy, { kind = "portal", p = p.a, portal = p })
      local b = add(p.b.c, p.b.wx, p.b.wy, { kind = "portal", p = p.b, portal = p })
      link(a, b, p.secs, "portal", p)
    end
  end
  if mode == "hearth" and ctx.bind and ctx.hearthWait then
    local b = add(ctx.bind.c, ctx.bind.wx, ctx.bind.wy, { kind = "bind", p = ctx.bind })
    link(g.start, b, (k.hearthSecs or 15) + ctx.hearthWait, "hearth", nil)
  elseif mode == "tele" then
    for _, t in ipairs(ctx.teleports or {}) do
      local to = t.to
      if to then
        local b = add(to.c, to.wx, to.wy, { kind = "tele", p = to, tele = t })
        link(g.start, b, t.cast + TELE_LOAD + (t.wait or 0), "teleport", t)
      end
    end
  end
  return g
end

-- Dijkstra con estado (nodo, ¿llegado volando?) para cobrar el despegue una vez por tramo de vuelo.
-- Devuelve { secs, legs } o nil. `sp` = factor de velocidad al andar.
local function Dijkstra(data, g, ctx)
  local k = data.k
  local walkSecsPerYard = (k.detour or 1.25) / ((k.run or 7) * (ctx.speed or 1))
  local takeOff = k.takeOff or 4
  local n = g.n
  local dist, prev = {}, {}
  local heap = { n = 0, k = {}, v = {} }
  local s0 = g.start * 2
  dist[s0] = 0
  HeapPush(heap, 0, s0)
  local targetState
  local C, X, Y = g.c, g.x, g.y
  while heap.n > 0 do
    local d, st = HeapPop(heap)
    if d <= (dist[st] or 1e18) then
      local u = floor(st / 2)
      local byFly = st - u * 2 == 1
      if u == g.target then targetState = st; break end
      Tick()
      for _, e in ipairs(g.edges[u]) do
        local v, secs, how = e[1], e[2], e[3]
        local extra = (how == "fly" and not byFly) and takeOff or 0
        local nd = d + secs + extra
        local vs = v * 2 + (how == "fly" and 1 or 0)
        if nd < (dist[vs] or 1e18) then
          dist[vs] = nd
          prev[vs] = { st, how, e[4], secs + extra, e[5] }
          HeapPush(heap, nd, vs)
        end
      end
      -- a pie, en línea recta, a cualquier punto del mismo continente
      local cu = C[u]
      if cu == 0 or cu == 1 then
        local ux, uy = X[u], Y[u]
        for v = 1, n do
          if v ~= u and v ~= g.start and C[v] == cu then
            local nd = d + Dist(ux, uy, X[v], Y[v]) * walkSecsPerYard
            local vs = v * 2
            if nd < (dist[vs] or 1e18) then
              dist[vs] = nd
              prev[vs] = { st, "walk", nil, nd - d, nil }
              HeapPush(heap, nd, vs)
            end
            Tick()
          end
        end
      end
    end
  end
  if not targetState then return nil end
  local raw, st = {}, targetState
  while prev[st] do
    local p = prev[st]
    raw[#raw + 1] = { how = p[2], ref = p[3], secs = p[4], from = floor(p[1] / 2), to = floor(st / 2) }
    st = p[1]
  end
  -- orden de salida a destino
  local legs = {}
  for i = #raw, 1, -1 do
    local r = raw[i]
    local fromInfo, toInfo = g.info[r.from], g.info[r.to]
    local last = legs[#legs]
    if r.how == "fly" and last and last.how == "fly" then
      -- varios saltos seguidos = un solo vuelo con paradas
      last.secs = last.secs + r.secs
      last.to, last.toId = toInfo.p, toInfo.id
      last.nodes[#last.nodes + 1] = toInfo.id
    else
      local leg = { how = r.how, secs = r.secs, from = fromInfo.p, to = toInfo.p }
      if r.how == "walk" then
        leg.yards = Dist(g.x[r.from], g.y[r.from], g.x[r.to], g.y[r.to])
      elseif r.how == "fly" then
        leg.fromId, leg.toId, leg.nodes = fromInfo.id, toInfo.id, { fromInfo.id, toInfo.id }
      elseif r.how == "ride" then
        leg.id, leg.kind = r.ref.id, r.ref.kind
      elseif r.how == "portal" then
        leg.id = r.ref.id
      elseif r.how == "teleport" then
        leg.spell, leg.name = r.ref.spell, r.ref.name
      end
      legs[#legs + 1] = leg
    end
  end
  -- un paseo de unas yardas (ya estás en el maestro de vuelo, en el muelle) no es un tramo
  local trimmed = {}
  for _, leg in ipairs(legs) do
    if not (leg.how == "walk" and leg.yards < SKIP_WALK) or #legs == 1 then trimmed[#trimmed + 1] = leg end
  end
  return { secs = dist[targetState], legs = trimmed }
end

local function Uses(plan, how)
  for _, leg in ipairs(plan.legs) do
    if leg.how == how then return true end
  end
  return false
end

-- Cuerpo del cálculo: sin vuelos ni transportes especiales (A), con la piedra de hogar (H) y con teletransportes (T);
-- gana el más rápido que cumpla sus márgenes. Es la función que ejecuta la corrutina.
local function Compute(data, ctx, start, target)
  local k = data.k
  local A = Dijkstra(data, BuildGraph(data, ctx, start, target, nil), ctx)
  local best = A
  if ctx.bind and ctx.hearthWait then
    local H = Dijkstra(data, BuildGraph(data, ctx, start, target, "hearth"), ctx)
    -- la piedra solo si el viaje sin ella dura al menos 3 min y ahorra al menos 2 min
    if H and Uses(H, "hearth") and (not A or (A.secs >= (k.hearthMinTrip or 180) and A.secs - H.secs >= (k.hearthMargin or 120))) then
      if not best or H.secs < best.secs then best = H end
    end
  end
  if ctx.teleports and #ctx.teleports > 0 then
    local Tl = Dijkstra(data, BuildGraph(data, ctx, start, target, "tele"), ctx)
    -- un teletransporte solo si ahorra 60 s o el 20 %
    if Tl and Uses(Tl, "teleport") and (not A or A.secs - Tl.secs >= math.max(k.teleMargin or 60, (k.teleShare or 0.2) * A.secs)) then
      if not best or Tl.secs < best.secs then best = Tl end
    end
  end
  return best or false
end

-- Cálculo síncrono (pruebas y /senda viaje): no cede.
function T.PlanSync(ctx, start, target)
  local data = T.Data()
  if not data or not ctx then return nil end
  local was = sliced
  sliced = false
  local res = Compute(data, ctx, start, target)
  sliced = was
  return res or nil
end

------------------------------------------------------------------------------
-- Texto del camino
------------------------------------------------------------------------------

local function Dur(secs)
  secs = secs or 0
  if secs < 90 then return format(L.TRAVEL_SECS or "%d s", floor(secs + 0.5)) end
  return format(L.TRAVEL_MINS or "%d min", floor(secs / 60 + 0.5))
end
T.Duration = Dur

local RIDE_FMT = { boat = "TRAVEL_BOAT", zeppelin = "TRAVEL_ZEPPELIN", tram = "TRAVEL_TRAM" }
local RIDE_DEFAULT = { TRAVEL_BOAT = "barco a %s", TRAVEL_ZEPPELIN = "zepelín a %s", TRAVEL_TRAM = "tranvía a %s" }

local BOARD_FMT = { fly = "TRAVEL_GO_FLY", boat = "TRAVEL_GO_BOAT", zeppelin = "TRAVEL_GO_ZEPPELIN",
  tram = "TRAVEL_GO_TRAM", portal = "TRAVEL_GO_PORTAL" }

-- Trozos del camino, uno por tramo que no sea «andar» (más «ve a X» al principio y «a pie» al final).
function T.Pieces(legs)
  local pieces = {}
  for i, leg in ipairs(legs) do
    local to = T.PlaceName(leg.to)
    if leg.how == "walk" then
      if i == #legs then
        if leg.secs >= 15 then pieces[#pieces + 1] = L.TRAVEL_WALK or "a pie" end
      elseif i == 1 and (leg.yards or 0) > NEAR_BOARD then
        -- «ve al tranvía de Ventormenta», no «ve a Ventormenta» (puede que ya estés en la ciudad)
        local nx = legs[2]
        local key = nx and (BOARD_FMT[nx.how == "ride" and nx.kind or nx.how]) or nil
        pieces[#pieces + 1] = format((key and L[key]) or L.TRAVEL_GO or "ve a %s", to)
      end
    elseif leg.how == "fly" then
      pieces[#pieces + 1] = format(L.TRAVEL_FLY or "vuela a %s", to) .. " (" .. Dur(leg.secs) .. ")"
    elseif leg.how == "ride" then
      local key = RIDE_FMT[leg.kind] or "TRAVEL_BOAT"
      pieces[#pieces + 1] = format(L[key] or RIDE_DEFAULT[key], to) .. " (" .. Dur(leg.secs) .. ")"
    elseif leg.how == "portal" then
      pieces[#pieces + 1] = format(L.TRAVEL_PORTAL or "portal a %s", to)
    elseif leg.how == "hearth" then
      pieces[#pieces + 1] = format(L.TRAVEL_HEARTH or "piedra de hogar a %s", to)
    elseif leg.how == "teleport" then
      pieces[#pieces + 1] = M.SpellName(leg.spell) or leg.name or "?"
    end
  end
  return pieces
end

local function PlanLine(plan)
  local pieces = T.Pieces(plan.legs)
  if #pieces == 0 then return nil end
  return format(L.TRAVEL_LINE or "Camino más rápido: %s", table.concat(pieces, L.TRAVEL_SEP or " » "))
end

-- ¿El camino es solo andar? (entonces no se enseña nada: la flecha ya apunta al destino)
local function WalkOnly(plan)
  for _, leg in ipairs(plan.legs) do
    if leg.how ~= "walk" then return false end
  end
  return true
end

------------------------------------------------------------------------------
-- Plan actual, trabajo en rebanadas y flecha
------------------------------------------------------------------------------

local plan          -- { dest, legs, secs, line, aim, kind, origin = {c, wx, wy}, t } | { dest, none = true }
local job           -- { co, cb, dest }
local pumpFrame
local dirty, lastStart = true, -1000
local dismissedDest
local pendingHighlight = false
local scanning, scannedOnce = false, false -- lectura de los nodos descubiertos (ScanTaxi)

local function Now() return (GetTime and GetTime()) or 0 end

local function Fire() Events:Fire("SENDA_TRAVEL_UPDATED") end

function T.GetPlan() return plan end

function T.HudLine()
  if not plan then return nil end
  if plan.none then return L.TRAVEL_NONE or "No conozco un camino hasta allí con los vuelos que tienes." end
  return plan.line
end

function T.MarkDirty(reason)
  dirty = true
  Debug("Viaje: recalcular (%s)", tostring(reason))
end

local function ClearArrow()
  if Senda.Arrow and Senda.Arrow.Has and Senda.Arrow:Has("travel") then Senda.Arrow:Clear("travel") end
end

local function ClearPlan()
  if plan or job then
    plan, job = nil, nil
    ClearArrow()
    Fire()
  end
end

-- Hacia dónde apunta la flecha: el punto de embarque del primer tramo (o el final del paseo hasta él). nil: ninguno.
local function Aim(legs)
  local first = legs[1]
  if not first then return nil end
  if first.how == "walk" then return legs[2] and first.to or nil end
  if first.how == "fly" or first.how == "ride" or first.how == "portal" then return first.from end
  return nil
end

local ARROW_KEY = { fly = "TRAVEL_ARROW_FLY", boat = "TRAVEL_ARROW_BOAT", zeppelin = "TRAVEL_ARROW_ZEPPELIN",
  tram = "TRAVEL_ARROW_TRAM", portal = "TRAVEL_ARROW_PORTAL" }
local ARROW_DEFAULT = { TRAVEL_ARROW_FLY = "Maestro de vuelo: %s", TRAVEL_ARROW_BOAT = "Muelle: %s",
  TRAVEL_ARROW_ZEPPELIN = "Zepelín: %s", TRAVEL_ARROW_TRAM = "Tranvía: %s", TRAVEL_ARROW_PORTAL = "Portal: %s" }

local function ArrowLabel(legs)
  local nextLeg = legs[1].how == "walk" and legs[2] or legs[1]
  local key = ARROW_KEY[nextLeg.how == "ride" and nextLeg.kind or nextLeg.how] or "TRAVEL_ARROW_FLY"
  return format(L[key] or ARROW_DEFAULT[key], T.PlaceName(nextLeg.from))
end

local function ApplyArrow()
  local A = Senda.Arrow
  if not (A and plan and plan.legs and plan.dest) then return end
  if dismissedDest == plan.dest then return end
  local aim = Aim(plan.legs)
  local pc, pn, pw = Compat.PlayerWorldPos()
  local wn, ww = aim and (aim.bwx or aim.wx), aim and (aim.bwy or aim.wy) -- el muelle: donde atraca el barco
  local arrived = aim and pc == aim.c and Dist(pn, pw, wn, ww) <= NEAR_BOARD
  if not aim or arrived or not aim.map or not aim.x then
    ClearArrow()
    return
  end
  if A:Has("travel") then return end
  A:SetTarget(aim.map, aim.x, aim.y, ArrowLabel(plan.legs), "travel",
    { continent = aim.c, wn = wn, ww = ww, radius = NEAR_BOARD })
end

------------------------------------------------------------------------------
-- Mapa de vuelo: marcar el nodo destino
------------------------------------------------------------------------------

-- Resplandor por botón en una tabla propia (claves débiles): no se escriben campos en los marcos de Blizzard,
-- así no se ensucia (taint) su tabla.
local glows = setmetatable({}, { __mode = "k" })
local function Glow(pin, on)
  if not pin then return end
  local tex = glows[pin]
  if on and not tex and pin.CreateTexture then
    tex = pin:CreateTexture(nil, "OVERLAY")
    tex:SetTexture("Interface\\Buttons\\UI-ActionButton-Border")
    tex:SetBlendMode("ADD")
    tex:SetPoint("CENTER", pin, "CENTER", 0, 0)
    tex:SetSize(64, 64)
    glows[pin] = tex
  end
  if tex then tex:SetShown(on and true or false) end
end
-- ¿Está marcado este botón del mapa de vuelo? (para las pruebas)
function T.Glowing(pin) return glows[pin] ~= nil and glows[pin]:IsShown() end

-- Nodo (id) al que lleva el primer vuelo del camino, o nil.
function T.NextFlightNode()
  if not (plan and plan.legs) then return nil end
  for i, leg in ipairs(plan.legs) do
    if leg.how == "fly" then return leg.toId, leg.to end
    if i > 1 or leg.how ~= "walk" then break end
  end
  return nil
end

-- Marca en el mapa de vuelo abierto el nodo al que hay que volar (con un resplandor en su botón); no vuela por ti.
-- Mapa moderno (FlightMapFrame: botones con taxiNodeData.nodeID) y el marco clásico (TaxiButtonN, por nombre).
function T.HighlightTaxi()
  local id, point = T.NextFlightNode()
  local marked = 0
  local function Each(fn)
    local FM = _G.FlightMapFrame
    if FM and FM.EnumeratePinsByTemplate and (not FM.IsShown or FM:IsShown()) then
      local ok, iter, a, b = pcall(FM.EnumeratePinsByTemplate, FM, "FlightMap_FlightPointPinTemplate")
      if ok and type(iter) == "function" then
        for pin in iter, a, b do fn(pin, pin.taxiNodeData and pin.taxiNodeData.nodeID, pin.taxiNodeData and pin.taxiNodeData.name) end
      end
    end
    local TF = _G.TaxiFrame
    if TF and TF.IsShown and TF:IsShown() and _G.NumTaxiNodes and _G.TaxiNodeName then
      local n = tonumber(_G.NumTaxiNodes()) or 0
      for i = 1, n do
        local pin = _G["TaxiButton" .. i]
        if pin then fn(pin, nil, _G.TaxiNodeName(i)) end
      end
    end
  end
  local target = point and (T.PlaceName(point)):lower()
  Each(function(pin, nodeId, name)
    local hit = false
    if id then
      if nodeId then
        hit = nodeId == id
      elseif type(name) == "string" and target then
        hit = FirstPart(name):lower() == target
      end
    end
    Glow(pin, hit)
    if hit then marked = marked + 1 end
  end)
  if marked > 0 and T.hinted ~= id then
    T.hinted = id
    M.Print(format(L.TRAVEL_TAXI_HINT or "Sigue por %s: lo he marcado en el mapa de vuelos.", T.PlaceName(point)))
  end
  return marked
end

local function TryHighlight()
  if not pendingHighlight then return end
  if plan and plan.legs and not job and plan.t and Now() - plan.t < 20 then
    local ok = T.HighlightTaxi()
    if ok and ok > 0 then pendingHighlight = false end
  end
end

------------------------------------------------------------------------------
-- Trabajo en rebanadas
------------------------------------------------------------------------------

local function StopPump()
  if pumpFrame then pumpFrame:SetScript("OnUpdate", nil) end
end

local function Pump()
  if not job then StopPump(); return end
  if M.InCombat() then return end
  ops, sliceStart, sliced = 0, debugprofilestop(), true
  job.frames = (job.frames or 0) + 1
  local ok, res = coroutine.resume(job.co)
  sliced = false
  if ops > T.maxSliceOps then T.maxSliceOps = ops end
  if not ok then
    job = nil
    StopPump()
    Senda:ReportError("Travel: " .. tostring(res))
    return
  end
  if coroutine.status(job.co) == "dead" then
    local j = job
    job = nil
    StopPump()
    T.lastJobFrames = j.frames
    j.cb(res)
  end
end

local function StartJob(fn, cb, dest)
  job = { co = coroutine.create(fn), cb = cb, dest = dest }
  pumpFrame = pumpFrame or CreateFrame("Frame")
  pumpFrame:SetScript("OnUpdate", Pump)
end

-- Fotogramas que tardó el último cálculo y máximo de operaciones en una rebanada (para las pruebas).
T.lastJobFrames, T.maxSliceOps = 0, 0

local function OnComputed(res, dest, start)
  local cur = Senda.Arrow and Senda.Arrow:Destination()
  if cur ~= dest then
    dirty = true -- el destino cambió mientras se calculaba
    return
  end
  if not res then
    plan = { dest = dest, none = true, t = Now(), origin = start }
    ClearArrow()
    Fire()
    return
  end
  if WalkOnly(res) then
    plan = { dest = dest, walkOnly = true, secs = res.secs, legs = res.legs, t = Now(), origin = start }
    ClearArrow()
    Fire()
    return
  end
  plan = { dest = dest, legs = res.legs, secs = res.secs, t = Now(), origin = start }
  plan.line = PlanLine(plan)
  ApplyArrow()
  Fire()
  TryHighlight()
end

local function Distance(c1, x1, y1, c2, x2, y2)
  if c1 ~= c2 then return math.huge end
  return Dist(x1, y1, x2, y2)
end

-- Mira si hace falta (volver a) calcular y lanza el trabajo. `force` ignora el tiempo mínimo entre cálculos.
function T.Refresh(force)
  if M.Opt("mod_travel") == false then ClearPlan(); return end
  if M.InCombat() or not Senda.Arrow then return end
  if Compat.OnTaxi() then return end -- volando: el camino ya está en marcha
  local dest, src = Senda.Arrow:Destination()
  if not dest or (src ~= "guide" and src ~= "manual" and src ~= "trainer" and src ~= "dungeon") or not dest.continent then ClearPlan(); return end
  local pc, pn, pw = Compat.PlayerWorldPos()
  if not pc or Compat.IsDead() then ClearPlan(); return end
  -- solo Reinos del Este (0) y Kalimdor (1): el continente nuevo de Forever no tiene yardas fiables
  if (pc ~= 0 and pc ~= 1) or (dest.continent ~= 0 and dest.continent ~= 1) then ClearPlan(); return end
  local far = pc ~= dest.continent or Distance(pc, pn, pw, dest.continent, dest.wn, dest.ww) > FAR_YARDS
  if not far then ClearPlan(); return end
  if not scannedOnce then T.ScanTaxi() end -- la primera vez que hace falta: qué vuelos has descubierto
  if plan and plan.dest == dest then ApplyArrow() end
  if plan and plan.dest == dest and not dirty and plan.t then
    -- plan vigente: se vuelve a calcular si te has alejado o ha envejecido
    local o = plan.origin
    local moved = Distance(pc, pn, pw, o.c, o.wx, o.wy)
    if moved <= REPLAN_MOVED and Now() - plan.t <= REPLAN_AGE then ApplyArrow(); return end
  end
  if job then return end
  -- el movimiento no recalcula más a menudo que REPLAN_MIN; un cambio de lo que sabes o llevas (dirty) sí
  if not force and not dirty and plan and plan.dest == dest and Now() - lastStart < REPLAN_MIN then return end
  local data = T.Data()
  if not data then return end
  local ctx = T.Context()
  if not ctx then return end
  dirty = false
  lastStart = Now()
  local start = { c = pc, wx = pn, wy = pw }
  local target = { c = dest.continent, wx = dest.wn, wy = dest.ww, map = dest.map, x = dest.x * 100, y = dest.y * 100 }
  StartJob(function() return Compute(data, ctx, start, target) end, function(res)
    OnComputed(res, dest, start)
  end, dest)
end

------------------------------------------------------------------------------
-- Descubrimiento de nodos de vuelo (sin abrir el maestro de vuelo)
------------------------------------------------------------------------------


-- Lee, mapa a mapa y de pocos en pocos, los nodos que el cliente da por descubiertos.
function T.ScanTaxi()
  local data = T.Data()
  if not data or scanning or M.InCombat() then return end
  scanning, scannedOnce = true, true
  local i, found, any = 1, {}, false
  local function Step()
    if M.InCombat() then scanning = false; return end
    for _ = 1, 4 do
      local map = data.maps[i]
      if not map then break end
      i = i + 1
      local list, und = Compat.DiscoveredTaxiOn(map)
      if und then any = true end
      for _, n in ipairs(list) do found[#found + 1] = n end
    end
    if data.maps[i] then M.After(0.05, Step); return end
    scanning = false
    -- un cliente que no marca ningún nodo como no descubierto no es de fiar: todo personaje tiene alguno
    if not any then return end
    local st, added = Store(), false
    for _, n in ipairs(found) do
      if data.nodes[n.id] then
        if not st.taxi[n.id] then st.taxi[n.id] = true; added = true end
        if n.name then st.names[n.id] = n.name end
      end
    end
    if added then T.MarkDirty("taxi") end
  end
  Step()
end

------------------------------------------------------------------------------
-- Comando, opciones y eventos
------------------------------------------------------------------------------

local function Slash(rest, args)
  local sub = (args and args[2] or ""):lower()
  if sub == "help" or sub == "ayuda" then
    M.Print(L.TRAVEL_SLASH_USAGE or "Uso: /senda viaje")
    return
  end
  local p = T.GetPlan()
  if sub == "recalcular" or sub == "refresh" then
    T.MarkDirty("slash")
    T.Refresh(true)
    M.Print(L.TRAVEL_SLASH_REFRESH or "Calculando el camino de nuevo.")
    return
  end
  if not p then
    M.Print(L.TRAVEL_SLASH_NOPLAN or "No hace falta ningún camino: el destino está cerca.")
    return
  end
  if p.none then M.Print(L.TRAVEL_NONE or "No conozco un camino hasta allí."); return end
  if p.walkOnly then M.Print(L.TRAVEL_SLASH_WALK or "Lo más rápido es ir a pie."); return end
  M.Print(format(L.TRAVEL_SLASH_TOTAL or "Camino más rápido: unos %s en total.", Dur(p.secs)))
  for i, piece in ipairs(T.Pieces(p.legs)) do M.Print("  %d. %s", i, piece) end
end

M.RegisterOption({ key = "mod_travel", label = L.OPT_TRAVEL or "Planificador de viaje", tooltip = L.OPT_TRAVEL_TIP, type = "toggle",
  default = true, onChange = function() dirty = true; T.Refresh(true) end })

M.OnReady(function()
  if Senda.Slash and Senda.Slash.Register then
    Senda.Slash:Register("viaje", Slash, L.TRAVEL_SLASH_HELP or "el camino más rápido al destino de la flecha")
  end
  Compat.NewTicker(2, function() T.Refresh(false) end)
end)

M.On("SENDA_ARROW_DEST", function(_, dest)
  if dismissedDest and dismissedDest ~= dest then dismissedDest = nil end
  dirty = true
  M.Debounce("travel-dest", 0.3, function() T.Refresh(true) end)
end)
M.On("SENDA_ARROW_DISMISSED", function(_, source)
  if source == "travel" and plan then dismissedDest = plan.dest end
end)
M.On("HEARTHSTONE_BOUND", OnBound)
M.On("NEW_TAXI_PATH", function() if D then M.After(1, function() T.ScanTaxi() end) end end)
M.On("TAXIMAP_OPENED", function()
  pendingHighlight = true
  T.hinted = nil
  dirty = true
  M.After(0.15, function()
    T.Refresh(true)
    TryHighlight()
  end)
  M.After(0.8, TryHighlight)
end)
M.On("SPELLS_CHANGED", function() dirty = true end)
M.On("BAG_UPDATE_DELAYED", function() dirty = true end)
M.On("PLAYER_ENTERING_WORLD", function() bindCache = nil end)
M.On("PLAYER_REGEN_ENABLED", function() M.After(0.5, function() T.Refresh(false) end) end)
M.On("SENDA_STEP_CHANGED", function() dirty = true end)

-- Senda / Modules / Gathering
-- Recolección y pesca en la pestaña Profesiones (solo lectura): en qué zonas de TU guía sigue subiendo cada
-- profesión que has aprendido, aviso cuando la zona se queda atrás (nodos en rojo) o te queda pequeña (todo gris),
-- mejor zona para tu habilidad y siguiente rango con su instructor.
-- Datos (los genera tools/gen_gathering.py, docs/PROFESSIONS.md «Recolección»), de las páginas de conocimiento:
--   kind = "professions": [[zone]] prof, map, side, levels, at = {map, x, y}, nodes = {{objeto, habilidad mínima, nodos}},
--                         full (pesca); [[bracket]] prof, from, to, zones = {{map, x, y, subidas}}; [[trainer]] con faction.
--   kind = "gathering_route": [[stop]] guide, section, levels, maps (mapas de la sección con nodos).
-- Reglas (Classic; sin verificar en Forever): naranja < req+25 (100 %), amarillo < req+50 (75 %), verde < req+100 (25 %),
-- gris después (0 %). Los rangos de recolección de Forever no piden nivel de personaje: Oficial a 50, Experto a 125,
-- Artesano a 200 (Professions.State se envuelve aquí para no avisar de un nivel que no existe).
local ADDON, Senda = ...
local M = Senda.Mod
if not M then return end
local L = M.L

local G = {}
Senda.Modules.Gathering = G

G.PROFS = { "herbalism", "mining", "skinning", "fishing" }
local IS = { herbalism = true, mining = true, skinning = true, fishing = true }
G.IS = IS
local WEIGHT = { orange = 1, yellow = 0.75, green = 0.25, grey = 0 }
G.WEIGHT = WEIGHT
-- Cuántos nodos (o apariciones) de una clase hacen falta para que cuente (igual que tools/gen_gathering.py MIN_UP).
local MIN_UP = { herbalism = 3, mining = 3, skinning = 10 }
local RANKS = {
  { name = "Aprendiz", learn = 0,   max = 75 },
  { name = "Oficial",  learn = 50,  max = 150 },
  { name = "Experto",  learn = 125, max = 225 },
  { name = "Artesano", learn = 200, max = 300 },
}
G.RANKS = RANKS
local MAX_ROUTE_ZONES = 4

------------------------------------------------------------------------
-- Reglas puras
------------------------------------------------------------------------
-- "red" = no se puede recoger todavía; nil si no hay requisito.
function G.Color(skill, req)
  skill, req = tonumber(skill) or 0, tonumber(req) or 0
  if skill < req then return "red" end
  if skill < req + 25 then return "orange" end
  if skill < req + 50 then return "yellow" end
  if skill < req + 100 then return "green" end
  return "grey"
end

local function Round(v) return math.floor((tonumber(v) or 0) + 0.5) end

-- Estado de una zona para una habilidad:
--   { counts = {red, orange, yellow, green, grey}, w, status = "good"|"slow"|"grey"|"red"|"lost"|"none", need }
-- good: sube bien (naranja + amarillo suficientes); slow: casi todo verde; grey: ya no sube nada;
-- red: lo que hay en cantidad pide más habilidad (need = la mínima de esos nodos); lost (pesca): el agua pierde peces.
function G.ZoneState(prof, zone, skill)
  local st = { counts = { red = 0, orange = 0, yellow = 0, green = 0, grey = 0 }, w = 0, status = "none" }
  if type(zone) ~= "table" then return st end
  if prof == "fishing" then
    local full = tonumber(zone.full) or 0
    st.need = full
    st.status = (skill or 0) >= full and "good" or "lost"
    return st
  end
  local minUp = MIN_UP[prof] or 3
  local lowestBig
  for _, n in ipairs(zone.nodes or {}) do
    local req, up = tonumber(n[2]) or 0, tonumber(n[3]) or 0
    local c = G.Color(skill, req)
    st.counts[c] = st.counts[c] + up
    st.w = st.w + up * (WEIGHT[c] or 0)
    if up >= minUp and (not lowestBig or req < lowestBig) then lowestBig = req end
  end
  local c = st.counts
  if c.orange + c.yellow >= minUp then
    st.status = "good"
  elseif c.orange + c.yellow + c.green > 0 then
    st.status = "slow"
  elseif c.red > 0 and c.grey == 0 then
    st.status = "red"
  elseif c.red > 0 and lowestBig and (skill or 0) < lowestBig then
    st.status = "red"
  else
    st.status = "grey"
  end
  if st.status == "red" or (lowestBig and (skill or 0) < lowestBig) then st.need = lowestBig end
  return st
end

------------------------------------------------------------------------
-- Datos de las páginas
------------------------------------------------------------------------
local cache
local function Data()
  if cache then return cache end
  local d = { zones = {}, brackets = {}, trainers = {}, stops = {} }
  for _, p in ipairs(M.Pages("professions")) do
    for _, z in ipairs(p.zone or {}) do
      if type(z) == "table" and IS[M.ProfKey(z.prof)] and z.map then
        local k = M.ProfKey(z.prof)
        d.zones[k] = d.zones[k] or {}
        d.zones[k][z.map] = z
      end
    end
    for _, b in ipairs(p.bracket or {}) do
      if type(b) == "table" and IS[M.ProfKey(b.prof)] then
        local k = M.ProfKey(b.prof)
        d.brackets[k] = d.brackets[k] or {}
        table.insert(d.brackets[k], b)
      end
    end
    for _, t in ipairs(p.trainer or {}) do
      if type(t) == "table" and IS[M.ProfKey(t.prof or "")] then
        local k = M.ProfKey(t.prof)
        d.trainers[k] = d.trainers[k] or {}
        table.insert(d.trainers[k], t)
      end
    end
  end
  for _, p in ipairs(M.Pages("gathering_route")) do
    for _, s in ipairs(p.stop or {}) do
      if type(s) == "table" and s.guide then
        d.stops[s.guide] = d.stops[s.guide] or {}
        table.insert(d.stops[s.guide], s)
      end
    end
  end
  cache = d
  return d
end
function G.Reset() cache = nil end
G.Data = Data

local function ZoneName(map, fallback)
  local C = Senda.Compat
  if C and C.MapName then
    local ok, n = pcall(C.MapName, map)
    if ok and type(n) == "string" and n ~= "" then return n end
  end
  return fallback or ("#" .. tostring(map))
end

function G.ZoneLabel(prof, map)
  local z = Data().zones[prof] and Data().zones[prof][map]
  return ZoneName(map, z and z.name)
end

-- Profesiones de recolección y pesca que el personaje ya tiene: { {key, rank, max} }.
function G.Learned()
  local out = {}
  for _, key in ipairs(G.PROFS) do
    local rank, max = M.ProfRank(key)
    if rank then table.insert(out, { key = key, rank = rank, max = max }) end
  end
  return out
end

------------------------------------------------------------------------
-- Rutas de tu guía
------------------------------------------------------------------------
-- Sección actual de la guía: guideId, sectionId.
function G.Current()
  local E = Senda.Engine
  if not E then return nil end
  local sec = E.CurrentSection and E:CurrentSection()
  return E.guideId, sec and sec.id
end

-- Zonas de tu guía (desde la sección actual hacia delante) que tienen datos de `prof`.
-- Devuelve { {map, name, section, levels, here, state, at} } sin repetir mapa, como mucho `limit`.
function G.RouteZones(prof, guideId, sectionId, level, skill, limit)
  limit = limit or MAX_ROUTE_ZONES
  local d = Data()
  local stops = d.stops[guideId or ""]
  local zones = d.zones[prof]
  if not stops or not zones then return {} end
  level = level or M.Level()
  local start = 1
  if sectionId then
    for i, s in ipairs(stops) do
      if s.section == sectionId then start = i; break end
    end
  else
    for i, s in ipairs(stops) do
      if (s.levels and s.levels[2] or 0) >= level then start = i; break end
    end
  end
  local out, seen = {}, {}
  for i = start, #stops do
    local s = stops[i]
    for _, map in ipairs(s.maps or {}) do
      local z = zones[map]
      if z and not seen[map] then
        seen[map] = true
        table.insert(out, { map = map, name = ZoneName(map, z.name), section = s.section, levels = s.levels,
          here = (i == start), state = G.ZoneState(prof, z, skill), at = z.at })
        if #out >= limit then return out end
      end
    end
  end
  return out
end

-- Banda (de 25 en 25) que contiene `skill`, con sus mejores zonas para tu bando.
function G.Bracket(prof, skill)
  local list = Data().brackets[prof] or {}
  local pick
  for _, b in ipairs(list) do
    if skill >= b.from and (skill < b.to or b.to >= 300) then pick = b end
  end
  if not pick then return nil end
  local faction, zones = M.Faction(), {}
  for _, row in ipairs(pick.zones or {}) do
    local z = Data().zones[prof] and Data().zones[prof][row[1]]
    local side = z and z.side or "AH"
    local ok = (faction == "Alliance" and side:find("A", 1, true)) or (faction == "Horde" and side:find("H", 1, true))
      or (faction ~= "Alliance" and faction ~= "Horde")
    if ok then
      table.insert(zones, { map = row[1], x = row[2], y = row[3], gain = row[4], name = ZoneName(row[1], z and z.name) })
    end
  end
  return { from = pick.from, to = pick.to, zones = zones }
end

------------------------------------------------------------------------
-- Rangos e instructores
------------------------------------------------------------------------
function G.RankFor(max)
  for i, r in ipairs(RANKS) do if max <= r.max then return i, r end end
  return #RANKS, RANKS[#RANKS]
end

-- Instructor de tu bando que enseña `rankName` (preferido: en tu mapa). { map, x, y, nombre } o nil.
function G.Trainer(prof, rankName)
  local list = Data().trainers[prof]
  if not list then return nil end
  local faction = M.Faction()
  local here
  local C = Senda.Compat
  if C and C.BestMap then local ok, m = pcall(C.BestMap); if ok then here = m end end
  local best, bestScore
  for _, t in ipairs(list) do
    local at = t.at
    local okSide = t.faction == nil or t.faction == faction or not faction
    local teaches = type(t.ranks) ~= "table" or #t.ranks == 0 or not rankName
    for _, r in ipairs(type(t.ranks) == "table" and t.ranks or {}) do if r == rankName then teaches = true end end
    if okSide and teaches and type(at) == "table" and at[1] and at[2] and at[3] then
      local score = (t.faction and 1 or 0) + ((here and at[1] == here) and 2 or 0)
      if not best or score > bestScore then best, bestScore = t, score end
    end
  end
  if best then return { best.at[1], best.at[2], best.at[3], best.at[4] or best.name } end
end

------------------------------------------------------------------------
-- Professions.State sin nivel de personaje para los rangos de recolección
------------------------------------------------------------------------
local function WrapProfessions()
  local P = Senda.Modules.Professions
  if not (P and P.State) or P.__gathering then return end
  P.__gathering = true
  local orig = P.State
  P.State = function(key, level, route)
    local k = M.ProfKey(key)
    if not IS[k] then return orig(key, level, route) end
    local real = level or M.Level()
    -- Forever no pide nivel de personaje para Oficial/Experto/Artesano de Herboristería, Minería y Desuello (la
    -- pesca sí, Classic): con un nivel alto el tope nunca queda «esperando nivel» y entrenar sale al llegar la habilidad.
    local st = orig(key, (k == "fishing") and real or 99, route)
    if k ~= "fishing" then
      st.target = math.min(300, real * 5)
      st.behind = st.rank ~= nil and st.rank < st.target - 40 or false
    end
    local rankName = (st.train and st.train.name) or (not st.rank and RANKS[1].name) or st.rankName
    local tr = G.Trainer(k, rankName)
    if tr then st.trainer = tr end
    return st
  end
end

------------------------------------------------------------------------
-- Pestaña Profesiones: sección de recolección
------------------------------------------------------------------------
local STATUS_TEXT = {
  good = function() return L.MOD_GATH_GOOD or "sube bien" end,
  slow = function() return L.MOD_GATH_SLOW or "va lento (casi todo verde)" end,
  grey = function() return L.MOD_GATH_GREY or "ya no sube nada: cambia de zona" end,
  red = function() return L.MOD_GATH_RED or "los nodos están en rojo" end,
  lost = function() return L.MOD_GATH_LOST or "pierdes peces" end,
}
local STATUS_HL = { good = "good", slow = "dim", grey = "warn", red = "warn", lost = "dim", none = "dim" }
local STATUS_COLOR = { good = "|cff7cc66f", slow = "|cffffd100", grey = "|cff999999", red = "|cffff6040", lost = "|cffffd100" }

local function StatusLine(prof, z)
  local s = z.state
  local txt = (STATUS_TEXT[s.status] and STATUS_TEXT[s.status]()) or ""
  local extra = ""
  if s.status == "red" and s.need then
    extra = " " .. string.format(L.MOD_GATH_NEED or "(pide %d)", s.need)
  elseif s.status == "lost" and s.need then
    extra = " " .. string.format(L.MOD_GATH_FULL or "(hasta %d de habilidad)", s.need)
  elseif prof ~= "fishing" and s.status ~= "none" then
    local c = s.counts
    extra = string.format("  |cffaaaaaa%s %d · %s %d · %s %d|r", L.MOD_GATH_ORANGE or "naranja", Round(c.orange),
      L.MOD_GATH_YELLOW or "amarillo", Round(c.yellow), L.MOD_GATH_GREEN or "verde", Round(c.green))
  end
  return (STATUS_COLOR[s.status] or "|cffffffff") .. txt .. "|r" .. extra
end

-- Nodos para la pestaña de profesiones (se añaden al final del documento de Professions.Refresh).
function G.Nodes(level)
  level = level or M.Level()
  local nodes = {}
  local guideId, sectionId = G.Current()
  local P = Senda.Modules.Professions
  for _, p in ipairs(G.Learned()) do
    local key, skill, max = p.key, p.rank, p.max
    local label = M.ProfLabel(key)
    table.insert(nodes, { t = "h2", text = string.format(L.MOD_GATH_HEAD or "%s: dónde recoger", label) })
    -- 1) tu ruta
    local zones = G.RouteZones(key, guideId, sectionId, level, skill)
    if #zones > 0 then
      table.insert(nodes, { t = "p", text = "|cffaaaaaa" .. (L.MOD_GATH_ROUTE or "En tu ruta:") .. "|r", raw = true })
      for _, z in ipairs(zones) do
        local lv = z.levels and string.format(" (%d-%d)", z.levels[1] or 0, z.levels[2] or 0) or ""
        local row = { t = "row", raw = true, hl = STATUS_HL[z.state.status], icon = "Interface\\Icons\\INV_Misc_Map_01",
          text = string.format("|cffffffff%s|r%s  %s", z.name, lv, StatusLine(key, z)) }
        table.insert(nodes, row)
      end
      local first = zones[1]
      if first.at and first.at[1] and first.at[2] and first.at[2] > 0 and P and P.Arrow then
        table.insert(nodes, { t = "btn", width = 280, label = (L.MOD_GATH_ARROW or "Flecha a") .. ": " .. first.name,
          onClick = function() P.Arrow({ first.at[1], first.at[2], first.at[3], first.name }, label) end })
      end
    elseif guideId then
      table.insert(nodes, { t = "p", text = "|cffaaaaaa" .. (L.MOD_GATH_NOROUTE or "Tu guía no pasa por zonas con datos de esta profesión.") .. "|r", raw = true })
    end
    -- 2) mejor zona para tu habilidad ahora
    local b = G.Bracket(key, skill)
    if b and b.zones[1] then
      local best = b.zones[1]
      table.insert(nodes, { t = "p", raw = true,
        text = string.format(L.MOD_GATH_BEST or "Mejor zona para %d-%d: |cffffffff%s|r.", b.from, b.to, best.name) })
      if best.x and best.x > 0 and P and P.Arrow then
        table.insert(nodes, { t = "btn", width = 280, label = (L.MOD_GATH_ARROW or "Flecha a") .. ": " .. best.name,
          onClick = function() P.Arrow({ best.map, best.x, best.y, best.name }, label) end })
      end
    end
    -- 3) siguiente rango
    local ri = G.RankFor(max)
    local nextR = RANKS[ri + 1]
    if nextR and skill >= nextR.learn - 10 then
      local msg
      if skill >= nextR.learn then
        msg = string.format(L.MOD_GATH_RANK_NOW or "Entrena %s ya: no pide nivel de personaje.", nextR.name)
      else
        msg = string.format(L.MOD_GATH_RANK_SOON or "%s se entrena a habilidad %d (no pide nivel de personaje).", nextR.name, nextR.learn)
      end
      if key == "fishing" then
        msg = msg .. " " .. (L.MOD_GATH_FISH_RANK or "Pesca: Experto es un libro y Artesano una misión; Oficial pide nivel 10.")
      end
      table.insert(nodes, { t = "p", raw = true, text = "|cffaaaaaa" .. msg .. "|r" })
    end
  end
  return nodes
end

-- Gancho que llama Professions.Refresh (una sola línea en Professions.lua).
local function Extend(nodes, level)
  if M.InCombat and M.InCombat() then return end
  local ok, extra = pcall(G.Nodes, level)
  if ok and type(extra) == "table" and #extra > 0 then
    table.insert(nodes, { t = "sp" })
    for _, n in ipairs(extra) do table.insert(nodes, n) end
  end
end

M.OnReady(function()
  WrapProfessions()
  local P = Senda.Modules.Professions
  if P then P.ExtraNodes = Extend end
end)
-- Si Professions.lua ya cargó (el orden de Modules.xml lo garantiza), engancha también ahora.
WrapProfessions()
do
  local P = Senda.Modules.Professions
  if P then P.ExtraNodes = Extend end
end

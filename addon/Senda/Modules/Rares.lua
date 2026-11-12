-- Senda / Modules / Rares
-- Alertas de raros: una línea en el HUD («Raro cerca: Madre Colmillo (nivel 10) · Señalar») con sonido
-- opcional, que apunta la flecha al raro con «Señalar».
--
-- Detección (cada camino solo gasta lo que el cliente ya entrega hecho, nunca recorre listas por fotograma):
--   * viñetas del minimapa: VIGNETTE_MINIMAP_UPDATED y un barrido de C_VignetteInfo.GetVignettes() (como mucho
--     cada 2 s, nunca en combate, repartido en tandas pequeñas) con GetVignetteInfo y GetVignettePosition;
--   * placas de nombre (NAME_PLATE_UNIT_ADDED), objetivo y ratón encima, con UnitClassification «rare» o
--     «rareelite», o un id que está en Data/Rares.lua.
-- Todo valor que el cliente devuelva «secreto» (en combate) se trata como desconocido y la unidad se salta.
-- No se avisa en instancias ni con el HUD oculto (hide-in-instances / ocultar todo).
--
-- La decisión es una función pura sobre una tabla de estado (Rares.Decide), así se prueba sin el juego:
--   rebote de 3 s por unidad, enfriamiento por raro, ignorar muertos, retener el aviso en combate y soltarlo al
--   salir (salvo que ya haya muerto o pasen 60 s). Los datos (nivel, rango y apariciones de 346 raros) salen de
--   data/rares/ vía tools/build.py (forever-db, GPL-3).
--
-- Adaptado de Polestar (GPL-3), addon/Polestar/Rares/Detect.lua y Rares.lua: caminos de detección, rebote por
-- GUID, decisión pura y retención en combate, sobre la API y las opciones de Senda.
local ADDON, Senda = ...
local Compat, Events = Senda.Compat, Senda.Events
local L = Senda.L

local type, tonumber, tostring, pairs, ipairs = type, tonumber, tostring, pairs, ipairs
local format, min, max = string.format, math.min, math.max

local Rares = {}
Senda.Rares = Rares

Rares.DEBOUNCE = 3       -- s entre dos miradas a la misma unidad
Rares.SCAN_EVERY = 2     -- s entre dos barridos de viñetas
Rares.HOLD_FOR = 60      -- s que un aviso retenido en combate sigue valiendo
Rares.COOLDOWN = 600     -- s antes de volver a avisar del mismo raro
Rares.SHOW_FOR = 45      -- s que la línea se queda en el HUD
Rares.LEVEL_WINDOW = 3   -- niveles de diferencia con «solo raros de mi nivel»
local SWEEP_AT = 200     -- entradas del rebote a partir de las cuales se barren las viejas
local SCAN_CHUNK = 8     -- viñetas por tanda (una tanda por fotograma)
local MAP_UP = 3         -- mapas padre que se prueban para la posición de una viñeta

local function Opt(key) return Senda.Options:Get(key) end

------------------------------------------------------------------------------
-- Datos: Senda.RaresData[id] = "<nivMín>-<nivMáx> <r|e> <mapa>:<x>,<y>;<x>,<y> ..." (x e y en décimas de %)
------------------------------------------------------------------------------

local parsed = {}

-- id -> { id, lo, hi (0 = nivel desconocido), elite, spawns = { { mapa, x%, y% }, ... } } o nil.
function Rares.Info(id)
  id = tonumber(id)
  if not id then return nil end
  local c = parsed[id]
  if c ~= nil then return c or nil end
  local raw = Senda.RaresData and Senda.RaresData[id]
  local lo, hi, kind, rest
  if type(raw) == "string" then lo, hi, kind, rest = raw:match("^(%d+)%-(%d+) (%a) (.*)$") end
  if not lo then
    parsed[id] = false
    return nil
  end
  local info = { id = id, lo = tonumber(lo), hi = tonumber(hi), elite = kind == "e", spawns = {} }
  for group in rest:gmatch("%S+") do
    local map, pts = group:match("^(%d+):(.+)$")
    if map then
      for xs, ys in pts:gmatch("(%d+),(%d+)") do
        info.spawns[#info.spawns + 1] = { tonumber(map), tonumber(xs) / 10, tonumber(ys) / 10 }
      end
    end
  end
  parsed[id] = info
  return info
end

function Rares.Known(id)
  return id ~= nil and Senda.RaresData ~= nil and Senda.RaresData[id] ~= nil
end

function Rares.Count()
  local n = 0
  for k in pairs(Senda.RaresData or {}) do if type(k) == "number" then n = n + 1 end end
  return n
end

-- Aparición más cercana al jugador dentro de su mapa (o en un mapa de la cadena de padres): map, x%, y%.
function Rares.NearestSpawn(info, playerMap, px, py)
  if not (info and info.spawns[1]) then return nil end
  local best, bestD
  for _, s in ipairs(info.spawns) do
    if not playerMap or s[1] == playerMap then
      local d
      if px and py then
        local dx, dy = s[2] / 100 - px, s[3] / 100 - py
        d = dx * dx + dy * dy
      else
        d = 0
      end
      if not bestD or d < bestD then best, bestD = s, d end
    end
  end
  if not best and not playerMap then best = info.spawns[1] end
  if best then return best[1], best[2], best[3] end
end

------------------------------------------------------------------------------
-- Decisión pura
------------------------------------------------------------------------------

-- Estado: { opts, now, level, combat, instance, hidden, ignored = { [npcId] = true },
--           recent = { [clave] = hora }, alerted = { [claveRaro] = hora }, held = { ev, t } | nil, lastScan }
-- opts: { enabled, near, cooldown, paths = { vignette, nameplate, target, mouseover } (false apaga un camino) }
function Rares.NewState()
  return { opts = { enabled = true, near = false, cooldown = Rares.COOLDOWN, paths = {} },
    now = 0, level = 1, combat = false, instance = false, hidden = false, ignored = {},
    recent = {}, nrecent = 0, alerted = {}, held = nil, lastScan = -1e9 }
end

local function RareKey(ev)
  if ev.id then return "rare:" .. ev.id end
  if type(ev.name) == "string" and ev.name ~= "" then return "name:" .. ev.name end
end

local function Sweep(st)
  local now, n = st.now, 0
  for k, t in pairs(st.recent) do
    if now - t > Rares.DEBOUNCE then st.recent[k] = nil else n = n + 1 end
  end
  st.nrecent = n
end

-- ev: { src = "vignette"|"nameplate"|"target"|"mouseover", guid, id, name, isRare, isPlayer, dead, lo, hi, release }
-- -> "alert" | "hold" | "skip", motivo. Solo toca las tablas del propio estado (recent, alerted, held).
function Rares.Decide(st, ev)
  local o = st.opts
  if not o.enabled then return "skip", "off" end
  if st.instance then return "skip", "instance" end
  if st.hidden then return "skip", "hidden" end
  if o.paths and o.paths[ev.src] == false then return "skip", "path" end
  if ev.isPlayer then return "skip", "player" end
  if not ev.isRare then return "skip", "notrare" end
  if ev.id and st.ignored and st.ignored[ev.id] then return "skip", "ignored" end
  if ev.dead then return "skip", "dead" end
  local rk = RareKey(ev)
  local uk = ev.guid or rk
  if not uk then return "skip", "unreadable" end
  if not ev.release then
    local last = st.recent[uk]
    if last and st.now - last < Rares.DEBOUNCE then return "skip", "debounce" end
    if last == nil then st.nrecent = st.nrecent + 1 end
    st.recent[uk] = st.now
    if st.nrecent > SWEEP_AT then Sweep(st) end
  end
  local cd = o.cooldown or Rares.COOLDOWN
  local at = rk and st.alerted[rk]
  if at and st.now - at < cd then return "skip", "cooldown" end
  if o.near and ev.lo and ev.hi and ev.lo > 0 and ev.hi > 0 and st.level then
    if ev.hi < st.level - Rares.LEVEL_WINDOW or ev.lo > st.level + Rares.LEVEL_WINDOW then return "skip", "level" end
  end
  if st.combat then
    st.held = { ev = ev, t = st.now }
    return "hold", "combat"
  end
  if rk then st.alerted[rk] = st.now end
  if st.held and st.held.ev == ev then st.held = nil end
  return "alert", "ok"
end

-- Al salir de combate: suelta el aviso retenido si sigue valiendo. st.refresh(ev), si existe, vuelve a leer
-- si ha muerto. -> accion, motivo, ev
function Rares.Release(st)
  local h = st.held
  st.held = nil
  if not h then return nil end
  if st.now - h.t > Rares.HOLD_FOR then return "skip", "stale", h.ev end
  local ev = h.ev
  if st.refresh then st.refresh(ev) end
  ev.release = true
  local action, reason = Rares.Decide(st, ev)
  return action, reason, ev
end

-- ¿Toca barrer las viñetas? -> segundos de espera (0 = ya) o nil si estás en combate.
function Rares.ScanDelay(st)
  if st.combat then return nil end
  return max(0, Rares.SCAN_EVERY - (st.now - st.lastScan))
end

------------------------------------------------------------------------------
-- Lecturas del cliente (todo protegido; un valor secreto cuenta como desconocido)
------------------------------------------------------------------------------

local function rd(fn, ...)
  local v = Compat.Try(fn, ...)
  if v == nil or Compat.IsSecret(v) then return nil end
  return v
end

local function field(t, k)
  local v = t[k]
  if v == nil or Compat.IsSecret(v) then return nil end
  return v
end

local S = Rares.NewState()
Rares.state = S

local function Now() return (GetTime and GetTime()) or 0 end

-- Pone al día el estado con el momento y las opciones.
local function Sync()
  S.now = Now()
  S.level = Compat.PlayerLevel()
  S.combat = Compat.InCombat()
  local inst = Compat.InstanceType()
  S.instance = inst ~= nil and inst ~= "none"
  S.hidden = Senda.Visibility and Senda.Visibility:Hidden() or false
  S.opts.enabled = Opt("raresEnabled") ~= false
  S.opts.near = Opt("raresNear") == true
  return S
end

local function LevelOf(unit, info)
  local lvl = rd(UnitLevel, unit)
  if type(lvl) == "number" and lvl > 0 then return lvl, lvl end
  if info and info.lo > 0 then return info.lo, info.hi end
end

-- Avistamiento a partir de una unidad (placa de nombre, objetivo, ratón).
local function FromUnit(unit, src)
  if not rd(UnitExists, unit) then return nil end
  local guid = rd(UnitGUID, unit)
  if type(guid) ~= "string" then return nil end
  local ev = { src = src, unit = unit, guid = guid }
  ev.isPlayer = rd(UnitIsPlayer, unit) == true or rd(UnitPlayerControlled, unit) == true
  if ev.isPlayer then return ev end
  ev.id = Compat.NpcIdFromGUID(guid)
  local class = rd(UnitClassification, unit)
  local info = ev.id and Rares.Info(ev.id)
  ev.isRare = class == "rare" or class == "rareelite" or info ~= nil
  if not ev.isRare then return ev end
  ev.dead = rd(UnitIsDead, unit) == true
  local name = rd(UnitName, unit)
  ev.name = type(name) == "string" and name or nil
  ev.lo, ev.hi = LevelOf(unit, info)
  return ev
end

-- Posición (mapa, x%, y%) de una viñeta: el mapa del jugador y hasta MAP_UP mapas padre.
local function VignettePos(guid)
  local VI = C_VignetteInfo
  if not (VI and VI.GetVignettePosition) then return nil end
  local map = Compat.BestMap()
  local tries = 0
  while map and tries <= MAP_UP do
    local pos = rd(VI.GetVignettePosition, guid, map)
    if type(pos) == "table" and pos.GetXY then
      local x, y = Compat.Try(pos.GetXY, pos)
      x, y = Compat.Num(x), Compat.Num(y)
      if x and y and (x > 0 or y > 0) then return map, x * 100, y * 100 end
    end
    local mi = Compat.MapInfo(map)
    map = mi and mi.parentMapID
    if map == 0 then map = nil end
    tries = tries + 1
  end
end

-- Avistamiento a partir de una viñeta: solo las de criaturas (un tesoro es un GameObject y no entra).
local function FromVignette(vguid)
  local VI = C_VignetteInfo
  if not (VI and VI.GetVignetteInfo) or type(vguid) ~= "string" then return nil end
  local info = rd(VI.GetVignetteInfo, vguid)
  if type(info) ~= "table" then return nil end
  local og = field(info, "objectGUID")
  if type(og) ~= "string" then return nil end
  local kind = og:match("^(%a+)%-")
  if kind ~= "Creature" and kind ~= "Vehicle" then return nil end
  local id = Compat.NpcIdFromGUID(og)
  local ev = { src = "vignette", guid = og, vguid = vguid, id = id, isRare = true }
  local name = field(info, "name")
  ev.name = type(name) == "string" and name or nil
  ev.dead = field(info, "isDead") == true
  local data = id and Rares.Info(id)
  if data and data.lo > 0 then ev.lo, ev.hi = data.lo, data.hi end
  ev.map, ev.x, ev.y = VignettePos(vguid)
  return ev
end

------------------------------------------------------------------------------
-- El aviso
------------------------------------------------------------------------------

local alert -- { id, name, lo, hi, elite, map, x, y (%), t, src }

local function LevelText(a)
  local lvl
  if a.lo and a.lo > 0 then
    lvl = a.lo == a.hi and tostring(a.lo) or (a.lo .. "-" .. a.hi)
  end
  if a.elite then lvl = (lvl and (lvl .. ", ") or "") .. (L.RARE_ELITE or "elite") end
  return lvl
end

-- Texto de la línea del HUD: con ficha {npc:N} (Senda.Names pone el nombre del cliente) o, si el id no se lee,
-- el nombre que dio el cliente. -> texto (fichas aún sin resolver)
function Rares.AlertText(a)
  local lvl = LevelText(a)
  local who = a.id and Senda.Names and Senda.Names:Get("npc", a.id)
  if a.id and (who or not a.name) then
    if lvl then return format(L.RARE_ALERT, a.id, lvl) end
    return format(L.RARE_ALERT_NOLEVEL, a.id)
  end
  local name = a.name or L.RARE_UNKNOWN_NAME
  if lvl then return format(L.RARE_ALERT_NAME, name, lvl) end
  return format(L.RARE_ALERT_NAME_NOLEVEL, name)
end

-- Para el HUD: texto de la línea y si se puede señalar; nil si no hay aviso.
function Rares.HudLine()
  if not alert then return nil end
  local text = Rares.AlertText(alert)
  if Senda.Names then text = Senda.Names:Resolve(text) end
  return text, alert.map ~= nil
end

function Rares.Current() return alert end

local function Refresh()
  if Senda.HUD and Senda.HUD.RequestRefresh then Senda.HUD:RequestRefresh() end
end

function Rares.Dismiss()
  alert = nil
  Refresh()
end

-- Apunta la flecha al raro.
function Rares.Point()
  local a = alert
  if not (a and a.map and Senda.Arrow) then return false end
  local name = a.id and Senda.Names and Senda.Names:Get("npc", a.id) or a.name or L.RARE_UNKNOWN_NAME
  Senda.Arrow:SetTarget(a.map, a.x, a.y, format(L.RARE_ARROW_LABEL, name), "rare", { radius = 15 })
  return true
end

local function PlayAlertSound()
  if not Opt("raresSound") then return end
  local id = (_G.SOUNDKIT and _G.SOUNDKIT.RAID_WARNING) or 8959
  Compat.Try(_G.PlaySound, id)
end

local function Show(ev)
  local info = ev.id and Rares.Info(ev.id)
  local a = { id = ev.id, name = ev.name, lo = ev.lo, hi = ev.hi, elite = info and info.elite or false,
    map = ev.map, x = ev.x, y = ev.y, t = S.now, src = ev.src }
  if not a.map and info then
    local pm, px, py = Compat.PlayerMapPos()
    a.map, a.x, a.y = Rares.NearestSpawn(info, pm, px, py)
  end
  alert = a
  Refresh()
  PlayAlertSound()
  local t = a.t
  Compat.After(Rares.SHOW_FOR, function()
    if alert and alert.t == t then Rares.Dismiss() end
  end)
end

local function Consider(ev)
  if not ev then return end
  local action = Rares.Decide(S, ev)
  if action == "alert" then Show(ev) end
  return action
end

------------------------------------------------------------------------------
-- Barrido de viñetas (con tope de frecuencia, en tandas, nunca en combate)
------------------------------------------------------------------------------

local scanQueued, scanPending = false, false

local function Chunk(list, i)
  Sync()
  if S.combat then scanPending = true; return end
  local last = min(i + SCAN_CHUNK - 1, #list)
  for j = i, last do Consider(FromVignette(list[j])) end
  if last < #list then Compat.After(0.01, function() Chunk(list, last + 1) end) end  -- siguiente fotograma
end

local function RunScan()
  scanQueued = false
  Sync()
  if S.combat then scanPending = true; return end
  if not (S.opts.enabled and not S.instance and not S.hidden) then return end
  local VI = C_VignetteInfo
  local list = VI and VI.GetVignettes and rd(VI.GetVignettes)
  S.lastScan = S.now
  if type(list) ~= "table" or #list == 0 then return end
  Chunk(list, 1)
end

function Rares.RequestScan()
  Sync()
  local delay = Rares.ScanDelay(S)
  if not delay then scanPending = true; return end
  if scanQueued then return end
  scanQueued = true
  Compat.After(delay, RunScan)
end

------------------------------------------------------------------------------
-- Eventos
------------------------------------------------------------------------------

local function OnVignette(_, vguid, onMinimap)
  if onMinimap == false then return end
  Sync()
  if not S.opts.enabled or S.instance or S.hidden then return end
  if S.opts.paths.vignette == false then return end
  Consider(FromVignette(vguid))
end

local function OnUnit(src, unit)
  Sync()
  if not S.opts.enabled or S.instance or S.hidden or S.opts.paths[src] == false then return end
  Consider(FromUnit(unit, src))
end

-- Vuelve a leer si el raro retenido ha muerto mientras combatías.
S.refresh = function(ev)
  if ev.src == "vignette" then
    local VI = C_VignetteInfo
    local info = VI and VI.GetVignetteInfo and ev.vguid and rd(VI.GetVignetteInfo, ev.vguid)
    if type(info) == "table" then ev.dead = field(info, "isDead") == true end
  elseif ev.unit and rd(UnitExists, ev.unit) and rd(UnitGUID, ev.unit) == ev.guid then
    ev.dead = rd(UnitIsDead, ev.unit) == true
  end
end

local function OnRegenEnabled()
  Sync()
  local action, _, ev = Rares.Release(S)
  if action == "alert" then Show(ev) end
  if scanPending then
    scanPending = false
    Rares.RequestScan()
  end
end

local function Register()
  Events:On("VIGNETTE_MINIMAP_UPDATED", OnVignette)
  Events:On("VIGNETTES_UPDATED", function() Rares.RequestScan() end)
  Events:On("NAME_PLATE_UNIT_ADDED", function(_, unit) OnUnit("nameplate", unit) end)
  Events:On("PLAYER_TARGET_CHANGED", function() OnUnit("target", "target") end)
  Events:On("UPDATE_MOUSEOVER_UNIT", function() OnUnit("mouseover", "mouseover") end)
  Events:On("PLAYER_REGEN_ENABLED", OnRegenEnabled)
  Events:On("PLAYER_ENTERING_WORLD", function()
    alert = nil
    scanPending = false
    Rares.RequestScan()
  end)
end

------------------------------------------------------------------------------
-- Opciones y comando
------------------------------------------------------------------------------

local SEC = L.OPT_SECTION_RARES
Senda.Options:Register({ key = "raresEnabled", label = L.OPT_RARES, tooltip = L.OPT_RARES_TIP, type = "toggle",
  default = true, section = SEC, order = 1,
  onChange = function(v) if v then Rares.RequestScan() else Rares.Dismiss() end end })
Senda.Options:Register({ key = "raresNear", label = L.OPT_RARES_NEAR, tooltip = L.OPT_RARES_NEAR_TIP, type = "toggle",
  default = false, section = SEC, order = 2 })
Senda.Options:Register({ key = "raresSound", label = L.OPT_RARES_SOUND, type = "toggle", default = true,
  section = SEC, order = 3 })

Senda.Slash:Register("raros", function(_, args)
  local sub = (args[2] or ""):lower()
  if sub == "off" or sub == "apagar" then
    Senda.Options:Set("raresEnabled", false)
    Senda:Print(L.SLASH_RARES_OFF)
  elseif sub == "on" or sub == "activar" then
    Senda.Options:Set("raresEnabled", true)
    Senda:Print(L.SLASH_RARES_ON)
  else
    local function yn(v) return v and L.SLASH_RARES_YES or L.SLASH_RARES_NO end
    Senda:Print(L.SLASH_RARES_STATUS, yn(Opt("raresEnabled") ~= false), yn(Opt("raresNear")), yn(Opt("raresSound")),
      Rares.Count())
  end
end, L.SLASH_RARES_HELP)

Events:On("SENDA_READY", Register)

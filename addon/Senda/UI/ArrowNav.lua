-- Caminos reales para la flecha: une UI/Arrow.lua con el addon Senda_Nav (docs/NAV.md, sección 8).
--   Senda.ArrowNav:Waypoint(t, map, x, y) -> wn, ww, yardas, índice, puntos | nil
--       Punto de mundo (norte, oeste) al que debe apuntar la flecha y yardas a pie que quedan por el
--       camino; nil = flecha recta (sin datos, calculando la primera ruta, volando, en taxi, en una
--       instancia, en otro continente o con la opción apagada). x, y en 0-1, como Compat.PlayerMapPos.
--   Senda.ArrowNav:TargetChanged(t)   -- el objetivo de la flecha cambió (Arrow.lua)
--   Senda.ArrowNav:State() -> "off" | "straight" | "routing" | "path", motivo
--   Senda.ArrowNav:Straight()          -- la flecha mide en línea recta en este fotograma
-- Reglas: los addons Senda_Nav, Senda_Nav_EK y Senda_Nav_Kalimdor se cargan bajo demanda y nunca en
-- combate (se espera a PLAYER_REGEN_ENABLED). Un paquete cargado se queda cargado toda la sesión: el cliente
-- no deja volver a cargar un addon, así que soltarlo obligaría a hacer /reload al volver a ese continente.
-- La búsqueda la reparte Senda_Nav en fotogramas (1,2 ms por fotograma fuera de combate).
-- La flecha no apunta al siguiente punto del camino sino a una «zanahoria» LOOK yardas más adelante por él:
-- así gira con suavidad en los recodos en vez de saltar al llegar a cada punto.
--   Senda.ArrowNav:Why() -> motivo de la última medida en línea recta (para el texto de la flecha)
--   Senda.ArrowNav:Path() -> path, índice (para dibujar el camino en el minimapa)
local _, Senda = ...
local Compat, Events = Senda.Compat, Senda.Events

local Nav = {}
Senda.ArrowNav = Nav

local RUNTIME = "Senda_Nav"
local PACKS = { [0] = true, [1] = true } -- continentes con paquete: Reinos del Este y Kalimdor
local REROUTE_COOLDOWN = 5 -- s mínimos entre dos rutas pedidas por salirse del camino
local RETRY_AFTER = 20     -- s antes de volver a pedir una ruta que falló, al mismo objetivo...
local RETRY_JUMP = 400    -- yd: un salto así (tranvía, barco, teletransporte) tras un fallo pide ruta sin esperar
local RETRY_MOVED = 30     -- ...y solo si el jugador se ha movido al menos estas yardas
local FAR_OFF = 120        -- yd: tan lejos del camino, la flecha va recta mientras se recalcula
local LOOK = 15            -- yd por delante en el camino a los que apunta la flecha

local sqrt = math.sqrt

local st = {
  runtime = nil,     -- nil: sin intentar; true: cargado; false: no disponible (motivo en runtimeWhy)
  packFail = {},     -- continente -> motivo por el que no hay paquete en esta sesión
  pending = false,   -- carga pedida en combate: se hace al salir
  continent = nil,   -- último continente del jugador
  key = nil,         -- objetivo de la ruta actual
  token = nil,       -- petición en curso (las respuestas viejas se ignoran)
  job = nil,
  path = nil,
  status = "idle",   -- idle | routing | ok | fail
  why = nil,
  routedAt = -math.huge,
  failAt = nil, failN = nil, failW = nil,
  requests = 0,      -- rutas pedidas (para el simulador y el informe)
  shown = false,     -- la última llamada devolvió un punto del camino
}
Nav.state = st

local function Enabled()
  return Senda.Options:Get("navPaths") ~= false
end

local function API() return rawget(_G, "SendaNav") end

local function Now() return GetTime() end

local function Key(t)
  return string.format("%d:%.5f:%.5f", t.map or 0, t.x or 0, t.y or 0)
end

local function Reset(key)
  local N = API()
  if st.job and N then N.Cancel(st.job) end
  st.key, st.token, st.job, st.path, st.status, st.why = key, nil, nil, nil, "idle", nil
  st.failAt, st.failN, st.failW = nil, nil, nil
  st.routedAt = -math.huge
  st.shown = false
end

-- En combate no se carga nada: se apunta y se carga al salir.
function Nav:Defer()
  st.pending = true
end

-- Carga el runtime (Senda_Nav). Un fallo (no instalado, desactivado) vale para toda la sesión.
local function LoadRuntime()
  if API() then st.runtime = true; return true end
  if st.runtime == false then return false end
  if Compat.InCombat() then Nav:Defer(); return false end
  local load = (C_AddOns and C_AddOns.LoadAddOn) or rawget(_G, "LoadAddOn")
  local ok, why = Compat.Try(load, RUNTIME)
  if ok and API() then
    st.runtime = true
    -- el paquete (9-12 MB) en otro fotograma: no se suman los dos tirones
    return false
  end
  st.runtime, st.runtimeWhy = false, tostring(why or "load")
  Senda:Debug("Senda_Nav no disponible: " .. st.runtimeWhy)
  return false
end

local function LoadPack(c)
  local N = API()
  if N.IsLoaded(c) then return true end
  if st.packFail[c] then return false end
  if Compat.InCombat() then Nav:Defer(); return false end
  local ok, why = N.Load(c)
  if ok then return true end
  if why == "combat" then
    Nav:Defer()
  else
    st.packFail[c] = tostring(why or "load")
    Senda:Debug("caminos: sin paquete del continente " .. c .. " (" .. st.packFail[c] .. ")")
  end
  return false
end

local function ContinentChanged(c)
  st.continent = c
  Reset(nil)
end

-- Yardas que quedan desde cada punto hasta el final del camino.
local function Prepare(path)
  local n = #path
  local rest = {}
  rest[n] = 0
  for i = n - 1, 1, -1 do
    local a, b = path[i], path[i + 1]
    local dx, dy = b.wx - a.wx, b.wy - a.wy
    rest[i] = rest[i + 1] + sqrt(dx * dx + dy * dy)
  end
  path.rest = rest
end

local function Request(t, map, x, y, pn, pw)
  local N = API()
  if st.job then N.Cancel(st.job) end
  local token = {}
  st.token, st.job, st.status, st.why = token, nil, "routing", nil
  st.routedAt = Now()
  st.requests = st.requests + 1
  local job = N.Route(map, x * 100, y * 100, t.map, t.x * 100, t.y * 100, function(path, costOrWhy)
    if st.token ~= token then return end -- respuesta de una ruta ya sustituida
    st.job = nil
    if path and #path > 0 then
      Prepare(path)
      st.path, st.status = path, "ok"
    else
      st.path, st.status, st.why = nil, "fail", tostring(costOrWhy)
      st.failAt, st.failN, st.failW = Now(), pn, pw
      Senda:Debug("caminos: sin ruta (" .. st.why .. ")")
    end
  end)
  -- Route puede responder en el acto (fallos de entrada): solo se guarda el trabajo si sigue en curso.
  if st.token == token and st.status == "routing" then st.job = job end
end

-- Punto LOOK yardas por delante del jugador siguiendo el camino desde el punto i (sin pasar de un ascensor
-- o portal: ahí hay que llegar al punto exacto).
local function Carrot(path, i, pn, pw)
  local ax, ay, left = pn, pw, LOOK
  for k = i, #path do
    local q = path[k]
    local dx, dy = q.wx - ax, q.wy - ay
    local d = sqrt(dx * dx + dy * dy)
    if d >= left then
      return ax + dx * left / d, ay + dy * left / d
    end
    left = left - d
    ax, ay = q.wx, q.wy
    if q.lift then break end
  end
  return ax, ay
end
Nav.Carrot = Carrot

function Nav:TargetChanged(t)
  local key = t and Key(t) or nil
  if key ~= st.key then Reset(key) end
end

local function Straight(why)
  st.straightWhy = why
  return nil
end

function Nav:Waypoint(t, map, x, y)
  st.shown = false
  if not Enabled() then return Straight("off") end
  if not (t and map and x and y) then return Straight("nopos") end
  if not (t.continent and PACKS[t.continent]) then return Straight("nodata") end
  local c, pn, pw = Compat.WorldPos(map, x, y)
  if not c then return Straight("nopos") end
  if c ~= st.continent then ContinentChanged(c) end
  if c ~= t.continent then return Straight("continent") end
  -- volando, en taxi o en una instancia no se anda: flecha recta
  if Compat.OnTaxi() then return Straight("taxi") end
  if Compat.IsFlying() then return Straight("flying") end
  local inst = Compat.InstanceType()
  if inst and inst ~= "none" then return Straight("instance") end
  if not LoadRuntime() then return Straight(st.runtime == false and "nonav" or "loading") end
  if not LoadPack(c) then
    if st.packFail[c] then return Straight("nodata") end
    return Straight(Compat.InCombat() and "combat" or "loading")
  end

  local key = Key(t)
  if key ~= st.key then Reset(key) end
  local now = Now()
  if st.status == "idle" then
    Request(t, map, x, y, pn, pw)
  elseif st.status == "fail" then
    local dn, dw = pn - (st.failN or pn), pw - (st.failW or pw)
    local d2 = dn * dn + dw * dw
    if (now - (st.failAt or now) >= RETRY_AFTER and d2 >= RETRY_MOVED * RETRY_MOVED) or d2 >= RETRY_JUMP * RETRY_JUMP then
      Request(t, map, x, y, pn, pw)
    end
  end
  local path = st.path
  if not path then -- calculando la primera ruta o sin ruta: recta
    return Straight(st.status == "routing" and "routing" or "noroute")
  end

  local N = API()
  local wp, i, yards, off = N.Next(path, map, x * 100, y * 100)
  if not (wp and i and yards) then return Straight("noroute") end
  if off then
    if st.status ~= "routing" and now - st.routedAt >= REROUTE_COOLDOWN then
      Request(t, map, x, y, pn, pw)
    end
    if yards > FAR_OFF then return Straight("routing") end
  end
  local along = yards + (path.rest[i] or 0)
  st.shown, st.idx, st.along, st.straightWhy = true, i, along, nil
  st.pn, st.pw = pn, pw
  local cn, cw = Carrot(path, i, pn, pw)
  st.aimN, st.aimW = cn, cw
  return cn, cw, along, i, #path
end

function Nav:Why() return st.straightWhy end

function Nav:Path()
  if not st.shown then return nil end
  return st.path, st.idx, st.pn, st.pw
end

-- Esta medida de la flecha va recta (sin posición, otro continente...): la marca «ruta» se apaga.
function Nav:Straight()
  st.shown = false
end

function Nav:State()
  if not Enabled() then return "off" end
  if st.shown then return "path" end
  if st.status == "routing" then return "routing" end
  return "straight", st.why or st.runtimeWhy
end

function Nav:SetEnabled()
  Reset(nil)
end

-- Al salir de combate se hace la carga pendiente (sin esperar al siguiente fotograma de la flecha, que
-- puede estar oculta en combate).
Events:On("PLAYER_REGEN_ENABLED", function()
  if not st.pending then return end
  st.pending = false
  local t = Senda.Arrow and Senda.Arrow:GetTarget()
  local map, x, y = Compat.PlayerMapPos()
  if t and map then Nav:Waypoint(t, map, x, y) end
end)

-- Cambio de continente aunque la flecha no esté mirando (sin objetivo): la ruta vieja ya no vale.
local function CheckContinent()
  local map, x, y = Compat.PlayerMapPos()
  if not map then return end
  local c = Compat.WorldPos(map, x, y)
  if c and c ~= st.continent then ContinentChanged(c) end
end
Events:On("ZONE_CHANGED_NEW_AREA", CheckContinent)
Events:On("PLAYER_ENTERING_WORLD", CheckContinent)

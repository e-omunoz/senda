-- Ruta en el minimapa: el camino a pie que sigue la flecha (UI/ArrowNav.lua), dibujado como una línea verde
-- sobre el minimapa. No se puede dibujar en el suelo del mundo 3D: el cliente no da esa API a los addons.
--   Senda.MinimapRoute:Refresh()   -- vuelve a dibujar ya (lo llama el temporizador; útil en pruebas)
--   Senda.MinimapRoute.lines        -- las líneas en uso (para el simulador)
-- Coste: como mucho 10 veces por segundo y solo los tramos que caen dentro del minimapa (MAX_LINES).
-- Escala: Minimap:GetViewRadius() (yardas que caben del centro al borde); sin esa función, las tablas de zoom
-- de siempre (interior/exterior). Respeta el minimapa giratorio (rotateMinimap) y los minimapas cuadrados
-- (GetMinimapShape de otros addons de interfaz).
local _, Senda = ...
local Compat, Events = Senda.Compat, Senda.Events
local L = Senda.L

local R = {}
Senda.MinimapRoute = R

local MAX_LINES = 48
local PERIOD = 0.1
local THICK = 3
local COLOR = { 0.35, 0.95, 0.45, 0.9 }

-- Diámetro visible en yardas por zoom (0-5): exterior e interior.
local OUTDOOR = { [0] = 466 + 2 / 3, 400, 333 + 1 / 3, 266 + 2 / 3, 200, 133 + 1 / 3 }
local INDOOR = { [0] = 300, 240, 180, 120, 80, 50 }

local holder
local pool, used = {}, 0
R.lines = {}

local function Opt(key) return Senda.Options:Get(key) end

local function ViewRadius()
  local mm = rawget(_G, "Minimap")
  if not mm then return nil end
  if mm.GetViewRadius then
    local ok, r = pcall(mm.GetViewRadius, mm)
    if ok and type(r) == "number" and r > 0 then return r end
  end
  local zoom = mm.GetZoom and mm:GetZoom() or 0
  local indoor = false
  if GetCVar then
    local inside, outside = tonumber(GetCVar("minimapInsideZoom")), tonumber(GetCVar("minimapZoom"))
    indoor = inside ~= nil and inside ~= outside and inside == zoom
  end
  return ((indoor and INDOOR or OUTDOOR)[zoom] or 300) / 2
end

local function Square()
  local shape = rawget(_G, "GetMinimapShape")
  return type(shape) == "function" and shape() == "SQUARE"
end

local function Line()
  used = used + 1
  local l = pool[used]
  if not l then
    l = holder:CreateLine(nil, "OVERLAY")
    l:SetThickness(THICK)
    l:SetColorTexture(COLOR[1], COLOR[2], COLOR[3], COLOR[4])
    pool[used] = l
  end
  return l
end

local function HideAll()
  for i = 1, #pool do pool[i]:Hide() end
  used = 0
  R.lines = {}
end

-- Recorta el segmento (x1,y1)-(x2,y2) al círculo de radio r o al cuadrado de lado 2r centrado en 0,0.
local function Clip(x1, y1, x2, y2, r, square)
  local dx, dy = x2 - x1, y2 - y1
  local t0, t1 = 0, 1
  if square then -- Liang-Barsky
    local p = { -dx, dx, -dy, dy }
    local q = { x1 + r, r - x1, y1 + r, r - y1 }
    for k = 1, 4 do
      if p[k] == 0 then
        if q[k] < 0 then return nil end
      else
        local t = q[k] / p[k]
        if p[k] < 0 then
          if t > t1 then return nil end
          if t > t0 then t0 = t end
        else
          if t < t0 then return nil end
          if t < t1 then t1 = t end
        end
      end
    end
  else
    local a = dx * dx + dy * dy
    if a < 1e-9 then return nil end
    local b = 2 * (x1 * dx + y1 * dy)
    local c = x1 * x1 + y1 * y1 - r * r
    local disc = b * b - 4 * a * c
    if disc <= 0 then return nil end
    local sq = math.sqrt(disc)
    local ta, tb = (-b - sq) / (2 * a), (-b + sq) / (2 * a)
    if ta > t0 then t0 = ta end
    if tb < t1 then t1 = tb end
    if t0 >= t1 then return nil end
  end
  return x1 + dx * t0, y1 + dy * t0, x1 + dx * t1, y1 + dy * t1
end

function R:Refresh()
  if not holder then return end
  HideAll()
  if Opt("navMinimap") == false or Opt("navPaths") == false then return end
  if Senda.Visibility and Senda.Visibility:Hidden() then return end
  local nav = Senda.ArrowNav
  local path, idx, pn, pw
  if nav and nav.Path then path, idx, pn, pw = nav:Path() end
  if not (path and idx and pn) then return end
  local mm = rawget(_G, "Minimap")
  local radius = ViewRadius()
  if not (mm and radius) then return end
  local half = (mm:GetWidth() or 0) / 2
  if half <= 0 then return end
  local scale = half / radius
  local r = half - 2
  local square = Square()
  local rot = GetCVar and GetCVar("rotateMinimap") == "1"
  local cf, sf = 1, 0
  if rot then
    local f = Compat.PlayerFacing()
    if not f then return end
    cf, sf = math.cos(f), math.sin(f)
  end
  -- mundo (norte, oeste) -> píxeles del minimapa (x este, y norte), girado si el minimapa gira
  local function P(wn, ww)
    local x, y = -(ww - pw) * scale, (wn - pn) * scale
    if rot then x, y = x * cf + y * sf, -x * sf + y * cf end
    return x, y
  end
  local ax, ay = 0, 0 -- desde el jugador al siguiente punto
  local lines = {}
  for k = idx, #path do
    local q = path[k]
    local bx, by = P(q.wx, q.wy)
    local cx1, cy1, cx2, cy2 = Clip(ax, ay, bx, by, r, square)
    if cx1 then
      local l = Line()
      l:SetStartPoint("CENTER", mm, cx1, cy1)
      l:SetEndPoint("CENTER", mm, cx2, cy2)
      l:Show()
      lines[#lines + 1] = l
      if used >= MAX_LINES then break end
    elseif (ax * ax + ay * ay) > (3 * r) * (3 * r) and (bx * bx + by * by) > (3 * r) * (3 * r) then
      break -- el camino ya va muy lejos del minimapa
    end
    if q.lift then break end -- tras un ascensor o portal el resto no está en este plano
    ax, ay = bx, by
  end
  R.lines = lines
end

local function Create()
  local mm = rawget(_G, "Minimap")
  if holder or not mm then return end
  holder = CreateFrame("Frame", nil, mm)
  holder:SetAllPoints(mm)
  holder:SetFrameLevel((mm:GetFrameLevel() or 1) + 4)
  local acc = 0
  holder:SetScript("OnUpdate", function(_, elapsed)
    acc = acc + elapsed
    if acc < PERIOD then return end
    acc = 0
    R:Refresh()
  end)
end

Senda.Options:Register({ key = "navMinimap", label = L.OPT_NAV_MINIMAP, tooltip = L.OPT_NAV_MINIMAP_TIP,
  type = "toggle", default = true, section = L.OPT_SECTION_ARROW or "Flecha", order = 6.5,
  onChange = function() R:Refresh() end })

Events:On("SENDA_READY", Create)

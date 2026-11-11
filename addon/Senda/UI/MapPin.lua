-- Marca en el mapa del mundo para el objetivo actual de la flecha (opcional).
-- Es una superposición mínima: un marco hijo del lienzo del mapa (WorldMapFrame.ScrollContainer.Child),
-- sin tocar proveedores de datos ni funciones de Blizzard. Si algo de esa estructura no existe, no hace nada.
-- Questie sigue encargándose de los iconos de misión; esto solo marca el destino de Senda.
local _, Senda = ...
local Compat, Events = Senda.Compat, Senda.Events
local L = Senda.L

local MapPin = {}
Senda.MapPin = MapPin

local pin, driver

local function Canvas()
  local wm = _G.WorldMapFrame
  local sc = wm and wm.ScrollContainer
  return wm, sc, sc and sc.Child
end

local function Hide()
  if pin then pin:Hide() end
end

local function Place()
  if not pin then return end
  local wm, sc, canvas = Canvas()
  local t = Senda.Arrow and Senda.Arrow:GetTarget()
  if not (Senda.Options:Get("mapPin") and t and wm and canvas and wm.GetMapID) then return Hide() end
  local ok, shown = pcall(wm.GetMapID, wm)
  if not ok or not shown then return Hide() end
  local x, y
  if t.map == shown then
    x, y = t.x, t.y
  elseif t.continent then
    x, y = Compat.MapPosFromWorld(t.continent, t.wn, t.ww, shown)
  end
  if not x or not y or x < 0 or x > 1 or y < 0 or y > 1 then return Hide() end
  local w, h = canvas:GetSize()
  if not w or w == 0 then return Hide() end
  -- Tamaño constante al hacer zoom: la marca se escala al revés que el lienzo, y como los
  -- desplazamientos de SetPoint van en la escala de la propia marca, se corrigen con esa escala.
  local scale = 1
  if sc.GetCanvasScale then
    local okS, s = pcall(sc.GetCanvasScale, sc)
    if okS and s and s > 0 then scale = 1 / s end
  end
  pin:SetScale(scale)
  pin:ClearAllPoints()
  pin:SetPoint("CENTER", canvas, "TOPLEFT", x * w / scale, -y * h / scale)
  pin.label = t.label
  pin:Show()
end

local function Setup()
  if driver then return end
  local wm, _, canvas = Canvas()
  if not (wm and canvas) then return end

  pin = CreateFrame("Frame", "SendaWorldMapPin", canvas)
  pin:SetSize(22, 22)
  pin:SetFrameLevel((canvas:GetFrameLevel() or 1) + 2000)
  local tex = pin:CreateTexture(nil, "OVERLAY")
  tex:SetAllPoints()
  tex:SetTexture("Interface\\TargetingFrame\\UI-RaidTargetingIcon_1")
  pin:EnableMouse(true)
  pin:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:SetText("Senda", Senda.COLOR[1], Senda.COLOR[2], Senda.COLOR[3])
    if self.label then GameTooltip:AddLine(self.label, 1, 1, 1, true) end
    GameTooltip:Show()
  end)
  pin:SetScript("OnLeave", function() GameTooltip:Hide() end)
  pin:Hide()

  -- El marco "driver" vive dentro del mapa: su OnUpdate solo corre con el mapa abierto.
  driver = CreateFrame("Frame", nil, wm)
  driver.acc = 0
  driver:SetScript("OnUpdate", function(self, dt)
    self.acc = self.acc + dt
    if self.acc < 0.1 then return end
    self.acc = 0
    Place()
  end)
end

Senda.Options:Register({ key = "mapPin", label = L.OPT_MAP_PIN, type = "toggle", default = true,
  section = L.OPT_SECTION_ARROW, order = 6, onChange = function(v) if not v then Hide() end end })

Events:On("SENDA_READY", function()
  pcall(Setup)
  if not driver then
    -- El mapa se carga bajo demanda en algunos clientes.
    Events:On("ADDON_LOADED", function(_, name)
      if name == "Blizzard_WorldMap" then pcall(Setup) end
    end)
  end
end)

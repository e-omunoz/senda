-- Flecha propia (sustituye a TomTom).
--   Senda.Arrow:SetTarget(map, x, y, label, source)  -- x, y en PORCENTAJE (0-100), como en los datos de guía
--   Senda.Arrow:Clear(source)
--   Senda.Arrow:GetTarget() -> target, source         -- target = { map, x, y (0-1), label }
-- Fuentes por prioridad: "corpse" > "manual" > "guide" > cualquier otra. La fuente "travel" (Modules/Travel.lua: primer
-- tramo del camino más rápido) pasa justo por delante del destino al que sustituye.
--   Senda.Arrow:Destination() -> target, source       -- el objetivo activo sin contar "travel"
-- Gira según la orientación del jugador (GetPlayerFacing puede devolver nil o un valor secreto: se tolera),
-- muestra distancia (m o yd) y tiempo estimado, se pone verde al acercarse y marca "has llegado".
-- Modo cadáver: siendo fantasma apunta a C_DeathInfo.GetCorpseMapPosition y vuelve a la guía al resucitar.
-- Caminos reales (opción navPaths, UI/ArrowNav.lua): si el objetivo está en tu continente, la flecha apunta
-- al siguiente punto del camino a pie de Senda_Nav y la distancia es la que queda por el camino («a pie»,
-- con la marca «ruta»); mientras se calcula, sin datos, volando, en taxi o en instancias, va recta.
local _, Senda = ...
local UI, Compat, Events = Senda.UI, Senda.Compat, Senda.Events
local L = Senda.L

local Arrow = {}
Senda.Arrow = Arrow

-- Las fuentes desconocidas (módulos) van justo detrás de "manual" y por delante de la guía.
local PRIORITY = { corpse = 1, manual = 2, guide = 3 }
local OTHER_PRIORITY = 2.5
local DEFAULT_ARRIVE = 10 -- metros
local TWO_PI = math.pi * 2

local targets = {}   -- source -> target
local active, activeSource
local frame
local tomtomUid

local function Opt(key) return Senda.Options:Get(key) end
local function Nav() return Senda.ArrowNav end

------------------------------------------------------------------------------
-- Objetivos
------------------------------------------------------------------------------

local function Pick(skipTravel)
  local best, bestSrc, bestP
  for src, t in pairs(targets) do
    if not (skipTravel and src == "travel") then
      local p = PRIORITY[src] or OTHER_PRIORITY
      if src == "travel" then
        local _, destSrc = Pick(true)
        p = (destSrc and (PRIORITY[destSrc] or OTHER_PRIORITY) or OTHER_PRIORITY) - 0.1
      end
      if not bestP or p < bestP then best, bestSrc, bestP = t, src, p end
    end
  end
  return best, bestSrc
end

local destination, destinationSource
local function CheckDestination()
  local t, src = Pick(true)
  if t ~= destination or src ~= destinationSource then
    destination, destinationSource = t, src
    Events:Fire("SENDA_ARROW_DEST", t, src)
  end
end

local function SyncTomTom()
  local TT = _G.TomTom
  if not TT then return end
  if tomtomUid and TT.RemoveWaypoint then pcall(TT.RemoveWaypoint, TT, tomtomUid) end
  tomtomUid = nil
  if not (Opt("tomtom") and active and TT.AddWaypoint) then return end
  local ok, uid = pcall(TT.AddWaypoint, TT, active.map, active.x, active.y,
    { title = active.label, persistent = false, minimap = true, world = true, from = "Senda" })
  if ok then tomtomUid = uid end
end

local function Update()
  local t, src = Pick()
  local changed = (t ~= active)
  active, activeSource = t, src
  if frame then
    frame.speed = nil
    frame.lastDist = nil
    Arrow:ApplyVisibility()
  end
  if changed then
    if Nav() then Nav():TargetChanged(active) end
    SyncTomTom()
    Events:Fire("SENDA_ARROW_TARGET", active, activeSource)
  end
  CheckDestination()
end

function Arrow:SetTarget(map, x, y, label, source, extra)
  map, x, y = tonumber(map), tonumber(x), tonumber(y)
  source = source or "manual"
  if not map or not x or not y then return end
  local t = { map = map, x = x / 100, y = y / 100, label = label, source = source }
  if type(extra) == "table" then for k, v in pairs(extra) do t[k] = v end end
  -- Posición de mundo en caché (no cambia mientras dure el objetivo); un módulo puede traerla ya calculada.
  if not (t.continent and t.wn and t.ww) then
    t.continent, t.wn, t.ww = Compat.WorldPos(map, t.x, t.y)
  end
  targets[source] = t
  Update()
end

-- ¿Hay un objetivo de esta fuente?
function Arrow:Has(source)
  return targets[source] ~= nil
end

function Arrow:Clear(source)
  if source then targets[source] = nil else wipe(targets) end
  Update()
end

function Arrow:GetTarget()
  return active, activeSource
end

-- El objetivo que el jugador quiere alcanzar (guía, punto manual, cadáver), sin el tramo intermedio de "travel".
function Arrow:Destination()
  return destination, destinationSource
end

------------------------------------------------------------------------------
-- Cálculo
------------------------------------------------------------------------------

-- Distancia (m) y rumbo al objetivo activo desde la posición actual: metros en línea recta (para «has
-- llegado»), rumbo, ¿otro continente?, metros que se muestran (por el camino si lo hay) y ¿por camino?
local function Measure(t)
  local nav = Nav()
  if nav then nav:Straight() end
  local map, x, y = Compat.PlayerMapPos()
  if not map then return nil end
  if t.continent then
    local c, n, w = Compat.WorldPos(map, x, y)
    if c then
      if c ~= t.continent then return nil, nil, true end
      local dN, dW = t.wn - n, t.ww - w
      local yards = math.sqrt(dN * dN + dW * dW)
      local metres = yards * 0.9144
      local wn, ww, along
      if nav then wn, ww, along = nav:Waypoint(t, map, x, y) end
      if wn then
        return metres, math.atan2(ww - w, wn - n), false, along * 0.9144, true
      end
      return metres, math.atan2(dW, dN), false, metres, false
    end
  end
  local m, a = Compat.WorldDistance(map, x, y, t.map, t.x, t.y)
  return m, a, false, m, false
end

local function FormatDist(m)
  if Opt("metres") then
    if m >= 1000 then return string.format("%.1f km", m / 1000) end
    return string.format("%d m", math.floor(m + 0.5))
  end
  return string.format("%d yd", math.floor(m / 0.9144 + 0.5))
end

-- Color según el giro: verde de frente, amarillo de lado, rojo detrás.
local function TurnColor(rel)
  local diff = math.abs(((rel + math.pi) % TWO_PI) - math.pi) / math.pi -- 0 de frente, 1 detrás
  if diff < 0.5 then
    return 0.35 + diff * 1.3, 0.9, 0.35
  end
  return 1, 0.9 - (diff - 0.5) * 1.3, 0.25
end

local function OnUpdate(self, elapsed)
  self.acc = (self.acc or 0) + elapsed
  if self.acc < 0.04 then return end
  local dt = self.acc
  self.acc = 0
  local t = active
  if not t then return end

  local dist, angle, otherContinent, shown, routed = Measure(t)
  self.label:SetText(t.label or "")
  self.route:SetShown(routed and dist ~= nil and dist > (t.radius or DEFAULT_ARRIVE) or false)
  if routed ~= self.routed then
    -- el camino cambia la distancia que se mide: la velocidad suavizada vuelve a empezar
    self.routed, self.speed, self.lastDist = routed, nil, nil
  end
  if not dist then
    self.arrow:Hide()
    self.check:Hide()
    self.unknown:Show()
    self.info:SetText(otherContinent and L.ARROW_OTHER_CONTINENT or L.ARROW_NO_POSITION)
    return
  end
  self.unknown:Hide()

  local arrive = t.radius or DEFAULT_ARRIVE
  if dist <= arrive then
    self.arrow:Hide()
    self.check:Show()
    self.info:SetText(UI:Color("green", L.ARROW_ARRIVED))
    -- Puntos de ruta: al llegar a uno se pasa al siguiente; los manuales se borran solos.
    if t.wps and t.wpIndex and t.wpIndex < #t.wps then
      Arrow:NextWaypoint(t)
    elseif activeSource ~= "guide" and activeSource ~= "corpse" then
      -- Puntos manuales o de módulos: se borran solos poco después de llegar.
      self.arrivedFor = (self.arrivedFor or 0) + dt
      if self.arrivedFor > 3 then self.arrivedFor = 0; Arrow:Clear(activeSource) end
    end
    return
  end
  self.arrivedFor = 0
  self.check:Hide()
  self.arrow:Show()

  local facing = Compat.PlayerFacing()
  if facing and angle then
    local rel = angle - facing
    self.arrow:SetRotation(rel)
    self.arrow:SetVertexColor(TurnColor(rel))
  else
    self.arrow:SetRotation(0)
    self.arrow:SetVertexColor(0.6, 0.6, 0.6)
  end

  -- Tiempo estimado: velocidad de acercamiento suavizada; si no, velocidad del personaje.
  -- Con camino, la distancia es la que queda por él.
  shown = shown or dist
  if self.lastDist then
    local closing = (self.lastDist - shown) / dt
    self.speed = self.speed and (self.speed * 0.85 + closing * 0.15) or closing
  end
  self.lastDist = shown
  local eta
  if self.speed and self.speed > 0.5 then
    eta = shown / self.speed
  else
    local sp = Compat.PlayerSpeed()
    if sp and sp > 0 and Compat.IsGhost() then eta = shown / (sp * 0.9144) end
  end
  local text = FormatDist(shown)
  if routed then text = string.format(L.ARROW_ON_FOOT, text) end
  if eta and eta < 3600 then text = text .. UI:Color("dim", "  ·  " .. Senda.Util.FormatTime(eta)) end
  self.info:SetText(text)
end

------------------------------------------------------------------------------
-- Marco
------------------------------------------------------------------------------

local function Create()
  if frame then return frame end
  local f = CreateFrame("Button", "SendaArrow", UIParent)
  f:SetSize(120, 92)
  f:SetClampedToScreen(true)
  f:SetMovable(true)
  f:EnableMouse(true)
  f:RegisterForDrag("LeftButton")
  f:RegisterForClicks("RightButtonUp")
  f:SetFrameStrata("MEDIUM")
  f:SetScript("OnDragStart", function(self) if not Opt("arrowLocked") then self:StartMoving() end end)
  f:SetScript("OnDragStop", function(self)
    self:StopMovingOrSizing()
    Senda:SaveFramePos(self, "arrow")
  end)
  Senda:RestoreFramePos(f, "arrow", "TOP", "TOP", 0, -120)

  f.arrow = f:CreateTexture(nil, "ARTWORK")
  f.arrow:SetSize(52, 52)
  f.arrow:SetPoint("TOP", 0, -2)
  f.arrow:SetTexture("Interface\\Minimap\\MinimapArrow")

  f.check = f:CreateTexture(nil, "ARTWORK")
  f.check:SetSize(36, 36)
  f.check:SetPoint("TOP", 0, -10)
  f.check:SetTexture("Interface\\RaidFrame\\ReadyCheck-Ready")
  f.check:Hide()

  f.unknown = f:CreateTexture(nil, "ARTWORK")
  f.unknown:SetSize(30, 30)
  f.unknown:SetPoint("TOP", 0, -12)
  f.unknown:SetTexture("Interface\\RaidFrame\\ReadyCheck-Waiting")
  f.unknown:Hide()

  f.label = f:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
  f.label:SetPoint("TOP", 0, -54)
  f.label:SetWidth(220)
  f.label:SetWordWrap(false)
  f.label:SetShadowOffset(1, -1)

  f.info = f:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  f.info:SetPoint("TOP", f.label, "BOTTOM", 0, -2)
  f.info:SetShadowOffset(1, -1)

  -- Marca pequeña «ruta»: la flecha sigue un camino a pie, no la línea recta.
  f.route = f:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
  f.route:SetPoint("LEFT", f.arrow, "RIGHT", 0, -6)
  f.route:SetShadowOffset(1, -1)
  f.route:SetTextColor(0.45, 0.85, 0.45)
  f.route:SetText(L.ARROW_ROUTE_MARK)
  f.route:Hide()

  f:SetScript("OnUpdate", OnUpdate)
  f:SetScript("OnClick", function()
    if activeSource ~= "guide" and activeSource ~= "corpse" then
      local src = activeSource
      Arrow:Clear(src)
      Events:Fire("SENDA_ARROW_DISMISSED", src)
    end
  end)
  f:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
    GameTooltip:SetText(active and active.label or "Senda", 1, 1, 1)
    if active then
      GameTooltip:AddLine(string.format("%s  %.1f, %.1f", Compat.MapName(active.map) or active.map,
        active.x * 100, active.y * 100), 0.7, 0.7, 0.7)
    end
    local nav = Nav()
    local state = nav and nav:State()
    if state == "path" then
      local path = nav.state.path
      local i, n = path and path.idx, path and #path
      if i and n then GameTooltip:AddLine(string.format(L.ARROW_TIP_PATH, i, n), 0.45, 0.85, 0.45, true) end
    elseif state == "routing" then
      GameTooltip:AddLine(L.ARROW_TIP_ROUTING, 0.7, 0.7, 0.7, true)
    end
    GameTooltip:AddLine(L.ARROW_TOOLTIP, nil, nil, nil, true)
    GameTooltip:Show()
  end)
  f:SetScript("OnLeave", function() GameTooltip:Hide() end)
  f:Hide()
  frame = f
  return f
end

function Arrow:ApplyVisibility()
  local f = Create()
  f:SetScale(Opt("arrowScale") or 1)
  local show = Opt("arrow") and active ~= nil and not (Opt("arrowCombatHide") and Compat.InCombat())
    and not (Senda.Visibility and Senda.Visibility:Hidden())
  f:SetShown(show and true or false)
end

function Arrow:NextWaypoint(t)
  t.wpIndex = t.wpIndex + 1
  local wp = t.wps[t.wpIndex]
  if wp then
    self:SetTarget(wp[1], wp[2], wp[3], wp[4] or t.baseLabel, "guide",
      { wps = t.wps, wpIndex = t.wpIndex, baseLabel = t.baseLabel, radius = 15 })
  end
end

------------------------------------------------------------------------------
-- Objetivo de la guía
------------------------------------------------------------------------------

local function GuideLabel(step)
  if step.at and step.at[4] then return step.at[4] end
  local title = Senda.HUD and Senda.HUD:StepTitle(step) or ""
  if title ~= "" then return title end
  local text = Senda.HUD and Senda.HUD:StepText(step) or step.text or ""
  if #text > 40 then
    -- Corte por bytes sin partir un carácter UTF-8 (los textos son español: á, ñ...).
    local cut = 38
    while cut > 0 and (text:byte(cut + 1) or 0) >= 0x80 and (text:byte(cut + 1) or 0) < 0xC0 do cut = cut - 1 end
    text = text:sub(1, cut) .. "…"
  end
  return text
end

local problemKey = ""

function Arrow:FollowStep()
  local step = Senda.Engine and Senda.Engine:CurrentStep()
  problemKey = ""
  if not step then targets.guide = nil; Update(); return end
  -- Misión fallida o abandonada: la flecha vuelve a quien la daba.
  local pr = Senda.Engine.Problem and Senda.Engine:Problem()
  local at = pr and pr.accept and pr.accept.step.at
  if type(at) == "table" and at[1] then
    problemKey = pr.kind .. ":" .. pr.quest
    self:SetTarget(at[1], at[2], at[3], string.format(L.ARROW_RETAKE, GuideLabel(pr.accept.step)), "guide")
    return
  end
  local label = GuideLabel(step)
  local radius = step["do"] == "goto" and step.radius or nil
  if type(step.at) == "table" and step.at[1] then
    local extra = { radius = radius }
    if type(step.wps) == "table" and type(step.wps[1]) == "table" then
      -- `at` es el primer punto y `wps` el resto: la flecha los recorre en orden.
      local route = { { step.at[1], step.at[2], step.at[3], step.at[4] } }
      for _, wp in ipairs(step.wps) do route[#route + 1] = wp end
      extra.wps, extra.wpIndex, extra.baseLabel = route, 1, label
    end
    self:SetTarget(step.at[1], step.at[2], step.at[3], label, "guide", extra)
  elseif type(step.wps) == "table" and type(step.wps[1]) == "table" then
    local wp = step.wps[1]
    self:SetTarget(wp[1], wp[2], wp[3], wp[4] or label, "guide",
      { wps = step.wps, wpIndex = 1, baseLabel = label, radius = 15 })
  else
    targets.guide = nil
    Update()
  end
end

------------------------------------------------------------------------------
-- Modo cadáver
------------------------------------------------------------------------------

local inRange = false

function Arrow:UpdateCorpse()
  if not Opt("corpse") or not Compat.IsGhost() then
    inRange = false
    if targets.corpse then self:Clear("corpse") end
    return
  end
  local map, x, y = Compat.CorpsePos(Compat.BestMap())
  if map then
    local label = inRange and L.CORPSE_IN_RANGE or L.CORPSE
    self:SetTarget(map, x * 100, y * 100, label, "corpse", { radius = 5 })
  end
end

------------------------------------------------------------------------------
-- Opciones y eventos
------------------------------------------------------------------------------

local SEC = L.OPT_SECTION_ARROW
local function Apply() if frame then Arrow:ApplyVisibility() end end
Senda.Options:Register({ key = "arrow", label = L.OPT_ARROW, type = "toggle", default = true, section = SEC,
  order = 1, onChange = Apply })
Senda.Options:Register({ key = "arrowLocked", label = L.OPT_ARROW_LOCKED, type = "toggle", default = false,
  section = SEC, order = 2 })
Senda.Options:Register({ key = "metres", label = L.OPT_METRES, type = "toggle", default = true, section = SEC,
  order = 3 })
Senda.Options:Register({ key = "corpse", label = L.OPT_CORPSE, tooltip = L.OPT_CORPSE_TIP, type = "toggle",
  default = true, section = SEC, order = 4, onChange = function() Arrow:UpdateCorpse() end })
Senda.Options:Register({ key = "arrowCombatHide", label = L.OPT_ARROW_COMBAT, type = "toggle", default = false,
  section = SEC, order = 5, onChange = Apply })
Senda.Options:Register({ key = "navPaths", label = L.OPT_NAV_PATHS, tooltip = L.OPT_NAV_PATHS_TIP, type = "toggle",
  default = true, section = SEC, order = 6, onChange = function() if Nav() then Nav():SetEnabled() end end })
Senda.Options:Register({ key = "tomtom", label = L.OPT_TOMTOM, tooltip = L.OPT_TOMTOM_TIP, type = "toggle",
  default = false, section = SEC, order = 7, onChange = function() SyncTomTom() end })
Senda.Options:Register({ key = "arrowScale", label = L.OPT_SCALE, type = "slider", default = 1, min = 0.5, max = 2,
  step = 0.05, section = SEC, order = 10, onChange = Apply })

Events:On("SENDA_READY", function()
  Create()
  Arrow:ApplyVisibility()
  Events:On("SENDA_STEP_CHANGED", function() Arrow:FollowStep() end)
  Events:On("SENDA_GUIDE_CHANGED", function() Arrow:FollowStep() end)
  -- Una misión puede fallar o abandonarse sin cambiar de paso: se recalcula solo si cambia el problema.
  Events:On("SENDA_STEP_UPDATED", function()
    local E = Senda.Engine
    if E and E.ProblemKey and E:ProblemKey() ~= problemKey then Arrow:FollowStep() end
  end)
  -- El estado de fantasma puede tardar un instante en reflejarse: se comprueba también con retraso.
  local corpse = function()
    Arrow:UpdateCorpse()
    Compat.After(1, function() Arrow:UpdateCorpse() end)
  end
  Events:On("PLAYER_DEAD", corpse)
  Events:On("PLAYER_ALIVE", corpse)
  Events:On("PLAYER_UNGHOST", corpse)
  Events:On("PLAYER_ENTERING_WORLD", function() Compat.After(1, corpse) end)
  Events:On("ZONE_CHANGED_NEW_AREA", function() Compat.After(0.5, corpse) end)
  Events:On("CORPSE_IN_RANGE", function() inRange = true; corpse() end)
  Events:On("CORPSE_OUT_OF_RANGE", function() inRange = false; corpse() end)
  Events:On("PLAYER_REGEN_DISABLED", Apply)
  Events:On("PLAYER_REGEN_ENABLED", Apply)
  Arrow:FollowStep()
  corpse()
end)

-- Ocultar el HUD y la flecha: dentro de mazmorras, bandas, campos de batalla y arenas (opción) y a mano
-- ("ocultar todo": clic en el botón del minimapa o /senda hide).
--   Senda.Visibility:Hidden()      -> true si ahora mismo HUD y flecha deben estar ocultos
--   Senda.Visibility:SetHidden(b)  -> oculta / muestra todo a mano (se guarda)
--   Senda.Visibility:Toggle()
-- Adaptado de Polestar (ocultar en mazmorras y botón "ocultar todo").
local _, Senda = ...
local Compat, Events = Senda.Compat, Senda.Events
local L = Senda.L

local Visibility = {}
Senda.Visibility = Visibility

local HIDE_TYPES = { party = true, raid = true, pvp = true, arena = true }
local inInstance = false

local function Opt(key) return Senda.Options:Get(key) end

function Visibility:InInstance() return inInstance end

function Visibility:Hidden()
  if Senda.db and Senda.db.hideAll then return true end
  return inInstance and Opt("hideInInstance") and true or false
end

local function Apply()
  if Senda.HUD and Senda.HUD.Apply then Senda.HUD:Apply() end
  if Senda.Arrow and Senda.Arrow.ApplyVisibility then Senda.Arrow:ApplyVisibility() end
end

-- Lee el tipo de instancia; si cambia, reaplica la visibilidad.
function Visibility:Update()
  local was = inInstance
  inInstance = HIDE_TYPES[Compat.InstanceType() or "none"] and true or false
  if was ~= inInstance then Apply() end
end

function Visibility:SetHidden(hidden)
  if not Senda.db then return end
  hidden = hidden and true or false
  if (Senda.db.hideAll and true or false) == hidden then return end
  Senda.db.hideAll = hidden or nil
  Apply()
  Senda:Print(hidden and L.HIDE_ALL_ON or L.HIDE_ALL_OFF)
end

function Visibility:Toggle()
  self:SetHidden(not (Senda.db and Senda.db.hideAll))
end

Senda.Options:Register({ key = "hideInInstance", label = L.OPT_HIDE_INSTANCE, tooltip = L.OPT_HIDE_INSTANCE_TIP,
  type = "toggle", default = true, section = L.OPT_SECTION_GENERAL, order = 30, onChange = Apply })

Events:On("SENDA_READY", function()
  Visibility:Update()
  Apply()
  local update = function() Visibility:Update() end
  Events:On("PLAYER_ENTERING_WORLD", update)
  Events:On("ZONE_CHANGED_NEW_AREA", update)
  -- Al cargar, el tipo de instancia puede tardar un instante en estar disponible.
  Compat.After(2, update)
end)

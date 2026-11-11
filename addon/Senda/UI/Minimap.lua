-- Botón del minimapa (arrastrable alrededor del minimapa, sin LibDBIcon).
-- Clic: panel. Clic derecho: HUD. Mayús+clic: flecha.
local _, Senda = ...
local Events = Senda.Events
local L = Senda.L

local button

local function Place()
  if not button or not Minimap then return end
  local a = math.rad(Senda.db.minimapAngle or 215)
  local r = (Minimap:GetWidth() or 140) / 2 + 10
  button:ClearAllPoints()
  button:SetPoint("CENTER", Minimap, "CENTER", math.cos(a) * r, math.sin(a) * r)
end

local function Create()
  if button or not Minimap then return end
  local b = CreateFrame("Button", "SendaMinimapButton", Minimap)
  b:SetSize(31, 31)
  b:SetFrameStrata("MEDIUM")
  b:SetFrameLevel((Minimap:GetFrameLevel() or 1) + 8)

  local bg = b:CreateTexture(nil, "BACKGROUND")
  bg:SetTexture("Interface\\Minimap\\UI-Minimap-Background")
  bg:SetSize(20, 20)
  bg:SetPoint("TOPLEFT", 7, -5)

  local icon = b:CreateTexture(nil, "ARTWORK")
  icon:SetTexture("Interface\\Icons\\INV_Misc_Map_01")
  icon:SetSize(18, 18)
  icon:SetPoint("TOPLEFT", 7, -6)
  icon:SetTexCoord(0.08, 0.92, 0.08, 0.92)

  local border = b:CreateTexture(nil, "OVERLAY")
  border:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")
  border:SetSize(53, 53)
  border:SetPoint("TOPLEFT")

  b:SetHighlightTexture("Interface\\Minimap\\UI-Minimap-ZoomButton-Highlight")
  b:RegisterForClicks("LeftButtonUp", "RightButtonUp")
  b:RegisterForDrag("LeftButton")

  b:SetScript("OnClick", function(_, btn)
    if btn == "RightButton" then
      Senda.HUD:Toggle()
    elseif IsShiftKeyDown() then
      Senda.Options:Set("arrow", not Senda.Options:Get("arrow"))
    else
      Senda.UI:TogglePanel()
    end
  end)
  b:SetScript("OnDragStart", function(self)
    self:LockHighlight()
    self:SetScript("OnUpdate", function()
      local mx, my = Minimap:GetCenter()
      local cx, cy = GetCursorPosition()
      local scale = Minimap:GetEffectiveScale()
      Senda.db.minimapAngle = math.deg(math.atan2(cy / scale - my, cx / scale - mx))
      Place()
    end)
  end)
  b:SetScript("OnDragStop", function(self)
    self:UnlockHighlight()
    self:SetScript("OnUpdate", nil)
  end)
  b:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_LEFT")
    GameTooltip:SetText("Senda", Senda.COLOR[1], Senda.COLOR[2], Senda.COLOR[3])
    local step = Senda.Engine and Senda.Engine:CurrentStep()
    if step and Senda.HUD then
      GameTooltip:AddLine(Senda.HUD:StepText(step), 1, 1, 1, true)
    end
    GameTooltip:AddLine(" ")
    for _, line in ipairs(L.MINIMAP_TIP_LINES) do GameTooltip:AddLine(line, 0.8, 0.8, 0.8) end
    GameTooltip:Show()
  end)
  b:SetScript("OnLeave", function() GameTooltip:Hide() end)
  button = b
  Place()
end

local function Apply()
  if not button then return end
  button:SetShown(Senda.Options:Get("minimap") and true or false)
end

Senda.Options:Register({ key = "minimap", label = L.OPT_MINIMAP, type = "toggle", default = true,
  section = L.OPT_SECTION_GENERAL, order = 10, onChange = Apply })

Events:On("SENDA_READY", function()
  Create()
  Apply()
end)

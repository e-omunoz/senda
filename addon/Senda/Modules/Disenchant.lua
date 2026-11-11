-- Senda / Modules / Disenchant
-- Botón «Desencantar» (botón de acción seguro): un clic = desencantar el siguiente verde que no te mejora.
-- Sin contaminar la interfaz: los atributos y mostrar/ocultar solo se tocan fuera de combate; al entrar en combate
-- se oculta (PLAYER_REGEN_DISABLED llega antes del bloqueo). Mayús+clic: no volver a proponer ese objeto.
-- Clic derecho y arrastrar: mover.
local ADDON, Senda = ...
local M = Senda.Mod
if not M then return end
local L = M.L

local D = {}
Senda.Modules.Disenchant = D

local DISENCHANT = 13262
local SKIP_LOC = { [""] = true, INVTYPE_NON_EQUIP_IGNORE = true, INVTYPE_BAG = true, INVTYPE_QUIVER = true,
  INVTYPE_AMMO = true, INVTYPE_TABARD = true, INVTYPE_BODY = true }

local btn

local function Keep()
  local db = M.DB()
  db.deKeep = db.deKeep or {}
  return db.deKeep
end

function D.Candidates()
  local out = {}
  local G = Senda.Modules.Gear
  local keep = Keep()
  local maxQ = M.Opt("mod_de_blue") and 3 or 2
  for _, it in ipairs(M.ScanBags()) do
    if it.link and it.quality and it.quality >= 2 and it.quality <= maxQ and not keep[it.id] and not it.locked then
      local _, loc = M.ItemInstant(it.link)
      if type(loc) == "string" and not SKIP_LOC[loc] then
        local upgrade = G and G.IsUpgrade and G.IsUpgrade(it.link)
        if not upgrade then table.insert(out, it) end
      end
    end
  end
  return out
end

function D.Update()
  if not btn or M.InCombat() then return end
  if M.Opt("mod_de") == false or not M.Known(DISENCHANT) then btn:Hide(); return end
  local c = D.Candidates()
  if #c == 0 then btn:Hide(); btn.link, btn.item = nil, nil; return end
  local it = c[1]
  btn:SetAttribute("macrotext", "/cast " .. (M.SpellName(DISENCHANT) or "Desencantar") .. "\n/use " .. it.bag .. " " .. it.slot)
  btn.link, btn.item = it.link, it.id
  local name = M.ItemInfo(it.link) or (L.MOD_DE_ITEM or "objeto")
  btn:SetText(string.format("%s: %s (%d)", L.MOD_DE_BUTTON or "Desencantar", name, #c))
  btn:Show()
end

local function Create()
  if btn or M.InCombat() then return end
  btn = CreateFrame("Button", "SendaDisenchantButton", UIParent, "SecureActionButtonTemplate,UIPanelButtonTemplate")
  btn:SetSize(280, 24)
  btn:SetAttribute("type", "macro")
  btn:SetAttribute("type2", "senda_noop")        -- el clic derecho solo sirve para arrastrar
  btn:SetAttribute("shift-type1", "senda_noop")  -- Mayús+clic: no desencanta, solo marca «conservar»
  btn:RegisterForClicks("AnyUp", "AnyDown")
  btn:SetMovable(true)
  btn:SetClampedToScreen(true)
  btn:RegisterForDrag("RightButton")
  btn:SetScript("OnDragStart", function(self) if not M.InCombat() then self:StartMoving() end end)
  btn:SetScript("OnDragStop", function(self)
    self:StopMovingOrSizing()
    local pt, _, rp, x, y = self:GetPoint()
    M.DB().dePoint = { pt, rp, x, y }
  end)
  btn:SetScript("OnEnter", function(self)
    if not self.link or not GameTooltip then return end
    GameTooltip:SetOwner(self, "ANCHOR_TOP")
    pcall(GameTooltip.SetHyperlink, GameTooltip, self.link)
    GameTooltip:AddLine(L.MOD_DE_HELP or "Clic: desencantar este objeto. Mayús+clic: no volver a proponerlo. Clic derecho y arrastrar: mover.", 1, 0.82, 0, true)
    GameTooltip:Show()
  end)
  btn:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
  btn:HookScript("OnClick", function(self, button, down)
    if down then return end
    if button == "LeftButton" and IsShiftKeyDown and IsShiftKeyDown() and self.item then
      Keep()[self.item] = true
      M.Print(string.format(L.MOD_DE_KEEP or "No volveré a proponer desencantar %s.", self.link or "?"))
      M.After(0.1, D.Update)
    end
  end)
  local p = M.DB().dePoint
  if type(p) == "table" and p[1] then
    btn:SetPoint(p[1], UIParent, p[2], p[3], p[4])
  else
    btn:SetPoint("CENTER", UIParent, "CENTER", 0, -230)
  end
  btn:Hide()
end

function D.ResetKeep()
  M.DB().deKeep = {}
  M.After(0.1, D.Update)
end

M.RegisterOption({ key = "mod_de", label = L.MOD_OPT_DE or "Botón Desencantar", type = "toggle", default = true,
  onChange = function() M.After(0.1, D.Update) end })
M.RegisterOption({ key = "mod_de_blue", label = L.MOD_OPT_DE_BLUE or "Desencantar: proponer también objetos azules", type = "toggle", default = false,
  onChange = function() M.After(0.1, D.Update) end })

M.OnReady(function() Create(); D.Update() end)
M.On("BAG_UPDATE_DELAYED", function() M.Debounce("de-update", 0.3, D.Update) end)
M.On("PLAYER_REGEN_ENABLED", function() if not btn then Create() end; D.Update() end)
M.On("PLAYER_REGEN_DISABLED", function() if btn and not InCombatLockdown() then btn:Hide() end end)
M.On("SPELLS_CHANGED", function() M.Debounce("de-update", 0.5, D.Update) end)

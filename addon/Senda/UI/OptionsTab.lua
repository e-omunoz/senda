-- Pestaña "Opciones": pinta todas las opciones registradas con Senda.Options:Register,
-- agrupadas por sección, y acciones de mantenimiento (reiniciar progreso, posiciones, exportar).
local _, Senda = ...
local UI, Events = Senda.UI, Senda.Events
local L = Senda.L

local tab = { controls = {}, headers = {} }

local function Layout()
  if not tab.child then return end
  local y = -6
  local lastSection
  local hi = 0
  for _, c in ipairs(tab.controls) do c:Hide() end
  for _, h in ipairs(tab.headers) do h:Hide(); h.line:Hide() end

  for _, o in ipairs(Senda.Options:List()) do
    local sec = o.section or L.OPT_SECTION_GENERAL
    if sec ~= lastSection then
      lastSection = sec
      hi = hi + 1
      local h = tab.headers[hi]
      if not h then
        h = UI:Label(tab.child, "", "GameFontNormal")
        h:SetTextColor(UI.C.accent[1], UI.C.accent[2], UI.C.accent[3])
        h.line = UI:Divider(tab.child, 0.8)
        tab.headers[hi] = h
      end
      y = y - (hi > 1 and 10 or 0)
      h:ClearAllPoints()
      h:SetPoint("TOPLEFT", 8, y)
      h:SetText(sec)
      h:Show()
      h.line:ClearAllPoints()
      h.line:SetPoint("TOPLEFT", 8, y - 16)
      h.line:SetPoint("RIGHT", tab.child, "RIGHT", -8, 0)
      h.line:Show()
      y = y - 24
    end
    local c = o.control
    if not c then
      local get = function() return Senda.Options:Get(o.key) end
      local set = function(v) Senda.Options:Set(o.key, v) end
      if o.type == "slider" then
        c = UI:Slider(tab.child, o.label, o.min or 0, o.max or 1, o.step or 0.05, get, set, o.format)
      else
        c = UI:Checkbox(tab.child, o.label, get, set, o.tooltip)
      end
      o.control = c
      tab.controls[#tab.controls + 1] = c
    end
    c:ClearAllPoints()
    c:SetPoint("TOPLEFT", 14, y)
    if c.Refresh then c:Refresh() end
    c:Show()
    y = y - (o.type == "slider" and 44 or 24)
  end
  tab.child:SetHeight(-y + 10)
end

local function Build(parent)
  local box = CreateFrame("Frame", nil, parent, BackdropTemplateMixin and "BackdropTemplate" or nil)
  UI:Backdrop(box, "inset")
  box:SetPoint("TOPLEFT")
  box:SetPoint("BOTTOMRIGHT", 0, 34)
  tab.sf, tab.child = UI:ScrollArea(box)

  local resetAt = 0
  local reset = UI:Button(parent, L.OPT_RESET_PROGRESS, 170, 24)
  reset:SetScript("OnClick", function(self)
    local now = GetTime()
    if now - resetAt > 5 then
      resetAt = now
      self:SetText(L.OPT_RESET_CONFIRM)
      Senda.Compat.After(5, function() self:SetText(L.OPT_RESET_PROGRESS) end)
      return
    end
    resetAt = 0
    self:SetText(L.OPT_RESET_PROGRESS)
    Senda.Engine:Reset()
    Senda:Print(L.SLASH_RESET_DONE)
  end)
  reset:SetPoint("BOTTOMLEFT", 0, 4)

  local pos = UI:Button(parent, L.OPT_RESET_POSITIONS, 170, 24, function()
    wipe(Senda.db.frames)
    Senda:Print(L.OPT_RESET_POSITIONS_DONE)
    if _G.ReloadUI then _G.ReloadUI() end
  end)
  pos:SetPoint("LEFT", reset, "RIGHT", 6, 0)

  local export = UI:Button(parent, L.OPT_EXPORT, 170, 24, function() Senda.Recorder:ShowExport() end)
  export:SetPoint("LEFT", pos, "RIGHT", 6, 0)
  UI:Tooltip(export, L.OPT_EXPORT, function()
    return string.format(L.RECORDER_COUNT, Senda.Recorder:Count())
  end)
end

UI:RegisterTab({
  key = "options",
  title = L.TAB_OPTIONS,
  icon = "Interface\\Icons\\INV_Misc_Gear_01",
  order = 99,
  build = Build,
  refresh = Layout,
})

Events:On("SENDA_OPTIONS_UPDATED", function() if UI:IsPanelShown() then Layout() end end)
Events:On("SENDA_OPTION_CHANGED", function()
  for _, c in ipairs(tab.controls) do if c.Refresh and c:IsShown() then c:Refresh() end end
end)

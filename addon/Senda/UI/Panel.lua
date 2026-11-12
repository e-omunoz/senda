-- Panel principal (/senda): ventana con pestañas laterales.
--   Senda.UI:RegisterTab({ key, title, icon, order, build = function(parent) end, refresh = function() end })
--   Senda.UI:ShowTab(key), :TogglePanel(), :ShowPanel(), :RefreshPanel()
-- Las pestañas se construyen la primera vez que se abren (build) y se refrescan cada vez que se muestran.
local _, Senda = ...
local UI = Senda.UI
local L = Senda.L

local tabs, tabByKey = {}, {}
local panel

local SIDEBAR_W = 168

local function SortTabs()
  table.sort(tabs, function(a, b)
    local oa, ob = a.order or 100, b.order or 100
    if oa ~= ob then return oa < ob end
    return tostring(a.title) < tostring(b.title)
  end)
end

local function LayoutSidebar()
  if not panel then return end
  SortTabs()
  for i, t in ipairs(tabs) do
    if not t.button then
      local b = UI:Button(panel.sidebar, "", SIDEBAR_W - 16, 26, function() UI:ShowTab(t.key) end)
      local fs = b:GetFontString()
      fs:ClearAllPoints()
      fs:SetPoint("LEFT", t.icon and 30 or 10, 0)
      fs:SetPoint("RIGHT", -6, 0)
      fs:SetJustifyH("LEFT")
      if t.icon then
        local ic = b:CreateTexture(nil, "ARTWORK")
        ic:SetSize(16, 16)
        ic:SetPoint("LEFT", 8, 0)
        ic:SetTexture(t.icon)
        ic:SetTexCoord(0.08, 0.92, 0.08, 0.92)
      end
      b:SetText(t.title)
      t.button = b
    end
    t.button:ClearAllPoints()
    t.button:SetPoint("TOPLEFT", 8, -8 - (i - 1) * 30)
  end
end

function UI:RegisterTab(t)
  if type(t) ~= "table" or not t.key then return end
  if tabByKey[t.key] then
    for k, v in pairs(t) do tabByKey[t.key][k] = v end
    return
  end
  tabs[#tabs + 1] = t
  tabByKey[t.key] = t
  LayoutSidebar()
end

local function Create()
  if panel then return panel end
  panel = UI:Frame("SendaMainFrame", UIParent, { title = "Senda", width = 780, height = 520,
    posKey = "main", strata = "HIGH" })
  panel:SetToplevel(true)
  panel:Hide()
  tinsert(UISpecialFrames, "SendaMainFrame")

  panel.subtitle = UI:Label(panel.header, "", "GameFontDisableSmall")
  panel.subtitle:SetPoint("LEFT", panel.title, "RIGHT", 10, 0)

  local sidebar = CreateFrame("Frame", nil, panel, BackdropTemplateMixin and "BackdropTemplate" or nil)
  UI:Backdrop(sidebar, "inset")
  sidebar:SetPoint("TOPLEFT", 8, -34)
  sidebar:SetPoint("BOTTOMLEFT", 8, 8)
  sidebar:SetWidth(SIDEBAR_W)
  panel.sidebar = sidebar

  local ver = UI:Label(sidebar, "v" .. Senda.VERSION, "GameFontDisableSmall")
  ver:SetPoint("BOTTOMLEFT", 10, 8)

  local content = CreateFrame("Frame", nil, panel)
  content:SetPoint("TOPLEFT", sidebar, "TOPRIGHT", 8, 0)
  content:SetPoint("BOTTOMRIGHT", -8, 8)
  panel.content = content

  panel:SetScript("OnShow", function() UI:RefreshPanel() end)
  LayoutSidebar()
  return panel
end

function UI:ShowTab(key)
  Create()
  local t = tabByKey[key] or tabs[1]
  if not t then return end
  for _, o in ipairs(tabs) do
    if o.frame then o.frame:Hide() end
    if o.button then o.button:SetActive(o == t) end
  end
  if not t.frame then
    local f = CreateFrame("Frame", nil, panel.content)
    f:SetAllPoints()
    t.frame = f
    if t.build then
      local ok, err = pcall(t.build, f)
      if not ok then
        local e = UI:Label(f, "Error: " .. tostring(err))
        e:SetPoint("TOPLEFT", 8, -8)
        e:SetPoint("RIGHT", -8, 0)
        Senda:ReportError(err)
      end
    end
  end
  t.frame:Show()
  panel.activeTab = t.key
  Senda.db.lastTab = t.key
  if t.refresh then pcall(t.refresh) end
end

function UI:RefreshPanel()
  if not panel or not panel:IsShown() then return end
  local g = Senda.Engine and Senda.Engine:Guide()
  panel.subtitle:SetText(g and (g.title or g.id) or L.NO_GUIDE)
  local t = tabByKey[panel.activeTab]
  if t and t.refresh and t.frame and t.frame:IsShown() then pcall(t.refresh) end
end

function UI:ShowPanel(key)
  Create()
  panel:Show()
  self:ShowTab(key or panel.activeTab or Senda.db.lastTab or (tabs[1] and tabs[1].key))
end

function UI:TogglePanel()
  if panel and panel:IsShown() then panel:Hide() else self:ShowPanel() end
end

function UI:IsPanelShown()
  return panel and panel:IsShown() or false
end

-- Refresco del panel cuando cambia la guía o el paso.
Senda.Events:On("SENDA_STEP_CHANGED", function() UI:RefreshPanel() end)
Senda.Events:On("SENDA_GUIDE_CHANGED", function() UI:RefreshPanel() end)

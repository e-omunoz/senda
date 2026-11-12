-- Pestaña «Objetos»: caja de búsqueda sobre Senda.Lookup (Modules/Lookup.lua).
--   Escribe parte del nombre (o el número) y pulsa Intro: lista de resultados con «Señalar» (flecha a la fuente
--   más cercana); al elegir uno se ve de dónde sale (botín, vendedores, recompensas y objetivos de misión).
--   Senda.LookupTab:Search(texto)  -- abre la pestaña y busca (la usa /senda objeto si se quiere)
local _, Senda = ...
local UI, Events, Compat = Senda.UI, Senda.Events, Senda.Compat
local L = Senda.L

local LookupTab = {}
Senda.LookupTab = LookupTab

local ROW_H = 24
local ROWS = 8
local DEBOUNCE = 0.4
local tab = { results = {}, rows = {} }

local function ItemName(id)
  return Senda.Names:Get("item", id) or Senda.Names:Placeholder("item", id)
end

local function Resolve(text)
  return Senda.Names:Resolve(text)
end

------------------------------------------------------------------------------
-- Pintado
------------------------------------------------------------------------------

local function ShowDetail()
  local id = tab.selected
  if not id then
    tab.detail:SetText(L.LOOKUP_TAB_SELECT, true)
    return
  end
  local lines = { UI:Color("accent", Resolve(string.format(L.LOOKUP_HEADER, ItemName(id), id))) }
  for _, line in ipairs(Senda.Lookup.Lines(id)) do lines[#lines + 1] = "  " .. Resolve(line) end
  tab.detail:SetText(table.concat(lines, "\n"), true)
end

local function Row(i)
  local r = tab.rows[i]
  if r then return r end
  r = CreateFrame("Button", nil, tab.list)
  r:SetHeight(ROW_H)
  r:SetPoint("TOPLEFT", 0, -(i - 1) * ROW_H)
  r:SetPoint("RIGHT", tab.list, "RIGHT", -2, 0)
  r.bg = r:CreateTexture(nil, "BACKGROUND")
  r.bg:SetAllPoints()
  r.bg:SetColorTexture(UI.C.accent[1], UI.C.accent[2], UI.C.accent[3], 0.14)
  r.bg:Hide()
  r.text = UI:Label(r, "", "GameFontHighlightSmall")
  r.text:SetPoint("LEFT", 6, 0)
  r.text:SetWordWrap(false)
  r.point = UI:Button(r, L.LOOKUP_POINT, 74, 20, function()
    if r.id then
      Senda.Lookup.Point(r.id)
      LookupTab:Refresh()
    end
  end)
  r.point:SetPoint("RIGHT", -2, 0)
  UI:Tooltip(r.point, L.LOOKUP_POINT, L.LOOKUP_POINT_TIP)
  r.text:SetPoint("RIGHT", r.point, "LEFT", -6, 0)
  r:RegisterForClicks("LeftButtonUp")
  r:SetScript("OnClick", function()
    tab.selected = r.id
    LookupTab:Refresh()
  end)
  tab.rows[i] = r
  return r
end

function LookupTab:Refresh()
  if not tab.built then return end
  local Lookup = Senda.Lookup
  tab.clear:SetEnabled(Senda.Arrow ~= nil and Senda.Arrow:Has("lookup"))
  local shown = #tab.results
  for i = 1, ROWS do
    local r = Row(i)
    local res = tab.results[i]
    if res then
      local id = res[1]
      r.id = id
      local line = ItemName(id)
      local sum = Lookup.Summary(id)
      if sum then line = line .. "  |cff8a929c" .. Resolve(sum) .. "|r" end
      r.text:SetText(line)
      r.point:SetEnabled(Lookup.CanPoint(id))
      r.bg:SetShown(id == tab.selected)
      r:Show()
    else
      r.id = nil
      r:Hide()
    end
  end
  if tab.searching then
    tab.status:SetText(L.LOOKUP_TAB_SEARCHING)
  elseif tab.query == nil then
    tab.status:SetText(L.LOOKUP_TAB_EMPTY)
  elseif shown == 0 then
    tab.status:SetText(tab.reason and (L["LOOKUP_ERR_" .. tab.reason:upper()] or "") or string.format(L.LOOKUP_TAB_NONE, tab.query))
  else
    local info = tab.info or {}
    tab.status:SetText(string.format(L.LOOKUP_TAB_COUNT, info.total or shown, info.named or 0, info.items or 0))
  end
  ShowDetail()
end

------------------------------------------------------------------------------
-- Búsqueda
------------------------------------------------------------------------------

function LookupTab:DoSearch(query)
  query = query or (tab.box and tab.box:GetText()) or ""
  query = query:gsub("^%s+", ""):gsub("%s+$", "")
  if query == "" then
    tab.query, tab.results, tab.info, tab.reason, tab.searching = nil, {}, nil, nil, false
    Senda.Lookup.CancelSearch()
    self:Refresh()
    return
  end
  tab.query = query
  tab.reason = nil
  tab.searching = true
  local started = Senda.Lookup.Search(query, function(results, info)
    tab.searching = false
    tab.results, tab.info, tab.reason = results or {}, info, info and info.reason
    if info and info.reason == "short" then tab.reason = nil; tab.results = {} end
    tab.selected = tab.results[1] and tab.results[1][1] or nil
    LookupTab:Refresh()
  end)
  if not started then tab.searching = false end
  self:Refresh()
end

-- Abre la pestaña con esa búsqueda.
function LookupTab:Search(query)
  UI:ShowPanel("lookup")
  if tab.box then tab.box:SetText(query or "") end
  self:DoSearch(query)
end

local function OnTextChanged(_, user)
  if not user then return end
  tab.typed = (tab.typed or 0) + 1
  local n = tab.typed
  Compat.After(DEBOUNCE, function()
    if n == tab.typed then LookupTab:DoSearch() end
  end)
end

------------------------------------------------------------------------------
-- Construcción
------------------------------------------------------------------------------

local function Build(parent)
  tab.intro = UI:Label(parent, L.LOOKUP_TAB_INTRO, "GameFontHighlightSmall")
  tab.intro:SetPoint("TOPLEFT", 6, -4)
  tab.intro:SetPoint("RIGHT", -6, 0)
  tab.intro:SetTextColor(0.75, 0.77, 0.8)

  local box = CreateFrame("EditBox", nil, parent, BackdropTemplateMixin and "BackdropTemplate" or nil)
  UI:Backdrop(box, "inset")
  box:SetAutoFocus(false)
  box:SetFontObject("ChatFontNormal")
  box:SetHeight(26)
  box:SetTextInsets(8, 8, 0, 0)
  box:SetMaxLetters(60)
  box:SetPoint("TOPLEFT", 6, -44)
  box.hint = UI:Label(box, L.LOOKUP_TAB_HINT, "GameFontDisableSmall")
  box.hint:SetPoint("LEFT", 10, 0)
  box:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
  box:SetScript("OnEnterPressed", function(self)
    self:ClearFocus()
    LookupTab:DoSearch()
  end)
  box:SetScript("OnTextChanged", function(self, user)
    self.hint:SetShown((self:GetText() or "") == "")
    OnTextChanged(self, user)
  end)
  tab.box = box

  tab.go = UI:Button(parent, L.LOOKUP_SEARCH, 80, 26, function() LookupTab:DoSearch() end)
  tab.go:SetPoint("TOPRIGHT", -6, -44)
  tab.clear = UI:Button(parent, L.LOOKUP_CLEAR_ARROW, 110, 26, function()
    Senda.Lookup.ClearPoint()
    LookupTab:Refresh()
  end)
  tab.clear:SetPoint("RIGHT", tab.go, "LEFT", -4, 0)
  box:SetPoint("RIGHT", tab.clear, "LEFT", -6, 0)

  tab.status = UI:Label(parent, "", "GameFontDisableSmall")
  tab.status:SetPoint("TOPLEFT", 8, -76)
  tab.status:SetPoint("RIGHT", -6, 0)

  tab.list = CreateFrame("Frame", nil, parent, BackdropTemplateMixin and "BackdropTemplate" or nil)
  UI:Backdrop(tab.list, "inset")
  tab.list:SetPoint("TOPLEFT", 6, -94)
  tab.list:SetPoint("RIGHT", -6, 0)
  tab.list:SetHeight(ROWS * ROW_H + 4)

  local area = CreateFrame("Frame", nil, parent, BackdropTemplateMixin and "BackdropTemplate" or nil)
  UI:Backdrop(area, "inset")
  area:SetPoint("TOPLEFT", tab.list, "BOTTOMLEFT", 0, -8)
  area:SetPoint("BOTTOMRIGHT", -6, 0)
  tab.detail = UI:ScrollText(area)

  tab.built = true
end

UI:RegisterTab({
  key = "lookup",
  title = L.TAB_LOOKUP,
  icon = "Interface\\Icons\\INV_Misc_Spyglass_03",
  order = 14,
  build = Build,
  refresh = function() LookupTab:Refresh() end,
})

-- Los nombres llegan después de pedirlos: se repinta una vez (agrupado por Senda.Names).
Events:On("SENDA_NAMES_UPDATED", function()
  if tab.built and UI:IsPanelShown() then LookupTab:Refresh() end
end)
Events:On("SENDA_ARROW_TARGET", function()
  if tab.built and UI:IsPanelShown() then LookupTab:Refresh() end
end)

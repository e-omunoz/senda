-- Pestaña "Guía": selector de guía y de sección, lista completa de pasos con su estado.
-- Clic en un paso: saltar a él. Clic derecho: marcar / desmarcar como hecho.
local _, Senda = ...
local UI, Events = Senda.UI, Senda.Events
local L = Senda.L
local Cond = Senda.Conditions

local ROW_H = 22
local view = { secIndex = nil } -- sección que se está viendo (nil = la del paso actual)
local tab = {}

local function Sections()
  local out, seen = {}, {}
  for _, e in ipairs(Senda.Engine:Steps()) do
    if not seen[e.secIndex] then
      seen[e.secIndex] = true
      local s = e.section
      local lv = s.levels and string.format(" (%d-%d)", s.levels[1] or 0, s.levels[2] or 0) or ""
      out[#out + 1] = { value = e.secIndex, text = (s.title or s.id) .. lv, section = s }
    end
  end
  return out
end

local function CurrentSecIndex()
  local e = Senda.Engine:Entry()
  if e then return e.secIndex end
  local steps = Senda.Engine:Steps()
  return steps[#steps] and steps[#steps].secIndex
end

local function Build(parent)
  -- Barra superior
  tab.guideDD = UI:Dropdown(parent, 230, function()
    local items = {}
    local valid = {}
    for _, g in ipairs(Senda.Guides:ForPlayer()) do valid[g.id] = true end
    for _, g in ipairs(Senda.Guides:List()) do
      local t = g.title or g.id
      if not valid[g.id] then t = UI:Color("dim", t .. " " .. L.GUIDE_NOT_FOR_YOU) end
      items[#items + 1] = { value = g.id, text = t }
    end
    return items
  end, function(id)
    view.secIndex = nil
    Senda.Engine:SetGuide(id)
  end)
  tab.guideDD:SetPoint("TOPLEFT", 4, -4)

  tab.secDD = UI:Dropdown(parent, 250, Sections, function(secIndex)
    view.secIndex = secIndex
    tab.Refresh()
  end)
  tab.secDD:SetPoint("LEFT", tab.guideDD, "RIGHT", 6, 0)

  tab.current = UI:Button(parent, L.GUIDE_TAB_CURRENT, 90, 22, function()
    view.secIndex = nil
    tab.Refresh(true)
  end)
  tab.current:SetPoint("TOPRIGHT", -4, -4)

  -- Resumen de sección
  tab.summary = UI:Label(parent, "", "GameFontHighlightSmall")
  tab.summary:SetPoint("TOPLEFT", tab.guideDD, "BOTTOMLEFT", 2, -8)
  tab.summary:SetPoint("RIGHT", -6, 0)
  tab.summary:SetTextColor(0.75, 0.77, 0.8)

  tab.progress = UI:Label(parent, "", "GameFontDisableSmall")
  tab.progress:SetPoint("BOTTOMLEFT", 6, 4)

  -- Lista
  local box = CreateFrame("Frame", nil, parent, BackdropTemplateMixin and "BackdropTemplate" or nil)
  UI:Backdrop(box, "inset")
  box:SetPoint("TOPLEFT", 0, -56)
  box:SetPoint("BOTTOMRIGHT", 0, 22)
  tab.box = box
  tab.sf, tab.child = UI:ScrollArea(box)
  tab.rows = {}
end

local function Row(i)
  local r = tab.rows[i]
  if r then return r end
  r = CreateFrame("Button", nil, tab.child)
  r:SetHeight(ROW_H)
  r:RegisterForClicks("LeftButtonUp", "RightButtonUp")
  r.bg = r:CreateTexture(nil, "BACKGROUND")
  r.bg:SetAllPoints()
  local hl = r:CreateTexture(nil, "HIGHLIGHT")
  hl:SetAllPoints()
  hl:SetColorTexture(1, 1, 1, 0.05)
  r.state = r:CreateTexture(nil, "ARTWORK")
  r.state:SetSize(14, 14)
  r.state:SetPoint("LEFT", 4, 0)
  r.icon = r:CreateTexture(nil, "ARTWORK")
  r.icon:SetSize(16, 16)
  r.icon:SetPoint("LEFT", r.state, "RIGHT", 4, 0)
  r.icon:SetTexCoord(0.06, 0.94, 0.06, 0.94)
  r.text = r:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  r.text:SetPoint("LEFT", r.icon, "RIGHT", 6, 0)
  r.text:SetPoint("RIGHT", -18, 0)
  r.text:SetJustifyH("LEFT")
  r.text:SetWordWrap(false)
  r.dot = r:CreateTexture(nil, "ARTWORK")
  r.dot:SetSize(10, 10)
  r.dot:SetPoint("RIGHT", -4, 0)
  r:SetScript("OnClick", function(self, btn)
    if not self.entry then return end
    if btn == "RightButton" then
      if Senda.Engine:IsDone(self.entry) then
        Senda.Engine:Unmark(self.entry.step.id)
      else
        Senda.Engine:Complete(self.entry.step.id)
      end
    else
      Senda.Engine:JumpTo(self.entry.index)
    end
    tab.Refresh()
  end)
  r:SetScript("OnEnter", function(self)
    local e = self.entry
    if not e then return end
    local HUD = Senda.HUD
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    local title = HUD:StepTitle(e.step)
    GameTooltip:SetText(HUD:TypeLabel(e.step) .. (title ~= "" and (": " .. title) or ""), 1, 1, 1)
    GameTooltip:AddLine(HUD:StepText(e.step), 0.85, 0.85, 0.85, true)
    if e.step.tip then GameTooltip:AddLine(e.step.tip, 1, 0.82, 0.25, true) end
    local st = HUD.STATUS[e.step.status or ""]
    if st then GameTooltip:AddLine(L[st[2]], 0.6, 0.6, 0.6) end
    GameTooltip:AddLine(e.step.id, 0.45, 0.45, 0.45)
    GameTooltip:AddLine(L.GUIDE_TAB_ROW_HINT, 0.45, 0.8, 0.65, true)
    GameTooltip:Show()
  end)
  r:SetScript("OnLeave", function() GameTooltip:Hide() end)
  tab.rows[i] = r
  return r
end

function tab.Refresh(scrollToCurrent)
  if not tab.rows then return end
  local Engine = Senda.Engine
  local g = Engine:Guide()
  tab.guideDD:SetValue(g and g.id, g and (g.title or g.id) or L.NO_GUIDE)

  local cur = CurrentSecIndex()
  local secIndex = view.secIndex or cur
  local secs = Sections()
  local secItem
  for _, s in ipairs(secs) do if s.value == secIndex then secItem = s end end
  tab.secDD:SetValue(secIndex, secItem and secItem.text or "—")
  tab.summary:SetText(secItem and secItem.section.summary or "")

  local done, total = Engine:Progress()
  local pct = total > 0 and math.floor(done / total * 100) or 0
  tab.progress:SetText(string.format(L.GUIDE_TAB_PROGRESS, done, total, pct))

  local n, currentRow = 0, nil
  for _, e in ipairs(Engine:Steps()) do
    if e.secIndex == secIndex then
      n = n + 1
      local r = Row(n)
      r.entry = e
      r:ClearAllPoints()
      r:SetPoint("TOPLEFT", 0, -(n - 1) * ROW_H)
      r:SetPoint("RIGHT", tab.child, "RIGHT")
      local mark = Engine:IsDone(e)
      local isCurrent = e.index == Engine:Index()
      local applicable = Cond:LevelFilter(e.step["if"])
      if isCurrent then
        r.bg:SetColorTexture(UI.C.accent[1], UI.C.accent[2], UI.C.accent[3], 0.18)
        currentRow = n
      elseif n % 2 == 0 then
        r.bg:SetColorTexture(1, 1, 1, 0.025)
      else
        r.bg:SetColorTexture(0, 0, 0, 0)
      end
      if mark == "s" then
        r.state:SetTexture("Interface\\RaidFrame\\ReadyCheck-NotReady")
      elseif mark then
        r.state:SetTexture("Interface\\RaidFrame\\ReadyCheck-Ready")
      elseif isCurrent then
        r.state:SetTexture("Interface\\ChatFrame\\ChatFrameExpandArrow")
      else
        r.state:SetTexture(nil)
      end
      r.icon:SetTexture(Cond:Icon(e.step))
      local title = Senda.HUD:StepTitle(e.step)
      local text = Senda.HUD:StepText(e.step)
      local line = title ~= "" and (UI:Color("accent", title) .. "  " .. text) or text
      if e.step.optional then line = line .. " " .. UI:Color("dim", L.OPTIONAL_TAG) end
      if not applicable then line = UI:Color("dim", line .. " " .. L.NOT_APPLICABLE) end
      r.text:SetText(line)
      r.text:SetAlpha((mark and not isCurrent) and 0.55 or 1)
      local st = Senda.HUD.STATUS[e.step.status or ""]
      r.dot:SetTexture(st and st[1] or nil)
      r:Show()
    end
  end
  for i = n + 1, #tab.rows do tab.rows[i]:Hide() end
  tab.child:SetHeight(math.max(n * ROW_H, 10))

  if n == 0 then
    tab.summary:SetText(g and L.GUIDE_TAB_EMPTY or L.NO_GUIDE_HINT)
  end
  if scrollToCurrent ~= false and currentRow and not view.secIndex then
    local target = math.max(0, (currentRow - 4) * ROW_H)
    local maxScroll = tab.sf:GetVerticalScrollRange() or 0
    tab.sf:SetVerticalScroll(math.min(target, maxScroll))
  end
end

UI:RegisterTab({
  key = "guide",
  title = L.TAB_GUIDE,
  icon = "Interface\\Icons\\INV_Misc_Map_01",
  order = 10,
  build = Build,
  refresh = function() tab.Refresh() end,
})

-- Refresco en vivo mientras el panel está abierto.
local pending = false
local function Live()
  if pending or not UI:IsPanelShown() then return end
  pending = true
  Senda.Compat.After(0.3, function()
    pending = false
    if UI:IsPanelShown() then tab.Refresh(false) end
  end)
end
Events:On("SENDA_STEP_COMPLETED", Live)
Events:On("SENDA_STEP_UPDATED", Live)
Events:On("SENDA_GUIDE_CHANGED", function() view.secIndex = nil end)

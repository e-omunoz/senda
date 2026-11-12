-- Pestaña «Aparte»: tres bloques coordinados (Engine/Aside.lua, Engine/Reserve.lua).
--   Para después:  lo aparcado con cuándo y dónde lo dejaste y su pista; «Retomar» (desvío) y «A la ruta».
--   Reserva de XP: misiones que puedes coger ya cerca, por XP por minuto; «Más misiones aquí», «Coger» y
--                  «Coger las que me faltan» (las justas para el nivel que te falta).
--   Desvío activo: sus pasos con su estado y «Cancelar desvío».
--   Senda.AsideTab:Open(block)  -- abre la pestaña en "parked" | "reserve" | "detour" (la línea del HUD)
local _, Senda = ...
local UI, Events, Compat = Senda.UI, Senda.Events, Senda.Compat
local L = Senda.L
local Cond = Senda.Conditions

local AsideTab = {}
Senda.AsideTab = AsideTab

local ROW_H = 34
local tab = {}
local BLOCKS = { "parked", "reserve", "detour" }
local TITLES = { parked = "ASIDE_BLOCK_PARKED", reserve = "ASIDE_BLOCK_RESERVE", detour = "ASIDE_BLOCK_DETOUR" }
local ICONS = { parked = "Interface\\Icons\\INV_Misc_PocketWatch_01", reserve = "Interface\\Icons\\INV_Misc_Book_08",
  detour = "Interface\\Icons\\Ability_Tracking" }

local function HUD() return Senda.HUD end

local function MapName(map)
  return map and (Senda.Names:Get("map", map) or Compat.MapName(map)) or "?"
end

local function Dist(m)
  if not m then return L.ASIDE_RESERVE_HERE end
  if m >= 1000 then return string.format("%.1f km", m / 1000) end
  return string.format("%d m", math.floor(m + 0.5))
end

------------------------------------------------------------------------------
-- Construcción
------------------------------------------------------------------------------

local function Block(key)
  local b = CreateFrame("Frame", nil, tab.child, BackdropTemplateMixin and "BackdropTemplate" or nil)
  UI:Backdrop(b, "inset")
  b.icon = b:CreateTexture(nil, "ARTWORK")
  b.icon:SetSize(16, 16)
  b.icon:SetPoint("TOPLEFT", 8, -7)
  b.icon:SetTexture(ICONS[key])
  b.icon:SetTexCoord(0.08, 0.92, 0.08, 0.92)
  b.title = UI:Label(b, L[TITLES[key]], "GameFontNormal")
  b.title:SetPoint("LEFT", b.icon, "RIGHT", 6, 0)
  b.status = UI:Label(b, "", "GameFontHighlightSmall")
  b.status:SetPoint("TOPLEFT", 10, -30)
  b.status:SetPoint("RIGHT", -10, 0)
  b.status:SetTextColor(0.75, 0.77, 0.8)
  b.flash = b:CreateTexture(nil, "BACKGROUND", nil, 1)
  b.flash:SetAllPoints()
  b.flash:SetColorTexture(UI.C.accent[1], UI.C.accent[2], UI.C.accent[3], 0.12)
  b.flash:Hide()
  b.rows = {}
  b.key = key
  return b
end

local function Row(b, i)
  local r = b.rows[i]
  if r then return r end
  r = CreateFrame("Frame", nil, b)
  r:SetHeight(ROW_H)
  r.state = r:CreateTexture(nil, "ARTWORK")
  r.state:SetSize(14, 14)
  r.state:SetPoint("TOPLEFT", 0, -2)
  r.text = UI:Label(r, "", "GameFontHighlightSmall")
  r.text:SetPoint("TOPLEFT", 20, -2)
  r.text:SetWordWrap(false)
  r.sub = UI:Label(r, "", "GameFontDisableSmall")
  r.sub:SetPoint("TOPLEFT", r.text, "BOTTOMLEFT", 0, -2)
  r.sub:SetWordWrap(false)
  r.b1 = UI:Button(r, "", 86, 20)
  r.b1:SetPoint("TOPRIGHT", 0, -4)
  r.b2 = UI:Button(r, "", 86, 20)
  r.b2:SetPoint("RIGHT", r.b1, "LEFT", -4, 0)
  r.text:SetPoint("RIGHT", r.b2, "LEFT", -6, 0)
  r.sub:SetPoint("RIGHT", r.b2, "LEFT", -6, 0)
  UI:Tooltip(r.b1, function(self) return rawget(self, "tipTitle") end, function(self) return rawget(self, "tip") end)
  UI:Tooltip(r.b2, function(self) return rawget(self, "tipTitle") end, function(self) return rawget(self, "tip") end)
  b.rows[i] = r
  return r
end

local function SetButton(btn, text, tipTitle, tip, fn)
  if not text then btn:Hide(); return end
  btn:SetText(text)
  btn.tipTitle, btn.tip = tipTitle, tip
  btn:SetScript("OnClick", function() fn(); AsideTab:Refresh() end)
  btn:SetEnabled(true)
  btn:Show()
end

local function Build(parent)
  tab.intro = UI:Label(parent, L.ASIDE_TAB_INTRO, "GameFontHighlightSmall")
  tab.intro:SetPoint("TOPLEFT", 6, -4)
  tab.intro:SetPoint("RIGHT", -6, 0)
  tab.intro:SetTextColor(0.75, 0.77, 0.8)
  local box = CreateFrame("Frame", nil, parent)
  box:SetPoint("TOPLEFT", 0, -40)
  box:SetPoint("BOTTOMRIGHT", 0, 0)
  tab.sf, tab.child = UI:ScrollArea(box)
  tab.blocks = {}
  for _, key in ipairs(BLOCKS) do tab.blocks[key] = Block(key) end
  -- Botones de cabecera de cada bloque
  local res = tab.blocks.reserve
  res.more = UI:Button(res, L.ASIDE_RESERVE_MORE, 140, 20, function()
    Senda.Reserve:Ask()
    AsideTab:Refresh()
  end)
  res.more:SetPoint("TOPRIGHT", -8, -5)
  UI:Tooltip(res.more, L.ASIDE_RESERVE_MORE, L.ASIDE_RESERVE_MORE_TIP)
  res.plan = UI:Button(res, L.ASIDE_RESERVE_TAKE_PLAN, 160, 20, function() AsideTab:TakePlan() end)
  res.plan:SetPoint("RIGHT", res.more, "LEFT", -4, 0)
  UI:Tooltip(res.plan, L.ASIDE_RESERVE_TAKE_PLAN, L.ASIDE_RESERVE_TAKE_PLAN_TIP)
  local det = tab.blocks.detour
  det.cancel = UI:Button(det, L.ASIDE_CANCEL, 130, 20, function()
    Senda.Aside:Cancel()
    AsideTab:Refresh()
  end)
  det.cancel:SetPoint("TOPRIGHT", -8, -5)
  UI:Tooltip(det.cancel, L.ASIDE_HUD_CANCEL, L.ASIDE_HUD_CANCEL_TIP)
end

------------------------------------------------------------------------------
-- Acciones
------------------------------------------------------------------------------

local function StartOrAdd(items)
  local A = Senda.Aside
  if A:Active() then return A:Add(items) end
  return A:Start(items)
end

function AsideTab:Take(q)
  return StartOrAdd({ { kind = "reserve", quest = q } })
end

function AsideTab:TakePlan()
  local st = Senda.Reserve:State()
  local list = st.plan or st.offers or {}
  local items = {}
  for _, o in ipairs(list) do items[#items + 1] = { kind = "reserve", quest = o.e.quest } end
  if #items > 0 then StartOrAdd(items) end
  self:Refresh()
end

function AsideTab:Resume(key)
  return StartOrAdd({ { kind = "parked", key = key } })
end

------------------------------------------------------------------------------
-- Refresco
------------------------------------------------------------------------------

local function InDetour()
  local out = {}
  for _, it in ipairs(Senda.Aside:Items()) do
    if it.kind == "reserve" then out[it.quest] = true elseif it.kind == "parked" then out[it.key] = true end
  end
  return out
end

local function FillParked(b, width)
  local E, A = Senda.Engine, Senda.Aside
  local list = E.Parked and E:Parked() or {}
  local inDetour = InDetour()
  b.status:SetText(#list == 0 and L.ASIDE_PARKED_EMPTY or "")
  local n = 0
  for _, it in ipairs(list) do
    n = n + 1
    local r = Row(b, n)
    r.item = it
    r.state:SetTexture("Interface\\Icons\\INV_Misc_PocketWatch_01")
    local steps = #it.steps
    r.text:SetText(UI:Color("accent", A:ItemName(it)) .. UI:Color("dim", "  · " ..
      (steps == 1 and L.ASIDE_PARKED_STEPS_1 or string.format(L.ASIDE_PARKED_STEPS, steps))))
    local sub = string.format(L.ASIDE_PARKED_WHEN, it.level or 0, MapName(it.map))
    if it.hint then sub = string.format(L.ASIDE_PARKED_HINT, Senda.Names:Resolve(it.hint)) .. " · " .. sub end
    r.sub:SetText(sub)
    if inDetour[it.key] then
      SetButton(r.b1, L.ASIDE_RESERVE_IN_DETOUR, nil, nil, function() end)
      r.b1:SetEnabled(false)
      r.b2:Hide()
    else
      SetButton(r.b1, L.ASIDE_RESUME, L.ASIDE_RESUME, L.ASIDE_RESUME_TIP, function() AsideTab:Resume(it.key) end)
      SetButton(r.b2, L.ASIDE_UNPARK, L.ASIDE_UNPARK, L.ASIDE_UNPARK_TIP, function() E:Unpark(it.key) end)
    end
  end
  return n
end

local function FillReserve(b)
  local R = Senda.Reserve
  local st = R:State()
  local inDetour = InDetour()
  local HUDm = HUD()
  local Th = HUDm and HUDm.Thousands or tostring
  local status
  if st.loading then
    status = L.ASIDE_RESERVE_LOADING
  elseif not st.reason then
    status = L.ASIDE_RESERVE_IDLE
  elseif #(st.offers or {}) == 0 then
    status = st.need and string.format(L.RESERVE_NEED_NONE, Th(st.need.xp)) or L.ASIDE_RESERVE_EMPTY
  elseif st.reason == "gate" then
    status = string.format(L.RESERVE_NEED, Th(st.need.xp), math.max(1, math.floor((st.planMins or 0) + 0.5)))
  else
    status = ""
  end
  b.status:SetText(status)
  b.plan:SetShown(st.reason == "gate" and #(st.plan or {}) > 0)
  local inPlan = {}
  for _, o in ipairs(st.plan or {}) do inPlan[o.e.quest] = true end
  local n = 0
  for _, o in ipairs(st.offers or {}) do
    n = n + 1
    local r = Row(b, n)
    local e = o.e
    r.state:SetTexture(inPlan[e.quest] and "Interface\\RaidFrame\\ReadyCheck-Ready" or "Interface\\GossipFrame\\AvailableQuestIcon")
    local name = Senda.Names:Get("quest", e.quest) or Senda.Names:Placeholder("quest", e.quest)
    r.text:SetText(UI:Color("accent", name) .. UI:Color("dim", "  " .. string.format(L.ASIDE_RESERVE_ROW, Th(o.xp),
      math.max(1, math.floor(o.mins + 0.5)), Dist(o.dist))))
    local giver = e.giver.kind == "o" and ("{obj:" .. e.giver.id .. "}") or ("{npc:" .. e.giver.id .. "}")
    local sub = Senda.Names:Resolve(giver) .. " · " .. MapName(e.giver.at[1])
    local dec = L["ASIDE_RESERVE_DEC_" .. (e.decision or "keep")]
    if dec and dec ~= "" then sub = sub .. " · " .. dec end
    r.sub:SetText(sub)
    if inDetour[e.quest] then
      SetButton(r.b1, L.ASIDE_RESERVE_IN_DETOUR, nil, nil, function() end)
      r.b1:SetEnabled(false)
    else
      SetButton(r.b1, L.ASIDE_RESERVE_TAKE, L.ASIDE_RESERVE_TAKE, L.ASIDE_RESERVE_TAKE_TIP, function() AsideTab:Take(e.quest) end)
    end
    r.b2:Hide()
  end
  return n
end

local function FillDetour(b)
  local A, E = Senda.Aside, Senda.Engine
  b.cancel:SetShown(A:Active())
  if not A:Active() then
    b.status:SetText(L.ASIDE_DETOUR_EMPTY)
    return 0
  end
  local main = E:CurrentStep()
  local back = main and HUD():StepTitle(main) or ""
  if main and back == "" then back = HUD():StepText(main) end
  if not main then back = L.ASIDE_DETOUR_ROUTE_END end
  local di, dn = A:Index(), #A:Steps()
  b.status:SetText(string.format(L.ASIDE_DETOUR_PROGRESS, math.min(di, dn), dn, back))
  local n = 0
  for i, d in ipairs(A:Steps()) do
    n = n + 1
    local r = Row(b, n)
    local s = d.step
    if d.mark == "s" then r.state:SetTexture("Interface\\RaidFrame\\ReadyCheck-NotReady")
    elseif d.mark or i < di then r.state:SetTexture("Interface\\RaidFrame\\ReadyCheck-Ready")
    elseif i == di then r.state:SetTexture("Interface\\ChatFrame\\ChatFrameExpandArrow")
    else r.state:SetTexture(Cond:Icon(s)) end
    local title = HUD():StepTitle(s)
    r.text:SetText(UI:Color(i == di and "gold" or "accent", HUD():TypeLabel(s) .. (title ~= "" and (": " .. title) or "")))
    r.sub:SetText(HUD():StepText(s))
    r.b1:Hide()
    r.b2:Hide()
  end
  return n
end

function AsideTab:Refresh()
  if not tab.blocks then return end
  local y = 0
  tab.blockY = {}
  local width = tab.child:GetWidth()
  for _, key in ipairs(BLOCKS) do
    local b = tab.blocks[key]
    local n
    if key == "parked" then n = FillParked(b, width)
    elseif key == "reserve" then n = FillReserve(b)
    else n = FillDetour(b) end
    for i = n + 1, #b.rows do b.rows[i]:Hide() end
    local sh = (b.status:GetText() or "") ~= "" and (b.status:GetStringHeight() + 6) or 0
    local ry = 30 + sh
    for i = 1, n do
      local r = b.rows[i]
      r:ClearAllPoints()
      r:SetPoint("TOPLEFT", 10, -ry)
      r:SetPoint("RIGHT", b, "RIGHT", -8, 0)
      r:Show()
      ry = ry + ROW_H
    end
    local h = ry + 6
    b:ClearAllPoints()
    b:SetPoint("TOPLEFT", 0, -y)
    b:SetPoint("RIGHT", tab.child, "RIGHT", 0, 0)
    b:SetHeight(h)
    tab.blockY[key] = y
    y = y + h + 8
  end
  tab.child:SetHeight(math.max(10, y))
end

-- Abre la pestaña en un bloque (lo resalta un momento).
function AsideTab:Open(block)
  UI:ShowPanel("aside")
  self:Refresh()
  local b = tab.blocks and tab.blocks[block or ""]
  if not b then return end
  local target = (tab.blockY and tab.blockY[block]) or 0
  local maxScroll = tab.sf:GetVerticalScrollRange() or 0
  tab.sf:SetVerticalScroll(math.min(target, maxScroll))
  tab.focus = block
  b.flash:Show()
  Compat.After(1.5, function() b.flash:Hide() end)
end

function AsideTab:Focused() return tab.focus end

UI:RegisterTab({
  key = "aside",
  title = L.TAB_ASIDE,
  icon = "Interface\\Icons\\INV_Misc_PocketWatch_01",
  order = 12,
  build = Build,
  refresh = function() AsideTab:Refresh() end,
})

-- Refresco en vivo mientras el panel está abierto.
local pending = false
local function Live()
  if pending or not UI:IsPanelShown() then return end
  pending = true
  Compat.After(0.3, function()
    pending = false
    if UI:IsPanelShown() then AsideTab:Refresh() end
  end)
end
for _, ev in ipairs({ "SENDA_PARKED", "SENDA_ASIDE_CHANGED", "SENDA_RESERVE_UPDATED", "SENDA_RESERVE_READY",
  "SENDA_STEP_CHANGED", "SENDA_NAMES_UPDATED" }) do
  Events:On(ev, Live)
end

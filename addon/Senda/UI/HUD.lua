-- HUD: paso actual compacto, movible y bloqueable.
-- Muestra sección + rango de niveles, icono por tipo de paso, título resuelto en el idioma del cliente,
-- progreso de objetivos, consejo, los 2 pasos siguientes atenuados, botones Atrás/Hecho/Saltar,
-- "Leer más" si el paso tiene `link` y un punto de estado de los datos (verificado/sin verificar/disputado).
local _, Senda = ...
local UI, Compat, Events = Senda.UI, Senda.Compat, Senda.Events
local L = Senda.L
local Cond = Senda.Conditions

local HUD = {}
Senda.HUD = HUD

local WIDTH = 320
local PAD = 8
local hud

------------------------------------------------------------------------------
-- Texto de los pasos (también lo usa la lista de la guía)
------------------------------------------------------------------------------

local function QuestName(id)
  return Compat.QuestTitle(id) or string.format(L.QUEST_FALLBACK, tostring(id))
end

local function ItemText(id, count)
  local name = Compat.ItemName(id) or string.format(L.ITEM_FALLBACK, tostring(id))
  if count and count > 1 then name = name .. " x" .. count end
  return name
end

-- Título corto del paso (qué misión / objeto / hechizo...), resuelto por id.
function HUD:StepTitle(step)
  if type(step) ~= "table" then return "" end
  local d = step["do"]
  local qs = Cond:Quests(step)
  if (d == "accept" or d == "turnin" or d == "complete" or d == "dungeon") and qs then
    local names = {}
    for i, q in ipairs(qs) do
      if i > 3 then names[#names + 1] = "…"; break end
      names[#names + 1] = QuestName(q)
    end
    return table.concat(names, ", ")
  elseif d == "train" and type(step.spells) == "table" then
    local names = {}
    for i, id in ipairs(step.spells) do
      if i > 4 then names[#names + 1] = "…"; break end
      names[#names + 1] = Compat.SpellName(id) or ("#" .. id)
    end
    return table.concat(names, ", ")
  elseif (d == "buy" or d == "have" or d == "loot" or d == "use") and step.item then
    return ItemText(step.item, step.count)
  elseif d == "level" and step.level then
    return string.format(L.LEVEL_N, step.level)
  elseif (d == "learn_prof" or d == "skill") and step.prof then
    local p = L["PROF_" .. step.prof] or step.prof
    if d == "skill" and step.skill then p = p .. " " .. step.skill end
    return p
  elseif (d == "fly" or d == "hearth") and step.zone then
    return Compat.MapName(step.zone) or ("#" .. step.zone)
  elseif d == "getfp" and step.node then
    return tostring(step.node)
  elseif step.at then
    return step.at[4] or Compat.MapName(step.at[1]) or ""
  end
  return ""
end

-- Texto de instrucción con sustitución de {quest}, {item}, {zone}.
function HUD:StepText(step)
  local t = step and step.text or ""
  if t:find("{", 1, true) then
    t = t:gsub("{quest}", function() return step.quest and QuestName(step.quest) or "" end)
    t = t:gsub("{item}", function() return step.item and ItemText(step.item) or "" end)
    t = t:gsub("{zone}", function() return step.zone and (Compat.MapName(step.zone) or "") or "" end)
  end
  return t
end

function HUD:TypeLabel(step)
  local d = step and step["do"]
  return (d and L["DO_" .. d]) or L.DO_unknown
end

-- Líneas de objetivos de la misión del paso: { text, finished }.
function HUD:ObjectiveLines(step)
  local out = {}
  local d = step and step["do"]
  if d ~= "complete" and d ~= "turnin" and d ~= "accept" then return out end
  local qs = Cond:Quests(step)
  if not qs then return out end
  for _, q in ipairs(qs) do
    if Compat.IsOnQuest(q) then
      for i, o in ipairs(Compat.QuestObjectives(q)) do
        if not step.obj or step.obj == i then
          local text = o.text
          if not text or text == "" then
            text = (o.have and o.need) and string.format("%d/%d", o.have, o.need) or "?"
          end
          out[#out + 1] = { text = text, finished = o.finished }
        end
      end
    end
  end
  return out
end

local STATUS = {
  verified   = { "Interface\\COMMON\\Indicator-Green", "STATUS_VERIFIED", "STATUS_VERIFIED_TIP" },
  unverified = { "Interface\\COMMON\\Indicator-Yellow", "STATUS_UNVERIFIED", "STATUS_UNVERIFIED_TIP" },
  disputed   = { "Interface\\COMMON\\Indicator-Red", "STATUS_DISPUTED", "STATUS_DISPUTED_TIP" },
}
HUD.STATUS = STATUS

------------------------------------------------------------------------------
-- Construcción
------------------------------------------------------------------------------

local function Opt(key) return Senda.Options:Get(key) end

local function FS(parent, font, r, g, b)
  local fs = parent:CreateFontString(nil, "OVERLAY", font or "GameFontHighlightSmall")
  fs:SetJustifyH("LEFT")
  fs:SetJustifyV("TOP")
  if r then fs:SetTextColor(r, g, b) end
  return fs
end

local function Create()
  if hud then return hud end
  local C = UI.C
  local f = CreateFrame("Frame", "SendaHUD", UIParent, BackdropTemplateMixin and "BackdropTemplate" or nil)
  UI:Backdrop(f, "panel")
  f:SetWidth(WIDTH)
  f:SetHeight(120)
  f:SetClampedToScreen(true)
  f:SetMovable(true)
  f:EnableMouse(true)
  f:RegisterForDrag("LeftButton")
  f:SetFrameStrata("MEDIUM")
  f:SetScript("OnDragStart", function(self)
    if not Opt("hudLocked") then self:StartMoving() end
  end)
  f:SetScript("OnDragStop", function(self)
    self:StopMovingOrSizing()
    Senda:SaveFramePos(self, "hud")
  end)
  Senda:RestoreFramePos(f, "hud", "TOPRIGHT", "TOPRIGHT", -220, -230)

  -- Cabecera ---------------------------------------------------------------
  local head = CreateFrame("Frame", nil, f)
  head:SetPoint("TOPLEFT", 1, -1)
  head:SetPoint("TOPRIGHT", -1, -1)
  head:SetHeight(20)
  local hbg = head:CreateTexture(nil, "BACKGROUND")
  hbg:SetAllPoints()
  hbg:SetColorTexture(C.bg2[1], C.bg2[2], C.bg2[3], 1)
  local accent = head:CreateTexture(nil, "ARTWORK")
  accent:SetPoint("TOPLEFT"); accent:SetPoint("BOTTOMLEFT")
  accent:SetWidth(2)
  accent:SetColorTexture(C.accent[1], C.accent[2], C.accent[3], 1)

  f.collapse = UI:IconButton(head, "Interface\\Buttons\\UI-MinusButton-Up", 14, function()
    Senda.db.hudCollapsed = not Senda.db.hudCollapsed
    HUD:Refresh()
  end)
  f.collapse:SetPoint("LEFT", 5, 0)
  UI:Tooltip(f.collapse, L.HUD_COLLAPSE)

  f.dot = CreateFrame("Frame", nil, head)
  f.dot:SetSize(14, 14)
  f.dot:SetPoint("RIGHT", -5, 0)
  f.dot.tex = f.dot:CreateTexture(nil, "OVERLAY")
  f.dot.tex:SetAllPoints()
  f.dot:EnableMouse(true)
  f.dot:SetScript("OnEnter", function(self)
    local s = STATUS[self.status or "unverified"] or STATUS.unverified
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:SetText(L[s[2]], 1, 1, 1)
    GameTooltip:AddLine(L[s[3]], nil, nil, nil, true)
    if self.stepId then GameTooltip:AddLine(self.stepId, 0.5, 0.5, 0.5) end
    GameTooltip:Show()
  end)
  f.dot:SetScript("OnLeave", function() GameTooltip:Hide() end)

  f.progress = FS(head, "GameFontDisableSmall")
  f.progress:SetPoint("RIGHT", f.dot, "LEFT", -6, 0)
  f.progress:SetJustifyV("MIDDLE")

  f.section = FS(head, "GameFontNormalSmall")
  f.section:SetPoint("LEFT", f.collapse, "RIGHT", 6, 0)
  f.section:SetPoint("RIGHT", f.progress, "LEFT", -6, 0)
  f.section:SetJustifyV("MIDDLE")
  f.section:SetWordWrap(false)
  f.head = head

  -- Paso actual ------------------------------------------------------------
  f.icon = f:CreateTexture(nil, "ARTWORK")
  f.icon:SetSize(28, 28)
  f.icon:SetPoint("TOPLEFT", PAD, -28)

  f.title = FS(f, "GameFontNormal")
  f.title:SetPoint("TOPLEFT", f.icon, "TOPRIGHT", 8, 1)
  f.title:SetPoint("RIGHT", -PAD, 0)

  f.text = FS(f, "GameFontHighlightSmall", C.text[1], C.text[2], C.text[3])
  f.text:SetPoint("TOPLEFT", f.title, "BOTTOMLEFT", 0, -3)
  f.text:SetPoint("RIGHT", -PAD, 0)
  if f.text.SetSpacing then f.text:SetSpacing(2) end

  f.objectives = FS(f, "GameFontHighlightSmall")
  f.objectives:SetPoint("TOPLEFT", f.text, "BOTTOMLEFT", 0, -4)
  f.objectives:SetPoint("RIGHT", -PAD, 0)

  f.tip = FS(f, "GameFontHighlightSmall", C.gold[1] * 0.9, C.gold[2] * 0.9, C.gold[3] * 0.6)
  f.tip:SetPoint("TOPLEFT", f.objectives, "BOTTOMLEFT", 0, -4)
  f.tip:SetPoint("RIGHT", -PAD, 0)

  -- Aviso corto de los módulos (Senda.HUD:SetAdvice)
  f.advice = FS(f, "GameFontHighlightSmall", C.accent[1], C.accent[2], C.accent[3])
  f.advice:SetPoint("TOPLEFT", f.tip, "BOTTOMLEFT", 0, -4)
  f.advice:SetPoint("RIGHT", -PAD, 0)

  -- Misiones aplazadas por nivel (clic: volver a la primera que ya se puede coger)
  f.gated = CreateFrame("Button", nil, f)
  f.gated:SetHeight(14)
  f.gated.text = FS(f.gated, "GameFontHighlightSmall")
  f.gated.text:SetAllPoints()
  f.gated.text:SetWordWrap(false)
  f.gated:SetScript("OnClick", function(self)
    if self.index then Senda.Engine:JumpTo(self.index) end
  end)
  f.gated:SetScript("OnEnter", function(self)
    if not self.tip then return end
    GameTooltip:SetOwner(self, "ANCHOR_BOTTOMLEFT")
    GameTooltip:SetText(L.LEVEL_GATE_TITLE, 1, 0.82, 0)
    for _, line in ipairs(self.tip) do GameTooltip:AddLine(line, 1, 1, 1, true) end
    GameTooltip:Show()
  end)
  f.gated:SetScript("OnLeave", function() GameTooltip:Hide() end)

  -- Vista previa de los siguientes pasos ----------------------------------
  f.sep = UI:Divider(f, 0.7)
  f.preview = {}
  for i = 1, 2 do
    local row = CreateFrame("Frame", nil, f)
    row:SetHeight(16)
    row.icon = row:CreateTexture(nil, "ARTWORK")
    row.icon:SetSize(14, 14)
    row.icon:SetPoint("LEFT")
    row.icon:SetDesaturated(true)
    row.icon:SetAlpha(0.7)
    row.text = FS(row, "GameFontDisableSmall")
    row.text:SetPoint("LEFT", row.icon, "RIGHT", 6, 0)
    row.text:SetPoint("RIGHT")
    row.text:SetWordWrap(false)
    row.text:SetJustifyV("MIDDLE")
    f.preview[i] = row
  end

  -- Botones ------------------------------------------------------------------
  f.back = UI:Button(f, "<", 26, 20, function() Senda.Engine:Back() end)
  UI:Tooltip(f.back, L.HUD_BACK)
  f.done = UI:Button(f, L.HUD_DONE, 70, 20, function() Senda.Engine:Advance() end)
  f.skip = UI:Button(f, L.HUD_SKIP, 60, 20, function() Senda.Engine:Skip() end)
  f.more = UI:Button(f, L.HUD_MORE, 74, 20, function()
    local step = Senda.Engine:CurrentStep()
    local link = step and (step.link or (Senda.Engine:CurrentSection() or {}).link)
    if link then UI:ShowLink(link) end
  end)
  f.menu = UI:Button(f, L.HUD_PANEL, 48, 20, function() UI:TogglePanel() end)
  UI:Tooltip(f.menu, L.HUD_OPEN_PANEL)

  hud = f
  return f
end

------------------------------------------------------------------------------
-- Refresco
------------------------------------------------------------------------------

function HUD:Refresh()
  if not hud or not hud:IsShown() then return end
  local f = hud
  local Engine = Senda.Engine
  local step, entry = Engine:CurrentStep()
  local collapsed = Senda.db.hudCollapsed

  f.collapse.icon:SetTexture(collapsed and "Interface\\Buttons\\UI-PlusButton-Up" or "Interface\\Buttons\\UI-MinusButton-Up")

  -- Cabecera
  local sec = entry and entry.section
  if sec then
    local lv = sec.levels and string.format(" |cff8c949e%d-%d|r", sec.levels[1] or 0, sec.levels[2] or 0) or ""
    f.section:SetText((sec.title or sec.id) .. lv)
  elseif not Engine:GuideId() then
    f.section:SetText(L.NO_GUIDE)
  else
    f.section:SetText(L.GUIDE_FINISHED_SHORT)
  end
  local done, total = Engine:Progress()
  f.progress:SetText(total > 0 and string.format("%d/%d", done, total) or "")
  local status = step and step.status or nil
  local st = STATUS[status or ""]
  f.dot:SetShown(st ~= nil)
  if st then f.dot.tex:SetTexture(st[1]) end
  f.dot.status, f.dot.stepId = status, step and step.id

  -- Paso
  local y = 28
  if step then
    f.icon:SetTexture(Cond:Icon(step))
    f.icon:SetTexCoord(0.06, 0.94, 0.06, 0.94)
    f.icon:Show()
    local title = self:StepTitle(step)
    local label = self:TypeLabel(step)
    local opt = step.optional and (" " .. UI:Color("dim", L.OPTIONAL_TAG)) or ""
    if title ~= "" then
      f.title:SetText(UI:Color("accent", label .. ":") .. " " .. title .. opt)
    else
      f.title:SetText(UI:Color("accent", label) .. opt)
    end
    local text = self:StepText(step)
    if step.at and step.at[2] then
      text = text .. UI:Color("dim", string.format("  (%.1f, %.1f)", step.at[2], step.at[3] or 0))
    end
    f.text:SetText(text)
  elseif Engine:GuideId() and #Engine:Steps() == 0 then
    f.icon:SetTexture("Interface\\RaidFrame\\ReadyCheck-Waiting")
    f.icon:SetTexCoord(0, 1, 0, 1)
    f.title:SetText(L.NO_GUIDE)
    f.text:SetText(L.GUIDE_TAB_EMPTY)
  else
    f.icon:SetTexture("Interface\\RaidFrame\\ReadyCheck-Ready")
    f.icon:SetTexCoord(0, 1, 0, 1)
    f.title:SetText(Engine:GuideId() and L.GUIDE_FINISHED or L.NO_GUIDE)
    f.text:SetText(Engine:GuideId() and L.GUIDE_FINISHED_HINT or L.NO_GUIDE_HINT)
  end
  f.title:SetWordWrap(not collapsed)
  f.text:SetShown(not collapsed)

  local titleH = math.max(f.title:GetStringHeight(), 12)
  local textH = collapsed and 0 or (f.text:GetStringHeight() + 3)
  y = y + math.max(28, titleH + textH) + 4

  -- Objetivos y consejo
  local objH, tipH = 0, 0
  if not collapsed and step then
    local lines = {}
    for _, o in ipairs(self:ObjectiveLines(step)) do
      local c = o.finished and UI.HEX.green or "ffd8d8d8"
      lines[#lines + 1] = "|c" .. c .. "• " .. o.text .. "|r"
    end
    if not Cond:IsAuto(step) then lines[#lines + 1] = UI:Color("dim", L.HUD_MANUAL_HINT) end
    f.objectives:SetText(table.concat(lines, "\n"))
    objH = #lines > 0 and (f.objectives:GetStringHeight() + 4) or 0
    f.tip:SetText(step.tip and ("|TInterface\\COMMON\\help-i:14:14:0:0|t" .. step.tip) or "")
    tipH = step.tip and (f.tip:GetStringHeight() + 4) or 0
  else
    f.objectives:SetText("")
    f.tip:SetText("")
  end
  f.objectives:SetShown(objH > 0)
  f.tip:SetShown(tipH > 0)
  local advH = 0
  if not collapsed and self.advice and self.advice ~= "" then
    f.advice:SetText(self.advice)
    advH = f.advice:GetStringHeight() + 4
  else
    f.advice:SetText("")
  end
  f.advice:SetShown(advH > 0)
  y = y + objH + tipH + advH

  -- Misiones aplazadas por nivel
  local gated = (not collapsed and Engine.LevelGated) and Engine:LevelGated() or {}
  f.gated.index, f.gated.tip = nil, nil
  if #gated > 0 then
    local ready, waiting, tip = {}, {}, {}
    for _, g in ipairs(gated) do
      local name = self:StepTitle(g.entry.step)
      if name == "" then name = self:StepText(g.entry.step) end
      g.name = name
      if g.ready then
        ready[#ready + 1] = g
        tip[#tip + 1] = UI:Color("green", "+ ") .. name
      else
        waiting[#waiting + 1] = g
        tip[#tip + 1] = string.format(L.LEVEL_GATE_TIP, g.level, name)
      end
    end
    local text
    if #ready > 0 then
      local first = ready[1] -- la primera en el orden de la ruta
      f.gated.index = first.index
      local nowLabel = first.entry.step["do"] == "train" and (L.LEVEL_GATE_NOW_TRAIN or L.LEVEL_GATE_NOW) or L.LEVEL_GATE_NOW
      text = UI:Color("green", nowLabel) .. " " .. first.name
      if #ready > 1 then text = text .. UI:Color("dim", string.format(" (+%d)", #ready - 1)) end
      tip[#tip + 1] = UI:Color("dim", L.LEVEL_GATE_CLICK)
    else
      local low = waiting[1]
      for _, g in ipairs(waiting) do if g.level < low.level then low = g end end
      text = UI:Color("dim", string.format(L.LEVEL_GATE_LATER, low.level) .. " " .. low.name)
      if #waiting > 1 then text = text .. UI:Color("dim", string.format(" (+%d)", #waiting - 1)) end
    end
    f.gated.tip = tip
    f.gated.text:SetText(text)
    f.gated:ClearAllPoints()
    f.gated:SetPoint("TOPLEFT", PAD, -y)
    f.gated:SetPoint("RIGHT", -PAD, 0)
    f.gated:Show()
    y = y + 16
  else
    f.gated:Hide()
  end

  -- Vista previa
  local showPreview = not collapsed and Opt("hudPreview")
  local nexts = showPreview and Engine:NextSteps(2) or {}
  if #nexts > 0 then
    f.sep:ClearAllPoints()
    f.sep:SetPoint("TOPLEFT", PAD, -y - 2)
    f.sep:SetPoint("TOPRIGHT", -PAD, -y - 2)
    f.sep:Show()
    y = y + 6
  else
    f.sep:Hide()
  end
  for i, row in ipairs(f.preview) do
    local e = nexts[i]
    if e then
      row:ClearAllPoints()
      row:SetPoint("TOPLEFT", PAD, -y)
      row:SetPoint("RIGHT", -PAD, 0)
      row.icon:SetTexture(Cond:Icon(e.step))
      local t = self:StepTitle(e.step)
      row.text:SetText(t ~= "" and (self:TypeLabel(e.step) .. ": " .. t) or self:StepText(e.step))
      row:Show()
      y = y + 16
    else
      row:Hide()
    end
  end

  -- Botones
  local hasStep = step ~= nil
  local link = step and (step.link or (sec and sec.link))
  local showButtons = not collapsed
  for _, b in ipairs({ f.back, f.done, f.skip, f.more, f.menu }) do b:SetShown(showButtons) end
  if showButtons then
    y = y + 6
    f.back:ClearAllPoints(); f.back:SetPoint("TOPLEFT", PAD, -y)
    f.done:ClearAllPoints(); f.done:SetPoint("LEFT", f.back, "RIGHT", 4, 0)
    f.skip:ClearAllPoints(); f.skip:SetPoint("LEFT", f.done, "RIGHT", 4, 0)
    f.menu:ClearAllPoints(); f.menu:SetPoint("TOPRIGHT", -PAD, -y)
    f.more:ClearAllPoints(); f.more:SetPoint("RIGHT", f.menu, "LEFT", -4, 0)
    f.more:SetShown(link ~= nil)
    f.done:SetEnabled(hasStep)
    f.skip:SetEnabled(hasStep)
    f.back:SetEnabled(Engine:GuideId() ~= nil and Engine:Index() > 1)
    y = y + 20
  end
  f:SetHeight(y + PAD)
end

-- Aviso corto de un módulo (p. ej. "Tienes puntos de talento sin gastar"). nil o "" lo quita.
function HUD:SetAdvice(text)
  self.advice = text
  self:RequestRefresh()
end

-- Refresco agrupado (muchos eventos -> un refresco).
local refreshPending = false
function HUD:RequestRefresh()
  if refreshPending then return end
  refreshPending = true
  Compat.After(0.15, function()
    refreshPending = false
    HUD:Refresh()
  end)
end

------------------------------------------------------------------------------
-- Visibilidad y opciones
------------------------------------------------------------------------------

function HUD:Apply()
  local f = Create()
  f:SetScale(Opt("hudScale") or 1)
  f:SetAlpha(Opt("hudAlpha") or 1)
  local show = Opt("hud") and not (Opt("hudCombatHide") and Compat.InCombat())
  f:SetShown(show and true or false)
  if show then self:Refresh() end
end

function HUD:Toggle()
  Senda.Options:Set("hud", not Opt("hud"))
end

local function Apply() if hud then HUD:Apply() end end

local SEC = L.OPT_SECTION_HUD
Senda.Options:Register({ key = "hud", label = L.OPT_HUD, type = "toggle", default = true, section = SEC, order = 1,
  onChange = Apply })
Senda.Options:Register({ key = "hudLocked", label = L.OPT_HUD_LOCKED, type = "toggle", default = false,
  section = SEC, order = 2 })
Senda.Options:Register({ key = "hudPreview", label = L.OPT_HUD_PREVIEW, type = "toggle", default = true,
  section = SEC, order = 3, onChange = Apply })
Senda.Options:Register({ key = "hudCombatHide", label = L.OPT_HUD_COMBAT, type = "toggle", default = false,
  section = SEC, order = 4, onChange = Apply })
Senda.Options:Register({ key = "hudScale", label = L.OPT_SCALE, type = "slider", default = 1, min = 0.6, max = 1.6,
  step = 0.05, section = SEC, order = 10, onChange = Apply })
Senda.Options:Register({ key = "hudAlpha", label = L.OPT_ALPHA, type = "slider", default = 1, min = 0.3, max = 1,
  step = 0.05, section = SEC, order = 11, onChange = Apply })

Events:On("SENDA_READY", function()
  HUD:Apply()
  local refresh = function() HUD:RequestRefresh() end
  Events:On("SENDA_STEP_CHANGED", refresh)
  Events:On("SENDA_STEP_UPDATED", refresh)
  Events:On("SENDA_GUIDE_CHANGED", refresh)
  Events:On("SENDA_ADVICE", function(_, text)
    if HUD.advice ~= text then HUD:SetAdvice(text) end
  end)
  Events:On("QUEST_DATA_LOAD_RESULT", refresh)
  Events:On("GET_ITEM_INFO_RECEIVED", refresh)
  Events:On("PLAYER_REGEN_DISABLED", function()
    if Opt("hudCombatHide") and hud then hud:Hide() end
  end)
  Events:On("PLAYER_REGEN_ENABLED", function()
    if Opt("hudCombatHide") then HUD:Apply() end
  end)
end)

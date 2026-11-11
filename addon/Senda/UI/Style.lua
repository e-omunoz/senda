-- Estilo común (tema oscuro plano) y piezas reutilizables para todos los módulos.
--   Senda.UI:Backdrop(frame, kind)                       -- kind: "panel" | "inset" | "button" | "tooltip"
--   Senda.UI:Frame(name, parent, opts)                   -- marco con cabecera, cierre y posición guardada
--   Senda.UI:Button(parent, text, width, height, onClick)  -- o (parent, text, width, onClick)
--   Senda.UI:IconButton(parent, texture, size, onClick, tooltip)
--   Senda.UI:ScrollText(parent)                          -- :SetText(texto con **negrita**, "- " y [enlaces](url))
--   Senda.UI:ScrollArea(parent)                          -- scroll genérico -> scrollFrame, child
--   Senda.UI:Checkbox(parent, label, get, set, tooltip)
--   Senda.UI:Slider(parent, label, min, max, step, get, set, fmt)
--   Senda.UI:Dropdown(parent, width, getItems, onSelect) -- getItems() -> { { value, text }, ... }
--   Senda.UI:Label(parent, text, font), :Divider(parent), :Tooltip(frame, title, body)
-- Solo texturas incluidas en el cliente; sin librerías externas.
local _, Senda = ...

local UI = Senda.UI or {}
Senda.UI = UI

local WHITE = "Interface\\Buttons\\WHITE8X8"
local BACKDROP_TEMPLATE = BackdropTemplateMixin and "BackdropTemplate" or nil

-- Paleta.
UI.C = {
  bg      = { 0.055, 0.060, 0.075, 0.94 },
  bg2     = { 0.090, 0.100, 0.120, 0.96 },
  inset   = { 0.035, 0.040, 0.050, 0.90 },
  border  = { 0.20, 0.22, 0.26, 1 },
  accent  = { Senda.COLOR[1], Senda.COLOR[2], Senda.COLOR[3], 1 },
  text    = { 0.92, 0.93, 0.95, 1 },
  dim     = { 0.55, 0.58, 0.62, 1 },
  gold    = { 1.00, 0.82, 0.25, 1 },
  green   = { 0.35, 0.85, 0.40, 1 },
  yellow  = { 1.00, 0.80, 0.20, 1 },
  red     = { 0.95, 0.30, 0.30, 1 },
}
UI.HEX = {
  accent = Senda.COLOR_HEX, gold = "ffffd140", dim = "ff8c949e", green = "ff59d966", yellow = "ffffcc33",
  red = "fff24d4d", white = "ffffffff",
}

function UI:Color(name, text)
  return "|c" .. (self.HEX[name] or "ffffffff") .. tostring(text) .. "|r"
end

local function SetColor(fn, obj, c, a)
  fn(obj, c[1], c[2], c[3], a or c[4] or 1)
end

------------------------------------------------------------------------------
-- Fondos
------------------------------------------------------------------------------

local BACKDROPS = {
  panel = { bgFile = WHITE, edgeFile = WHITE, edgeSize = 1, insets = { left = 1, right = 1, top = 1, bottom = 1 } },
}

function UI:Backdrop(f, kind)
  if not f or not f.SetBackdrop then return f end
  kind = kind or "panel"
  f:SetBackdrop(BACKDROPS.panel)
  local C = self.C
  if kind == "inset" then
    SetColor(f.SetBackdropColor, f, C.inset)
    SetColor(f.SetBackdropBorderColor, f, C.border, 0.8)
  elseif kind == "button" then
    SetColor(f.SetBackdropColor, f, C.bg2)
    SetColor(f.SetBackdropBorderColor, f, C.border)
  elseif kind == "tooltip" then
    SetColor(f.SetBackdropColor, f, C.bg, 0.97)
    SetColor(f.SetBackdropBorderColor, f, C.accent, 0.8)
  else
    SetColor(f.SetBackdropColor, f, C.bg)
    SetColor(f.SetBackdropBorderColor, f, C.border)
  end
  return f
end

-- Texto auxiliar.
function UI:Label(parent, text, font)
  local fs = parent:CreateFontString(nil, "OVERLAY", font or "GameFontHighlightSmall")
  fs:SetJustifyH("LEFT")
  if text then fs:SetText(text) end
  return fs
end

function UI:Divider(parent, alpha)
  local t = parent:CreateTexture(nil, "ARTWORK")
  t:SetColorTexture(self.C.border[1], self.C.border[2], self.C.border[3], alpha or 1)
  t:SetHeight(1)
  return t
end

function UI:Tooltip(frame, title, body)
  frame:HookScript("OnEnter", function(self)
    local t = type(title) == "function" and title(self) or title
    if not t then return end
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:SetText(t, 1, 1, 1)
    local b = type(body) == "function" and body(self) or body
    if b then GameTooltip:AddLine(b, nil, nil, nil, true) end
    GameTooltip:Show()
  end)
  frame:HookScript("OnLeave", function() GameTooltip:Hide() end)
end

------------------------------------------------------------------------------
-- Marco con cabecera
------------------------------------------------------------------------------

-- opts: { title, width, height, posKey, closable = true, movable = true, strata, point = {...} }
function UI:Frame(name, parent, opts)
  opts = opts or {}
  local f = CreateFrame("Frame", name, parent or UIParent, BACKDROP_TEMPLATE)
  self:Backdrop(f, opts.kind or "panel")
  f:SetSize(opts.width or 400, opts.height or 300)
  f:SetClampedToScreen(true)
  if opts.strata then f:SetFrameStrata(opts.strata) end

  if opts.title then
    local header = CreateFrame("Frame", nil, f)
    header:SetPoint("TOPLEFT", 1, -1)
    header:SetPoint("TOPRIGHT", -1, -1)
    header:SetHeight(opts.headerHeight or 26)
    local bg = header:CreateTexture(nil, "BACKGROUND")
    bg:SetAllPoints()
    bg:SetColorTexture(self.C.bg2[1], self.C.bg2[2], self.C.bg2[3], 1)
    local line = header:CreateTexture(nil, "ARTWORK")
    line:SetPoint("BOTTOMLEFT"); line:SetPoint("BOTTOMRIGHT")
    line:SetHeight(1)
    line:SetColorTexture(self.C.accent[1], self.C.accent[2], self.C.accent[3], 0.6)
    f.title = header:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    f.title:SetPoint("LEFT", 10, 0)
    f.title:SetTextColor(self.C.text[1], self.C.text[2], self.C.text[3])
    f.title:SetText(opts.title)
    f.header = header
  end

  if opts.closable ~= false then
    local close = self:IconButton(f.header or f, "Interface\\Buttons\\UI-StopButton", 14, function() f:Hide() end)
    close:SetPoint("TOPRIGHT", f, "TOPRIGHT", -6, -6)
    close.icon:SetVertexColor(0.8, 0.8, 0.8)
    f.close = close
  end

  if opts.movable ~= false then
    f:SetMovable(true)
    local handle = f.header or f
    handle:EnableMouse(true)
    handle:RegisterForDrag("LeftButton")
    handle:SetScript("OnDragStart", function()
      if f.locked then return end
      f:StartMoving()
    end)
    handle:SetScript("OnDragStop", function()
      f:StopMovingOrSizing()
      if opts.posKey then Senda:SaveFramePos(f, opts.posKey) end
    end)
  end

  if opts.posKey and Senda.db then
    local p = opts.point or { "CENTER", "CENTER", 0, 0 }
    Senda:RestoreFramePos(f, opts.posKey, p[1], p[2], p[3], p[4])
  elseif opts.point then
    f:SetPoint(opts.point[1], UIParent, opts.point[2], opts.point[3], opts.point[4])
  else
    f:SetPoint("CENTER")
  end
  return f
end

------------------------------------------------------------------------------
-- Botones
------------------------------------------------------------------------------

local function ButtonVisual(b)
  local C = UI.C
  if not b:IsEnabled() then
    b:SetAlpha(0.4)
    SetColor(b.SetBackdropBorderColor, b, C.border)
    return
  end
  b:SetAlpha(1)
  if b.active then
    SetColor(b.SetBackdropColor, b, C.accent, 0.22)
    SetColor(b.SetBackdropBorderColor, b, C.accent, 0.9)
  elseif b.hover then
    SetColor(b.SetBackdropColor, b, C.bg2)
    SetColor(b.SetBackdropBorderColor, b, C.accent, 0.8)
  else
    SetColor(b.SetBackdropColor, b, C.bg2)
    SetColor(b.SetBackdropBorderColor, b, C.border)
  end
end

function UI:Button(parent, text, width, height, onClick)
  -- También admite la forma corta Button(parent, text, width, onClick).
  if type(height) == "function" then onClick, height = height, nil end
  local b = CreateFrame("Button", nil, parent, BACKDROP_TEMPLATE)
  self:Backdrop(b, "button")
  b:SetSize(width or 80, height or 22)
  local fs = b:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  fs:SetPoint("CENTER")
  b:SetFontString(fs)
  b:SetText(text or "")
  b:RegisterForClicks("LeftButtonUp", "RightButtonUp")
  b:SetScript("OnEnter", function(self) self.hover = true; ButtonVisual(self) end)
  b:SetScript("OnLeave", function(self) self.hover = false; ButtonVisual(self) end)
  b:SetScript("OnMouseDown", function(self) if self:IsEnabled() then fs:SetPoint("CENTER", 1, -1) end end)
  b:SetScript("OnMouseUp", function() fs:SetPoint("CENTER", 0, 0) end)
  b:SetScript("OnEnable", ButtonVisual)
  b:SetScript("OnDisable", ButtonVisual)
  if onClick then b:SetScript("OnClick", onClick) end
  -- Marca el botón como seleccionado (pestañas, filtros).
  function b:SetActive(v) self.active = v and true or false; ButtonVisual(self) end
  ButtonVisual(b)
  return b
end

function UI:IconButton(parent, texture, size, onClick, tooltip)
  local b = CreateFrame("Button", nil, parent)
  b:SetSize(size or 16, size or 16)
  local icon = b:CreateTexture(nil, "ARTWORK")
  icon:SetAllPoints()
  icon:SetTexture(texture)
  b.icon = icon
  local hl = b:CreateTexture(nil, "HIGHLIGHT")
  hl:SetAllPoints()
  hl:SetTexture(texture)
  hl:SetBlendMode("ADD")
  hl:SetAlpha(0.4)
  b:RegisterForClicks("LeftButtonUp", "RightButtonUp")
  if onClick then b:SetScript("OnClick", onClick) end
  if tooltip then self:Tooltip(b, tooltip) end
  return b
end

------------------------------------------------------------------------------
-- Scroll
------------------------------------------------------------------------------

-- Área desplazable genérica: devuelve scrollFrame y el hijo (ancho ajustado automáticamente).
function UI:ScrollArea(parent)
  local sf = CreateFrame("ScrollFrame", nil, parent, "UIPanelScrollFrameTemplate")
  sf:SetPoint("TOPLEFT", 4, -4)
  sf:SetPoint("BOTTOMRIGHT", -26, 4)
  local child = CreateFrame("Frame", nil, sf)
  child:SetSize(10, 10)
  sf:SetScrollChild(child)
  sf:SetScript("OnSizeChanged", function(self, w)
    child:SetWidth(math.max(10, w or self:GetWidth()))
  end)
  sf.child = child
  return sf, child
end

-- Convierte el "markdown" mínimo de las páginas de conocimiento a texto con colores.
function UI:FormatText(text)
  if type(text) ~= "string" then return "" end
  local out = {}
  for line in (text .. "\n"):gmatch("(.-)\n") do
    local h = line:match("^#+%s*(.+)$")
    if h then
      line = self:Color("accent", h)
    else
      line = line:gsub("^%s*[-*]%s+", "  • ")
    end
    line = line:gsub("%*%*(.-)%*%*", "|cffffffff%1|r")
    line = line:gsub("%[(.-)%]%((.-)%)", "|c" .. self.HEX.accent .. "%1|r |c" .. self.HEX.dim .. "(%2)|r")
    out[#out + 1] = line
  end
  return table.concat(out, "\n")
end

-- Texto largo desplazable. sf:SetText(texto [, sinFormato])
function UI:ScrollText(parent)
  local sf, child = self:ScrollArea(parent)
  local fs = child:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  fs:SetPoint("TOPLEFT", 6, -6)
  fs:SetJustifyH("LEFT")
  fs:SetJustifyV("TOP")
  if fs.SetSpacing then fs:SetSpacing(3) end
  sf.fs = fs
  local function Layout()
    local w = math.max(50, (sf:GetWidth() or 300) - 12)
    fs:SetWidth(w)
    child:SetHeight(fs:GetStringHeight() + 16)
  end
  sf:HookScript("OnSizeChanged", Layout)
  function sf:SetText(text, raw)
    fs:SetText(raw and (text or "") or UI:FormatText(text))
    Layout()
    self:SetVerticalScroll(0)
  end
  return sf
end

------------------------------------------------------------------------------
-- Controles de opciones
------------------------------------------------------------------------------

function UI:Checkbox(parent, label, get, set, tooltip)
  local b = CreateFrame("Button", nil, parent)
  b:SetSize(260, 20)
  local box = CreateFrame("Frame", nil, b, BACKDROP_TEMPLATE)
  box:SetSize(16, 16)
  box:SetPoint("LEFT")
  self:Backdrop(box, "inset")
  local check = box:CreateTexture(nil, "OVERLAY")
  check:SetPoint("CENTER")
  check:SetSize(20, 20)
  check:SetTexture("Interface\\Buttons\\UI-CheckBox-Check")
  local text = b:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  text:SetPoint("LEFT", box, "RIGHT", 8, 0)
  text:SetText(label or "")
  b.text = text
  function b:Refresh()
    check:SetShown(get() and true or false)
  end
  b:SetScript("OnClick", function(self)
    set(not get())
    self:Refresh()
  end)
  b:SetScript("OnEnter", function() SetColor(box.SetBackdropBorderColor, box, UI.C.accent) end)
  b:SetScript("OnLeave", function() SetColor(box.SetBackdropBorderColor, box, UI.C.border, 0.8) end)
  if tooltip then self:Tooltip(b, label, tooltip) end
  b:Refresh()
  return b
end

function UI:Slider(parent, label, minV, maxV, step, get, set, fmt)
  local f = CreateFrame("Frame", nil, parent)
  f:SetSize(260, 38)
  local text = f:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  text:SetPoint("TOPLEFT")
  local value = f:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  value:SetPoint("TOPRIGHT")
  value:SetTextColor(self.C.accent[1], self.C.accent[2], self.C.accent[3])

  local s = CreateFrame("Slider", nil, f, BACKDROP_TEMPLATE)
  s:SetOrientation("HORIZONTAL")
  s:SetPoint("TOPLEFT", 0, -18)
  s:SetPoint("TOPRIGHT", 0, -18)
  s:SetHeight(10)
  self:Backdrop(s, "inset")
  s:SetThumbTexture(WHITE)
  local thumb = s:GetThumbTexture()
  thumb:SetSize(10, 14)
  thumb:SetVertexColor(self.C.accent[1], self.C.accent[2], self.C.accent[3])
  s:SetMinMaxValues(minV, maxV)
  s:SetValueStep(step or 0.05)
  if s.SetObeyStepOnDrag then s:SetObeyStepOnDrag(true) end
  s:EnableMouseWheel(true)

  local function Show(v)
    value:SetText(fmt and fmt(v) or string.format("%.2f", v))
  end
  local updating = false
  s:SetScript("OnValueChanged", function(_, v)
    if updating then return end
    v = Senda.Util.Round(v, step or 0.05)
    Show(v)
    set(v)
  end)
  s:SetScript("OnMouseWheel", function(self, delta)
    local v = Senda.Util.Clamp(self:GetValue() + delta * (step or 0.05), minV, maxV)
    self:SetValue(v)
  end)
  text:SetText(label or "")
  function f:Refresh()
    updating = true
    local v = get() or minV
    s:SetValue(v)
    Show(v)
    updating = false
  end
  f.slider = s
  f:Refresh()
  return f
end

------------------------------------------------------------------------------
-- Desplegable propio (no depende de UIDropDownMenu)
------------------------------------------------------------------------------

local dropList -- lista compartida

local function DropList()
  if dropList then return dropList end
  local f = CreateFrame("Frame", "SendaDropdownList", UIParent, BACKDROP_TEMPLATE)
  UI:Backdrop(f, "tooltip")
  f:SetFrameStrata("FULLSCREEN_DIALOG")
  f:SetClampedToScreen(true)
  f:EnableMouse(true)
  f:Hide()
  local sf, child = UI:ScrollArea(f)
  f.sf, f.child, f.rows = sf, child, {}
  -- Se cierra al pulsar fuera.
  f:SetScript("OnShow", function(self)
    self.elapsed = 0
    self:SetScript("OnUpdate", function(s, dt)
      s.elapsed = s.elapsed + dt
      if s.elapsed > 0.2 and (IsMouseButtonDown("LeftButton") or IsMouseButtonDown("RightButton"))
        and not s:IsMouseOver() and not (s.owner and s.owner:IsMouseOver()) then
        s:Hide()
      end
    end)
  end)
  f:SetScript("OnHide", function(self) self:SetScript("OnUpdate", nil) end)
  dropList = f
  return f
end

function UI:Dropdown(parent, width, getItems, onSelect)
  local b = self:Button(parent, "", width or 200, 22)
  b:GetFontString():ClearAllPoints()
  b:GetFontString():SetPoint("LEFT", 8, 0)
  b:GetFontString():SetPoint("RIGHT", -20, 0)
  b:GetFontString():SetJustifyH("LEFT")
  local arrow = b:CreateTexture(nil, "OVERLAY")
  arrow:SetSize(12, 12)
  arrow:SetPoint("RIGHT", -6, 0)
  arrow:SetTexture("Interface\\ChatFrame\\ChatFrameExpandArrow")
  arrow:SetRotation(-math.pi / 2)

  function b:SetValue(value, text)
    self.value = value
    self:SetText(text or tostring(value or ""))
  end

  b:SetScript("OnClick", function(self)
    local list = DropList()
    if list:IsShown() and list.owner == self then list:Hide(); return end
    local items = getItems() or {}
    list.owner = self
    list:ClearAllPoints()
    list:SetPoint("TOPLEFT", self, "BOTTOMLEFT", 0, -2)
    local w = self:GetWidth()
    local rowH = 20
    for _, r in ipairs(list.rows) do r:Hide() end
    for i, it in ipairs(items) do
      local r = list.rows[i]
      if not r then
        r = CreateFrame("Button", nil, list.child)
        r:SetHeight(rowH)
        local hl = r:CreateTexture(nil, "HIGHLIGHT")
        hl:SetAllPoints()
        hl:SetColorTexture(UI.C.accent[1], UI.C.accent[2], UI.C.accent[3], 0.2)
        local fs = r:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        fs:SetPoint("LEFT", 6, 0)
        fs:SetPoint("RIGHT", -4, 0)
        fs:SetJustifyH("LEFT")
        fs:SetWordWrap(false)
        r.fs = fs
        list.rows[i] = r
      end
      r:ClearAllPoints()
      r:SetPoint("TOPLEFT", 0, -(i - 1) * rowH)
      r:SetPoint("RIGHT", list.child, "RIGHT")
      local selected = (it.value == self.value)
      r.fs:SetText((selected and UI:Color("accent", "› ") or "  ") .. tostring(it.text or it.value))
      r:SetScript("OnClick", function()
        list:Hide()
        self:SetValue(it.value, it.text)
        if onSelect then onSelect(it.value, it) end
      end)
      r:Show()
    end
    local h = math.min(#items, 16) * rowH + 10
    list:SetSize(w, math.max(h, 30))
    list.child:SetHeight(#items * rowH)
    list:Show()
  end)
  return b
end

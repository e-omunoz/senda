-- Widget API: CreateFrame and the stub regions (FontString, Texture) with enough state for the addon to
-- run headless: visibility (OnShow/OnHide), scripts and hooks, events, anchors, sizes, text, values.
-- Unknown methods: a permissive fallback returns a no-op (and logs "Type:Method") so a missing stub never
-- stops the run; the log is printed at the end so each entry can be reviewed against the real API.
local Sim = Sim

local all = {}     -- every widget, creation order
local updaters = {} -- frames with an OnUpdate script

local POINTS = {
  TOPLEFT = true, TOP = true, TOPRIGHT = true, LEFT = true, CENTER = true, RIGHT = true,
  BOTTOMLEFT = true, BOTTOM = true, BOTTOMRIGHT = true,
}
local STRATA = { BACKGROUND = true, LOW = true, MEDIUM = true, HIGH = true, DIALOG = true, FULLSCREEN = true,
  FULLSCREEN_DIALOG = true, TOOLTIP = true, PARENT = true }
local FRAME_TYPES = {
  Frame = true, Button = true, CheckButton = true, ScrollFrame = true, EditBox = true, Slider = true,
  StatusBar = true, GameTooltip = true, Cooldown = true, Model = true, PlayerModel = true, MessageFrame = true,
  SimpleHTML = true, ColorSelect = true,
}
local TEMPLATES = {
  BackdropTemplate = true, UIPanelScrollFrameTemplate = true, SecureActionButtonTemplate = true,
  UIPanelButtonTemplate = true, UICheckButtonTemplate = true, UIPanelCloseButton = true,
  GameTooltipTemplate = true, SecureHandlerBaseTemplate = true, InputBoxTemplate = true,
}

local function usage(cond, msg)
  if not cond then error(msg, 3) end
end

local function isWidget(v) return type(v) == "table" and rawget(v, "__isWidget") == true end
Sim.IsWidget = isWidget

------------------------------------------------------------------------------
-- Methods
------------------------------------------------------------------------------

local Region = {}   -- every widget
local FrameM = {}   -- Frame and subclasses
local FontStringM, TextureM = {}, {}
local ButtonM, CheckButtonM, ScrollFrameM, EditBoxM, SliderM, StatusBarM, TooltipM, BackdropM = {}, {}, {}, {}, {}, {}, {}, {}

-- Region (shared) -----------------------------------------------------------
function Region:GetName() return self.__name end
function Region:GetObjectType() return self.__type end
function Region:IsObjectType(t) return self.__type == t or (t == "Frame" and FRAME_TYPES[self.__type]) or false end
function Region:GetParent() return self.__parent end
function Region:IsShown() return self.__shown end
function Region:IsVisible()
  local o = self
  while o do
    if not o.__shown then return false end
    o = o.__parent
  end
  return true
end

local function visibleSet(root, set)
  set = set or {}
  local function walk(o, parentVisible)
    local v = parentVisible and o.__shown
    set[o] = v
    for _, c in ipairs(o.__children) do walk(c, v) end
  end
  local parentVisible = (root.__parent == nil) or root.__parent:IsVisible()
  walk(root, parentVisible)
  return set
end

local function setShown(self, v)
  v = v and true or false
  if self.__shown == v then return end
  local before = visibleSet(self)
  self.__shown = v
  local after = visibleSet(self)
  -- OnShow / OnHide for every frame whose effective visibility changed (parent first).
  local order = {}
  local function walk(o) order[#order + 1] = o; for _, c in ipairs(o.__children) do walk(c) end end
  walk(self)
  for _, o in ipairs(order) do
    if before[o] ~= after[o] and o.__isFrame then
      Sim.RunScript(o, after[o] and "OnShow" or "OnHide")
    end
  end
end
function Region:Show() setShown(self, true) end
function Region:Hide() setShown(self, false) end
function Region:SetShown(v) setShown(self, v) end

function Region:SetParent(p)
  usage(p == nil or isWidget(p) or type(p) == "string", "Usage: SetParent(parent)")
  if type(p) == "string" then p = _G[p] end
  local old = self.__parent
  if old then
    for i, c in ipairs(old.__children) do if c == self then table.remove(old.__children, i); break end end
  end
  self.__parent = p
  if p then p.__children[#p.__children + 1] = self end
end

local function anchorTarget(self, rel)
  if rel == nil then return self.__parent end
  if type(rel) == "string" then
    local t = _G[rel]
    usage(isWidget(t), "SetPoint(): unknown relative frame name '" .. rel .. "'")
    return t
  end
  usage(isWidget(rel), "SetPoint(): relativeTo must be a region, a frame name or nil")
  return rel
end

function Region:SetPoint(point, a, b, c, d)
  usage(type(point) == "string" and POINTS[point:upper()], "SetPoint(): invalid point '" .. tostring(point) .. "'")
  local rel, relPoint, x, y
  if a == nil or isWidget(a) or type(a) == "string" then
    if type(a) == "string" and POINTS[a:upper()] and not _G[a] then
      error("SetPoint(): relativeTo is the point name '" .. a .. "' (missing relative frame?)", 2)
    end
    rel = anchorTarget(self, a)
    if type(b) == "number" then relPoint, x, y = point, b, c
    else relPoint, x, y = b or point, c, d end
  elseif type(a) == "number" then
    rel, relPoint, x, y = self.__parent, point, a, b
  else
    error("SetPoint(): bad argument #2 (" .. type(a) .. ")", 2)
  end
  usage(type(relPoint) == "string" and POINTS[relPoint:upper()], "SetPoint(): invalid relative point '" .. tostring(relPoint) .. "'")
  usage(x == nil or type(x) == "number", "SetPoint(): offsetX must be a number")
  usage(y == nil or type(y) == "number", "SetPoint(): offsetY must be a number")
  usage(rel ~= self, "SetPoint(): cannot anchor to itself")
  for i, p in ipairs(self.__points) do
    if p[1] == point then table.remove(self.__points, i); break end
  end
  self.__points[#self.__points + 1] = { point, rel, relPoint, x or 0, y or 0 }
end
function Region:SetAllPoints(rel)
  rel = anchorTarget(self, rel)
  self.__points = { { "TOPLEFT", rel, "TOPLEFT", 0, 0 }, { "BOTTOMRIGHT", rel, "BOTTOMRIGHT", 0, 0 } }
end
function Region:ClearAllPoints() self.__points = {} end
function Region:GetNumPoints() return #self.__points end
function Region:GetPoint(i)
  local p = self.__points[i or 1]
  if p then return p[1], p[2], p[3], p[4], p[5] end
end

local function spansWidth(self)
  local l, r
  for _, p in ipairs(self.__points) do
    if p[1]:find("LEFT") then l = true end
    if p[1]:find("RIGHT") then r = true end
  end
  return l and r
end
local function spansHeight(self)
  local t, b
  for _, p in ipairs(self.__points) do
    if p[1]:find("TOP") then t = true end
    if p[1]:find("BOTTOM") then b = true end
  end
  return t and b
end
function Region:GetWidth()
  if spansWidth(self) then
    local rel = self.__points[1][2]
    return math.max(0, (rel and rel ~= self and rel:GetWidth() or 0) - 8)
  end
  return self.__w or 0
end
function Region:GetHeight()
  if spansHeight(self) then
    local rel = self.__points[1][2]
    return math.max(0, (rel and rel ~= self and rel:GetHeight() or 0) - 8)
  end
  return self.__h or 0
end
function Region:GetSize() return self:GetWidth(), self:GetHeight() end
local function sizeChanged(self)
  if self.__isFrame then Sim.RunScript(self, "OnSizeChanged", self:GetWidth(), self:GetHeight()) end
end
function Region:SetWidth(w)
  usage(type(w) == "number", "Usage: SetWidth(width) — got " .. type(w))
  if self.__w ~= w then self.__w = w; sizeChanged(self) end
end
function Region:SetHeight(h)
  usage(type(h) == "number", "Usage: SetHeight(height) — got " .. type(h))
  if self.__h ~= h then self.__h = h; sizeChanged(self) end
end
function Region:SetSize(w, h)
  usage(type(w) == "number" and type(h) == "number", "Usage: SetSize(width, height)")
  if self.__w ~= w or self.__h ~= h then self.__w, self.__h = w, h; sizeChanged(self) end
end
function Region:GetCenter() return 960, 540 end
function Region:GetLeft() return 0 end
function Region:GetRight() return self:GetWidth() end
function Region:GetTop() return self:GetHeight() end
function Region:GetBottom() return 0 end
function Region:GetRect() return 0, 0, self:GetWidth(), self:GetHeight() end
function Region:SetAlpha(a) usage(type(a) == "number", "Usage: SetAlpha(alpha)"); self.__alpha = a end
function Region:GetAlpha() return self.__alpha or 1 end
function Region:GetEffectiveAlpha() return self.__alpha or 1 end
function Region:SetScale(s) usage(type(s) == "number" and s > 0, "SetScale(): scale must be > 0"); self.__scale = s end
function Region:GetScale() return self.__scale or 1 end
function Region:GetEffectiveScale() return self.__scale or 1 end
function Region:SetDrawLayer() end
function Region:SetIgnoreParentAlpha() end
function Region:SetIgnoreParentScale() end
function Region:IsMouseOver() return false end
function Region:SetVertexColor(r, g, b, a)
  usage(type(r) == "number" and type(g) == "number" and type(b) == "number", "Usage: SetVertexColor(r, g, b [, a])")
end

-- FontString -----------------------------------------------------------------
local function textArg(v, what)
  local t = type(v)
  usage(v == nil or t == "string" or t == "number", (what or "SetText") .. "(): bad argument (" .. t .. ")")
  return v ~= nil and tostring(v) or nil
end
function FontStringM:SetText(t) self.__text = textArg(t) end
function FontStringM:GetText() return self.__text end
function FontStringM:SetFormattedText(fmt, ...) self.__text = string.format(fmt, ...) end
function FontStringM:GetStringHeight()
  local t = self.__text
  if not t or t == "" then return 0 end
  local lines = 1
  for _ in t:gmatch("\n") do lines = lines + 1 end
  return lines * 12
end
function FontStringM:GetStringWidth() return #(self.__text or "") * 6 end
function FontStringM:GetUnboundedStringWidth() return #(self.__text or "") * 6 end
function FontStringM:SetTextColor(r, g, b, a)
  usage(type(r) == "number" and type(g) == "number" and type(b) == "number", "Usage: SetTextColor(r, g, b [, a])")
end
function FontStringM:GetTextColor() return 1, 1, 1, 1 end
function FontStringM:SetFont() return true end
function FontStringM:SetFontObject(f) usage(f ~= nil, "Usage: SetFontObject(font)") end
function FontStringM:SetJustifyH(j) usage(j == "LEFT" or j == "CENTER" or j == "RIGHT", "SetJustifyH(): invalid value " .. tostring(j)) end
function FontStringM:SetJustifyV(j) usage(j == "TOP" or j == "MIDDLE" or j == "BOTTOM", "SetJustifyV(): invalid value " .. tostring(j)) end
function FontStringM:SetWordWrap() end
function FontStringM:SetNonSpaceWrap() end
function FontStringM:SetMaxLines() end
function FontStringM:SetSpacing(n) usage(type(n) == "number", "Usage: SetSpacing(n)") end
function FontStringM:SetShadowOffset() end
function FontStringM:SetShadowColor() end
function FontStringM:IsTruncated() return false end

-- Texture ----------------------------------------------------------------------
function TextureM:SetTexture(t)
  usage(t == nil or type(t) == "string" or type(t) == "number", "SetTexture(): bad argument (" .. type(t) .. ")")
  if type(t) == "string" and t:find(":", 1, true) then
    Sim.Misuse("Texture:SetTexture", "'" .. t .. "' is not a texture path (renders as a blank/green square)")
  end
  self.__texture = t
  return true
end
function TextureM:GetTexture() return self.__texture end
function TextureM:SetAtlas(a) self.__texture = a end
function TextureM:SetColorTexture(r, g, b, a)
  usage(type(r) == "number" and type(g) == "number" and type(b) == "number", "Usage: SetColorTexture(r, g, b [, a])")
  self.__texture = "color"
end
function TextureM:SetTexCoord(...) usage(select("#", ...) == 4 or select("#", ...) == 8, "Usage: SetTexCoord(l, r, t, b)") end
function TextureM:SetDesaturated() end
function TextureM:SetRotation(r) usage(type(r) == "number", "Usage: SetRotation(radians)"); self.__rotation = r end
function TextureM:GetRotation() return self.__rotation or 0 end
function TextureM:SetBlendMode(m) usage(type(m) == "string", "Usage: SetBlendMode(mode)") end
function TextureM:SetGradient() end

-- Frame ------------------------------------------------------------------------
local SCRIPT_TYPES = {
  OnEvent = true, OnUpdate = true, OnShow = true, OnHide = true, OnEnter = true, OnLeave = true,
  OnMouseDown = true, OnMouseUp = true, OnMouseWheel = true, OnDragStart = true, OnDragStop = true,
  OnSizeChanged = true, OnLoad = true, OnReceiveDrag = true, OnAttributeChanged = true,
  OnHyperlinkClick = true, OnHyperlinkEnter = true, OnHyperlinkLeave = true,
  -- Button / CheckButton
  OnClick = true, PreClick = true, PostClick = true, OnDoubleClick = true, OnEnable = true, OnDisable = true,
  -- EditBox
  OnTextChanged = true, OnEscapePressed = true, OnEnterPressed = true, OnEditFocusGained = true,
  OnEditFocusLost = true, OnTabPressed = true, OnChar = true, OnKeyDown = true, OnKeyUp = true,
  -- Slider / StatusBar / ScrollFrame
  OnValueChanged = true, OnMinMaxChanged = true, OnVerticalScroll = true, OnScrollRangeChanged = true,
  OnHorizontalScroll = true,
  -- GameTooltip
  OnTooltipSetItem = false, OnTooltipSetSpell = false, OnTooltipCleared = true, OnTooltipSetDefaultAnchor = true,
}
local function checkScript(self, name)
  local ok = SCRIPT_TYPES[name]
  if ok == false then
    -- OnTooltipSetItem/Spell were removed in 10.0.2 (TooltipDataProcessor replaced them).
    error(self.__type .. " doesn't have a \"" .. tostring(name) .. "\" script", 3)
  end
  usage(ok, self.__type .. " doesn't have a \"" .. tostring(name) .. "\" script")
end

function FrameM:SetScript(name, fn)
  checkScript(self, name)
  usage(fn == nil or type(fn) == "function", "SetScript(): handler must be a function or nil")
  self.__scripts[name] = fn
  if name == "OnUpdate" then updaters[self] = fn and true or nil end
end
function FrameM:GetScript(name) return self.__scripts[name] end
function FrameM:HasScript(name) return SCRIPT_TYPES[name] == true end
function FrameM:HookScript(name, fn)
  checkScript(self, name)
  usage(type(fn) == "function", "HookScript(): handler must be a function")
  self.__hooks[name] = self.__hooks[name] or {}
  table.insert(self.__hooks[name], fn)
  if name == "OnUpdate" then updaters[self] = true end
end

local function registerFrame(self, event, units)
  usage(type(event) == "string", "Usage: RegisterEvent(event)")
  if Sim.REMOVED_EVENTS[event] then
    error("Attempt to register unknown event \"" .. event .. "\"", 3)
  end
  local list = Sim.eventFrames[event]
  if not list then list = {}; Sim.eventFrames[event] = list end
  local found = false
  for _, f in ipairs(list) do if f == self then found = true end end
  if not found then list[#list + 1] = self end
  self.__events[event] = units or true
  return true
end
function FrameM:RegisterEvent(event) return registerFrame(self, event) end
function FrameM:RegisterUnitEvent(event, ...)
  local units = {}
  for _, u in ipairs({ ... }) do units[u] = true end
  return registerFrame(self, event, units)
end
function FrameM:UnregisterEvent(event)
  self.__events[event] = nil
  local list = Sim.eventFrames[event]
  if list then for i, f in ipairs(list) do if f == self then table.remove(list, i); break end end end
end
function FrameM:UnregisterAllEvents() for ev in pairs(self.__events) do self:UnregisterEvent(ev) end end
function FrameM:IsEventRegistered(event) return self.__events[event] ~= nil end

function FrameM:CreateFontString(name, layer, template)
  return Sim.NewWidget("FontString", name, self, template)
end
function FrameM:CreateTexture(name, layer, template)
  return Sim.NewWidget("Texture", name, self, template)
end
function FrameM:SetFrameStrata(s) usage(STRATA[s], "SetFrameStrata(): invalid strata " .. tostring(s)) end
function FrameM:GetFrameStrata() return "MEDIUM" end
function FrameM:SetFrameLevel(n) usage(type(n) == "number", "Usage: SetFrameLevel(level)"); self.__level = n end
function FrameM:GetFrameLevel() return self.__level or 1 end
function FrameM:SetToplevel() end
function FrameM:SetMovable() end
function FrameM:IsMovable() return true end
function FrameM:SetResizable() end
function FrameM:EnableMouse() end
function FrameM:EnableMouseWheel() end
function FrameM:EnableKeyboard() end
function FrameM:SetPropagateKeyboardInput() end
function FrameM:SetClampedToScreen() end
function FrameM:RegisterForDrag() end
function FrameM:StartMoving() end
function FrameM:StopMovingOrSizing() end
function FrameM:SetUserPlaced() end
function FrameM:SetHyperlinksEnabled() end
function FrameM:SetAttribute(k, v) self.__attrs[k] = v; Sim.RunScript(self, "OnAttributeChanged", k, v) end
function FrameM:GetAttribute(k) return self.__attrs[k] end
function FrameM:GetChildren() return table.unpack(self.__children) end
function FrameM:GetNumChildren() return #self.__children end
function FrameM:Raise() end
function FrameM:Lower() end
function FrameM:SetID(id) self.__id = id end
function FrameM:GetID() return self.__id or 0 end
function FrameM:SetHitRectInsets() end

-- Backdrop (only with BackdropTemplate, as on the real client) ----------------
function BackdropM:SetBackdrop(t) usage(t == nil or type(t) == "table", "Usage: SetBackdrop(backdropInfo)"); self.__backdrop = t end
function BackdropM:GetBackdrop() return self.__backdrop end
function BackdropM:SetBackdropColor(r, g, b, a)
  usage(type(r) == "number" and type(g) == "number" and type(b) == "number", "Usage: SetBackdropColor(r, g, b [, a])")
end
function BackdropM:SetBackdropBorderColor(r, g, b, a)
  usage(type(r) == "number" and type(g) == "number" and type(b) == "number", "Usage: SetBackdropBorderColor(r, g, b [, a])")
end
function BackdropM:ApplyBackdrop() end

-- Button -----------------------------------------------------------------------
function ButtonM:SetText(t)
  t = textArg(t)
  self.__text = t
  if self.__fs then self.__fs:SetText(t) end
end
function ButtonM:GetText() return self.__fs and self.__fs:GetText() or self.__text end
function ButtonM:SetFormattedText(fmt, ...) self:SetText(string.format(fmt, ...)) end
function ButtonM:SetFontString(fs) usage(isWidget(fs) and fs.__type == "FontString", "Usage: SetFontString(fontString)"); self.__fs = fs end
function ButtonM:GetFontString() return self.__fs end
function ButtonM:IsEnabled() return self.__enabled end
function ButtonM:SetEnabled(v)
  v = v and true or false
  if self.__enabled == v then return end
  self.__enabled = v
  Sim.RunScript(self, v and "OnEnable" or "OnDisable")
end
function ButtonM:Enable() self:SetEnabled(true) end
function ButtonM:Disable() self:SetEnabled(false) end
function ButtonM:RegisterForClicks() end
function ButtonM:SetNormalTexture() end
function ButtonM:SetPushedTexture() end
function ButtonM:SetHighlightTexture() end
function ButtonM:SetDisabledTexture() end
function ButtonM:GetNormalTexture() return self.__normalTex end
function ButtonM:LockHighlight() end
function ButtonM:UnlockHighlight() end
function ButtonM:SetNormalFontObject() end
function ButtonM:SetHighlightFontObject() end
function ButtonM:SetDisabledFontObject() end
function ButtonM:SetButtonState() end
function ButtonM:GetTextWidth() return #(self:GetText() or "") * 6 end
function ButtonM:Click(button, down)
  if not self.__enabled then return end
  button = button or "LeftButton"
  if self.__type == "CheckButton" then self.__checked = not self.__checked end
  Sim.RunScript(self, "PreClick", button, down or false)
  Sim.RunScript(self, "OnClick", button, down or false)
  Sim.RunScript(self, "PostClick", button, down or false)
end
function CheckButtonM:SetChecked(v) self.__checked = v and true or false end
function CheckButtonM:GetChecked() return self.__checked or false end

-- ScrollFrame ------------------------------------------------------------------
function ScrollFrameM:SetScrollChild(c) usage(isWidget(c), "Usage: SetScrollChild(frame)"); self.__scrollChild = c; c:SetParent(self) end
function ScrollFrameM:GetScrollChild() return self.__scrollChild end
function ScrollFrameM:SetVerticalScroll(v) usage(type(v) == "number", "Usage: SetVerticalScroll(offset)"); self.__vscroll = v end
function ScrollFrameM:GetVerticalScroll() return self.__vscroll or 0 end
function ScrollFrameM:GetVerticalScrollRange()
  local c = self.__scrollChild
  return math.max(0, (c and c:GetHeight() or 0) - self:GetHeight())
end
function ScrollFrameM:SetHorizontalScroll() end
function ScrollFrameM:UpdateScrollChildRect() end

-- EditBox ----------------------------------------------------------------------
function EditBoxM:SetText(t)
  self.__text = textArg(t) or ""
  Sim.RunScript(self, "OnTextChanged", false)
end
function EditBoxM:GetText() return self.__text or "" end
function EditBoxM:Insert(t) self.__text = (self.__text or "") .. tostring(t) end
function EditBoxM:SetMultiLine() end
function EditBoxM:SetAutoFocus() end
function EditBoxM:SetMaxLetters(n) usage(type(n) == "number", "Usage: SetMaxLetters(n)") end
function EditBoxM:SetTextInsets() end
function EditBoxM:SetFocus() if not self.__focus then self.__focus = true; Sim.RunScript(self, "OnEditFocusGained") end end
function EditBoxM:ClearFocus() if self.__focus then self.__focus = false; Sim.RunScript(self, "OnEditFocusLost") end end
function EditBoxM:HasFocus() return self.__focus or false end
function EditBoxM:HighlightText(a, b) self.__highlight = { a or 0, b or -1 } end
function EditBoxM:SetCursorPosition() end
function EditBoxM:SetFontObject(f) usage(f ~= nil, "Usage: SetFontObject(font)") end
function EditBoxM:SetFont() return true end
function EditBoxM:SetJustifyH() end
function EditBoxM:SetTextColor() end
function EditBoxM:SetNumeric() end
function EditBoxM:SetEnabled(v) self.__enabled = v and true or false end
function EditBoxM:IsEnabled() return self.__enabled end
function EditBoxM:Enable() self.__enabled = true end
function EditBoxM:Disable() self.__enabled = false end

-- Slider / StatusBar -------------------------------------------------------------
local function setValue(self, v)
  usage(type(v) == "number", "Usage: SetValue(value)")
  local lo, hi = self.__min or 0, self.__max or 1
  if v < lo then v = lo elseif v > hi then v = hi end
  local changed = self.__value ~= v
  self.__value = v
  if changed then Sim.RunScript(self, "OnValueChanged", v, false) end
end
function SliderM:SetValue(v) setValue(self, v) end
function SliderM:GetValue() return self.__value or 0 end
function SliderM:SetMinMaxValues(lo, hi)
  usage(type(lo) == "number" and type(hi) == "number" and lo <= hi, "Usage: SetMinMaxValues(min, max)")
  self.__min, self.__max = lo, hi
  if self.__value then
    if self.__value < lo then setValue(self, lo) elseif self.__value > hi then setValue(self, hi) end
  end
end
function SliderM:GetMinMaxValues() return self.__min or 0, self.__max or 1 end
function SliderM:SetValueStep(s) usage(type(s) == "number", "Usage: SetValueStep(step)") end
function SliderM:SetObeyStepOnDrag() end
function SliderM:SetOrientation(o) usage(o == "HORIZONTAL" or o == "VERTICAL", "SetOrientation(): invalid value") end
function SliderM:SetThumbTexture(t)
  local tex = self.__thumb or Sim.NewWidget("Texture", nil, self)
  tex:SetTexture(t)
  self.__thumb = tex
end
function SliderM:GetThumbTexture() return self.__thumb end
function SliderM:SetStepsPerPage() end
function SliderM:IsEnabled() return self.__enabled end
function SliderM:SetEnabled(v) self.__enabled = v and true or false end
function SliderM:Enable() self.__enabled = true end
function SliderM:Disable() self.__enabled = false end
function StatusBarM:SetValue(v) setValue(self, v) end
function StatusBarM:GetValue() return self.__value or 0 end
StatusBarM.SetMinMaxValues = SliderM.SetMinMaxValues
StatusBarM.GetMinMaxValues = SliderM.GetMinMaxValues
function StatusBarM:SetStatusBarTexture(t)
  local tex = self.__bar or Sim.NewWidget("Texture", nil, self)
  if type(t) == "string" or type(t) == "number" then tex:SetTexture(t) end
  self.__bar = tex
end
function StatusBarM:GetStatusBarTexture() return self.__bar end
function StatusBarM:SetStatusBarColor(r, g, b, a)
  usage(type(r) == "number" and type(g) == "number" and type(b) == "number", "Usage: SetStatusBarColor(r, g, b [, a])")
end
function StatusBarM:SetOrientation() end
function StatusBarM:SetReverseFill() end

-- GameTooltip ------------------------------------------------------------------
function TooltipM:SetOwner(owner, anchor)
  usage(isWidget(owner), "Usage: GameTooltip:SetOwner(owner [, anchor])")
  self.__owner = owner
  self.__lines = {}
  self.__item = nil
end
function TooltipM:GetOwner() return self.__owner end
function TooltipM:ClearLines() self.__lines = {}; self.__item = nil end
function TooltipM:SetText(t, r, g, b, a, wrap)
  usage(t == nil or type(t) == "string" or type(t) == "number", "GameTooltip:SetText(): bad text (" .. type(t) .. ")")
  self.__lines = { tostring(t or "") }
end
function TooltipM:AddLine(t, r, g, b, wrap)
  usage(t == nil or type(t) == "string" or type(t) == "number", "GameTooltip:AddLine(): bad text (" .. type(t) .. ")")
  self.__lines = self.__lines or {}
  self.__lines[#self.__lines + 1] = tostring(t or "")
end
function TooltipM:AddDoubleLine(a, b) self:AddLine(tostring(a) .. "  " .. tostring(b)) end
function TooltipM:NumLines() return #(self.__lines or {}) end
function TooltipM:Lines() return self.__lines or {} end
function TooltipM:SetHyperlink(link)
  usage(type(link) == "string", "Usage: GameTooltip:SetHyperlink(link)")
  self.__lines = { link }
  if link:find("item:", 1, true) then self.__item = link end
  Sim.TooltipDataPosted(self, link)
end
function TooltipM:SetItemByID(id) self:SetHyperlink("item:" .. tostring(id)) end
function TooltipM:SetBagItem(bag, slot)
  local it = Sim.BagItem(bag, slot)
  if it then self:SetHyperlink(Sim.ItemLink(it.id)) end
end
function TooltipM:SetSpellByID(id) usage(type(id) == "number", "Usage: SetSpellByID(spellID)"); self.__lines = { "spell " .. id } end
function TooltipM:GetItem()
  if not self.__item then return nil end
  local id = Sim.ItemIdOf(self.__item)
  local it = Sim.ItemData(id)
  return it.name, Sim.ItemLink(id), id
end
function TooltipM:SetMinimumWidth() end
function TooltipM:SetPadding() end
function TooltipM:IsOwned(f) return self.__owner == f end
function TooltipM:FadeOut() self:Hide() end

------------------------------------------------------------------------------
-- Construction
------------------------------------------------------------------------------

local CLASS_METHODS = {
  FontString = { FontStringM },
  Texture = { TextureM },
  Frame = { FrameM },
  Button = { ButtonM, FrameM },
  CheckButton = { CheckButtonM, ButtonM, FrameM },
  ScrollFrame = { ScrollFrameM, FrameM },
  EditBox = { EditBoxM, FrameM },
  Slider = { SliderM, FrameM },
  StatusBar = { StatusBarM, FrameM },
  GameTooltip = { TooltipM, FrameM },
}

-- Members a feature check must NOT find unless the frame really has them.
local ABSENT_UNLESS_BACKDROP = { SetBackdrop = true, SetBackdropColor = true, SetBackdropBorderColor = true,
  GetBackdrop = true, ApplyBackdrop = true }

local function makeMeta(otype, backdrop)
  local chain = CLASS_METHODS[otype] or { FrameM }
  return {
    __index = function(t, k)
      for _, m in ipairs(chain) do
        local f = m[k]; if f ~= nil then return f end
      end
      local f = Region[k]
      if f ~= nil then return f end
      if backdrop then
        f = BackdropM[k]; if f ~= nil then return f end
      end
      if type(k) ~= "string" or not k:match("^[A-Z]") or ABSENT_UNLESS_BACKDROP[k] then return nil end
      -- Permissive fallback for unknown methods (logged; review at the end of the run).
      local key = otype .. ":" .. k
      Sim.unknownMethods[key] = (Sim.unknownMethods[key] or 0) + 1
      return function() end
    end,
    __tostring = function(t) return otype .. "(" .. tostring(rawget(t, "__name") or "anonymous") .. ")" end,
  }
end
local metas = {}
local function metaFor(otype, backdrop)
  local key = otype .. (backdrop and "+bd" or "")
  if not metas[key] then metas[key] = makeMeta(otype, backdrop) end
  return metas[key]
end

function Sim.NewWidget(otype, name, parent, template)
  usage(name == nil or type(name) == "string", "CreateFrame(): name must be a string or nil")
  usage(parent == nil or isWidget(parent), "CreateFrame(): parent must be a frame (got " .. type(parent) .. ")")
  local backdrop = false
  if type(template) == "string" and otype ~= "FontString" and otype ~= "Texture" then
    for tpl in template:gmatch("[^,%s]+") do
      if not TEMPLATES[tpl] then error("CreateFrame(): Couldn't find inherited node \"" .. tpl .. "\"", 3) end
      if tpl == "BackdropTemplate" then backdrop = true end
    end
  end
  local o = {
    __isWidget = true, __type = otype, __name = name, __parent = nil, __children = {},
    __shown = true, __scripts = {}, __hooks = {}, __events = {}, __points = {}, __attrs = {},
    __enabled = true, __isFrame = (otype ~= "FontString" and otype ~= "Texture"), __template = template,
  }
  setmetatable(o, metaFor(otype, backdrop))
  if parent then o.__parent = parent; parent.__children[#parent.__children + 1] = o end
  if name then _G[name] = o end
  all[#all + 1] = o
  -- Template children the addon relies on.
  if type(template) == "string" then
    if template:find("UIPanelScrollFrameTemplate", 1, true) then
      o.ScrollBar = Sim.NewWidget("Slider", nil, o)
    end
    if template:find("UIPanelButtonTemplate", 1, true) then
      o.Text = Sim.NewWidget("FontString", nil, o)
      o.__fs = o.Text
    end
    if template:find("UICheckButtonTemplate", 1, true) then
      o.Text = Sim.NewWidget("FontString", nil, o)
    end
  end
  return o
end

function CreateFrame(otype, name, parent, template, id)
  usage(type(otype) == "string" and FRAME_TYPES[otype], "CreateFrame(): unknown frame type '" .. tostring(otype) .. "'")
  if type(parent) == "string" then parent = _G[parent] end
  local f = Sim.NewWidget(otype, name, parent, template)
  if id then f.__id = id end
  return f
end

function CreateFont(name)
  local f = { __font = name }
  _G[name] = f
  return f
end

-- Runs a script and its hooks (each protected: an error fails the run, like the client's error popup).
function Sim.RunScript(f, name, ...)
  local s = f.__scripts[name]
  local label = name .. " (" .. tostring(f) .. ")"
  if s then Sim.SafeCall(label, s, f, ...) end
  for _, h in ipairs(f.__hooks[name] or {}) do Sim.SafeCall(label .. " hook", h, f, ...) end
end

function Sim.RunOnUpdate(dt)
  local list = {}
  for f in pairs(updaters) do list[#list + 1] = f end
  for _, f in ipairs(list) do
    if f:IsVisible() and (f.__scripts.OnUpdate or f.__hooks.OnUpdate) then
      Sim.RunScript(f, "OnUpdate", dt)
    end
  end
end

-- Mouse helpers for scenarios.
function Sim.Click(f, button) usage(isWidget(f), "Sim.Click(frame)"); f:Click(button or "LeftButton", false) end
function Sim.Hover(f) Sim.RunScript(f, "OnEnter"); Sim.RunScript(f, "OnLeave") end

function Sim.AllWidgets() return all end

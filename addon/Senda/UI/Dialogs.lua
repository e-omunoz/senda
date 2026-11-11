-- Diálogos: texto copiable (exportar observaciones) y enlace "Leer más".
--   Senda.UI:CopyDialog(title, text, hint)   -- texto multilínea seleccionado, listo para Ctrl+C
--   Senda.UI:ShowLink(path)                  -- URL de la web (base Senda.WEB) en una línea copiable
local _, Senda = ...
local UI = Senda.UI
local L = Senda.L

local copy

local function CopyFrame()
  if copy then return copy end
  local f = UI:Frame("SendaCopyDialog", UIParent, { title = "Senda", width = 560, height = 360,
    strata = "DIALOG", posKey = "copy" })
  f:Hide()
  tinsert(UISpecialFrames, "SendaCopyDialog")

  f.hint = UI:Label(f, "", "GameFontDisableSmall")
  f.hint:SetPoint("BOTTOMLEFT", 12, 10)
  f.hint:SetPoint("BOTTOMRIGHT", -12, 10)

  local area = CreateFrame("Frame", nil, f, BackdropTemplateMixin and "BackdropTemplate" or nil)
  UI:Backdrop(area, "inset")
  area:SetPoint("TOPLEFT", 10, -36)
  area:SetPoint("BOTTOMRIGHT", -10, 30)

  local sf, child = UI:ScrollArea(area)
  local eb = CreateFrame("EditBox", nil, child)
  eb:SetMultiLine(true)
  eb:SetAutoFocus(false)
  eb:SetFontObject("ChatFontNormal")
  eb:SetMaxLetters(0)
  eb:SetPoint("TOPLEFT", 4, -4)
  eb:SetPoint("RIGHT", child, "RIGHT", -4, 0)
  eb:SetScript("OnEscapePressed", function() f:Hide() end)
  -- Solo lectura: si se edita, se restaura el texto.
  eb:SetScript("OnTextChanged", function(self, user)
    if user and self.fixed then self:SetText(self.fixed); self:HighlightText() end
    child:SetHeight(math.max(sf:GetHeight(), (self:GetHeight() or 0) + 8))
  end)
  eb:SetScript("OnEditFocusGained", function(self) self:HighlightText() end)
  sf:HookScript("OnMouseDown", function() eb:SetFocus() end)
  f.eb, f.sf = eb, sf

  -- Línea única (enlaces).
  local line = CreateFrame("EditBox", nil, f, BackdropTemplateMixin and "BackdropTemplate" or nil)
  UI:Backdrop(line, "inset")
  line:SetAutoFocus(false)
  line:SetFontObject("ChatFontNormal")
  line:SetHeight(26)
  line:SetTextInsets(8, 8, 0, 0)
  line:SetPoint("TOPLEFT", 12, -44)
  line:SetPoint("TOPRIGHT", -12, -44)
  line:SetScript("OnEscapePressed", function() f:Hide() end)
  line:SetScript("OnEnterPressed", function() f:Hide() end)
  line:SetScript("OnTextChanged", function(self, user)
    if user and self.fixed then self:SetText(self.fixed); self:HighlightText() end
  end)
  line:SetScript("OnEditFocusGained", function(self) self:HighlightText() end)
  f.line = line

  copy = f
  return f
end

function UI:CopyDialog(title, text, hint)
  local f = CopyFrame()
  f:SetSize(560, 360)
  f.title:SetText(title or "Senda")
  f.hint:SetText(hint or L.COPY_HINT)
  f.line:Hide()
  f.sf:GetParent():Show()
  f.eb.fixed = text or ""
  f.eb:SetWidth(math.max(100, f.sf:GetWidth() - 8))
  f.eb:SetText(text or "")
  f:Show()
  f.eb:SetFocus()
  f.eb:HighlightText()
end

function UI:ShowLink(path, title)
  local url = tostring(path or "")
  if not url:match("^https?://") then
    url = Senda.WEB .. url:gsub("^/", "")
  end
  local f = CopyFrame()
  f:SetSize(520, 110)
  f.title:SetText(title or L.LINK_TITLE)
  f.hint:SetText(L.COPY_HINT)
  f.sf:GetParent():Hide()
  f.line.fixed = url
  f.line:SetText(url)
  f.line:Show()
  f:Show()
  f.line:SetFocus()
  f.line:HighlightText()
end

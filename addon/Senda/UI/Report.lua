-- Ventana de informe de errores: /senda informe y el botón del bicho en la cabecera del HUD.
--   Senda.Report:Open()                  abre la ventana (con el contexto tomado en ese momento)
--   Senda.Report:Context()               -> tabla con los datos del informe (sin nombres de personaje ni reino)
--   Senda.Report:Text(desc, ctx)         -> informe completo en texto
--   Senda.Report:IssueURL(desc, ctx)     -> enlace de GitHub «nueva incidencia» con título y cuerpo corto, < 2000 caracteres
-- El jugador cuenta qué pasó; el informe añade lo que hace falta para arreglarlo: guía, paso (id y texto),
-- posición, nivel, raza y clase, versión de Senda, build y idioma del cliente, otros addons, los últimos 20
-- errores de Lua que Senda capturó (Core/Events.lua) y el estado en el registro de las misiones del paso.
-- No lleva nombre de personaje ni de reino. El juego no da portapapeles ni abre enlaces: "Copiar" selecciona
-- el texto para Ctrl+C y el enlace sale en una línea copiable.
-- Idea tomada de Polestar (UI/Report.lua); el código es propio.
local _, Senda = ...
local UI, Compat = Senda.UI, Senda.Compat
local Cond = Senda.Conditions
local L = Senda.L

local Report = {}
Senda.Report = Report

Report.ISSUES_URL = "https://github.com/e-omunoz/senda/issues/new"
Report.URL_MAX = 1900   -- el límite práctico de un enlace es 2000; se deja margen
Report.DESC_MAX = 600   -- letras de la descripción
Report.ERRORS_MAX = 20

local format, concat = string.format, table.concat

local function Plain(text)
  return ((tostring(text or ""):gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""):gsub("|T.-|t", "")))
end

local function OneLine(text, max)
  text = Plain(text):gsub("%s+", " ")
  if max and #text > max then text = text:sub(1, max) .. "…" end
  return text
end

local function Trim(s)
  return ((tostring(s or ""):gsub("^%s+", ""):gsub("%s+$", "")))
end

------------------------------------------------------------------------------
-- Contexto
------------------------------------------------------------------------------

local function QuestState(q)
  local S, Engine = L.REPORT_QSTATE, Senda.Engine
  if Engine:IsQuestSkipped(q) then return S.skipped end
  if Compat.IsQuestFailed(q) then return S.failed end
  if Compat.IsOnQuest(q) then return Compat.IsQuestComplete(q) and S.ready or S.log end
  if Compat.IsQuestDone(q) or (Engine.turnedIn and Engine.turnedIn[q]) then return S.done end
  return S.none
end

function Report:Context()
  local Engine = Senda.Engine
  local c = {
    version = Senda.VERSION, build = Compat.Build(), locale = Senda.LOCALE,
    level = Compat.PlayerLevel(), race = Compat.PlayerRace(), class = Compat.PlayerClass(),
    faction = Compat.PlayerFaction(),
    guideId = Engine:GuideId(), quests = {}, skipped = Engine:SkippedCount(),
    addons = Compat.LoadedAddons(40), errors = {},
  }
  local step = Engine:CurrentStep()
  if step then
    c.stepId, c.stepDo = step.id, step["do"]
    c.stepIndex, c.stepTotal = Engine:Index(), #Engine:Steps()
    c.stepText = Senda.HUD and OneLine(Senda.HUD:StepText(step), 200) or nil
    for i, q in ipairs(Cond:Quests(step) or {}) do
      if i > 4 then break end
      local parts = {}
      if Compat.IsOnQuest(q) then
        for _, o in ipairs(Compat.QuestObjectives(q)) do
          if o.have and o.need then parts[#parts + 1] = format("%d/%d%s", o.have, o.need, o.finished and "+" or "") end
        end
      end
      c.quests[#c.quests + 1] = { id = q, state = QuestState(q), objectives = concat(parts, " ") }
    end
  end
  local map, x, y = Compat.PlayerMapPos()
  if map then
    c.map, c.x, c.y = map, x and x * 100, y and y * 100
    c.mapName = Compat.MapName(map)
  end
  local target = Senda.Arrow and Senda.Arrow.GetTarget and Senda.Arrow:GetTarget()
  if type(target) == "table" and target.map then
    c.arrow = format("%s (%s %.1f, %.1f)", OneLine(target.label or "?", 60), tostring(target.map),
      (target.x or 0) * 100, (target.y or 0) * 100)
  end
  local list = Senda.Errors and Senda.Errors.list or {}
  for i = math.max(1, #list - Report.ERRORS_MAX + 1), #list do c.errors[#c.errors + 1] = list[i] end
  return c
end

-- Informe completo en texto (lo que se copia). `desc` es lo que escribió el jugador.
function Report:Text(desc, c)
  c = c or self:Context()
  local lab = L.REPORT_LABELS
  local lines = {}
  local function add(key, value) lines[#lines + 1] = format("%s: %s", lab[key], tostring(value)) end
  desc = Trim(desc)
  if desc ~= "" then add("desc", desc) end
  add("version", c.version)
  add("client", format("%s (%s)", c.build, tostring(c.locale)))
  add("char", format("%s %s %s %s", tostring(c.level or "?"), tostring(c.race or "?"), tostring(c.class or "?"),
    tostring(c.faction or "")))
  add("guide", c.guideId or "-")
  if c.stepId then
    add("step", format("%s (%s/%s) [%s]", c.stepId, tostring(c.stepIndex), tostring(c.stepTotal), tostring(c.stepDo)))
    if c.stepText and c.stepText ~= "" then add("text", c.stepText) end
  end
  if c.map then
    add("pos", format("%s%s %.1f, %.1f", tostring(c.map), c.mapName and (" (" .. c.mapName .. ")") or "", c.x or 0, c.y or 0))
  end
  if c.arrow then add("arrow", c.arrow) end
  if #c.quests > 0 then
    local q = {}
    for _, e in ipairs(c.quests) do
      q[#q + 1] = format("%d %s%s", e.id, e.state, e.objectives ~= "" and (" " .. e.objectives) or "")
    end
    add("quests", concat(q, "; "))
  end
  if c.skipped > 0 then add("skipped", c.skipped) end
  local others = {}
  for _, name in ipairs(c.addons) do
    if name ~= Senda.ADDON then others[#others + 1] = name end
  end
  add("addons", #others > 0 and concat(others, ", ") or L.REPORT_NONE)
  lines[#lines + 1] = format(lab.errors, #c.errors) .. ":"
  if #c.errors == 0 then
    lines[#lines + 1] = "  " .. L.REPORT_NONE
  else
    for i, e in ipairs(c.errors) do
      lines[#lines + 1] = format("  %d. %s%s", i, e.n > 1 and format("(×%d) ", e.n) or "", OneLine(e.msg))
    end
  end
  return concat(lines, "\n")
end

------------------------------------------------------------------------------
-- Enlace de GitHub
------------------------------------------------------------------------------

local function Enc(s)
  return (tostring(s):gsub("[^%w%-%._~]", function(ch) return format("%%%02X", ch:byte()) end))
end
Report.Encode = Enc

-- Prefijo de `text` (caracteres UTF-8 enteros) cuya codificación cabe en `room`; con «…» si hubo que cortar.
local function EncodeFit(text, room)
  if room <= 0 then return "" end
  local whole = Enc(text)
  if #whole <= room then return whole end
  local ell = Enc("…")
  local out, used = {}, 0
  for ch in text:gmatch("[\1-\127\194-\244][\128-\191]*") do
    local e = Enc(ch)
    if used + #e > room - #ell then break end
    out[#out + 1] = e
    used = used + #e
  end
  if used == 0 and room < #ell then return "" end
  return concat(out) .. ell
end

function Report:IssueURL(desc, c)
  c = c or self:Context()
  local title = c.stepId and format(L.REPORT_ISSUE_TITLE, c.stepId) or L.REPORT_ISSUE_TITLE_NOSTEP
  local base = Report.ISSUES_URL .. "?title=" .. Enc(title) .. "&body="
  -- Cuerpo corto: la descripción y lo mínimo para localizar el paso; el informe completo se pega aparte.
  local short = {
    format("Senda %s · %s (%s)", c.version, c.build, tostring(c.locale)),
    format("%s · %s", c.guideId or "-", c.stepId or "-"),
    format("%s %s %s", tostring(c.level or "?"), tostring(c.race or "?"), tostring(c.class or "?")),
  }
  if c.map then short[#short + 1] = format("%s %.1f, %.1f", tostring(c.map), c.x or 0, c.y or 0) end
  local tails = {
    "\n\n" .. concat(short, "\n") .. "\n\n" .. L.REPORT_PASTE,
    "\n\n" .. short[1] .. "\n" .. short[2],
    "",
  }
  desc = Trim(desc)
  local limit = Report.URL_MAX - #base
  for i, tail in ipairs(tails) do
    local t = Enc(tail)
    local room = limit - #t
    if room >= 80 or i == #tails then
      return base .. EncodeFit(desc, room) .. t
    end
  end
  return base
end

------------------------------------------------------------------------------
-- Ventana
------------------------------------------------------------------------------

local frame

-- Área con borde y un EditBox multilínea que se desplaza. Devuelve área, editbox.
local function TextBox(parent, readonly)
  local area = CreateFrame("Frame", nil, parent, BackdropTemplateMixin and "BackdropTemplate" or nil)
  UI:Backdrop(area, "inset")
  local sf, child = UI:ScrollArea(area)
  local eb = CreateFrame("EditBox", nil, child)
  eb:SetMultiLine(true)
  eb:SetAutoFocus(false)
  eb:SetFontObject("ChatFontNormal")
  eb:SetMaxLetters(readonly and 0 or Report.DESC_MAX)
  eb:SetPoint("TOPLEFT", 4, -4)
  eb:SetPoint("RIGHT", child, "RIGHT", -4, 0)
  eb:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
  eb:SetScript("OnTextChanged", function(self, user)
    if readonly and user and self.fixed then self:SetText(self.fixed); self:HighlightText() end
    child:SetHeight(math.max(sf:GetHeight(), (self:GetHeight() or 0) + 8))
    if not readonly and user then Report:Refresh() end
  end)
  if readonly then eb:SetScript("OnEditFocusGained", function(self) self:HighlightText() end) end
  sf:HookScript("OnMouseDown", function() eb:SetFocus() end)
  area.sf, area.eb = sf, eb
  return area, eb
end

local function Build()
  if frame then return frame end
  local f = UI:Frame("SendaReportFrame", UIParent, { title = L.REPORT_TITLE, width = 580, height = 540,
    strata = "DIALOG", posKey = "report" })
  f:Hide()
  tinsert(UISpecialFrames, "SendaReportFrame")

  f.descLabel = UI:Label(f, L.REPORT_DESC_LABEL)
  f.descLabel:SetPoint("TOPLEFT", 12, -36)
  local descArea, descEb = TextBox(f, false)
  descArea:SetPoint("TOPLEFT", 10, -54)
  descArea:SetPoint("TOPRIGHT", -10, -54)
  descArea:SetHeight(84)
  f.desc = descEb

  f.ctxLabel = UI:Label(f, L.REPORT_CONTEXT_LABEL)
  f.ctxLabel:SetPoint("TOPLEFT", 12, -148)
  f.copy = UI:Button(f, L.REPORT_COPY, 90, 22, function()
    f.report:SetFocus()
    f.report:HighlightText()
    Senda:Print(L.REPORT_COPY_DONE)
  end)
  f.copy:SetPoint("TOPRIGHT", -10, -143)

  local repArea, repEb = TextBox(f, true)
  repArea:SetPoint("TOPLEFT", 10, -168)
  repArea:SetPoint("BOTTOMRIGHT", -10, 112)
  f.report, f.reportSf = repEb, repArea.sf

  f.urlLabel = UI:Label(f, L.REPORT_URL_LABEL)
  f.urlLabel:SetPoint("BOTTOMLEFT", 12, 88)
  local line = CreateFrame("EditBox", nil, f, BackdropTemplateMixin and "BackdropTemplate" or nil)
  UI:Backdrop(line, "inset")
  line:SetAutoFocus(false)
  line:SetFontObject("ChatFontNormal")
  line:SetHeight(26)
  line:SetTextInsets(8, 8, 0, 0)
  line:SetMaxLetters(0)
  line:SetPoint("BOTTOMLEFT", 12, 56)
  line:SetPoint("BOTTOMRIGHT", -12, 56)
  line:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
  line:SetScript("OnTextChanged", function(self, user)
    if user and self.fixed then self:SetText(self.fixed); self:HighlightText() end
  end)
  line:SetScript("OnEditFocusGained", function(self) self:HighlightText() end)
  f.url = line

  f.hint = UI:Label(f, L.REPORT_HINT, "GameFontDisableSmall")
  f.hint:SetPoint("BOTTOMLEFT", 12, 12)
  f.hint:SetPoint("BOTTOMRIGHT", -12, 12)

  frame = f
  return f
end

-- Recalcula el informe y el enlace con la descripción actual (el contexto no cambia mientras está abierta).
function Report:Refresh()
  local f = frame
  if not f or not f.ctx then return end
  local desc = f.desc:GetText() or ""
  local text = self:Text(desc, f.ctx)
  f.report.fixed = text
  f.report:SetWidth(math.max(100, (f.reportSf:GetWidth() or 0) - 8))
  f.report:SetText(text)
  local url = self:IssueURL(desc, f.ctx)
  f.url.fixed = url
  f.url:SetText(url)
  f.url:SetCursorPosition(0)
end

function Report:Open()
  local f = Build()
  f.ctx = self:Context()
  f:Show()
  self:Refresh()
  f.desc:SetFocus()
end

function Report:IsOpen() return frame ~= nil and frame:IsShown() end

-- Senda / Modules / Bars
-- Distribución recomendada de barras de acción para tu nivel, con iconos reales (gris = aún no lo tienes).
-- Fuente: páginas con [[slot]] slot, key, spell | macro | item, icon, minlevel, bar (si existen); si no, se deduce
-- del conocimiento: barra principal = rotación de tu nivel + macros SND_; barra inferior izquierda = el resto de
-- hechizos entrenados. Colocar en tus barras es opcional, pide confirmación y nunca se hace en combate.
local ADDON, Senda = ...
local M = Senda.Mod
if not M then return end
local L = M.L

local B = {}
Senda.Modules.Bars = B

local KEYS = { "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "=" }
local MAIN, LOWER_LEFT = 1, 61   -- primera casilla de la barra principal y de la inferior izquierda

local function IsPassive(id)
  if C_Spell and C_Spell.IsSpellPassive then
    local ok, r = pcall(C_Spell.IsSpellPassive, id); if ok then return r end
  end
  if IsPassiveSpell then
    local ok, r = pcall(IsPassiveSpell, id); if ok then return r end
  end
  return false
end

-- { title, rows = { { slot, key, spell, alt, alt2, spell_name, macro, item, icon, minlevel } } }
function B.Layout()
  local level = M.Level()
  -- 1) explícito en el conocimiento: [[slot]] (con `bar` = título) o [[bar]] + [[bar.slot]] (con `level`), que es
  --    el formato de los archivos kind = "bars".
  local explicit, groups = {}, {}
  local function add(title, s)
    if type(s) ~= "table" or not s.slot then return end
    title = title or (L.MOD_BARS_MAIN or "Barra principal")
    if not groups[title] then groups[title] = { title = title, rows = {} }; table.insert(explicit, groups[title]) end
    table.insert(groups[title].rows, { slot = s.slot, key = s.key, spell = s.spell, alt = s.alt, alt2 = s.alt2,
      spell_name = s.spell_name, macro = s.macro, item = s.item, icon = s.icon, note = s.note,
      minlevel = s.minlevel or s.level })
  end
  for _, p in ipairs(M.Pages()) do
    for _, s in ipairs(type(p.slot) == "table" and p.slot or {}) do add(type(s) == "table" and s.bar or nil, s) end
    for _, b in ipairs(type(p.bar) == "table" and p.bar or {}) do
      if type(b) == "table" then
        for _, s in ipairs(type(b.slot) == "table" and b.slot or {}) do add(b.title, s) end
      end
    end
  end
  if #explicit > 0 then
    for _, g in ipairs(explicit) do table.sort(g.rows, function(a, b) return a.slot < b.slot end) end
    return explicit
  end

  -- 2) deducido: rotación + macros + resto de hechizos
  local K = Senda.Modules.Knowledge
  local MC = Senda.Modules.Macros
  local entries, used = {}, {}
  local phase = K and K.PhaseFor and K.PhaseFor(level)
  for _, id in ipairs(phase and phase.spells or {}) do
    if not used[id] then used[id] = true; table.insert(entries, { spell = id, minlevel = phase.from }) end
  end
  if MC and MC.List then
    for _, e in ipairs(MC.List()) do
      if (e.m.minlevel or 1) <= level then table.insert(entries, { macro = e.name, icon = e.icon, minlevel = e.m.minlevel or 1 }) end
    end
  end
  if K and K.TrainList then
    local seenName = {}
    for _, e in ipairs(entries) do if e.spell then seenName[M.SpellName(e.spell) or e.spell] = true end end
    for _, e in ipairs(K.TrainList()) do
      local name = M.SpellName(e.spell)
      if e.level <= level and not used[e.spell] and not (name and seenName[name]) and not IsPassive(e.spell) then
        used[e.spell] = true
        if name then seenName[name] = true end
        table.insert(entries, { spell = e.spell, minlevel = e.level })
      end
    end
  end
  local main = { title = L.MOD_BARS_MAIN or "Barra principal (1 a =)", rows = {} }
  local lower = { title = L.MOD_BARS_LOWER or "Inferior izquierda", rows = {} }
  for i, e in ipairs(entries) do
    if i <= 12 then
      e.slot, e.key = MAIN + i - 1, KEYS[i]
      table.insert(main.rows, e)
    elseif i <= 24 then
      e.slot = LOWER_LEFT + i - 13
      table.insert(lower.rows, e)
    end
  end
  local out = {}
  if #main.rows > 0 then table.insert(out, main) end
  if #lower.rows > 0 then table.insert(out, lower) end
  return out
end

local function MacroIndex(name)
  local MC = Senda.Modules.Macros
  if MC and MC.Index then return MC.Index(name) end
  if GetMacroIndexByName then local i = GetMacroIndexByName(name); if i and i > 0 then return i end end
  return nil
end

-- Hechizo de la casilla: el primero que conoces de spell, alt, alt2 (p. ej. Armadura de mago > de hielo > de
-- Escarcha). Devuelve id, conocido; si no conoces ninguno, el principal.
local function EntrySpell(e)
  local first
  for _, k in ipairs({ "spell", "alt", "alt2" }) do
    local id = e[k]
    if id then
      first = first or id
      if M.Known(id) then return id, true end
    end
  end
  return first, false
end

local function EntryAvailable(e)
  if e.macro then return MacroIndex(e.macro) ~= nil end
  if e.item then return M.ItemCount(e.item) > 0 end
  local id, known = EntrySpell(e)
  if id then return known end
  return e.spell_name ~= nil and M.InBook(e.spell_name)
end

local function EntryIcon(e)
  if e.item then return M.ItemIcon(e.item) end
  if type(e.icon) == "number" then return M.SpellIcon(e.icon) end
  if type(e.icon) == "string" then
    if e.icon:find(":", 1, true) then
      -- "spell:<id>", "item:<id>" o "name:<hechizo>" (formato del conocimiento): no es una ruta de textura.
      local MC = Senda.Modules.Macros
      local tex = MC and MC.IconFor and MC.IconFor({ icon = e.icon })
      if type(tex) == "number" then return tex end
    elseif e.icon:find("\\", 1, true) then
      return e.icon
    else
      return "Interface\\Icons\\" .. e.icon
    end
  end
  local id = EntrySpell(e)
  if id then return M.SpellIcon(id) end
  if e.spell_name then return M.SpellIcon(e.spell_name) end
  return nil
end

local function EntryLabel(e)
  if e.macro then return e.macro end
  if e.item then return M.ItemName(e.item) or ("#" .. e.item) end
  local id = EntrySpell(e)
  if not id and e.spell_name then return e.spell_name end
  return M.SpellName(id) or ("#" .. tostring(id))
end

------------------------------------------------------------------------
-- Colocar (fuera de combate)
------------------------------------------------------------------------
local function PickupEntry(e)
  if e.macro then
    local idx = MacroIndex(e.macro)
    if idx and PickupMacro then PickupMacro(idx); return true end
    return false
  end
  if e.item then
    local f = (C_Item and C_Item.PickupItem) or _G.PickupItem
    if f and M.ItemCount(e.item) > 0 then pcall(f, e.item); return true end
    return false
  end
  local id, known = EntrySpell(e)
  local name
  if id then
    if not known then return false end
    name = M.SpellName(id)
  elseif e.spell_name and M.InBook(e.spell_name) then
    name = e.spell_name
  else
    return false
  end
  local bi = M.BookIndex(name)
  if bi then
    local bank = (Enum and Enum.SpellBookSpellBank and Enum.SpellBookSpellBank.Player) or "spell"
    local f = (C_SpellBook and C_SpellBook.PickupSpellBookItem) or _G.PickupSpellBookItem
    if f and pcall(f, bi, bank) then return true end
  end
  local f = (C_Spell and C_Spell.PickupSpell) or _G.PickupSpell
  if f then return (pcall(f, id or name)) end
  return false
end

function B.Place()
  if M.InCombat() then M.Print(L.MOD_BARS_COMBAT or "No se puede en combate."); return end
  if not (PlaceAction and ClearCursor) then return end
  local layout = B.Layout()
  local hasMacro = false
  for _, g in ipairs(layout) do for _, e in ipairs(g.rows) do if e.macro then hasMacro = true end end end
  local MC = Senda.Modules.Macros
  if hasMacro and MC and MC.CreateAll then MC.CreateAll(true) end
  local onlyEmpty = M.Opt("mod_bars_empty") ~= false
  local placed, skipped, missing = 0, 0, 0
  for _, g in ipairs(layout) do
    for _, e in ipairs(g.rows) do
      if onlyEmpty and HasAction and HasAction(e.slot) then
        skipped = skipped + 1
      else
        ClearCursor()
        local picked = PickupEntry(e)
        if picked and GetCursorInfo and GetCursorInfo() then
          PlaceAction(e.slot)
          placed = placed + 1
        else
          missing = missing + 1
        end
        ClearCursor()
      end
    end
  end
  M.Print(string.format(L.MOD_BARS_DONE or "Barras: %d colocadas, %d casillas ocupadas sin tocar, %d pendientes (aún no las tienes).", placed, skipped, missing))
  B.Refresh()
end

------------------------------------------------------------------------
-- Pestaña
------------------------------------------------------------------------
local ui = { buttons = {}, titles = {} }

local function IconButton(i)
  local b = ui.buttons[i]
  if b then return b end
  b = CreateFrame("Button", nil, ui.grid)
  b:SetSize(36, 36)
  b.icon = b:CreateTexture(nil, "ARTWORK")
  b.icon:SetAllPoints()
  local border = b:CreateTexture(nil, "OVERLAY")
  border:SetTexture("Interface\\Buttons\\UI-Quickslot2")
  border:SetPoint("CENTER")
  border:SetSize(62, 62)
  b.key = b:CreateFontString(nil, "OVERLAY", "NumberFontNormalSmallGray")
  b.key:SetPoint("TOPRIGHT", -1, -2)
  b.lv = b:CreateFontString(nil, "OVERLAY", "NumberFontNormal")
  b.lv:SetPoint("BOTTOMLEFT", 2, 2)
  b.m = b:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  b.m:SetPoint("BOTTOMRIGHT", -1, 1)
  b:SetScript("OnEnter", function(self)
    local e = self.entry
    if not e or not GameTooltip then return end
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:AddLine(EntryLabel(e))
    if e.macro then GameTooltip:AddLine(L.MOD_BARS_MACRO or "Macro de Senda", 0.3, 0.82, 0.66) end
    if e.key then GameTooltip:AddLine((L.MOD_BARS_KEY or "Tecla:") .. " " .. e.key, 1, 1, 1) end
    GameTooltip:AddLine(string.format(L.MOD_BARS_FROM or "Desde el nivel %d", e.minlevel or 1), 1, 1, 1)
    if not EntryAvailable(e) then GameTooltip:AddLine(L.MOD_BARS_NOT_YET or "Aún no disponible", 1, 0.5, 0.25) end
    GameTooltip:Show()
  end)
  b:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
  ui.buttons[i] = b
  return b
end

local function Title(i)
  local t = ui.titles[i]
  if not t then t = ui.grid:CreateFontString(nil, "OVERLAY", "GameFontNormal"); ui.titles[i] = t end
  return t
end

function B.Refresh()
  if not ui.grid then return end
  local level = M.Level()
  local layout = B.Layout()
  for _, b in ipairs(ui.buttons) do b:Hide() end
  for _, t in ipairs(ui.titles) do t:Hide() end
  local y, n = -6, 0
  for gi, g in ipairs(layout) do
    local t = Title(gi)
    t:ClearAllPoints(); t:SetPoint("TOPLEFT", 8, y); t:SetText(g.title); t:Show()
    y = y - 20
    for i, e in ipairs(g.rows) do
      n = n + 1
      local b = IconButton(n)
      b.entry = e
      b:ClearAllPoints()
      b:SetPoint("TOPLEFT", 8 + ((i - 1) % 12) * 42, y - math.floor((i - 1) / 12) * 42)
      b.icon:SetTexture(EntryIcon(e) or "Interface\\Icons\\INV_Misc_QuestionMark")
      local ok = EntryAvailable(e)
      b.icon:SetDesaturated(not ok)
      b.icon:SetAlpha(ok and 1 or 0.55)
      b.key:SetText(e.key or "")
      b.lv:SetText(level >= (e.minlevel or 1) and "" or tostring(e.minlevel))
      b.m:SetText(e.macro and "|cff4dd1a8M|r" or "")
      b:Show()
    end
    y = y - (math.floor((math.max(1, #g.rows) - 1) / 12) + 1) * 42 - 10
  end
  if #layout == 0 then
    local t = Title(1)
    t:ClearAllPoints(); t:SetPoint("TOPLEFT", 8, y); t:SetText(L.MOD_BARS_NONE or "Todavía no hay datos para sugerir barras a tu clase."); t:Show()
    y = y - 24
  end
  ui.grid:SetHeight(-y + 4)
  ui.tips:ClearAllPoints()
  ui.tips:SetPoint("TOPLEFT", ui.grid, "BOTTOMLEFT", 8, -4)
  ui.tips:SetPoint("RIGHT", ui.body, "RIGHT", -8, 0)
end

local function Build(parent)
  local bar, body = M.Toolbar(parent)
  ui.body = body
  local place = M.Button(bar, L.MOD_BARS_PLACE or "Colocar en mis barras", 170, function()
    if M.InCombat() then M.Print(L.MOD_BARS_COMBAT or "No se puede en combate."); return end
    local onlyEmpty = M.Opt("mod_bars_empty") ~= false
    M.Confirm(onlyEmpty and (L.MOD_BARS_CONFIRM_EMPTY or "Senda pondrá lo recomendado solo en las casillas vacías de la barra principal y la inferior izquierda. ¿Seguir?")
      or (L.MOD_BARS_CONFIRM_ALL or "Esto sustituye lo que tengas en la barra principal y en la inferior izquierda por lo recomendado. ¿Seguir?"),
      B.Place, L.MOD_BARS_PLACE_SHORT or "Colocar")
  end)
  place:SetPoint("LEFT", 6, 0)
  local cb = M.Check(bar, L.MOD_BARS_ONLY_EMPTY or "Solo casillas vacías",
    function() return M.Opt("mod_bars_empty") ~= false end,
    function(v) M.SetOpt("mod_bars_empty", v) end)
  cb:SetPoint("LEFT", place, "RIGHT", 8, 0)
  ui.grid = CreateFrame("Frame", nil, body)
  ui.grid:SetPoint("TOPLEFT", 0, 0)
  ui.grid:SetPoint("TOPRIGHT", 0, 0)
  ui.grid:SetHeight(10)
  ui.tips = body:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  ui.tips:SetJustifyH("LEFT")
  ui.tips:SetSpacing(2)
  ui.tips:SetText(L.MOD_BARS_TIPS or "Gris = aún no lo tienes (el número es el nivel). M = macro de Senda. Pasa el ratón para ver qué es.\nLas barras no suben de rango solas en todos los casos: vuelve a colocar tras entrenar si ves un rango antiguo.")
end

M.RegisterTab({ key = "bars", title = L.MOD_TAB_BARS or "Barras", icon = "Interface\\Icons\\INV_Misc_Book_11",
  order = 51, build = Build, refresh = B.Refresh })
M.RegisterOption({ key = "mod_bars_empty", label = L.MOD_OPT_BARS_EMPTY or "Barras: colocar solo en casillas vacías", type = "toggle", default = true })

M.On("SPELLS_CHANGED", function() if ui.grid and ui.grid:IsVisible() then M.Debounce("bars-refresh", 0.5, B.Refresh) end end)
M.On("UPDATE_MACROS", function() if ui.grid and ui.grid:IsVisible() then M.Debounce("bars-refresh", 0.5, B.Refresh) end end)

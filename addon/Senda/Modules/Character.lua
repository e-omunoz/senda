-- Senda / Modules / Character
-- «Análisis»: revisión del personaje (talentos, hechizos sin entrenar, equipo bajo o que no te sirve, profesiones,
-- consumibles y bolsas) y exportación en texto para pedir consejo fuera del juego (Ctrl+C).
local ADDON, Senda = ...
local M = Senda.Mod
if not M then return end
local L = M.L

local C = {}
Senda.Modules.Character = C

local STAT_NAMES = { L.MOD_STAT_STR or "Fuerza", L.MOD_STAT_AGI or "Agilidad", L.MOD_STAT_STA or "Aguante",
  L.MOD_STAT_INT or "Intelecto", L.MOD_STAT_SPI or "Espíritu" }
local SCHOOLS = { [2] = "Sagrado", [3] = "Fuego", [4] = "Naturaleza", [5] = "Escarcha", [6] = "Sombras", [7] = "Arcano" }

local function TalentSummary()
  if not (GetNumTalentTabs and GetTalentTabInfo and GetNumTalents and GetTalentInfo) then
    return L.MOD_CHAR_NO_TALENTS or "(no se pueden leer los talentos en este cliente)"
  end
  local parts = {}
  local okT, tabs = pcall(GetNumTalentTabs)
  for t = 1, (okT and tabs or 0) do
    local _, a, b = pcall(GetTalentTabInfo, t)
    local name = (type(a) == "string" and a) or (type(b) == "string" and b) or ("Árbol " .. t)
    local total, detail = 0, {}
    local okN, n = pcall(GetNumTalents, t)
    for i = 1, (okN and n or 0) do
      local ok, tname, _, _, _, rank, maxRank = pcall(GetTalentInfo, t, i)
      if ok and tname and rank and rank > 0 then
        total = total + rank
        table.insert(detail, tname .. " " .. rank .. "/" .. (maxRank or "?"))
      end
    end
    table.insert(parts, string.format("%s (%d): %s", name, total, table.concat(detail, ", ")))
  end
  return table.concat(parts, "\n")
end

------------------------------------------------------------------------
-- Análisis: lista de { text, hl }
------------------------------------------------------------------------
function C.Analyze()
  local tips = {}
  local function add(t, hl) table.insert(tips, { text = t, hl = hl }) end
  local level = M.Level()
  local K = Senda.Modules.Knowledge
  local G = Senda.Modules.Gear
  local P = Senda.Modules.Professions

  local unspent = M.UnspentTalents()
  if unspent > 0 then
    local cur = K and K.CurrentPick and K.CurrentPick(level)
    add(string.format(L.MOD_UNSPENT or "Tienes %d punto(s) de talento sin gastar.", unspent) ..
      (cur and (" " .. (L.MOD_NOW_PICK or "Ahora toca:") .. " " .. K.PickLabel(cur)) or ""), "warn")
  end

  if K and K.TrainNow then
    for _, e in ipairs(K.TrainNow(level)) do
      if e.level <= level - 2 then
        add(string.format(L.MOD_CHAR_MISSING_SPELL or "Te falta %s (nivel %d): pasa por el instructor.", M.SpellName(e.spell) or ("#" .. e.spell), e.level), "warn")
      end
    end
  end

  -- arma a distancia / varita para clases que la puntúan
  local W = G and G.Weights and G.Weights() or {}
  if level >= 5 and ((W.WAND_DPS or 0) > 0 or (W.RANGED_DPS or 0) >= 1) and not GetInventoryItemLink("player", 18) then
    add(L.MOD_CHAR_NO_RANGED or "No llevas arma a distancia (varita, arco...): para tu clase es importante.", "warn")
  end

  -- equipo
  local low, wrong = {}, {}
  local slots = G and G.SLOT_ORDER or {}
  for _, slot in ipairs(slots) do
    local link = GetInventoryItemLink("player", slot)
    local sname = G.SLOTS[slot] or tostring(slot)
    if link then
      local _, _, _, ilvl = M.ItemInfo(link)
      if ilvl and level >= 15 and ilvl < level - 15 then table.insert(low, sname) end
      local stats = M.ItemStats(link)
      local hasPrimary = false
      for k in pairs(stats) do
        local key = tostring(k)
        if key:find("STRENGTH") or key:find("AGILITY") or key:find("INTELLECT") or key:find("SPIRIT") then hasPrimary = true end
      end
      if hasPrimary and G.Score(link) <= 0.5 then table.insert(wrong, sname) end
    elseif level >= 10 and slot ~= 13 and slot ~= 14 and slot ~= 17 and slot ~= 18 then
      table.insert(low, sname .. " (" .. (L.MOD_EMPTY or "vacío") .. ")")
    end
  end
  if #low > 0 then add((L.MOD_CHAR_LOW_GEAR or "Equipo bajo o vacío:") .. " " .. table.concat(low, ", ")) end
  if #wrong > 0 then add((L.MOD_CHAR_WRONG_STATS or "Piezas con estadísticas que no te sirven:") .. " " .. table.concat(wrong, ", ")) end

  -- profesiones
  if P and P.States then
    local ok, states = pcall(P.States, level)
    local inPlan = {}
    for _, st in ipairs(ok and states or {}) do
      inPlan[st.key] = true
      if st.missing and level >= 5 then add(string.format(L.MOD_PROF_MISSING or "No tienes %s.", st.label), "warn")
      elseif st.train then add(P.Advice(st), "warn")
      elseif st.behind then add(string.format(L.MOD_ADV_BEHIND or "%s va atrasada (%d, ideal ~%d para tu nivel): dedica un rato a subirla.", st.label, st.rank, st.target)) end
    end
    if next(inPlan) then
      for _, p in ipairs(M.Professions()) do
        if M.GATHERING[p.key] and not inPlan[p.key] then
          add(string.format(L.MOD_CHAR_NOT_IN_PLAN or "Tienes %s, que no está en el plan de profesiones de la guía.", p.name))
        end
      end
    end
  end

  -- avisos del asesor (consumibles, mascota, bolsas)
  local A = Senda.Modules.Advisor
  if A and A.Warnings then
    for _, w in ipairs(A.Warnings()) do
      if w.key ~= "talents" then add(w.long) end
    end
  end
  return tips
end

------------------------------------------------------------------------
-- Exportación
------------------------------------------------------------------------
function C.ExportText()
  local lines = {}
  local function Ln(s) table.insert(lines, s) end
  local level = M.Level()
  local raceName = UnitRace("player")
  local className = UnitClass("player")
  Ln("SENDA " .. tostring(Senda.VERSION or "") .. " - " .. (L.MOD_CHAR_EXPORT_TITLE or "EXPORTACIÓN DEL PERSONAJE"))
  Ln(string.format("%s %s | %s %d", raceName or "?", className or "?", L.MOD_LEVEL or "Nivel", level))
  Ln(string.format("XP: %d/%d | Oro: %.2f | Zona: %s", UnitXP("player") or 0, UnitXPMax("player") or 0,
    (GetMoney and GetMoney() or 0) / 10000, (GetZoneText and GetZoneText()) or "?"))
  local stats = {}
  for i = 1, 5 do
    local ok, _, v = pcall(UnitStat, "player", i)
    table.insert(stats, STAT_NAMES[i] .. " " .. ((ok and v) or 0))
  end
  Ln((L.MOD_CHAR_STATS or "Estadísticas") .. ": " .. table.concat(stats, ", "))
  if GetSpellBonusDamage then
    local sp = {}
    for school = 2, 7 do
      local ok, v = pcall(GetSpellBonusDamage, school)
      if ok and v and v > 0 then table.insert(sp, SCHOOLS[school] .. " " .. v) end
    end
    if #sp > 0 then Ln((L.MOD_CHAR_SP or "Poder con hechizos") .. ": " .. table.concat(sp, ", ")) end
  end
  Ln(string.format("Vida %d, %s %d", UnitHealthMax("player") or 0, L.MOD_CHAR_POWER or "recurso", UnitPowerMax("player") or 0))
  Ln("")
  Ln(string.format("TALENTOS (sin gastar: %d)", M.UnspentTalents()))
  Ln(TalentSummary())
  Ln("")
  Ln("PROFESIONES")
  for _, p in ipairs(M.Professions()) do Ln(string.format("%s %d/%d", p.name, p.rank, p.max)) end
  Ln("")
  Ln("EQUIPO")
  local G = Senda.Modules.Gear
  for _, slot in ipairs(G and G.SLOT_ORDER or {}) do
    local link = GetInventoryItemLink("player", slot)
    local sname = G.SLOTS[slot] or tostring(slot)
    if link then
      local name, _, _, ilvl = M.ItemInfo(link)
      local extra, seen = {}, {}
      for k, v in pairs(M.ItemStats(link)) do
        local short = (type(_G[k]) == "string" and _G[k]) or tostring(k):gsub("ITEM_MOD_", ""):gsub("_SHORT", "")
        if type(v) == "number" and v % 1 ~= 0 then v = string.format("%.1f", v) end
        local label = short:lower()
        if (type(_G[k]) == "string" or tostring(k):find("^ITEM_MOD_")) and not seen[label] then
          seen[label] = true
          table.insert(extra, short .. " " .. tostring(v))
        end
      end
      Ln(string.format("%s: %s (nivel %s) %s", sname, name or "?", tostring(ilvl or "?"), table.concat(extra, ", ")))
    else
      Ln(sname .. ": " .. (L.MOD_EMPTY or "vacío"))
    end
  end
  Ln("")
  local K = Senda.Modules.Knowledge
  if K and K.TrainList then
    local known = {}
    for _, e in ipairs(K.TrainList()) do
      if e.level <= level then
        table.insert(known, (M.SpellName(e.spell) or ("#" .. e.spell)) .. (M.Known(e.spell) and " sí" or " no"))
      end
    end
    if #known > 0 then
      Ln("HECHIZOS DE LA GUÍA HASTA TU NIVEL")
      Ln(table.concat(known, ", "))
      Ln("")
    end
  end
  Ln(string.format("Huecos libres en bolsas: %d", M.FreeSlots()))
  if Senda.Engine and Senda.Engine.CurrentStep then
    local ok, step = pcall(Senda.Engine.CurrentStep, Senda.Engine)
    if ok and type(step) == "table" then
      Ln(string.format("Paso actual de la guía: %s - %s", tostring(step.id or "?"), M.StripColors(step.text or "")))
    end
  end
  Ln("")
  Ln("AVISOS DE SENDA")
  local tips = C.Analyze()
  if #tips == 0 then Ln(L.MOD_ADV_ALL_OK or "Todo en orden para tu nivel.") end
  for _, t in ipairs(tips) do Ln("- " .. M.StripColors(t.text)) end
  return table.concat(lines, "\n")
end

------------------------------------------------------------------------
-- Pestaña
------------------------------------------------------------------------
local ui = {}

function C.Refresh()
  if not ui.doc then return end
  local nodes = { { t = "h1", text = L.MOD_CHAR_TITLE or "Análisis de tu personaje" } }
  local ok, tips = pcall(C.Analyze)
  if not ok then
    table.insert(nodes, { t = "p", text = (L.MOD_CHAR_ERROR or "No se pudo analizar:") .. " " .. tostring(tips) })
  elseif #tips == 0 then
    table.insert(nodes, { t = "row", hl = "good", icon = "Interface\\RaidFrame\\ReadyCheck-Ready", text = L.MOD_ADV_ALL_OK or "Todo en orden para tu nivel." })
  else
    for _, t in ipairs(tips) do table.insert(nodes, { t = "row", raw = true, hl = t.hl, text = t.text }) end
  end
  table.insert(nodes, { t = "sp" })
  table.insert(nodes, { t = "p", text = L.MOD_CHAR_EXPORT_HELP or "¿Quieres un análisis más a fondo? Pulsa «Exportar», copia el texto (Ctrl+A, Ctrl+C) y pégalo donde pidas consejo. El addon no puede conectarse a internet: WoW no lo permite." })
  ui.doc:Set(nodes, true)
end

local function Build(parent)
  local bar, body = M.Toolbar(parent)
  local a = M.Button(bar, L.MOD_CHAR_ANALYZE or "Analizar", 100, function() C.Refresh() end)
  a:SetPoint("LEFT", 6, 0)
  local e = M.Button(bar, L.MOD_CHAR_EXPORT or "Exportar", 120, function()
    local ok, text = pcall(C.ExportText)
    M.ShowExport(L.MOD_CHAR_EXPORT_HINT or "Pulsa Ctrl+A y luego Ctrl+C para copiar.", ok and text or tostring(text))
  end)
  e:SetPoint("LEFT", a, "RIGHT", 4, 0)
  ui.doc = M.Doc(body)
end

M.RegisterTab({ key = "character", title = L.MOD_TAB_CHAR or "Análisis", icon = "Interface\\Icons\\INV_Misc_Spyglass_02",
  order = 60, build = Build, refresh = C.Refresh })

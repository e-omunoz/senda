-- Senda / Modules / Duo
-- Subir en pareja: detecta a tu compañero en el grupo, abre el tramo del conocimiento que os toca (páginas
-- kind = "page" con id que empieza por "duo-"; con levels se elige por el nivel más bajo de los dos, sin levels
-- se muestran siempre) y compara vuestros diarios de misiones (compartidas / solo tú).
local ADDON, Senda = ...
local M = Senda.Mod
if not M then return end
local L = M.L

local D = {}
Senda.Modules.Duo = D

function D.Partner()
  local units = {}
  for i = 1, 4 do
    local u = "party" .. i
    if UnitExists(u) and UnitIsPlayer(u) then table.insert(units, u) end
  end
  if #units == 0 then return nil end
  -- Si alguien del grupo usa Senda (Modules/Party.lua), ese es el compañero. Su nombre solo vive en memoria.
  local P = Senda.Party
  local synced = P and P.Members and P.Members()[1]
  local want = synced and synced.name
  local me = M.Level()
  local best, bestDiff
  for _, u in ipairs(units) do
    local name = UnitName(u)
    if want and name == want then best = u; break end
    local diff = math.abs((UnitLevel(u) or me) - me)
    if not best or diff < bestDiff then best, bestDiff = u, diff end
  end
  local _, cls = UnitClass(best)
  return { unit = best, name = UnitName(best), level = UnitLevel(best), class = cls, classLocal = UnitClass(best) }
end

function D.Pages()
  local brackets, general = {}, {}
  for _, p in ipairs(M.Pages("page")) do
    if type(p.id) == "string" and p.id:sub(1, 4) == "duo-" then
      if type(p.levels) == "table" then table.insert(brackets, p) else table.insert(general, p) end
    end
  end
  table.sort(brackets, function(a, b) return a.levels[1] < b.levels[1] end)
  return brackets, general
end

local function IndexFor(level, list)
  local best = 1
  for i, p in ipairs(list) do
    if M.InRange(level, p.levels) then return i end
    if p.levels[1] <= level then best = i end
  end
  return best
end

-- Misiones de tu diario: compartidas con el compañero y solo tuyas.
function D.QuestCompare(unit)
  local shared, mine = {}, {}
  if not (unit and C_QuestLog and C_QuestLog.GetNumQuestLogEntries and C_QuestLog.GetInfo and C_QuestLog.IsUnitOnQuest) then
    return shared, mine, false
  end
  local okN, n = pcall(C_QuestLog.GetNumQuestLogEntries)
  for i = 1, (okN and n or 0) do
    local ok, info = pcall(C_QuestLog.GetInfo, i)
    if ok and type(info) == "table" and not info.isHeader and info.questID and not info.isHidden then
      local okU, on = pcall(C_QuestLog.IsUnitOnQuest, unit, info.questID)
      if okU and on then table.insert(shared, info.title or ("#" .. info.questID))
      else table.insert(mine, info.title or ("#" .. info.questID)) end
    end
  end
  return shared, mine, true
end

------------------------------------------------------------------------
-- Pestaña
------------------------------------------------------------------------
local ui = { auto = true }

local function PageNodes(p, nodes)
  table.insert(nodes, { t = "h1", text = (p.title or p.id) .. M.StatusTag(p.status), raw = true })
  if p.summary then table.insert(nodes, { t = "md", text = p.summary }) end
  for _, b in ipairs(p.block or {}) do
    if type(b) == "table" then
      if b.heading then table.insert(nodes, { t = "h2", text = b.heading .. M.StatusTag(b.status), raw = true }) end
      table.insert(nodes, { t = "md", text = b.body })
    end
  end
end

function D.Refresh()
  if not ui.doc then return end
  local brackets, general = D.Pages()
  local partner = D.Partner()
  local me = M.Level()
  local low = partner and math.min(me, partner.level or me) or me
  local nodes = {}
  if partner then
    local txt = string.format("|cff7cc66f" .. (L.MOD_DUO_PARTNER or "Tu compañero: %s (%s, nivel %d). Tú: nivel %d.") .. "|r",
      partner.name or "?", partner.classLocal or "?", partner.level or 0, me)
    local diff = math.abs((partner.level or me) - me)
    if diff >= 3 then
      txt = txt .. "\n|cffff8040" .. string.format(L.MOD_DUO_GAP or "Os lleváis %d niveles: que el de menos nivel haga primero sus misiones de clase, o que el otro le acompañe.", diff) .. "|r"
    end
    table.insert(nodes, { t = "p", text = txt, raw = true })
  else
    table.insert(nodes, { t = "p", raw = true, text = "|cffaaaaaa" .. (L.MOD_DUO_INVITE or "Invita a tu compañero al grupo y esta pestaña se abrirá en vuestro tramo (el del nivel más bajo).") .. "|r" })
  end

  if #brackets > 0 then
    if ui.auto or not ui.index then ui.index = IndexFor(low, brackets) end
    ui.index = math.max(1, math.min(#brackets, ui.index))
    local p = brackets[ui.index]
    ui.header:SetText(string.format("%s  |cff888888%d-%d|r", p.title or p.id, p.levels[1], p.levels[2]))
    ui.prev:SetEnabled(ui.index > 1)
    ui.next:SetEnabled(ui.index < #brackets)
    PageNodes(p, nodes)
  else
    ui.header:SetText("")
    ui.prev:SetEnabled(false); ui.next:SetEnabled(false)
    if #general == 0 then table.insert(nodes, { t = "p", text = L.MOD_DUO_NONE or "Todavía no hay guía en pareja para tu clase." }) end
  end

  local P = Senda.Party
  local synced = (P and P.Members) and P.Members() or {}
  if #synced > 0 then
    table.insert(nodes, { t = "h1", text = L.DUO_TAB_SYNC or "Sincronización" })
    local hold = P.HoldLine and P.HoldLine()
    if hold then table.insert(nodes, { t = "p", raw = true, text = "|cffffd140" .. hold .. "|r" }) end
    for _, m in ipairs(synced) do
      local rel = P.Relation(m)
      if rel then table.insert(nodes, { t = "li", text = rel, raw = true }) end
      local who = P.Who(m)
      if who.level then table.insert(nodes, { t = "li", raw = true, text = string.format(L.DUO_TAB_LEVEL or "%s: nivel %d", m.name, who.level) }) end
      table.insert(nodes, { t = "li", raw = true, text = string.format(L.DUO_TAB_QUESTS or "%s lleva %d misiones en el registro.", m.name, m.n or 0) })
      local done = P.TheirDoneNear(m)
      if #done > 0 then
        local names = {}
        for i, q in ipairs(done) do
          if i > 8 then names[#names + 1] = "…"; break end
          names[#names + 1] = "«" .. (Senda.Compat.QuestTitle(q) or ("#" .. q)) .. "»"
        end
        table.insert(nodes, { t = "li", raw = true, text = string.format(L.DUO_TAB_DONE or "%s ya entregó, cerca de tu paso: %s", m.name, table.concat(names, ", ")) })
      end
    end
  end

  if partner then
    local shared, mine, ok = D.QuestCompare(partner.unit)
    if ok and (#shared > 0 or #mine > 0) then
      table.insert(nodes, { t = "h1", text = L.MOD_DUO_QUESTS or "Vuestras misiones" })
      if #shared > 0 then
        table.insert(nodes, { t = "h2", text = string.format(L.MOD_DUO_SHARED or "Compartidas (%d)", #shared) })
        for i, q in ipairs(shared) do if i > 15 then break end table.insert(nodes, { t = "li", text = q, raw = true }) end
      end
      if #mine > 0 then
        table.insert(nodes, { t = "h2", text = string.format(L.MOD_DUO_ONLY_ME or "Solo las tienes tú (%d): compártelas si puede cogerlas", #mine) })
        for i, q in ipairs(mine) do if i > 15 then break end table.insert(nodes, { t = "li", text = q, raw = true }) end
      end
    end
  end

  for _, p in ipairs(general) do PageNodes(p, nodes) end
  if ui.sync then ui.sync:SetEnabled(#synced > 0) end
  ui.doc:Set(nodes, true)
end

local function Build(parent)
  local bar, body = M.Toolbar(parent)
  ui.prev = M.Button(bar, "<", 30, function() ui.auto = false; ui.index = (ui.index or 1) - 1; D.Refresh() end)
  ui.prev:SetPoint("LEFT", 6, 0)
  ui.next = M.Button(bar, ">", 30, function() ui.auto = false; ui.index = (ui.index or 1) + 1; D.Refresh() end)
  ui.next:SetPoint("LEFT", ui.prev, "RIGHT", 4, 0)
  local now = M.Button(bar, L.MOD_DUO_OUR_LEVEL or "Nuestro nivel", 110, function() ui.auto = true; D.Refresh() end)
  now:SetPoint("LEFT", ui.next, "RIGHT", 4, 0)
  ui.sync = M.Button(bar, L.DUO_SYNC_BUTTON or "Pedir que salte a mi paso", 170, function()
    if Senda.Party then Senda.Party.RequestSync() end
  end)
  ui.sync:SetPoint("RIGHT", -6, 0)
  ui.header = bar:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  ui.header:SetPoint("LEFT", now, "RIGHT", 10, 0)
  ui.header:SetPoint("RIGHT", ui.sync, "LEFT", -6, 0)
  ui.header:SetJustifyH("LEFT")
  ui.doc = M.Doc(body)
end

M.RegisterTab({ key = "duo", title = L.MOD_TAB_DUO or "En pareja", icon = "Interface\\Icons\\Spell_Holy_PrayerOfHealing",
  order = 30, build = Build, refresh = D.Refresh })

-- Aviso al formar pareja (una vez por compañero y sesión).
local greeted = {}
local function Roster()
  local p = D.Partner()
  if p and p.name and not greeted[p.name] then
    greeted[p.name] = true
    local brackets, general = D.Pages()
    if #brackets + #general > 0 then
      M.Print(string.format(L.MOD_DUO_HELLO or "Subiendo en pareja con %s (nivel %d). Consejos en la pestaña «En pareja».", p.name, p.level or 0))
    end
  end
  if ui.doc and ui.doc.scroll:IsVisible() then M.Debounce("duo-refresh", 0.5, D.Refresh) end
end
M.On("GROUP_ROSTER_UPDATE", Roster)
M.On("UNIT_LEVEL", function(_, unit) if unit and unit:find("^party") then Roster() end end)
M.On("QUEST_LOG_UPDATE", function() if ui.doc and ui.doc.scroll:IsVisible() then M.Debounce("duo-refresh", 1, D.Refresh) end end)
M.On("PLAYER_LEVEL_UP", function() ui.auto = true end)
M.On("SENDA_PARTY_UPDATED", function() if ui.doc and ui.doc.scroll:IsVisible() then M.Debounce("duo-refresh", 0.5, D.Refresh) end end)

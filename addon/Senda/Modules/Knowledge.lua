-- Senda / Modules / Knowledge
-- Muestra las páginas de conocimiento (Senda.Knowledge) en pestañas:
--   Por niveles (kind = "page" con levels; se abre en el tramo de tu nivel), Talentos, Hechizos
--   (sabidos / por entrenar, con iconos), Rotación y Notas (páginas generales).
-- Expone Senda.Modules.Knowledge para el asesor, el instructor y el análisis.
local ADDON, Senda = ...
local M = Senda.Mod
if not M then return end
local L = M.L

local K = {}
Senda.Modules.Knowledge = K

local READY = "|TInterface\\RaidFrame\\ReadyCheck-Ready:14:14|t"
local WAIT = "|TInterface\\RaidFrame\\ReadyCheck-Waiting:14:14|t"
local NOT = "|TInterface\\RaidFrame\\ReadyCheck-NotReady:14:14|t"

------------------------------------------------------------------------
-- Consultas
------------------------------------------------------------------------
local function IsDuo(p) return type(p.id) == "string" and p.id:sub(1, 4) == "duo-" end

-- Páginas por tramo de nivel (sin las de pareja), ordenadas por nivel inicial.
function K.Brackets()
  local out = {}
  for _, p in ipairs(M.Pages("page")) do
    if type(p.levels) == "table" and not IsDuo(p) then table.insert(out, p) end
  end
  table.sort(out, function(a, b)
    if a.levels[1] ~= b.levels[1] then return a.levels[1] < b.levels[1] end
    return (a.order or 1000) < (b.order or 1000)
  end)
  return out
end

function K.BracketIndexFor(level, list)
  list = list or K.Brackets()
  local best
  for i, p in ipairs(list) do
    if M.InRange(level, p.levels) then return i end
    if p.levels[1] <= level then best = i end
  end
  return best or 1
end

-- Páginas generales (sin niveles y que no son de pareja).
function K.Generic()
  local out = {}
  for _, p in ipairs(M.Pages("page")) do
    if type(p.levels) ~= "table" and not IsDuo(p) then table.insert(out, p) end
  end
  return out
end

-- Talentos: lista plana { level, talent, tree, rank, note, status, page } ordenada por nivel.
function K.Picks()
  local out = {}
  for _, p in ipairs(M.Pages("talents")) do
    for _, pk in ipairs(p.pick or {}) do
      if type(pk) == "table" and pk.level then
        table.insert(out, { level = pk.level, talent = pk.talent, tree = pk.tree, rank = pk.rank,
          note = pk.note, status = pk.status or p.status, page = p })
      end
    end
  end
  table.sort(out, function(a, b) return a.level < b.level end)
  return out
end

local function TreeName(tree)
  if type(tree) == "string" then return tree end
  if type(tree) == "number" and GetTalentTabInfo then
    local ok, a, b = pcall(GetTalentTabInfo, tree)
    if ok then return (type(a) == "string" and a) or (type(b) == "string" and b) or nil end
  end
  return nil
end

function K.TalentName(pk)
  local t = pk.talent
  if type(t) == "number" then
    return M.SpellName(t) or ("#" .. t), M.SpellIcon(t)
  end
  return tostring(t or "?"), nil
end

function K.PickLabel(pk)
  local name = K.TalentName(pk)
  local tree = TreeName(pk.tree)
  local s = name
  if pk.rank then s = s .. " " .. pk.rank end
  if tree then s = s .. " |cff888888(" .. tree .. ")|r" end
  return s
end

-- Talento que toca a este nivel (el último con level <= nivel) y el siguiente.
function K.CurrentPick(level)
  level = level or M.Level()
  local cur, nxt
  for _, pk in ipairs(K.Picks()) do
    if pk.level <= level then cur = pk elseif not nxt then nxt = pk end
  end
  return cur, nxt
end

-- Hechizos: lista plana { level, spell, cost, note, status } ordenada por nivel.
function K.TrainList()
  local out = {}
  for _, p in ipairs(M.Pages("spells")) do
    for _, tr in ipairs(p.train or {}) do
      if type(tr) == "table" and tr.level and type(tr.spells) == "table" then
        for _, id in ipairs(tr.spells) do
          table.insert(out, { level = tr.level, spell = id, cost = tr.cost, note = tr.note, status = tr.status or p.status,
            pet = tr.pet, quest = tr.quest, optional = tr.optional })
        end
      end
    end
  end
  table.sort(out, function(a, b) return a.level < b.level end)
  return out
end

-- Hechizos de tu nivel o inferiores que aún no conoces.
function K.TrainNow(level)
  level = level or M.Level()
  local out, seen = {}, {}
  for _, e in ipairs(K.TrainList()) do
    -- Solo lo que enseña el instructor y la guía recomienda: fuera habilidades de la mascota (pet),
    -- hechizos de misión (quest) y los que no usa tu build (optional).
    if e.level <= level and not e.pet and not e.quest and not e.optional and not seen[e.spell] and not M.Known(e.spell) then
      seen[e.spell] = true
      table.insert(out, e)
    end
  end
  return out
end

-- Ids recomendados (para marcar en el instructor).
function K.TrainSet(level)
  local set = {}
  for _, e in ipairs(K.TrainNow(level)) do set[e.spell] = e end
  return set
end

-- Fase de rotación de un nivel (y su página).
function K.PhaseFor(level)
  level = level or M.Level()
  local best, bestPage
  for _, p in ipairs(M.Pages("rotation")) do
    for _, ph in ipairs(p.phase or {}) do
      if type(ph) == "table" and ph.from and ph.to and level >= ph.from and level <= ph.to then
        if not best or ph.from > best.from then best, bestPage = ph, p end
      end
    end
  end
  return best, bestPage
end

------------------------------------------------------------------------
-- Pestaña «Por niveles»
------------------------------------------------------------------------
local lv = { auto = true }

local function PageNodes(p, level, nodes)
  table.insert(nodes, { t = "h1", text = (p.title or p.id) .. M.StatusTag(p.status), raw = true })
  if p.summary then table.insert(nodes, { t = "md", text = p.summary }) end
  for _, b in ipairs(p.block or {}) do
    if type(b) == "table" then
      local head = b.heading
      local inRange = type(b.levels) == "table" and M.InRange(level, b.levels)
      if type(b.levels) == "table" then
        local tag = string.format(" |cff888888(%s %d-%d)|r", L.MOD_LEVELS or "niveles", b.levels[1], b.levels[2])
        head = (head or "") .. tag
        if inRange then head = "|cffffd100> |r" .. head end
      end
      if head then table.insert(nodes, { t = "h2", text = head .. M.StatusTag(b.status) }) end
      table.insert(nodes, { t = "md", text = b.body })
    end
  end
  local url = M.WebURL(p.link)
  if url then
    table.insert(nodes, { t = "sp" })
    table.insert(nodes, { t = "btn", label = L.MOD_READ_MORE or "Leer más en la web", width = 200,
      onClick = function() M.CopyPopup(url) end })
  end
end

local function RefreshLevels()
  if not lv.doc then return end
  local list = K.Brackets()
  if #list == 0 then
    lv.header:SetText("")
    lv.prev:SetEnabled(false); lv.next:SetEnabled(false)
    lv.doc:Text(L.MOD_NO_BRACKETS or "Todavía no hay guía por niveles para tu clase.")
    return
  end
  local level = M.Level()
  if lv.auto or not lv.index then lv.index = K.BracketIndexFor(level, list) end
  lv.index = math.max(1, math.min(#list, lv.index))
  local p = list[lv.index]
  lv.header:SetText(string.format("%s  |cff888888%d-%d|r", p.title or p.id, p.levels[1], p.levels[2]))
  lv.prev:SetEnabled(lv.index > 1)
  lv.next:SetEnabled(lv.index < #list)
  local nodes = {}
  if not M.InRange(level, p.levels) then
    table.insert(nodes, { t = "p", text = string.format("|cffaaaaaa" .. (L.MOD_NOT_YOUR_BRACKET or "Este tramo no es el de tu nivel (%d).") .. "|r", level), raw = true })
  end
  PageNodes(p, level, nodes)
  lv.doc:Set(nodes)
end

local function BuildLevels(parent)
  local bar, body = M.Toolbar(parent)
  lv.prev = M.Button(bar, "<", 30, function() lv.auto = false; lv.index = (lv.index or 1) - 1; RefreshLevels() end)
  lv.prev:SetPoint("LEFT", 6, 0)
  lv.next = M.Button(bar, ">", 30, function() lv.auto = false; lv.index = (lv.index or 1) + 1; RefreshLevels() end)
  lv.next:SetPoint("LEFT", lv.prev, "RIGHT", 4, 0)
  local now = M.Button(bar, L.MOD_MY_LEVEL or "Mi nivel", 80, function() lv.auto = true; RefreshLevels() end)
  now:SetPoint("LEFT", lv.next, "RIGHT", 4, 0)
  lv.header = bar:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  lv.header:SetPoint("LEFT", now, "RIGHT", 10, 0)
  lv.header:SetPoint("RIGHT", -6, 0)
  lv.header:SetJustifyH("LEFT")
  lv.doc = M.Doc(body)
  lv.parent = parent
end

------------------------------------------------------------------------
-- Pestaña «Talentos»
------------------------------------------------------------------------
local tal = {}

local function RefreshTalents()
  if not tal.doc then return end
  local level = M.Level()
  local nodes = {}
  local unspent = M.UnspentTalents()
  local cur, nxt = K.CurrentPick(level)
  if unspent > 0 then
    table.insert(nodes, { t = "row", hl = "warn", icon = "Interface\\Icons\\Ability_Marksmanship",
      text = string.format(L.MOD_UNSPENT or "Tienes %d punto(s) de talento sin gastar.", unspent) ..
        (cur and ("\n" .. (L.MOD_NOW_PICK or "Ahora toca:") .. " |cffffffff" .. K.PickLabel(cur) .. "|r") or ""), raw = true })
  elseif nxt then
    table.insert(nodes, { t = "p", text = string.format("|cffaaaaaa" .. (L.MOD_NEXT_PICK or "Siguiente talento al nivel %d: %s") .. "|r", nxt.level, K.PickLabel(nxt)), raw = true })
  end
  local pages = M.Pages("talents")
  if #pages == 0 then
    table.insert(nodes, { t = "p", text = L.MOD_NO_TALENTS or "Todavía no hay talentos recomendados para tu clase." })
  end
  for _, p in ipairs(pages) do
    table.insert(nodes, { t = "h1", text = (p.title or p.id) .. M.StatusTag(p.status), raw = true })
    if p.summary then table.insert(nodes, { t = "md", text = p.summary }) end
    local picks = {}
    for _, pk in ipairs(p.pick or {}) do if type(pk) == "table" and pk.level then table.insert(picks, pk) end end
    table.sort(picks, function(a, b) return a.level < b.level end)
    for _, pk in ipairs(picks) do
      local _, icon = K.TalentName(pk)
      local isCur = cur and cur.level == pk.level and cur.talent == pk.talent
      local text = string.format("|cffffd100%d|r  %s", pk.level, K.PickLabel(pk)) .. M.StatusTag(pk.status)
      if pk.note then text = text .. "\n|cffaaaaaa" .. pk.note .. "|r" end
      table.insert(nodes, { t = "row", raw = true, text = text, icon = icon or "Interface\\Icons\\INV_Misc_Book_11",
        spell = type(pk.talent) == "number" and pk.talent or nil,
        hl = isCur and "now" or (pk.level > level and "dim" or nil), desat = pk.level > level,
        right = isCur and (L.MOD_NOW or "ahora") or nil })
    end
    local url = M.WebURL(p.link)
    if url then table.insert(nodes, { t = "btn", label = L.MOD_READ_MORE or "Leer más en la web", width = 200, onClick = function() M.CopyPopup(url) end }) end
  end
  tal.doc:Set(nodes, true)
end

local function BuildTalents(parent)
  tal.doc = M.Doc(parent)
end

------------------------------------------------------------------------
-- Pestaña «Hechizos»
------------------------------------------------------------------------
local sp = {}

local function RefreshSpells()
  if not sp.doc then return end
  local level = M.Level()
  local nodes = {}
  local now = K.TrainNow(level)
  if #now > 0 then
    local names = {}
    for _, e in ipairs(now) do table.insert(names, M.SpellTag(e.spell, 14) .. (M.SpellName(e.spell) or ("#" .. e.spell))) end
    table.insert(nodes, { t = "row", hl = "warn", raw = true, icon = "Interface\\Icons\\INV_Misc_Book_09",
      text = string.format(L.MOD_TRAIN_NOW or "Para entrenar ya (%d):", #now) .. "\n" .. table.concat(names, ", ") })
  end
  local pages = M.Pages("spells")
  if #pages == 0 then
    table.insert(nodes, { t = "p", text = L.MOD_NO_SPELLS or "Todavía no hay lista de hechizos para tu clase." })
  end
  for _, p in ipairs(pages) do
    table.insert(nodes, { t = "h1", text = (p.title or p.id) .. M.StatusTag(p.status), raw = true })
    if p.summary then table.insert(nodes, { t = "md", text = p.summary }) end
    local trains = {}
    for _, tr in ipairs(p.train or {}) do if type(tr) == "table" and tr.level then table.insert(trains, tr) end end
    table.sort(trains, function(a, b) return a.level < b.level end)
    for _, tr in ipairs(trains) do
      local head = string.format("%s %d", L.MOD_LEVEL or "Nivel", tr.level)
      if tr.cost then head = head .. "  |cffaaaaaa" .. M.Money(tr.cost) .. "|r" end
      table.insert(nodes, { t = "h2", text = head .. M.StatusTag(tr.status), raw = true })
      if tr.note then table.insert(nodes, { t = "md", text = tr.note }) end
      for _, id in ipairs(tr.spells or {}) do
        local known = M.Known(id)
        local right, hl
        if known then right, hl = READY .. " |cff7cc66f" .. (L.MOD_KNOWN or "sabido") .. "|r", nil
        elseif tr.level <= level then right, hl = WAIT .. " |cffff8040" .. (L.MOD_TRAIN_IT or "entrena ya") .. "|r", "warn"
        else right, hl = NOT .. " |cff888888" .. string.format(L.MOD_AT_LEVEL or "nivel %d", tr.level) .. "|r", "dim" end
        table.insert(nodes, { t = "row", raw = true, icon = M.SpellIcon(id) or "Interface\\Icons\\INV_Misc_QuestionMark",
          text = M.SpellName(id) or ("#" .. id), spell = id, right = right, hl = hl,
          desat = (not known and tr.level > level) })
      end
    end
  end
  sp.doc:Set(nodes, true)
end

local function BuildSpells(parent)
  sp.doc = M.Doc(parent)
end

------------------------------------------------------------------------
-- Pestaña «Rotación»
------------------------------------------------------------------------
local rot = {}

local function PhaseNodes(ph, nodes, isCur)
  local head = string.format("%s %d-%d", L.MOD_LEVELS_CAP or "Niveles", ph.from, ph.to)
  if isCur then head = "|cffffd100> |r" .. head .. " |cffffd100(" .. (L.MOD_YOUR_LEVEL or "tu nivel") .. ")|r" end
  table.insert(nodes, { t = "h2", text = head .. M.StatusTag(ph.status), raw = true })
  if type(ph.spells) == "table" and #ph.spells > 0 then
    local parts = {}
    for i, id in ipairs(ph.spells) do
      local name = M.SpellName(id) or ("#" .. id)
      local col = M.Known(id) and "|cffffffff" or "|cff888888"
      table.insert(parts, string.format("%d. %s%s%s|r", i, M.SpellTag(id, 18), col, name))
    end
    table.insert(nodes, { t = "p", text = table.concat(parts, "   "), raw = true })
  end
  table.insert(nodes, { t = "md", text = ph.text })
  if ph.note then table.insert(nodes, { t = "md", text = "|cffaaaaaa" .. ph.note .. "|r" }) end
end

local function RefreshRotation()
  if not rot.doc then return end
  local level = M.Level()
  local nodes = {}
  local cur = K.PhaseFor(level)
  local pages = M.Pages("rotation")
  if #pages == 0 then
    table.insert(nodes, { t = "p", text = L.MOD_NO_ROTATION or "Todavía no hay rotación para tu clase." })
  end
  if cur then
    table.insert(nodes, { t = "h1", text = L.MOD_ROTATION_NOW or "Tu rotación ahora" })
    PhaseNodes(cur, nodes, true)
  end
  for _, p in ipairs(pages) do
    table.insert(nodes, { t = "h1", text = (p.title or p.id) .. M.StatusTag(p.status), raw = true })
    if p.summary then table.insert(nodes, { t = "md", text = p.summary }) end
    local phases = {}
    for _, ph in ipairs(p.phase or {}) do if type(ph) == "table" and ph.from then table.insert(phases, ph) end end
    table.sort(phases, function(a, b) return a.from < b.from end)
    for _, ph in ipairs(phases) do
      if ph ~= cur then PhaseNodes(ph, nodes, false) end
    end
  end
  rot.doc:Set(nodes, true)
end

local function BuildRotation(parent)
  rot.doc = M.Doc(parent)
end

------------------------------------------------------------------------
-- Pestaña «Notas» (páginas generales)
------------------------------------------------------------------------
local gen = {}

local function RefreshGeneric()
  if not gen.doc then return end
  local list = K.Generic()
  if #list == 0 then
    gen.header:SetText("")
    gen.prev:SetEnabled(false); gen.next:SetEnabled(false)
    gen.doc:Text(L.MOD_NO_PAGES or "No hay más páginas para tu clase.")
    return
  end
  gen.index = math.max(1, math.min(#list, gen.index or 1))
  local p = list[gen.index]
  gen.header:SetText(string.format("%s  |cff888888%d/%d|r", p.title or p.id, gen.index, #list))
  gen.prev:SetEnabled(gen.index > 1)
  gen.next:SetEnabled(gen.index < #list)
  local nodes = {}
  PageNodes(p, M.Level(), nodes)
  gen.doc:Set(nodes)
end

local function BuildGeneric(parent)
  local bar, body = M.Toolbar(parent)
  gen.prev = M.Button(bar, "<", 30, function() gen.index = (gen.index or 1) - 1; RefreshGeneric() end)
  gen.prev:SetPoint("LEFT", 6, 0)
  gen.next = M.Button(bar, ">", 30, function() gen.index = (gen.index or 1) + 1; RefreshGeneric() end)
  gen.next:SetPoint("LEFT", gen.prev, "RIGHT", 4, 0)
  gen.header = bar:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  gen.header:SetPoint("LEFT", gen.next, "RIGHT", 10, 0)
  gen.header:SetPoint("RIGHT", -6, 0)
  gen.header:SetJustifyH("LEFT")
  gen.doc = M.Doc(body)
end

------------------------------------------------------------------------
-- Registro
------------------------------------------------------------------------
M.RegisterTab({ key = "levels", title = L.MOD_TAB_LEVELS or "Por niveles", icon = "Interface\\Icons\\INV_Misc_Map_01",
  order = 20, build = BuildLevels, refresh = RefreshLevels })
M.RegisterTab({ key = "talents", title = L.MOD_TAB_TALENTS or "Talentos", icon = "Interface\\Icons\\Ability_Marksmanship",
  order = 21, build = BuildTalents, refresh = RefreshTalents })
M.RegisterTab({ key = "spells", title = L.MOD_TAB_SPELLS or "Hechizos", icon = "Interface\\Icons\\INV_Misc_Book_09",
  order = 22, build = BuildSpells, refresh = RefreshSpells })
M.RegisterTab({ key = "rotation", title = L.MOD_TAB_ROTATION or "Rotación", icon = "Interface\\Icons\\Spell_Nature_StarFall",
  order = 23, build = BuildRotation, refresh = RefreshRotation })
M.RegisterTab({ key = "notes", title = L.MOD_TAB_NOTES or "Notas", icon = "Interface\\Icons\\INV_Misc_Note_01",
  order = 24, build = BuildGeneric, refresh = RefreshGeneric })

M.RegisterOption({ key = "mod_levelmsg", label = L.MOD_OPT_LEVELMSG or "Mensajes al subir de nivel (talento, hechizos, tramo)",
  type = "toggle", default = true })

local function Visible(doc) return doc and doc.scroll and doc.scroll:IsVisible() end

function K.RefreshVisible()
  if Visible(lv.doc) then RefreshLevels() end
  if Visible(tal.doc) then RefreshTalents() end
  if Visible(sp.doc) then RefreshSpells() end
  if Visible(rot.doc) then RefreshRotation() end
end

M.On("SPELLS_CHANGED", function() M.Debounce("knowledge-refresh", 0.5, K.RefreshVisible) end)
M.On("CHARACTER_POINTS_CHANGED", function() M.Debounce("knowledge-refresh", 0.5, K.RefreshVisible) end)

-- Subida de nivel: avisos en el chat y la pestaña vuelve a tu tramo.
M.On("PLAYER_LEVEL_UP", function(_, level)
  level = tonumber(level) or M.Level()
  lv.auto = true
  M.After(1, K.RefreshVisible)
  if not M.Opt("mod_levelmsg") then return end
  local trains = {}
  for _, e in ipairs(K.TrainList()) do
    if e.level == level then table.insert(trains, M.SpellName(e.spell) or ("#" .. e.spell)) end
  end
  if #trains > 0 then
    M.Print("|cffffd100" .. (L.MOD_GO_TRAIN or "Ve al instructor:") .. "|r " .. table.concat(trains, ", "))
  end
  for _, pk in ipairs(K.Picks()) do
    if pk.level == level then M.Print("|cffffd100" .. (L.MOD_TALENT or "Talento:") .. "|r " .. K.PickLabel(pk)) end
  end
  for _, p in ipairs(K.Brackets()) do
    if p.levels[1] == level then
      M.Print("|cffffd100" .. (L.MOD_NEW_BRACKET or "Nuevo tramo:") .. "|r " .. (p.title or p.id) .. " (" .. (L.MOD_TAB_LEVELS or "Por niveles") .. ")")
    end
  end
end)

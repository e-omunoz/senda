-- Senda / Modules / Dungeons
-- Diario de mazmorras (pestaña «Mazmorras»): las mazmorras que encuentras al subir, con sus niveles, dónde está la
-- entrada (flecha a la puerta o a la piedra de encuentro; el planificador de viaje calcula el camino), sus misiones
-- (marcadas las que lleva tu guía, las hechas y las que tienes) y el botín que mejora a tu build.
--
--   Senda.Modules.Dungeons.Ready() / .Load([fn]) / .LoadNow()  -- descodifica Data/Dungeons.lua bajo demanda
--   Senda.Modules.Dungeons.List() -> mazmorras de tu bando por nivel recomendado
--   Senda.Modules.Dungeons.Get(key) -> ficha    .ForStep(step) -> clave del paso `dungeon` de la guía o nil
--   Senda.Modules.Dungeons.Quests(key) -> { { id, level, min, inGuide, done, inLog, chain, inside, giver }, ... }
--   Senda.Modules.Dungeons.Loot(key[, level]) -> { { e, score, d, cur, slot, why, up }, ... } para tu clase y build
--   Senda.Modules.Dungeons.Point(key[, "stone"]) / .Clear() / .Open(key)
--
-- Datos: tools/build.py (render_dungeons) desde data/dungeons/: fichas y misiones de tools/gen_dungeons.py (forever-db
-- y tablas del cliente), botín de tools/gen_dungeon_journal.py (ForeverLevelingBiS, MIT, y forever-db). Las cadenas se
-- descodifican la primera vez que se abre el diario, fuera de combate y 200 filas por fotograma. Solo `steps` (el
-- índice paso -> mazmorra que usa el HUD) se lee al cargar.
local ADDON, Senda = ...
local M = Senda.Mod
if not M then return end
local L = M.L
local Compat = Senda.Compat

local D = {}
Senda.Modules.Dungeons = D

local format = string.format
local SLICE = 200
local ARROW_SOURCE = "dungeon"

------------------------------------------------------------------------------
-- Descodificación
------------------------------------------------------------------------------
local data       -- { list = { ficha }, byKey, quests = { [key] = { fila } }, loot = { [key] = { fila } } }
local loadCo, loadFrame, loadWaiters

local function Raw() return Senda.DungeonsData end

local function Split(s, sep)
  local t, n, i = {}, 0, 1
  while true do
    local j = s:find(sep, i, true)
    n = n + 1
    if not j then t[n] = s:sub(i); break end
    t[n] = s:sub(i, j - 1)
    i = j + #sep
  end
  return t
end

local function Lines(blob, fn, tick)
  for line in (blob or ""):gmatch("[^\n]+") do
    fn(line)
    if tick then tick() end
  end
end

local function Point(s)
  if not s or s == "" then return nil end
  local p = Split(s, ",")
  local map, x, y = tonumber(p[1]), tonumber(p[2]), tonumber(p[3])
  if not (map and x and y) then return nil end
  return { map = map, x = x, y = y, extra = p[4] }
end

local function IdList(s)
  local out = {}
  if s and s ~= "" then
    for _, v in ipairs(Split(s, ";")) do out[#out + 1] = tonumber(v) end
  end
  return out
end

local function DecodeAll(tick)
  local R = Raw()
  local out = { list = {}, byKey = {}, quests = {}, loot = {} }
  if type(R) ~= "table" then return out end
  Lines(R.list, function(line)
    local f = Split(line, "|")
    local qr = Split(f[7] or "", "-")
    local dg = { key = f[1], map = tonumber(f[2]), area = tonumber(f[3]), name = f[4], entry = tonumber(f[5]),
      rec = tonumber(f[6]), qlo = tonumber(qr[1]), qhi = tonumber(qr[2]), faction = f[8], forever = f[9] == "1",
      entrance = Point(f[10]), stone = Point(f[11]), bosses = {} }
    if dg.stone then dg.stone.yards = tonumber(dg.stone.extra) end
    for _, b in ipairs(f[12] and f[12] ~= "" and Split(f[12], ";") or {}) do
      local npc, name = b:match("^(%d+)=(.*)$")
      dg.bosses[#dg.bosses + 1] = { npc = tonumber(npc) or 0, name = name or b }
    end
    out.list[#out.list + 1] = dg
    out.byKey[dg.key] = dg
    out.quests[dg.key] = {}
    out.loot[dg.key] = {}
  end, tick)
  Lines(R.quests, function(line)
    local f = Split(line, "|")
    local list = out.quests[f[1]]
    if not list then return end
    local giver
    local kind, gid, pos = (f[10] or ""):match("^(%a)(%d+)@?(.*)$")
    if kind then giver = { kind = kind, id = tonumber(gid), at = Point(pos) } end
    list[#list + 1] = { id = tonumber(f[2]), level = tonumber(f[3]) or 0, min = tonumber(f[4]) or 0, faction = f[5],
      classes = tonumber(f[6]) or 0, races = tonumber(f[7]) or 0, scope = f[8], started = f[9], giver = giver,
      all = IdList(f[11]), any = IdList(f[12]), xp = tonumber(f[13]) or 0 }
  end, tick)
  Lines(R.loot, function(line)
    local f = Split(line, "|")
    local list = out.loot[f[1]]
    if not list then return end
    local stats = {}
    for _, kv in ipairs(f[11] and f[11] ~= "" and Split(f[11], ",") or {}) do
      local k, v = kv:match("^([%u%d_]+)=(.+)$")
      if k then stats[k] = tonumber(v) end
    end
    list[#list + 1] = { id = tonumber(f[2]), inv = tonumber(f[3]), class = tonumber(f[4]), sub = tonumber(f[5]),
      req = tonumber(f[6]) or 0, q = tonumber(f[7]) or 2, npc = tonumber(f[8]) or 0, pct = tonumber(f[9]),
      cls = tonumber(f[10]) or 0, stats = stats }
  end, tick)
  table.sort(out.list, function(a, b)
    local ra, rb = a.rec or a.entry or 99, b.rec or b.entry or 99
    if ra ~= rb then return ra < rb end
    return a.key < b.key
  end)
  return out
end

function D.Ready() return data ~= nil end

-- Descodificación inmediata (pruebas, o si hace falta ya).
function D.LoadNow()
  if not data then data = DecodeAll() end
  return data
end

local function LoadStep()
  if not loadCo then
    if loadFrame then loadFrame:Hide() end
    return
  end
  if M.InCombat() then return end
  local ok, res = coroutine.resume(loadCo)
  if not ok then
    loadCo = nil
    loadFrame:Hide()
    M.Debug("Mazmorras: error al cargar: %s", tostring(res))
    return
  end
  if coroutine.status(loadCo) == "dead" then
    loadCo = nil
    loadFrame:Hide()
    data = data or res
    local waiters = loadWaiters or {}
    loadWaiters = nil
    for _, fn in ipairs(waiters) do pcall(fn) end
    M.Fire("SENDA_DUNGEONS_READY")
  end
end

-- Descodifica repartido en fotogramas, fuera de combate. `fn` se llama al terminar.
function D.Load(fn)
  if data then
    if fn then fn() end
    return
  end
  loadWaiters = loadWaiters or {}
  if fn then loadWaiters[#loadWaiters + 1] = fn end
  if loadCo then return end
  local k = 0
  loadCo = coroutine.create(function()
    return DecodeAll(function()
      k = k + 1
      if k % SLICE == 0 then coroutine.yield() end
    end)
  end)
  if not loadFrame then
    loadFrame = CreateFrame("Frame")
    loadFrame:SetScript("OnUpdate", LoadStep)
  end
  loadFrame:Show()
end

-- Ids del diario para `/senda volcar` (Core/NamesDump.lua): misiones, PNJ (jefes y dadores) y objetos de botín.
-- Dentro de una corrutina descodifica cediendo cada SLICE filas; fuera, de golpe.
function D.DumpIds()
  if not data then
    local k = 0
    data = DecodeAll(function()
      k = k + 1
      if k % SLICE == 0 and coroutine.running() then coroutine.yield() end
    end)
  end
  local out = { quests = {}, npcs = {}, items = {} }
  for _, dg in ipairs(data.list) do
    for _, b in ipairs(dg.bosses) do if b.npc > 0 then out.npcs[#out.npcs + 1] = b.npc end end
    for _, q in ipairs(data.quests[dg.key] or {}) do
      out.quests[#out.quests + 1] = q.id
      if q.giver and q.giver.kind == "n" then out.npcs[#out.npcs + 1] = q.giver.id end
    end
    for _, e in ipairs(data.loot[dg.key] or {}) do
      out.items[#out.items + 1] = e.id
      if e.npc > 0 then out.npcs[#out.npcs + 1] = e.npc end
    end
  end
  return out
end

------------------------------------------------------------------------------
-- Consultas
------------------------------------------------------------------------------

-- Clave de la mazmorra de un paso `do = "dungeon"` de la guía (índice compilado; no hace falta descodificar).
function D.ForStep(step)
  local R = Raw()
  if type(step) ~= "table" or step["do"] ~= "dungeon" or type(R) ~= "table" or type(R.steps) ~= "table" then return nil end
  return R.steps[step.id]
end

local function FactionCode()
  local f = M.Faction()
  if f == "Horde" then return "H" end
  if f == "Alliance" then return "A" end
  return nil
end

local function ForFaction(code, fac)
  if not code or not fac or fac == "" then return true end
  return fac:find(code, 1, true) ~= nil
end

function D.List()
  if not data then return {} end
  local code = FactionCode()
  local out = {}
  for _, dg in ipairs(data.list) do
    if ForFaction(code, dg.faction) then out[#out + 1] = dg end
  end
  return out
end

function D.Get(key) return data and data.byKey[key or ""] or nil end

-- Nombre en el idioma del cliente: el área de la instancia (C_Map.GetAreaInfo) o la cadena de Locale.lua.
function D.Name(dg)
  if not dg then return "?" end
  if dg.area and dg.area > 0 and C_Map and C_Map.GetAreaInfo then
    local ok, n = pcall(C_Map.GetAreaInfo, dg.area)
    if ok and type(n) == "string" and n ~= "" and not (Compat.IsSecret and Compat.IsSecret(n)) then return n end
  end
  return L["DUNGEON_" .. (dg.key:upper():gsub("%-", "_"))] or dg.name or dg.key
end

-- Rango de niveles en texto: «entrada 10 · recomendado 16 · misiones 17-22».
function D.LevelText(dg)
  local parts = {}
  if dg.entry then parts[#parts + 1] = format(L.DUNGEON_LV_ENTRY or "entrada %d", dg.entry) end
  if dg.rec then parts[#parts + 1] = format(L.DUNGEON_LV_REC or "recomendado %d", dg.rec) end
  if dg.qlo and dg.qhi then parts[#parts + 1] = format(L.DUNGEON_LV_QUESTS or "misiones %d-%d", dg.qlo, dg.qhi) end
  return table.concat(parts, " · ")
end

-- La mazmorra que toca: la del paso actual de la guía o la de nivel recomendado más cercano al tuyo (sin pasarse).
function D.Suggested()
  local E = Senda.Engine
  local step = E and E:CurrentStep()
  local k = D.ForStep(step)
  if k then return k end
  local lv = M.Level()
  local best, bestD
  for _, dg in ipairs(D.List()) do
    local rec = dg.rec or dg.entry
    if rec and (dg.entry or 1) <= lv + 2 then
      local dd = math.abs(rec - lv)
      if not bestD or dd < bestD then best, bestD = dg.key, dd end
    end
  end
  return best or (D.List()[1] and D.List()[1].key)
end

-- Misiones de la guía activa (las que se cogen, completan o entregan en algún paso).
local guideCache = { id = nil, n = -1, set = {} }
local function GuideQuests()
  local E = Senda.Engine
  if not E then return {} end
  local steps = E:Steps() or {}
  local id = E:GuideId()
  if guideCache.id == id and guideCache.n == #steps then return guideCache.set end
  local set = {}
  for _, e in ipairs(steps) do
    local s = e.step
    if s then
      if s.quest then set[s.quest] = true end
      for _, q in ipairs(type(s.quests) == "table" and s.quests or {}) do set[q] = true end
    end
  end
  guideCache = { id = id, n = #steps, set = set }
  return set
end
D.GuideQuests = GuideQuests

local RACE_BIT = { Human = 1, Orc = 2, Dwarf = 4, NightElf = 8, Scourge = 16, Tauren = 32, Gnome = 64, Troll = 128 }
local CLASS_BIT = { WARRIOR = 1, PALADIN = 2, HUNTER = 4, ROGUE = 8, PRIEST = 16, SHAMAN = 64, MAGE = 128,
  WARLOCK = 256, DRUID = 1024 }
local function HasBit(mask, bit)
  if not mask or mask == 0 or not bit then return true end
  return mask % (bit * 2) >= bit
end

-- Misiones de la mazmorra que puede coger tu personaje (bando, clase, raza), con su estado.
function D.Quests(key)
  local list = data and data.quests[key or ""]
  if not list then return {} end
  local code = FactionCode()
  local cls, race = M.Class(), M.Race()
  local inGuide = GuideQuests()
  local out = {}
  for _, q in ipairs(list) do
    if ForFaction(code, q.faction) and HasBit(q.classes, CLASS_BIT[cls or ""]) and
      (q.races == 0 or not RACE_BIT[race or ""] or HasBit(q.races, RACE_BIT[race])) then
      local done = Compat.IsQuestDone(q.id)
      local before = {}
      if not done then
        for _, r in ipairs(q.all) do if not Compat.IsQuestDone(r) then before[#before + 1] = r end end
      end
      out[#out + 1] = { q = q, id = q.id, level = q.level, min = q.min, inGuide = inGuide[q.id] == true, done = done,
        inLog = (not done) and Compat.IsOnQuest(q.id) or false, chain = q.scope == "c", inside = q.started == "i",
        giver = q.giver, before = before }
    end
  end
  table.sort(out, function(a, b)
    if a.inGuide ~= b.inGuide then return a.inGuide end
    if a.chain ~= b.chain then return not a.chain end
    if a.level ~= b.level then return a.level < b.level end
    return a.id < b.id
  end)
  return out
end

-- Botín para tu clase y build: lo que puedes llevar y cuyos puntos vienen sobre todo de lo que tu build busca
-- (no solo de Aguante o armadura). Primero lo que te mejora, por mejora; después el resto, por puntos.
D.CORE_SHARE = 0.3
function D.Loot(key, level)
  local list = data and data.loot[key or ""]
  local G = Senda.Modules.Gear
  if not list or not G or not G.CanUseData then return {} end
  level = level or M.Level()
  local out = {}
  for _, e in ipairs(list) do
    if G.CanUseData(e.inv, e.class, e.sub, e.cls) then
      local lv = math.max(level, e.req or 0)
      local score, core = G.ScoreData(e.stats, e.class, e.sub, lv)
      if score > 0 and core > 0 and core >= D.CORE_SHARE * score then
        local ok, d, slot, why, cur = pcall(G.DeltaData, e, level)
        if not ok then d, slot, why, cur = nil, nil, nil, nil end
        out[#out + 1] = { e = e, score = score, d = d, slot = slot, why = why, cur = cur,
          up = d ~= nil and d > 0.5 and why == nil }
      end
    end
  end
  table.sort(out, function(a, b)
    if a.up ~= b.up then return a.up end
    if a.up then return a.d > b.d end
    if a.score ~= b.score then return a.score > b.score end
    return a.e.id < b.e.id
  end)
  return out
end

------------------------------------------------------------------------------
-- Flecha
------------------------------------------------------------------------------

function D.Point(key, which)
  local dg = D.Get(key)
  if not (dg and Senda.Arrow) then return false end
  local p = (which == "stone") and dg.stone or dg.entrance
  if not p then return false end
  local fmt = (which == "stone") and (L.DUNGEON_ARROW_STONE or "Piedra de encuentro: %s") or (L.DUNGEON_ARROW or "Mazmorra: %s")
  Senda.Arrow:SetTarget(p.map, p.x, p.y, format(fmt, D.Name(dg)), ARROW_SOURCE, { radius = 20, dungeon = key, which = which or "entrance" })
  M.Fire("SENDA_DUNGEONS_ARROW", key)
  return true
end

function D.Clear()
  if Senda.Arrow and Senda.Arrow:Has(ARROW_SOURCE) then Senda.Arrow:Clear(ARROW_SOURCE) end
  M.Fire("SENDA_DUNGEONS_ARROW", nil)
end

-- Mazmorra a la que apunta la flecha ahora (o nil).
function D.Pointed()
  local t = Senda.Arrow and Senda.Arrow:Destination()
  if t and t.source == ARROW_SOURCE then return t.dungeon, t.which end
  return nil
end

-- Apunta la flecha al dador de una misión de la lista.
function D.PointGiver(row)
  local g = row and row.giver
  if not (g and g.at and Senda.Arrow) then return false end
  local tok = (g.kind == "o" and "{obj:" or "{npc:") .. g.id .. "}"
  local who = Senda.Names and Senda.Names:Resolve(tok) or tok
  Senda.Arrow:SetTarget(g.at.map, g.at.x, g.at.y, format(L.DUNGEON_ARROW_GIVER or "%s", who), ARROW_SOURCE,
    { radius = 10, giver = row.id })
  M.Fire("SENDA_DUNGEONS_ARROW", nil)
  return true
end

------------------------------------------------------------------------------
-- Pestaña
------------------------------------------------------------------------------
local ui = {}
local LIST_W = 168

local function Selected()
  return ui.key or M.DB().dungeonKey
end

local function MapName(map)
  return (Senda.Names and Senda.Names:Get("map", map)) or Compat.MapName(map) or ("#" .. tostring(map))
end

local function Tok(kind, id)
  if Senda.Names then return Senda.Names:Resolve("{" .. kind .. ":" .. id .. "}") end
  return "#" .. id
end

local function LevelColor(dg)
  local lv = M.Level()
  local rec = dg.rec or dg.entry or lv
  if dg.entry and lv < dg.entry then return "ff8c949e" end   -- aún no puedes entrar
  if lv > rec + 8 then return "ff8c949e" end                 -- se te queda baja
  if math.abs(lv - rec) <= 4 then return "ff59d966" end      -- es tu momento
  return "ffffd140"
end

local function RefreshList()
  if not ui.listChild then return end
  local list = D.List()
  local key = Selected()
  local guideStep = D.ForStep(Senda.Engine and Senda.Engine:CurrentStep())
  for i, dg in ipairs(list) do
    local b = ui.buttons[i]
    if not b then
      b = Senda.UI:Button(ui.listChild, "", LIST_W - 12, 22)
      local fs = b:GetFontString()
      fs:ClearAllPoints()
      fs:SetPoint("LEFT", 6, 0)
      fs:SetPoint("RIGHT", -4, 0)
      fs:SetJustifyH("LEFT")
      fs:SetWordWrap(false)
      ui.buttons[i] = b
    end
    b:ClearAllPoints()
    b:SetPoint("TOPLEFT", 2, -2 - (i - 1) * 24)
    local lv = dg.rec or dg.entry
    local mark = (guideStep == dg.key) and "|cffffd140»|r " or ""
    b:SetText(mark .. "|c" .. LevelColor(dg) .. (lv and (lv .. "  ") or "") .. "|r" .. D.Name(dg))
    b:SetScript("OnClick", function() D.Select(dg.key) end)
    b:SetActive(dg.key == key)
    b:Show()
  end
  for i = #list + 1, #ui.buttons do ui.buttons[i]:Hide() end
  ui.listChild:SetHeight(math.max(10, #list * 24 + 4))
end

local function TravelLine(dg)
  local key, which = D.Pointed()
  if key ~= dg.key then return "|cffaaaaaa" .. (L.DUNGEON_TRAVEL_HINT or "Pon la flecha en la entrada y Senda calcula el camino más rápido con tus vuelos, barcos y piedra de hogar.") .. "|r" end
  local T = Senda.Modules.Travel
  local plan = T and T.GetPlan and T.GetPlan()
  local where = which == "stone" and (L.DUNGEON_TO_STONE or "a la piedra de encuentro") or (L.DUNGEON_TO_DOOR or "a la entrada")
  if plan and not plan.none and plan.line then
    local total = (T.Duration and plan.secs) and (" (" .. format(L.DUNGEON_TRAVEL_TOTAL or "unos %s", T.Duration(plan.secs)) .. ")") or ""
    return plan.line .. total
  elseif plan and plan.none then
    return L.TRAVEL_NONE or "No conozco un camino hasta allí con los vuelos que tienes."
  elseif plan and plan.walkOnly then
    return format(L.DUNGEON_TRAVEL_WALK or "Lo más rápido es ir a pie %s: sigue la flecha.", where)
  end
  return format(L.DUNGEON_TRAVEL_NEAR or "La flecha te lleva %s.", where)
end

local function QuestRow(r)
  local name = (Senda.Names and Senda.Names:Get("quest", r.id)) or (Senda.Names and Senda.Names:Placeholder("quest", r.id)) or ("#" .. r.id)
  local icon, tag
  if r.done then
    icon, tag = "Interface\\RaidFrame\\ReadyCheck-Ready", "|cff59d966" .. (L.DUNGEON_Q_DONE or "hecha") .. "|r"
  elseif r.inLog then
    icon, tag = "Interface\\GossipFrame\\ActiveQuestIcon", "|cffffd140" .. (L.DUNGEON_Q_LOG or "la llevas") .. "|r"
  else
    icon = "Interface\\GossipFrame\\AvailableQuestIcon"
  end
  local bits = { format(L.DUNGEON_Q_LEVEL or "nivel %d", r.level) }
  if r.min > M.Level() then bits[#bits + 1] = "|cffff8040" .. format(L.DUNGEON_Q_MIN or "desde el %d", r.min) .. "|r" end
  if r.giver then
    local g = r.giver
    local who = (g.kind == "i") and format(L.DUNGEON_Q_ITEM or "empieza con %s", Tok("item", g.id))
      or Tok(g.kind == "o" and "obj" or "npc", g.id)
    if g.at then who = who .. " · " .. MapName(g.at.map) end
    bits[#bits + 1] = who
  end
  if r.inside then bits[#bits + 1] = L.DUNGEON_Q_INSIDE or "se coge dentro" end
  if r.chain then bits[#bits + 1] = L.DUNGEON_Q_CHAIN or "previa o continuación" end
  local sub = "|cffaaaaaa" .. table.concat(bits, " · ") .. "|r"
  if #r.before > 0 then
    local names = {}
    for i, q in ipairs(r.before) do
      if i > 2 then names[#names + 1] = "…"; break end
      names[#names + 1] = "«" .. ((Senda.Names and Senda.Names:Get("quest", q)) or ("#" .. q)) .. "»"
    end
    sub = sub .. "\n|cffff8040" .. format(L.DUNGEON_Q_BEFORE or "Antes: %s", table.concat(names, ", ")) .. "|r"
  end
  local right = r.inGuide and ("|cffffd140" .. (L.DUNGEON_Q_IN_GUIDE or "en tu guía") .. "|r") or ""
  if tag then right = (right ~= "" and (right .. " · ") or "") .. tag end
  return { t = "row", raw = true, icon = icon, text = name .. "\n" .. sub, right = right, hl = r.inGuide and "now" or nil,
    desat = r.done, tip = r.giver and r.giver.at and (L.DUNGEON_Q_POINT or "Clic: flecha a quien la da.") or nil,
    onClick = function() if D.PointGiver(r) then D.Refresh() end end, quest = r.id }
end

local function LootRow(it, level)
  local G = Senda.Modules.Gear
  local e = it.e
  local name = M.ItemInfo(e.id)
  if not name then M.RequestItem(e.id) end
  local slot = G and G.SLOTS and it.slot and G.SLOTS[it.slot] or "?"
  local src = (e.npc and e.npc > 0) and Tok("npc", e.npc) or (L.DUNGEON_LOOT_TRASH or "bichos de la mazmorra")
  local pct = (e.pct and e.pct > 0) and (" · " .. format("%g %%", e.pct)) or ""
  local right
  if it.up then
    right = G.GainText(it.d, it.cur)
  elseif it.why then
    right = "|cffff8040" .. it.why .. "|r"
  else
    right = "|cffaaaaaa" .. (L.MOD_GEAR_NOT_UP or "no te mejora") .. "|r"
  end
  return { t = "row", raw = true, item = e.id, icon = M.ItemIcon(e.id), hl = it.up and "good" or nil,
    text = (name or (Senda.Names and Senda.Names:Placeholder("item", e.id)) or ("#" .. e.id)) .. "\n|cffaaaaaa" .. slot .. " — " .. src .. pct .. "|r",
    right = right, lootItem = e.id }
end

function D.Refresh()
  if not ui.doc then return end
  if not data then
    ui.doc:Set({ { t = "p", text = L.DUNGEON_LOADING or "Cargando el diario de mazmorras…" } })
    D.Load(function() D.Refresh() end)
    return
  end
  RefreshList()
  local dg = D.Get(Selected())
  if not dg then
    ui.doc:Set({ { t = "p", text = L.DUNGEON_NONE or "No hay mazmorras para tu bando." } })
    return
  end
  local level = M.Level()
  local nodes = { { t = "h1", text = D.Name(dg) } }
  nodes[#nodes + 1] = { t = "p", raw = true, text = "|cffffd100" .. D.LevelText(dg) .. "|r" ..
    ((dg.entry and level < dg.entry) and ("\n|cffff8040" .. format(L.DUNGEON_TOO_LOW or "Aún no puedes entrar: te faltan %d niveles.", dg.entry - level) .. "|r") or "") }
  local stepKey = D.ForStep(Senda.Engine and Senda.Engine:CurrentStep())
  if stepKey == dg.key then
    nodes[#nodes + 1] = { t = "p", raw = true, text = "|cffffd140" .. (L.DUNGEON_GUIDE_NOW or "Tu guía te manda aquí ahora.") .. "|r" }
  end

  -- Dónde está y cómo llegar
  nodes[#nodes + 1] = { t = "h2", text = L.DUNGEON_WHERE or "Dónde está" }
  local e = dg.entrance
  if e then
    local txt = format(L.DUNGEON_ENTRANCE or "Entrada: %s (%.1f, %.1f)", MapName(e.map), e.x, e.y)
    if e.extra == "g" then txt = txt .. " |cffaaaaaa" .. (L.DUNGEON_ENTRANCE_GUIDE or "(punto de la guía, sin comprobar)") .. "|r" end
    if dg.stone then
      txt = txt .. "\n" .. format(L.DUNGEON_STONE or "Piedra de encuentro: %s (%.1f, %.1f), a unas %d yardas de la entrada", MapName(dg.stone.map), dg.stone.x, dg.stone.y, dg.stone.yards or 0)
    end
    nodes[#nodes + 1] = { t = "p", raw = true, text = txt }
    nodes[#nodes + 1] = { t = "btn", label = L.DUNGEON_POINT or "Flecha a la entrada", width = 170, onClick = function() D.Point(dg.key); D.Refresh() end }
    if dg.stone then
      nodes[#nodes + 1] = { t = "btn", label = L.DUNGEON_POINT_STONE or "Flecha a la piedra", width = 170, onClick = function() D.Point(dg.key, "stone"); D.Refresh() end }
    end
    if Senda.Arrow and Senda.Arrow:Has(ARROW_SOURCE) then
      nodes[#nodes + 1] = { t = "btn", label = L.DUNGEON_CLEAR or "Quitar la flecha", width = 170, onClick = function() D.Clear(); D.Refresh() end }
    end
    nodes[#nodes + 1] = { t = "p", raw = true, text = TravelLine(dg) }
  else
    nodes[#nodes + 1] = { t = "p", raw = true, text = "|cffaaaaaa" .. (L.DUNGEON_NO_ENTRANCE or "El cliente no da el punto de la entrada de esta mazmorra y aún no lo hemos comprobado en el juego.") .. "|r" }
  end
  if #dg.bosses > 0 then
    local names = {}
    for _, b in ipairs(dg.bosses) do
      names[#names + 1] = (b.npc > 0 and (Senda.Names and Senda.Names:Get("npc", b.npc))) or b.name
    end
    nodes[#nodes + 1] = { t = "p", raw = true, text = "|cffaaaaaa" .. (L.DUNGEON_BOSSES or "Jefes:") .. "|r " .. table.concat(names, ", ") }
  end

  -- Misiones
  local qs = D.Quests(dg.key)
  nodes[#nodes + 1] = { t = "h1", text = format(L.DUNGEON_QUESTS or "Misiones (%d)", #qs) }
  if #qs == 0 then
    nodes[#nodes + 1] = { t = "p", text = L.DUNGEON_QUESTS_NONE or "Ninguna misión de esta mazmorra para tu personaje en los datos." }
  else
    for _, r in ipairs(qs) do nodes[#nodes + 1] = QuestRow(r) end
  end

  -- Botín
  local G = Senda.Modules.Gear
  local key = G and G.BuildKey and G.BuildKey()
  local loot = D.Loot(dg.key, level)
  nodes[#nodes + 1] = { t = "h1", text = key and format(L.DUNGEON_LOOT_BUILD or "Botín para tu build: %s", G.BuildLabel(key)) or (L.DUNGEON_LOOT or "Botín para tu clase") }
  if #loot == 0 then
    nodes[#nodes + 1] = { t = "p", text = L.DUNGEON_LOOT_NONE or "Los datos de botín no traen nada de esta mazmorra para tu clase y build." }
  else
    for i, it in ipairs(loot) do
      if i > 12 and not it.up then break end
      nodes[#nodes + 1] = LootRow(it, level)
    end
  end
  nodes[#nodes + 1] = { t = "p", raw = true, text = "|cffaaaaaa" .. (L.DUNGEON_LOOT_NOTE or "Botín de ForeverLevelingBiS (MIT) y forever-db; Senda lo valora con los pesos de tu build.") .. "|r" }
  ui.doc:Set(nodes, ui.keepScroll)
  ui.keepScroll = nil
  ui.nodes = nodes
end

-- Elige una mazmorra en la pestaña.
function D.Select(key)
  ui.key = key
  M.DB().dungeonKey = key
  D.Refresh()
end

-- Abre la pestaña en una mazmorra (la línea del paso del HUD).
function D.Open(key)
  if key then ui.key = key; M.DB().dungeonKey = key end
  if Senda.UI and Senda.UI.ShowPanel then Senda.UI:ShowPanel("dungeons") end
  D.Load(function() D.Refresh() end)
end

-- Lo que la pestaña enseña ahora (pruebas): clave, nodos.
function D.Shown() return ui.key, ui.nodes end

local function Build(parent)
  local left = CreateFrame("Frame", nil, parent, BackdropTemplateMixin and "BackdropTemplate" or nil)
  if Senda.UI and Senda.UI.Backdrop then Senda.UI:Backdrop(left, "inset") end
  left:SetPoint("TOPLEFT", 0, 0)
  left:SetPoint("BOTTOMLEFT", 0, 0)
  left:SetWidth(LIST_W)
  ui.listFrame, ui.listChild = Senda.UI:ScrollArea(left)
  ui.buttons = {}
  local right = CreateFrame("Frame", nil, parent)
  right:SetPoint("TOPLEFT", left, "TOPRIGHT", 4, 0)
  right:SetPoint("BOTTOMRIGHT", 0, 0)
  ui.doc = M.Doc(right)
  if not Selected() then ui.key = nil end
end

local function OnShow()
  D.Load(function()
    if not ui.key then ui.key = M.DB().dungeonKey or D.Suggested() end
    -- si la guía manda a una mazmorra, se abre en ella
    local k = D.ForStep(Senda.Engine and Senda.Engine:CurrentStep())
    if k and ui.followStep ~= k then ui.key, ui.followStep = k, k end
    D.Refresh()
  end)
  D.Refresh()
end

M.RegisterTab({ key = "dungeons", title = L.MOD_TAB_DUNGEONS or "Mazmorras", icon = "Interface\\Icons\\INV_Misc_Key_14",
  order = 13, build = Build, refresh = OnShow })

-- Refresco en vivo mientras se ve la pestaña.
local function Live()
  if not (ui.doc and Senda.UI and Senda.UI.IsPanelShown and Senda.UI:IsPanelShown()) then return end
  M.Debounce("dungeons-live", 0.3, function()
    if Senda.UI:IsPanelShown() then ui.keepScroll = true; D.Refresh() end
  end)
end
for _, ev in ipairs({ "SENDA_NAMES_UPDATED", "SENDA_TRAVEL_UPDATED", "SENDA_STEP_CHANGED", "QUEST_TURNED_IN",
  "QUEST_ACCEPTED", "PLAYER_EQUIPMENT_CHANGED", "GET_ITEM_INFO_RECEIVED" }) do
  M.On(ev, Live)
end

-- Al entrar en una instancia la flecha a la mazmorra ya no hace falta.
M.On("PLAYER_ENTERING_WORLD", function()
  local inInstance = IsInInstance and select(1, IsInInstance())
  if inInstance then D.Clear() end
end)

-- /senda mazmorra [nombre o clave]: abre el diario (en la mazmorra que toca o en la que nombres).
local function Slash(rest)
  local q = (rest or ""):lower()
  D.Load(function()
    local key
    if q ~= "" then
      for _, dg in ipairs(D.List()) do
        if dg.key:find(q, 1, true) or D.Name(dg):lower():find(q, 1, true) or (dg.name or ""):lower():find(q, 1, true) then
          key = dg.key
          break
        end
      end
    end
    D.Open(key or D.Suggested())
  end)
end
M.OnReady(function()
  if Senda.Slash and Senda.Slash.Register then
    Senda.Slash:Register("mazmorra", Slash, L.DUNGEON_SLASH_HELP or "abre el diario de mazmorras (o /senda mazmorra minas)")
  end
end)

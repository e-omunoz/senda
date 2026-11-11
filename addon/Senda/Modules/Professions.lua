-- Senda / Modules / Professions
-- Progreso y ruta de subida de profesiones desde el conocimiento kind = "professions":
--   [[route]] prof, from, to, craft (id de objeto o de hechizo) o craft_spell, mats = [[id, n]], trainer = [map, x, y, "nombre"], note
--   [[trainer]] prof, ranks, for_class, name, at = [map, x, y, "etiqueta"] (página; se usa si la ruta no trae trainer)
-- Qué fabricar ahora, material que falta (bolsas + banco), instructor con la flecha y avisos de tope de rango.
local ADDON, Senda = ...
local M = Senda.Mod
if not M then return end
local L = M.L

local P = {}
Senda.Modules.Professions = P

-- Rangos de profesión (mecánica del juego): tope, nombre, habilidad y nivel para entrenar el siguiente.
local RANKS = {
  { max = 75,  name = L.MOD_RANK_1 or "Aprendiz", skill = 0,   level = 5 },
  { max = 150, name = L.MOD_RANK_2 or "Oficial",  skill = 50,  level = 10 },
  { max = 225, name = L.MOD_RANK_3 or "Experto",  skill = 125, level = 20 },
  { max = 300, name = L.MOD_RANK_4 or "Artesano", skill = 200, level = 35 },
}
P.RANKS = RANKS

------------------------------------------------------------------------
-- Datos
------------------------------------------------------------------------
-- { order = {key...}, [key] = { key, segs = {...} } }
function P.Routes()
  local out = { order = {} }
  for _, p in ipairs(M.Pages("professions")) do
    for _, s in ipairs(p.route or {}) do
      if type(s) == "table" and s.prof and s.from and s.to then
        local key = M.ProfKey(s.prof)
        if not out[key] then
          out[key] = { key = key, segs = {}, page = p }
          table.insert(out.order, key)
        end
        table.insert(out[key].segs, s)
      end
    end
  end
  for _, key in ipairs(out.order) do
    table.sort(out[key].segs, function(a, b) return a.from < b.from end)
  end
  -- [[trainer]] a nivel de página (formato de los archivos de profesión): { prof, ranks, for_class, name, at, text }.
  -- El instructor depende de la clase (raza) y del rango, así que no va dentro de cada [[route]].
  local class = M.Class()
  for _, p in ipairs(M.Pages("professions")) do
    for _, t in ipairs(type(p.trainer) == "table" and p.trainer or {}) do
      if type(t) == "table" and t.prof and (t.for_class == nil or t.for_class == "ANY" or t.for_class == class) then
        local key = M.ProfKey(t.prof)
        for _, k in ipairs(out.order) do
          if k == key or key == "both" then
            out[k].trainers = out[k].trainers or {}
            table.insert(out[k].trainers, t)
          end
        end
      end
    end
  end
  return out
end

-- Instructor de [[trainer]] con coordenadas para el rango `rankName`: [map, x, y, "nombre"] o nil.
local function PageTrainer(route, rankName)
  local best, bestScore
  for _, t in ipairs(route and route.trainers or {}) do
    local at = t.at
    -- Solo los que enseñan ese rango (una lista de rangos vacía o ausente = sin restricción).
    local teaches = type(t.ranks) ~= "table" or #t.ranks == 0 or not rankName
    for _, r in ipairs(type(t.ranks) == "table" and t.ranks or {}) do
      if r == rankName then teaches = true end
    end
    if teaches and type(at) == "table" and at[1] and at[2] and at[3] then
      local score = (t.for_class and t.for_class ~= "ANY") and 1 or 0
      if not best or score > bestScore then best, bestScore = t, score end
    end
  end
  if best then return { best.at[1], best.at[2], best.at[3], best.at[4] or best.name } end
end

local function Ranks()
  -- Si alguna página trae [[rank]] max, name, skill, level, se usa en lugar de la tabla de arriba.
  for _, p in ipairs(M.Pages("professions")) do
    if type(p.rank) == "table" and #p.rank > 0 then return p.rank end
  end
  return RANKS
end

local function RankIndex(max)
  local r = Ranks()
  for i, x in ipairs(r) do if max <= x.max then return i, r end end
  return #r, r
end

------------------------------------------------------------------------
-- Material: bolsas + banco (caché del banco al abrirlo)
------------------------------------------------------------------------
local function BankCache()
  local db = M.DB()
  db.bankCount = db.bankCount or {}
  return db.bankCount
end

function P.Have(id)
  local withBank = M.ItemCount(id, true)
  local bags = M.ItemCount(id)
  return math.max(withBank, bags + (BankCache()[id] or 0))
end

local bankOpen = false
local function CacheBank()
  local ids = {}
  local first = (NUM_BAG_SLOTS or 4) + 1
  local last = (NUM_BAG_SLOTS or 4) + (NUM_BANKBAGSLOTS or 7) + 1
  local bags = { BANK_CONTAINER or -1 }
  for b = first, last do table.insert(bags, b) end
  for _, bag in ipairs(bags) do
    for slot = 1, M.BagSlots(bag) do
      local it = M.SlotInfo(bag, slot)
      if it then ids[it.id] = true end
    end
  end
  local cache = {}
  for id in pairs(ids) do
    local inBank = M.ItemCount(id, true) - M.ItemCount(id)
    if inBank > 0 then cache[id] = inBank end
  end
  M.DB().bankCount = cache
end
P.CacheBank = CacheBank

-- mats: {id, n} o {id, n, idBase, nBase} (p. ej. madeja = 2 paños): cuenta madejas y paño suelto.
local function MatUnits(m)
  local per = tonumber(m[4]) or 1
  local have = P.Have(m[1]) * per + (m[3] and P.Have(m[3]) or 0)
  return have, per, m[3] or m[1]
end

local function CraftsLeft(s, rank)
  local from = math.max(rank, s.from)
  if from >= s.to then return 0 end
  local total = tonumber(s.n) or (s.to - s.from)
  return math.max(1, math.ceil(total * (s.to - from) / math.max(1, s.to - s.from)))
end
P.CraftsLeft = CraftsLeft

function P.SegName(s)
  if s.name then return s.name end
  if s.craft then return M.ItemName(s.craft) or M.SpellName(s.craft) or ("#" .. s.craft) end
  if s.craft_spell then return M.SpellName(s.craft_spell) or ("#" .. s.craft_spell) end
  return string.format("%d-%d", s.from, s.to)
end

-- `craft` = objeto fabricado; `craft_spell` = hechizo (encantamientos, que no crean objeto).
function P.SegIcon(s)
  if s.craft_spell then return M.SpellIcon(s.craft_spell) end
  if not s.craft then return nil end
  return M.ItemIcon(s.craft) or M.SpellIcon(s.craft)
end

------------------------------------------------------------------------
-- Estado de una profesión
------------------------------------------------------------------------
-- { key, label, missing, rank, max, rankName, train = rango, capped = rango, seg, left, canNow,
--   mats = {{id, have, need, miss}}, trainer, done, behind, target }
function P.State(key, level, route)
  level = level or M.Level()
  route = route or P.Routes()[key]
  local st = { key = key, label = M.ProfLabel(key) }
  local segs = route and route.segs or {}
  local rank, max = M.ProfRank(key)
  if not rank then
    st.missing = true
    local first = Ranks()[1]
    st.trainer = (segs[1] and segs[1].trainer) or PageTrainer(route, first and first.name)
    return st
  end
  st.rank, st.max = rank, max
  local ri, ranks = RankIndex(max)
  st.rankName = ranks[ri] and ranks[ri].name
  local nextR = ranks[ri + 1]
  if nextR and rank >= max - 15 then
    if level >= (nextR.level or 0) and rank >= (nextR.skill or 0) then st.train = nextR
    elseif level < (nextR.level or 0) then st.capped = nextR end
  end
  local trainer
  for _, s in ipairs(segs) do
    if s.trainer and s.from <= rank then trainer = s.trainer end
    if rank < s.to and not st.seg then st.seg = s end
  end
  if st.seg and st.seg.trainer then trainer = st.seg.trainer end
  st.trainer = trainer or (segs[1] and segs[1].trainer)
    or PageTrainer(route, (st.train and st.train.name) or (st.capped and st.capped.name) or st.rankName)
  if #segs == 0 then return st end
  if not st.seg then st.done = true; return st end
  local s = st.seg
  st.left = CraftsLeft(s, rank)
  st.mats = {}
  local canNow = st.left
  for _, m in ipairs(s.mats or {}) do
    if type(m) == "table" and m[1] then
      local have, per, base = MatUnits(m)
      local needOne = (tonumber(m[2]) or 1) * per
      canNow = math.min(canNow, math.floor(have / needOne))
      local need = needOne * st.left
      table.insert(st.mats, { id = base, have = have, need = need, miss = math.max(0, need - have) })
    end
  end
  st.canNow = (#st.mats > 0) and canNow or 0
  st.target = math.min(300, level * 5)
  st.behind = not st.capped and rank < st.target - 40
  return st
end

function P.States(level)
  local routes = P.Routes()
  local out = {}
  for _, key in ipairs(routes.order) do table.insert(out, P.State(key, level, routes[key])) end
  return out
end

-- Material que falta para el tramo actual de todas las profesiones: { [id] = cantidad }.
function P.ShoppingList()
  local want = {}
  for _, st in ipairs(P.States()) do
    for _, m in ipairs(st.mats or {}) do
      if m.miss > 0 then want[m.id] = (want[m.id] or 0) + m.miss end
    end
  end
  return want
end

-- Material que pide la ruta desde tu habilidad hasta el final: { [id] = cantidad }.
function P.RouteNeeds()
  local need = {}
  local routes = P.Routes()
  for _, key in ipairs(routes.order) do
    local rank = M.ProfRank(key)
    if rank then
      for _, s in ipairs(routes[key].segs) do
        local n = CraftsLeft(s, rank)
        if n > 0 then
          for _, m in ipairs(s.mats or {}) do
            if type(m) == "table" and m[1] then
              local per = tonumber(m[4]) or 1
              local id = m[3] or m[1]
              need[id] = (need[id] or 0) + (tonumber(m[2]) or 1) * per * n
            end
          end
        end
      end
    end
  end
  return need
end

function P.Arrow(tr, label)
  if type(tr) ~= "table" or not tr[1] then return end
  local name = tr[4] or label or (L.MOD_TRAINER or "Instructor")
  if Senda.Arrow and Senda.Arrow.SetTarget then
    local ok = pcall(Senda.Arrow.SetTarget, Senda.Arrow, tr[1], tr[2], tr[3], name, "professions")
    if ok then M.Print((L.MOD_ARROW_TO or "Flecha hacia:") .. " " .. name); return end
  end
  M.Print(string.format("%s: %.1f, %.1f", name, tr[2] or 0, tr[3] or 0))
end

local function TrainerText(tr)
  if type(tr) ~= "table" then return nil end
  return string.format("%s (%.1f, %.1f)", tr[4] or (L.MOD_TRAINER or "instructor"), tr[2] or 0, tr[3] or 0)
end
P.TrainerText = TrainerText

-- Frase corta para el asesor (o nil).
function P.Advice(st)
  if st.missing then
    return string.format(L.MOD_PROF_LEARN or "Aprende %s%s.", st.label, st.trainer and (" (" .. TrainerText(st.trainer) .. ")") or "")
  end
  if st.train then
    return string.format(L.MOD_PROF_TRAIN or "Entrena %s de %s ya: los puntos por encima de %d se pierden.", st.train.name, st.label, st.max)
  end
  return nil
end

------------------------------------------------------------------------
-- Avisos de tope (una vez por rango)
------------------------------------------------------------------------
local function CheckCaps()
  local db = M.DB()
  db.capWarned = db.capWarned or {}
  local level = M.Level()
  for _, st in ipairs(P.States(level)) do
    if st.rank and st.max and st.rank >= st.max - 5 and (st.train or st.capped) then
      local tag = st.key .. st.max
      if not db.capWarned[tag] then
        db.capWarned[tag] = true
        if st.train then
          M.Print(string.format("|cffffd100%s %d/%d:|r " .. (L.MOD_PROF_CAP_TRAIN or "entrena %s ya, o perderás puntos."), st.label, st.rank, st.max, st.train.name))
        else
          M.Print(string.format("|cffffd100%s %d/%d:|r " .. (L.MOD_PROF_CAP_WAIT or "%s pide nivel %d. Guarda el material hasta entonces."), st.label, st.rank, st.max, st.capped.name, st.capped.level or 0))
        end
        M.Fire("SENDA_PROF_CAP", st.key, st.rank, st.max)
      end
    end
  end
end

------------------------------------------------------------------------
-- Pestaña
------------------------------------------------------------------------
local ui = { bars = {} }
local BAR_H = 20

local function Bar(i)
  local b = ui.bars[i]
  if b then return b end
  b = CreateFrame("StatusBar", nil, ui.head)
  b:SetHeight(BAR_H - 2)
  b:SetStatusBarTexture("Interface\\TargetingFrame\\UI-StatusBar")
  local bg = b:CreateTexture(nil, "BACKGROUND")
  bg:SetAllPoints()
  bg:SetColorTexture(0, 0, 0, 0.5)
  b.text = b:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  b.text:SetPoint("CENTER")
  ui.bars[i] = b
  return b
end

function P.Refresh()
  if not ui.doc then return end
  local level = M.Level()
  local states = P.States(level)
  local shown = {}
  for _, st in ipairs(states) do shown[st.key] = true end
  local others = {}
  for _, p in ipairs(M.Professions()) do
    if not shown[p.key] then table.insert(others, p) end
  end

  -- barras de habilidad
  local n = 0
  local function bar(label, rank, max, warn)
    n = n + 1
    local b = Bar(n)
    b:ClearAllPoints()
    b:SetPoint("TOPLEFT", 8, -4 - (n - 1) * BAR_H)
    b:SetPoint("RIGHT", ui.head, "RIGHT", -8, 0)
    b:Show()
    if rank then
      b:SetMinMaxValues(0, math.max(1, max))
      b:SetValue(rank)
      if warn then b:SetStatusBarColor(1, 0.5, 0.25) else b:SetStatusBarColor(unpack(Senda.COLOR or { 0.3, 0.82, 0.66 })) end
      b.text:SetText(string.format("%s  %d / %d%s", label, rank, max, warn and ("  · " .. (L.MOD_PROF_NEAR_CAP or "entrena el rango siguiente")) or ""))
    else
      b:SetMinMaxValues(0, 1); b:SetValue(0); b:SetStatusBarColor(0.4, 0.4, 0.4)
      b.text:SetText(label .. ": " .. (L.MOD_PROF_NOT_LEARNED or "sin aprender"))
    end
  end
  for _, st in ipairs(states) do bar(st.label, st.rank, st.max, st.train ~= nil) end
  for _, p in ipairs(others) do bar(p.name, p.rank, p.max, false) end
  for i = n + 1, #ui.bars do ui.bars[i]:Hide() end
  local headH = n * BAR_H + 8
  ui.head:SetHeight(math.max(1, headH))
  ui.body:ClearAllPoints()
  ui.body:SetPoint("TOPLEFT", ui.parent, "TOPLEFT", 0, -headH)
  ui.body:SetPoint("BOTTOMRIGHT", ui.parent, "BOTTOMRIGHT", 0, 0)

  local nodes = {}
  if #states == 0 then
    table.insert(nodes, { t = "p", text = L.MOD_NO_PROF_ROUTE or "Todavía no hay rutas de profesión para tu clase." })
  end
  for _, st in ipairs(states) do
    local head = st.label
    if st.rank then head = string.format("%s %d/%d%s", st.label, st.rank, st.max, st.rankName and (" · " .. st.rankName) or "") end
    table.insert(nodes, { t = "h1", text = head })
    if st.missing then
      table.insert(nodes, { t = "row", hl = "warn", raw = true, icon = "Interface\\Icons\\INV_Misc_Book_09",
        text = string.format(L.MOD_PROF_MISSING or "No tienes %s.", st.label) .. (st.trainer and ("\n" .. TrainerText(st.trainer)) or "") })
    end
    if st.train then
      table.insert(nodes, { t = "row", hl = "warn", raw = true, icon = "Interface\\Icons\\INV_Misc_Book_11",
        text = string.format(L.MOD_PROF_TRAIN or "Entrena %s de %s ya: los puntos por encima de %d se pierden.", st.train.name, st.label, st.max) })
    elseif st.capped then
      table.insert(nodes, { t = "row", hl = "dim", raw = true, icon = "Interface\\Icons\\INV_Misc_PocketWatch_01",
        text = string.format(L.MOD_PROF_CAPPED or "Te acercas al tope. %s pide nivel %d: hasta entonces, sube de nivel y guarda material.", st.capped.name, st.capped.level or 0) })
    end
    if st.done then
      table.insert(nodes, { t = "p", text = L.MOD_PROF_DONE or "Ruta de subida terminada." })
    elseif st.seg then
      local s = st.seg
      local what
      if #(st.mats or {}) > 0 then
        what = string.format(L.MOD_PROF_NOW_CRAFT or "Ahora: fabrica unas |cffffffff%d x %s|r (de %d a %d).", st.left, P.SegName(s), math.max(st.rank, s.from), s.to)
      else
        what = string.format(L.MOD_PROF_NOW or "Ahora: |cffffffff%s|r (de %d a %d).", P.SegName(s), math.max(st.rank, s.from), s.to)
      end
      table.insert(nodes, { t = "row", hl = "now", raw = true, icon = P.SegIcon(s) or "Interface\\Icons\\Trade_Engineering",
        text = what .. M.StatusTag(s.status), item = (s.craft and M.ItemName(s.craft)) and s.craft or nil,
        spell = s.craft_spell or ((s.craft and not M.ItemName(s.craft)) and s.craft or nil) })
      if s.note then table.insert(nodes, { t = "md", text = s.note }) end
      for _, m in ipairs(st.mats or {}) do
        local col = m.miss > 0 and "|cffff8040" or "|cff7cc66f"
        table.insert(nodes, { t = "row", raw = true, icon = M.ItemIcon(m.id), item = m.id,
          text = (M.ItemName(m.id) or ("#" .. m.id)) .. string.format("  |cffaaaaaa%s %d / %d|r", L.MOD_HAVE or "tienes", m.have, m.need),
          right = m.miss > 0 and (col .. string.format(L.MOD_MISSING_N or "faltan %d", m.miss) .. "|r") or (col .. (L.MOD_ENOUGH or "suficiente") .. "|r") })
      end
      if (st.canNow or 0) > 0 then
        table.insert(nodes, { t = "row", hl = "good", raw = true, icon = "Interface\\RaidFrame\\ReadyCheck-Ready",
          text = string.format(L.MOD_PROF_CAN_NOW or "Con lo que llevas puedes fabricar %d ya.", st.canNow) })
      end
      if st.behind then
        table.insert(nodes, { t = "p", text = string.format("|cffff8040" .. (L.MOD_PROF_BEHIND or "Va atrasada: para tu nivel, lo ideal es ~%d.") .. "|r", st.target), raw = true })
      end
    end
    if st.trainer then
      local tr = st.trainer
      table.insert(nodes, { t = "btn", width = 280, label = (L.MOD_ARROW_TRAINER or "Flecha al instructor") .. ": " .. (tr[4] or "?"),
        onClick = function() P.Arrow(tr, st.label) end })
    end
  end
  local inBank = next(BankCache()) ~= nil
  if not inBank then
    table.insert(nodes, { t = "sp" })
    table.insert(nodes, { t = "p", text = "|cffaaaaaa" .. (L.MOD_OPEN_BANK or "Abre el banco una vez para que Senda cuente lo que guardas.") .. "|r", raw = true })
  end
  ui.doc:Set(nodes, true)
end

local function Build(parent)
  ui.parent = parent
  ui.head = CreateFrame("Frame", nil, parent)
  ui.head:SetPoint("TOPLEFT", 0, 0)
  ui.head:SetPoint("TOPRIGHT", 0, 0)
  ui.head:SetHeight(1)
  ui.body = CreateFrame("Frame", nil, parent)
  ui.body:SetPoint("TOPLEFT", 0, -8)
  ui.body:SetPoint("BOTTOMRIGHT", 0, 0)
  ui.doc = M.Doc(ui.body)
end

M.RegisterTab({ key = "professions", title = L.MOD_TAB_PROF or "Profesiones", icon = "Interface\\Icons\\Trade_Tailoring",
  order = 41, build = Build, refresh = P.Refresh })
M.RegisterOption({ key = "mod_profcap", label = L.MOD_OPT_PROFCAP or "Avisar cuando una profesión llega al tope de su rango",
  type = "toggle", default = true })

local function Changed()
  M.Debounce("prof-caps", 1, function()
    if M.Opt("mod_profcap") ~= false then CheckCaps() end
    if ui.doc and ui.doc.scroll:IsVisible() then P.Refresh() end
  end)
end
M.On("SKILL_LINES_CHANGED", Changed)
M.On("TRADE_SKILL_LIST_UPDATE", Changed)
M.On("CHAT_MSG_SKILL", Changed)
M.On("PLAYER_LEVEL_UP", Changed)
M.On("BANKFRAME_OPENED", function() bankOpen = true; pcall(CacheBank) end)
M.On("BANKFRAME_CLOSED", function() bankOpen = false end)
M.On("PLAYERBANKSLOTS_CHANGED", function() if bankOpen then M.Debounce("prof-bank", 0.5, CacheBank) end end)
M.On("BAG_UPDATE_DELAYED", function() if bankOpen then M.Debounce("prof-bank", 0.5, CacheBank) end end)
M.OnReady(Changed)

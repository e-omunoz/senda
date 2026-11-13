-- Senda / Modules / Professions
-- Las profesiones reales del personaje: todas las que tiene aprendidas (principales, secundarias y de recolección,
-- leídas del cliente con M.Professions / M.ProfRank) y, si aún le falta alguna principal, la recomendación de su clase
-- con el porqué. Para cada una: tramo actual, qué fabricar, fabricaciones esperadas que quedan, material que falta
-- (bolsas + banco), siguiente rango y dónde entrenarlo (instructor de tu facción, el más cercano; flecha).
-- Datos: conocimiento kind = "professions" (data/knowledge/general/professions-<prof>.toml, generados por
-- tools/gen_professions.py):
--   prof, prof_kind, assumes, [[rank]] name, max, skill, level, how, item
--   [[route]] prof, from, to, craft | craft_spell, spell, name, n, mats = [[id, n(, idBase, nBase)]], colors, learn,
--             learn_skill, note, status          (tramo de fabricación)
--   [[route]] prof, from, to, train, level, note (paso «entrena el rango siguiente»)
--   [[trainer]] prof, npc, name, faction, ranks, at = [map, x, y, "etiqueta"] | text, book, quest
-- y en la página general de profesiones: [[recommend]] class, profs, why.
local ADDON, Senda = ...
local M = Senda.Mod
if not M then return end
local L = M.L

local P = {}
Senda.Modules.Professions = P

-- Rangos por defecto (si la profesión no trae [[rank]]): tope, nombre, habilidad y nivel para entrenarlo.
-- Forever: Aprendiz desde nivel 1 (Classic pedía 5); Oficial 10; Experto 20 y Artesano 35 (Polestar trainers.rs).
local RANKS = {
  { max = 75,  name = L.MOD_RANK_1 or "Aprendiz", skill = 0,   level = 1 },
  { max = 150, name = L.MOD_RANK_2 or "Oficial",  skill = 50,  level = 10 },
  { max = 225, name = L.MOD_RANK_3 or "Experto",  skill = 125, level = 20 },
  { max = 300, name = L.MOD_RANK_4 or "Artesano", skill = 200, level = 35 },
}
-- Recolección: los rangos siguientes no piden nivel en Forever.
local GATHER_RANKS = {
  { max = 75,  name = RANKS[1].name, skill = 0,   level = 1 },
  { max = 150, name = RANKS[2].name, skill = 50,  level = 0 },
  { max = 225, name = RANKS[3].name, skill = 125, level = 0 },
  { max = 300, name = RANKS[4].name, skill = 200, level = 0 },
}
P.RANKS = RANKS
P.SECONDARY = { cooking = true, firstaid = true, fishing = true }

-- Ciudad de inicio por raza (desempate si no se puede medir la distancia al instructor).
local RACE_HOME = {
  Gnome = { [1455] = true, [1426] = true }, Dwarf = { [1455] = true, [1426] = true },
  Human = { [1453] = true, [1429] = true }, NightElf = { [1457] = true, [1438] = true },
}
local CAPITALS = { [1453] = 1, [1455] = 2, [1457] = 3 }

-- Fichas {item:N}/{spell:N}/{npc:N} de los textos de los datos, con el nombre del cliente.
local function Resolve(text)
  if type(text) ~= "string" then return text end
  local N = Senda.Names
  if N and N.Resolve then
    local ok, r = pcall(N.Resolve, N, text)
    if ok and type(r) == "string" then return r end
  end
  return text
end
P.Resolve = Resolve

local function Kind(key)
  if M.GATHERING[key] then return "gathering" end
  if P.SECONDARY[key] then return "secondary" end
  return "primary"
end
P.Kind = Kind

------------------------------------------------------------------------
-- Datos
------------------------------------------------------------------------
-- Plan de profesiones de tu clase: `prof_plan` en una página de tu clase, si no [[recommend]] de tu clase, si no el
-- `order_profs` general. Devuelve la lista ordenada y el porqué.
function P.PlanList()
  local class = M.Class()
  local plan, why, fallback
  for _, p in ipairs(M.Pages()) do
    if type(p.prof_plan) == "table" and p.class == class then plan = p.prof_plan end
    for _, r in ipairs(type(p.recommend) == "table" and p.recommend or {}) do
      if type(r) == "table" and r.class == class then
        why = why or r.why
        if not plan and type(r.profs) == "table" then plan = r.profs end
      end
    end
    if type(p.order_profs) == "table" and not fallback then fallback = p.order_profs end
  end
  local list = {}
  for _, k in ipairs(plan or fallback or {}) do table.insert(list, M.ProfKey(k)) end
  return list, why
end

function P.Plan()
  local set = {}
  for _, k in ipairs((P.PlanList())) do set[k] = true end
  return set
end

-- Todo lo que hay en los datos por profesión: { [key] = { key, page, segs, trains, trainers, ranks } }.
local function AllData()
  local data = {}
  local class, faction = M.Class(), M.Faction()
  local function get(key)
    data[key] = data[key] or { key = key, segs = {}, trains = {}, trainers = {} }
    return data[key]
  end
  for _, p in ipairs(M.Pages("professions")) do
    if p.prof then
      local d = get(M.ProfKey(p.prof))
      d.page = d.page or p
      if type(p.rank) == "table" and #p.rank > 0 then d.ranks = d.ranks or p.rank end
    end
    for _, s in ipairs(type(p.route) == "table" and p.route or {}) do
      if type(s) == "table" and s.prof and s.from and s.to then
        local d = get(M.ProfKey(s.prof))
        d.page = d.page or p
        if s.train then table.insert(d.trains, s) else table.insert(d.segs, s) end
      end
    end
    for _, t in ipairs(type(p.trainer) == "table" and p.trainer or {}) do
      if type(t) == "table" and t.prof
        and (t.faction == nil or t.faction == faction)
        and (t.for_class == nil or t.for_class == "ANY" or t.for_class == class) then
        local key = M.ProfKey(t.prof)
        if key == "both" then
          table.insert(get("tailoring").trainers, t)
          table.insert(get("enchanting").trainers, t)
        else
          table.insert(get(key).trainers, t)
        end
      end
    end
  end
  for _, d in pairs(data) do
    table.sort(d.segs, function(a, b) return a.from < b.from end)
    table.sort(d.trains, function(a, b) return a.to < b.to end)
  end
  return data
end
P.AllData = AllData

-- Profesiones que se enseñan: { { key, learned, inPlan, recommended } } en orden.
-- Todas las aprendidas (principales primero); si faltan principales, las del plan de tu clase que no tienes.
function P.Shown()
  local planList = P.PlanList()
  local plan = {}
  for i, k in ipairs(planList) do plan[k] = i end
  local learned, out, seen, primaries = {}, {}, {}, 0
  for _, p in ipairs(M.Professions()) do
    if p.key and not seen[p.key] then
      seen[p.key] = true
      table.insert(learned, p.key)
      if Kind(p.key) ~= "secondary" then primaries = primaries + 1 end
    end
  end
  -- Instantáneas de M.ProfRank (Compat) que M.Professions no listase.
  for _, k in ipairs(planList) do
    if not seen[k] and M.ProfRank(k) then
      seen[k] = true; table.insert(learned, k)
      if Kind(k) ~= "secondary" then primaries = primaries + 1 end
    end
  end
  table.sort(learned, function(a, b)
    local ka, kb = Kind(a) == "secondary" and 1 or 0, Kind(b) == "secondary" and 1 or 0
    if ka ~= kb then return ka < kb end
    local pa, pb = plan[a] or 99, plan[b] or 99
    if pa ~= pb then return pa < pb end
    return a < b
  end)
  for _, k in ipairs(learned) do table.insert(out, { key = k, learned = true, inPlan = plan[k] ~= nil }) end
  local free = 2 - primaries
  for _, k in ipairs(planList) do
    if free <= 0 then break end
    if not seen[k] and Kind(k) ~= "secondary" then
      seen[k] = true
      free = free - 1
      table.insert(out, { key = k, learned = false, inPlan = true, recommended = true })
    end
  end
  return out
end

-- { order = {key...}, [key] = { key, segs, trains, trainers, ranks, page, learned, inPlan, recommended } }
function P.Routes()
  local data = AllData()
  local out = { order = {} }
  for _, sh in ipairs(P.Shown()) do
    local d = data[sh.key] or { key = sh.key, segs = {}, trains = {}, trainers = {} }
    d.learned, d.inPlan, d.recommended = sh.learned, sh.inPlan, sh.recommended
    out[sh.key] = d
    table.insert(out.order, sh.key)
  end
  return out
end

local function Ranks(route)
  if route and type(route.ranks) == "table" and #route.ranks > 0 then return route.ranks end
  if route and Kind(route.key) == "gathering" then return GATHER_RANKS end
  -- Página de rangos general (professions-materials.toml).
  for _, p in ipairs(M.Pages("professions")) do
    if not p.prof and type(p.rank) == "table" and #p.rank > 0 then return p.rank end
  end
  return RANKS
end
P.Ranks = Ranks

local function RankIndex(max, ranks)
  for i, x in ipairs(ranks) do if max <= x.max then return i end end
  return #ranks
end

------------------------------------------------------------------------
-- Instructores
------------------------------------------------------------------------
local function Teaches(t, rankName)
  if not rankName or type(t.ranks) ~= "table" or #t.ranks == 0 then return true end
  for _, r in ipairs(t.ranks) do if r == rankName then return true end end
  return false
end

-- El instructor de tu facción que enseña `rankName`: el más cercano si se puede medir; si no, el de tu ciudad de inicio,
-- luego las capitales (Ventormenta, Forjaz, Darnassus). Devuelve { map, x, y, etiqueta } y la entrada, o el texto si
-- solo hay texto.
function P.TrainerFor(route, rankName)
  local pm, px, py = M.Compat("PlayerMapPos")
  local home = RACE_HOME[M.Race() or ""] or {}
  local best, bestScore, textOnly
  for i, t in ipairs(route and route.trainers or {}) do
    if Teaches(t, rankName) then
      local at = t.at
      if type(at) == "table" and at[1] and at[2] and at[3] then
        local score
        local d = pm and M.Compat("WorldDistance", pm, px, py, at[1], at[2] / 100, at[3] / 100)
        if type(d) == "number" then
          score = d
        else
          score = 100000 + (home[at[1]] and 0 or ((CAPITALS[at[1]] or 9) * 1000)) + i
        end
        if t.for_class and t.for_class ~= "ANY" then score = score - 0.5 end
        if not best or score < bestScore then best, bestScore = t, score end
      elseif not textOnly then
        textOnly = t
      end
    end
  end
  if best then return { best.at[1], best.at[2], best.at[3], best.at[4] or best.name }, best end
  if textOnly then return nil, textOnly end
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
  if s.spell and M.SpellName(s.spell) then return M.SpellName(s.spell) end
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

-- «naranja hasta 34 · amarillo 35 · verde 47 · gris 60» desde colors = {aprende, amarillo, verde, gris}.
function P.ColorText(s)
  local c = type(s.colors) == "table" and s.colors
  if not c or not c[4] then return nil end
  return string.format("|cffff8040%s %d|r · |cffffff00%s %d|r · |cff40c040%s %d|r · |cff808080%s %d|r",
    L.MOD_PROF_ORANGE or "naranja", c[1], L.MOD_PROF_YELLOW or "amarillo", c[2],
    L.MOD_PROF_GREEN or "verde", c[3], L.MOD_PROF_GREY or "gris", c[4])
end

------------------------------------------------------------------------
-- Estado de una profesión
------------------------------------------------------------------------
-- { key, label, kind, learned, inPlan, recommended, missing, rank, max, rankName, ranks, nextRank, nextTrainer,
--   nextTrainerText, train = rango, capped = rango, seg, left, leftTotal, canNow, mats = {{id, have, need, miss}},
--   trainer, done, noRoute, behind, target }
function P.State(key, level, route)
  level = level or M.Level()
  key = M.ProfKey(key)
  route = route or P.Routes()[key] or AllData()[key] or { key = key, segs = {}, trains = {}, trainers = {} }
  local st = { key = key, label = M.ProfLabel(key), kind = Kind(key), learned = route.learned,
    inPlan = route.inPlan, recommended = route.recommended }
  local segs = route.segs or {}
  local ranks = Ranks(route)
  st.ranks = ranks
  st.noRoute = #segs == 0
  local rank, max = M.ProfRank(key)
  if not rank then
    st.missing = true
    st.nextRank = ranks[1]
    st.trainer, st.trainerEntry = P.TrainerFor(route, ranks[1] and ranks[1].name)
    st.nextTrainer = st.trainer
    return st
  end
  st.learned = true
  st.rank, st.max = rank, max
  local ri = RankIndex(max, ranks)
  st.rankName = ranks[ri] and ranks[ri].name
  local nextR = ranks[ri + 1]
  st.nextRank = nextR
  if nextR then
    st.nextTrainer, st.nextTrainerEntry = P.TrainerFor(route, nextR.name)
    if rank >= max - 15 then
      if level >= (nextR.level or 0) and rank >= (nextR.skill or 0) then st.train = nextR
      elseif level < (nextR.level or 0) then st.capped = nextR end
    end
  end
  st.atCap = rank >= max and max < 300
  -- Instructor del rango actual (recetas nuevas) o, si toca, del siguiente.
  st.trainer = (st.train or st.capped) and st.nextTrainer or P.TrainerFor(route, st.rankName)
  if #segs == 0 then return st end
  local leftTotal = 0
  for _, s in ipairs(segs) do
    if rank < s.to and not st.seg then st.seg = s end
    leftTotal = leftTotal + CraftsLeft(s, rank)
  end
  st.leftTotal = leftTotal
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
  -- No se puede fabricar lo que aún no se aprende: el tramo empieza más arriba que tu habilidad.
  if s.learn_skill and rank < s.learn_skill then st.notYet = true; st.canNow = 0 end
  st.target = math.min(300, level * 5)
  st.behind = not st.capped and st.inPlan and rank < st.target - 40
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

-- Recetas de tu ruta que ya puedes aprender y aún te sirven: { [nombre en minúsculas] = { st, seg } }.
-- La usa el instructor para resaltarlas (nombre del cliente y, de reserva, el esES de los datos).
function P.TrainerRecipes()
  local out = {}
  for _, st in ipairs(P.States()) do
    local route = P.Routes()[st.key]
    if st.rank and route then
      for _, s in ipairs(route.segs or {}) do
        if s.to > st.rank and (s.learn_skill or s.from) <= st.rank then
          local names = { s.spell and M.SpellName(s.spell), s.name, s.craft and M.ItemName(s.craft) }
          for _, n in ipairs(names) do
            if type(n) == "string" and n ~= "" then out[n:lower()] = { st = st, seg = s } end
          end
        end
      end
    end
  end
  return out
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

-- Cómo se consigue el rango siguiente: instructor, libro o misión.
function P.RankHow(st)
  local r = st.nextRank
  if not r then return nil end
  local gate = {}
  if (r.skill or 0) > 0 then table.insert(gate, string.format(L.MOD_PROF_GATE_SKILL or "habilidad %d", r.skill)) end
  if (r.level or 0) > 1 then table.insert(gate, string.format(L.MOD_PROF_GATE_LEVEL or "nivel %d", r.level)) end
  local where = st.nextTrainer and st.nextTrainer[4] or (st.nextTrainerEntry and (st.nextTrainerEntry.text or st.nextTrainerEntry.name))
  local how
  if r.how == "book" then
    how = string.format(L.MOD_PROF_RANK_BOOK or "%s es un libro: cómpralo y léelo", r.name)
  elseif r.how == "quest" then
    how = string.format(L.MOD_PROF_RANK_QUEST or "%s es una misión", r.name)
  else
    how = string.format(L.MOD_PROF_RANK_TRAIN or "Siguiente rango: %s", r.name)
  end
  return how .. (#gate > 0 and (" (" .. table.concat(gate, ", ") .. ")") or "") .. (where and (": " .. where) or "")
end

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
P.CheckCaps = CheckCaps

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

-- Nodos de una profesión (los usa la pestaña; separado para poder probarlo).
function P.Nodes(st)
  local nodes = {}
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
  if st.noRoute and not st.missing then
    local txt
    if st.kind == "gathering" then
      txt = L.MOD_PROF_GATHER or "Se sube recolectando: cada nodo que no esté en gris da puntos. Recoge todo lo que veas mientras sigues la guía."
    else
      txt = L.MOD_PROF_NO_ROUTE or "Senda aún no tiene una ruta de subida para esta profesión."
    end
    table.insert(nodes, { t = "p", text = txt })
  elseif st.done then
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
      spell = s.craft_spell or s.spell })
    local col = P.ColorText(s)
    if col then table.insert(nodes, { t = "p", raw = true, text = col }) end
    if s.learn then
      table.insert(nodes, { t = "p", raw = true, text = "|cffaaaaaa" .. (L.MOD_PROF_LEARN_FROM or "Receta:") .. " " .. Resolve(s.learn) .. "|r" })
    end
    if s.note then table.insert(nodes, { t = "md", text = Resolve(s.note) }) end
    for _, m in ipairs(st.mats or {}) do
      local c = m.miss > 0 and "|cffff8040" or "|cff7cc66f"
      table.insert(nodes, { t = "row", raw = true, icon = M.ItemIcon(m.id), item = m.id,
        text = (M.ItemName(m.id) or ("#" .. m.id)) .. string.format("  |cffaaaaaa%s %d / %d|r", L.MOD_HAVE or "tienes", m.have, m.need),
        right = m.miss > 0 and (c .. string.format(L.MOD_MISSING_N or "faltan %d", m.miss) .. "|r") or (c .. (L.MOD_ENOUGH or "suficiente") .. "|r") })
    end
    if (st.canNow or 0) > 0 then
      table.insert(nodes, { t = "row", hl = "good", raw = true, icon = "Interface\\RaidFrame\\ReadyCheck-Ready",
        text = string.format(L.MOD_PROF_CAN_NOW or "Con lo que llevas puedes fabricar %d ya.", st.canNow) })
    end
    if st.leftTotal and st.leftTotal > 0 then
      table.insert(nodes, { t = "p", raw = true, text = string.format("|cffaaaaaa" ..
        (L.MOD_PROF_LEFT_TOTAL or "Quedan unas %d fabricaciones esperadas hasta %d.") .. "|r", st.leftTotal, st.seg and 300 or st.max) })
    end
    if st.behind then
      table.insert(nodes, { t = "p", text = string.format("|cffff8040" .. (L.MOD_PROF_BEHIND or "Va atrasada: para tu nivel, lo ideal es ~%d.") .. "|r", st.target), raw = true })
    end
  end
  -- Siguiente rango y dónde.
  local how = not st.missing and P.RankHow(st)
  if how then
    table.insert(nodes, { t = "p", raw = true, text = "|cffffd100" .. how .. "|r" })
  end
  local tr = st.missing and st.trainer or ((st.train or st.capped) and st.nextTrainer) or st.nextTrainer or st.trainer
  if tr then
    table.insert(nodes, { t = "btn", width = 280, label = (L.MOD_ARROW_TRAINER or "Flecha al instructor") .. ": " .. (tr[4] or "?"),
      onClick = function() P.Arrow(tr, st.label) end })
  end
  return nodes
end

function P.Refresh()
  if not ui.doc then return end
  local level = M.Level()
  local states = P.States(level)

  -- barras de habilidad: las que tienes (y las recomendadas que no)
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
  for i = n + 1, #ui.bars do ui.bars[i]:Hide() end
  local headH = n * BAR_H + 8
  ui.head:SetHeight(math.max(1, headH))
  ui.body:ClearAllPoints()
  ui.body:SetPoint("TOPLEFT", ui.parent, "TOPLEFT", 0, -headH)
  ui.body:SetPoint("BOTTOMRIGHT", ui.parent, "BOTTOMRIGHT", 0, 0)

  local nodes = {}
  local anyPrimary = false
  for _, st in ipairs(states) do if st.rank and st.kind ~= "secondary" then anyPrimary = true end end
  local _, why = P.PlanList()
  local recommended = {}
  for _, st in ipairs(states) do if st.recommended then table.insert(recommended, st.label) end end
  if #recommended > 0 then
    table.insert(nodes, { t = "h1", text = anyPrimary and (L.MOD_PROF_REC_SECOND or "Te falta una profesión principal")
      or (L.MOD_PROF_REC_TITLE or "Profesiones recomendadas para tu clase") })
    table.insert(nodes, { t = "p", text = table.concat(recommended, " + ") })
    if why then table.insert(nodes, { t = "md", text = (L.MOD_PROF_WHY or "**Por qué:**") .. " " .. Resolve(why) }) end
  end
  if #states == 0 then
    table.insert(nodes, { t = "p", text = L.MOD_NO_PROF_ROUTE or "Todavía no hay rutas de profesión para tu clase." })
  end
  for _, st in ipairs(states) do
    for _, nd in ipairs(P.Nodes(st)) do table.insert(nodes, nd) end
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

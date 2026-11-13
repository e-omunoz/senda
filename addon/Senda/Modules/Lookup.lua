-- Senda / Modules / Lookup
-- Buscador de objetos: de dónde sale cada objeto de las guías (botín, vendedores, recompensas y objetivos de misión).
--   * Línea en la descripción del objeto, una sola: «Senda: lo suelta {npc:N} en {map:N}» / «Senda: recompensa de
--     {quest:N}» / «Senda: para {quest:N}» (solo si se sabe; se apaga en Opciones > Objetos).
--   * /senda objeto <nombre o id>            dónde conseguirlo
--     /senda objeto señalar <nombre o id>    además apunta la flecha a la fuente más cercana
--   * Pestaña «Objetos» (UI/LookupTab.lua): caja de búsqueda, resultados y «Señalar».
--
-- Los datos (data/lookup/, docs/LOOKUP.md) viven en el addon aparte Senda_Lookup (LoadOnDemand, compilado por
-- tools/build.py): no cargan hasta que se mira el primer objeto o se busca, y siempre fuera de combate (en combate
-- la línea simplemente no sale). Una cadena por objeto, desempaquetada solo al consultarlo; los nombres para buscar
-- se registran como respaldo de {item:N} (Senda.Names) y la búsqueda los recorre por rebanadas (< 2 ms por
-- fotograma): el índice (nombre -> id) solo existe mientras se busca y se suelta 90 s después.
local ADDON, Senda = ...
local Compat, Events, Names = Senda.Compat, Senda.Events, Senda.Names
local L = Senda.L

local type, tonumber, tostring, pairs, ipairs = type, tonumber, tostring, pairs, ipairs
local format, floor = string.format, math.floor

local Lookup = {}
Senda.Lookup = Lookup

local ADDON_NAME = "Senda_Lookup"
local TIP_RGB = { 0.30, 0.82, 0.66 }
local MAX_TIP_NPCS = 2        -- PNJ nombrados en la línea de la descripción
local MAX_LINE = 5            -- fuentes por tipo en el detalle
local MAX_RESULTS = 20
local MIN_QUERY = 2
local IDX_IDLE = 90           -- s sin buscar tras los que se suelta el índice
local OPS_SLICE = 500         -- operaciones baratas por fotograma en las tareas por rebanadas
local BUDGET_MS = 1.5

Lookup.stats = { loads = 0, maxSliceOps = 0, searches = 0, indexBuilds = 0 }

local function Opt(key) return Senda.Options:Get(key) end

------------------------------------------------------------------------------
-- Carga del addon de datos
------------------------------------------------------------------------------

local failed -- motivo por el que no hay datos (toda la sesión), nil si aún se puede intentar
local registered = false

local function Data() return rawget(_G, "Senda_Lookup") end

function Lookup.IsLoaded()
  local d = Data()
  return type(d) == "table" and type(d.items) == "table"
end

-- Los nombres compilados pasan a ser respaldo de {item:N} y se sueltan de aquí (no se guardan dos copias).
local function RegisterNames()
  if registered then return end
  registered = true
  local d = Data()
  if not (d and type(d.names) == "table") then return end
  for loc, packed in pairs(d.names) do
    if Names:WantsLocale(loc) then Names:AddFallback(loc, "item", packed) end
  end
  d.names = nil
end

-- Carga Senda_Lookup si hace falta. -> true | false, "combat" | "missing" | "load"
function Lookup.Load()
  if Lookup.IsLoaded() then
    RegisterNames()
    return true
  end
  if failed then return false, failed end
  if Compat.InCombat() then return false, "combat" end
  local load = (C_AddOns and C_AddOns.LoadAddOn) or rawget(_G, "LoadAddOn")
  if type(load) ~= "function" then
    failed = "missing"
    return false, failed
  end
  local loaded, why = Compat.Try(load, ADDON_NAME)
  Lookup.stats.loads = Lookup.stats.loads + 1
  if loaded and Lookup.IsLoaded() then
    RegisterNames()
    return true
  end
  failed = (why == "MISSING" or why == "DISABLED") and "missing" or "load"
  Senda:Debug("Senda_Lookup no disponible: " .. tostring(why))
  return false, failed
end

------------------------------------------------------------------------------
-- Datos de un objeto
------------------------------------------------------------------------------

local entries, nEntries = {}, 0
local places = { n = {}, o = {} }

-- id -> { s = { { "n"|"o"|"i", id, prob|nil }, ... }, N, v = { npc }, g = { { mapa, x, y } }, q = { { quest, elegir } }, Q,
-- o = { quest }, O } o nil si no se conoce.
function Lookup.Entry(id)
  id = tonumber(id)
  local d = Data()
  if not (id and d and d.items) then return nil end
  local e = entries[id]
  if e ~= nil then return e or nil end
  local raw = d.items[id]
  if type(raw) ~= "string" then return nil end
  e = {}
  for k, v in raw:gmatch("(%a)=([^;]*)") do
    if k == "s" then
      e.s = {}
      for kind, sid, p in v:gmatch("(%a)(%d+):?([%d%.]*)") do e.s[#e.s + 1] = { kind, tonumber(sid), tonumber(p) } end
    elseif k == "v" then
      e.v = {}
      for n in v:gmatch("%d+") do e.v[#e.v + 1] = tonumber(n) end
    elseif k == "g" then
      e.g = {}
      for m, x, y in v:gmatch("(%d+):([%d%.]+):([%d%.]+)") do e.g[#e.g + 1] = { tonumber(m), tonumber(x), tonumber(y) } end
    elseif k == "q" then
      e.q = {}
      for q, c in v:gmatch("(%d+)(c?)") do e.q[#e.q + 1] = { tonumber(q), c == "c" } end
    elseif k == "o" then
      e.o = {}
      for q in v:gmatch("%d+") do e.o[#e.o + 1] = tonumber(q) end
    elseif k == "N" or k == "Q" or k == "O" then
      e[k] = tonumber(v)
    end
  end
  if nEntries >= 200 then entries, nEntries = {}, 0 end
  entries[id], nEntries = e, nEntries + 1
  return e
end

-- Lugar de un PNJ (kind "n") o de un objeto del mundo ("o"): { map (uiMap, 0 = mazmorra), x, y (%), mapId, n,
-- instance } o nil.
function Lookup.Place(kind, id)
  id = tonumber(id)
  local d = Data()
  local t = d and d.places and d.places[kind]
  if not (id and t) then return nil end
  local memo = places[kind]
  local p = memo[id]
  if p ~= nil then return p or nil end
  local raw = t[id]
  if type(raw) == "string" then
    local m, x, y, mid, n = raw:match("^(%d+),(%-?[%d%.]+),(%-?[%d%.]+),(%-?%d+),(%d+)$")
    if m then
      p = { map = tonumber(m), x = tonumber(x), y = tonumber(y), mapId = tonumber(mid), n = tonumber(n),
        instance = tonumber(m) == 0 }
    end
  end
  memo[id] = p or false
  return p
end

local function InZone(p, playerMap)
  return p and playerMap and not p.instance and p.map == playerMap
end

------------------------------------------------------------------------------
-- La línea de la descripción
------------------------------------------------------------------------------

local function Where(p)
  if not p then return "" end
  if p.instance then return L.LOOKUP_IN_DUNGEON end
  return format(L.LOOKUP_IN_MAP, p.map)
end

local function NpcRef(r)
  if r[3] then return format("{npc:%d} (%s%%)", r[2], tostring(r[3])) end
  return format("{npc:%d}", r[2])
end

-- Texto con fichas ({npc:N}, {map:N}...) de la línea «Senda: ...», o nil si no se sabe nada del objeto. Una sola
-- fuente, la mejor: botín de PNJ (los de tu zona primero) > objeto del mundo > contenedor > vendedor > sitio de la
-- ruta > recompensa de misión > objetivo de misión.
function Lookup.TipText(id)
  local e = Lookup.Entry(id)
  if not e then return nil end
  local playerMap = Compat.BestMap()
  if e.s then
    local npcs, obj, box = {}, nil, nil
    for _, r in ipairs(e.s) do
      if r[1] == "n" then
        npcs[#npcs + 1] = r
      elseif r[1] == "o" then
        if not obj or (not InZone(Lookup.Place("o", obj[2]), playerMap) and InZone(Lookup.Place("o", r[2]), playerMap)) then
          obj = r
        end
      else
        box = box or r
      end
    end
    if #npcs > 0 then
      -- el mapa de la línea: el tuyo si algún PNJ está en él; si no, el del mejor PNJ con sitio
      local mapSel
      for _, r in ipairs(npcs) do
        if InZone(Lookup.Place("n", r[2]), playerMap) then mapSel = playerMap break end
      end
      local first
      for _, r in ipairs(npcs) do
        local p = Lookup.Place("n", r[2])
        if p and not first then first = p end
      end
      local shown, place = {}, nil
      for _, r in ipairs(npcs) do
        local p = Lookup.Place("n", r[2])
        local ok
        if mapSel then ok = InZone(p, mapSel)
        elseif first then ok = p and p.map == first.map
        else ok = true end
        if ok and #shown < MAX_TIP_NPCS then
          shown[#shown + 1] = NpcRef(r)
          place = place or p
        end
      end
      local extra = (e.N or #e.s) - #shown
      local more = extra > 0 and format(L.LOOKUP_MORE, extra) or ""
      local fmt = #shown == 1 and L.LOOKUP_TIP_DROP_ONE or L.LOOKUP_TIP_DROP_MANY
      return format(fmt, table.concat(shown, L.LOOKUP_AND), Where(place), more)
    end
    if obj then return format(L.LOOKUP_TIP_OBJECT, Where(Lookup.Place("o", obj[2]))) end
    if box then return format(L.LOOKUP_TIP_CONTAINER, box[2]) end
  end
  if e.v and e.v[1] then
    return format(L.LOOKUP_TIP_VENDOR, e.v[1], Where(Lookup.Place("n", e.v[1])))
  end
  if e.g and e.g[1] then
    local g = e.g[1]
    for _, c in ipairs(e.g) do if InZone({ map = c[1] }, playerMap) then g = c break end end
    return format(L.LOOKUP_TIP_ROUTE, g[1])
  end
  if e.q and e.q[1] then return format(L.LOOKUP_TIP_REWARD, e.q[1][1]) end
  if e.o and e.o[1] then return format(L.LOOKUP_TIP_QUEST, e.o[1]) end
  return nil
end

local function ItemIdOfTooltip(tt, data)
  local id = type(data) == "table" and not Compat.IsSecret(data) and Compat.Num(data.id)
  if id then return id end
  if tt and tt.GetItem then
    local ok, _, link = pcall(tt.GetItem, tt)
    if ok and type(link) == "string" and not Compat.IsSecret(link) then return tonumber(link:match("item:(%d+)")) end
  end
end

-- Descripciones a rehacer cuando lleguen nombres. Tabla aparte (débil): escribir campos en GameTooltip lo contamina.
local pendingTips = setmetatable({}, { __mode = "k" })

local function OnTooltipItem(tt, data)
  if not tt or not tt.AddLine then return end
  pendingTips[tt] = nil
  if Opt("lookupTip") == false then return end
  local id = ItemIdOfTooltip(tt, data)
  if not id then return end
  if not Lookup.IsLoaded() then
    -- en combate no se carga nada: la línea sale cuando el objeto se mire fuera de combate
    local ok = Lookup.Load()
    if not ok then return end
  end
  local text = Lookup.TipText(id)
  if not text then return end
  local pending = false
  Names:EachToken(text, function(kind, tid)
    if not Names:Get(kind, tid) then pending = true end
  end)
  pendingTips[tt] = pending or nil
  tt:AddLine(Names:Resolve(text), TIP_RGB[1], TIP_RGB[2], TIP_RGB[3], true)
end
Lookup.OnTooltipItem = OnTooltipItem

local hooked = false
local function HookTooltips()
  if hooked then return end
  hooked = true
  if TooltipDataProcessor and TooltipDataProcessor.AddTooltipPostCall and Enum and Enum.TooltipDataType then
    TooltipDataProcessor.AddTooltipPostCall(Enum.TooltipDataType.Item, function(tt, data)
      if tt == GameTooltip or tt == ItemRefTooltip then pcall(OnTooltipItem, tt, data) end
    end)
  elseif GameTooltip and GameTooltip.HookScript then
    pcall(GameTooltip.HookScript, GameTooltip, "OnTooltipSetItem", function(tt) pcall(OnTooltipItem, tt) end)
    if ItemRefTooltip then
      pcall(ItemRefTooltip.HookScript, ItemRefTooltip, "OnTooltipSetItem", function(tt) pcall(OnTooltipItem, tt) end)
    end
  end
end

-- Cuando llegan los nombres que faltaban, la descripción que se está viendo se rehace una vez.
local function RefreshTooltips()
  for _, tt in ipairs({ GameTooltip, ItemRefTooltip }) do
    if tt and pendingTips[tt] and tt.IsShown and tt:IsShown() then
      pendingTips[tt] = nil
      if tt.RefreshData then pcall(tt.RefreshData, tt) end
    end
  end
end

------------------------------------------------------------------------------
-- Fuentes con sitio (para «Señalar») y la más cercana
------------------------------------------------------------------------------

local function Add(list, src)
  list[#list + 1] = src
  return src
end

-- Fuentes de un objeto, en este orden: botín, vendedores, sitio de la ruta. Cada una:
--   { kind = "drop" | "vendor" | "route" | "object", npc | obj, chance, via (objeto contenedor), place }
-- place = { map, x, y (%), instance } o nil (se sabe la fuente pero no dónde está).
function Lookup.Sources(id)
  local e = Lookup.Entry(id)
  local out = {}
  if not e then return out end
  for _, r in ipairs(e.s or {}) do
    if r[1] == "n" then
      Add(out, { kind = "drop", npc = r[2], chance = r[3], place = Lookup.Place("n", r[2]) })
    elseif r[1] == "o" then
      Add(out, { kind = "object", obj = r[2], chance = r[3], place = Lookup.Place("o", r[2]) })
    elseif r[1] == "i" then
      local c = Lookup.Entry(r[2])
      local n = 0
      for _, r2 in ipairs(c and c.s or {}) do
        if r2[1] == "n" and n < MAX_TIP_NPCS then
          n = n + 1
          Add(out, { kind = "drop", npc = r2[2], chance = r[3], via = r[2], place = Lookup.Place("n", r2[2]) })
        end
      end
    end
  end
  for _, npc in ipairs(e.v or {}) do
    Add(out, { kind = "vendor", npc = npc, place = Lookup.Place("n", npc) })
  end
  for _, g in ipairs(e.g or {}) do
    Add(out, { kind = "route", place = { map = g[1], x = g[2], y = g[3], instance = g[1] == 0 } })
  end
  return out
end

-- La fuente con sitio en un mapa de verdad más cercana al jugador: src, metros (nil si no se puede medir). Sin
-- posición del jugador o en otro continente se queda la primera (la de mejor probabilidad). -> src | nil, motivo
-- ("nodata" | "none" | "dungeon")
function Lookup.Nearest(id)
  if not Lookup.IsLoaded() then return nil, "nodata" end
  local list = Lookup.Sources(id)
  local pm, px, py = Compat.PlayerMapPos()
  local best, bestD, first, sawDungeon
  for _, s in ipairs(list) do
    local p = s.place
    if p and p.instance then
      sawDungeon = true
    elseif p and p.map and p.map > 0 then
      first = first or s
      local d = pm and Compat.WorldDistance(pm, px, py, p.map, p.x / 100, p.y / 100)
      if d and (not bestD or d < bestD) then best, bestD = s, d end
    end
  end
  if best then return best, bestD end
  if first then return first, nil end
  return nil, sawDungeon and "dungeon" or "none"
end

local function ItemName(id)
  return Names:Get("item", id) or Names:Placeholder("item", id)
end

local function SourceLabel(s)
  if s.npc then return Names:Get("npc", s.npc) or Names:Placeholder("npc", s.npc) end
  return L.LOOKUP_WORLD_OBJECT
end

-- Apunta la flecha a la fuente más cercana. -> true, src, metros | false, "nodata" | "none" | "dungeon" | "combat"
function Lookup.Point(id)
  id = tonumber(id)
  if not id then return false, "none" end
  local ok, why = Lookup.Load()
  if not ok then return false, why end
  local src, meters = Lookup.Nearest(id)
  if not src then return false, meters end -- el segundo valor es el motivo
  if not Senda.Arrow then return false, "none" end
  local p = src.place
  Senda.Arrow:SetTarget(p.map, p.x, p.y, format(L.LOOKUP_ARROW_LABEL, ItemName(id), SourceLabel(src)), "lookup",
    { radius = 15 })
  Lookup.pointed = { id = id, src = src }
  return true, src, meters
end

function Lookup.ClearPoint()
  Lookup.pointed = nil
  if Senda.Arrow then Senda.Arrow:Clear("lookup") end
end

------------------------------------------------------------------------------
-- Detalle (chat y pestaña): líneas con fichas
------------------------------------------------------------------------------

local function Meters(m)
  if not m then return nil end
  if m >= 1000 then return format("%.1f km", m / 1000) end
  return format("%d m", floor(m + 0.5))
end

local function Quests(list, total, fmt)
  local t = {}
  for i, q in ipairs(list) do
    if i > MAX_LINE then break end
    local id = type(q) == "table" and q[1] or q
    t[#t + 1] = format("{quest:%d}", id) .. ((type(q) == "table" and q[2]) and (" " .. L.LOOKUP_CHOICE) or "")
  end
  local extra = (total or #list) - #t
  return format(fmt, table.concat(t, ", ") .. (extra > 0 and format(L.LOOKUP_MORE, extra) or ""))
end

-- Líneas (con fichas) de lo que se sabe del objeto, para /senda objeto y la pestaña. Siempre devuelve alguna.
function Lookup.Lines(id)
  local e = Lookup.Entry(id)
  if not e then return { L.LOOKUP_UNKNOWN } end
  local out = {}
  local drops, objs, boxes = {}, {}, {}
  for _, r in ipairs(e.s or {}) do
    if r[1] == "n" then drops[#drops + 1] = r elseif r[1] == "o" then objs[#objs + 1] = r else boxes[#boxes + 1] = r end
  end
  if #drops > 0 then
    local t = {}
    for i, r in ipairs(drops) do
      if i > MAX_LINE then break end
      local p = Lookup.Place("n", r[2])
      local bits = {}
      if p then bits[#bits + 1] = p.instance and L.LOOKUP_DUNGEON or format("{map:%d}", p.map) end
      if r[3] then bits[#bits + 1] = tostring(r[3]) .. "%" end
      t[#t + 1] = format("{npc:%d}", r[2]) .. (#bits > 0 and (" (" .. table.concat(bits, ", ") .. ")") or "")
    end
    local extra = (e.N or #e.s) - #t
    out[#out + 1] = format(L.LOOKUP_L_DROPS, table.concat(t, "; ") .. (extra > 0 and format(L.LOOKUP_MORE, extra) or ""))
  end
  if #objs > 0 then
    local t = {}
    for i, r in ipairs(objs) do
      if i > 3 then break end
      local p = Lookup.Place("o", r[2])
      t[#t + 1] = p and (p.instance and L.LOOKUP_DUNGEON or format("{map:%d}", p.map)) or L.LOOKUP_WORLD_OBJECT
    end
    out[#out + 1] = format(L.LOOKUP_L_OBJECTS, table.concat(t, ", "))
  end
  if #boxes > 0 then
    out[#out + 1] = format(L.LOOKUP_L_CONTAINER, format("{item:%d}", boxes[1][2]))
  end
  if e.v and e.v[1] then
    local t = {}
    for i, npc in ipairs(e.v) do
      if i > MAX_LINE then break end
      local p = Lookup.Place("n", npc)
      t[#t + 1] = format("{npc:%d}", npc) .. (p and not p.instance and (" ({map:" .. p.map .. "})") or "")
    end
    out[#out + 1] = format(L.LOOKUP_L_VENDORS, table.concat(t, "; "))
  end
  if e.g and e.g[1] then
    local t = {}
    for _, g in ipairs(e.g) do t[#t + 1] = g[1] == 0 and L.LOOKUP_DUNGEON or format("{map:%d}", g[1]) end
    out[#out + 1] = format(L.LOOKUP_L_ROUTE, table.concat(t, ", "))
  end
  if e.q then out[#out + 1] = Quests(e.q, e.Q, L.LOOKUP_L_REWARD) end
  if e.o then out[#out + 1] = Quests(e.o, e.O, L.LOOKUP_L_OBJECTIVE) end
  if #out == 0 then out[1] = L.LOOKUP_UNKNOWN end
  return out
end

-- ¿Se puede señalar? (una fuente con sitio en un mapa)
function Lookup.CanPoint(id)
  return (Lookup.Nearest(id)) ~= nil
end

-- Resumen de una línea para una lista de resultados (con fichas): la misma que la descripción pero sin «Senda: ».
function Lookup.Summary(id)
  local t = Lookup.TipText(id)
  if not t then return nil end
  return (t:gsub("^Senda: ", ""))
end

------------------------------------------------------------------------------
-- Búsqueda por nombre (por rebanadas)
------------------------------------------------------------------------------

local ACCENTS = {
  ["\195\161"] = "a", ["\195\169"] = "e", ["\195\173"] = "i", ["\195\179"] = "o", ["\195\186"] = "u",
  ["\195\188"] = "u", ["\195\177"] = "n", ["\195\129"] = "a", ["\195\137"] = "e", ["\195\141"] = "i",
  ["\195\147"] = "o", ["\195\154"] = "u", ["\195\156"] = "u", ["\195\145"] = "n",
}

-- Minúsculas y sin tildes (los nombres y la consulta se comparan así).
function Lookup.Normalize(s)
  if type(s) ~= "string" then return "" end
  s = s:gsub("\195[\128-\191]", ACCENTS)
  return s:lower()
end
local Norm = Lookup.Normalize

local job, idx, idxTimer, idxStamp, pump
local searchSeq = 0

local ops, sliceStart, sliced = 0, 0, false
local function Tick()
  if not sliced then return end
  ops = ops + 1
  if ops >= OPS_SLICE or (ops % 64 == 0 and (debugprofilestop() - sliceStart) > BUDGET_MS) then
    coroutine.yield()
  end
end

local function Pump()
  if not job then
    if pump then pump:SetScript("OnUpdate", nil) end
    return
  end
  if Compat.InCombat() then return end
  ops, sliceStart, sliced = 0, debugprofilestop(), true
  local ok, res = coroutine.resume(job.co)
  sliced = false
  if ops > Lookup.stats.maxSliceOps then Lookup.stats.maxSliceOps = ops end
  if not ok then
    job = nil
    if pump then pump:SetScript("OnUpdate", nil) end
    Senda:ReportError("Lookup: " .. tostring(res))
    return
  end
  if coroutine.status(job.co) == "dead" then
    local j = job
    job = nil
    if pump then pump:SetScript("OnUpdate", nil) end
    pcall(j.cb, res)
  end
end

local function StartJob(fn, cb)
  job = { co = coroutine.create(fn), cb = cb }
  pump = pump or CreateFrame("Frame")
  pump:SetScript("OnUpdate", Pump)
end

local function ReleaseIndex()
  idx, idxTimer = nil, nil
end

local function Touch()
  idxStamp = (GetTime and GetTime()) or 0
  if idxTimer then return end
  idxTimer = true
  local function check()
    local now = (GetTime and GetTime()) or 0
    if job then idxStamp = now end
    local left = IDX_IDLE - (now - idxStamp)
    if left <= 0.01 then ReleaseIndex() else Compat.After(left, check) end
  end
  Compat.After(IDX_IDLE, check)
end

-- Nombre que el cliente ya tiene en caché (sin pedir nada al servidor).
local function ClientCached(id)
  local CI = C_Item
  if not (CI and CI.IsItemDataCachedByID and CI.GetItemNameByID) then return nil end
  local ok, cached = pcall(CI.IsItemDataCachedByID, id)
  if not (ok and cached == true) then return nil end
  return Names.Usable((Compat.Try(CI.GetItemNameByID, id)))
end
Lookup.ClientCached = ClientCached

-- Construye el índice: por objeto, los nombres conocidos (cliente, volcado, idioma del cliente, inglés) normalizados
-- y pegados con tabuladores. Es el trabajo grande de la búsqueda; se repite solo si se suelta.
local function BuildIndex()
  Lookup.stats.indexBuilds = Lookup.stats.indexBuilds + 1
  local maps = {}
  for _, pk in ipairs(Names:PackStrings("item")) do
    local loc, s = pk[1], pk[2]
    local m = maps[loc] or {}
    maps[loc] = m
    local pos = 1
    while true do
      local a, b, id, name = s:find("\n(%d+)\t([^\n]*)", pos)
      if not a then break end
      id = tonumber(id)
      if m[id] == nil then m[id] = name end
      pos = b + 1
      Tick()
    end
  end
  local order = {}
  for _, pk in ipairs(Names:PackStrings("item")) do order[#order + 1] = pk[1] end
  local ids, text = {}, {}
  local n = 0
  for id in pairs(Data().items) do
    local seen, parts = {}, {}
    local function add(v)
      if v and v ~= "" and not seen[v] then
        seen[v] = true
        parts[#parts + 1] = Norm(v)
      end
    end
    add(ClientCached(id))
    add(Names:Dumped("item", id))
    for _, loc in ipairs(order) do add(maps[loc] and maps[loc][id]) end
    n = n + 1
    ids[n] = id
    text[n] = table.concat(parts, "\t")
    Tick()
  end
  return { ids = ids, text = text, n = n, named = 0 }
end

-- Puntúa una coincidencia: 0 nombre igual, 1 empieza por la consulta, 2 palabra que empieza, 3 contiene.
local function Score(t, q, words)
  if t == q then return 0 end
  local best = 3
  for name in t:gmatch("[^\t]+") do
    if name == q then return 0 end
    if name:sub(1, #q) == q then best = math.min(best, 1)
    elseif name:find(" " .. q, 1, true) then best = math.min(best, 2) end
  end
  return best
end

-- Busca por nombre (o por número / enlace). cb(resultados, info) cuando termina; resultados = { { id, score } } ya
-- ordenados y recortados a MAX_RESULTS; info = { total (coincidencias), named (objetos con nombre en el índice),
-- items (objetos del buscador), reason ("short" | "combat" | "missing" | "load" | nil) }.
-- Devuelve false, motivo si no puede empezar (en combate, datos ausentes, consulta corta).
function Lookup.Search(query, cb)
  query = tostring(query or ""):gsub("^%s+", ""):gsub("%s+$", "")
  searchSeq = searchSeq + 1
  local seq = searchSeq
  job = nil
  local direct = tonumber(query:match("item:(%d+)")) or tonumber(query:match("^#?(%d+)$"))
  local ok, why = Lookup.Load()
  if not ok then
    cb({}, { reason = why })
    return false, why
  end
  Lookup.stats.searches = Lookup.stats.searches + 1
  if direct then
    cb({ { direct, 0 } }, { total = 1, items = 0, direct = true, known = Lookup.Entry(direct) ~= nil })
    return true
  end
  local q = Norm(query)
  if #q < MIN_QUERY then
    cb({}, { reason = "short" })
    return false, "short"
  end
  local words = {}
  for w in q:gmatch("%S+") do words[#words + 1] = w end
  StartJob(function()
    if not idx then idx = BuildIndex() end
    Touch()
    local out, total = {}, 0
    local ids, text = idx.ids, idx.text
    for i = 1, idx.n do
      local t = text[i]
      local hit = t ~= ""
      if hit then
        for w = 1, #words do
          if not t:find(words[w], 1, true) then hit = false break end
        end
      end
      if hit then
        total = total + 1
        if #out < 600 then out[#out + 1] = { ids[i], Score(t, q, words) } end
      end
      Tick()
    end
    table.sort(out, function(a, b)
      if a[2] ~= b[2] then return a[2] < b[2] end
      return a[1] < b[1]
    end)
    local named = 0
    for i = 1, idx.n do if text[i] ~= "" then named = named + 1 end end
    while #out > MAX_RESULTS do out[#out] = nil end
    return { out, { total = total, named = named, items = idx.n } }
  end, function(res)
    if seq ~= searchSeq then return end -- una búsqueda más nueva sustituyó a esta
    cb(res[1], res[2])
  end)
  return true
end

function Lookup.Searching() return job ~= nil end
function Lookup.IndexLoaded() return idx ~= nil end
function Lookup.CancelSearch()
  searchSeq = searchSeq + 1
  job = nil
end

------------------------------------------------------------------------------
-- /senda objeto
------------------------------------------------------------------------------

local function Say(text)
  Senda:Print("%s", Names:Resolve(text))
end

local function ShowItem(id)
  Say(format(L.LOOKUP_HEADER, ItemName(id), id))
  for _, line in ipairs(Lookup.Lines(id)) do Say("  " .. line) end
  if Lookup.CanPoint(id) then
    Say("  " .. format(L.LOOKUP_POINT_HINT, id))
  end
end

local function PointAndSay(id)
  local ok, src, meters = Lookup.Point(id)
  if ok then
    local p = src.place
    Say(format(L.LOOKUP_POINTED, ItemName(id), SourceLabel(src), p.instance and "" or format("{map:%d}", p.map),
      Meters(meters) or "?"))
  else
    Say(L["LOOKUP_NOPOINT_" .. tostring(src):upper()] or L.LOOKUP_NOPOINT_NONE)
  end
end

local function Command(rest, args)
  local first = (args[2] or ""):lower()
  local point = first == "señalar" or first == "senalar" or first == "point" or first == "way"
  local clear = first == "borrar" or first == "clear" or first == "quitar"
  if clear then
    Lookup.ClearPoint()
    Say(L.LOOKUP_CLEARED)
    return
  end
  local query = rest or ""
  if point then query = query:gsub("^%S+%s*", "") end
  if query == "" then
    if point and Lookup.last then
      return PointAndSay(Lookup.last)
    end
    Say(L.LOOKUP_USAGE)
    return
  end
  local started, why = Lookup.Search(query, function(results, info)
    if info.reason then
      if info.reason ~= "short" then Say(L["LOOKUP_ERR_" .. info.reason:upper()] or L.LOOKUP_ERR_LOAD) end
      return
    end
    if #results == 0 then
      Say(format(L.LOOKUP_NONE, query))
      return
    end
    local best = results[1]
    local single = #results == 1 or best[2] == 0
    if single then
      Lookup.last = best[1]
      if info.direct and not info.known then
        Say(format(L.LOOKUP_NOT_IN_DATA, best[1]))
        return
      end
      if point then PointAndSay(best[1]) else ShowItem(best[1]) end
      return
    end
    Say(format(L.LOOKUP_MANY, info.total, query))
    for i, r in ipairs(results) do
      if i > 8 then break end
      Say(format("  %d. %s", r[1], ItemName(r[1])))
    end
    Say(L.LOOKUP_PICK)
  end)
  if not started then
    if why == "short" then Say(L.LOOKUP_ERR_SHORT) end
    -- en los demás casos el aviso ya salió por el callback
  end
end

Senda.Slash:Register("objeto", Command, L.LOOKUP_SLASH_HELP)

------------------------------------------------------------------------------
-- Opción y eventos
------------------------------------------------------------------------------

Senda.Options:Register({ key = "lookupTip", label = L.OPT_LOOKUP_TIP, tooltip = L.OPT_LOOKUP_TIP_TIP, type = "toggle",
  default = true, section = L.OPT_SECTION_LOOKUP, order = 1 })

Events:On("SENDA_NAMES_UPDATED", RefreshTooltips)
Events:On("SENDA_READY", HookTooltips)

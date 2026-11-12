-- /senda volcar: pide al cliente el nombre de cada misión, PNJ, objeto, hechizo y zona que usan las guías y el
-- conocimiento compilados (y los datos de raros, mazmorras y viajes si algún día se compilan: Senda.Rares,
-- Senda.Dungeons, Senda.Travel), y lo guarda con el idioma y el build del cliente en SendaNamesDB (cuenta).
-- tools/import_names.py lo pasa a data/locale/<idioma>/ como dato verificado en el juego.
--
--   /senda volcar             empieza o retoma (solo pide lo que falta en este build)
--   /senda volcar parar       se detiene; se retoma con /senda volcar
--   /senda volcar reiniciar   borra lo guardado de este idioma y empieza de cero
--
-- Nunca bloquea: todo va en una corrutina que avanza un poco cada fotograma (recorrer los datos cede cada
-- WALK_STEP nodos; las peticiones salen de PER_SLICE en PER_SLICE, con un máximo de MAX_INFLIGHT esperando
-- respuesta) y se para en combate. SendaNamesDB:
--   { version = 1, locales = { esES = { build, date, done, quest = { [id] = nombre }, npc, item, spell, map,
--                                        missing = { quest = { [id] = true }, ... } } } }
local _, Senda = ...
local Compat, Events, Names = Senda.Compat, Senda.Events, Senda.Names
local L = Senda.L

local Dump = {}
Names.Dump = Dump

local PER_SLICE = 20
local MAX_INFLIGHT = 40
local WALK_STEP = 1000
local PROGRESS_EVERY = 5 -- s entre líneas de progreso en el chat
local KINDS = Names.CLIENT_KINDS

-- Claves de los datos compilados que llevan ids, y de qué tipo.
local KEY_KIND = { quest = "quest", npc = "npc", item = "item", craft = "item", spell = "spell", map = "map",
  zone = "map" }
local LIST_KIND = { quests = "quest", npcs = "npc", items = "item", spells = "spell" }

local co, frame, job

local function Today()
  local ok, d = pcall(date, "%Y-%m-%d")
  return ok and type(d) == "string" and d or nil
end

local function DB()
  if type(SendaNamesDB) ~= "table" then SendaNamesDB = {} end
  local db = SendaNamesDB
  db.version = 1
  if type(db.locales) ~= "table" then db.locales = {} end
  return db
end

-- Datos de este idioma para este build (un build distinto empieza de cero: los nombres pueden cambiar).
local function LocaleDB(reset)
  local db, build = DB(), Compat.Build()
  local d = db.locales[Names.LOCALE]
  if reset or type(d) ~= "table" or d.build ~= build then
    if type(d) == "table" and d.build ~= build and not reset then
      Senda:Print(L.NAMES_DUMP_NEW_BUILD, tostring(build))
    end
    d = { build = build }
    db.locales[Names.LOCALE] = d
  end
  d.missing = type(d.missing) == "table" and d.missing or {}
  for _, k in ipairs(KINDS) do
    if type(d[k]) ~= "table" then d[k] = {} end
    if type(d.missing[k]) ~= "table" then d.missing[k] = {} end
  end
  return d
end

------------------------------------------------------------------------------
-- Recorrido de los datos (dentro de la corrutina)
------------------------------------------------------------------------------

-- Fuentes de ids: secciones de todas las guías, páginas de conocimiento y, si existen, raros/mazmorras/viajes.
local function Sources()
  local out = {}
  local G = Senda.Guides
  if G and G.AllSections then
    for _, sec in ipairs(G:AllSections()) do out[#out + 1] = sec end
  end
  local K = Senda.Knowledge
  if K and type(K.pages) == "table" then out[#out + 1] = K.pages end
  for _, key in ipairs({ "Rares", "Dungeons", "Travel" }) do
    local t = rawget(Senda, key)
    if type(t) == "table" then out[#out + 1] = t end
  end
  -- Diario de mazmorras: sus ids (descodifica dentro de esta corrutina si aún no se abrió el diario)
  local DG = Senda.Modules and Senda.Modules.Dungeons
  if DG and DG.DumpIds then out[#out + 1] = DG.DumpIds() end
  return out
end

local function Collect(ids)
  local seen, n = {}, 0
  local function add(kind, id)
    id = tonumber(id)
    if id and id > 0 and ids[kind] then ids[kind][id] = true end
  end
  local function tick()
    n = n + 1
    if n % WALK_STEP == 0 then coroutine.yield() end
  end
  local function walk(t, depth)
    if seen[t] or depth > 12 then return end
    seen[t] = true
    for k, v in pairs(t) do
      tick()
      local tv = type(v)
      if tv == "string" then
        Names:EachToken(v, add)
      elseif tv == "number" then
        local kind = KEY_KIND[k]
        if kind then add(kind, v) end
      elseif tv == "table" then
        local kind = LIST_KIND[k]
        if kind then
          for _, x in ipairs(v) do if type(x) == "number" then add(kind, x) end end
        elseif k == "at" or k == "trainer" then
          add("map", v[1])
        elseif k == "wps" then
          for _, w in ipairs(v) do if type(w) == "table" then add("map", w[1]) end end
        elseif k == "mats" then
          for _, m in ipairs(v) do if type(m) == "table" then add("item", m[1]) end end
        else
          walk(v, depth + 1)
        end
      end
    end
  end
  for _, src in ipairs(Sources()) do walk(src, 0) end
end

------------------------------------------------------------------------------
-- Trabajo
------------------------------------------------------------------------------

local function Pct()
  if not job or job.total == 0 then return 100 end
  return math.floor((job.have + job.answered) * 100 / job.total)
end

local function Body(d)
  local ids = {}
  for _, k in ipairs(KINDS) do ids[k] = {} end
  Collect(ids)
  local queue, total, have = {}, 0, 0
  for _, kind in ipairs(KINDS) do
    local list = {}
    for id in pairs(ids[kind]) do
      total = total + 1
      if d[kind][id] == nil then list[#list + 1] = id else have = have + 1 end
    end
    table.sort(list)
    for _, id in ipairs(list) do
      queue[#queue + 1] = kind
      queue[#queue + 1] = id
    end
  end
  job.total, job.have, job.todo = total, have, #queue / 2
  if job.todo == 0 then
    d.done, d.date = true, Today()
    Senda:Print(L.NAMES_DUMP_NOTHING, total)
    job.quiet = true
    return
  end
  Senda:Print(L.NAMES_DUMP_START, job.todo, total)
  local i = 1
  while i <= #queue do
    local started = 0
    while i <= #queue and started < PER_SLICE and job.inflight < MAX_INFLIGHT do
      local kind, id = queue[i], queue[i + 1]
      i = i + 2
      started = started + 1
      job.started = job.started + 1
      job.inflight = job.inflight + 1
      local j = job -- una respuesta tardía de un volcado parado o reiniciado no cuenta en el siguiente
      Names:Request(kind, id, function(name)
        j.inflight = j.inflight - 1
        j.answered = j.answered + 1
        if name then
          d[kind][id] = name
          d.missing[kind][id] = nil
          j.ok = j.ok + 1
        else
          d.missing[kind][id] = true
          j.miss = j.miss + 1
        end
      end)
    end
    coroutine.yield()
  end
  while job.inflight > 0 do coroutine.yield() end
  d.done, d.date = true, Today()
end

local function Stop()
  co = nil
  if frame then frame:Hide() end
end

local function Step()
  if not co then return Stop() end
  if Compat.InCombat() then
    if not job.paused then
      job.paused = true
      Senda:Print(L.NAMES_DUMP_PAUSED)
    end
    return
  end
  job.paused = false
  local ok, err = coroutine.resume(co)
  if not ok then
    Stop()
    Senda:ReportError(err)
    return
  end
  if coroutine.status(co) == "dead" then
    Stop()
    if not job.quiet then Senda:Print(L.NAMES_DUMP_DONE, job.ok, job.miss) end
    Events:Fire("SENDA_NAMES_DUMPED", job.ok, job.miss)
    return
  end
  local now = (GetTime and GetTime()) or 0
  if job.total > 0 and now - job.lastPrint >= PROGRESS_EVERY then
    job.lastPrint = now
    Senda:Print(L.NAMES_DUMP_PROGRESS, job.have + job.answered, job.total, Pct())
  end
end

function Dump:Running() return co ~= nil end

-- Peticiones lanzadas en esta ejecución y las que aún esperan respuesta (pruebas y depuración).
function Dump:Started() return job and job.started or 0 end
function Dump:InFlight() return job and job.inflight or 0 end

-- Progreso: hechos, total, ok, sin respuesta (nil si nunca se ha lanzado en esta sesión).
function Dump:Progress()
  if not job then return nil end
  return job.have + job.answered, job.total, job.ok, job.miss
end

function Dump:Start(reset)
  if co then
    Senda:Print(L.NAMES_DUMP_RUNNING, job.have + job.answered, job.total)
    return false
  end
  local d = LocaleDB(reset)
  d.done = false
  job = { total = 0, have = 0, todo = 0, answered = 0, ok = 0, miss = 0, inflight = 0, started = 0, lastPrint = 0 }
  job.lastPrint = (GetTime and GetTime()) or 0
  co = coroutine.create(function() Body(d) end)
  if not frame then
    frame = CreateFrame("Frame")
    frame:SetScript("OnUpdate", Step)
  end
  frame:Show()
  return true
end

function Dump:Stop()
  if not co then
    Senda:Print(L.NAMES_DUMP_NOT_RUNNING)
    return false
  end
  Stop()
  Senda:Print(L.NAMES_DUMP_STOPPED, job.have + job.answered, job.total)
  return true
end

Senda.Slash:Register("volcar", function(_, args)
  local sub = (args[2] or ""):lower()
  if sub == "parar" or sub == "stop" then
    Dump:Stop()
  elseif sub == "reiniciar" or sub == "reset" then
    if co then Stop() end
    Dump:Start(true)
  elseif sub == "help" or sub == "ayuda" then
    Senda:Print(L.NAMES_DUMP_HELP)
  else
    Dump:Start(false)
  end
end, L.NAMES_DUMP_SLASH)

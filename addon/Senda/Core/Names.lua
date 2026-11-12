-- Nombres en el idioma del cliente para las fichas de los textos de las guías:
--   {quest:N} misión · {npc:N} PNJ · {item:N} objeto · {spell:N} hechizo · {map:N} zona (uiMapID)
--   {obj:N} objeto del mundo (el cliente no lo nombra por id: solo el respaldo)
--
--   Senda.Names:Resolve(text) -> texto con las fichas sustituidas (nunca bloquea)
--   Senda.Names:Get(kind, id) -> nombre, origen ("client" | "dump" | "pack") o nil
--   Senda.Names:Request(kind, id, fn) -> fn(nombre|nil, kind, id) cuando el cliente responde (solo el cliente)
--   Senda.Names:Cached(kind, id) -> nombre que el cliente ya dio en esta sesión, o nil
--   Senda.Names:AddFallback(locale, kind, packed) -- lo llaman los archivos generados Locale/Names_<locale>.lua
--                                                    y el buscador de objetos (Modules/Lookup.lua) al cargar Senda_Lookup
--   Senda.Names:WantsLocale(locale) -> ¿le sirve a este cliente el respaldo de ese idioma?
--
-- Orden: lo que el cliente ya dio en esta sesión; si no, se le pide (sin esperar) y mientras tanto se usa lo que
-- guardó /senda volcar en SendaNamesDB (mismo idioma) o el respaldo compilado de data/locale/<idioma>/ (el del
-- cliente y, en último lugar, el inglés). Cuando llegan nombres que se están mostrando, un único evento
-- "SENDA_NAMES_UPDATED" (agrupado) hace que el HUD se redibuje.
--
-- Cómo pregunta al cliente:
--   misión  C_QuestLog.GetTitleForQuestID; si no está en caché, RequestLoadQuestByID y QUEST_DATA_LOAD_RESULT
--   PNJ     C_TooltipInfo.GetHyperlink("unit:Creature-0-0-0-0-<id>-0"), primera línea (reintentos cortos)
--   objeto  C_Item.GetItemNameByID; si no, Item:CreateFromItemID(id):ContinueOnItemLoad
--   hechizo C_Spell.GetSpellName (y RequestLoadSpellData + SPELL_DATA_LOAD_RESULT si existe)
--   zona    C_Map.GetMapInfo(id).name
-- Los valores secretos (combate) cuentan como «sin respuesta»; un fallo se vuelve a intentar al minuto.
-- Idea de la caché y del redibujado agrupado: Adaptado de Polestar, addon/Polestar/Core/Names.lua.
local _, Senda = ...
local Compat, Events = Senda.Compat, Senda.Events
local L = Senda.L

local Names = {}
Senda.Names = Names

local type, tonumber, tostring, pcall, ipairs, pairs = type, tonumber, tostring, pcall, ipairs, pairs
local Try, IsSecret = Compat.Try, Compat.IsSecret

Names.KINDS = { "quest", "npc", "item", "spell", "map", "obj" }
-- Los que el cliente sabe nombrar por id (los que pide /senda volcar).
Names.CLIENT_KINDS = { "quest", "npc", "item", "spell", "map" }

local LOCALE = (GetLocale and GetLocale()) or "esES"
Names.LOCALE = LOCALE
local ALIAS = { esMX = "esES", enGB = "enUS" }
local ORDER = { LOCALE }
if ALIAS[LOCALE] then ORDER[#ORDER + 1] = ALIAS[LOCALE] end
if LOCALE ~= "enUS" and ALIAS[LOCALE] ~= "enUS" then ORDER[#ORDER + 1] = "enUS" end

local PLACEHOLDER = {
  quest = "QUEST_FALLBACK", npc = "NPC_FALLBACK", item = "ITEM_FALLBACK", spell = "SPELL_FALLBACK",
  map = "MAP_FALLBACK", obj = "OBJ_FALLBACK",
}

local RETRY_AFTER = 60   -- s: un nombre que el cliente no dio se vuelve a pedir pasado este tiempo
local TIMEOUT = 10       -- s: espera máxima de una respuesta asíncrona
local NPC_TRIES, NPC_GAP = 8, 0.25

local cache, state, failedAt, shown, packs, packMemo = {}, {}, {}, {}, {}, {}
local waiters = {} -- "kind:id" -> { fn, ... }
local deadlines = {} -- "kind:id" -> GetTime() límite de una petición asíncrona (sin PNJ: esos se sondean)
local sweeping = false
for _, k in ipairs(Names.KINDS) do
  cache[k], state[k], failedAt[k], shown[k], packMemo[k] = {}, {}, {}, {}, {}
end

local function Now() return (GetTime and GetTime()) or 0 end

-- Cadena útil como nombre (ni secreta, ni vacía, ni «Recuperando datos»).
local function Usable(v)
  if v == nil or IsSecret(v) or type(v) ~= "string" or v == "" then return nil end
  if v == rawget(_G, "RETRIEVING_DATA") or v == rawget(_G, "UNKNOWNOBJECT") or v == rawget(_G, "UNKNOWN") then
    return nil
  end
  return v
end
Names.Usable = Usable

------------------------------------------------------------------------------
-- Respaldo: SendaNamesDB (volcado del cliente) y Locale/Names_<locale>.lua (compilado)
------------------------------------------------------------------------------

function Names:WantsLocale(loc)
  for _, l in ipairs(ORDER) do
    if l == loc then return true end
  end
  return false
end

-- packed: "<id>\t<nombre>" por línea. Se guarda tal cual y se corta al pedirlo (sin tablas enormes en memoria).
function Names:AddFallback(loc, kind, packed)
  if type(packed) ~= "string" or not cache[kind] or not self:WantsLocale(loc) then return end
  packs[loc] = packs[loc] or {}
  packs[loc][kind] = (packs[loc][kind] or "\n") .. packed .. "\n"
  packMemo[kind] = {}
end

local function FromPack(kind, id)
  local memo = packMemo[kind]
  local v = memo[id]
  if v ~= nil then return v or nil end
  local key = "\n" .. id .. "\t"
  for _, loc in ipairs(ORDER) do
    local s = packs[loc] and packs[loc][kind]
    if s then
      local i = s:find(key, 1, true)
      if i then
        local j = s:find("\n", i + #key, true)
        v = s:sub(i + #key, (j or (#s + 1)) - 1)
        break
      end
    end
  end
  memo[id] = v or false
  return v
end

local function FromDump(kind, id)
  local db = rawget(_G, "SendaNamesDB")
  local d = type(db) == "table" and type(db.locales) == "table" and db.locales[LOCALE]
  if type(d) ~= "table" then return nil end
  local t = d[kind]
  local v = type(t) == "table" and t[id]
  -- Los objetos del buscador (Modules/Lookup.lua) que el volcado ve aparte, en `litem`.
  if not v and kind == "item" and type(d.litem) == "table" then v = d.litem[id] end
  return type(v) == "string" and v ~= "" and v or nil
end

-- Nombre del volcado guardado (SendaNamesDB), sin mirar el respaldo compilado.
function Names:Dumped(kind, id)
  id = tonumber(id)
  if not id or not cache[kind] then return nil end
  return FromDump(kind, id)
end

-- Respaldo compilado de un tipo: lista { { idioma, texto }, ... } en el orden de preferencia, con el texto en el
-- formato de AddFallback (una línea "id<TAB>nombre" por nombre). Lo recorre el buscador de objetos por rebanadas; no
-- se copia.
function Names:PackStrings(kind)
  local out = {}
  for _, loc in ipairs(ORDER) do
    local s = packs[loc] and packs[loc][kind]
    if s then out[#out + 1] = { loc, s } end
  end
  return out
end

-- Respaldo sin preguntar al cliente (volcado guardado o compilado).
function Names:Fallback(kind, id)
  id = tonumber(id)
  if not id or not cache[kind] then return nil end
  return FromDump(kind, id) or FromPack(kind, id)
end

------------------------------------------------------------------------------
-- Cliente
------------------------------------------------------------------------------

local CLIENT = {}

function CLIENT.quest(id)
  local QL = C_QuestLog
  return QL and Usable((Try(QL.GetTitleForQuestID, id))) or nil
end

function CLIENT.npc(id)
  local TI = C_TooltipInfo
  if not (TI and TI.GetHyperlink) then return nil end
  local data = Try(TI.GetHyperlink, "unit:Creature-0-0-0-0-" .. id .. "-0")
  if type(data) ~= "table" or IsSecret(data) then return nil end
  local lines = data.lines
  local first = type(lines) == "table" and not IsSecret(lines) and lines[1]
  if type(first) ~= "table" then return nil end
  return Usable(first.leftText)
end

function CLIENT.item(id)
  local CI = C_Item
  return CI and CI.GetItemNameByID and Usable((Try(CI.GetItemNameByID, id))) or nil
end

function CLIENT.spell(id)
  local CS = C_Spell
  local n = CS and CS.GetSpellName and Usable((Try(CS.GetSpellName, id)))
  return n or Usable(Compat.SpellName(id))
end

function CLIENT.map(id)
  return Usable(Compat.MapName(id))
end

local redrawPending = false
local function ScheduleRedraw()
  if redrawPending then return end
  redrawPending = true
  Compat.After(0.2, function()
    redrawPending = false
    Events:Fire("SENDA_NAMES_UPDATED")
  end)
end

local function Report(err) Senda:ReportError(err) end

-- Respuesta (nombre o nil) de una petición. async: llegó más tarde (puede hacer falta redibujar).
local function Finish(kind, id, name, async)
  if state[kind][id] ~= "wait" then return end
  if name then
    cache[kind][id] = name
    state[kind][id] = nil
  else
    state[kind][id] = "fail"
    failedAt[kind][id] = Now()
  end
  local key = kind .. ":" .. id
  deadlines[key] = nil
  local list = waiters[key]
  waiters[key] = nil
  if list then
    for _, fn in ipairs(list) do
      local ok, err = pcall(fn, name, kind, id)
      if not ok then Report(err) end
    end
  end
  if async and name and shown[kind][id] then ScheduleRedraw() end
end

local ASYNC = {}

function ASYNC.quest(id)
  local QL = C_QuestLog
  if not (QL and QL.RequestLoadQuestByID) then return false end
  Try(QL.RequestLoadQuestByID, id)
  return true
end

function ASYNC.item(id)
  local ItemMixin = rawget(_G, "Item")
  if type(ItemMixin) == "table" and ItemMixin.CreateFromItemID then
    local ok, it = pcall(ItemMixin.CreateFromItemID, ItemMixin, id)
    if ok and type(it) == "table" and it.ContinueOnItemLoad then
      local empty = it.IsItemEmpty and Try(it.IsItemEmpty, it)
      if empty then return false end
      local okc = pcall(it.ContinueOnItemLoad, it, function()
        local n = (it.GetItemName and Usable((Try(it.GetItemName, it)))) or CLIENT.item(id)
        Finish("item", id, n, true)
      end)
      if okc then return true end
    end
  end
  local CI = C_Item
  if CI and CI.RequestLoadItemDataByID then
    Try(CI.RequestLoadItemDataByID, id)
    return true
  end
  return false
end

function ASYNC.npc(id)
  local tries = 0
  local function Poll()
    if state.npc[id] ~= "wait" then return end
    tries = tries + 1
    local n = CLIENT.npc(id)
    if n or tries >= NPC_TRIES then
      Finish("npc", id, n, true)
    else
      Compat.After(NPC_GAP, Poll)
    end
  end
  Compat.After(NPC_GAP, Poll)
  return true
end

function ASYNC.spell(id)
  local CS = C_Spell
  if not (CS and CS.RequestLoadSpellData) then return false end
  Try(CS.RequestLoadSpellData, id)
  return true
end

-- Pide el nombre al cliente. Puede terminar en el acto (ya estaba en caché) o más tarde.
local function Start(kind, id)
  if state[kind][id] == "wait" or not CLIENT[kind] then return end
  state[kind][id] = "wait"
  local n = CLIENT[kind](id)
  if n then return Finish(kind, id, n, false) end
  local starter = ASYNC[kind]
  if not (starter and starter(id)) then return Finish(kind, id, nil, false) end
  if kind ~= "npc" and state[kind][id] == "wait" then
    deadlines[kind .. ":" .. id] = Now() + TIMEOUT
    if not sweeping then
      sweeping = true
      Compat.After(1, Names._Sweep)
    end
  end
end

-- Una sola revisión por segundo de las peticiones que no han respondido a tiempo (no un temporizador por id).
function Names._Sweep()
  local now, left, late = Now(), false, nil
  for key, t in pairs(deadlines) do
    if t <= now then
      late = late or {}
      late[#late + 1] = key
    else
      left = true
    end
  end
  for _, key in ipairs(late or {}) do
    local kind, id = key:match("^(%l+):(%d+)$")
    id = tonumber(id)
    if kind and id and state[kind][id] == "wait" then Finish(kind, id, CLIENT[kind](id), true) end
    deadlines[key] = nil
  end
  if left then
    Compat.After(1, Names._Sweep)
  else
    sweeping = false
  end
end

local function Retriable(kind, id)
  local st = state[kind][id]
  if st == nil then return true end
  return st == "fail" and (Now() - (failedAt[kind][id] or 0)) >= RETRY_AFTER
end

-- Respuestas del servidor.
local function Arrived(kind, id, success)
  id = tonumber(id)
  if not id or state[kind][id] ~= "wait" then return end
  Finish(kind, id, success ~= false and CLIENT[kind](id) or nil, true)
end
Events:On("QUEST_DATA_LOAD_RESULT", function(_, id, success) Arrived("quest", id, success) end)
Events:On("GET_ITEM_INFO_RECEIVED", function(_, id, success)
  -- con Item:ContinueOnItemLoad la respuesta llega por su función; esto cubre RequestLoadItemDataByID
  id = tonumber(id)
  if id and state.item[id] == "wait" then
    local n = CLIENT.item(id)
    if n or success == false then Finish("item", id, n, true) end
  end
end)
Events:On("SPELL_DATA_LOAD_RESULT", function(_, id, success) Arrived("spell", id, success) end)

------------------------------------------------------------------------------
-- API
------------------------------------------------------------------------------

function Names:Cached(kind, id)
  id = tonumber(id)
  return id and cache[kind] and cache[kind][id] or nil
end

-- Solo el cliente: fn(nombre|nil, kind, id). Si ya lo tiene, fn se llama en el acto.
function Names:Request(kind, id, fn)
  id = tonumber(id)
  if not id or not cache[kind] then
    if fn then fn(nil, kind, id) end
    return
  end
  local n = cache[kind][id]
  if n then
    if fn then fn(n, kind, id) end
    return
  end
  if not CLIENT[kind] then
    if fn then fn(nil, kind, id) end
    return
  end
  if fn then
    local key = kind .. ":" .. id
    waiters[key] = waiters[key] or {}
    table.insert(waiters[key], fn)
  end
  if state[kind][id] == "fail" and not Retriable(kind, id) then
    -- falló hace poco: se responde ya que no hay nombre (sin volver a preguntar)
    local key = kind .. ":" .. id
    local list = waiters[key]
    waiters[key] = nil
    for _, f in ipairs(list or {}) do
      local ok, err = pcall(f, nil, kind, id)
      if not ok then Report(err) end
    end
    return
  end
  if state[kind][id] == "fail" then state[kind][id] = nil end
  Start(kind, id)
end

-- Nombre para mostrar: cliente (pidiéndolo si hace falta, sin esperar) y, mientras, el respaldo.
function Names:Get(kind, id)
  id = tonumber(id)
  if not id or not cache[kind] then return nil end
  local n = cache[kind][id]
  if n then return n, "client" end
  shown[kind][id] = true
  if CLIENT[kind] and Retriable(kind, id) then
    if state[kind][id] == "fail" then state[kind][id] = nil end
    Start(kind, id)
    n = cache[kind][id]
    if n then return n, "client" end
  end
  n = FromDump(kind, id)
  if n then return n, "dump" end
  n = FromPack(kind, id)
  if n then return n, "pack" end
  return nil
end

-- Texto de reserva cuando no hay ningún nombre ("Misión #155").
function Names:Placeholder(kind, id)
  local fmt = L[PLACEHOLDER[kind] or ""] or "#%s"
  return string.format(fmt, tostring(id))
end

-- Sustituye las fichas {kind:id} de un texto. Las de un tipo desconocido se dejan como están.
function Names:Resolve(text)
  if type(text) ~= "string" or not text:find("{", 1, true) then return text end
  return (text:gsub("{(%l+):(%d+)}", function(kind, id)
    if not cache[kind] then return nil end
    return Names:Get(kind, id) or Names:Placeholder(kind, id)
  end))
end

-- Fichas de un texto: fn(kind, id) por cada una (las usa /senda volcar).
function Names:EachToken(text, fn)
  if type(text) ~= "string" or not text:find("{", 1, true) then return end
  for kind, id in text:gmatch("{(%l+):(%d+)}") do
    if cache[kind] then fn(kind, tonumber(id)) end
  end
end

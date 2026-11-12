-- Senda / Modules / Party
-- Pareja sincronizada: tu progreso y el de tu compañero de grupo, por mensajes de addon ocultos.
-- Solo ids y cuentas, nunca texto: dos clientes en idiomas distintos se entienden igual.
--
-- Reglas: mensajes de addon al grupo (canal PARTY) y nunca en banda; nada sale hasta que un miembro
-- del grupo ha contestado al saludo (o ha hablado Senda de cualquier forma). Al entrar en un grupo,
-- iniciar sesión o recargar en uno, o cuando entra alguien que aún no ha hablado Senda, sale un saludo
-- "1H|<versión>"; quien contesta recibe todo y quien nunca contesta no recibe nada más.
--
-- Mensajes (prefijo "Senda"; el número inicial es la versión del formato):
--   1H|<ver>                 saludo
--   1|33:5/8,0/1;60:-        cambios del registro de misiones ("60:-": salió del registro)
--   1S|...  1R|...           instantánea completa ("R": y pide la tuya)
--   1P|<índice>|<ver>|<guía> dónde vas por número (con la instantánea; informativo)
--   2P|<paso>|<guía>         dónde vas por id de paso (el que cuenta para delante/detrás)
--   2D|<q>,<q>,...           misiones entregadas de los pasos cerca del tuyo
--   2K|<q>,<q>,...           misiones que ha saltado («Saltar esta misión»): sus pasos no cuentan para delante/detrás
--   2U|<nivel>|<CLASE>|<Raza>|<ver>  quién eres (para saber qué pasos son de los dos)
--   2G|<paso>|<guía>         «Pedir que salte a mi paso»; el otro acepta o rechaza
--   2A|<y|n|x|=|p>           respuesta: sí, no, no puede, ya está, ya va por delante
-- Todo mensaje cabe en 255 bytes (el registro se parte por misiones enteras). Los cambios salen 2 s
-- después del último QUEST_LOG_UPDATE, nunca con un temporizador fijo. Un envío que el cliente rechaza
-- (límite de mensajes, bloqueo en instancia) se reintenta unos segundos después, en orden.
--
-- La espera: en un paso `complete` compartido, si tú ya terminaste un objetivo que tu compañero aún
-- necesita, el paso no avanza ni la guía entrega sola esa misión ("Espera a Ana: le falta 3/8"),
-- hasta que él termine, pulses «Seguir sin él», lleve más de 120 s desconectado o deje el grupo.
-- Los nombres de los compañeros solo viven en memoria: nunca se guardan en SavedVariables.
--
-- Adaptado de Polestar, addon/Polestar/Quests/Party.lua (formato de mensajes, saludo, instantáneas,
-- pasos compartidos, petición de sincronizar y espera del grupo), sobre el motor y la API de Senda.
local ADDON, Senda = ...
local Compat, Events, Util = Senda.Compat, Senda.Events, Senda.Util
local L = Senda.L

local tonumber, ipairs, pairs, next, type, tostring = tonumber, ipairs, pairs, next, type, tostring
local concat = table.concat

local Party = {}
Senda.Party = Party

Party.PREFIX = "Senda"
Party.MAX_BYTES = 255

local V1, V2 = "1", "2"
local MAX_QUESTS, MAX_OBJECTIVES, MAX_COUNT = 40, 10, 999
local DEBOUNCE = 2            -- s tras un cambio del registro / del paso
local JOIN_MIN, JOIN_SPREAD = 2, 2 -- saludo e instantánea 2-4 s después (que el otro ya escuche)
local REPLY_GAP = JOIN_MIN    -- una petición de instantánea dentro de esto ya tiene la nuestra
local RETRY, MAX_TRIES = 3, 6 -- envío rechazado: reintento cada 3 s, hasta 6 veces
local GONE_GRACE = 120        -- s que un compañero desconectado sigue reteniendo la espera
local SYNC_GAP = 30           -- s entre peticiones de saltar (en cada sentido)
local ANSWER_WINDOW = 300     -- s en que cuenta una respuesta a nuestra petición
local DONE_BACK, DONE_AHEAD = 20, 5
local HEARD_LOG = 8           -- mensajes oídos que guarda /senda pareja debug

------------------------------------------------------------------------------
-- Formato de los mensajes
------------------------------------------------------------------------------

local function piece(e)
  if e.counts == false then return e.q .. ":-" end
  local parts = {}
  for i, c in ipairs(e.counts) do parts[i] = c[1] .. "/" .. c[2] end
  return e.q .. ":" .. concat(parts, ",")
end

-- entries: { { q = id, counts = { { cur, max }, ... } | false }, ... } -> mensajes en orden (solo el
-- primero lleva la marca de instantánea: "R" si además pide la del otro) y, por mensaje, el índice de
-- la última entrada que lleva.
function Party.Encode(entries, snapshot, asks)
  local out, ends, parts, size = {}, {}, {}, 0
  local function header()
    if #out > 0 or not (snapshot or asks) then return V1 .. "|" end
    return V1 .. (asks and "R|" or "S|")
  end
  for i, e in ipairs(entries) do
    local p = piece(e)
    local extra = (#parts > 0 and 1 or 0) + #p
    if #parts > 0 and (#parts >= MAX_QUESTS or #header() + size + extra > Party.MAX_BYTES) then
      out[#out + 1] = header() .. concat(parts, ";")
      ends[#out] = i - 1
      parts, size, extra = {}, 0, #p
    end
    parts[#parts + 1] = p
    size = size + extra
  end
  if #parts > 0 or #out == 0 then
    out[#out + 1] = header() .. concat(parts, ";")
    ends[#out] = #entries
  end
  return out, ends
end

local function count(s)
  local n = tonumber(s)
  return n and n <= MAX_COUNT and n or nil
end

-- -> snapshot, entries, asks; nil si está mal formado o es de otra versión.
function Party.Decode(text)
  if type(text) ~= "string" then return nil end
  local mark, body = text:match("^" .. V1 .. "([SR]?)|(.*)$")
  if not mark then return nil end
  local entries = {}
  if body ~= "" then
    for p in (body .. ";"):gmatch("([^;]*);") do
      local q, rest = p:match("^(%d+):(.*)$")
      q = q and tonumber(q)
      if not q or q <= 0 or #entries >= MAX_QUESTS then return nil end
      local counts
      if rest == "-" then
        counts = false
      else
        counts = {}
        if rest ~= "" then
          for c in (rest .. ","):gmatch("([^,]*),") do
            local cur, max = c:match("^(%d+)/(%d+)$")
            cur, max = count(cur), count(max)
            if not (cur and max) or #counts >= MAX_OBJECTIVES then return nil end
            counts[#counts + 1] = { cur, max }
          end
        end
      end
      entries[#entries + 1] = { q = q, counts = counts }
    end
  end
  return mark ~= "", entries, mark == "R"
end

local function field(v) return (tostring(v or ""):gsub("|", ""):sub(1, 32)) end

function Party.EncodeHello() return V1 .. "H|" .. field(Senda.VERSION) end
function Party.DecodeHello(text)
  if type(text) ~= "string" then return nil end
  return text:match("^" .. V1 .. "H|([^|]*)$")
end

-- pos = { index, guide } -> "1P|<índice>|<versión>|<guía>".
function Party.EncodePos(pos)
  if type(pos) ~= "table" or type(pos.guide) ~= "string" or pos.guide == "" then return nil end
  local text = V1 .. "P|" .. (tonumber(pos.index) or 0) .. "|" .. field(Senda.VERSION) .. "|" .. pos.guide
  return #text <= Party.MAX_BYTES and text or nil
end
function Party.DecodePos(text)
  if type(text) ~= "string" then return nil end
  local index, version, guide = text:match("^" .. V1 .. "P|(%d+)|([^|]*)|(.+)$")
  if not index then return nil end
  return { index = tonumber(index), version = version, guide = guide }
end

-- pos = { key, guide } -> "2P|<paso>|<guía>" (o "2G|" con `request`).
local KEY = "[%w%-%._]+"
function Party.EncodeAt(pos, request)
  if type(pos) ~= "table" or type(pos.guide) ~= "string" or type(pos.key) ~= "string" then return nil end
  if not pos.key:match("^" .. KEY .. "$") or not pos.guide:match("^" .. KEY .. "$") then return nil end
  local text = V2 .. (request and "G|" or "P|") .. pos.key .. "|" .. pos.guide
  return #text <= Party.MAX_BYTES and text or nil
end
function Party.DecodeAt(text)
  if type(text) ~= "string" then return nil end
  local mark, key, guide = text:match("^" .. V2 .. "([PG])|(" .. KEY .. ")|(" .. KEY .. ")$")
  if not mark then return nil end
  return { key = key, guide = guide }, mark == "G"
end

local DONE_HEAD = V2 .. "D|"
function Party.EncodeDone(ids)
  local parts, size = {}, #DONE_HEAD
  for _, q in ipairs(type(ids) == "table" and ids or {}) do
    q = tonumber(q)
    if q and q > 0 and q == math.floor(q) then
      local p = tostring(q)
      local extra = (#parts > 0 and 1 or 0) + #p
      if #parts >= MAX_QUESTS or size + extra > Party.MAX_BYTES then break end
      parts[#parts + 1], size = p, size + extra
    end
  end
  return DONE_HEAD .. concat(parts, ",")
end
function Party.DecodeDone(text)
  if type(text) ~= "string" then return nil end
  local body = text:match("^" .. V2 .. "D|([%d,]*)$")
  if not body then return nil end
  local out, n = {}, 0
  if body == "" then return out end
  for p in (body .. ","):gmatch("([^,]*),") do
    local q = tonumber(p)
    if not q or q <= 0 or n >= MAX_QUESTS then return nil end
    if not out[q] then out[q], n = true, n + 1 end
  end
  return out
end

-- Misiones saltadas: "2K|<q>,<q>,..." (las que caben en un mensaje; las demás no se descuentan).
local SKIP_HEAD, MAX_SKIPPED = V2 .. "K|", 80
function Party.EncodeSkipped(ids)
  local list = {}
  for _, q in ipairs(type(ids) == "table" and ids or {}) do
    q = tonumber(q)
    if q and q > 0 and q == math.floor(q) then list[#list + 1] = q end
  end
  table.sort(list)
  local parts, size = {}, #SKIP_HEAD
  for _, q in ipairs(list) do
    local p = tostring(q)
    local extra = (#parts > 0 and 1 or 0) + #p
    if #parts >= MAX_SKIPPED or size + extra > Party.MAX_BYTES then break end
    parts[#parts + 1], size = p, size + extra
  end
  return SKIP_HEAD .. concat(parts, ",")
end
function Party.DecodeSkipped(text)
  if type(text) ~= "string" then return nil end
  local body = text:match("^" .. V2 .. "K|([%d,]*)$")
  if not body then return nil end
  local out, n = {}, 0
  if body == "" then return out end
  for p in (body .. ","):gmatch("([^,]*),") do
    local q = tonumber(p)
    if not q or q <= 0 or n >= MAX_SKIPPED then return nil end
    if not out[q] then out[q], n = true, n + 1 end
  end
  return out
end

-- u = { level, class ("WARLOCK"), race ("Gnome") } -> "2U|<nivel>|<CLASE>|<Raza>|<versión>".
function Party.EncodeUnit(u)
  local level = type(u) == "table" and tonumber(u.level)
  if not level or level < 1 or level > MAX_COUNT then return nil end
  local function token(v) return (type(v) == "string" and v:match("^%a+$")) and v or "" end
  return V2 .. "U|" .. math.floor(level) .. "|" .. token(u.class) .. "|" .. token(u.race) .. "|" .. field(Senda.VERSION)
end
function Party.DecodeUnit(text)
  if type(text) ~= "string" then return nil end
  local level, class, race, version = text:match("^" .. V2 .. "U|(%d+)|(%a*)|(%a*)|([^|]*)$")
  level = count(level)
  if not level or level < 1 then return nil end
  return { level = level, class = class ~= "" and class or nil, race = race ~= "" and race or nil,
    version = version ~= "" and version or nil }
end

local ANSWERS = { y = true, n = true, x = true, ["="] = true, p = true }
function Party.EncodeAnswer(code) return ANSWERS[code] and (V2 .. "A|" .. code) or nil end
function Party.DecodeAnswer(text)
  if type(text) ~= "string" then return nil end
  local code = text:match("^" .. V2 .. "A|(.)$")
  return code and ANSWERS[code] and code or nil
end

------------------------------------------------------------------------------
-- Estado
------------------------------------------------------------------------------

local function Opt(key)
  local v = Senda.Options and Senda.Options:Get(key)
  if v == nil then return true end
  return v and true or false
end

local spoken = {}    -- clave -> true: ha hablado Senda (saludo, respuesta o cualquier mensaje válido)
local roster = {}    -- clave -> unidad ("party1"), conectados
local units = {}     -- clave -> unidad, conectados o no
local members = {}   -- clave -> { key, name, quests = { [q] = { {cur,max}, ... } }, n, at, pos, done, unit }
local gone = {}      -- clave -> { m, at }: desconectados (retienen la espera GONE_GRACE s)
local released = {}  -- misión -> true: «Seguir sin él»
local greeted = {}   -- clave -> true: ya se dijo en el chat que usa Senda
local lastSent = {}  -- misión -> cuentas que el grupo tiene de nosotros
local posSent, doneSent, unitSent, skipSent
local outbox = {}    -- { { kind, text, tries } } en orden
local retryPending = false
local flushPending, posPending, unitPending, snapPending, pendingAsks, helloPending = false, false, false, false, false, false
local lastSnapshotAt
local combatOwed = false
local sync = { asked = {}, heardAt = {} }
local diag = { sends = 0, refused = 0, dropped = 0, heard = 0, matched = 0, log = {} }
local SYNC_POPUP = "SENDA_PARTY_SYNC"

local function grouped()
  return (IsInGroup and IsInGroup() and not (IsInRaid and IsInRaid())) and true or false
end
Party.Grouped = grouped

local function sharing() return Opt("duoSync") and grouped() and next(spoken) ~= nil end

local function now() return GetTime and GetTime() or 0 end

local changedPending = false
local function changed()
  if changedPending then return end
  changedPending = true
  Compat.After(0.3, function()
    changedPending = false
    Events:Fire("SENDA_PARTY_UPDATED")
    if Senda.Engine and Senda.Engine.RequestEvaluate then Senda.Engine:RequestEvaluate(0.1, "party") end
  end)
end

------------------------------------------------------------------------------
-- Envío: cola en orden con reintento de lo que el cliente rechaza
------------------------------------------------------------------------------

local function rawSend(text)
  local fn = C_ChatInfo and C_ChatInfo.SendAddonMessage
  if not fn then return false end
  local ok, r = pcall(fn, Party.PREFIX, text, "PARTY")
  diag.sends = diag.sends + 1
  diag.lastSend = text:sub(1, 3)
  diag.lastResult = ok and r or "error"
  if not ok then return false end
  local results = Enum and Enum.SendAddonMessageResult
  local success = results and results.Success or 0
  if r == false or (type(r) == "number" and r ~= success) then
    diag.refused = diag.refused + 1
    return false
  end
  return true
end

local pump
local function schedulePump(delay)
  if retryPending then return end
  retryPending = true
  Compat.After(delay, function()
    retryPending = false
    pump()
  end)
end

pump = function()
  if not grouped() then
    outbox = {}
    return
  end
  while outbox[1] do
    local m = outbox[1]
    if rawSend(m.text) then
      table.remove(outbox, 1)
    else
      m.tries = m.tries + 1
      if m.tries >= MAX_TRIES then
        table.remove(outbox, 1)
        diag.dropped = diag.dropped + 1
      else
        return schedulePump(RETRY)
      end
    end
  end
end

-- kind: "q" cambios (se acumulan), "s" instantánea; el resto ("H", "P", "D", "U", "G", "A") sustituye
-- al pendiente del mismo tipo.
local function queue(kind, text)
  if not text then return end
  if kind ~= "q" and kind ~= "s" then
    for i = #outbox, 1, -1 do
      if outbox[i].kind == kind and outbox[i].tries == 0 then table.remove(outbox, i) end
    end
  end
  outbox[#outbox + 1] = { kind = kind, text = text, tries = 0 }
  if not retryPending then pump() end
end

------------------------------------------------------------------------------
-- Lo nuestro: registro, paso, entregadas, quién somos
------------------------------------------------------------------------------

-- misión -> cuentas como se envían ("5/8,0/1"; "" sin objetivos).
function Party.ReadLog()
  local out = {}
  local Q = C_QuestLog
  if not (Q and Q.GetNumQuestLogEntries and Q.GetInfo) then return out end
  local n, kept = Compat.Try(Q.GetNumQuestLogEntries) or 0, 0
  for i = 1, Compat.Num(n) or 0 do
    local info = Compat.Try(Q.GetInfo, i)
    local q = type(info) == "table" and not info.isHeader and not info.isHidden and Compat.Num(info.questID)
    if q and q > 0 and not out[q] and kept < MAX_QUESTS then
      kept = kept + 1
      local objs = Compat.QuestObjectives(q)
      local parts = {}
      for j = 1, math.min(#objs, MAX_OBJECTIVES) do
        local o = objs[j]
        local need = math.min(o.need or 1, MAX_COUNT)
        local have = o.have or (o.finished and need or 0)
        parts[j] = math.min(have, MAX_COUNT) .. "/" .. need
      end
      out[q] = concat(parts, ",")
    end
  end
  return out
end

local function countsOf(s)
  if s == nil then return false end
  local out = {}
  for cur, max in s:gmatch("(%d+)/(%d+)") do out[#out + 1] = { tonumber(cur), tonumber(max) } end
  return out
end

-- Dónde vas: { key = id del paso, index, guide }, o nil sin guía o con la guía terminada.
function Party.MyPos()
  local E = Senda.Engine
  local g = E and E:GuideId()
  if not g then return nil end
  local step = E:CurrentStep()
  return { key = step and step.id or nil, index = step and E:Index() or 0, guide = g }
end

-- Lo entregado de los pasos cerca del tuyo (DONE_BACK antes, DONE_AHEAD después), lo más cerca primero.
function Party.MyDone()
  local E, Cond = Senda.Engine, Senda.Conditions
  local steps = E and E:Steps() or {}
  local live = math.min(E and E:Index() or 1, #steps + 1)
  local out, seen = {}, {}
  local function look(s)
    local e = steps[s]
    for _, q in ipairs(e and Cond:Quests(e.step) or {}) do
      if not seen[q] then
        seen[q] = true
        if Compat.IsQuestDone(q) or (E.turnedIn and E.turnedIn[q]) then out[#out + 1] = q end
      end
    end
  end
  for d = 0, DONE_BACK do
    look(live - d)
    if d > 0 and d <= DONE_AHEAD then look(live + d) end
  end
  return out
end

function Party.MySkipped()
  local t = Senda.db and Senda.db.skippedQuests
  local out = {}
  for q, v in pairs(t or {}) do if v and type(q) == "number" then out[#out + 1] = q end end
  return out
end

function Party.MyUnit()
  local _, class = Compat.Try(UnitClass, "player")
  local _, race = Compat.Try(UnitRace, "player")
  return { level = Compat.PlayerLevel(), class = class, race = race }
end

local function sendPos(force)
  posPending = false
  if not sharing() then return end
  local pos = Party.MyPos()
  local text = pos and pos.key and Party.EncodeAt(pos) or nil
  if text and (text ~= posSent or force) then
    queue("P", text)
    posSent = text
  end
  local done = Party.EncodeDone(Party.MyDone())
  if done ~= (doneSent or DONE_HEAD) or (force and done ~= DONE_HEAD) then
    queue("D", done)
    doneSent = done
  end
  local skipped = Party.EncodeSkipped(Party.MySkipped())
  if skipped ~= (skipSent or SKIP_HEAD) or (force and skipped ~= SKIP_HEAD) then
    queue("K", skipped)
    skipSent = skipped
  end
end

local function sendUnit(force)
  unitPending = false
  if not sharing() then return end
  local text = Party.EncodeUnit(Party.MyUnit())
  if text and (text ~= unitSent or force) then
    queue("U", text)
    unitSent = text
  end
end

-- Todo el registro, sustituyendo lo que el grupo sabe de nosotros; `asks`: y pide el suyo.
local function snapshot(asks)
  snapPending, pendingAsks = false, false
  if not grouped() or next(spoken) == nil or not Opt("duoSync") then return end
  if Compat.InCombat() then
    combatOwed = true
    pendingAsks = asks or pendingAsks
    return
  end
  local log, ids = Party.ReadLog(), {}
  for q in pairs(log) do ids[#ids + 1] = q end
  table.sort(ids)
  local entries = {}
  for i, q in ipairs(ids) do entries[i] = { q = q, counts = countsOf(log[q]) } end
  -- La instantánea sustituye a los cambios aún sin enviar.
  for i = #outbox, 1, -1 do
    if (outbox[i].kind == "q" or outbox[i].kind == "s") and outbox[i].tries == 0 then table.remove(outbox, i) end
  end
  local msgs = Party.Encode(entries, true, asks)
  for _, m in ipairs(msgs) do queue("s", m) end
  lastSent = log
  lastSnapshotAt = now()
  local pos = Party.MyPos()
  if pos then queue("I", Party.EncodePos(pos)) end
  sendPos(true)
  sendUnit(true)
end

local function scheduleSnapshot(asks)
  if asks then pendingAsks = true end
  if snapPending then return end
  snapPending = true
  Compat.After(JOIN_MIN + math.random() * JOIN_SPREAD, function() snapshot(pendingAsks) end)
end

local function hello()
  helloPending = false
  if not grouped() or not Opt("duoSync") then return end
  -- Si todos los del grupo ya han hablado Senda (su saludo llegó antes), no hace falta.
  local anyNew = false
  for key in pairs(roster) do
    if not spoken[key] then anyNew = true end
  end
  if anyNew then queue("H", Party.EncodeHello()) end
end

local function scheduleHello()
  if helloPending then return end
  helloPending = true
  Compat.After(JOIN_MIN + math.random() * JOIN_SPREAD, hello)
end

-- Cambios del registro desde lo último enviado.
local function flush()
  flushPending = false
  if not sharing() or snapPending then return end
  if Compat.InCombat() then combatOwed = true; return end
  local log, ids = Party.ReadLog(), {}
  for q, s in pairs(log) do
    if lastSent[q] ~= s then ids[#ids + 1] = q end
  end
  for q in pairs(lastSent) do
    if log[q] == nil then ids[#ids + 1] = q end
  end
  if #ids == 0 then return end
  table.sort(ids)
  local entries = {}
  for i, q in ipairs(ids) do entries[i] = { q = q, counts = countsOf(log[q]) } end
  for _, m in ipairs((Party.Encode(entries, false))) do queue("q", m) end
  lastSent = log
end

local function onLog()
  if flushPending or not sharing() then return end
  flushPending = true
  Compat.After(DEBOUNCE, flush)
end

local function onStep()
  if posPending or not sharing() then return end
  posPending = true
  Compat.After(DEBOUNCE, function() sendPos(false) end)
end

local function onLevel()
  if unitPending or not sharing() then return end
  unitPending = true
  Compat.After(DEBOUNCE, function() sendUnit(false) end)
end

------------------------------------------------------------------------------
-- Grupo
------------------------------------------------------------------------------

-- Clave y nombre de una unidad del grupo ("Ana" o "Ana-Reino"); false si el nombre es secreto.
local function unitKey(unit)
  local name, realm = Compat.Try(UnitName, unit)
  if name == nil then return nil end
  if Compat.IsSecret(name) or Compat.IsSecret(realm) then return false end
  if type(name) ~= "string" or name == "" then return nil end
  if type(realm) == "string" and realm ~= "" then return name .. "-" .. realm, name end
  return name, name
end

local function forgetAll()
  local had = next(members) ~= nil or next(spoken) ~= nil or next(gone) ~= nil
  spoken, roster, units, members, gone, released, lastSent = {}, {}, {}, {}, {}, {}, {}
  posSent, doneSent, unitSent, skipSent, outbox = nil, nil, nil, nil, {}
  sync.asked, sync.heardAt = {}, {}
  if sync.pending then
    sync.pending = nil
    if StaticPopup_Hide then StaticPopup_Hide(SYNC_POPUP) end
  end
  if had then changed() end
end

local function readRoster()
  if not grouped() then return forgetAll() end
  local online, offline, unitOf, fresh, moved = {}, {}, {}, false, false
  local n = Compat.Num(Compat.Try(GetNumSubgroupMembers)) or 0
  for i = 1, math.min(n, 4) do
    local unit = "party" .. i
    local key = unitKey(unit)
    if key == false then return end -- nombre secreto: se deja el grupo como estaba hasta el siguiente evento
    if key then
      unitOf[key] = unit
      local conn = Compat.Try(UnitIsConnected, unit)
      if conn == false then
        offline[key] = true
      else
        online[key] = unit
        if not roster[key] then
          moved = true
          if not spoken[key] then fresh = true end
        end
        local g = gone[key]
        if g and not members[key] and now() - g.at < GONE_GRACE then members[key] = g.m end
      end
    end
  end
  for key in pairs(roster) do
    if not online[key] then moved = true end
  end
  roster, units = online, unitOf
  for key, m in pairs(members) do
    if not online[key] then
      members[key] = nil
      if offline[key] then
        gone[key] = { m = m, at = now() }
        Compat.After(GONE_GRACE + 0.5, changed) -- la espera lo suelta pasada la gracia
      end
    end
  end
  for key in pairs(gone) do
    if not offline[key] then gone[key] = nil end
  end
  for key in pairs(spoken) do
    if not (online[key] or offline[key]) then spoken[key] = nil end
  end
  if moved then changed() end
  if fresh then scheduleHello() end
end

-- Quién envía: "me", o la clave, la unidad y el nombre corto de un miembro del grupo.
local function matchSender(sender)
  local base = sender:match("^([^%-]+)") or sender
  local me = Compat.Try(UnitName, "player")
  if type(me) == "string" and (sender == me or base == me) then return "me" end
  for key, unit in pairs(units) do
    local _, short = unitKey(unit)
    if sender == key or base == short then return key, unit, short end
  end
  return nil
end

local function memberFor(key, short)
  local m = members[key]
  if not m then
    m = { key = key, name = short, quests = {}, n = 0 }
    members[key] = m
  end
  m.name = short
  return m
end

-- Un miembro habló Senda. Si es nuevo y su mensaje no pide nuestra instantánea, se la mandamos.
local function heard(key, short, asks)
  if spoken[key] then return false end
  spoken[key] = true
  memberFor(key, short)
  if not greeted[key] then
    greeted[key] = true
    Senda:Print(L.DUO_HEARD, short)
  end
  if not asks and Opt("duoSync") then scheduleSnapshot(false) end
  changed()
  return true
end

local function apply(m, entries, snap)
  if snap then m.quests, m.n = {}, 0 end
  for _, e in ipairs(entries) do
    local had = m.quests[e.q] ~= nil
    if e.counts == false then
      if had then
        m.quests[e.q] = nil
        m.n = m.n - 1
      end
    elseif had or m.n < MAX_QUESTS then
      if not had then m.n = m.n + 1 end
      m.quests[e.q] = e.counts
    end
  end
end

------------------------------------------------------------------------------
-- Pasos compartidos y delante/detrás
------------------------------------------------------------------------------

-- Lista completa de la guía (todas las secciones y pasos, sin filtrar por clase): { list, pos }.
local fullCache = {}
local function FullOrder(guideId)
  local c = guideId and fullCache[guideId]
  if c then return c end
  c = { list = {}, pos = {} }
  if not guideId then return c end
  for _, sec in ipairs(Senda.Guides:SectionsOf(guideId)) do
    for _, s in ipairs(sec.steps or {}) do
      if type(s) == "table" and s.id and not c.pos[s.id] then
        c.list[#c.list + 1] = { step = s, section = sec }
        c.pos[s.id] = #c.list
      end
    end
  end
  fullCache[guideId] = c
  return c
end

-- ¿Pasa el filtro `if` para el compañero `who` ({ class, race })? Lo que no sabemos de él, sí.
local function PartnerFilter(f, who)
  if type(f) ~= "table" then return true end
  if f.class and who.class and not Util.Contains(f.class, who.class) then return false end
  if f.race and who.race and not Util.Contains(f.race, who.race) then return false end
  if f.faction and f.faction ~= Compat.PlayerFaction() then return false end
  return true
end

local function ForPartner(entry, who)
  return PartnerFilter(entry.section and entry.section["if"], who) and PartnerFilter(entry.step["if"], who)
end
Party.ForPartner = ForPartner

-- ¿Salta este paso `skipped` (conjunto de misiones saltadas)? Igual que Engine:StepSkipped: solo pasos de
-- misión y solo si todas sus misiones están saltadas.
local QUESTY = { accept = true, complete = true, turnin = true, dungeon = true }
local function SkippedIn(set, step)
  if not set or next(set) == nil or not QUESTY[step["do"]] then return false end
  local qs = Senda.Conditions:Quests(step)
  if not qs then return false end
  for _, q in ipairs(qs) do
    if not set[q] then return false end
  end
  return true
end

local function ForMe(entry)
  local Cond = Senda.Conditions
  return Cond:StaticFilter(entry.section and entry.section["if"]) and Cond:StaticFilter(entry.step["if"])
end

-- Clase y raza de un miembro: las del cliente, si no las que mandó ("2U|").
function Party.Who(m)
  local unit = m and units[m.key]
  local class, race
  if unit then
    local _, c = Compat.Try(UnitClass, unit)
    local _, r = Compat.Try(UnitRace, unit)
    if type(c) == "string" and not Compat.IsSecret(c) then class = c end
    if type(r) == "string" and not Compat.IsSecret(r) then race = r end
  end
  local u = m and m.unit
  return { class = class or (u and u.class), race = race or (u and u.race), level = u and u.level }
end

-- Pasos de los dos entre tu paso y el suyo: >0 va por delante, <0 por detrás; nil si su paso no está
-- en tu guía. Los pasos que solo tiene uno de los dos (los de tu clase, los suyos) no cuentan, ni los de
-- misiones que alguno de los dos ha saltado.
function Party.StepsApart(m)
  local E = Senda.Engine
  local step = E and E:CurrentStep()
  local at = m and m.at
  if not (step and at) then return nil end
  local order = FullOrder(E:GuideId())
  local a, b = order.pos[step.id], order.pos[at.key]
  if not (a and b) then return nil end
  local who = Party.Who(m)
  local mine = Senda.db and Senda.db.skippedQuests
  local lo, hi, sign = a, b, 1
  if b < a then lo, hi, sign = b, a, -1 end
  local n = 0
  for i = lo, hi - 1 do
    local e = order.list[i]
    if ForMe(e) and ForPartner(e, who) and not SkippedIn(mine, e.step) and not SkippedIn(m.skipped, e.step) then
      n = n + 1
    end
  end
  return n * sign
end

------------------------------------------------------------------------------
-- La espera
------------------------------------------------------------------------------

-- Los compañeros por los que se espera: conectados y los desconectados hace menos de GONE_GRACE s.
local function holders()
  local out, t = {}, now()
  for _, m in pairs(members) do out[#out + 1] = m end
  for _, g in pairs(gone) do
    if t - g.at < GONE_GRACE then out[#out + 1] = g.m end
  end
  table.sort(out, function(x, y) return x.name < y.name end)
  return out
end

local function waits() return Opt("duoWait") and grouped() end

-- Quién necesita aún objetivos de este paso `complete` compartido: { { name, cur, max, quest }, ... } o nil.
function Party.WaitFor(entry)
  local step = entry and entry.step
  if not (step and step["do"] == "complete" and waits()) then return nil end
  local qs = Senda.Conditions:Quests(step)
  if not qs then return nil end
  local out
  for _, m in ipairs(holders()) do
    if ForPartner(entry, Party.Who(m)) then
      for _, q in ipairs(qs) do
        local counts = not released[q] and Compat.IsOnQuest(q) and m.quests[q]
        if counts then
          local list = step.obj and { counts[step.obj] } or counts
          for _, c in ipairs(list) do
            if c[1] < c[2] then
              out = out or {}
              out[#out + 1] = { name = m.name, cur = c[1], max = c[2], quest = q }
              break
            end
          end
        end
      end
    end
  end
  return out
end

-- ¿Retiene el grupo este paso? Lo pregunta el motor cuando ya lo has cumplido tú.
function Party.Holds(entry)
  local w = Party.WaitFor(entry)
  return w ~= nil and #w > 0
end

-- ¿Espera el grupo para entregar la misión q? (la entrega automática no la hace mientras tanto)
function Party.HoldsQuest(q)
  if not q or released[q] or not waits() or not Compat.IsOnQuest(q) then return false end
  for _, m in ipairs(holders()) do
    for _, c in ipairs(m.quests[q] or {}) do
      if c[1] < c[2] then return true end
    end
  end
  return false
end

-- «Seguir sin él»: las misiones del paso actual dejan de esperar hasta que termine el grupo.
function Party.GoOn()
  local step = Senda.Engine:CurrentStep()
  for _, q in ipairs(step and Senda.Conditions:Quests(step) or {}) do released[q] = true end
  changed()
end

-- Línea de espera del HUD para el paso actual, si ya lo cumpliste tú y el compañero no.
function Party.HoldLine()
  local E = Senda.Engine
  local step, entry = E:CurrentStep()
  if not step or step["do"] ~= "complete" then return nil end
  if Senda.Conditions:Check(step, E.state or {}) ~= true then return nil end
  local w = Party.WaitFor(entry)
  if not w or #w == 0 then return nil end
  local parts, seen = {}, {}
  for _, x in ipairs(w) do
    if not seen[x.name] then
      seen[x.name] = true
      parts[#parts + 1] = string.format(L.DUO_WAIT, x.name, x.cur .. "/" .. x.max)
    end
  end
  return concat(parts, "\n")
end

------------------------------------------------------------------------------
-- Lo que se muestra
------------------------------------------------------------------------------

-- Miembros que han hablado Senda (con su progreso), por nombre.
function Party.Members()
  local out = {}
  for _, m in pairs(members) do out[#out + 1] = m end
  table.sort(out, function(x, y) return x.name < y.name end)
  return out
end

function Party.Relation(m)
  local d = Party.StepsApart(m)
  if d == nil then
    if m.at then return string.format(L.DUO_ELSEWHERE, m.name) end
    return nil
  end
  if d == 1 then return string.format(L.DUO_AHEAD_1, m.name) end
  if d > 1 then return string.format(L.DUO_AHEAD, m.name, d) end
  if d == -1 then return string.format(L.DUO_BEHIND_1, m.name) end
  if d < -1 then return string.format(L.DUO_BEHIND, m.name, -d) end
  return string.format(L.DUO_SAME, m.name)
end

-- Misiones de tus pasos cercanos (DONE_BACK antes, DONE_AHEAD x 3 después) que el compañero ya entregó
-- y tú no: ids en el orden de la guía.
function Party.TheirDoneNear(m)
  local out = {}
  if not (m and m.done) then return out end
  local E, Cond = Senda.Engine, Senda.Conditions
  local steps = E:Steps()
  local live, seen = E:Index(), {}
  for s = math.max(1, live - DONE_BACK), math.min(#steps, live + DONE_AHEAD * 3) do
    for _, q in ipairs(Cond:Quests(steps[s].step) or {}) do
      if not seen[q] and m.done[q] and not Compat.IsQuestDone(q) then
        seen[q] = true
        out[#out + 1] = q
      end
    end
  end
  return out
end

-- Línea corta del HUD: dónde va cada compañero y si ya entregó la misión de tu paso.
function Party.HudLine()
  if not grouped() then return nil end
  local list = Party.Members()
  if #list == 0 then return nil end
  local step = Senda.Engine:CurrentStep()
  local qs = step and Senda.Conditions:Quests(step) or {}
  local parts = {}
  for _, m in ipairs(list) do
    local r = Party.Relation(m) or m.name
    for _, q in ipairs(qs) do
      if m.done and m.done[q] then r = r .. " · " .. L.DUO_DONE_HERE; break end
    end
    parts[#parts + 1] = r
  end
  return L.DUO_HUD_PREFIX .. " " .. concat(parts, " · ")
end

------------------------------------------------------------------------------
-- «Pedir que salte a mi paso»
------------------------------------------------------------------------------

local function answer(code) if grouped() then queue("A", Party.EncodeAnswer(code)) end end

-- Lo que haría aceptar el paso `at` de un compañero `who`: { target, skip, keep, keeps } o nil y el
-- código de respuesta. Se quedan pendientes (keeps[i] = true) los pasos que él no tiene (los de tu
-- clase) y los de coger una misión que aún no tienes y que la guía usa desde su paso en adelante: sin
-- cogerla no podrías hacer su paso.
function Party.SyncOffer(at, who)
  local E, Cond = Senda.Engine, Senda.Conditions
  if not (at and E:GuideId()) then return nil, "x" end
  local steps = E:Steps()
  local t
  for i, e in ipairs(steps) do
    if e.step.id == at.key then t = i; break end
  end
  if not t then return nil, "x" end
  local cur = E:Index()
  if t == cur then return nil, "=" end
  if t < cur then return nil, "p" end
  local later = {}
  for i = t, #steps do
    for _, q in ipairs(Cond:Quests(steps[i].step) or {}) do later[q] = true end
  end
  local skip, keep, keeps = 0, 0, {}
  for i = cur, t - 1 do
    local e = steps[i]
    if not E:IsMarked(e) then
      local s, needed = e.step, false
      if s["do"] == "accept" then
        for _, q in ipairs(Cond:Quests(s) or {}) do
          if later[q] and not E:QuestTaken(q) then needed = true end
        end
      end
      if needed or not ForPartner(e, who) then
        keep, keeps[i] = keep + 1, true
      else
        skip = skip + 1
      end
    end
  end
  if skip == 0 then return nil, "=" end
  return { target = t, skip = skip, keep = keep, keeps = keeps }
end

local function showPrompt(text, req)
  if not (StaticPopupDialogs and StaticPopup_Show) then return false end
  StaticPopupDialogs[SYNC_POPUP] = StaticPopupDialogs[SYNC_POPUP] or {
    text = "%s",
    button1 = L.DUO_SYNC_ACCEPT,
    button2 = L.DUO_SYNC_DECLINE,
    OnAccept = function(_, data) Party.AcceptSync(data) end,
    OnCancel = function(_, data, reason) if reason ~= "override" then Party.DeclineSync(data) end end,
    timeout = 0,
    whileDead = true,
    hideOnEscape = true,
    preferredIndex = 3,
  }
  StaticPopup_Show(SYNC_POPUP, text, nil, req)
  return true
end

local function onSyncRequest(key, name, at)
  local t = now()
  local last = sync.heardAt[key]
  if last and t - last < SYNC_GAP then return end
  sync.heardAt[key] = t
  local who = Party.Who(members[key])
  local offer, code = Party.SyncOffer(at, who)
  if not offer then
    answer(code)
    if code == "x" then Senda:Print(L.DUO_SYNC_CANT_ME, name)
    elseif code == "p" then Senda:Print(L.DUO_SYNC_PAST_ME, name) end
    return
  end
  local req = { key = key, name = name, at = at, who = who }
  sync.pending = req
  local step = Senda.Engine:Entry(offer.target).step
  local title = Senda.HUD and Senda.HUD.StepTitle and Senda.HUD:StepTitle(step) or ""
  local label = Senda.HUD and Senda.HUD.TypeLabel and Senda.HUD:TypeLabel(step) or ""
  local what = title ~= "" and (label .. ": " .. title) or (Senda.HUD and Senda.HUD:StepText(step) or step.id)
  local text = string.format(offer.skip == 1 and L.DUO_SYNC_PROMPT_1 or L.DUO_SYNC_PROMPT, name, what, offer.skip)
  if offer.keep > 0 then text = text .. "\n" .. string.format(L.DUO_SYNC_PROMPT_KEEP, offer.keep) end
  if not showPrompt(text, req) then
    sync.pending = nil
    answer("n")
  end
end

-- Aceptada: se saltan los pasos hasta el suyo, salvo los que él no tiene (los de tu clase), que se
-- quedan pendientes. Responde "y". True si se movió.
function Party.AcceptSync(req)
  req = req or sync.pending
  if not req or req ~= sync.pending then return false end
  sync.pending = nil
  local E = Senda.Engine
  local offer, code = Party.SyncOffer(req.at, req.who)
  if not offer then
    answer(code or "x")
    return false
  end
  local steps = E:Steps()
  for i = E:Index(), offer.target - 1 do
    local e = steps[i]
    if not E:IsMarked(e) and not offer.keeps[i] then E:Mark(e, "s") end
  end
  E.held = nil
  E:MoveTo(E:NextPending(E:Index()))
  E:RequestEvaluate(0.1, "sync")
  answer("y")
  Senda:Print(L.DUO_SYNC_DONE_ME, req.name)
  return true
end

function Party.DeclineSync(req)
  req = req or sync.pending
  if not req or req ~= sync.pending then return false end
  sync.pending = nil
  answer("n")
  return true
end

local ANSWER_TEXT = { y = "DUO_SYNC_YES", n = "DUO_SYNC_NO", x = "DUO_SYNC_CANT", ["="] = "DUO_SYNC_SAME", p = "DUO_SYNC_PAST" }
local function onSyncAnswer(key, name, code)
  local at = sync.asked[key]
  if not at or now() - at > ANSWER_WINDOW then return end
  sync.asked[key] = nil
  Senda:Print(L[ANSWER_TEXT[code]], name)
end

-- Pide al grupo que salte a tu paso. Una vez cada SYNC_GAP s. True si salió.
function Party.RequestSync()
  if not sharing() then
    Senda:Print(L.DUO_SYNC_NOBODY)
    return false
  end
  local pos = Party.MyPos()
  local text = pos and pos.key and Party.EncodeAt(pos, true)
  if not text then
    Senda:Print(L.DUO_SYNC_NOSTEP)
    return false
  end
  local t = now()
  if sync.askedAt and t - sync.askedAt < SYNC_GAP then
    Senda:Print(L.DUO_SYNC_WAIT, math.ceil(SYNC_GAP - (t - sync.askedAt)))
    return false
  end
  sync.askedAt = t
  for key in pairs(spoken) do sync.asked[key] = t end
  queue("G", text)
  Senda:Print(L.DUO_SYNC_ASKED)
  return true
end

------------------------------------------------------------------------------
-- Recepción
------------------------------------------------------------------------------

local function logHeard(sender, text)
  local log = diag.log
  log[#log + 1] = (sender:match("^([^%-]+)") or sender) .. ": " .. text:sub(1, 48)
  if #log > HEARD_LOG then table.remove(log, 1) end
end

local function onAddonMessage(_, prefix, text, channel, sender)
  if Compat.IsSecret(prefix) or Compat.IsSecret(text) or Compat.IsSecret(channel) or Compat.IsSecret(sender) then return end
  if prefix ~= Party.PREFIX or type(text) ~= "string" or type(sender) ~= "string" then return end
  diag.heard = diag.heard + 1
  logHeard(sender, text)
  if channel ~= "PARTY" or not grouped() or not Opt("duoSync") then return end
  local key, _, short = matchSender(sender)
  if key == "me" then return end
  if not key then
    readRoster()
    key, _, short = matchSender(sender)
    if not key or key == "me" then return end
  end
  if not roster[key] then return end
  diag.matched = diag.matched + 1

  if Party.DecodeHello(text) then
    heard(key, short, true)
    scheduleSnapshot(true)
    return
  end
  local pos = Party.DecodePos(text)
  if pos then
    heard(key, short, false)
    memberFor(key, short).pos = pos
    return
  end
  local at, request = Party.DecodeAt(text)
  if at then
    heard(key, short, false)
    if request then return onSyncRequest(key, short, at) end
    memberFor(key, short).at = at
    changed()
    return
  end
  local code = Party.DecodeAnswer(text)
  if code then
    heard(key, short, false)
    return onSyncAnswer(key, short, code)
  end
  local done = Party.DecodeDone(text)
  if done then
    heard(key, short, false)
    memberFor(key, short).done = done
    changed()
    return
  end
  local skipped = Party.DecodeSkipped(text)
  if skipped then
    heard(key, short, false)
    memberFor(key, short).skipped = skipped
    changed()
    return
  end
  local u = Party.DecodeUnit(text)
  if u then
    heard(key, short, false)
    memberFor(key, short).unit = u
    changed()
    return
  end
  local snap, entries, asks = Party.Decode(text)
  if snap == nil then return end
  heard(key, short, asks)
  if asks and sharing() and not snapPending and not (lastSnapshotAt and now() - lastSnapshotAt < REPLY_GAP) then
    scheduleSnapshot(false)
  end
  apply(memberFor(key, short), entries, snap)
  changed()
end

------------------------------------------------------------------------------
-- /senda pareja
------------------------------------------------------------------------------

local function yn(v) return v and L.DUO_YES or L.DUO_NO end

function Party.Debug()
  local out = {}
  local function add(fmt, ...) out[#out + 1] = string.format(fmt, ...) end
  local reg = C_ChatInfo and C_ChatInfo.IsAddonMessagePrefixRegistered and Compat.Try(C_ChatInfo.IsAddonMessagePrefixRegistered, Party.PREFIX)
  add(L.DUO_DEBUG_PREFIX, Party.PREFIX, yn(reg), tostring(diag.prefixResult))
  add(L.DUO_DEBUG_GROUP, yn(grouped()), yn(IsInRaid and IsInRaid()), yn(Opt("duoSync")), yn(Opt("duoWait")))
  add(L.DUO_DEBUG_SENT, diag.sends, diag.refused, diag.dropped, #outbox, tostring(diag.lastSend), tostring(diag.lastResult))
  add(L.DUO_DEBUG_HEARD, diag.heard, diag.matched)
  local n = Compat.Num(Compat.Try(GetNumSubgroupMembers)) or 0
  for i = 1, math.min(n, 4) do
    local key, short = unitKey("party" .. i)
    add(L.DUO_DEBUG_MEMBER, i, key == false and "?" or tostring(short), yn(key and spoken[key]),
      key and members[key] and members[key].n or 0)
  end
  for _, line in ipairs(diag.log) do add(L.DUO_DEBUG_LINE, line) end
  return out
end
function Party.Diag() return diag end

local function Status()
  if not grouped() then
    Senda:Print((IsInRaid and IsInRaid()) and L.DUO_STATUS_RAID or L.DUO_STATUS_SOLO)
    return
  end
  local list = Party.Members()
  if #list == 0 then
    Senda:Print(L.DUO_STATUS_WAITING)
    return
  end
  for _, m in ipairs(list) do
    Senda:Print("%s", Party.Relation(m) or m.name)
  end
  local hold = Party.HoldLine()
  if hold then Senda:Print("%s", hold) end
end

local function SlashCmd(rest, args)
  local sub = (args[2] or ""):lower()
  if sub == "debug" then
    for _, line in ipairs(Party.Debug()) do Senda:Print("%s", line) end
  elseif sub == "saltar" or sub == "sync" then
    Party.RequestSync()
  elseif sub == "seguir" or sub == "goon" then
    Party.GoOn()
    Senda:Print(L.DUO_GONE_ON)
  elseif sub == "" then
    Status()
  else
    Senda:Print(L.DUO_SLASH_USAGE)
  end
end

------------------------------------------------------------------------------
-- Arranque y eventos
------------------------------------------------------------------------------

local SEC = L.OPT_SECTION_DUO
Senda.Options:Register({ key = "duoSync", label = L.OPT_DUO_SYNC, tooltip = L.OPT_DUO_SYNC_TIP, type = "toggle",
  default = true, section = SEC, order = 1, onChange = function(v)
    if v then
      readRoster()
      if grouped() then scheduleHello() end
    else
      forgetAll()
    end
  end })
Senda.Options:Register({ key = "duoWait", label = L.OPT_DUO_WAIT, tooltip = L.OPT_DUO_WAIT_TIP, type = "toggle",
  default = true, section = SEC, order = 2, onChange = function() changed() end })

if Senda.Slash and Senda.Slash.Register then
  Senda.Slash:Register("pareja", SlashCmd, L.DUO_SLASH_HELP)
end

Events:On("SENDA_READY", function()
  if C_ChatInfo and C_ChatInfo.RegisterAddonMessagePrefix then
    diag.prefixResult = Compat.Try(C_ChatInfo.RegisterAddonMessagePrefix, Party.PREFIX)
  end
  Events:On("CHAT_MSG_ADDON", onAddonMessage)
  Events:On("GROUP_ROSTER_UPDATE", readRoster)
  Events:On("GROUP_LEFT", forgetAll)
  Events:On("UNIT_CONNECTION", function(_, unit)
    if type(unit) == "string" and unit:match("^party%d$") then readRoster() end
  end)
  Events:On("QUEST_LOG_UPDATE", onLog)
  Events:On("PLAYER_LEVEL_UP", onLevel)
  Events:On("SENDA_STEP_CHANGED", onStep)
  Events:On("SENDA_GUIDE_CHANGED", onStep)
  Events:On("SENDA_SKIPPED", onStep)
  Events:On("SENDA_GUIDES_UPDATED", function() fullCache = {} end)
  Events:On("PLAYER_REGEN_ENABLED", function()
    if not combatOwed then return end
    combatOwed = false
    if pendingAsks or not lastSnapshotAt then scheduleSnapshot(pendingAsks) else onLog() end
  end)
  readRoster()
end)

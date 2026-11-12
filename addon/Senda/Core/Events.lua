-- Bus de eventos: eventos reales de WoW y eventos internos ("SENDA_*") con varios suscriptores.
--   Senda.Events:On(event, fn)   -> fn(event, ...)
--   Senda.Events:Off(event, fn)
--   Senda.Events:Fire(name, ...)
-- Los errores de un suscriptor no impiden que se ejecuten los demás (se envían al manejador de errores).
-- Registro de errores: Senda.Errors:Add(err) guarda los últimos 20 errores de Lua que Senda captura (sin rutas ni
-- el nombre del personaje ni del reino) para la ventana de informe (UI/Report.lua); Senda:ReportError(err) los
-- guarda y los pasa al manejador de errores del juego.
local _, Senda = ...

local Errors = { list = {}, max = 20, maxLen = 400 }
Senda.Errors = Errors

local function Scrub(msg)
  msg = tostring(msg or "?")
  msg = msg:gsub("[Ii]nterface[\\/][Aa]dd[Oo]ns[\\/]", "")
  local function hide(value, label)
    if type(value) == "string" and #value >= 2 then
      msg = msg:gsub((value:gsub("%p", "%%%0")), label)
    end
  end
  if UnitName then hide((UnitName("player")), "<pj>") end
  if GetRealmName then hide(GetRealmName(), "<reino>") end
  if #msg > Errors.maxLen then msg = msg:sub(1, Errors.maxLen) .. "…" end
  return msg
end

function Errors:Add(err)
  local ok, msg = pcall(Scrub, err)
  if not ok then msg = "?" end
  local last = self.list[#self.list]
  if last and last.msg == msg then
    last.n = last.n + 1
    return
  end
  self.list[#self.list + 1] = { msg = msg, n = 1 }
  while #self.list > self.max do table.remove(self.list, 1) end
end

function Errors:Count() return #self.list end

function Senda:ReportError(err)
  Errors:Add(err)
  local h = geterrorhandler and geterrorhandler()
  if h then h(err) else Senda:Print(tostring(err)) end
end

local Events = {}
Senda.Events = Events

local handlers = {}      -- event -> { fn, fn, ... }
local registered = {}    -- eventos de WoW ya registrados en el marco
local frame = CreateFrame("Frame", "SendaEventFrame")

local function IsInternal(event)
  return type(event) == "string" and event:sub(1, 6) == "SENDA_"
end

local function Report(err) Senda:ReportError(err) end

local function Dispatch(event, ...)
  local list = handlers[event]
  if not list then return end
  -- Se recorre una copia por si un suscriptor se da de baja durante el envío.
  local n = #list
  if n == 0 then return end
  local snapshot = { unpack(list, 1, n) }
  for i = 1, n do
    local ok, err = pcall(snapshot[i], event, ...)
    if not ok then Report(err) end
  end
end

frame:SetScript("OnEvent", function(_, event, ...) Dispatch(event, ...) end)

-- Suscribe fn a event. Devuelve true si el evento existe (o es interno).
function Events:On(event, fn)
  if type(event) ~= "string" or type(fn) ~= "function" then return false end
  local list = handlers[event]
  if not list then list = {}; handlers[event] = list end
  for _, f in ipairs(list) do
    if f == fn then return true end
  end
  list[#list + 1] = fn
  if not IsInternal(event) and not registered[event] then
    -- RegisterEvent lanza error si el evento no existe en este cliente: lo toleramos.
    local ok = pcall(frame.RegisterEvent, frame, event)
    registered[event] = ok and true or "missing"
    if not ok then Senda:Debug("Evento no disponible: %s", event) end
    return ok
  end
  return registered[event] ~= "missing"
end

function Events:Off(event, fn)
  local list = handlers[event]
  if not list then return end
  for i = #list, 1, -1 do
    if list[i] == fn then table.remove(list, i) end
  end
  if #list == 0 and registered[event] == true then
    pcall(frame.UnregisterEvent, frame, event)
    registered[event] = nil
  end
end

-- Lanza un evento (normalmente interno) a sus suscriptores.
function Events:Fire(event, ...)
  Dispatch(event, ...)
end

-- ¿Está disponible este evento de WoW en el cliente?
function Events:IsAvailable(event)
  return registered[event] == true
end

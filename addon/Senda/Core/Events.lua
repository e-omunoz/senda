-- Bus de eventos: eventos reales de WoW y eventos internos ("SENDA_*") con varios suscriptores.
--   Senda.Events:On(event, fn)   -> fn(event, ...)
--   Senda.Events:Off(event, fn)
--   Senda.Events:Fire(name, ...)
-- Los errores de un suscriptor no impiden que se ejecuten los demás (se envían al manejador de errores).
local _, Senda = ...

local Events = {}
Senda.Events = Events

local handlers = {}      -- event -> { fn, fn, ... }
local registered = {}    -- eventos de WoW ya registrados en el marco
local frame = CreateFrame("Frame", "SendaEventFrame")

local function IsInternal(event)
  return type(event) == "string" and event:sub(1, 6) == "SENDA_"
end

local function Report(err)
  local h = geterrorhandler and geterrorhandler()
  if h then h(err) else Senda:Print(tostring(err)) end
end

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

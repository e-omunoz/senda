-- Senda: espacio de nombres y utilidades básicas.
-- Todo el addon vive en la tabla compartida (local ADDON, Senda = ...). Se expone como _G.Senda
-- solo para depurar (/dump Senda.db) y para que otros addons puedan consultar el estado.
local ADDON, Senda = ...

_G.Senda = Senda
Senda.ADDON = ADDON

-- Versión: desde el .toc (C_AddOns moderno, con reserva a la global clásica).
do
  local v
  local getMeta = (C_AddOns and C_AddOns.GetAddOnMetadata) or _G.GetAddOnMetadata
  if getMeta then
    local ok, r = pcall(getMeta, ADDON, "Version")
    if ok and type(r) == "string" and r ~= "" and not r:find("@", 1, true) then v = r end
  end
  Senda.VERSION = v or "0.1.0"
end

Senda.WEB = "https://e-omunoz.github.io/senda/"

-- Colores de marca (r, g, b) usados por el chat y la UI.
Senda.COLOR = { 0.30, 0.82, 0.66 }
Senda.COLOR_HEX = "ff4dd1a8"

local PREFIX = "|c" .. Senda.COLOR_HEX .. "Senda|r: "

-- Mensaje con prefijo en el chat.
function Senda:Print(msg, ...)
  if select("#", ...) > 0 then msg = string.format(tostring(msg), ...) end
  local frame = DEFAULT_CHAT_FRAME or ChatFrame1
  if frame then frame:AddMessage(PREFIX .. tostring(msg)) end
end

-- Mensaje de depuración: solo si db.opts.debug está activo.
function Senda:Debug(msg, ...)
  local db = self.db
  if not (db and db.opts and db.opts.debug) then return end
  if select("#", ...) > 0 then
    local ok, r = pcall(string.format, tostring(msg), ...)
    msg = ok and r or tostring(msg)
  end
  local frame = DEFAULT_CHAT_FRAME or ChatFrame1
  if frame then frame:AddMessage("|cff888888Senda[dbg]:|r " .. tostring(msg)) end
end

-- Utilidades genéricas -------------------------------------------------------

Senda.Util = Senda.Util or {}
local Util = Senda.Util

-- Copia superficial.
function Util.Copy(t)
  local r = {}
  for k, v in pairs(t) do r[k] = v end
  return r
end

-- Copia profunda (sin ciclos).
function Util.DeepCopy(t)
  if type(t) ~= "table" then return t end
  local r = {}
  for k, v in pairs(t) do r[k] = Util.DeepCopy(v) end
  return r
end

-- Rellena en `dst` las claves que falten con los valores de `defaults` (recursivo).
function Util.Merge(dst, defaults)
  for k, v in pairs(defaults) do
    if dst[k] == nil then
      dst[k] = Util.DeepCopy(v)
    elseif type(v) == "table" and type(dst[k]) == "table" then
      Util.Merge(dst[k], v)
    end
  end
  return dst
end

-- ¿Contiene la lista el valor? (lista nil = "sin restricción" -> true).
function Util.Contains(list, value)
  if type(list) ~= "table" then return list == value end
  for _, v in ipairs(list) do
    if v == value then return true end
  end
  return false
end

function Util.Round(n, step)
  step = step or 1
  return math.floor(n / step + 0.5) * step
end

function Util.Clamp(n, lo, hi)
  if n < lo then return lo elseif n > hi then return hi end
  return n
end

-- "1:23" o "45 s".
function Util.FormatTime(sec)
  if not sec or sec ~= sec or sec == math.huge then return "?" end
  sec = math.floor(sec + 0.5)
  if sec < 60 then return sec .. " s" end
  if sec < 3600 then return string.format("%d:%02d", math.floor(sec / 60), sec % 60) end
  return string.format("%d:%02d:%02d", math.floor(sec / 3600), math.floor(sec / 60) % 60, sec % 60)
end

-- Divide una cadena por espacios respetando "texto entre comillas".
function Util.Args(s)
  local out = {}
  s = s or ""
  local i = 1
  while i <= #s do
    local c = s:sub(i, i)
    if c == '"' then
      local j = s:find('"', i + 1, true) or (#s + 1)
      out[#out + 1] = s:sub(i + 1, j - 1)
      i = j + 1
    elseif c:match("%s") then
      i = i + 1
    else
      local j = s:find("%s", i) or (#s + 1)
      out[#out + 1] = s:sub(i, j - 1)
      i = j
    end
  end
  return out
end

-- Registro de opciones (la pestaña "Opciones" de la UI las pinta automáticamente).
--   Senda.Options:Register({ key, label, type = "toggle"|"slider", default, min, max, step,
--                            onChange = function(value) end, section, order, tooltip, format })
--   Senda.Options:Get(key), :Set(key, value), :List()
-- Los valores viven en SendaDB.opts. Se puede registrar antes de que exista la base de datos.
local _, Senda = ...

local Options = {}
Senda.Options = Options

local registry, byKey = {}, {}
local seq = 0

function Options:Register(opt)
  if type(opt) ~= "table" or type(opt.key) ~= "string" then return end
  if byKey[opt.key] then
    -- Re-registro: se actualiza la definición existente.
    for k, v in pairs(opt) do byKey[opt.key][k] = v end
    return
  end
  seq = seq + 1
  opt.seq = seq
  opt.type = opt.type or "toggle"
  registry[#registry + 1] = opt
  byKey[opt.key] = opt
  if Senda.db and Senda.db.opts[opt.key] == nil and opt.default ~= nil then
    Senda.db.opts[opt.key] = opt.default
  end
  if Senda.ready then Senda.Events:Fire("SENDA_OPTIONS_UPDATED", opt.key) end
end

function Options:ApplyDefaults()
  local opts = Senda.db and Senda.db.opts
  if not opts then return end
  for _, o in ipairs(registry) do
    if opts[o.key] == nil and o.default ~= nil then opts[o.key] = o.default end
  end
end

function Options:Get(key)
  local opts = Senda.db and Senda.db.opts
  local v = opts and opts[key]
  if v == nil and byKey[key] then v = byKey[key].default end
  return v
end

function Options:Set(key, value)
  if not (Senda.db and Senda.db.opts) then return end
  Senda.db.opts[key] = value
  local o = byKey[key]
  if o and o.onChange then
    local ok, err = pcall(o.onChange, value)
    if not ok then Senda:Debug("onChange %s: %s", key, tostring(err)) end
  end
  Senda.Events:Fire("SENDA_OPTION_CHANGED", key, value)
end

function Options:Definition(key) return byKey[key] end

-- Opciones ordenadas por sección (orden de aparición de la sección) y por `order`.
function Options:List()
  local secOrder, n = {}, 0
  for _, o in ipairs(registry) do
    local s = o.section or ""
    if not secOrder[s] then n = n + 1; secOrder[s] = o.sectionOrder or n * 10 end
  end
  local out = {}
  for i, o in ipairs(registry) do out[i] = o end
  table.sort(out, function(a, b)
    local sa, sb = secOrder[a.section or ""], secOrder[b.section or ""]
    if sa ~= sb then return sa < sb end
    local oa, ob = a.order or 100, b.order or 100
    if oa ~= ob then return oa < ob end
    return a.seq < b.seq
  end)
  return out
end

-- Opciones del núcleo.
local L = Senda.L
Options:Register({ key = "debug", label = L.OPT_DEBUG, type = "toggle", default = false,
  section = L.OPT_SECTION_GENERAL, order = 99 })
Options:Register({ key = "skipOptional", label = L.OPT_SKIP_OPTIONAL, tooltip = L.OPT_SKIP_OPTIONAL_TIP,
  type = "toggle", default = false, section = L.OPT_SECTION_GENERAL, order = 20,
  onChange = function() if Senda.Engine then Senda.Engine:RequestEvaluate(0.1, "opt") end end })

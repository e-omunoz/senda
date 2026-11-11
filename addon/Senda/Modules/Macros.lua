-- Senda / Modules / Macros
-- Crea y actualiza macros a partir del conocimiento kind = "macros" ([[macro]] name, icon, minlevel, body, note).
-- Solo toca macros con el prefijo SND_: nunca sobrescribe las del jugador. Nada en combate.
--
-- Marcadores en body:
--   {123}      nombre del hechizo 123 en tu idioma (la macro espera a que lo conozcas)
--   {?123}     igual, pero sin exigir que lo conozcas (hechizos de mascota)
--   {n:Nombre} hechizo por nombre (vale si está en tu libro)
--   {hs}       id de la mejor Piedra de salud que lleves (se actualiza sola al cambiar las bolsas)
local ADDON, Senda = ...
local M = Senda.Mod
if not M then return end
local L = M.L

local MC = {}
Senda.Modules.Macros = MC

local PREFIX = "SND_"
local MAX_NAME, MAX_BODY = 16, 255
local DEFAULT_ICON = "INV_MISC_QUESTIONMARK"
-- Piedras de salud (de peor a mejor), datos del juego.
local HEALTHSTONES = { 5512, 19004, 19005, 5511, 19006, 19007, 5509, 19008, 19009, 5510, 19010, 19011, 9421, 19012, 19013 }

function MC.ManagedName(name)
  name = tostring(name or "")
  if name:sub(1, #PREFIX) ~= PREFIX then name = PREFIX .. name end
  return name:sub(1, MAX_NAME)
end

function MC.IsManaged(name) return type(name) == "string" and name:sub(1, #PREFIX) == PREFIX end

function MC.Index(name)
  if not GetMacroIndexByName then return nil end
  local ok, idx = pcall(GetMacroIndexByName, MC.ManagedName(name))
  if ok and idx and idx > 0 then return idx end
  return nil
end

function MC.BestHealthstone()
  for i = #HEALTHSTONES, 1, -1 do
    if M.ItemCount(HEALTHSTONES[i]) > 0 then return HEALTHSTONES[i] end
  end
  return nil
end
MC.HEALTHSTONES = HEALTHSTONES

local function ResolveBody(text)
  local ok = true
  local body = tostring(text or "")
  body = body:gsub("{hs}", function() return tostring(MC.BestHealthstone() or HEALTHSTONES[1]) end)
  body = body:gsub("{(%??)(%d+)}", function(opt, id)
    id = tonumber(id)
    local name = M.SpellName(id)
    if not name then ok = false; return "" end
    if opt ~= "?" and not M.Known(id) then ok = false end
    return name
  end)
  body = body:gsub("{n:([^}]+)}", function(name)
    if not M.InBook(name) then ok = false end
    return name
  end)
  if not ok then return nil, "spell" end
  if #body > MAX_BODY then return nil, "long" end
  return body
end

-- Cuerpo resuelto o nil, motivo ("level" | "spell" | "long"). Si `body` no se puede resolver, se prueban las
-- `fallbacks` del conocimiento en orden (p. ej. Inmolar en lugar de Terror de agonía antes del nivel 8).
function MC.Resolve(m, level)
  level = level or M.Level()
  if m.minlevel and level < m.minlevel then return nil, "level" end
  local body, why = ResolveBody(m.body)
  if not body and type(m.fallbacks) == "table" then
    for _, fb in ipairs(m.fallbacks) do
      local alt = ResolveBody(fb)
      if alt then return alt end
    end
  end
  return body, why
end

-- Icono: id de hechizo, "spell:<id>", "item:<id>", "name:<hechizo>" (formato del conocimiento) o nombre de icono.
local function IconFor(m)
  local i = m.icon
  if type(i) == "number" then return M.SpellIcon(i) or DEFAULT_ICON end
  if type(i) == "string" and i ~= "" then
    local kind, ref = i:match("^(%a+):(.+)$")
    if kind == "spell" then return M.SpellIcon(tonumber(ref)) or DEFAULT_ICON end
    if kind == "item" then return M.ItemIcon(tonumber(ref)) or DEFAULT_ICON end
    if kind == "name" then return M.SpellIcon(ref) or DEFAULT_ICON end
    return (i:gsub("^[Ii]nterface\\[Ii]cons\\", ""))
  end
  return DEFAULT_ICON
end
MC.IconFor = IconFor

-- Icono con el que se guarda la macro en el juego. Si el cuerpo empieza por #showtooltip, la macro debe
-- llevar el icono de interrogación (134400): solo así el juego pone el icono del hechizo que se lanzaría
-- en cada momento (cambia con [mod:alt], [@mouseover], etc.). Con un icono fijo, ese icono no cambia nunca.
local DYNAMIC_ICON = 134400 -- INV_Misc_QuestionMark
local function GameIcon(m, body)
  if type(body) == "string" and body:match("^%s*#show") then return DYNAMIC_ICON end
  return IconFor(m)
end
MC.GameIcon = GameIcon

-- Todas las macros del conocimiento, con su estado.
function MC.List()
  local out, level = {}, M.Level()
  for _, p in ipairs(M.Pages("macros")) do
    for _, m in ipairs(p.macro or {}) do
      if type(m) == "table" and m.name and m.body then
        local body, why = MC.Resolve(m, level)
        table.insert(out, { m = m, name = MC.ManagedName(m.name), body = body, why = why,
          idx = MC.Index(m.name), status = m.status or p.status, icon = IconFor(m), gameIcon = GameIcon(m, body) })
      end
    end
  end
  return out
end

local function Space(perChar)
  if not GetNumMacros then return true end
  local ok, nAcc, nChar = pcall(GetNumMacros)
  if not ok then return true end
  if perChar then return (nChar or 0) < (MAX_CHARACTER_MACROS or 18) end
  return (nAcc or 0) < (MAX_ACCOUNT_MACROS or 120)
end

local function Apply(e, allowCreate)
  if e.idx then
    if not MC.IsManaged(e.name) then return "skip" end
    local okI, _, curIcon, current = pcall(GetMacroInfo, e.idx)
    -- También se reescribe si tenía un icono fijo y ahora debe ser dinámico (macros creadas antes de 0.3.3).
    if okI and current == e.body and (e.gameIcon ~= DYNAMIC_ICON or curIcon == DYNAMIC_ICON) then return "same" end
    local ok = pcall(EditMacro, e.idx, e.name, e.gameIcon or e.icon, e.body)
    return ok and "updated" or "fail"
  end
  if not allowCreate then return "skip" end
  local perChar = M.Opt("mod_macro_char") ~= false
  if not Space(perChar) then return "full" end
  local ok = pcall(CreateMacro, e.name, e.gameIcon or e.icon, e.body, perChar)
  return ok and "made" or "fail"
end

-- Crea las que falten y actualiza las existentes (solo fuera de combate).
function MC.CreateAll(quiet)
  if M.InCombat() then M.Print(L.MOD_MACRO_COMBAT or "No se pueden crear macros en combate."); return end
  if not (CreateMacro and EditMacro) then return end
  local made, updated, pendingN, full = 0, 0, 0, 0
  for _, e in ipairs(MC.List()) do
    if e.body then
      local r = Apply(e, true)
      if r == "made" then made = made + 1 elseif r == "updated" then updated = updated + 1 elseif r == "full" then full = full + 1 end
    else
      pendingN = pendingN + 1
    end
  end
  if not quiet then
    M.Print(string.format(L.MOD_MACRO_DONE or "Macros: %d creadas, %d actualizadas, %d pendientes (nivel o hechizo que aún no tienes).", made, updated, pendingN))
    if full > 0 then M.Print(L.MOD_MACRO_FULL or "No queda sitio para más macros: borra alguna en /macro.") end
  end
  MC.Refresh()
end

-- Actualiza solo las macros SND_ ya creadas (nuevos rangos, piedra de salud...).
local dirty = false
function MC.UpdateExisting()
  if M.InCombat() then dirty = true; return end
  dirty = false
  if not (EditMacro and GetMacroInfo) or M.Opt("mod_macro_auto") == false then return end
  for _, e in ipairs(MC.List()) do
    if e.idx and e.body then Apply(e, false) end
  end
end

------------------------------------------------------------------------
-- Pestaña
------------------------------------------------------------------------
local ui = {}

function MC.Refresh()
  if not ui.doc then return end
  local list = MC.List()
  local nodes = {}
  table.insert(nodes, { t = "p", text = L.MOD_MACRO_HELP or "Pulsa «Crear o actualizar» y arrastra cada macro a tus barras (clic en la fila, fuera de combate). Se actualizan solas al subir de nivel. Solo se tocan las macros que empiezan por SND_." })
  if #list == 0 then
    table.insert(nodes, { t = "p", text = L.MOD_NO_MACROS or "Todavía no hay macros para tu clase." })
  end
  local level = M.Level()
  for _, e in ipairs(list) do
    local state, hl
    if e.why == "level" then state, hl = string.format(L.MOD_AT_LEVEL or "nivel %d", e.m.minlevel or 0), "dim"
    elseif e.why == "spell" then state, hl = "|cffff8040" .. (L.MOD_MACRO_NOSPELL or "falta el hechizo") .. "|r", "dim"
    elseif e.why == "long" then state, hl = "|cffff4040" .. (L.MOD_MACRO_LONG or "demasiado larga") .. "|r", "warn"
    elseif e.idx then state = "|cff7cc66f" .. (L.MOD_MACRO_MADE or "creada") .. "|r"
    else state, hl = "|cffffd100" .. (L.MOD_MACRO_READY or "lista para crear") .. "|r", "now" end
    local text = "|cffffffff" .. e.name .. "|r" .. M.StatusTag(e.status)
    if e.m.note then text = text .. "\n" .. e.m.note end
    local preview = (e.body or e.m.body or ""):gsub("\n", " | ")
    text = text .. "\n|cff777777" .. preview .. "|r"
    local icon = e.icon
    if type(icon) == "string" and not icon:find("\\", 1, true) then icon = "Interface\\Icons\\" .. icon end
    table.insert(nodes, { t = "row", raw = true, text = text, right = state, hl = hl, icon = icon,
      desat = e.body == nil or (e.m.minlevel or 1) > level,
      tip = e.idx and (L.MOD_MACRO_DRAG or "Clic: coge la macro para ponerla en una barra.") or nil,
      onClick = function()
        local idx = MC.Index(e.m.name)
        if idx and PickupMacro and not M.InCombat() then PickupMacro(idx) end
      end })
  end
  ui.doc:Set(nodes, true)
end

local function Build(parent)
  local bar, body = M.Toolbar(parent)
  local b = M.Button(bar, L.MOD_MACRO_CREATE or "Crear o actualizar macros", 200, function() MC.CreateAll() end)
  b:SetPoint("LEFT", 6, 0)
  local cb = M.Check(bar, L.MOD_MACRO_CHAR or "Del personaje (si no, de la cuenta)",
    function() return M.Opt("mod_macro_char") ~= false end,
    function(v) M.SetOpt("mod_macro_char", v) end)
  cb:SetPoint("LEFT", b, "RIGHT", 10, 0)
  ui.doc = M.Doc(body)
end

M.RegisterTab({ key = "macros", title = L.MOD_TAB_MACROS or "Macros", icon = "Interface\\Icons\\INV_Scroll_03",
  order = 50, build = Build, refresh = MC.Refresh })
M.RegisterOption({ key = "mod_macro_auto", label = L.MOD_OPT_MACRO_AUTO or "Actualizar solas las macros SND_ (rangos nuevos, piedra de salud)",
  type = "toggle", default = true })
M.RegisterOption({ key = "mod_macro_char", label = L.MOD_OPT_MACRO_CHAR or "Crear las macros en la pestaña del personaje",
  type = "toggle", default = true })

local function Soon() M.Debounce("macros-update", 1, MC.UpdateExisting) end
M.On("PLAYER_LEVEL_UP", function(_, level)
  Soon()
  level = tonumber(level)
  if level and M.Opt("mod_levelmsg") ~= false then
    for _, e in ipairs(MC.List()) do
      if e.m.minlevel == level then
        M.Print("|cffffd100" .. (L.MOD_MACRO_NEW or "Macro nueva disponible:") .. "|r " .. e.name .. " (" .. (L.MOD_TAB_MACROS or "Macros") .. ")")
      end
    end
  end
end)
M.On("SPELLS_CHANGED", Soon)
M.On("BAG_UPDATE_DELAYED", Soon)
M.On("PLAYER_REGEN_ENABLED", function() if dirty then Soon() end end)
M.OnReady(Soon)

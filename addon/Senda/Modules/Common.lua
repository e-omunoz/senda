-- Senda / Modules / Common
-- Utilidades compartidas por los módulos portados (Senda.Mod). Todo lo que toca al núcleo
-- (Compat, UI, Options, Knowledge, Events) se llama con comprobación de existencia y pcall,
-- para que un módulo nunca rompa el addon si falta algo.
local ADDON, Senda = ...

local M = {}
Senda.Mod = M
Senda.Modules = Senda.Modules or {}   -- API pública de cada módulo: Senda.Modules.Gear, .Professions...

------------------------------------------------------------------------
-- Cadenas: L.CLAVE or "Texto". rawget evita metatablas que devuelvan la propia clave.
------------------------------------------------------------------------
M.L = setmetatable({}, { __index = function(_, k)
  local t = Senda.L
  if type(t) ~= "table" then return nil end
  local v = rawget(t, k)
  if type(v) == "string" then return v end
  return nil
end })
local L = M.L

------------------------------------------------------------------------
-- Chat, depuración
------------------------------------------------------------------------
function M.Print(msg, ...)
  if select("#", ...) > 0 then
    local ok, r = pcall(string.format, tostring(msg), ...)
    msg = ok and r or tostring(msg)
  end
  if Senda.Print then
    Senda:Print(msg)
  elseif DEFAULT_CHAT_FRAME then
    DEFAULT_CHAT_FRAME:AddMessage("|cff4dd1a8Senda|r: " .. tostring(msg))
  end
end

function M.Debug(msg, ...)
  if Senda.Debug then pcall(Senda.Debug, Senda, msg, ...) end
end

-- pcall que informa por depuración y devuelve los valores si va bien.
function M.Try(fn, ...)
  local res = { pcall(fn, ...) }
  if not res[1] then
    M.Debug("Módulo: %s", tostring(res[2]))
    return nil
  end
  return unpack(res, 2, table.maxn(res))
end

function M.StripColors(s)
  s = tostring(s or "")
  s = s:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", "")
  s = s:gsub("|H.-|h(.-)|h", "%1"):gsub("|T.-|t", "")
  return s
end

------------------------------------------------------------------------
-- Eventos
------------------------------------------------------------------------
local ownFrame, ownHandlers
local function OwnOn(event, fn)
  if not ownFrame then
    ownFrame, ownHandlers = CreateFrame("Frame"), {}
    ownFrame:SetScript("OnEvent", function(_, ev, ...)
      for _, f in ipairs(ownHandlers[ev] or {}) do
        local ok, err = pcall(f, ev, ...)
        if not ok then M.Debug("Evento %s: %s", ev, tostring(err)) end
      end
    end)
  end
  ownHandlers[event] = ownHandlers[event] or {}
  table.insert(ownHandlers[event], fn)
  if event:sub(1, 6) ~= "SENDA_" then pcall(ownFrame.RegisterEvent, ownFrame, event) end
end

-- fn(event, ...). Usa el bus del núcleo; si no existe, un marco propio.
function M.On(event, fn)
  if Senda.Events and Senda.Events.On then
    local ok = pcall(Senda.Events.On, Senda.Events, event, fn)
    if ok then return end
  end
  OwnOn(event, fn)
end

function M.Fire(name, ...)
  if Senda.Events and Senda.Events.Fire then pcall(Senda.Events.Fire, Senda.Events, name, ...) end
end

-- Se ejecuta una vez cuando el núcleo está listo (SENDA_READY) o, de reserva, 2 s tras PLAYER_LOGIN.
local readyFns, isReady = {}, false
local function RunReady()
  if isReady then return end
  isReady = true
  for _, fn in ipairs(readyFns) do
    local ok, err = pcall(fn)
    if not ok then M.Debug("Arranque de módulo: %s", tostring(err)) end
  end
end
function M.OnReady(fn)
  if isReady then pcall(fn) else table.insert(readyFns, fn) end
end
function M.IsReady() return isReady end
M.On("SENDA_READY", RunReady)
M.On("PLAYER_LOGIN", function()
  if C_Timer and C_Timer.After then C_Timer.After(2, RunReady) else RunReady() end
end)

function M.After(sec, fn)
  if C_Timer and C_Timer.After then C_Timer.After(sec, function() pcall(fn) end) else pcall(fn) end
end

-- Agrupa llamadas seguidas (p. ej. BAG_UPDATE_DELAYED en ráfaga).
local pending = {}
function M.Debounce(key, sec, fn)
  if pending[key] then return end
  pending[key] = true
  M.After(sec, function() pending[key] = nil; fn() end)
end

function M.InCombat()
  return (InCombatLockdown and InCombatLockdown()) or false
end

------------------------------------------------------------------------
-- Datos guardados y opciones
------------------------------------------------------------------------
local tmpDB = {}
-- Tabla por personaje para los módulos: SendaDB.modules (o temporal si aún no hay db).
function M.DB()
  local db = Senda.db
  if type(db) ~= "table" then return tmpDB end
  db.modules = db.modules or {}
  return db.modules
end

local optDefaults = {}
function M.RegisterOption(def)
  optDefaults[def.key] = def.default
  if Senda.Options and Senda.Options.Register then
    local ok, err = pcall(Senda.Options.Register, Senda.Options, def)
    if not ok then M.Debug("Opción %s: %s", def.key, tostring(err)) end
  end
end

function M.Opt(key)
  if Senda.Options and Senda.Options.Get then
    local ok, v = pcall(Senda.Options.Get, Senda.Options, key)
    if ok and v ~= nil then return v end
  end
  local db = Senda.db
  if type(db) == "table" and type(db.opts) == "table" and db.opts[key] ~= nil then return db.opts[key] end
  return optDefaults[key]
end

function M.SetOpt(key, value)
  if Senda.Options and Senda.Options.Set then
    local ok = pcall(Senda.Options.Set, Senda.Options, key, value)
    if ok then return end
  end
  local db = Senda.db
  if type(db) == "table" then
    db.opts = db.opts or {}
    db.opts[key] = value
  end
end

------------------------------------------------------------------------
-- Jugador
------------------------------------------------------------------------
function M.Level() return (UnitLevel and UnitLevel("player")) or 1 end
function M.Class() local _, c = UnitClass("player"); return c end
function M.Race() local _, r = UnitRace("player"); return r end
function M.Faction() return UnitFactionGroup and UnitFactionGroup("player") end

function M.UnspentTalents()
  if UnitCharacterPoints then
    local ok, n = pcall(UnitCharacterPoints, "player")
    if ok and type(n) == "number" then return n end
  end
  if GetUnspentTalentPoints then
    local ok, n = pcall(GetUnspentTalentPoints)
    if ok and type(n) == "number" then return n end
  end
  return 0
end

function M.Money(c)
  c = math.floor(tonumber(c) or 0)
  if GetCoinTextureString then
    local ok, s = pcall(GetCoinTextureString, c)
    if ok and s then return s end
  end
  local g, s, cp = math.floor(c / 10000), math.floor(c / 100) % 100, c % 100
  if g > 0 then return string.format("%d o %d p", g, s) end
  if s > 0 then return string.format("%d p %d c", s, cp) end
  return cp .. " c"
end

function M.MoneyPlain(c)
  c = math.floor(tonumber(c) or 0)
  local g, s, cp = math.floor(c / 10000), math.floor(c / 100) % 100, c % 100
  if g > 0 then return string.format("%d o %d p", g, s) end
  if s > 0 then return string.format("%d p %d c", s, cp) end
  return cp .. " c"
end

------------------------------------------------------------------------
-- Hechizos (Compat del núcleo primero; si no, la API moderna con reservas)
------------------------------------------------------------------------
local function Compat(name, ...)
  local C = Senda.Compat
  local f = C and C[name]
  if type(f) ~= "function" then return nil end
  local res = { pcall(f, ...) }
  if not res[1] then return nil end
  return unpack(res, 2, table.maxn(res))
end
M.Compat = Compat

local function RawSpellInfo(s)
  if s == nil then return nil end
  if C_Spell and C_Spell.GetSpellInfo then
    local ok, i = pcall(C_Spell.GetSpellInfo, s)
    if ok and type(i) == "table" and i.name then return i.name, i.iconID, i.spellID end
  end
  if _G.GetSpellInfo then
    local ok, n, _, icon, _, _, _, id = pcall(_G.GetSpellInfo, s)
    if ok and n then return n, icon, id end
  end
  return nil
end

-- Libro de hechizos por nombre (jugador y mascota). Forever puede usar otro id de rango.
local book
local function ScanBook()
  book = {}
  local bank = (Enum and Enum.SpellBookSpellBank and Enum.SpellBookSpellBank.Player) or "spell"
  local petBank = (Enum and Enum.SpellBookSpellBank and Enum.SpellBookSpellBank.Pet) or "pet"
  local nameOf = (C_SpellBook and C_SpellBook.GetSpellBookItemName) or _G.GetSpellBookItemName
  if not nameOf then return end
  local numLines = (C_SpellBook and C_SpellBook.GetNumSpellBookSkillLines) or _G.GetNumSpellTabs
  local lineInfo = (C_SpellBook and C_SpellBook.GetSpellBookSkillLineInfo)
  if numLines then
    local okN, n = pcall(numLines)
    for t = 1, (okN and n or 0) do
      local offset, num
      if lineInfo then
        local ok, i = pcall(lineInfo, t)
        if ok and type(i) == "table" then offset, num = i.itemIndexOffset, i.numSpellBookItems end
      elseif _G.GetSpellTabInfo then
        local ok, _, _, o, c = pcall(_G.GetSpellTabInfo, t)
        if ok then offset, num = o, c end
      end
      if offset and num then
        for i = offset + 1, offset + num do
          local ok, nm = pcall(nameOf, i, bank)
          if ok and nm then book[nm] = book[nm] or i end
          -- se guarda el índice más alto (rango más alto)
          if ok and nm and i > book[nm] then book[nm] = i end
        end
      end
    end
  end
  local numPet = 0
  if C_SpellBook and C_SpellBook.HasPetSpells then
    local ok, n = pcall(C_SpellBook.HasPetSpells); if ok then numPet = tonumber(n) or 0 end
  elseif HasPetSpells then
    local ok, n = pcall(HasPetSpells); if ok then numPet = tonumber(n) or 0 end
  end
  for i = 1, numPet do
    local ok, nm = pcall(nameOf, i, petBank)
    if ok and nm and not book[nm] then book[nm] = -i end
  end
end
M.On("SPELLS_CHANGED", function() book = nil end)
M.On("LEARNED_SPELL_IN_TAB", function() book = nil end)
M.On("UNIT_PET", function() book = nil end)
M.On("PET_BAR_UPDATE", function() book = nil end)

function M.InBook(name)
  if not name then return false end
  if not book then pcall(ScanBook) end
  return book ~= nil and book[name] ~= nil
end

-- Índice (positivo) del rango más alto en el libro del jugador.
function M.BookIndex(name)
  if not name then return nil end
  if not book then pcall(ScanBook) end
  local i = book and book[name]
  if i and i > 0 then return i end
  return nil
end

function M.SpellName(id)
  if not id then return nil end
  local n = Compat("SpellName", id)
  if type(n) == "string" and n ~= "" then return n end
  return (RawSpellInfo(id))
end

function M.SpellIcon(id)
  if not id then return nil end
  local i = Compat("SpellIcon", id)
  if i then return i end
  if C_Spell and C_Spell.GetSpellTexture then
    local ok, t = pcall(C_Spell.GetSpellTexture, id)
    if ok and t then return t end
  end
  local _, icon = RawSpellInfo(id)
  return icon
end

function M.Known(id)
  if not id then return false end
  if type(id) == "string" then return M.InBook(id) end
  if Compat("IsSpellKnown", id) then return true end
  if IsPlayerSpell then
    local ok, r = pcall(IsPlayerSpell, id); if ok and r then return true end
  end
  if C_SpellBook and C_SpellBook.IsSpellKnown then
    local ok, r = pcall(C_SpellBook.IsSpellKnown, id); if ok and r then return true end
  end
  if IsSpellKnown then
    local ok, r = pcall(IsSpellKnown, id); if ok and r then return true end
  end
  local n = M.SpellName(id)
  return n ~= nil and M.InBook(n)
end

------------------------------------------------------------------------
-- Objetos
------------------------------------------------------------------------
local function packOK(ok, ...) if ok then return ... end end

function M.ItemInfo(item)
  if not item then return nil end
  local f = (C_Item and C_Item.GetItemInfo) or _G.GetItemInfo
  if not f then return nil end
  return packOK(pcall(f, item))
end

-- id, equipLoc, classID, subclassID, icon
function M.ItemInstant(item)
  if not item then return nil end
  local f = (C_Item and C_Item.GetItemInfoInstant) or _G.GetItemInfoInstant
  if not f then return nil end
  local ok, id, _, _, loc, icon, classID, subID = pcall(f, item)
  if ok then return id, loc, classID, subID, icon end
end

function M.RequestItem(id)
  if type(id) == "number" and C_Item and C_Item.RequestLoadItemDataByID then pcall(C_Item.RequestLoadItemDataByID, id) end
end

function M.ItemName(id)
  if not id then return nil end
  local n = Compat("ItemName", id)
  if type(n) == "string" and n ~= "" then return n end
  n = M.ItemInfo(id)
  if type(n) == "string" then return n end
  M.RequestItem(id)
  return nil
end

function M.ItemIcon(id)
  if not id then return nil end
  local i = Compat("ItemIcon", id)
  if i then return i end
  local f = (C_Item and C_Item.GetItemIconByID) or _G.GetItemIcon
  if f then
    local ok, t = pcall(f, id); if ok and t then return t end
  end
  local _, _, _, _, icon = M.ItemInstant(id)
  return icon
end

-- Recuento en bolsas (bank = true: también banco).
function M.ItemCount(id, bank)
  if not id then return 0 end
  if not bank then
    local n = Compat("ItemCount", id)
    if type(n) == "number" then return n end
  end
  local f = (C_Item and C_Item.GetItemCount) or _G.GetItemCount
  if not f then return 0 end
  local ok, n = pcall(f, id, bank and true or false)
  return (ok and tonumber(n)) or 0
end

function M.ItemStats(link)
  local f = (C_Item and C_Item.GetItemStats) or _G.GetItemStats
  if not f or not link then return {} end
  local ok, r = pcall(f, link)
  if ok and type(r) == "table" then return r end
  return {}
end

function M.IconTag(tex, size)
  if not tex then return "" end
  size = size or 16
  return string.format("|T%s:%d:%d:0:0|t ", tostring(tex), size, size)
end
function M.ItemTag(id, size) return M.IconTag(M.ItemIcon(id), size) end
function M.SpellTag(id, size) return M.IconTag(M.SpellIcon(id), size) end

-- Nombre del objeto con icono (o "objeto 123" mientras el cliente lo carga).
function M.ItemLabel(id, size)
  return M.ItemTag(id, size or 14) .. (M.ItemName(id) or ("objeto " .. tostring(id)))
end

------------------------------------------------------------------------
-- Bolsas
------------------------------------------------------------------------
function M.BagSlots(bag)
  if C_Container and C_Container.GetContainerNumSlots then
    local ok, n = pcall(C_Container.GetContainerNumSlots, bag); return (ok and n) or 0
  elseif _G.GetContainerNumSlots then
    local ok, n = pcall(_G.GetContainerNumSlots, bag); return (ok and n) or 0
  end
  return 0
end

-- { id, count, quality, link, bound, bag, slot } o nil
function M.SlotInfo(bag, slot)
  if C_Container and C_Container.GetContainerItemInfo then
    local ok, info = pcall(C_Container.GetContainerItemInfo, bag, slot)
    if ok and type(info) == "table" and info.itemID then
      return { id = info.itemID, count = info.stackCount or 1, quality = info.quality, link = info.hyperlink,
               bound = info.isBound, locked = info.isLocked, noValue = info.hasNoValue, bag = bag, slot = slot }
    end
    return nil
  elseif _G.GetContainerItemInfo then
    local ok, _, c, locked, q, _, _, l, _, noValue, i = pcall(_G.GetContainerItemInfo, bag, slot)
    if ok and i then return { id = i, count = c or 1, quality = q, link = l, locked = locked, noValue = noValue, bag = bag, slot = slot } end
  end
  return nil
end

local BAGS = { 0, 1, 2, 3, 4 }
function M.ScanBags()
  local out = {}
  local last = (NUM_TOTAL_EQUIPPED_BAG_SLOTS or NUM_BAG_SLOTS or 4)
  for bag = 0, last do
    for slot = 1, M.BagSlots(bag) do
      local it = M.SlotInfo(bag, slot)
      if it then table.insert(out, it) end
    end
  end
  return out
end

function M.FreeSlots()
  local free = 0
  for _, bag in ipairs(BAGS) do
    local n
    if C_Container and C_Container.GetContainerNumFreeSlots then
      local ok, r = pcall(C_Container.GetContainerNumFreeSlots, bag); n = ok and r
    elseif _G.GetContainerNumFreeSlots then
      local ok, r = pcall(_G.GetContainerNumFreeSlots, bag); n = ok and r
    end
    free = free + (tonumber(n) or 0)
  end
  return free
end

------------------------------------------------------------------------
-- Profesiones
------------------------------------------------------------------------
-- Clave de profesión -> fragmentos del nombre en el cliente (es-ES y en-US).
-- En es-ES, Sastrería aparece a veces como «Costura» y Herboristería como «Botánica».
M.PROF_KEYS = {
  tailoring = { "sastr", "costura", "tailor" },
  enchanting = { "encant", "enchant" },
  alchemy = { "alquim", "alchem" },
  blacksmithing = { "herrer", "blacksmith" },
  leatherworking = { "peleter", "leatherwork" },
  engineering = { "ingenier", "engineer" },
  herbalism = { "herbor", "botán", "botan", "herbal" },
  mining = { "miner", "mining" },
  skinning = { "desuell", "skinn" },
  firstaid = { "primeros", "first aid" },
  cooking = { "cocina", "cooking" },
  fishing = { "pesca", "fishing" },
}
M.PROF_LABELS = {
  tailoring = "Sastrería", enchanting = "Encantamiento", alchemy = "Alquimia", blacksmithing = "Herrería",
  leatherworking = "Peletería", engineering = "Ingeniería", herbalism = "Herboristería", mining = "Minería",
  skinning = "Desuello", firstaid = "Primeros auxilios", cooking = "Cocina", fishing = "Pesca",
}
M.GATHERING = { herbalism = true, mining = true, skinning = true }

function M.ProfKey(key)
  key = tostring(key or ""):lower():gsub("[%s_%-]", "")
  if key == "firstaid" then return "firstaid" end
  return key
end

function M.KeyForName(name)
  local n = tostring(name or ""):lower()
  for key, pats in pairs(M.PROF_KEYS) do
    for _, p in ipairs(pats) do
      if n:find(p, 1, true) then return key end
    end
  end
  return nil
end

-- Lista { name, rank, max, key } de todas las profesiones (API clásica, moderna y C_TradeSkillUI).
function M.Professions()
  local list, seen = {}, {}
  local function put(name, rank, maxRank)
    local key = name and M.KeyForName(name)
    if key and maxRank and maxRank > 0 and not seen[key] then
      seen[key] = true
      table.insert(list, { name = name, rank = rank or 0, max = maxRank, key = key })
    end
  end
  if GetProfessions and GetProfessionInfo then
    local ok, p1, p2, arch, fish, cook, fa = pcall(GetProfessions)
    if ok then
      for _, idx in ipairs({ p1 or false, p2 or false, arch or false, fish or false, cook or false, fa or false }) do
        if idx then
          local ok2, name, _, rank, maxRank = pcall(GetProfessionInfo, idx)
          if ok2 then put(name, rank, maxRank) end
        end
      end
    end
  end
  if GetNumSkillLines and GetSkillLineInfo then
    local okN, n = pcall(GetNumSkillLines)
    for i = 1, (okN and n or 0) do
      local ok, name, isHeader, _, rank, _, _, maxRank = pcall(GetSkillLineInfo, i)
      if ok and not isHeader then put(name, rank, maxRank) end
    end
  end
  if C_TradeSkillUI and C_TradeSkillUI.GetAllProfessionTradeSkillLines and C_TradeSkillUI.GetProfessionInfoBySkillLineID then
    local ok, lines = pcall(C_TradeSkillUI.GetAllProfessionTradeSkillLines)
    if ok and type(lines) == "table" then
      for _, id in ipairs(lines) do
        local ok2, info = pcall(C_TradeSkillUI.GetProfessionInfoBySkillLineID, id)
        if ok2 and type(info) == "table" and (info.maxSkillLevel or 0) > 0 then
          put(info.professionName or info.parentProfessionName, info.skillLevel, info.maxSkillLevel)
        end
      end
    end
  end
  return list
end

-- rank, max, name para una clave (Compat.ProfessionRank primero).
function M.ProfRank(key)
  key = M.ProfKey(key)
  local r, mx = Compat("ProfessionRank", key)
  if type(r) == "number" and type(mx) == "number" and mx > 0 then
    return r, mx, M.PROF_LABELS[key] or key
  end
  for _, p in ipairs(M.Professions()) do
    if p.key == key then return p.rank, p.max, p.name end
  end
  return nil
end

function M.ProfLabel(key)
  key = M.ProfKey(key)
  local _, _, name = M.ProfRank(key)
  return name or M.PROF_LABELS[key] or key
end

------------------------------------------------------------------------
-- Conocimiento
------------------------------------------------------------------------
local function PageAllowed(p)
  if type(p) ~= "table" then return false end
  if type(p.race) == "table" and #p.race > 0 then
    local r, ok = M.Race(), false
    for _, x in ipairs(p.race) do if x == r then ok = true end end
    if not ok then return false end
  end
  if p.faction and p.faction ~= M.Faction() then return false end
  return true
end

-- Páginas de la clase del jugador (y "ANY"), opcionalmente de un tipo, ordenadas por order e id.
function M.Pages(kind)
  local K = Senda.Knowledge
  if not (K and K.ForClass) then return {} end
  local out, seen = {}, {}
  for _, cls in ipairs({ M.Class() or "ANY", "ANY" }) do
    local ok, list = pcall(K.ForClass, K, cls)
    if ok and type(list) == "table" then
      for _, p in ipairs(list) do
        if type(p) == "table" and p.id and not seen[p.id] and (not kind or p.kind == kind) and PageAllowed(p) then
          seen[p.id] = true
          table.insert(out, p)
        end
      end
    end
  end
  table.sort(out, function(a, b)
    local oa, ob = a.order or 1000, b.order or 1000
    if oa ~= ob then return oa < ob end
    return tostring(a.id) < tostring(b.id)
  end)
  return out
end

function M.InRange(level, range)
  if type(range) ~= "table" then return true end
  local a, b = range[1] or 1, range[2] or 999
  return level >= a and level <= b
end

-- Insignia de estado para datos no verificados.
function M.StatusTag(status)
  if status == "disputed" then return " |cffff8040" .. (L.MOD_DISPUTED or "(en duda)") .. "|r" end
  if status == "unverified" then return " |cff888888" .. (L.MOD_UNVERIFIED or "(sin verificar)") .. "|r" end
  return ""
end

-- URL completa de un campo link de la web.
function M.WebURL(link)
  if not link or link == "" then return nil end
  if link:match("^https?://") then return link end
  local base = Senda.WEB or ""
  if base:sub(-1) == "/" and link:sub(1, 1) == "/" then link = link:sub(2) end
  return base .. link
end

------------------------------------------------------------------------
-- UI: helpers con estilo común (los del núcleo si existen) y reservas propias
------------------------------------------------------------------------
local function OwnBackdrop(f)
  if not f.SetBackdrop then return end
  f:SetBackdrop({
    bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background-Dark",
    edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
    tile = true, tileSize = 16, edgeSize = 16,
    insets = { left = 4, right = 4, top = 4, bottom = 4 },
  })
  local c = Senda.COLOR or { 0.30, 0.82, 0.66 }
  f:SetBackdropBorderColor(c[1], c[2], c[3])
end

function M.Backdrop(f)
  if Senda.UI and Senda.UI.Backdrop then
    local ok = pcall(Senda.UI.Backdrop, Senda.UI, f)
    if ok then return f end
  end
  OwnBackdrop(f)
  return f
end

function M.Frame(parent, name)
  local f = CreateFrame("Frame", name, parent, BackdropTemplateMixin and "BackdropTemplate" or nil)
  M.Backdrop(f)
  return f
end

function M.Button(parent, label, width, onClick)
  local b
  if Senda.UI and Senda.UI.Button then
    local ok, r = pcall(Senda.UI.Button, Senda.UI, parent, label, width, onClick)
    if ok and type(r) == "table" and r.SetText and r.SetScript then b = r end
  end
  if not b then b = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate") end
  b:SetSize(width or 120, 22)
  b:SetText(label or "")
  if onClick then b:SetScript("OnClick", onClick) end
  return b
end

function M.Check(parent, label, getter, setter)
  local cb = CreateFrame("CheckButton", nil, parent, "UICheckButtonTemplate")
  cb:SetSize(24, 24)
  local fs = cb:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  fs:SetPoint("LEFT", cb, "RIGHT", 2, 0)
  fs:SetText(label)
  cb:SetChecked(getter() and true or false)
  cb:SetScript("OnClick", function(self) setter(self:GetChecked() and true or false) end)
  return cb
end

-- Ventanas emergentes: copiar enlace y confirmar.
local function PopupEditBox(self)
  return self.editBox or self.EditBox or (self.GetEditBox and self:GetEditBox())
end

StaticPopupDialogs["SENDA_MOD_COPY"] = {
  text = "%s",
  button1 = CLOSE or "Cerrar",
  hasEditBox = true, editBoxWidth = 340,
  OnShow = function(self, data)
    local eb = PopupEditBox(self)
    if eb and data then eb:SetText(data.text or ""); eb:SetFocus(); eb:HighlightText() end
  end,
  EditBoxOnEscapePressed = function(self) self:GetParent():Hide() end,
  EditBoxOnEnterPressed = function(self) self:GetParent():Hide() end,
  EditBoxOnTextChanged = function(self, data)
    local p = self:GetParent()
    local want = (data and data.text) or (p and p.data and p.data.text)
    if want and self:GetText() ~= want then self:SetText(want); self:HighlightText() end
  end,
  timeout = 0, whileDead = true, hideOnEscape = true, preferredIndex = 3,
}

function M.CopyPopup(text, title)
  if not StaticPopup_Show then return end
  StaticPopup_Show("SENDA_MOD_COPY",
    title or (L.MOD_COPY_LINK or "Copia el enlace con Ctrl+C y pégalo en tu navegador:"), nil, { text = text })
end

StaticPopupDialogs["SENDA_MOD_CONFIRM"] = {
  text = "%s",
  button1 = ACCEPT or "Aceptar", button2 = CANCEL or "Cancelar",
  OnAccept = function(self, data) if data and data.fn then pcall(data.fn) end end,
  timeout = 0, whileDead = true, hideOnEscape = true, preferredIndex = 3,
}

function M.Confirm(text, fn, button1)
  if not StaticPopup_Show then return end
  local d = StaticPopupDialogs["SENDA_MOD_CONFIRM"]
  d.button1 = button1 or ACCEPT or "Aceptar"
  StaticPopup_Show("SENDA_MOD_CONFIRM", text, nil, { fn = fn })
end

-- Pestañas
function M.RegisterTab(def)
  if not (Senda.UI and Senda.UI.RegisterTab) then
    M.Debug("UI:RegisterTab no disponible; pestaña %s sin registrar", tostring(def.key))
    return false
  end
  local build = def.build
  def.build = function(parent)
    local ok, err = pcall(build, parent)
    if not ok then
      M.Debug("Pestaña %s: %s", tostring(def.key), tostring(err))
      local fs = parent:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
      fs:SetPoint("TOPLEFT", 10, -10)
      fs:SetText(L.MOD_TAB_ERROR or "No se pudo construir esta pestaña.")
    end
    if def.refresh and parent.HookScript then
      parent:HookScript("OnShow", function() pcall(def.refresh) end)
    end
  end
  local refresh = def.refresh
  if refresh then def.refresh = function(...) local ok, err = pcall(refresh, ...); if not ok then M.Debug("Pestaña %s: %s", tostring(def.key), tostring(err)) end end end
  local ok, err = pcall(Senda.UI.RegisterTab, Senda.UI, def)
  if not ok then M.Debug("RegisterTab %s: %s", tostring(def.key), tostring(err)) end
  return ok
end

-- Barra superior de una pestaña: devuelve (barra, contenedor inferior).
function M.Toolbar(parent, height)
  height = height or 28
  local bar = CreateFrame("Frame", nil, parent)
  bar:SetPoint("TOPLEFT", 0, 0)
  bar:SetPoint("TOPRIGHT", 0, 0)
  bar:SetHeight(height)
  local body = CreateFrame("Frame", nil, parent)
  body:SetPoint("TOPLEFT", 0, -height)
  body:SetPoint("BOTTOMRIGHT", 0, 0)
  return bar, body
end

------------------------------------------------------------------------
-- Documento desplazable con mini-marcado
--   nodos: { t = "h1"|"h2"|"p"|"li"|"md"|"row"|"btn"|"sp", ... }
--   md:  texto con **negrita**, listas '- ' y enlaces [texto](https://...)
--   row: { icon, text, right, hl = "good"|"warn"|"now"|"dim", spell, item, link, onClick, desat }
--   btn: { label, onClick, width }
------------------------------------------------------------------------
local HL = {
  now = { 1, 0.82, 0, 0.16 }, good = { 0.3, 0.8, 0.3, 0.12 }, warn = { 1, 0.45, 0.1, 0.16 }, dim = { 0, 0, 0, 0 },
}

function M.Doc(parent)
  local doc = { urls = {}, nodes = {} }
  local sf = CreateFrame("ScrollFrame", nil, parent, "UIPanelScrollFrameTemplate")
  sf:SetPoint("TOPLEFT", parent, "TOPLEFT", 4, -4)
  sf:SetPoint("BOTTOMRIGHT", parent, "BOTTOMRIGHT", -26, 4)
  local child = CreateFrame("Frame", nil, sf)
  child:SetSize(400, 10)
  sf:SetScrollChild(child)
  doc.scroll, doc.child = sf, child

  local function onLink(_, link)
    local n = tonumber(tostring(link or ""):match("sendaurl:(%d+)"))
    if n and doc.urls[n] then M.CopyPopup(doc.urls[n]) end
  end
  local function enableLinks(f)
    if f.SetHyperlinksEnabled then
      pcall(f.SetHyperlinksEnabled, f, true)
      f:SetScript("OnHyperlinkClick", onLink)
      return true
    end
    return false
  end
  doc.hyper = enableLinks(child)

  local pool, used = { fs = {}, h1 = {}, h2 = {}, line = {}, row = {}, btn = {} }, {}
  local cr, cg, cb = unpack(Senda.COLOR or { 0.30, 0.82, 0.66 })
  local makers = {
    fs = function()
      local f = child:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
      f:SetJustifyH("LEFT"); f:SetJustifyV("TOP"); f:SetSpacing(2)
      return f
    end,
    h1 = function()
      local f = child:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
      f:SetJustifyH("LEFT"); f:SetTextColor(cr, cg, cb)
      return f
    end,
    h2 = function()
      local f = child:CreateFontString(nil, "OVERLAY", "GameFontNormal")
      f:SetJustifyH("LEFT")
      return f
    end,
    line = function()
      local t = child:CreateTexture(nil, "ARTWORK")
      t:SetColorTexture(cr, cg, cb, 0.35)
      t:SetHeight(1)
      return t
    end,
    row = function()
      local r = CreateFrame("Button", nil, child)
      r.bg = r:CreateTexture(nil, "BACKGROUND"); r.bg:SetAllPoints()
      r.icon = r:CreateTexture(nil, "ARTWORK"); r.icon:SetSize(20, 20); r.icon:SetPoint("TOPLEFT", 4, -3)
      r.text = r:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
      r.text:SetJustifyH("LEFT"); r.text:SetJustifyV("TOP"); r.text:SetSpacing(2)
      r.right = r:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
      r.right:SetPoint("TOPRIGHT", -6, -6); r.right:SetJustifyH("RIGHT")
      enableLinks(r)
      r:SetScript("OnEnter", function(self)
        local n = self.node
        if not n or not GameTooltip then return end
        if n.spell or n.item or n.link or n.tip then
          GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
          local ok = false
          if n.link then ok = pcall(GameTooltip.SetHyperlink, GameTooltip, n.link)
          elseif n.item then ok = pcall(GameTooltip.SetHyperlink, GameTooltip, "item:" .. n.item)
          elseif n.spell then
            if GameTooltip.SetSpellByID then ok = pcall(GameTooltip.SetSpellByID, GameTooltip, n.spell) end
          end
          if n.tip then GameTooltip:AddLine(n.tip, 1, 0.82, 0, true); ok = true end
          if ok then GameTooltip:Show() else GameTooltip:Hide() end
        end
      end)
      r:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
      r:SetScript("OnClick", function(self, button) local n = self.node; if n and n.onClick then pcall(n.onClick, button) end end)
      return r
    end,
    btn = function()
      local b = M.Button(child, "", 160)
      b:SetScript("OnClick", function(self) if self.fn then pcall(self.fn) end end)
      return b
    end,
  }
  local function get(kind)
    used[kind] = (used[kind] or 0) + 1
    local o = pool[kind][used[kind]]
    if not o then o = makers[kind](); pool[kind][used[kind]] = o end
    o:ClearAllPoints()
    o:Show()
    return o
  end

  -- Texto en línea: enlaces y negrita.
  local function inline(s, pend)
    s = tostring(s or "")
    s = s:gsub("%[([^%]]+)%]%((https?://[^%)%s]+)%)", function(text, url)
      table.insert(doc.urls, url)
      local n = #doc.urls
      if doc.hyper then return "|cff4fc3f7|Haddon:sendaurl:" .. n .. "|h" .. text .. "|h|r" end
      if pend then table.insert(pend, { text = text, n = n }) end
      return "|cff4fc3f7" .. text .. "|r"
    end)
    s = s:gsub("%*%*(.-)%*%*", "|cffffffff%1|r")
    return s
  end
  doc.Inline = function(_, s) return inline(s) end

  -- Expande un nodo md en nodos p/li/h2/btn.
  local function expand(text, out)
    local para, pend = {}, {}
    local function flushLinks()
      for _, l in ipairs(pend) do
        local url = doc.urls[l.n]
        table.insert(out, { t = "btn", label = (L.MOD_LINK or "Enlace") .. ": " .. l.text, width = 260,
          onClick = function() M.CopyPopup(url) end })
      end
      pend = {}
    end
    local function flush()
      if #para > 0 then table.insert(out, { t = "p", text = table.concat(para, "\n"), raw = true }); para = {} end
      flushLinks()
    end
    for line in (tostring(text or "") .. "\n"):gmatch("(.-)\r?\n") do
      local item = line:match("^%s*[-*]%s+(.+)$")
      local head = line:match("^#+%s+(.+)$")
      if item then
        flush()
        table.insert(out, { t = "li", text = inline(item, pend), raw = true })
        flushLinks()
      elseif head then
        flush()
        table.insert(out, { t = "h2", text = inline(head, pend), raw = true })
      elseif line:match("^%s*$") then
        flush()
      else
        table.insert(para, inline(line, pend))
      end
    end
    flush()
  end

  local function render()
    local w = sf:GetWidth() - 8
    if not w or w < 120 then w = 460 end
    child:SetWidth(w)
    for _, list in pairs(pool) do for _, o in ipairs(list) do o:Hide() end end
    used = {}
    doc.urls = {}
    local flat = {}
    for _, n in ipairs(doc.nodes) do
      if n.t == "md" then expand(n.text, flat) else table.insert(flat, n) end
    end
    local y = -4
    for i, n in ipairs(flat) do
      local t = n.t
      local text = n.text
      if text and not n.raw then text = inline(text) end
      if t == "h1" then
        if i > 1 then
          local ln = get("line"); ln:SetPoint("TOPLEFT", 4, y - 4); ln:SetWidth(w - 8); y = y - 12
        end
        local f = get("h1"); f:SetPoint("TOPLEFT", 4, y); f:SetWidth(w - 8); f:SetText(text or "")
        y = y - f:GetStringHeight() - 6
      elseif t == "h2" then
        local f = get("h2"); f:SetPoint("TOPLEFT", 4, y - 2); f:SetWidth(w - 8); f:SetText(text or "")
        y = y - f:GetStringHeight() - 6
      elseif t == "p" or t == "li" then
        local f = get("fs")
        local indent = (t == "li") and 18 or 4
        f:SetPoint("TOPLEFT", indent, y)
        f:SetWidth(w - indent - 4)
        f:SetTextColor(0.86, 0.86, 0.86)
        f:SetText((t == "li" and "• " or "") .. (text or ""))
        y = y - f:GetStringHeight() - ((t == "li") and 3 or 8)
      elseif t == "row" then
        local r = get("row")
        r.node = n
        r:SetPoint("TOPLEFT", 2, y)
        r:SetWidth(w - 4)
        local c = HL[n.hl or ""] or { 0, 0, 0, 0 }
        r.bg:SetColorTexture(c[1], c[2], c[3], c[4])
        local hasIcon = n.icon ~= nil
        r.icon:SetShown(hasIcon)
        if hasIcon then
          r.icon:SetTexture(n.icon)
          r.icon:SetDesaturated(n.desat and true or false)
          r.icon:SetAlpha(n.desat and 0.6 or 1)
        end
        r.right:SetText(n.right or "")
        local rightW = (n.right and n.right ~= "") and (r.right:GetStringWidth() + 12) or 6
        r.text:ClearAllPoints()
        r.text:SetPoint("TOPLEFT", hasIcon and 30 or 6, -5)
        r.text:SetWidth(math.max(60, w - 4 - (hasIcon and 30 or 6) - rightW))
        r.text:SetText(text or "")
        local h = math.max(26, r.text:GetStringHeight() + 10)
        r:SetHeight(h)
        y = y - h - 2
      elseif t == "btn" then
        local b = get("btn")
        b:SetPoint("TOPLEFT", n.x or 6, y - 2)
        b:SetWidth(n.width or 180)
        b:SetText(n.label or "")
        b.fn = n.onClick
        b:SetEnabled(n.disabled ~= true)
        y = y - 28
      elseif t == "sp" then
        y = y - (n.h or 8)
      end
    end
    child:SetHeight(-y + 8)
  end

  function doc:Set(nodes, keepScroll)
    self.nodes = nodes or {}
    render()
    if not keepScroll then sf:SetVerticalScroll(0) end
  end
  function doc:Text(md) self:Set({ { t = "md", text = md } }) end

  local lastW
  sf:SetScript("OnSizeChanged", function(self)
    local w = math.floor(self:GetWidth() or 0)
    if w ~= lastW and w > 120 then
      lastW = w
      M.Debounce(doc, 0.05, function() render() end)
    end
  end)
  return doc
end

------------------------------------------------------------------------
-- Ventana de exportación (texto copiable grande)
------------------------------------------------------------------------
local exportFrame
function M.ShowExport(title, text)
  if not exportFrame then
    local f = M.Frame(UIParent, "SendaModExport")
    f:SetSize(560, 420)
    f:SetPoint("CENTER")
    f:SetFrameStrata("DIALOG")
    f:SetMovable(true); f:EnableMouse(true); f:SetClampedToScreen(true)
    f:RegisterForDrag("LeftButton")
    f:SetScript("OnDragStart", f.StartMoving)
    f:SetScript("OnDragStop", f.StopMovingOrSizing)
    f.title = f:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    f.title:SetPoint("TOPLEFT", 12, -10)
    f.title:SetPoint("RIGHT", -36, 0)
    f.title:SetJustifyH("LEFT")
    local close = CreateFrame("Button", nil, f, "UIPanelCloseButton")
    close:SetPoint("TOPRIGHT", -2, -2)
    local sf = CreateFrame("ScrollFrame", nil, f, "UIPanelScrollFrameTemplate")
    sf:SetPoint("TOPLEFT", 10, -32)
    sf:SetPoint("BOTTOMRIGHT", -30, 10)
    local eb = CreateFrame("EditBox", nil, sf)
    eb:SetMultiLine(true)
    eb:SetFontObject(ChatFontNormal)
    eb:SetWidth(500)
    eb:SetAutoFocus(false)
    eb:SetScript("OnEscapePressed", function(self) self:ClearFocus(); f:Hide() end)
    sf:SetScrollChild(eb)
    f.eb = eb
    if UISpecialFrames then table.insert(UISpecialFrames, "SendaModExport") end
    exportFrame = f
  end
  exportFrame.title:SetText(title or "")
  exportFrame:Show()
  exportFrame.eb:SetText(text or "")
  exportFrame.eb:SetFocus()
  exportFrame.eb:HighlightText()
end

-- Avisos al HUD del núcleo (si existe) y evento interno para quien lo quiera.
function M.SetAdvice(text)
  if Senda.HUD and Senda.HUD.SetAdvice then pcall(Senda.HUD.SetAdvice, Senda.HUD, text) end
  M.Fire("SENDA_ADVICE", text)
end

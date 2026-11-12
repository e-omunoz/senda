-- Senda / Modules / Gear
-- Valoración de equipo para subir de nivel, con los pesos de la build de tu clase y de tu tramo de nivel:
--   · línea «Senda: +12% para tu build» en la descripción de los objetos
--   · marca la mejor recompensa de misión (o la que más vale si ninguna te mejora)
--   · avisa de mejoras en las bolsas («Ponte X: mejora…») y busca más en banco (caché), recetas y misiones del diario
--   · pestaña Equipo: lo que llevas, mejoras, «Mejor pieza conocida para tu tramo» y dónde buscar
-- Pesos: páginas de conocimiento kind = "weights" (data/knowledge/<clase>/weights.toml: [[build]] y [[band]] por
-- tramo de nivel, con fuente; docs/GEAR.md). Clases sin esa página: el campo `weights` de una página, o la tabla de
-- reserva de abajo. Nunca recomienda lo que tu clase no puede llevar; lo que pide nivel o aprender un arma solo se
-- propone si no hay nada que puedas ponerte ya, y siempre con el motivo.
-- La tabla de claves de estadísticas del cliente está adaptada de Polestar, addon/Polestar/Gear/Gear.lua
-- (GPL-3.0, commit 19bd636e).
local ADDON, Senda = ...
local M = Senda.Mod
if not M then return end
local L = M.L

local G = {}
Senda.Modules.Gear = G

------------------------------------------------------------------------
-- Pesos de reserva (clases sin página kind = "weights"). Más alto = más importante.
-- SP = poder con hechizos; SCHOOL/SCHOOL_W = escuela preferida; MP5 = maná cada 5 s;
-- DPS = DPS de arma cuerpo a cuerpo; RANGED_DPS = arco/fusil/ballesta; WAND_DPS(_30) = varita (desde el 30).
------------------------------------------------------------------------
local WEIGHTS = {
  PRIEST  = { SP = 1.0, SCHOOL = "SHADOW", SCHOOL_W = 1.0, INT = 0.55, SPI = 0.6, STA = 0.4, MP5 = 0.6, ARMOR = 0.005, WAND_DPS = 1.4, WAND_DPS_30 = 0.8 },
  WARRIOR = { STR = 1.0, AGI = 0.6, STA = 0.5, AP = 0.45, ARMOR = 0.01, DPS = 3.0, RANGED_DPS = 0.3 },
  ROGUE   = { AGI = 1.0, STR = 0.5, STA = 0.4, AP = 0.45, ARMOR = 0.005, DPS = 3.0, RANGED_DPS = 0.3 },
  HUNTER  = { AGI = 1.0, INT = 0.3, STA = 0.4, AP = 0.2, RAP = 0.45, SPI = 0.1, ARMOR = 0.005, DPS = 0.5, RANGED_DPS = 3.0 },
  PALADIN = { STR = 1.0, STA = 0.6, INT = 0.4, AGI = 0.4, SPI = 0.2, AP = 0.4, SP = 0.3, ARMOR = 0.01, DPS = 2.5 },
  SHAMAN  = { STR = 0.8, INT = 0.6, AGI = 0.5, STA = 0.5, SP = 0.6, MP5 = 0.6, AP = 0.35, ARMOR = 0.008, DPS = 2.5 },
}
local SCHOOL_WORDS = { SHADOW = { "sombra", "shadow" }, FROST = { "escarcha", "frost" }, FIRE = { "fuego", "fire" },
  ARCANE = { "arcano", "arcane" }, NATURE = { "naturaleza", "nature" }, HOLY = { "sagrado", "holy" } }

-- Estadística del cliente (C_Item.GetItemStats) -> clave de peso. Adaptado de Polestar (Gear/Gear.lua, STAT_FROM_API).
local STAT = {
  ITEM_MOD_STRENGTH_SHORT = "STR", ITEM_MOD_AGILITY_SHORT = "AGI", ITEM_MOD_STAMINA_SHORT = "STA",
  ITEM_MOD_INTELLECT_SHORT = "INT", ITEM_MOD_SPIRIT_SHORT = "SPI", RESISTANCE0_NAME = "ARMOR",
  ITEM_MOD_ATTACK_POWER_SHORT = "AP", ITEM_MOD_RANGED_ATTACK_POWER_SHORT = "RAP",
  ITEM_MOD_SPELL_DAMAGE_DONE_SHORT = "SP", ITEM_MOD_SPELL_POWER_SHORT = "SP",
  ITEM_MOD_MANA_REGENERATION_SHORT = "MP5", ITEM_MOD_POWER_REGEN0_SHORT = "MP5",
  ITEM_MOD_CRIT_RATING_SHORT = "CRIT", ITEM_MOD_CRIT_MELEE_RATING_SHORT = "CRIT",
  ITEM_MOD_HIT_RATING_SHORT = "HIT", ITEM_MOD_HIT_MELEE_RATING_SHORT = "HIT",
  ITEM_MOD_CRIT_SPELL_RATING_SHORT = "SPELL_CRIT", ITEM_MOD_HIT_SPELL_RATING_SHORT = "SPELL_HIT",
  ITEM_MOD_DEFENSE_SKILL_RATING_SHORT = "DEFENSE", ITEM_MOD_DODGE_RATING_SHORT = "DODGE",
  ITEM_MOD_DAMAGE_PER_SECOND_SHORT = "WEAPON_DPS",
}

-- Armadura (subclase de objeto 4): 1 tela, 2 cuero, 3 malla, 4 placas, 6 escudo. Malla/placas desde el 40.
local ARMOR = {
  MAGE = 1, WARLOCK = 1, PRIEST = 1, ROGUE = 2, DRUID = 2,
  HUNTER = { 2, 3 }, SHAMAN = { 2, 3 }, WARRIOR = { 3, 4 }, PALADIN = { 3, 4 },
}
local SHIELD = { WARRIOR = true, PALADIN = true, SHAMAN = true }
-- Reliquias (subclase 4/7-11): libro (7) paladín, ídolo (8) druida, tótem (9) chamán.
local RELIC = { PALADIN = 7, DRUID = 8, SHAMAN = 9 }
-- Llevar un arma en la mano izquierda.
local DUAL = { WARRIOR = true, ROGUE = true, HUNTER = true }
-- Armas (subclase de objeto 2) que cada clase puede aprender. Druida: armas de asta en Forever (Woo Ping, druid-gear).
local WEAPONS = {
  WARRIOR = { 0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 13, 15, 16, 18 },
  PALADIN = { 0, 1, 4, 5, 6, 7, 8 },
  HUNTER  = { 0, 1, 2, 3, 6, 7, 8, 10, 13, 15, 16, 18 },
  ROGUE   = { 2, 3, 4, 7, 13, 15, 16, 18 },
  PRIEST  = { 4, 10, 15, 19 },
  SHAMAN  = { 0, 1, 4, 5, 10, 13, 15 },
  MAGE    = { 7, 10, 15, 19 },
  WARLOCK = { 7, 10, 15, 19 },
  DRUID   = { 4, 5, 6, 10, 13, 15 },
}
-- Habilidad de arma: subclase -> fragmentos del nombre (es/en). false = no necesita habilidad.
local WEAPON_SKILL = {
  [0] = { "hachas de una", "one-handed axe" }, [1] = { "hachas de dos", "two-handed axe" }, [2] = { "arco", "bow" },
  [3] = { "armas de fuego", "gun" }, [4] = { "mazas de una", "one-handed mace" }, [5] = { "mazas de dos", "two-handed mace" },
  [6] = { "armas de asta", "polearm" }, [7] = { "espadas de una", "one-handed sword" }, [8] = { "espadas de dos", "two-handed sword" },
  [10] = { "bast", "stave", "staff" }, [13] = { "puño", "fist" }, [15] = { "daga", "dagger" }, [16] = { "arrojadiza", "thrown" },
  [18] = { "ballesta", "crossbow" }, [19] = false,
}
-- Hechizo de competencia de cada arma (si el cliente no da las líneas de habilidad): Hachas 196, Hachas de dos manos
-- 197, Arcos 264, Armas de fuego 266, Mazas 198, Mazas de dos manos 199, Armas de asta 200, Espadas 201, Espadas de
-- dos manos 202, Bastones 227, Armas de puño 15590, Dagas 1180, Arrojadizas 2567, Ballestas 5011.
local SKILL_SPELL = { [0] = 196, [1] = 197, [2] = 264, [3] = 266, [4] = 198, [5] = 199, [6] = 200, [7] = 201,
  [8] = 202, [10] = 227, [13] = 15590, [15] = 1180, [16] = 2567, [18] = 5011 }
local SKILL_KEY = { [0] = "AXE", [1] = "AXE2", [2] = "BOW", [3] = "GUN", [4] = "MACE", [5] = "MACE2", [6] = "POLEARM",
  [7] = "SWORD", [8] = "SWORD2", [10] = "STAFF", [13] = "FIST", [15] = "DAGGER", [16] = "THROWN", [18] = "CROSSBOW" }

local LOC = {
  INVTYPE_HEAD = { 1 }, INVTYPE_NECK = { 2 }, INVTYPE_SHOULDER = { 3 }, INVTYPE_CLOAK = { 15 },
  INVTYPE_CHEST = { 5 }, INVTYPE_ROBE = { 5 }, INVTYPE_WRIST = { 9 }, INVTYPE_HAND = { 10 },
  INVTYPE_WAIST = { 6 }, INVTYPE_LEGS = { 7 }, INVTYPE_FEET = { 8 }, INVTYPE_FINGER = { 11, 12 },
  INVTYPE_TRINKET = { 13, 14 }, INVTYPE_WEAPON = { 16 }, INVTYPE_WEAPONMAINHAND = { 16 },
  INVTYPE_2HWEAPON = { 16 }, INVTYPE_HOLDABLE = { 17 }, INVTYPE_WEAPONOFFHAND = { 17 }, INVTYPE_SHIELD = { 17 },
  INVTYPE_RANGED = { 18 }, INVTYPE_RANGEDRIGHT = { 18 }, INVTYPE_THROWN = { 18 }, INVTYPE_RELIC = { 18 },
}
G.LOC = LOC
local OFFHAND = { INVTYPE_HOLDABLE = true, INVTYPE_WEAPONOFFHAND = true, INVTYPE_SHIELD = true }

local SLOTS = {
  [1] = L.MOD_SLOT_HEAD or "Cabeza", [2] = L.MOD_SLOT_NECK or "Cuello", [3] = L.MOD_SLOT_SHOULDER or "Hombros",
  [5] = L.MOD_SLOT_CHEST or "Pecho", [6] = L.MOD_SLOT_WAIST or "Cintura", [7] = L.MOD_SLOT_LEGS or "Piernas",
  [8] = L.MOD_SLOT_FEET or "Pies", [9] = L.MOD_SLOT_WRIST or "Muñecas", [10] = L.MOD_SLOT_HANDS or "Manos",
  [11] = L.MOD_SLOT_RING1 or "Anillo 1", [12] = L.MOD_SLOT_RING2 or "Anillo 2", [13] = L.MOD_SLOT_TRINKET1 or "Abalorio 1",
  [14] = L.MOD_SLOT_TRINKET2 or "Abalorio 2", [15] = L.MOD_SLOT_BACK or "Espalda", [16] = L.MOD_SLOT_MAIN or "Arma",
  [17] = L.MOD_SLOT_OFF or "Mano izq.", [18] = L.MOD_SLOT_RANGED or "A distancia",
}
G.SLOTS = SLOTS
G.SLOT_ORDER = { 1, 2, 3, 15, 5, 9, 10, 6, 7, 8, 11, 12, 13, 14, 16, 17, 18 }

------------------------------------------------------------------------
-- Builds y pesos por tramo
------------------------------------------------------------------------
local function WeightsPage()
  local pages = M.Pages("weights")
  local class = M.Class()
  for _, p in ipairs(pages) do
    if p.class == class and type(p.build) == "table" and type(p.band) == "table" then return p end
  end
end

-- Builds de tu clase: { { key, school, default }, ... } (vacía si la clase no tiene página de pesos).
function G.Builds()
  local p = WeightsPage()
  return p and p.build or {}
end

-- Build activa: la elegida (druida: felino u oso) o la de por defecto.
function G.BuildKey()
  local list = G.Builds()
  if #list == 0 then return nil end
  local want = M.DB().gearBuild
  local def
  for _, b in ipairs(list) do
    if b.key == want then return b.key, b end
    if b.default then def = b end
  end
  def = def or list[1]
  return def.key, def
end

function G.BuildLabel(key)
  if not key then return nil end
  return L["GEAR_BUILD_" .. key] or key
end

local cachedW = {}
local function Invalidate() cachedW = {} end

function G.SetBuild(key)
  for _, b in ipairs(G.Builds()) do
    if b.key == key then
      M.DB().gearBuild = key
      Invalidate()
      return true
    end
  end
  return false
end

-- Tramo de pesos de tu build para un nivel: band = { build, from, to, ref, w }.
function G.Band(level)
  level = level or M.Level()
  local p = WeightsPage()
  if not p then return nil end
  local key = G.BuildKey()
  for _, b in ipairs(p.band) do
    if b.build == key and level >= (b.from or 1) and level <= (b.to or 60) then return b end
  end
end

-- Pesos para tu build y nivel (o los de reserva). Tabla plana { STA = .., SCHOOL = "SHADOW", ... }.
function G.Weights(level)
  level = level or M.Level()
  local key = (G.BuildKey() or "-") .. ":" .. level
  if cachedW[key] then return cachedW[key] end
  local W
  local band = G.Band(level)
  if band and type(band.w) == "table" then
    W = {}
    for k, v in pairs(band.w) do W[k] = v end
    local _, b = G.BuildKey()
    W.SCHOOL = b and b.school or nil
  else
    for _, p in ipairs(M.Pages()) do
      if type(p.weights) == "table" and next(p.weights) then W = p.weights; break end
    end
    W = W or WEIGHTS[M.Class() or ""] or { STA = 1, INT = 0.5, STR = 0.5, AGI = 0.5, SP = 0.5 }
  end
  cachedW[key] = W
  return W
end

------------------------------------------------------------------------
-- Puntuación
------------------------------------------------------------------------
local function ArmorMax()
  local a = ARMOR[M.Class() or ""]
  if type(a) == "table" then return (M.Level() >= 40) and a[2] or a[1] end
  return a or 4
end

local function Contains(list, v)
  for _, x in ipairs(list or {}) do if x == v then return true end end
  return false
end

local skillCache
M.On("SKILL_LINES_CHANGED", function() skillCache = nil end)
M.On("SPELLS_CHANGED", function() skillCache = nil end)
local function SkillLines()
  if skillCache then return skillCache end
  skillCache = {}
  if GetNumSkillLines and GetSkillLineInfo then
    local okN, n = pcall(GetNumSkillLines)
    for i = 1, (okN and tonumber(n) or 0) do
      local ok, name, isHeader = pcall(GetSkillLineInfo, i)
      if ok and type(name) == "string" and not isHeader then table.insert(skillCache, name:lower()) end
    end
  end
  return skillCache
end

local function KnownSpell(id)
  if M.Known then
    local ok, r = pcall(M.Known, id)
    if ok then return r and true or false end
  end
  return false
end

-- ¿Sabes usar esa arma? Líneas de habilidad del cliente; si no las da, el hechizo de competencia. Sin ninguna
-- de las dos fuentes (datos aún sin cargar) se da por sabida, para no esconder nada por error.
local function HasWeaponSkill(sub)
  local words = WEAPON_SKILL[sub]
  if words == false then return true end
  local lines = SkillLines()
  if #lines > 0 and words then
    for _, n in ipairs(lines) do
      for _, w in ipairs(words) do if n:find(w, 1, true) then return true end end
    end
    return false
  end
  local spell = SKILL_SPELL[sub]
  if not spell then return true end
  if lines.anySpell == nil then
    lines.anySpell = false
    for _, id in pairs(SKILL_SPELL) do
      if KnownSpell(id) then lines.anySpell = true; break end
    end
  end
  if not lines.anySpell then return true end
  return KnownSpell(spell)
end
G.HasWeaponSkill = HasWeaponSkill

-- Lo que el cliente solo pone en el texto del objeto (poder con hechizos de una escuela, golpe y crítico en %).
-- Caché por enlace y escuela (el texto de un objeto no cambia): evita releer la descripción en cada valoración.
local extrasCache, extrasCount = {}, 0
local function TooltipExtras(item, W)
  local ckey = tostring(item) .. "#" .. tostring(W.SCHOOL)
  local hit = extrasCache[ckey]
  if hit then return hit end
  local out = { SP = 0, SCHOOL = 0, SPELL_HIT = 0, SPELL_CRIT = 0, HIT = 0, CRIT = 0 }
  if not (C_TooltipInfo and C_TooltipInfo.GetHyperlink) or type(item) ~= "string" then return out end
  local ok, data = pcall(C_TooltipInfo.GetHyperlink, item)
  if not ok or type(data) ~= "table" or type(data.lines) ~= "table" then return out end
  -- Solo se guarda una descripción ya cargada (con algo más que el nombre); si no, se vuelve a pedir la próxima vez.
  if #data.lines > 1 then
    if extrasCount >= 500 then extrasCache, extrasCount = {}, 0 end
    extrasCount = extrasCount + 1
    extrasCache[ckey] = out
  end
  local want = SCHOOL_WORDS[W.SCHOOL or ""] or {}
  for _, line in ipairs(data.lines) do
    local t = type(line) == "table" and type(line.leftText) == "string" and line.leftText:lower() or ""
    local spell = t:find("hechizo") or t:find("spell")
    local pct = tonumber(t:match("(%d+)%s*%%") or "")
    if pct and (t:find("crítico") or t:find("critical")) then
      if spell then out.SPELL_CRIT = out.SPELL_CRIT + pct else out.CRIT = out.CRIT + pct end
    elseif pct and (t:find("golpe") or t:find("hit")) then
      if spell then out.SPELL_HIT = out.SPELL_HIT + pct else out.HIT = out.HIT + pct end
    else
      local n = tonumber(t:match("(%d+)%D*$") or "")
      if n and spell and (t:find("daño") or t:find("damage") or t:find("poder") or t:find("power")) then
        local isSchool = false
        for _, w in ipairs(want) do if t:find(w, 1, true) then isSchool = true end end
        if isSchool then out.SCHOOL = out.SCHOOL + n
        elseif not (t:find("cura") or t:find("sana") or t:find("heal")) or t:find("daño") or t:find("damage") then
          out.SP = out.SP + n
        end
      end
    end
  end
  return out
end

-- Clave de peso de una estadística del cliente (exacta y, si no, por fragmentos como antes).
local function StatKey(k)
  local key = tostring(k)
  local s = STAT[key]
  if s then return s end
  if key:find("SPELL") and key:find("HIT") then return "SPELL_HIT" end
  if key:find("SPELL") and key:find("CRIT") then return "SPELL_CRIT" end
  if key:find("STAMINA") then return "STA" end
  if key:find("INTELLECT") then return "INT" end
  if key:find("SPIRIT") then return "SPI" end
  if key:find("STRENGTH") then return "STR" end
  if key:find("AGILITY") then return "AGI" end
  if key:find("RANGED_ATTACK_POWER") then return "RAP" end
  if key:find("ATTACK_POWER") then return "AP" end
  if key:find("DAMAGE_PER_SECOND") then return "WEAPON_DPS" end
  if key:find("MANA_REGENERATION") or key:find("POWER_REGEN0") or key:find("MP5") then return "MP5" end
  if key:find("SPELL") and (key:find("POWER") or key:find("DAMAGE")) then return "SP" end
  if key:find("RESISTANCE0") or key == "ARMOR" then return "ARMOR" end
end

function G.Score(item, level)
  level = level or M.Level()
  local W = G.Weights(level)
  local st = M.ItemStats(item)
  local _, _, classID, subID = M.ItemInstant(item)
  local s, has = 0, {}
  for k, v in pairs(st) do
    if type(v) == "number" then
      local key = StatKey(k)
      if key == "WEAPON_DPS" then
        local w
        if classID == 2 and subID == 19 then w = (level >= 30 and W.WAND_DPS_30) or W.WAND_DPS
        elseif classID == 2 and (subID == 2 or subID == 3 or subID == 18 or subID == 16) then w = W.RANGED_DPS
        else w = W.DPS end
        s = s + v * (w or 0)
      elseif key == "RAP" then
        s = s + v * (W.RAP or W.AP or 0)
      elseif key == "SP" and W.SCHOOL and tostring(k):find(W.SCHOOL) then
        has.SP = true
        s = s + v * (W.SCHOOL_W or W.SP or 0)
      elseif key then
        has[key] = true
        s = s + v * (W[key] or 0)
      end
    end
  end
  local needSP = not has.SP and ((W.SP or 0) > 0 or (W.SCHOOL_W or 0) > 0)
  local needPct = not (has.SPELL_HIT or has.SPELL_CRIT or has.HIT or has.CRIT)
    and ((W.SPELL_HIT or 0) > 0 or (W.SPELL_CRIT or 0) > 0 or (W.HIT or 0) > 0 or (W.CRIT or 0) > 0)
  if needSP or needPct then
    local x = TooltipExtras(item, W)
    if needSP then s = s + x.SP * (W.SP or 0) + x.SCHOOL * (W.SCHOOL_W or W.SP or 0) end
    if needPct then
      s = s + x.SPELL_HIT * (W.SPELL_HIT or 0) + x.SPELL_CRIT * (W.SPELL_CRIT or 0)
        + x.HIT * (W.HIT or 0) + x.CRIT * (W.CRIT or 0)
    end
  end
  return s
end

function G.SlotScore(slot, level)
  local link = GetInventoryItemLink and GetInventoryItemLink("player", slot)
  return link and G.Score(link, level) or 0, link
end

local function MainIsTwoHand()
  local link = GetInventoryItemLink and GetInventoryItemLink("player", 16)
  if not link then return false end
  local _, loc = M.ItemInstant(link)
  return loc == "INVTYPE_2HWEAPON"
end

-- ¿Tu clase lo puede llevar alguna vez? (armadura, escudo, reliquia, armas que aprende, mano izquierda)
function G.ClassCanUse(item)
  local _, loc, classID, subID = M.ItemInstant(item)
  if not (loc and LOC[loc]) then return false end
  local cls = M.Class() or ""
  if classID == 4 then
    if subID == 6 then return SHIELD[cls] == true end
    if subID and subID >= 7 and subID <= 11 then return RELIC[cls] == subID end
    if subID and subID >= 1 and subID <= 4 and subID > ArmorMax() then return false end
  elseif classID == 2 then
    if WEAPONS[cls] and not Contains(WEAPONS[cls], subID) then return false end
    if loc == "INVTYPE_WEAPONOFFHAND" and not DUAL[cls] then return false end
  end
  return true
end

-- mejora (puntos), ranura, motivo ("no" = tu clase no lo usa; "nivel N"; aprende el arma; necesitas una mano),
-- puntos de lo que llevas en esa ranura.
function G.Delta(item, level)
  level = level or M.Level()
  local _, loc, classID, subID = M.ItemInstant(item)
  local slots = loc and LOC[loc]
  if not slots then return nil end
  if not G.ClassCanUse(item) then return nil, slots[1], "no" end
  local score = G.Score(item, level)
  local cur
  local why
  if loc == "INVTYPE_2HWEAPON" then
    cur = G.SlotScore(16, level) + G.SlotScore(17, level)
  elseif OFFHAND[loc] and MainIsTwoHand() then
    -- Para llevarlo hay que soltar el arma de dos manos.
    cur = G.SlotScore(16, level)
    why = L.GEAR_NEEDS_ONEHAND or "necesitas un arma de una mano"
  elseif #slots == 2 then
    cur = math.min(G.SlotScore(slots[1], level), G.SlotScore(slots[2], level))
  else
    cur = G.SlotScore(slots[1], level)
  end
  local _, _, _, _, minLevel = M.ItemInfo(item)
  if (minLevel or 0) > level then why = string.format(L.MOD_AT_LEVEL or "nivel %d", minLevel) end
  if classID == 2 and not HasWeaponSkill(subID) then
    local key = SKILL_KEY[subID]
    why = (key and L["GEAR_LEARN_" .. key]) or L.MOD_GEAR_LEARN_SKILL or "aprende esa arma"
  end
  return score - cur, slots[1], why, cur, score
end

-- Porcentaje de mejora respecto a lo que llevas (nil si la ranura está vacía o no puntúa).
function G.Percent(d, cur)
  if not d or not cur or cur < 1 then return nil end
  return math.floor(d / cur * 100 + (d >= 0 and 0.5 or -0.5))
end

function G.IsUpgrade(link)
  local ok, d, _, why = pcall(G.Delta, link)
  return ok and d ~= nil and d > 0.5 and why ~= "no"
end

-- Texto corto de la mejora: «+12% para tu build», «ranura vacía», «-8% …», «igual».
function G.GainText(d, cur)
  if not d then return nil end
  local pct = G.Percent(d, cur)
  if d > 0.5 then
    if pct then return string.format("|cff7cc66f" .. (L.GEAR_PCT_UP or "+%d%% para tu build") .. "|r", pct) end
    return "|cff7cc66f" .. (L.GEAR_EMPTY_UP or "mejora para tu build: no llevas nada ahí") .. "|r"
  elseif d < -0.5 then
    return string.format("|cffff8040" .. (L.GEAR_PCT_DOWN or "%d%% para tu build") .. "|r", pct or math.floor(d - 0.5))
  end
  return "|cffcccccc" .. (L.GEAR_SAME or "igual que lo tuyo para tu build") .. "|r"
end

function G.DeltaText(d, slot, why, cur)
  if why == "no" then return "|cff888888" .. (L.GEAR_USELESS or "no te sirve: tu clase no lo puede llevar") .. "|r" end
  local txt = G.GainText(d, cur)
  if not txt then return nil end
  if why then txt = txt .. " · " .. why end
  return txt
end

------------------------------------------------------------------------
-- Descripción de objetos: una línea «Senda: +12% para tu build»
------------------------------------------------------------------------
local function OnTooltipItem(tt)
  if M.Opt("mod_gear_tips") == false or not tt or not tt.GetItem then return end
  local ok, _, link = pcall(tt.GetItem, tt)
  if not ok or not link then return end
  local ok2, d, slot, why, cur = pcall(G.Delta, link)
  if not ok2 then return end
  local txt = G.DeltaText(d, slot, why, cur)
  if txt then tt:AddLine("Senda: " .. txt) end
end
G.OnTooltipItem = OnTooltipItem

local hooked = false
local function HookTooltips()
  if hooked then return end
  hooked = true
  if TooltipDataProcessor and TooltipDataProcessor.AddTooltipPostCall and Enum and Enum.TooltipDataType then
    TooltipDataProcessor.AddTooltipPostCall(Enum.TooltipDataType.Item, function(tt)
      if tt == GameTooltip or tt == ItemRefTooltip then pcall(OnTooltipItem, tt) end
    end)
  elseif GameTooltip and GameTooltip.HookScript then
    pcall(GameTooltip.HookScript, GameTooltip, "OnTooltipSetItem", OnTooltipItem)
    if ItemRefTooltip then pcall(ItemRefTooltip.HookScript, ItemRefTooltip, "OnTooltipSetItem", OnTooltipItem) end
  end
end

------------------------------------------------------------------------
-- Recompensas de misión
------------------------------------------------------------------------
local function RewardFrame(i)
  local f = _G["QuestInfoRewardsFrameQuestInfoItem" .. i] or _G["QuestInfoItem" .. i]
  if not f and QuestInfoRewardsFrame and type(QuestInfoRewardsFrame.RewardButtons) == "table" then
    f = QuestInfoRewardsFrame.RewardButtons[i]
  end
  return f
end

local function ClearMarks()
  for i = 1, 10 do
    local f = RewardFrame(i)
    if f and f.sendaMark then f.sendaMark:Hide() end
  end
end

local function Mark(i, text)
  local f = RewardFrame(i)
  if not f then return end
  if not f.sendaMark then
    f.sendaMark = f:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    f.sendaMark:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", -2, 2)
  end
  f.sendaMark:SetText(text)
  f.sendaMark:Show()
end

-- Mejor recompensa para tu build: primero lo que puedes ponerte ya; si nada de eso te mejora, lo que pide nivel o
-- aprender el arma (con el motivo); si nada te mejora, la que más vale en el vendedor. Nunca lo que tu clase no lleva.
-- Devuelve best, bestD, bestI, bestWhy, cash, cashV, cashI, bestCur.
function G.PickReward(getLink, n)
  local now, later = { d = 0.5 }, { d = 0.5 }
  local cash, cashV, cashI = nil, -1, nil
  for i = 1, n do
    local link = getLink(i)
    if link then
      local ok, d, _, why, cur = pcall(G.Delta, link)
      if ok and d and why ~= "no" then
        local slot = (why == nil) and now or later
        if d > slot.d then slot.link, slot.d, slot.i, slot.why, slot.cur = link, d, i, why, cur end
      end
      local price = select(11, M.ItemInfo(link)) or 0
      if price > cashV then cash, cashV, cashI = link, price, i end
    end
  end
  local b = now.link and now or later
  return b.link, b.link and b.d or 0.5, b.i, b.why, cash, cashV, cashI, b.cur
end

local lastRewardMsg
local function OnQuestRewards()
  ClearMarks()
  if M.Opt("mod_gear_tips") == false or not GetNumQuestChoices then return end
  local n = GetNumQuestChoices() or 0
  if n < 2 then return end
  local best, d, bi, why, cash, cv, ci, cur = G.PickReward(function(i) return GetQuestItemLink("choice", i) end, n)
  local msg
  if best then
    Mark(bi, "|cff7cc66f" .. (L.MOD_GEAR_BEST or "MEJOR") .. "|r")
    msg = string.format(L.GEAR_REWARD or "Recompensa recomendada para tu build: %s (%s).", best,
      M.StripColors(G.DeltaText(d, nil, why, cur)))
  elseif cash and cv > 0 then
    Mark(ci, "|cffffd100" .. (L.MOD_GEAR_SELL or "VENDER") .. "|r")
    msg = string.format(L.MOD_GEAR_REWARD_CASH or "Ninguna te mejora. Coge %s: vale %s en el vendedor.", cash, M.Money(cv))
  end
  if msg and msg ~= lastRewardMsg then lastRewardMsg = msg; M.Print(msg) end
end
G.OnQuestRewards = OnQuestRewards

------------------------------------------------------------------------
-- Cachés: banco y recetas
------------------------------------------------------------------------
local function Equippable(link)
  local _, loc = M.ItemInstant(link)
  return loc and LOC[loc] ~= nil
end

local bankOpen = false
local function CacheBankGear()
  local links = {}
  local bags = { BANK_CONTAINER or -1 }
  local first = (NUM_BAG_SLOTS or 4) + 1
  for b = first, first + (NUM_BANKBAGSLOTS or 7) do table.insert(bags, b) end
  for _, bag in ipairs(bags) do
    for slot = 1, M.BagSlots(bag) do
      local it = M.SlotInfo(bag, slot)
      if it and it.link and Equippable(it.link) then table.insert(links, it.link) end
    end
  end
  M.DB().bankGear = links
end

local function CacheRecipes()
  if not (C_TradeSkillUI and C_TradeSkillUI.GetAllRecipeIDs and C_TradeSkillUI.GetRecipeInfo) then return end
  local ok, ids = pcall(C_TradeSkillUI.GetAllRecipeIDs)
  if not ok or type(ids) ~= "table" or #ids == 0 then return end
  local pname
  if C_TradeSkillUI.GetBaseProfessionInfo then
    local okb, base = pcall(C_TradeSkillUI.GetBaseProfessionInfo)
    if okb and type(base) == "table" then pname = base.professionName end
  end
  if not pname and C_TradeSkillUI.GetChildProfessionInfo then
    local okc, ch = pcall(C_TradeSkillUI.GetChildProfessionInfo)
    if okc and type(ch) == "table" then pname = ch.parentProfessionName or ch.professionName end
  end
  local list = {}
  for _, rid in ipairs(ids) do
    local okr, info = pcall(C_TradeSkillUI.GetRecipeInfo, rid)
    if okr and type(info) == "table" and info.learned ~= false then
      local link
      if C_TradeSkillUI.GetRecipeOutputItemData then
        local oko, out = pcall(C_TradeSkillUI.GetRecipeOutputItemData, rid)
        if oko and type(out) == "table" then
          link = out.hyperlink or (out.itemID and (select(2, M.ItemInfo(out.itemID)) or ("item:" .. out.itemID)))
        end
      end
      if not link and C_TradeSkillUI.GetRecipeItemLink then
        local okl, l = pcall(C_TradeSkillUI.GetRecipeItemLink, rid)
        if okl then link = l end
      end
      if link and Equippable(link) then table.insert(list, link) end
    end
  end
  local db = M.DB()
  db.recipes = db.recipes or {}
  db.recipes[pname or "?"] = list
end

-- Recompensas del diario de misiones: { link, quest }
local function QuestLogRewards()
  local out = {}
  if M.InCombat() then return out end
  if C_QuestLog and C_QuestLog.GetNumQuestLogEntries and C_QuestLog.GetInfo and GetNumQuestLogChoices and GetQuestLogItemLink then
    local prev = C_QuestLog.GetSelectedQuest and C_QuestLog.GetSelectedQuest()
    local okN, n = pcall(C_QuestLog.GetNumQuestLogEntries)
    for i = 1, (okN and n or 0) do
      local ok, info = pcall(C_QuestLog.GetInfo, i)
      if ok and type(info) == "table" and not info.isHeader and info.questID then
        if C_QuestLog.SetSelectedQuest then pcall(C_QuestLog.SetSelectedQuest, info.questID) end
        local okc, nc = pcall(GetNumQuestLogChoices, info.questID, true)
        local okr, nr = false, 0
        if GetNumQuestLogRewards then okr, nr = pcall(GetNumQuestLogRewards, info.questID) end
        for kind, cnt in pairs({ choice = okc and nc or 0, reward = okr and nr or 0 }) do
          for j = 1, (tonumber(cnt) or 0) do
            local okl, link = pcall(GetQuestLogItemLink, kind, j, info.questID)
            if okl and link then table.insert(out, { link = link, quest = info.title or "?" }) end
          end
        end
      end
    end
    if prev and C_QuestLog.SetSelectedQuest then pcall(C_QuestLog.SetSelectedQuest, prev) end
  elseif GetNumQuestLogEntries and GetQuestLogTitle and SelectQuestLogEntry and GetNumQuestLogChoices and GetQuestLogItemLink then
    local prev = GetQuestLogSelection and GetQuestLogSelection()
    for i = 1, (GetNumQuestLogEntries() or 0) do
      local title, _, _, isHeader = GetQuestLogTitle(i)
      if title and not isHeader then
        SelectQuestLogEntry(i)
        for _, kind in ipairs({ "choice", "reward" }) do
          local cnt = (kind == "choice" and GetNumQuestLogChoices() or (GetNumQuestLogRewards and GetNumQuestLogRewards() or 0)) or 0
          for j = 1, cnt do
            local link = GetQuestLogItemLink(kind, j)
            if link then table.insert(out, { link = link, quest = title }) end
          end
        end
      end
    end
    if prev then SelectQuestLogEntry(prev) end
  end
  return out
end

------------------------------------------------------------------------
-- Mejoras disponibles: { link, d, slot, why, src, cur }
------------------------------------------------------------------------
function G.FindUpgrades()
  local ups, seen = {}, {}
  local function consider(link, src)
    if not link or seen[link] then return end
    seen[link] = true
    local ok, d, slot, why, cur = pcall(G.Delta, link)
    if ok and d and why ~= "no" and d > 0.5 then table.insert(ups, { link = link, d = d, slot = slot, why = why, src = src, cur = cur }) end
  end
  for _, it in ipairs(M.ScanBags()) do
    if it.link and Equippable(it.link) then consider(it.link, L.MOD_GEAR_IN_BAGS or "en tus bolsas") end
  end
  local db = M.DB()
  for _, link in ipairs(db.bankGear or {}) do consider(link, L.MOD_GEAR_IN_BANK or "en el banco") end
  for prof, list in pairs(db.recipes or {}) do
    for _, link in ipairs(list) do consider(link, string.format(L.MOD_GEAR_CRAFT or "te lo fabricas (%s)", prof)) end
  end
  local okq, rewards = pcall(QuestLogRewards)
  if okq then for _, r in ipairs(rewards) do consider(r.link, (L.MOD_GEAR_QUEST or "misión") .. ": " .. r.quest) end end
  table.sort(ups, function(a, b) return a.d > b.d end)
  return ups
end

local function EquipLine(link, d, cur, slot)
  local pct = G.Percent(d, cur)
  if pct then
    return string.format(L.GEAR_EQUIP_PCT or "Ponte %s: mejora un %d%% para tu build (%s, lo llevas en las bolsas).",
      link, pct, SLOTS[slot] or "?")
  end
  return string.format(L.GEAR_EQUIP_EMPTY or "Ponte %s: no llevas nada en %s (lo llevas en las bolsas).", link, SLOTS[slot] or "?")
end

-- Consejos breves para el asesor.
function G.Tips()
  local tips = {}
  local ok, ups = pcall(G.FindUpgrades)
  if not ok then return tips end
  local bySlot = {}
  local inBags = L.MOD_GEAR_IN_BAGS or "en tus bolsas"
  for _, u in ipairs(ups) do
    if not bySlot[u.slot] then
      bySlot[u.slot] = true
      if u.src == inBags and not u.why then
        table.insert(tips, EquipLine(u.link, u.d, u.cur, u.slot))
      elseif #tips < 4 then
        table.insert(tips, string.format(L.GEAR_TIP or "%s en %s: %s, %s%s.", M.StripColors(G.GainText(u.d, u.cur)),
          SLOTS[u.slot] or "?", u.link, u.src, u.why and (" (" .. u.why .. ")") or ""))
      end
    end
  end
  return tips
end

-- Dónde buscar (opcional): páginas con [[gear]] o [[item]] (general/gear-items.toml) from, to, id, src y,
-- opcionalmente, class (solo para esa clase).
local function WhereList()
  local out = {}
  local class = M.Class()
  for _, p in ipairs(M.Pages()) do
    for _, field in ipairs({ "gear", "item" }) do
      for _, w in ipairs(type(p[field]) == "table" and p[field] or {}) do
        if type(w) == "table" and w.id and (w.class == nil or w.class == "ANY" or w.class == class) then
          table.insert(out, w)
        end
      end
    end
  end
  return out
end

------------------------------------------------------------------------
-- Mejor pieza conocida para tu tramo (data/knowledge/<clase>/bis-forever.toml, tools/gen_bis.py)
------------------------------------------------------------------------
local function AreaName(id)
  if C_Map and C_Map.GetAreaInfo then
    local ok, n = pcall(C_Map.GetAreaInfo, id)
    if ok and type(n) == "string" and n ~= "" then return n end
  end
  return "#" .. tostring(id)
end

local function Tok(kind, id)
  local N = Senda.Names
  if N and N.Resolve then return N:Resolve("{" .. kind .. ":" .. id .. "}") end
  return "#" .. tostring(id)
end

-- De dónde sale una pieza de la lista, en palabras.
function G.BisSource(e)
  if e.quest then return string.format(L.GEAR_SRC_QUEST or "misión «%s»", Tok("quest", e.quest)) end
  if e.craft then
    local prof = e.prof and (L["PROF_" .. e.prof] or e.prof) or "?"
    return string.format(L.GEAR_SRC_CRAFT or "receta %s (%s %d)", Tok("spell", e.craft), prof, e.skill or 0)
  end
  if e.zone then
    local pct = string.format("%g", e.pct or 0)
    if e.npc and e.npc > 0 then
      return string.format(L.GEAR_SRC_DROP or "botín de %s en %s (%s %%)", Tok("npc", e.npc), AreaName(e.zone), pct)
    end
    return string.format(L.GEAR_SRC_DROP_ANY or "botín en %s (%s %%)", AreaName(e.zone), pct)
  end
  return "?"
end

-- Piezas de la lista para tu build y nivel: { e, from, to }.
function G.BisFor(level)
  level = level or M.Level()
  local key = G.BuildKey()
  local race = M.Race()
  local out = {}
  if not key then return out end
  for _, p in ipairs(M.Pages("bis")) do
    if p.class == M.Class() then
      for _, e in ipairs(type(p.bis) == "table" and p.bis or {}) do
        if e.build == key and level >= (e.from or 1) and level <= (e.to or 60) and (not e.race or e.race == race) then
          table.insert(out, e)
        end
      end
    end
  end
  table.sort(out, function(a, b) return (a.slot or 0) < (b.slot or 0) end)
  return out
end

------------------------------------------------------------------------
-- Aviso de mejoras nuevas en las bolsas
------------------------------------------------------------------------
local announced = {}
local function ScanBagsForUpgrades()
  if M.Opt("mod_gear_bagscan") == false or M.InCombat() then return end
  for _, it in ipairs(M.ScanBags()) do
    if it.link and not announced[it.link] and Equippable(it.link) then
      local ok, d, slot, why, cur = pcall(G.Delta, it.link)
      if ok and d and d > 0.5 and why == nil then
        announced[it.link] = true
        M.Print(EquipLine(it.link, d, cur, slot))
      end
    end
  end
end
G.ScanBagsForUpgrades = ScanBagsForUpgrades

------------------------------------------------------------------------
-- Pestaña
------------------------------------------------------------------------
local ui = {}

local function BuildLine(level)
  local key = G.BuildKey()
  if not key then return nil end
  local band = G.Band(level)
  local txt = string.format(L.GEAR_BUILD_LINE or "Tu build: %s", G.BuildLabel(key))
  if band then
    txt = txt .. " · " .. string.format(L.GEAR_BAND_LINE or "tramo %d-%d (pesos: %s)", band.from or 1, band.to or 60, band.ref or "?")
  end
  return txt
end

local function OtherBuild()
  local key = G.BuildKey()
  for _, b in ipairs(G.Builds()) do if b.key ~= key then return b.key end end
end

function G.Refresh()
  if not ui.doc then return end
  local level = M.Level()
  local nodes = { { t = "h1", text = L.MOD_GEAR_YOURS or "Tu equipo" } }
  local bl = BuildLine(level)
  if bl then table.insert(nodes, { t = "p", text = "|cffffd100" .. bl .. "|r", raw = true }) end
  if ui.switch then
    local other = OtherBuild()
    if other then
      ui.switch:SetText(string.format(L.GEAR_SWITCH or "Usar %s", G.BuildLabel(other)))
      ui.switch:Show()
    else
      ui.switch:Hide()
    end
  end
  for _, slot in ipairs(G.SLOT_ORDER) do
    local sc, link = G.SlotScore(slot)
    table.insert(nodes, { t = "row", raw = true, link = link,
      icon = (link and GetInventoryItemTexture and GetInventoryItemTexture("player", slot)) or "Interface\\PaperDoll\\UI-Backpack-EmptySlot",
      text = (SLOTS[slot] or "?") .. ": " .. (link or ("|cff888888" .. (L.MOD_EMPTY or "vacío") .. "|r")),
      right = link and string.format("|cffaaaaaa%d|r", math.floor(sc + 0.5)) or nil, desat = link == nil })
  end
  table.insert(nodes, { t = "h1", text = L.MOD_GEAR_UPGRADES or "Mejoras que puedes conseguir ya" })
  local ok, ups = pcall(G.FindUpgrades)
  if ok and #ups > 0 then
    for i, u in ipairs(ups) do
      if i > 15 then break end
      local _, _, _, _, icon = M.ItemInstant(u.link)
      local pct = G.Percent(u.d, u.cur)
      table.insert(nodes, { t = "row", raw = true, link = u.link, icon = icon, hl = (u.why == nil) and "good" or nil,
        text = u.link .. "\n|cffaaaaaa" .. (SLOTS[u.slot] or "?") .. " — " .. u.src .. "|r" .. (u.why and (" |cffff8040(" .. u.why .. ")|r") or ""),
        right = pct and string.format("|cff7cc66f+%d%%|r", pct) or string.format("|cff7cc66f+%d|r", math.floor(u.d + 0.5)) })
    end
  else
    table.insert(nodes, { t = "p", text = L.MOD_GEAR_NONE or "Nada mejor en bolsas, banco, recetas que conoces ni misiones del diario." })
  end
  local db = M.DB()
  if not db.bankGear then table.insert(nodes, { t = "p", text = "|cffaaaaaa" .. (L.MOD_OPEN_BANK or "Abre el banco una vez para que Senda cuente lo que guardas.") .. "|r", raw = true }) end
  if not db.recipes or not next(db.recipes) then
    table.insert(nodes, { t = "p", text = "|cffaaaaaa" .. (L.MOD_GEAR_OPEN_PROF or "Abre tus ventanas de profesión una vez para que Senda vea tus recetas.") .. "|r", raw = true })
  end

  -- Mejor pieza conocida para tu tramo
  local bis = G.BisFor(level)
  if #bis > 0 then
    table.insert(nodes, { t = "h1", text = L.GEAR_BIS_TITLE or "Mejor pieza conocida para tu tramo" })
    for _, e in ipairs(bis) do
      local name, link = M.ItemInfo(e.id)
      if not link then M.RequestItem(e.id) end
      local tag
      local equipped = GetInventoryItemID and (GetInventoryItemID("player", e.slot) == e.id
        or (e.slot == 11 and GetInventoryItemID("player", 12) == e.id) or (e.slot == 13 and GetInventoryItemID("player", 14) == e.id))
      if equipped then tag = "|cff7cc66f" .. (L.GEAR_BIS_HAVE or "ya la llevas") .. "|r"
      elseif not link then tag = "|cffaaaaaa(" .. (L.MOD_GEAR_LOADING or "pulsa Actualizar para valorarlo") .. ")|r"
      else
        local okd, d, _, why, cur = pcall(G.Delta, link)
        if okd and d and why ~= "no" then tag = G.GainText(d, cur) else tag = "" end
      end
      table.insert(nodes, { t = "row", raw = true, item = e.id, icon = M.ItemIcon(e.id),
        text = (name or ("#" .. e.id)) .. "\n|cffaaaaaa" .. (SLOTS[e.slot] or "?") .. " — " .. G.BisSource(e) .. "|r",
        right = tag })
    end
    table.insert(nodes, { t = "p", text = "|cffaaaaaa" .. (L.GEAR_BIS_NOTE or "Objetos de ForeverLevelingBiS (MIT); Senda elige con los pesos de tu build.") .. "|r", raw = true })
  end

  local where = WhereList()
  local rows = {}
  for _, w in ipairs(where) do
    if level >= (w.from or 1) - 3 and level <= (w.to or 60) then
      local name, link = M.ItemInfo(w.id)
      if not link then M.RequestItem(w.id) end
      local okd, d, _, why, cur = pcall(G.Delta, link or ("item:" .. w.id))
      if not (okd and why == "no") then
        local tag
        if not link then tag = "|cffaaaaaa(" .. (L.MOD_GEAR_LOADING or "pulsa Actualizar para valorarlo") .. ")|r"
        elseif okd and d and d > 0.5 then tag = G.GainText(d, cur)
        else tag = "|cffaaaaaa" .. (L.MOD_GEAR_NOT_UP or "no te mejora") .. "|r" end
        table.insert(rows, { d = (okd and d) or 0, node = { t = "row", raw = true, item = w.id, icon = M.ItemIcon(w.id),
          text = (name or ("#" .. w.id)) .. (w.src and ("\n|cffaaaaaa" .. w.src .. "|r") or "") .. M.StatusTag(w.status), right = tag } })
      end
    end
  end
  if #rows > 0 then
    table.insert(nodes, { t = "h1", text = L.MOD_GEAR_WHERE or "Dónde buscar más para tu nivel" })
    table.sort(rows, function(a, b) return a.d > b.d end)
    for _, r in ipairs(rows) do table.insert(nodes, r.node) end
  end
  local W = G.Weights(level)
  local parts = {}
  for k, v in pairs(W) do if type(v) == "number" and v > 0 then table.insert(parts, { k = k, v = v }) end end
  table.sort(parts, function(a, b) if a.v ~= b.v then return a.v > b.v end return a.k < b.k end)
  local txt = {}
  for _, p in ipairs(parts) do table.insert(txt, string.format("%s %.2f", p.k, p.v)) end
  table.insert(nodes, { t = "sp" })
  table.insert(nodes, { t = "p", text = "|cffaaaaaa" .. (L.MOD_GEAR_WEIGHTS or "Pesos por punto:") .. " " .. table.concat(txt, ", ") ..
    ". " .. (L.MOD_GEAR_HOVER or "Pasa el ratón por cualquier objeto para ver si te mejora.") .. "|r", raw = true })
  ui.doc:Set(nodes, true)
end

local function Build(parent)
  local bar, body = M.Toolbar(parent)
  local b = M.Button(bar, L.MOD_REFRESH or "Actualizar", 100, function() G.Refresh() end)
  b:SetPoint("LEFT", 6, 0)
  ui.switch = M.Button(bar, "", 150, function()
    local other = OtherBuild()
    if other and G.SetBuild(other) then
      M.Print(string.format(L.GEAR_BUILD_SET or "Equipo: ahora valoro para %s.", G.BuildLabel(other)))
      wipe(announced)
      G.Refresh()
    end
  end)
  ui.switch:SetPoint("LEFT", b, "RIGHT", 6, 0)
  ui.switch:Hide()
  ui.doc = M.Doc(body)
end

M.RegisterTab({ key = "gear", title = L.MOD_TAB_GEAR or "Equipo", icon = "Interface\\Icons\\INV_Chest_Cloth_17",
  order = 40, build = Build, refresh = G.Refresh })
M.RegisterOption({ key = "mod_gear_tips", label = L.MOD_OPT_GEAR_TIPS or "Valorar objetos (descripción y recompensas de misión)",
  type = "toggle", default = true })
M.RegisterOption({ key = "mod_gear_bagscan", label = L.MOD_OPT_GEAR_BAGSCAN or "Avisar de mejoras nuevas en las bolsas",
  type = "toggle", default = true })

-- /senda equipo [oso | felino]: build con la que se valora (druida) o la actual.
local BUILD_WORDS = { oso = "bear", bear = "bear", felino = "cat", gato = "cat", cat = "cat" }
local function SlashCmd(arg)
  arg = type(arg) == "string" and arg:lower():match("^%s*(%S*)") or ""
  local key = BUILD_WORDS[arg] or (arg ~= "" and arg) or nil
  if key then
    if G.SetBuild(key) then
      wipe(announced)
      M.Print(string.format(L.GEAR_BUILD_SET or "Equipo: ahora valoro para %s.", G.BuildLabel(key)))
      if ui.doc then G.Refresh() end
    else
      M.Print(L.GEAR_BUILD_UNKNOWN or "Esa build no es de tu clase.")
    end
    return
  end
  M.Print(BuildLine(M.Level()) or (L.GEAR_BUILD_NONE or "Tu clase no tiene pesos por build: Senda usa pesos generales."))
end
if Senda.Slash and Senda.Slash.Register then
  Senda.Slash:Register("equipo", SlashCmd, L.GEAR_SLASH_HELP)
end

M.OnReady(function() pcall(HookTooltips) end)
M.On("QUEST_COMPLETE", function() M.After(0.1, OnQuestRewards) end)
M.On("QUEST_DETAIL", function() M.After(0.1, OnQuestRewards) end)
M.On("QUEST_FINISHED", function() ClearMarks() end)
M.On("BANKFRAME_OPENED", function() bankOpen = true; pcall(CacheBankGear) end)
M.On("BANKFRAME_CLOSED", function() bankOpen = false end)
M.On("PLAYERBANKSLOTS_CHANGED", function() if bankOpen then M.Debounce("gear-bank", 0.5, CacheBankGear) end end)
M.On("TRADE_SKILL_SHOW", function() M.After(0.5, CacheRecipes) end)
M.On("TRADE_SKILL_LIST_UPDATE", function() M.Debounce("gear-recipes", 0.5, CacheRecipes) end)
M.On("TRADE_SKILL_DATA_SOURCE_CHANGED", function() M.Debounce("gear-recipes", 0.5, CacheRecipes) end)
M.On("BAG_UPDATE_DELAYED", function()
  M.Debounce("gear-bagscan", 1.5, ScanBagsForUpgrades)
  if bankOpen then M.Debounce("gear-bank", 0.5, CacheBankGear) end
end)
M.On("PLAYER_LEVEL_UP", function() Invalidate(); wipe(announced) end)

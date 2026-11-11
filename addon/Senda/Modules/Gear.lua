-- Senda / Modules / Gear
-- Valoración de equipo para subir de nivel:
--   · línea «Senda: Mejora +N» en la descripción de los objetos
--   · marca la mejor recompensa de misión (o la que más vale si ninguna te mejora)
--   · busca mejoras en bolsas, banco (caché), recetas que conoces y recompensas del diario
-- Pesos por clase: los de una página de conocimiento con el campo `weights` si existe; si no, la tabla de abajo.
local ADDON, Senda = ...
local M = Senda.Mod
if not M then return end
local L = M.L

local G = {}
Senda.Modules.Gear = G

------------------------------------------------------------------------
-- Pesos por punto (más alto = más importante). Reserva si el conocimiento no trae `weights`.
-- SP = poder con hechizos; SCHOOL/SCHOOL_W = escuela preferida; MP5 = maná cada 5 s;
-- DPS = DPS de arma cuerpo a cuerpo; RANGED_DPS = arco/fusil/ballesta; WAND_DPS(_30) = varita (desde el 30).
-- Brujo y mago: guías de Forever (Warcraft Tavern, 9 nov 2026), heredado del addon anterior.
------------------------------------------------------------------------
local WEIGHTS = {
  WARLOCK = { SP = 1.0, SCHOOL = "SHADOW", SCHOOL_W = 1.0, SPI = 0.5, INT = 0.45, STA = 0.35, MP5 = 0.6, ARMOR = 0.005, WAND_DPS = 1.5, WAND_DPS_30 = 0.6 },
  MAGE    = { SP = 1.0, SCHOOL = "FROST",  SCHOOL_W = 1.0, INT = 0.6, MP5 = 0.6, STA = 0.4, SPI = 0.3, ARMOR = 0.005, WAND_DPS = 1.2, WAND_DPS_30 = 1.0 },
  PRIEST  = { SP = 1.0, SCHOOL = "SHADOW", SCHOOL_W = 1.0, INT = 0.55, SPI = 0.6, STA = 0.4, MP5 = 0.6, ARMOR = 0.005, WAND_DPS = 1.4, WAND_DPS_30 = 0.8 },
  WARRIOR = { STR = 1.0, AGI = 0.6, STA = 0.5, AP = 0.45, ARMOR = 0.01, DPS = 3.0, RANGED_DPS = 0.3 },
  ROGUE   = { AGI = 1.0, STR = 0.5, STA = 0.4, AP = 0.45, ARMOR = 0.005, DPS = 3.0, RANGED_DPS = 0.3 },
  HUNTER  = { AGI = 1.0, INT = 0.3, STA = 0.4, AP = 0.2, RAP = 0.45, SPI = 0.1, ARMOR = 0.005, DPS = 0.5, RANGED_DPS = 3.0 },
  PALADIN = { STR = 1.0, STA = 0.6, INT = 0.4, AGI = 0.4, SPI = 0.2, AP = 0.4, SP = 0.3, ARMOR = 0.01, DPS = 2.5 },
  SHAMAN  = { STR = 0.8, INT = 0.6, AGI = 0.5, STA = 0.5, SP = 0.6, MP5 = 0.6, AP = 0.35, ARMOR = 0.008, DPS = 2.5 },
  DRUID   = { STR = 0.6, AGI = 0.7, INT = 0.6, STA = 0.5, SPI = 0.4, SP = 0.6, AP = 0.3, ARMOR = 0.008, DPS = 0.5 },
}
local SCHOOL_WORDS = { SHADOW = { "sombra", "shadow" }, FROST = { "escarcha", "frost" }, FIRE = { "fuego", "fire" },
  ARCANE = { "arcano", "arcane" }, NATURE = { "naturaleza", "nature" }, HOLY = { "sagrado", "holy" } }

-- Armadura (subclase de objeto 4): 1 tela, 2 cuero, 3 malla, 4 placas, 6 escudo. Malla/placas desde el 40.
local ARMOR = {
  MAGE = 1, WARLOCK = 1, PRIEST = 1, ROGUE = 2, DRUID = 2,
  HUNTER = { 2, 3 }, SHAMAN = { 2, 3 }, WARRIOR = { 3, 4 }, PALADIN = { 3, 4 },
}
local SHIELD = { WARRIOR = true, PALADIN = true, SHAMAN = true }
local RELIC = { PALADIN = true, DRUID = true, SHAMAN = true }
-- Armas (subclase de objeto 2) que cada clase puede aprender.
local WEAPONS = {
  WARRIOR = { 0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 13, 15, 16, 18 },
  PALADIN = { 0, 1, 4, 5, 6, 7, 8 },
  HUNTER  = { 0, 1, 2, 3, 6, 7, 8, 10, 13, 15, 16, 18 },
  ROGUE   = { 2, 3, 4, 7, 13, 15, 16, 18 },
  PRIEST  = { 4, 10, 15, 19 },
  SHAMAN  = { 0, 1, 4, 5, 10, 13, 15 },
  MAGE    = { 7, 10, 15, 19 },
  WARLOCK = { 7, 10, 15, 19 },
  DRUID   = { 4, 5, 10, 13, 15 },
}
-- Habilidad de arma: subclase -> fragmentos del nombre (es/en). false = no necesita habilidad.
local WEAPON_SKILL = {
  [0] = { "hachas de una", "one-handed axe" }, [1] = { "hachas de dos", "two-handed axe" }, [2] = { "arco", "bow" },
  [3] = { "armas de fuego", "gun" }, [4] = { "mazas de una", "one-handed mace" }, [5] = { "mazas de dos", "two-handed mace" },
  [6] = { "armas de asta", "polearm" }, [7] = { "espadas de una", "one-handed sword" }, [8] = { "espadas de dos", "two-handed sword" },
  [10] = { "bast", "stave", "staff" }, [13] = { "puño", "fist" }, [15] = { "daga", "dagger" }, [16] = { "arrojadiza", "thrown" },
  [18] = { "ballesta", "crossbow" }, [19] = false,
}

local LOC = {
  INVTYPE_HEAD = { 1 }, INVTYPE_NECK = { 2 }, INVTYPE_SHOULDER = { 3 }, INVTYPE_CLOAK = { 15 },
  INVTYPE_CHEST = { 5 }, INVTYPE_ROBE = { 5 }, INVTYPE_WRIST = { 9 }, INVTYPE_HAND = { 10 },
  INVTYPE_WAIST = { 6 }, INVTYPE_LEGS = { 7 }, INVTYPE_FEET = { 8 }, INVTYPE_FINGER = { 11, 12 },
  INVTYPE_TRINKET = { 13, 14 }, INVTYPE_WEAPON = { 16 }, INVTYPE_WEAPONMAINHAND = { 16 },
  INVTYPE_2HWEAPON = { 16 }, INVTYPE_HOLDABLE = { 17 }, INVTYPE_WEAPONOFFHAND = { 17 }, INVTYPE_SHIELD = { 17 },
  INVTYPE_RANGED = { 18 }, INVTYPE_RANGEDRIGHT = { 18 }, INVTYPE_THROWN = { 18 }, INVTYPE_RELIC = { 18 },
}
G.LOC = LOC

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
-- Pesos
------------------------------------------------------------------------
local cachedW
function G.Weights()
  if cachedW then return cachedW end
  for _, p in ipairs(M.Pages()) do
    if type(p.weights) == "table" and next(p.weights) then cachedW = p.weights; return cachedW end
  end
  cachedW = WEIGHTS[M.Class() or ""] or { STA = 1, INT = 0.5, STR = 0.5, AGI = 0.5, SP = 0.5 }
  return cachedW
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
local function HasWeaponSkill(sub)
  local words = WEAPON_SKILL[sub]
  if words == false then return true end
  if not words or not (GetNumSkillLines and GetSkillLineInfo) then return true end
  if not skillCache then
    skillCache = {}
    local okN, n = pcall(GetNumSkillLines)
    for i = 1, (okN and n or 0) do
      local ok, name, isHeader = pcall(GetSkillLineInfo, i)
      if ok and name and not isHeader then table.insert(skillCache, name:lower()) end
    end
  end
  if #skillCache == 0 then return true end
  for _, n in ipairs(skillCache) do
    for _, w in ipairs(words) do if n:find(w, 1, true) then return true end end
  end
  return false
end

-- Poder con hechizos leído del texto del objeto si la API no lo da como estadística.
local function TooltipSpellPower(item)
  if not (C_TooltipInfo and C_TooltipInfo.GetHyperlink) or type(item) ~= "string" then return 0, 0 end
  local ok, data = pcall(C_TooltipInfo.GetHyperlink, item)
  if not ok or type(data) ~= "table" or not data.lines then return 0, 0 end
  local W = G.Weights()
  local want = SCHOOL_WORDS[W.SCHOOL or ""] or {}
  local sp, school = 0, 0
  for _, line in ipairs(data.lines) do
    local t = type(line.leftText) == "string" and line.leftText:lower() or ""
    local n = tonumber(t:match("(%d+)%D*$") or "")
    if n and (t:find("hechizo") or t:find("spell")) and (t:find("daño") or t:find("damage") or t:find("poder") or t:find("power")) then
      local isSchool = false
      for _, w in ipairs(want) do if t:find(w, 1, true) then isSchool = true end end
      if isSchool then school = school + n
      elseif not (t:find("cura") or t:find("sana") or t:find("heal")) or t:find("daño") or t:find("damage") then sp = sp + n end
    end
  end
  return sp, school
end

function G.Score(item)
  local W = G.Weights()
  local st = M.ItemStats(item)
  local _, _, classID, subID = M.ItemInstant(item)
  local level = M.Level()
  local s, hasSP = 0, false
  for k, v in pairs(st) do
    if type(v) == "number" then
      local key = tostring(k)
      if key:find("STAMINA") then s = s + v * (W.STA or 0)
      elseif key:find("INTELLECT") then s = s + v * (W.INT or 0)
      elseif key:find("SPIRIT") then s = s + v * (W.SPI or 0)
      elseif key:find("STRENGTH") then s = s + v * (W.STR or 0)
      elseif key:find("AGILITY") then s = s + v * (W.AGI or 0)
      elseif key:find("RANGED_ATTACK_POWER") then s = s + v * (W.RAP or W.AP or 0)
      elseif key:find("ATTACK_POWER") then s = s + v * (W.AP or 0)
      elseif key:find("DAMAGE_PER_SECOND") then
        local w
        if classID == 2 and subID == 19 then w = (level >= 30 and W.WAND_DPS_30) or W.WAND_DPS
        elseif classID == 2 and (subID == 2 or subID == 3 or subID == 18 or subID == 16) then w = W.RANGED_DPS
        else w = W.DPS end
        s = s + v * (w or 0)
      elseif key:find("MANA_REGENERATION") or key:find("POWER_REGEN0") or key:find("MP5") then s = s + v * (W.MP5 or 0)
      elseif key:find("SPELL") and (key:find("POWER") or key:find("DAMAGE")) then
        hasSP = true
        if W.SCHOOL and key:find(W.SCHOOL) then s = s + v * (W.SCHOOL_W or W.SP or 0) else s = s + v * (W.SP or 0) end
      elseif key:find("RESISTANCE0") or key == "ARMOR" then s = s + v * (W.ARMOR or 0) end
    end
  end
  if not hasSP and ((W.SP or 0) > 0 or (W.SCHOOL_W or 0) > 0) then
    local sp, school = TooltipSpellPower(item)
    s = s + sp * (W.SP or 0) + school * (W.SCHOOL_W or W.SP or 0)
  end
  return s
end

function G.SlotScore(slot)
  local link = GetInventoryItemLink and GetInventoryItemLink("player", slot)
  return link and G.Score(link) or 0, link
end

-- mejora (número), ranura, motivo ("no" = no te sirve; "nivel N"; "aprende X")
function G.Delta(item)
  local _, loc, classID, subID = M.ItemInstant(item)
  local slots = loc and LOC[loc]
  if not slots then return nil end
  local cls = M.Class() or ""
  if classID == 4 then
    if subID == 6 then if not SHIELD[cls] then return nil, slots[1], "no" end
    elseif subID and subID >= 7 and subID <= 11 then if not RELIC[cls] then return nil, slots[1], "no" end
    elseif subID and subID >= 1 and subID <= 4 and subID > ArmorMax() then return nil, slots[1], "no" end
  elseif classID == 2 then
    if WEAPONS[cls] and not Contains(WEAPONS[cls], subID) then return nil, slots[1], "no" end
  end
  local score = G.Score(item)
  local cur
  if loc == "INVTYPE_2HWEAPON" then
    cur = G.SlotScore(16) + G.SlotScore(17)
  elseif #slots == 2 then
    cur = math.min(G.SlotScore(slots[1]), G.SlotScore(slots[2]))
  else
    cur = G.SlotScore(slots[1])
  end
  local why
  local _, _, _, _, minLevel = M.ItemInfo(item)
  if (minLevel or 0) > M.Level() then why = string.format(L.MOD_AT_LEVEL or "nivel %d", minLevel) end
  if classID == 2 and not HasWeaponSkill(subID) then why = L.MOD_GEAR_LEARN_SKILL or "aprende esa arma" end
  return score - cur, slots[1], why
end

function G.IsUpgrade(link)
  local ok, d, _, why = pcall(G.Delta, link)
  return ok and d ~= nil and d > 0.5 and why ~= "no"
end

function G.DeltaText(d, slot, why)
  if why == "no" then return "|cff888888" .. (L.MOD_GEAR_USELESS or "No te sirve (tu clase no lo usa)") .. "|r" end
  if not d then return nil end
  local txt
  if d > 0.5 then txt = string.format("|cff7cc66f" .. (L.MOD_GEAR_UP or "Mejora +%d") .. "|r (%s)", math.floor(d + 0.5), SLOTS[slot] or "?")
  elseif d < -0.5 then txt = string.format("|cffff8040" .. (L.MOD_GEAR_DOWN or "Peor que lo tuyo (%d)") .. "|r", math.floor(d - 0.5))
  else txt = "|cffcccccc" .. (L.MOD_GEAR_SAME or "Igual que lo tuyo") .. "|r" end
  if why then txt = txt .. " · " .. why end
  return txt
end

------------------------------------------------------------------------
-- Descripción de objetos
------------------------------------------------------------------------
local function OnTooltipItem(tt)
  if M.Opt("mod_gear_tips") == false or not tt or not tt.GetItem then return end
  local ok, _, link = pcall(tt.GetItem, tt)
  if not ok or not link then return end
  local ok2, d, slot, why = pcall(G.Delta, link)
  if not ok2 then return end
  local txt = G.DeltaText(d, slot, why)
  if txt then tt:AddLine("Senda: " .. txt) end
end

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

-- Mejor recompensa para ti o, si ninguna te mejora, la que más vale.
function G.PickReward(getLink, n)
  local best, bestD, bestI, bestWhy = nil, 0.5, nil, nil
  local cash, cashV, cashI = nil, -1, nil
  for i = 1, n do
    local link = getLink(i)
    if link then
      local ok, d, _, why = pcall(G.Delta, link)
      if ok and d and why ~= "no" and d > bestD then best, bestD, bestI, bestWhy = link, d, i, why end
      local price = select(11, M.ItemInfo(link)) or 0
      if price > cashV then cash, cashV, cashI = link, price, i end
    end
  end
  return best, bestD, bestI, bestWhy, cash, cashV, cashI
end

local lastRewardMsg
local function OnQuestRewards()
  ClearMarks()
  if M.Opt("mod_gear_tips") == false or not GetNumQuestChoices then return end
  local n = GetNumQuestChoices() or 0
  if n < 2 then return end
  local best, d, bi, why, cash, cv, ci = G.PickReward(function(i) return GetQuestItemLink("choice", i) end, n)
  local msg
  if best then
    Mark(bi, "|cff7cc66f" .. (L.MOD_GEAR_BEST or "MEJOR") .. "|r")
    msg = string.format(L.MOD_GEAR_REWARD or "Recompensa recomendada: %s (mejora +%d%s).", best, math.floor(d + 0.5), why and (", " .. why) or "")
  elseif cash and cv > 0 then
    Mark(ci, "|cffffd100" .. (L.MOD_GEAR_SELL or "VENDER") .. "|r")
    msg = string.format(L.MOD_GEAR_REWARD_CASH or "Ninguna te mejora. Coge %s: vale %s en el vendedor.", cash, M.Money(cv))
  end
  if msg and msg ~= lastRewardMsg then lastRewardMsg = msg; M.Print(msg) end
end

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
-- Mejoras disponibles: { link, d, slot, why, src }
------------------------------------------------------------------------
function G.FindUpgrades()
  local ups, seen = {}, {}
  local function consider(link, src)
    if not link or seen[link] then return end
    seen[link] = true
    local ok, d, slot, why = pcall(G.Delta, link)
    if ok and d and why ~= "no" and d > 0.5 then table.insert(ups, { link = link, d = d, slot = slot, why = why, src = src }) end
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
        table.insert(tips, string.format(L.MOD_GEAR_EQUIP or "Ponte %s: mejora +%d en %s (lo llevas en las bolsas).", u.link, math.floor(u.d + 0.5), SLOTS[u.slot] or "?"))
      elseif #tips < 4 then
        table.insert(tips, string.format(L.MOD_GEAR_TIP or "Mejora +%d en %s: %s, %s%s.", math.floor(u.d + 0.5), SLOTS[u.slot] or "?", u.link, u.src, u.why and (" (" .. u.why .. ")") or ""))
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
-- Aviso de mejoras nuevas en las bolsas
------------------------------------------------------------------------
local announced = {}
local function ScanBagsForUpgrades()
  if M.Opt("mod_gear_bagscan") == false or M.InCombat() then return end
  for _, it in ipairs(M.ScanBags()) do
    if it.link and not announced[it.link] and Equippable(it.link) then
      local ok, d, slot, why = pcall(G.Delta, it.link)
      if ok and d and d > 0.5 and why == nil then
        announced[it.link] = true
        M.Print(string.format(L.MOD_GEAR_EQUIP or "Ponte %s: mejora +%d en %s (lo llevas en las bolsas).", it.link, math.floor(d + 0.5), SLOTS[slot] or "?"))
      end
    end
  end
end

------------------------------------------------------------------------
-- Pestaña
------------------------------------------------------------------------
local ui = {}

function G.Refresh()
  if not ui.doc then return end
  local level = M.Level()
  local nodes = { { t = "h1", text = L.MOD_GEAR_YOURS or "Tu equipo" } }
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
      table.insert(nodes, { t = "row", raw = true, link = u.link, icon = icon, hl = (u.why == nil) and "good" or nil,
        text = u.link .. "\n|cffaaaaaa" .. (SLOTS[u.slot] or "?") .. " — " .. u.src .. "|r" .. (u.why and (" |cffff8040(" .. u.why .. ")|r") or ""),
        right = string.format("|cff7cc66f+%d|r", math.floor(u.d + 0.5)) })
    end
  else
    table.insert(nodes, { t = "p", text = L.MOD_GEAR_NONE or "Nada mejor en bolsas, banco, recetas que conoces ni misiones del diario." })
  end
  local db = M.DB()
  if not db.bankGear then table.insert(nodes, { t = "p", text = "|cffaaaaaa" .. (L.MOD_OPEN_BANK or "Abre el banco una vez para que Senda cuente lo que guardas.") .. "|r", raw = true }) end
  if not db.recipes or not next(db.recipes) then
    table.insert(nodes, { t = "p", text = "|cffaaaaaa" .. (L.MOD_GEAR_OPEN_PROF or "Abre tus ventanas de profesión una vez para que Senda vea tus recetas.") .. "|r", raw = true })
  end
  local where = WhereList()
  local rows = {}
  for _, w in ipairs(where) do
    if level >= (w.from or 1) - 3 and level <= (w.to or 60) then
      local name, link = M.ItemInfo(w.id)
      if not link then M.RequestItem(w.id) end
      local okd, d, _, why = pcall(G.Delta, link or ("item:" .. w.id))
      if not (okd and why == "no") then
        local tag
        if not link then tag = "|cffaaaaaa(" .. (L.MOD_GEAR_LOADING or "pulsa Actualizar para valorarlo") .. ")|r"
        elseif okd and d and d > 0.5 then tag = string.format("|cff7cc66f+%d|r", math.floor(d + 0.5))
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
  local W = G.Weights()
  local parts = {}
  for k, v in pairs(W) do if type(v) == "number" then table.insert(parts, { k = k, v = v }) end end
  table.sort(parts, function(a, b) return a.v > b.v end)
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
  ui.doc = M.Doc(body)
end

M.RegisterTab({ key = "gear", title = L.MOD_TAB_GEAR or "Equipo", icon = "Interface\\Icons\\INV_Chest_Cloth_17",
  order = 40, build = Build, refresh = G.Refresh })
M.RegisterOption({ key = "mod_gear_tips", label = L.MOD_OPT_GEAR_TIPS or "Valorar objetos (descripción y recompensas de misión)",
  type = "toggle", default = true })
M.RegisterOption({ key = "mod_gear_bagscan", label = L.MOD_OPT_GEAR_BAGSCAN or "Avisar de mejoras nuevas en las bolsas",
  type = "toggle", default = true })

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
M.On("PLAYER_LEVEL_UP", function() cachedW = nil; wipe(announced) end)

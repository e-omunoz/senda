-- Game API mock (Mainline 12.x shapes): player/unit state, maps and positions, quest log, spells,
-- items/bags, merchant, trainer, macros/action bars, tooltips, chat, popups and the global frames.
-- Every API checks its arguments; misuse is recorded (Sim.apiErrors) and raised, because the addon wraps
-- most Blizzard calls in pcall and would otherwise hide the problem.
local Sim = Sim

Sim.apiErrors = {}
local function bad(fname, msg)
  local m = fname .. ": " .. msg
  local seen = false
  for _, e in ipairs(Sim.apiErrors) do if e == m then seen = true end end
  if not seen then
    Sim.apiErrors[#Sim.apiErrors + 1] = m
    Sim.Out("  !! API MISUSE " .. m .. "\n" .. debug.traceback("", 3))
  end
  error(m, 3)
end
-- Misuse that the client tolerates silently (wrong icon, bad texture path): recorded, not raised.
function Sim.Misuse(fname, msg)
  local m = fname .. ": " .. msg
  for _, e in ipairs(Sim.apiErrors) do if e == m then return end end
  Sim.apiErrors[#Sim.apiErrors + 1] = m
  Sim.Out("  !! API MISUSE " .. m)
end
local function iconArg(icon, fname)
  if icon == nil or type(icon) == "number" then return end
  if type(icon) ~= "string" then bad(fname, "icon must be a fileID or an icon name (got " .. type(icon) .. ")") end
  if not (icon:match("^[%w_%-]+$") or icon:find("\\", 1, true)) then
    Sim.Misuse(fname, "invalid icon '" .. icon .. "' (the macro gets the question mark)")
  end
end
local function num(v, fname, what) if type(v) ~= "number" then bad(fname, (what or "argument") .. " must be a number (got " .. type(v) .. ")") end return v end
local function str(v, fname, what) if type(v) ~= "string" then bad(fname, (what or "argument") .. " must be a string (got " .. type(v) .. ")") end return v end

------------------------------------------------------------------------------
-- Player state
------------------------------------------------------------------------------

local RACES = {
  Gnome = { name = "Gnomo", id = 7 }, Human = { name = "Humano", id = 1 }, Dwarf = { name = "Enano", id = 3 },
  NightElf = { name = "Elfo de la noche", id = 4 },
}
local CLASSES = {
  WARLOCK = { name = "Brujo", id = 9, power = 0 }, MAGE = { name = "Mago", id = 8, power = 0 },
  WARRIOR = { name = "Guerrero", id = 1, power = 1 }, PRIEST = { name = "Sacerdote", id = 5, power = 0 },
  DRUID = { name = "Druida", id = 11, power = 0 },
}

function Sim.SetupCharacter(cfg)
  local p = {
    name = cfg.name or "Pruebas", race = cfg.race or "Gnome", class = cfg.class or "WARLOCK",
    level = cfg.level or 1, faction = cfg.faction or "Alliance",
    map = cfg.map or 1426, x = cfg.x or 0.5, y = cfg.y or 0.5, facing = cfg.facing or 0,
    combat = cfg.combat or false, dead = false, ghost = false, onTaxi = false, corpse = nil,
    money = cfg.money or 1500, xp = 0, xpMax = 400,
    quests = {},      -- questID -> { objectives = { {text, type, finished, numFulfilled, numRequired} } }
    questOrder = {},  -- log order
    completed = cfg.completed or {}, -- questID -> true (flagged completed)
    spells = {},      -- spellID -> true
    bags = { [0] = {} },
    equipped = cfg.equipped or {},
    profs = cfg.profs or {},
    pet = false,
  }
  for _, id in ipairs(cfg.spells or {}) do p.spells[id] = true end
  for slot, it in pairs(cfg.bag or {}) do p.bags[0][slot] = { id = it[1], count = it[2] or 1 } end
  Sim.player = p
  Sim.party = {}
  Sim.npc = nil
  Sim.merchant = nil
  Sim.trainer = nil
  Sim.questChoices = nil
  Sim.macros = {}
  Sim.actions = {}
  Sim.cursor = nil
  Sim.purchases = {}
  Sim.learned = {}
  Sim.questCache = {}
  Sim.npcCache = {}
  Sim.shift = false
  return p
end

------------------------------------------------------------------------------
-- Maps: each zone is a rectangle (in yards) of its continent, so positions convert consistently.
------------------------------------------------------------------------------

Sim.MAPS = {
  [947]  = { name = "Azeroth", parent = 0, type = 0, continent = 0, n = 20000, w = 20000, sx = 40000, sy = 40000 },
  [1415] = { name = "Reinos del Este", parent = 947, type = 2, continent = 0, n = 10000, w = 10000, sx = 20000, sy = 20000 },
  [1414] = { name = "Kalimdor", parent = 947, type = 2, continent = 1, n = 10000, w = 10000, sx = 20000, sy = 20000 },
  [1438] = { name = "Teldrassil", parent = 1414, type = 3, continent = 1, n = 9000, w = 1000, sx = 5091, sy = 3393 },
  [1426] = { name = "Dun Morogh", parent = 1415, type = 3, continent = 0, n = 2000, w = 2500, sx = 4925, sy = 3283 },
  [1455] = { name = "Forjaz", parent = 1426, type = 3, continent = 0, n = 1200, w = 900, sx = 790, sy = 527 },
  [1432] = { name = "Loch Modan", parent = 1415, type = 3, continent = 0, n = 1000, w = -2000, sx = 2758, sy = 1839 },
  [1429] = { name = "Bosque de Elwynn", parent = 1415, type = 3, continent = 0, n = -7000, w = 1500, sx = 3470, sy = 2314 },
  [1453] = { name = "Ventormenta", parent = 1429, type = 3, continent = 0, n = -7500, w = 1200, sx = 1737, sy = 1158 },
  [1436] = { name = "Páramos de Poniente", parent = 1415, type = 3, continent = 0, n = -9500, w = 2500, sx = 3500, sy = 2333 },
}
local function mapData(id)
  if type(id) ~= "number" then return nil end
  local m = Sim.MAPS[id]
  if m then return m end
  -- Unknown zone of the Eastern Kingdoms: own rectangle far from the others.
  m = { name = "Zona #" .. id, parent = 1415, type = 3, continent = 0, n = -9000 + (id % 50) * 300, w = -6000 + (id % 37) * 300, sx = 3000, sy = 2000 }
  Sim.MAPS[id] = m
  return m
end
Sim.MapData = mapData

local Vector2D = {}
Vector2D.__index = Vector2D
function Vector2D:GetXY() return self.x, self.y end
function Vector2D:SetXY(x, y) self.x, self.y = x, y end
function CreateVector2D(x, y) return setmetatable({ x = x, y = y }, Vector2D) end

local function toWorld(map, x, y)
  local m = mapData(map)
  return m.continent, m.n - y * m.sy, m.w - x * m.sx
end
local function fromWorld(map, wn, ww)
  local m = mapData(map)
  return (m.w - ww) / m.sx, (m.n - wn) / m.sy
end

C_Map = {}
function C_Map.GetBestMapForUnit(unit)
  str(unit, "C_Map.GetBestMapForUnit", "unit")
  if unit ~= "player" then return nil end
  if Sim.player.instance then return nil end
  return Sim.player.map
end
function C_Map.GetPlayerMapPosition(map, unit)
  num(map, "C_Map.GetPlayerMapPosition", "uiMapID")
  str(unit, "C_Map.GetPlayerMapPosition", "unit")
  local p = Sim.player
  if unit ~= "player" or p.instance then return nil end
  if map == p.map then return CreateVector2D(p.x, p.y) end
  local c, wn, ww = toWorld(p.map, p.x, p.y)
  if mapData(map).continent ~= c then return nil end
  return CreateVector2D(fromWorld(map, wn, ww))
end
function C_Map.GetMapInfo(map)
  num(map, "C_Map.GetMapInfo", "uiMapID")
  local m = mapData(map)
  return { mapID = map, name = m.name, mapType = m.type, parentMapID = m.parent, flags = 0 }
end
function C_Map.GetWorldPosFromMapPos(map, pos)
  num(map, "C_Map.GetWorldPosFromMapPos", "uiMapID")
  if type(pos) ~= "table" or type(pos.GetXY) ~= "function" then bad("C_Map.GetWorldPosFromMapPos", "mapPosition must be a Vector2D") end
  local x, y = pos:GetXY()
  num(x, "C_Map.GetWorldPosFromMapPos", "mapPosition.x"); num(y, "C_Map.GetWorldPosFromMapPos", "mapPosition.y")
  local c, wn, ww = toWorld(map, x, y)
  return c, CreateVector2D(wn, ww)
end
function C_Map.GetMapPosFromWorldPos(continent, pos, overrideMap)
  num(continent, "C_Map.GetMapPosFromWorldPos", "continentID")
  if type(pos) ~= "table" or type(pos.GetXY) ~= "function" then bad("C_Map.GetMapPosFromWorldPos", "worldPosition must be a Vector2D") end
  local map = overrideMap or Sim.player.map
  if mapData(map).continent ~= continent then return nil end
  local wn, ww = pos:GetXY()
  local x, y = fromWorld(map, wn, ww)
  return map, CreateVector2D(x, y)
end
function C_Map.GetMapWorldSize(map)
  num(map, "C_Map.GetMapWorldSize", "uiMapID")
  local m = mapData(map)
  return m.sx, m.sy
end

function GetPlayerFacing()
  if Sim.player.instance then return nil end
  return Sim.player.facing
end
function GetZoneText() return mapData(Sim.player.map).name end
GetRealZoneText = GetZoneText
function GetSubZoneText() return "" end
function GetMinimapZoneText() return GetZoneText() end
function GetBindLocation() return Sim.player.bind or "Kharanos" end
-- player.instance: nil (outside) or the instance type ("party", "raid", "pvp", "arena"; true = "party").
function IsInInstance()
  local i = Sim.player.instance
  return i and true or false, i and (type(i) == "string" and i or "party") or "none"
end
function Sim.SetInstance(kind)
  Sim.player.instance = kind or nil
  Sim.Fire("PLAYER_ENTERING_WORLD", false, false)
end

-- Moves the player (x, y in 0-1) and runs the frames in between.
function Sim.MoveTo(map, x, y)
  local p = Sim.player
  local changed = map ~= p.map
  p.map, p.x, p.y = map, x, y
  if changed then Sim.Fire("ZONE_CHANGED_NEW_AREA") end
end

C_DeathInfo = {}
function C_DeathInfo.GetCorpseMapPosition(map)
  num(map, "C_DeathInfo.GetCorpseMapPosition", "uiMapID")
  local c = Sim.player.corpse
  if not c then return nil end
  if map == c.map then return CreateVector2D(c.x, c.y) end
  local cont, wn, ww = toWorld(c.map, c.x, c.y)
  if mapData(map).continent ~= cont then return nil end
  local x, y = fromWorld(map, wn, ww)
  if x < 0 or x > 1 or y < 0 or y > 1 then return nil end
  return CreateVector2D(x, y)
end
function C_DeathInfo.GetGraveyardsForMap() return {} end
function C_DeathInfo.GetSelfResurrectOptions() return {} end

------------------------------------------------------------------------------
-- Units
------------------------------------------------------------------------------

local function isPlayerUnit(u) return u == "player" end
local function unitArg(u, fname) if type(u) ~= "string" then bad(fname, "unit must be a string (got " .. type(u) .. ")") end return u end

function UnitExists(u)
  unitArg(u, "UnitExists")
  if u == "player" then return true end
  if u == "pet" then return Sim.player.pet and true or false end
  local n = u:match("^party(%d)$")
  if n then return Sim.party[tonumber(n)] ~= nil end
  if u == "npc" or u == "questnpc" or u == "target" then return Sim.npc ~= nil end
  return false
end
local function partyOf(u) local n = u:match("^party(%d)$"); return n and Sim.party[tonumber(n)] end
function UnitIsPlayer(u) unitArg(u, "UnitIsPlayer"); return u == "player" or partyOf(u) ~= nil end
function GetRealmName() return Sim.realm or "Reino de Prueba" end
function UnitName(u)
  unitArg(u, "UnitName")
  if u == "player" then return Sim.player.name end
  local pm = partyOf(u)
  if pm then return pm.name end
  if (u == "npc" or u == "target") and Sim.npc then return Sim.npc.name or "PNJ" end
  return nil
end
function UnitClass(u)
  unitArg(u, "UnitClass")
  local token = u == "player" and Sim.player.class or (partyOf(u) and partyOf(u).class)
  if not token then return nil end
  local c = CLASSES[token] or { name = token, id = 0 }
  return c.name, token, c.id
end
function UnitRace(u)
  unitArg(u, "UnitRace")
  local token = u == "player" and Sim.player.race or (partyOf(u) and partyOf(u).race)
  if not token then return nil end
  local r = RACES[token] or { name = token, id = 0 }
  return r.name, token, r.id
end
function UnitLevel(u)
  unitArg(u, "UnitLevel")
  if u == "player" then return Sim.player.level end
  local pm = partyOf(u)
  if pm then return pm.level end
  return 0
end
function UnitFactionGroup(u)
  unitArg(u, "UnitFactionGroup")
  if u ~= "player" then return nil end
  return Sim.player.faction, Sim.player.faction == "Alliance" and "Alianza" or "Horda"
end
function UnitGUID(u)
  unitArg(u, "UnitGUID")
  if u == "player" then return "Player-1234-0A1B2C3D" end
  if (u == "npc" or u == "questnpc" or u == "target") and Sim.npc then
    return string.format("Creature-0-1234-0-5678-%d-0000ABCDEF", Sim.npc.id)
  end
  return nil
end
function UnitIsDeadOrGhost(u) unitArg(u, "UnitIsDeadOrGhost"); return u == "player" and (Sim.player.dead or Sim.player.ghost) or false end
function UnitIsDead(u) unitArg(u, "UnitIsDead"); return u == "player" and Sim.player.dead or false end
function UnitIsGhost(u) unitArg(u, "UnitIsGhost"); return u == "player" and Sim.player.ghost or false end
function UnitOnTaxi(u) unitArg(u, "UnitOnTaxi"); return u == "player" and Sim.player.onTaxi or false end
function UnitAffectingCombat(u) return u == "player" and Sim.player.combat or false end
function UnitXP(u) return Sim.player.xp end
function UnitXPMax(u) return Sim.player.xpMax end
function UnitStat(u, i) num(i, "UnitStat", "statIndex"); return 20, 20 + i, 0, 0 end
function UnitHealth(u) return 100 end
function UnitHealthMax(u) return 100 end
function UnitPower(u) return 100 end
function UnitPowerMax(u) return 100 end
function UnitPowerType(u)
  local c = CLASSES[Sim.player.class] or {}
  return c.power or 0, (c.power or 0) == 0 and "MANA" or "RAGE"
end
function GetUnitSpeed(u) unitArg(u, "GetUnitSpeed"); return Sim.player.speed or 0, 7, 7, 4.72 end
function InCombatLockdown() return Sim.player.combat end
function IsMounted() return false end
function IsResting() return false end
function GetSpellBonusDamage(school) num(school, "GetSpellBonusDamage", "school"); return 0 end
function GetMoney() return Sim.player.money end
function GetCoinTextureString(c)
  num(c, "GetCoinTextureString", "copper")
  return string.format("%dg %ds %dc", math.floor(c / 10000), math.floor(c / 100) % 100, c % 100)
end
GetMoneyString = GetCoinTextureString
function GetLocale() return Sim.locale or "esES" end
function GetBuildInfo() return "1.60.1", "70291", "Nov 4 2026", 16001, "", "", 16001 end
function GetServerTime() return time() end
function IsShiftKeyDown() return Sim.shift end
function IsControlKeyDown() return Sim.ctrl == true end
function IsAltKeyDown() return false end
function IsMouseButtonDown() return false end
function GetCursorPosition() return 960, 540 end
function PlaySound() end
function ReloadUI() Sim.Out("  (ReloadUI requested)") end

------------------------------------------------------------------------------
-- Quests
------------------------------------------------------------------------------

Sim.QUEST_TITLES = { [179] = "Avituallamiento enano", [3115] = "Memorando grabado", [233] = "Correo de Coldridge",
  [783] = "Una amenaza interior", [7] = "Kobolds en la cantera" }

local function questTitle(id)
  return Sim.QUEST_TITLES[id] or ("Misión " .. id)
end

C_QuestLog = {}
function C_QuestLog.GetTitleForQuestID(id)
  num(id, "C_QuestLog.GetTitleForQuestID", "questID")
  if Sim.player.quests[id] or Sim.questCache[id] then return questTitle(id) end
  return nil -- not cached yet: RequestLoadQuestByID + QUEST_DATA_LOAD_RESULT
end
function C_QuestLog.RequestLoadQuestByID(id)
  num(id, "C_QuestLog.RequestLoadQuestByID", "questID")
  if Sim.questCache[id] then return end
  C_Timer.After(0.2, function()
    if not Sim.questCache[id] then
      Sim.questCache[id] = true
      Sim.Fire("QUEST_DATA_LOAD_RESULT", id, true)
    end
  end)
end
function C_QuestLog.IsQuestFlaggedCompleted(id)
  num(id, "C_QuestLog.IsQuestFlaggedCompleted", "questID")
  return Sim.player.completed[id] == true
end
function C_QuestLog.IsOnQuest(id)
  num(id, "C_QuestLog.IsOnQuest", "questID")
  return Sim.player.quests[id] ~= nil
end
function C_QuestLog.GetLogIndexForQuestID(id)
  num(id, "C_QuestLog.GetLogIndexForQuestID", "questID")
  for i, q in ipairs(Sim.player.questOrder) do if q == id then return i end end
  return nil
end
local function allFinished(q)
  if #q.objectives == 0 then return q.complete == true end
  for _, o in ipairs(q.objectives) do if not o.finished then return false end end
  return true
end
function C_QuestLog.ReadyForTurnIn(id)
  num(id, "C_QuestLog.ReadyForTurnIn", "questID")
  local q = Sim.player.quests[id]
  return q ~= nil and allFinished(q)
end
function C_QuestLog.IsComplete(id)
  num(id, "C_QuestLog.IsComplete", "questID")
  local q = Sim.player.quests[id]
  return q ~= nil and allFinished(q)
end
function C_QuestLog.GetQuestObjectives(id)
  num(id, "C_QuestLog.GetQuestObjectives", "questID")
  local q = Sim.player.quests[id]
  if not q then return {} end
  local out = {}
  for i, o in ipairs(q.objectives) do
    out[i] = { text = o.text, type = o.type or "monster", finished = o.finished, numFulfilled = o.have, numRequired = o.need }
  end
  return out
end
function C_QuestLog.GetNumQuestLogEntries() return #Sim.player.questOrder, #Sim.player.questOrder end
function C_QuestLog.GetInfo(i)
  num(i, "C_QuestLog.GetInfo", "questLogIndex")
  local id = Sim.player.questOrder[i]
  if not id then return nil end
  return { title = questTitle(id), questID = id, isHeader = false, isHidden = false, level = Sim.player.level }
end
function C_QuestLog.IsFailed(id)
  num(id, "C_QuestLog.IsFailed", "questID")
  local q = Sim.player.quests[id]
  return q ~= nil and q.failed == true
end
-- Returns totalTime, elapsedTime (seconds) like the client; nothing when the quest has no timer.
function C_QuestLog.GetTimeAllowed(id)
  num(id, "C_QuestLog.GetTimeAllowed", "questID")
  local q = Sim.player.quests[id]
  if not (q and q.timer) then return nil end
  return q.timer.total, math.min(q.timer.total, Sim.time - q.timer.start)
end
function C_QuestLog.GetSelectedQuest() return Sim.selectedQuest or 0 end
function C_QuestLog.SetSelectedQuest(id) num(id, "C_QuestLog.SetSelectedQuest", "questID"); Sim.selectedQuest = id end
function C_QuestLog.IsUnitOnQuest(unit, id)
  unitArg(unit, "C_QuestLog.IsUnitOnQuest"); num(id, "C_QuestLog.IsUnitOnQuest", "questID")
  local pm = partyOf(unit)
  return pm and pm.quests and pm.quests[id] or false
end
function C_QuestLog.GetQuestIDForLogIndex(i) return Sim.player.questOrder[i] end
function C_QuestLog.GetQuestTagInfo() return nil end
function GetNumQuestLogChoices(questID, includeCurrencies)
  num(questID, "GetNumQuestLogChoices", "questID")
  return 0
end
function GetNumQuestLogRewards(questID) num(questID, "GetNumQuestLogRewards", "questID"); return 0 end
function GetQuestLogItemLink(kind, i, questID) str(kind, "GetQuestLogItemLink", "type"); num(i, "GetQuestLogItemLink", "index"); return nil end

-- Scenario helpers (fire the same events as the client).
function Sim.AcceptQuest(id, objectives, opts)
  local q = { objectives = {} }
  if opts and opts.timeLimit then q.timer = { total = opts.timeLimit, start = Sim.time } end
  for i, o in ipairs(objectives or {}) do
    q.objectives[i] = { text = o[1], have = 0, need = o[2] or 1, finished = false, type = o[3] }
  end
  Sim.player.quests[id] = q
  table.insert(Sim.player.questOrder, id)
  Sim.Fire("QUEST_ACCEPTED", id)
  Sim.Fire("QUEST_LOG_UPDATE")
end
function Sim.ProgressQuest(id, objIndex, have)
  local q = Sim.player.quests[id]
  local o = q.objectives[objIndex]
  o.have = math.min(have, o.need)
  o.finished = o.have >= o.need
  Sim.Fire("UNIT_QUEST_LOG_CHANGED", "player")
  Sim.Fire("QUEST_LOG_UPDATE")
end
function Sim.FinishQuestObjectives(id)
  local q = Sim.player.quests[id]
  for i, o in ipairs(q.objectives) do Sim.ProgressQuest(id, i, o.need) end
  if #q.objectives == 0 then q.complete = true; Sim.Fire("QUEST_LOG_UPDATE") end
end
function Sim.FailQuest(id)
  Sim.player.quests[id].failed = true
  Sim.Fire("QUEST_LOG_UPDATE")
end
-- Abandon: the quest leaves the log with no turn-in (QUEST_REMOVED only).
function Sim.AbandonQuest(id)
  Sim.player.quests[id] = nil
  for i, q in ipairs(Sim.player.questOrder) do if q == id then table.remove(Sim.player.questOrder, i); break end end
  Sim.Fire("QUEST_REMOVED", id, false)
  Sim.Fire("QUEST_LOG_UPDATE")
end
function Sim.TurnInQuest(id)
  Sim.player.quests[id] = nil
  for i, q in ipairs(Sim.player.questOrder) do if q == id then table.remove(Sim.player.questOrder, i); break end end
  Sim.player.completed[id] = true
  Sim.Fire("QUEST_TURNED_IN", id, 100, 25)
  Sim.Fire("QUEST_REMOVED", id, false)
  Sim.Fire("QUEST_LOG_UPDATE")
end

------------------------------------------------------------------------------
-- Spells
------------------------------------------------------------------------------

Sim.SPELL_NAMES = { [686] = "Descarga de las Sombras", [348] = "Inmolar", [172] = "Corrupción", [702] = "Maldición de debilidad",
  [688] = "Invocar diablillo", [687] = "Piel de demonio", [133] = "Bola de Fuego", [168] = "Armadura de escarcha",
  [5009] = "Varitas", [13262] = "Desencantar", [8690] = "Piedra de hogar", [6201] = "Crear piedra de salud",
  -- three ranks of one spell, for the action-bar rank upgrade
  [116] = "Descarga de Escarcha", [205] = "Descarga de Escarcha", [837] = "Descarga de Escarcha" }
-- spell id -> rank number (C_Spell.GetSpellSubtext says "Rango N"); spells not listed have no rank.
Sim.SPELL_RANKS = { [116] = 1, [205] = 2, [837] = 3 }
local function spellArg(s, fname)
  if type(s) ~= "number" and type(s) ~= "string" then bad(fname, "spell must be a spellID or a name (got " .. type(s) .. ")") end
  if type(s) == "string" then
    for id, n in pairs(Sim.SPELL_NAMES) do if n == s then return id end end
    return tonumber(s:match("^Hechizo (%d+)$"))
  end
  return s
end
local function spellName(id) return Sim.SPELL_NAMES[id] or ("Hechizo " .. id) end

C_Spell = {}
function C_Spell.GetSpellInfo(s)
  local id = spellArg(s, "C_Spell.GetSpellInfo")
  if not id or id <= 0 then return nil end
  return { name = spellName(id), iconID = 136000 + id % 1000, originalIconID = 136000 + id % 1000, castTime = 1500,
    minRange = 0, maxRange = 30, spellID = id, rank = nil }
end
function C_Spell.GetSpellName(s) local i = C_Spell.GetSpellInfo(s); return i and i.name end
function C_Spell.GetSpellTexture(s) local id = spellArg(s, "C_Spell.GetSpellTexture"); return id and (136000 + id % 1000) end
function C_Spell.GetSpellSubtext(s)
  local id = spellArg(s, "C_Spell.GetSpellSubtext")
  local r = id and Sim.SPELL_RANKS[id]
  if not r then return "" end
  return (Sim.locale == "enUS" and "Rank " or "Rango ") .. r
end
function C_Spell.IsSpellPassive(s) spellArg(s, "C_Spell.IsSpellPassive"); return false end
function C_Spell.PickupSpell(s)
  local id = spellArg(s, "C_Spell.PickupSpell")
  if Sim.player.combat then error("Interface action failed because of an AddOn") end
  Sim.cursor = { "spell", id }
end
function C_Spell.DoesSpellExist(s) return spellArg(s, "C_Spell.DoesSpellExist") ~= nil end

local function knownList()
  local ids = {}
  for id in pairs(Sim.player.spells) do ids[#ids + 1] = id end
  table.sort(ids)
  return ids
end
C_SpellBook = {}
local function knows(id) return Sim.knowAll or Sim.player.spells[id] == true end
function C_SpellBook.IsSpellKnown(id, isPet) num(id, "C_SpellBook.IsSpellKnown", "spellID"); return knows(id) end
function C_SpellBook.IsSpellInSpellBook(id) num(id, "C_SpellBook.IsSpellInSpellBook", "spellID"); return knows(id) end
function C_SpellBook.GetNumSpellBookSkillLines() return 1 end
function C_SpellBook.GetSpellBookSkillLineInfo(i)
  num(i, "C_SpellBook.GetSpellBookSkillLineInfo", "skillLineIndex")
  if i ~= 1 then return nil end
  return { name = "General", iconID = 0, itemIndexOffset = 0, numSpellBookItems = #knownList(), isGuild = false }
end
function C_SpellBook.GetSpellBookItemName(i, bank)
  num(i, "C_SpellBook.GetSpellBookItemName", "index")
  if bank ~= Enum.SpellBookSpellBank.Player and bank ~= Enum.SpellBookSpellBank.Pet then
    bad("C_SpellBook.GetSpellBookItemName", "spellBank must be an Enum.SpellBookSpellBank value (got " .. tostring(bank) .. ")")
  end
  if bank == Enum.SpellBookSpellBank.Pet then return nil end
  local id = knownList()[i]
  return id and spellName(id) or nil, ""
end
function C_SpellBook.GetSpellBookItemInfo(i, bank)
  num(i, "C_SpellBook.GetSpellBookItemInfo", "index")
  if bank == Enum.SpellBookSpellBank.Pet then return nil end
  local id = knownList()[i]
  return id and { spellID = id, itemType = Enum.SpellBookItemType.Spell, actionID = id, name = spellName(id) } or nil
end
function C_SpellBook.HasPetSpells() return nil end
function C_SpellBook.PickupSpellBookItem(i, bank)
  num(i, "C_SpellBook.PickupSpellBookItem", "index")
  local id = knownList()[i]
  if id then Sim.cursor = { "spell", id } end
end
function IsPlayerSpell(id) num(id, "IsPlayerSpell", "spellID"); return knows(id) end
function IsSpellKnown(id, isPet) num(id, "IsSpellKnown", "spellID"); return knows(id) end
function IsSpellKnownOrOverridesKnown(id) num(id, "IsSpellKnownOrOverridesKnown", "spellID"); return knows(id) end

function Sim.LearnSpell(id)
  Sim.player.spells[id] = true
  Sim.Fire("LEARNED_SPELL_IN_SKILL_LINE", id, 1, false)
  Sim.Fire("SPELLS_CHANGED")
end

------------------------------------------------------------------------------
-- Items and bags
------------------------------------------------------------------------------

-- id -> { name, quality, ilvl, minLevel, class, sub, loc, price, stack, stats, spell }
Sim.ITEMS = {
  [6948] = { name = "Piedra de hogar", quality = 1, class = 15, sub = 0, loc = "", price = 0, stack = 1 },
  [2589] = { name = "Paño de lino", quality = 1, class = 7, sub = 5, loc = "", price = 13, stack = 20 },
  [2996] = { name = "Rollo de lino", quality = 1, class = 7, sub = 5, loc = "", price = 40, stack = 20 },
  [159]  = { name = "Agua de manantial", quality = 1, class = 0, sub = 5, loc = "", price = 1, stack = 20, minLevel = 1, spell = { "Beber", 430 } },
  [1179] = { name = "Leche de cabra helada", quality = 1, class = 0, sub = 5, loc = "", price = 6, stack = 20, minLevel = 5, spell = { "Beber", 431 } },
  [4540] = { name = "Pan duro", quality = 1, class = 0, sub = 5, loc = "", price = 1, stack = 20, minLevel = 1, spell = { "Comida", 433 } },
  [7073] = { name = "Colmillo roto", quality = 0, class = 15, sub = 0, loc = "", price = 6, stack = 20 },
  [7074] = { name = "Mandíbula astillada", quality = 0, class = 15, sub = 0, loc = "", price = 4, stack = 20 },
  [15970] = { name = "Brazales del búho", quality = 2, class = 4, sub = 1, loc = "INVTYPE_WRIST", price = 120, stack = 1, ilvl = 12, minLevel = 2,
    stats = { ITEM_MOD_INTELLECT_SHORT = 3, ITEM_MOD_SPIRIT_SHORT = 2 } },
  [5069] = { name = "Varita de fuego", quality = 2, class = 2, sub = 19, loc = "INVTYPE_RANGEDRIGHT", price = 300, stack = 1, ilvl = 15, minLevel = 10,
    stats = { ITEM_MOD_DAMAGE_PER_SECOND_SHORT = 11.3 } },
  [2504] = { name = "Arco de madera", quality = 1, class = 2, sub = 2, loc = "INVTYPE_RANGED", price = 5, stack = 1, ilvl = 5, minLevel = 1 },
  [6096] = { name = "Camisa de aprendiz", quality = 1, class = 4, sub = 1, loc = "INVTYPE_BODY", price = 1, stack = 1 },
  [57]   = { name = "Túnica de acólito", quality = 1, class = 4, sub = 1, loc = "INVTYPE_ROBE", price = 1, stack = 1, ilvl = 1,
    stats = {} },
  [3000] = { name = "Túnica de lino con aguante", quality = 2, class = 4, sub = 1, loc = "INVTYPE_CHEST", price = 80, stack = 1, ilvl = 8, minLevel = 3,
    stats = { ITEM_MOD_STAMINA_SHORT = 3, ITEM_MOD_INTELLECT_SHORT = 1 } },
  [3001] = { name = "Cota de malla remendada", quality = 2, class = 4, sub = 3, loc = "INVTYPE_CHEST", price = 140, stack = 1, ilvl = 8, minLevel = 3,
    stats = { ITEM_MOD_STAMINA_SHORT = 2, ITEM_MOD_STRENGTH_SHORT = 2 } },
  [5512] = { name = "Piedra de salud menor", quality = 1, class = 0, sub = 0, loc = "", price = 0, stack = 1 },
  [11286] = { name = "Flecha afilada", quality = 1, class = 6, sub = 2, loc = "INVTYPE_AMMO", price = 1, stack = 200, minLevel = 1 },
}
local QUALITY_COLOR = { [0] = "ff9d9d9d", [1] = "ffffffff", [2] = "ff1eff00", [3] = "ff0070dd", [4] = "ffa335ee" }

function Sim.ItemData(id)
  local it = Sim.ITEMS[id]
  if it then return it end
  return { name = "Objeto " .. tostring(id), quality = 1, class = 15, sub = 0, loc = "", price = 0, stack = 1, unknown = true }
end
function Sim.ItemIdOf(item)
  if type(item) == "number" then return item end
  if type(item) == "string" then
    local id = tonumber(item:match("item:(%d+)")) or tonumber(item)
    if id then return id end
    for k, v in pairs(Sim.ITEMS) do if v.name == item then return k end end
  end
  return nil
end
function Sim.ItemLink(id)
  local it = Sim.ItemData(id)
  return string.format("|c%s|Hitem:%d::::::::%d:::::::::|h[%s]|h|r", QUALITY_COLOR[it.quality] or "ffffffff", id, Sim.player.level, it.name)
end
local function itemArg(item, fname)
  if type(item) ~= "number" and type(item) ~= "string" then bad(fname, "item must be an itemID, link or name (got " .. type(item) .. ")") end
  return Sim.ItemIdOf(item)
end
local function iconOf(id) return 134000 + (id % 1000) end

C_Item = {}
-- Item data is cached lazily, like the client: the first GetItemInfo/GetItemNameByID of an item returns nil,
-- queues a load and GET_ITEM_INFO_RECEIVED fires a moment later. Items in bags/equipped are cached.
Sim.itemCache = {}
local function itemCached(id)
  if Sim.itemCache[id] then return true end
  for _, slots in pairs(Sim.player.bags) do for _, it in pairs(slots) do if it.id == id then return true end end end
  for _, eid in pairs(Sim.player.equipped) do if eid == id then return true end end
  return false
end
Sim.itemWaiters = {} -- id -> { fn, ... } (Item:ContinueOnItemLoad)
local function requestItem(id)
  if Sim.itemCache[id] or Sim.itemPending and Sim.itemPending[id] then return end
  Sim.itemPending = Sim.itemPending or {}
  Sim.itemPending[id] = true
  C_Timer.After(0.2, function()
    Sim.itemPending[id] = nil
    Sim.itemCache[id] = true
    Sim.Fire("GET_ITEM_INFO_RECEIVED", id, true)
    local list = Sim.itemWaiters[id]
    Sim.itemWaiters[id] = nil
    for _, fn in ipairs(list or {}) do Sim.SafeCall("Item:ContinueOnItemLoad callback", fn) end
  end)
end
function C_Item.GetItemInfo(item)
  local id = itemArg(item, "C_Item.GetItemInfo")
  if not id then return nil end
  if not itemCached(id) then requestItem(id); return nil end
  local it = Sim.ItemData(id)
  return it.name, Sim.ItemLink(id), it.quality, it.ilvl or 1, it.minLevel or 0, "Tipo", "Subtipo", it.stack or 1, it.loc or "",
    iconOf(id), it.price or 0, it.class, it.sub, 0, 0, nil, false
end
function C_Item.GetItemInfoInstant(item)
  local id = itemArg(item, "C_Item.GetItemInfoInstant")
  if not id then return nil end
  local it = Sim.ItemData(id)
  return id, "Tipo", "Subtipo", it.loc or "", iconOf(id), it.class, it.sub
end
function C_Item.GetItemNameByID(item)
  local id = itemArg(item, "C_Item.GetItemNameByID")
  if not id then return nil end
  if not itemCached(id) then requestItem(id); return nil end
  return Sim.ItemData(id).name
end
-- ItemMixin (Item:CreateFromItemID): the async way to wait for an item's data.
Item = {}
local ItemObj = {}
ItemObj.__index = ItemObj
function Item:CreateFromItemID(id)
  if self ~= Item then bad("Item.CreateFromItemID", "call it with ':' (Item:CreateFromItemID(id))") end
  num(id, "Item:CreateFromItemID", "itemID")
  return setmetatable({ itemID = id }, ItemObj)
end
function ItemObj:GetItemID() return self.itemID end
function ItemObj:IsItemEmpty() return self.itemID == nil end
function ItemObj:IsItemDataCached() return itemCached(self.itemID) end
function ItemObj:GetItemName()
  if not itemCached(self.itemID) then return nil end
  return Sim.ItemData(self.itemID).name
end
function ItemObj:ContinueOnItemLoad(fn)
  if type(fn) ~= "function" then bad("ItemMixin:ContinueOnItemLoad", "callback must be a function") end
  if itemCached(self.itemID) then fn(); return end
  local w = Sim.itemWaiters[self.itemID] or {}
  Sim.itemWaiters[self.itemID] = w
  w[#w + 1] = fn
  requestItem(self.itemID)
end

function C_Item.GetItemIconByID(item) local id = itemArg(item, "C_Item.GetItemIconByID"); return id and iconOf(id) end
function C_Item.GetItemQualityByID(item) local id = itemArg(item, "C_Item.GetItemQualityByID"); return id and Sim.ItemData(id).quality end
function C_Item.RequestLoadItemDataByID(item) local id = itemArg(item, "C_Item.RequestLoadItemDataByID"); if id then requestItem(id) end end
function C_Item.GetItemSpell(item)
  local id = itemArg(item, "C_Item.GetItemSpell")
  local s = id and Sim.ItemData(id).spell
  if s then return s[1], s[2] end
  return nil
end
function C_Item.GetItemStats(link)
  str(link, "C_Item.GetItemStats", "itemLink")
  local id = Sim.ItemIdOf(link)
  local st = {}
  for k, v in pairs(id and Sim.ItemData(id).stats or {}) do st[k] = v end
  return st
end
function C_Item.PickupItem(item) local id = itemArg(item, "C_Item.PickupItem"); Sim.cursor = { "item", id } end
function C_Item.IsEquippableItem(item) local id = itemArg(item, "C_Item.IsEquippableItem"); return (Sim.ItemData(id).loc or "") ~= "" end

function Sim.BagItem(bag, slot) return Sim.player.bags[bag] and Sim.player.bags[bag][slot] end
function C_Item.GetItemCount(item, includeBank, includeUses, includeReagentBank)
  local id = itemArg(item, "C_Item.GetItemCount")
  local n = 0
  for bag, slots in pairs(Sim.player.bags) do
    if bag >= 0 and bag <= 4 or includeBank then
      for _, it in pairs(slots) do if it.id == id then n = n + it.count end end
    end
  end
  return n
end

C_Container = {}
function C_Container.GetContainerNumSlots(bag)
  num(bag, "C_Container.GetContainerNumSlots", "containerIndex")
  if bag == 0 then return 16 end
  return 0
end
function C_Container.GetContainerNumFreeSlots(bag)
  num(bag, "C_Container.GetContainerNumFreeSlots", "bagIndex")
  if bag ~= 0 then return 0, 0 end
  local used = 0
  for _ in pairs(Sim.player.bags[0]) do used = used + 1 end
  return 16 - used, 0
end
function C_Container.GetContainerItemInfo(bag, slot)
  num(bag, "C_Container.GetContainerItemInfo", "containerIndex"); num(slot, "C_Container.GetContainerItemInfo", "slotIndex")
  local it = Sim.BagItem(bag, slot)
  if not it then return nil end
  local d = Sim.ItemData(it.id)
  return { iconFileID = iconOf(it.id), stackCount = it.count, isLocked = false, quality = d.quality, isReadable = false,
    hasLoot = false, hyperlink = Sim.ItemLink(it.id), isFiltered = false, hasNoValue = (d.price or 0) == 0,
    itemID = it.id, isBound = false }
end
function C_Container.GetContainerItemLink(bag, slot) local it = Sim.BagItem(bag, slot); return it and Sim.ItemLink(it.id) end
function C_Container.UseContainerItem(bag, slot)
  num(bag, "C_Container.UseContainerItem", "containerIndex"); num(slot, "C_Container.UseContainerItem", "slotIndex")
  if Sim.player.combat then error("Interface action failed because of an AddOn") end
  local it = Sim.BagItem(bag, slot)
  if not it then return end
  if Sim.merchant and MerchantFrame:IsShown() then
    Sim.player.money = Sim.player.money + (Sim.ItemData(it.id).price or 0) * it.count
    Sim.player.bags[bag][slot] = nil
    Sim.sold = (Sim.sold or 0) + 1
  end
end
function Sim.AddItem(id, count)
  local bag = Sim.player.bags[0]
  for slot = 1, 16 do
    if not bag[slot] then bag[slot] = { id = id, count = count or 1 }; return slot end
  end
end

function GetInventoryItemLink(unit, slot)
  unitArg(unit, "GetInventoryItemLink"); num(slot, "GetInventoryItemLink", "slot")
  local id = unit == "player" and Sim.player.equipped[slot]
  return id and Sim.ItemLink(id) or nil
end
function GetInventoryItemID(unit, slot) return unit == "player" and Sim.player.equipped[slot] or nil end
function GetInventoryItemTexture(unit, slot)
  unitArg(unit, "GetInventoryItemTexture"); num(slot, "GetInventoryItemTexture", "slot")
  local id = unit == "player" and Sim.player.equipped[slot]
  return id and iconOf(id) or nil
end

------------------------------------------------------------------------------
-- Professions
------------------------------------------------------------------------------

function GetProfessions()
  local p = Sim.player.profs
  return p[1] and 1 or nil, p[2] and 2 or nil, nil, nil, nil
end
function GetProfessionInfo(i)
  num(i, "GetProfessionInfo", "index")
  local p = Sim.player.profs[i]
  if not p then bad("GetProfessionInfo", "invalid profession index " .. i) end
  return p.name, 136000, p.rank, p.max, 2, 0, p.skillLine, 0, -1, 0
end
C_TradeSkillUI = {}
function C_TradeSkillUI.GetAllProfessionTradeSkillLines() return {} end
function C_TradeSkillUI.GetProfessionInfoBySkillLineID(id) num(id, "C_TradeSkillUI.GetProfessionInfoBySkillLineID", "skillLineID"); return nil end
function C_TradeSkillUI.GetTradeSkillDisplayName(id) num(id, "C_TradeSkillUI.GetTradeSkillDisplayName", "skillLineID"); return nil end
function C_TradeSkillUI.GetAllRecipeIDs() return {} end

------------------------------------------------------------------------------
-- Flight paths
------------------------------------------------------------------------------

C_TaxiMap = {}
function C_TaxiMap.GetAllTaxiNodes(map)
  num(map, "C_TaxiMap.GetAllTaxiNodes", "uiMapID")
  return Sim.taxiNodes or {}
end
function GetTaxiMapID() return Sim.player.map end

------------------------------------------------------------------------------
-- Merchant / trainer / quest rewards
------------------------------------------------------------------------------

local function merchantItem(i, fname)
  num(i, fname, "index")
  return Sim.merchant and Sim.merchant[i]
end
function GetMerchantNumItems() return Sim.merchant and #Sim.merchant or 0 end
function GetMerchantItemID(i) local m = merchantItem(i, "GetMerchantItemID"); return m and m.id end
function GetMerchantItemLink(i) local m = merchantItem(i, "GetMerchantItemLink"); return m and Sim.ItemLink(m.id) end
function GetMerchantItemMaxStack(i) local m = merchantItem(i, "GetMerchantItemMaxStack"); return m and 20 or 0 end
C_MerchantFrame = {}
function C_MerchantFrame.GetItemInfo(i)
  local m = merchantItem(i, "C_MerchantFrame.GetItemInfo")
  if not m then return nil end
  return { name = Sim.ItemData(m.id).name, texture = iconOf(m.id), price = m.price, stackCount = m.stack or 1,
    numAvailable = m.avail or -1, isPurchasable = true, isUsable = true, hasExtendedCost = false }
end
function BuyMerchantItem(i, qty)
  num(i, "BuyMerchantItem", "index")
  if qty ~= nil then num(qty, "BuyMerchantItem", "quantity") end
  if not (Sim.merchant and MerchantFrame:IsShown()) then bad("BuyMerchantItem", "no merchant open") end
  Sim.purchases[#Sim.purchases + 1] = { index = i, qty = qty or 1 }
end
function CanMerchantRepair() return false end

function GetNumTrainerServices() return Sim.trainer and #Sim.trainer or 0 end
local function trainerService(i, fname) num(i, fname, "index"); return Sim.trainer and Sim.trainer[i] end
function GetTrainerServiceInfo(i)
  local s = trainerService(i, "GetTrainerServiceInfo")
  if not s then return nil end
  return spellName(s.spell), s.rank or "", s.category or "available", false
end
function GetTrainerServiceCost(i) local s = trainerService(i, "GetTrainerServiceCost"); return s and s.cost or 0, false, 0 end
function GetTrainerServiceIcon(i) local s = trainerService(i, "GetTrainerServiceIcon"); return s and (136000 + s.spell % 1000) end
function BuyTrainerService(i)
  local s = trainerService(i, "BuyTrainerService")
  if not (s and ClassTrainerFrame and ClassTrainerFrame:IsShown()) then bad("BuyTrainerService", "no trainer open / bad index") end
  Sim.learned[#Sim.learned + 1] = s.spell
end
function IsTradeskillTrainer() return false end

function GetNumQuestChoices() return Sim.questChoices and #Sim.questChoices or 0 end

-- Quest dialog windows: Sim.qwin = { kind = "detail"|"progress"|"complete"|"greeting"|"gossip", id = questID }.
-- The functions below are the client's; they only work while the matching window is open.
Sim.autoLog = {} -- what the add-on did: "accept 12", "complete 12", "reward 12 1", "select-active 12"...
local function winId() return Sim.qwin and Sim.qwin.id or 0 end
function GetQuestID() return winId() end
function QuestGetAutoAccept() return false end
function QuestFlagsPVP() return Sim.qwin and Sim.qwin.pvp or false end
function AcknowledgeAutoAcceptQuest() end
function GetQuestMoneyToGet() return Sim.qwin and Sim.qwin.money or 0 end
function IsQuestCompletable() return Sim.qwin ~= nil and Sim.qwin.kind == "progress" and Sim.qwin.completable ~= false end
function CloseQuest() Sim.qwin = nil; Sim.questChoices = nil; Sim.Fire("QUEST_FINISHED") end
function AcceptQuest()
  if not (Sim.qwin and Sim.qwin.kind == "detail") then bad("AcceptQuest", "no quest detail window open") end
  if Sim.player.combat then bad("AcceptQuest", "protected in combat") end
  local id = Sim.qwin.id
  Sim.autoLog[#Sim.autoLog + 1] = "accept " .. id
  Sim.qwin = nil
  Sim.AcceptQuest(id, Sim.qwin_objectives and Sim.qwin_objectives[id] or { { "Objetivo", 1 } })
  Sim.Fire("QUEST_FINISHED")
end
function CompleteQuest()
  if not (Sim.qwin and Sim.qwin.kind == "progress") then bad("CompleteQuest", "no quest progress window open") end
  Sim.autoLog[#Sim.autoLog + 1] = "complete " .. Sim.qwin.id
  Sim.qwin.kind = "complete"
  Sim.questChoices = Sim.qwin.choices
  Sim.Fire("QUEST_COMPLETE")
end
function GetQuestReward(choice)
  if not (Sim.qwin and Sim.qwin.kind == "complete") then bad("GetQuestReward", "no quest reward window open") end
  local id = Sim.qwin.id
  Sim.autoLog[#Sim.autoLog + 1] = "reward " .. id .. " " .. tostring(choice)
  Sim.qwin = nil
  Sim.questChoices = nil
  Sim.TurnInQuest(id)
  Sim.Fire("QUEST_FINISHED")
end
function Sim.OpenQuest(kind, id, opts)
  Sim.qwin = { kind = kind, id = id }
  for k, v in pairs(opts or {}) do Sim.qwin[k] = v end
  Sim.questChoices = opts and opts.choices or nil
  Sim.Fire(kind == "detail" and "QUEST_DETAIL" or kind == "progress" and "QUEST_PROGRESS" or "QUEST_COMPLETE")
end
-- Greeting / gossip windows list quests: active = { {id=, complete=} }, available = { id, ... }.
function Sim.OpenNpc(kind, active, available)
  Sim.qwin = { kind = kind, id = 0, active = active or {}, available = available or {} }
  Sim.Fire(kind == "greeting" and "QUEST_GREETING" or "GOSSIP_SHOW")
end
function GetNumActiveQuests() return Sim.qwin and Sim.qwin.kind == "greeting" and #Sim.qwin.active or 0 end
function GetNumAvailableQuests() return Sim.qwin and Sim.qwin.kind == "greeting" and #Sim.qwin.available or 0 end
function GetActiveTitle(i) local a = Sim.qwin.active[i]; return "Misión " .. a.id, a.complete end
function GetActiveQuestID(i) return Sim.qwin.active[i].id end
function GetAvailableQuestInfo(i) return "Misión", 1, false, false, Sim.qwin.available[i] end
function SelectActiveQuest(i)
  local a = Sim.qwin.active[i]
  Sim.autoLog[#Sim.autoLog + 1] = "select-active " .. a.id
  Sim.OpenQuest("progress", a.id)
end
function SelectAvailableQuest(i)
  local id = Sim.qwin.available[i]
  Sim.autoLog[#Sim.autoLog + 1] = "select-available " .. id
  Sim.OpenQuest("detail", id)
end
C_GossipInfo = {}
function C_GossipInfo.GetOptions() return {} end
function C_GossipInfo.CloseGossip() Sim.qwin = nil end
function C_GossipInfo.GetActiveQuests()
  local out = {}
  for i, a in ipairs(Sim.qwin and Sim.qwin.kind == "gossip" and Sim.qwin.active or {}) do
    out[i] = { questID = a.id, isComplete = a.complete, title = "Misión " .. a.id }
  end
  return out
end
function C_GossipInfo.GetAvailableQuests()
  local out = {}
  for i, id in ipairs(Sim.qwin and Sim.qwin.kind == "gossip" and Sim.qwin.available or {}) do
    out[i] = { questID = id, title = "Misión " .. id }
  end
  return out
end
function C_GossipInfo.SelectActiveQuest(id)
  num(id, "C_GossipInfo.SelectActiveQuest", "questID")
  Sim.autoLog[#Sim.autoLog + 1] = "select-active " .. id
  Sim.OpenQuest("progress", id)
end
function C_GossipInfo.SelectAvailableQuest(id)
  num(id, "C_GossipInfo.SelectAvailableQuest", "questID")
  Sim.autoLog[#Sim.autoLog + 1] = "select-available " .. id
  Sim.OpenQuest("detail", id)
end
function GetQuestItemLink(kind, i)
  str(kind, "GetQuestItemLink", "type"); num(i, "GetQuestItemLink", "index")
  local id = kind == "choice" and Sim.questChoices and Sim.questChoices[i]
  return id and Sim.ItemLink(id) or nil
end
function GetNumQuestRewards() return 0 end

------------------------------------------------------------------------------
-- Macros and action bars
------------------------------------------------------------------------------

local function macroCounts()
  local acc, char = 0, 0
  for _, m in ipairs(Sim.macros) do if m.perChar then char = char + 1 else acc = acc + 1 end end
  return acc, char
end
function GetNumMacros() return macroCounts() end
function GetMacroIndexByName(name)
  str(name, "GetMacroIndexByName", "name")
  for i, m in ipairs(Sim.macros) do if m.name == name then return i end end
  return 0
end
function GetMacroInfo(i)
  if type(i) == "string" then i = GetMacroIndexByName(i) end
  num(i, "GetMacroInfo", "index")
  local m = Sim.macros[i]
  if not m then return nil end
  return m.name, m.icon, m.body
end
function CreateMacro(name, icon, body, perChar)
  str(name, "CreateMacro", "name")
  iconArg(icon, "CreateMacro")
  str(body, "CreateMacro", "body")
  if Sim.player.combat then error("Interface action failed because of an AddOn") end
  if #name > 16 then bad("CreateMacro", "name longer than 16 characters") end
  if #body > 255 then bad("CreateMacro", "body longer than 255 characters") end
  Sim.macros[#Sim.macros + 1] = { name = name, icon = icon, body = body, perChar = perChar and true or false }
  Sim.Fire("UPDATE_MACROS")
  return #Sim.macros
end
function EditMacro(i, name, icon, body)
  num(i, "EditMacro", "index")
  local m = Sim.macros[i]
  if not m then bad("EditMacro", "no macro at index " .. i) end
  iconArg(icon, "EditMacro")
  if Sim.player.combat then error("Interface action failed because of an AddOn") end
  m.name, m.icon, m.body = name or m.name, icon or m.icon, body or m.body
  Sim.Fire("UPDATE_MACROS")
  return i
end
function PickupMacro(i)
  if type(i) == "string" then i = GetMacroIndexByName(i) end
  num(i, "PickupMacro", "index")
  if Sim.macros[i] then Sim.cursor = { "macro", i } end
end
function HasAction(slot) num(slot, "HasAction", "slot"); return Sim.actions[slot] ~= nil end
function PlaceAction(slot)
  num(slot, "PlaceAction", "slot")
  if Sim.player.combat then error("Interface action failed because of an AddOn") end
  if Sim.cursor then Sim.actions[slot] = Sim.cursor; Sim.cursor = nil end
end
function ClearCursor() Sim.cursor = nil end
function GetCursorInfo() if Sim.cursor then return Sim.cursor[1], Sim.cursor[2] end end
function GetActionInfo(slot) local a = Sim.actions[slot]; if a then return a[1], a[2] end end

------------------------------------------------------------------------------
-- Auras, add-ons, misc C_ namespaces
------------------------------------------------------------------------------

C_UnitAuras = {}
function C_UnitAuras.GetAuraDataByIndex(unit, i, filter)
  unitArg(unit, "C_UnitAuras.GetAuraDataByIndex"); num(i, "C_UnitAuras.GetAuraDataByIndex", "index")
  return nil
end
function C_UnitAuras.GetPlayerAuraBySpellID() return nil end

C_AddOns = {}
function C_AddOns.GetAddOnMetadata(name, field)
  str(name, "C_AddOns.GetAddOnMetadata", "name"); str(field, "C_AddOns.GetAddOnMetadata", "variable")
  if name ~= Sim.addonName then return nil end
  return Sim.tocMeta and Sim.tocMeta[field]
end
-- Installed add-ons (tests can add more): Sim.addons = { { name = "Questie", loaded = true }, ... }
local function addonList() return Sim.addons or { { name = Sim.addonName, loaded = true } } end
function C_AddOns.GetNumAddOns() return #addonList() end
function C_AddOns.IsAddOnLoaded(nameOrIndex)
  local list = addonList()
  if type(nameOrIndex) == "number" then
    local a = list[nameOrIndex]
    return a ~= nil and a.loaded == true, a ~= nil and a.loaded == true
  end
  for _, a in ipairs(list) do
    if a.name == nameOrIndex then return a.loaded == true, a.loaded == true end
  end
  return false, false
end
function C_AddOns.GetAddOnInfo(nameOrIndex)
  local a = type(nameOrIndex) == "number" and addonList()[nameOrIndex] or { name = nameOrIndex }
  if not a then return nil end
  return a.name, a.name, "", true, "INSECURE", false
end
function C_AddOns.LoadAddOn(name) return false, "MISSING" end

-- Creature names (the client caches them lazily: the first tooltip of an unseen creature comes back empty).
Sim.NPC_NAMES = { [658] = "Sten Brazorrecio", [2079] = "Conservador Ilthalaine", [3595] = "Shanda", [467] = "El Defias Traidor" }
Sim.npcCache = {}
C_TooltipInfo = {}
function C_TooltipInfo.GetHyperlink(link)
  str(link, "C_TooltipInfo.GetHyperlink", "hyperlink")
  if link:sub(1, 5) == "unit:" then
    local id = tonumber(link:match("^unit:Creature%-0%-0%-0%-0%-(%d+)%-0$"))
    if not id then bad("C_TooltipInfo.GetHyperlink", "unit hyperlink must be unit:Creature-0-0-0-0-<npcID>-0 (got " .. link .. ")") end
    Sim.npcLookups = (Sim.npcLookups or 0) + 1
    if not Sim.npcCache[id] then
      if not Sim.npcPending then Sim.npcPending = {} end
      if not Sim.npcPending[id] then
        Sim.npcPending[id] = true
        C_Timer.After(0.3, function() Sim.npcPending[id] = nil; Sim.npcCache[id] = true end)
      end
      return { type = Enum.TooltipDataType.Unit, lines = {} }
    end
    return { type = Enum.TooltipDataType.Unit, id = id,
      lines = { { leftText = Sim.NPC_NAMES[id] or ("Criatura " .. id) }, { leftText = "Nivel 5" } } }
  end
  local id = Sim.ItemIdOf(link)
  local d = id and Sim.ItemData(id)
  local lines = { { leftText = d and d.name or link } }
  if d and d.tooltip then for _, t in ipairs(d.tooltip) do lines[#lines + 1] = { leftText = t } end end
  return { type = 0, id = id, lines = lines }
end

Sim.tooltipPostCalls = {}
TooltipDataProcessor = {}
function TooltipDataProcessor.AddTooltipPostCall(kind, fn)
  if type(fn) ~= "function" then bad("TooltipDataProcessor.AddTooltipPostCall", "callback must be a function") end
  Sim.tooltipPostCalls[kind] = Sim.tooltipPostCalls[kind] or {}
  table.insert(Sim.tooltipPostCalls[kind], fn)
end
function TooltipDataProcessor.AddTooltipPreCall() end
function Sim.TooltipDataPosted(tt, link)
  local id = Sim.ItemIdOf(link)
  if not (link:find("item:", 1, true) and id) then return end
  local data = { type = Enum.TooltipDataType.Item, id = id, lines = C_TooltipInfo.GetHyperlink(link).lines }
  for _, kind in ipairs({ Enum.TooltipDataType.Item, "ALL" }) do
    for _, fn in ipairs(Sim.tooltipPostCalls[kind] or {}) do
      Sim.SafeCall("TooltipDataProcessor post-call", fn, tt, data)
    end
  end
end

Enum = {
  SendAddonMessageResult = { Success = 0, InvalidPrefix = 1, InvalidMessage = 2, AddonMessageThrottle = 3,
    InvalidChatType = 4, NotInGroup = 5, TargetRequired = 6, InvalidChannel = 7, ChannelThrottle = 8,
    GeneralError = 9, NotInGuild = 10, AddOnMessageLockdown = 11, TargetOffline = 12 },
  RegisterAddonMessagePrefixResult = { Success = 0, DuplicatePrefix = 1, InvalidPrefix = 2, MaxPrefixes = 3 },
  TooltipDataType = { Item = 0, Spell = 1, Unit = 2 },
  SpellBookSpellBank = { Player = 0, Pet = 1 },
  SpellBookItemType = { None = 0, Spell = 1, FutureSpell = 2, PetAction = 3, Flyout = 4 },
  FlightPathState = { Current = 0, Reachable = 1, Unreachable = 2 },
  PlayerInteractionType = { None = 0, TradePartner = 1, Item = 2, Gossip = 3, QuestGiver = 4, Merchant = 5,
    TaxiNode = 6, Trainer = 7, Banker = 8, Binder = 21, ProfessionsTrainer = 59, StableMaster = 13, Auctioneer = 21 + 100 },
  ItemQuality = { Poor = 0, Common = 1, Uncommon = 2, Rare = 3, Epic = 4 },
}

-- Constants
NUM_BAG_SLOTS, NUM_TOTAL_EQUIPPED_BAG_SLOTS, NUM_BANKBAGSLOTS, BANK_CONTAINER = 4, 5, 7, -1
MAX_ACCOUNT_MACROS, MAX_CHARACTER_MACROS = 120, 18
CLOSE, ACCEPT, CANCEL, OKAY, YES, NO = "Cerrar", "Aceptar", "Cancelar", "Aceptar", "Sí", "No"
ITEM_MOD_INTELLECT_SHORT, ITEM_MOD_SPIRIT_SHORT, ITEM_MOD_STAMINA_SHORT, ITEM_MOD_STRENGTH_SHORT, ITEM_MOD_AGILITY_SHORT =
  "Intelecto", "Espíritu", "Aguante", "Fuerza", "Agilidad"
ITEM_MOD_DAMAGE_PER_SECOND_SHORT = "Daño por segundo"
BackdropTemplateMixin = {}
UISpecialFrames = {}
SlashCmdList = {}
StaticPopupDialogs = {}

------------------------------------------------------------------------------
-- Global frames
------------------------------------------------------------------------------

function Sim.CreateGlobalFrames()
  UIParent = CreateFrame("Frame", "UIParent")
  UIParent:SetSize(1920, 1080)
  WorldFrame = CreateFrame("Frame", "WorldFrame")
  Minimap = CreateFrame("Frame", "Minimap", UIParent)
  Minimap:SetSize(140, 140)
  GameTooltip = CreateFrame("GameTooltip", "GameTooltip", UIParent, "GameTooltipTemplate")
  GameTooltip:Hide()
  ItemRefTooltip = CreateFrame("GameTooltip", "ItemRefTooltip", UIParent, "GameTooltipTemplate")
  ItemRefTooltip:Hide()
  -- World map: canvas = ScrollContainer.Child; GetMapID / GetCanvasScale are real mixin methods.
  WorldMapFrame = CreateFrame("Frame", "WorldMapFrame", UIParent)
  WorldMapFrame:SetSize(1000, 700)
  WorldMapFrame:Hide()
  WorldMapFrame.ScrollContainer = CreateFrame("ScrollFrame", nil, WorldMapFrame)
  WorldMapFrame.ScrollContainer:SetSize(1000, 667)
  WorldMapFrame.ScrollContainer.Child = CreateFrame("Frame", nil, WorldMapFrame.ScrollContainer)
  WorldMapFrame.ScrollContainer.Child:SetSize(1002, 668)
  WorldMapFrame.mapID = Sim.player.map
  function WorldMapFrame:GetMapID() return self.mapID end
  function WorldMapFrame:SetMapID(id) self.mapID = id end
  function WorldMapFrame.ScrollContainer:GetCanvasScale() return 1 end
  MerchantFrame = CreateFrame("Frame", "MerchantFrame", UIParent)
  MerchantFrame:SetSize(336, 444)
  MerchantFrame:Hide()
  -- Quest reward buttons (QuestInfoRewardsFrame.RewardButtons, created by the quest frame).
  QuestInfoRewardsFrame = CreateFrame("Frame", "QuestInfoRewardsFrame", UIParent)
  QuestInfoRewardsFrame.RewardButtons = {}
  for i = 1, 6 do
    QuestInfoRewardsFrame.RewardButtons[i] = CreateFrame("Button", "QuestInfoRewardsFrameQuestInfoItem" .. i, QuestInfoRewardsFrame)
  end
  ChatFontNormal = CreateFont("ChatFontNormal")
  for _, n in ipairs({ "GameFontNormal", "GameFontNormalSmall", "GameFontHighlight", "GameFontHighlightSmall",
    "GameFontDisableSmall", "GameFontNormalLarge", "NumberFontNormal", "NumberFontNormalSmallGray" }) do
    CreateFont(n)
  end

  -- Chat
  local chat = {}
  function chat:AddMessage(msg, r, g, b)
    if type(msg) ~= "string" and type(msg) ~= "number" then
      error("bad argument #1 to 'AddMessage' (string expected, got " .. type(msg) .. ")", 2)
    end
    local line = Sim.StripCodes(msg)
    Sim.chat[#Sim.chat + 1] = line
    Sim.Out("    [chat] " .. line)
  end
  DEFAULT_CHAT_FRAME = chat
  ChatFrame1 = chat
end

------------------------------------------------------------------------------
-- Group and addon messages
-- Sim.party[i] = { name, realm?, class, race?, level, quests = {}, offline? }; Sim.raid = true: a raid.
-- C_ChatInfo.SendAddonMessage records every send in Sim.addonSent ({ prefix, text, channel, result, t }),
-- echoes it back to the sender (as the client does) and, in the two-player mode of run.js, hands it to the
-- other client through __busSend. Sim.addonFault = n: the next n sends are refused with
-- Enum.SendAddonMessageResult.AddonMessageThrottle (nothing is delivered).
------------------------------------------------------------------------------

Sim.addonSent = {}
Sim.addonInbox = {}  -- { due, prefix, text, channel, sender }
Sim.addonFault = 0
Sim.realm = "Reino"
local addonPrefixes = {}

function GetRealmName() return Sim.realm end
function GetNormalizedRealmName() return Sim.realm end
function Ambiguate(name, context)
  str(name, "Ambiguate", "fullName"); str(context, "Ambiguate", "context")
  local base, realm = name:match("^([^%-]+)%-(.+)$")
  if base and (context == "short" or realm == Sim.realm) then return base end
  return name
end
local function partyCount() local n = 0; for i = 1, 4 do if Sim.party[i] then n = i end end; return n end
function IsInRaid() return Sim.raid == true end
function IsInGroup() return Sim.raid == true or partyCount() > 0 end
function GetNumSubgroupMembers() return partyCount() end
function GetNumGroupMembers()
  if Sim.raid then return math.max(partyCount() + 1, Sim.raidSize or 10) end
  local n = partyCount()
  return n > 0 and n + 1 or 0
end
function UnitIsConnected(u)
  unitArg(u, "UnitIsConnected")
  if u == "player" then return true end
  local pm = partyOf(u)
  if not pm then return false end
  return not pm.offline
end
function UnitInParty(u) unitArg(u, "UnitInParty"); return u == "player" or partyOf(u) ~= nil end

C_ChatInfo = {}
function C_ChatInfo.RegisterAddonMessagePrefix(prefix)
  str(prefix, "C_ChatInfo.RegisterAddonMessagePrefix", "prefix")
  if #prefix > 16 then return Enum.RegisterAddonMessagePrefixResult.InvalidPrefix end
  if addonPrefixes[prefix] then return Enum.RegisterAddonMessagePrefixResult.DuplicatePrefix end
  addonPrefixes[prefix] = true
  return Enum.RegisterAddonMessagePrefixResult.Success
end
function C_ChatInfo.IsAddonMessagePrefixRegistered(prefix)
  str(prefix, "C_ChatInfo.IsAddonMessagePrefixRegistered", "prefix")
  return addonPrefixes[prefix] == true
end
local CHAT_TYPES = { PARTY = true, RAID = true, GUILD = true, WHISPER = true, INSTANCE_CHAT = true, CHANNEL = true }
function C_ChatInfo.SendAddonMessage(prefix, text, chatType, target)
  str(prefix, "C_ChatInfo.SendAddonMessage", "prefix"); str(text, "C_ChatInfo.SendAddonMessage", "message")
  str(chatType, "C_ChatInfo.SendAddonMessage", "chatType")
  local R = Enum.SendAddonMessageResult
  if #prefix > 16 then return R.InvalidPrefix end
  if #text > 255 then bad("C_ChatInfo.SendAddonMessage", "message longer than 255 bytes (" .. #text .. ")") end
  if not CHAT_TYPES[chatType] then return R.InvalidChatType end
  local result = R.Success
  if (chatType == "PARTY" or chatType == "RAID") and not IsInGroup() then result = R.NotInGroup
  elseif Sim.addonFault > 0 then Sim.addonFault = Sim.addonFault - 1; result = R.AddonMessageThrottle end
  Sim.addonSent[#Sim.addonSent + 1] = { prefix = prefix, text = text, channel = chatType, result = result, t = Sim.time }
  if Sim.verbose then Sim.Out("  > addon " .. prefix .. " " .. chatType .. " " .. text .. " -> " .. result) end
  if result ~= R.Success then return result end
  local sender = Sim.player.name .. "-" .. Sim.realm
  Sim.addonInbox[#Sim.addonInbox + 1] = { due = Sim.time + 0.05, prefix = prefix, text = text, channel = chatType, sender = sender }
  local busSend = rawget(_G, "__busSend")
  if busSend then busSend(prefix, text, chatType, Sim.time, sender) end
  return result
end
-- Texts of the addon messages that went out (sends since index `from`, default 1) with this prefix.
function Sim.AddonTexts(prefix, from)
  local out = {}
  for i = from or 1, #Sim.addonSent do
    local m = Sim.addonSent[i]
    if (not prefix or m.prefix == prefix) and m.result == Enum.SendAddonMessageResult.Success then out[#out + 1] = m.text end
  end
  return out
end
local function deliver(prefix, text, channel, sender)
  if not addonPrefixes[prefix] then return end
  Sim.Fire("CHAT_MSG_ADDON", prefix, text, channel, sender, Sim.player.name, 0, 0, "", 0)
end
-- Per frame: self-echoes and, in the two-player mode, the other client's messages that are due.
table.insert(Sim.frameHooks, function()
  local keep, due = {}, {}
  for _, m in ipairs(Sim.addonInbox) do
    if m.due <= Sim.time + 1e-9 then due[#due + 1] = m else keep[#keep + 1] = m end
  end
  Sim.addonInbox = keep
  for _, m in ipairs(due) do deliver(m.prefix, m.text, m.channel, m.sender) end
  local busRecv = rawget(_G, "__busRecv")
  if busRecv then
    while true do
      local prefix, text, channel, sender = busRecv(Sim.time)
      if not prefix then break end
      deliver(prefix, text, channel, sender)
    end
  end
end)

-- Static popups: the dialog frame gets the shown data; Sim.AcceptPopup() presses button1.
function StaticPopup_Show(which, text1, text2, data)
  str(which, "StaticPopup_Show", "which")
  local d = StaticPopupDialogs[which]
  if not d then bad("StaticPopup_Show", "unknown dialog " .. which) end
  local f = _G.StaticPopup1 or CreateFrame("Frame", "StaticPopup1", UIParent)
  f.editBox = f.editBox or CreateFrame("EditBox", nil, f)
  f.which, f.data = which, data
  f.text = string.format(d.text or "%s", text1 or "", text2 or "")
  Sim.lastPopup = f
  f:Show()
  if d.OnShow then Sim.SafeCall("StaticPopup OnShow " .. which, d.OnShow, f, data) end
  if d.hasEditBox and d.EditBoxOnTextChanged then
    Sim.SafeCall("StaticPopup EditBoxOnTextChanged " .. which, d.EditBoxOnTextChanged, f.editBox, data)
  end
  return f
end
function StaticPopup_Hide(which)
  if _G.StaticPopup1 and _G.StaticPopup1.which == which then
    _G.StaticPopup1:Hide()
    if Sim.lastPopup == _G.StaticPopup1 then Sim.lastPopup = nil end
  end
end
-- Presses button2 (OnCancel with reason "clicked").
function Sim.DeclinePopup()
  local f = Sim.lastPopup
  if not f then return false end
  local d = StaticPopupDialogs[f.which]
  if d.OnCancel then Sim.SafeCall("StaticPopup OnCancel " .. f.which, d.OnCancel, f, f.data, "clicked") end
  f:Hide()
  Sim.lastPopup = nil
  return true
end
function Sim.AcceptPopup()
  local f = Sim.lastPopup
  if not f then return false end
  local d = StaticPopupDialogs[f.which]
  if d.OnAccept then Sim.SafeCall("StaticPopup OnAccept " .. f.which, d.OnAccept, f, f.data) end
  f:Hide()
  Sim.lastPopup = nil
  return true
end

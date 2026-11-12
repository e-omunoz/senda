-- Helpers shared by the scenarios in run.js (loaded after the mock, before the add-on).
local Sim = Sim

Sim.failures = {}
Sim.checks = 0

function Check(cond, msg, detail)
  Sim.checks = Sim.checks + 1
  if cond then
    Sim.Out("  ok   " .. msg)
  else
    Sim.failures[#Sim.failures + 1] = msg .. (detail and (" — " .. tostring(detail)) or "")
    Sim.Out("  FAIL " .. msg .. (detail and (" — " .. tostring(detail)) or ""))
  end
  return cond
end

function Section(title) Sim.Out("  -- " .. title) end

-- Character presets ------------------------------------------------------------
Sim.CHARS = {
  ["gnome-warlock"] = { race = "Gnome", class = "WARLOCK", level = 1, map = 1426, x = 0.300, y = 0.715,
    spells = { 686, 687 },
    bag = { [1] = { 6948 }, [2] = { 2589, 5 }, [3] = { 7073, 3 }, [4] = { 7074, 1 }, [5] = { 15970, 1 }, [6] = { 2504, 1 } },
    equipped = { [4] = 6096, [5] = 57 } },
  ["human-mage"] = { race = "Human", class = "MAGE", level = 1, map = 1429, x = 0.480, y = 0.420,
    spells = { 133, 168 },
    bag = { [1] = { 6948 }, [2] = { 159, 4 } },
    profs = { { name = "Sastrería", skillLine = 197, rank = 50, max = 75 } },
    equipped = { [5] = 57 } },
  ["nightelf-druid"] = { race = "NightElf", class = "DRUID", level = 1, map = 1438, x = 0.587, y = 0.443,
    spells = { 5176, 5185 },
    bag = { [1] = { 6948 }, [2] = { 159, 4 } },
    equipped = {} },
  ["nightelf-warrior"] = { race = "NightElf", class = "WARRIOR", level = 3, map = 1438, x = 0.58, y = 0.44,
    bag = { [1] = { 6948 } }, equipped = {} },
  -- Horda (fase 4): una guía por raza, para cualquier clase.
  ["orc-warrior"] = { race = "Orc", class = "WARRIOR", faction = "Horde", level = 1, map = 1411, x = 0.433, y = 0.685,
    spells = { 6673 }, bag = { [1] = { 6948 } }, equipped = {} },
  ["undead-mage"] = { race = "Scourge", class = "MAGE", faction = "Horde", level = 1, map = 1420, x = 0.302, y = 0.716,
    spells = { 133, 168 }, bag = { [1] = { 6948 }, [2] = { 159, 4 } }, equipped = {} },
  ["tauren-druid"] = { race = "Tauren", class = "DRUID", faction = "Horde", level = 1, map = 1412, x = 0.445, y = 0.775,
    spells = { 5176, 5185 }, bag = { [1] = { 6948 }, [2] = { 159, 4 } }, equipped = {} },
  ["troll-shaman"] = { race = "Troll", class = "SHAMAN", faction = "Horde", level = 1, map = 1411, x = 0.433, y = 0.685,
    bag = { [1] = { 6948 } }, equipped = {} },
  ["skyborne-hunter"] = { race = "Skyborne", class = "HUNTER", faction = "Horde", level = 1, map = 2521, x = 0.428, y = 0.234,
    bag = { [1] = { 6948 } }, equipped = {} },
}

-- Captures registrations the add-on keeps in locals (tabs, module slash subcommands) by wrapping the public
-- registration functions right after the file that defines them is loaded.
Sim.tabs, Sim.slashModules = {}, {}
Sim.afterFile["Core/Slash.lua"] = function()
  local S = Sim.ns.Slash
  local orig = S.Register
  S.Register = function(self, name, fn, help)
    local ok = orig(self, name, fn, help)
    if ok then Sim.slashModules[#Sim.slashModules + 1] = name end
    return ok
  end
end
Sim.afterFile["UI/Panel.lua"] = function()
  local UI = Sim.ns.UI
  local orig = UI.RegisterTab
  UI.RegisterTab = function(self, t)
    if type(t) == "table" and t.key then
      local dup = false
      for _, x in ipairs(Sim.tabs) do if x.key == t.key then dup = true end end
      if not dup then Sim.tabs[#Sim.tabs + 1] = t end
    end
    return orig(self, t)
  end
end

-- Accessors ----------------------------------------------------------------------
function S() return Sim.ns end
function StepId()
  local step = Sim.ns.Engine:CurrentStep()
  return step and step.id
end
function StepIndexOf(id)
  for i, e in ipairs(Sim.ns.Engine:Steps()) do if e.step.id == id then return i end end
end
function HudTitle() return SendaHUD and SendaHUD.title:GetText() or "" end
function HudText() return SendaHUD and SendaHUD.text:GetText() or "" end
function ArrowTarget()
  local t, src = Sim.ns.Arrow:GetTarget()
  return t, src
end
function Plain(s) return Sim.StripCodes(s or "") end

function Slash(msg)
  Sim.Out("  /senda " .. msg)
  local before = #Sim.chat
  Sim.SafeCall("SlashCmdList.SENDA('" .. msg .. "')", SlashCmdList.SENDA, msg)
  Sim.Advance(0.3)
  local lines = {}
  for i = before + 1, #Sim.chat do lines[#lines + 1] = Sim.chat[i] end
  return lines
end

-- Builds and refreshes every registered tab through the panel, then calls each refresh directly
-- (the panel wraps refresh in a silent pcall, so a direct call is what surfaces errors).
function RunAllTabs()
  local UI = Sim.ns.UI
  Sim.SafeCall("UI:ShowPanel", UI.ShowPanel, UI)
  Check(SendaMainFrame and SendaMainFrame:IsShown(), "main panel opens")
  for _, t in ipairs(Sim.tabs) do
    local errs = #Sim.errors
    Sim.SafeCall("UI:ShowTab(" .. t.key .. ")", UI.ShowTab, UI, t.key)
    Sim.Advance(0.2)
    if t.refresh then Sim.SafeCall("tab refresh " .. t.key, t.refresh) end
    Sim.Advance(0.2)
    Check(t.frame ~= nil and t.frame:IsShown() and #Sim.errors == errs, "tab '" .. t.key .. "' builds and refreshes")
  end
end

-- OnEnter/OnLeave of every visible widget that has one (tooltips are a classic source of nil errors).
function HoverAll()
  local n = 0
  for _, f in ipairs(Sim.AllWidgets()) do
    if f.__isFrame and f:IsVisible() and (f.__scripts.OnEnter or f.__hooks.OnEnter) then
      Sim.RunScript(f, "OnEnter")
      Sim.RunScript(f, "OnLeave")
      n = n + 1
    end
  end
  return n
end

-- Clicks (left, then right) every visible, enabled button under `root` that has an OnClick, accepting any
-- confirmation popup it opens. A fuzz pass over the UI: the point is only that nothing raises.
function ClickAll(root, skip)
  local list = {}
  local function walk(f)
    if f.__type == "Button" or f.__type == "CheckButton" then list[#list + 1] = f end
    for _, c in ipairs(f.__children) do walk(c) end
  end
  walk(root)
  local n = 0
  for _, f in ipairs(list) do
    if f:IsVisible() and f:IsEnabled() and (f.__scripts.OnClick or f.__hooks.OnClick) and not (skip and skip(f)) then
      for _, button in ipairs({ "LeftButton", "RightButton" }) do
        if f:IsVisible() and f:IsEnabled() then
          f:Click(button, false)
          n = n + 1
          Sim.Advance(0.1)
          if Sim.lastPopup then Sim.AcceptPopup(); Sim.Advance(0.1) end
        end
      end
    end
  end
  return n
end

-- Plays a guide end to end: for each current step, makes the game state satisfy its condition the way the
-- client would (quest log + events, position, spells, professions, taxi, hearth...) and checks that the engine
-- advances on its own. Manual steps (note/use, or anything still pending) are completed with the HUD's Done.
-- Returns { auto = n, manual = n, stuck = { "id (do)" ... } }.
function AutoPlay(maxSteps)
  local E = Sim.ns.Engine
  local p = Sim.player
  local res = { auto = 0, manual = 0, stuck = {} }
  local function ensureAccepted(q)
    if not p.quests[q] and not p.completed[q] then Sim.AcceptQuest(q, { { "Objetivo", 1 } }); Sim.Advance(0.1) end
  end
  for _ = 1, maxSteps or 2000 do
    local step, entry = E:CurrentStep()
    if not step then break end
    local sec = entry.section
    -- Al entrar en una sección, el personaje tiene el nivel con que la termina un jugador real:
    -- así las misiones con nivel mínimo dentro de la sección no se aplazan en el recorrido completo.
    if sec.levels and sec.levels[2] and p.level < sec.levels[2] then
      p.level = sec.levels[2]
      Sim.Fire("PLAYER_LEVEL_UP", p.level, 0, 0, 0, 0, 0, 0, 0, 0)
    end
    local f = step["if"]
    if f and f.minlevel and p.level < f.minlevel then
      p.level = f.minlevel
      Sim.Fire("PLAYER_LEVEL_UP", p.level, 0, 0, 0, 0, 0, 0, 0, 0)
    end
    local d = step["do"]
    local qs = step.quests or (step.quest and { step.quest }) or {}
    local manual = false
    if d == "accept" then
      for _, q in ipairs(qs) do ensureAccepted(q) end
    elseif d == "complete" then
      for _, q in ipairs(qs) do
        ensureAccepted(q)
        if p.quests[q] then
          if step.obj and p.quests[q].objectives[step.obj] then Sim.ProgressQuest(q, step.obj, 99)
          else Sim.FinishQuestObjectives(q) end
        end
      end
    elseif d == "turnin" or d == "dungeon" then
      if #qs == 0 then manual = true end
      for _, q in ipairs(qs) do
        ensureAccepted(q)
        if p.quests[q] then Sim.FinishQuestObjectives(q); Sim.TurnInQuest(q) end
      end
    elseif d == "goto" then
      if step.at then Sim.MoveTo(step.at[1], step.at[2] / 100, step.at[3] / 100) else manual = true end
    elseif d == "train" then
      for _, id in ipairs(step.spells or {}) do Sim.LearnSpell(id) end
      if not step.spells then manual = true end
    elseif d == "learn_prof" or d == "skill" then
      local key = step.prof
      local line = Sim.ns.Compat.PROF_SKILLLINE[key]
      local found
      for _, pr in ipairs(p.profs) do if pr.skillLine == line then found = pr end end
      if not found and #p.profs < 2 then
        found = { name = key, skillLine = line, rank = 1, max = 75 }
        table.insert(p.profs, found)
      end
      if found and step.skill then found.rank = math.max(found.rank, step.skill); found.max = math.max(found.max, found.rank) end
      if not found then manual = true end
      Sim.Fire("SKILL_LINES_CHANGED")
    elseif d == "buy" or d == "have" or d == "loot" then
      Sim.AddItem(step.item, step.count or 1)
      Sim.Fire("BAG_UPDATE_DELAYED")
    elseif d == "level" then
      p.level = math.max(p.level, step.level or p.level)
      Sim.Fire("PLAYER_LEVEL_UP", p.level, 0, 0, 0, 0, 0, 0, 0, 0)
    elseif d == "sethearth" then
      if step.at then Sim.MoveTo(step.at[1], step.at[2] / 100, step.at[3] / 100) end
      Sim.Fire("HEARTHSTONE_BOUND")
    elseif d == "hearth" then
      Sim.Fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-hs", 8690)
      Sim.Advance(0.2)
      if step.zone then Sim.MoveTo(step.zone, 0.5, 0.5) else Sim.Fire("ZONE_CHANGED_NEW_AREA") end
    elseif d == "getfp" then
      local id = tonumber(step.node) or 900
      Sim.taxiNodes = { { nodeID = id, name = tostring(step.node), state = Enum.FlightPathState.Current } }
      if step.at then Sim.MoveTo(step.at[1], step.at[2] / 100, step.at[3] / 100) end
      Sim.Fire("TAXIMAP_OPENED", 1)
    elseif d == "fly" then
      p.onTaxi = true
      Sim.Fire("PLAYER_CONTROL_LOST")
      Sim.Advance(1)
      Sim.MoveTo(step.zone or p.map, 0.5, 0.5)
      p.onTaxi = false
      Sim.Fire("PLAYER_CONTROL_GAINED")
    else
      manual = true
    end
    Sim.Advance(2.5)
    local now = E:CurrentStep()
    if now ~= step then
      if manual then res.manual = res.manual + 1 else res.auto = res.auto + 1 end
    else
      if not manual and Sim.ns.Conditions:IsAuto(step) then
        res.stuck[#res.stuck + 1] = step.id .. " (" .. tostring(d) .. ")"
      else
        res.manual = res.manual + 1
      end
      Sim.Click(SendaHUD.done)
      Sim.Advance(0.5)
      if E:CurrentStep() == step then
        res.stuck[#res.stuck + 1] = step.id .. " (Done did not advance)"
        break
      end
    end
  end
  return res
end

-- Flips every registered option and restores it (runs every onChange handler).
function ToggleAllOptions()
  local O = Sim.ns.Options
  for _, o in ipairs(O:List()) do
    local v = O:Get(o.key)
    if o.type == "slider" then
      Sim.SafeCall("option " .. o.key, O.Set, O, o.key, o.min or 0)
      Sim.SafeCall("option " .. o.key, O.Set, O, o.key, v)
    else
      Sim.SafeCall("option " .. o.key, O.Set, O, o.key, not v)
      Sim.Advance(0.2)
      Sim.SafeCall("option " .. o.key, O.Set, O, o.key, v)
    end
    Sim.Advance(0.2)
  end
end

-- Two-player helpers ---------------------------------------------------------------
-- A small guide both a gnome warlock and a night elf druid follow, with one step for each class only:
-- dp-003 is the warlock's, dp-007 the druid's.
function DuoGuide()
  local G = Sim.ns.Guides
  local function st(id, d, extra)
    local s = { id = id, ["do"] = d, text = "Paso " .. id, status = "unverified" }
    for k, v in pairs(extra or {}) do s[k] = v end
    return s
  end
  G:RegisterSection({ id = "duo-prueba-1", title = "Pareja de prueba", levels = { 1, 10 }, map = 1438, steps = {
    st("dp-001", "accept", { quest = 9001 }),
    st("dp-002", "complete", { quest = 9001 }),
    st("dp-003", "note", { ["if"] = { class = { "WARLOCK" } } }),
    st("dp-004", "turnin", { quest = 9001 }),
    st("dp-005", "accept", { quest = 9002 }),
    st("dp-006", "complete", { quest = 9002 }),
    st("dp-007", "note", { ["if"] = { class = { "DRUID" } } }),
    st("dp-008", "turnin", { quest = 9002 }),
    st("dp-009", "accept", { quest = 9003 }),
    st("dp-010", "complete", { quest = 9003 }),
    st("dp-011", "turnin", { quest = 9003 }),
    st("dp-012", "note"),
  } })
  G:RegisterGuide({ id = "duo-prueba", title = "Pareja de prueba", faction = "Alliance", order = -1,
    sections = { "duo-prueba-1" } })
  Sim.ns.Engine:SetGuide("duo-prueba", true)
end

-- Joins `name` (class, race) to the party as party1 and fires the roster event.
function DuoJoin(name, class, race)
  Sim.party[1] = { name = name, class = class, race = race, level = Sim.player.level, quests = {} }
  Sim.Fire("GROUP_ROSTER_UPDATE")
end

-- A quest log as Party sends it, sorted: "q:a/b,c/d;q2:...". From the player's own log, or (member name)
-- from what Party received of that party member.
function DuoLog(member)
  local P = Sim.ns.Party
  local ids, by = {}, {}
  if member then
    for _, m in ipairs(P.Members()) do
      if m.name == member then
        for q, counts in pairs(m.quests) do
          local parts = {}
          for i, c in ipairs(counts) do parts[i] = c[1] .. "/" .. c[2] end
          by[q] = table.concat(parts, ",")
        end
      end
    end
  else
    by = P.ReadLog()
  end
  for q in pairs(by) do ids[#ids + 1] = q end
  table.sort(ids)
  local out = {}
  for i, q in ipairs(ids) do out[i] = q .. ":" .. by[q] end
  return table.concat(out, ";")
end

-- The party member `name` as Party knows it (nil until they answered).
function DuoMember(name)
  for _, m in ipairs(Sim.ns.Party.Members()) do if m.name == name then return m end end
end

-- Errors the add-on caught itself and only printed (pcall + Print/Debug) still count as failures.
local CHAT_ERROR_PATTERNS = { "%.lua:%d+:", "attempt to ", "bad argument", "stack traceback", "^Senda: Error:" }

function Sim.Finish()
  for _, line in ipairs(Sim.chat) do
    for _, p in ipairs(CHAT_ERROR_PATTERNS) do
      if line:find(p) then Sim.failures[#Sim.failures + 1] = "error printed to chat: " .. line; break end
    end
  end
  for _, e in ipairs(Sim.errors) do
    Sim.failures[#Sim.failures + 1] = "Lua error (" .. e.where .. "): " .. e.msg
  end
  for _, e in ipairs(Sim.apiErrors) do
    Sim.failures[#Sim.failures + 1] = "API misuse: " .. e
  end
  local um = {}
  for k, n in pairs(Sim.unknownMethods) do um[#um + 1] = k .. " x" .. n end
  table.sort(um)
  local mg = {}
  for k, n in pairs(Sim.missingGlobals) do mg[#mg + 1] = k end
  table.sort(mg)
  __report("failures", #Sim.failures)
  __report("checks", Sim.checks)
  __report("failureText", table.concat(Sim.failures, "\n"))
  __report("unknownMethods", table.concat(um, ", "))
  __report("missingGlobals", table.concat(mg, ", "))
  __report("warnings", table.concat(Sim.warnings, "\n"))
end

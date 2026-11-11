#!/usr/bin/env node
// Headless simulation of the Senda add-on: runs the real addon/Senda files on fengari (Lua VM in JS)
// against a mocked WoW Mainline 12.x API (tests/wowsim/mock/*.lua) and plays a set of scenarios.
// Each scenario gets a fresh Lua state (= a fresh client session). Exit code 1 if anything fails.
//
//   node run.js            all scenarios
//   node run.js b g        only those (g needs b's SavedVariables, so b runs first anyway)
//   node run.js -v         verbose (every fired event)
'use strict';

// Lua 5.1 prints integral floats as "3", not "3.0": WoW runs 5.1.
process.env.FENGARICONF = JSON.stringify({ LUA_COMPAT_FLOATSTRING: true });

const fs = require('fs');
const path = require('path');
const { lua, lauxlib, lualib, to_luastring, to_jsstring } = require('fengari');

const HERE = __dirname;
const ROOT = path.resolve(HERE, '..', '..');
const ADDON_ROOT = path.join(ROOT, 'addon').split(path.sep).join('/');
const MOCK_FILES = ['compat51', 'core', 'frames', 'api', 'loader'].map((n) => path.join(HERE, 'mock', n + '.lua'));
const SCENARIO_HELPERS = path.join(HERE, 'scenario.lua');

const args = process.argv.slice(2);
const VERBOSE = args.includes('-v');
const only = args.filter((a) => !a.startsWith('-'));

// ---------------------------------------------------------------------------
// Lua state
// ---------------------------------------------------------------------------

function pushJsString(L, s) {
  lua.lua_pushstring(L, to_luastring(s));
}

function newState(report) {
  const L = lauxlib.luaL_newstate();
  lualib.luaL_openlibs(L);
  lua.lua_pushjsfunction(L, (L) => {
    const p = lua.lua_tojsstring(L, 1);
    let buf;
    try {
      buf = fs.readFileSync(p);
    } catch (e) {
      lua.lua_pushnil(L);
      return 1;
    }
    lua.lua_pushstring(L, Uint8Array.from(buf)); // raw bytes: the add-on is UTF-8, Lua strings are bytes
    return 1;
  });
  lua.lua_setglobal(L, to_luastring('__readfile'));
  lua.lua_pushjsfunction(L, (L) => {
    console.log(lua.lua_tojsstring(L, 1));
    return 0;
  });
  lua.lua_setglobal(L, to_luastring('__out'));
  lua.lua_pushjsfunction(L, (L) => {
    const k = lua.lua_tojsstring(L, 1);
    const t = lua.lua_type(L, 2);
    report[k] = t === lua.LUA_TNUMBER ? lua.lua_tonumber(L, 2) : (t === lua.LUA_TNIL ? null : lua.lua_tojsstring(L, 2));
    return 0;
  });
  lua.lua_setglobal(L, to_luastring('__report'));
  return L;
}

// Runs a chunk with a traceback handler. Returns null or the error text.
function run(L, code, chunkname) {
  lua.lua_getglobal(L, to_luastring('debug'));
  lua.lua_getfield(L, -1, to_luastring('traceback'));
  lua.lua_remove(L, -2);
  const base = lua.lua_gettop(L);
  const st = lauxlib.luaL_loadbuffer(L, to_luastring(code), null, to_luastring(chunkname));
  if (st !== lua.LUA_OK) {
    const err = lua.lua_tojsstring(L, -1);
    lua.lua_settop(L, base - 1);
    return err;
  }
  const r = lua.lua_pcall(L, 0, 0, base);
  let err = null;
  if (r !== lua.LUA_OK) err = lua.lua_tojsstring(L, -1);
  lua.lua_settop(L, base - 1);
  return err;
}

function runFile(L, file) {
  const code = fs.readFileSync(file, 'utf8');
  return run(L, code, '@' + path.relative(ROOT, file).split(path.sep).join('/'));
}

// ---------------------------------------------------------------------------
// Scenarios. `lua` runs after the mock is ready and the character is set up; it calls Login() itself.
// ---------------------------------------------------------------------------

const L_ = String.raw;

const SCENARIO_SWEEP = L_`
  Login()
  Sim.party[1] = { name = "Compi", class = "MAGE", level = 1, quests = {} }
  Sim.Fire("GROUP_ROSTER_UPDATE")
  RunAllTabs()
  local errs = #Sim.errors
  local byKey = {}
  for _, t in ipairs(Sim.tabs) do byKey[t.key] = t end
  for lvl = 1, 60 do
    Sim.player.level = lvl
    Sim.party[1].level = math.max(1, lvl - 3)
    Sim.Fire("PLAYER_LEVEL_UP", lvl, 0, 0, 0, 0, 0, 0, 0, 0)
    Sim.Advance(1.2)
    for _, t in ipairs(Sim.tabs) do
      if t.refresh then Sim.SafeCall("tab refresh " .. t.key .. " at level " .. lvl, t.refresh) end
    end
    if lvl == 1 or lvl % 20 == 0 then
      -- page through every bracket (not only the one of this level) with the tabs' own < > buttons
      for _, key in ipairs({ "levels", "notes", "duo" }) do
        S().UI:ShowTab(key)
        for _ = 1, 5 do ClickAll(byKey[key].frame) end
      end
    end
  end
  Check(#Sim.errors == errs, "every tab renders at every level 1-60")
`;

const SCENARIO_E = L_`
      Login()
      local cmds = { "", "", "help", "ayuda", "hud", "hud", "guide", "guia", "guide human-mage", "guide gnome-warlock",
        "guide no-such-guide", "way 30 70 Prueba", "way 30.5,70.2 Coma", "way", "way 120 5", "way clear", "map",
        "debug", "debug", "export", "exportar", "reset", "reset", "reiniciar", "comando-raro" }
      for _, c in ipairs(cmds) do Slash(c) end
      Check(S().Engine:GuideId() == "gnome-warlock", "guide switched back with /senda guide")
      Check(SendaCopyDialog and SendaCopyDialog:IsShown(), "/senda export opens the copy dialog")
      Section("module subcommands (" .. #Sim.slashModules .. ")")
      for _, name in ipairs(Sim.slashModules) do
        Slash(name)
        Slash(name .. " help")
      end
      Check(true, #Sim.slashModules .. " module subcommand(s) ran")
      Section("panel tabs")
      Check(#Sim.tabs >= 10, "tabs registered: " .. #Sim.tabs)
      RunAllTabs()
      Check(HoverAll() > 0, "tooltips (OnEnter) of every visible widget run")
      Section("options")
      ToggleAllOptions()
      Check(true, "every option toggled and restored")
      Slash("")
      Check(not SendaMainFrame:IsShown(), "/senda toggles the panel closed")

      Section("click every button of every tab, the HUD, the arrow and the minimap button")
      local errs = #Sim.errors
      for _, t in ipairs(Sim.tabs) do
        if not SendaMainFrame:IsShown() then S().UI:ShowPanel() end
        S().UI:ShowTab(t.key)
        Sim.Advance(0.2)
        local n = ClickAll(t.frame)
        if SendaDropdownList and SendaDropdownList:IsShown() then n = n + ClickAll(SendaDropdownList) end
        Sim.Out("    tab " .. t.key .. ": " .. n .. " clicks")
      end
      Slash("way 35 75 Manual")
      ClickAll(SendaHUD)
      ClickAll(SendaArrow)
      Sim.shift = true; ClickAll(SendaMinimapButton); Sim.shift = false
      ClickAll(SendaMinimapButton)
      Sim.RunScript(SendaMinimapButton, "OnDragStart"); Sim.Advance(0.2); Sim.RunScript(SendaMinimapButton, "OnDragStop")
      Check(#Sim.errors == errs, "UI click pass raised no errors")

      Section("world map pin")
      S().Engine:SetGuide("gnome-warlock", true)
      Sim.Advance(1)
      WorldMapFrame:Show()
      Sim.Advance(0.5)
      Check(SendaWorldMapPin and SendaWorldMapPin:IsShown(), "map pin shown on the world map for the arrow target")
      WorldMapFrame.mapID = 1414
      Sim.Advance(0.5)
      Check(not SendaWorldMapPin:IsShown(), "map pin hidden on another continent's map")
      WorldMapFrame:Hide()

      Section("finish the guide")
      local E = S().Engine
      E:JumpTo(#E:Steps())
      Sim.Advance(0.5)
      Sim.Click(SendaHUD.done)
      Sim.Advance(1)
      Check(E:IsFinished(), "Done on the last step finishes the guide")
      Check(Plain(HudTitle()) == S().L.GUIDE_FINISHED, "HUD shows the finished state", HudTitle())
      local _, src = ArrowTarget()
      Check(src == nil, "no arrow target once finished", src)
      Sim.Click(SendaHUD.back)
      Sim.Advance(0.5)
      Check(not E:IsFinished(), "Back from the finished state returns to the last step")
    `;

const scenarios = [
  {
    id: 'a',
    title: 'Gnome warlock level 1 logs in',
    char: 'gnome-warlock',
    lua: L_`
      Login()
      local E = S().Engine
      Check(E:GuideId() == "gnome-warlock", "guide gnome-warlock auto-selected", E:GuideId())
      Check(StepId() == "coldridge-001", "first step is coldridge-001", StepId())
      Check(SendaHUD and SendaHUD:IsShown(), "HUD is shown")
      local title = Plain(HudTitle())
      Check(title:find("Acepta", 1, true) ~= nil, "HUD title shows the step type", title)
      Check(title:find(Sim.QUEST_TITLES[179], 1, true) ~= nil, "HUD title shows the quest name (after QUEST_DATA_LOAD_RESULT)", title)
      Check(Plain(HudText()):find("Sten Stoutarm", 1, true) ~= nil, "HUD shows the step text", HudText())
      local t, src = ArrowTarget()
      Check(src == "guide" and t and t.map == 1426, "arrow follows the guide step", src)
      Check(SendaArrow and SendaArrow:IsShown(), "arrow is shown")
      Check(SendaMinimapButton ~= nil and SendaMinimapButton:IsShown(), "minimap button is shown")
      local found = false
      for _, l in ipairs(Sim.chat) do if l:find("Brujo gnomo", 1, true) then found = true end end
      Check(found, "chat announces the selected guide")
      Section("generated guide data as the engine sees it")
      local G = S().Guides
      for _, g in ipairs(G:List()) do
        Check(#G:SectionsOf(g.id) == #g.sections, g.id .. ": every listed section is registered")
        local seen, dup, badAt = {}, {}, {}
        for _, sec in ipairs(G:SectionsOf(g.id)) do
          for _, st in ipairs(sec.steps) do
            if seen[st.id] then dup[#dup + 1] = st.id end
            seen[st.id] = true
            local at = st.at
            if at and not (type(at[1]) == "number" and at[2] and at[3] and at[2] >= 0 and at[2] <= 100 and at[3] >= 0 and at[3] <= 100) then
              badAt[#badAt + 1] = st.id
            end
          end
        end
        Check(#dup == 0, g.id .. ": step ids are unique", table.concat(dup, ", "))
        Check(#badAt == 0, g.id .. ": every 'at' is [uiMapID, 0-100, 0-100]", table.concat(badAt, ", "))
      end
    `,
  },
  {
    id: 'b',
    title: 'Quest accept/turn-in, level up, goto by position',
    char: 'gnome-warlock',
    lua: L_`
      Login()
      local E = S().Engine
      Check(StepId() == "coldridge-001", "starts at coldridge-001", StepId())

      Section("QUEST_ACCEPTED 179")
      Sim.AcceptQuest(179, { { "Carne de lobo: 0/8", 8 } })
      Sim.Advance(1)
      Check(StepId() == "coldridge-002", "accept step completes -> coldridge-002 (complete 179)", StepId())
      Check(Plain(HudTitle()):find("Completa", 1, true) ~= nil, "HUD shows the complete step", HudTitle())
      local t2 = ArrowTarget()
      Check(t2 and math.abs(t2.x - 0.288) < 1e-6, "arrow points at the step's 'at'")
      Sim.MoveTo(1426, 0.288, 0.738)
      Sim.Advance(0.5)
      t2 = ArrowTarget()
      Check(t2 and t2.label == "Lobos al este", "arriving at 'at' moves the arrow on to the step's wps[1]", t2 and t2.label)
      Sim.MoveTo(1426, 0.300, 0.715)
      Sim.ProgressQuest(179, 1, 3)
      Sim.Advance(1)
      Check(StepId() == "coldridge-002", "partial objectives keep the step", StepId())
      Check(Plain(SendaHUD.objectives:GetText()):find("Carne de lobo", 1, true) ~= nil, "HUD lists the quest objectives",
        SendaHUD.objectives:GetText())
      Sim.FinishQuestObjectives(179)
      Sim.Advance(1)
      Check(StepId() == "coldridge-003", "objectives done -> coldridge-003 (turn in)", StepId())

      Section("QUEST_TURNED_IN 179")
      Sim.TurnInQuest(179)
      Sim.Advance(1)
      Check(StepId() == "coldridge-004", "turn-in completes -> coldridge-004", StepId())
      local p = S():GuideProgress("gnome-warlock")
      Check(p.done["coldridge-001"] == "a" and p.done["coldridge-003"] == "a", "auto-completed steps are marked 'a'")

      Section("HUD buttons")
      Sim.Click(SendaHUD.done)
      Sim.Advance(0.5)
      Check(StepId() == "coldridge-005" and p.done["coldridge-004"] == "d", "Done marks 004 'd' and moves on", StepId())
      Sim.Click(SendaHUD.back)
      Sim.Advance(0.5)
      Check(StepId() == "coldridge-004" and p.done["coldridge-004"] == nil, "Back returns to 004 and unmarks it", StepId())
      Sim.AcceptQuest(3115)
      Sim.Advance(1)
      Check(StepId() == "coldridge-005", "accepting 3115 completes the held step", StepId())
      Sim.Click(SendaHUD.skip)
      Sim.Advance(0.5)
      Check(p.done["coldridge-005"] == "s", "Skip marks 's'", p.done["coldridge-005"])

      Section("PLAYER_LEVEL_UP")
      Sim.player.level = 2
      Sim.Fire("PLAYER_LEVEL_UP", 2, 15, 0, 0, 1, 0, 0, 0, 0)
      Sim.Advance(2)
      Check(#Sim.errors == 0, "level up handled without errors")

      Section("goto step completes by position")
      local gi = StepIndexOf("coldridge-042")
      Check(gi ~= nil, "goto step coldridge-042 exists")
      E:JumpTo(gi)
      Sim.Advance(1)
      Check(StepId() == "coldridge-042", "jumped to the goto step", StepId())
      Sim.MoveTo(1426, 0.36, 0.67)
      Sim.Advance(2)
      Check(StepId() == "coldridge-042", "still far (> radius): goto pending", StepId())
      local t = ArrowTarget()
      Check(t and math.abs(t.x - 0.41) < 1e-6 and math.abs(t.y - 0.63) < 1e-6, "arrow points at the goto target")
      Check(Plain(SendaArrow.info:GetText()):find("%d+ m") ~= nil, "arrow shows the distance", SendaArrow.info:GetText())
      Sim.MoveTo(1426, 0.4095, 0.6305)
      Sim.Advance(2)
      Check(p.done["coldridge-042"] == "a", "arriving within the radius completes the goto (ticker + C_Timer)", p.done["coldridge-042"])
      Check(StepId() ~= "coldridge-042" and E:Index() > gi, "engine moved past the goto step", StepId())
      __report("expectStep", StepId())
      local n = 0
      for _ in pairs(p.done) do n = n + 1 end
      __report("expectDone", n)
      __report("saved", Sim.SaveVariables())
      __report("world", Sim.ExportWorld())
    `,
  },
  {
    id: 'c',
    title: 'Human mage logs in (and every tab with mage data)',
    char: 'human-mage',
    lua: L_`
      Login()
      local E = S().Engine
      Check(E:GuideId() == "human-mage", "guide human-mage auto-selected", E:GuideId())
      Check(StepId() ~= nil, "a current step exists", StepId())
      Check(SendaHUD:IsShown() and Plain(HudTitle()) ~= "", "HUD shows the first step", HudTitle())
      RunAllTabs()
      Check(HoverAll() > 0, "tooltips (OnEnter) of every visible widget run")
    `,
  },
  {
    id: 'd',
    title: 'Death: corpse arrow, then back to the guide',
    char: 'gnome-warlock',
    lua: L_`
      Login()
      local L = S().L
      local t0, src0 = ArrowTarget()
      local guideLabel = t0 and t0.label
      Check(src0 == "guide" and guideLabel, "arrow starts on the guide target", tostring(guideLabel))
      Sim.player.dead = true
      Sim.Fire("PLAYER_DEAD")
      Sim.Advance(1.5)
      local _, src = ArrowTarget()
      Check(src == "guide", "dead (not released): still the guide target", src)

      Section("release spirit (ghost)")
      Sim.player.dead, Sim.player.ghost = false, true
      Sim.player.corpse = { map = 1426, x = 0.300, y = 0.715 }
      Sim.MoveTo(1426, 0.33, 0.55)
      Sim.Fire("PLAYER_ALIVE")
      Sim.Advance(1.5)
      local t, src2 = ArrowTarget()
      Check(src2 == "corpse", "ghost: arrow source is the corpse", src2)
      Check(t and t.label == L.CORPSE, "ghost: arrow label is the corpse", t and t.label)
      Check(t and math.abs(t.x - 0.300) < 1e-6 and math.abs(t.y - 0.715) < 1e-6, "arrow points at C_DeathInfo.GetCorpseMapPosition")
      Check(Plain(SendaArrow.label:GetText()) == L.CORPSE, "arrow frame shows the corpse label", SendaArrow.label:GetText())
      Sim.MoveTo(1426, 0.301, 0.712)
      Sim.Fire("CORPSE_IN_RANGE")
      Sim.Advance(1.5)
      t = ArrowTarget()
      Check(t and t.label == L.CORPSE_IN_RANGE, "CORPSE_IN_RANGE updates the label", t and t.label)

      Section("resurrect")
      Sim.player.ghost = false
      Sim.player.corpse = nil
      Sim.Fire("PLAYER_UNGHOST")
      Sim.Fire("PLAYER_ALIVE")
      Sim.Advance(1.5)
      local t3, src3 = ArrowTarget()
      Check(src3 == "guide", "PLAYER_UNGHOST restores the guide target", src3)
      Check(t3 and t3.label == guideLabel, "guide label restored", t3 and t3.label)
    `,
  },
  {
    id: 'e',
    title: 'Every /senda subcommand and every panel tab',
    char: 'gnome-warlock',
    lua: SCENARIO_E,
  },
  {
    id: 'e2',
    title: 'Same as e on an English client (enUS strings and format arguments)',
    char: 'gnome-warlock',
    locale: 'enUS',
    lua: SCENARIO_E,
  },
  {
    id: 'f',
    title: 'Merchant, trainer, bags, quest rewards, combat, tooltips, misc events',
    char: 'gnome-warlock',
    lua: L_`
      Sim.CHARS["gnome-warlock"].level = 5
      Login()
      Sim.player.level = 5

      Section("merchant")
      Sim.merchant = { { id = 159, price = 25, stack = 5 }, { id = 1179, price = 125, stack = 5 },
        { id = 4540, price = 25, stack = 5 }, { id = 2996, price = 100, stack = 1, avail = 2 } }
      MerchantFrame:Show()
      Sim.Fire("PLAYER_INTERACTION_MANAGER_FRAME_SHOW", Enum.PlayerInteractionType.Merchant)
      Sim.Fire("MERCHANT_SHOW")
      Sim.Advance(1)
      Check(SendaVendorPanel and SendaVendorPanel:IsShown(), "vendor shopping list is shown")
      local buy
      for _, f in ipairs(Sim.AllWidgets()) do
        if f.__type == "Button" and f:GetParent() == SendaVendorPanel and Plain(f:GetText() or ""):find("^Comprar") then buy = f end
      end
      Check(buy and buy:IsEnabled(), "buy button enabled (food and drink to buy)", buy and buy:GetText())
      if buy then
        Sim.Click(buy)
        Check(Sim.lastPopup ~= nil, "buy asks for confirmation")
        Sim.AcceptPopup()
        Sim.Advance(1)
        Check(#Sim.purchases > 0, "confirmed purchase calls BuyMerchantItem", #Sim.purchases)
      end
      S().Modules.Vendor.SellGreys()
      Sim.Advance(1)
      Check((Sim.sold or 0) >= 2, "grey items sold", Sim.sold)
      Sim.Fire("MERCHANT_UPDATE")
      Sim.Fire("BAG_UPDATE_DELAYED")
      Sim.Advance(1)
      MerchantFrame:Hide()
      Sim.Fire("MERCHANT_CLOSED")
      Sim.Advance(0.5)

      Section("trainer")
      CreateFrame("Frame", "ClassTrainerFrame", UIParent) -- Blizzard_TrainerUI is load-on-demand
      Sim.trainer = { { spell = 348, cost = 10 }, { spell = 172, cost = 100 }, { spell = 702, cost = 100 },
        { spell = 1454, cost = 500, category = "unavailable" } }
      Sim.Fire("TRAINER_SHOW")
      Sim.Advance(1)
      Check(SendaTrainerPanel and SendaTrainerPanel:IsShown(), "trainer panel is shown")
      Sim.Fire("TRAINER_UPDATE")
      Sim.Advance(1)
      ClassTrainerFrame:Hide()
      Sim.Fire("TRAINER_CLOSED")

      Section("bags")
      Sim.AddItem(3000, 1)
      Sim.Fire("BAG_UPDATE")
      Sim.Fire("BAG_UPDATE_DELAYED")
      Sim.Advance(3)

      Section("quest rewards (QUEST_COMPLETE)")
      Sim.questChoices = { 3001, 3000 }
      Sim.Fire("QUEST_COMPLETE")
      Sim.Advance(0.5)
      local m = QuestInfoRewardsFrame.RewardButtons[2].sendaMark
      Check(m and m:IsShown() and Plain(m:GetText()):find("MEJOR") ~= nil, "best reward marked", m and m:GetText())
      Sim.Fire("QUEST_FINISHED")
      Sim.Advance(0.2)

      Section("combat")
      Sim.player.combat = true
      Sim.Fire("PLAYER_REGEN_DISABLED")
      Sim.Fire("QUEST_LOG_UPDATE")
      Sim.Fire("BAG_UPDATE_DELAYED")
      Sim.Fire("UNIT_AURA", "player")
      Sim.Advance(2)
      Sim.player.combat = false
      Sim.Fire("PLAYER_REGEN_ENABLED")
      Sim.Advance(3)

      Section("tooltip hooks")
      Check(#(Sim.tooltipPostCalls[Enum.TooltipDataType.Item] or {}) > 0, "an item tooltip post-call is registered")
      GameTooltip:SetOwner(UIParent, "ANCHOR_NONE")
      GameTooltip:SetHyperlink(Sim.ItemLink(15970))
      local lines = table.concat(GameTooltip:Lines(), "\n")
      Check(Plain(lines):find("Senda:", 1, true) ~= nil, "item tooltip gets the Senda line", lines)
      GameTooltip:SetOwner(UIParent, "ANCHOR_NONE")
      GameTooltip:SetHyperlink(Sim.ItemLink(3001))
      Check(Plain(table.concat(GameTooltip:Lines(), "\n")):find("Senda:", 1, true) ~= nil, "mail item tooltip says it is not for you")
      ItemRefTooltip:SetOwner(UIParent, "ANCHOR_NONE")
      ItemRefTooltip:SetHyperlink(Sim.ItemLink(6948))
      GameTooltip:Hide()

      Section("misc events")
      Sim.npc = { id = 658, name = "Sten Stoutarm" }
      Sim.AcceptQuest(179, { { "Carne de lobo", 8 } })
      Sim.taxiNodes = { { nodeID = 6, name = "Forjaz, Dun Morogh", state = Enum.FlightPathState.Current } }
      Sim.Fire("TAXIMAP_OPENED", 1)
      Sim.Fire("HEARTHSTONE_BOUND")
      Sim.Fire("UNIT_SPELLCAST_SUCCEEDED", "player", "Cast-1", 8690)
      Sim.party[1] = { name = "Compi", class = "MAGE", level = 6, quests = { [179] = true } }
      Sim.Fire("GROUP_ROSTER_UPDATE")
      Sim.player.pet = true
      Sim.Fire("UNIT_PET", "player")
      Sim.Fire("SKILL_LINES_CHANGED")
      Sim.Fire("BANKFRAME_OPENED")
      Sim.Fire("BANKFRAME_CLOSED")
      Sim.LearnSpell(348)
      Sim.Fire("ZONE_CHANGED")
      Sim.Fire("ZONE_CHANGED_NEW_AREA")
      Sim.Fire("PLAYER_CONTROL_LOST")
      Sim.Fire("PLAYER_CONTROL_GAINED")
      Sim.Fire("CHAT_MSG_SKILL", "skill")
      Sim.Fire("QUEST_DETAIL")
      Sim.Advance(6)

      Section("macros and bars")
      S().Modules.Macros.CreateAll()
      Sim.Advance(1)
      Sim.knowAll = true -- every spell known: every macro whose spells resolve gets created
      Sim.player.level = 60
      Sim.Fire("SPELLS_CHANGED")
      Sim.Advance(1)
      S().Modules.Macros.CreateAll()
      Sim.Advance(1)
      Check(#Sim.macros > 0, "macros created once their spells are known", #Sim.macros)
      for _, m in ipairs(Sim.macros) do
        Check(m.name:sub(1, 4) == "SND_" and not m.body:find("{", 1, true), "macro " .. m.name .. " fully resolved", m.body)
      end
      Sim.AddItem(5512, 1)
      Sim.Fire("BAG_UPDATE_DELAYED")
      Sim.Advance(2)
      Sim.Fire("PLAYER_LEVEL_UP", 60, 0, 0, 0, 0, 0, 0, 0, 0)
      Sim.Advance(2)
      S().Modules.Bars.Place()
      Sim.Advance(1)
      Check(next(Sim.actions) ~= nil, "Bars.Place put something on the action bars")
      RunAllTabs()
    `,
  },
  {
    id: 'h',
    title: 'Play the whole gnome-warlock guide: every auto step completes on its own',
    char: 'gnome-warlock',
    lua: L_`
      Login()
      local r = AutoPlay(3000)
      Sim.Out(string.format("    auto %d, manual %d, stuck %d", r.auto, r.manual, #r.stuck))
      Check(S().Engine:IsFinished(), "guide finished", StepId())
      Check(#r.stuck == 0, "no auto-detectable step got stuck", table.concat(r.stuck, ", "))
    `,
  },
  {
    id: 'i',
    title: 'Play the whole human-mage guide: every auto step completes on its own',
    char: 'human-mage',
    lua: L_`
      Login()
      local r = AutoPlay(3000)
      Sim.Out(string.format("    auto %d, manual %d, stuck %d", r.auto, r.manual, #r.stuck))
      Check(S().Engine:IsFinished(), "guide finished", StepId())
      Check(#r.stuck == 0, "no auto-detectable step got stuck", table.concat(r.stuck, ", "))
    `,
  },
  {
    id: 'k',
    title: 'Character without a guide (night elf warrior): HUD, slash and panel still work',
    char: 'nightelf-warrior',
    lua: L_`
      Login()
      local E = S().Engine
      Check(E:GuideId() == nil, "no guide selected", E:GuideId())
      Check(Plain(HudTitle()) == S().L.NO_GUIDE, "HUD shows 'no guide'", HudTitle())
      for _, c in ipairs({ "", "guide", "map", "way 40 40", "reset", "reset", "hud", "hud" }) do Slash(c) end
      ClickAll(SendaHUD)
      RunAllTabs()
      HoverAll()
      Slash("guide gnome-warlock")
      Check(E:GuideId() == "gnome-warlock", "a guide can still be chosen by hand")
    `,
  },
  {
    id: 'l',
    title: 'Existing character installs Senda (level 7, Coldridge done, reload in combat)',
    char: 'gnome-warlock',
    lua: L_`
      local cfg = Sim.CHARS["gnome-warlock"]
      cfg.level, cfg.map, cfg.x, cfg.y = 7, 1426, 0.46, 0.53
      local done = {}
      for _, q in ipairs({ 179, 3115, 233, 170, 234, 183, 182, 3364, 3365, 1599, 3361, 97277, 218, 282 }) do done[q] = true end
      cfg.completed = done
      cfg.combat = true
      Login()
      local E = S().Engine
      Check(E:GuideId() == "gnome-warlock", "guide selected while in combat")
      Sim.player.combat = false
      Sim.Fire("PLAYER_REGEN_ENABLED")
      Sim.Advance(6)
      -- coldridge-038 is the last turn-in among those quests; 039 accepts 420, still pending
      Check(StepId() == "coldridge-039", "resumes right after the last turned-in quest of the route", StepId())
      Check(SendaDisenchantButton ~= nil, "secure button created after combat")
      RunAllTabs()
    `,
  },
  {
    id: 'm',
    title: 'Levels 1-60: every tab and the level-up messages at every level (warlock)',
    char: 'gnome-warlock',
    lua: SCENARIO_SWEEP,
  },
  {
    id: 'm2',
    title: 'Levels 1-60: every tab and the level-up messages at every level (mage)',
    char: 'human-mage',
    lua: SCENARIO_SWEEP,
  },
  {
    id: 'n',
    title: 'Knowledge data reaches the modules (bars, macros, profession trainers, gear list)',
    char: 'human-mage',
    lua: L_`
      Sim.CHARS["human-mage"].level = 10
      Login()
      Sim.player.level = 10
      local M = S().Modules
      Section("bars: [[bar]] + [[bar.slot]] from the knowledge")
      local layout = M.Bars.Layout()
      local titles = {}
      for _, g in ipairs(layout) do titles[#titles + 1] = g.title end
      Check(#layout == 3 and titles[3]:find("Inferior derecha", 1, true) ~= nil, "bar layout comes from mage-bars (3 bars)", table.concat(titles, " | "))
      local armor
      for _, g in ipairs(layout) do for _, e in ipairs(g.rows) do if e.slot == 51 then armor = e end end end
      Check(armor and (armor.minlevel or 0) == 1, "slot level read from 'level'", armor and armor.minlevel)
      S().UI:ShowPanel(); S().UI:ShowTab("bars"); Sim.Advance(0.3)
      M.Bars.Place()
      Sim.Advance(0.5)
      Check(Sim.actions[51] and Sim.actions[51][2] == 168, "slot 51 gets the known alternative (Armadura de Escarcha, alt2)", Sim.actions[51] and Sim.actions[51][2])
      Check(Sim.actions[61] and Sim.actions[61][2] == 133, "slot 61 gets Bola de Fuego", Sim.actions[61] and Sim.actions[61][2])

      Section("macros: icon spell:/item:/name: and fallbacks")
      Sim.player.spells[5504] = true -- Conjurar agua (the body wants 587 + 5504; fallback only 5504)
      Sim.Fire("SPELLS_CHANGED")
      Sim.Advance(1)
      M.Macros.CreateAll()
      Sim.Advance(0.5)
      local made = {}
      for _, m in ipairs(Sim.macros) do made[m.name] = m end
      Check(made.SND_Conjurar ~= nil, "SND_Conjurar created from its fallback body", made.SND_Conjurar and made.SND_Conjurar.body)
      Check(made.SND_Piedra ~= nil and type(made.SND_Piedra.icon) == "number", "macro icon 'item:5512' resolved to a fileID", made.SND_Piedra and tostring(made.SND_Piedra.icon))

      Section("professions: page-level [[trainer]] (at, for_class, ranks)")
      local st = M.Professions.State("tailoring")
      Check(st.trainer ~= nil and st.trainer[1] == 1453, "tailoring trainer for a mage comes from [[trainer]] (Ventormenta)", st.trainer and table.concat(st.trainer, ", "))
      local ench = M.Professions.State("enchanting")
      Check(ench.missing and ench.trainer == nil, "enchanting for a mage: no Apprentice trainer with coordinates -> no arrow",
        ench.trainer and table.concat(ench.trainer, ", "))

      Section("gear: [[item]] list (Dónde buscar)")
      S().UI:ShowTab("gear"); Sim.Advance(1)
      M.Gear.Refresh(); Sim.Advance(0.5)
      local found = false
      for _, f in ipairs(Sim.AllWidgets()) do
        if f.__type == "FontString" and f:IsVisible() and (f:GetText() or ""):find("Dónde buscar", 1, true) then found = true end
      end
      Check(found, "gear tab lists the [[item]] entries for the level")
    `,
  },
  {
    id: 'g',
    title: 'Re-login with the SavedVariables of b: progress restored by step id',
    char: 'gnome-warlock',
    needs: 'b',
    lua: L_`
      Login()
      local E = S().Engine
      Check(E:GuideId() == "gnome-warlock", "saved guide restored", E:GuideId())
      Check(StepId() == SIM_EXPECT_STEP, "current step restored by id", tostring(StepId()) .. " vs " .. tostring(SIM_EXPECT_STEP))
      local p = S():GuideProgress("gnome-warlock")
      local n = 0
      for _ in pairs(p.done) do n = n + 1 end
      Check(n >= SIM_EXPECT_DONE, "marked steps restored", n .. " vs " .. SIM_EXPECT_DONE)
      Check(p.done["coldridge-004"] == "a" and p.done["coldridge-005"] == "s" and p.done["coldridge-042"] == "a",
        "marks kept with their kind (a/d/s)")
      local ok = Plain(HudTitle()) ~= ""
      Check(ok, "HUD shows the restored step", HudTitle())
    `,
  },
];

// ---------------------------------------------------------------------------
// Runner
// ---------------------------------------------------------------------------

function runScenario(sc, carry) {
  const report = {};
  const L = newState(report);
  for (const f of MOCK_FILES) {
    const err = runFile(L, f);
    if (err) return { report, fatal: 'mock ' + path.basename(f) + ': ' + err };
  }
  let err = runFile(L, SCENARIO_HELPERS);
  if (err) return { report, fatal: 'scenario.lua: ' + err };
  const saved = carry.saved || '';
  const prelude = `
    SIM_ROOT = ${JSON.stringify(ADDON_ROOT)}
    Sim.verbose = ${VERBOSE}
    SIM_EXPECT_STEP = ${JSON.stringify(carry.expectStep || null)}
    SIM_EXPECT_DONE = ${Number(carry.expectDone || 0)}
    Sim.locale = ${JSON.stringify(sc.locale || 'esES')}
    local cfg = Sim.CHARS[${JSON.stringify(sc.char)}]
    Sim.SetupCharacter(cfg)
    Sim.CreateGlobalFrames()
    Sim.ImportWorld(${JSON.stringify(carry.world || '')})
    function Login()
      Sim.SetupCharacter(cfg)
      Sim.ImportWorld(${JSON.stringify(carry.world || '')})
      WorldMapFrame.mapID = Sim.player.map
      Sim.PrepareClientEnv()
      Sim.Login(SIM_ROOT, ${JSON.stringify(saved)}, function()
        -- debug on: errors the add-on swallows into Senda:Debug reach the chat and fail the run
        SendaDB = SendaDB or {}
        SendaDB.opts = SendaDB.opts or {}
        SendaDB.opts.debug = true
      end)
    end
  `;
  err = run(L, prelude, '=prelude');
  if (err) return { report, fatal: 'prelude: ' + err };
  err = run(L, sc.lua, '=scenario ' + sc.id);
  if (err) {
    run(L, `Sim.RecordError(${JSON.stringify(err)}, "scenario body")`, '=x');
  }
  err = run(L, 'Sim.Finish()', '=finish');
  if (err) return { report, fatal: 'finish: ' + err };
  return { report };
}

// fengari is Lua 5.3: library functions that WoW's Lua 5.1 lacks would run here and fail in the client.
// (5.2+ syntax is already rejected by `luac5.1 -p` in CI.)
function lua51LibraryCheck() {
  const banned = /\b(table\.(pack|unpack|move)|math\.(type|tointeger|ult)|string\.(pack|unpack|packsize)|utf8\.|rawlen|coroutine\.isyieldable)\b|(^|[^\w.:])load\s*\(/;
  const problems = [];
  const walk = (dir) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) walk(p);
      else if (e.name.endsWith('.lua')) {
        fs.readFileSync(p, 'utf8').split('\n').forEach((line, i) => {
          const code = line.replace(/--.*$/, '');
          if (banned.test(code)) problems.push(`${path.relative(ROOT, p)}:${i + 1}: ${line.trim()}`);
        });
      }
    }
  };
  walk(path.join(ROOT, 'addon', 'Senda'));
  return problems;
}

function main() {
  const libProblems = lua51LibraryCheck();
  console.log(`=== Lua 5.1 library check: ${libProblems.length ? 'FAIL' : 'ok'} ===`);
  for (const p of libProblems) console.log('  ' + p);
  const wanted = new Set(only.length ? only : scenarios.map((s) => s.id));
  for (const s of scenarios) if (wanted.has(s.id) && s.needs) wanted.add(s.needs);
  const carry = {};
  const results = [];
  const allUnknown = new Set();
  const allMissing = new Set();
  for (const sc of scenarios) {
    if (!wanted.has(sc.id)) continue;
    console.log(`\n=== [${sc.id}] ${sc.title} (${sc.char}) ===`);
    const c = sc.needs ? carry[sc.needs] || {} : {};
    const t0 = Date.now();
    const { report, fatal } = runScenario(sc, c);
    carry[sc.id] = report;
    const failures = fatal ? 1 : report.failures || 0;
    if (fatal) console.log('  FATAL ' + fatal);
    if (report.failureText) console.log('  failures:\n    ' + report.failureText.split('\n').join('\n    '));
    for (const m of (report.unknownMethods || '').split(', ').filter(Boolean)) allUnknown.add(m.replace(/ x\d+$/, ''));
    for (const m of (report.missingGlobals || '').split(', ').filter(Boolean)) allMissing.add(m);
    console.log(`  -> ${failures ? 'FAILED' : 'passed'} (${report.checks || 0} checks, ${failures} failure(s), ${Date.now() - t0} ms)`);
    results.push({ id: sc.id, title: sc.title, failures });
  }
  console.log('\n=== Summary ===');
  for (const r of results) console.log(`  [${r.id}] ${r.failures ? 'FAIL' : 'ok  '} ${r.title}`);
  if (allUnknown.size) {
    console.log('\nWidget methods served by the permissive fallback (no-op), review against the real API:');
    console.log('  ' + [...allUnknown].sort().join(', '));
  }
  if (allMissing.size) {
    console.log('\nUndefined globals the add-on probed (nil on this mock; guarded by the add-on):');
    console.log('  ' + [...allMissing].sort().join(', '));
  }
  const failed = results.filter((r) => r.failures).length + (libProblems.length ? 1 : 0);
  console.log(failed ? `\n${failed} scenario(s) failed` : '\nAll scenarios passed');
  process.exit(failed ? 1 : 0);
}

main();

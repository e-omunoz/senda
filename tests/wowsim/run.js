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
const zlib = require('zlib');
const path = require('path');
const { lua, lauxlib, lualib, to_luastring, to_jsstring } = require('fengari');

const HERE = __dirname;
const ROOT = path.resolve(HERE, '..', '..');
const ADDON_ROOT = path.join(ROOT, 'addon').split(path.sep).join('/');
const MOCK_FILES = ['compat51', 'core', 'frames', 'api', 'nav', 'loader'].map((n) => path.join(HERE, 'mock', n + '.lua'));
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
  // zlib for the mock's C_EncodingUtil.DecompressString and the synthetic navigation packs (mock/nav.lua)
  for (const [name, fn] of [['__zinflate', zlib.inflateSync], ['__zdeflate', zlib.deflateSync]]) {
    lua.lua_pushjsfunction(L, (L) => {
      const raw = lua.lua_tolstring(L, 1);
      let out;
      try {
        out = fn(Buffer.from(raw));
      } catch (e) {
        lua.lua_pushnil(L);
        return 1;
      }
      const arr = Uint8Array.from(out);
      lua.lua_pushlstring(L, arr, arr.length);
      return 1;
    });
    lua.lua_setglobal(L, to_luastring(name));
  }
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
      -- the Mazmorras tab's buttons point the arrow on purpose (a target the player chose): drop it so the
      -- checks below see only the guide's own targets
      S().Modules.Dungeons.Clear()
      Slash("way 35 75 Manual")
      ClickAll(SendaHUD)
      ClickAll(SendaArrow)
      Sim.shift = true; ClickAll(SendaMinimapButton); Sim.shift = false
      ClickAll(SendaMinimapButton)  -- left click = hide-all toggle, right click = menu
      if SendaDropdownList then SendaDropdownList:Hide() end
      S().Visibility:SetHidden(false)
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
    id: 'macro',
    title: 'Conditional macros (#showtooltip) get the dynamic "?" icon, also when updating old ones',
    char: 'gnome-warlock',
    lua: L_`
      Login()
      Sim.Advance(6)
      local p = Sim.player
      p.level = 16
      Sim.Fire("PLAYER_LEVEL_UP", 16, 0, 0, 0, 0, 0, 0, 0, 0)
      Sim.Advance(1)
      Sim.LearnSpell(689); Sim.LearnSpell(1120); Sim.Advance(0.5)
      -- an old SND_Drenar created by 0.3.2 with a fixed icon
      CreateMacro("SND_Drenar", 136169, "#showtooltip /cast old", true)
      local MC = S().Modules.Macros
      local made = 0
      for _, e in ipairs(MC.List()) do
        if e.body then
          local fn = MC.Apply or MC.ApplyOne
          if e.gameIcon then made = made + 1 end
        end
      end
      Check(made > 0, "macro list exposes the game icon")
      if MC.CreateAll then MC.CreateAll() elseif MC.UpdateExisting then MC.UpdateExisting() end
      Sim.Advance(0.5)
      local m
      for _, x in ipairs(Sim.macros) do if x.name == "SND_Drenar" then m = x end end
      Check(m ~= nil and m.icon == 134400, "SND_Drenar uses the dynamic question-mark icon", m and tostring(m.icon))
      Check(m ~= nil and m.body:find("[mod:alt]", 1, true) ~= nil, "SND_Drenar body has the Alt condition", m and m.body)
    `,
  },
  {
    id: 'adv',
    title: 'Advisor: profession plan per class, no pet spells as trainer spells',
    char: 'gnome-warlock',
    lua: L_`
      Login()
      Sim.Advance(6)
      local p = Sim.player
      p.level = 16
      Sim.Fire("PLAYER_LEVEL_UP", 16, 0, 0, 0, 0, 0, 0, 0, 0)
      Sim.Advance(1)
      local A = S().Modules.Advisor
      local txt = {}
      for _, it in ipairs(A.Items()) do txt[#txt + 1] = Plain(it.text) end
      local all = table.concat(txt, " | ")
      Sim.Out("    " .. all)
      Check(not all:find("Herborister", 1, true) and not all:find("Alquimia", 1, true), "warlock is not told to learn Herbalism/Alchemy", all)
      Check(not all:find("Sacrificio", 1, true), "voidwalker Sacrifice is not a trainer spell", all)
      local P = S().Modules.Professions
      local keys = {}
      for _, k in ipairs(P.Routes().order) do keys[#keys + 1] = k end
      Check(table.concat(keys, ",") == "tailoring,enchanting", "warlock profession routes = tailoring, enchanting", table.concat(keys, ","))
    `,
  },
  {
    id: 'adv2',
    title: 'Advisor: druid plan is Herbalism + Alchemy',
    char: 'nightelf-druid',
    lua: L_`
      Login()
      Sim.Advance(6)
      local P = S().Modules.Professions
      local keys = {}
      for _, k in ipairs(P.Routes().order) do keys[#keys + 1] = k end
      table.sort(keys)
      Check(table.concat(keys, ",") == "alchemy,herbalism", "druid profession routes = herbalism, alchemy", table.concat(keys, ","))
    `,
  },
  {
    id: 'gate2',
    title: 'Trainer visits above your level are postponed (warlock 16 at "lo del 18")',
    char: 'gnome-warlock',
    lua: L_`
      Login()
      Sim.Advance(6)
      local E = S().Engine
      local p = Sim.player
      p.level = 16
      Sim.Fire("PLAYER_LEVEL_UP", 16, 0, 0, 0, 0, 0, 0, 0, 0)
      Sim.Advance(1)
      local i = StepIndexOf("a17wf-064")
      Check(i ~= nil, "step a17wf-064 exists")
      E:JumpTo(i)
      E:Advance()
      Sim.Advance(1)
      Check(StepId() ~= "a17wf-065", "the level-18 training step is not current at level 16", StepId())
      local g
      for _, x in ipairs(E:LevelGated()) do if x.entry.step.id == "a17wf-065" then g = x end end
      Check(g ~= nil and g.level == 18 and not g.ready, "training is remembered until level 18")
      local before = #Sim.chat
      p.level = 18
      Sim.Fire("PLAYER_LEVEL_UP", 18, 0, 0, 0, 0, 0, 0, 0, 0)
      Sim.Advance(1)
      local said = false
      for k = before + 1, #Sim.chat do if Sim.chat[k]:find("Ya puedes entrenar", 1, true) then said = true end end
      Check(said, "chat says you can train now")
      local btn = SendaHUD.gated
      Check(btn and btn:IsShown() and Plain(btn.text:GetText()):find("Ya puedes entrenar", 1, true) ~= nil, "HUD green line offers the training", btn and btn.text:GetText())
      if btn and btn.index then btn:GetScript("OnClick")(btn) end
      Sim.Advance(0.5)
      Check(StepId() == "a17wf-065", "clicking it goes to the training step", StepId())
      for _, id in ipairs(E:CurrentStep().spells or {}) do Sim.LearnSpell(id) end
      Sim.Advance(1)
      Check(StepId() ~= "a17wf-065", "learning the spells completes the step on its own", StepId())
    `,
  },
  {
    id: 'gate',
    title: 'Quests above your level are postponed and offered again on level-up',
    char: 'gnome-warlock',
    lua: L_`
      Login()
      Sim.Advance(6)
      local E = S().Engine
      local p = Sim.player
      p.level = 16
      Sim.Fire("PLAYER_LEVEL_UP", 16, 0, 0, 0, 0, 0, 0, 0, 0)
      Sim.Advance(1)
      local i = StepIndexOf("a19rr-016")
      Check(i ~= nil, "step a19rr-016 exists")
      E:JumpTo(i)
      E:Advance()
      Sim.Advance(1)
      Check(StepId() ~= "a19rr-017", "level-18 quest (a19rr-017) is not the current step at level 16", StepId())
      local gated = E:LevelGated()
      local g17
      for _, g in ipairs(gated) do if g.entry.step.id == "a19rr-017" then g17 = g end end
      Check(g17 ~= nil and g17.level == 18 and not g17.ready, "a19rr-017 is listed as postponed until 18")
      Check(SendaHUD.gated and SendaHUD.gated:IsShown(), "HUD shows the postponed line")
      Check(Plain(SendaHUD.gated.text:GetText()):find("Al nivel 1", 1, true) ~= nil, "HUD line says at which level (lowest postponed first)", SendaHUD.gated.text:GetText())
      Section("walk the rest of the section: never asked to complete/turn in quest 20")
      local bad
      for _ = 1, 80 do
        local st = E:CurrentStep()
        if not st or st.id:sub(1, 5) ~= "a19rr" then break end
        if st.quest == 20 and (st["do"] == "complete" or st["do"] == "turnin") then bad = st.id; break end
        E:Skip(); Sim.Advance(0.3)
      end
      Check(bad == nil, "complete/turnin of the untaken quest 20 are passed over", bad)
      Section("level up to 18")
      local before = #Sim.chat
      p.level = 18
      Sim.Fire("PLAYER_LEVEL_UP", 18, 0, 0, 0, 0, 0, 0, 0, 0)
      Sim.Advance(1)
      local said = false
      for k = before + 1, #Sim.chat do if Sim.chat[k]:find("Ya tienes nivel", 1, true) then said = true end end
      local readyNow = false
      for _, g in ipairs(E:LevelGated()) do if g.entry.step.id == "a19rr-017" and g.ready then readyNow = true end end
      if not readyNow then
        -- the cursor may have left the section window; check from a step inside the section
        E:JumpTo(StepIndexOf("a19rr-030") or i); Sim.Advance(0.5)
        for _, g in ipairs(E:LevelGated()) do if g.entry.step.id == "a19rr-017" and g.ready then readyNow = true end end
      end
      Check(readyNow, "a19rr-017 is now ready")
      Check(said or readyNow, "chat or HUD tells you it is available")
      local btn = SendaHUD.gated
      if btn.index then btn:GetScript("OnClick")(btn) end
      Sim.Advance(0.5)
      Check(StepId() == "a19rr-017", "clicking the green line goes back to a19rr-017", StepId())
    `,
  },
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
    id: 'j',
    title: 'Night elf druid: guide auto-selected, then the whole guide plays through',
    char: 'nightelf-druid',
    lua: L_`
      Login()
      local E = S().Engine
      Check(E:GuideId() == "nightelf-druid", "guide nightelf-druid auto-selected", E:GuideId())
      Check(StepId() == "nesg-001", "starts at the first Shadowglen step", StepId())
      RunAllTabs()
      local r = AutoPlay(3000)
      Sim.Out(string.format("    auto %d, manual %d, stuck %d", r.auto, r.manual, #r.stuck))
      Check(E:IsFinished(), "guide finished", StepId())
      Check(#r.stuck == 0, "no auto-detectable step got stuck", table.concat(r.stuck, ", "))
    `,
  },
  {
    id: 'ps',
    title: 'Polestar prototype (nightelf-druid-ps): never auto-selected, loads by hand and plays through',
    char: 'nightelf-druid',
    lua: L_`
      Login()
      local E, G = S().Engine, S().Guides
      Check(G:Get("nightelf-druid-ps") ~= nil, "prototype guide registered")
      Check(G:IsManualOnly(G:Get("nightelf-druid-ps")), "prototype is manual-only (order < 0)")
      Check(E:GuideId() == "nightelf-druid", "auto-selection keeps nightelf-druid", E:GuideId())
      local list = G:ForPlayer()
      -- Las guías solo a mano (prototipo y rutas importadas de Polestar) van detrás de todas las demás.
      local seenManual, order, hasProto = false, true, false
      for _, g in ipairs(list) do
        if G:IsManualOnly(g) then seenManual = true elseif seenManual then order = false end
        if g.id == "nightelf-druid-ps" then hasProto = true end
      end
      Check(hasProto, "prototype listed among the valid guides")
      Check(order and list[1].id == "nightelf-druid", "manual-only guides listed after the hand-written one", list[1] and list[1].id)
      Slash("guide nightelf-druid-ps")
      Check(E:GuideId() == "nightelf-druid-ps", "/senda guide nightelf-druid-ps selects it", E:GuideId())
      Check(StepId() == "ps-teld-001", "starts at the first imported step", StepId())
      RunAllTabs()
      local r = AutoPlay(1000)
      Sim.Out(string.format("    auto %d, manual %d, stuck %d", r.auto, r.manual, #r.stuck))
      if #r.stuck > 0 then Sim.Out("    stuck: " .. table.concat(r.stuck, ", ")) end
      Check(E:IsFinished(), "prototype guide finished", StepId())
      Check(#r.stuck == 0, "no auto-detectable step got stuck", table.concat(r.stuck, ", "))
    `,
  },
  {
    id: 's',
    title: 'Profession lessons (reqskill): skipped without the profession, offered once learned',
    char: 'nightelf-druid',
    lua: L_`
      Sim.CHARS["nightelf-druid"].level = 6
      Login()
      local E = S().Engine
      local function entry(id) for _, e in ipairs(E.steps) do if e.step.id == id then return e end end end
      local alch, cook = entry("netd-010"), entry("netd-012")
      Check(alch and alch.step.reqskill and alch.step.reqskill[1] == 171, "alchemy lesson carries reqskill 171")
      Check(entry("netd-016").index < alch.index, "learning Alchemy comes before the lesson")
      Check(E:NoSkill(alch) == true, "lesson skipped without Alchemy")
      Check(E:NoSkill(cook) == false, "cooking lesson needs no profession")
      table.insert(Sim.player.profs, { name = "Alquimia", skillLine = 171, rank = 1, max = 75 })
      Check(E:NoSkill(alch) == false, "lesson offered once Alchemy is learned")
      local elix = entry("netd-027") -- lleva if.prof = alchemy: puede no estar resuelto aún
      Check(elix == nil or E:NoSkill(elix) == true, "Syral's elixirs still wait for Alchemy 20")
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
    id: 'gear-reward',
    title: 'Gear: quest reward choice picks the build item (Affliction warlock), message and weights from weights.toml',
    char: 'gnome-warlock',
    lua: L_`
      Sim.CHARS["gnome-warlock"].level = 12
      Login()
      Sim.Advance(2)
      local G = S().Modules.Gear
      Check(G.BuildKey() == "affliction", "warlock build = affliction (default of warlock-weights)", G.BuildKey())
      local band = G.Band(12)
      Check(band and band.from == 1 and band.to == 29, "level 12 uses the 1-29 band", band and (band.from .. "-" .. band.to))
      local W = G.Weights(12)
      Check(W.SCHOOL == "SHADOW" and W.WAND_DPS == 2 and W.STA == 0.8, "weights come from the band (school from the build)",
        tostring(W.SCHOOL) .. " " .. tostring(W.WAND_DPS) .. " " .. tostring(W.STA))
      local function Pick(ids)
        local best = G.PickReward(function(k) return ids[k] and Sim.ItemLink(ids[k]) end, #ids)
        return best and Sim.ItemIdOf(best)
      end
      Check(Pick({ 90002, 90001, 90007 }) == 90001, "cloth Int/Spirit robe beats leather Agility/Stamina vests", Pick({ 90002, 90001, 90007 }))
      Section("the real reward window")
      Sim.questChoices = { 90002, 90001, 90007 }
      local before = #Sim.chat
      G.OnQuestRewards()
      Sim.Advance(0.2)
      local said = table.concat(Sim.chat, " | ", before + 1)
      Check(said:find("Túnica de aprendiz de sombras", 1, true) ~= nil and said:find("para tu build", 1, true) ~= nil,
        "chat recommends the robe for your build", said)
      Sim.questChoices = nil
    `,
  },
  {
    id: 'gear-usable',
    title: 'Gear: items the class cannot wear are never recommended (mage, druid)',
    char: 'human-mage',
    lua: L_`
      Sim.CHARS["human-mage"].level = 14
      Login()
      Sim.Advance(2)
      local G = S().Modules.Gear
      Check(G.BuildKey() == "frost", "mage build = frost", G.BuildKey())
      local function Pick(ids)
        local best = G.PickReward(function(k) return ids[k] and Sim.ItemLink(ids[k]) end, #ids)
        return best and Sim.ItemIdOf(best)
      end
      -- mail (huge stats), shield, two-handed axe and a small cloth glove
      local pick = Pick({ 90003, 90004, 90008, 90006 })
      Check(pick == 90006, "mage takes the cloth gloves, never mail, shield or axe", pick)
      for _, id in ipairs({ 90003, 90004, 90008 }) do
        local _, _, why = G.Delta(Sim.ItemLink(id))
        Check(why == "no", "Delta marks " .. Sim.ITEMS[id].name .. " as unusable", why)
        Check(not G.IsUpgrade(Sim.ItemLink(id)), Sim.ITEMS[id].name .. " is never an upgrade")
      end
      Check(Pick({ 90003, 90004, 90008 }) == nil, "only unusable choices: no recommendation (sell value instead)")
      Section("bags: an unusable item with big stats is never announced")
      Sim.player.bags[0][10] = { id = 90003, count = 1 }
      local before = #Sim.chat
      Sim.Fire("BAG_UPDATE_DELAYED")
      Sim.Advance(2)
      local said = table.concat(Sim.chat, " | ", before + 1)
      Check(not said:find("Coraza de malla", 1, true), "no «Ponte» for the mail chest", said)
      local ups = G.FindUpgrades()
      local listed = false
      for _, u in ipairs(ups) do if Sim.ItemIdOf(u.link) == 90003 then listed = true end end
      Check(not listed, "the gear list never offers the mail chest")
    `,
  },
  {
    id: 'gear-tip',
    title: 'Gear: tooltip line «+N% para tu build», bag scan «Ponte X: mejora» and the gear tab (best known piece)',
    char: 'gnome-warlock',
    lua: L_`
      Sim.CHARS["gnome-warlock"].level = 12
      Sim.CHARS["gnome-warlock"].equipped = { [4] = 6096, [5] = 3000 }
      Login()
      Sim.Advance(2)
      local function TipLine(id)
        GameTooltip:SetOwner(UIParent, "ANCHOR_NONE")
        GameTooltip:SetHyperlink(Sim.ItemLink(id))
        local found
        for _, l in ipairs(GameTooltip:Lines()) do if l:find("^Senda:") then found = (found and (found .. " / ") or "") .. Plain(l) end end
        GameTooltip:Hide()
        return found
      end
      -- equipped chest 3000: 3 Sta 1 Int = 0.8*3 + 0.75 = 3.15; robe 90001: 0.75*5 + 0.6*5 + 0.8*3 + 0.005*20 = 9.25
      local line = TipLine(90001)
      Check(line == "Senda: +194% para tu build", "one tooltip line with the percent for the build", line)
      local n = 0
      GameTooltip:SetOwner(UIParent, "ANCHOR_NONE"); GameTooltip:SetHyperlink(Sim.ItemLink(90001))
      for _, l in ipairs(GameTooltip:Lines()) do if l:find("^Senda:") then n = n + 1 end end
      Check(n == 1, "exactly one Senda line", n)
      Check((TipLine(90003) or ""):find("no te sirve", 1, true) ~= nil, "mail chest: «no te sirve»", TipLine(90003))
      Check((TipLine(90006) or ""):find("no llevas nada", 1, true) ~= nil, "empty hands slot: says so", TipLine(90006))
      Section("bag scan")
      Sim.player.bags[0][10] = { id = 90001, count = 1 }
      local before = #Sim.chat
      Sim.Fire("BAG_UPDATE_DELAYED")
      Sim.Advance(2)
      local said = table.concat(Sim.chat, " | ", before + 1)
      Check(said:find("Ponte", 1, true) ~= nil and said:find("194%", 1, true) ~= nil and said:find("para tu build", 1, true) ~= nil,
        "«Ponte X: mejora un 194% para tu build»", said)
      Section("gear tab")
      S().UI:ShowPanel(); S().UI:ShowTab("gear"); Sim.Advance(0.5)
      S().Modules.Gear.Refresh(); Sim.Advance(0.5)
      local texts = {}
      for _, f in ipairs(Sim.AllWidgets()) do
        if f.__type == "FontString" and f:IsVisible() then texts[#texts + 1] = Plain(f:GetText() or "") end
      end
      local all = table.concat(texts, " | ")
      Check(all:find("Mejor pieza conocida para tu tramo", 1, true) ~= nil, "tab shows the best known pieces for the band")
      Check(all:find("Tu build: Aflicción", 1, true) ~= nil and all:find("tramo 1-29", 1, true) ~= nil, "tab shows build and weight band")
      Check(all:find("+194%", 1, true) ~= nil, "upgrade list shows the percent", all:sub(1, 300))
      local bis = S().Modules.Gear.BisFor(12)
      Check(#bis >= 8, "bis-forever has pieces for 11-20 (affliction)", #bis)
      local ok = true
      for _, e in ipairs(bis) do
        local src = S().Modules.Gear.BisSource(e)
        if src == "?" or src == "" then ok = false end
      end
      Check(ok, "every piece has a readable source")
    `,
  },
  {
    id: 'gear-band',
    title: 'Gear: the level band switch changes the pick (warlock wand weight drops at 30)',
    char: 'gnome-warlock',
    lua: L_`
      Sim.CHARS["gnome-warlock"].level = 29
      Login()
      Sim.Advance(2)
      local G = S().Modules.Gear
      local function Pick(ids)
        local best = G.PickReward(function(k) return ids[k] and Sim.ItemLink(ids[k]) end, #ids)
        return best and Sim.ItemIdOf(best)
      end
      Check(Pick({ 90001, 5069 }) == 5069, "level 29: the wand (DPS weight 2) wins", Pick({ 90001, 5069 }))
      Sim.player.level = 30
      Sim.Fire("PLAYER_LEVEL_UP", 30, 0, 0, 0, 0, 0, 0, 0, 0)
      Sim.Advance(1)
      Check(G.Band(30).from == 30, "level 30 uses the 30-39 band", G.Band(30).from)
      Check(Pick({ 90001, 5069 }) == 90001, "level 30: the robe wins (wand weight 0.6)", Pick({ 90001, 5069 }))
      Sim.player.level = 40
      Sim.Fire("PLAYER_LEVEL_UP", 40, 0, 0, 0, 0, 0, 0, 0, 0)
      Sim.Advance(1)
      Check(G.Weights(40).SPI == 0.3, "level 40: blended band (Spirit 0.3)", G.Weights(40).SPI)
    `,
  },
  {
    id: 'gear-skill',
    title: 'Gear: a staff before learning Staves is not picked over something you can wear now',
    char: 'gnome-warlock',
    lua: L_`
      Sim.CHARS["gnome-warlock"].level = 12
      Login()
      Sim.Advance(2)
      Sim.player.spells[1180] = true -- Dagas
      Sim.player.spells[5009] = true -- Varitas
      Sim.Fire("SPELLS_CHANGED")
      Sim.Advance(0.5)
      local G = S().Modules.Gear
      local function Pick(ids)
        local best, _, _, why = G.PickReward(function(k) return ids[k] and Sim.ItemLink(ids[k]) end, #ids)
        return best and Sim.ItemIdOf(best), why
      end
      local _, _, why = G.Delta(Sim.ItemLink(90005))
      Check(why ~= nil and why:find("Bastones", 1, true) ~= nil, "staff says to learn Staves", why)
      Check(Pick({ 90005, 90006 }) == 90006, "the gloves you can wear now win over the staff", Pick({ 90005, 90006 }))
      local id, w = Pick({ 90005 })
      Check(id == 90005 and w ~= nil, "staff alone: offered, with the reason", tostring(id) .. " " .. tostring(w))
      Sim.LearnSpell(227) -- Bastones (Woo Ping)
      Sim.Advance(0.5)
      Check(Pick({ 90005, 90006 }) == 90005, "after learning Staves the staff wins", Pick({ 90005, 90006 }))
      Section("off hand while wielding a staff")
      Sim.player.equipped[16] = 90005
      local d, _, why2 = G.Delta(Sim.ItemLink(90009))
      Check(d < 0 and why2 ~= nil, "orb vs equipped staff: worse and says you'd drop the staff", tostring(d) .. " " .. tostring(why2))
    `,
  },
  {
    id: 'gear-druid',
    title: 'Gear: feral druid, cat for levelling and bear for elites (/senda equipo oso)',
    char: 'nightelf-druid',
    lua: L_`
      Sim.CHARS["nightelf-druid"].level = 14
      Login()
      Sim.Advance(2)
      local G = S().Modules.Gear
      local function Pick(ids)
        local best = G.PickReward(function(k) return ids[k] and Sim.ItemLink(ids[k]) end, #ids)
        return best and Sim.ItemIdOf(best)
      end
      Check(G.BuildKey() == "cat", "druid default build = cat", G.BuildKey())
      Check(Pick({ 90002, 90007, 90003, 90001 }) == 90002, "cat: Agility/Strength leather vest", Pick({ 90002, 90007, 90003, 90001 }))
      local lines = Slash("equipo oso")
      Check(G.BuildKey() == "bear", "/senda equipo oso switches to bear", G.BuildKey())
      Check(table.concat(lines, " "):find("oso", 1, true) ~= nil, "chat confirms the build", table.concat(lines, " "))
      Check(Pick({ 90002, 90007, 90003, 90001 }) == 90007, "bear: Stamina/armor leather vest", Pick({ 90002, 90007, 90003, 90001 }))
      Check(Pick({ 90003, 90008, 90004 }) == nil, "mail, axe and shield are never recommended to a druid")
      Slash("equipo felino")
      Check(G.BuildKey() == "cat", "/senda equipo felino back to cat", G.BuildKey())
      Section("gear tab switch button")
      S().UI:ShowPanel(); S().UI:ShowTab("gear"); Sim.Advance(0.5)
      local btn
      for _, f in ipairs(Sim.AllWidgets()) do
        if f.__type == "Button" and f:IsVisible() and (f:GetText() or ""):find("^Usar ") then btn = f end
      end
      Check(btn ~= nil, "tab shows the «Usar Feral, oso…» button")
      if btn then Sim.Click(btn); Sim.Advance(0.3) end
      Check(G.BuildKey() == "bear", "the button switches the build", G.BuildKey())
      Check(SendaDB.modules.gearBuild == "bear", "the choice is saved per character")
    `,
  },
  {
    id: 'gear-en',
    title: 'Gear: tooltip line in English',
    char: 'human-mage',
    locale: 'enUS',
    lua: L_`
      Sim.CHARS["human-mage"].level = 12
      Sim.CHARS["human-mage"].equipped = { [5] = 3000 }
      Login()
      Sim.Advance(2)
      GameTooltip:SetOwner(UIParent, "ANCHOR_NONE")
      GameTooltip:SetHyperlink(Sim.ItemLink(90001))
      local line
      for _, l in ipairs(GameTooltip:Lines()) do if l:find("^Senda:") then line = Plain(l) end end
      Check(line ~= nil and line:find("%% for your build$") ~= nil, "English tooltip line", line)
      GameTooltip:SetHyperlink(Sim.ItemLink(90004))
      line = nil
      for _, l in ipairs(GameTooltip:Lines()) do if l:find("^Senda:") then line = Plain(l) end end
      Check(line ~= nil and line:find("your class can't wear it", 1, true) ~= nil, "English unusable line", line)
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
  {
    id: 'auto',
    title: 'Quest automation: accepts/turns in only the guide quests, no reward choice, Shift and the option suppress it',
    char: 'nightelf-druid',
    lua: L_`
      Login()
      Sim.Advance(6)
      local E = S().Engine
      local function logHas(s) for _, l in ipairs(Sim.autoLog) do if l == s then return true end end return false end
      Check(StepId() == "nesg-001", "starts at the first accept (quest 456)", StepId())
      Section("accept")
      Sim.OpenQuest("detail", 9999); Sim.Advance(0.3)
      Check(not logHas("accept 9999"), "a quest the guide does not list is never accepted")
      Sim.OpenQuest("detail", 3519); Sim.Advance(0.3)
      Check(not logHas("accept 3519"), "a quest far ahead in the guide is not accepted")
      Sim.shift = true
      Sim.OpenQuest("detail", 456); Sim.Advance(0.3)
      Check(not logHas("accept 456"), "holding Shift suppresses the accept")
      Sim.shift = false
      S().Options:Set("autoQuests", false)
      Sim.OpenQuest("detail", 456); Sim.Advance(0.3)
      Check(not logHas("accept 456"), "the option off suppresses the accept")
      S().Options:Set("autoQuests", true)
      Sim.player.combat = true
      Sim.OpenQuest("detail", 456); Sim.Advance(0.3)
      Check(not logHas("accept 456"), "no accept in combat")
      Sim.player.combat = false
      Sim.OpenQuest("detail", 456); Sim.Advance(0.5)
      Check(logHas("accept 456"), "the current step's quest is accepted")
      Check(S().Compat.IsOnQuest(456), "quest 456 is in the log")
      Sim.OpenQuest("detail", 458); Sim.Advance(0.5)
      Check(logHas("accept 458"), "the next step's quest (upcoming few steps) is accepted too")
      Section("turn in")
      Sim.FinishQuestObjectives(456); Sim.Advance(1)
      Check(StepId() == "nesg-004", "after finishing, the turn-in of 456 is current", StepId())
      Sim.OpenQuest("progress", 458); Sim.Advance(0.3)
      Check(not logHas("complete 458"), "a quest the current step does not turn in is left alone")
      Sim.qwin = nil
      Sim.OpenQuest("progress", 456); Sim.Advance(0.5)
      Check(logHas("complete 456") and logHas("reward 456 0"), "the turn-in is completed with no choice")
      Check(S().Compat.IsQuestDone(456), "quest 456 is turned in")
      Section("reward choice")
      Sim.Advance(1)
      E:JumpTo(StepIndexOf("nesg-009"))
      Sim.FinishQuestObjectives(458); Sim.Advance(1)
      Check(StepId() == "nesg-009", "turn-in step of 458 is current", StepId())
      Sim.OpenQuest("progress", 458, { choices = { 6948, 2589 } }); Sim.Advance(0.3)
      Check(logHas("complete 458"), "progress window is completed")
      Check(not logHas("reward 458 0") and not logHas("reward 458 1") and not logHas("reward 458 2"),
        "with several choices the window stays open")
      Check(Sim.qwin ~= nil and Sim.qwin.kind == "complete", "the reward window is still open")
      CloseQuest()
      Sim.OpenQuest("progress", 458, { choices = { 2589 } }); Sim.Advance(0.3)
      Check(logHas("reward 458 1"), "a single choice is taken")
      Section("gossip and greeting")
      Sim.Advance(1)
      local want
      for _, e in ipairs(E:Steps()) do
        if e.step["do"] == "accept" and E:WantsQuest("accept", e.step.quest) then want = e.step.quest; break end
      end
      Check(want ~= nil, "there is a next accept in the route", tostring(want))
      Sim.OpenNpc("gossip", {}, { 9999, want }); Sim.Advance(0.3)
      Check(logHas("select-available " .. want), "gossip: the guide's quest is picked from the list", tostring(want))
      Check(not logHas("select-available 9999"), "gossip: the other quest is not picked")
      Sim.Advance(1)
      want = nil
      for _, e in ipairs(E:Steps()) do
        if e.step["do"] == "accept" and E:WantsQuest("accept", e.step.quest) then want = e.step.quest; break end
      end
      Sim.qwin = nil
      Sim.OpenNpc("greeting", {}, { 9999, want }); Sim.Advance(0.3)
      Check(logHas("select-available " .. want) or (Sim.qwin and Sim.qwin.id == want), "greeting: opens the guide's quest", tostring(want))
      Check(not logHas("select-available 9999"), "greeting: the other quest is not picked")
    `,
  },
  {
    id: 'timed',
    title: 'Timed quests: countdown on the HUD, chat warnings at 5 and 1 minute, failure notice',
    char: 'nightelf-druid',
    lua: L_`
      Login()
      Sim.Advance(6)
      local E = S().Engine
      Sim.AcceptQuest(456, { { "Bichos", 3 } }, { timeLimit = 400 })
      Sim.Advance(1.5)
      E:JumpTo(StepIndexOf("nesg-003")); Sim.Advance(1.5)
      local txt = Plain(SendaHUD.status:GetText())
      Check(txt:find("6:3", 1, true) ~= nil or txt:find("6:4", 1, true) ~= nil, "HUD shows the countdown (about 6:3x)", txt)
      Check(SendaHUD.status:IsShown(), "the countdown line is visible")
      local function said(from, needle)
        for k = from + 1, #Sim.chat do if Sim.chat[k]:find(needle, 1, true) then return true end end
        return false
      end
      local before = #Sim.chat
      Sim.Advance(110)
      Check(said(before, "te quedan 5:00") or said(before, "te quedan 4:59") or said(before, "te quedan 4:5"), "chat warns at 5 minutes", Sim.chat[#Sim.chat])
      before = #Sim.chat
      Sim.Advance(240)
      Check(said(before, "te quedan 1:00") or said(before, "te quedan 0:59") or said(before, "te quedan 0:5"), "chat warns at 1 minute", Sim.chat[#Sim.chat])
      before = #Sim.chat
      Sim.Advance(60)
      Sim.FailQuest(456)
      Sim.Advance(2)
      Check(said(before, "se acabó el tiempo"), "chat says the time ran out")
      txt = Plain(SendaHUD.status:GetText())
      Check(txt:find("Fallida", 1, true) ~= nil, "HUD says the quest failed", txt)
      Check(SendaHUD.retake:IsShown() and SendaHUD.skipq:IsShown(), "HUD offers retake / skip buttons")
      local t = ArrowTarget()
      Check(t and math.abs(t.x * 100 - 58.69) < 0.01 and math.abs(t.y * 100 - 44.27) < 0.01, "arrow points back to the quest giver (accept step)")
      Check(t and Plain(t.label):find("coger de nuevo", 1, true) ~= nil, "arrow label says take it again", t and t.label)
    `,
  },
  {
    id: 'lost',
    title: 'Failed / abandoned quests: retake goes back to the accept step, skip drops the rest of the quest',
    char: 'nightelf-druid',
    lua: L_`
      Login()
      Sim.Advance(6)
      local E = S().Engine
      Sim.AcceptQuest(456, { { "Bichos", 3 } })
      Sim.AcceptQuest(458, { { "Cosas", 1 } })
      Sim.Advance(1.5)
      Check(StepId() == "nesg-003", "current step is 'complete 456'", StepId())
      Section("abandoned then skip")
      Sim.AbandonQuest(456); Sim.Advance(1.5)
      Check(StepId() == "nesg-003", "the step is not silently skipped when you abandon the quest", StepId())
      Check(E:IsAbandoned(456), "the engine remembers the abandonment")
      Check(Plain(SendaHUD.status:GetText()):find("abandonaste", 1, true) ~= nil, "HUD says you abandoned it", SendaHUD.status:GetText())
      Check(SendaHUD.retake:IsShown(), "retake button visible")
      local t = ArrowTarget()
      Check(t and math.abs(t.x * 100 - 58.69) < 0.01, "arrow points to the quest giver")
      Sim.Click(SendaHUD.skipq); Sim.Advance(1)
      local p = S():GuideProgress("nightelf-druid")
      Check(p.done["nesg-003"] == "s" and p.done["nesg-004"] == "s", "skip marks the rest of the quest as skipped")
      Check(not E:IsAbandoned(456), "the abandonment is cleared")
      Check(StepId() ~= "nesg-003" and StepId() ~= "nesg-004", "the route moved on", StepId())
      Section("failed, abandon, retake")
      local p2 = S():GuideProgress("nightelf-druid")
      p2.done["nesg-003"] = nil; p2.done["nesg-004"] = nil
      Sim.AcceptQuest(456, { { "Bichos", 3 } }); Sim.Advance(1)
      E:JumpTo(StepIndexOf("nesg-003")); Sim.Advance(0.5)
      Sim.FailQuest(456); Sim.Advance(1.5)
      Check(E:Problem() and E:Problem().kind == "failed", "failed quest is detected")
      Sim.AbandonQuest(456); Sim.Advance(1.5)
      Check(E:Problem() and E:Problem().kind == "abandoned", "abandoning the failed quest leaves it 'abandoned'")
      Sim.Click(SendaHUD.retake); Sim.Advance(0.5)
      Check(StepId() == "nesg-001", "retake goes back to the accept step", StepId())
      Sim.OpenQuest("detail", 456); Sim.Advance(1)
      Check(S().Compat.IsOnQuest(456), "taking the quest again (automation)")
      Check(not E:IsAbandoned(456), "the flag is cleared")
      Check(StepId() == "nesg-003", "the route continues at the complete step", StepId())
    `,
  },
  {
    id: 'escort',
    title: 'Escort steps show the escort note; guides mark their escort quests',
    char: 'nightelf-druid',
    lua: L_`
      Login()
      Sim.Advance(6)
      local E = S().Engine
      Sim.player.level = 12
      Sim.Fire("PLAYER_LEVEL_UP", 12, 0, 0, 0, 0, 0, 0, 0, 0)
      Sim.Advance(1)
      local i = StepIndexOf("netd-065")
      Check(i ~= nil, "escort accept step exists")
      Check(E:Entry(i).step.escort == true, "step netd-065 carries escort = true")
      E:JumpTo(i); Sim.Advance(1)
      Check(StepId() == "netd-065", "on the escort step", StepId())
      Check(SendaHUD.escort:IsShown() and Plain(SendaHUD.escort:GetText()):find("Escolta:", 1, true) ~= nil, "HUD shows the escort note", SendaHUD.escort:GetText())
      E:JumpTo(StepIndexOf("nesg-001")); Sim.Advance(1)
      Check(not SendaHUD.escort:IsShown(), "no escort note on ordinary steps")
      local n = 0
      for _, e in ipairs(E:Steps()) do if e.step.escort then n = n + 1 end end
      Check(n >= 4, "the druid guide marks its escort steps: " .. n)
    `,
  },
  {
    id: 'hide',
    title: 'Hide in instances, hide-all (minimap click and /senda hide), minimap menu',
    char: 'nightelf-druid',
    lua: L_`
      Login()
      Sim.Advance(6)
      Check(SendaHUD:IsShown() and SendaArrow:IsShown(), "HUD and arrow shown outside instances")
      Section("instances")
      for _, kind in ipairs({ "party", "raid", "pvp", "arena" }) do
        Sim.SetInstance(kind); Sim.Advance(0.5)
        Check(not SendaHUD:IsShown() and not SendaArrow:IsShown(), "hidden in " .. kind)
        Sim.SetInstance(nil); Sim.Advance(0.5)
        Check(SendaHUD:IsShown() and SendaArrow:IsShown(), "back after leaving " .. kind)
      end
      S().Options:Set("hideInInstance", false)
      Sim.SetInstance("party"); Sim.Advance(0.5)
      Check(SendaHUD:IsShown(), "the option off keeps the HUD in dungeons")
      Sim.SetInstance(nil)
      S().Options:Set("hideInInstance", true)
      Section("hide all")
      Slash("hide")
      Check(not SendaHUD:IsShown() and not SendaArrow:IsShown(), "/senda hide hides HUD and arrow")
      Check(S().db.hideAll == true, "the state is saved")
      Slash("hide")
      Check(SendaHUD:IsShown() and SendaArrow:IsShown(), "/senda hide again shows them")
      Sim.ctrl = true
      SendaMinimapButton:Click("LeftButton", false); Sim.Advance(0.3)
      Check(not SendaHUD:IsShown() and not SendaArrow:IsShown(), "minimap ctrl+click hides everything")
      SendaMinimapButton:Click("LeftButton", false); Sim.Advance(0.3)
      Check(SendaHUD:IsShown() and SendaArrow:IsShown(), "minimap ctrl+click again shows everything")
      Sim.ctrl = false
      Section("minimap menu")
      SendaMinimapButton:Click("RightButton", false); Sim.Advance(0.3)
      Check(SendaDropdownList and SendaDropdownList:IsShown(), "right-click opens the menu")
      local rows = 0
      for _, r in ipairs(SendaDropdownList.rows) do if r:IsShown() then rows = rows + 1 end end
      Check(rows == 4, "menu has panel / HUD / arrow / hide-all", rows)
      Sim.Click(SendaDropdownList.rows[2]); Sim.Advance(0.3)
      Check(not SendaHUD:IsShown(), "menu entry toggles the HUD")
      S().HUD:Toggle(); Sim.Advance(0.3)
      Check(SendaHUD:IsShown(), "HUD back on")
    `,
  },
  {
    id: 'lcard',
    title: 'Level-up card: new class spells, cost, where; quiet in combat/instances',
    char: 'gnome-warlock',
    lua: L_`
      Login()
      Sim.player.spells[348] = true -- level-1 Immolate: nothing pending below level 4
      Sim.Advance(6)
      local E, SC = S().Engine, S().Modules.SpellCards
      local p = Sim.player
      local function shown() return SendaLevelCard and SendaLevelCard:IsShown() end
      Section("a level with nothing new says nothing")
      p.level = 2
      Sim.Fire("PLAYER_LEVEL_UP", 2, 0, 0, 0, 0, 0, 0, 0, 0)
      Sim.Advance(3)
      Check(not shown(), "no card at level 2")

      Section("level 6")
      p.level = 6
      Sim.Fire("PLAYER_LEVEL_UP", 6, 0, 0, 0, 0, 0, 0, 0, 0)
      Sim.Advance(3)
      Check(shown(), "card shown at level 6")
      local head = Plain(SendaLevelCard.head:GetText())
      Check(head:find("Nivel 6", 1, true) and head:find("3 hechizos", 1, true), "head says level and count", head)
      local n = 0
      for _, b in ipairs(SendaLevelCard.icons) do if b:IsShown() then n = n + 1 end end
      Check(n == 3, "one icon per spell", n)
      Check(SendaLevelCard.icons[1].spell == 172, "icons are in level order", SendaLevelCard.icons[1].spell)
      local errs = #Sim.errors
      for _, b in ipairs(SendaLevelCard.icons) do Sim.RunScript(b, "OnEnter"); Sim.RunScript(b, "OnLeave") end
      Check(#Sim.errors == errs, "icon tooltips run without errors")
      -- the trainer data (data/knowledge/trainer) gives the prices: 5 s in total for 1454 and 695 at level 6
      Check(Plain(SendaLevelCard.cost:GetText()):find("Coste: 0g 5s 0c", 1, true) ~= nil, "compiled prices are said", SendaLevelCard.cost:GetText())
      local w = SC.Where(SC.LevelList())
      Check(w and w.kind == "trainer" and w.at and w.at[1] == 1426, "falls back to the guide's trainer on this map", w and w.kind)
      Check(SendaLevelCard.point:IsShown(), "point button offered")
      Sim.Click(SendaLevelCard.point); Sim.Advance(0.3)
      local t, src = ArrowTarget()
      Check(src == "trainer" and t and t.map == 1426, "the arrow points to the trainer", src)

      Section("auto-hide")
      Sim.Advance(46)
      Check(not shown(), "the card goes away by itself")

      Section("trainer visit caches the cost")
      CreateFrame("Frame", "ClassTrainerFrame", UIParent)
      Sim.trainer = { { spell = 172, cost = 100 }, { spell = 695, cost = 100 }, { spell = 1454, cost = 500 } }
      Sim.Fire("TRAINER_SHOW"); Sim.Advance(1)
      ClassTrainerFrame:Hide(); Sim.Fire("TRAINER_CLOSED"); Sim.Advance(0.5)
      Check(S().Modules.Trainer.CachedCost(172) == 100, "cost cached from the trainer", S().Modules.Trainer.CachedCost(172))
      local total, unknown = SC.Cost(SC.LevelList())
      Check(total > 0 and unknown == 0, "total known (knowledge costs, cache as fallback)", total .. "/" .. unknown)

      Section("combat and instances")
      p.combat = true
      Sim.Fire("PLAYER_LEVEL_UP", 6, 0, 0, 0, 0, 0, 0, 0, 0)
      Sim.Advance(3)
      Check(not shown(), "never in combat")
      p.combat = false
      p.money = 200
      Sim.Fire("PLAYER_REGEN_ENABLED")
      Sim.Advance(3)
      Check(shown(), "shown when combat ends")
      Check(Plain(SendaLevelCard.cost:GetText()):find("te faltan", 1, true) ~= nil, "money (200) does not cover the total", SendaLevelCard.cost:GetText())
      SC.Dismiss("level")
      Check(not shown(), "close button hides it")
      Sim.SetInstance("party"); Sim.Advance(0.5)
      Sim.Fire("PLAYER_LEVEL_UP", 6, 0, 0, 0, 0, 0, 0, 0, 0)
      Sim.Advance(3)
      Check(not shown(), "never in an instance")
      Sim.SetInstance(nil); Sim.Advance(3)
      Check(shown(), "shown after leaving the instance")
      p.money = 100000; Sim.Fire("SPELLS_CHANGED"); Sim.Advance(1.5)
      Check(Plain(SendaLevelCard.cost:GetText()):find("te llega", 1, true) ~= nil, "enough money is said", SendaLevelCard.cost:GetText())

      Section("learning everything removes the card")
      for _, s in ipairs(SC.LevelList()) do Sim.LearnSpell(s.id) end
      Sim.Advance(2)
      Check(not shown(), "nothing left to train: card gone")
    `,
  },
  {
    id: 'lcard2',
    title: 'Level-up card: guide step nearby, green line not duplicated, login with pending spells',
    char: 'gnome-warlock',
    lua: L_`
      Login()
      Sim.player.spells[348] = true -- level-1 Immolate: nothing pending below level 4
      local E, SC = S().Engine, S().Modules.SpellCards
      local p = Sim.player
      p.level = 6
      local function shown() return SendaLevelCard and SendaLevelCard:IsShown() end
      Sim.Advance(14)
      Check(shown(), "pending spells at login show the card once")
      SC.Dismiss("level")
      Section("a guide train step a few steps ahead")
      local i = StepIndexOf("dun-morogh-006")
      Check(i ~= nil, "step dun-morogh-006 exists")
      E:JumpTo(i - 2); Sim.Advance(1)
      local w = SC.Where(SC.LevelList())
      Check(w and w.kind == "guide" and w.steps >= 1 and w.steps <= 3, "the guide's train step is near", w and (w.kind .. "/" .. tostring(w.steps)))
      E:JumpTo(i); Sim.Advance(1)
      w = SC.Where(SC.LevelList())
      Check(w and w.kind == "current", "on the train step itself", w and w.kind)
      Section("the green line owns the message")
      p.level = 16
      Sim.Fire("PLAYER_LEVEL_UP", 16, 0, 0, 0, 0, 0, 0, 0, 0)
      Sim.Advance(1)
      local j = StepIndexOf("a17wf-064")
      E:JumpTo(j); E:Advance(); Sim.Advance(1)
      local before = #Sim.chat
      p.level = 18
      Sim.Fire("PLAYER_LEVEL_UP", 18, 0, 0, 0, 0, 0, 0, 0, 0)
      Sim.Advance(3)
      local said = 0
      for k = before + 1, #Sim.chat do if Sim.chat[k]:find("Ya puedes entrenar", 1, true) then said = said + 1 end end
      Check(said == 1, "the engine says it once", said)
      Check(SendaHUD.gated:IsShown(), "green line in the HUD")
      Check(shown(), "the card lists the spells")
      Check(SC.Where(SC.LevelList()).kind == "gate", "where: left to the green line")
      Check(not SendaLevelCard.route:IsShown() and not SendaLevelCard.point:IsShown(), "no second route or button")
    `,
  },
  {
    id: 'lcard-en',
    title: 'Level-up and rank cards in English',
    char: 'gnome-warlock',
    locale: 'enUS',
    lua: L_`
      Login()
      Sim.player.spells[348] = true -- level-1 Immolate: nothing pending below level 4
      Sim.Advance(6)
      local p = Sim.player
      p.level = 6
      Sim.Fire("PLAYER_LEVEL_UP", 6, 0, 0, 0, 0, 0, 0, 0, 0)
      Sim.Advance(3)
      Check(SendaLevelCard and SendaLevelCard:IsShown(), "card shown")
      local head = Plain(SendaLevelCard.head:GetText())
      Check(head:find("Level 6: you can train 3 spells", 1, true) ~= nil, "English head", head)
      Check(Plain(SendaLevelCard.cost:GetText()):find("Cost: 0g 5s 0c", 1, true) ~= nil, "English cost line", SendaLevelCard.cost:GetText())
      Sim.actions[1] = { "spell", 116 }
      Sim.LearnSpell(116); Sim.LearnSpell(837); Sim.Advance(14)
      Check(SendaRankCard and SendaRankCard:IsShown(), "rank card shown")
      Check(Plain(SendaRankCard.rows[1].text:GetText()):find("rank 1 to 3", 1, true) ~= nil, "English rank line", SendaRankCard.rows[1].text:GetText())
      Check(Plain(SendaRankCard.upgrade:GetText()) == "Upgrade", "English button")
    `,
  },
  {
    id: 'rankcard',
    title: 'Action-bar rank upgrade: card, upgrade out of combat only, never macros/items, keep a rank',
    char: 'human-mage',
    lua: L_`
      Login()
      Sim.Advance(14)
      local SC = S().Modules.SpellCards
      local p = Sim.player
      local function shown() return SendaRankCard and SendaRankCard:IsShown() end
      Check(not shown(), "nothing to renew at the start")
      CreateMacro("SND_Prueba", 136243, "/cast Bola de Fuego", true)
      Sim.actions[1] = { "spell", 116 }
      Sim.actions[2] = { "macro", GetMacroIndexByName("SND_Prueba") }
      Sim.actions[3] = { "item", 6948 }
      Sim.actions[4] = { "spell", 205 }
      Sim.actions[5] = { "spell", 133 }       -- no rank: never listed
      Sim.actions[7] = { "spell", 116 }
      Sim.LearnSpell(116); Sim.LearnSpell(205)
      Sim.Advance(3)
      Check(shown(), "the card shows rank 1 as old (rank 2 is the best)")
      local list, slots = SC.OldRanks()
      Check(#list == 1 and list[1].id == 116 and list[1].bestId == 205 and slots == 2, "only rank 1 is old (2 slots)", #list .. "/" .. slots)
      Sim.LearnSpell(837)
      Sim.Advance(3)
      list, slots = SC.OldRanks()
      Check(#list == 2 and slots == 3, "after learning rank 3: two old spells, 3 slots", #list .. "/" .. slots)
      Check(Plain(SendaRankCard.rows[1].text:GetText()):find("rango 1 a 3", 1, true) ~= nil, "line says rank 1 to 3", SendaRankCard.rows[1].text:GetText())
      Check(Plain(SendaRankCard.rows[2].text:GetText()):find("rango 2 a 3", 1, true) ~= nil, "line says rank 2 to 3", SendaRankCard.rows[2].text:GetText())
      local errs = #Sim.errors
      Sim.RunScript(SendaRankCard.rows[1], "OnEnter"); Sim.RunScript(SendaRankCard.rows[1], "OnLeave")
      Check(#Sim.errors == errs, "row tooltip runs")

      Section("combat: nothing happens until it ends")
      p.combat = true
      Sim.Click(SendaRankCard.upgrade); Sim.Advance(0.5)
      Check(Sim.actions[1][2] == 116 and Sim.actions[4][2] == 205, "bars untouched in combat")
      p.combat = false
      Sim.Fire("PLAYER_REGEN_ENABLED"); Sim.Advance(2)
      Check(Sim.actions[1][2] == 837 and Sim.actions[7][2] == 837 and Sim.actions[4][2] == 837, "upgraded after combat")
      Check(Sim.actions[2][1] == "macro" and Sim.actions[3][1] == "item" and Sim.actions[5][2] == 133, "macro, item and unranked spell untouched")
      Check(not shown(), "the card goes away")

      Section("busy cursor")
      Sim.actions[1] = { "spell", 116 }
      SC.Check(true); Sim.Advance(0.5)
      Check(shown(), "card back for a new old rank")
      Sim.cursor = { "item", 6948 }
      Sim.Click(SendaRankCard.upgrade); Sim.Advance(0.5)
      Check(Sim.actions[1][2] == 116, "nothing placed with something on the cursor")
      Sim.cursor = nil

      Section("keep this rank")
      Sim.Click(SendaRankCard.rows[1], "RightButton"); Sim.Advance(0.5)
      Check(S().db.modules.cards.keptRanks[116] == true, "the choice is saved")
      Check(not shown(), "kept spell is not listed any more")
      Sim.Fire("SPELLS_CHANGED"); Sim.Advance(3)
      Check(not shown() and Sim.actions[1][2] == 116, "it does not come back; the kept rank stays on the bar")
      Section("slash")
      local lines = Slash("renovar")
      local said = false
      for _, l in ipairs(lines) do if l:find("ya tienen el rango", 1, true) then said = true end end
      Check(said, "/senda renovar says the bars are fine", table.concat(lines, "|"))
    `,
  },
  {
    id: 'names',
    title: 'Name tokens: cached and uncached quest, NPC tooltip, fallback table, secret values, one batched redraw',
    char: 'gnome-warlock',
    lua: L_`
      -- the NPC 467 tooltip comes back as a secret value (combat): it must count as "no answer"
      local realSecret = issecretvalue
      issecretvalue = function(v) return v == "El Defias Traidor" end
      Login()
      local N, G, E, HUD = S().Names, S().Guides, S().Engine, S().HUD
      Check(N ~= nil and N.Resolve ~= nil, "Senda.Names is loaded")
      Section("compiled fallback (Locale/Names_esES.lua, Names_enUS.lua as last resort)")
      local n, src = N:Get("quest", 456)
      Check(n == "El equilibrio de la naturaleza" and src == "pack", "uncached quest 456 shows the esES fallback", tostring(n) .. " / " .. tostring(src))
      n, src = N:Get("npc", 3595)
      Check(n == "Shanda" and src == "pack", "NPC without an esES name falls back to the English one", tostring(n) .. " / " .. tostring(src))
      N:AddFallback("esES", "obj", "999999\tCofre de pruebas")
      N:AddFallback("frFR", "obj", "999998\tCoffre")
      Check(N:Get("obj", 999999) == "Cofre de pruebas", "game object token uses the fallback table")
      Check(N:Get("obj", 999998) == nil, "a fallback of another client language is ignored")

      Section("a step with tokens: synchronous answer first, never blocks")
      Sim.questCache[179] = true -- quest 179 is in the client cache, 783 is not
      G:RegisterSection({ id = "sim-names", title = "Fichas", levels = { 1, 2 }, map = 1426, steps = {
        { id = "sim-names-001", ["do"] = "note",
          text = "Coge «{quest:179}» y «{quest:783}» de {npc:658}; usa {item:6948} y {spell:686} en {map:1426} junto a {obj:999999}. {foo:3}",
          tip = "Pregunta a {npc:3595} y a {npc:467}.", status = "unverified" } } })
      G:RegisterGuide({ id = "sim-names", title = "Fichas", sections = { "sim-names" }, order = -1 })
      local updates = 0
      S().Events:On("SENDA_NAMES_UPDATED", function() updates = updates + 1 end)
      E:SetGuide("sim-names")
      local step = E:CurrentStep()
      Check(step and step.id == "sim-names-001", "token step is current", step and step.id)
      local t = Plain(HUD:StepText(step))
      Check(t:find("«Avituallamiento enano»", 1, true) ~= nil, "cached quest resolves at once", t)
      Check(t:find("«Misión #783»", 1, true) ~= nil, "uncached quest shows a placeholder meanwhile", t)
      Check(t:find("PNJ #658", 1, true) ~= nil, "uncached creature shows a placeholder meanwhile", t)
      Check(t:find("Piedra de hogar", 1, true) ~= nil, "item in the bags resolves at once", t)
      Check(t:find("Descarga de las Sombras", 1, true) ~= nil, "spell resolves (C_Spell.GetSpellName)", t)
      Check(t:find("en Dun Morogh", 1, true) ~= nil, "map resolves (C_Map.GetMapInfo)", t)
      Check(t:find("junto a Cofre de pruebas", 1, true) ~= nil, "game object resolves from the fallback", t)
      Check(t:find("{foo:3}", 1, true) ~= nil, "unknown token kinds are left alone", t)

      Section("QUEST_DATA_LOAD_RESULT and the creature tooltip arrive: one batched redraw")
      Sim.Advance(2)
      local hud = Plain(HudText())
      Check(hud:find("«Una amenaza interior»", 1, true) ~= nil, "HUD shows the quest title after QUEST_DATA_LOAD_RESULT", hud)
      Check(hud:find("de Sten Brazorrecio", 1, true) ~= nil, "HUD shows the NPC name read from the tooltip's first line", hud)
      Check(not hud:find("#", 1, true), "no placeholder left in the HUD", hud)
      Check(updates >= 1 and updates <= 2, "names arriving together fire one batched SENDA_NAMES_UPDATED", updates)
      local tip = Plain(SendaHUD.tip:GetText() or "")
      Check(tip:find("Pregunta a Shanda", 1, true) ~= nil, "tip tokens resolve too", tip)
      Check(tip:find("PNJ #467", 1, true) ~= nil, "a secret tooltip name is never shown or cached", tip)
      Check(N:Cached("npc", 467) == nil and N:Cached("npc", 658) == "Sten Brazorrecio", "session cache holds client answers only")
      n, src = N:Get("quest", 456)
      Check(src == "client" and n == "Misión 456", "the client's name replaces the fallback once it arrives", tostring(n) .. " / " .. tostring(src))

      Section("Request: asynchronous callback, item through Item:ContinueOnItemLoad")
      local got
      N:Request("item", 2589, function(name) got = name end)
      Check(type(got) == "string" and got ~= "", "item in bags answers at once", got)
      local got2
      Sim.itemCache[12345] = nil
      N:Request("item", 12345, function(name) got2 = name or false end)
      Check(got2 == nil, "uncached item answers later, not at once")
      Sim.Advance(1)
      Check(type(got2) == "string" and got2 ~= "", "Item:ContinueOnItemLoad delivers the name", got2)
      local got3
      N:Request("obj", 5, function(name) got3 = name or false end)
      Check(got3 == false, "game objects cannot be asked to the client (nil at once)")

      Section("other views resolve tokens")
      RunAllTabs()
      HoverAll()
      local target = ArrowTarget()
      Check(true, "arrow, guide list and tooltips ran with tokens")
      issecretvalue = realSecret
    `,
  },
  {
    id: 'volcar',
    title: '/senda volcar: every id of the compiled guides into SendaNamesDB, throttled, paused in combat, resumable',
    char: 'nightelf-druid',
    lua: L_`
      Login()
      local D = S().Names.Dump
      Check(D ~= nil, "dump module loaded")
      local lines = Slash("volcar")
      Check(D:Running(), "/senda volcar starts the dump")
      local said = false
      for _, l in ipairs(lines) do if l:find("Volcando los nombres del juego", 1, true) then said = true end end
      local frames = 0
      while select(2, D:Progress()) == 0 and frames < 2000 do Sim.Advance(0.05); frames = frames + 1 end
      Sim.Out("    collected in " .. frames .. " frames")
      local done1, total = D:Progress()
      Check(total and total > 200, "ids collected from guides and knowledge", total)
      Check(said or done1 ~= nil, "start line in chat", table.concat(lines, " | "))

      Section("throttled: at most 20 new requests per frame and 40 waiting")
      local maxStep, maxWait, last = 0, 0, D:Started()
      for _ = 1, 40 do
        Sim.Advance(0.05)
        local now = D:Started()
        maxStep = math.max(maxStep, now - last)
        maxWait = math.max(maxWait, D:InFlight())
        last = now
      end
      Check(maxStep > 0 and maxStep <= 20, "requests per frame-slice <= 20", maxStep)
      Check(maxWait <= 40, "requests waiting for an answer <= 40", maxWait)

      Section("paused in combat")
      Sim.player.combat = true
      Sim.Advance(0.2)
      local p1 = D:Progress()
      Sim.Advance(2)
      local p2 = D:Progress()
      Check(p2 - p1 <= 40, "no new requests during combat (only answers already in flight)", p1 .. " -> " .. p2)
      local paused = false
      for _, l in ipairs(Sim.chat) do if l:find("en pausa", 1, true) then paused = true end end
      Check(paused, "chat says the dump is paused")
      Sim.player.combat = false

      Section("stop and resume")
      Sim.Advance(1)
      Slash("volcar parar")
      Check(not D:Running(), "/senda volcar parar stops it")
      local d = SendaNamesDB.locales.esES
      local saved = 0
      for _ in pairs(d.quest) do saved = saved + 1 end
      Check(saved > 0, "names saved so far are kept", saved)
      Slash("volcar")
      Check(D:Running(), "/senda volcar resumes")
      for _ = 1, 400 do if select(2, D:Progress()) > 0 then break end Sim.Advance(0.05) end
      local doneR, totalR = D:Progress()
      Check(doneR >= saved and totalR == total, "resume skips what is already saved", doneR .. "/" .. totalR)

      local t0 = Sim.time
      for _ = 1, 600 do
        Sim.Advance(1)
        if not D:Running() then break end
      end
      Check(not D:Running(), "dump finished", string.format("%.0f s simulated", Sim.time - t0))
      local done, tot, ok, miss = D:Progress()
      Check(done == tot, "every id answered", done .. "/" .. tot)
      Sim.Out(string.format("    %d ids, %d new names, %d without answer, %.0f s simulated", tot, ok, miss, Sim.time - t0))
      Check(d.build == "1.60.1.70291", "build recorded", d.build)
      Check(type(d.date) == "string" and d.date:match("^%d%d%d%d%-%d%d%-%d%d$") ~= nil, "date recorded", d.date)
      Check(d.done == true, "marked done")
      Check(d.quest[456] ~= nil, "quest of the guide saved", d.quest[456])
      Check(d.npc[2079] == "Conservador Ilthalaine", "NPC name from the creature tooltip", d.npc[2079])
      Check(d.map[1438] == "Teldrassil", "map name", d.map[1438])
      local nItem, nSpell = 0, 0
      for _ in pairs(d.item) do nItem = nItem + 1 end
      for _ in pairs(d.spell) do nSpell = nSpell + 1 end
      Check(nItem > 0 and nSpell > 0, "items and spells (knowledge) saved", nItem .. " items, " .. nSpell .. " spells")
      local fin = false
      for _, l in ipairs(Sim.chat) do if l:find("Volcado terminado", 1, true) then fin = true end end
      Check(fin, "chat says it finished")
      local mark = #Sim.chat
      Slash("volcar")
      for _ = 1, 400 do if not D:Running() then break end Sim.Advance(0.05) end
      local nothing = false
      for i = mark + 1, #Sim.chat do if Sim.chat[i]:find("Ya tienes los", 1, true) then nothing = true end end
      Check(nothing and not D:Running(), "a second run has nothing left to ask", Sim.chat[#Sim.chat])
      local sv = Sim.SaveVariables()
      Check(sv:find("SendaNamesDB = {", 1, true) ~= nil, "SendaNamesDB is a saved variable")
      Check(sv:find('"Conservador Ilthalaine"', 1, true) ~= nil, "names reach the SavedVariables file")
      Section("the dump is used as fallback")
      Check(S().Names:Get("npc", 2079) == "Conservador Ilthalaine", "dumped name available")
    `,
  },
  {
    id: 'objcount',
    title: 'Objective counters: live 6/7 on the HUD (also in combat), one evaluation per debounce',
    char: 'nightelf-druid',
    lua: L_`
      Login()
      local E = S().Engine
      local evals = 0
      local orig = E.Evaluate
      E.Evaluate = function(self, ...) evals = evals + 1; return orig(self, ...) end
      Sim.AcceptQuest(456, { { "Sable de la noche joven muerto", 7 }, { "Jabalí de cardo joven muerto: 0/4", 4 } })
      Sim.AcceptQuest(458, { { "Cosas", 1 } })
      Sim.Advance(1.5)
      Check(StepId() == "nesg-003", "current step is 'complete 456'", StepId())
      local obj = Plain(SendaHUD.objectives:GetText())
      Check(obj:find("Sable de la noche joven muerto 0/7", 1, true) ~= nil, "HUD adds the count when the client text has none", obj)
      Check(obj:find("Jabalí de cardo joven muerto: 0/4", 1, true) ~= nil and not obj:find("0/4 0/4", 1, true),
        "the client's own text (with its count) is shown as is", obj)

      Section("counters update in combat, without moving the step")
      Sim.player.combat = true
      Sim.Fire("PLAYER_REGEN_DISABLED")
      local nUpd = 0
      S().Events:On("SENDA_OBJECTIVES_UPDATED", function() nUpd = nUpd + 1 end)
      Sim.ProgressQuest(456, 1, 6)
      Sim.Advance(1)
      obj = Plain(SendaHUD.objectives:GetText())
      Check(obj:find("muerto 6/7", 1, true) ~= nil, "HUD shows 6/7 during combat", obj)
      Check(nUpd == 1, "one SENDA_OBJECTIVES_UPDATED for the change", nUpd)
      Sim.Fire("QUEST_LOG_UPDATE"); Sim.Advance(1)
      Check(nUpd == 1, "no redraw when the counters did not change", nUpd)
      Sim.ProgressQuest(456, 1, 7)
      Sim.ProgressQuest(456, 2, 4)
      Sim.Advance(1)
      Check(StepId() == "nesg-003", "the step does not move in combat", StepId())
      obj = SendaHUD.objectives:GetText()
      Check(Plain(obj):find("muerto 7/7", 1, true) ~= nil and obj:find(S().UI.HEX.green, 1, true) ~= nil,
        "finished objectives turn green", obj)

      Section("one evaluation per debounce")
      evals = 0
      for _ = 1, 12 do Sim.Fire("QUEST_LOG_UPDATE"); Sim.Fire("UNIT_QUEST_LOG_CHANGED", "player") end
      Sim.Advance(1)
      Check(evals == 1, "a burst of 24 log events -> 1 evaluation", evals)
      Sim.player.combat = false
      Sim.Fire("PLAYER_REGEN_ENABLED")
      Sim.Advance(1)
      Check(StepId() == "nesg-004", "leaving combat completes the step", StepId())
    `,
  },
  {
    id: 'objstep',
    title: 'A complete step with obj=N finishes with its objective, before the quest',
    char: 'gnome-warlock',
    lua: L_`
      Login()
      local E = S().Engine
      Sim.player.level = 30
      Sim.Fire("PLAYER_LEVEL_UP", 30, 0, 0, 0, 0, 0, 0, 0, 0)
      Sim.Advance(1)
      Sim.AcceptQuest(1802, { { "Tomo mohoso", 1, "item" }, { "Manuscrito", 1, "item" } })
      Sim.Advance(1)
      E:JumpTo(StepIndexOf("wl-felhunter-007"))
      Sim.Advance(1)
      Check(StepId() == "wl-felhunter-007", "on the obj=1 step", StepId())
      local obj = Plain(SendaHUD.objectives:GetText())
      Check(obj:find("Tomo mohoso", 1, true) ~= nil and not obj:find("Manuscrito", 1, true), "HUD lists only objective 1", obj)
      Sim.ProgressQuest(1802, 2, 1)
      Sim.Advance(1)
      Check(StepId() == "wl-felhunter-007", "finishing another objective does not complete it", StepId())
      Sim.ProgressQuest(1802, 1, 1)
      Sim.Advance(1.5)
      local p = S():GuideProgress("gnome-warlock")
      Check(p.done["wl-felhunter-007"] == "a", "obj=1 step completed by its objective", p.done["wl-felhunter-007"])
      Check(StepId() ~= "wl-felhunter-007", "the route moved on", StepId())
      Section("obj step completes while the quest is still open")
      Sim.player.quests[1802].objectives[1].have = 0
      Sim.player.quests[1802].objectives[1].finished = false
      Sim.player.quests[1802].objectives[2].have = 0
      Sim.player.quests[1802].objectives[2].finished = false
      Sim.Fire("QUEST_LOG_UPDATE")
      E:JumpTo(StepIndexOf("wl-felhunter-008"))
      Sim.Advance(1)
      Check(StepId() == "wl-felhunter-008", "on the obj=2 step", StepId())
      Sim.ProgressQuest(1802, 2, 1)
      Sim.Advance(1.5)
      Check(not S().Compat.IsQuestComplete(1802), "the quest itself is not complete")
      Check(p.done["wl-felhunter-008"] == "a", "obj=2 step completed anyway", p.done["wl-felhunter-008"])
    `,
  },
  {
    id: 'skiptree',
    title: 'Skip a quest and the quests that depend on it (right-click on the HUD), banner and Undo, in every guide',
    char: 'nightelf-druid',
    lua: L_`
      Login()
      local E, L = S().Engine, S().L
      Check(StepId() == "nesg-001", "starts at the accept step of 456", StepId())
      Check(SendaHUD.hit:IsShown(), "the step area takes a right-click on a quest step")
      Check(SendaHUD.bug:IsShown(), "the bug button is in the HUD header")
      local fl = S().Guides:Followups(456)
      local has457 = false
      for _, q in ipairs(fl or {}) do if q == 457 then has457 = true end end
      Check(has457, "the compiled index says 457 follows 456")
      Check(S().Guides:Followups(99999999) == nil, "unknown quests have no follow-ups")

      Section("right-click opens the menu")
      Sim.Click(SendaHUD.hit, "RightButton")
      Check(SendaDropdownList and SendaDropdownList:IsShown(), "right-click opens the skip menu")
      local rows = {}
      for _, r in ipairs(SendaDropdownList.rows) do if r:IsShown() then rows[#rows + 1] = Plain(r.fs:GetText()) end end
      Check(#rows >= 1 and rows[1]:find("Saltar esta misión", 1, true) ~= nil, "first entry: skip this quest", table.concat(rows, "|"))
      local hasPark = false
      for _, r in ipairs(rows) do if r:find("Dejar para después", 1, true) then hasPark = true end end
      Check(hasPark, "the menu also offers to leave it for later", table.concat(rows, "|"))
      Check(rows[1]:find("que dependen", 1, true) ~= nil or rows[1]:find("que depende", 1, true) ~= nil,
        "the entry says how many depend on it", rows[1])
      local n = select(2, E:SkipPlan(456))
      Check(n >= 1, "at least one dependent quest is in this guide", n)
      Sim.Click(SendaDropdownList.rows[1]); Sim.Advance(0.5)

      Section("everything of 456 and its dependents is skipped")
      local p = S():GuideProgress("nightelf-druid")
      Check(E:IsQuestSkipped(456) and E:IsQuestSkipped(457), "456 and 457 are in the skipped set")
      for _, id in ipairs({ "nesg-001", "nesg-003", "nesg-004", "nesg-005", "nesg-018", "nesg-022" }) do
        Check(E:IsDone(StepIndexOf(id)) == "s", id .. " reads as skipped", E:IsDone(StepIndexOf(id)))
      end
      Check(StepId() == "nesg-002", "the guide moves on to the next quest (458)", StepId())
      Check(S().db.skippedQuests[456] == true, "saved in the character's database")
      Check(p.done["nesg-001"] == nil, "the progress of the guide itself is not touched")
      Check(not E:IsQuestSkipped(458), "an unrelated quest is not skipped")
      local last = E:LastSkip()
      Check(last and last.quest == 456 and last.count == n, "the skip is remembered for the banner", last and last.count)
      Check(SendaHUD.banner:IsShown(), "banner shown")
      local banner = Plain(SendaHUD.banner.text:GetText())
      local qname = Plain(S().Names:Get("quest", 456) or "")
      local expect = n == 1 and string.format(L.SKIP_BANNER_1, qname) or string.format(L.SKIP_BANNER_N, qname, n)
      Check(banner:find("Saltada «", 1, true) == 1 and banner:find("depende", 1, true) ~= nil, "banner: skipped X and N that depend on it", banner)
      Check(banner == Plain(expect), "banner text matches the strings", banner)
      Check(Plain(SendaHUD.banner.undo:GetText()) == "Deshacer", "banner has the Undo button")
      local done, total = E:Progress()
      Check(done >= 6, "progress counts the skipped steps", done .. "/" .. total)

      Section("the skip is shared by every guide")
      local function questsOf(guide)
        local out = {}
        for _, e in ipairs(S().Guides:Resolve(guide)) do
          for _, q in ipairs(S().Conditions:Quests(e.step) or {}) do out[q] = true end
        end
        return out
      end
      local a, b = questsOf("human-mage"), questsOf("gnome-warlock")
      local common
      for q in pairs(a) do if b[q] and not (S().db.skippedQuests[q]) then common = q end end
      if common then
        E:SkipQuestTree(common)
        local stepsSkipped = 0
        for _, guide in ipairs({ "human-mage", "gnome-warlock" }) do
          E:SetGuide(guide, true)
          Sim.Advance(0.5)
          for _, e in ipairs(E:Steps()) do
            for _, q in ipairs(S().Conditions:Quests(e.step) or {}) do
              if q == common and E:IsDone(e) == "s" then stepsSkipped = stepsSkipped + 1 end
            end
          end
        end
        Check(stepsSkipped >= 2, "quest " .. common .. " reads as skipped in both guides", stepsSkipped)
        E:UndoSkip()
        E:SetGuide("nightelf-druid", true)
        Sim.Advance(0.5)
      else
        Check(false, "the two guides share a quest")
      end

      Section("Undo")
      E:UndoSkip(last)
      Sim.Advance(0.5)
      Check(not E:IsQuestSkipped(456) and not E:IsQuestSkipped(457), "the quests are back")
      Check(StepId() == "nesg-001", "back at the first step of the quest", StepId())
      Check(E:IsDone(StepIndexOf("nesg-005")) == nil, "its steps are pending again")
      Check(not SendaHUD.banner:IsShown(), "the banner goes away")
      Check(E:LastSkip() == nil, "nothing left to undo")

      Section("skip again from the HUD, close the banner, restore everything from the menu")
      Sim.Click(SendaHUD.hit, "RightButton")
      Sim.Click(SendaDropdownList.rows[1]); Sim.Advance(0.5)
      Check(E:IsQuestSkipped(456) and SendaHUD.banner:IsShown(), "skipped again")
      Sim.Click(SendaHUD.banner.close); Sim.Advance(0.3)
      Check(not SendaHUD.banner:IsShown() and E:IsQuestSkipped(456), "closing the banner keeps the skip")
      Sim.Click(SendaHUD.hit, "RightButton")
      rows = {}
      for _, r in ipairs(SendaDropdownList.rows) do if r:IsShown() then rows[#rows + 1] = Plain(r.fs:GetText()) end end
      Check(#rows >= 1 and rows[#rows]:find("Restaurar las", 1, true) ~= nil, "the menu offers to restore the skipped quests", table.concat(rows, "|"))
      Sim.Click(SendaDropdownList.rows[#rows]); Sim.Advance(0.5)
      Check(E:SkippedCount() == 0 and StepId() == "nesg-001", "all restored", StepId())

      Section("skipped steps survive a reload")
      E:SkipQuestTree(456)
      Sim.Advance(0.5)
      __report("saved", Sim.SaveVariables())
      __report("world", Sim.ExportWorld())
    `,
  },
  {
    id: 'skiptree-reload',
    title: 'Skipped quests are still skipped after a reload; the English client says it in English',
    char: 'nightelf-druid',
    locale: 'enUS',
    needs: 'skiptree',
    lua: L_`
      Login()
      local E, L = S().Engine, S().L
      Check(E:IsQuestSkipped(456), "456 still skipped after the reload")
      Check(StepId() == "nesg-002", "the guide did not go back", StepId())
      Check(E:IsDone(StepIndexOf("nesg-003")) == "s", "its steps still read as skipped")
      Check(S().Guides:Followups(456) ~= nil, "the follow-up index is loaded")
      Check(L.SKIP_MENU == "Skip this quest", "English strings", L.SKIP_MENU)
      Sim.Click(SendaHUD.hit, "RightButton")
      local rows = {}
      for _, r in ipairs(SendaDropdownList.rows) do if r:IsShown() then rows[#rows + 1] = Plain(r.fs:GetText()) end end
      Check(#rows >= 1 and rows[#rows]:find("Restore the", 1, true) ~= nil, "the restore entry is in English", table.concat(rows, "|"))
      SendaDropdownList:Hide()
      E:SkipQuestTree(458)
      Sim.Advance(0.5)
      local banner = Plain(SendaHUD.banner.text:GetText())
      Check(banner:find("Skipped “", 1, true) == 1, "banner in English", banner)
      E:UndoSkip()
      Sim.Advance(0.3)
      Check(Plain(SendaHUD.banner.undo:GetText()) == "Undo", "Undo button in English")
    `,
  },
  {
    id: 'park',
    title: 'Aside: leave the succubus chain for later (HUD clock), passed over but pending, reminder in Ashenvale, resume as a detour',
    char: 'gnome-warlock',
    lua: L_`
      Login()
      Sim.Advance(6)
      local E, A, L = S().Engine, S().Aside, S().L
      local p = Sim.player
      p.level = 20
      Sim.Fire("PLAYER_LEVEL_UP", 20, 0, 0, 0, 0, 0, 0, 0, 0)
      Sim.Advance(1)
      local i = StepIndexOf("wl-succubus-003")
      Check(i ~= nil, "the succubus chain is in the warlock guide")
      E:JumpTo(i); Sim.Advance(0.5)
      Check(StepId() == "wl-succubus-003", "on the first step of the chain", StepId())
      local sec = E:Entry().section
      Check(sec.parkable == true and type(sec.later_hint) == "string" and sec.later_hint:find("Vallefresno", 1, true) ~= nil,
        "the section is parkable and carries its Spanish hint", sec.later_hint)
      Check(SendaHUD.park:IsShown() and SendaHUD.park:IsEnabled(), "HUD clock button is there and enabled")

      Section("HUD clock: leave for later")
      Sim.Click(SendaHUD.park); Sim.Advance(0.5)
      local prog = S():GuideProgress("gnome-warlock")
      local it = prog.parked and prog.parked["s:wl-succubus"]
      Check(it ~= nil and it.kind == "section", "progress.parked keeps the whole section")
      Check(it and it.level == 20 and it.map == 1426 and type(it.when) == "number", "with when (level, time) and where (map)", it and it.map)
      Check(StepId() ~= nil and StepId():sub(1, 12) ~= "wl-succubus-", "the route moves on past the chain", StepId())
      local parkedSteps, marked = 0, 0
      for _, e in ipairs(E:Steps()) do
        if e.section.id == "wl-succubus" then
          if E:StepParked(e) then parkedSteps = parkedSteps + 1 end
          if E:IsDone(e) then marked = marked + 1 end
        end
      end
      Check(parkedSteps > 10, "every step of the section reads as parked", parkedSteps)
      Check(marked == 0, "none is marked done or skipped", marked)
      Check(E:IsApplicable(E:Entry(i)) == false, "the engine passes over them like skipped ones")
      local list = E:Parked()
      Check(#list == 1 and #list[1].steps > 5, "Parked() lists it with its pending steps", #list)
      local rem0 = A:Reminder()
      Check(rem0 == nil and SendaHUD.aside.block ~= "parked", "no reminder in Dun Morogh", rem0 and (rem0.reason .. " " .. tostring(rem0.dkey)))
      Check(SendaHUD.park:IsEnabled() or true, "clock still usable on the next step")

      Section("reminder when entering Ashenvale")
      Sim.MoveTo(1440, 0.40, 0.50); Sim.Advance(1)
      Check(SendaHUD.aside:IsShown() and SendaHUD.aside.block == "parked", "HUD shows one reminder line in Ashenvale")
      local line = Plain(SendaHUD.aside.text:GetText())
      Check(line:find("Pendiente aquí: Brujo: Súcubo o Íncubo", 1, true) ~= nil and line:find("Retomar", 1, true) ~= nil,
        "«Pendiente aquí: <name> · Retomar»", line)
      Sim.Click(SendaHUD.aside); Sim.Advance(0.5)
      Check(SendaMainFrame:IsShown() and S().AsideTab:Focused() == "parked", "clicking it opens the Aside tab at the For later block")
      Sim.Click(SendaHUD.aside, "RightButton"); Sim.Advance(0.5)
      local rem1 = A:Reminder()
      Check(rem1 == nil and SendaHUD.aside.block ~= "parked", "right-click: not reminded here again", rem1 and (rem1.reason .. " " .. tostring(rem1.dkey)))
      Sim.MoveTo(1426, 0.5, 0.5); Sim.Advance(0.5)
      Sim.MoveTo(1413, 0.49, 0.57); Sim.Advance(0.5)
      Check(SendaHUD.aside:IsShown() and SendaHUD.aside.block == "parked", "still reminded in the Barrens (another map of the chain)")

      Section("the tab: For later block with Resume / Back to route")
      local tabs = {}
      for _, t in ipairs(Sim.tabs) do tabs[t.key] = t end
      S().AsideTab:Open("parked"); Sim.Advance(0.3)
      local frame = tabs.aside.frame
      local resume
      for _, b in ipairs(Sim.AllWidgets()) do
        if b.__type == "Button" and b:IsVisible() and b.GetText and Plain(b:GetText() or "") == "Retomar" then resume = b end
      end
      Check(frame and frame:IsShown() and resume ~= nil, "the For later block shows a Resume button")

      Section("resume: a detour with the chain's own steps")
      local mainBefore = StepId()
      Sim.Click(resume); Sim.Advance(0.5)
      Check(A:Active(), "a detour is active")
      Check(Plain(SendaHUD.section:GetText()):find("Desvío 1/", 1, true) == 1, "HUD header says it is a detour", SendaHUD.section:GetText())
      Check(SendaHUD.cancelDetour:IsShown(), "HUD offers Cancel detour")
      Check(Plain(SendaHUD.detour:GetText()):find("Al acabar vuelves a", 1, true) ~= nil, "HUD says where you go back to")
      local t, src = ArrowTarget()
      Check(t and src == "guide" and (t.label or ""):find("Desvío:", 1, true) == 1, "the arrow follows the detour", t and t.label)
      local first = A:CurrentStep()
      Check(first and first.id:sub(1, 12) == "wl-succubus-", "the detour's first step is from the chain", first and first.id)
      Check(StepId() == mainBefore, "the main route keeps its place", StepId())
      -- do the first quest of the chain in the detour: it counts for the route
      local q = first.quest
      if first["do"] == "accept" and q then
        Sim.AcceptQuest(q, { { "Objetivo", 1 } }); Sim.Advance(0.5)
        Check(prog.done[first.id] == "a", "a step done in the detour is marked in the route", prog.done[first.id])
        Check(A:CurrentStep() ~= first, "the detour moves on")
      end

      Section("cancel: back to the route, the rest stays parked")
      Sim.Click(SendaHUD.cancelDetour); Sim.Advance(0.5)
      Check(not A:Active(), "detour cancelled")
      Check(StepId() == mainBefore, "back on the route where it was", StepId())
      t, src = ArrowTarget()
      Check(not t or (t.label or ""):find("Desvío:", 1, true) == nil, "the arrow is back on the route", t and t.label)
      Check(prog.parked["s:wl-succubus"] ~= nil, "what is left of the chain is still parked")

      Section("back to the route")
      E:Unpark("s:wl-succubus"); Sim.Advance(0.5)
      Check(prog.parked["s:wl-succubus"] == nil, "no longer parked")
      Check(StepId():sub(1, 12) == "wl-succubus-", "the route goes back to the chain", StepId())
      Section("park again and keep it for the reload")
      Sim.Click(SendaHUD.park); Sim.Advance(0.5)
      __report("saved", Sim.SaveVariables())
      __report("world", Sim.ExportWorld())
    `,
  },
  {
    id: 'park-reload',
    title: 'Aside: a parked chain survives a reload; English client',
    char: 'gnome-warlock',
    locale: 'enUS',
    needs: 'park',
    lua: L_`
      Login()
      Sim.Advance(6)
      local E, L = S().Engine, S().L
      local prog = S():GuideProgress("gnome-warlock")
      Check(prog.parked and prog.parked["s:wl-succubus"] ~= nil, "still parked after the reload")
      Check(StepId():sub(1, 12) ~= "wl-succubus-", "the route still passes over it", StepId())
      Check(L.HUD_PARK == "Leave for later" and L.TAB_ASIDE == "Aside", "English strings")
      Sim.MoveTo(1440, 0.40, 0.50); Sim.Advance(1)
      local line = Plain(SendaHUD.aside.text:GetText() or "")
      Check(SendaHUD.aside:IsShown() and line:find("Pending here: ", 1, true) ~= nil and line:find("Resume", 1, true) ~= nil, "English reminder", line)
      RunAllTabs()
    `,
  },
  {
    id: 'park-quest',
    title: 'Aside: right-click «Dejar para después» parks a quest and its dependents (mage); the druid bear chain parks with Lunaclaw',
    char: 'human-mage',
    lua: L_`
      Login()
      Sim.Advance(6)
      local E, A = S().Engine, S().Aside
      Check(StepId() == "hmage-northshire-001", "mage starts at 783", StepId())
      Sim.Click(SendaHUD.hit, "RightButton")
      local row
      for _, r in ipairs(SendaDropdownList.rows) do
        if r:IsShown() and Plain(r.fs:GetText()):find("Dejar para después", 1, true) then row = r end
      end
      Check(row ~= nil, "the right-click menu offers «Dejar para después»")
      Sim.Click(row); Sim.Advance(0.5)
      local prog = S():GuideProgress("human-mage")
      local it = prog.parked and prog.parked["q:783"]
      Check(it and it.kind == "quest" and it.quest == 783, "783 is parked")
      local fl = S().Guides:Followups(783) or {}
      Check(#fl == 0 or #it.list == #fl + 1 or #it.list >= 2, "with the quests that depend on it", it and #it.list)
      Check(E:IsDone(StepIndexOf("hmage-northshire-001")) == nil and E:StepParked(E:Entry(StepIndexOf("hmage-northshire-001"))),
        "its steps are parked, not done")
      Check(StepId() ~= "hmage-northshire-001" and StepId() ~= "hmage-northshire-002", "the route moves on", StepId())
      Check(not S().Engine:IsQuestSkipped(783), "parking is not skipping")
      Section("doing it by yourself clears it")
      Sim.AcceptQuest(783, {}); Sim.Advance(0.3)
      Sim.FinishQuestObjectives(783); Sim.TurnInQuest(783); Sim.Advance(0.5)
      local own, deps = 0, 0
      for _, x in ipairs(E:Parked()) do
        if x.key == "q:783" then
          for _, e in ipairs(x.steps) do if e.step.quest == 783 then own = own + 1 else deps = deps + 1 end end
        end
      end
      Check(own == 0, "a parked quest you hand in on your own leaves the pending steps", own)
      Check(deps > 0 and prog.parked["q:783"] ~= nil, "its dependents stay parked until you resume them", deps)
      E:Unpark("q:783"); Sim.Advance(1)
      Check(prog.done["hmage-northshire-002"] == "a" or E:IsDone(StepIndexOf("hmage-northshire-002")) ~= nil,
        "back on the route, the steps you already did read as done by the game")
      RunAllTabs()
      Section("druid: the bear chain parks together with Lunaclaw")
      local hasDruid = S().Guides:Get("nightelf-druid") ~= nil
      Check(hasDruid, "druid guide registered")
    `,
  },
  {
    id: 'park-druid',
    title: 'Aside: parking the druid bear-form chain also parks the Lunaclaw section that follows it',
    char: 'nightelf-druid',
    lua: L_`
      Login()
      Sim.Advance(6)
      local E = S().Engine
      local p = Sim.player
      p.level = 10
      Sim.Fire("PLAYER_LEVEL_UP", 10, 0, 0, 0, 0, 0, 0, 0, 0)
      Sim.Advance(1)
      local i = StepIndexOf("dr-10-bear-002")
      Check(i ~= nil, "bear chain step exists")
      E:JumpTo(i); Sim.Advance(0.3)
      local info = E:ParkInfo(E:Entry(i))
      Check(info and info.kind == "section" and info.hint ~= nil, "a parkable class section with its hint", info and info.hint)
      local hasLuna = false
      for _, sid in ipairs(info and info.sections or {}) do if sid == "dr-11-lunaclaw" then hasLuna = true end end
      Check(hasLuna, "the chain includes dr-11-lunaclaw (its quests depend on the bear chain)")
      E:Park(E:Entry(i)); Sim.Advance(0.5)
      local cur = StepId() or ""
      Check(cur:sub(1, 6) ~= "dr-10-" and cur:sub(1, 6) ~= "dr-11-", "the route passes over both sections", cur)
      local luna = StepIndexOf("dr-11-lunaclaw-001") or StepIndexOf("dr-11-lunaclaw-002")
      Check(luna and E:StepParked(E:Entry(luna)), "Lunaclaw steps are parked too")
    `,
  },
  {
    id: 'reserve',
    title: 'Aside: a level-gated step offers real XP-reserve quests nearby; a detour follows them and returns to the route',
    char: 'gnome-warlock',
    lua: L_`
      Login()
      Sim.Advance(6)
      local E, A, R, L = S().Engine, S().Aside, S().Reserve, S().L
      local p = Sim.player
      Check(R:Count() > 500, "the compiled reserve has quests", R:Count())
      Check(not R:Ready(), "and is not decoded until needed")
      p.level = 17
      Sim.Fire("PLAYER_LEVEL_UP", 17, 0, 0, 0, 0, 0, 0, 0, 0)
      Sim.Advance(1)
      E:JumpTo(StepIndexOf("a19rr-016"))
      E:Advance()
      Sim.MoveTo(1433, 0.271, 0.486)
      p.xp, p.xpMax = 17000, 17700
      Sim.Fire("PLAYER_XP_UPDATE", "player")
      Sim.Advance(1)
      local need = R:Need()
      Check(need and need.level == 18 and need.xp == 700, "the next route step needs level 18: 700 XP missing", need and need.xp)
      Sim.Advance(3)
      Check(R:Ready(), "the reserve loads on demand, out of combat")
      local st = R:State()
      Check(st.reason == "gate" and #(st.offers or {}) > 0, "offered because the route is level-gated", st.reason)
      local route = R:RouteQuests()
      local ok, real = true, {}
      for _, o in ipairs(st.offers) do
        if route[o.e.quest] or not R:Available(o.e) or o.e.reqlevel > 17 then ok = false end
        real[o.e.quest] = true
      end
      Check(ok, "only quests you can take now and that the route does not ask for")
      Check(real[118] or real[120] or real[129], "real pool entries: Redridge quests of the Polestar route (118, 120, 129)")
      for i = 2, #st.offers do
        if st.offers[i].rate > st.offers[i - 1].rate then ok = false end
      end
      Check(ok, "sorted by XP per minute (with the walk to the giver)")
      local e118 = R:Get(118)
      Check(e118 and e118.giver.at[1] == 1433 and e118.turnin and e118.xp > 0 and e118.mins > 0 and e118.reqlevel <= 17,
        "an entry carries giver, turn-in, XP, minutes and level")
      Check(R:QuestXP({ xp = 1000, level = 10 }, 15) == 1000 and R:QuestXP({ xp = 1000, level = 10 }, 16) == 800
        and R:QuestXP({ xp = 1000, level = 10 }, 18) == 400 and R:QuestXP({ xp = 1000, level = 10 }, 25) == 100,
        "quest XP drops above quest level + 5 (80/60/40/20/10%)")
      Sim.Advance(0.5)
      Check(SendaHUD.aside:IsShown(), "HUD shows one reserve line")
      local line = Plain(SendaHUD.aside.text:GetText())
      Check(line:find("Te faltan 700 XP para el siguiente paso: estas misiones te los dan en ~", 1, true) == 1, "«Te faltan N XP ... en ~M min»", line)
      Sim.Click(SendaHUD.aside); Sim.Advance(0.5)
      Check(S().AsideTab:Focused() == "reserve", "clicking it opens the reserve block")

      Section("take the ones I need: a detour")
      local mainBefore = StepId()
      S().AsideTab:TakePlan(); Sim.Advance(0.5)
      Check(A:Active(), "detour started")
      local steps = A:Steps()
      Check(#steps == 3 * #st.plan, "accept, complete and turn in for each quest", #steps)
      Check(steps[1].step["do"] == "accept" and steps[#steps].step["do"] == "turnin", "accepts first, turn-ins last")
      Check(HudText():find("Coge «", 1, true) == 1, "the HUD shows the detour step text", HudText())
      local t = ArrowTarget()
      Check(t and (t.label or ""):find("Desvío:", 1, true) == 1, "the arrow follows the detour", t and t.label)
      Section("play the detour")
      local guard = 0
      while A:Active() and guard < 60 do
        guard = guard + 1
        local s = A:CurrentStep()
        local q = s.quest
        if s["do"] == "accept" then Sim.AcceptQuest(q, { { "Objetivo", 1 } })
        elseif s["do"] == "complete" then Sim.FinishQuestObjectives(q)
        elseif s["do"] == "turnin" then Sim.TurnInQuest(q) end
        Sim.Advance(0.5)
      end
      Check(not A:Active(), "the detour ends on its own when everything is handed in")
      for _, o in ipairs(st.plan) do Check(p.completed[o.e.quest] == true, "handed in " .. o.e.quest) end
      Check(StepId() == mainBefore, "back on the route where it was", StepId())
      t = ArrowTarget()
      Check(not t or (t.label or ""):find("Desvío:", 1, true) == nil, "the arrow is back on the route")
      Check(Plain(SendaHUD.section:GetText()):find("Desvío", 1, true) == nil, "the HUD shows the route again")

      Section("more quests here, by hand")
      R:Ask(); Sim.Advance(0.5)
      Check(R:Asked(), "«Más misiones aquí» asked on this map")
      RunAllTabs()
    `,
  },
  {
    id: 'detour-route',
    title: 'Aside: a quest done in a detour marks the main route step; goto steps of the route wait',
    char: 'nightelf-druid',
    lua: L_`
      Login()
      Sim.Advance(6)
      local E, A, R = S().Engine, S().Aside, S().Reserve
      R:LoadNow()
      -- the next accept step of the route whose quest is also in the reserve
      local q, idx
      for i = E:Index(), #E:Steps() do
        local s = E:Steps()[i].step
        if s["do"] == "accept" and s.quest and R:Get(s.quest) then q, idx = s.quest, i; break end
      end
      Check(q ~= nil, "found a route quest that is also in the reserve", q)
      E:JumpTo(idx); Sim.Advance(0.5)
      Check(StepId() == E:Steps()[idx].step.id, "the route is on its accept step")
      Check(A:Start({ { kind = "reserve", quest = q } }), "detour with that quest")
      Sim.Advance(0.3)
      Check(A:CurrentStep()["do"] == "accept" and A:CurrentStep().quest == q, "detour: accept it")
      Check(S().Engine:WantsQuest("accept", q), "auto-accept takes the detour quest")
      Sim.AcceptQuest(q, { { "Objetivo", 1 } }); Sim.Advance(0.6)
      Check(E:IsDone(idx) == "a", "the main route's accept step is marked by the game", E:IsDone(idx))
      Sim.FinishQuestObjectives(q); Sim.Advance(0.5)
      Sim.TurnInQuest(q); Sim.Advance(0.6)
      Check(not A:Active(), "detour finished")
      local all = true
      for _, e in ipairs(E:Steps()) do
        local s = e.step
        if s.quest == q and (s["do"] == "accept" or s["do"] == "complete" or s["do"] == "turnin") and e.index < E:Index() and not E:IsDone(e) then all = false end
      end
      Check(all, "the route counts what you did in the detour")
      Check(S().Guides:Get("nightelf-druid") ~= nil, "guide still active")
      Section("a route goto passed during a detour is not done")
      local gi
      for i = E:Index(), #E:Steps() do if E:Steps()[i].step["do"] == "goto" and E:Steps()[i].step.at then gi = i; break end end
      if gi then
        E:JumpTo(gi); Sim.Advance(0.3)
        local other
        for _, e in ipairs(R:LoadNow()) do if e.quest ~= q then other = e.quest; break end end
        A:Start({ { kind = "reserve", quest = other } }); Sim.Advance(0.3)
        local at = E:Steps()[gi].step.at
        Sim.MoveTo(at[1], at[2] / 100, at[3] / 100); Sim.Advance(1.5)
        Check(StepId() == E:Steps()[gi].step.id, "walking over the route's goto in a detour does not complete it", StepId())
        A:Cancel(); Sim.Advance(1.5)
        Check(StepId() ~= E:Steps()[gi].step.id, "after the detour, the goto completes as usual", StepId())
      end
      Section("a detour in progress is saved")
      local pick
      for _, e in ipairs(R:LoadNow()) do if R:Available(e) and not S().Engine:QuestTaken(e.quest) then pick = e.quest; break end end
      Check(pick ~= nil and A:Start({ { kind = "reserve", quest = pick } }), "detour started", pick)
      Sim.Advance(0.3)
      Sim.AcceptQuest(pick, { { "Objetivo", 1 } }); Sim.Advance(0.5)
      Check(A:Index() == 2, "first step done", A:Index())
      __report("pick", pick)
      __report("saved", Sim.SaveVariables())
      __report("world", Sim.ExportWorld())
    `,
  },
  {
    id: 'detour-reload',
    title: 'Aside: the active detour comes back after a reload, where it was',
    char: 'nightelf-druid',
    needs: 'detour-route',
    lua: L_`
      Login()
      Sim.Advance(6)
      local A = S().Aside
      Check(A:Active(), "the detour is back after the reload")
      local s = A:CurrentStep()
      Check(s and s["do"] == "complete", "on its second step (complete)", s and s["do"])
      Check(Plain(SendaHUD.section:GetText()):find("Desvío 2/3", 1, true) == 1, "HUD shows the detour", SendaHUD.section:GetText())
      A:Cancel(); Sim.Advance(0.5)
      Check(not A:Active() and S().db.aside.detour == nil, "cancelled and forgotten")
    `,
  },
  {
    id: 'report',
    title: 'Bug report window: context, last 20 caught errors, no names, copy box and GitHub link under 2000 characters',
    char: 'nightelf-druid',
    lua: L_`
      Login()
      local R, E, L = S().Report, S().Engine, S().L
      Sim.addons = { { name = "Senda", loaded = true }, { name = "Questie", loaded = true }, { name = "TomTom", loaded = true },
        { name = "Blizzard_Foo", loaded = true }, { name = "Apagado", loaded = false } }
      local me = Sim.player.name
      Check(me and #me >= 2, "the test character has a name", me)

      Section("the errors Senda catches are kept (last 20, scrubbed)")
      local handled = 0
      local old = geterrorhandler()
      seterrorhandler(function() handled = handled + 1 end)
      local n = 0
      S().Events:On("SENDA_TEST_ERROR", function() n = n + 1; error("fallo " .. n .. " de " .. me .. " en " .. GetRealmName()) end)
      for _ = 1, 25 do S().Events:Fire("SENDA_TEST_ERROR") end
      seterrorhandler(old)
      Check(handled == 25, "the errors still reach the game's handler", handled)
      Check(S().Errors:Count() == 20, "only the last 20 are kept", S().Errors:Count())
      local list = S().Errors.list
      Check(list[1].msg:find("fallo 6 ", 1, true) ~= nil and list[20].msg:find("fallo 25 ", 1, true) ~= nil, "oldest dropped first", list[1].msg)
      Check(not list[20].msg:find(me, 1, true) and not list[20].msg:find(GetRealmName(), 1, true), "no character or realm name", list[20].msg)
      Check(list[20].msg:find("<pj>", 1, true) ~= nil and list[20].msg:find("<reino>", 1, true) ~= nil, "replaced by placeholders", list[20].msg)

      Section("/senda informe opens the window")
      Slash("informe")
      Check(SendaReportFrame and SendaReportFrame:IsShown(), "/senda informe opens the report window")
      SendaReportFrame:Hide()
      Slash("report")
      Check(SendaReportFrame:IsShown(), "/senda report is an alias")
      SendaReportFrame:Hide()
      Sim.Click(SendaHUD.bug)
      Check(SendaReportFrame:IsShown(), "the HUD bug button opens it too")
      local f = SendaReportFrame
      local text = f.report:GetText()
      local function has(s) return text:find(s, 1, true) ~= nil end
      Check(has("Senda: " .. S().VERSION), "Senda version")
      Check(has("1.60.1.70291") and has("esES"), "client build and locale")
      Check(has("NightElf") and has("DRUID"), "race and class")
      Check(has("nightelf-druid") and has("nesg-001") and has("[accept]"), "guide and step id")
      Check(has("Texto: Coge la misión"), "step text", text)
      Check(has("1438"), "map", text)
      Check(has("456 sin coger"), "quest log state of the step's quest", text)
      Check(has("Questie") and has("TomTom") and not has("Blizzard_Foo") and not has("Apagado"), "other enabled addons only", text)
      Check(has("Errores de Senda (últimos 20)"), "error section header")
      local count = 0
      for _ in text:gmatch("fallo %d+ de <pj>") do count = count + 1 end
      Check(count == 20, "20 errors listed", count)
      Check(not has(me) and not has(GetRealmName()), "no character or realm name anywhere in the report")

      Section("quest log state follows the game")
      Sim.AcceptQuest(456, { { "Sable de la noche joven muerto", 7 } })
      Sim.ProgressQuest(456, 1, 3)
      Sim.Advance(1)
      E:JumpTo(StepIndexOf("nesg-003"))
      Sim.Advance(0.5)
      local t2 = R:Text("", R:Context())
      Check(t2:find("456 en el registro 3/7", 1, true) ~= nil, "in the log with the objective counter", t2)
      Check(t2:find("Descripción", 1, true) == nil, "no description line when empty")

      Section("description, copy box and link")
      local words = {}
      for i = 1, 150 do words[i] = "ñandú" end
      f.desc:SetText("La flecha no se mueve. " .. table.concat(words, " "))
      Sim.RunScript(f.desc, "OnTextChanged", true)
      text = f.report:GetText()
      Check(text:find("Descripción: La flecha no se mueve.", 1, true) ~= nil, "the description goes first in the report")
      local url = f.url:GetText()
      Check(url:sub(1, 52) == "https://github.com/e-omunoz/senda/issues/new?title=P", "link to the GitHub new-issue page", url:sub(1, 70))
      Check(#url <= 2000 and #url <= R.URL_MAX, "link under 2000 characters", #url)
      Check(url:find("&body=", 1, true) ~= nil and url:find("Problema%20en%20el%20paso%20nesg", 1, true) ~= nil, "title with the step", url:sub(1, 120))
      Check(url:find("La%20flecha%20no%20se%20mueve", 1, true) ~= nil, "the description is in the body")
      Check(url:find("%E2%80%A6", 1, true) ~= nil, "a long description is cut with an ellipsis")
      Check(not url:find("%%[^0-9A-F]") and not url:find("%%[0-9A-F][^0-9A-F]"), "the link is well encoded")
      Check(not url:find(me, 1, true), "no character name in the link")
      Check(f.url.fixed == url and f.report.fixed == text, "boxes are read-only copies")
      f.desc:SetText("Corto")
      Sim.RunScript(f.desc, "OnTextChanged", true)
      url = f.url:GetText()
      Check(url:find("body=Corto%0A%0ASenda", 1, true) ~= nil, "short body: description, then the minimal context", url)
      Check(#url < 900, "a short report gives a short link", #url)
      Sim.Click(f.copy)
      Check(f.report:HasFocus() and f.report.__highlight ~= nil, "Copy selects all the text of the copy box")
      Check(f.url:IsShown() and f.url:GetText() == url, "the link sits in its own copyable line")

      Section("the window reflects when it was opened")
      f:Hide()
      E:SkipQuestTree(458)
      Sim.Advance(0.3)
      R:Open()
      Check(f.report:GetText():find("Misiones saltadas: ", 1, true) ~= nil, "skipped quests are counted in the report", f.report:GetText())
      f:Hide()
      Check(#Sim.errors == 0, "no Lua errors")
    `,
  },
  {
    id: 'place',
    title: 'Placement (setup): play into Teldrassil; keep early SavedVariables and the later world',
    char: 'nightelf-druid',
    lua: L_`
      Login()
      Check(StepId() == "nesg-001", "fresh character starts at nesg-001", StepId())
      -- A manual skip saved early: placement must keep it (and it vouches for nothing).
      S():GuideProgress("nightelf-druid").done["netd-013"] = "s"
      local early = Sim.SaveVariables()
      S():GuideProgress("nightelf-druid").done["netd-013"] = nil
      local n = 0
      while StepId() ~= "netd-013" and n < 120 do AutoPlay(1); n = n + 1 end
      Check(StepId() == "netd-013", "played up to netd-013 (turn in 97944)", tostring(StepId()) .. " after " .. n .. " steps")
      Check(n >= 10, "more than 10 steps played", n)
      __report("saved", early)
      __report("world", Sim.ExportWorld())
    `,
  },
  {
    id: 'place-wiped',
    title: 'Placement: SavedVariables wiped mid-guide -> the step is recomputed from the quest log',
    char: 'nightelf-druid',
    needs: 'place',
    wipeSaved: true,
    lua: L_`
      Login()
      local E = S().Engine
      Check(StepId() == "netd-013", "placed at the first pending quest step", StepId())
      local p = S():GuideProgress("nightelf-druid")
      Check(p.done["nesg-043"] == "a", "the goto to Dolanaar behind the progress passes", p.done["nesg-043"])
      Check(p.done["netd-002"] == "a", "the hearthstone bind behind the progress passes", p.done["netd-002"])
      Check(p.done["netd-021"] == "a", "a profession step behind the progress passes (profession not known now)", p.done["netd-021"])
      Check(E:ResumeIndex() == StepIndexOf("netd-013"), "ResumeIndex gives the same place", E:ResumeIndex())
      local said = false
      for _, l in ipairs(Sim.chat) do if l:find("registro de misiones", 1, true) then said = true end end
      Check(said, "chat explains the placement")

      Section("sliced over frames")
      E:Place("test")
      Check(E:Placing(), "placement runs in the background")
      local frames = 0
      while E:Placing() and frames < 400 do Sim.Advance(Sim.FRAME); frames = frames + 1 end
      Check(not E:Placing() and frames >= 2, "placement takes several frames for " .. #E:Steps() .. " steps", frames)
      Check(StepId() == "netd-013", "a second placement changes nothing", StepId())
    `,
  },
  {
    id: 'place-stale',
    title: 'Placement: character that played without the add-on is placed after those steps; skips respected',
    char: 'nightelf-druid',
    needs: 'place',
    lua: L_`
      Login()
      local E = S().Engine
      local p = S():GuideProgress("nightelf-druid")
      Check(p.done["netd-013"] == "s", "manual skip kept", p.done["netd-013"])
      -- netd-015 hands in a profession quest this character no longer qualifies for (no profession after the
      -- relog), so the first pending step after the skipped netd-013 is netd-017.
      Check(StepId() == "netd-017", "placed after the steps played without the add-on (and the skipped one)", StepId())
      Check(p.done["nesg-004"] == "a" and p.done["nesg-043"] == "a", "steps passed are marked done")
      Section("Back is respected across a reload")
      E:JumpTo(StepIndexOf("nesg-043"))
      Sim.Advance(1)
      Check(StepId() == "nesg-043", "went back to nesg-043", StepId())
      Check(p.held == "nesg-043", "the held step is saved", p.held)
      __report("expectStep", StepId())
      __report("saved", Sim.SaveVariables())
      __report("world", Sim.ExportWorld())
    `,
  },
  {
    id: 'place-held',
    title: 'Placement: a step you went back to is not moved by the placement after a reload',
    char: 'nightelf-druid',
    needs: 'place-stale',
    lua: L_`
      Login()
      Sim.Advance(6)
      Check(StepId() == SIM_EXPECT_STEP, "still on the step you went back to", tostring(StepId()) .. " vs " .. tostring(SIM_EXPECT_STEP))
      Sim.Click(SendaHUD.done)
      Sim.Advance(1)
      Check(StepId() == "netd-017", "Done moves on to where you were", StepId())
    `,
  },
  {
    id: 'duo',
    title: 'Duo sync (two clients): hello, snapshots, counts, steps ahead/behind, hold, skip to my step, 40-quest log',
    char: 'gnome-warlock',
    duo: { char: 'nightelf-druid', name: 'Lunaria' },
    lua: L_`
      Peer("Login()")
      Login()
      DuoGuide()
      Peer("DuoGuide()")
      Sim.Advance(1)
      Sim.AcceptQuest(9001, { { "Jabalíes muertos", 8 } })
      Sim.ProgressQuest(9001, 1, 3)
      Peer([[Sim.AcceptQuest(9001, { { "Jabalíes muertos", 8 } }); Sim.ProgressQuest(9001, 1, 1)]])
      Sim.Advance(1)
      Check(StepId() == "dp-002" and Peer("return StepId()") == "dp-002", "both on dp-002 (complete 9001)", StepId())
      Check(#Sim.AddonTexts("Senda") == 0, "solo: nothing sent")

      Section("hello and snapshots both ways")
      local before = #Sim.addonSent
      DuoJoin("Lunaria", "DRUID", "NightElf")
      Peer([[DuoJoin("Pruebas", "WARLOCK", "Gnome")]])
      Sim.Advance(1)
      local first = Sim.AddonTexts("Senda", before + 1)
      Check(#first == 0, "nothing goes out at once (the hello waits for the others to listen)", table.concat(first, " "))
      Sim.Advance(12)
      local sent = Sim.AddonTexts("Senda", before + 1)
      Check(sent[1] and sent[1]:match("^1[HR]|") ~= nil, "the first message is the hello (or the answer to hers)", sent[1])
      local m = DuoMember("Lunaria")
      Check(m ~= nil, "A heard Lunaria's Senda")
      Check(DuoLog("Lunaria") == "9001:1/8", "A has Lunaria's log from her snapshot", DuoLog("Lunaria"))
      Check(Peer([[return DuoLog("Pruebas")]]) == "9001:3/8", "B has A's log from A's snapshot", Peer([[return DuoLog("Pruebas")]]))
      local snap = false
      for _, t in ipairs(sent) do if t:match("^1[SR]|") then snap = true end end
      Check(snap, "A sent a snapshot (1S/1R)")
      Check(m and m.at and m.at.key == "dp-002", "A knows Lunaria's step by key (2P)", m and m.at and m.at.key)
      Check(m and m.unit and m.unit.class == "DRUID", "A knows Lunaria's class (2U)")
      Check(Plain(SendaHUD.duo:GetText()):find("Lunaria está en tu paso", 1, true) ~= nil, "HUD duo line: on your step", SendaHUD.duo:GetText())

      Section("one count change -> one message within ~2 s")
      before = #Sim.addonSent
      Sim.ProgressQuest(9001, 1, 4)
      Sim.Advance(1.5)
      Check(#Sim.AddonTexts("Senda", before + 1) == 0, "debounced: nothing after 1.5 s")
      Sim.Advance(1)
      sent = Sim.AddonTexts("Senda", before + 1)
      Check(#sent == 1 and sent[1] == "1|9001:4/8", "exactly one delta message", table.concat(sent, " "))
      Sim.Advance(0.5)
      Check(Peer([[return DuoLog("Pruebas")]]) == "9001:4/8", "B sees 4/8")

      Section("hold: A finished, Lunaria still needs the objective")
      Sim.ProgressQuest(9001, 1, 8)
      Sim.Advance(3)
      Check(StepId() == "dp-002", "A stays on dp-002 while Lunaria needs 1/8", StepId())
      Check(SendaHUD.duoWait:IsShown() and Plain(SendaHUD.duoWait:GetText()) == "Espera a Lunaria: le falta 1/8", "HUD: wait line", SendaHUD.duoWait:GetText())
      Check(SendaHUD.goOn:IsShown(), "HUD: 'Seguir sin él' button")
      Check(S().Party.HoldsQuest(9001), "no automatic turn-in while she needs it")
      Peer([[Sim.ProgressQuest(9001, 1, 8)]])
      Sim.Advance(4)
      Check(StepId() == "dp-003", "A moves on once Lunaria is done: the warlock-only step", StepId())
      Check(not SendaHUD.goOn:IsShown(), "no wait line any more")

      Section("ahead/behind by step key, a warlock-only step between")
      Check(Peer("return StepId()") == "dp-004", "B skipped A's class step: on dp-004", Peer("return StepId()"))
      Sim.Advance(3)
      Check(S().Party.StepsApart(DuoMember("Lunaria")) == 0, "A: dp-003 (warlock) vs dp-004 counts 0 shared steps", S().Party.StepsApart(DuoMember("Lunaria")))
      Check(Peer([[return S().Party.StepsApart(DuoMember("Pruebas"))]]) == 0, "B: the same from the other side")
      Sim.Click(SendaHUD.done)
      Sim.Advance(3)
      Check(StepId() == "dp-004", "A on dp-004 after Done", StepId())
      Peer([[Sim.TurnInQuest(9001)]])
      Sim.Advance(3)
      Peer([[Sim.AcceptQuest(9002, { { "Lobos", 5 } })]])
      Sim.Advance(4)
      Check(Peer("return StepId()") == "dp-006", "B on dp-006", Peer("return StepId()"))
      Check(S().Party.StepsApart(DuoMember("Lunaria")) == 2, "A: Lunaria 2 steps ahead", S().Party.StepsApart(DuoMember("Lunaria")))
      Check(Peer([[return S().Party.StepsApart(DuoMember("Pruebas"))]]) == -2, "B: Pruebas 2 steps behind")
      Check(Plain(SendaHUD.duo:GetText()):find("Lunaria va 2 pasos por delante", 1, true) ~= nil, "HUD says 2 steps ahead", SendaHUD.duo:GetText())
      Check(Plain(SendaHUD.duo:GetText()):find("ya la entregó", 1, true) ~= nil, "HUD: she already handed in this step's quest", SendaHUD.duo:GetText())
      local near = S().Party.TheirDoneNear(DuoMember("Lunaria"))
      Check(near[1] == 9001, "Lunaria's done quests near your step: 9001", near[1])

      Section("ask to skip to my step: decline, then accept")
      Peer([[S().Party.RequestSync()]])
      Sim.Advance(1)
      Check(Sim.lastPopup ~= nil and Sim.lastPopup.which == "SENDA_PARTY_SYNC", "A gets the prompt")
      Check(Sim.lastPopup and Sim.lastPopup.text:find("Lunaria te pide que saltes a su paso", 1, true) ~= nil, "prompt text", Sim.lastPopup and Sim.lastPopup.text)
      Sim.DeclinePopup()
      Sim.Advance(1)
      Check(StepId() == "dp-004", "declined: A stays on dp-004", StepId())
      Check(Peer([[for i = #Sim.chat, 1, -1 do if Sim.chat[i]:find("prefiere seguir en su paso", 1, true) then return true end end return false]]), "B hears the decline")
      Sim.Advance(31)
      Peer([[S().Party.RequestSync()]])
      Sim.Advance(1)
      Check(Sim.AcceptPopup(), "A accepts the second request")
      Sim.Advance(2)
      Check(StepId() == "dp-005", "accepted: A jumped to dp-005 (the first step of hers it can do: accept 9002)", StepId())
      Check(Peer([[for i = #Sim.chat, 1, -1 do if Sim.chat[i]:find("ha saltado a tu paso", 1, true) then return true end end return false]]), "B hears the accept")

      Section("/senda pareja")
      local lines = Slash("pareja debug")
      local joined = table.concat(lines, "|")
      Check(joined:find("prefijo Senda registrado: sí", 1, true) ~= nil and joined:find("oídos", 1, true) ~= nil and joined:find("oído Lunaria", 1, true) ~= nil,
        "/senda pareja debug shows prefix, sends and messages heard", joined)
      Slash("pareja")
      Slash("pareja seguir")
      Slash("pareja nada")
      S().UI:ShowPanel(); S().UI:ShowTab("duo"); Sim.Advance(1)
      for _, t in ipairs(Sim.tabs) do if t.key == "duo" and t.refresh then Sim.SafeCall("duo tab", t.refresh) end end

      Section("a 40-quest log splits under 255 bytes and decodes identical")
      for i = 1, 39 do
        local q = 9100 + i
        Sim.AcceptQuest(q, { { "Uno", 15 }, { "Dos", 10 }, { "Tres", 120 } })
        local o = Sim.player.quests[q].objectives
        o[1].have, o[2].have, o[3].have = i % 15, i % 10, (i * 7) % 120
      end
      before = #Sim.addonSent
      Sim.Fire("QUEST_LOG_UPDATE")
      Sim.Advance(4)
      sent = Sim.AddonTexts("Senda", before + 1)
      local deltas, longest = 0, 0
      for _, t in ipairs(sent) do
        if t:match("^1|") then deltas = deltas + 1 end
        longest = math.max(longest, #t)
      end
      local nq = 0
      for _ in pairs(S().Party.ReadLog()) do nq = nq + 1 end
      Check(nq == 40, "A has 40 quests", nq)
      Check(deltas >= 3 and longest <= 255, "split into " .. deltas .. " messages, longest " .. longest .. " bytes")
      Sim.Advance(1)
      Check(Peer([[return DuoLog("Pruebas")]]) == DuoLog(), "B decodes exactly A's log", Peer([[return DuoLog("Pruebas")]]))
      local a, b = S().Party.Encode, S().Party.Decode
      local entries = {}
      for i = 1, 40 do entries[i] = { q = 100000 + i, counts = { { 999, 999 }, { 12, 15 }, { 0, 3 } } } end
      local msgs = a(entries, true, false)
      local back, ok = {}, true
      for i, t in ipairs(msgs) do
        if #t > 255 then ok = false end
        local snap, list = b(t)
        if (i == 1) ~= snap then ok = false end
        for _, e in ipairs(list or {}) do back[#back + 1] = e end
      end
      Check(ok and #back == 40 and back[40].q == 100040 and back[40].counts[3][2] == 3, "Encode/Decode round trip (" .. #msgs .. " messages)")
      Check(#Sim.apiErrors == 0, "no oversized or malformed send")
    `,
  },
  {
    id: 'duo2',
    title: 'Duo sync (two clients): a refused send is retried; Seguir sin él; partner offline 120 s releases the hold',
    char: 'gnome-warlock',
    duo: { char: 'nightelf-druid', name: 'Lunaria' },
    lua: L_`
      Peer("Login()")
      Login()
      DuoGuide()
      Peer("DuoGuide()")
      Sim.AcceptQuest(9001, { { "Jabalíes muertos", 8 } })
      Peer([[Sim.AcceptQuest(9001, { { "Jabalíes muertos", 8 } })]])
      DuoJoin("Lunaria", "DRUID", "NightElf")
      Peer([[DuoJoin("Pruebas", "WARLOCK", "Gnome")]])
      Sim.Advance(12)
      Check(DuoMember("Lunaria") ~= nil and Peer([[return DuoMember("Pruebas") ~= nil]]), "both synced")

      Section("refused send (throttle) is retried")
      local before = #Sim.addonSent
      Sim.addonFault = 2
      Sim.ProgressQuest(9001, 1, 2)
      Sim.Advance(2.5)
      local refused = 0
      for i = before + 1, #Sim.addonSent do
        if Sim.addonSent[i].result == Enum.SendAddonMessageResult.AddonMessageThrottle then refused = refused + 1 end
      end
      Check(refused == 1, "the client refused the delta", refused)
      Check(Peer([[return DuoLog("Pruebas")]]) == "9001:0/8", "B has not got it yet")
      Sim.Advance(8)
      local sent = Sim.AddonTexts("Senda", before + 1)
      Check(#sent == 1 and sent[1] == "1|9001:2/8", "sent once it went through", table.concat(sent, " "))
      Check(Peer([[return DuoLog("Pruebas")]]) == "9001:2/8", "B got it after the retry")
      Check(S().Party.Diag().refused == 2, "two refusals counted", S().Party.Diag().refused)

      Section("Seguir sin él")
      Sim.ProgressQuest(9001, 1, 8)
      Sim.Advance(3)
      Check(StepId() == "dp-002" and SendaHUD.goOn:IsShown(), "held on dp-002", StepId())
      Sim.Click(SendaHUD.goOn)
      Sim.Advance(2)
      Check(StepId() == "dp-003", "'Seguir sin él' lets A go on", StepId())
      Check(not S().Party.HoldsQuest(9001), "the quest is released")

      Section("partner offline: the hold lasts 120 s")
      Sim.Click(SendaHUD.done)
      Sim.TurnInQuest(9001)
      Sim.Advance(2)
      Sim.AcceptQuest(9002, { { "Lobos", 5 } })
      Peer([[Sim.AcceptQuest(9002, { { "Lobos", 5 } })]])
      Sim.Advance(4)
      Check(StepId() == "dp-006", "A on dp-006", StepId())
      Sim.FinishQuestObjectives(9002)
      Sim.Advance(3)
      Check(StepId() == "dp-006" and SendaHUD.goOn:IsShown(), "held: Lunaria needs 0/5", SendaHUD.duoWait:GetText())
      Sim.party[1].offline = true
      Sim.Fire("UNIT_CONNECTION", "party1", false)
      Sim.Advance(60)
      Check(StepId() == "dp-006", "still held 60 s after she went offline", StepId())
      Sim.Advance(62)
      Check(StepId() ~= "dp-006", "released after 120 s offline", StepId())
    `,
  },
  {
    id: 'duo3',
    title: 'Duo sync: nothing sent in a raid or to a party member without Senda (only the hello)',
    char: 'gnome-warlock',
    lua: L_`
      Login()
      Sim.AcceptQuest(9001, { { "Jabalíes muertos", 8 } })
      Section("raid")
      Sim.raid = true
      DuoJoin("Ana", "MAGE", "Human")
      Sim.ProgressQuest(9001, 1, 2)
      Sim.Advance(15)
      Check(#Sim.addonSent == 0, "in a raid nothing is sent", #Sim.addonSent)
      local lines = Slash("pareja")
      Check(table.concat(lines, "|"):find("En banda no se sincroniza nada", 1, true) ~= nil, "/senda pareja says so")
      Section("party member without Senda")
      Sim.raid = false
      Sim.Fire("GROUP_ROSTER_UPDATE")
      Sim.Advance(10)
      Sim.ProgressQuest(9001, 1, 3)
      Sim.Advance(5)
      Sim.Fire("PLAYER_LEVEL_UP", 2, 0, 0, 0, 0, 0, 0, 0, 0)
      S().Engine:Skip()
      Sim.Advance(5)
      local sent = Sim.AddonTexts()
      Check(#sent == 1 and sent[1]:match("^1H|") ~= nil, "only the hello went out", table.concat(sent, " "))
      Check(Sim.addonSent[1].channel == "PARTY", "on the party channel")
      Check(not S().Party.RequestSync(), "no skip request without a partner")
      Check(SendaHUD.duo:GetText() == "" or not SendaHUD.duo:IsShown(), "no duo line on the HUD")
      lines = Slash("pareja debug")
      Check(table.concat(lines, "|"):find("enviados 1", 1, true) ~= nil, "/senda pareja debug counts the hello", table.concat(lines, "|"))
      Section("a second hello only for someone new")
      Sim.party[2] = { name = "Bruno", class = "WARRIOR", race = "Dwarf", level = 1, quests = {} }
      Sim.Fire("GROUP_ROSTER_UPDATE")
      Sim.Advance(6)
      Check(#Sim.AddonTexts() == 2, "one more hello when Bruno joins", #Sim.AddonTexts())
      Sim.Fire("GROUP_ROSTER_UPDATE")
      Sim.Advance(6)
      Check(#Sim.AddonTexts() == 2, "no hello for the same roster")
    `,
  },
  {
    id: 'duo4',
    title: 'Duo sync: "va por delante" discounts the steps either side skipped (2K message)',
    char: 'gnome-warlock',
    duo: { char: 'nightelf-druid', name: 'Lunaria' },
    lua: L_`
      Peer("Login()")
      Login()
      DuoGuide()
      Peer("DuoGuide()")
      DuoJoin("Lunaria", "DRUID", "NightElf")
      Peer([[DuoJoin("Pruebas", "WARLOCK", "Gnome")]])
      Sim.Advance(12)
      Check(DuoMember("Lunaria") ~= nil, "A heard Lunaria")
      Check(StepId() == "dp-001", "A on dp-001", StepId())
      Section("Lunaria jumps ahead to dp-009")
      Peer([[local E = S().Engine
        for i, e in ipairs(E:Steps()) do if e.step.id == "dp-009" then E:JumpTo(i) end end]])
      Sim.Advance(4)
      Check(Peer("return StepId()") == "dp-009", "B on dp-009", Peer("return StepId()"))
      local apart = S().Party.StepsApart(DuoMember("Lunaria"))
      Check(apart == 6, "A: 6 shared steps (1,2,4,5,6,8; dp-003 and dp-007 belong to one class)", apart)
      Section("Lunaria skips quest 9002: its three steps no longer count")
      Peer([[S().Engine:SkipQuestTree(9002)]])
      Sim.Advance(4)
      local m = DuoMember("Lunaria")
      Check(m and m.skipped and m.skipped[9002], "A received her skipped quests (2K)")
      Check(S().Party.StepsApart(m) == 3, "A: 3 steps apart after her skip", S().Party.StepsApart(m))
      Check(Peer([[return S().Party.StepsApart(DuoMember("Pruebas"))]]) == -3, "B: -3 from her side")
      Section("I skip 9001 too: nothing left that both can do")
      S().Engine:SkipQuestTree(9001)
      Sim.Advance(4)
      Check(S().Party.StepsApart(DuoMember("Lunaria")) == 0, "A: 0 shared steps left", S().Party.StepsApart(DuoMember("Lunaria")))
      Section("wire format")
      local P = S().Party
      Check(P.EncodeSkipped({ 30, 5, 5 }) == "2K|5,5,30" or P.EncodeSkipped({ 30, 5 }) == "2K|5,30", "encode sorted")
      local d = P.DecodeSkipped("2K|5,30")
      Check(d and d[5] and d[30], "decode")
      Check(P.DecodeSkipped("2K|5,x") == nil and P.DecodeSkipped("2K|0") == nil, "malformed rejected")
      local many = {}
      for i = 1, 100 do many[i] = 100000 + i end
      Check(#P.EncodeSkipped(many) <= 255, "long list fits in 255 bytes")
      Check(#Sim.apiErrors == 0, "no malformed send")
    `,
  },
  {
    id: 'hudwhy',
    title: 'HUD: the why line of a step (option on by default), its own block, no overlap, tooltip',
    char: 'gnome-warlock',
    lua: L_`
      Login()
      local G, E, HUD = S().Guides, S().Engine, S().HUD
      Sim.questCache[179] = true
      G:RegisterSection({ id = "sim-why", title = "Por qué", levels = { 1, 2 }, map = 1426, steps = {
        { id = "sim-why-001", ["do"] = "accept", quest = 179, npc = 658, at = { 1426, 29.9, 71.2 },
          text = "Coge la misión.", tip = "Un consejo.", status = "unverified",
          why = "+3.144 XP · ~2,2 min · desbloquea «{quest:179}» y 3 más" },
        { id = "sim-why-002", ["do"] = "note", text = "Sin motivo.", status = "unverified" } } })
      G:RegisterGuide({ id = "sim-why", title = "Por qué", sections = { "sim-why" }, order = -1 })
      E:SetGuide("sim-why", true)
      Sim.Advance(1)
      Check(S().Options:Get("hudWhy") == true, "option on by default")
      local f = SendaHUD
      local why = Plain(f.why:GetText() or "")
      Check(f.why:IsShown() and why:find("+3.144 XP · ~2,2 min", 1, true) ~= nil, "why line shown", why)
      Check(not why:find("{quest", 1, true), "tokens resolved", why)
      Check(not Plain(f.text:GetText()):find("XP", 1, true), "it is not in the step text block")
      Check(f.extraLine == nil or HUD.extraLine == nil, "the extra-line slot is untouched", tostring(HUD.extraLine))
      local function top(fs) local _, _, _, _, y = fs:GetPoint(1); return y end
      Check(f.tip:IsShown() and top(f.tip) < top(f.why) - f.why:GetStringHeight() + 0.5,
        "tip sits below the why line (no overlap)", tostring(top(f.tip)) .. " vs " .. tostring(top(f.why)))
      Check(top(f.why) <= -(28 + 12 + f.text:GetStringHeight()), "why starts under the step text", top(f.why))
      Check(HUD.hitTip ~= nil and Plain(HUD.hitBody):find("3.144 XP", 1, true) ~= nil, "right-click tooltip carries the why", tostring(HUD.hitBody))
      Section("option off")
      S().Options:Set("hudWhy", false)
      Sim.Advance(1)
      Check(not f.why:IsShown(), "hidden with the option off")
      Check(not (HUD.hitBody or ""):find("3.144", 1, true), "tooltip without it too", tostring(HUD.hitBody))
      S().Options:Set("hudWhy", true)
      Section("step without why")
      E:Skip()
      Sim.Advance(1)
      Check(StepId() == "sim-why-002" and not f.why:IsShown(), "no why, no line", StepId())
      Check(#Sim.apiErrors == 0, "no API errors")
    `,
  },
];

scenarios.push(...require('./scenarios_rec').scenarios);
scenarios.push(...require('./scenarios_nav').scenarios);
scenarios.push(...require('./scenarios_travel').scenarios);
scenarios.push(...require('./scenarios_rares').scenarios);
scenarios.push(...require('./scenarios_audit').scenarios);
scenarios.push(...require('./scenarios_dungeons').scenarios);

// ---------------------------------------------------------------------------
// Runner
// ---------------------------------------------------------------------------

// Two-player mode (scenario `duo: { char, name }`): a second Lua state is the partner's client. Every
// C_ChatInfo.SendAddonMessage of one reaches the other as CHAT_MSG_ADDON BUS_LATENCY seconds later (in
// order). The main state drives the clock: each of its frames first advances the partner's clock to the
// same time. The scenario runs in the main state; Peer("lua code") runs code in the partner's state and
// returns its first result (string, number, boolean or nil). The partner's own errors fail the scenario.
const BUS_LATENCY = 0.1;

function bootState(L, sc, carry, char, name) {
  for (const f of MOCK_FILES) {
    const err = runFile(L, f);
    if (err) return 'mock ' + path.basename(f) + ': ' + err;
  }
  let err = runFile(L, SCENARIO_HELPERS);
  if (err) return 'scenario.lua: ' + err;
  const saved = sc.wipeSaved ? '' : carry.saved || ''; // wipeSaved: the SavedVariables were lost
  const prelude = `
    SIM_ROOT = ${JSON.stringify(ADDON_ROOT)}
    Sim.verbose = ${VERBOSE}
    SIM_EXPECT_STEP = ${JSON.stringify(carry.expectStep || null)}
    SIM_EXPECT_DONE = ${Number(carry.expectDone || 0)}
    Sim.locale = ${JSON.stringify(sc.locale || 'esES')}
    -- The preset itself (scenarios may change it before Login()); a copy only to give it another name.
    local cfg = Sim.CHARS[${JSON.stringify(char)}]
    if ${JSON.stringify(name || null)} then
      local named = {}
      for k, v in pairs(cfg) do named[k] = v end
      named.name = ${JSON.stringify(name || null)}
      cfg = named
    end
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
  if (err) return 'prelude: ' + err;
  return null;
}

// Pushes a JS value onto a Lua stack (string, number, boolean; anything else as nil).
function pushValue(L, v) {
  if (typeof v === 'string') pushJsString(L, v);
  else if (typeof v === 'number') lua.lua_pushnumber(L, v);
  else if (typeof v === 'boolean') lua.lua_pushboolean(L, v);
  else lua.lua_pushnil(L);
}

// Reads the value at `idx` of a Lua stack as a JS value (tables and functions become their type name).
function readValue(L, idx) {
  const t = lua.lua_type(L, idx);
  if (t === lua.LUA_TNUMBER) return lua.lua_tonumber(L, idx);
  if (t === lua.LUA_TSTRING) return lua.lua_tojsstring(L, idx);
  if (t === lua.LUA_TBOOLEAN) return lua.lua_toboolean(L, idx);
  if (t === lua.LUA_TNIL || t === lua.LUA_TNONE) return null;
  return '<' + to_jsstring(lua.lua_typename(L, t)) + '>';
}

// Wires the message bus between two states (send, receive) and, on the main one, Peer() and the clock.
function wireBus(A, B) {
  const queues = new Map([[A, []], [B, []]]);
  for (const [self, other] of [[A, B], [B, A]]) {
    lua.lua_pushjsfunction(self, (L) => {
      queues.get(other).push({
        prefix: lua.lua_tojsstring(L, 1), text: lua.lua_tojsstring(L, 2), channel: lua.lua_tojsstring(L, 3),
        due: lua.lua_tonumber(L, 4) + BUS_LATENCY, sender: lua.lua_tojsstring(L, 5),
      });
      return 0;
    });
    lua.lua_setglobal(self, to_luastring('__busSend'));
    lua.lua_pushjsfunction(self, (L) => {
      const now = lua.lua_tonumber(L, 1);
      const q = queues.get(self);
      if (!q.length || q[0].due > now + 1e-9) return 0;
      const m = q.shift();
      for (const v of [m.prefix, m.text, m.channel, m.sender]) pushJsString(L, v);
      return 4;
    });
    lua.lua_setglobal(self, to_luastring('__busRecv'));
  }
  lua.lua_pushjsfunction(A, (L) => {
    const t = lua.lua_tonumber(L, 1);
    const err = run(B, `Sim.AdvanceTo(${t})`, '=peer clock');
    if (err) run(B, `Sim.RecordError(${JSON.stringify(err)}, "peer clock")`, '=x');
    return 0;
  });
  lua.lua_setglobal(A, to_luastring('__peerSync'));
  lua.lua_pushjsfunction(A, (L) => {
    const code = lua.lua_tojsstring(L, 1);
    lua.lua_getglobal(B, to_luastring('debug'));
    lua.lua_getfield(B, -1, to_luastring('traceback'));
    lua.lua_remove(B, -2);
    const base = lua.lua_gettop(B);
    let st = lauxlib.luaL_loadbuffer(B, to_luastring(code), null, to_luastring('=peer'));
    if (st === lua.LUA_OK) st = lua.lua_pcall(B, 0, 1, base);
    if (st !== lua.LUA_OK) {
      const err = lua.lua_tojsstring(B, -1);
      lua.lua_settop(B, base - 1);
      lua.lua_pushnil(L);
      pushJsString(L, err);
      return 2;
    }
    const v = readValue(B, -1);
    lua.lua_settop(B, base - 1);
    pushValue(L, v);
    return 1;
  });
  lua.lua_setglobal(A, to_luastring('__peer'));
  const err = run(B, 'local out = Sim.Out; Sim.Out = function(s) out("  [peer]" .. tostring(s)) end', '=peer out');
  if (err) return err;
  return run(A, `
    table.insert(Sim.frameHooks, 1, function() __peerSync(Sim.time) end)
    function Peer(code)
      local v, err = __peer(code)
      if err then Sim.RecordError(err, "Peer()") end
      return v
    end
  `, '=bus');
}

function runScenario(sc, carry) {
  const report = {};
  const L = newState(report);
  let err = bootState(L, sc, carry, sc.char, sc.name);
  if (err) return { report, fatal: err };
  let peerReport = null;
  let B = null;
  if (sc.duo) {
    peerReport = {};
    B = newState(peerReport);
    err = bootState(B, sc, {}, sc.duo.char, sc.duo.name);
    if (err) return { report, fatal: 'peer ' + err };
    err = wireBus(L, B);
    if (err) return { report, fatal: 'bus: ' + err };
  }
  err = run(L, sc.lua, '=scenario ' + sc.id);
  if (err) {
    run(L, `Sim.RecordError(${JSON.stringify(err)}, "scenario body")`, '=x');
  }
  err = run(L, 'Sim.Finish()', '=finish');
  if (err) return { report, fatal: 'finish: ' + err };
  if (B) {
    err = run(B, 'Sim.Finish()', '=peer finish');
    if (err) return { report, fatal: 'peer finish: ' + err };
    report.failures = (report.failures || 0) + (peerReport.failures || 0);
    report.checks = (report.checks || 0) + (peerReport.checks || 0);
    if (peerReport.failureText) {
      const peerText = peerReport.failureText.split('\n').map((l) => 'peer: ' + l).join('\n');
      report.failureText = report.failureText ? report.failureText + '\n' + peerText : peerText;
    }
  }
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
    let failures = fatal ? 1 : report.failures || 0;
    if (sc.post && !fatal) {
      // node-side checks (they run the real tools on what the sim saved)
      const extra = [];
      let checks = 0;
      const ctx = {
        check(cond, msg, detail) {
          checks++;
          console.log(`  ${cond ? 'ok  ' : 'FAIL'} ${msg}${!cond && detail ? ' — ' + detail : ''}`);
          if (!cond) extra.push(msg + (detail ? ' — ' + detail : ''));
          return cond;
        },
      };
      const res = sc.post(report, carry, ctx) || {};
      if (res.warn) console.log('  WARN ' + res.warn);
      for (const f of res.fail || []) { console.log('  FAIL ' + f); extra.push(f); }
      failures += extra.length;
      report.checks = (report.checks || 0) + checks;
    }
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

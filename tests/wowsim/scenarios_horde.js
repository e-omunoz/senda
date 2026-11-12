'use strict';
// Scenarios of the Horde routes (plan, phase 4): one guide per Horde race (orc-horde, troll-horde, tauren-horde,
// undead-horde, skyborne-horde), class-neutral, with the shared Horde route data/shared/h*.toml. Loaded by run.js.
// The files of Horde guides only register for Horde characters (tools/build.py, faction gate): Alliance
// characters must not see them at all.

const L_ = String.raw;

// Checks shared by the play-through scenarios: guide auto-selected, starts at the race start, and plays to the end.
function playThrough(guide, first, cls) {
  return L_`
      Login()
      local E, G = S().Engine, S().Guides
      Check(E:GuideId() == "${guide}", "guide ${guide} auto-selected", E:GuideId())
      Check(StepId() == "${first}", "starts at the first step of the race start", StepId())
      -- class-neutral guide: only this class's training steps are resolved
      local mine, other = 0, 0
      for _, e in ipairs(E:Steps()) do
        local f = e.step["if"]
        if e.step["do"] == "train" then
          if f and f.class and f.class[1] == "${cls}" then mine = mine + 1 else other = other + 1 end
        end
      end
      Check(mine > 0, "the guide trains this class (${cls}): " .. mine .. " train steps")
      Check(other == 0, "no training step of another class is resolved", other)
      local r = AutoPlay(6000)
      Sim.Out(string.format("    auto %d, manual %d, stuck %d", r.auto, r.manual, #r.stuck))
      if #r.stuck > 0 then Sim.Out("    stuck: " .. table.concat(r.stuck, ", ")) end
      Check(E:IsFinished(), "guide finished", StepId())
      Check(#r.stuck == 0, "no auto-detectable step got stuck", table.concat(r.stuck, ", "))
      Check(Sim.player.level >= 60, "the route reaches level 60", Sim.player.level)
  `;
}

const scenarios = [
  {
    id: 'horde-a',
    title: 'Orc warrior level 1 logs in: orc-horde auto-selected, Horde data registered, Alliance data intact',
    char: 'orc-warrior',
    lua: L_`
      Login()
      local E, G = S().Engine, S().Guides
      Check(E:GuideId() == "orc-horde", "guide orc-horde auto-selected", E:GuideId())
      Check(StepId() == "orc-001", "first step is orc-001 (Kaltunk, Valley of Trials)", StepId())
      Check(SendaHUD and SendaHUD:IsShown(), "HUD is shown")
      Check(Plain(HudTitle()):find("Acepta", 1, true) ~= nil, "HUD title shows the step type", HudTitle())
      local t, src = ArrowTarget()
      Check(src == "guide" and t and t.map == 1411, "arrow follows the guide step in Durotar", src)
      local found = false
      for _, l in ipairs(Sim.chat) do if l:find("Orco 1-60", 1, true) then found = true end end
      Check(found, "chat announces the selected guide")
      Section("Horde guides as the engine sees them")
      local ids = { "orc-horde", "troll-horde", "tauren-horde", "undead-horde", "skyborne-horde" }
      for _, id in ipairs(ids) do
        local g = G:Get(id)
        Check(g ~= nil and g.faction == "Horde", id .. " registered for a Horde character")
        if g then
          Check(#G:SectionsOf(id) == #g.sections, id .. ": every listed section is registered", #G:SectionsOf(id) .. "/" .. #g.sections)
          local seen, dup, badAt, steps = {}, {}, {}, 0
          for _, sec in ipairs(G:SectionsOf(id)) do
            for _, st in ipairs(sec.steps) do
              steps = steps + 1
              if seen[st.id] then dup[#dup + 1] = st.id end
              seen[st.id] = true
              local at = st.at
              if at and not (type(at[1]) == "number" and at[2] and at[3] and at[2] >= 0 and at[2] <= 100 and at[3] >= 0 and at[3] <= 100) then
                badAt[#badAt + 1] = st.id
              end
            end
          end
          Check(#dup == 0, id .. ": step ids are unique", table.concat(dup, ", "))
          Check(#badAt == 0, id .. ": every 'at' is [uiMapID, 0-100, 0-100]", table.concat(badAt, ", "))
          Check(steps > 2000, id .. ": 1-60 route (" .. steps .. " steps)")
        end
      end
      local list = G:ForPlayer()
      Check(list[1] and list[1].id == "orc-horde", "best guide for an orc is orc-horde", list[1] and list[1].id)
      for _, g in ipairs(list) do
        Check(g.faction ~= "Alliance", "no Alliance guide offered to a Horde character: " .. g.id)
      end
      Check(G:Get("gnome-warlock") ~= nil, "Alliance guides still load (their files have no gate)")
      Check(G:Score(G:Get("gnome-warlock")) == 0, "an Alliance guide scores 0 for a Horde character")
      Slash("guide troll-horde")
      Check(E:GuideId() == "troll-horde", "another Horde guide can be chosen by hand", E:GuideId())
      Slash("guide orc-horde")
      Check(E:GuideId() == "orc-horde", "and back to orc-horde", E:GuideId())
      RunAllTabs()
      Check(HoverAll() > 0, "tooltips of the visible widgets run")
    `,
  },
  {
    id: 'horde-b',
    title: 'Orc warrior: accept, turn-in, warrior training (spells from the trainer list) and the level gate',
    char: 'orc-warrior',
    lua: L_`
      Login()
      local E = S().Engine
      Section("accept and turn-in at Kaltunk and Gornek")
      local q = E:CurrentStep().quest
      Sim.AcceptQuest(q, { { "Habla con Gornek", 1 } })
      Sim.Advance(3)
      Check(StepId() ~= "orc-001", "accepting the quest advances", StepId())
      Section("warrior training step")
      local train
      for i, e in ipairs(E:Steps()) do
        if e.step["do"] == "train" and S().Conditions:Check(e.step, {}) ~= true then train = { i = i, e = e } break end
      end
      Check(train ~= nil, "a training step is resolved for the warrior")
      if train then
        local st = train.e.step
        Check(st["if"] and st["if"].class and st["if"].class[1] == "WARRIOR", "it is the warrior's", st.id)
        Check(type(st.spells) == "table" and #st.spells > 0, "it lists the spells to learn", st.spells and #st.spells)
        Check(st.npc ~= nil and st.at ~= nil, "it points at a warrior trainer", st.npc)
        Check(type(st.reqlevel) == "number", "it carries the level the trainer asks for", st.reqlevel)
        -- a training step waits for the level the trainer asks for (Engine:WaitLevel): get there first
        Check(E:WaitLevel(train.e) == st.reqlevel or Sim.player.level >= st.reqlevel, "below its level the step waits", E:WaitLevel(train.e))
        Sim.player.level = st.reqlevel
        Sim.Fire("PLAYER_LEVEL_UP", st.reqlevel, 0, 0, 0, 0, 0, 0, 0, 0)
        Sim.Advance(1)
        Check(E:WaitLevel(train.e) == nil, "at its level it no longer waits")
        for _ = 1, 40 do
          if StepId() == st.id then break end
          Sim.Click(SendaHUD.done)
          Sim.Advance(0.5)
        end
        Check(StepId() == st.id, "reached the training step with Done", StepId())
        for _, id in ipairs(st.spells) do Sim.LearnSpell(id) end
        Sim.Advance(3)
        Check(StepId() ~= st.id, "learning the spells completes the step on its own", StepId())
      end
      Section("text tokens resolve (no raw {kind:id} left in the HUD)")
      for _ = 1, 12 do
        local txt = Plain(HudText()) .. " " .. Plain(HudTitle())
        Check(not txt:find("{%l+:%d+}"), "HUD text has no raw token: " .. tostring(StepId()), txt)
        Sim.Click(SendaHUD.done)
        Sim.Advance(0.5)
      end
    `,
  },
  {
    id: 'horde-c',
    title: 'Alliance characters are untouched: no Horde guide registered, auto-selection and lists as before',
    char: 'gnome-warlock',
    lua: L_`
      Login()
      local E, G = S().Engine, S().Guides
      Check(E:GuideId() == "gnome-warlock", "gnome warlock still gets gnome-warlock", E:GuideId())
      Check(StepId() == "coldridge-001", "first step unchanged", StepId())
      for _, id in ipairs({ "orc-horde", "troll-horde", "tauren-horde", "undead-horde", "skyborne-horde" }) do
        Check(G:Get(id) == nil, id .. " not registered for an Alliance character")
      end
      local hs = 0
      for _, sec in ipairs(G:AllSections()) do if sec.id:match("^h%d%d%-") then hs = hs + 1 end end
      Check(hs == 0, "no shared Horde section registered", hs)
      for _, g in ipairs(G:List()) do
        Check(g.faction ~= "Horde", "guide list has no Horde guide: " .. g.id)
      end
      Slash("guide orc-horde")
      Check(E:GuideId() == "gnome-warlock", "/senda guide orc-horde does nothing for the Alliance", E:GuideId())
    `,
  },
  {
    id: 'horde-d',
    title: 'Play the whole orc-horde guide as an orc warrior: every auto step completes on its own',
    char: 'orc-warrior',
    lua: playThrough('orc-horde', 'orc-001', 'WARRIOR'),
  },
  {
    id: 'horde-e',
    title: 'Play the whole undead-horde guide as an undead mage: every auto step completes on its own',
    char: 'undead-mage',
    lua: playThrough('undead-horde', 'und-001', 'MAGE'),
  },
  {
    id: 'horde-f',
    title: 'Play the whole tauren-horde guide as a tauren druid: every auto step completes on its own',
    char: 'tauren-druid',
    lua: playThrough('tauren-horde', 'tau-001', 'DRUID'),
  },
  {
    id: 'horde-g',
    title: 'Play the whole troll-horde guide as a troll shaman: every auto step completes on its own',
    char: 'troll-shaman',
    lua: playThrough('troll-horde', 'trl-001', 'SHAMAN'),
  },
  {
    id: 'horde-h',
    title: 'Play the whole skyborne-horde guide as a Skyborne hunter: every auto step completes on its own',
    char: 'skyborne-hunter',
    lua: playThrough('skyborne-horde', 'sky-001', 'HUNTER'),
  },
];

module.exports = { scenarios };

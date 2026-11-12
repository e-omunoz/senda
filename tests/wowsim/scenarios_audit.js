'use strict';
// Scenarios of the data audit (tools/audit_guides.py, docs/AUDIT.md): breadcrumbs from Guides/Followups.lua
// (RegisterBreadcrumbs) and the guide fixes it led to, played in the real addon. Loaded by run.js.

const L_ = String.raw;

const PRELUDE = L_`
  -- On this character's route at all (the guide is resolved with its race and class filters).
  function Applicable(id) return StepIndexOf(id) ~= nil end
  function LevelTo(n)
    Sim.player.level = n
    Sim.Fire("PLAYER_LEVEL_UP", n, 0, 0, 0, 0, 0, 0, 0, 0)
    Sim.Advance(1)
  end
  function JumpToStep(id)
    local i = StepIndexOf(id)
    Check(i ~= nil, "step " .. id .. " exists")
    S().Engine:JumpTo(i)
    Sim.Advance(1)
  end
  function Skipped(id)
    local i = StepIndexOf(id)
    return i ~= nil and S().Engine:StepSkipped(S().Engine:Entry(i)) and true or false
  end
`;

const scenarios = [
  {
    id: 'audit-crumb-skip',
    title: 'Breadcrumbs: skipping Lago\'s errand (1717) does not skip Devourer of Souls (1716) or the succubus chain',
    char: 'gnome-warlock',
    lua: PRELUDE + L_`
      Login()
      Sim.Advance(2)
      local E, G = S().Engine, S().Guides
      LevelTo(21)
      Check(G:Followups(1717) == nil, "1717 has no dependents (it only leads to 1716)", tostring(G:Followups(1717)))
      local leads = G:BreadcrumbTargets(1717)
      Check(leads and leads[1] == 1716, "1717 is a breadcrumb for 1716", leads and table.concat(leads, ","))
      local info = E:SkipQuestTree(1717)
      Check(info and #info.list == 1 and info.list[1] == 1717, "skipping 1717 skips only 1717",
        info and table.concat(info.list, ","))
      Sim.Advance(1)
      Check(Skipped("wl-succubus-001") and Skipped("wl-succubus-002"), "the errand and its turn-in are skipped")
      Check(not Skipped("wl-succubus-003"), "Gakin's Devourer of Souls stays on the route")
      Check(not Skipped("wl-succubus-007"), "the succubus chain stays on the route")
      E:UndoSkip(info)
      Sim.Advance(1)
      Check(not Skipped("wl-succubus-001"), "undo brings the errand back")
      Check(#Sim.errors == 0, "no Lua errors")
    `,
  },
  {
    id: 'audit-crumb-held',
    title: 'Breadcrumbs: with the errand (1717) still in the log, its turn-in to Gakin is not passed when 1716 is taken',
    char: 'gnome-warlock',
    lua: PRELUDE + L_`
      Login()
      Sim.Advance(2)
      LevelTo(21)
      JumpToStep("wl-succubus-001")
      Check(StepId() == "wl-succubus-001", "Lago's errand is current", StepId())
      Sim.AcceptQuest(1717)
      Sim.Advance(1)
      Check(StepId() == "wl-succubus-002", "after taking the errand: hand it to Gakin", StepId())
      Sim.AcceptQuest(1716)
      Sim.Advance(1)
      Check(StepId() == "wl-succubus-002", "1716 taken while 1717 is in the log: the turn-in still waits", StepId())
      Sim.TurnInQuest(1717)
      Sim.Advance(1)
      Check(StepId() ~= "wl-succubus-002" and StepId() ~= "wl-succubus-003",
        "1717 handed in, 1716 already in the log: the route moves on", StepId())
      Check(#Sim.errors == 0, "no Lua errors")
    `,
  },
  {
    id: 'audit-voidwalker-crumb',
    title: 'Breadcrumbs: The Slaughtered Lamb (1715, Lago) is passed once Surena Caledon (1688) is in the log',
    char: 'gnome-warlock',
    lua: PRELUDE + L_`
      Login()
      Sim.Advance(2)
      LevelTo(10)
      local leads = S().Guides:BreadcrumbTargets(1715)
      Check(leads and leads[1] == 1688, "1715 is a breadcrumb for 1688", leads and table.concat(leads, ","))
      JumpToStep("wl-voidwalker-001")
      Check(StepId() == "wl-voidwalker-001", "Lago's quest is current", StepId())
      Sim.AcceptQuest(1688)
      Sim.Advance(1)
      local cur = StepId()
      Check(cur ~= "wl-voidwalker-001" and cur ~= "wl-voidwalker-005",
        "with 1688 in the log, Lago's quest and its turn-in are passed", cur)
      local text = S().Engine:Entry(StepIndexOf("wl-voidwalker-001")).step.text
      Check(text:find("a ras del suelo", 1, true) ~= nil, "the step says Lago stands at the cavern's floor", text)
      Check(#Sim.errors == 0, "no Lua errors")
    `,
  },
  {
    id: 'audit-farsen-gnome',
    title: 'Loch Modan: a gnome who did Farsen in Dun Morogh is not sent back to him; Kadrell gets the Stout',
    char: 'gnome-warlock',
    lua: PRELUDE + L_`
      Login()
      Sim.Advance(2)
      for _, id in ipairs({ "a12lm-002", "a12lm-003", "a12lm-004", "a12lm-005", "a12lm-006", "a12lm-008" }) do
        Check(not Applicable(id), id .. " (Farsen again) is not for a gnome")
      end
      Check(Applicable("a12lm-007") and Applicable("a12lm-009"), "the Dark Iron map is still for a gnome")
      Check(Applicable("a12lm-020a"), "a gnome hands Stout to Kadrell (414) in Thelsamar")
      local st = S().Engine:Entry(StepIndexOf("a12lm-020a")).step
      Check(st.quest == 414 and st.npc == 1340 and st.at[2] == 34.2 and st.at[3] == 47.8,
        "the turn-in points at Kadrell's forever-db spawn", st.at and (st.at[2] .. "," .. st.at[3]))
      Check(#Sim.errors == 0, "no Lua errors")
    `,
  },
  {
    id: 'audit-farsen-human',
    title: 'Loch Modan: a human still does Farsen\'s chain in a12 and has no Stout to hand in',
    char: 'human-mage',
    lua: PRELUDE + L_`
      Login()
      Sim.Advance(2)
      Check(Applicable("a12lm-002") and Applicable("a12lm-008"), "Farsen's chain is on the human route")
      Check(not Applicable("a12lm-020a"), "no Stout to Kadrell for a human")
      Check(#Sim.errors == 0, "no Lua errors")
    `,
  },
  {
    id: 'audit-library-book',
    title: 'Mage library: the book is looted at Azora\'s tower, then Garion Wendell gives and takes its quest',
    char: 'human-mage',
    lua: PRELUDE + L_`
      Login()
      Sim.Advance(2)
      LevelTo(20)
      JumpToStep("mg-20-library-001")
      local st = S().Engine:CurrentStep()
      Check(st and st["do"] == "loot" and st.item == 203755, "first step: loot the Research Journal", st and st["do"])
      Sim.AddItem(203755, 1)
      Sim.Fire("BAG_UPDATE_DELAYED")
      Sim.Advance(1)
      Check(StepId() == "mg-20-library-001b", "with the book in the bags: take its quest from Garion", StepId())
      Check(S().Engine:CurrentStep().npc == 211033, "the accept step names Garion Wendell")
      Sim.AcceptQuest(79092)
      Sim.Advance(1)
      Check(StepId() == "mg-20-library-002", "then hand the book in", StepId())
      Check(#Sim.errors == 0, "no Lua errors")
    `,
  },
  {
    id: 'audit-cat-spirit',
    title: 'Druid cat form: the Great Cat Spirit steps point at its forever-db spawn (Moonglade 54.5, 75.0)',
    char: 'nightelf-druid',
    lua: PRELUDE + L_`
      Login()
      Sim.Advance(2)
      for _, id in ipairs({ "dr-20-cat-005", "dr-20-cat-006", "dr-20-cat-009", "dr-20-cat-010" }) do
        local i = StepIndexOf(id)
        local at = i and S().Engine:Entry(i).step.at
        Check(at and at[1] == 1450 and at[2] == 54.5 and at[3] == 75.0, id .. " at the spawn",
          at and (at[1] .. "," .. at[2] .. "," .. at[3]))
      end
      Check(#Sim.errors == 0, "no Lua errors")
    `,
  },
];

module.exports = { scenarios };

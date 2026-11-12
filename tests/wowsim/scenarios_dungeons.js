'use strict';
// Scenarios of the dungeon journal (addon/Senda/Modules/Dungeons.lua + Data/Dungeons.lua compiled by tools/build.py
// from data/dungeons/): the tab opens and decodes lazily, the quest list marks the guide's quests, the arrow goes to
// the entrance / meeting stone (and the travel planner takes it), the loot list fits the class and build (druid
// cat/feral, warlock cloth caster, mage frost caster), and the HUD's dungeon step text opens the journal.
// Loaded by run.js.

const L_ = String.raw;

const SETUP = L_`
  function DG() return S().Modules.Dungeons end
  function SetLevel(n)
    Sim.player.level = n
    Sim.Fire("PLAYER_LEVEL_UP", n, 0, 0, 0, 0, 0, 0, 0, 0)
    Sim.Advance(0.2)
  end
  function OpenJournal(key)
    DG().Open(key)
    for _ = 1, 40 do
      if DG().Ready() then break end
      Sim.Advance(0.1)
    end
    Sim.Advance(0.5)
  end
  -- Rows of the shown doc: kind = "quest" | "loot" (by the field the module sets on them).
  function Rows(kind)
    local _, nodes = DG().Shown()
    local out = {}
    for _, n in ipairs(nodes or {}) do
      if n.t == "row" and ((kind == "quest" and n.quest) or (kind == "loot" and n.lootItem)) then out[#out + 1] = n end
    end
    return out
  end
  function Button(label)
    local _, nodes = DG().Shown()
    for _, n in ipairs(nodes or {}) do if n.t == "btn" and n.label == label then return n end end
  end
  function Has(stats, ...)
    for _, k in ipairs({ ... }) do if (stats[k] or 0) > 0 then return true end end
    return false
  end
`;

const scenarios = [
  {
    id: 'dungeons-tab',
    title: 'Dungeon journal: the tab opens, decodes lazily out of combat, lists the Alliance dungeons and marks the guide quests',
    char: 'gnome-warlock',
    lua: SETUP + L_`
      Login()
      Sim.Advance(3)
      local D = DG()
      Check(D ~= nil, "Senda.Modules.Dungeons exists")
      Check(S().DungeonsData ~= nil and S().DungeonsData.schema == 1, "Data/Dungeons.lua is loaded")
      Check(not D.Ready(), "nothing decoded at login (lazy)")
      Check(D.ForStep({ ["do"] = "dungeon", id = "a21dm-022" }) == "deadmines", "the guide's Deadmines step maps to its card")
      Check(D.ForStep({ ["do"] = "goto", id = "a21dm-022" }) == nil, "only dungeon steps map")

      Section("no decoding in combat")
      Sim.player.combat = true
      Sim.Fire("PLAYER_REGEN_DISABLED")
      D.Load()
      Sim.Advance(1)
      Check(not D.Ready(), "still not decoded while in combat")
      Sim.player.combat = false
      Sim.Fire("PLAYER_REGEN_ENABLED")
      for _ = 1, 30 do if D.Ready() then break end; Sim.Advance(0.05) end
      Check(D.Ready(), "decoded after combat, in slices")

      Section("list")
      local list = D.List()
      local keys = {}
      for _, dg in ipairs(list) do keys[dg.key] = dg end
      Check(#list >= 20 and keys.deadmines and keys["wailing-caverns"] and keys["blackfathom-deeps"] and keys["stormwind-stockade"]
        and keys.gnomeregan and keys["scarlet-monastery"] and keys["razorfen-kraul"] and keys["razorfen-downs"] and keys.uldaman
        and keys.zulfarrak and keys.maraudon and keys["sunken-temple"] and keys["blackrock-depths"] and keys["dire-maul"]
        and keys.scholomance and keys.stratholme, "every priority dungeon is listed", #list)
      Check(keys["ragefire-chasm"] == nil, "Ragefire Chasm (Horde finder) is not listed for the Alliance")
      local prev = 0
      local sorted = true
      for _, dg in ipairs(list) do
        local r = dg.rec or dg.entry or 99
        if r < prev then sorted = false end
        prev = r
      end
      Check(sorted, "sorted by recommended level")
      local dm = keys.deadmines
      Check(dm.entry == 10 and dm.rec == 16 and dm.entrance and dm.entrance.map == 1436, "Deadmines: entry 10, recommended 16, entrance in Westfall",
        tostring(dm.entry) .. "/" .. tostring(dm.rec))
      Check(dm.stone ~= nil and dm.stone.map == 1436, "Deadmines has its meeting stone")
      Check(#dm.bosses >= 6, "Deadmines bosses", #dm.bosses)
      Check(D.Name(dm) == "Las Minas de la Muerte", "name from the client (C_Map.GetAreaInfo)", D.Name(dm))
      Check(D.Name(keys.gnomeregan) == "Gnomeregan", "name from Locale.lua when the client has none", D.Name(keys.gnomeregan))
      Check(D.LevelText(dm):find("16", 1, true) ~= nil, "level text", D.LevelText(dm))
      local raw = D.LoadNow()
      local mp5, n = false, 0
      for _, items in pairs(raw.loot) do
        for _, e in ipairs(items) do
          n = n + 1
          if (e.stats.MP5 or 0) > 0 then mp5 = true end
        end
      end
      Check(n > 300 and mp5, "loot decoded with every stat key (MP5 too)", n)

      Section("tab")
      SetLevel(20)
      OpenJournal("deadmines")
      Check(SendaMainFrame:IsShown(), "panel shown")
      local key, nodes = D.Shown()
      Check(key == "deadmines" and nodes and nodes[1].t == "h1", "the journal shows the Deadmines card", key)
      local qrows = Rows("quest")
      Check(#qrows >= 5, "Deadmines quests for a gnome", #qrows)
      local byId = {}
      for _, r in ipairs(qrows) do byId[r.quest] = r end
      Check(byId[166] and Plain(byId[166].right):find("en tu guía", 1, true), "«The Defias Brotherhood» (166) is marked as in your guide", byId[166] and byId[166].right)
      local inGuideFirst = true
      local seenOther = false
      for _, r in ipairs(qrows) do
        local g = Plain(r.right or ""):find("en tu guía", 1, true) ~= nil
        if not g then seenOther = true elseif seenOther then inGuideFirst = false end
      end
      Check(inGuideFirst, "guide quests are listed first")
      local rows = D.Quests("deadmines")
      local marked = 0
      local inGuide = D.GuideQuests()
      for _, r in ipairs(rows) do
        if r.inGuide then marked = marked + 1 end
        Check(r.inGuide == (inGuide[r.id] == true), "quest " .. r.id .. " marked exactly when the guide has it")
      end
      Check(marked >= 4, "several Deadmines quests are in the warlock guide", marked)
      Section("a done quest and a quest in the log")
      Sim.player.completed[166] = true
      Sim.AcceptQuest(214, { { "Objetivo", 1 } })
      Sim.Advance(0.6)
      local st = {}
      for _, r in ipairs(D.Quests("deadmines")) do st[r.id] = r end
      Check(st[166] and st[166].done, "166 shows as done")
      Check(st[214] and st[214].inLog, "214 shows as in your log")

      Section("warlock: cloth caster loot")
      local loot = D.Loot("deadmines")
      Check(#loot > 0, "Deadmines has loot for an affliction warlock", #loot)
      local okAll = true
      local bad
      for _, it in ipairs(loot) do
        local e = it.e
        if e.class == 4 and e.sub >= 2 and e.sub <= 4 then okAll = false; bad = e.id end
        if e.class == 2 and not (e.sub == 7 or e.sub == 10 or e.sub == 15 or e.sub == 19) then okAll = false; bad = e.id end
        if not Has(e.stats, "INT", "SP", "SPI", "SP_SHADOW", "MP5", "SPELL_CRIT", "SPELL_HIT") and not (e.class == 2 and e.sub == 19) then okAll = false; bad = e.id end
      end
      Check(okAll, "only cloth/caster pieces a warlock can wear", bad)
      Check(#Rows("loot") > 0, "the tab shows loot rows")
      RunAllTabs()
      Check(#Sim.errors == 0, "no Lua errors", Sim.errors[1])
    `,
  },
  {
    id: 'dungeons-druid',
    title: 'Dungeon journal: a feral druid sees cat/feral pieces (agility, strength, leather), never cloth caster gear',
    char: 'nightelf-druid',
    lua: SETUP + L_`
      Login()
      Sim.Advance(3)
      SetLevel(22)
      local D = DG()
      OpenJournal("wailing-caverns")
      Check(D.Ready(), "decoded")
      local G = S().Modules.Gear
      Check(G.BuildKey() == "cat", "druid build is cat", G.BuildKey())
      local function check(key)
        local loot = D.Loot(key)
        local okAll, bad, agi, leather = true, nil, 0, 0
        for _, it in ipairs(loot) do
          local e = it.e
          if e.class == 4 and e.sub >= 3 and e.sub <= 4 then okAll = false; bad = e.id end
          if not Has(e.stats, "AGI", "STR", "AP", "DPS", "CRIT", "HIT") then okAll = false; bad = e.id end
          if (e.stats.AGI or 0) > 0 then agi = agi + 1 end
          if e.class == 4 and e.sub == 2 then leather = leather + 1 end
        end
        for i = 1, math.min(4, #loot) do
          local e, parts = loot[i].e, {}
          for k, v in pairs(e.stats) do parts[#parts + 1] = k .. "=" .. v end
          table.sort(parts)
          Sim.Out("    " .. key .. " #" .. i .. ": " .. e.id .. " " .. table.concat(parts, ",") .. (loot[i].up and " (mejora)" or ""))
        end
        Check(#loot > 0, key .. ": loot for a cat druid", #loot)
        Check(okAll, key .. ": only feral pieces (agility/strength/attack, no mail or plate)", bad)
        return agi, leather
      end
      local a1, l1 = check("wailing-caverns")
      local a2, l2 = check("deadmines")
      local a3, l3 = check("blackfathom-deeps")
      Check(a1 + a2 + a3 > 0 and l1 + l2 + l3 > 0, "agility and leather pieces among them", (a1 + a2 + a3) .. " agi, " .. (l1 + l2 + l3) .. " leather")
      Section("upgrades first")
      local loot = D.Loot("wailing-caverns")
      local seenNot = false
      local order = true
      for _, it in ipairs(loot) do
        if not it.up then seenNot = true elseif seenNot then order = false end
      end
      Check(order, "upgrades are listed before the rest")
      Check(loot[1] and loot[1].up, "with nothing equipped, the best piece is an upgrade")
      Section("bear build changes the ranking")
      G.SetBuild("bear")
      local bear = D.Loot("wailing-caverns")
      Check(#bear > 0, "bear sees loot too", #bear)
      G.SetBuild("cat")
      Section("tab rows")
      local rows = Rows("loot")
      Check(#rows > 0 and (Plain(rows[1].right):find("%+") ~= nil or Plain(rows[1].right):find("mejora", 1, true) ~= nil), "first loot row shows the gain for your build", rows[1] and rows[1].right)
      local _, nodes = D.Shown()
      local head
      for _, n in ipairs(nodes) do if n.t == "h1" and n.text:find("build", 1, true) then head = n.text end end
      Check(head and head:find("felino", 1, true), "loot header names the build", head)
      Check(#Sim.errors == 0, "no Lua errors", Sim.errors[1])
    `,
  },
  {
    id: 'dungeons-arrow',
    title: 'Dungeon journal: arrow to the entrance and to the meeting stone, the travel planner takes it, cleared inside the instance',
    char: 'human-mage',
    lua: SETUP + L_`
      Login()
      Sim.Advance(3)
      SetLevel(18)
      local D = DG()
      OpenJournal("deadmines")
      local btn = Button("Flecha a la entrada")
      Check(btn ~= nil, "«Flecha a la entrada» button")
      btn.onClick()
      Sim.Advance(0.5)
      local t, src = S().Arrow:Destination()
      Check(src == "dungeon" and t and t.map == 1436 and math.abs(t.x - 0.382) < 0.001 and math.abs(t.y - 0.775) < 0.001,
        "arrow to the Deadmines entrance (Westfall 38.2, 77.5)", t and (t.map .. " " .. t.x .. "," .. t.y))
      Check(t and t.label and Plain(t.label):find("Minas de la Muerte", 1, true), "arrow label names the dungeon", t and t.label)
      Check(D.Pointed() == "deadmines", "the journal knows where the arrow points")
      Check(Button("Quitar la flecha") ~= nil, "«Quitar la flecha» appears")
      local _, nodes = D.Shown()
      local travel
      for _, n in ipairs(nodes) do if n.t == "p" and n.text and (n.text:find("La flecha te lleva", 1, true) or n.text:find("Camino", 1, true) or n.text:find("pie", 1, true) or n.text:find("No conozco", 1, true)) then travel = n.text end end
      Check(travel ~= nil, "how to get there is shown", travel)
      Section("travel planner takes a dungeon target")
      local TV = S().Modules.Travel
      Sim.Advance(4)
      Check(#Sim.errors == 0, "planner runs on the dungeon target without errors", Sim.errors[1])
      Section("meeting stone")
      Button("Flecha a la piedra").onClick()
      Sim.Advance(0.3)
      t, src = S().Arrow:Destination()
      local stone = D.Get("deadmines").stone
      Check(src == "dungeon" and t.map == stone.map and math.abs(t.x - stone.x / 100) < 0.001, "arrow to the meeting stone", t and t.label)
      Section("clear")
      Button("Quitar la flecha").onClick()
      Sim.Advance(0.3)
      Check(not S().Arrow:Has("dungeon"), "arrow cleared")
      Section("quest giver")
      local r
      for _, row in ipairs(Rows("quest")) do if row.tip then r = row; break end end
      Check(r ~= nil, "a quest row with a known giver")
      r.onClick()
      Sim.Advance(0.3)
      Check(S().Arrow:Has("dungeon"), "clicking a quest points the arrow at its giver")
      Section("inside the instance")
      D.Point("deadmines")
      Sim.SetInstance("party")
      Sim.Advance(0.5)
      Check(not S().Arrow:Has("dungeon"), "entering the instance clears the dungeon arrow")
      Sim.SetInstance(nil)
      Section("no entrance from the client: the guide's point")
      local th = D.Get("the-hall-of-thanes")
      Check(th and th.entrance and th.entrance.extra == "g" and th.entrance.map == 1455, "Hall of Thanes: entrance from the guide step", th and th.entrance and th.entrance.map)
      Check(D.Point("the-hall-of-thanes"), "arrow to it")
      local ruins = D.Get("ruins-of-lordaeron")
      Check(ruins and ruins.entrance == nil and not D.Point("ruins-of-lordaeron"), "no point at all: no arrow")
      Section("mage frost loot")
      local loot = D.Loot("deadmines")
      local okAll = #loot > 0
      for _, it in ipairs(loot) do
        local e = it.e
        if (e.class == 4 and e.sub >= 2 and e.sub <= 4) or not (Has(e.stats, "INT", "SP", "SPI", "SP_FROST", "MP5", "SPELL_CRIT", "SPELL_HIT") or (e.class == 2 and e.sub == 19)) then okAll = false end
        Check((e.stats.SP_SHADOW or 0) == 0 or Has(e.stats, "INT", "SP", "SPI", "SP_FROST"), "mage: a shadow-only piece is not shown (" .. e.id .. ")")
      end
      Check(okAll, "mage sees cloth caster pieces")
      Check(#Sim.errors == 0, "no Lua errors", Sim.errors[1])
    `,
  },
  {
    id: 'dungeons-hud',
    title: 'Dungeon journal: the HUD text of a dungeon step links to its card (no new line); /senda mazmorra',
    char: 'gnome-warlock',
    lua: SETUP + L_`
      Login()
      Sim.Advance(3)
      local E = S().Engine
      local i = StepIndexOf("a21dm-022")
      Check(i ~= nil, "the Deadmines dungeon step is in the warlock guide")
      SetLevel(20)
      E:JumpTo(i)
      Sim.Advance(0.5)
      Check(StepId() == "a21dm-022", "current step is the dungeon step", StepId())
      local text = Plain(HudText())
      Check(text:find("Ver en Mazmorras", 1, true) ~= nil, "step text links to the journal", text)
      Check(S().HUD.dungeonKey == "deadmines", "HUD knows the dungeon")
      local extra = S().HUD.extraLine
      Section("click on the step")
      Sim.Click(SendaHUD.hit, "LeftButton")
      for _ = 1, 30 do if DG().Ready() then break end; Sim.Advance(0.1) end
      Sim.Advance(0.5)
      Check(SendaMainFrame:IsShown(), "the panel opens")
      local key, nodes = DG().Shown()
      Check(key == "deadmines", "on the Deadmines card", key)
      local now
      for _, n in ipairs(nodes or {}) do if n.t == "p" and n.text and n.text:find("Tu guía te manda aquí", 1, true) then now = true end end
      Check(now, "the card says the guide sends you there now")
      Check(S().HUD.extraLine == extra, "no extra HUD line was added")
      Section("a quest step has no link")
      SendaMainFrame:Hide()
      E:JumpTo(i + 1)
      Sim.Advance(0.5)
      Check(Plain(HudText()):find("Ver en Mazmorras", 1, true) == nil, "next step: no link", StepId())
      Check(S().HUD.dungeonKey == nil, "HUD dungeon key cleared")
      Sim.Click(SendaHUD.hit, "LeftButton")
      Sim.Advance(0.3)
      Check(not SendaMainFrame:IsShown(), "left click on a normal step does nothing")
      Section("/senda mazmorra gnomeregan")
      Slash("mazmorra gnomeregan")
      Sim.Advance(0.5)
      Check(SendaMainFrame:IsShown() and DG().Shown() == "gnomeregan", "slash opens Gnomeregan", (DG().Shown()))
      local ids = DG().DumpIds()
      Check(#ids.quests > 500 and #ids.npcs > 200 and #ids.items > 300, "/senda volcar gets the journal's ids", #ids.quests .. "/" .. #ids.npcs .. "/" .. #ids.items)
      Check(#Sim.errors == 0, "no Lua errors", Sim.errors[1])
    `,
  },
];

module.exports = { scenarios };

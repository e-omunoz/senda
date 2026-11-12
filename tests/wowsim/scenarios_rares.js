'use strict';
// Scenarios of the rare alerts (addon/Senda/Modules/Rares.lua + Data/Rares.lua compiled by tools/build.py):
// the pure Decide(state, event) rules, minimap vignettes, nameplates / target / mouseover, combat hold,
// secret values, hide-in-instances / hide-all, the options, and the compiled data. Loaded by run.js.

const fs = require('fs');
const path = require('path');

const L_ = String.raw;
const ROOT = path.resolve(__dirname, '..', '..');

const scenarios = [
  {
    id: 'rares-decide',
    title: 'Rare alerts: Decide() rules (debounce, cooldown, combat hold, dead, instance, level window) and the data',
    char: 'human-mage',
    lua: L_`
      Login()
      local R = S().Rares
      Check(R ~= nil and R.Decide ~= nil, "Senda.Rares.Decide exists")
      local function new(over)
        local st = R.NewState()
        st.now, st.level = 100, 10
        for k, v in pairs(over or {}) do st[k] = v end
        return st
      end
      local function ev(over)
        local e = { src = "nameplate", guid = "Creature-0-1-0-0-471-0000000001", id = 471, name = "Mother Fang",
          isRare = true, lo = 10, hi = 10 }
        for k, v in pairs(over or {}) do e[k] = v end
        return e
      end
      Section("plain rules")
      local a, why = R.Decide(new(), ev())
      Check(a == "alert" and why == "ok", "a live rare alerts", tostring(a) .. " " .. tostring(why))
      local st = new(); st.opts.enabled = false
      a, why = R.Decide(st, ev()); Check(a == "skip" and why == "off", "off -> skip", why)
      a, why = R.Decide(new({ instance = true }), ev()); Check(a == "skip" and why == "instance", "instance -> skip", why)
      a, why = R.Decide(new({ hidden = true }), ev()); Check(a == "skip" and why == "hidden", "hidden -> skip", why)
      st = new(); st.opts.paths.nameplate = false
      a, why = R.Decide(st, ev()); Check(a == "skip" and why == "path", "path off -> skip", why)
      a, why = R.Decide(new(), ev({ isPlayer = true })); Check(a == "skip" and why == "player", "player -> skip", why)
      a, why = R.Decide(new(), ev({ isRare = false })); Check(a == "skip" and why == "notrare", "not a rare -> skip", why)
      st = new(); st.ignored[471] = true
      a, why = R.Decide(st, ev()); Check(a == "skip" and why == "ignored", "ignored id -> skip", why)
      a, why = R.Decide(new(), ev({ dead = true })); Check(a == "skip" and why == "dead", "dead -> skip", why)
      a, why = R.Decide(new(), ev({ guid = false, id = false, name = false }))
      Check(a == "skip" and why == "unreadable", "nothing readable -> skip", why)
      a = R.Decide(new(), ev({ guid = false, id = false, name = "Algo"}))
      Check(a == "alert", "a name alone is enough (key name:...)")

      Section("debounce 3 s per unit, cooldown per rare")
      st = new()
      Check(R.Decide(st, ev()) == "alert", "first sighting alerts")
      st.now = 101
      a, why = R.Decide(st, ev()); Check(a == "skip" and why == "debounce", "1 s later: debounce", why)
      st.now = 102.9
      a, why = R.Decide(st, ev()); Check(a == "skip" and why == "debounce", "2.9 s after the first look: still debounce", why)
      st.now = 106
      a, why = R.Decide(st, ev()); Check(a == "skip" and why == "cooldown", "after the debounce: cooldown of the same rare", why)
      st.now = 100 + R.COOLDOWN + 10
      Check(R.Decide(st, ev()) == "alert", "after the cooldown it alerts again")
      st = new()
      R.Decide(st, ev())
      st.now = 101
      a = R.Decide(st, ev({ guid = "Creature-0-1-0-0-79-0000000002", id = 79, name = "Narg" }))
      Check(a == "alert", "another rare is not debounced by the first")
      Section("sweep of the debounce table")
      st = new()
      for i = 1, 260 do
        st.now = 100 + i * 0.05
        R.Decide(st, ev({ guid = "Creature-0-1-0-0-9000-" .. i, id = 9000 + i }))
      end
      local n = 0
      for _ in pairs(st.recent) do n = n + 1 end
      Check(n <= 260 and st.nrecent == n, "counter matches the table", n .. " / " .. tostring(st.nrecent))
      st.now = 200
      for i = 1, 150 do R.Decide(st, ev({ guid = "Creature-0-1-0-0-9500-" .. i, id = 9500 + i })) end
      n = 0
      for _ in pairs(st.recent) do n = n + 1 end
      Check(n == 150 and st.nrecent == 150 and st.recent["Creature-0-1-0-0-9000-1"] == nil, "old entries swept (" .. n .. ")")

      Section("level window")
      st = new({ level = 10 }); st.opts.near = true
      a, why = R.Decide(st, ev({ lo = 26, hi = 26 })); Check(a == "skip" and why == "level", "level 26 vs 10 with the option on -> skip", why)
      st = new({ level = 10 }); st.opts.near = true
      Check(R.Decide(st, ev({ lo = 13, hi = 13 })) == "alert", "+3 levels is inside the window")
      st = new({ level = 10 }); st.opts.near = true
      a, why = R.Decide(st, ev({ lo = 14, hi = 14 })); Check(a == "skip" and why == "level", "+4 levels is outside", why)
      st = new({ level = 20 }); st.opts.near = true
      a, why = R.Decide(st, ev({ lo = 16, hi = 16 })); Check(a == "skip" and why == "level", "-4 levels is outside", why)
      st = new({ level = 20 }); st.opts.near = true
      Check(R.Decide(st, ev({ lo = 17, hi = 17 })) == "alert", "-3 levels is inside")
      st = new({ level = 10 }); st.opts.near = true
      Check(R.Decide(st, ev({ lo = false, hi = false })) == "alert", "unknown level still alerts")
      st = new({ level = 10 })
      Check(R.Decide(st, ev({ lo = 40, hi = 40 })) == "alert", "option off: any level alerts")

      Section("combat hold and release")
      st = new({ combat = true })
      a, why = R.Decide(st, ev()); Check(a == "hold" and why == "combat", "in combat -> hold", why)
      Check(st.held ~= nil and st.held.ev.id == 471, "the sighting is kept")
      st.combat, st.now = false, 110
      local act, _, e = R.Release(st)
      Check(act == "alert" and e.id == 471, "released after combat -> alert", tostring(act))
      Check(st.held == nil, "nothing held afterwards")
      Check(R.Release(st) == nil, "a second release does nothing")
      st = new({ combat = true })
      R.Decide(st, ev())
      st.refresh = function(x) x.dead = true end
      st.combat, st.now = false, 110
      act, why = R.Release(st); Check(act == "skip" and why == "dead", "died meanwhile -> no alert", tostring(act) .. " " .. tostring(why))
      st = new({ combat = true })
      R.Decide(st, ev())
      st.combat, st.now = false, 100 + R.HOLD_FOR + 1
      act, why = R.Release(st); Check(act == "skip" and why == "stale", "held for more than 60 s -> dropped", tostring(why))
      st = new({ combat = true })
      R.Decide(st, ev())
      st.combat, st.now, st.instance = false, 110, true
      act = R.Release(st); Check(act == "skip", "entered an instance meanwhile -> dropped")
      st = new({ combat = true })
      R.Decide(st, ev())
      R.Decide(st, ev({ guid = "Creature-0-1-0-0-79-0000000002", id = 79 }))
      Check(st.held.ev.id == 79, "only the last sighting is held")
      st.combat, st.now = false, 110
      Check(R.Release(st) == "alert", "and it is the one released")
      st = new({ combat = true })
      R.Decide(st, ev())
      st.combat, st.now = false, 105
      R.Release(st)
      st.now = 106
      a, why = R.Decide(st, ev())
      Check(a == "skip" and (why == "debounce" or why == "cooldown"), "after the release the same rare does not alert again", why)

      Section("scan throttle")
      st = new()
      Check(R.ScanDelay(st) == 0, "first scan: now")
      st.lastScan = 100
      st.now = 100.5
      Check(math.abs(R.ScanDelay(st) - 1.5) < 1e-6, "0.5 s after a scan: wait 1.5 s", tostring(R.ScanDelay(st)))
      st.now = 102.1
      Check(R.ScanDelay(st) == 0, "2 s later: scan")
      st.combat = true
      Check(R.ScanDelay(st) == nil, "never in combat")

      Section("compiled data")
      local info = R.Info(471)
      Check(info and info.lo == 10 and info.hi == 10 and not info.elite, "Mother Fang: level 10, rare")
      Check(info and info.spawns[1][1] == 1429 and math.abs(info.spawns[1][2] - 62.1) < 0.01 and math.abs(info.spawns[1][3] - 48.0) < 0.01,
        "Mother Fang spawn in Elwynn (62.1, 48.0)")
      info = R.Info(8282)
      Check(info and info.elite and info.lo == 51, "Highlord Mastrogonde: rare elite 51")
      Check(R.Info(5) == nil and R.Info("x") == nil, "unknown ids are nil")
      Check(R.Count() == 346, "346 rares with a known spawn", R.Count())
      Check(R.Known(471) and not R.Known(5), "Known()")
      local m, x, y = R.NearestSpawn(R.Info(61), 1429, 0.29, 0.58)
      Check(m == 1429 and math.abs(x - 29.2) < 0.01 and math.abs(y - 58.0) < 0.01, "nearest spawn of Thuros to (29, 58)", tostring(x) .. "," .. tostring(y))
      Check(R.NearestSpawn(R.Info(61), 1436, 0.5, 0.5) == nil, "no spawn on another map")
    `,
  },
  {
    id: 'rares-vignette',
    title: 'Rare alerts: minimap vignettes, HUD line, Señalar, scan throttle and slicing, hide in instances, options',
    char: 'human-mage',
    lua: L_`
      Login()
      local p = Sim.player
      p.level = 10
      Sim.NPC_NAMES[471] = "Madre Colmillo"
      Sim.NPC_NAMES[462] = "Vultros"
      local sounds = 0
      PlaySound = function() sounds = sounds + 1 end
      local function Line() return SendaHUD.rare:IsShown() and Plain(SendaHUD.rare:GetText()) or nil end
      Sim.Advance(1)
      Check(Line() == nil, "no alert line at the start")

      Section("a rare appears on the minimap")
      local vg = Sim.AddVignette({ id = 471, name = "Mother Fang", map = 1429, x = 0.621, y = 0.480 })
      Sim.Advance(1)
      Check(Line() == "Raro cerca: Madre Colmillo (nivel 10)", "line with the esES name from the client token", tostring(Line()))
      Check(sounds == 1, "one sound", sounds)
      Check(SendaHUD.rarePoint:IsShown(), "Señalar button shown (the vignette has a position)")
      Check(S().Rares.Current().map == 1429 and math.abs(S().Rares.Current().x - 62.1) < 0.01, "position from the vignette")
      Section("same unit again within 3 s: nothing new")
      Sim.Fire("VIGNETTE_MINIMAP_UPDATED", vg, true)
      Sim.Fire("VIGNETTE_MINIMAP_UPDATED", vg, true)
      Sim.Advance(1)
      Check(sounds == 1, "no second sound", sounds)
      Section("Señalar points the arrow")
      Sim.Click(SendaHUD.rarePoint)
      local t, src = ArrowTarget()
      Check(src == "rare" and t.map == 1429 and math.abs(t.x - 0.621) < 1e-6 and math.abs(t.y - 0.480) < 1e-6, "arrow at the vignette position", tostring(src))
      Check(t.label:find("Madre Colmillo", 1, true) ~= nil, "arrow label has the rare's name", t.label)
      Section("dismiss, and expiry after 45 s")
      Sim.Click(SendaHUD.rareClose); Sim.Advance(0.5)
      Check(Line() == nil, "the X hides the line")
      S().Arrow:Clear("rare")
      Sim.AddVignette({ id = 79, name = "Narg the Taskmaster", map = 1429, x = 0.409, y = 0.775 }); Sim.Advance(1)
      Check(Line() ~= nil and Line():find("nivel 10", 1, true) ~= nil, "another rare: new line", tostring(Line()))
      Sim.Advance(40)
      Check(Line() ~= nil, "still there after 41 s")
      Sim.Advance(6)
      Check(Line() == nil, "gone after 45 s")

      Section("filters: treasure, dead, player map without position")
      local before = sounds
      Sim.AddVignette({ id = 99, name = "Cofre", map = 1429, x = 0.3, y = 0.3, treasure = true }); Sim.Advance(1)
      Check(Line() == nil, "a treasure (GameObject) is not a rare")
      Sim.AddVignette({ id = 99, name = "Morgaine the Sly", map = 1429, x = 0.308, y = 0.647, dead = true }); Sim.Advance(1)
      Check(Line() == nil and sounds == before, "a dead rare does not alert")
      Section("position through a parent map")
      p.map, p.x, p.y = 1453, 0.5, 0.5 -- Stormwind, child of Elwynn
      Sim.Fire("ZONE_CHANGED_NEW_AREA"); Sim.Advance(0.5)
      Sim.AddVignette({ id = 61, name = "Thuros Lightfingers", map = 1429, x = 0.509, y = 0.831, onlyOwnMap = true }); Sim.Advance(1)
      Check(Line() ~= nil and SendaHUD.rarePoint:IsShown(), "vignette with a position only on the zone map (player on a child map)", tostring(Line()))
      Check(S().Rares.Current().map == 1429, "position found on the parent", tostring(S().Rares.Current().map))
      p.map, p.x, p.y = 1429, 0.48, 0.42
      Sim.Fire("ZONE_CHANGED_NEW_AREA"); Sim.Advance(0.5)
      S().Rares.Dismiss()

      Section("scan: throttle and slicing")
      Sim.vignettes, Sim.vignetteOrder = {}, {}
      Sim.Advance(3)
      for i = 1, 20 do
        Sim.AddVignette({ id = 20000 + i, name = "Raro " .. i, map = 1429, x = 0.1 + i / 100, y = 0.5 }, true)
      end
      local calls0 = Sim.vignetteCalls.list
      local perFrame, last = 0, Sim.vignetteCalls.info
      table.insert(Sim.frameHooks, function()
        local n = Sim.vignetteCalls.info - last
        last = Sim.vignetteCalls.info
        if n > perFrame then perFrame = n end
      end)
      for _ = 1, 30 do Sim.Fire("VIGNETTES_UPDATED") end
      Sim.Advance(0.5)
      Check(Sim.vignetteCalls.list - calls0 == 1, "30 VIGNETTES_UPDATED in a burst -> one GetVignettes", Sim.vignetteCalls.list - calls0)
      Sim.Advance(1)
      Check(Sim.vignetteCalls.list - calls0 == 1, "still one inside 2 s")
      Sim.Fire("VIGNETTES_UPDATED"); Sim.Advance(2.5)
      Check(Sim.vignetteCalls.list - calls0 == 2, "next scan after 2 s", Sim.vignetteCalls.list - calls0)
      Check(perFrame <= 8 and perFrame > 0, "at most 8 vignettes read per frame (" .. perFrame .. ")")
      Check(S().Rares.Current() ~= nil, "the scan found rares")

      Section("hide in instances and hide all")
      S().Rares.Dismiss()
      Sim.vignettes, Sim.vignetteOrder = {}, {}
      Sim.Advance(3)
      sounds = 0
      Sim.SetInstance("party"); Sim.Advance(0.5)
      Sim.AddVignette({ id = 472, name = "Fedfennel", map = 1429, x = 0.681, y = 0.449 }); Sim.Advance(1)
      Check(S().Rares.Current() == nil and sounds == 0, "no alert in a dungeon")
      Sim.vignettes, Sim.vignetteOrder = {}, {}
      Sim.SetInstance(nil); Sim.Advance(0.5)
      Slash("hide")
      Sim.AddVignette({ id = 472, name = "Fedfennel", map = 1429, x = 0.665, y = 0.409, guid = nil }); Sim.Advance(1)
      Check(S().Rares.Current() == nil and sounds == 0, "no alert with everything hidden", tostring(S().Rares.Current() and S().Rares.Current().src) .. " sounds " .. sounds .. " hidden " .. tostring(S().Visibility:Hidden()))
      Slash("hide"); Sim.Advance(0.5)

      Section("options")
      S().Options:Set("raresSound", false)
      Sim.AddVignette({ id = 472, name = "Fedfennel", map = 1429, x = 0.67, y = 0.40 }); Sim.Advance(1)
      Check(Line() ~= nil and sounds == 0, "sound option off: line but no sound", tostring(Line()) .. " " .. sounds)
      S().Options:Set("raresSound", true)
      S().Options:Set("raresEnabled", false); Sim.Advance(0.5)
      Check(Line() == nil, "turning the alerts off clears the line")
      Sim.AddVignette({ id = 462, name = "Vultros", map = 1436, x = 0.62, y = 0.755 }); Sim.Advance(1)
      Check(Line() == nil, "off: no alerts")
      S().Options:Set("raresEnabled", true)
      S().Options:Set("raresNear", true)
      Sim.AddVignette({ id = 462, name = "Vultros", map = 1436, x = 0.616, y = 0.742 }); Sim.Advance(1)
      Check(Line() == nil, "±3 levels on: Vultros (26) is ignored for a level 10", tostring(Line()))
      p.level = 24; Sim.Fire("PLAYER_LEVEL_UP", 24, 0, 0, 0, 0, 0, 0, 0, 0)
      Sim.Advance(12)
      Sim.AddVignette({ id = 462, name = "Vultros", map = 1436, x = 0.62, y = 0.74 }); Sim.Advance(1)
      Check(Line() ~= nil and Line():find("Vultros", 1, true) ~= nil, "at level 24 Vultros (26) alerts", tostring(Line()))
      S().Options:Set("raresNear", false)
      local lines = Slash("raros")
      Check(table.concat(lines, "|"):find("Alertas de raros: sí", 1, true) ~= nil and table.concat(lines, "|"):find("346", 1, true) ~= nil,
        "/senda raros prints the status", table.concat(lines, "|"))
      lines = Slash("raros off")
      Check(S().Options:Get("raresEnabled") == false, "/senda raros off")
      Slash("raros on")
      Check(S().Options:Get("raresEnabled") == true, "/senda raros on")
    `,
  },
  {
    id: 'rares-units',
    title: 'Rare alerts: nameplates, target and mouseover (classification, known id, players, pets, unknown rares)',
    char: 'nightelf-druid',
    lua: L_`
      Login()
      local p = Sim.player
      p.level = 9
      Sim.NPC_NAMES[14430] = "Acechador del Ocaso"
      local sounds = 0
      PlaySound = function() sounds = sounds + 1 end
      local function Line() return SendaHUD.rare:IsShown() and Plain(SendaHUD.rare:GetText()) or nil end
      Section("nameplate of a rare")
      Sim.SetUnit("nameplate1", { id = 14430, name = "Duskstalker", level = 9, class = "rare" })
      Sim.Fire("NAME_PLATE_UNIT_ADDED", "nameplate1"); Sim.Advance(1)
      Check(Line() == "Raro cerca: Acechador del Ocaso (nivel 9)", "alert from a nameplate", tostring(Line()))
      Check(sounds == 1, "one sound", sounds)
      Check(SendaHUD.rarePoint:IsShown(), "pointable: Duskstalker is in the data and in this zone")
      Sim.Click(SendaHUD.rarePoint)
      local t, src = ArrowTarget()
      Check(src == "rare" and t.map == 1438 and math.abs(t.x - 0.581) < 1e-6 and math.abs(t.y - 0.767) < 1e-6, "arrow at the nearest known spawn (58.1, 76.7)", tostring(t and t.x))
      Sim.Fire("NAME_PLATE_UNIT_ADDED", "nameplate1"); Sim.Advance(1)
      Check(sounds == 1, "the same plate again: nothing", sounds)
      Sim.units.nameplate1 = nil
      S().Rares.Dismiss(); S().Arrow:Clear("rare")

      Section("normal mob, player, pet, dead")
      Sim.SetUnit("nameplate2", { id = 3000, name = "Lobo", level = 9, class = "normal" })
      Sim.Fire("NAME_PLATE_UNIT_ADDED", "nameplate2")
      Sim.SetUnit("nameplate3", { player = true, name = "Otro", level = 60, class = "rare" })
      Sim.Fire("NAME_PLATE_UNIT_ADDED", "nameplate3")
      Sim.SetUnit("nameplate4", { id = 14431, name = "Mascota", level = 9, class = "rare", controlled = true })
      Sim.Fire("NAME_PLATE_UNIT_ADDED", "nameplate4")
      Sim.SetUnit("nameplate5", { id = 14431, name = "Fury Shelda", level = 8, class = "rare", dead = true })
      Sim.Fire("NAME_PLATE_UNIT_ADDED", "nameplate5")
      Sim.Advance(1)
      Check(Line() == nil and sounds == 1, "none of them alerts", tostring(Line()))

      Section("known id although the client says normal")
      Sim.SetUnit("nameplate6", { id = 14432, name = "Threggil", level = 6, class = "normal" })
      Sim.Fire("NAME_PLATE_UNIT_ADDED", "nameplate6"); Sim.Advance(1)
      Check(Line() ~= nil and Line():find("nivel 6", 1, true) ~= nil, "id in the data counts", tostring(Line()))
      S().Rares.Dismiss()

      Section("unknown rare elite by classification: name, no data")
      Sim.SetUnit("nameplate7", { id = 123456, name = "Bestia Desconocida", level = 12, class = "rareelite" })
      Sim.Fire("NAME_PLATE_UNIT_ADDED", "nameplate7"); Sim.Advance(1)
      Check(Line() ~= nil, "alerts", tostring(Line()))
      Check(Line() and Line():find("nivel 12", 1, true) ~= nil, "level from the unit", tostring(Line()))
      Check(not SendaHUD.rarePoint:IsShown(), "nothing to point at without data or a vignette")
      S().Rares.Dismiss()

      Section("target and mouseover")
      Sim.units.nameplate7 = nil
      Sim.SetUnit("target", { id = 14429, name = "Grimmaw", level = 11, class = "rare" })
      Sim.Fire("PLAYER_TARGET_CHANGED"); Sim.Advance(1)
      Check(Line() ~= nil and Line():find("nivel 11", 1, true) ~= nil, "target", tostring(Line()))
      S().Rares.Dismiss()
      Sim.units.target = nil
      Sim.SetUnit("mouseover", { id = 14428, name = "Uruson", level = 7, class = "rare" })
      Sim.Fire("UPDATE_MOUSEOVER_UNIT"); Sim.Advance(1)
      Check(Line() ~= nil and Line():find("nivel 7", 1, true) ~= nil, "mouseover", tostring(Line()))
      Sim.Fire("UPDATE_MOUSEOVER_UNIT"); Sim.Fire("UPDATE_MOUSEOVER_UNIT"); Sim.Advance(1)
      Check(sounds == 5, "mouseover flicker is debounced", sounds)
      Sim.units.mouseover = nil
      Sim.Fire("UPDATE_MOUSEOVER_UNIT"); Sim.Fire("PLAYER_TARGET_CHANGED"); Sim.Advance(1)
      Check(sounds == 5, "no unit: nothing")
    `,
  },
  {
    id: 'rares-combat',
    title: 'Rare alerts: combat hold (alert after combat unless dead), secret values, nothing scanned in combat',
    char: 'gnome-warlock',
    lua: L_`
      -- Midnight: values can be "secret" in combat. The sim marks the string "<secret>" as one.
      local SECRET = "<secret>"
      issecretvalue = function(v) return v == SECRET end
      Login()
      local p = Sim.player
      p.level = 10
      Sim.NPC_NAMES[1132] = "Timber"
      local sounds = 0
      PlaySound = function() sounds = sounds + 1 end
      local function Line() return SendaHUD.rare:IsShown() and Plain(SendaHUD.rare:GetText()) or nil end
      Section("nameplate in combat: held, alerted when combat ends")
      p.combat = true
      Sim.Fire("PLAYER_REGEN_DISABLED")
      Sim.SetUnit("nameplate1", { id = 1132, name = "Timber", level = 10, class = "rare" })
      Sim.Fire("NAME_PLATE_UNIT_ADDED", "nameplate1"); Sim.Advance(2)
      Check(Line() == nil and sounds == 0, "nothing shown or heard in combat")
      p.combat = false
      Sim.Fire("PLAYER_REGEN_ENABLED"); Sim.Advance(1)
      Check(Line() == "Raro cerca: Timber (nivel 10)", "alert right after combat", tostring(Line()))
      Check(sounds == 1, "one sound", sounds)
      S().Rares.Dismiss()

      Section("it died during the fight: no alert")
      Sim.units.nameplate1 = nil
      p.combat = true
      Sim.SetUnit("nameplate2", { id = 1119, name = "Hammerspine", level = 12, class = "rare" })
      Sim.Fire("NAME_PLATE_UNIT_ADDED", "nameplate2"); Sim.Advance(1)
      Sim.units.nameplate2.dead = true
      p.combat = false
      Sim.Fire("PLAYER_REGEN_ENABLED"); Sim.Advance(1)
      Check(Line() == nil and sounds == 1, "dead when combat ends -> skipped")

      Section("held for more than 60 s: dropped")
      p.combat = true
      Sim.SetUnit("nameplate3", { id = 1130, name = "Bjarn", level = 12, class = "rare" })
      Sim.Fire("NAME_PLATE_UNIT_ADDED", "nameplate3"); Sim.Advance(65)
      p.combat = false
      Sim.Fire("PLAYER_REGEN_ENABLED"); Sim.Advance(1)
      Check(Line() == nil, "a long fight: the held alert is stale")

      Section("vignettes in combat: no scan, one scan afterwards")
      p.combat = true
      local calls0 = Sim.vignetteCalls.list
      Sim.AddVignette({ id = 1260, name = "Great Father Arctikus", map = 1426, x = 0.234, y = 0.546 }, true)
      Sim.Fire("VIGNETTES_UPDATED"); Sim.Advance(5)
      Check(Sim.vignetteCalls.list == calls0, "GetVignettes is never called in combat", Sim.vignetteCalls.list - calls0)
      Check(Line() == nil, "no alert in combat")
      p.combat = false
      Sim.Fire("PLAYER_REGEN_ENABLED"); Sim.Advance(3)
      Check(Sim.vignetteCalls.list == calls0 + 1, "the pending scan runs once combat ends", Sim.vignetteCalls.list - calls0)
      Check(Line() ~= nil and Line():find("nivel 11", 1, true) ~= nil, "and finds the rare", tostring(Line()))
      S().Rares.Dismiss()

      Section("a vignette event in combat is held and released")
      p.combat = true
      Sim.AddVignette({ id = 8503, name = "Gibblewilt", map = 1426, x = 0.248, y = 0.432 })
      Sim.Advance(1)
      Check(Line() == nil, "held")
      p.combat = false
      Sim.Fire("PLAYER_REGEN_ENABLED"); Sim.Advance(1)
      Check(Line() ~= nil and Line():find("nivel 11", 1, true) ~= nil, "released after combat", tostring(Line()))
      S().Rares.Dismiss()

      Section("secret values are unknown, never errors")
      Sim.SetUnit("nameplate8", { id = 1137, name = SECRET, level = 9, class = SECRET })
      Sim.units.nameplate8.guid = SECRET
      Sim.Fire("NAME_PLATE_UNIT_ADDED", "nameplate8"); Sim.Advance(1)
      Check(Line() == nil, "secret GUID: unit skipped")
      Sim.SetUnit("nameplate9", { id = 1137, name = SECRET, level = 9, class = SECRET })
      Sim.units.nameplate9.guid = Sim.CreatureGUID(1137, 3)
      Sim.Fire("NAME_PLATE_UNIT_ADDED", "nameplate9"); Sim.Advance(1)
      Check(Line() ~= nil, "readable GUID of a known rare with secret name and class still alerts (data level)", tostring(Line()))
      S().Rares.Dismiss()
      local v = Sim.AddVignette({ id = 1137, name = SECRET, map = 1426, x = 0.42, y = 0.49, objectGUID = SECRET }, true)
      Sim.Fire("VIGNETTE_MINIMAP_UPDATED", v, true); Sim.Advance(1)
      Check(Line() == nil, "secret objectGUID in a vignette: skipped")
      local w = Sim.AddVignette({ id = 1119, name = SECRET, map = 1426, x = 0.42, y = 0.49 })
      Sim.Advance(1)
      Check(Line() ~= nil and Line():find("Raro cerca:", 1, true) ~= nil, "secret vignette name: the id token is used", tostring(Line()))
    `,
  },
  {
    id: 'rares-en',
    title: 'Rare alerts in an English client: strings, names without data',
    char: 'gnome-warlock',
    locale: 'enUS',
    lua: L_`
      Login()
      Sim.player.level = 12
      local function Line() return SendaHUD.rare:IsShown() and Plain(SendaHUD.rare:GetText()) or nil end
      Sim.SetUnit("nameplate1", { id = 123456, name = "Mystery Beast", level = 12, class = "rareelite" })
      Sim.Fire("NAME_PLATE_UNIT_ADDED", "nameplate1"); Sim.Advance(1)
      Check(Line() == "Rare nearby: #123456 (level 12, elite)" or (Line() or ""):find("Rare nearby:", 1, true) == 1, "English line", tostring(Line()))
      Check(SendaHUD.rarePoint.GetText and Plain(SendaHUD.rarePoint:GetText()) == "Point", "button text in English", tostring(SendaHUD.rarePoint:GetText()))
      Check(S().L.OPT_RARES == "Alert about nearby rares", "option label in English")
    `,
  },
  {
    id: 'rares-data',
    title: 'Rare data: compiled file is small, every entry well formed',
    char: 'human-mage',
    lua: L_`
      Login()
      local R = S().Rares
      local bad, n, spawns = 0, 0, 0
      for id, raw in pairs(S().RaresData) do
        if type(id) == "number" then
          n = n + 1
          local info = R.Info(id)
          if not info or #info.spawns == 0 or info.hi < info.lo then bad = bad + 1 else spawns = spawns + #info.spawns end
          for _, s in ipairs(info and info.spawns or {}) do
            if s[2] < 0 or s[2] > 100 or s[3] < 0 or s[3] > 100 then bad = bad + 1 end
          end
        end
      end
      Check(n == 346 and bad == 0, "346 entries, all well formed", n .. " / bad " .. bad)
      Check(spawns == 964, "964 spawn points", spawns)
      __report("raresData", n)
    `,
    post(report, carry, ctx) {
      const file = path.join(ROOT, 'addon', 'Senda', 'Data', 'Rares.lua');
      const size = fs.statSync(file).size;
      ctx.check(size < 40 * 1024, 'addon/Senda/Data/Rares.lua is under 40 KB (' + size + ' bytes)');
      const src = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'rares', 'rares.json'), 'utf8'));
      const withSpawns = src.filter((r) => r.spawns && r.spawns.length).length;
      ctx.check(withSpawns === 346, 'data/rares/rares.json has 346 rares with a spawn', String(withSpawns));
    },
  },
];

module.exports = { scenarios };

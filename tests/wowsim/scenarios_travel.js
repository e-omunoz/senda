'use strict';
// Scenarios of the travel planner (addon/Senda/Modules/Travel.lua + Data/Travel.lua, compiled from data/travel).
// Loaded by run.js. Two kinds: pure planner checks with a hand-made context (T.PlanSync) whose expected answers
// come from docs/TRAVEL.md, and end-to-end runs (arrow -> plan -> HUD line -> arrow to the first leg -> taxi map).

const L_ = String.raw;

// Two test maps whose rectangles are the real world yards of each continent, so the data's world positions
// (wx north, wy west) and the mock's map positions agree. Helpers shared by the scenarios.
const SETUP = L_`
  Sim.MAPS[9001] = { name = "Reinos del Este (prueba)", parent = 947, type = 2, continent = 0, n = 3000, w = 4000, sx = 20000, sy = 20000 }
  Sim.MAPS[9002] = { name = "Kalimdor (prueba)", parent = 947, type = 2, continent = 1, n = 12000, w = 5000, sx = 20000, sy = 20000 }
  function Where(c, wn, ww)
    local map = c == 0 and 9001 or 9002
    local m = Sim.MAPS[map]
    return map, (m.w - ww) / m.sx, (m.n - wn) / m.sy
  end
  function GoTo(c, wn, ww) local map, x, y = Where(c, wn, ww); Sim.MoveTo(map, x, y) end
  function Aim(c, wn, ww, label, src)
    local map, x, y = Where(c, wn, ww)
    S().Arrow:SetTarget(map, x * 100, y * 100, label or "Destino", src or "manual")
  end
  function TT() return S().Modules.Travel end
  function TD() return TT().Data() end
  function Node(id) return TD().nodes[id] end
  function Known(ids)
    local fps = {}
    for _, id in ipairs(ids) do fps[id] = Node(id).name end
    S().db.char.fps = fps
    TT().MarkDirty("test")
  end
  function AllIds()
    local ids = {}
    for _, n in ipairs(TD().nodeList) do ids[#ids + 1] = n.id end
    return ids
  end
  function Settle() Sim.Advance(4) end
  -- the sim's guide target lives on a made-up map: clear it so only the points the scenario sets count
  function NoGuide() S().Arrow:Clear("guide") end
  function Plan() return TT().GetPlan() end
  function Hows(legs)
    local out = {}
    for _, l in ipairs(legs or {}) do out[#out + 1] = l.how .. (l.id and (":" .. l.id) or "") end
    return table.concat(out, ",")
  end
  function RideId(legs) for _, l in ipairs(legs) do if l.how == "ride" then return l.id end end end
  function Has(legs, how, id)
    for _, l in ipairs(legs or {}) do if l.how == how and (not id or l.id == id or l.spell == id) then return true end end
    return false
  end
  function TravelLine() return Plain(SendaHUD.travel:GetText()) end
  function Pt(id) local n = Node(id); return { c = n.c, wx = n.wx, wy = n.wy } end
  -- a planner context by hand: faction mask, class, which nodes are known, speed factor, hearth and teleports
  function Ctx(over)
    local ctx = { mask = 1, class = "MAGE", known = {}, speed = 1, teleports = {} }
    for _, id in ipairs(AllIds()) do ctx.known[id] = true end
    for k, v in pairs(over or {}) do ctx[k] = v end
    return ctx
  end
  function Inn(area)
    for _, i in ipairs(TD().inns) do if i.area == area then return i end end
  end
  function InnPt(area) local i = Inn(area); return { c = i.p.c, wx = i.p.wx, wy = i.p.wy } end
`;

const scenarios = [
  {
    id: 'travel',
    title: 'Travel planner: expected routes (Stormwind-Auberdine, tram vs flight, walk under 400 yd, unknown and enemy nodes, hearth)',
    char: 'human-mage',
    lua: SETUP + L_`
      Login()
      Sim.Advance(6)
      local T = TT()
      local D = TD()
      Section("data")
      Check(D ~= nil and #D.nodeList == 63, "63 flight nodes decoded", D and #D.nodeList)
      Check(#D.flights == 268 and #D.rides == 13 and #D.teleports == 8, "268 flights, 13 rides, 8 teleports", #D.flights .. "/" .. #D.rides .. "/" .. #D.teleports)
      Check(#D.inns == 45 and #D.portals == 2, "45 inns, 2 portals on the two continents", #D.inns .. "/" .. #D.portals)
      Check(D.k.run == 7 and D.k.detour == 1.25 and D.k.hearthItem == 6948, "planner constants", D.k.detour)

      Section("Stormwind -> Auberdine: Forever's harbour boat")
      local r = T.PlanSync(Ctx(), Pt(2), Pt(26))
      Check(r ~= nil and RideId(r.legs) == "boat-stormwind-auberdine", "boat from Stormwind Harbor", r and Hows(r.legs))
      Check(r ~= nil and math.abs(r.secs - 428) < 15, "about 428 s (docs/TRAVEL.md)", r and r.secs)
      Section("... and without that boat: through Menethil (flight or boat), never walking the sea")
      r = T.PlanSync(Ctx({ noRide = { ["boat-stormwind-auberdine"] = true } }), Pt(2), Pt(26))
      local ride = r and RideId(r.legs)
      Sim.Out("    " .. (r and Hows(r.legs) or "?"))
      Check(r ~= nil and ride ~= nil and ride ~= "boat-stormwind-auberdine" and ride:find("auberdine", 1, true) ~= nil, "a Wetlands/Hillsbrad boat to Auberdine", r and Hows(r.legs))
      Check(r ~= nil and Has(r.legs, "fly") and math.abs(r.secs - 961) < 40, "flight to Menethil first, about 961 s", r and r.secs)

      Section("Ironforge -> Stormwind: tram or flight")
      local tram
      for _, x in ipairs(D.rides) do if x.id == "tram-stormwind-ironforge" then tram = x end end
      local gate = { c = 0, wx = tram.b.wx, wy = tram.b.wy + 150 }
      local trade = { c = 0, wx = tram.a.wx, wy = tram.a.wy - 200 }
      r = T.PlanSync(Ctx(), gate, trade)
      Check(r ~= nil and Has(r.legs, "ride", "tram-stormwind-ironforge") and not Has(r.legs, "fly"), "tram gate to the Trade District rides the tram", r and Hows(r.legs))
      r = T.PlanSync(Ctx(), Pt(6), Pt(2))
      Check(r ~= nil and Has(r.legs, "fly") and not Has(r.legs, "ride"), "flight master to flight master (both known) flies", r and Hows(r.legs))
      r = T.PlanSync(Ctx({ known = {} }), Pt(6), Pt(2))
      Check(r ~= nil and Has(r.legs, "ride", "tram-stormwind-ironforge") and not Has(r.legs, "fly"), "the same with no flight known: the tram", r and Hows(r.legs))
      r = T.PlanSync(Ctx({ known = { [6] = true } }), Pt(6), Pt(2))
      Check(r ~= nil and Has(r.legs, "ride", "tram-stormwind-ironforge") and not Has(r.legs, "fly"), "only Ironforge known: no flight, the tram", r and Hows(r.legs))

      Section("walk beats fly under 400 yd")
      local d = Node(12)
      r = T.PlanSync(Ctx(), Pt(12), { c = d.c, wx = d.wx + 350, wy = d.wy })
      Check(r ~= nil and #r.legs == 1 and r.legs[1].how == "walk", "350 yd: walk", r and Hows(r.legs))
      r = T.PlanSync(Ctx(), Pt(12), { c = d.c, wx = d.wx, wy = d.wy - 399 })
      Check(r ~= nil and #r.legs == 1 and r.legs[1].how == "walk", "399 yd: walk", r and Hows(r.legs))

      Section("unknown and other-faction nodes are never used")
      local sets = { { 2 }, { 2, 6 }, { 2, 7, 12 }, { 5, 6, 8, 14 }, {} }
      local bad, runs = 0, 0
      for _, ids in ipairs(sets) do
        local known = {}
        for _, id in ipairs(ids) do known[id] = true end
        for _, pair in ipairs({ { 2, 26 }, { 2, 8 }, { 12, 6 }, { 14, 7 }, { 8, 2 } }) do
          local rr = T.PlanSync(Ctx({ known = known }), Pt(pair[1]), Pt(pair[2]))
          runs = runs + 1
          for _, l in ipairs(rr and rr.legs or {}) do
            if l.how == "fly" then
              for _, id in ipairs(l.nodes) do if not known[id] then bad = bad + 1 end end
            end
          end
        end
      end
      Check(runs == 25 and bad == 0, "no unknown node on any of " .. runs .. " plans", bad)
      r = T.PlanSync(Ctx({ known = { [2] = true } }), Pt(2), Pt(8))
      Check(r ~= nil and not Has(r.legs, "fly"), "with only Stormwind known there is nothing to fly to", r and Hows(r.legs))
      bad = 0
      for _, pair in ipairs({ { 2, 11 }, { 6, 10 }, { 12, 13 }, { 8, 56 }, { 14, 18 } }) do
        local rr = T.PlanSync(Ctx(), Pt(pair[1]), Pt(pair[2]))
        for _, l in ipairs(rr and rr.legs or {}) do
          if l.how == "fly" then for _, id in ipairs(l.nodes) do if Node(id).mask == 2 then bad = bad + 1 end end end
          if l.how == "ride" then for _, x in ipairs(D.rides) do if x.id == l.id and x.mask == 2 then bad = bad + 1 end end end
        end
      end
      Check(bad == 0, "an Alliance character never flies or rides Horde services", bad)
      bad = 0
      for _, pair in ipairs({ { 23, 22 }, { 11, 20 }, { 10, 18 }, { 21, 56 } }) do
        local rr = T.PlanSync(Ctx({ mask = 2, class = "WARRIOR" }), Pt(pair[1]), Pt(pair[2]))
        for _, l in ipairs(rr and rr.legs or {}) do
          if l.how == "fly" then for _, id in ipairs(l.nodes) do if Node(id).mask == 1 then bad = bad + 1 end end end
          if l.how == "ride" then for _, x in ipairs(D.rides) do if x.id == l.id and x.mask == 1 then bad = bad + 1 end end end
        end
      end
      Check(bad == 0, "a Horde character never flies or rides Alliance services", bad)
      r = T.PlanSync(Ctx({ class = "MAGE" }), Pt(62), Pt(27))
      local uses62 = false
      for _, l in ipairs(r and r.legs or {}) do
        if l.how == "fly" then for _, id in ipairs(l.nodes) do if id == 62 or id == 63 then uses62 = true end end end
      end
      Check(r ~= nil and not uses62, "a mage never flies from or to the druid-only Nighthaven nodes", r and Hows(r.legs))
      r = T.PlanSync(Ctx({ class = "DRUID" }), Pt(62), Pt(27))
      local from62 = false
      for _, l in ipairs(r and r.legs or {}) do if l.how == "fly" and l.fromId == 62 then from62 = true end end
      Check(from62, "a druid flies from Nighthaven to Rut'theran", r and Hows(r.legs))

      Section("hearthstone")
      local bind = Inn(1519).p
      r = T.PlanSync(Ctx({ bind = bind, hearthWait = 0 }), InnPt(271), InnPt(1519))
      Check(r ~= nil and r.legs[1].how == "hearth" and r.secs < 25, "bound in Stormwind, far away, off cooldown: hearth", r and (Hows(r.legs) .. " " .. r.secs))
      r = T.PlanSync(Ctx({ bind = bind, hearthWait = 3000 }), InnPt(271), InnPt(1519))
      Check(r ~= nil and not Has(r.legs, "hearth"), "on cooldown (50 min): not the hearth", r and Hows(r.legs))
      r = T.PlanSync(Ctx({ bind = bind }), InnPt(271), InnPt(1519))
      Check(r ~= nil and not Has(r.legs, "hearth"), "no hearthstone (no hearthWait): not the hearth", r and Hows(r.legs))
      r = T.PlanSync(Ctx({ bind = bind, hearthWait = 0 }), InnPt(87), InnPt(1519))
      Check(r ~= nil and not Has(r.legs, "hearth"), "a trip under 3 minutes: not the hearth", r and (Hows(r.legs) .. " " .. r.secs))
      r = T.PlanSync(Ctx({ bind = Inn(2102).p, hearthWait = 0 }), InnPt(271), InnPt(1519))
      Check(r ~= nil and not Has(r.legs, "hearth"), "bound far from the target: not the hearth", r and Hows(r.legs))

      Section("class teleports")
      local tele = {}
      for _, t in ipairs(D.teleports) do
        if t.spell == 3565 then tele[1] = { spell = 3565, name = t.name, cast = t.cast, to = t.to, wait = 0 } end
      end
      r = T.PlanSync(Ctx({ teleports = tele }), InnPt(1519), InnPt(1659))
      Check(r ~= nil and Has(r.legs, "teleport", 3565) and r.secs < 150, "mage Stormwind -> Darnassus: the teleport", r and (Hows(r.legs) .. " " .. r.secs))
      r = T.PlanSync(Ctx(), InnPt(1519), InnPt(1659))
      Check(r ~= nil and not Has(r.legs, "teleport") and r.secs > 400, "without the spell: boats and portals", r and (Hows(r.legs) .. " " .. r.secs))
      Section("walking speed")
      local a, b = Pt(12), { c = d.c, wx = d.wx + 700, wy = d.wy }
      local slow = T.PlanSync(Ctx({ known = {} }), a, b)
      local fast = T.PlanSync(Ctx({ known = {}, speed = 1.6 }), a, b)
      Check(slow ~= nil and fast ~= nil and math.abs(fast.secs * 1.6 - slow.secs) < 0.5, "60 % mount: 1.6 times faster", slow and fast and (slow.secs .. " vs " .. fast.secs))
      Check(slow ~= nil and math.abs(slow.secs - 700 * 1.25 / 7) < 0.5, "700 yd on foot = 700 x 1.25 / 7 s", slow and slow.secs)
      Check(#Sim.errors == 0, "no Lua errors", #Sim.errors)
    `,
  },
  {
    id: 'travel-hud',
    title: 'Travel planner end to end: arrow target far away -> HUD line, arrow to the first leg, sliced job, follow the plan (human mage)',
    char: 'human-mage',
    lua: SETUP + L_`
      Login()
      Sim.Advance(6)
      NoGuide()
      local T = TT()
      local n2, n26 = Node(2), Node(26)
      Known({ 2 })
      GoTo(0, n2.wx, n2.wy)
      Section("another continent: Stormwind -> Auberdine")
      Aim(1, n26.wx, n26.wy, "Auberdine")
      Settle()
      local p = Plan()
      Check(p ~= nil and not p.none and p.legs ~= nil, "a plan exists", p and p.none and "none")
      Check(p ~= nil and RideId(p.legs) == "boat-stormwind-auberdine", "it takes Forever's Stormwind - Auberdine boat", p and Hows(p.legs))
      Check(T.maxSliceOps <= 720, "no slice ran more than 720 operations", T.maxSliceOps)
      local line = TravelLine()
      Sim.Out("    HUD: " .. line)
      Check(line:find("^Camino más rápido: ") ~= nil and line:find("barco a", 1, true) ~= nil, "HUD line starts 'Camino más rápido:' and has the boat", line)
      Check(line:find("a pie$") ~= nil, "... and ends on foot", line)
      Check(SendaHUD.travel:IsShown(), "the travel line is shown")
      local t, src = ArrowTarget()
      Check(src == "travel", "the arrow points at the first leg", src)
      Check(t ~= nil and t.label ~= nil and Plain(t.label):find("^Muelle: ") ~= nil, "labelled with the dock", t and t.label)
      local ride
      for _, x in ipairs(TD().rides) do if x.id == "boat-stormwind-auberdine" then ride = x end end
      Check(t ~= nil and math.abs(t.wn - ride.a.bwx) < 0.5 and math.abs(t.ww - ride.a.bwy) < 0.5, "at the boarding point of the dock", t and (t.wn .. "," .. t.ww))
      local dt, dsrc = S().Arrow:Destination()
      Check(dsrc == "manual" and dt ~= nil and dt.label == "Auberdine", "the destination is still the manual point", dsrc)

      Section("arrive at the dock: no more arrow, the line stays")
      GoTo(0, ride.a.bwx, ride.a.bwy)
      Sim.Advance(3)
      local _, src2 = ArrowTarget()
      Check(src2 == "manual", "arrow back on the destination at the dock", src2)
      Check(TravelLine():find("barco a", 1, true) ~= nil, "the line stays", TravelLine())
      Sim.Advance(10)
      p = Plan()
      Check(p ~= nil and p.legs[1].how == "ride" and Plain(TravelLine()):find("^Camino más rápido: barco a") ~= nil, "replanned from the dock: boat first", p and Hows(p.legs))

      Section("a big graph (every node known) is sliced over many frames")
      Known(AllIds())
      Sim.Advance(1)
      GoTo(0, n2.wx, n2.wy)
      Aim(1, Node(52).wx, Node(52).wy, "Everlook")
      Settle()
      Check(Plan() ~= nil and not Plan().none, "a plan to Everlook")
      Check(T.lastJobFrames >= 4, "the job took several frames", T.lastJobFrames)
      Check(T.maxSliceOps <= 720, "no slice ran more than 720 operations", T.maxSliceOps)
      Sim.Out("    HUD: " .. TravelLine() .. " (" .. T.lastJobFrames .. " frames)")
      Known({ 2 })

      Section("a destination close by needs no plan")
      GoTo(0, ride.a.bwx, ride.a.bwy)
      Aim(0, ride.a.bwx - 300, ride.a.bwy, "Cerca")
      Settle()
      Check(Plan() == nil and not SendaHUD.travel:IsShown(), "under 800 yd: no plan, no line")
      Check(not S().Arrow:Has("travel"), "no travel arrow")

      Section("Forever's new continent (2991) has no reliable yards: no plan")
      Sim.MAPS[9003] = { name = "Continente nuevo (prueba)", parent = 947, type = 2, continent = 2991, n = 4000, w = 4000, sx = 8000, sy = 8000 }
      S().Arrow:SetTarget(9003, 50, 50, "Zona nueva", "manual")
      Settle()
      Check(Plan() == nil and not S().Arrow:Has("travel") and not SendaHUD.travel:IsShown(), "no plan towards continent 2991")

      Section("the manual point is cleared: the plan goes with it")
      Aim(1, n26.wx, n26.wy, "Auberdine")
      GoTo(0, n2.wx, n2.wy)
      Settle()
      Check(Plan() ~= nil and S().Arrow:Has("travel"), "plan again")
      Slash("way clear")
      Settle()
      Check(Plan() == nil and not S().Arrow:Has("travel") and not SendaHUD.travel:IsShown(), "no plan, no arrow, no line")

      Section("/senda viaje")
      Aim(1, n26.wx, n26.wy, "Auberdine")
      Settle()
      local lines = Slash("viaje")
      local joined = Plain(table.concat(lines, "|"))
      Check(joined:find("Camino más rápido: unos", 1, true) ~= nil and joined:find("barco a", 1, true) ~= nil, "prints the plan", joined)
      Slash("viaje help")
      Slash("viaje recalcular")
      Settle()
      Check(Plan() ~= nil, "plan after viaje recalcular")

      Section("the option turns it off")
      S().Options:Set("mod_travel", false)
      Sim.Advance(1)
      Check(Plan() == nil and not S().Arrow:Has("travel"), "travel planner off: no plan")
      S().Options:Set("mod_travel", true)
      Settle()
      Check(Plan() ~= nil, "back on: plan")

      Section("another route: known flights, a far destination on the same continent")
      Slash("way clear")
      Known({ 2, 6, 8 })
      local n8 = Node(8)
      Aim(0, n8.wx, n8.wy, "Thelsamar")
      Settle()
      p = Plan()
      Check(p ~= nil and Has(p.legs, "fly") and TravelLine():find("vuela a", 1, true) ~= nil, "flies to Thelsamar", p and Hows(p.legs))
      Known({})
      Settle()
      p = Plan()
      Check(p ~= nil and not Has(p.legs, "fly") and not (TravelLine():find("vuela", 1, true)), "no known flight: no flight in the line", p and Hows(p.legs))

      Section("in combat the planner pauses")
      Slash("way clear")
      Settle()
      Known({ 2 })
      Aim(1, n26.wx, n26.wy, "Auberdine")
      Sim.player.combat = true
      Sim.Advance(5)
      Check(Plan() == nil, "no plan was computed in combat")
      Sim.player.combat = false
      Sim.Fire("PLAYER_REGEN_ENABLED")
      Settle()
      Check(Plan() ~= nil, "plan once combat ends")
      Check(#Sim.errors == 0, "no Lua errors", #Sim.errors)
    `,
  },
  {
    id: 'travel-taxi',
    title: 'Travel planner: the flight map highlights the destination node and never flies for you; unknown nodes stay out (human mage)',
    char: 'human-mage',
    lua: SETUP + L_`
      Login()
      Sim.Advance(6)
      NoGuide()
      local T = TT()
      local n2, n6, n8 = Node(2), Node(6), Node(8)
      Known({ 2, 6, 8 })
      GoTo(0, n2.wx, n2.wy)
      Aim(0, n8.wx, n8.wy, "Thelsamar")
      Settle()
      Check(select(2, ArrowTarget()) ~= nil, "an arrow target exists")
      local p = Plan()
      Check(p ~= nil and p.legs[1].how == "fly", "the first leg is a flight from where we stand", p and Hows(p.legs))
      Check(T.NextFlightNode() == 8, "the node to fly to is Thelsamar (8)", T.NextFlightNode())
      Section("the flight map opens")
      local pins = {}
      local list = {}
      for _, id in ipairs({ 2, 6, 8 }) do
        local pin = CreateFrame("Frame", nil, UIParent)
        pin.taxiNodeData = { nodeID = id, name = Node(id).name }
        pins[id] = pin
        list[#list + 1] = pin
      end
      FlightMapFrame = {
        IsShown = function() return true end,
        EnumeratePinsByTemplate = function(self, tmpl)
          local i = 0
          return function() i = i + 1; return list[i] end
        end,
      }
      local before = #Sim.chat
      Sim.Fire("TAXIMAP_OPENED", 1)
      Sim.Advance(2)
      Check(pins[8].sendaGlow ~= nil and pins[8].sendaGlow:IsShown(), "Thelsamar's button is highlighted")
      Check(not (pins[2].sendaGlow and pins[2].sendaGlow:IsShown()) and not (pins[6].sendaGlow and pins[6].sendaGlow:IsShown()), "the others are not")
      local chat = ""
      for i = before + 1, #Sim.chat do chat = chat .. Plain(Sim.chat[i]) .. "|" end
      Check(chat:find("lo he marcado en el mapa de vuelos", 1, true) ~= nil, "a chat hint says which node", chat)
      Check(Sim.player.onTaxi == false, "it did not fly for us")
      Check(T.HighlightTaxi() == 1, "HighlightTaxi marks exactly one node")
      Section("the destination changes: the mark follows")
      Known({ 2, 6, 8, 7 })
      local n7 = Node(7)
      Aim(0, n7.wx, n7.wy, "Menethil")
      Settle()
      Check(T.NextFlightNode() ~= nil, "a flight is still the first leg", T.NextFlightNode())
      T.HighlightTaxi()
      local lit = 0
      for id, pin in pairs(pins) do if pin.sendaGlow and pin.sendaGlow:IsShown() then lit = lit + 1 end end
      Check(lit <= 1, "at most one node is marked", lit)
      Section("no destination: nothing is marked")
      Slash("way clear")
      Settle()
      Check(T.HighlightTaxi() == 0, "no highlight without a plan")
      local anyLit = false
      for id, pin in pairs(pins) do if pin.sendaGlow and pin.sendaGlow:IsShown() then anyLit = true end end
      Check(not anyLit, "all marks cleared")
      Section("classic taxi frame: buttons matched by name")
      TaxiFrame = { IsShown = function() return true end }
      FlightMapFrame = nil
      local names = { "Stormwind, Elwynn", "Ironforge, Dun Morogh", "Thelsamar, Loch Modan" }
      function NumTaxiNodes() return 3 end
      function TaxiNodeName(i) return names[i] end
      for i = 1, 3 do _G["TaxiButton" .. i] = CreateFrame("Frame", nil, UIParent) end
      Aim(0, n8.wx, n8.wy, "Thelsamar")
      Settle()
      Check(T.HighlightTaxi() == 1 and TaxiButton3.sendaGlow:IsShown() and not (TaxiButton1.sendaGlow and TaxiButton1.sendaGlow:IsShown()), "classic: Thelsamar's button")
      Check(#Sim.errors == 0, "no Lua errors", #Sim.errors)
    `,
  },
  {
    id: 'travel-lock',
    title: 'Travel planner: hearthstone (bind, cooldown, bound at an innkeeper) and walking speed (gnome warlock)',
    char: 'gnome-warlock',
    lua: SETUP + L_`
      Login()
      Sim.Advance(6)
      NoGuide()
      local T = TT()
      local sw = Node(2)
      Section("walking speed from knowledge")
      Check(T.SpeedFactor() == 1, "no mount: 1", T.SpeedFactor())
      Sim.LearnSpell(5784)
      Check(T.SpeedFactor() == 1.6, "Summon Felsteed: 60 %", T.SpeedFactor())
      Sim.LearnSpell(23161)
      Check(T.SpeedFactor() == 2.0, "Summon Dreadsteed: 100 %", T.SpeedFactor())
      Sim.player.spells[5784], Sim.player.spells[23161] = nil, nil
      Section("bound by name: the client's own area name for the inn")
      Sim.areaNames[1519] = "Ciudad de Ventormenta"
      Sim.player.bind = "Ciudad de Ventormenta"
      Check(T.BoundInn() ~= nil and T.BoundInn().area == 1519, "the bind location is the Stormwind inn", T.BoundInn() and T.BoundInn().area)
      Sim.player.bind = "Kharanos"
      Sim.Fire("HEARTHSTONE_BOUND")
      Sim.Advance(1)
      Check(T.BoundInn() ~= nil and T.BoundInn().area == 2102, "English data name: Kharanos is the Thunderbrew inn", T.BoundInn() and T.BoundInn().area)
      Section("bound at an innkeeper: the position teaches which inn a Spanish name means")
      local gold = Inn(87)
      GoTo(0, gold.p.wx + 10, gold.p.wy + 5)
      Sim.player.bind = "Villadorada"
      Check(T.BoundInn() == nil, "an unknown name matches no inn yet")
      Sim.Fire("HEARTHSTONE_BOUND")
      Sim.Advance(1)
      Check(T.BoundInn() ~= nil and T.BoundInn().area == 87, "after binding next to the Goldshire inn it is that one", T.BoundInn() and T.BoundInn().area)
      Check(S().db.char.travel.inn["villadorada"] == 295, "remembered per character (innkeeper 295)", S().db.char.travel.inn["villadorada"])

      Section("hearthstone in the plan: bound in Stormwind, standing far away")
      local sw_inn = Inn(1519).p
      GoTo(0, sw_inn.wx + 5, sw_inn.wy)
      Sim.player.bind = "Ciudad de Ventormenta"
      Sim.Fire("HEARTHSTONE_BOUND")
      Sim.Advance(1)
      Check(S().db.char.travel.inn["ciudad de ventormenta"] == 6740, "bound next to the Stormwind inn: innkeeper 6740", S().db.char.travel.inn["ciudad de ventormenta"])
      Known({ 2, 14 })
      local south = Inn(271).p
      GoTo(0, south.wx, south.wy)
      Aim(0, sw_inn.wx, sw_inn.wy, "Posada de Ventormenta")
      Settle()
      local p = Plan()
      Check(p ~= nil and p.legs ~= nil and p.legs[1].how == "hearth", "first leg: hearthstone", p and Hows(p.legs))
      local line = TravelLine()
      Sim.Out("    HUD: " .. line)
      Check(line:find("^Camino más rápido: piedra de hogar a Ciudad de Ventormenta") ~= nil, "HUD: piedra de hogar a Ciudad de Ventormenta", line)
      Check(not S().Arrow:Has("travel"), "no arrow to walk to: the hearth is cast where you stand")
      Section("on cooldown: the hearth is not offered")
      Sim.cooldowns.items[6948] = 3000
      Sim.Fire("BAG_UPDATE_DELAYED")
      Sim.Advance(12)
      Settle()
      p = Plan()
      Check(p ~= nil and p.legs ~= nil and not Has(p.legs, "hearth") and (Has(p.legs, "fly") or Has(p.legs, "ride")), "boats and flights instead", p and Hows(p.legs))
      Check(TravelLine():find("piedra de hogar", 1, true) == nil, "the line does not mention the hearthstone", TravelLine())
      Sim.cooldowns.items[6948] = 0
      Sim.Fire("BAG_UPDATE_DELAYED")
      Sim.Advance(12)
      Settle()
      p = Plan()
      Check(p ~= nil and p.legs ~= nil and p.legs[1].how == "hearth", "off cooldown again: the hearth is back", p and Hows(p.legs))
      Section("no hearthstone in the bags")
      Sim.player.bags[0][1] = nil
      for slot, it in pairs(Sim.player.bags[0]) do if it.id == 6948 then Sim.player.bags[0][slot] = nil end end
      Sim.Fire("BAG_UPDATE_DELAYED")
      Sim.Advance(12)
      Settle()
      p = Plan()
      Check(p ~= nil and p.legs ~= nil and not Has(p.legs, "hearth"), "without the item no hearth", p and Hows(p.legs))
      Check(#Sim.errors == 0, "no Lua errors", #Sim.errors)
    `,
  },
  {
    id: 'travel-druid',
    title: 'Travel planner: teleports need the spell and the reagent; travel form speeds walking; flight paths read from the world map (night elf druid)',
    char: 'nightelf-druid',
    lua: SETUP + L_`
      Login()
      Sim.Advance(6)
      NoGuide()
      local T = TT()
      Section("travel form")
      Check(T.SpeedFactor() == 1, "no travel form: 1", T.SpeedFactor())
      Sim.LearnSpell(783)
      Check(T.SpeedFactor() == 1.4, "Travel Form: +40 %", T.SpeedFactor())
      Section("Teleport: Moonglade, only with the spell")
      local sw = Inn(1519).p
      local nh = Node(62)
      GoTo(0, sw.wx, sw.wy)
      Known({ 2, 49 })
      Aim(1, nh.wx, nh.wy, "Nighthaven")
      Settle()
      local p = Plan()
      Check(p ~= nil and not Has(p.legs, "teleport"), "without the spell: no teleport", p and Hows(p.legs))
      Sim.LearnSpell(18960)
      Sim.SPELL_NAMES[18960] = "Teletransporte: Claros de la Luna"
      Settle()
      p = Plan()
      Check(p ~= nil and p.legs ~= nil and Has(p.legs, "teleport", 18960), "with the spell: Teleport: Moonglade", p and Hows(p.legs))
      Check(TravelLine():find("Teletransporte: Claros de la Luna", 1, true) ~= nil, "HUD names the spell as the client does", TravelLine())
      Sim.cooldowns.spells[18960] = 1500
      Sim.Fire("SPELLS_CHANGED")
      Sim.Advance(12)
      Settle()
      p = Plan()
      Check(p ~= nil and p.legs ~= nil and not Has(p.legs, "teleport"), "on cooldown (25 min): not offered", p and Hows(p.legs))
      Section("flight paths read from the world map without opening a flight master")
      Sim.cooldowns.spells[18960] = 0
      Slash("way clear")
      Sim.areaNames[1519] = "Ciudad de Ventormenta"
      S().db.char.fps = {}
      S().db.char.travel = nil
      Sim.taxiWorld = {}
      for _, id in ipairs({ 2, 6, 8, 12 }) do Sim.taxiWorld[id] = { map = Node(id).map, name = "Nodo " .. id .. ", Zona", known = (id == 2 or id == 6) } end
      T.ScanTaxi()
      Sim.Advance(3)
      local known = T.KnownNodes()
      Check(known[2] and known[6] and not known[8] and not known[12], "discovered nodes 2 and 6 are known; 8 and 12 are not")
      Check(S().db.char.travel.names[2] == "Nodo 2, Zona", "the client's name is kept for display")
      Section("a client that marks no node as undiscovered is not trusted")
      S().db.char.travel = nil
      for _, n in pairs(Sim.taxiWorld) do n.known = true end
      T.ScanTaxi()
      Sim.Advance(3)
      local k2 = 0
      for _ in pairs(T.KnownNodes()) do k2 = k2 + 1 end
      Check(k2 == 0, "nothing learned from an all-discovered answer", k2)
      Check(#Sim.errors == 0, "no Lua errors", #Sim.errors)
    `,
  },
  {
    id: 'travel-mage',
    title: 'Travel planner: mage teleport needs the spell and the Rune of Teleportation; plan through the real context (human mage)',
    char: 'human-mage',
    lua: SETUP + L_`
      Login()
      Sim.Advance(6)
      NoGuide()
      local T = TT()
      local sw = Inn(1519).p
      local dar = Inn(1659).p
      GoTo(0, sw.wx, sw.wy)
      Known({ 2 })
      Aim(1, dar.wx, dar.wy, "Darnassus")
      Settle()
      local p = Plan()
      Check(p ~= nil and p.legs ~= nil and not Has(p.legs, "teleport"), "no spell: no teleport", p and Hows(p.legs))
      Sim.LearnSpell(3565)
      Sim.SPELL_NAMES[3565] = "Teletransporte: Darnassus"
      Settle()
      p = Plan()
      Check(p ~= nil and p.legs ~= nil and not Has(p.legs, "teleport"), "the spell but no Rune of Teleportation: no teleport", p and Hows(p.legs))
      Sim.player.bags[0][20] = { id = 17031, count = 2 }
      Sim.Fire("BAG_UPDATE_DELAYED")
      Sim.Advance(12)
      Settle()
      p = Plan()
      Check(p ~= nil and p.legs ~= nil and Has(p.legs, "teleport", 3565), "spell + rune: Teleport: Darnassus", p and Hows(p.legs))
      local line = TravelLine()
      Sim.Out("    HUD: " .. line)
      Check(line:find("^Camino más rápido: Teletransporte: Darnassus") ~= nil, "HUD names it first", line)
      Check(not S().Arrow:Has("travel"), "no arrow to walk to for a teleport")
      Section("other faction's teleport is never used")
      Sim.LearnSpell(3563)
      Sim.player.bags[0][21] = { id = 17031, count = 2 }
      Sim.Fire("BAG_UPDATE_DELAYED")
      local ctx = T.Context()
      local hordeTele = false
      for _, t in ipairs(ctx.teleports) do if t.spell == 3563 then hordeTele = true end end
      Check(not hordeTele, "Teleport: Undercity is Horde-only: not in an Alliance context")
      Check(ctx.mask == 1 and ctx.class == "MAGE", "context: Alliance mage", ctx.mask .. " " .. tostring(ctx.class))
      Check(#Sim.errors == 0, "no Lua errors", #Sim.errors)
    `,
  },
];

module.exports = { scenarios };

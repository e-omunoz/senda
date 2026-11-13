'use strict';
// Scenarios of gathering and fishing on the Professions tab (addon/Senda/Modules/Gathering.lua + the data of
// data/knowledge/general/professions-{herbalism,mining,skinning,fishing}.toml and gathering-route.toml, compiled
// to addon/Senda/Knowledge/general.lua). Loaded by run.js.

const L_ = String.raw;

const scenarios = [
  {
    id: 'gathering-druid',
    title: 'Gathering: night elf druid with Herbalism 40 sees the zones of her guide, colours and the right trainer',
    char: 'nightelf-druid',
    lua: L_`
      local c = Sim.CHARS["nightelf-druid"]
      c.level = 12
      c.profs = { { name = "Herboristería", skillLine = 182, rank = 40, max = 75 } }
      Login()
      Sim.Advance(1)
      local G = S().Modules.Gathering
      Check(G ~= nil and G.RouteZones ~= nil, "Senda.Modules.Gathering exists")

      Section("pure rules")
      Check(G.Color(40, 50) == "red", "skill below the node: red")
      Check(G.Color(60, 50) == "orange" and G.Color(80, 50) == "yellow" and G.Color(120, 50) == "green" and G.Color(150, 50) == "grey",
        "orange < req+25, yellow < req+50, green < req+100, grey after")

      Section("data from the knowledge pages")
      local d = G.Data()
      Check(d.zones.herbalism and d.zones.herbalism[1438] ~= nil, "Teldrassil herb zone is loaded")
      Check(d.zones.herbalism[1439] ~= nil, "Darkshore herb zone is loaded")
      local st = G.ZoneState("herbalism", d.zones.herbalism[1438], 40)
      Check(st.status == "good", "Teldrassil at skill 40: good", st.status)
      st = G.ZoneState("herbalism", d.zones.herbalism[1438], 190)
      Check(st.status == "grey", "Teldrassil at skill 190: nothing gives skill any more", st.status)
      st = G.ZoneState("herbalism", d.zones.herbalism[1439], 1)
      Check(st.status ~= "good" or st.counts.red > 0, "Darkshore at skill 1 has red nodes", st.status)

      Section("route of the druid guide")
      local guide, section = G.Current()
      Check(guide == "nightelf-druid", "current guide", tostring(guide))
      local zones = G.RouteZones("herbalism", guide, section, 12, 40)
      Check(#zones >= 2, "at least two route zones", #zones)
      Check(zones[1].map == 1438, "the first route zone is Teldrassil (her starting area)", zones[1] and zones[1].map)
      local maps = {}
      for _, z in ipairs(zones) do maps[z.map] = true end
      Check(maps[1439], "Darkshore (Costa Oscura) comes next on her route")
      Check(zones[1].state.status == "good", "Teldrassil is still good at 40")

      Section("fallen behind: the route zone turns red or grey")
      local far = G.RouteZones("herbalism", guide, section, 12, 190)
      Check(far[1] and far[1].state.status == "grey", "at skill 190 Teldrassil is grey", far[1] and far[1].state.status)
      local low = G.RouteZones("herbalism", guide, "ne-darkshore", 12, 1)
      Check(low[1] and (low[1].state.counts.red > 0), "Darkshore has red nodes at skill 1", low[1] and low[1].map)

      Section("trainer of her faction, no character level")
      local tr = G.Trainer("herbalism", "Oficial")
      Check(tr ~= nil and tr[4] ~= nil, "an Alliance herbalism trainer with coordinates", tr and tr[4])
      local P = S().Modules.Professions
      local ps = P.State("herbalism", 12)
      Check(ps.rank == 40 and ps.max == 75, "Professions.State keeps working", tostring(ps.rank))
      Check(ps.capped == nil, "no 'asks character level' cap for gathering ranks")
      ps = P.State("herbalism", 12)
      Check(ps.trainer ~= nil and ps.trainer[1] ~= nil, "state carries a trainer", ps.trainer and ps.trainer[4])

      Section("the Professions tab shows the section")
      S().UI:ShowPanel(); S().UI:ShowTab("professions"); Sim.Advance(1)
      P.Refresh(); Sim.Advance(0.5)
      local seen = {}
      for _, f in ipairs(Sim.AllWidgets()) do
        if f.__type == "FontString" and f:IsVisible() then seen[#seen + 1] = f:GetText() or "" end
      end
      local all = table.concat(seen, "\n")
      Check(all:find("recoger", 1, true) ~= nil, "section header (recoger)")
      Check(all:find("En tu ruta", 1, true) ~= nil, "'En tu ruta' line")
      Check(all:find("Teldrassil", 1, true) ~= nil, "Teldrassil listed", all:sub(1, 200))
      Check(all:find("Te acercas al tope", 1, true) == nil, "no bogus 'asks level' cap warning")
    `,
  },
  {
    id: 'gathering-mage-fishing',
    title: 'Gathering: human mage with Mining and Fishing: Elwynn first, fishing water rule, hook skipped without learned professions',
    char: 'human-mage',
    lua: L_`
      local c = Sim.CHARS["human-mage"]
      c.level = 8
      c.profs = { { name = "Minería", skillLine = 186, rank = 30, max = 75 }, { name = "Pesca", skillLine = 356, rank = 60, max = 75 } }
      Login()
      Sim.Advance(1)
      local G = S().Modules.Gathering
      local learned = G.Learned()
      local have = {}
      for _, p in ipairs(learned) do have[p.key] = p.rank end
      Check(have.mining == 30 and have.fishing == 60, "learned gathering professions detected", tostring(have.mining) .. "/" .. tostring(have.fishing))
      local guide, section = G.Current()
      local mz = G.RouteZones("mining", guide, section, 8, 30)
      Check(mz[1] and mz[1].map == 1429, "mage mining starts in Elwynn", mz[1] and mz[1].map)
      local d = G.Data()
      local fz = d.zones.fishing and d.zones.fishing[1429]
      Check(fz ~= nil and fz.full == 25, "Elwynn water loses no fish from skill 25")
      Check(G.ZoneState("fishing", fz, 60).status == "good", "fishing at 60 in Elwynn: good")
      Check(G.ZoneState("fishing", d.zones.fishing[1434], 60).status == "lost", "Stranglethorn water loses fish at skill 60")
      local b = G.Bracket("mining", 30)
      Check(b and b.zones[1] ~= nil, "a mining bracket for skill 30 with zones", b and b.from)
      local nodes = G.Nodes(8)
      Check(#nodes >= 4, "section nodes for two learned professions", #nodes)
      -- A character with no gathering profession gets nothing
      local g2 = S().Modules.Gathering
      Check(g2.IS.herbalism and not g2.IS.tailoring, "only gathering professions are handled")
    `,
  },
  {
    id: 'gathering-warlock-none',
    title: 'Gathering: warlock without gathering professions: the tab is untouched',
    char: 'gnome-warlock',
    lua: L_`
      Login()
      Sim.Advance(1)
      local G = S().Modules.Gathering
      Check(#G.Learned() == 0, "no gathering professions learned")
      Check(#G.Nodes(1) == 0, "no extra nodes")
      S().UI:ShowPanel(); S().UI:ShowTab("professions"); Sim.Advance(1)
      S().Modules.Professions.Refresh(); Sim.Advance(0.5)
      Check(true, "Professions.Refresh works with the hook and nothing learned")
    `,
  },
];

module.exports = { scenarios };

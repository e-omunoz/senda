'use strict';
// Scenarios of the flight-point step filters (if.fp / if.nofp, Engine/Conditions.lua) on the real Wetlands entry
// (data/shared/a26-los-humedales.toml): a character that does not know Thelsamar (node 8) must not be told to
// fly there. Loaded by run.js.

const L_ = String.raw;

const GO = L_`
  Login()
  local E = S().Engine
  Sim.player.level = 26
  Sim.Fire("PLAYER_LEVEL_UP", 26, 0, 0, 0, 0, 0, 0, 0, 0)
  Sim.Advance(1)
  function Know(ids)
    local fps = {}
    for _, id in ipairs(ids) do fps[id] = "Nodo " .. id end
    S().db.char.fps = fps
    S().Events:Fire("SENDA_TRAVEL_UPDATED")
  end
  function Jump(id) E:JumpTo(StepIndexOf(id)); Sim.Advance(1) end
  function App(id) return E:IsApplicable(E:Steps()[StepIndexOf(id)]) end
`;

const scenarios = [
  {
    id: 'fpf-a',
    title: 'Gnome warlock with flight points 2,4,5,6: no "Vuela a Thelsamar", the getfp walking step instead',
    char: 'gnome-warlock',
    lua: GO + L_`
      Know({ 2, 4, 5, 6 })
      Sim.Advance(1)
      Check(StepIndexOf("a26wl-004") ~= nil, "a26wl-004 is in the gnome warlock guide")
      Check(not App("a26wl-004"), "the fly step is not applicable without node 8")
      Check(App("a26wl-ne-01") and App("a26wl-ne-02"), "the getfp steps are applicable for a gnome")
      Jump("a26wl-002"); E:Advance(); Sim.Advance(1)
      Check(StepId() == "a26wl-ne-02", "the route shows the Thelsamar getfp (Ironforge one auto-completes)", StepId())
      Check(Plain(HudText()):find("Vuela a Thelsamar", 1, true) == nil, "HUD does not say fly to Thelsamar", Plain(HudText()))
      Check(Plain(HudText()):find("Thelsamar", 1, true) ~= nil, "HUD names Thelsamar", Plain(HudText()))
      Section("Without Ironforge either, the first stop is the Ironforge flight master")
      Know({ 2, 4, 5 })
      Jump("a26wl-ne-01")
      Check(StepId() == "a26wl-ne-01", "Ironforge getfp is shown", StepId())
      Check(#Sim.apiErrors == 0, "no API errors")
    `,
  },
  {
    id: 'fpf-b',
    title: 'Gnome warlock with node 8 known: fly step shown, the getfp steps auto-complete; learning it live re-evaluates',
    char: 'gnome-warlock',
    lua: GO + L_`
      Know({ 2, 4, 5, 6, 8 })
      Sim.Advance(1)
      Check(App("a26wl-004"), "the fly step is applicable with node 8")
      Check(not App("a26wl-ne-01"), "the Ironforge getfp (nofp 8) is hidden")
      Jump("a26wl-002"); E:Advance(); Sim.Advance(1)
      Check(StepId() == "a26wl-004", "the fly step is the current one", StepId())
      local C = S().Conditions
      Check(C:Check(E:Steps()[StepIndexOf("a26wl-ne-02")].step, {}) == true, "getfp Thelsamar auto-completes (known)")
      Check(C:Check(E:Steps()[StepIndexOf("a26wl-ne-01")].step, {}) == true, "getfp Ironforge auto-completes (known)")
      Section("the player learns Thelsamar while on the walking step")
      Know({ 2, 4, 5, 6 })
      Sim.Advance(1)
      Check(StepId() == "a26wl-ne-02", "walking step current again", StepId())
      S().db.char.fps[8] = "Thelsamar, Loch Modan"
      S().Events:Fire("SENDA_TRAVEL_UPDATED")
      Sim.Advance(2)
      Check(StepId() ~= "a26wl-ne-02", "the route moved on once node 8 is known", StepId())
      Check(#Sim.apiErrors == 0, "no API errors")
    `,
  },
  {
    id: 'fpf-c',
    title: 'Human mage: same filter, same Wetlands entry; filter by node name',
    char: 'human-mage',
    lua: GO + L_`
      Know({ 2, 4, 5 })
      Sim.Advance(1)
      Check(not App("a26wl-004"), "mage: no fly step without node 8")
      Check(App("a26wl-ne-01") and App("a26wl-ne-02"), "mage: walking getfp steps")
      Know({ 2, 4, 5, 6, 8 })
      Check(App("a26wl-004"), "mage: fly step with node 8")
      Section("by node name too")
      local C = S().Conditions
      S().db.char.fps = { [8] = "Thelsamar, Loch Modan" }
      Check(C:FpFilter({ fp = { "Thelsamar" } }) == true, "fp by name matches")
      Check(C:FpFilter({ nofp = { "Thelsamar" } }) == false, "nofp by name hides it")
      Check(C:FpFilter({ fp = { "8" }, nofp = { "6" } }) == true, "fp 8 known and nofp 6 unknown")
      Check(C:FpFilter({}) == true and C:FpFilter(nil) == true, "no filter: always shown")
      Check(#Sim.apiErrors == 0, "no API errors")
    `,
  },
  {
    id: 'fpf-e2e',
    title: 'The reported case end to end: gnome warlock 21 in Darkshire, flight points 2,4,5,6, on a26wl-004: the guide sends to Thelsamar on foot, the planner never walks over the Dun Morogh mountains (real map frames)',
    char: 'gnome-warlock',
    lua: GO + L_`
      -- the real Forever map frames (forever-db ui_map.jsonl) of the zones on the way, so map percent and world yards
      -- agree with the travel data and the walk graph
      local FR = {
        [1431] = { "Bosque del Ocaso", -9716.666, -11516.666, 833.333, -1866.667 },
        [1433] = { "Montañas Crestagrana", -8575, -10022.916, -1681.25, -3852.084 },
        [1429] = { "Bosque de Elwynn", -7939.583, -10254.166, 1535.417, -1935.417 },
        [1453] = { "Ventormenta", -7995.83, -9154.17, 1722.92, -14.584 },
        [1426] = { "Dun Morogh", -3877.083, -7160.417, 1802.083, -3122.917 },
        [1455] = { "Forjaz", -4569.241, -5096.846, -713.591, -1504.216 },
        [1432] = { "Loch Modan", -4487.5, -6327.083, -1993.75, -4752.083 },
        [1437] = { "Los Humedales", -2147.917, -4904.167, -389.583, -4525 },
      }
      for id, f in pairs(FR) do
        local m = Sim.MAPS[id] or { parent = 1415, type = 3 }
        m.name, m.continent, m.n, m.sy, m.w, m.sx = f[1], 0, f[2], f[2] - f[3], f[4], f[4] - f[5]
        Sim.MAPS[id] = m
      end
      local T = S().Modules.Travel
      local D = T.Data()
      local function Node(id) return D.nodes[id] end
      local function Place(map, wn, ww)
        local m = Sim.MAPS[map]
        Sim.MoveTo(map, (m.w - ww) / m.sx, (m.n - wn) / m.sy)
      end
      local function KnowN(ids)
        local fps = {}
        for _, id in ipairs(ids) do fps[id] = Node(id).name end
        S().db.char.fps = fps
        T.MarkDirty("test")
        S().Events:Fire("SENDA_TRAVEL_UPDATED")
      end
      local function Legs(r)
        local out = {}
        for _, l in ipairs(r and r.legs or {}) do
          local what = l.how
          if l.how == "fly" then what = "fly " .. table.concat(l.nodes, ">") end
          if l.how == "ride" then what = l.id end
          if l.how == "walk" then what = string.format("walk %d yd (%s -> %s)", l.yards or 0, l.from.name or "?", l.to.name or "?") end
          out[#out + 1] = what .. string.format(" %.0fs", l.secs)
        end
        return table.concat(out, " | ")
      end
      -- every walk leg at least its straight line, and no walk leg that leaves the Ironforge flight master for
      -- Loch Modan or the Wetlands shorter than the tunnel (2900 yd to Thelsamar)
      local function Sane(r)
        for _, l in ipairs(r and r.legs or {}) do
          if l.how == "walk" then
            local s = math.sqrt((l.from.wx - l.to.wx) ^ 2 + (l.from.wy - l.to.wy) ^ 2)
            if l.yards < s * 0.98 then return false, "walk shorter than its straight line" end
            if l.from.fp == 6 and l.yards < 2500 then return false, "walk from Ironforge over the mountains" end
          end
        end
        return true
      end
      local function Show(label)
        Sim.Advance(4)
        local p = T.GetPlan()
        local at, src = ArrowTarget()
        Sim.Out(string.format("    [%s] step %s | HUD: %s", label, tostring(StepId()), Plain(HudText()):gsub("\n", " / ")))
        Sim.Out("      travel: " .. Plain(SendaHUD.travel:GetText() or ""))
        Sim.Out("      legs: " .. (p and not p.none and Legs(p) or "-"))
        Sim.Out("      arrow: " .. tostring(src) .. " " .. (at and Plain(at.label or at.title or "") or "-"))
        return p
      end

      Sim.player.level = 21
      Sim.Fire("PLAYER_LEVEL_UP", 21, 0, 0, 0, 0, 0, 0, 0, 0)
      Sim.player.bind = "Darkshire"
      Sim.Fire("HEARTHSTONE_BOUND")
      KnowN({ 2, 4, 5, 6 })
      local dk = Node(12)
      Place(1431, dk.wx - 30, dk.wy)
      Sim.Advance(2)

      Section("saved on a26wl-004 (Vuela a Thelsamar) without the Thelsamar node")
      Jump("a26wl-004")
      S().Engine:Evaluate("test")
      Sim.Advance(2)
      local p = Show("a26wl-004")
      Check(StepId() == "a26wl-ne-02", "the engine leaves the fly step for the walking getfp to Thelsamar", StepId())
      Check(Plain(HudText()):find("Vuela a Thelsamar", 1, true) == nil, "no «Vuela a Thelsamar»", Plain(HudText()))
      Check(p ~= nil and not p.none and #p.legs > 0, "a plan to Thelsamar", p and Legs(p))
      local ok, why = Sane(p)
      Check(ok, "no walk over the mountains on the way to Thelsamar", why)
      local tunnel
      for _, l in ipairs(p and p.legs or {}) do if l.how == "walk" and l.to.fp == nil and l.from.fp == 6 then tunnel = l end end
      Check(tunnel == nil or tunnel.yards > 2500, "Ironforge -> Thelsamar on foot goes through the tunnel", tunnel and tunnel.yards)
      -- there is no land way from Duskwood to Loch Modan (the Searing Gorge gate is closed): fly to Ironforge first
      local toIF = false
      for _, l in ipairs(p and p.legs or {}) do if l.how == "fly" and l.toId == 6 then toIF = true end end
      Check(toIF, "flies to Ironforge (no walk from Duskwood over the Burning Steppes and the Searing Gorge)", p and Legs(p))
      Check(Plain(SendaHUD.travel:GetText() or ""):find("Ironforge", 1, true) ~= nil, "the HUD travel line names Ironforge", Plain(SendaHUD.travel:GetText() or ""))

      Section("arrives at Thelsamar and learns the node; on to Menethil through Dun Algaz")
      local th = Node(8)
      Place(1432, th.wx - 20, th.wy)
      S().db.char.fps[8] = th.name
      T.MarkDirty("test")
      S().Events:Fire("SENDA_TRAVEL_UPDATED")
      Sim.Advance(2)
      Jump("a26wl-009")
      p = Show("a26wl-009 from Thelsamar")
      ok, why = Sane(p)
      Check(ok, "Thelsamar -> Menethil: sane walk legs", why)
      local hasFly = false
      for _, l in ipairs(p and p.legs or {}) do if l.how == "fly" then hasFly = true end end
      Check(not hasFly, "no flight from Thelsamar to Menethil (the node is unknown)", p and Legs(p))

      Section("the reported plan: Menethil (a26wl-009) straight from Darkshire with 2,4,5,6")
      KnowN({ 2, 4, 5, 6 })
      Place(1431, dk.wx - 30, dk.wy)
      Sim.Advance(2)
      Jump("a26wl-009")
      p = Show("a26wl-009 from Darkshire")
      ok, why = Sane(p)
      Check(ok, "Darkshire -> Menethil: no straight walk from Ironforge", why)
      Check(#Sim.errors == 0, "no Lua errors", #Sim.errors)
      Check(#Sim.apiErrors == 0, "no API errors")
    `,
  },
];

module.exports = { scenarios };

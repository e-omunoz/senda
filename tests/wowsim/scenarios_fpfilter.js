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
];

module.exports = { scenarios };

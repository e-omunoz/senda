'use strict';
// Scenarios of the arrow on real walking paths (addon/Senda/UI/ArrowNav.lua + the real addon/Senda_Nav).
// The continent packs are synthetic (tests/wowsim/mock/nav.lua): one sector of 64x64 cells around the
// character's start, in the real pack format, with a wall (local column 32, rows 0-47) so the walk from
// the west side to the east side has to go round its south end (rows 48-63). Loaded by run.js.

const L_ = String.raw;

// Shared Lua: the wall, a pack around (map, x, y) and helpers to read the arrow.
const PRELUDE = L_`
  local function Wall(lx, ly) return lx == 32 and ly <= 47 end
  function NavPackAt(map, x, y) return Sim.NavPack(map, x, y, { blocked = Wall }) end
  function NavGo(D, lx, ly)
    local x, y = Sim.NavPoint(D, lx, ly)
    Sim.MoveTo(D.info.map, x, y)
  end
  function NavTarget(D, lx, ly, label, source)
    local x, y = Sim.NavPoint(D, lx, ly)
    S().Arrow:SetTarget(D.info.map, x * 100, y * 100, label or "Destino", source or "manual")
  end
  function NavState() return S().ArrowNav.state end
  -- Advances frame by frame until the route is in (or the time runs out); returns the frames it took.
  function NavWait(maxSec)
    local frames = 0
    while frames * Sim.FRAME < (maxSec or 5) do
      Sim.Advance(Sim.FRAME)
      frames = frames + 1
      local st = NavState()
      if st.status ~= "routing" and st.status ~= "idle" then break end
    end
    return frames
  end
  -- Rotation the arrow should show to aim at world point (n, w) from the player (facing 0 in the mock).
  function AimAt(n, w)
    local map, x, y = S().Compat.PlayerMapPos()
    local _, pn, pw = S().Compat.WorldPos(map, x, y)
    return math.atan2(w - pw, n - pn)
  end
  function StraightAim()
    local t = ArrowTarget()
    return AimAt(t.wn, t.ww)
  end
  function Near(a, b, tol) return a and b and math.abs(a - b) <= (tol or 1e-6) end
  function LoadsOf(name)
    local n, inCombat = 0, 0
    for _, l in ipairs(Sim.addonLoads) do
      if l.name == name then n = n + 1; if l.combat then inCombat = inCombat + 1 end end
    end
    return n, inCombat
  end
  function ArrowInfo() return Plain(SendaArrow.info:GetText()) end
`;

const scenarios = [
  {
    id: 'nav-route',
    title: 'Real paths: the arrow asks for a route, points at its waypoints and follows them to the target',
    char: 'gnome-warlock',
    lua: PRELUDE + L_`
      Sim.profileTick = 0.02 -- the router really spans frames
      local D = NavPackAt(1426, 0.300, 0.715)
      Sim.EnableNav({ [0] = D })
      Login()
      local L, N = S().L, S().ArrowNav
      Check(S().Options:Get("navPaths") == true, "option «Seguir caminos reales» is on by default")
      Check(LoadsOf("Senda_Nav") == 1 and LoadsOf("Senda_Nav_EK") == 1, "the guide target on this continent loads Senda_Nav and the EK pack once",
        LoadsOf("Senda_Nav") .. "/" .. LoadsOf("Senda_Nav_EK"))
      Check(LoadsOf("Senda_Nav_Kalimdor") == 0, "Kalimdor's pack is not loaded in the Eastern Kingdoms")
      Check(SendaNav and SendaNav.IsLoaded(0), "SendaNav has the EK pack")

      Section("target across the wall")
      NavGo(D, 10, 10)
      Sim.Advance(0.5)
      local before = NavState().requests
      NavTarget(D, 54, 10, "Al otro lado")
      Sim.Advance(Sim.FRAME)
      Check(NavState().status == "routing", "a route is requested for the new target", NavState().status)
      Check(NavState().requests == before + 1, "exactly one request", NavState().requests - before)
      Check(ArrowInfo():find(L.ARROW_MODE_PATH, 1, true) == nil, "no «Ruta a pie» while it computes")
      Check(Near(SendaArrow.goal, StraightAim()), "straight arrow while the route computes")
      Check(ArrowInfo():find(L.ARROW_MODE_LINE, 1, true) == 1 and ArrowInfo():find(L.ARROW_WHY_routing, 1, true) ~= nil,
        "«Línea recta» with «calculando la ruta…» while it computes", ArrowInfo())
      local frames = NavWait(10) + 1
      local st = NavState()
      Check(st.status == "ok" and st.path ~= nil, "the route arrives", st.status .. " " .. tostring(st.why))
      Check(frames > 2, "the search was spread over several frames", frames)
      Sim.Advance(Sim.FRAME)
      local path = st.path
      local deep = 0
      for _, p in ipairs(path) do deep = math.max(deep, p.gy - D.info.gy0) end
      Check(#path >= 3, "the path has turns (" .. #path .. " points)")
      Check(deep >= 48, "the path goes round the south end of the wall", deep)
      local wp = path[st.idx]
      Check(st.shown and st.idx == 2, "the arrow follows the path's first waypoint", st.idx)
      Check(Near(SendaArrow.goal, AimAt(st.aimN, st.aimW)), "the arrow aims at the look-ahead point on the path, not at the target")
      do
        local map0, x0, y0 = S().Compat.PlayerMapPos()
        local _, pn0, pw0 = S().Compat.WorldPos(map0, x0, y0)
        local dc = math.sqrt((st.aimN - pn0) ^ 2 + (st.aimW - pw0) ^ 2)
        Check(dc <= 15.01, "the look-ahead point is at most 15 yd ahead", string.format("%.1f", dc))
      end
      Check(not Near(SendaArrow.goal, StraightAim(), 0.2), "...which is not the straight direction")
      Sim.Advance(1)
      Check(Near(SendaArrow.arrow:GetRotation(), SendaArrow.goal, 0.02), "the arrow's turn settles on the aim (smoothed)")
      Check(SendaArrow.direct:IsShown(), "the small gold arrow marks the straight line")
      Check(ArrowInfo():find(L.ARROW_MODE_PATH, 1, true) == 1, "the text says «Ruta a pie»", ArrowInfo())
      Check(#S().MinimapRoute.lines > 0, "the route is drawn on the minimap", #S().MinimapRoute.lines)
      local t = ArrowTarget()
      local map, x, y = S().Compat.PlayerMapPos()
      local straight = select(3, S().Compat.WorldDistance(map, x, y, t.map, t.x, t.y))
      Check(st.along > straight * 1.3, "the distance is along the path, longer than the straight line",
        string.format("%.0f yd vs %.0f yd", st.along, straight))
      Sim.Hover(SendaArrow)
      Check(true, "the arrow's tooltip with the path line runs")

      Section("follow the waypoints")
      local requests = st.requests
      local lastIdx, back = st.idx, false
      for i = 2, #path do
        Sim.MoveTo(path[i].map, path[i].x / 100, path[i].y / 100)
        Sim.Advance(0.1)
        if NavState().idx and NavState().idx < lastIdx then back = true end
        lastIdx = NavState().idx or lastIdx
      end
      Check(not back, "the waypoint index only moves forward")
      Check(lastIdx == #path, "the last waypoint is reached", lastIdx .. "/" .. #path)
      Check(NavState().requests == requests, "walking the path never asks for another route", NavState().requests - requests)
      Check(SendaArrow.check:IsShown() and ArrowInfo() == L.ARROW_ARRIVED, "the arrow says you arrived", ArrowInfo())
      Sim.Advance(4)
      local _, src = ArrowTarget()
      Check(src == "guide", "the manual point clears itself and the guide takes over", src)

      Section("option off and on")
      NavGo(D, 10, 10)
      NavTarget(D, 54, 10, "Otra vez")
      NavWait(10)
      Sim.Advance(Sim.FRAME)
      Check(NavState().shown, "following the path again")
      S().Options:Set("navPaths", false)
      Sim.Advance(0.2)
      Check(S().ArrowNav:State() == "off" and ArrowInfo():find(L.ARROW_MODE_PATH, 1, true) == nil, "option off: no path")
      Check(#S().MinimapRoute.lines == 0, "option off: nothing on the minimap")
      Check(Near(SendaArrow.goal, StraightAim()), "option off: straight arrow")
      Check(ArrowInfo():find(L.ARROW_MODE_LINE, 1, true) == 1, "option off: «Línea recta»", ArrowInfo())
      local r0 = NavState().requests
      S().Options:Set("navPaths", true)
      NavWait(10)
      Sim.Advance(Sim.FRAME)
      Check(NavState().requests == r0 + 1 and NavState().shown, "option on: a new route and the path again")
      Check(#Sim.errors == 0, "no Lua errors")
    `,
  },
  {
    id: 'nav-reroute',
    title: 'Real paths: off the path asks again (with a cooldown); a new target asks again and drops the old answer',
    char: 'gnome-warlock',
    lua: PRELUDE + L_`
      Sim.profileTick = 0.02
      local D = NavPackAt(1426, 0.300, 0.715)
      Sim.EnableNav({ [0] = D })
      Login()
      NavGo(D, 10, 10)
      NavTarget(D, 54, 10, "Al otro lado")
      NavWait(10)
      Sim.Advance(6) -- past the cooldown of the first request
      local st = NavState()
      Check(st.status == "ok", "first route in", st.status)
      local r0 = st.requests

      Section("off the path")
      NavGo(D, 10, 40) -- ~60 yd from the first leg
      Sim.Advance(0.1)
      Check(NavState().requests == r0 + 1, "SendaNav.Next says off route: a new route is asked", NavState().requests - r0)
      NavWait(10)
      Sim.Advance(Sim.FRAME)
      st = NavState()
      local first = st.path[1]
      Check(st.status == "ok" and math.abs(first.gx - D.info.gx0 - 10) <= 1 and math.abs(first.gy - D.info.gy0 - 40) <= 1,
        "the new path starts where the player is", st.path and (first.gx - D.info.gx0) .. "," .. (first.gy - D.info.gy0))
      Check(st.shown, "the arrow follows the new path")

      Section("cooldown")
      NavGo(D, 5, 60) -- off the new path right away
      Sim.Advance(1)
      Check(NavState().requests == r0 + 1, "within the cooldown no new route is asked", NavState().requests - r0)
      Sim.Advance(5)
      Check(NavState().requests == r0 + 2, "after the cooldown it asks again", NavState().requests - r0)
      NavWait(10)

      Section("target changes")
      local r1 = NavState().requests
      NavTarget(D, 54, 60, "Sur")
      Sim.Advance(Sim.FRAME)
      Check(NavState().requests == r1 + 1, "a new target asks for a route at once", NavState().requests - r1)
      Check(NavState().path == nil, "the old target's path is dropped")
      -- a second change before the first answer: only the last target's route counts
      NavTarget(D, 60, 30, "Este")
      NavWait(10)
      Sim.Advance(Sim.FRAME)
      st = NavState()
      local last = st.path and st.path[#st.path]
      Check(last and math.abs(last.gx - D.info.gx0 - 60) <= 1 and math.abs(last.gy - D.info.gy0 - 30) <= 1,
        "the path ends at the last target (the earlier answer is ignored)", last and (last.gx - D.info.gx0) .. "," .. (last.gy - D.info.gy0))
      Check(#Sim.errors == 0, "no Lua errors")
    `,
  },
  {
    id: 'nav-combat',
    title: 'Real paths: nothing loads in combat (queued until PLAYER_REGEN_ENABLED); routes in combat; corpse mode routes to the corpse',
    char: 'human-mage',
    lua: PRELUDE + L_`
      Sim.profileTick = 0.02
      local D = NavPackAt(1429, 0.480, 0.420)
      Sim.EnableNav({ [0] = D })
      Sim.CHARS["human-mage"].combat = true -- logs in fighting
      Login()
      Sim.CHARS["human-mage"].combat = nil
      Check(Sim.player.combat, "in combat")
      NavGo(D, 10, 10)
      NavTarget(D, 54, 10, "Al otro lado")
      Sim.Advance(3)
      Check(#Sim.addonLoads == 0, "in combat no add-on is loaded", #Sim.addonLoads)
      Check(NavState().pending, "the load is queued")
      Check(not NavState().shown and Near(SendaArrow.goal, StraightAim()), "straight arrow meanwhile")

      Section("combat ends")
      Sim.player.combat = false
      Sim.Fire("PLAYER_REGEN_ENABLED")
      Check(LoadsOf("Senda_Nav") == 1, "PLAYER_REGEN_ENABLED loads Senda_Nav at once")
      NavWait(10)
      Sim.Advance(Sim.FRAME)
      local n, inCombat = LoadsOf("Senda_Nav_EK")
      Check(n == 1 and inCombat == 0, "then the EK pack, out of combat", n .. "/" .. inCombat)
      Check(NavState().shown and ArrowInfo():find(S().L.ARROW_MODE_PATH, 1, true) == 1, "and the arrow follows the path")

      Section("a new route in combat (the pack is already loaded)")
      Sim.player.combat = true
      Sim.Fire("PLAYER_REGEN_DISABLED")
      NavTarget(D, 54, 60, "Sur")
      NavWait(10)
      Sim.Advance(Sim.FRAME)
      Check(NavState().status == "ok" and NavState().shown, "routes are computed in combat too", NavState().status)
      local _, c2 = LoadsOf("Senda_Nav_EK")
      Check(c2 == 0 and #Sim.addonLoads == 2, "still no load in combat", #Sim.addonLoads)
      Sim.player.combat = false
      Sim.Fire("PLAYER_REGEN_ENABLED")
      S().Arrow:Clear("manual")

      Section("corpse mode routes to the corpse")
      local cx, cy = Sim.NavPoint(D, 54, 20)
      Sim.player.dead = true
      Sim.Fire("PLAYER_DEAD")
      Sim.Advance(1)
      Sim.player.dead, Sim.player.ghost = false, true
      Sim.player.corpse = { map = 1429, x = cx, y = cy }
      NavGo(D, 8, 12) -- the graveyard, west of the wall
      Sim.Fire("PLAYER_ALIVE")
      Sim.Advance(1.5)
      local _, src = ArrowTarget()
      Check(src == "corpse", "ghost: the arrow goes to the corpse", src)
      NavWait(10)
      Sim.Advance(Sim.FRAME)
      local st = NavState()
      local last = st.path and st.path[#st.path]
      Check(st.shown and last and math.abs(last.gx - D.info.gx0 - 54) <= 1 and math.abs(last.gy - D.info.gy0 - 20) <= 1,
        "the corpse arrow follows a walking path to the corpse", last and (last.gx - D.info.gx0) .. "," .. (last.gy - D.info.gy0))
      local r = st.requests
      Sim.Fire("CORPSE_OUT_OF_RANGE")
      Sim.Advance(2)
      Check(NavState().requests == r, "refreshing the corpse target (same place) does not ask again", NavState().requests - r)
      Sim.player.ghost, Sim.player.corpse = false, nil
      Sim.Fire("PLAYER_UNGHOST")
      Sim.Advance(1.5)
      _, src = ArrowTarget()
      Check(src == "guide", "resurrected: back to the guide", src)
      Check(#Sim.errors == 0, "no Lua errors")
    `,
  },
  {
    id: 'nav-missing',
    title: 'Real paths: without Senda_Nav installed the arrow stays straight and the load is tried once',
    char: 'gnome-warlock',
    lua: PRELUDE + L_`
      Login()
      local D = NavPackAt(1426, 0.300, 0.715)
      NavGo(D, 10, 10)
      NavTarget(D, 54, 10, "Al otro lado")
      Sim.Advance(5)
      Check(LoadsOf("Senda_Nav") == 1, "LoadAddOn(Senda_Nav) tried once, not every frame", LoadsOf("Senda_Nav"))
      Check(NavState().runtime == false and S().ArrowNav:State() == "straight", "marked unavailable for the session")
      Check(SendaArrow:IsShown() and SendaArrow.arrow:IsShown(), "the arrow works")
      Check(Near(SendaArrow.goal, StraightAim()), "straight arrow")
      Check(ArrowInfo():find(S().L.ARROW_MODE_LINE, 1, true) == 1, "no marker, plain distance", ArrowInfo())
      Check(#Sim.errors == 0, "no Lua errors")
    `,
  },
  {
    id: 'nav-fallback',
    title: 'Real paths: straight arrow flying, on a taxi, in an instance and when there is no route',
    char: 'gnome-warlock',
    lua: PRELUDE + L_`
      local D = NavPackAt(1426, 0.300, 0.715)
      Sim.EnableNav({ [0] = D })
      Login()
      -- planificador de viaje apagado: aquí solo se prueba la flecha sobre el objetivo (el viaje tiene sus escenarios)
      S().Options:Set("mod_travel", false)
      NavGo(D, 10, 10)
      NavTarget(D, 54, 10, "Al otro lado")
      NavWait(5)
      Sim.Advance(Sim.FRAME)
      Check(NavState().shown, "following the path")
      for _, case in ipairs({ { "flying", "flying" }, { "onTaxi", "on a flight path" } }) do
        Sim.player[case[1]] = true
        Sim.Advance(0.2)
        Check(not NavState().shown and ArrowInfo():find(S().L.ARROW_MODE_PATH, 1, true) == nil, case[2] .. ": no path")
        Check(Near(SendaArrow.goal, StraightAim()), case[2] .. ": straight arrow")
        Sim.player[case[1]] = false
        Sim.Advance(0.2)
        Check(NavState().shown, case[2] .. " over: back on the path (no new route needed)")
      end
      S().Options:Set("hideInInstance", false) -- keep the arrow running inside
      Sim.SetInstance("party")
      Sim.Advance(0.5)
      Check(SendaArrow:IsShown() and not NavState().shown and ArrowInfo():find(S().L.ARROW_MODE_PATH, 1, true) == nil, "in an instance: no path")
      Sim.SetInstance(nil)
      S().Options:Set("hideInInstance", true)
      Sim.Advance(0.5)
      Check(NavState().shown, "out of the instance: the path again")

      Section("no route to the target")
      local r = NavState().requests
      S().Arrow:SetTarget(1426, 60, 30, "Lejos", "manual") -- outside the pack's cells
      NavWait(5)
      Sim.Advance(0.2)
      Check(NavState().status == "fail" and NavState().why == "offmesh", "the router says offmesh", tostring(NavState().why))
      Check(not NavState().shown and Near(SendaArrow.goal, StraightAim()), "straight arrow")
      Sim.Advance(30)
      Check(NavState().requests == r + 1, "standing still, the failed route is not asked again", NavState().requests - r)
      NavGo(D, 10, 40)
      Sim.Advance(0.2)
      Check(NavState().requests == r + 2, "after moving away (and the wait) it is tried again", NavState().requests - r)

      Section("other continent")
      S().Arrow:SetTarget(1438, 50, 50, "Teldrassil", "manual")
      Sim.Advance(1)
      Check(not NavState().shown and ArrowInfo() == S().L.ARROW_OTHER_CONTINENT, "target on another continent: no route", ArrowInfo())
      Check(#Sim.errors == 0, "no Lua errors")
    `,
  },
  {
    id: 'nav-continent',
    title: 'Real paths: Kalimdor pack for the druid; both packs stay loaded, so going back needs no /reload',
    char: 'nightelf-druid',
    lua: PRELUDE + L_`
      local K = NavPackAt(1438, 0.587, 0.443)
      local E = NavPackAt(1426, 0.300, 0.715)
      Sim.EnableNav({ [0] = E, [1] = K })
      Login()
      -- planificador de viaje apagado: aquí solo se prueba la flecha sobre el objetivo (el viaje tiene sus escenarios)
      S().Options:Set("mod_travel", false)
      NavGo(K, 10, 10)
      NavTarget(K, 54, 10, "Al otro lado")
      NavWait(5)
      Sim.Advance(Sim.FRAME)
      Check(NavState().shown, "Teldrassil: following a path")
      Check(SendaNav.IsLoaded(1) and not SendaNav.IsLoaded(0), "only Kalimdor's pack is loaded")
      Check(LoadsOf("Senda_Nav_EK") == 0, "EK's pack never loaded in Kalimdor")

      Section("by boat to the Eastern Kingdoms")
      NavGo(E, 10, 10)
      Sim.Advance(0.5)
      Check(SendaNav.IsLoaded(1), "Kalimdor's pack stays loaded (the client could not load it again)")
      Check(ArrowInfo() == S().L.ARROW_OTHER_CONTINENT, "the old target is on another continent", ArrowInfo())
      NavTarget(E, 54, 10, "Al otro lado (EK)")
      NavWait(5)
      Sim.Advance(Sim.FRAME)
      Check(SendaNav.IsLoaded(0) and NavState().shown, "EK's pack is loaded and the arrow follows a path there")

      Section("back to Kalimdor")
      NavGo(K, 10, 10)
      Sim.Advance(0.5)
      Check(SendaNav.IsLoaded(0) and SendaNav.IsLoaded(1), "both packs stay loaded")
      NavTarget(K, 54, 10, "Otra vez")
      NavWait(5)
      Sim.Advance(Sim.FRAME)
      Check(NavState().packFail[1] == nil and NavState().shown, "back in Kalimdor the arrow follows a path again, no /reload",
        tostring(NavState().packFail[1]))
      Check(LoadsOf("Senda_Nav_Kalimdor") == 1, "the client was asked for Kalimdor's pack only once", LoadsOf("Senda_Nav_Kalimdor"))
      Check(#Sim.errors == 0, "no Lua errors")
    `,
  },
  {
    id: 'quest-superseded',
    title: 'Chain: an errand step is done once the next quest of the chain is in the log (Lago -> Gakin, gnome warlock)',
    char: 'gnome-warlock',
    lua: PRELUDE + L_`
      Login()
      Sim.Advance(2)
      local E, p = S().Engine, Sim.player
      p.level = 21
      Sim.Fire("PLAYER_LEVEL_UP", 21, 0, 0, 0, 0, 0, 0, 0, 0)
      Sim.Advance(1)
      local i = StepIndexOf("wl-succubus-001")
      Check(i ~= nil, "step wl-succubus-001 (Lago Blackwrench's errand) exists")
      E:JumpTo(i)
      Sim.Advance(1)
      Check(StepId() == "wl-succubus-001", "Lago's errand is current", StepId())
      Sim.AcceptQuest(1716)
      Sim.Advance(1)
      Check(StepId() ~= "wl-succubus-001" and StepId() ~= "wl-succubus-002",
        "with Devourer of Souls (1716) in the log, the errand (1717) and its turn-in are passed", StepId())
      Check(#Sim.errors == 0, "no Lua errors")
    `,
  },
  {
    id: 'arrow-tram',
    title: 'Arrow inside the Deeprun Tram (no position): says to ride the tram instead of «position unavailable»',
    char: 'gnome-warlock',
    lua: PRELUDE + L_`
      Login()
      Sim.Advance(2)
      local L = S().L
      S().Arrow:SetTarget(1455, 47.6, 9.3, "Lago", "manual")
      Sim.Advance(0.2)
      _G.GetInstanceInfo = function() return "Tranvía subterráneo", "none", 0, "", 0, 0, false, 369 end
      S().Compat.PlayerMapPos = function() return nil end
      Sim.Advance(0.2)
      Check(ArrowInfo() == L.ARROW_TRAM, "inside the tram the arrow says to ride it", ArrowInfo())
      _G.GetInstanceInfo = function() return "Otro", "party", 1, "", 5, 0, false, 36 end
      Sim.Advance(0.2)
      Check(ArrowInfo() == L.ARROW_NO_POSITION, "elsewhere without a position: «position unavailable»", ArrowInfo())
      Check(#Sim.errors == 0, "no Lua errors")
    `,
  },
];

module.exports = { scenarios };

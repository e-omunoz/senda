'use strict';
// Scenarios of the arrow's targets and arrival (addon/Senda/UI/Arrow.lua, UI/ArrowNav.lua): which module
// target wins a priority tie, route points (`wps`) skipped ahead, advanced while the arrow is hidden and kept
// over a /reload, the floor hints given to Senda_Nav, arrival measured along the path and the end of a path
// that stops short of an off-mesh target. Synthetic packs as in scenarios_nav.js (tests/wowsim/mock/nav.lua).
// Loaded by run.js.

const L_ = String.raw;

// Shared Lua: a pack around (map, x, y) with a wall (local column 32, rows 0-47) and helpers.
const PRELUDE = L_`
  local function Wall(lx, ly) return lx == 32 and ly <= 47 end
  function NavPackAt(map, x, y, blocked) return Sim.NavPack(map, x, y, { blocked = blocked or Wall }) end
  function NavGo(D, lx, ly)
    local x, y = Sim.NavPoint(D, lx, ly)
    Sim.MoveTo(D.info.map, x, y)
  end
  function NavTarget(D, lx, ly, label, source, extra)
    local x, y = Sim.NavPoint(D, lx, ly)
    S().Arrow:SetTarget(D.info.map, x * 100, y * 100, label or "Destino", source or "manual", extra)
  end
  function NavState() return S().ArrowNav.state end
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
  function ArrowInfo() return Plain(SendaArrow.info:GetText()) end
  function StraightMetres()
    local t = ArrowTarget()
    local map, x, y = S().Compat.PlayerMapPos()
    return S().Compat.WorldDistance(map, x, y, t.map, t.x, t.y)
  end
`;

const scenarios = [
  {
    id: 'arrow-prio',
    title: 'Arrow: module targets of the same priority, the latest one wins (not pairs() order)',
    char: 'gnome-warlock',
    lua: L_`
      Login()
      Sim.Advance(2)
      local A = S().Arrow
      local srcs = { "lookup", "rare", "dungeon", "professions", "trainer" }
      local wrong = {}
      for i, s in ipairs(srcs) do
        A:SetTarget(1426, 40 + i, 50, s, s)
        local _, src = A:GetTarget()
        if src ~= s then wrong[#wrong + 1] = s .. "->" .. tostring(src) end
      end
      Check(#wrong == 0, "after each SetTarget the newest module target is the one shown", table.concat(wrong, ", "))
      Section("in the reverse order too")
      A:Clear()
      wrong = {}
      for i = #srcs, 1, -1 do
        local s = srcs[i]
        A:SetTarget(1426, 40 + i, 50, s, s)
        local _, src = A:GetTarget()
        if src ~= s then wrong[#wrong + 1] = s .. "->" .. tostring(src) end
      end
      Check(#wrong == 0, "newest wins whatever the source name", table.concat(wrong, ", "))
      Section("refreshing the same point does not steal the arrow")
      A:SetTarget(1426, 45, 50, "trainer again", "trainer") -- same point as before, older source
      local _, src = A:GetTarget()
      Check(src == "lookup", "a module re-setting its own point keeps its place", src)
      A:SetTarget(1426, 47, 52, "trainer moved", "trainer")
      _, src = A:GetTarget()
      Check(src == "trainer", "a new point of a module is new: it goes in front", src)
      Section("clearing the newest falls back to the next newest")
      A:Clear("trainer")
      _, src = A:GetTarget()
      Check(src == "lookup", "next newest", src)
      A:Clear("lookup")
      _, src = A:GetTarget()
      Check(src == "rare", "and the next", src)
      Section("priorities still rule")
      A:SetTarget(1426, 30, 50, "manual", "manual")
      A:SetTarget(1426, 31, 50, "dungeon newer", "dungeon")
      _, src = A:GetTarget()
      Check(src == "manual", "manual beats a newer module target", src)
      Check(#Sim.errors == 0, "no Lua errors")
    `,
  },
  {
    id: 'arrow-wps',
    title: 'Arrow: route points skip ahead, advance while the arrow is hidden, and the step keeps its point',
    char: 'gnome-warlock',
    lua: L_`
      Login()
      local A = S().Arrow
      Check(StepId() == "coldridge-001", "starts at coldridge-001", StepId())
      Sim.AcceptQuest(179, { { "Carne de lobo: 0/8", 8 } })
      Sim.Advance(1)
      Check(StepId() == "coldridge-002", "on coldridge-002 (at + 2 wps)", StepId())
      local t = ArrowTarget()
      Check(t.wpIndex == 1 and math.abs(t.x - 0.288) < 1e-6, "the arrow starts at the step's 'at'", t.wpIndex)

      Section("skip ahead: walk straight to the last point")
      Sim.MoveTo(1426, 0.270, 0.710) -- "Lobos al oeste", never near 'at' or "Lobos al este"
      Sim.Advance(0.5)
      t = ArrowTarget()
      Check(t.wpIndex == 3 and t.label == "Lobos al oeste", "the arrow moves on to the nearer later point", tostring(t.wpIndex) .. " " .. tostring(t.label))
      local saved = S().db.char.wps and S().db.char.wps["coldridge-002"]
      Check(saved and saved.i == 3, "the point is saved for the step (SendaDB.char.wps)", saved and saved.i)

      Section("a rebuild of the guide does not reset it")
      A:FollowStep()
      t = ArrowTarget()
      Check(t.wpIndex == 3, "FollowStep restores the saved point", t.wpIndex)
      S().Events:Fire("SENDA_STEP_CHANGED")
      Sim.Advance(0.3)
      Check(ArrowTarget().wpIndex == 3, "...also through SENDA_STEP_CHANGED", ArrowTarget().wpIndex)

      Section("no skip from afar")
      local wps = { { 1426, 40, 50, "W1" }, { 1426, 42, 50, "W2" }, { 1426, 44, 50, "W3" }, { 1426, 46, 50, "W4" } }
      Sim.MoveTo(1426, 0.50, 0.40) -- far from all of them, nearer W4 than W1
      A:SetTarget(1426, 40, 50, "W1", "guide", { wps = wps, wpIndex = 1, baseLabel = "kill", radius = 15 })
      Sim.Advance(0.6)
      Check(ArrowTarget().wpIndex == 1, "far from every point the order is kept", ArrowTarget().wpIndex)

      Section("arrow hidden (option off)")
      S().Options:Set("arrow", false)
      Sim.Advance(0.3)
      Check(not SendaArrow:IsShown(), "the arrow is hidden")
      Sim.MoveTo(1426, 0.40, 0.50)
      Sim.Advance(0.5)
      t = ArrowTarget()
      Check(t.wpIndex == 2, "standing on W1 with the arrow off moves on to W2", t.wpIndex)
      Sim.MoveTo(1426, 0.42, 0.50)
      Sim.Advance(0.5)
      Check(ArrowTarget().wpIndex == 3, "...and on to W3", ArrowTarget().wpIndex)
      S().Options:Set("arrow", true)

      Section("arrow hidden in combat")
      S().Options:Set("arrowCombatHide", true)
      Sim.player.combat = true
      Sim.Fire("PLAYER_REGEN_DISABLED")
      Sim.Advance(0.3)
      Check(not SendaArrow:IsShown(), "hidden in combat")
      Sim.MoveTo(1426, 0.44, 0.50)
      Sim.Advance(0.5)
      Check(ArrowTarget().wpIndex == 4, "standing on W3 in combat moves on to W4", ArrowTarget().wpIndex)
      Sim.player.combat = false
      Sim.Fire("PLAYER_REGEN_ENABLED")
      S().Options:Set("arrowCombatHide", false)

      Section("manual target cleared on arrival while hidden")
      S().Options:Set("arrow", false)
      A:SetTarget(1426, 44.1, 50, "Aquí", "manual")
      Sim.Advance(4)
      Check(not A:Has("manual"), "a manual point clears itself on arrival with the arrow off")
      S().Options:Set("arrow", true)

      Section("back to the guide step for the reload")
      A:FollowStep()
      Check(ArrowTarget().wpIndex == 3, "the step's saved point again", ArrowTarget().wpIndex)
      Check(#Sim.errors == 0, "no Lua errors")
      __report("saved", Sim.SaveVariables())
      __report("world", Sim.ExportWorld())
    `,
  },
  {
    id: 'arrow-wps-reload',
    title: 'Arrow: the route point of the step survives a /reload',
    char: 'gnome-warlock',
    needs: 'arrow-wps',
    lua: L_`
      Login()
      Sim.Advance(2)
      Check(StepId() == "coldridge-002", "still on coldridge-002", StepId())
      local t = ArrowTarget()
      Check(t and t.wpIndex == 3 and t.label == "Lobos al oeste", "the arrow comes back on the saved point, not the first",
        t and (tostring(t.wpIndex) .. " " .. tostring(t.label)))
      Check(#Sim.errors == 0, "no Lua errors")
    `,
  },
  {
    id: 'arrow-floor',
    title: 'Arrow: floor hints for Senda_Nav (indoors/outdoors, the path being followed, the target height) and the retry without them',
    char: 'gnome-warlock',
    lua: PRELUDE + L_`
      Sim.profileTick = 0.02
      -- the wall, and a closed box (cells 50-60) whose inside cannot be reached
      local function Blocked(lx, ly)
        if lx == 32 and ly <= 47 then return true end
        local box = lx >= 50 and lx <= 60 and ly >= 50 and ly <= 60
        return box and (lx == 50 or lx == 60 or ly == 50 or ly == 60)
      end
      local D = NavPackAt(1426, 0.300, 0.715, Blocked)
      Sim.EnableNav({ [0] = D })
      Login()
      S().Arrow:Clear("guide")
      local seen = {}
      local route = SendaNav.Route
      SendaNav.Route = function(fm, fx, fy, tm, tx, ty, cb, opts)
        seen[#seen + 1] = opts or false
        return route(fm, fx, fy, tm, tx, ty, cb, opts)
      end
      local function Last() return seen[#seen] end
      NavGo(D, 10, 10)
      Sim.Advance(0.5)

      Section("no IsIndoors, no height: no hints (every floor)")
      NavTarget(D, 20, 20, "A")
      NavWait(10)
      Check(Last() == false, "no options", tostring(Last()))

      Section("outdoors: the top floor")
      _G.IsIndoors = function() return false end
      NavTarget(D, 20, 21, "B")
      NavWait(10)
      Check(Last() and Last().fhint == "top" and Last().fz == nil, "fhint = top", Last() and Last().fhint)

      Section("indoors: floors with a ceiling")
      _G.IsIndoors = function() return true end
      NavTarget(D, 20, 22, "C")
      NavWait(10)
      Check(Last() and Last().fhint == "under", "fhint = under", Last() and Last().fhint)

      Section("the target's height goes as tz")
      NavTarget(D, 20, 23, "D", "manual", { z = 123.5 })
      NavWait(10)
      Check(Last() and Last().tz == 123.5 and Last().tnear == true, "tz = 123.5", Last() and Last().tz)

      Section("the floor of the path being followed")
      NavTarget(D, 54, 10, "E")
      NavWait(10)
      local st = NavState()
      Check(st.status == "ok", "route", st.status)
      for _, p in ipairs(st.path) do p.z = 77 end
      Sim.Advance(0.2)
      Check(st.floor and st.floor.z == 77, "the floor of the path next to the player is noted", st.floor and st.floor.z)
      NavTarget(D, 20, 30, "F")
      NavWait(10)
      Check(Last() and Last().fz == 77 and Last().fhint == nil, "the next route starts on that floor", Last() and tostring(Last().fz))
      NavGo(D, 10, 60) -- > 40 yd away: that floor no longer says where the player is
      Sim.Advance(0.2)
      NavTarget(D, 20, 31, "G")
      NavWait(10)
      Check(Last() and Last().fz == nil and Last().fhint == "under", "far from it, back to IsIndoors", Last() and tostring(Last().fz))

      Section("the client's own height, when it gives one")
      _G.UnitPosition = function() return 0, 0, 345.5, 0 end
      NavTarget(D, 20, 32, "H")
      NavWait(10)
      Check(Last() and Last().fz == 345.5, "fz from UnitPosition", Last() and tostring(Last().fz))
      _G.UnitPosition = function() return 0, 0, 0, 0 end
      NavTarget(D, 20, 33, "I")
      NavWait(10)
      Check(Last() and Last().fz == nil, "a z of exactly 0 is unknown", Last() and tostring(Last().fz))
      _G.UnitPosition = nil

      Section("unreachable with hints: asked again without them")
      local r0, n0 = st.requests, #seen
      NavTarget(D, 55, 55, "Caja")
      NavWait(10)
      Sim.Advance(0.5)
      Check(#seen == n0 + 2 and seen[n0 + 1] ~= false and seen[n0 + 2] == false, "two requests: with hints, then without",
        tostring(#seen - n0))
      Check(st.status == "fail" and st.requests == r0 + 2, "then the usual failure", st.status)
      _G.IsIndoors = nil
      SendaNav.Route = route
      Check(#Sim.errors == 0, "no Lua errors")
    `,
  },
  {
    id: 'arrow-arrive-path',
    title: 'Arrow: arrival is measured along the walking path (a target just across a wall is not «arrived»)',
    char: 'gnome-warlock',
    lua: PRELUDE + L_`
      Sim.profileTick = 0.02
      local D = NavPackAt(1426, 0.300, 0.715)
      Sim.EnableNav({ [0] = D })
      Login()
      S().Arrow:Clear("guide")
      local L = S().L
      NavGo(D, 31, 10)
      Sim.Advance(0.5)
      NavTarget(D, 33, 10, "Al otro lado del muro")
      NavWait(10)
      Sim.Advance(0.2)
      local st = NavState()
      Check(st.status == "ok", "route", st.status)
      Check(StraightMetres() < 10, "the target is within 10 m in a straight line", string.format("%.1f m", StraightMetres()))
      Check(st.shown and st.along > 100, "but more than 100 yd along the path", string.format("%.0f yd", st.along or -1))
      Check(not SendaArrow.check:IsShown() and ArrowInfo():find(L.ARROW_ARRIVED, 1, true) == nil, "the arrow does not say «arrived»", ArrowInfo())
      Sim.Advance(4)
      Check(S().Arrow:Has("manual"), "the manual point is not cleared (not there yet)")
      Section("walk the path")
      local path = st.path
      for i = 2, #path do
        Sim.MoveTo(path[i].map, path[i].x / 100, path[i].y / 100)
        Sim.Advance(0.1)
      end
      local x, y = Sim.NavPoint(D, 33, 10)
      Sim.MoveTo(1426, x, y)
      Sim.Advance(0.3)
      Check(SendaArrow.check:IsShown(), "at the target: arrived", ArrowInfo())
      Sim.Advance(4)
      Check(not S().Arrow:Has("manual"), "and the manual point clears itself")
      Check(#Sim.errors == 0, "no Lua errors")
    `,
  },
  {
    id: 'arrow-pathend',
    title: 'Arrow: at the end of a path that stops short of an off-mesh target the arrow points straight at it',
    char: 'gnome-warlock',
    lua: PRELUDE + L_`
      Sim.profileTick = 0.02
      local D = NavPackAt(1426, 0.300, 0.715, function(lx, ly) return lx >= 40 and ly <= 20 end)
      Sim.EnableNav({ [0] = D })
      Login()
      S().Arrow:Clear("guide")
      local L = S().L
      NavGo(D, 10, 10)
      Sim.Advance(0.5)
      NavTarget(D, 46, 10, "Dentro de la roca")
      NavWait(10)
      local st = NavState()
      Check(st.status == "ok" and st.path, "route to the snapped end", st.status)
      local last = st.path[#st.path]
      Sim.MoveTo(last.map, last.x / 100, last.y / 100)
      Sim.Advance(0.5)
      Check(not st.shown, "on the last leg with no path left the arrow leaves the path", ArrowInfo())
      Check(S().ArrowNav:Why() == "pathend", "reason: end of the path", tostring(S().ArrowNav:Why()))
      Check(Near(SendaArrow.goal, StraightAim(), 1e-3), "the arrow points straight at the target",
        string.format("%.2f vs %.2f", SendaArrow.goal or -9, StraightAim()))
      Check(ArrowInfo():find(L.ARROW_MODE_LINE, 1, true) == 1 and ArrowInfo():find(L.ARROW_WHY_pathend, 1, true) ~= nil,
        "«Línea recta» with the end-of-path reason", ArrowInfo())
      Check(ArrowInfo():find("Ruta a pie  0 m", 1, true) == nil, "never «Ruta a pie 0 m»", ArrowInfo())
      Check(StraightMetres() > 10, "the target is still some way off", string.format("%.0f m", StraightMetres()))
      Section("a little before the end the path still leads")
      local prev = st.path[#st.path - 1]
      local x = (prev.x + last.x) / 200
      local y = (prev.y + last.y) / 200
      Sim.MoveTo(last.map, x, y)
      Sim.Advance(0.3)
      if st.along and st.along >= 5 then
        Check(st.shown, "following the path while more than 5 yd are left", string.format("%.1f yd", st.along))
      else
        Check(true, "last leg shorter than 10 yd: nothing to check")
      end
      Check(#Sim.errors == 0, "no Lua errors")
    `,
  },
];

module.exports = { scenarios };

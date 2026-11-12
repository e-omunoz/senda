-- Senda_Nav: walking routes over the real terrain of the WoW: Forever client (docs/NAV.md, section 8).
-- Copyright (C) 2026 Senda contributors. GPL-3.0-only.
--
-- Global API (no dependency on Senda):
--   SendaNav.Load(continent) -> ok, reason
--       Loads the continent's pack (0 or "EK" = Eastern Kingdoms, 1 or "Kalimdor") with
--       C_AddOns.LoadAddOn. Only out of combat: in combat it returns false, "combat" and loads it
--       as soon as combat ends.
--   SendaNav.Route(fromMap, fx, fy, toMap, tx, ty, callback [, opts]) -> job
--       uiMapId + percent (0-100) ends. The search runs a slice per frame (<= SendaNav.budget ms)
--       and then calls callback(path, cost, job) or callback(nil, reason, job). reason: "map"
--       (no world position for a map), "continent" (ends on different continents), "nodata"
--       (pack not loaded, e.g. in combat), "offmesh", "unreachable", "error: ...".
--       path = { {map, x, y, wx, wy, z?, lift = name|nil}, ..., continent = c, cost = yards }:
--       the first waypoint is the start; a waypoint with `lift` is where a lift or portal ride
--       starts, and the next waypoint is where it ends.
--       opts: { fz = z, tz = z } (ends' heights, to pick a floor), { look = n }.
--   SendaNav.Next(path, map, x, y [, z]) -> waypoint, index, yards, offRoute, arrived
--       The waypoint an arrow should point at for a player at uiMapId/percent (x, y). Keeps its
--       progress in path.idx (only moves forward). offRoute: farther than SendaNav.offRoute yards
--       from the current leg (route again). arrived: within SendaNav.radius of the last waypoint.
--   SendaNav.Cancel(job), SendaNav.Busy(), SendaNav.IsLoaded(c), SendaNav.Unload(c),
--   SendaNav.ToWorld(map, x, y), SendaNav.ToMap(continent, wx, wy, maps...), SendaNav.stats.
--   Settings: SendaNav.budget, combatBudget, idleAfter, radius, offRoute, look (string pulling
--   look-ahead in cells; nil = the router's 200).

local ADDON, ns = ...
local R = ns.Router

local SendaNav = {}
_G.SendaNav = SendaNav

SendaNav.version = 1
SendaNav.budget = 1.2       -- ms of search per frame out of combat
SendaNav.combatBudget = 0.5 -- ms of search per frame in combat
SendaNav.idleAfter = 30     -- s without searches before the decoded caches are dropped
SendaNav.radius = 4         -- yd: a waypoint is reached within this distance
SendaNav.offRoute = 30      -- yd from the current leg: off the route
SendaNav.stats = { load = {} }

local ADDONS = { [0] = "Senda_Nav_EK", [1] = "Senda_Nav_Kalimdor" }
local NAMES = { ek = 0, eastern = 0, ["0"] = 0, kalimdor = 1, ["1"] = 1 }
local unloaded, pending = {}, {}

local function cont(c)
	if c == 0 or c == 1 then return c end
	if type(c) == "string" then return NAMES[c:lower()] end
	return nil
end

local function inCombat() return InCombatLockdown and InCombatLockdown() and true or false end

-- ---------------------------------------------------------------- coordinates
-- Each uiMap's frame in world yards, from two corners through C_Map (the client's own UiMap
-- tables): wx = top + (bottom - top) * y%, wy = left + (right - left) * x%.
local frames = {}

local function vec(x, y)
	if CreateVector2D then return CreateVector2D(x, y) end
	return { x = x, y = y, GetXY = function(v) return v.x, v.y end }
end
local function xyOf(v)
	if not v then return nil end
	if v.GetXY then return v:GetXY() end
	return v.x, v.y
end

local function frameOf(map)
	local f = frames[map]
	if f ~= nil then return f or nil end
	f = false
	if map and C_Map and C_Map.GetWorldPosFromMapPos then
		local c1, p1 = C_Map.GetWorldPosFromMapPos(map, vec(0, 0))
		local c2, p2 = C_Map.GetWorldPosFromMapPos(map, vec(1, 1))
		local top, left = xyOf(p1)
		local bottom, right = xyOf(p2)
		if c1 and c1 == c2 and top and bottom and top ~= bottom and left ~= right then
			f = { c = c1, top = top, left = left, bottom = bottom, right = right }
		end
	end
	frames[map] = f
	return f or nil
end

-- uiMapId + percent -> continent, wx, wy (world yards; wx north, wy west).
function SendaNav.ToWorld(map, x, y)
	local f = frameOf(map)
	if not (f and x and y) then return nil end
	return f.c, f.top + (f.bottom - f.top) * y / 100, f.left + (f.right - f.left) * x / 100
end

local function percent(f, wx, wy)
	return (wy - f.left) / (f.right - f.left) * 100, (wx - f.top) / (f.bottom - f.top) * 100
end

-- World -> uiMapId + percent: the first of the given maps that contains the point, else the
-- client's own choice (C_Map.GetMapPosFromWorldPos), else the first given map (outside 0-100).
function SendaNav.ToMap(c, wx, wy, ...)
	local firstMap
	for i = 1, select("#", ...) do
		local map = select(i, ...)
		local f = map and frameOf(map)
		if f and f.c == c then
			local x, y = percent(f, wx, wy)
			if x >= 0 and x <= 100 and y >= 0 and y <= 100 then return map, x, y end
			firstMap = firstMap or map
		end
	end
	if C_Map and C_Map.GetMapPosFromWorldPos then
		local map, pos = C_Map.GetMapPosFromWorldPos(c, vec(wx, wy))
		local x, y = xyOf(pos)
		if map and x then return map, x * 100, y * 100 end
	end
	if firstMap then
		local x, y = percent(frameOf(firstMap), wx, wy)
		return firstMap, x, y
	end
	return nil
end

-- ---------------------------------------------------------------- driver
local driver = CreateFrame("Frame")
local quiet = 0 -- seconds without work
local idled = true

local function onUpdate(_, elapsed)
	if R.Busy() then
		quiet, idled = 0, false
		R.Step(inCombat() and SendaNav.combatBudget or SendaNav.budget)
	else
		quiet = quiet + (elapsed or 0)
		if not idled and quiet >= SendaNav.idleAfter then
			R.Idle()
			idled = true
		end
		if idled then driver:SetScript("OnUpdate", nil) end
	end
end

local function wake()
	quiet = 0
	driver:SetScript("OnUpdate", onUpdate)
end

driver:SetScript("OnEvent", function(_, event)
	if event == "PLAYER_REGEN_ENABLED" then
		driver:UnregisterEvent("PLAYER_REGEN_ENABLED")
		for c in pairs(pending) do
			pending[c] = nil
			SendaNav.Load(c)
		end
	end
end)

-- ---------------------------------------------------------------- loading
function SendaNav.IsLoaded(c)
	c = cont(c)
	return c ~= nil and R.HasData(c)
end

function SendaNav.Load(c)
	c = cont(c)
	if c == nil then return false, "continent" end
	if R.HasData(c) then return true end
	if unloaded[c] then return false, "unloaded" end
	if inCombat() then
		pending[c] = true
		driver:RegisterEvent("PLAYER_REGEN_ENABLED")
		return false, "combat"
	end
	local load = (C_AddOns and C_AddOns.LoadAddOn) or LoadAddOn
	if not load then return false, "api" end
	local m0, t0 = collectgarbage("count"), debugprofilestop()
	local ok, reason = load(ADDONS[c])
	SendaNav.stats.load[c] = { ms = debugprofilestop() - t0, kb = collectgarbage("count") - m0 }
	if not ok then return false, reason or "load" end
	if not R.HasData(c) then return false, "nodata" end
	return true
end

-- Releases a continent's pack (memory comes back at the next garbage collection). It cannot be
-- loaded again in this session: the client loads an addon once.
function SendaNav.Unload(c)
	c = cont(c)
	if c == nil or not (SendaNavData and SendaNavData[c]) then return false end
	R.Drop(c)
	SendaNavData[c] = nil
	unloaded[c] = true
	return true
end

-- ---------------------------------------------------------------- routes
function SendaNav.Route(fromMap, fx, fy, toMap, tx, ty, callback, opts)
	opts = opts or {}
	local fail = { failed = true }
	local c1, sx, sy = SendaNav.ToWorld(fromMap, fx, fy)
	local c2, ex, ey = SendaNav.ToWorld(toMap, tx, ty)
	if not c1 or not c2 then callback(nil, "map", fail); return fail end
	if c1 ~= c2 then callback(nil, "continent", fail); return fail end
	if not R.HasData(c1) and not (ADDONS[c1] and SendaNav.Load(c1)) then
		callback(nil, "nodata", fail)
		return fail
	end
	local req = { sx = sx, sy = sy, sz = opts.fz, tx = ex, ty = ey, tz = opts.tz, look = opts.look or SendaNav.look }
	local job = R.Find(c1, req, function(points, costOrReason, j)
		if not points then return callback(nil, costOrReason, j) end
		local path = { continent = c1, cost = costOrReason, from = fromMap, to = toMap, idx = 2 }
		for i, p in ipairs(points) do
			local map, x, y = SendaNav.ToMap(c1, p.wx, p.wy, toMap, fromMap)
			path[i] = { map = map, x = x, y = y, wx = p.wx, wy = p.wy, z = p.z, lift = p.lift, gx = p.gx, gy = p.gy, li = p.li }
		end
		callback(path, costOrReason, j)
	end)
	wake()
	return job
end

function SendaNav.Cancel(job) R.Cancel(job) end
function SendaNav.Busy() return R.Busy() end

-- ---------------------------------------------------------------- following a path
local sqrt = math.sqrt

local function segDist(px, py, ax, ay, bx, by)
	local dx, dy = bx - ax, by - ay
	local l2 = dx * dx + dy * dy
	local t = l2 > 0 and ((px - ax) * dx + (py - ay) * dy) / l2 or 0
	if t < 0 then t = 0 elseif t > 1 then t = 1 end
	local qx, qy = ax + dx * t - px, ay + dy * t - py
	return sqrt(qx * qx + qy * qy)
end

local function reached(w, px, py, z, radius)
	local dx, dy = w.wx - px, w.wy - py
	if dx * dx + dy * dy > radius * radius then return false end
	-- with heights on both sides, a different floor is not there yet (lifts, stacked floors)
	if z and w.z and math.abs(w.z - z) > 6 then return false end
	return true
end

function SendaNav.Next(path, map, x, y, z)
	local n = path and #path or 0
	if n == 0 then return nil end
	local c, px, py = SendaNav.ToWorld(map, x, y)
	if not c or c ~= path.continent then return path[path.idx or n], path.idx or n, nil, true, false end
	if n == 1 then
		local w = path[1]
		local d = sqrt((w.wx - px) ^ 2 + (w.wy - py) ^ 2)
		return w, 1, d, d > SendaNav.offRoute, d <= SendaNav.radius
	end
	local i = path.idx or 2
	if i < 2 then i = 2 elseif i > n then i = n end
	local radius = SendaNav.radius
	-- reached the target: on to the next one
	while i < n and reached(path[i], px, py, z, radius) do i = i + 1 end
	-- skipped ahead: a later leg (up to 6, never past a ride) is closer than the current one
	local a, b = path[i - 1], path[i]
	-- on a ride the player waits at its start: off the route only when away from it
	local cur = a.lift and sqrt((a.wx - px) ^ 2 + (a.wy - py) ^ 2) or segDist(px, py, a.wx, a.wy, b.wx, b.wy)
	for j = i + 1, math.min(n, i + 6) do
		local p, q = path[j - 1], path[j]
		if path[j - 2] and path[j - 2].lift then break end
		if p.lift then break end
		local d = segDist(px, py, p.wx, p.wy, q.wx, q.wy)
		if d + 1 < cur then i, cur = j, d end
	end
	path.idx = i
	local w = path[i]
	local d = sqrt((w.wx - px) ^ 2 + (w.wy - py) ^ 2)
	local arrived = i == n and reached(w, px, py, z, radius)
	return w, i, d, cur > SendaNav.offRoute, arrived
end

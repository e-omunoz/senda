-- tests/navsim: follows a found path with SendaNav.Next, as an arrow would.
-- Copyright (C) 2026 Senda contributors. GPL-3.0-only.
--
-- A walker moves along the path's legs at 7 yd/s, 10 updates a second, and takes every ride
-- (lift or portal) at once. After every move it asks SendaNav.Next where to go, in the uiMap the
-- route started in, without a height. Checks: the index never goes back, never lags behind the
-- leg being walked, the walker is never reported off the route, and the end reports `arrived`.
-- Then a point 60 yd to the side of a leg must be reported off the route.



local function copy(path)
	local t = {}
	for k, v in pairs(path) do t[k] = v end
	t.idx = nil
	return t
end

function navsim.walk(path0)
	local path = copy(path0)
	local map = path.from
	local n = #path
	local calls, worst, total = 0, 0, 0
	local last, lag, ahead, off, problems = 0, 0, 0, 0, {}
	local arrived = false
	local function ask(wx, wy, leg)
		local m, x, y = SendaNav.ToMap(path.continent, wx, wy, map)
		local t0 = debugprofilestop()
		local w, i, d, offRoute, arr = SendaNav.Next(path, m, x, y)
		local dt = debugprofilestop() - t0
		calls, total = calls + 1, total + dt
		if dt > worst then worst = dt end
		if not w then problems[#problems + 1] = "no waypoint"; return end
		if i < last then problems[#problems + 1] = ("index went back %d -> %d"):format(last, i) end
		if i < leg then lag = math.max(lag, leg - i) end
		if i > leg then ahead = math.max(ahead, i - leg) end
		if offRoute then off = off + 1 end
		last = i
		arrived = arr
	end
	ask(path[1].wx, path[1].wy, 2)
	for i = 2, n do
		local a, b = path[i - 1], path[i]
		if a.lift then
			ask(b.wx, b.wy, math.min(i + 1, n))
		else
			local dx, dy = b.wx - a.wx, b.wy - a.wy
			local len = math.sqrt(dx * dx + dy * dy)
			local steps = math.max(1, math.ceil(len / 0.7))
			for s = 1, steps do
				local f = s / steps
				ask(a.wx + dx * f, a.wy + dy * f, s == steps and math.min(i + 1, n) or i)
			end
		end
	end
	if lag > 0 then problems[#problems + 1] = ("lagged %d legs"):format(lag) end
	if off > 0 then problems[#problems + 1] = ("off route %d times on the path"):format(off) end
	if not arrived then problems[#problems + 1] = "never arrived" end
	-- off to the side of the longest walked leg
	local best, bi = 0, nil
	for i = 2, n do
		if not path[i - 1].lift then
			local l = math.sqrt((path[i].wx - path[i - 1].wx) ^ 2 + (path[i].wy - path[i - 1].wy) ^ 2)
			if l > best then best, bi = l, i end
		end
	end
	if bi and best > 1 then
		local side = copy(path0)
		side.idx = bi
		local a, b = path[bi - 1], path[bi]
		local mx, my = (a.wx + b.wx) / 2, (a.wy + b.wy) / 2
		local nx, ny = -(b.wy - a.wy) / best, (b.wx - a.wx) / best
		local m, x, y = SendaNav.ToMap(path.continent, mx + nx * 60, my + ny * 60, map)
		local _, _, _, offRoute = SendaNav.Next(side, m, x, y)
		if not offRoute then problems[#problems + 1] = "60 yd to the side not reported off the route" end
	end
	return #problems == 0, table.concat(problems, "; "), calls, worst, total, ahead
end

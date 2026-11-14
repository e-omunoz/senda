-- Senda_Nav: the HPA* router over the navigation packs (docs/NAV.md, sections 3 and 8).
-- Copyright (C) 2026 Senda contributors. GPL-3.0-only.
--
-- Adapted from Senda's reference router (nav/lua/SendaNavRouter.lua). Reads SendaNavData[map]
-- (the data addons Senda_Nav_EK and Senda_Nav_Kalimdor) and finds walks: each end connects to its
-- sector's entrances by a grid search inside the sector, an A* runs over the entrance graph and
-- every hop is refined by a grid A* inside its sector; the line is then pulled straight where the
-- coarse links allow it. Every search runs in a coroutine that yields when the frame's slice is
-- spent, and yields early before a blob decode that would not fit in what is left of the slice.
--
-- Client API used: C_EncodingUtil.DecodeBase64, C_EncodingUtil.DecompressString,
-- Enum.CompressionMethod.Zlib, debugprofilestop. Nothing else; no globals of its own.

local _, ns = ...
local R = {}
ns.Router = R

local byte, floor, abs, max, min = string.byte, math.floor, math.abs, math.max, math.min
local yield, create, resume, status = coroutine.yield, coroutine.create, coroutine.resume, coroutine.status
local pairs, ipairs, tostring = pairs, ipairs, tostring

local ADT = 1600 / 3
local CELL = ADT / 128
local SEC = 64
local SX = 128
local ORIGIN = 32 * ADT
local DX = { 1, 1, 0, -1, -1, -1, 0, 1 }
local DY = { 0, 1, 1, 1, 0, -1, -1, -1 }
local SQ2 = 1.4142135623731
local LEN = {}
for d = 1, 8 do LEN[d] = (d % 2 == 0) and CELL * SQ2 or CELL end
local NOCOST = 65535
-- DIR[(my + 1) * 3 + mx + 2]: direction index 1-8 of the step (mx, my).
local DIR = {}
for d = 1, 8 do DIR[(DY[d] + 1) * 3 + DX[d] + 2] = d end

R.CELL, R.ORIGIN = CELL, ORIGIN

-- HAS[m * 8 + li + 1]: bit li of mask m.
local HAS = {}
for m = 0, 255 do
	for li = 0, 7 do HAS[m * 8 + li + 1] = floor(m / 2 ^ li) % 2 == 1 end
end

R.maxCells = 24   -- decoded cell sectors kept (LRU)
R.maxGraphs = 400 -- decoded sector graphs kept between searches (all dropped past this)
R.look = 200      -- string pulling: farthest anchor tried ahead

local clock = debugprofilestop

-- ---------------------------------------------------------------- budget
local job -- the running job, only while its coroutine runs

-- tick(w): w units of work done (1 = about one cell expansion, a few microseconds); the clock is
-- read every 16 units and the coroutine yields once the slice is spent.
local function tick(w)
	local j = job
	if not j then return end
	local n = j.ops + (w or 1)
	j.ops = n
	if n >= j.check then
		j.check = n + 16
		if clock() > j.deadline then yield() end
	end
end

-- Yields first when `ms` would not fit in what is left of the slice: decodes cannot yield
-- halfway, so they start on a fresh frame when the slice is nearly spent.
local function room(ms)
	local j = job
	if not j then return end
	local now = clock()
	-- only when this slice already did some work: a decode longer than a whole slice still runs
	if now + ms > j.deadline and now - j.resumed > 0.05 then yield() end
end

-- decode cost estimate (ms), learned from the decodes done (moving maximum that decays)
local decEst = 0.15

local function decode(s)
	room(decEst)
	local t0 = clock()
	local raw = C_EncodingUtil.DecodeBase64(s)
	local out = raw and C_EncodingUtil.DecompressString(raw, Enum.CompressionMethod.Zlib)
	local dt = clock() - t0
	decEst = max(dt, decEst * 0.97, 0.05)
	if job then job.decodes = job.decodes + 1; job.decodeMs = job.decodeMs + dt end
	return out
end

-- ---------------------------------------------------------------- per map state
local maps = {}

function R.HasData(map)
	local D = SendaNavData and SendaNavData[map]
	return D and D.G and D.C and D.v == 1 and true or false
end

local function M(map)
	local m = maps[map]
	if m and m.D == (SendaNavData and SendaNavData[map]) then return m end
	if not R.HasData(map) then return nil end
	m = { D = SendaNavData[map], swim = SendaNavData[map].swim or 3, cells = {}, ncells = 0, graphs = {}, ngraphs = 0, use = 0 }
	maps[map] = m
	return m
end

-- ---------------------------------------------------------------- cells
-- A decoded sector: s (bytes), first[k + 1] (first layer ordinal of cell k), cellOf[o + 1],
-- L (layers), lb (offset of the link bytes), cb (class bytes), zo[k + 1] (z offset, multi-layer).
local function cells(m, sid)
	local c = m.cells[sid]
	m.use = m.use + 1
	if c then c.used = m.use; return c end
	if c == false then return nil end
	local enc = m.D.C[sid]
	if not enc then m.cells[sid] = false; return nil end
	local s = decode(enc)
	if m.cells[sid] then return cells(m, sid) end
	-- past the cache size, the least recently used sector goes and its tables are reused (less
	-- garbage, so shorter collector steps); the sector just used is never the one evicted
	local first, cellOf
	if m.ncells >= R.maxCells then
		local old, ot
		for k, v in pairs(m.cells) do
			if v and (not ot or v.used < ot) then old, ot = k, v.used end
		end
		if old then
			local oc = m.cells[old]
			m.cells[old] = nil
			m.ncells = m.ncells - 1
			first, cellOf = oc.first, oc.cellOf
			oc.first, oc.cellOf, oc.s = nil, nil, nil
		end
	end
	first, cellOf = first or {}, cellOf or {}
	local o = 0
	for k = 0, SEC * SEC - 1 do
		first[k + 1] = o
		local n = byte(s, 2 + k)
		for _ = 1, n do o = o + 1; cellOf[o] = k end
		if k % 128 == 127 then tick(16) end
	end
	first[SEC * SEC + 1] = o
	local L = o -- cellOf entries past L (from a reused table) are never read
	local lb = 2 + SEC * SEC -- link of ordinal o (0-based), direction d (1-8): byte(s, lb + o * 8 + d - 1)
	local cb = lb + 8 * L
	local zo, zp = {}, cb + L
	for k = 0, SEC * SEC - 1 do
		local n = first[k + 2] - first[k + 1]
		if n >= 2 then zo[k + 1] = zp; zp = zp + 2 * n end
		if k % 256 == 255 then tick(16) end
	end
	m.use = m.use + 1
	c = { s = s, first = first, cellOf = cellOf, L = L, lb = lb, cb = cb, zo = zo, used = m.use }
	m.cells[sid] = c
	m.ncells = m.ncells + 1
	return c
end

local function sidOf(gx, gy) return floor(gy / SEC) * SX + floor(gx / SEC) end
local function inGrid(gx, gy) return gx >= 0 and gy >= 0 and gx < SEC * SX and gy < SEC * SX end

-- Layers of global cell (gx, gy).
local function count(m, gx, gy)
	if not inGrid(gx, gy) then return 0, nil, 0 end
	local c = cells(m, sidOf(gx, gy))
	if not c then return 0, nil, 0 end
	local k = (gy % SEC) * SEC + gx % SEC
	return c.first[k + 2] - c.first[k + 1], c, k
end

local function layerZ(c, k, li)
	local p = c.zo[k + 1]
	if not p then return nil end
	local lo, hi = byte(c.s, p + 2 * li, p + 2 * li + 1)
	local v = lo + hi * 256
	if v >= 32768 then v = v - 65536 end
	return v
end

-- ---------------------------------------------------------------- heap (min, by f)
local function heapNew() return { n = 0, k = {}, v = {} } end
local function push(h, f, v)
	local n = h.n + 1
	h.n = n
	local K, V = h.k, h.v
	while n > 1 do
		local p = floor(n / 2)
		if K[p] <= f then break end
		K[n], V[n] = K[p], V[p]
		n = p
	end
	K[n], V[n] = f, v
end
local function pop(h)
	local n = h.n
	if n == 0 then return nil end
	local K, V = h.k, h.v
	local rf, rv = K[1], V[1]
	local lf, lv = K[n], V[n]
	K[n], V[n] = nil, nil
	n = n - 1
	h.n = n
	local i = 1
	while true do
		local l = i * 2
		if l > n then break end
		local r = l + 1
		if r <= n and K[r] < K[l] then l = r end
		if K[l] >= lf then break end
		K[i], V[i] = K[l], V[l]
		i = l
	end
	if n > 0 then K[i], V[i] = lf, lv end
	return rv, rf
end

local function octile(ax, ay, bx, by)
	local dx, dy = abs(ax - bx), abs(ay - by)
	if dx > dy then return (dx - dy + dy * SQ2) * CELL end
	return (dy - dx + dx * SQ2) * CELL
end

-- ---------------------------------------------------------------- grid search in one sector
-- sources: { ord, cost, ... } pairs; goal: ordinal or nil; reverse: walk the links backwards.
-- Returns dist, parent (tables by ordinal).
local function sectorSearch(m, sid, sources, goal, reverse)
	local c = cells(m, sid)
	local s, first, cellOf, lb, cb = c.s, c.first, c.cellOf, c.lb, c.cb
	local swim = m.swim
	local dist, parent, done = {}, {}, {}
	local h = heapNew()
	local gk = goal and cellOf[goal + 1]
	local gx, gy = gk and gk % SEC, gk and floor(gk / SEC)
	for i = 1, #sources, 2 do
		local o, d0 = sources[i], sources[i + 1]
		if not dist[o] or d0 < dist[o] then
			dist[o] = d0
			local k = cellOf[o + 1]
			push(h, d0 + (gk and octile(k % SEC, floor(k / SEC), gx, gy) or 0), o)
		end
	end
	local j = job
	while true do
		local o = pop(h)
		if not o then break end
		if not done[o] then
			done[o] = true
			j.exp = j.exp + 1
			tick()
			if o == goal then break end
			local k = cellOf[o + 1]
			local x, y = k % SEC, floor(k / SEC)
			local d0 = dist[o]
			if not reverse then
				local base = lb + o * 8 - 1
				for d = 1, 8 do
					local mk = byte(s, base + d)
					if mk > 0 then
						local nx, ny = x + DX[d], y + DY[d]
						if nx >= 0 and ny >= 0 and nx < SEC and ny < SEC then
							local nk = ny * SEC + nx
							local f0, f1 = first[nk + 1], first[nk + 2]
							for li = 0, f1 - f0 - 1 do
								if HAS[mk * 8 + li + 1] then
									local t = f0 + li
									local nd = d0 + LEN[d] * (byte(s, cb + t) == 1 and swim or 1)
									local cur = dist[t]
									if not cur or nd < cur then
										dist[t] = nd
										parent[t] = o
										push(h, nd + (gk and octile(nx, ny, gx, gy) or 0), t)
									end
								end
							end
						end
					end
				end
			else
				local li = o - first[k + 1]
				local cost0 = byte(s, cb + o) == 1 and swim or 1
				for d = 1, 8 do
					local px, py = x - DX[d], y - DY[d]
					if px >= 0 and py >= 0 and px < SEC and py < SEC then
						local pk = py * SEC + px
						for p = first[pk + 1], first[pk + 2] - 1 do
							local mk = byte(s, lb + p * 8 + d - 1)
							if mk > 0 and HAS[mk * 8 + li + 1] then
								local nd = d0 + LEN[d] * cost0
								local cur = dist[p]
								if not cur or nd < cur then
									dist[p] = nd
									parent[p] = o
									push(h, nd + (gk and octile(px, py, gx, gy) or 0), p)
								end
							end
						end
					end
				end
			end
		end
	end
	return dist, parent
end

-- ---------------------------------------------------------------- the entrance graph
-- A decoded sector graph: s, n, co (cost offset), cross[i + 1] = { d, j, cost, ... }, comp[i + 1].
local function graph(m, sid)
	local g = m.graphs[sid]
	if g ~= nil then return g or nil end
	local enc = m.D.G[sid]
	if not enc then m.graphs[sid] = false; return nil end
	local s = decode(enc)
	if m.graphs[sid] then return m.graphs[sid] end
	local n = byte(s, 1)
	local cell, li, comp = {}, {}, {}
	for i = 0, n - 1 do
		local p = 2 + 6 * i
		local a, b, l, _, c0, c1 = byte(s, p, p + 5)
		cell[i + 1], li[i + 1], comp[i + 1] = a + b * 256, l, c0 + c1 * 256
	end
	local co = 2 + 6 * n
	local xo = co + 2 * n * n
	local mc = byte(s, xo) + byte(s, xo + 1) * 256
	local cross = {}
	for q = 0, mc - 1 do
		local p = xo + 2 + 4 * q
		local i, d, jn, c = byte(s, p, p + 3)
		local t = cross[i + 1]
		if not t then t = {}; cross[i + 1] = t end
		t[#t + 1] = d; t[#t + 1] = jn; t[#t + 1] = c / 10
	end
	g = { s = s, n = n, co = co, cell = cell, li = li, comp = comp, cross = cross, sid = sid }
	m.graphs[sid] = g
	m.ngraphs = m.ngraphs + 1
	return g
end

-- Node id: sid * 256 + i.
local function nodeXY(g, i)
	local k = g.cell[i + 1]
	return (g.sid % SX) * SEC + k % SEC, floor(g.sid / SX) * SEC + floor(k / SEC)
end

-- liftAt[node] = { target, cost, name, ... }
local function liftsOf(m)
	if m.liftAt then return m.liftAt end
	local at = {}
	local function find(gx, gy, li)
		local sid = sidOf(gx, gy)
		local g = graph(m, sid)
		if not g then return nil end
		local k = (gy % SEC) * SEC + gx % SEC
		for i = 0, g.n - 1 do
			if g.cell[i + 1] == k and g.li[i + 1] == li then return sid * 256 + i end
		end
	end
	for _, l in ipairs(m.D.L or {}) do
		local a, b = find(l[1], l[2], l[3]), find(l[4], l[5], l[6])
		if a and b then
			at[a] = at[a] or {}
			local t = at[a]; t[#t + 1] = b; t[#t + 1] = l[7]; t[#t + 1] = l[9] or ""
			if l[8] == 0 then
				at[b] = at[b] or {}
				t = at[b]; t[#t + 1] = a; t[#t + 1] = l[7]; t[#t + 1] = l[9] or ""
			end
		end
	end
	m.liftAt = at
	return at
end

-- ---------------------------------------------------------------- ends
-- The nearest cell with layers within r cells of a world point, and the layers to start from:
--   z known: the layer nearest that height;
--   else hint "top" (the player is outdoors): the highest layer;
--   else hint "under" (indoors: a cave, a building, a city under a mountain): the layers with
--   another one above them (every layer if the cell has one);
--   else every layer (the search takes the cheapest).
-- Returns sid, { ord, ... }, gx, gy, z (the height of the layer picked when there is exactly
-- one and the pack has it: single-layer cells carry no height).
local function snap(m, wx, wy, z, r, hint)
	local gx, gy = floor((ORIGIN - wy) / CELL), floor((ORIGIN - wx) / CELL)
	for ring = 0, r do
		local best, bx, by
		for dy = -ring, ring do
			for dx = -ring, ring do
				if max(abs(dx), abs(dy)) == ring then
					local n = count(m, gx + dx, gy + dy)
					if n > 0 then
						local d = dx * dx + dy * dy
						if not best or d < best then best, bx, by = d, gx + dx, gy + dy end
					end
				end
			end
		end
		if best then
			local n, c, k = count(m, bx, by)
			local f0 = c.first[k + 1]
			local out, oz = {}, nil
			if n > 1 and (z or hint == "top" or hint == "under") then
				local bl, bd, top, topz
				for li = 0, n - 1 do
					local lz = layerZ(c, k, li)
					if z then
						local d = lz and abs(lz - z) or 1e9
						if not bd or d < bd then bl, bd = li, d end
					end
					if lz and (not topz or lz > topz) then top, topz = li, lz end
				end
				if z then
					out[1] = f0 + bl
				elseif hint == "top" or not top then
					out[1] = f0 + (top or n - 1)
				else
					for li = 0, n - 1 do
						if li ~= top then out[#out + 1] = f0 + li end
					end
				end
				if #out == 1 then oz = layerZ(c, k, out[1] - f0) end
			else
				for li = 0, n - 1 do out[#out + 1] = f0 + li end
			end
			return sidOf(bx, by), out, bx, by, oz
		end
	end
end
R.snap = function(map, wx, wy, z, hint)
	local m = M(map)
	if not m then return nil end
	local sid, out, gx, gy, oz = snap(m, wx, wy, z, 8, hint)
	if not sid then return nil end
	local zs = {}
	local c = cells(m, sid)
	local k = (gy % SEC) * SEC + gx % SEC
	for i, o in ipairs(out) do zs[i] = layerZ(c, k, o - c.first[k + 1]) or false end
	return gx, gy, zs, oz
end

-- ---------------------------------------------------------------- the walk
local function ordOfNode(m, g, i)
	local c = cells(m, g.sid)
	return c.first[g.cell[i + 1] + 1] + g.li[i + 1]
end

local function chain(parent, o)
	local t = { o }
	while parent[o] do o = parent[o]; t[#t + 1] = o end
	return t
end

-- Global state of an ordinal of sector sid: gx, gy, li.
local function stateOf(m, sid, o)
	local c = cells(m, sid)
	local k = c.cellOf[o + 1]
	return (sid % SX) * SEC + k % SEC, floor(sid / SX) * SEC + floor(k / SEC), o - c.first[k + 1]
end

-- Mask of the layers a straight walk from (ax, ay, layers mask am) reaches at (bx, by);
-- 0 when some step has no link.
local function trace(m, ax, ay, am, bx, by)
	local x, y, cur = ax, ay, am
	local dx, dy = bx - ax, by - ay
	local sx, sy = dx > 0 and 1 or (dx < 0 and -1 or 0), dy > 0 and 1 or (dy < 0 and -1 or 0)
	local adx, ady = abs(dx), abs(dy)
	local i, j = 0, 0
	while i < adx or j < ady do
		local tx, ty = (2 * i + 1) * ady, (2 * j + 1) * adx
		local mx, my
		if i >= adx then mx, my = 0, sy
		elseif j >= ady then mx, my = sx, 0
		elseif tx < ty then mx, my = sx, 0
		elseif ty < tx then mx, my = 0, sy
		else mx, my = sx, sy end
		if mx ~= 0 then i = i + 1 end
		if my ~= 0 then j = j + 1 end
		local d = DIR[(my + 1) * 3 + mx + 2]
		local n, c, k = count(m, x, y)
		local nn = count(m, x + mx, y + my)
		local nxt = 0
		for li = 0, n - 1 do
			if HAS[cur * 8 + li + 1] then
				local mk = byte(c.s, c.lb + (c.first[k + 1] + li) * 8 + d - 1)
				for t = 0, nn - 1 do
					if HAS[mk * 8 + t + 1] and not HAS[nxt * 8 + t + 1] then nxt = nxt + 2 ^ t end
				end
			end
		end
		if nxt == 0 then return 0 end
		cur = nxt
		x, y = x + mx, y + my
		tick()
	end
	return cur
end
R.trace = function(map, ax, ay, al, bx, by, bl)
	local m = M(map)
	return m and HAS[trace(m, ax, ay, 2 ^ al, bx, by) * 8 + bl + 1] or false
end

local function run(m, req)
	local ssid, so = snap(m, req.sx, req.sy, req.sz, 8, req.shint)
	-- goal height unknown: with `tnear` and a known start height, the goal floor nearest it (a floor
	-- picked by a hint is not a height: from the top of a city the nearest goal floor can be a roof)
	local tz = req.tz
	if tz == nil and req.tnear then tz = req.sz end
	local gsid, go, ggx, ggy = snap(m, req.tx, req.ty, tz, 8, req.thint)
	if not ssid or not gsid then return nil, "offmesh" end
	local src, gsrc = {}, {}
	for _, o in ipairs(so) do src[#src + 1] = o; src[#src + 1] = 0 end
	for _, o in ipairs(go) do gsrc[#gsrc + 1] = o; gsrc[#gsrc + 1] = 0 end
	local fd, fp = sectorSearch(m, ssid, src, nil, false)
	local bd, bp = sectorSearch(m, gsid, gsrc, nil, true)
	-- direct inside one sector
	local best, bestGoal, last = math.huge, nil, nil
	if ssid == gsid then
		for _, o in ipairs(go) do
			if fd[o] and fd[o] < best then best, bestGoal = fd[o], o end
		end
	end
	local sg, gg = graph(m, ssid), graph(m, gsid)
	local goalCost, goalComp = {}, {}
	if gg then
		for i = 0, gg.n - 1 do
			local c = bd[ordOfNode(m, gg, i)]
			if c then goalCost[gsid * 256 + i] = c; goalComp[gg.comp[i + 1]] = true end
		end
	end
	local dist, par, closed = {}, {}, {}
	local h = heapNew()
	local hx, hy = ggx, ggy
	local any = false
	if sg then
		for i = 0, sg.n - 1 do
			local c = fd[ordOfNode(m, sg, i)]
			if c then
				local id = ssid * 256 + i
				dist[id] = c; par[id] = false
				local x, y = nodeXY(sg, i)
				push(h, c + octile(x, y, hx, hy), id)
				if goalComp[sg.comp[i + 1]] then any = true end
			end
		end
	end
	if not bestGoal and not any then return nil, "unreachable" end
	local liftAt = liftsOf(m)
	local j = job
	while true do
		local id, f = pop(h)
		if not id or f >= best then break end
		if not closed[id] then
			closed[id] = true
			j.aexp = j.aexp + 1
			tick(16) -- an expansion reads up to 255 costs: check the clock every time
			local d0 = dist[id]
			local gc = goalCost[id]
			if gc and d0 + gc < best then best, last = d0 + gc, id end
			local sid, i = floor(id / 256), id % 256
			local g = graph(m, sid)
			local s, n, co = g.s, g.n, g.co
			local p = co + 2 * i * n
			for jn = 0, n - 1 do
				if jn ~= i then
					local lo, hi = byte(s, p + 2 * jn, p + 2 * jn + 1)
					local c = lo + hi * 256
					if c ~= NOCOST then
						local t = sid * 256 + jn
						local nd = d0 + c
						if not dist[t] or nd < dist[t] then
							dist[t] = nd; par[t] = id
							local x, y = nodeXY(g, jn)
							push(h, nd + octile(x, y, hx, hy), t)
						end
					end
				end
			end
			local cr = g.cross[i + 1]
			if cr then
				local x0, y0 = nodeXY(g, i)
				for q = 1, #cr, 3 do
					local d, jn, c = cr[q], cr[q + 1], cr[q + 2]
					local sid2 = sidOf(x0 + DX[d + 1], y0 + DY[d + 1])
					local g2 = graph(m, sid2)
					if g2 then
						local t = sid2 * 256 + jn
						local nd = d0 + c
						if not dist[t] or nd < dist[t] then
							dist[t] = nd; par[t] = id
							local x, y = nodeXY(g2, jn)
							push(h, nd + octile(x, y, hx, hy), t)
						end
					end
				end
			end
			local lf = liftAt[id]
			if lf then
				for q = 1, #lf, 3 do
					local t, c = lf[q], lf[q + 1]
					local nd = d0 + c
					if not dist[t] or nd < dist[t] then
						dist[t] = nd; par[t] = id
						local x, y = nodeXY(graph(m, floor(t / 256)), t % 256)
						push(h, nd + octile(x, y, hx, hy), t)
					end
				end
			end
		end
	end
	if best == math.huge then return nil, "unreachable" end
	-- refine into states { gx, gy, li, ... } and the lift breaks (break after state index b)
	local pts, breaks = {}, {}
	local function add(sid, o)
		local x, y, li = stateOf(m, sid, o)
		pts[#pts + 1] = x; pts[#pts + 1] = y; pts[#pts + 1] = li
	end
	if not last then
		local t = chain(fp, bestGoal)
		for q = #t, 1, -1 do add(ssid, t[q]) end
	else
		local hops = { last }
		while par[hops[#hops]] do hops[#hops + 1] = par[hops[#hops]] end
		local first = hops[#hops]
		local fsid = floor(first / 256)
		local t = chain(fp, ordOfNode(m, graph(m, fsid), first % 256))
		for q = #t, 1, -1 do add(ssid, t[q]) end
		for q = #hops, 2, -1 do
			local a, b = hops[q], hops[q - 1]
			local sa, sb = floor(a / 256), floor(b / 256)
			local ga, gb = graph(m, sa), graph(m, sb)
			local liftName
			local lf = liftAt[a]
			if lf then for z = 1, #lf, 3 do if lf[z] == b then liftName = lf[z + 2] end end end
			if liftName then
				breaks[#pts / 3] = liftName
				add(sb, ordOfNode(m, gb, b % 256))
			elseif sa ~= sb then
				add(sb, ordOfNode(m, gb, b % 256))
			else
				local oa, ob = ordOfNode(m, ga, a % 256), ordOfNode(m, gb, b % 256)
				local _, rp = sectorSearch(m, sa, { oa, 0 }, ob, false)
				local c2 = chain(rp, ob)
				for z = #c2 - 1, 1, -1 do add(sa, c2[z]) end
			end
		end
		local lg = graph(m, floor(last / 256))
		local c3 = chain(bp, ordOfNode(m, lg, last % 256))
		for z = 2, #c3 do add(gsid, c3[z]) end
	end
	-- string pulling: from each anchor the farthest point in sight (up to `look` ahead)
	local n = #pts / 3
	local keep = { 1 }
	local i = 1
	local look = req.look or R.look
	while i < n do
		local stop = n
		for b = i, n - 1 do if breaks[b] then stop = b; break end end
		if stop == i then
			i = i + 1; keep[#keep + 1] = i
		else
			local bestj = i + 1
			local ax, ay, al = pts[3 * i - 2], pts[3 * i - 1], pts[3 * i]
			for jj = min(stop, i + look), i + 2, -1 do
				local bx, by, bl = pts[3 * jj - 2], pts[3 * jj - 1], pts[3 * jj]
				local mk = trace(m, ax, ay, 2 ^ al, bx, by)
				if HAS[mk * 8 + bl + 1] then bestj = jj; break end
			end
			i = bestj; keep[#keep + 1] = i
		end
	end
	local out = {}
	for _, q in ipairs(keep) do
		local gx, gy, li = pts[3 * q - 2], pts[3 * q - 1], pts[3 * q]
		local _, c, k = count(m, gx, gy)
		out[#out + 1] = {
			wx = ORIGIN - (gy + 0.5) * CELL, wy = ORIGIN - (gx + 0.5) * CELL,
			z = c and layerZ(c, k, li) or nil,
			gx = gx, gy = gy, li = li,
			lift = breaks[q],
		}
	end
	return out, best
end

-- ---------------------------------------------------------------- jobs
local queue = {}

-- Find(map, {sx, sy, sz?, shint?, tx, ty, tz?, thint?, tnear?, look?}, callback(points | nil, cost | reason, job)) -> job
-- sz / tz: heights of the ends (the floor nearest each); shint / thint: "top" or "under" when the
-- height is unknown (see snap); tnear: without tz, the goal floor nearest sz.
-- points = { {wx, wy, z?, gx, gy, li, lift = name|nil}, ... }: a point with `lift` is the start
-- of a ride (lift or portal) that ends at the next point.
function R.Find(map, req, callback)
	local m = M(map)
	local j = { map = map, req = req, callback = callback, ops = 0, check = 16, exp = 0, aexp = 0, frames = 0, decodes = 0, decodeMs = 0, cpu = 0 }
	if not m then
		callback(nil, "nodata", j)
		return j
	end
	-- no pcall inside: Lua 5.1 cannot yield across it; resume reports the error instead
	j.co = create(function() return run(m, req) end)
	queue[#queue + 1] = j
	return j
end

function R.Cancel(j) if j then j.cancelled = true end end
function R.Busy() return queue[1] ~= nil end

local function trim()
	for _, m in pairs(maps) do
		if m.ngraphs > R.maxGraphs then m.graphs, m.ngraphs, m.liftAt = {}, 0, nil end
	end
end

-- Runs queued jobs for at most ms milliseconds (one slice; call once a frame).
function R.Step(ms)
	local t0 = clock()
	local deadline = t0 + ms
	while queue[1] and clock() < deadline do
		local j = queue[1]
		if j.cancelled then
			table.remove(queue, 1)
		else
			j.deadline = deadline
			j.frames = j.frames + 1
			job = j
			local ts = clock()
			j.resumed = ts
			local ok, a, b = resume(j.co)
			j.cpu = j.cpu + (clock() - ts)
			job = nil
			if status(j.co) == "dead" then
				table.remove(queue, 1)
				trim()
				if j.cancelled then
					-- dropped silently
				elseif not ok then
					j.callback(nil, "error: " .. tostring(a), j)
				else
					j.callback(a, b, j)
				end
			else
				break
			end
		end
	end
end

-- Drops decoded data (call after a while without searches).
function R.Idle()
	for _, m in pairs(maps) do m.cells, m.ncells, m.graphs, m.ngraphs, m.liftAt = {}, 0, {}, 0, nil end
end

-- Forgets a map entirely (its pack must also be released by the caller).
function R.Drop(map)
	maps[map] = nil
	for i = #queue, 1, -1 do
		if queue[i].map == map then queue[i].cancelled = true end
	end
end

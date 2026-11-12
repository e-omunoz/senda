-- tests/navsim: the slice of the WoW: Forever client API that Senda_Nav uses, for headless runs in
-- the official Lua 5.1 (src/main.rs). Copyright (C) 2026 Senda contributors. GPL-3.0-only.
--
-- The host (src/main.rs) provides: navsim.readfile(path), navsim.root (repo root),
-- navsim.frames[uiMap] = { map, left, right, top, bottom } (forever-db ui_map.jsonl, the client's
-- UiMap frames), C_EncodingUtil.DecodeBase64 / DecompressString, Enum, debugprofilestop.

local frames = navsim.frames

-- ---------------------------------------------------------------- combat
navsim.combat = false
function InCombatLockdown() return navsim.combat end

-- ---------------------------------------------------------------- vectors and C_Map
local V = {}
V.__index = V
function V:GetXY() return self.x, self.y end
function CreateVector2D(x, y) return setmetatable({ x = x, y = y }, V) end

C_Map = {}
-- (uiMap, normalized map position) -> continent, world position (x = north, y = west)
function C_Map.GetWorldPosFromMapPos(map, pos)
	local f = frames[map]
	if not f then return nil end
	local x, y = pos:GetXY()
	return f.map, CreateVector2D(f.top + (f.bottom - f.top) * y, f.left + (f.right - f.left) * x)
end
-- (continent, world position, override?) -> uiMap, normalized position. Without an override, the
-- smallest map of that continent that contains the point (a zone before its continent).
function C_Map.GetMapPosFromWorldPos(c, pos, override)
	local wx, wy = pos:GetXY()
	local function at(f) return (wy - f.left) / (f.right - f.left), (wx - f.top) / (f.bottom - f.top) end
	if override then
		local f = frames[override]
		if not f or f.map ~= c then return nil end
		return override, CreateVector2D(at(f))
	end
	local best, ba
	for ui, f in pairs(frames) do
		if f.map == c then
			local x, y = at(f)
			if x >= 0 and x <= 1 and y >= 0 and y <= 1 then
				local a = math.abs((f.right - f.left) * (f.bottom - f.top))
				if not ba or a < ba then best, ba = ui, a end
			end
		end
	end
	if not best then return nil end
	return best, CreateVector2D(at(frames[best]))
end

-- ---------------------------------------------------------------- frames
local all = {}
local F = {}
F.__index = F
function F:SetScript(k, fn) self.scripts[k] = fn end
function F:GetScript(k) return self.scripts[k] end
function F:RegisterEvent(e) self.events[e] = true end
function F:UnregisterEvent(e) self.events[e] = nil end
function F:Show() self.shown = true end
function F:Hide() self.shown = false end
function CreateFrame()
	local f = setmetatable({ scripts = {}, events = {}, shown = true }, F)
	all[#all + 1] = f
	return f
end

-- One rendered frame: every shown frame's OnUpdate. Returns how many ran.
function navsim.frame(elapsed)
	local n = 0
	for _, f in ipairs(all) do
		local fn = f.shown and f.scripts.OnUpdate
		if fn then fn(f, elapsed); n = n + 1 end
	end
	return n
end
function navsim.event(e, ...)
	for _, f in ipairs(all) do
		local fn = f.events[e] and f.scripts.OnEvent
		if fn then fn(f, e, ...) end
	end
end
function navsim.updating()
	for _, f in ipairs(all) do if f.shown and f.scripts.OnUpdate then return true end end
	return false
end

-- ---------------------------------------------------------------- addons
-- Loads addon/<name>/<name>.toc: its files in order, each called with (name, namespace).
local loaded = {}
C_AddOns = {}
function C_AddOns.IsAddOnLoaded(name) return loaded[name] == true end
function C_AddOns.LoadAddOn(name)
	if loaded[name] then return true end
	local dir = navsim.root .. "/addon/" .. name .. "/"
	local toc = navsim.readfile(dir .. name .. ".toc")
	if not toc then return false, "MISSING" end
	local ns = {}
	navsim.toc = navsim.toc or {}
	local meta = {}
	for line in toc:gmatch("[^\r\n]+") do
		local k, v = line:match("^##%s*([%w%-]+):%s*(.-)%s*$")
		if k then
			meta[k] = v
		elseif not line:match("^#") and line:match("%S") then
			local file = line:gsub("\\", "/"):match("^%s*(.-)%s*$")
			local src = navsim.readfile(dir .. file)
			if not src then return false, "MISSING " .. file end
			local fn, err = loadstring(src, "@" .. name .. "/" .. file)
			if not fn then error(err) end
			fn(name, ns)
		end
	end
	navsim.toc[name] = meta
	loaded[name] = true
	return true
end

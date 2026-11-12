-- Navigation mock: C_EncodingUtil (base64 here, zlib through node's zlib: __zinflate / __zdeflate),
-- C_AddOns.LoadAddOn for the load-on-demand add-ons Senda_Nav (the REAL addon/Senda_Nav files:
-- Router.lua and SendaNav.lua) and the continent packs, which are synthetic: one 64x64 sector built here
-- in the real pack format (docs/NAV.md, section 3) around a point of a mock map, with a wall to walk around.
-- Loading an add-on in combat is recorded as API misuse (Senda must wait for PLAYER_REGEN_ENABLED).
local Sim = Sim
local load = load -- PrepareClientEnv removes the global; the side add-ons are loaded with this one

-- fengari has no collector API (lua_gc): "count" (SendaNav's load stats) answers 0, the rest is a no-op.
local gc = collectgarbage
function collectgarbage(opt, ...)
  local ok, r = pcall(gc, opt, ...)
  if ok then return r end
  return 0
end

------------------------------------------------------------------------------
-- Encoding
------------------------------------------------------------------------------

local B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
local B64I = {}
for i = 1, 64 do B64I[B64:byte(i)] = i - 1 end

local function b64encode(s)
  local out = {}
  for i = 1, #s, 3 do
    local a, b, c = s:byte(i, i + 2)
    local n = a * 65536 + (b or 0) * 256 + (c or 0)
    local c1, c2 = math.floor(n / 262144) % 64, math.floor(n / 4096) % 64
    local c3, c4 = math.floor(n / 64) % 64, n % 64
    out[#out + 1] = B64:sub(c1 + 1, c1 + 1) .. B64:sub(c2 + 1, c2 + 1)
      .. (b and B64:sub(c3 + 1, c3 + 1) or "=") .. (c and B64:sub(c4 + 1, c4 + 1) or "=")
  end
  return table.concat(out)
end

local function b64decode(s)
  local out, n, bits = {}, 0, 0
  for i = 1, #s do
    local v = B64I[s:byte(i)]
    if v then
      n, bits = n * 64 + v, bits + 6
      if bits >= 8 then
        bits = bits - 8
        local d = 2 ^ bits
        out[#out + 1] = string.char(math.floor(n / d) % 256)
        n = n % d
      end
    end
  end
  return table.concat(out)
end
Sim.B64Encode, Sim.B64Decode = b64encode, b64decode

Enum.CompressionMethod = { Deflate = 0, Zlib = 1 }
C_EncodingUtil = {}
function C_EncodingUtil.DecodeBase64(s)
  if type(s) ~= "string" then error("C_EncodingUtil.DecodeBase64: source must be a string", 2) end
  return b64decode(s)
end
function C_EncodingUtil.DecompressString(s, method)
  if type(s) ~= "string" then error("C_EncodingUtil.DecompressString: source must be a string", 2) end
  if method ~= Enum.CompressionMethod.Zlib then error("C_EncodingUtil.DecompressString: only Zlib in the mock", 2) end
  return __zinflate(s)
end

------------------------------------------------------------------------------
-- Synthetic packs
------------------------------------------------------------------------------

local ADT = 1600 / 3
local CELL = ADT / 128
local SEC = 64
local ORIGIN = 32 * ADT
local DX = { 1, 1, 0, -1, -1, -1, 0, 1 }
local DY = { 0, 1, 1, 1, 0, -1, -1, -1 }

-- Global cell of a mock map point (x, y in 0-1).
local function cellOf(map, x, y)
  local m = Sim.MapData(map)
  local wn, ww = m.n - y * m.sy, m.w - x * m.sx
  return math.floor((ORIGIN - ww) / CELL), math.floor((ORIGIN - wn) / CELL), m.continent
end

-- Pack for `continent` with one sector: the one holding (map, x, y). Every cell walkable (one layer, links
-- to its 8 neighbours; diagonals only when both sides are open) except opts.blocked(lx, ly) -> true.
-- Returns the pack table (SendaNavData[continent]) with pack.info = { map, gx0, gy0, sid }.
function Sim.NavPack(map, x, y, opts)
  opts = opts or {}
  local gx, gy, continent = cellOf(map, x, y)
  local sx, sy = math.floor(gx / SEC), math.floor(gy / SEC)
  local sid = sy * 128 + sx
  local blocked = opts.blocked or function() return false end
  local open = {}
  for ly = 0, SEC - 1 do
    for lx = 0, SEC - 1 do open[ly * SEC + lx] = not blocked(lx, ly) end
  end
  local function isOpen(lx, ly) return lx >= 0 and ly >= 0 and lx < SEC and ly < SEC and open[ly * SEC + lx] end
  local counts, links, classes = {}, {}, {}
  for k = 0, SEC * SEC - 1 do
    local lx, ly = k % SEC, math.floor(k / SEC)
    if open[k] then
      counts[#counts + 1] = string.char(1)
      for d = 1, 8 do
        local nx, ny = lx + DX[d], ly + DY[d]
        local ok = isOpen(nx, ny)
        if ok and DX[d] ~= 0 and DY[d] ~= 0 then ok = isOpen(lx + DX[d], ly) and isOpen(lx, ly + DY[d]) end
        links[#links + 1] = string.char(ok and 1 or 0)
      end
      classes[#classes + 1] = string.char(0)
    else
      counts[#counts + 1] = string.char(0)
    end
  end
  local raw = string.char(1) .. table.concat(counts) .. table.concat(links) .. table.concat(classes)
  local D = { v = 1, map = continent, cell = CELL, sec = SEC, swim = 3, G = {}, C = {}, L = {} }
  D.C[sid] = b64encode(__zdeflate(raw))
  D.info = { map = map, gx0 = sx * SEC, gy0 = sy * SEC, sid = sid, continent = continent }
  return D
end

-- Centre of local cell (lx, ly) of a pack's sector as a point (0-1) of the pack's map.
function Sim.NavPoint(D, lx, ly)
  local info = D.info
  local m = Sim.MapData(info.map)
  local wn = ORIGIN - (info.gy0 + ly + 0.5) * CELL
  local ww = ORIGIN - (info.gx0 + lx + 0.5) * CELL
  return (m.w - ww) / m.sx, (m.n - wn) / m.sy
end

-- Local cell of a mock map point inside a pack's sector.
function Sim.NavCell(D, map, x, y)
  local gx, gy = cellOf(map, x, y)
  return gx - D.info.gx0, gy - D.info.gy0
end

------------------------------------------------------------------------------
-- Load-on-demand add-ons
------------------------------------------------------------------------------

Sim.addonLoads = {}  -- { name, combat, time } for every C_AddOns.LoadAddOn call
Sim.navInstalled = nil -- set by Sim.EnableNav: { Senda_Nav = true, Senda_Nav_EK = pack|true, ... }
local loadedSide = {}

-- Runs <root>/<name>/<name>.toc's Lua files with their own namespace (the client's varargs), without
-- touching the main add-on's state (Sim.addonName, its .toc metadata, its SavedVariables).
function Sim.LoadSideAddon(root, name)
  local base = root .. "/" .. name
  local toc = __readfile(base .. "/" .. name .. ".toc")
  if not toc then return false end
  local ns = {}
  for line in (toc .. "\n"):gmatch("([^\r\n]*)\r?\n") do
    if line:match("%S") and not line:match("^%s*#") then
      local rel = line:match("^%s*(.-)%s*$"):gsub("\\", "/")
      local src = __readfile(base .. "/" .. rel)
      if not src then error("cannot read " .. name .. "/" .. rel) end
      local chunk, err = load(src, "@" .. name .. "/" .. rel, "t")
      if not chunk then Sim.RecordError(err, "syntax " .. name .. "/" .. rel); return false end
      if not Sim.SafeCall("loading " .. name .. "/" .. rel, chunk, name, ns) then return false end
    end
  end
  return true
end

-- Makes the navigation add-ons installed: the real Senda_Nav and the given packs ({ [0] = pack, [1] = pack };
-- a continent without a pack is not installed).
function Sim.EnableNav(packs)
  packs = packs or {}
  Sim.navInstalled = { Senda_Nav = true, Senda_Nav_EK = packs[0], Senda_Nav_Kalimdor = packs[1] }
end

local PACK_OF = { Senda_Nav_EK = 0, Senda_Nav_Kalimdor = 1 }

function C_AddOns.LoadAddOn(name)
  if type(name) ~= "string" and type(name) ~= "number" then error("C_AddOns.LoadAddOn: name must be a string", 2) end
  Sim.addonLoads[#Sim.addonLoads + 1] = { name = name, combat = Sim.player.combat, time = Sim.time }
  local inst = Sim.navInstalled
  if not (inst and inst[name]) then return false, "MISSING" end
  if Sim.player.combat then
    Sim.Misuse("C_AddOns.LoadAddOn", "loaded " .. name .. " in combat")
  end
  if loadedSide[name] then return true end
  local ok
  if name == "Senda_Nav" then
    ok = Sim.LoadSideAddon(SIM_ROOT, "Senda_Nav")
  else
    local c = PACK_OF[name]
    SendaNavData = rawget(_G, "SendaNavData") or {}
    SendaNavData[c] = inst[name]
    ok = true
  end
  loadedSide[name] = ok or nil
  return ok and true or false, ok and nil or "CORRUPT"
end

function Sim.NavLoaded(name) return loadedSide[name] == true end

-- Flying (IsFlying) for the arrow's straight fallback.
function IsFlying() return Sim.player.flying == true end

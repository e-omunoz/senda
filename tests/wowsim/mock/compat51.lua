-- Lua 5.1 compatibility shims for fengari (Lua 5.3), limited to what WoW's Lua 5.1 offers and the
-- addon (or the mock) relies on. Integral floats already print without ".0" (FENGARICONF in run.js).

unpack = unpack or table.unpack
table.getn = table.getn or function(t) return #t end
math.pow = math.pow or function(a, b) return a ^ b end
math.mod = math.mod or math.fmod
math.ldexp = math.ldexp or function(m, e) return m * 2.0 ^ e end
loadstring = loadstring or function(s, name) return load(s, name) end

if not math.atan2 then
  local atan = math.atan
  math.atan2 = function(y, x) return atan(y, x) end
end

-- table.maxn: largest positive numeric key (WoW's 5.1 has it, 5.3 removed it).
table.maxn = table.maxn or function(t)
  local n = 0
  for k in pairs(t) do
    if type(k) == "number" and k > n then n = k end
  end
  return n
end

-- string.format: Lua 5.1 truncates non-integral numbers for %d/%x/%c...; 5.3 raises
-- "number has no integer representation". In the other direction, 5.3's %s accepts any value via
-- tostring, while WoW (5.1) raises "string expected, got nil". Emulate 5.1 in both cases so the sim
-- neither invents errors nor hides real ones.
do
  local orig = string.format
  local INT = { d = true, i = true, c = true, o = true, u = true, x = true, X = true }
  local floor, ceil, type, tonumber, select = math.floor, math.ceil, type, tonumber, select
  local function trunc(n) if n >= 0 then return floor(n) else return ceil(n) end end
  string.format = function(fmt, ...)
    if type(fmt) ~= "string" and type(fmt) ~= "number" then
      return orig(fmt, ...) -- let the original raise its usual error
    end
    local n = select("#", ...)
    local args = { ... }
    local i = 0
    for _, conv in tostring(fmt):gmatch("%%([%-%+ #0]*%d*%.?%d*)([%a%%])") do
      if conv ~= "%" then
        i = i + 1
        local v = args[i]
        if i > n then
          error(("bad argument #%d to 'format' (no value)"):format(i + 1), 2)
        end
        if INT[conv] then
          local num = tonumber(v)
          if num and num == num and num ~= math.huge and num ~= -math.huge then args[i] = trunc(num) end
        elseif conv == "s" then
          if type(v) ~= "string" and type(v) ~= "number" then
            error(("bad argument #%d to 'format' (string expected, got %s)"):format(i + 1, type(v)), 2)
          end
        end
      end
    end
    return orig(fmt, unpack(args, 1, n))
  end
  -- ("%d"):format(x) goes through the string metatable, which indexes the same `string` table.
end

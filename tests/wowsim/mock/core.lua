-- Simulation core: clock, timers (C_Timer), error capture, protected handler calls, event dispatch,
-- chat output and the generic WoW Lua utility globals (strsplit, wipe, tinsert...).
Sim = Sim or {}
local Sim = Sim

Sim.time = 1000.0          -- GetTime()
Sim.errors = {}            -- { msg, where }
Sim.warnings = {}          -- API misuse that did not raise inside the addon, mock gaps...
Sim.chat = {}              -- every line added to a chat frame (colour codes stripped)
Sim.log = {}
Sim.unknownMethods = {}    -- ["Type:Method"] = count (permissive widget fallback)
Sim.missingGlobals = {}    -- [name] = count (read of an undefined global)
Sim.verbose = false
Sim.frameHooks = {}        -- functions run once per simulated frame, after timers and OnUpdate

local out = __out or print

function Sim.Out(s) out(tostring(s)) end

function Sim.StripCodes(s)
  s = tostring(s or "")
  s = s:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", "")
  s = s:gsub("|H.-|h(.-)|h", "%1"):gsub("|T.-|t", "")
  return s
end

------------------------------------------------------------------------------
-- Errors
------------------------------------------------------------------------------

function Sim.RecordError(msg, where)
  msg = tostring(msg)
  Sim.errors[#Sim.errors + 1] = { msg = msg, where = where or "?" }
  Sim.Out("  !! LUA ERROR (" .. tostring(where) .. "): " .. msg)
end

function Sim.Warn(msg)
  for _, w in ipairs(Sim.warnings) do if w == msg then return end end
  Sim.warnings[#Sim.warnings + 1] = msg
  if Sim.verbose then Sim.Out("  ?? " .. msg) end
end

local traceback = debug.traceback
local function handler(err)
  return traceback(tostring(err), 2)
end

-- Calls fn(...) like the client calls a script handler: errors go to the error handler (= failure).
function Sim.SafeCall(where, fn, ...)
  if type(fn) ~= "function" then return end
  local r = table.pack(xpcall(fn, handler, ...))
  if not r[1] then
    Sim.RecordError(r[2], where)
    return false
  end
  return true, table.unpack(r, 2, r.n)
end

-- geterrorhandler(): the addon reports errors it catches itself (Events bus, tab builders) here.
local errorHandler = function(err)
  Sim.RecordError(traceback(tostring(err), 2), "geterrorhandler")
end
function geterrorhandler() return errorHandler end
function seterrorhandler(fn) errorHandler = fn end

------------------------------------------------------------------------------
-- Clock and timers
------------------------------------------------------------------------------

local timers = {}
local timerSeq = 0

local function schedule(delay, fn, ticker)
  timerSeq = timerSeq + 1
  local t = { due = Sim.time + math.max(0, tonumber(delay) or 0), fn = fn, seq = timerSeq, ticker = ticker }
  timers[#timers + 1] = t
  return t
end

local TimerObj = {}
TimerObj.__index = TimerObj
function TimerObj:Cancel() self.cancelled = true; if self.entry then self.entry.cancelled = true end end
function TimerObj:IsCancelled() return self.cancelled == true end

C_Timer = {}
function C_Timer.After(delay, fn)
  if type(delay) ~= "number" then error("Usage: C_Timer.After(seconds, callback)", 2) end
  if type(fn) ~= "function" then error("Usage: C_Timer.After(seconds, callback): callback must be a function", 2) end
  schedule(delay, fn)
end
function C_Timer.NewTimer(delay, fn)
  if type(fn) ~= "function" then error("Usage: C_Timer.NewTimer(seconds, callback)", 2) end
  local obj = setmetatable({}, TimerObj)
  obj.entry = schedule(delay, function() if not obj.cancelled then fn(obj) end end)
  return obj
end
function C_Timer.NewTicker(interval, fn, iterations)
  if type(interval) ~= "number" or type(fn) ~= "function" then error("Usage: C_Timer.NewTicker(seconds, callback [, iterations])", 2) end
  local obj = setmetatable({ left = iterations }, TimerObj)
  local function tick()
    if obj.cancelled then return end
    fn(obj)
    if obj.left then obj.left = obj.left - 1; if obj.left <= 0 then obj.cancelled = true; return end end
    if not obj.cancelled then obj.entry = schedule(interval, tick, true) end
  end
  obj.entry = schedule(interval, tick, true)
  return obj
end

function GetTime() return Sim.time end
function GetTimePreciseSec() return Sim.time end
function debugprofilestop() return Sim.time * 1000 end
function time() return 1793000000 + math.floor(Sim.time) end
date = os.date

local function runDueTimers()
  local guard = 0
  while true do
    guard = guard + 1
    if guard > 10000 then Sim.RecordError("timer storm (more than 10000 callbacks in one frame)", "C_Timer"); return end
    local best, bi
    for i, t in ipairs(timers) do
      if t.due <= Sim.time + 1e-9 and (not best or t.due < best.due or (t.due == best.due and t.seq < best.seq)) then
        best, bi = t, i
      end
    end
    if not best then return end
    table.remove(timers, bi)
    if not best.cancelled then Sim.SafeCall("C_Timer callback", best.fn) end
  end
end

Sim.FRAME = 0.05 -- seconds per simulated frame (20 fps)

-- Advances the clock `sec` seconds: timers, then OnUpdate of every visible frame, once per frame.
function Sim.Advance(sec)
  local steps = math.max(1, math.floor((sec or 0) / Sim.FRAME + 0.5))
  for _ = 1, steps do
    Sim.time = Sim.time + Sim.FRAME
    runDueTimers()
    if Sim.RunOnUpdate then Sim.RunOnUpdate(Sim.FRAME) end
    for _, hook in ipairs(Sim.frameHooks) do hook() end
  end
end

-- Advances frame by frame until the clock reaches `t` (the two-player mode keeps both clients in step).
function Sim.AdvanceTo(t)
  while Sim.time + Sim.FRAME / 2 < t do Sim.Advance(Sim.FRAME) end
end

function Sim.PendingTimers()
  local n = 0
  for _, t in ipairs(timers) do if not t.cancelled then n = n + 1 end end
  return n
end

------------------------------------------------------------------------------
-- Events (frames register through the widget API, see frames.lua)
------------------------------------------------------------------------------

Sim.eventFrames = {} -- event -> { frame, ... } in registration order

-- Events treated as unknown: RegisterEvent raises like the real client does for a missing event, which
-- exercises the add-on's guards (Senda.Events:On wraps RegisterEvent in pcall).
Sim.REMOVED_EVENTS = {
  LEARNED_SPELL_IN_TAB = true,      -- 11.0: replaced by LEARNED_SPELL_IN_SKILL_LINE
  CHARACTER_POINTS_CHANGED = true,  -- classic talent-points event; not expected on a Mainline 12.x client
}

function Sim.Fire(event, ...)
  local list = Sim.eventFrames[event]
  if Sim.verbose then Sim.Out("  > event " .. event) end
  if not list then return end
  local snapshot = {}
  for i, f in ipairs(list) do snapshot[i] = f end
  local unit = ...
  for _, f in ipairs(snapshot) do
    local reg = f.__events[event]
    if reg and (reg == true or (type(reg) == "table" and reg[unit])) then
      local script = f.__scripts.OnEvent
      if script then Sim.SafeCall("OnEvent " .. event .. " (" .. (f:GetName() or "anonymous frame") .. ")", script, f, event, ...) end
      for _, hook in ipairs(f.__hooks.OnEvent or {}) do
        Sim.SafeCall("OnEvent hook " .. event, hook, f, event, ...)
      end
    end
  end
end

------------------------------------------------------------------------------
-- WoW Lua utility globals
------------------------------------------------------------------------------

function strsplit(sep, s, limit)
  if type(sep) ~= "string" or type(s) ~= "string" then error("Usage: strsplit(delimiter, subject [, pieces])", 2) end
  local outt, start = {}, 1
  while true do
    if limit and #outt == limit - 1 then outt[#outt + 1] = s:sub(start); break end
    local i = nil
    for j = start, #s do
      if sep:find(s:sub(j, j), 1, true) then i = j; break end
    end
    if not i then outt[#outt + 1] = s:sub(start); break end
    outt[#outt + 1] = s:sub(start, i - 1)
    start = i + 1
  end
  return table.unpack(outt)
end
function strjoin(sep, ...) return table.concat({ ... }, sep) end
function strtrim(s, chars)
  chars = chars or " \t\r\n"
  local p = "[" .. chars:gsub("[%]%^%-%%]", "%%%0") .. "]"
  return (s:gsub("^" .. p .. "+", ""):gsub(p .. "+$", ""))
end
function strconcat(...) return table.concat({ ... }) end
function wipe(t)
  if type(t) ~= "table" then error("bad argument #1 to 'wipe' (table expected, got " .. type(t) .. ")", 2) end
  for k in pairs(t) do t[k] = nil end
  return t
end
table.wipe = wipe
tinsert, tremove, tContains = table.insert, table.remove, nil
function tContains(t, v) for _, x in ipairs(t) do if x == v then return true end end return false end
format, strfind, strsub, strlen, strlower, strupper, strrep, strbyte, strchar, strmatch, gsub, gmatch =
  string.format, string.find, string.sub, string.len, string.lower, string.upper, string.rep, string.byte, string.char,
  string.match, string.gsub, string.gmatch
floor, ceil, abs, max, min, sqrt, mod = math.floor, math.ceil, math.abs, math.max, math.min, math.sqrt, math.fmod
random = math.random
sort = table.sort
getn = table.getn
function issecretvalue() return false end -- Midnight API: nothing is secret out of combat in the sim
function securecall(fn, ...) if type(fn) == "string" then fn = _G[fn] end return fn(...) end
function hooksecurefunc(a, b, c)
  local tbl, name, hook
  if type(a) == "table" then tbl, name, hook = a, b, c else tbl, name, hook = _G, a, b end
  local orig = tbl[name]
  if type(orig) ~= "function" then error("hooksecurefunc(): " .. tostring(name) .. " is not a function", 2) end
  tbl[name] = function(...)
    local r = table.pack(orig(...))
    Sim.SafeCall("hooksecurefunc " .. tostring(name), hook, ...)
    return table.unpack(r, 1, r.n)
  end
end
function Mixin(obj, ...) for _, m in ipairs({ ... }) do for k, v in pairs(m) do obj[k] = v end end return obj end
function CreateFromMixins(...) return Mixin({}, ...) end

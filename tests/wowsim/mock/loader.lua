-- Add-on loader: reads the .toc, follows the XML <Script>/<Include> entries in order and runs every Lua
-- file with the client's varargs (addonName, sharedTable). Also SavedVariables (load and serialize)
-- and the login event sequence.
local Sim = Sim
local load = load -- WoW's 5.1 has no string `load`; the sim keeps its own reference (see PrepareClientEnv)

local function readfile(path)
  local s = __readfile(path)
  if not s then error("cannot read " .. path, 2) end
  return s
end

local function dirname(p) return (p:match("^(.*)/[^/]*$") or ".") end
local function norm(p) return (p:gsub("\\", "/")) end

Sim.loadedFiles = {}
Sim.afterFile = {} -- relpath -> function() (scenario hooks, e.g. capture registrations)

local function runLua(root, rel, addonName, ns)
  local src = readfile(root .. "/" .. rel)
  local chunk, err = load(src, "@" .. rel, "t")
  if not chunk then
    Sim.RecordError(err, "syntax " .. rel)
    return
  end
  Sim.SafeCall("loading " .. rel, chunk, addonName, ns)
  Sim.loadedFiles[#Sim.loadedFiles + 1] = rel
  local hook = Sim.afterFile[rel]
  if hook then hook() end
end

local function runXml(root, rel, addonName, ns)
  local src = readfile(root .. "/" .. rel)
  local base = dirname(rel)
  src = src:gsub("<!%-%-.-%-%->", "")
  for tag, file in src:gmatch("<(%a+)%s+file%s*=%s*\"([^\"]+)\"") do
    local child = base .. "/" .. norm(file)
    if tag == "Script" then
      runLua(root, child, addonName, ns)
    elseif tag == "Include" then
      runXml(root, child, addonName, ns)
    else
      Sim.Warn("XML tag <" .. tag .. "> ignored in " .. rel)
    end
  end
end

-- Loads <root>/<name>/<name>.toc. Returns the shared namespace table.
function Sim.LoadAddon(root, name)
  Sim.addonName = name
  local base = root .. "/" .. name
  local toc = readfile(base .. "/" .. name .. ".toc")
  Sim.tocMeta = {}
  local files = {}
  for line in (toc .. "\n"):gmatch("([^\r\n]*)\r?\n") do
    local k, v = line:match("^##%s*([^:]+):%s*(.-)%s*$")
    if k then
      Sim.tocMeta[k] = v
    elseif line:match("%S") and not line:match("^%s*#") then
      files[#files + 1] = norm(line:match("^%s*(.-)%s*$"))
    end
  end
  Sim.savedVariables = {}
  for _, key in ipairs({ "SavedVariables", "SavedVariablesPerCharacter" }) do
    for v in (Sim.tocMeta[key] or ""):gmatch("[%w_]+") do Sim.savedVariables[#Sim.savedVariables + 1] = v end
  end
  local ns = {}
  Sim.ns = ns
  for _, f in ipairs(files) do
    if f:match("%.xml$") then runXml(base, f, name, ns)
    elseif f:match("%.lua$") then runLua(base, f, name, ns)
    else Sim.Warn("TOC entry ignored: " .. f) end
  end
  return ns
end

------------------------------------------------------------------------------
-- SavedVariables
------------------------------------------------------------------------------

local function serialize(v, indent, seen)
  local t = type(v)
  if t == "string" then return string.format("%q", v) end
  if t == "number" then
    if v == math.floor(v) and math.abs(v) < 2 ^ 53 then return string.format("%d", v) end
    return string.format("%.17g", v)
  end
  if t == "boolean" then return tostring(v) end
  if t ~= "table" then return nil end -- functions, frames' userdata... are not saved by the client
  if Sim.IsWidget(v) then return nil end
  if seen[v] then error("SavedVariables: table referenced twice / cycle") end
  seen[v] = true
  local keys = {}
  for k in pairs(v) do
    if type(k) == "string" or type(k) == "number" then keys[#keys + 1] = k end
  end
  table.sort(keys, function(a, b)
    if type(a) == type(b) then return a < b end
    return type(a) == "number"
  end)
  local pad = string.rep("  ", indent + 1)
  local parts = {}
  for _, k in ipairs(keys) do
    local sv = serialize(v[k], indent + 1, seen)
    if sv then
      local sk = type(k) == "number" and ("[" .. serialize(k, 0, seen) .. "]") or ("[" .. string.format("%q", k) .. "]")
      parts[#parts + 1] = pad .. sk .. " = " .. sv .. ","
    end
  end
  seen[v] = nil
  if #parts == 0 then return "{}" end
  return "{\n" .. table.concat(parts, "\n") .. "\n" .. string.rep("  ", indent) .. "}"
end
Sim.Serialize = function(v) return serialize(v, 0, {}) end

function Sim.SaveVariables()
  local out = {}
  for _, name in ipairs(Sim.savedVariables or {}) do
    local v = rawget(_G, name)
    if v ~= nil then out[#out + 1] = name .. " = " .. (serialize(v, 0, {}) or "nil") end
  end
  return table.concat(out, "\n") .. "\n"
end

function Sim.RestoreVariables(src)
  if not src or src == "" then return end
  local chunk, err = load(src, "=SavedVariables", "t")
  if not chunk then error("bad SavedVariables: " .. tostring(err)) end
  chunk()
end

-- Server-side state that survives a relog (quests, level, position), for scenario chaining.
function Sim.ExportWorld()
  local p = Sim.player
  return "return " .. serialize({ level = p.level, map = p.map, x = p.x, y = p.y, completed = p.completed,
    quests = p.quests, questOrder = p.questOrder, spells = p.spells }, 0, {})
end
function Sim.ImportWorld(src)
  if not src or src == "" then return end
  local w = load(src, "=world", "t")()
  local p = Sim.player
  for k, v in pairs(w) do p[k] = v end
end

------------------------------------------------------------------------------
-- Login
------------------------------------------------------------------------------

-- The client runs the add-on files, then loads its SavedVariables, then fires ADDON_LOADED.
-- `beforeLoaded` runs between restoring SavedVariables and ADDON_LOADED (the sim turns debug on there).
function Sim.Login(root, savedVars, beforeLoaded)
  Sim.LoadAddon(root, "Senda")
  Sim.RestoreVariables(savedVars)
  if beforeLoaded then beforeLoaded() end
  Sim.Fire("ADDON_LOADED", "Senda", false)
  Sim.Fire("SPELLS_CHANGED")
  Sim.Fire("PLAYER_LOGIN")
  Sim.Fire("PLAYER_ENTERING_WORLD", true, false)
  Sim.Fire("QUEST_LOG_UPDATE")
  Sim.Fire("BAG_UPDATE_DELAYED")
  Sim.Advance(6)
end

-- Removes what the WoW client does not offer (no io/os/require/dofile, no string `load`, no utf8 library) and
-- records reads of undefined globals (APIs the add-on probes that the mock, or the client, lacks).
function Sim.PrepareClientEnv()
  for _, name in ipairs({ "io", "os", "require", "dofile", "loadfile", "package", "utf8", "load" }) do
    rawset(_G, name, nil)
  end
  Sim.TrackMissingGlobals()
end
function Sim.TrackMissingGlobals()
  setmetatable(_G, { __index = function(_, k)
    if type(k) == "string" and not k:match("^StaticPopup%d") then
      Sim.missingGlobals[k] = (Sim.missingGlobals[k] or 0) + 1
    end
    return nil
  end })
end

-- Comandos de chat: /senda [hud | hide | reset | guide <id> | way x y [texto] | map | debug | export | informe | help]
local _, Senda = ...
local L = Senda.L
local Util, Compat = Senda.Util, Senda.Compat

local resetPending = 0

local commands = {}
local extraHelp = {} -- { name, help } de subcomandos registrados por módulos

-- API para módulos: Senda.Slash:Register(name, fn, help). fn(rest, args) recibe el resto del texto
-- y la lista de argumentos (args[1] es el propio subcomando). No sustituye comandos del núcleo.
Senda.Slash = Senda.Slash or {}
function Senda.Slash:Register(name, fn, help)
  if type(name) ~= "string" or type(fn) ~= "function" then return false end
  name = name:lower()
  if commands[name] and not extraHelp[name] then return false end
  commands[name] = function(args, rest) return fn(rest, args) end
  if not extraHelp[name] then extraHelp[#extraHelp + 1] = name end
  extraHelp[name] = help or ""
  return true
end

commands[""] = function()
  if Senda.UI and Senda.UI.TogglePanel then Senda.UI:TogglePanel() end
end

commands.hud = function()
  if Senda.HUD and Senda.HUD.Toggle then Senda.HUD:Toggle() end
end

commands.hide = function()
  if Senda.Visibility then Senda.Visibility:Toggle() end
end

commands.reset = function()
  local now = GetTime and GetTime() or 0
  if now - resetPending > 10 then
    resetPending = now
    Senda:Print(L.SLASH_RESET_CONFIRM)
    return
  end
  resetPending = 0
  if Senda.Engine and Senda.Engine.Reset then Senda.Engine:Reset() end
  Senda:Print(L.SLASH_RESET_DONE)
end

commands.guide = function(args)
  local id = args[2]
  local Guides = Senda.Guides
  if not id then
    Senda:Print(L.SLASH_GUIDES_HEADER)
    local active = Senda.Engine and Senda.Engine:GuideId()
    for _, g in ipairs(Guides:List()) do
      local mark = (g.id == active) and " |cff4dd1a8<|r" or ""
      Senda:Print("  %s - %s%s", g.id, g.title or g.id, mark)
    end
    return
  end
  if not Guides:Get(id) then
    Senda:Print(L.SLASH_GUIDE_UNKNOWN, id)
    return
  end
  Senda.Engine:SetGuide(id)
end

commands.way = function(args)
  if not Senda.Arrow then return end
  if not args[2] or args[2] == "clear" or args[2] == "borrar" then
    Senda.Arrow:Clear("manual")
    Senda:Print(L.SLASH_WAY_CLEARED)
    return
  end
  -- Admite "/senda way 30.5 70.2 texto" y "/senda way 30.5,70.2 texto".
  local x, y, first = args[2], args[3], 4
  if x and x:find(",", 1, true) then
    x, y = x:match("^([%d%.]+),([%d%.]+)$")
    first = 3
  end
  x, y = tonumber(x), tonumber(y)
  local map = Compat.BestMap()
  if not x or not y or not map or x < 0 or x > 100 or y < 0 or y > 100 then
    Senda:Print(L.SLASH_WAY_USAGE)
    return
  end
  local label = table.concat(args, " ", first)
  if label == "" then label = string.format("%.1f, %.1f", x, y) end
  Senda.Arrow:SetTarget(map, x, y, label, "manual")
  Senda:Print(L.SLASH_WAY_SET, label, Compat.MapName(map) or map, x, y)
end

commands.map = function()
  local map, x, y = Compat.PlayerMapPos()
  local best = Compat.BestMap()
  if map then
    Senda:Print("uiMapID %d (%s)  %.2f, %.2f", map, Compat.MapName(map) or "?", x * 100, y * 100)
  else
    Senda:Print(L.SLASH_MAP_NOPOS, tostring(best))
  end
  local info = best and Compat.MapInfo(best)
  if info and info.parentMapID then
    Senda:Print("  parent: %s (%s)", tostring(info.parentMapID), Compat.MapName(info.parentMapID) or "?")
  end
  local facing = Compat.PlayerFacing()
  Senda:Print("  facing: %s  build: %s", facing and string.format("%.2f", facing) or "?", Compat.Build())
end

commands.debug = function()
  local v = not (Senda.db.opts.debug)
  if Senda.Options then Senda.Options:Set("debug", v) else Senda.db.opts.debug = v end
  Senda:Print(v and L.SLASH_DEBUG_ON or L.SLASH_DEBUG_OFF)
end

commands.export = function()
  if Senda.Recorder and Senda.Recorder.ShowExport then
    Senda.Recorder:ShowExport()
  end
end

commands.informe = function()
  if Senda.Report and Senda.Report.Open then Senda.Report:Open() end
end

commands.help = function()
  Senda:Print(L.SLASH_HELP_HEADER, Senda.VERSION)
  for _, line in ipairs(L.SLASH_HELP_LINES) do Senda:Print("  " .. line) end
  for _, name in ipairs(extraHelp) do
    local h = extraHelp[name]
    Senda:Print("  /senda %s%s", name, (h and h ~= "") and (" — " .. h) or "")
  end
end

-- Alias en español.
commands.ocultar = commands.hide
commands.guia = commands.guide
commands.ayuda = commands.help
commands.reiniciar = commands.reset
commands.exportar = commands.export
commands.report = commands.informe
commands.bug = commands.informe

SLASH_SENDA1 = "/senda"
SlashCmdList.SENDA = function(msg)
  if not Senda.ready then return end
  local args = Util.Args(msg or "")
  local cmd = (args[1] or ""):lower()
  local rest = (msg or ""):match("^%s*%S+%s*(.-)%s*$") or ""
  local fn = commands[cmd]
  if not fn then
    Senda:Print(L.SLASH_UNKNOWN, cmd)
    fn = commands.help
  end
  local ok, err = pcall(fn, args, rest)
  if not ok then
    Senda:Print("Error: %s", tostring(err))
  end
end

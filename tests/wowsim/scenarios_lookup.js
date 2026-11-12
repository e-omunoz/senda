'use strict';
// Scenarios of the item finder (addon/Senda/Modules/Lookup.lua, UI/LookupTab.lua, the item part of
// Core/NamesDump.lua) over the REAL generated add-on addon/Senda_Lookup (tools/build.py, data/lookup/):
// the tooltip line, /senda objeto, "Señalar" (nearest source), the search (frame-sliced, lazily indexed), the
// panel tab, the English client, and the dump / ingest round trip (the node side runs tools/import_names.py on
// what the sim saved). Loaded by run.js.

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const L_ = String.raw;
const ROOT = path.resolve(__dirname, '..', '..');

// Shared helpers, injected at the top of every scenario body.
const HELPERS = L_`
  local function Tip(id, tt)
    tt = tt or GameTooltip
    tt:SetOwner(UIParent, "ANCHOR_NONE")
    tt:SetHyperlink(Sim.ItemLink(id))
    tt:Show()
    local found = {}
    for _, l in ipairs(tt:Lines()) do if l:find("^Senda:") then found[#found + 1] = Plain(l) end end
    return found
  end
  local function Loads()
    local n = 0
    for _, a in ipairs(Sim.addonLoads) do if a.name == "Senda_Lookup" then n = n + 1 end end
    return n
  end
  local function All(lines) return Plain(table.concat(lines, "\n")) end
  -- Slash(), but waits for the (frame-sliced) search to finish before collecting the chat lines.
  local function Cmd(msg)
    Sim.Out("  /senda " .. msg)
    local before = #Sim.chat
    Sim.SafeCall("SlashCmdList.SENDA('" .. msg .. "')", SlashCmdList.SENDA, msg)
    for _ = 1, 600 do
      if not Sim.ns.Lookup.Searching() then break end
      Sim.Advance(0.05)
    end
    Sim.Advance(0.3)
    local lines = {}
    for i = before + 1, #Sim.chat do lines[#lines + 1] = Sim.chat[i] end
    return lines
  end
`;

const scenarios = [
  {
    id: 'lookup-tip',
    title: 'Item finder: one tooltip line (drop, object, vendor, reward, objective, route), lazy load out of combat, option, zone first',
    char: 'gnome-warlock',
    lua: HELPERS + L_`
      Login()
      local LK = S().Lookup
      Check(LK ~= nil and LK.TipText ~= nil, "Senda.Lookup exists")
      Check(rawget(_G, "Senda_Lookup") == nil and Loads() == 0, "the data add-on is not loaded at login")
      Check(Sim.tocMeta ~= nil, "main toc read")

      Section("combat: nothing loads, no line")
      Sim.player.combat = true
      local t = Tip(3083)
      Check(#t == 0 and Loads() == 0, "no line and no load while in combat", #t .. " / " .. Loads())
      Sim.player.combat = false

      Section("first look out of combat: loads once, one line")
      t = Tip(3083)
      Check(Loads() == 1 and LK.IsLoaded(), "Senda_Lookup loaded on the first item look", Loads())
      Check(#t == 1, "exactly one Senda line", #t)
      Check(t[1]:find("^Senda: lo sueltan ") ~= nil, "two droppers on the same map: «lo sueltan»", t[1])
      Check(t[1]:find("(80%)", 1, true) ~= nil and t[1]:find(" y ", 1, true) ~= nil, "chance of each and «y»", t[1])
      Check(t[1]:find("en Dun Morogh", 1, true) ~= nil, "zone name from the client", t[1])
      Check(t[1]:find("PNJ #1211", 1, true) ~= nil, "uncached creature: placeholder at first", t[1])
      Sim.Advance(2)
      local lines = {}
      for _, l in ipairs(GameTooltip:Lines()) do if l:find("^Senda:") then lines[#lines + 1] = Plain(l) end end
      Check(#lines == 1 and lines[1]:find("Criatura 1211 (80%) y Criatura 8503 (80%) en Dun Morogh", 1, true) ~= nil,
        "the tooltip you are looking at is rebuilt once the names arrive", All(lines))
      GameTooltip:Hide()
      Check(Loads() == 1, "still one load")

      Section("one dropper + more sources, an object, a vendor")
      t = Tip(2676)
      Check(#t == 1 and t[1]:find("^Senda: lo suelta ") ~= nil and t[1]:find("(75%)", 1, true) ~= nil
        and t[1]:find("(+1 más)", 1, true) ~= nil, "one NPC with the rest counted", t[1])
      t = Tip(10438)
      Check(#t == 1 and t[1]:find("^Senda: se saca de un objeto del mundo en Dun Morogh") ~= nil, "world object only", All(t))
      t = Tip(2894)
      Check(#t == 1 and t[1]:find("^Senda: lo vende ") ~= nil and t[1]:find("en Dun Morogh", 1, true) ~= nil, "vendor", All(t))

      Section("quest items")
      t = Tip(1008)
      Check(#t == 1 and t[1]:find("^Senda: recompensa de ") ~= nil, "quest reward", All(t))
      t = Tip(10005)
      Check(#t == 1 and t[1]:find("^Senda: para ") ~= nil, "objective only", All(t))
      t = Tip(11243)
      Check(#t == 1 and t[1]:find("^Senda: recógelo en ") ~= nil, "route place beats a reward", All(t))
      Sim.Advance(1.5)

      Section("unknown items and synthetic entries")
      Check(#Tip(6948) == 0, "an item that is not in the data gets no line")
      local D = rawget(_G, "Senda_Lookup")
      D.items[999001] = "s=i159"
      t = Tip(999001)
      Check(#t == 1 and t[1]:find("^Senda: sale de ") ~= nil, "container item", All(t))
      D.places.o[999276] = "0,-120.5,88,36,1"
      D.items[999002] = "s=o999276:100"
      t = Tip(999002)
      Check(#t == 1 and t[1]:find("en una mazmorra", 1, true) ~= nil, "a world object in a dungeon", All(t))
      D.items[999003] = "s=n1:100"
      t = Tip(999003)
      Check(#t == 1 and t[1]:find("^Senda: lo suelta ") ~= nil and not t[1]:find(" en ", 1, true), "a source without a place: no «en»", All(t))

      Section("sources of the player's zone first")
      D.items[999004] = "s=n3577:90,n1397:40"
      t = Tip(999004)
      Check(t[1]:find("en Dun Morogh", 1, true) ~= nil and not t[1]:find("#1421", 1, true), "in Dun Morogh: the Dun Morogh dropper", All(t))
      Sim.player.map = 1421
      t = Tip(999004)
      Check(t[1]:find("(90%)", 1, true) ~= nil, "elsewhere: the best chance", All(t))
      Sim.player.map = 1426

      Section("ItemRefTooltip, the option, secret ids")
      ItemRefTooltip:SetOwner(UIParent, "ANCHOR_NONE")
      ItemRefTooltip:SetHyperlink(Sim.ItemLink(1008))
      local ref = false
      for _, l in ipairs(ItemRefTooltip:Lines()) do if l:find("^Senda: recompensa") then ref = true end end
      Check(ref, "the chat-link tooltip gets the line too")
      S().Options:Set("lookupTip", false)
      Check(#Tip(1008) == 0, "option off: no line")
      S().Options:Set("lookupTip", true)
      Check(#Tip(1008) == 1, "option on again: the line is back")
      local real = issecretvalue
      issecretvalue = function(v) return type(v) == "table" end
      GameTooltip:SetOwner(UIParent, "ANCHOR_NONE")
      Sim.SafeCall("secret tooltip data", LK.OnTooltipItem, GameTooltip, { id = 1008 })
      issecretvalue = real
      Check(true, "secret tooltip data is skipped without errors")
      Check(Loads() == 1, "the data add-on was loaded exactly once in the whole scenario", Loads())
    `,
  },
  {
    id: 'lookup-slash',
    title: 'Item finder: /senda objeto by id, name, accents, ambiguous, none, link, combat, not-in-data',
    char: 'human-mage',
    lua: HELPERS + L_`
      Login()
      local LK = S().Lookup

      Section("in combat nothing loads")
      Sim.player.combat = true
      local lines = Cmd("objeto 182")
      Check(Plain(table.concat(lines, " ")):find("En combate no se carga el buscador", 1, true) ~= nil, "says so", All(lines))
      Check(Loads() == 0 and not LK.IsLoaded(), "and loads nothing")
      Sim.player.combat = false

      Section("by number")
      lines = Cmd("objeto 182")
      local text = All(lines)
      Check(text:find("(objeto 182)", 1, true) ~= nil, "header with the id", text)
      Check(text:find("Lo sueltan: ", 1, true) ~= nil and text:find("Bosque de Elwynn", 1, true) ~= nil and text:find("100%", 1, true) ~= nil,
        "drops with zone and chance", text)
      Check(text:find("/senda objeto señalar 182", 1, true) ~= nil, "offers the arrow", text)
      Check(Loads() == 1, "loaded on the first use")
      lines = Cmd("objeto 159")
      text = All(lines)
      Check(text:find("Lo venden: ", 1, true) ~= nil and text:find("Recompensa de: ", 1, true) ~= nil
        and text:find("(a elegir)", 1, true) ~= nil and text:find("(+", 1, true) ~= nil, "vendors, rewards (choice) and the truncated total", text)
      lines = Cmd("objeto 10005")
      text = All(lines)
      Check(text:find("Lo piden: ", 1, true) ~= nil and text:find("señalar", 1, true) == nil, "objective-only: no arrow offered", text)

      Section("by name: English from forever-db, Spanish from the guides, accents ignored")
      lines = Cmd("objeto Garrick's Head")
      Check(All(lines):find("(objeto 182)", 1, true) ~= nil, "exact English name", All(lines))
      lines = Cmd("objeto MUSGOVIL")
      Check(All(lines):find("(objeto 3297)", 1, true) ~= nil, "exact Spanish name, any case", All(lines))
      lines = Cmd("objeto canon de pluma")
      Check(All(lines):find("(objeto 3406)", 1, true) ~= nil, "«canon» finds «Cañón»", All(lines))
      lines = Cmd("objeto CAÑÓN PLUMA")
      Check(All(lines):find("(objeto 3406)", 1, true) ~= nil, "accents and capitals in the query, words in any place", All(lines))
      lines = Cmd("objeto item:182")
      Check(All(lines):find("(objeto 182)", 1, true) ~= nil, "an item link / item:N")
      lines = Cmd("objeto #182")
      Check(All(lines):find("(objeto 182)", 1, true) ~= nil, "#N")

      Section("ambiguous, none, short, not in the data")
      lines = Cmd("objeto talisman")
      text = All(lines)
      Check(text:find("objetos coinciden con «talisman»", 1, true) ~= nil and text:find("Elige uno", 1, true) ~= nil, "a list with a hint", text)
      local listed = 0
      for _, l in ipairs(lines) do if Plain(l):find("^Senda:   %d+%. ") then listed = listed + 1 end end
      Check(listed >= 2 and listed <= 8, "at most 8 listed", listed)
      lines = Cmd("objeto xyzzyplugh")
      Check(All(lines):find("No encuentro ningún objeto que se llame «xyzzyplugh»", 1, true) ~= nil, "none", All(lines))
      lines = Cmd("objeto a")
      Check(All(lines):find("al menos 2 letras", 1, true) ~= nil, "too short", All(lines))
      lines = Cmd("objeto 6948")
      Check(All(lines):find("no está en los datos de Senda", 1, true) ~= nil, "an item the data does not know", All(lines))
      lines = Cmd("objeto")
      Check(All(lines):find("Uso: /senda objeto", 1, true) ~= nil, "usage", All(lines))
      Check(All(Slash("ayuda")):find("/senda objeto", 1, true) ~= nil, "listed in /senda ayuda")
      Check(Loads() == 1, "one load for all of it", Loads())
    `,
  },
  {
    id: 'lookup-point',
    title: 'Item finder: Señalar points the arrow at the nearest known source (zone, vendor, other continent, dungeon, none)',
    char: 'gnome-warlock',
    lua: HELPERS + L_`
      Login()
      local LK = S().Lookup
      Check(LK.Load(), "load the data")
      local function Dest()
        local t, src = S().Arrow:Destination()
        return t, src
      end
      Section("nearest of two droppers, by distance from the player")
      Sim.player.map, Sim.player.x, Sim.player.y = 1426, 0.5, 0.5
      local ok, src, meters = LK.Point(3083)
      Check(ok and src.npc == 1211 and meters and meters > 1000 and meters < 1300, "from the middle of the zone: npc 1211", tostring(src and src.npc) .. " " .. tostring(meters))
      local t, source = Dest()
      Check(source == "lookup" and t.map == 1426 and math.abs(t.x - 0.26) < 1e-6 and math.abs(t.y - 0.408) < 1e-6, "the arrow is at the dropper", tostring(source))
      Check(t.label:find("Brazales") == nil and t.label:find(":", 1, true) ~= nil, "label names item and source", t.label)
      Sim.player.x, Sim.player.y = 0.25, 0.43
      ok, src = LK.Point(3083)
      Check(ok and src.npc == 8503, "next to the other one: npc 8503", tostring(src and src.npc))

      Section("a vendor beats a dropper that is far")
      local D = rawget(_G, "Senda_Lookup")
      D.items[999010] = "s=n3577:100;v=1247"
      Sim.player.x, Sim.player.y = 0.47, 0.52
      ok, src = LK.Point(999010)
      Check(ok and src.kind == "vendor" and src.npc == 1247, "the vendor of the zone", tostring(src and src.kind))

      Section("another continent: still points (the travel planner takes over)")
      ok, src = LK.Point(10639)
      Check(ok and src.place.map == 1438, "a source on Teldrassil", tostring(src and src.place and src.place.map))
      t, source = Dest()
      Check(source == "lookup" and t.map == 1438, "destination on Kalimdor")

      Section("clear, last item, /senda objeto señalar")
      LK.ClearPoint()
      Check(not S().Arrow:Has("lookup"), "cleared")
      local lines = Cmd("objeto señalar 3083")
      Check(All(lines):find("Flecha puesta para", 1, true) ~= nil and select(2, Dest()) == "lookup", "/senda objeto señalar <id>", All(lines))
      Check(All(lines):find(" m.", 1, true) ~= nil or All(lines):find(" km.", 1, true) ~= nil, "says how far", All(lines))
      lines = Cmd("objeto borrar")
      Check(not S().Arrow:Has("lookup") and All(lines):find("quitada", 1, true) ~= nil, "/senda objeto borrar")
      Cmd("objeto 3083")
      Cmd("objeto señalar")
      Check(S().Arrow:Has("lookup"), "señalar alone uses the last item")
      lines = Cmd("objeto way 2676")
      Check(S().Arrow:Has("lookup"), "English alias: way")
      LK.ClearPoint()

      Section("nothing to aim at")
      D.items[999011] = "s=o999277:100"
      D.places.o[999277] = "0,-120.5,88,36,1"
      ok, src = LK.Point(999011)
      Check(not ok and src == "dungeon", "dungeon only", tostring(src))
      lines = Cmd("objeto señalar 999011")
      Check(All(lines):find("solo sale en una mazmorra", 1, true) ~= nil, "says so", All(lines))
      ok, src = LK.Point(1008)
      Check(not ok and src == "none", "quest reward only: no place", tostring(src))
      lines = Cmd("objeto señalar 1008")
      Check(All(lines):find("solo se sabe la misión", 1, true) ~= nil, "says so", All(lines))
      D.items[999012] = "s=n1:100"
      ok, src = LK.Point(999012)
      Check(not ok and src == "none", "a source with no known place", tostring(src))
      Check(not S().Arrow:Has("lookup"), "no arrow was set by the failures")

      Section("the guide arrow is replaced and comes back")
      local before = S().Arrow:Destination()
      LK.Point(3083)
      Check(select(2, Dest()) == "lookup", "the item wins over the guide while pointed")
      LK.ClearPoint()
      Check(select(2, Dest()) ~= "lookup", "the guide arrow is back")
    `,
  },
  {
    id: 'lookup-search',
    title: 'Item finder: search is sliced across frames, lazily indexed, released when idle, paused in combat, newest wins',
    char: 'human-mage',
    lua: HELPERS + L_`
      Login()
      local LK = S().Lookup
      Check(LK.Load(), "load the data")
      Check(not LK.IndexLoaded(), "no index yet: nothing is built until someone searches")
      local function Run(q, maxFrames)
        local got, info
        local started = LK.Search(q, function(r, i) got, info = r, i end)
        local frames = 0
        while got == nil and frames < (maxFrames or 600) do Sim.Advance(0.05); frames = frames + 1 end
        return got, info, frames, started
      end

      Section("the first search builds the index over several frames")
      local res, info, frames = Run("musgovil")
      Check(res and res[1] and res[1][1] == 3297 and res[1][2] == 0, "exact name first", res and res[1] and res[1][1])
      Check(frames > 2, "spread over several frames, not one", frames)
      Check(LK.stats.maxSliceOps <= 520, "no frame did more than ~500 operations", LK.stats.maxSliceOps)
      Check(info.items > 5000 and info.named > 5000, "the whole data is indexed with names", info.items .. " / " .. info.named)
      Check(LK.IndexLoaded() and LK.stats.indexBuilds == 1, "index kept for the next search")

      Section("later searches reuse it, ordering and filters")
      res, info, frames = Run("of the")
      Check(info.total > 20 and #res == 20, "capped at 20 results", info.total .. " / " .. #res)
      local ordered = true
      for i = 2, #res do
        if res[i][2] < res[i - 1][2] or (res[i][2] == res[i - 1][2] and res[i][1] < res[i - 1][1]) then ordered = false end
      end
      Check(ordered, "sorted by match quality, then id")
      Check(LK.stats.indexBuilds == 1, "index not rebuilt")
      res = Run("pluma negra")
      local has3406 = false
      for _, r in ipairs(res) do if r[1] == 3406 then has3406 = true end end
      Check(has3406, "every word has to match, in any order", #res)
      res, info = Run("ñ")
      Check(#res == 0 and info.reason == "short", "one letter is too short")
      res = Run("159")
      Check(res[1][1] == 159, "a number is an id")
      res = Run("item:2676|h[x]")
      Check(res[1][1] == 2676, "an item link")

      Section("names the client or the dump know are searchable too (after the index is rebuilt)")
      Sim.Advance(100)
      Check(not LK.IndexLoaded(), "the index is released after 90 s idle")
      Sim.ITEMS[2676] = { name = "Brillaverde", quality = 1, class = 7, sub = 0, loc = "", price = 1, stack = 20 }
      Sim.itemCache[2676] = true
      SendaNamesDB = { version = 1, locales = { esES = { build = "1.60.1.70291", litem = { [10005] = "Cuerno de Margol" } } } }
      res = Run("brillaverde")
      Check(res[1] and res[1][1] == 2676, "a name the client already has", res[1] and res[1][1])
      res = Run("cuerno de margol")
      Check(res[1] and res[1][1] == 10005, "a name from /senda volcar (litem)", res[1] and res[1][1])
      Check(LK.stats.indexBuilds == 2, "rebuilt once", LK.stats.indexBuilds)
      res = Run("Margol's Gigantic Horn")
      Check(res[1] and res[1][1] == 10005, "and the English name still matches")

      Section("combat pauses the work, the newest search wins")
      local got1, got2
      LK.Search("talisman", function(r) got1 = r end)
      LK.Search("musgovil", function(r) got2 = r end)
      for _ = 1, 60 do Sim.Advance(0.05) end
      Check(got1 == nil and got2 and got2[1][1] == 3297, "the older search never answers", tostring(got1))
      Sim.Advance(100)
      Check(not LK.IndexLoaded(), "released again")
      local got3
      Sim.player.combat = true
      LK.Search("musgovil", function(r) got3 = r end)
      for _ = 1, 40 do Sim.Advance(0.05) end
      Check(got3 == nil and not LK.IndexLoaded(), "no work in combat")
      Sim.player.combat = false
      for _ = 1, 400 do if got3 then break end Sim.Advance(0.05) end
      Check(got3 and got3[1][1] == 3297, "it finishes after combat")
      Check(LK.stats.maxSliceOps <= 520, "still no heavy frame", LK.stats.maxSliceOps)
    `,
  },
  {
    id: 'lookup-tab',
    title: 'Item finder: panel tab (search box, results, Señalar, detail, clear arrow, empty and no-result states)',
    char: 'nightelf-druid',
    lua: HELPERS + L_`
      Sim.ITEMS[3297] = { name = "Musgovil", quality = 1, class = 7, sub = 0, loc = "", price = 1, stack = 20 }
      Sim.ITEMS[3406] = { name = "Cañón de pluma negra", quality = 1, class = 7, sub = 0, loc = "", price = 1, stack = 20 }
      Login()
      local LK = S().Lookup
      RunAllTabs()
      local UI = S().UI
      local function Texts()
        local texts = {}
        for _, f in ipairs(Sim.AllWidgets()) do
          if f.__type == "FontString" and f:IsVisible() then texts[#texts + 1] = Plain(f:GetText() or "") end
        end
        return table.concat(texts, " | ")
      end
      local function Box()
        for _, f in ipairs(Sim.AllWidgets()) do
          if f.__type == "EditBox" and f.hint and f:IsVisible() then return f end
        end
      end
      UI:ShowTab("lookup"); Sim.Advance(0.3)
      local box = Box()
      Check(box ~= nil, "the search box exists")
      Check(Texts():find("Escribe un nombre arriba", 1, true) ~= nil, "empty state", Texts():sub(1, 200))

      Section("type, Enter: results")
      box:SetText("musgovil")
      Sim.RunScript(box, "OnEnterPressed")
      for _ = 1, 400 do Sim.Advance(0.05) if not LK.Searching() then break end end
      Sim.Advance(0.3)
      local all = Texts()
      Check(all:find("Musgovil", 1, true) ~= nil, "the result row shows the name", all:sub(1, 300))
      Check(all:find("Lo sueltan", 1, true) ~= nil, "the first result is selected: its detail is shown", all:sub(1, 400))
      Check(all:find("objetos tienen nombre", 1, true) ~= nil, "status line counts named items", all:sub(1, 300))

      Section("Señalar on the row, Quitar flecha")
      local point
      for _, f in ipairs(Sim.AllWidgets()) do
        if f.__type == "Button" and f:IsVisible() and f:GetText() == "Señalar" then point = f break end
      end
      Check(point ~= nil and point:IsEnabled(), "an enabled Señalar button on a pointable result")
      Sim.RunScript(point, "OnClick")
      Check(select(2, S().Arrow:GetTarget()) == "lookup" or S().Arrow:Has("lookup"), "the arrow points at the source")
      local clear
      for _, f in ipairs(Sim.AllWidgets()) do
        if f.__type == "Button" and f:IsVisible() and f:GetText() == "Quitar flecha" then clear = f break end
      end
      Check(clear ~= nil and clear:IsEnabled(), "Quitar flecha is enabled while an item arrow exists")
      Sim.RunScript(clear, "OnClick")
      Check(not S().Arrow:Has("lookup") and not clear:IsEnabled(), "cleared and disabled again")

      Section("typing searches by itself after a pause, other states")
      box:SetText("pluma negra")
      Sim.RunScript(box, "OnTextChanged", true)
      Sim.Advance(0.1)
      Check(not LK.Searching(), "not yet: it waits for you to stop typing")
      for _ = 1, 400 do Sim.Advance(0.05) end
      Check(Texts():find("Cañón de pluma negra", 1, true) ~= nil and Texts():find("resultados", 1, true) ~= nil, "results appeared", Texts():sub(1, 300))
      box:SetText("xyzzyplugh")
      Sim.RunScript(box, "OnEnterPressed")
      for _ = 1, 400 do Sim.Advance(0.05) if not LK.Searching() then break end end
      Sim.Advance(0.3)
      Check(Texts():find("Ningún objeto coincide con «xyzzyplugh»", 1, true) ~= nil, "no results message", Texts():sub(1, 300))
      box:SetText("")
      Sim.RunScript(box, "OnEnterPressed")
      Sim.Advance(0.3)
      Check(Texts():find("Escribe un nombre arriba", 1, true) ~= nil, "empty again")
      S().LookupTab:Search("garrick")
      for _ = 1, 400 do Sim.Advance(0.05) if not LK.Searching() then break end end
      Sim.Advance(0.3)
      Check(Texts():find("Garrick", 1, true) ~= nil, "LookupTab:Search opens the tab with a search", Texts():sub(1, 300))
      Check(HoverAll() > 0, "tooltips of the tab run")
    `,
  },
  {
    id: 'lookup-en',
    title: 'Item finder on an English client: tooltip, slash, tab and options in English',
    char: 'gnome-warlock',
    locale: 'enUS',
    lua: HELPERS + L_`
      Login()
      local LK = S().Lookup
      local function EnTip(id)
        GameTooltip:SetOwner(UIParent, "ANCHOR_NONE")
        GameTooltip:SetHyperlink(Sim.ItemLink(id))
        local out = {}
        for _, l in ipairs(GameTooltip:Lines()) do if l:find("^Senda:") then out[#out + 1] = Plain(l) end end
        return out
      end
      local t = EnTip(3083)
      Check(#t == 1 and t[1]:find("^Senda: dropped by ") ~= nil and t[1]:find(" and ", 1, true) ~= nil and t[1]:find(" in Dun Morogh", 1, true) ~= nil, "drop line", t[1])
      t = EnTip(10438); Check(t[1] and t[1]:find("comes from a world object in Dun Morogh", 1, true) ~= nil, "object line", tostring(t[1]))
      t = EnTip(2894); Check(t[1] and t[1]:find("^Senda: sold by ") ~= nil, "vendor line", tostring(t[1]))
      t = EnTip(1008); Check(t[1] and t[1]:find("^Senda: reward from ") ~= nil, "reward line", tostring(t[1]))
      t = EnTip(10005); Check(t[1] and t[1]:find("^Senda: for ") ~= nil, "objective line", tostring(t[1]))
      t = EnTip(11243); Check(t[1] and t[1]:find("^Senda: pick it up in ") ~= nil, "route line", tostring(t[1]))
      local lines = Cmd("objeto 159")
      local text = Plain(table.concat(lines, "\n"))
      Check(text:find("(item 159)", 1, true) ~= nil and text:find("Dropped by: ", 1, true) ~= nil and text:find("Sold by: ", 1, true) ~= nil
        and text:find("Reward from: ", 1, true) ~= nil, "slash detail in English", text)
      lines = Cmd("objeto refreshing spring water")
      Check(Plain(table.concat(lines, " ")):find("(item 159)", 1, true) ~= nil, "English name search")
      lines = Cmd("objeto xyzzyplugh")
      Check(Plain(table.concat(lines, " ")):find("No item matches", 1, true) ~= nil, "none message in English")
      lines = Cmd("objeto señalar 3083")
      Check(Plain(table.concat(lines, " ")):find("Arrow set for", 1, true) ~= nil, "point message in English", Plain(table.concat(lines, " ")))
      Check(S().L.OPT_LOOKUP_TIP == "Say in item tooltips where they come from", "option label in English")
      RunAllTabs()
      S().UI:ShowTab("lookup"); Sim.Advance(0.3)
      local found = false
      for _, f in ipairs(Sim.AllWidgets()) do
        if f.__type == "FontString" and f:IsVisible() and (f:GetText() or ""):find("Type a name above", 1, true) then found = true end
      end
      Check(found, "tab empty state in English")
      local lines2 = Slash("volcar ayuda")
      Check(Plain(table.concat(lines2, " ")):find("item finder", 1, true) ~= nil, "dump help mentions the item finder in English")
    `,
  },
  {
    id: 'lookup-dump',
    title: 'Item finder names: /senda volcar saves the cached ones into litem (no requests), "volcar objetos" asks for the rest, throttled and paused in combat; the ingest round trip',
    char: 'gnome-warlock',
    lua: HELPERS + L_`
      Sim.ITEMS[2676] = { name = "Brillaverde", quality = 1, class = 7, sub = 0, loc = "", price = 1, stack = 20 }
      Sim.ITEMS[10005] = { name = "Cuerno gigantesco de Margol", quality = 1, class = 15, sub = 0, loc = "", price = 1, stack = 1 }
      Login()
      local D = S().Names.Dump
      local LK = S().Lookup
      Sim.itemCache[2676] = true
      Sim.itemCache[10005] = true

      Section("plain /senda volcar: only what the client already has, nothing is requested")
      Slash("volcar")
      for _ = 1, 400 do
        if not D:Running() then break end
        Sim.Advance(0.5)
      end
      Check(not D:Running(), "the dump finished")
      local d = SendaNamesDB.locales.esES
      Check(type(d.litem) == "table", "litem table exists")
      Check(d.litem[2676] == "Brillaverde" and d.litem[10005] == "Cuerno gigantesco de Margol", "cached names saved", tostring(d.litem[2676]))
      Check(d.litem[11243] == nil and d.litem[3297] == nil, "uncached lookup items are not asked for")
      Check(Sim.itemCache[11243] == nil and not (Sim.itemPending and Sim.itemPending[11243]), "the server was not asked for them", tostring(Sim.itemPending and Sim.itemPending[11243]))
      local said = false
      for _, l in ipairs(Sim.chat) do if l:find("Objetos del buscador: 2 nombres nuevos", 1, true) then said = true end end
      Check(said, "chat says how many were new", Sim.chat[#Sim.chat])
      Check(Loads() == 1, "the lookup data was loaded (out of combat) by the dump", Loads())

      Section("/senda volcar objetos: asks for the rest, throttled")
      local before = #Sim.chat
      Slash("volcar objetos")
      Check(D:Running(), "started")
      local maxStep, maxWait, last = 0, 0, D:Started()
      local frames = 0
      while select(2, D:Progress()) == 0 and frames < 2000 do Sim.Advance(0.05); frames = frames + 1 end
      for _ = 1, 4000 do
        Sim.Advance(0.05)
        local now = D:Started()
        maxStep = math.max(maxStep, now - last)
        maxWait = math.max(maxWait, D:InFlight())
        last = now
        if now > 600 then break end
      end
      Check(maxStep > 0 and maxStep <= 20, "at most 20 requests per frame", maxStep)
      Check(maxWait <= 40, "at most 40 waiting", maxWait)
      local asked = false
      for i = before + 1, #Sim.chat do if Sim.chat[i]:find("Pidiendo al juego", 1, true) then asked = true end end
      Check(asked, "chat says it is asking for item names")

      Section("paused in combat")
      Sim.player.combat = true
      Sim.Advance(0.2)
      local p1 = D:Started()
      Sim.Advance(2)
      Check(D:Started() == p1, "no new requests during combat", p1 .. " -> " .. D:Started())
      Sim.player.combat = false

      Section("finishes")
      for _ = 1, 700 do
        Sim.Advance(1)
        if not D:Running() then break end
      end
      Check(not D:Running(), "dump finished")
      local n = 0
      for _ in pairs(d.litem) do n = n + 1 end
      Check(n > 5400, "nearly every lookup item has a name now", n)
      Check(d.litem[10438] ~= nil and d.litem[11243] ~= nil, "formerly uncached items answered", tostring(d.litem[11243]))
      local miss = 0
      for _ in pairs(d.missing.litem) do miss = miss + 1 end
      Check(miss == 0, "no item without an answer", miss)
      Check(d.item[159] == nil or d.litem[159] == nil, "an item is saved once: guide items in item, the rest in litem")
      local fin = false
      for _, l in ipairs(Sim.chat) do if l:find("Volcado terminado", 1, true) then fin = true end end
      Check(fin, "chat says it finished")
      Section("second run has nothing left to ask")
      local mark = #Sim.chat
      Slash("volcar objetos")
      for _ = 1, 400 do if not D:Running() then break end Sim.Advance(0.05) end
      local again = false
      for i = mark + 1, #Sim.chat do if Sim.chat[i]:find("Objetos del buscador: 0 nombres nuevos", 1, true) then again = true end end
      Check(again and not D:Running(), "nothing new, nothing asked", Sim.chat[#Sim.chat])
      Section("the dump is a fallback for {item:N}")
      Check(S().Names:Dumped("item", 11243) == d.litem[11243] and d.litem[11243] ~= nil, "Names:Dumped reads litem")
      __report("saved", Sim.SaveVariables())
      Check(Sim.SaveVariables():find('["litem"]', 1, true) ~= nil, "litem reaches the SavedVariables file")
    `,
    post(report, carry, ctx) {
      // The real ingest tool on what the sim saved: SendaNamesDB.litem -> data/lookup/locale/esES/items.json.
      const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'senda-lookup-'));
      try {
        const sv = path.join(tmp, 'Senda.lua');
        fs.writeFileSync(sv, report.saved || '');
        const r = spawnSync('python', ['-I', path.join(ROOT, 'tools', 'import_names.py'), sv, '--root', tmp],
          { encoding: 'utf8' });
        ctx.check(r.status === 0, 'tools/import_names.py ingests the saved variables', (r.stderr || '').slice(0, 300));
        const f = path.join(tmp, 'data', 'lookup', 'locale', 'esES', 'items.json');
        ctx.check(fs.existsSync(f), 'the names land in data/lookup/locale/esES/items.json');
        if (fs.existsSync(f)) {
          const names = JSON.parse(fs.readFileSync(f, 'utf8')).names;
          ctx.check(names['2676'] && names['2676'].name === 'Brillaverde' && /^ingame:/.test(names['2676'].source),
            'a name the client had is ingested with an ingame source', JSON.stringify(names['2676']));
          ctx.check(Object.keys(names).length > 5400, 'the whole dump is ingested (' + Object.keys(names).length + ')');
        }
        const guide = path.join(tmp, 'data', 'locale', 'esES', 'items.json');
        ctx.check(fs.existsSync(guide) && !('11243' in JSON.parse(fs.readFileSync(guide, 'utf8')).names),
          'items of the guides go to data/locale, the lookup-only ones do not');
        ctx.check(/Objetos del buscador: nuevos \d+/.test(r.stdout || ''), 'the report counts the lookup names', (r.stdout || '').slice(0, 200));
      } finally {
        fs.rmSync(tmp, { recursive: true, force: true });
      }
      return {};
    },
  },
];

module.exports = { scenarios };

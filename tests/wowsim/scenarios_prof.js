'use strict';
// Scenarios of the professions tab (addon/Senda/Modules/Professions.lua + Trainer.lua) over the generated routes
// (data/knowledge/general/professions-<prof>.toml, tools/gen_professions.py): the tab follows the professions the
// character really has, Spanish names from the client tables, next rank and trainer of the faction, the rank-cap
// warning, the class recommendation with its "por qué", and the trainer highlight. Loaded by run.js.

const L_ = String.raw;

// Text of every visible FontString (the tab's document), plain.
const TAB_TEXT = L_`
  local function TabText()
    local out = {}
    for _, f in ipairs(Sim.AllWidgets()) do
      if f.__type == "FontString" and f:IsVisible() then
        local t = f:GetText()
        if t and t ~= "" then out[#out + 1] = Plain(t) end
      end
    end
    return table.concat(out, " | ")
  end
  local function Keys(P)
    local keys = {}
    for _, k in ipairs(P.Routes().order) do keys[#keys + 1] = k end
    return table.concat(keys, ",")
  end
`;

const scenarios = [
  {
    id: 'prof-warlock',
    title: 'Professions: warlock with Tailoring 1 and Enchanting 1 learned sees both routes, Spanish names, next rank in Ironforge',
    char: 'gnome-warlock',
    lua: TAB_TEXT + L_`
      local cfg = Sim.CHARS["gnome-warlock"]
      cfg.level = 12
      cfg.profs = { { name = "Sastrería", skillLine = 197, rank = 1, max = 75 }, { name = "Encantamiento", skillLine = 333, rank = 1, max = 75 } }
      Login()
      Sim.Advance(2)
      -- The esES client names the recipe spells (the mock only knows the ones it is told).
      Sim.SPELL_NAMES[2387] = "Capa de lino"
      local P = S().Modules.Professions
      Check(Keys(P) == "tailoring,enchanting", "routes = the two learned professions", Keys(P))
      local t = P.State("tailoring")
      Check(t.learned and t.rank == 1 and t.max == 75, "tailoring read from the client (1/75)", tostring(t.rank) .. "/" .. tostring(t.max))
      Check(t.seg ~= nil and t.seg.name == "Capa de lino", "tailoring 1: Capa de lino (esES from the client tables)", t.seg and t.seg.name)
      Check(t.seg and t.seg.colors and t.seg.colors[2] == 35 and t.seg.colors[4] == 60, "Linen Cloak colours from the client (yellow 35, grey 60)",
        t.seg and table.concat(t.seg.colors or {}, ","))
      Check((t.left or 0) > 0 and (t.leftTotal or 0) > 250, "expected crafts: this bracket and the whole route", tostring(t.left) .. " / " .. tostring(t.leftTotal))
      local linen
      for _, m in ipairs(t.mats or {}) do if m.id == 2589 then linen = m end end
      Check(linen ~= nil and linen.have == 5 and linen.miss > 0, "missing material counted as Linen Cloth (bolts + loose cloth)", linen and (linen.have .. "/" .. linen.need))
      Check(t.nextRank and t.nextRank.name == "Oficial" and t.nextRank.level == 10, "next rank Oficial (skill 50, level 10)", t.nextRank and t.nextRank.name)
      Check(t.nextTrainer and t.nextTrainer[1] == 1455, "a gnome trains Journeyman Tailoring in Ironforge", t.nextTrainer and table.concat(t.nextTrainer, ", "))
      local e = P.State("enchanting")
      Check(e.seg ~= nil and e.seg.name:find("Encantar", 1, true) == 1, "enchanting route in Spanish", e.seg and e.seg.name)
      Check(e.nextTrainer and e.nextTrainer[1] == 1455, "enchanting Journeyman trainer in Ironforge (Gimble Thistlefuzz)", e.nextTrainer and e.nextTrainer[4])
      S().UI:ShowPanel(); S().UI:ShowTab("professions"); Sim.Advance(0.5)
      P.Refresh(); Sim.Advance(0.3)
      local txt = TabText()
      Check(txt:find("Capa de lino", 1, true) ~= nil, "tab shows the craft by its Spanish name", txt:sub(1, 300))
      Check(txt:find("Siguiente rango: Oficial", 1, true) ~= nil, "tab shows the next rank", txt:sub(1, 300))
      Check(txt:find("Quedan unas", 1, true) ~= nil, "tab shows the expected crafts left")
      Check(txt:find("recomendadas", 1, true) == nil, "no recommendation block: both primaries learned")
    `,
  },
  {
    id: 'prof-mining',
    title: 'Professions: a gnome warlock who learned Mining (not in the plan) sees Mining listed, and the plan for the free slot',
    char: 'gnome-warlock',
    lua: TAB_TEXT + L_`
      local cfg = Sim.CHARS["gnome-warlock"]
      cfg.level = 9
      cfg.profs = { { name = "Minería", skillLine = 186, rank = 30, max = 75 } }
      Login()
      Sim.Advance(2)
      local P = S().Modules.Professions
      Check(Keys(P) == "mining,tailoring", "mining (learned) + tailoring (recommended for the free slot)", Keys(P))
      local m = P.State("mining")
      Check(m.learned and m.rank == 30 and m.kind == "gathering", "mining state from the client", tostring(m.rank) .. " " .. tostring(m.kind))
      Check(m.inPlan == false, "mining is not in the warlock plan")
      local t = P.State("tailoring")
      Check(t.missing and t.recommended, "tailoring recommended, not learned")
      Check(t.trainer and t.trainer[1] == 1455, "Apprentice Tailoring trainer for a gnome in Ironforge", t.trainer and table.concat(t.trainer, ", "))
      S().UI:ShowPanel(); S().UI:ShowTab("professions"); Sim.Advance(0.5)
      P.Refresh(); Sim.Advance(0.3)
      local txt = TabText()
      Check(txt:find("Minería", 1, true) ~= nil, "tab lists Minería", txt:sub(1, 300))
      Check(txt:find("Te falta una profesión principal", 1, true) ~= nil, "tab says a primary is missing", txt:sub(1, 400))
      Check(txt:find("Por qué", 1, true) ~= nil, "with the why")
    `,
  },
  {
    id: 'prof-druid',
    title: 'Professions: night elf druid with Herbalism + Alchemy (alchemy route at 90, Darnassus trainers)',
    char: 'nightelf-druid',
    lua: TAB_TEXT + L_`
      local cfg = Sim.CHARS["nightelf-druid"]
      cfg.level = 22
      cfg.profs = { { name = "Alquimia", skillLine = 171, rank = 90, max = 150 }, { name = "Botánica", skillLine = 182, rank = 100, max = 150 } }
      Login()
      Sim.Advance(2)
      local P = S().Modules.Professions
      Check(Keys(P) == "herbalism,alchemy", "the druid's two professions, in plan order", Keys(P))
      local a = P.State("alchemy")
      Check(a.seg ~= nil and a.seg.from <= 90 and a.seg.to > 90 and a.seg.name ~= "", "alchemy bracket at 90", a.seg and (a.seg.from .. "-" .. a.seg.to .. " " .. a.seg.name))
      Check(a.nextRank and a.nextRank.name == "Experto", "next rank Experto", a.nextRank and a.nextRank.name)
      Check(a.nextTrainer and a.nextTrainer[1] == 1457, "Expert Alchemy in Darnassus (Ainethil)", a.nextTrainer and table.concat(a.nextTrainer, ", "))
      local h = P.State("herbalism")
      Check(h.learned and h.rank == 100 and h.kind == "gathering", "herbalism («Botánica») read from the client", tostring(h.rank))
      S().UI:ShowPanel(); S().UI:ShowTab("professions"); Sim.Advance(0.5)
      P.Refresh(); Sim.Advance(0.3)
      local txt = TabText()
      Check(txt:find("Alquimia 90/150", 1, true) ~= nil, "tab shows Alquimia 90/150", txt:sub(1, 300))
    `,
  },
  {
    id: 'prof-cap',
    title: 'Professions: rank cap at 75 without Journeyman warns to train (and waits for level 10 below it)',
    char: 'gnome-warlock',
    lua: TAB_TEXT + L_`
      local cfg = Sim.CHARS["gnome-warlock"]
      cfg.level = 8
      cfg.profs = { { name = "Sastrería", skillLine = 197, rank = 75, max = 75 } }
      Login()
      Sim.Advance(3)
      local P = S().Modules.Professions
      local t = P.State("tailoring")
      Check(t.capped and t.capped.name == "Oficial" and not t.train, "level 8: Journeyman waits for level 10", t.capped and t.capped.name)
      Check(t.atCap, "at the cap")
      Sim.player.level = 10
      Sim.Fire("PLAYER_LEVEL_UP", 10, 0, 0, 0, 0, 0, 0, 0, 0)
      Sim.Advance(2)
      t = P.State("tailoring")
      Check(t.train and t.train.name == "Oficial", "level 10: train Journeyman now", t.train and t.train.name)
      local adv = P.Advice(t) or ""
      Check(adv:find("Entrena Oficial de", 1, true) ~= nil and adv:find("75", 1, true) ~= nil, "advice: train Oficial, points above 75 are lost", adv)
      local chat = table.concat(Sim.chat or {}, " | ")
      Check(Plain(chat):find("entrena Oficial ya", 1, true) ~= nil or Plain(chat):find("pide nivel 10", 1, true) ~= nil, "cap warning in the chat", Plain(chat):sub(-300))
      S().UI:ShowPanel(); S().UI:ShowTab("professions"); Sim.Advance(0.5)
      P.Refresh(); Sim.Advance(0.3)
      local txt = TabText()
      Check(txt:find("Entrena Oficial de", 1, true) ~= nil, "tab shows the train-now warning", txt:sub(1, 300))
    `,
  },
  {
    id: 'prof-none',
    title: 'Professions: no profession yet: class recommendation with its why; secondary professions are listed too',
    char: 'human-mage',
    lua: TAB_TEXT + L_`
      local cfg = Sim.CHARS["human-mage"]
      local saved = cfg.profs
      cfg.level = 6
      cfg.profs = { { name = "Cocina", skillLine = 185, rank = 12, max = 75, slot = "cook" } }
      Login()
      Sim.Advance(2)
      cfg.profs = saved
      local P = S().Modules.Professions
      Check(Keys(P) == "cooking,tailoring,enchanting", "cooking (learned) + the mage plan", Keys(P))
      local c = P.State("cooking")
      Check(c.learned and c.rank == 12 and c.kind == "secondary" and c.seg ~= nil, "cooking route at 12", c.seg and c.seg.name)
      local t = P.State("tailoring")
      Check(t.missing and t.trainer and t.trainer[1] == 1453, "Apprentice Tailoring for a human: Stormwind", t.trainer and table.concat(t.trainer, ", "))
      S().UI:ShowPanel(); S().UI:ShowTab("professions"); Sim.Advance(0.5)
      P.Refresh(); Sim.Advance(0.3)
      local txt = TabText()
      Check(txt:find("Profesiones recomendadas para tu clase", 1, true) ~= nil, "recommendation title", txt:sub(1, 300))
      Check(txt:find("Por qué", 1, true) ~= nil and txt:find("paño", 1, true) ~= nil, "with the why (cloth from humanoids)", txt:sub(1, 600))
    `,
  },
  {
    id: 'prof-trainer',
    title: 'Professions: the trainer window highlights the route recipe you can learn now',
    char: 'gnome-warlock',
    lua: L_`
      local cfg = Sim.CHARS["gnome-warlock"]
      cfg.level = 12
      cfg.profs = { { name = "Sastrería", skillLine = 197, rank = 20, max = 75 } }
      Login()
      Sim.Advance(2)
      Sim.SPELL_NAMES[8776] = "Cinturón de lino"
      Sim.SPELL_NAMES[3915] = "Camisa de lino marrón"
      if ClassTrainerFrame then ClassTrainerFrame:Show() end
      Sim.trainer = { { spell = 3915, cost = 50 }, { spell = 8776, cost = 50 } }
      local T = S().Modules.Trainer
      local list = T.Services()
      local belt, shirt
      for _, s in ipairs(list) do
        if s.name == "Cinturón de lino" then belt = s end
        if s.name == "Camisa de lino marrón" then shirt = s end
      end
      Check(belt and belt.rec and belt.prof ~= nil, "Linen Belt (route 15-70) is highlighted", belt and tostring(belt.rec))
      Check(shirt and not shirt.rec, "a recipe off the route is not", shirt and tostring(shirt.rec))
    `,
  },
];

module.exports = { scenarios };

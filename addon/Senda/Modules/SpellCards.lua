-- Senda / Modules / SpellCards
-- Dos tarjetas pegadas al HUD:
--   1) Al subir de nivel (y al entrar en el juego si queda algo pendiente): los hechizos de clase que ya puedes
--      entrenar (Knowledge.TrainNow), con icono y tooltip del juego, el coste total (el del conocimiento o el que
--      Trainer.lua guardó al visitar al instructor), si te llega el dinero y dónde entrenar: el paso de entrenar de
--      la guía si está cerca, si no el instructor de tu clase que conoce la guía. Un botón apunta la flecha.
--      Si el HUD ya ofrece la línea verde de «Ya puedes entrenar», la tarjeta no repite dónde.
--   2) Rangos de las barras: tras aprender hechizos (y al entrar) busca en tus casillas hechizos con un rango
--      mayor en el libro y ofrece «Renovar» (fuera de combate). Clic derecho en una línea = mantener ese rango.
--      Nunca toca macros ni objetos.
-- Nunca se muestran en combate ni en instancias; se quitan solas pasado un rato.
-- Adaptado de Polestar (QoL/Spells.lua, UI/SpellCards.lua): la lectura del libro por rangos y el cambio de casillas.
local ADDON, Senda = ...
local M = Senda.Mod
if not M then return end
local L = M.L

local C = {}
Senda.Modules.SpellCards = C

C.HIDE_AFTER = 45     -- segundos en pantalla
C.NEAR_STEPS = 8      -- «cerca» en la guía: hasta este número de pasos pendientes
C.SLOTS = 180         -- casillas de acción que se leen
C.MAX_ICONS = 20
C.MAX_RANK_LINES = 5
C.LOGIN_DELAY = 8

local function UI() return Senda.UI end

------------------------------------------------------------------------
-- Datos guardados
------------------------------------------------------------------------
local function Store()
  local db = M.DB()
  if type(db.cards) ~= "table" then db.cards = {} end
  return db.cards
end
local function Sub(key)
  local s = Store()
  if type(s[key]) ~= "table" then s[key] = {} end
  return s[key]
end

function C.Kept(id) return Sub("keptRanks")[id] == true end
function C.Keep(id, on) Sub("keptRanks")[id] = (on ~= false) or nil end

------------------------------------------------------------------------
-- Cuándo se puede enseñar
------------------------------------------------------------------------
local function InstanceType()
  local f = Senda.Compat and Senda.Compat.InstanceType
  if f then local ok, t = pcall(f); if ok then return t end end
  return "none"
end

local function Blocked()
  if M.InCombat() then return true end
  local t = InstanceType()
  if t and t ~= "none" then return true end
  if Senda.Visibility and Senda.Visibility.Hidden and Senda.Visibility:Hidden() then return true end
  return false
end

------------------------------------------------------------------------
-- Hechizos nuevos del nivel
------------------------------------------------------------------------
-- { { id, level, cost (nil si no se sabe), trainer } } de lo que el instructor te enseña ahora.
function C.LevelList()
  local K = Senda.Modules.Knowledge
  local T = Senda.Modules.Trainer
  local out = {}
  if not (K and K.TrainNow) then return out end
  local ok, now = pcall(K.TrainNow)
  if not ok or type(now) ~= "table" then return out end
  for _, e in ipairs(now) do
    -- El precio que el instructor te mostró (con descuentos de reputación) gana al compilado del conocimiento.
    local cost = T and T.CachedCost and T.CachedCost(e.spell) or nil
    if not cost then cost = e.cost end
    out[#out + 1] = { id = e.spell, level = e.level, cost = cost, trainer = e.trainer }
  end
  return out
end

local function ListKey(list)
  local ids = {}
  for _, s in ipairs(list) do ids[#ids + 1] = tostring(s.id) end
  return table.concat(ids, ",")
end

-- Coste total: (suma conocida, cuántos hechizos sin precio).
function C.Cost(list)
  local total, unknown = 0, 0
  for _, s in ipairs(list) do
    if s.cost then total = total + s.cost else unknown = unknown + 1 end
  end
  return total, unknown
end

local function StepAt(step)
  local at = step and step.at
  if type(at) == "table" and tonumber(at[1]) and tonumber(at[2]) and tonumber(at[3]) then return at end
end

local function MapName(map)
  local f = Senda.Compat and Senda.Compat.MapName
  return f and f(map) or nil
end

local function Place(step, at)
  return at[4] or MapName(at[1]) or ""
end

-- Dónde entrenar: { kind = "gate"|"current"|"guide"|"trainer", steps, at, label } o nil.
function C.Where(list)
  local E = Senda.Engine
  if not E then return nil end
  -- La línea verde del HUD («Ya puedes entrenar...») ya lo ofrece: no se repite.
  if E.LevelGated then
    for _, g in ipairs(E:LevelGated()) do
      if g.ready and g.entry.step["do"] == "train" then return { kind = "gate" } end
    end
  end
  local cur = E:CurrentStep()
  if cur and cur["do"] == "train" then return { kind = "current", steps = 0 } end
  if E.NextSteps then
    for i, e in ipairs(E:NextSteps(C.NEAR_STEPS)) do
      local at = e.step["do"] == "train" and StepAt(e.step)
      if at then return { kind = "guide", steps = i, at = at, label = Place(e.step, at) } end
    end
  end
  -- Instructor indicado en el conocimiento (campo opcional `trainer = [mapa, x, y, "nombre"]`).
  for _, s in ipairs(list) do
    local t = s.trainer
    if type(t) == "table" and tonumber(t[1]) and tonumber(t[2]) and tonumber(t[3]) then
      return { kind = "trainer", at = t, label = t[4] or MapName(t[1]) or "" }
    end
  end
  -- Instructor de la guía: el de tu mapa (el más cercano), si no el siguiente pendiente, si no el último.
  local map, px, py
  if Senda.Compat and Senda.Compat.PlayerMapPos then map, px, py = Senda.Compat.PlayerMapPos() end
  local here, after, last, bestD
  local idx = E:Index() or 1
  for i, e in ipairs(E:Steps()) do
    local at = e.step["do"] == "train" and StepAt(e.step)
    if at and E:IsApplicable(e) then
      last = { at = at, step = e.step }
      if i > idx and not after then after = last end
      if map and tonumber(at[1]) == map then
        local d = (at[2] / 100 - (px or 0)) ^ 2 + (at[3] / 100 - (py or 0)) ^ 2
        if not bestD or d < bestD then bestD, here = d, last end
      end
    end
  end
  local pick = here or after or last
  if pick then return { kind = "trainer", at = pick.at, label = Place(pick.step, pick.at) } end
  return nil
end

------------------------------------------------------------------------
-- Rangos en las barras
------------------------------------------------------------------------
local function RankOf(id)
  local fn = (C_Spell and C_Spell.GetSpellSubtext) or _G.GetSpellSubtext
  if not fn then return nil end
  local ok, text = pcall(fn, id)
  if ok and type(text) == "string" then return tonumber(text:match("(%d+)")) end
  return nil
end
C.RankOf = RankOf

local function EachBookSpell(fn)
  local SB = C_SpellBook
  if SB and SB.GetNumSpellBookSkillLines and SB.GetSpellBookSkillLineInfo and SB.GetSpellBookItemInfo then
    local bank = (Enum and Enum.SpellBookSpellBank and Enum.SpellBookSpellBank.Player) or 0
    local spellType = Enum and Enum.SpellBookItemType and Enum.SpellBookItemType.Spell or 1
    for i = 1, SB.GetNumSpellBookSkillLines() or 0 do
      local line = SB.GetSpellBookSkillLineInfo(i)
      if line then
        local off = line.itemIndexOffset or 0
        for k = off + 1, off + (line.numSpellBookItems or 0) do
          local info = SB.GetSpellBookItemInfo(k, bank)
          if info and info.spellID and info.itemType == spellType then fn(info.spellID) end
        end
      end
    end
  elseif GetNumSpellTabs and GetSpellTabInfo and GetSpellBookItemInfo then
    for i = 1, GetNumSpellTabs() or 0 do
      local _, _, off, n = GetSpellTabInfo(i)
      for k = (off or 0) + 1, (off or 0) + (n or 0) do
        local kind, id = GetSpellBookItemInfo(k, "spell")
        if kind == "SPELL" and id then fn(id) end
      end
    end
  end
end

-- nombre -> { rank, id } del rango más alto del libro (solo hechizos con rango).
function C.BookBest()
  local best = {}
  pcall(EachBookSpell, function(id)
    local name, rank = M.SpellName(id), RankOf(id)
    if name and rank then
      local b = best[name]
      if not b or rank > b.rank then best[name] = { rank = rank, id = id } end
    end
  end)
  return best
end

local function SlotSpell(slot)
  if not GetActionInfo then return nil end
  local has = (C_ActionBar and C_ActionBar.HasAction) or _G.HasAction
  if has and not has(slot) then return nil end
  local kind, id = GetActionInfo(slot)
  if kind == "spell" and type(id) == "number" then return id end
  return nil
end

-- { { id, bestId, name, have, best, slots = {...} } }, número de casillas.
-- Solo hechizos (nunca macros ni objetos) con rango y uno mayor en el libro; sin los que mantuviste.
function C.OldRanks()
  local book = C.BookBest()
  local byId, list, n = {}, {}, 0
  for slot = 1, C.SLOTS do
    local id = SlotSpell(slot)
    if id and not C.Kept(id) then
      local name = M.SpellName(id)
      local b = name and book[name]
      local have = b and RankOf(id)
      if b and have and b.rank > have and b.id ~= id then
        local e = byId[id]
        if not e then
          e = { id = id, bestId = b.id, name = name, have = have, best = b.rank, slots = {} }
          byId[id] = e
          list[#list + 1] = e
        end
        e.slots[#e.slots + 1] = slot
        n = n + 1
      end
    end
  end
  table.sort(list, function(a, b) return a.slots[1] < b.slots[1] end)
  return list, n
end

local function Pickup(id)
  local f = (C_Spell and C_Spell.PickupSpell) or _G.PickupSpell
  if f then f(id) end
end

local upgradeWaiting = false

-- Cambia esas casillas por el rango más alto. Devuelve cuántas cambió (nil = espera al final del combate).
function C.Upgrade()
  if M.InCombat() then
    upgradeWaiting = true
    M.Print(L.CARD_RANK_AFTER_COMBAT)
    return nil
  end
  upgradeWaiting = false
  if not (PlaceAction and ClearCursor) then return 0 end
  if GetCursorInfo and GetCursorInfo() then
    M.Print(L.CARD_CURSOR_BUSY)
    return 0
  end
  local done = 0
  for _, e in ipairs((C.OldRanks())) do
    for _, slot in ipairs(e.slots) do
      if SlotSpell(slot) == e.id then
        ClearCursor()
        local ok = pcall(Pickup, e.bestId)
        if ok and GetCursorInfo and GetCursorInfo() then
          pcall(PlaceAction, slot)
          ClearCursor() -- el rango antiguo vuelve al cursor
          if SlotSpell(slot) == e.bestId then done = done + 1 end
        else
          ClearCursor()
        end
      end
    end
  end
  if done > 0 then M.Print(string.format(done == 1 and L.CARD_RANK_DONE_1 or L.CARD_RANK_DONE, done)) end
  C.rankTold = nil
  return done
end

------------------------------------------------------------------------
-- Tarjetas (marcos)
------------------------------------------------------------------------
local W, PAD = 320, 8
local cards = {}   -- level / rank

-- Orden vertical: HUD, tarjeta de nivel, tarjeta de rangos.
local function Plan()
  local prev
  local hud = _G.SendaHUD
  for _, key in ipairs({ "level", "rank" }) do
    local c = cards[key]
    if c and c.frame:IsShown() then
      c.frame:ClearAllPoints()
      if prev then
        c.frame:SetPoint("TOPLEFT", prev, "BOTTOMLEFT", 0, -4)
      elseif hud and hud:IsShown() then
        c.frame:SetPoint("TOPLEFT", hud, "BOTTOMLEFT", 0, -4)
      else
        c.frame:SetPoint("TOP", UIParent, "TOP", 0, -170)
      end
      prev = c.frame
    end
  end
end

local function Dismiss(key)
  local c = cards[key]
  if not c then return end
  c.want = false
  c.token = (c.token or 0) + 1
  c.frame:Hide()
  Plan()
end
C.Dismiss = Dismiss

local function NewFrame(key, name)
  local ui = UI()
  local f = CreateFrame("Frame", name, UIParent, BackdropTemplateMixin and "BackdropTemplate" or nil)
  ui:Backdrop(f, "panel")
  f:SetWidth(W)
  f:SetHeight(80)
  f:SetClampedToScreen(true)
  f:SetFrameStrata("MEDIUM")
  f:EnableMouse(true)
  f:Hide()
  f.head = f:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  f.head:SetPoint("TOPLEFT", PAD, -8)
  f.head:SetPoint("RIGHT", -24, 0)
  f.head:SetJustifyH("LEFT")
  f.close = ui:IconButton(f, "Interface\\Buttons\\UI-StopButton", 12, function() Dismiss(key) end)
  f.close:SetPoint("TOPRIGHT", -6, -7)
  return f
end

local function FS(parent, color)
  local fs = parent:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  fs:SetJustifyH("LEFT")
  fs:SetJustifyV("TOP")
  if color then fs:SetTextColor(color[1], color[2], color[3]) end
  return fs
end

local function SpellTooltip(self)
  if not (GameTooltip and self.spell) then return end
  GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
  if GameTooltip.SetSpellByID then
    pcall(GameTooltip.SetSpellByID, GameTooltip, self.spell)
  elseif GameTooltip.SetHyperlink then
    pcall(GameTooltip.SetHyperlink, GameTooltip, "spell:" .. tostring(self.spell))
  end
  if self.cost and self.cost > 0 then
    GameTooltip:AddLine(string.format(L.CARD_SPELL_COST, M.MoneyPlain(self.cost)), 1, 1, 1)
  end
  GameTooltip:Show()
end

local function StartTimer(key)
  local c = cards[key]
  c.token = (c.token or 0) + 1
  local token = c.token
  M.After(C.HIDE_AFTER, function()
    if c.token == token then Dismiss(key) end
  end)
end

-- Tarjeta de nivel ----------------------------------------------------
local function LevelCard()
  local c = cards.level
  if c then return c end
  local ui = UI()
  c = { key = "level" }
  c.frame = NewFrame("level", "SendaLevelCard")
  local f = c.frame
  f.icons = {}
  f.more = FS(f)
  f.cost = FS(f)
  f.route = FS(f, { 0.95, 0.80, 0.30 })
  f.point = ui:Button(f, L.CARD_POINT, 90, 20, function()
    local w = c.where
    if not (w and w.at and Senda.Arrow) then return end
    local label = (w.label and w.label ~= "") and w.label or L.CARD_TRAINER
    Senda.Arrow:SetTarget(w.at[1], w.at[2], w.at[3], label, "trainer")
    M.Print(string.format(L.CARD_POINTED, label))
  end)
  ui:Tooltip(f.point, L.CARD_POINT, L.CARD_POINT_TIP)
  cards.level = c
  return c
end

local function IconButton(f, i)
  local b = f.icons[i]
  if b then return b end
  b = CreateFrame("Button", nil, f)
  b:SetSize(26, 26)
  b.tex = b:CreateTexture(nil, "ARTWORK")
  b.tex:SetAllPoints()
  b.tex:SetTexCoord(0.07, 0.93, 0.07, 0.93)
  b:SetScript("OnEnter", SpellTooltip)
  b:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
  f.icons[i] = b
  return b
end

local function RenderLevel()
  local c = LevelCard()
  local f = c.frame
  local list = C.LevelList()
  if #list == 0 then return false end
  local money = GetMoney and GetMoney() or 0
  local total, unknown = C.Cost(list)
  f.head:SetText(string.format(#list == 1 and L.CARD_LEVEL_HEAD_1 or L.CARD_LEVEL_HEAD, M.Level(), #list))
  local y = 26
  for i = 1, #f.icons do f.icons[i]:Hide() end
  local shown = math.min(#list, C.MAX_ICONS)
  for i = 1, shown do
    local s = list[i]
    local b = IconButton(f, i)
    b.spell, b.cost = s.id, s.cost
    b.tex:SetTexture(M.SpellIcon(s.id) or "Interface\\Icons\\INV_Misc_QuestionMark")
    b:ClearAllPoints()
    b:SetPoint("TOPLEFT", PAD + ((i - 1) % 10) * 30, -(y + math.floor((i - 1) / 10) * 30))
    b:Show()
  end
  y = y + (math.floor((shown - 1) / 10) + 1) * 30
  if #list > shown then
    f.more:SetText(string.format(L.CARD_MORE, #list - shown))
    f.more:ClearAllPoints(); f.more:SetPoint("TOPLEFT", PAD, -y); f.more:Show()
    y = y + 14
  else
    f.more:Hide()
  end
  -- coste y si te llega
  local ui = UI()
  local text
  if total > 0 and unknown == 0 then
    if money >= total then
      text = ui:Color("green", string.format(L.CARD_COST_OK, M.Money(total), M.Money(money)))
    else
      text = ui:Color("red", string.format(L.CARD_COST_SHORT, M.Money(total), M.Money(money), M.Money(total - money)))
    end
  elseif total > 0 then
    text = ui:Color("gold", string.format(L.CARD_COST_PARTIAL, M.Money(total), unknown, M.Money(money)))
  else
    text = ui:Color("dim", string.format(L.CARD_COST_UNKNOWN, M.Money(money)))
  end
  f.cost:SetText(text)
  f.cost:ClearAllPoints(); f.cost:SetPoint("TOPLEFT", PAD, -y); f.cost:SetPoint("RIGHT", -PAD, 0)
  y = y + f.cost:GetStringHeight() + 4
  -- dónde
  local w = C.Where(list)
  c.where = w
  local route
  local label = w and w.label
  if w and (not label or label == "") then label = L.CARD_TRAINER end
  if w and w.kind == "current" then
    route = L.CARD_ROUTE_CURRENT
  elseif w and w.kind == "guide" then
    route = w.steps == 1 and string.format(L.CARD_ROUTE_GUIDE_1, label) or string.format(L.CARD_ROUTE_GUIDE, w.steps, label)
  elseif w and w.kind == "trainer" then
    route = string.format(L.CARD_ROUTE_TRAINER, label)
  end
  if route then
    f.route:SetText(route)
    f.route:ClearAllPoints(); f.route:SetPoint("TOPLEFT", PAD, -y); f.route:SetPoint("RIGHT", -PAD, 0)
    f.route:Show()
    y = y + f.route:GetStringHeight() + 4
  else
    f.route:SetText(""); f.route:Hide()
  end
  local canPoint = w ~= nil and w.at ~= nil
  f.point:SetShown(canPoint)
  if canPoint then
    f.point:ClearAllPoints(); f.point:SetPoint("TOPLEFT", PAD, -y)
    y = y + 24
  end
  f:SetHeight(y + 6)
  return true
end

-- Tarjeta de rangos --------------------------------------------------
local function RankCard()
  local c = cards.rank
  if c then return c end
  local ui = UI()
  c = { key = "rank", rows = {} }
  c.frame = NewFrame("rank", "SendaRankCard")
  local f = c.frame
  f.rows = c.rows
  f.more = FS(f)
  f.hint = FS(f, { 0.55, 0.58, 0.62 })
  f.upgrade = ui:Button(f, L.CARD_RANK_UPGRADE, 90, 20, function()
    C.Upgrade()
    M.After(0.3, function() C.Check(true) end)
  end)
  ui:Tooltip(f.upgrade, L.CARD_RANK_UPGRADE, L.CARD_RANK_UPGRADE_TIP)
  cards.rank = c
  return c
end

local function RankRow(c, i)
  local r = c.rows[i]
  if r then return r end
  r = CreateFrame("Button", nil, c.frame)
  r:SetHeight(18)
  r:RegisterForClicks("LeftButtonUp", "RightButtonUp")
  r.tex = r:CreateTexture(nil, "ARTWORK")
  r.tex:SetSize(16, 16)
  r.tex:SetPoint("LEFT")
  r.text = FS(r)
  r.text:SetPoint("LEFT", r.tex, "RIGHT", 6, 0)
  r.text:SetPoint("RIGHT")
  r.text:SetJustifyV("MIDDLE")
  r.text:SetWordWrap(false)
  r:SetScript("OnClick", function(self, button)
    if button == "RightButton" and self.spell then
      C.Keep(self.spell, true)
      M.Print(string.format(L.CARD_KEPT, self.name or ""))
      C.Check(true)
    end
  end)
  r:SetScript("OnEnter", function(self)
    if not GameTooltip then return end
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:SetText(self.name or "", 1, 1, 1)
    GameTooltip:AddLine(L.CARD_RANK_KEEP_TIP, 0.8, 0.8, 0.8, true)
    GameTooltip:Show()
  end)
  r:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
  c.rows[i] = r
  return r
end

local function RenderRank()
  local c = RankCard()
  local f = c.frame
  local list, n = C.OldRanks()
  if #list == 0 then return false end
  f.head:SetText(L.CARD_RANK_HEAD)
  local y = 26
  for i = 1, #c.rows do c.rows[i]:Hide() end
  local shown = math.min(#list, C.MAX_RANK_LINES)
  for i = 1, shown do
    local e = list[i]
    local r = RankRow(c, i)
    r.spell, r.name = e.id, e.name
    r.tex:SetTexture(M.SpellIcon(e.id) or "Interface\\Icons\\INV_Misc_QuestionMark")
    local slots = #e.slots == 1 and L.CARD_RANK_SLOTS_1 or string.format(L.CARD_RANK_SLOTS, #e.slots)
    r.text:SetText(string.format(L.CARD_RANK_LINE, e.name, e.have, e.best) .. " |cff8c949e" .. slots .. "|r")
    r:ClearAllPoints()
    r:SetPoint("TOPLEFT", PAD, -y)
    r:SetPoint("RIGHT", -PAD, 0)
    r:Show()
    y = y + 20
  end
  if #list > shown then
    f.more:SetText(string.format(L.CARD_MORE, #list - shown))
    f.more:ClearAllPoints(); f.more:SetPoint("TOPLEFT", PAD, -y); f.more:Show()
    y = y + 14
  else
    f.more:Hide()
  end
  f.hint:SetText(L.CARD_RANK_HINT)
  f.hint:ClearAllPoints(); f.hint:SetPoint("TOPLEFT", PAD, -y); f.hint:SetPoint("RIGHT", -PAD, 0)
  y = y + f.hint:GetStringHeight() + 4
  f.upgrade:ClearAllPoints(); f.upgrade:SetPoint("TOPLEFT", PAD, -y)
  y = y + 24
  f:SetHeight(y + 6)
  c.count = n
  return true
end

local RENDER = { level = RenderLevel, rank = RenderRank }

-- Muestra (o quita) lo que toque ahora; se llama tras cualquier cambio.
function C.Flush()
  for _, key in ipairs({ "level", "rank" }) do
    local c = cards[key]
    if c and c.want then
      if Blocked() then
        c.frame:Hide()
      elseif RENDER[key]() then
        if not c.frame:IsShown() then
          c.frame:Show()
          StartTimer(key)
        end
      else
        c.want = false
        c.frame:Hide()
      end
    end
  end
  Plan()
end

local function Want(creator)
  local c = creator()
  c.want = true
  c.frame:Hide()   -- se pone el temporizador al mostrarla
  C.Flush()
end

------------------------------------------------------------------------
-- Disparadores
------------------------------------------------------------------------
-- Nivel: al subir, si algún hechizo pendiente es de este nivel; al entrar, si la lista cambió desde la última vez.
function C.CheckLevel(level, login)
  if M.Opt("mod_card_level") == false then return false end
  local list = C.LevelList()
  if #list == 0 then return false end
  local key = ListKey(list)
  local seen = Sub("told")
  if login then
    if seen.level == key then return false end
  else
    local fresh = false
    for _, s in ipairs(list) do if s.level == level then fresh = true end end
    if not fresh then return false end
  end
  seen.level = key
  Want(LevelCard)
  return true
end

-- Rangos: avisa de la lista nueva (la misma lista no se repite en la sesión).
function C.Check(force)
  if M.Opt("mod_card_rank") == false then return false end
  local list = C.OldRanks()
  if #list == 0 then
    C.rankTold = nil
    local c = cards.rank
    if c then c.want = false; c.frame:Hide(); Plan() end
    return false
  end
  local parts = {}
  for _, e in ipairs(list) do parts[#parts + 1] = e.id .. ">" .. e.bestId .. "@" .. table.concat(e.slots, ".") end
  local key = table.concat(parts, ",")
  if key == C.rankTold and not force then return false end
  C.rankTold = key
  Want(RankCard)
  return true
end

function C.Visible(key) local c = cards[key]; return c ~= nil and c.frame:IsShown() end

M.RegisterOption({ key = "mod_card_level", label = L.CARD_OPT_LEVEL, type = "toggle", default = true })
M.RegisterOption({ key = "mod_card_rank", label = L.CARD_OPT_RANK, type = "toggle", default = true })

local function Safe(fn, ...)
  local ok, err = pcall(fn, ...)
  if not ok then M.Debug("SpellCards: %s", tostring(err)) end
end

M.On("PLAYER_LEVEL_UP", function(_, level)
  level = tonumber(level) or M.Level()
  -- Después del aviso de la línea verde del motor y de que el cliente actualice el libro.
  M.After(2, function() Safe(C.CheckLevel, level, false) end)
end)

local changes, bookPending = 0, false
local function BookChanged()
  changes = changes + 1
  local mine = changes
  M.After(1, function()
    if mine ~= changes then return end
    -- En combate (formas, posturas: SPELLS_CHANGED salta a menudo) no se leen barras ni libro: al salir.
    if M.InCombat() then bookPending = true; return end
    local c = cards.level
    if c and c.want then Safe(C.Flush) end -- aprendiste algo: refresca la lista (o la quita)
    if C.armed then Safe(C.Check, false) end
  end)
end
M.On("SPELLS_CHANGED", BookChanged)
M.On("LEARNED_SPELL_IN_SKILL_LINE", BookChanged)
M.On("LEARNED_SPELL_IN_TAB", BookChanged)

M.On("PLAYER_REGEN_DISABLED", function() Safe(C.Flush) end)
M.On("PLAYER_REGEN_ENABLED", function()
  if upgradeWaiting then M.After(0.5, function() Safe(C.Upgrade) end) end
  if bookPending then bookPending = false; BookChanged() end
  M.After(1, function() Safe(C.Flush) end)
end)
M.On("PLAYER_ENTERING_WORLD", function() M.After(2, function() Safe(C.Flush) end) end)
M.On("ZONE_CHANGED_NEW_AREA", function() M.After(1, function() Safe(C.Flush) end) end)

M.OnReady(function()
  M.After(C.LOGIN_DELAY, function()
    C.armed = true
    Safe(C.CheckLevel, M.Level(), true)
    Safe(C.Check, false)
  end)
end)

if Senda.Slash and Senda.Slash.Register then
  local function Run()
    C.armed = true
    if not C.Check(true) then M.Print(L.CARD_RANKS_NONE) end
  end
  Senda.Slash:Register("renovar", Run, L.CARD_SLASH_HELP)
  Senda.Slash:Register("ranks", Run, L.CARD_SLASH_HELP)
end

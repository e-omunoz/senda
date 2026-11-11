-- Senda / Modules / Advisor
-- «Qué hago»: lo más útil que puedes hacer ahora, por orden (talentos, instructor, profesiones, bolsas, avisos,
-- mejoras de equipo, siguiente paso de la guía), más avisos cortos para el HUD (Senda.HUD:SetAdvice si existe,
-- y siempre el evento interno SENDA_ADVICE). No calcula nada en combate (valores secretos de Midnight).
--
-- Avisos opcionales desde el conocimiento: [[warn]] check = "item"|"pet"|"buff"|"spell", spell, items, min,
-- minlevel, text. Sin ellos se usan avisos genéricos (bolsas, talentos, mascota perdida, piedra de salud).
local ADDON, Senda = ...
local M = Senda.Mod
if not M then return end
local L = M.L

local A = {}
Senda.Modules.Advisor = A

-- Crear piedra de salud (todos los rangos), datos del juego.
local CREATE_HS = { 6201, 6202, 5699, 11729, 11730 }

local function KnowsAny(ids)
  for _, id in ipairs(ids or {}) do if M.Known(id) then return true end end
  return false
end

local function CountAny(ids)
  local n = 0
  for _, id in ipairs(ids or {}) do n = n + M.ItemCount(id) end
  return n
end

local function PlayerBuffs()
  local ids, names = {}, {}
  for i = 1, 40 do
    local a
    if C_UnitAuras and C_UnitAuras.GetAuraDataByIndex then
      local ok, r = pcall(C_UnitAuras.GetAuraDataByIndex, "player", i, "HELPFUL"); a = ok and r
    end
    if not a then break end
    if a.spellId then ids[a.spellId] = true end
    if a.name then names[a.name] = true end
  end
  return ids, names
end

local function Resting()
  return (IsMounted and IsMounted()) or (UnitOnTaxi and UnitOnTaxi("player")) or (UnitIsDeadOrGhost and UnitIsDeadOrGhost("player"))
end

------------------------------------------------------------------------
-- Avisos cortos: { short, long }
------------------------------------------------------------------------
function A.Warnings()
  local w = {}
  if M.InCombat() then return w end
  local level = M.Level()
  local function add(short, long, key) table.insert(w, { short = short, long = long or short, key = key }) end

  local unspent = M.UnspentTalents()
  if unspent > 0 then add(string.format(L.MOD_WARN_TALENTS or "%d talento(s) sin gastar", unspent), nil, "talents") end

  local free = M.FreeSlots()
  if free < 3 then add(L.MOD_WARN_BAGS or "Bolsas llenas",
    string.format(L.MOD_WARN_BAGS_LONG or "Solo te quedan %d huecos en las bolsas: vende grises o desencanta verdes.", free)) end

  local custom, customPet, customHS = {}, false, false
  for _, p in ipairs(M.Pages()) do
    for _, c in ipairs(type(p.warn) == "table" and p.warn or {}) do
      if type(c) == "table" then table.insert(custom, c) end
    end
  end
  local buffIds, buffNames
  for _, c in ipairs(custom) do
    if level >= (c.minlevel or 1) and (not c.spell or c.check == "spell" or M.Known(c.spell)) then
      local hit = false
      if c.check == "pet" then
        customPet = true
        hit = not UnitExists("pet") and not Resting()
      elseif c.check == "item" then
        local MC = Senda.Modules.Macros
        for _, id in ipairs(c.items or {}) do
          for _, hs in ipairs(MC and MC.HEALTHSTONES or {}) do if id == hs then customHS = true end end
        end
        hit = CountAny(c.items) < (c.min or 1)
      elseif c.check == "buff" then
        if not buffIds then buffIds, buffNames = PlayerBuffs() end
        hit = true
        for _, id in ipairs(c.spells or (c.spell and { c.spell }) or {}) do
          local n = M.SpellName(id)
          if buffIds[id] or (n and buffNames[n]) then hit = false end
        end
        if Resting() then hit = false end
      elseif c.check == "spell" then
        hit = c.spell and not M.Known(c.spell)
      end
      if hit and c.text then add(c.text) end
    end
  end

  -- Mascota perdida: si este personaje ha tenido mascota y ahora no la lleva.
  if not customPet and M.DB().hadPet and not UnitExists("pet") and not Resting() then
    add(L.MOD_WARN_PET or "Sin mascota", L.MOD_WARN_PET_LONG or "No llevas tu mascota/demonio: invócala antes del siguiente combate.")
  end
  -- Piedra de salud: si sabes crearla y no llevas.
  if not customHS and KnowsAny(CREATE_HS) then
    local MC = Senda.Modules.Macros
    if MC and MC.HEALTHSTONES and CountAny(MC.HEALTHSTONES) == 0 then
      add(L.MOD_WARN_HS or "Sin Piedra de salud", L.MOD_WARN_HS_LONG or "No llevas Piedra de salud: créala antes de salir.")
    end
  end
  return w
end

------------------------------------------------------------------------
-- Lista de consejos: { text, icon, hl }
------------------------------------------------------------------------
function A.Items()
  local out = {}
  local level = M.Level()
  local function add(text, icon, hl) table.insert(out, { text = text, icon = icon, hl = hl }) end
  local K = Senda.Modules.Knowledge
  local P = Senda.Modules.Professions
  local G = Senda.Modules.Gear

  local unspent = M.UnspentTalents()
  if unspent > 0 then
    local cur = K and K.CurrentPick and K.CurrentPick(level)
    add(string.format(L.MOD_ADV_TALENTS or "Gasta %d punto(s) de talento.", unspent) ..
      (cur and (" " .. (L.MOD_NOW_PICK or "Ahora toca:") .. " |cffffffff" .. K.PickLabel(cur) .. "|r") or ""),
      "Interface\\Icons\\Ability_Marksmanship", "warn")
  end
  if K and K.TrainNow then
    local now = K.TrainNow(level)
    if #now > 0 then
      local names = {}
      for i, e in ipairs(now) do
        if i > 4 then table.insert(names, "..."); break end
        table.insert(names, M.SpellName(e.spell) or ("#" .. e.spell))
      end
      add(string.format(L.MOD_ADV_TRAIN or "Ve al instructor: %d hechizo(s) sin entrenar (%s).", #now, table.concat(names, ", ")),
        "Interface\\Icons\\INV_Misc_Book_09", "warn")
    end
  end
  local states = {}
  if P and P.States then
    local ok, r = pcall(P.States, level); if ok then states = r end
    for _, st in ipairs(states) do
      if (st.missing and level >= 5) or st.train then
        add(P.Advice(st), "Interface\\Icons\\Trade_Tailoring", "warn")
      end
    end
  end
  for _, wv in ipairs(A.Warnings()) do
    if wv.key ~= "talents" then add(wv.long, "Interface\\Icons\\INV_Misc_Bag_08", "warn") end
  end
  if G and G.Tips then
    local ok, tips = pcall(G.Tips)
    if ok then for _, t in ipairs(tips) do add(t, "Interface\\Icons\\INV_Chest_Cloth_17", "good") end end
  end
  local behind = {}
  for _, st in ipairs(states) do
    if (st.canNow or 0) > 0 and not st.capped then
      add(string.format(L.MOD_ADV_CRAFT or "Antes de salir, fabrica %d x %s: tienes el material.", st.canNow, P.SegName(st.seg)),
        P.SegIcon(st.seg), "good")
    end
    if st.behind and not st.done then table.insert(behind, st) end
  end
  for _, st in ipairs(behind) do
    add(string.format(L.MOD_ADV_BEHIND or "%s va atrasada (%d, ideal ~%d para tu nivel): dedica un rato a subirla.", st.label, st.rank, st.target),
      "Interface\\Icons\\Trade_Engineering")
  end
  if Senda.Engine and Senda.Engine.CurrentStep then
    local ok, step = pcall(Senda.Engine.CurrentStep, Senda.Engine)
    if ok and type(step) == "table" and step.text then
      add((L.MOD_ADV_STEP or "Siguiente paso de la guía:") .. " " .. step.text, "Interface\\Icons\\INV_Misc_Map_01", "now")
    end
  end
  local focus
  if #behind > 0 then
    focus = "|cffffd100" .. (L.MOD_FOCUS_PROF or "Foco: profesiones.") .. "|r " .. (L.MOD_FOCUS_PROF_LONG or "Súbelas hasta tu nivel y luego sigue con la guía.")
  else
    focus = "|cffffd100" .. (L.MOD_FOCUS_LEVEL or "Foco: subir de nivel.") .. "|r " .. (L.MOD_FOCUS_LEVEL_LONG or "Las profesiones van al día: fabrica solo cuando tengas material.")
  end
  return out, focus
end

-- Venta: grises y verdes sin usar.
local function SellLines()
  local lines = {}
  local greyN, greyV, greens = 0, 0, 0
  local G = Senda.Modules.Gear
  for _, it in ipairs(M.ScanBags()) do
    local _, _, q, _, _, _, _, _, equip, _, price = M.ItemInfo(it.link or it.id)
    q = it.quality or q
    if q == 0 and not it.noValue then
      greyN = greyN + it.count
      greyV = greyV + (price or 0) * it.count
    elseif q == 2 and type(equip) == "string" and equip ~= "" and equip ~= "INVTYPE_NON_EQUIP_IGNORE"
      and not (G and G.IsUpgrade and G.IsUpgrade(it.link or it.id)) then
      greens = greens + 1
    end
  end
  if greyN > 0 then table.insert(lines, string.format(L.MOD_ADV_GREYS or "Vende %d objetos grises (%s).", greyN, M.Money(greyV))) end
  if greens > 0 then
    if M.ProfRank("enchanting") then
      table.insert(lines, string.format(L.MOD_ADV_GREENS_DE or "Verdes sin usar en las bolsas: %d. Desencántalos.", greens))
    else
      table.insert(lines, string.format(L.MOD_ADV_GREENS or "Verdes sin usar en las bolsas: %d. Subasta o vendedor.", greens))
    end
  end
  return lines
end

------------------------------------------------------------------------
-- HUD
------------------------------------------------------------------------
local lastAdvice
function A.UpdateHUD()
  if M.InCombat() then return end
  if M.Opt("mod_advisor_hud") == false then
    if lastAdvice ~= "" then lastAdvice = ""; M.SetAdvice(nil) end
    return
  end
  local w = A.Warnings()
  local text
  if #w > 0 then
    local parts = {}
    for _, x in ipairs(w) do table.insert(parts, x.short) end
    text = "|cffff8040" .. table.concat(parts, " · ") .. "|r"
  end
  if text ~= lastAdvice then
    lastAdvice = text
    M.SetAdvice(text)
  end
end

------------------------------------------------------------------------
-- Pestaña
------------------------------------------------------------------------
local ui = {}

function A.Refresh()
  if not ui.doc then return end
  if M.InCombat() then
    ui.doc:Text(L.MOD_ADV_COMBAT or "En combate no se calcula nada. Vuelve a mirar al terminar.")
    return
  end
  local items, focus = A.Items()
  local nodes = { { t = "p", text = focus, raw = true } }
  if #items == 0 then
    table.insert(nodes, { t = "row", hl = "good", raw = true, icon = "Interface\\RaidFrame\\ReadyCheck-Ready",
      text = L.MOD_ADV_ALL_OK or "Todo en orden para tu nivel." })
  end
  for i, it in ipairs(items) do
    table.insert(nodes, { t = "row", raw = true, icon = it.icon, hl = it.hl, text = string.format("|cffffd100%d.|r %s", i, it.text) })
  end
  local sell = SellLines()
  if #sell > 0 then
    table.insert(nodes, { t = "h2", text = L.MOD_ADV_SELL or "Qué vender" })
    for _, s in ipairs(sell) do table.insert(nodes, { t = "li", text = s, raw = true }) end
  end
  table.insert(nodes, { t = "sp" })
  table.insert(nodes, { t = "p", raw = true, text = string.format("|cffaaaaaa%s %s|r", L.MOD_ADV_MONEY or "Llevas", M.Money(GetMoney and GetMoney() or 0)) })
  ui.doc:Set(nodes, true)
end

local function Build(parent)
  local bar, body = M.Toolbar(parent)
  local b = M.Button(bar, L.MOD_REFRESH or "Actualizar", 100, function() A.Refresh() end)
  b:SetPoint("LEFT", 6, 0)
  ui.doc = M.Doc(body)
end

M.RegisterTab({ key = "advisor", title = L.MOD_TAB_ADVISOR or "Qué hago", icon = "Interface\\Icons\\INV_Misc_Note_01",
  order = 15, build = Build, refresh = A.Refresh })
M.RegisterOption({ key = "mod_advisor_hud", label = L.MOD_OPT_ADVISOR_HUD or "Avisos del asesor en el HUD (talentos, bolsas, mascota, piedra...)",
  type = "toggle", default = true, onChange = function() lastAdvice = false; A.UpdateHUD() end })

function A.Update()
  M.Debounce("advisor-update", 1, function()
    if M.InCombat() then return end
    A.UpdateHUD()
    if ui.doc and ui.doc.scroll:IsVisible() then A.Refresh() end
  end)
end

M.On("UNIT_PET", function(_, unit)
  if unit == "player" and UnitExists("pet") then M.DB().hadPet = true end
  A.Update()
end)
for _, ev in ipairs({ "BAG_UPDATE_DELAYED", "PLAYER_LEVEL_UP", "SKILL_LINES_CHANGED", "SPELLS_CHANGED", "PLAYER_REGEN_ENABLED",
  "CHARACTER_POINTS_CHANGED", "PLAYER_MOUNT_DISPLAY_CHANGED", "PLAYER_UNGHOST", "PLAYER_ALIVE",
  "SENDA_STEP_CHANGED", "SENDA_GUIDE_CHANGED" }) do
  M.On(ev, A.Update)
end
M.On("UNIT_AURA", function(_, unit) if unit == "player" and not M.InCombat() then M.Debounce("advisor-aura", 2, A.Update) end end)
M.OnReady(function()
  if UnitExists("pet") then M.DB().hadPet = true end
  A.Update()
end)

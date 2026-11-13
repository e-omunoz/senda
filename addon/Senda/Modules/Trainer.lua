-- Senda / Modules / Trainer
-- Al abrir un instructor (TRAINER_SHOW): panel junto a su ventana con lo que puedes aprender, marcando lo que la
-- guía recomienda para tu nivel (conocimiento kind = "spells") y el coste total. Aprender pide confirmación.
-- En instructores de profesión: rango siguiente y receta de tu ruta (conocimiento kind = "professions").
local ADDON, Senda = ...
local M = Senda.Mod
if not M then return end
local L = M.L

local T = {}
Senda.Modules.Trainer = T

-- Precios vistos en el instructor, guardados por nombre y rango (los usa la tarjeta de subida de nivel).
local function CostKey(name, rank)
  return tostring(name):lower() .. "|" .. tostring(tonumber(tostring(rank or ""):match("(%d+)")) or 0)
end
local function CostCache()
  local db = M.DB()
  if type(db.trainerCost) ~= "table" then db.trainerCost = {} end
  return db.trainerCost
end
-- Coste (cobre) que viste en el instructor de un hechizo (id), o nil.
function T.CachedCost(id)
  local name = M.SpellName(id)
  if not name then return nil end
  local rank = Senda.Modules.SpellCards and Senda.Modules.SpellCards.RankOf and Senda.Modules.SpellCards.RankOf(id)
  local c = CostCache()
  return c[CostKey(name, rank)] or (not rank and c[CostKey(name, 1)]) or nil
end

-- { i, name, rank, cost, rec }
local function Services()
  local out = {}
  if not (GetNumTrainerServices and GetTrainerServiceInfo) then return out end
  local K = Senda.Modules.Knowledge
  local recNames = {}
  if K and K.TrainNow then
    local ok, list = pcall(K.TrainNow)
    if ok then
      for _, e in ipairs(list) do
        local n = M.SpellName(e.spell)
        if n then recNames[n:lower()] = true end
      end
    end
  end
  -- Recetas de las rutas de tus profesiones que ya puedes aprender y aún te dan puntos (datos generados).
  local profNames = {}
  local P = Senda.Modules.Professions
  if P and P.TrainerRecipes then
    local ok, list = pcall(P.TrainerRecipes)
    if ok and type(list) == "table" then profNames = list end
  end
  local okN, n = pcall(GetNumTrainerServices)
  for i = 1, (okN and n or 0) do
    local ok, name, rank, category = pcall(GetTrainerServiceInfo, i)
    if ok and name and category == "available" then
      local cost = 0
      if GetTrainerServiceCost then
        local okc, c = pcall(GetTrainerServiceCost, i); if okc then cost = c or 0 end
      end
      local lname = name:lower()
      if cost > 0 then CostCache()[CostKey(name, rank)] = cost end
      local pr = profNames[lname]
      table.insert(out, { i = i, name = name, rank = rank, cost = cost,
        rec = recNames[lname] or pr ~= nil, prof = pr })
    end
  end
  return out
end
T.Services = Services

local function Learn(list)
  if not BuyTrainerService then return end
  table.sort(list, function(a, b) return a.i > b.i end)
  for _, s in ipairs(list) do pcall(BuyTrainerService, s.i) end
  M.Print(L.MOD_TRAINER_DONE or "Aprendido. Recuerda poner los rangos nuevos en tus barras (pestaña Barras).")
end

local function ConfirmLearn(list)
  if #list == 0 then return end
  local lines, total = {}, 0
  for _, s in ipairs(list) do
    table.insert(lines, s.name .. ((s.rank and s.rank ~= "") and (" (" .. s.rank .. ")") or ""))
    total = total + s.cost
  end
  M.Confirm(string.format("Senda: " .. (L.MOD_TRAINER_CONFIRM or "¿Aprender %d?"), #list) .. "\n\n" .. table.concat(lines, "\n") ..
    "\n\n" .. (L.MOD_TOTAL or "Total") .. ": " .. M.MoneyPlain(total), function() Learn(list); M.After(0.5, T.Refresh) end,
    L.MOD_TRAINER_LEARN or "Aprender")
end

------------------------------------------------------------------------
-- Panel
------------------------------------------------------------------------
local panel, doc, recBtn, allBtn, announced

local function Ensure()
  local parent = ClassTrainerFrame
  if panel then return panel end
  if not parent then return nil end
  panel = M.Frame(parent, "SendaTrainerPanel")
  panel:SetSize(270, 340)
  panel:SetPoint("TOPLEFT", parent, "TOPRIGHT", 4, -30)
  local title = panel:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  title:SetPoint("TOPLEFT", 10, -8)
  title:SetText("Senda: " .. (L.MOD_TRAINER_TITLE or "qué aprender"))
  local holder = CreateFrame("Frame", nil, panel)
  holder:SetPoint("TOPLEFT", 4, -24)
  holder:SetPoint("BOTTOMRIGHT", -4, 60)
  doc = M.Doc(holder)
  recBtn = M.Button(panel, L.MOD_TRAINER_REC or "Aprender lo recomendado", 246, function()
    local list = {}
    for _, s in ipairs(Services()) do if s.rec then table.insert(list, s) end end
    ConfirmLearn(list)
  end)
  recBtn:SetPoint("BOTTOM", 0, 34)
  allBtn = M.Button(panel, L.MOD_TRAINER_ALL or "Aprender todo", 246, function() ConfirmLearn(Services()) end)
  allBtn:SetPoint("BOTTOM", 0, 8)
  return panel
end

function T.Refresh()
  if not Ensure() then return end
  local isProf = IsTradeskillTrainer and IsTradeskillTrainer()
  local list = Services()
  local money = GetMoney and GetMoney() or 0
  local nodes = {}
  local recCost, allCost, recN = 0, 0, 0
  for _, s in ipairs(list) do
    allCost = allCost + s.cost
    if s.rec then recCost = recCost + s.cost; recN = recN + 1 end
  end
  if isProf then
    local P = Senda.Modules.Professions
    if P and P.States then
      local ok, states = pcall(P.States)
      for _, st in ipairs(ok and states or {}) do
        if st.train then
          table.insert(nodes, { t = "row", hl = "warn", raw = true, icon = "Interface\\Icons\\INV_Misc_Book_11",
            text = string.format(L.MOD_TRAINER_PROF_RANK or "%s %d/%d: si este instructor es de %s, aprende %s ahora.",
              st.label, st.rank, st.max, st.label, st.train.name) })
        end
      end
    end
  end
  if #list == 0 then
    table.insert(nodes, { t = "p", text = L.MOD_TRAINER_NOTHING or "Nada nuevo que aprender aquí." })
  end
  -- primero lo recomendado
  table.sort(list, function(a, b)
    if a.rec ~= b.rec then return a.rec end
    return a.i < b.i
  end)
  for _, s in ipairs(list) do
    local label = s.name .. ((s.rank and s.rank ~= "") and (" |cffaaaaaa(" .. s.rank .. ")|r") or "")
    local icon
    if GetTrainerServiceIcon then local ok, ic = pcall(GetTrainerServiceIcon, s.i); if ok then icon = ic end end
    local why
    if s.prof then
      why = string.format(L.MOD_TRAINER_PROF_REC or "receta de tu ruta de %s (%d-%d)", s.prof.st.label, s.prof.seg.from, s.prof.seg.to)
    elseif s.rec then
      why = L.MOD_TRAINER_RECOMMENDED or "recomendado para tu nivel"
    end
    table.insert(nodes, { t = "row", raw = true, icon = icon, hl = s.rec and "now" or nil,
      text = label .. (why and ("\n|cffffd100" .. why .. "|r") or ""),
      right = M.Money(s.cost) })
  end
  if #list > 0 then
    table.insert(nodes, { t = "p", raw = true, text = string.format("%s: %s  ·  %s: %s",
      L.MOD_TRAINER_REC_SHORT or "Recomendado", M.Money(recCost), L.MOD_TOTAL or "Total", M.Money(allCost)) ..
      (allCost > money and ("\n|cffff8040" .. (L.MOD_TRAINER_NO_MONEY or "No te llega para todo: primero lo recomendado.") .. "|r") or "") })
  end
  doc:Set(nodes)
  recBtn:SetText(string.format("%s (%d, %s)", L.MOD_TRAINER_REC or "Aprender lo recomendado", recN, M.MoneyPlain(recCost)))
  recBtn:SetEnabled(recN > 0 and recCost <= money)
  allBtn:SetText(string.format("%s (%d, %s)", L.MOD_TRAINER_ALL or "Aprender todo", #list, M.MoneyPlain(allCost)))
  allBtn:SetEnabled(#list > 0 and allCost <= money)
  panel:SetShown(#list > 0 or #nodes > 1)

  if not announced and not isProf and #list > 0 then
    announced = true
    M.Print(string.format(L.MOD_TRAINER_CHAT or "Puedes aprender %d (%d recomendados). Total %s; llevas %s.",
      #list, recN, M.MoneyPlain(allCost), M.MoneyPlain(money)))
  end
end

M.RegisterOption({ key = "mod_trainer", label = L.MOD_OPT_TRAINER or "Ayuda en los instructores", type = "toggle", default = true })

M.On("TRAINER_SHOW", function()
  announced = false
  if M.Opt("mod_trainer") == false then if panel then panel:Hide() end return end
  M.After(0.2, T.Refresh)
end)
M.On("TRAINER_UPDATE", function() if panel and panel:IsShown() then M.Debounce("trainer-refresh", 0.3, T.Refresh) end end)
M.On("TRAINER_CLOSED", function() if panel then panel:Hide() end end)

-- Senda / Modules / Vendor
-- Al abrir un vendedor (MERCHANT_SHOW): lista de la compra junto a la ventana
--   · material de profesión que te falta para el tramo actual (si este vendedor lo tiene)
--   · componentes de la clase (opcional: páginas con [[reagent]] item, count, minlevel, maxlevel)
--   · bebida (si usas maná) y comida de tu nivel, solo si llevas poca
--   · munición si llevas arco, ballesta o arma de fuego (los lanzadores no la necesitan)
-- y venta de objetos grises (con botón o automática, según la opción). Toda compra pide confirmación.
local ADDON, Senda = ...
local M = Senda.Mod
if not M then return end
local L = M.L

local V = {}
Senda.Modules.Vendor = V

local AMMO_TARGET = 1000

------------------------------------------------------------------------
-- Vendedor
------------------------------------------------------------------------
local function MerchantItem(i)
  local id = GetMerchantItemID and GetMerchantItemID(i)
  local link = GetMerchantItemLink and GetMerchantItemLink(i)
  if not id and link then id = tonumber(link:match("item:(%d+)")) end
  local price, stack, avail
  if C_MerchantFrame and C_MerchantFrame.GetItemInfo then
    local ok, info = pcall(C_MerchantFrame.GetItemInfo, i)
    if ok and type(info) == "table" then price, stack, avail = info.price, info.stackCount, info.numAvailable end
  end
  if price == nil and GetMerchantItemInfo then
    local ok, _, _, p, q, n = pcall(GetMerchantItemInfo, i)
    if ok then price, stack, avail = p, q, n end
  end
  return id, price or 0, math.max(1, stack or 1), avail or -1, link
end

local function MerchantItems()
  local out = {}
  local n = GetMerchantNumItems and GetMerchantNumItems() or 0
  for i = 1, n do
    local id, price, stack, avail, link = MerchantItem(i)
    if id then table.insert(out, { index = i, id = id, price = price, stack = stack, avail = avail, link = link }) end
  end
  return out
end

-- "drink" | "food" | nil para un consumible (por el hechizo que lanza).
local function ConsumableKind(item)
  local _, _, classID, subID = M.ItemInstant(item)
  if classID ~= 0 or subID ~= 5 then return nil end
  local spell
  if C_Item and C_Item.GetItemSpell then
    local ok, s = pcall(C_Item.GetItemSpell, item); if ok then spell = s end
  elseif GetItemSpell then
    local ok, s = pcall(GetItemSpell, item); if ok then spell = s end
  end
  local s = tostring(spell or ""):lower()
  if s:find("beb", 1, true) or s:find("drink", 1, true) then return "drink" end
  if s:find("comida", 1, true) or s:find("food", 1, true) or s:find("comer", 1, true) then return "food" end
  if s:find("refresc", 1, true) or s:find("refreshment", 1, true) then return "drink" end
  return nil
end

local function BagCounts()
  local kinds, ammo = { drink = 0, food = 0 }, { [2] = 0, [3] = 0 }
  for _, it in ipairs(M.ScanBags()) do
    local k = ConsumableKind(it.id)
    if k then kinds[k] = kinds[k] + it.count end
    local _, _, classID, subID = M.ItemInstant(it.id)
    if classID == 6 and ammo[subID] then ammo[subID] = ammo[subID] + it.count end
  end
  return kinds, ammo
end

-- Subclase de munición que pide tu arma a distancia (2 flechas, 3 balas) o nil.
local function AmmoType()
  local link = GetInventoryItemLink and GetInventoryItemLink("player", 18)
  if not link then return nil end
  local _, _, classID, subID = M.ItemInstant(link)
  if classID ~= 2 then return nil end
  if subID == 2 or subID == 18 then return 2 end
  if subID == 3 then return 3 end
  return nil
end

------------------------------------------------------------------------
-- Plan de compra
------------------------------------------------------------------------
-- { { index, id, qty, stack, price, cost, why } }, total
function V.Plan()
  local level = M.Level()
  local items = MerchantItems()
  local byId = {}
  for _, it in ipairs(items) do byId[it.id] = byId[it.id] or it end
  local want, why = {}, {}
  local function add(id, qty, reason)
    if qty and qty > 0 and byId[id] then
      want[id] = (want[id] or 0) + qty
      why[id] = why[id] or reason
    end
  end

  -- profesiones
  local P = Senda.Modules.Professions
  if P and P.ShoppingList then
    local ok, list = pcall(P.ShoppingList)
    if ok then for id, q in pairs(list) do add(id, q, L.MOD_VENDOR_WHY_PROF or "profesión") end end
  end
  -- componentes (opcional)
  for _, p in ipairs(M.Pages()) do
    for _, r in ipairs(type(p.reagent) == "table" and p.reagent or {}) do
      if type(r) == "table" and r.item and level >= (r.minlevel or 1) and level <= (r.maxlevel or 999) then
        add(r.item, (r.count or 1) - M.ItemCount(r.item), L.MOD_VENDOR_WHY_REAGENT or "componente")
      end
    end
  end
  -- comida y bebida
  local stock = tonumber(M.Opt("mod_vendor_stock")) or 20
  if stock > 0 then
    local have = BagCounts()
    local best = {}
    for _, it in ipairs(items) do
      local k = ConsumableKind(it.id)
      if k then
        local _, _, _, _, minLevel = M.ItemInfo(it.id)
        minLevel = minLevel or 0
        if minLevel <= level and (not best[k] or minLevel > best[k].lvl) then best[k] = { id = it.id, lvl = minLevel } end
      end
    end
    local usesMana = UnitPowerType and UnitPowerType("player") == 0
    if best.drink and usesMana then add(best.drink.id, stock - have.drink, L.MOD_VENDOR_WHY_DRINK or "bebida") end
    if best.food then add(best.food.id, stock - have.food, L.MOD_VENDOR_WHY_FOOD or "comida") end
  end
  -- munición
  local ammoType = AmmoType()
  if ammoType then
    local _, ammo = BagCounts()
    local best
    for _, it in ipairs(items) do
      local _, _, classID, subID = M.ItemInstant(it.id)
      if classID == 6 and subID == ammoType then
        local _, _, _, _, minLevel = M.ItemInfo(it.id)
        minLevel = minLevel or 0
        if minLevel <= level and (not best or minLevel > best.lvl) then best = { id = it.id, lvl = minLevel } end
      end
    end
    if best then add(best.id, AMMO_TARGET - (ammo[ammoType] or 0), L.MOD_VENDOR_WHY_AMMO or "munición") end
  end

  local plan, total = {}, 0
  for id, qty in pairs(want) do
    local it = byId[id]
    local buys = math.ceil(qty / it.stack)
    local units = buys * it.stack
    if it.avail and it.avail >= 0 then units = math.min(units, it.avail * it.stack); buys = math.ceil(units / it.stack) end
    if units > 0 then
      local cost = buys * it.price
      table.insert(plan, { index = it.index, id = id, qty = units, stack = it.stack, price = it.price, cost = cost, why = why[id] })
      total = total + cost
    end
  end
  table.sort(plan, function(a, b) return a.index < b.index end)
  return plan, total
end

local function BuyPlan(plan)
  if not BuyMerchantItem then return end
  for _, b in ipairs(plan) do
    local left = b.qty
    local max = (GetMerchantItemMaxStack and GetMerchantItemMaxStack(b.index)) or 20
    if not max or max < 1 then max = 1 end
    while left > 0 do
      local q = math.min(left, max)
      pcall(BuyMerchantItem, b.index, q)
      left = left - q
    end
  end
  M.Print(L.MOD_VENDOR_BOUGHT or "Comprado.")
end

------------------------------------------------------------------------
-- Grises
------------------------------------------------------------------------
local function Greys()
  local list, value = {}, 0
  for _, it in ipairs(M.ScanBags()) do
    if it.quality == 0 and not it.noValue and not it.locked then
      local price = select(11, M.ItemInfo(it.link or it.id)) or 0
      if price > 0 then
        table.insert(list, it)
        value = value + price * it.count
      end
    end
  end
  return list, value
end

local selling = false
local function SellGreys()
  if selling then return end
  local list, value = Greys()
  if #list == 0 then return end
  local use = (C_Container and C_Container.UseContainerItem) or _G.UseContainerItem
  if not use then return end
  selling = true
  local i = 1
  local function step()
    if not (MerchantFrame and MerchantFrame:IsShown()) or M.InCombat() then selling = false; return end
    for _ = 1, 10 do
      local it = list[i]
      if not it then
        selling = false
        M.Print(string.format(L.MOD_VENDOR_SOLD or "Vendidos %d objetos grises por %s.", #list, M.Money(value)))
        return
      end
      pcall(use, it.bag, it.slot)
      i = i + 1
    end
    M.After(0.2, step)
  end
  step()
end
V.SellGreys = SellGreys

------------------------------------------------------------------------
-- Panel junto a la ventana del vendedor
------------------------------------------------------------------------
local panel, doc, buyBtn, sellBtn

local function Ensure()
  if panel or not MerchantFrame then return panel end
  panel = M.Frame(MerchantFrame, "SendaVendorPanel")
  panel:SetSize(260, 300)
  panel:SetPoint("TOPLEFT", MerchantFrame, "TOPRIGHT", 4, -30)
  local title = panel:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  title:SetPoint("TOPLEFT", 10, -8)
  title:SetText("Senda: " .. (L.MOD_VENDOR_TITLE or "lista de la compra"))
  local holder = CreateFrame("Frame", nil, panel)
  holder:SetPoint("TOPLEFT", 4, -24)
  holder:SetPoint("BOTTOMRIGHT", -4, 60)
  doc = M.Doc(holder)
  buyBtn = M.Button(panel, L.MOD_VENDOR_BUY or "Comprar", 236, function()
    local plan, total = V.Plan()
    if #plan == 0 then return end
    local lines = {}
    for _, b in ipairs(plan) do table.insert(lines, b.qty .. " x " .. (M.ItemName(b.id) or ("#" .. b.id))) end
    M.Confirm("Senda: " .. (L.MOD_VENDOR_CONFIRM or "¿Comprar esto?") .. "\n\n" .. table.concat(lines, "\n") ..
      "\n\n" .. (L.MOD_TOTAL or "Total") .. ": " .. M.MoneyPlain(total), function() BuyPlan(plan); M.After(0.5, V.Refresh) end,
      L.MOD_VENDOR_BUY or "Comprar")
  end)
  buyBtn:SetPoint("BOTTOM", 0, 34)
  sellBtn = M.Button(panel, L.MOD_VENDOR_SELL or "Vender grises", 236, function() SellGreys(); M.After(1.5, V.Refresh) end)
  sellBtn:SetPoint("BOTTOM", 0, 8)
  return panel
end

function V.Refresh()
  if not Ensure() then return end
  local plan, total = V.Plan()

  local greys, gv = Greys()
  if #plan == 0 and #greys == 0 then panel:Hide(); return end
  local nodes = {}
  if #plan == 0 then
    table.insert(nodes, { t = "p", text = L.MOD_VENDOR_NOTHING or "Nada que comprar aquí." })
  end
  for _, b in ipairs(plan) do
    table.insert(nodes, { t = "row", raw = true, item = b.id, icon = M.ItemIcon(b.id),
      text = string.format("%d x %s\n|cffaaaaaa%s|r", b.qty, M.ItemName(b.id) or ("#" .. b.id), b.why or ""),
      right = M.Money(b.cost) })
  end
  local money = GetMoney and GetMoney() or 0
  if #plan > 0 then
    table.insert(nodes, { t = "p", raw = true, text = (L.MOD_TOTAL or "Total") .. ": " .. M.Money(total) ..
      (total > money and ("\n|cffff8040" .. (L.MOD_VENDOR_NO_MONEY or "No te llega para todo.") .. "|r") or "") })
  end
  doc:Set(nodes)
  buyBtn:SetText(string.format("%s (%s)", L.MOD_VENDOR_BUY or "Comprar", M.MoneyPlain(total)))
  buyBtn:SetEnabled(#plan > 0)
  sellBtn:SetText(string.format("%s: %d (%s)", L.MOD_VENDOR_SELL or "Vender grises", #greys, M.MoneyPlain(gv)))
  sellBtn:SetEnabled(#greys > 0 and not selling)
  panel:Show()
end

local function OnShow()
  if M.Opt("mod_vendor") == false then if panel then panel:Hide() end return end
  if M.Opt("mod_vendor_autosell") then SellGreys() end
  M.After(0.3, V.Refresh)
end

M.RegisterOption({ key = "mod_vendor", label = L.MOD_OPT_VENDOR or "Lista de la compra en los vendedores", type = "toggle", default = true })
M.RegisterOption({ key = "mod_vendor_autosell", label = L.MOD_OPT_AUTOSELL or "Vender los objetos grises automáticamente", type = "toggle", default = false })
M.RegisterOption({ key = "mod_vendor_stock", label = L.MOD_OPT_STOCK or "Comida y bebida que llevar (0 = no comprar)", type = "slider",
  default = 20, min = 0, max = 60 })

M.On("MERCHANT_SHOW", function() pcall(OnShow) end)
M.On("MERCHANT_CLOSED", function() if panel then panel:Hide() end; selling = false end)
M.On("MERCHANT_UPDATE", function() if panel and panel:IsShown() then M.Debounce("vendor-refresh", 0.3, V.Refresh) end end)
M.On("BAG_UPDATE_DELAYED", function() if panel and panel:IsShown() then M.Debounce("vendor-refresh", 0.3, V.Refresh) end end)

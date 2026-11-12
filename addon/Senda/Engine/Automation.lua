-- Automatización de misiones: acepta y entrega las que el paso actual de la guía pide.
--   Senda.Engine:WantsQuest("accept"|"turnin", questID) -> true si la guía quiere esa acción ahora
-- Reglas: solo misiones que la guía lista (el paso actual y los próximos AHEAD pasos al aceptar; solo el
-- paso actual y su cadena al entregar); con Mayús pulsado no hace nada; nunca en combate; si la entrega
-- tiene varias recompensas a elegir, deja la ventana abierta (el asesor de equipo ayuda a elegir); no
-- acepta las que cuestan dinero ni las que piden confirmar el PvP.
-- Adaptado de Polestar, Core/Automation.lua (ventanas de misión, saludo y diálogo de PNJ con C_GossipInfo).
local _, Senda = ...
local Compat, Events = Senda.Compat, Senda.Events
local Engine = Senda.Engine
local Cond = Senda.Conditions
local L = Senda.L

local Automation = {}
Senda.Automation = Automation

local AHEAD = 6 -- pasos pendientes por delante en los que se acepta

local function HasQuest(step, q)
  for _, x in ipairs(Cond:Quests(step) or {}) do
    if x == q then return true end
  end
  return false
end

function Engine:WantsQuest(kind, q)
  q = Compat.Num(q)
  if not (self.guideId and q and q ~= 0) then return false end
  local cur = self.steps[self.index]
  if not cur then return false end
  if kind == "turnin" then
    -- El paso actual y los de su cadena (entregar A y coger B en el mismo PNJ). Si el actual es solo
    -- "ve a" (llegar al PNJ), también el siguiente pendiente.
    local base = { cur }
    if cur.step["do"] == "goto" then
      local nxt = self.steps[self:NextPending(self.index + 1)]
      if nxt then base[#base + 1] = nxt end
    end
    for _, b in ipairs(base) do
      local chain = b.step.chain
      for _, e in ipairs(self.steps) do
        if e == b or (chain and e.step.chain == chain and not self:IsMarked(e)) then
          if e.step["do"] == "turnin" and HasQuest(e.step, q) and self:IsApplicable(e) then return true end
        end
      end
    end
    return false
  elseif kind == "accept" then
    if Compat.IsOnQuest(q) or Compat.IsQuestDone(q) or self.turnedIn[q] then return false end
    -- Una fallida o abandonada que la guía quiere recuperar.
    local pr = self:Problem()
    if pr and pr.quest == q and pr.kind == "abandoned" then return true end
    local seen = 0
    for i = self.index, #self.steps do
      local e = self.steps[i]
      if not self:IsMarked(e) and self:IsApplicable(e) then
        if e.step["do"] == "accept" and HasQuest(e.step, q) then return true end
        seen = seen + 1
        if seen > AHEAD then break end
      end
    end
  end
  return false
end

local function Enabled()
  return Senda.Options:Get("autoQuests") and not Compat.ShiftDown() and not Compat.InCombat()
end

local function QuestId()
  return _G.GetQuestID and Compat.Num(Compat.Try(_G.GetQuestID)) or nil
end

local function WantsTurnIn(q)
  return q and Compat.IsOnQuest(q) and Engine:WantsQuest("turnin", q)
end

local function OnDetail()
  if not Enabled() then return end
  local q = QuestId()
  if not (q and Engine:WantsQuest("accept", q)) then return end
  if _G.QuestFlagsPVP and Compat.Try(_G.QuestFlagsPVP) then return end -- pide confirmar el PvP
  if _G.QuestGetAutoAccept and Compat.Try(_G.QuestGetAutoAccept) then
    if _G.AcknowledgeAutoAcceptQuest then pcall(_G.AcknowledgeAutoAcceptQuest) end
  elseif _G.AcceptQuest then
    pcall(_G.AcceptQuest)
  end
  Senda:Debug("Auto: aceptada %s", tostring(q))
end

local function OnProgress()
  if not Enabled() then return end
  local q = QuestId()
  if not WantsTurnIn(q) then return end
  if _G.IsQuestCompletable and Compat.Try(_G.IsQuestCompletable) and _G.CompleteQuest then
    pcall(_G.CompleteQuest)
  end
end

local function OnComplete()
  if not Enabled() then return end
  local q = QuestId()
  if not WantsTurnIn(q) then return end
  local choices = _G.GetNumQuestChoices and Compat.Num(Compat.Try(_G.GetNumQuestChoices)) or 0
  if choices > 1 then return end -- con recompensa a elegir decide el jugador
  local money = _G.GetQuestMoneyToGet and Compat.Num(Compat.Try(_G.GetQuestMoneyToGet)) or 0
  if money > 0 then return end   -- cuesta dinero: lo confirma el jugador
  if _G.GetQuestReward then
    pcall(_G.GetQuestReward, choices == 1 and 1 or 0)
    Senda:Debug("Auto: entregada %s", tostring(q))
  end
end

-- Saludo de varias misiones (PNJ u objeto): primero las entregas, que suelen abrir la siguiente.
local function OnGreeting()
  if not Enabled() then return end
  local numActive = _G.GetNumActiveQuests and Compat.Num(Compat.Try(_G.GetNumActiveQuests)) or 0
  if _G.GetActiveTitle and _G.GetActiveQuestID and _G.SelectActiveQuest then
    for i = 1, numActive do
      local _, isComplete = Compat.Try(_G.GetActiveTitle, i)
      if isComplete and WantsTurnIn(Compat.Num(Compat.Try(_G.GetActiveQuestID, i))) then
        pcall(_G.SelectActiveQuest, i)
        return
      end
    end
  end
  local numAvailable = _G.GetNumAvailableQuests and Compat.Num(Compat.Try(_G.GetNumAvailableQuests)) or 0
  if _G.GetAvailableQuestInfo and _G.SelectAvailableQuest then
    for i = 1, numAvailable do
      local _, _, _, _, id = Compat.Try(_G.GetAvailableQuestInfo, i)
      if Engine:WantsQuest("accept", id) then
        pcall(_G.SelectAvailableQuest, i)
        return
      end
    end
  end
end

-- Diálogo de PNJ con misiones (C_GossipInfo se selecciona por id de misión).
local function OnGossip()
  if not Enabled() then return end
  local G = _G.C_GossipInfo
  if not G then return end
  if G.GetActiveQuests and G.SelectActiveQuest then
    for _, info in ipairs(Compat.Try(G.GetActiveQuests) or {}) do
      if info.isComplete and WantsTurnIn(Compat.Num(info.questID)) then
        pcall(G.SelectActiveQuest, info.questID)
        return
      end
    end
  end
  if G.GetAvailableQuests and G.SelectAvailableQuest then
    for _, info in ipairs(Compat.Try(G.GetAvailableQuests) or {}) do
      if Engine:WantsQuest("accept", Compat.Num(info.questID)) then
        pcall(G.SelectAvailableQuest, info.questID)
        return
      end
    end
  end
end

Automation.OnDetail, Automation.OnProgress, Automation.OnComplete = OnDetail, OnProgress, OnComplete
Automation.OnGreeting, Automation.OnGossip = OnGreeting, OnGossip

Senda.Options:Register({ key = "autoQuests", label = L.OPT_AUTO_QUESTS, tooltip = L.OPT_AUTO_QUESTS_TIP,
  type = "toggle", default = true, section = L.OPT_SECTION_QUESTS, order = 10 })

Events:On("SENDA_READY", function()
  Events:On("QUEST_DETAIL", OnDetail)
  Events:On("QUEST_PROGRESS", OnProgress)
  Events:On("QUEST_COMPLETE", OnComplete)
  Events:On("QUEST_GREETING", OnGreeting)
  Events:On("GOSSIP_SHOW", OnGossip)
end)

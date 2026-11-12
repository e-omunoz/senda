-- Registro de guías y secciones.
--   Senda.Guides:RegisterSection(t)  -- { id, title, levels = {a, b}, map, summary, link, ["if"], steps = {...} }
--   Senda.Guides:RegisterGuide(t)    -- { id, title, faction, races, classes, sections = { "id" | "shared:id", ... } }
--   Senda.Guides:Get(id), :GetSection(id), :AllSections(), :List(), :ForPlayer()
--   Senda.Guides:Resolve(guideId) -> lista plana de entradas { step, section, secIndex, index }
--   Senda.Guides:RegisterFollowups(texto), :Followups(questId) -> lista de misiones que dependen de ella
-- Las secciones pueden registrarse antes o después que las guías: se resuelven tarde.
local _, Senda = ...
local Util, Compat = Senda.Util, Senda.Compat

local Guides = {}
Senda.Guides = Guides

local guides, guideOrder = {}, {}
local sections = {}
local stepIndex = {} -- stepId -> step (para Engine:Complete(stepId) y depuración)

local function SectionKey(id)
  if type(id) ~= "string" then return id end
  return (id:gsub("^shared:", ""))
end

function Guides:RegisterSection(t)
  if type(t) ~= "table" or type(t.id) ~= "string" then return end
  t.steps = t.steps or t.step or {}
  for _, s in ipairs(t.steps) do
    if type(s) == "table" and s.id then
      if stepIndex[s.id] and stepIndex[s.id] ~= s then
        Senda:Debug("Id de paso duplicado: %s", s.id)
      end
      stepIndex[s.id] = s
    end
  end
  sections[t.id] = t
end

function Guides:RegisterGuide(t)
  if type(t) ~= "table" or type(t.id) ~= "string" then return end
  if not guides[t.id] then guideOrder[#guideOrder + 1] = t.id end
  t.sections = t.sections or {}
  guides[t.id] = t
  if Senda.ready then Senda.Events:Fire("SENDA_GUIDES_UPDATED") end
end

function Guides:Get(id) return id and guides[id] end
function Guides:GetSection(id) return id and sections[SectionKey(id)] end
function Guides:GetStep(id) return id and stepIndex[id] end

-- Índice de dependencias entre misiones (lo genera tools/build.py en Guides/Followups.lua):
-- cadena "q>d1,d2;q>d1" con, para cada misión de las guías, todas las que dependen de ella (cierre
-- transitivo). Se lee una sola vez, en el primer uso.
local followupText, followups = nil, nil

function Guides:RegisterFollowups(text)
  followupText = type(text) == "string" and text or nil
  followups = nil
end

function Guides:Followups(q)
  if not followups then
    followups = {}
    for entry in (followupText or ""):gmatch("[^;]+") do
      local id, list = entry:match("^(%d+)>(.+)$")
      if id then
        local t = {}
        for d in list:gmatch("%d+") do t[#t + 1] = tonumber(d) end
        followups[tonumber(id)] = t
      end
    end
  end
  return followups[q]
end

-- Todas las secciones registradas, en orden de id (las recorre /senda volcar).
function Guides:AllSections()
  local out = {}
  for _, sec in pairs(sections) do out[#out + 1] = sec end
  table.sort(out, function(a, b) return a.id < b.id end)
  return out
end

function Guides:List()
  local out = {}
  for _, id in ipairs(guideOrder) do out[#out + 1] = guides[id] end
  return out
end

-- ¿Puede este jugador usar la guía? Devuelve una puntuación (0 = no) para elegir la mejor.
function Guides:Score(g)
  if not g then return 0 end
  local race, class, faction = Compat.PlayerRace(), Compat.PlayerClass(), Compat.PlayerFaction()
  if g.faction and faction and g.faction ~= faction then return 0 end
  local score = 1
  if g.races and #g.races > 0 then
    if not Util.Contains(g.races, race) then return 0 end
    score = score + 2
  end
  if g.classes and #g.classes > 0 then
    if not Util.Contains(g.classes, class) then return 0 end
    score = score + 4
  end
  return score
end

-- Guía solo a mano (`order` negativo en guide.toml, p. ej. un prototipo importado): sale en la lista y se
-- puede elegir con /senda guide <id>, pero la elección automática nunca la coge.
function Guides:IsManualOnly(g)
  return type(g) == "table" and type(g.order) == "number" and g.order < 0
end

-- Guías válidas para el jugador, de mejor a peor (las de solo a mano, al final).
function Guides:ForPlayer()
  local out = {}
  for i, id in ipairs(guideOrder) do
    local s = self:Score(guides[id])
    if s > 0 then out[#out + 1] = { g = guides[id], s = s, i = i, m = self:IsManualOnly(guides[id]) } end
  end
  table.sort(out, function(a, b)
    if a.m ~= b.m then return not a.m end
    if a.s ~= b.s then return a.s > b.s end
    return a.i < b.i
  end)
  for i, e in ipairs(out) do out[i] = e.g end
  return out
end

-- Secciones (tablas) de una guía, en orden, ignorando las que falten.
function Guides:SectionsOf(guideId)
  local g = guides[guideId]
  local out = {}
  if not g then return out end
  for _, sid in ipairs(g.sections) do
    local sec = sections[SectionKey(sid)]
    if sec then
      out[#out + 1] = sec
    else
      Senda:Debug("Sección no encontrada: %s (guía %s)", tostring(sid), guideId)
    end
  end
  return out
end

-- Lista plana de pasos aplicables (filtros estáticos: clase, raza, facción, profesión).
-- Los filtros de nivel son dinámicos y los evalúa el motor al avanzar.
function Guides:Resolve(guideId)
  local Cond = Senda.Conditions
  local flat = {}
  for secIndex, sec in ipairs(self:SectionsOf(guideId)) do
    if Cond:StaticFilter(sec["if"]) then
      for _, s in ipairs(sec.steps) do
        if type(s) == "table" and s.id and Cond:StaticFilter(s["if"]) then
          flat[#flat + 1] = { step = s, section = sec, secIndex = secIndex, index = #flat + 1 }
        end
      end
    end
  end
  return flat
end

-- Registro mínimo de páginas de conocimiento (Knowledge/ lo genera tools/build.py).
--   Senda.Knowledge:Register(t), :ForClass(class) -> lista ordenada, :Get(id), :All()
-- Los paneles que las muestran los aportan otros módulos; aquí solo se guardan los datos.
-- Si otro archivo ya definió estos métodos, se respetan.
local _, Senda = ...

local K = Senda.Knowledge or {}
Senda.Knowledge = K
K.pages = K.pages or {}

local function ByOrder(a, b)
  local oa, ob = a.order or 1000, b.order or 1000
  if oa ~= ob then return oa < ob end
  return tostring(a.id) < tostring(b.id)
end

if not K.Register then
  function K:Register(t)
    if type(t) ~= "table" or not t.id then return end
    self.pages[t.id] = t
    if Senda.ready then Senda.Events:Fire("SENDA_KNOWLEDGE_UPDATED", t.id) end
  end
end

if not K.Get then
  function K:Get(id) return self.pages[id] end
end

if not K.All then
  function K:All()
    local out = {}
    for _, p in pairs(self.pages) do out[#out + 1] = p end
    table.sort(out, ByOrder)
    return out
  end
end

if not K.ForClass then
  function K:ForClass(class)
    local out = {}
    for _, p in pairs(self.pages) do
      if p.class == nil or p.class == "ANY" or p.class == class then out[#out + 1] = p end
    end
    table.sort(out, ByOrder)
    return out
  end
end

-- Base de datos guardada (SendaDB por personaje, SendaRecorderDB por cuenta), esquema versionado
-- y arranque del addon:
--   ADDON_LOADED  -> SendaDB listo (migraciones + valores por defecto)
--   PLAYER_LOGIN  -> se lanza "SENDA_READY" (el motor, la UI y los módulos se inicializan ahí)
local ADDON, Senda = ...
local Util = Senda.Util

local SCHEMA = 1

-- Valores por defecto de SendaDB. Las opciones registradas con Senda.Options:Register añaden los suyos.
local DEFAULTS = {
  schema = SCHEMA,
  opts = {},          -- opciones (clave -> valor)
  guide = nil,        -- id de la guía activa
  progress = {},      -- [guideId] = { done = { [stepId] = "a"|"d"|"s" }, current = stepId, index = n }
  frames = {},        -- posiciones de marcos: [nombre] = { point, relPoint, x, y }
  minimapAngle = 215,
  hudCollapsed = false,
  skippedQuests = {}, -- [questId] = true: misiones saltadas con "Saltar esta misión" (valen para todas las guías)
  modules = {},       -- datos persistentes de los módulos (Modules/)
  char = {
    fps = {},         -- nodos de vuelo conocidos: [nodeID] = nombre
    wps = {},         -- punto de ruta de la flecha por paso: [stepId] = { i = índice, n = orden } (UI/Arrow.lua)
  },
}

-- Migraciones: MIGRATIONS[n] convierte un esquema n-1 en n.
local MIGRATIONS = {
  -- [2] = function(db) ... end,
}

local function Migrate(db)
  local from = tonumber(db.schema) or 0
  if from == 0 then
    db.schema = SCHEMA
    return
  end
  for v = from + 1, SCHEMA do
    local m = MIGRATIONS[v]
    if m then
      local ok, err = pcall(m, db)
      if not ok then Senda:Print("Migración %d fallida: %s", v, tostring(err)) end
    end
    db.schema = v
  end
end

local function InitDB()
  if type(SendaDB) ~= "table" then SendaDB = {} end
  Migrate(SendaDB)
  Util.Merge(SendaDB, DEFAULTS)
  Senda.db = SendaDB

  if type(SendaRecorderDB) ~= "table" then SendaRecorderDB = {} end
  Senda.recorder = SendaRecorderDB

  -- Valores por defecto de las opciones registradas antes de tener la base de datos.
  if Senda.Options and Senda.Options.ApplyDefaults then Senda.Options:ApplyDefaults() end
end

-- Guarda / restaura la posición de un marco por nombre.
function Senda:SaveFramePos(frame, key)
  if not self.db or not frame then return end
  local point, _, relPoint, x, y = frame:GetPoint(1)
  if point then self.db.frames[key] = { point, relPoint, x, y } end
end

function Senda:RestoreFramePos(frame, key, defPoint, defRel, defX, defY)
  frame:ClearAllPoints()
  local p = self.db and self.db.frames[key]
  if type(p) == "table" and p[1] then
    local ok = pcall(frame.SetPoint, frame, p[1], UIParent, p[2] or p[1], p[3] or 0, p[4] or 0)
    if ok then return end
  end
  frame:SetPoint(defPoint or "CENTER", UIParent, defRel or defPoint or "CENTER", defX or 0, defY or 0)
end

-- Progreso de una guía (se crea si no existe).
function Senda:GuideProgress(guideId)
  local db = self.db
  if not db or not guideId then return nil end
  local p = db.progress[guideId]
  if type(p) ~= "table" then
    p = { done = {} }
    db.progress[guideId] = p
  end
  p.done = p.done or {}
  return p
end

Senda.Events:On("ADDON_LOADED", function(_, name)
  if name ~= ADDON then return end
  InitDB()
  Senda.Events:Fire("SENDA_DB_LOADED")
end)

Senda.Events:On("PLAYER_LOGIN", function()
  if not Senda.db then InitDB() end
  Senda.ready = true
  Senda.Events:Fire("SENDA_READY")
end)

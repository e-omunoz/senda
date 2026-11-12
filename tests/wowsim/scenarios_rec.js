'use strict';
// Scenarios of the session recorder (addon/Senda/Recorder/Session.lua) and its measurement pipeline
// (tools/ingest_recording.py). Loaded by run.js. `post(report, carry, ctx)` runs after the Lua part in node:
// it feeds the SavedVariables the sim produced to the real ingest tool and checks the numbers.

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const L_ = String.raw;
const ROOT = path.resolve(__dirname, '..', '..');

function ingest(saved) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'senda-rec-'));
  const sv = path.join(dir, 'Senda.lua');
  fs.writeFileSync(sv, saved, 'utf8');
  const py = process.env.PYTHON || 'python';
  const r = spawnSync(py, [path.join(ROOT, 'tools', 'ingest_recording.py'), sv, '--stdout'], { encoding: 'utf8' });
  fs.rmSync(dir, { recursive: true, force: true });
  if (r.error) return { skipped: String(r.error) };
  if (r.status !== 0) return { error: (r.stderr || '') + (r.stdout || '') };
  return { doc: JSON.parse(r.stdout) };
}

function approx(a, b, tol) {
  return typeof a === 'number' && Math.abs(a - b) <= tol;
}

const scenarios = [
  {
    id: 'rec1',
    title: 'Session recorder: off by default; scripted session (walk, AFK gap, combat, death, XP) then logout',
    char: 'gnome-warlock',
    lua: L_`
      Login()
      local E, p = S().Engine, Sim.player
      Check(S().Session ~= nil and not S().Session:IsRunning(), "recording is off by default")
      Check(S().recorder.chunks == nil or next(S().recorder.chunks) == nil, "nothing recorded while off")
      Sim.Advance(5)
      E:Advance(); Sim.Advance(1)
      Check(S().recorder.chunks == nil or next(S().recorder.chunks) == nil, "stepping while off records nothing")
      E:JumpTo(1); Sim.Advance(1)
      local stepA = StepId()
      Check(S().Options:Get("recordSession") == false, "option recordSession defaults to false")
      Slash("grabar")
      Slash("grabar rastro off"); Slash("grabar rastro on")

      Section("start (relative t = 0)")
      p.name = "Zyxwvut"; p.realm = "Reino-Zyx"
      p.map, p.x, p.y = 1426, 0.300, 0.715
      local T0 = Sim.time
      S().Options:Set("recordSession", true)  -- same as /senda grabar on
      Check(S().Session:IsRunning(), "recording starts when the option is turned on")
      Sim.Advance(5)
      p.xp = 60; Sim.Fire("PLAYER_XP_UPDATE", "player")
      Sim.Advance(5)                          -- t = 10
      E:Advance()                             -- next
      local stepB = StepId()
      Check(stepB ~= stepA, "step B differs from step A", stepB)
      Section("B: walk 20 s east, AFK 10 min, combat, death")
      local x0 = p.x
      for i = 1, 20 do p.x = x0 + 0.0015 * i; Sim.Advance(1) end   -- t = 30, 29.6 yd per 4 s... straight line
      local yardsWalked = 0.0015 * 20 * 4925
      p.afk = true; Sim.Fire("PLAYER_FLAGS_CHANGED", "player")
      Sim.Advance(600)                        -- t = 630
      p.afk = false; Sim.Fire("PLAYER_FLAGS_CHANGED", "player")
      p.combat = true; Sim.Fire("PLAYER_REGEN_DISABLED")
      Sim.Advance(10)                         -- t = 640
      p.combat = false; Sim.Fire("PLAYER_REGEN_ENABLED")
      Sim.Fire("PLAYER_DEAD")
      Sim.Advance(5)                          -- t = 645
      E:Advance()                             -- next
      local stepC = StepId()
      Sim.party[1] = { name = "Wqplmok", class = "MAGE", level = 1, quests = {} }
      Sim.Fire("GROUP_ROSTER_UPDATE")         -- duo from here on (step C)
      Section("C: level up, then 395 s of nothing and logout")
      Sim.Advance(5)                          -- t = 650
      p.level = 2; p.xp = 30; p.xpMax = 900
      Sim.Fire("PLAYER_LEVEL_UP", 2, 0, 0, 0, 0, 0, 0, 0, 0)
      Sim.Fire("PLAYER_XP_UPDATE", "player")
      Sim.Advance(395)                        -- t = 1045
      local before = Sim.time - T0
      Sim.Fire("PLAYER_LOGOUT")
      Check(not S().Session:IsRunning(), "logout closes the session")
      local n, bytes = S().Session:Stats()
      Check(n >= 1 and bytes > 0, "chunks stored: " .. n .. " (" .. bytes .. " bytes)")
      local dump = {}
      for _, k in ipairs((function() local t = {} for q in pairs(S().recorder.chunks) do t[#t + 1] = q end table.sort(t) return t end)()) do
        dump[#dump + 1] = S().recorder.chunks[k]
      end
      Sim.Out("    " .. table.concat(dump, "\n    "):gsub("\t", " "))
      __report("stepA", stepA); __report("stepB", stepB); __report("stepC", stepC)
      __report("elapsed", before)
      __report("expectStep", StepId())
      __report("yards", yardsWalked)
      __report("saved", Sim.SaveVariables())
      __report("world", Sim.ExportWorld())
    `,
  },
  {
    id: 'rec2',
    title: 'Session recorder: /reload continues the step pass; ingest gives the exact step times',
    char: 'gnome-warlock',
    needs: 'rec1',
    lua: L_`
      Sim.time = Sim.time + 5000   -- a later play session
      Login()
      local E, p = S().Engine, Sim.player
      Check(S().Session:IsRunning(), "recording resumes after the reload (option saved)")
      Check(StepId() == SIM_EXPECT_STEP, "step restored", tostring(StepId()))
      p.name = "Zyxwvut"
      Sim.Advance(14)                        -- Login already advanced 6 s: t = 20 in this session
      local stepC = StepId()
      E:Advance()                            -- next: ends the pass of C that began before the reload
      Sim.Advance(10)
      Sim.AcceptQuest(179, { { "Carne", 8 } })
      Sim.Advance(2)
      Sim.FinishQuestObjectives(179)
      Sim.Advance(2)
      Sim.TurnInQuest(179)
      Sim.Advance(3)
      Sim.Fire("PLAYER_LOGOUT")
      __report("stepC2", stepC)
      __report("saved", Sim.SaveVariables())
    `,
    post(report, carry, ctx) {
      const r1 = carry.rec1 || {};
      const res = ingest(report.saved);
      if (res.skipped) return { warn: 'python not available: ' + res.skipped };
      const out = [];
      if (res.error) return { fail: ['ingest failed: ' + res.error.trim()] };
      const d = res.doc;
      ctx.check(d.schema === 2 && d.sessions.length === 2, 'ingest finds the 2 sessions (login and reload)', JSON.stringify(d.stats));
      ctx.check(d.stats.bad_records === 0, 'no rejected records', JSON.stringify(d.stats));
      const byStep = {};
      for (const p of d.passes) (byStep[p.step] = byStep[p.step] || []).push(p);
      const A = (byStep[r1.stepA] || [])[0];
      const B = (byStep[r1.stepB] || [])[0];
      const C = (byStep[r1.stepC] || [])[0];
      ctx.check(A && A.partial && approx(A.time, 10, 0.05) && A.xp === 60 && A.left === 'next', 'step A: 10.0 s, 60 XP, partial (entry unseen), left by next', JSON.stringify(A));
      ctx.check(B && !B.partial && B.completed && approx(B.time, 35, 0.05), 'step B: 35.0 s active (20 walking + 15; the 600 s AFK counts zero)', JSON.stringify(B));
      ctx.check(B && approx(B.combat, 10, 0.05) && approx(B.afk, 600, 0.05) && B.deaths === 1, 'step B: 10.0 s combat, 600 s AFK, 1 death', JSON.stringify(B));
      ctx.check(B && approx(B.yards, r1.yards, 12) && B.yards > 100, 'step B: yards walked ~' + Math.round(r1.yards), String(B && B.yards));
      ctx.check(B && B.duo === false && C && C.duo === true, 'duo yes/no flag: off in step B, on in step C');
      ctx.check(C && C.completed && C.xp === 370 && approx(C.idle, 95, 0.05), 'step C: level-up XP counted across levels (370), idle 95 s', JSON.stringify(C));
      ctx.check(C && approx(C.time, 325, 0.05), 'step C: 5 + 300 (idle gap capped at 5 min) before the reload + 20 s after = 325.0 s (the reload continues the pass)', JSON.stringify(C));
      ctx.check(C && C.segments === 2 && !C.partial, 'step C: one pass over two sessions (reload), not partial', JSON.stringify(C));
      const s1 = d.sessions[0];
      ctx.check(s1.deaths === 1 && s1.duo === true && s1.xp === 430, 'session 1: 1 death, duo yes/no flag set, 430 XP', JSON.stringify({ d: s1.deaths, duo: s1.duo, xp: s1.xp }));
      ctx.check(approx(s1.active, 350, 0.05), 'session 1 active time = 10 + 35 + 305', String(s1.active));
      ctx.check(s1.xp_per_hour === Math.round(430 * 3600 / 350), 'session 1 XP/hour', String(s1.xp_per_hour));
      const s2 = d.sessions[1];
      ctx.check(s2.accepts === 1 && s2.completes === 1 && s2.turnins === 1, 'session 2: quest accept / complete / turn-in', JSON.stringify(s2));
      const text = JSON.stringify(d);
      for (const bad of ['Zyxwvut', 'Reino', 'Wqplmok', 'Pruebas']) {
        ctx.check(!text.includes(bad), 'ingested document has no "' + bad + '"');
      }
    },
  },
  {
    id: 'recpriv',
    title: 'Privacy: no character, realm, group member or NPC name ever reaches the saved data',
    char: 'gnome-warlock',
    lua: L_`
      Login()
      local E, p = S().Engine, Sim.player
      local secrets = { "Qzxvbnm", "Realm-Plkjhg", "Mnbvcxz", "Npcname-Asdfgh" }
      p.name, p.realm = secrets[1], secrets[2]
      Sim.party[1] = { name = secrets[3], class = "MAGE", level = 1, quests = {} }
      Sim.npc = { id = 658, name = secrets[4] }
      S().Options:Set("recordSession", true)
      Sim.Fire("GROUP_ROSTER_UPDATE")
      Sim.Advance(3)
      Sim.AcceptQuest(179, { { "Carne", 8 } })
      Sim.Advance(2)
      p.xp = 10; Sim.Fire("PLAYER_XP_UPDATE", "player")
      Sim.Fire("PLAYER_REGEN_DISABLED"); Sim.Advance(2); Sim.Fire("PLAYER_REGEN_ENABLED")
      Sim.Fire("CHAT_MSG_WHISPER", "hola " .. secrets[1], secrets[3])
      Sim.Fire("CHAT_MSG_PARTY", "mensaje de " .. secrets[3], secrets[3])
      E:Advance(); Sim.Advance(2)
      Sim.Fire("PLAYER_LOGOUT")
      local all = Sim.SaveVariables()
      local n = 0
      for _ = 1, 1 do n = S().Session:Stats() end
      Check(n >= 1, "something was recorded (" .. n .. " chunks)")
      for _, s in ipairs(secrets) do
        Check(not all:find(s, 1, true), "saved data has no \"" .. s .. "\"")
      end
      local rec = Sim.Serialize(SendaRecorderDB)
      Check(not rec:find("Reino", 1, true) and not rec:find("Pruebas", 1, true), "no realm text in SendaRecorderDB")
      Check(S().recorder.chunks and next(S().recorder.chunks) ~= nil, "chunks exist")
      -- the char id is random, not derived from the name
      Check(SendaDB.recId and not SendaDB.recId:lower():find("qzxvbnm", 1, true), "character id is random")
      __report("saved", all)
    `,
    post(report, carry, ctx) {
      const res = ingest(report.saved);
      if (res.skipped) return { warn: 'python not available: ' + res.skipped };
      if (res.error) return { fail: ['ingest failed: ' + res.error.trim()] };
      const text = JSON.stringify(res.doc);
      for (const bad of ['Qzxvbnm', 'Realm-Plkjhg', 'Mnbvcxz', 'Npcname-Asdfgh']) {
        ctx.check(!text.includes(bad), 'ingested document has no "' + bad + '"');
      }
    },
  },
  {
    id: 'reccap',
    title: 'Session recorder: size cap drops the oldest chunks; trail stops after 30 min idle and resumes; option off stops it',
    char: 'gnome-warlock',
    lua: L_`
      Login()
      local p = Sim.player
      local db = S().recorder
      db.chunks = {}
      for i = 1, 5 do db.chunks[i] = string.rep("x", 1024 * 1024) end  -- 5 MiB of old chunks
      db.seq = 5
      p.map, p.x, p.y = 1426, 0.30, 0.70
      S().Options:Set("recordSession", true)
      Sim.Advance(70)                       -- a refresh (60 s) trims
      local total = 0
      for _, s in pairs(db.chunks) do total = total + #s end
      Check(total <= 4 * 1024 * 1024, "stored chunks fit the 4 MiB cap", total)
      Check(db.chunks[1] == nil and db.chunks[6] ~= nil, "oldest chunks dropped first, the open one kept")
      Check(db.dropped >= 2, "dropped chunks counted", db.dropped)
      Section("trail: moves, stops after 30 idle min, resumes")
      local open = db.chunks[db.seq]
      local function Count(kind)
        local n = 0
        for _, s in pairs(db.chunks) do
          if #s < 100000 then
            for line in (s .. "\n"):gmatch("([^\n]*)\n") do
              if line:sub(1, 2) == kind .. "\t" then n = n + 1 end
            end
          end
        end
        return n
      end
      for i = 1, 8 do p.x = 0.30 + 0.002 * i; Sim.Advance(1) end   -- 9.85 yd/s: a sample every 2 s
      S().Session:Flush()
      local moving = Count("p")
      Check(moving >= 4 and moving <= 9, "position samples while moving (~every 2 s): " .. moving)
      Sim.Advance(1850)                      -- idle 30+ min: trail stops, one "t 0"
      Sim.Advance(60)
      S().Session:Flush()
      Check(Count("t") >= 1, "trail stop recorded after 30 idle minutes")
      Sim.Advance(5)
      p.x = 0.45; Sim.Advance(1); p.x = 0.46; Sim.Advance(3)
      S().Session:Flush()
      local ts = Count("t")
      Check(ts >= 2, "trail resumes on movement (stop + resume markers): " .. ts)
      Section("option off")
      S().Options:Set("recordSession", false)
      Check(not S().Session:IsRunning(), "turning the option off stops the session")
      local n1 = S().Session:Stats()
      Sim.Advance(10); Sim.Fire("PLAYER_DEAD")
      local n2 = S().Session:Stats()
      Check(n1 == n2, "nothing recorded after turning it off")
      Slash("grabar limpiar")
      Check(S().Session:Stats() == 0, "/senda grabar limpiar deletes the chunks")
    `,
  },
];

module.exports = { scenarios, ingest };

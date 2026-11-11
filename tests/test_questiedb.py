"""Tests for tools/questiedb (codec, Lua parser, builder), tools/ingest.py and tools/verify.py.

Synthetic inputs only, except RealQuestieDBSmoke which runs when the user's QuestieDB is installed
(set SENDA_QUESTIEDB or keep the default path). Run: python -m unittest tests.test_questiedb -v
"""

from __future__ import annotations

import base64
import json
import os
import struct
import sys
import tempfile
import textwrap
import tomllib
import unittest
import zlib
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from questiedb import cbor, luaparse, toc  # noqa: E402
from questiedb.db import QuestDB, resolve_questiedb  # noqa: E402
from questiedb import constants  # noqa: E402
import ingest  # noqa: E402
import verify  # noqa: E402


# --------------------------------------------------------------------------------------------
# Tiny CBOR encoder (test helper), mirroring C_EncodingUtil.SerializeCBOR's Lua mapping
# --------------------------------------------------------------------------------------------

def _head(major, n):
    if n < 24:
        return bytes([(major << 5) | n])
    if n < 256:
        return bytes([(major << 5) | 24, n])
    if n < 65536:
        return bytes([(major << 5) | 25]) + struct.pack(">H", n)
    if n < 2 ** 32:
        return bytes([(major << 5) | 26]) + struct.pack(">I", n)
    return bytes([(major << 5) | 27]) + struct.pack(">Q", n)


def enc(v) -> bytes:
    if v is None:
        return b"\xf6"
    if v is True:
        return b"\xf5"
    if v is False:
        return b"\xf4"
    if isinstance(v, int):
        return _head(0, v) if v >= 0 else _head(1, -1 - v)
    if isinstance(v, float):
        return b"\xfb" + struct.pack(">d", v)
    if isinstance(v, str):
        b = v.encode("utf-8")
        return _head(2, len(b)) + b  # Lua strings serialize as byte strings
    if isinstance(v, list):
        return _head(4, len(v)) + b"".join(enc(x) for x in v)
    if isinstance(v, dict):
        return _head(5, len(v)) + b"".join(enc(k) + enc(x) for k, x in v.items())
    raise TypeError(v)


def b64(v) -> str:
    return base64.b64encode(enc(v)).decode()


class CBORTests(unittest.TestCase):
    def test_roundtrip_values(self):
        for v in [0, 23, 24, 255, 256, 65535, 65536, 2 ** 32 + 77, -1, -500, 1.5, "Sten", [1, None, 3],
                  {1: "a", "p": 6}, {1426: [[29.93, 71.2]]}, True, False]:
            self.assertEqual(cbor.decode(enc(v)), v)

    def test_real_samples(self):
        # Shapes taken from the Forever TOC: quest 179 starters and NPC 658 spawns.
        self.assertEqual(cbor.decode(base64.b64decode("gYEZApI=")), [[658]])
        spawns = cbor.decode(base64.b64decode("gYGC+0A97hR64Ueu+0BRzMzMzMzN"))
        self.assertEqual(len(spawns), 1)
        self.assertAlmostEqual(spawns[0][0][0], 29.93)
        self.assertEqual(cbor.decode(base64.b64decode("oQOBgxkC7vYA")), {3: [[750, None, 0]]})

    def test_half_float_and_indefinite(self):
        self.assertEqual(cbor.decode(bytes([0xF9, 0x3C, 0x00])), 1.0)
        self.assertEqual(cbor.decode(bytes([0x9F, 0x01, 0x02, 0xFF])), [1, 2])
        self.assertEqual(cbor.decode(bytes([0xBF, 0x01, 0x02, 0xFF])), {1: 2})

    def test_errors(self):
        with self.assertRaises(cbor.CBORError):
            cbor.decode(bytes([0x82, 0x01]))
        with self.assertRaises(cbor.CBORError):
            cbor.decode(bytes([0x01, 0x02]))


class TocStoreTests(unittest.TestCase):
    def test_chunks_ids_and_presence(self):
        ids_b64 = base64.b64encode(zlib.compress(enc([1, 7]))).decode()
        meta = {
            "Quest-IDS": "~2~", "Quest-IDS-1": ids_b64[:5], "Quest-IDS-2": ids_b64[5:],
            # field 1 name, 4 requiredLevel; p: bit (2-1) set -> field 2 (table) present
            "Quest-7-S": b64({1: "Test", 4: 3, "p": 2}),
            "Quest-7-2": b64([[100]]),
            "Quest-7-3": b64([[999]]),  # present in store but not flagged in p: must be ignored
        }
        store = toc.MetaStore(meta)
        self.assertEqual(store.ids("Quest-"), [1, 7])
        row = store.entity("Quest-", 7, {1: "string", 2: "table", 3: "table", 4: "number"})
        self.assertEqual(row, {1: "Test", 4: 3, 2: [[100]]})
        self.assertIsNone(store.entity("Quest-", 1, {1: "string"}))

    def test_missing_chunk_part(self):
        store = toc.MetaStore({"Npc-IDS": "~3~", "Npc-IDS-1": "a"})
        with self.assertRaises(ValueError):
            store.get("Npc-IDS")

    def test_read_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.toc"
            p.write_text("## Interface: 16001\n## X-Flavor: Forever\r\n## X-Quest-1-S: abc=\nsrc\\a.lua\n", encoding="utf-8")
            self.assertEqual(toc.read_metadata(p), {"Flavor": "Forever", "Quest-1-S": "abc="})


class LuaParseTests(unittest.TestCase):
    def test_savedvariables(self):
        src = textwrap.dedent('''
            SendaRecorderDB = {
              ["obs"] = {
                { t = 1762800000, kind = "accept", quest = 179, npc = 658, map = 1426,
                  x = 0.2993, y = 0.712, level = 1, race = "Gnome", ["class"] = "WARLOCK", build = "1.60.1.70291" }, -- [1]
                {kind='turnin', quest=0x10, x=-1.5e1, note=[[multi
            line]], esc="a\\"b\\65"},
              },
              ["empty"] = {},
              flag = true, nothing = nil,
            }
            SendaDB = nil
        ''')
        out = luaparse.parse_assignments(src)
        db = luaparse.to_py(out["SendaRecorderDB"])
        self.assertEqual(db["obs"][0]["class"], "WARLOCK")
        self.assertEqual(db["obs"][1]["quest"], 16)
        self.assertEqual(db["obs"][1]["x"], -15.0)
        self.assertEqual(db["obs"][1]["note"], "multi\nline")
        self.assertEqual(db["obs"][1]["esc"], 'a"bA')
        self.assertEqual(db["empty"], [])
        self.assertTrue(db["flag"])
        self.assertNotIn("nothing", db)
        self.assertIsNone(out["SendaDB"])

    def test_env_and_unresolved(self):
        env = lambda path: {"questKeys": {"startedBy": 2}, "zoneIDs": {"DUN_MOROGH": 1}}[path[0]][path[1]]
        src = '''{ [questKeys.startedBy] = {{1, 2}}, [9] = ({["MAGE"] = 3})[playerClass],
                   [10] = zoneIDs.DUN_MOROGH + 1, [11] = l10n("x"), [12] = a == b or c }'''
        t = luaparse.parse_value(src, env)
        self.assertEqual(luaparse.to_py(t[2]), [[1, 2]])
        self.assertIs(t[9], luaparse.UNRESOLVED)
        self.assertEqual(t[10], 2)
        self.assertIs(t[11], luaparse.UNRESOLVED)
        self.assertIs(t[12], luaparse.UNRESOLVED)
        self.assertFalse(luaparse.is_resolved(t))

    def test_no_code_execution(self):
        with self.assertRaises(luaparse.LuaParseError):
            luaparse.parse_value("{ f = function() os.execute('x') end }")

    def test_to_py_sparse(self):
        self.assertEqual(luaparse.to_py(luaparse.LuaTable({1: "a", 3: "c"})), {1: "a", 3: "c"})


class ConstantsTests(unittest.TestCase):
    def test_masks(self):
        self.assertTrue(constants.race_allowed(4294967373, "Gnome"))
        self.assertTrue(constants.race_allowed(4294967373, "Skyborne", "Alliance"))
        self.assertFalse(constants.race_allowed(4294967373, "Orc"))
        self.assertTrue(constants.class_allowed(0, "WARLOCK"))
        self.assertFalse(constants.class_allowed(128, "WARLOCK"))
        self.assertEqual(constants.races_in_mask(4294967373), ["ALLIANCE"])


# --------------------------------------------------------------------------------------------
# Synthetic QuestieDB install -> builder -> API
# --------------------------------------------------------------------------------------------

META = {
    "questMeta.lua": {1: "name", 2: "startedBy", 3: "finishedBy", 4: "requiredLevel", 5: "questLevel",
                      6: "requiredRaces", 7: "requiredClasses", 8: "objectivesText", 10: "objectives",
                      12: "preQuestGroup", 13: "preQuestSingle", 17: "zoneOrSort", 22: "nextQuestInChain"},
    "npcMeta.lua": {1: "name", 4: "minLevel", 5: "maxLevel", 7: "spawns", 9: "zoneID", 10: "questStarts",
                    11: "questEnds", 13: "friendlyToFaction", 15: "npcFlags"},
    "itemMeta.lua": {1: "name", 2: "npcDrops", 14: "vendors"},
    "objectMeta.lua": {1: "name", 2: "questStarts", 4: "spawns"},
}
TABLE_FIELDS = {"startedBy", "finishedBy", "objectivesText", "objectives", "preQuestGroup", "preQuestSingle",
                "spawns", "questStarts", "questEnds", "npcDrops", "vendors"}
STRING_FIELDS = {"name", "friendlyToFaction"}


def _meta_lua(names: dict[int, str]) -> str:
    def kind(n):
        return "table" if n in TABLE_FIELDS else "string" if n in STRING_FIELDS else "number"
    nm = ", ".join(f"[{i}]='{n}'" for i, n in names.items())
    ty = ", ".join(f"[{i}]='{kind(n)}'" for i, n in names.items())
    return f"local meta = {{\n  names = {{\n{nm}\n  }},\n  types = {{\n{ty}\n  }},\n}}\nreturn meta\n"


def make_fake_questiedb(base: Path) -> Path:
    root = base / "AddOns" / "QuestieDB"
    (root / "src" / "meta").mkdir(parents=True)
    for fname, names in META.items():
        (root / "src" / "meta" / fname).write_text(_meta_lua(names), encoding="utf-8")
    zones = root / "support" / "Forever" / "Zones"
    zones.mkdir(parents=True)
    (zones / "areaIdToUiMapId.lua").write_text(textwrap.dedent('''
        ZoneDB.private.areaIdToUiMapIdOverride = [[return {
            [0] = 0, -- Existing fail-safe
        }]]
        ZoneDB.private.areaIdToUiMapId = [[return {
            [1] = 1426, -- Dun Morogh
            [132] = 1426, -- Coldridge Valley -> Dun Morogh
        }]]
    '''), encoding="utf-8")
    (zones / "uiMapIdToAreaId.lua").write_text(
        "ZoneDB.private.uiMapIdToAreaId = [[return {\n    [1426] = 1, -- Dun Morogh\n}]]\n", encoding="utf-8")
    (zones / "subZoneToParentZone.lua").write_text(
        "ZoneDB.private.subZoneToParentZone = [[return {\n  [6176] = 1, -- Coldridge Valley -> Dun Morogh\n}]]\n",
        encoding="utf-8")
    enum = root / "src" / "corrections" / "enum"
    enum.mkdir(parents=True)
    (enum / "zones.lua").write_text("constants.zoneIDs = {\n  DUN_MOROGH = 1,\n}\n", encoding="utf-8")
    (enum / "quests.lua").write_text("constants.sortKeys = {\n  WARLOCK = -61,\n}\n", encoding="utf-8")
    fixes = root / "src" / "corrections" / "Forever"
    fixes.mkdir(parents=True)
    (fixes / "foreverQuestFixes.lua").write_text(textwrap.dedent('''
        function ForeverQuestFixes:Load()
          return {}
        end
        function ForeverQuestFixes:LoadDynamic()
            local questKeys = QuestieDB.questKeys
            local zoneIDs = ZoneDB.zoneIDs
            local questFixesHorde = {
                [2] = { [questKeys.startedBy] = {{999}} },
            }
            local questFixesAlliance = {
                [2] = { -- Second
                    [questKeys.startedBy] = {{20}},
                    [questKeys.nextQuestInChain] = ({["MAGE"] = 5})[playerClass],
                },
            }
            if UnitFactionGroup("Player") == "Horde" then return questFixesHorde else return questFixesAlliance end
        end
    '''), encoding="utf-8")
    ids = lambda xs: base64.b64encode(zlib.compress(enc(xs))).decode()
    lines = ["## Interface: 16001", "## X-Flavor: Forever", "## X-BUILD-COMMIT: abc123"]
    # Quest 1: started/ended by NPC 10 at Coldridge, Gnome+Dwarf only, warlock only.
    lines += [f"## X-Quest-IDS: {ids([1, 2])}",
              f"## X-Quest-1-S: {b64({1: 'First Steps', 4: 1, 5: 2, 6: 64 + 4, 7: 256, 17: 132, 'p': (1 << 1) | (1 << 2) | (1 << 9)})}",
              f"## X-Quest-1-2: {b64([[10]])}", f"## X-Quest-1-3: {b64([[10]])}",
              f"## X-Quest-1-10: {b64({3: [[750, None, 0]]})}",
              f"## X-Quest-2-S: {b64({1: 'Second', 4: 3, 5: 4, 17: 1, 'p': (1 << 1) | (1 << 2) | (1 << 11)})}",
              f"## X-Quest-2-2: {b64([[11]])}", f"## X-Quest-2-3: {b64([[11]])}",
              f"## X-Quest-2-12: {b64([1])}"]
    spawns = enc([[[29.93, 71.2]]])  # {[1] = {{29.93, 71.2}}}
    big = base64.b64encode(spawns).decode()
    lines += [f"## X-Npc-IDS: {ids([10, 11, 20])}",
              f"## X-Npc-10-S: {b64({1: 'Sten', 4: 5, 5: 5, 9: 1, 13: 'A', 15: 3, 'p': (1 << 6)})}",
              "## X-Npc-10-7: ~2~", f"## X-Npc-10-7-1: {big[:8]}", f"## X-Npc-10-7-2: {big[8:]}",
              f"## X-Npc-11-S: {b64({1: 'Other', 4: 6, 5: 7, 15: 2, 'p': (1 << 6)})}",
              f"## X-Npc-11-7: {b64({132: [[50.0, 50.0]]})}",
              f"## X-Npc-20-S: {b64({1: 'Fixed', 4: 1, 5: 1, 'p': (1 << 6)})}",
              f"## X-Npc-20-7: {b64({1: [[40.0, 40.0]]})}",
              f"## X-Item-IDS: {ids([750])}", f"## X-Item-750-S: {b64({1: 'Tough Wolf Meat', 'p': 0})}",
              f"## X-Object-IDS: {ids([])}"]
    (root / "QuestieDB_Forever.toc").write_text("\n".join(lines) + "\n", encoding="utf-8")
    questie = base / "AddOns" / "Questie" / "Database" / "Corrections"
    questie.mkdir(parents=True)
    (questie / "QuestieQuestBlacklist.lua").write_text(textwrap.dedent('''
        local HIDE_ON_MAP = "HIDE_ON_MAP"
        function QuestieQuestBlacklist:Load()
            local questsToBlacklist = {
                [2] = HIDE_ON_MAP,
                [3] = true,
                [4] = Expansions.Current >= Expansions.Wotlk,
                [5] = false,
            }
            return questsToBlacklist
        end
    '''), encoding="utf-8")
    return root


class BuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.root = make_fake_questiedb(base)
        cls.cache = base / "cache"
        cls.db = QuestDB.open(cls.root, cache_dir=cls.cache, verbose=None)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_quest(self):
        q = self.db.quest(1)
        self.assertEqual(q["name"], "First Steps")
        self.assertEqual((q["level"], q["requiredLevel"]), (2, 1))
        self.assertEqual(q["starters"]["npc"], [10])
        self.assertEqual(q["zone"]["uiMapId"], 1426)
        self.assertEqual(q["objectives"]["item"][0]["id"], 750)
        self.assertTrue(self.db.can_take(1, "Gnome", "WARLOCK"))
        self.assertFalse(self.db.can_take(1, "Human", "WARLOCK"))
        self.assertFalse(self.db.can_take(1, "Gnome", "MAGE"))

    def test_dynamic_correction_and_blacklist(self):
        q = self.db.quest(2)
        self.assertEqual(q["starters"]["npc"], [20])  # Alliance fix applied, not Horde
        self.assertEqual(q["nextQuestInChain"], 0)  # class-dependent value skipped
        self.assertEqual(q["preQuestGroup"], [1])
        self.assertEqual(q["hidden"], "hide_on_map")
        self.assertIn(["Quest", 2, 22, "foreverQuestFixes.lua"], self.db.info["skipped_corrections"])

    def test_npc_spawns_area_to_uimap_and_chunked(self):
        n = self.db.npc(10)
        self.assertEqual(n["spawns"], [[1426, 29.93, 71.2, 1]])
        self.assertEqual(n["friendlyTo"], "A")
        self.assertEqual(self.db.npc(11)["spawns"][0][:3], [1426, 50.0, 50.0])
        self.assertEqual(self.db.npc_quests(10), {"starts": [1], "ends": [1]})
        self.assertEqual(self.db.npc_quests(20)["starts"], [2])

    def test_search_chain_zone(self):
        names = [r.get("name") for r in self.db.search("coldridge")]
        self.assertIn("Coldridge Valley", names)
        self.assertEqual(self.db.chain(1)["followups"][0]["id"], 2)
        rows = self.db.zone_quests(1426, race="Gnome", cls="WARLOCK", max_level=10)
        self.assertEqual([r["id"] for r in rows], [1, 2])
        rows = self.db.zone_quests(1426, race="Human", cls="MAGE")
        self.assertEqual([r["id"] for r in rows], [2])

    def test_cache_reused(self):
        files = list(self.cache.glob("*.pickle"))
        self.assertEqual(len(files), 1)
        mtime = files[0].stat().st_mtime_ns
        QuestDB.open(self.root, cache_dir=self.cache)
        self.assertEqual(files[0].stat().st_mtime_ns, mtime)


# --------------------------------------------------------------------------------------------
# ingest.py
# --------------------------------------------------------------------------------------------

class IngestTests(unittest.TestCase):
    def test_clean_strips_personal_and_normalizes(self):
        o = ingest.clean({"t": 1762812345, "kind": "accept", "quest": 179, "npc": 658, "map": 1426, "x": 0.2993,
                          "y": 0.712, "level": 1, "race": "Gnome", "class": "warlock", "build": "1.60.1.70291",
                          "player": "Secretname", "realm": "Realm"})
        self.assertEqual(o, {"kind": "accept", "quest": 179, "npc": 658, "map": 1426, "level": 1, "x": 29.93,
                             "y": 71.2, "race": "Gnome", "class": "WARLOCK", "build": "1.60.1.70291",
                             "t": 1762812345 // 86400 * 86400})
        self.assertIsNone(ingest.clean({"kind": "chat", "text": "hi"}))

    def test_parse_merge_and_write(self):
        with tempfile.TemporaryDirectory() as d:
            sv = Path(d) / "WTF" / "Account" / "X" / "SavedVariables"
            sv.mkdir(parents=True)
            (sv / "Senda.lua").write_text(textwrap.dedent('''
                SendaRecorderDB = {
                  ["owner"] = "Secretname-Realm",
                  ["obs"] = {
                    {["t"] = 100, ["kind"] = "accept", ["quest"] = 179, ["npc"] = 658, ["map"] = 1426, ["x"] = 29.93, ["y"] = 71.2, ["build"] = "1.60.1.70291"},
                    {["t"] = 200, ["kind"] = "accept", ["quest"] = 179, ["npc"] = 658, ["map"] = 1426, ["x"] = 29.95, ["y"] = 71.21, ["build"] = "1.60.1.70291"},
                    {["t"] = 300, ["kind"] = "bind", ["map"] = 1426, ["x"] = 47.0, ["y"] = 52.0},
                  },
                }
            '''), encoding="utf-8")
            out = Path(d) / "obs"
            self.assertEqual(ingest.main([str(Path(d) / "WTF"), "--out", str(out)]), 0)
            doc = json.loads((out / "1.60.1.70291.json").read_text(encoding="utf-8"))
            self.assertEqual(doc["count"], 1)
            self.assertEqual(doc["observations"][0]["n"], 2)
            self.assertTrue((out / "unknown.json").exists())
            self.assertNotIn("Secretname", (out / "1.60.1.70291.json").read_text(encoding="utf-8"))
            ingest.main([str(sv / "Senda.lua"), "--out", str(out)])  # re-ingest merges counts
            doc = json.loads((out / "1.60.1.70291.json").read_text(encoding="utf-8"))
            self.assertEqual(doc["observations"][0]["n"], 4)


# --------------------------------------------------------------------------------------------
# verify.py
# --------------------------------------------------------------------------------------------

SECTION = '''id = "coldridge"
title = "Valle"
levels = [1, 6]
map = 1426

# comentario que debe sobrevivir
[[step]]
id = "c-001"
do = "accept"
quest = 1
npc = 10
at = [1426, 30.0, 71.0]
text = "Coge."
status = "unverified"   # estado
sources = ["https://warcraft.wiki.gg/wiki/First_Steps"]

[[step]]
id = "c-002"
do = "accept"
quest = 2
npc = 10
at = [1426, 40.0, 40.0]
text = "Coge la segunda."
status = "unverified"
sources = [
  "questie:quest/2",
]

[step.if]
class = ["WARLOCK"]

[[step]]
id = "c-003"
do = "turnin"
quest = 1
npc = 10
at = [1426, 29.9, 71.2]
text = "Entrega."
status = "unverified"

[[step]]
id = "c-004"
do = "accept"
quest = 1
npc = 10
at = [1426, 60.0, 71.0]
text = "Coordenadas malas."
status = "verified"
sources = ["questie:quest/1"]
'''


class VerifyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.qdb = make_fake_questiedb(base)
        os.environ["SENDA_QUESTIEDB"] = str(cls.qdb)
        cls.repo = base / "repo"
        g = cls.repo / "data" / "guides" / "gnome-warlock"
        g.mkdir(parents=True)
        (g / "guide.toml").write_text('id = "gnome-warlock"\ntitle = "x"\nfaction = "Alliance"\nraces = ["Gnome"]\n'
                                      'classes = ["WARLOCK"]\nsections = ["01-coldridge"]\n', encoding="utf-8")
        (g / "01-coldridge.toml").write_text(SECTION, encoding="utf-8")
        obs = cls.repo / "data" / "observations"
        obs.mkdir(parents=True)
        (obs / "1.60.1.json").write_text(json.dumps({"observations": [
            {"kind": "turnin", "quest": 1, "npc": 10, "map": 1426, "x": 29.9, "y": 71.1, "build": "1.60.1"}]}),
            encoding="utf-8")
        h = cls.repo / "harness"
        h.mkdir()
        (h / "sources.toml").write_text('[[source]]\nid = "wiki"\ntier = "community_curated"\nkind = "reference"\n'
                                        'match = ["warcraft.wiki.gg"]\n', encoding="utf-8")
        import questiedb.db as dbmod
        cls._cache = dbmod.CACHE_DIR
        dbmod.CACHE_DIR = base / "cache"

    @classmethod
    def tearDownClass(cls):
        import questiedb.db as dbmod
        dbmod.CACHE_DIR = cls._cache
        os.environ.pop("SENDA_QUESTIEDB", None)
        cls.tmp.cleanup()

    def run_verify(self, *extra):
        return verify.main(["--root", str(self.repo), "--today", "2026-11-11", *extra])

    def test_report_and_apply(self):
        rc = self.run_verify("--apply-status")
        self.assertEqual(rc, 1)  # c-004 conflicts
        report = json.loads((self.repo / "harness" / "reports" / "verify-latest.json").read_text(encoding="utf-8"))
        res = {r["step"]: r for r in report["results"]}
        self.assertEqual(res["c-001"]["verdict"], "confirm")
        self.assertTrue(res["c-001"]["db_confirmed"])
        # c-002: npc 10 is not the (Alliance-corrected) starter 20 and prereq 1 not turned in yet
        checks = {c["check"]: c["result"] for c in res["c-002"]["checks"]}
        self.assertEqual(checks["starter"], "conflict")
        self.assertEqual(checks["prereqs"], "conflict")
        self.assertEqual(res["c-003"]["verdict"], "confirm")
        self.assertTrue(res["c-003"]["obs_confirmed"])
        self.assertEqual({c["check"]: c["result"] for c in res["c-004"]["checks"]}["coords"], "conflict")
        self.assertTrue(any("c-004" in s for s in report["suggestions"]))
        self.assertTrue((self.repo / "harness" / "reports" / "verify-latest.md").exists())

        text = (self.repo / "data" / "guides" / "gnome-warlock" / "01-coldridge.toml").read_text(encoding="utf-8")
        doc = tomllib.loads(text)
        steps = {s["id"]: s for s in doc["step"]}
        # db + a generic wiki URL is NOT enough any more (rule (c) needs an official source or a
        # harness-checked quote), so c-001 stays unverified.
        self.assertEqual(steps["c-001"]["status"], "unverified")
        self.assertEqual(steps["c-002"]["status"], "unverified")  # conflict: untouched
        self.assertEqual(steps["c-003"]["status"], "verified")  # rule (b): observation
        self.assertIn("ingame:obs", steps["c-003"]["sources"])
        self.assertEqual(steps["c-004"]["status"], "verified")  # never downgraded
        self.assertIn("# comentario que debe sobrevivir", text)
        self.assertIn('status = "unverified"   # estado', text)  # inline comment preserved
        self.assertEqual(steps["c-002"]["if"]["class"], ["WARLOCK"])

    def test_edit_step_multiline_sources(self):
        text = '[[step]]\nid = "a"\nstatus = "unverified"\nsources = [\n  "x",\n  "y"  # c\n]\n\n[[step]]\nid = "b"\nstatus = "unverified"\n'
        out = verify.edit_step(text, "a", "verified", ["questie:quest/1"], "2026-01-02")
        doc = tomllib.loads(out)
        self.assertEqual(doc["step"][0]["sources"], ["x", "y", "questie:quest/1"])
        self.assertEqual(doc["step"][0]["checked"], "2026-01-02")
        self.assertEqual(doc["step"][1]["status"], "unverified")
        out = verify.edit_step(out, "b", "verified", ["ingame:obs"], "2026-01-02")
        doc = tomllib.loads(out)
        self.assertEqual(doc["step"][1]["sources"], ["ingame:obs"])
        self.assertIsNone(verify.edit_step(text, "zzz", "verified", [], "2026-01-02"))


# --------------------------------------------------------------------------------------------
# Real QuestieDB smoke test (skipped when not installed)
# --------------------------------------------------------------------------------------------

def _real_root():
    try:
        return resolve_questiedb()
    except FileNotFoundError:
        return None


@unittest.skipUnless(_real_root(), "QuestieDB for Forever is not installed")
class RealQuestieDBSmoke(unittest.TestCase):
    def test_coldridge(self):
        db = QuestDB.open(_real_root())
        q = db.quest(179)
        self.assertEqual(q["name"], "Dwarven Outfitters")
        self.assertIn(658, q["starters"]["npc"])
        n = db.npc(658)
        self.assertEqual(n["name"], "Sten Stoutarm")
        self.assertTrue(any(s[0] == 1426 for s in n["spawns"]))
        self.assertIn(179, db.npc_quests(658)["starts"])
        ids = [r["id"] for r in db.zone_quests(1426, race="Gnome", cls="WARLOCK", max_level=5)]
        self.assertIn(179, ids)


if __name__ == "__main__":
    unittest.main()

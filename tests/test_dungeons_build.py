"""Tests del diario de mazmorras: tools/build.py (render_dungeons) -> addon/Senda/Data/Dungeons.lua, y la conversión de
estadísticas de tools/gen_dungeon_journal.py.

    python -m unittest tests.test_dungeons_build -v
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import build  # noqa: E402
import gen_dungeon_journal as gj  # noqa: E402
import validate  # noqa: E402
from common import Paths  # noqa: E402

PRIORITY = ["deadmines", "wailing-caverns", "blackfathom-deeps", "stormwind-stockade", "gnomeregan", "scarlet-monastery",
            "razorfen-kraul", "razorfen-downs", "uldaman", "zulfarrak", "maraudon", "sunken-temple", "blackrock-depths",
            "dire-maul", "scholomance", "stratholme"]


def sec(*steps):
    return SimpleNamespace(data={"step": list(steps)})


DUNGEONS = [
    {"key": "deadmines", "name": "Deadmines", "entrance": {"uiMapId": 1436, "x": 38.2, "y": 77.5}},
    {"key": "uldaman", "name": "Uldaman", "entrance": {"uiMapId": 1432, "x": 34.9, "y": 85.5}},
    {"key": "the-hall-of-thanes", "name": "The Hall of Thanes", "entrance": None},
]
QUESTS = {"deadmines": [{"id": 166, "scope": "zone"}, {"id": 2040, "scope": "chain"}],
          "uldaman": [{"id": 709, "scope": "zone"}], "the-hall-of-thanes": []}


class StepMapping(unittest.TestCase):
    def test_text_quests_and_point(self):
        steps = build.dungeon_steps([sec(
            {"id": "a", "do": "dungeon", "text": "Haz las Minas de la Muerte en grupo."},
            {"id": "b", "do": "dungeon", "text": "Opcional.", "quests": [709]},
            {"id": "c", "do": "dungeon", "text": "Busca grupo y entra en Hall of Thanes."},
            {"id": "d", "do": "dungeon", "text": "Algo.", "at": [1436, 39.0, 78.0]},
            {"id": "e", "do": "dungeon", "text": "Solo una previa.", "quests": [2040]},
            {"id": "f", "do": "dungeon", "text": "Fortaleza Krol'dok."},
            {"id": "g", "do": "goto", "text": "Minas de la Muerte"},
        )], DUNGEONS, QUESTS)
        self.assertEqual(steps, {"a": "deadmines", "b": "uldaman", "c": "the-hall-of-thanes", "d": "deadmines"})


class RepoData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = Paths(REPO)
        cls.ds = validate.load_and_check(cls.paths)
        cls.lua = build.render_dungeons(cls.paths, cls.ds.sections)
        cls.blobs = {k: re.search(k + r" = \[==\[\n(.*?)\n\]==\]", cls.lua, re.S).group(1).split("\n")
                     for k in ("list", "quests", "loot")}

    def test_generated_file_is_current_and_compact(self):
        self.assertIsNotNone(self.lua)
        on_disk = (REPO / "addon" / "Senda" / "Data" / "Dungeons.lua").read_text(encoding="utf-8")
        self.assertEqual(on_disk, self.lua)
        self.assertLess(len(self.lua.encode("utf-8")), 150_000, "el plan pide 80-150 KB")
        self.assertIn("Dungeons.lua", (REPO / "addon" / "Senda" / "Data" / "Data.xml").read_text(encoding="utf-8"))

    def test_priority_dungeons_have_card_entrance_and_quests(self):
        rows = {r.split("|")[0]: r.split("|") for r in self.blobs["list"]}
        qkeys = {r.split("|")[0] for r in self.blobs["quests"]}
        for k in PRIORITY:
            self.assertIn(k, rows)
            f = rows[k]
            self.assertTrue(f[9].endswith(",c"), f"{k}: entrada del cliente")
            self.assertTrue(f[4] and f[5], f"{k}: niveles")
            self.assertIn(k, qkeys, f"{k}: misiones")
        self.assertEqual(rows["uldaman"][9].split(",")[0], "1418", "Uldaman se nombra en Tierras Inhóspitas")
        self.assertTrue(rows["the-hall-of-thanes"][9].endswith(",g"), "Hall of Thanes: entrada del paso de la guía")

    def test_loot_rows_are_well_formed(self):
        n = 0
        for r in self.blobs["loot"]:
            f = r.split("|")
            self.assertEqual(len(f), 11, r)
            for kv in filter(None, f[10].split(",")):
                k, v = kv.split("=")
                self.assertRegex(k, r"^[A-Z][A-Z0-9_]*$")
                float(v)
            n += 1
        self.assertGreater(n, 300)
        keys = {r.split("|")[0] for r in self.blobs["loot"]}
        for k in ("deadmines", "wailing-caverns", "blackfathom-deeps", "stormwind-stockade", "gnomeregan",
                  "scarlet-monastery", "razorfen-kraul", "scholomance", "stratholme"):
            self.assertIn(k, keys)

    def test_guide_dungeon_steps_map(self):
        steps = dict(re.findall(r'\["([a-z0-9-]+)"\] = "([a-z0-9-]+)"', self.lua.split("list =")[0]))
        self.assertEqual(steps.get("a21dm-022"), "deadmines")
        self.assertEqual(steps.get("a44-badlands-022"), "uldaman")
        self.assertEqual(steps.get("a40-monasterio-004"), "scarlet-monastery")
        self.assertEqual(steps.get("a47-tanaris-029"), "zulfarrak")
        self.assertNotIn("a41-riverglades-010", steps)  # Krol'dok no es una mazmorra del cliente

    def test_journal_sources(self):
        j = json.loads((REPO / "data" / "dungeons" / "journal.json").read_text(encoding="utf-8"))
        self.assertIn("MIT", j["sources"]["ForeverLevelingBiS"]["licence"])
        for items in j["loot"].values():
            for e in items:
                self.assertIn(e["stats_from"], ("flb", "era"))
                self.assertTrue(set(e["src"]) <= {"flb", "fdb"})


class Stats(unittest.TestCase):
    def test_item_stats(self):
        e = gj.item_stats("17 29 24 3 2 10 spi11 sp32 heal32 dmin39 dmax60 speed2800")
        self.assertEqual((e["inv"], e["req"], e["class"], e["sub"]), (17, 24, 2, 10))
        self.assertEqual(e["stats"]["SPI"], 11)
        self.assertEqual(e["stats"]["SP"], 32)
        self.assertNotIn("heal", e["stats"])
        self.assertAlmostEqual(e["stats"]["DPS"], 17.7, places=1)
        e = gj.item_stats("20 30 25 3 4 1 int10 spShadow14 cls256")
        self.assertEqual(e["stats"], {"INT": 10, "SP_SHADOW": 14})
        self.assertEqual(e["cls"], 256)
        self.assertTrue(gj.equippable(e))
        self.assertFalse(gj.equippable(gj.item_stats("0 1 0 1 15 0")))


if __name__ == "__main__":
    unittest.main()

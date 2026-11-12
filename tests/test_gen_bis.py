"""Tests de tools/gen_bis.py y de las comprobaciones de pesos de equipo de tools/validate.py (solo stdlib).

    python -m unittest discover -s tests -p "test_gen_bis.py" -v
"""
from __future__ import annotations

import contextlib
import io
import shutil
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import gen_bis  # noqa: E402
import validate  # noqa: E402
from common import Paths  # noqa: E402

FIXTURE = REPO / "tests" / "fixtures" / "repo"

# Forever.lua mínimo con el formato de Polestar (inventoryType ilvl req calidad clase subclase estadísticas).
FOREVER = """-- prueba
local DB = Polestar and Polestar.ItemDB
DB.Register(nil, {
[1001]="20 12 12 2 4 1 int5 spi5 sta3",
[1002]="5 12 12 2 4 2 agi9 str9",
[1003]="5 12 12 3 4 3 int20 spi20",
[1004]="20 12 12 2 4 1 int1",
[1005]="17 14 12 2 2 10 int6 spi6 dmin20 dmax30 speed3000",
[1006]="26 14 12 2 2 19 dmin10 dmax20 speed1500",
[1007]="20 12 0 2 4 1 int9 spi9",
[1008]="20 12 12 2 4 1 int30 spi30",
[1009]="2 12 12 2 4 0 int4 cls1024",
})
DB.RegisterLeveling({ source = "ForeverLevelingBiS", version = "v0.12.0-beta", generated = "2026-10-13", licence = "MIT", items = 9, quests = 2 }, {
professions = { "Alchemy" },
names = {
[1001]="Robe",
},
src = {
[1001]="q10",
[1002]="q10",
[1003]="d100x500z1581",
[1004]="d100x500z1581",
[1005]="d200x120z718",
[1006]="c300p6s50",
[1007]="q11",
[1008]="d100x10z1581",
[1009]="q10",
},
quests = {
[10]="12 8 1 12 0 0 0|1001,1002||Alliance quest",
[11]="15 10 2 12 0 0 0|1007||Horde quest",
},
})
"""

WEIGHTS = """id = "warlock-weights"
class = "WARLOCK"
kind = "weights"
title = "Pesos"
status = "unverified"

[[build]]
key = "affliction"
school = "SHADOW"
default = true

[[band]]
build = "affliction"
from = 1
to = 60
w = { SP = 1.0, INT = 0.75, SPI = 0.6, STA = 0.8, WAND_DPS = 2.0 }
"""


class GenBisTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.forever = self.tmp / "Forever.lua"
        self.forever.write_text(FOREVER, encoding="utf-8")
        self.data = gen_bis.read_forever(self.forever)
        self.weights = tomllib.loads(WEIGHTS)

    def tearDown(self):
        self._tmp.cleanup()

    def picks(self):
        text, _ = gen_bis.render("WARLOCK", gen_bis.CLASSES["WARLOCK"], self.data, self.weights,
                                 {"commit": "abc", "flb": "v0.12.0-beta", "flb_date": "2026-10-13", "sha": "0" * 64,
                                  "checked": "2026-10-13"})
        return tomllib.loads(text)["bis"]

    def test_reads_sections(self):
        self.assertEqual(len(self.data["items"]), 9)
        self.assertEqual(self.data["src"][1003], "d100x500z1581")
        self.assertIn("MIT", self.data["meta"])

    def test_class_rules_and_sources(self):
        band = [b for b in self.picks() if b["from"] == 11]
        ids = {b["id"] for b in band}
        self.assertIn(1001, ids, "the cloth robe from an Alliance quest")
        self.assertNotIn(1002, ids, "leather is not for a warlock")
        self.assertNotIn(1003, ids, "mail is not for a warlock, whatever its stats")
        self.assertNotIn(1007, ids, "a Horde-only quest reward is not offered")
        self.assertNotIn(1008, ids, "a 1% drop is below the minimum chance")
        self.assertNotIn(1009, ids, "an item restricted to druids")
        chest = [b for b in band if b["slot"] == 5]
        self.assertEqual([b["id"] for b in chest], [1001], "best usable chest wins over the int1 robe")
        self.assertEqual(chest[0]["quest"], 10)
        staff = [b for b in band if b["slot"] == 16]
        self.assertEqual(staff[0]["id"], 1005)
        self.assertEqual((staff[0]["npc"], staff[0]["zone"], staff[0]["pct"]), (200, 718, 12))
        wand = [b for b in band if b["slot"] == 18]
        self.assertEqual((wand[0]["id"], wand[0]["craft"], wand[0]["prof"]), (1006, 300, "tailoring"))

    def test_refuses_non_mit(self):
        self.data["meta"] = self.data["meta"].replace('"MIT"', '"All Rights Reserved"')
        with self.assertRaises(SystemExit):
            gen_bis.polestar_meta(self.tmp, self.forever, self.data)


class WeightsValidationTests(unittest.TestCase):
    def run_validate(self, weights: str, bis: str | None = None):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "repo"
            shutil.copytree(FIXTURE, root)
            kdir = root / "data" / "knowledge" / "warlock"
            kdir.mkdir(parents=True, exist_ok=True)
            (kdir / "weights.toml").write_text(weights, encoding="utf-8")
            if bis:
                (kdir / "bis-forever.toml").write_text(bis, encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                ds = validate.load_and_check(Paths(root))
            return [str(e) for e in ds.errors]

    def test_valid(self):
        self.assertEqual([e for e in self.run_validate(WEIGHTS) if "weights" in e], [])

    def test_gap_and_unknown_key(self):
        bad = WEIGHTS.replace("to = 60", "to = 30").replace("WAND_DPS", "WAND")
        errs = " ".join(self.run_validate(bad))
        self.assertIn("llegar al 60", errs)
        self.assertIn("clave de peso desconocida 'WAND'", errs)

    def test_bis_build_must_exist(self):
        bis = ('id = "warlock-bis"\nclass = "WARLOCK"\nkind = "bis"\ntitle = "B"\nstatus = "unverified"\n\n'
               '[[bis]]\nfrom = 1\nto = 10\nbuild = "demo"\nslot = 5\nid = 1\n')
        errs = " ".join(self.run_validate(WEIGHTS, bis))
        self.assertIn("build 'demo' no está en los pesos de WARLOCK", errs)


if __name__ == "__main__":
    unittest.main()

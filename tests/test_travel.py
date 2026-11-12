"""data/travel -> addon/Senda/Data/Travel.lua (tools/build.py, render_travel).

El addon decodifica las cadenas de Data/Travel.lua en Modules/Travel.lua; aquí se comprueba que lo compilado dice lo
mismo que los JSON de data/travel y que el formato (filas con «|», puntos con «,») no se rompe con ningún nombre.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build  # noqa: E402
from common import Paths  # noqa: E402

TRAVEL = ROOT / "data" / "travel"
LUA = ROOT / "addon" / "Senda" / "Data" / "Travel.lua"


def rows(name: str) -> list[dict]:
    with open(TRAVEL / f"{name}.json", encoding="utf-8") as fh:
        return json.load(fh)["rows"]


def blob(text: str, key: str) -> list[list[str]]:
    m = re.search(rf"^  {key} = \[==\[\n(.*?)\n\]==\],$", text, re.MULTILINE | re.DOTALL)
    assert m, f"falta {key}"
    return [line.split("|") for line in m.group(1).split("\n") if line]


class TravelData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = build.render_travel(Paths())
        assert cls.text is not None

    def test_committed_file_is_current(self):
        self.assertEqual(LUA.read_text(encoding="utf-8"), self.text, "ejecuta python tools/build.py")

    def test_header_and_constants(self):
        self.assertTrue(self.text.startswith("-- GENERADO por tools/build.py"))
        m = re.search(r"consts = \{ (.*?) \},", self.text)
        self.assertIsNotNone(m)
        consts = dict(re.findall(r"(\w+) = ([\d.]+)", m.group(1)))
        with open(TRAVEL / "meta.json", encoding="utf-8") as fh:
            meta = json.load(fh)["constants"]
        self.assertEqual(float(consts["run"]), meta["run_speed_yd_s"])
        self.assertEqual(float(consts["detour"]), meta["walk_detour"])
        self.assertEqual(float(consts["flySpeed"]), meta["flight_speed_yd_s"])
        self.assertEqual(int(consts["hearthItem"]), meta["hearth_item"])
        self.assertEqual(float(consts["teleShare"]), meta["teleport_share"])

    def test_nodes_match_json(self):
        got = blob(self.text, "nodes")
        want = rows("taxi_nodes")
        self.assertEqual(len(got), len(want))
        for f, t in zip(got, sorted(want, key=lambda t: t["id"])):
            self.assertEqual(int(f[0]), t["id"])
            self.assertEqual(int(f[1]), t["mask"])
            self.assertEqual(f[2], t.get("class") or "")
            c, wx, wy = f[3].split(",")[:3]
            self.assertEqual((int(c), float(wx), float(wy)), (t["c"], round(t["wx"], 1), round(t["wy"], 1)))
            self.assertEqual(f[4], t["name"])

    def test_flights_reference_nodes_and_are_complete(self):
        ids = {int(f[0]) for f in blob(self.text, "nodes")}
        flights = blob(self.text, "flights")
        self.assertEqual(len(flights), len(rows("flights")))
        for a, b, secs in flights:
            self.assertIn(int(a), ids)
            self.assertIn(int(b), ids)
            self.assertGreater(float(secs), 0)

    def test_rides_have_both_ends_and_times(self):
        got = blob(self.text, "rides")
        self.assertEqual(len(got), len(rows("transports")))
        for f in got:
            self.assertEqual(len(f), 14, f)
            self.assertIn(f[1], ("boat", "zeppelin", "tram"))
            self.assertIn(int(f[2]), (1, 2, 3))
            for v in f[3:8]:
                self.assertGreaterEqual(float(v), 0)
            for pt in (f[8], f[11]):
                self.assertEqual(len(pt.split(",")), 7, pt)

    def test_only_continents_with_real_yards(self):
        # Reinos del Este y Kalimdor: los portales del continente nuevo de Forever (2991) no se compilan.
        self.assertEqual(len(blob(self.text, "portals")), 2)
        self.assertEqual(len(blob(self.text, "inns")), 45)
        for f in blob(self.text, "portals") + blob(self.text, "inns"):
            for field in f:
                m = re.match(r"^(\d+),-?[\d.]+,-?[\d.]+,", field)
                if m:
                    self.assertIn(int(m.group(1)), (0, 1))

    def test_teleports(self):
        got = blob(self.text, "teleports")
        self.assertEqual(len(got), 8)
        by_spell = {int(f[0]): f for f in got}
        self.assertEqual(by_spell[556][5], "bind")  # Llamada astral: a la posada vinculada
        self.assertEqual(by_spell[3565][1], "MAGE")
        self.assertEqual(by_spell[3565][4], "17031:1")  # Runa de teletransporte
        self.assertEqual(by_spell[18960][1], "DRUID")
        self.assertEqual(by_spell[18960][4], "")

    def test_no_reserved_characters_in_names(self):
        for key in ("nodes", "rides", "portals", "inns", "teleports"):
            for f in blob(self.text, key):
                for field in f:
                    self.assertNotIn("]==]", field)

    def test_deterministic(self):
        self.assertEqual(build.render_travel(Paths()), self.text)

    def test_missing_data_dir_renders_nothing(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(build.render_travel(Paths(d)))


if __name__ == "__main__":
    unittest.main()

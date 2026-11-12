"""Tests de la compilación de los raros: tools/build.py (render_rares) -> addon/Senda/Data/Rares.lua.

    python -m unittest tests.test_rares_build -v
"""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import build  # noqa: E402
from common import Paths  # noqa: E402

FIXTURE = REPO / "tests" / "fixtures" / "repo"

RARES = [
    {"id": 471, "name": "Mother Fang", "rank": "rare", "level": [10, 10], "spawns": [[1429, 62.1, 48.0]]},
    {"id": 8282, "name": "Highlord Mastrogonde", "rank": "rareelite", "level": [51, 51],
     "spawns": [[1426, 49.7, 84.6], [1427, 29.3, 28.0], [1426, 50.0, 85.0]]},
    {"id": 14697, "name": "Lumbering Horror", "rank": "rare", "level": [1, 1], "spawns": [[1423, 10.0, 20.5]]},
    {"id": 1849, "name": "Dreadwhisper", "rank": "rare", "level": [30, 30], "spawns": []},
]


def quiet(fn, *a):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = fn(*a)
    return rc, out.getvalue(), err.getvalue()


class RaresBuild(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="senda-rares-"))
        self.root = self.tmp / "repo"
        shutil.copytree(FIXTURE, self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self):
        d = self.root / "data" / "rares"
        d.mkdir(parents=True, exist_ok=True)
        (d / "rares.json").write_text(json.dumps(RARES), encoding="utf-8")
        (d / "meta.json").write_text(json.dumps({"source": {"name": "forever-db", "version": "9.9"}}), encoding="utf-8")

    def test_compact_lua(self):
        self.write()
        out = build.render_rares(Paths(self.root))
        lua = out[Paths(self.root).out_data / "Rares.lua"]
        self.assertIn('[471] = "10-10 r 1429:621,480",', lua)
        self.assertIn('[8282] = "51-51 e 1426:497,846;500,850 1427:293,280",', lua)
        self.assertIn('[14697] = "0-0 r 1423:100,205",', lua)  # nivel 1 de forever-db = marcador: desconocido
        self.assertNotIn("1849", lua)  # sin aparición no entra
        self.assertIn("forever-db 9.9", lua)
        xml = out[Paths(self.root).out_data / "Data.xml"]
        self.assertIn('<Script file="Rares.lua"/>', xml)

    def test_build_writes_and_checks(self):
        self.write()
        rc, _, err = quiet(build.main, ["--root", str(self.root), "-q"])
        self.assertEqual(rc, 0, err)
        data = self.root / "addon" / "Senda" / "Data"
        self.assertEqual(sorted(p.name for p in data.iterdir()), ["Data.xml", "Rares.lua"])
        rc, _, err = quiet(build.main, ["--root", str(self.root), "--check", "-q"])
        self.assertEqual(rc, 0, err)
        # sin data/rares: Data.xml vacío y el Rares.lua generado se borra
        shutil.rmtree(self.root / "data" / "rares")
        rc, _, err = quiet(build.main, ["--root", str(self.root), "-q"])
        self.assertEqual(rc, 0, err)
        self.assertEqual(sorted(p.name for p in data.iterdir()), ["Data.xml"])
        self.assertNotIn("<Script", (data / "Data.xml").read_text(encoding="utf-8"))

    def test_repo_data_is_small_and_complete(self):
        lua = (REPO / "addon" / "Senda" / "Data" / "Rares.lua").read_text(encoding="utf-8")
        self.assertLess(len(lua.encode("utf-8")), 40 * 1024)
        self.assertEqual(lua.count('",\n'), 346)


if __name__ == "__main__":
    unittest.main()

"""Tests de la Reserva de XP (tools/reserve.py y su paso en tools/build.py; solo stdlib).

    python -m unittest discover -s tests -p "test_*.py" -v
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
import reserve  # noqa: E402
from common import GENERATED_HEADER, Paths  # noqa: E402

FIXTURE = REPO / "tests" / "fixtures" / "repo"

ROW = {"quest": 118, "reqlevel": 14, "level": 18, "xp": 340, "est_minutes": 0.3, "decision": "keep",
       "races": 4294967373, "classes": 0, "giver": ["n", 341, 1433, 32.1, 48.6], "turnin": ["n", 341, 1433, 32.1, 48.6],
       "pre_all": [], "pre_any": [], "objectives": "c445x10,i2589x5", "point": [1433, 40.0, 60.25], "guide": "x"}


class ReserveEncodeTests(unittest.TestCase):
    def test_line(self):
        line = reserve.encode(ROW)
        self.assertEqual(line, "118|14|18|340|3|k|4294967373|0|n341@1433:32.1,48.6|n341@1433:32.1,48.6|||c445x10,i2589x5|1433:40,60.2")

    def test_line_with_prereqs_and_object_giver(self):
        r = dict(ROW, giver=["o", 20985, 1413, 64.2, 67.4], pre_all=[1, 2], pre_any=[3], point=None, decision="drop",
                 est_minutes=12.04)
        f = reserve.encode(r).split("|")
        self.assertEqual(f[4], "120")
        self.assertEqual(f[5], "d")
        self.assertEqual(f[8], "o20985@1413:64.2,67.4")
        self.assertEqual((f[10], f[11], f[13]), ("1,2", "3", ""))


class ReserveBuildTests(unittest.TestCase):
    def test_render_from_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            shutil.copytree(FIXTURE, root)
            paths = Paths(root)
            self.assertIsNone(reserve.render(paths))
            data = {"_": "x", "forever_db": "2026.11.1", "scores": ["g"], "quests": [ROW, dict(ROW, quest=7, giver=["n", 1, 1426, 1, 2])]}
            reserve.write_snapshot(paths, data)
            self.assertEqual(reserve.read_snapshot(paths)["quests"][0]["quest"], 118)
            text = reserve.render(paths)
            self.assertIn(GENERATED_HEADER, text.splitlines()[0])
            self.assertIn("R:RegisterZone(1426, ", text)
            self.assertIn("R:RegisterZone(1433, ", text)
            self.assertLess(text.index("R:RegisterZone(1426"), text.index("R:RegisterZone(1433"))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                rc = build.build(paths, quiet=True)
            self.assertEqual(rc, 0)
            self.assertTrue((paths.out_guides / "Reserve.lua").exists())
            self.assertIn('<Script file="Reserve.lua"/>', (paths.out_guides / "Guides.xml").read_text(encoding="utf-8"))

    def test_real_snapshot(self):
        """data/reserve.json: solo lo que pueden coger los tres personajes, con datos completos, y < 300 KB en Lua."""
        paths = Paths(REPO)
        data = reserve.read_snapshot(paths)
        self.assertIsNotNone(data, "falta data/reserve.json (python tools/build.py --refresh-reserve)")
        rows = data["quests"]
        self.assertGreater(len(rows), 300)
        alliance = 1 | 4 | 8 | 64
        mine = {"Gnome": 64, "Human": 1, "NightElf": 8}
        classes = {"WARLOCK": 256, "MAGE": 128, "DRUID": 1024}
        seen = set()
        for r in rows:
            self.assertNotIn(r["quest"], seen)
            seen.add(r["quest"])
            self.assertGreater(r["xp"], 0)
            self.assertGreater(r["est_minutes"], 0)
            self.assertIn(r["decision"], ("keep", "optional", "drop"))
            self.assertTrue(r["races"] == 0 or r["races"] & alliance, r["quest"])
            ok = any((r["races"] == 0 or r["races"] & rm) and (r["classes"] == 0 or r["classes"] & classes[c])
                     for (race, c), rm in (((k, c), mine[k]) for k, c in
                                           (("Gnome", "WARLOCK"), ("Human", "MAGE"), ("NightElf", "DRUID"))))
            self.assertTrue(ok, r["quest"])
            for w in (r["giver"], r["turnin"]):
                self.assertIn(w[0], ("n", "o"))
                self.assertTrue(0 <= w[3] <= 100 and 0 <= w[4] <= 100, r["quest"])
        lua = reserve.render(paths)
        self.assertLess(len(lua.encode("utf-8")), 300 * 1024)
        committed = (paths.out_guides / "Reserve.lua").read_text(encoding="utf-8")
        self.assertEqual(committed, lua)

    def test_refresh_needs_foreverdb(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            shutil.copytree(FIXTURE, root)
            with self.assertRaises(FileNotFoundError):
                reserve.refresh(Paths(root), foreverdb=str(Path(tmp) / "nothing"))


class SectionParkFieldsTests(unittest.TestCase):
    def test_class_sections_parkable(self):
        """Las secciones de clase de los tres personajes llevan `parkable` y una pista en español."""
        import tomllib
        found = {}
        for gid in ("gnome-warlock", "human-mage", "nightelf-druid"):
            for f in (REPO / "data" / "guides" / gid).glob("*.toml"):
                d = tomllib.loads(f.read_text(encoding="utf-8"))
                if d.get("parkable"):
                    self.assertIsInstance(d.get("later_hint"), str)
                    self.assertTrue(1 <= d.get("later_level", 0) <= 60)
                    found[d["id"]] = d
        self.assertIn("wl-succubus", found)
        self.assertIn("Vallefresno", found["wl-succubus"]["later_hint"])
        self.assertEqual(found["wl-succubus"].get("later_map"), 1440)
        for sid in ("wl-felhunter", "wl-felsteed", "mg-20-teleport", "dr-10-bear", "dr-20-cat"):
            self.assertIn(sid, found)
        text = (REPO / "addon" / "Senda" / "Guides" / "gnome-warlock.lua").read_text(encoding="utf-8")
        self.assertIn("parkable = true", text)
        self.assertIn("later_map = 1440", text)


if __name__ == "__main__":
    unittest.main()

"""Pruebas de tools/gen_horde.py (entrenamiento de clase) y de la guarda de facción de tools/build.py."""
from __future__ import annotations

import sys
import unittest
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build  # noqa: E402
import gen_horde as GH  # noqa: E402


class FakeNamer:
    def token(self, kind, ident, fallback=None):
        return "{%s:%s}" % (kind, ident)


def fake_trainer(rows_by_class):
    t = GH.Trainer.__new__(GH.Trainer)
    t.spells = rows_by_class
    return t


class TrainerTests(unittest.TestCase):
    def test_real_lists_skip_talent_ranks(self):
        tr = GH.Trainer(ROOT)
        for cls in GH.CLASSES:
            sold = {r["spell"] for r in tr.spells[cls]}
            for r in tr.spells[cls]:
                if r.get("prev"):
                    self.assertIn(r["prev"], sold, f"{cls} {r['spell']}: su rango anterior no lo vende el instructor")

    def test_between_splits_race_spells(self):
        tr = fake_trainer({"PRIEST": [
            {"level": 2, "spell": 1, "prev": 0, "racemask": 0},
            {"level": 4, "spell": 2, "prev": 0, "racemask": 1 << 7},   # trol
            {"level": 6, "spell": 3, "prev": 0, "racemask": 0},
        ]})
        common, by_race = tr.between("PRIEST", 1, 4, None)
        self.assertEqual([r["spell"] for r in common], [1])
        self.assertEqual(list(by_race), ["Troll"])
        common, by_race = tr.between("PRIEST", 1, 4, "Orc")
        self.assertEqual(by_race, {})


class ExpandTrainingTests(unittest.TestCase):
    def step(self, sid, **kw):
        d = {"id": sid, "do": "note", "status": "unverified", "sources": ["polestar:x/g#1"]}
        d.update(kw)
        return d

    def test_one_step_per_class_with_spells_and_level(self):
        tr = fake_trainer({c: [] for c in GH.CLASSES} | {
            "WARRIOR": [{"level": 1, "spell": 10, "prev": 0}, {"level": 4, "spell": 11, "prev": 0},
                        {"level": 10, "spell": 12, "prev": 0}],
            "MAGE": [{"level": 4, "spell": 20, "prev": 0}],
        })
        cands = [{"npc": 1, "map": 1411, "x": 40.0, "y": 60.0, "classes": ["WARRIOR"]},
                 {"npc": 2, "map": 1411, "x": 41.0, "y": 61.0, "classes": ["MAGE"]}]
        steps = [self.step("s-001"), self.step("s-002", _train={"cands": cands, "zone": 1411, "last_at": None}),
                 self.step("s-003")]
        prev: dict[str, int] = {}
        stats = defaultdict(int)
        out = GH.expand_training(steps, (1, 9), prev, tr, None, FakeNamer(), stats)  # punto: nivel 5
        trains = [s for s in out if s["do"] == "train"]
        self.assertEqual({s["id"] for s in trains}, {"s-002-wr", "s-002-mg"})
        wr = next(s for s in trains if s["id"] == "s-002-wr")
        self.assertEqual(wr["spells"], [10, 11])
        self.assertEqual(wr["if"], {"class": ["WARRIOR"]})
        self.assertEqual(wr["npc"], 1)
        self.assertEqual(wr["reqlevel"], 4)
        self.assertIn("trainer:warrior", wr["sources"])
        self.assertEqual(prev["WARRIOR"], 5)

    def test_no_trainer_no_step(self):
        tr = fake_trainer({c: [{"level": 2, "spell": 99, "prev": 0}] for c in GH.CLASSES})
        steps = [self.step("s-001", _train={"cands": [], "zone": None, "last_at": None})]
        out = GH.expand_training(steps, (1, 4), {}, tr, None, FakeNamer(), defaultdict(int))
        self.assertEqual(out, [])


class FactionGateTests(unittest.TestCase):
    def test_horde_files_are_gated_alliance_not(self):
        horde = build._lua_file("data/guides/orc-horde/", ["-- cuerpo"], "Horde")
        self.assertIn('if faction and faction ~= "Horde" then return end', horde)
        ally = build._lua_file("data/guides/gnome-warlock/", ["-- cuerpo"], "Alliance")
        self.assertNotIn("faction", ally)
        self.assertEqual(ally, build._lua_file("data/guides/gnome-warlock/", ["-- cuerpo"]))


class PolishTests(unittest.TestCase):
    def test_class_guide_reference_removed(self):
        st = {"text": "Después ofrece «{quest:1838}». La guía de clase de guerrero «{quest:1838}» la cubre."}
        GH.polish(st)
        self.assertEqual(st["text"], "Después ofrece «{quest:1838}».")


if __name__ == "__main__":
    unittest.main()

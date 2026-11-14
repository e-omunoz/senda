"""Alturas de los pasos (tools/heights.py, data/heights.json): la `z` que lleva cada `at` a la flecha."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import heights  # noqa: E402
import validate  # noqa: E402
from common import Paths  # noqa: E402


class HeightFor(unittest.TestCase):
    ROWS = {"s1": [1429, 39.1, 81.7, 22.6]}

    def test_snapshot_height_when_the_point_matches(self):
        self.assertEqual(heights.height_for({"id": "s1", "at": [1429, 39.1, 81.7]}, self.ROWS), 22.6)
        self.assertEqual(heights.height_for({"id": "s1", "at": [1429, 39.1, 81.7, "Mina"]}, self.ROWS), 22.6)

    def test_a_moved_point_drops_the_height(self):
        self.assertIsNone(heights.height_for({"id": "s1", "at": [1429, 39.2, 81.7]}, self.ROWS))
        self.assertIsNone(heights.height_for({"id": "s1"}, self.ROWS))
        self.assertIsNone(heights.height_for({"id": "s2", "at": [1429, 39.1, 81.7]}, self.ROWS))

    def test_the_step_own_z_wins(self):
        self.assertEqual(heights.height_for({"id": "s1", "at": [1429, 39.1, 81.7], "z": 75}, self.ROWS), 75)


class Snapshot(unittest.TestCase):
    def test_rows_belong_to_current_steps(self):
        paths = Paths()
        rows = heights.read(paths)
        self.assertGreater(len(rows), 1000)
        ds = validate.load_and_check(paths)
        stale = [i for i in ds.warnings if "heights.json" in str(i)]
        self.assertEqual(stale, [], "data/heights.json tiene alturas obsoletas: python tools/build.py --refresh-heights")
        # los puntos de la auditoría de pisos que son pasos de guía (Mina Abisal, Entrañas)
        self.assertAlmostEqual(rows["hmage-elwynn-052"][3], 22.6)
        self.assertAlmostEqual(rows["h12-argenteos-114"][3], -43.0)


if __name__ == "__main__":
    unittest.main()

"""Tests de tools/gen_gathering.py: reglas de color, datos generados (herboristería, minería, desuello, pesca) y la ruta
de las guías. Los de determinismo y los que cruzan con el cliente necesitan .cache (forever-db y wago): se saltan sin ella.

    python -m unittest tests.test_gen_gathering -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import gen_gathering as gg  # noqa: E402
from common import Paths, load_toml  # noqa: E402

KN = REPO / "data" / "knowledge" / "general"
FDB = REPO / ".cache" / "foreverdb"
WAGO = REPO / ".cache" / "wago"
HAVE_CACHE = (FDB / "data" / "spawn.jsonl").exists() and (WAGO / "Lock.csv").exists()


def page(prof):
    return load_toml(KN / f"professions-{prof}.toml")


class Rules(unittest.TestCase):
    def test_gathering_colours(self):
        self.assertIsNone(gg.color(49, 50))
        self.assertEqual(gg.color(50, 50), "orange")
        self.assertEqual(gg.color(74, 50), "orange")
        self.assertEqual(gg.color(75, 50), "yellow")
        self.assertEqual(gg.color(99, 50), "yellow")
        self.assertEqual(gg.color(100, 50), "green")
        self.assertEqual(gg.color(149, 50), "green")
        self.assertEqual(gg.color(150, 50), "grey")

    def test_probabilities(self):
        self.assertEqual(gg.weight(1, 1), 1.0)
        self.assertEqual(gg.weight(30, 1), 0.75)
        self.assertEqual(gg.weight(60, 1), 0.25)
        self.assertEqual(gg.weight(101, 1), 0.0)
        self.assertEqual(gg.weight(10, 50), 0.0)  # rojo: no se puede recoger

    def test_skinning_requirement(self):
        self.assertEqual(gg.skinning_req(1), 1)
        self.assertEqual(gg.skinning_req(10), 1)
        self.assertEqual(gg.skinning_req(11), 10)
        self.assertEqual(gg.skinning_req(15), 50)
        self.assertEqual(gg.skinning_req(20), 100)
        self.assertEqual(gg.skinning_req(21), 105)
        self.assertEqual(gg.skinning_req(60), 300)

    def test_fishing_catches(self):
        self.assertEqual(gg.catches(1, 75), 74)           # cada captura sube por debajo de 75
        self.assertAlmostEqual(gg.catches(1, 300), 1308, delta=2)  # «unas 1.300 capturas» (Polestar)
        self.assertGreater(gg.catches(225, 300), gg.catches(75, 150))

    def test_every_node_skill_exists_in_the_client_lock_table(self):
        if not (WAGO / "Lock.csv").exists():
            self.skipTest("sin .cache/wago")
        locks = gg.lock_skills(WAGO)
        for table, lock_type in ((gg.HERBS, 2), (gg.ORES, 3)):
            for name, (req, _item) in table.items():
                if name in gg.FOREVER_ONLY:
                    continue
                self.assertIn(req, locks[lock_type], f"{name}: la habilidad {req} no está en Lock (tipo {lock_type})")


class GeneratedData(unittest.TestCase):
    def test_pages_exist_and_validate_shape(self):
        for prof in gg.PROFS:
            p = page(prof)
            self.assertEqual(p["kind"], "professions")
            self.assertTrue(p["route"], prof)
            self.assertTrue(p["zone"], prof)
            self.assertTrue(p["bracket"], prof)
            self.assertEqual(p["status"], "unverified")
            # una banda cubre 1..300 sin huecos ni solapes
            routes = sorted(p["route"], key=lambda r: r["from"])
            self.assertEqual(routes[0]["from"], 1)
            self.assertEqual(routes[-1]["to"], 300)
            for a, b in zip(routes, routes[1:]):
                self.assertEqual(a["to"], b["from"])
            for r in p["route"]:
                self.assertGreater(r["n"], 0)

    def test_starting_bands_use_starting_zones(self):
        for prof in ("herbalism", "mining", "skinning"):
            first = next(b for b in page(prof)["bracket"] if b["from"] == 1)
            self.assertTrue(first["zones"], prof)
            for m, _x, _y, _w in first["zones"]:
                lo, _hi, _side = gg.ZONES[m]
                self.assertLessEqual(lo, 15, f"{prof}: {gg.zone_name(m)} no es zona de nivel bajo para habilidad 1-25")

    def test_zone_nodes_colours(self):
        z = {z["map"]: z for z in page("herbalism")["zone"]}
        tel = z[1438]
        # Teldrassil: Flor de paz/Hojaplata (1), Raíz de tierra (15), Marregal (50)
        reqs = sorted({n[1] for n in tel["nodes"]})
        self.assertEqual(reqs[:2], [1, 15])
        st = {c: 0 for c in ("orange", "yellow", "green", "grey")}
        for _item, req, up in tel["nodes"]:
            c = gg.color(10, req)
            if c:
                st[c] += up
        self.assertGreater(st["orange"], 20)  # a 10 casi todo sube al máximo
        self.assertEqual(st["grey"], 0)
        # a 190 todo es gris en Teldrassil
        self.assertEqual(sum(1 for n in tel["nodes"] if gg.color(190, n[1]) != "grey"), 0)

    def test_forever_node_skills_are_classic(self):
        mining = {z["map"]: z for z in page("mining")["zone"]}
        items = {2770: 1, 2771: 65, 2775: 75, 2772: 125, 2776: 155, 3858: 175, 7911: 230, 10620: 245}
        for z in mining.values():
            for item, req, _up in z["nodes"]:
                if item in items and item != 10620:
                    self.assertIn(req, (items[item], 230 if item == 7911 else items[item]))
        self.assertIn(1438, mining, "Teldrassil trae la Chunk of Amber de Forever (Polestar)")

    def test_trainers(self):
        for prof in gg.PROFS:
            ts = page(prof)["trainer"]
            self.assertTrue(ts, prof)
            for t in ts:
                self.assertEqual(len(t["at"]), 4)
                self.assertTrue(0 <= t["at"][1] <= 100 and 0 <= t["at"][2] <= 100, t)
                self.assertTrue(set(t["ranks"]) <= set(gg.RANK_NAMES))
            # los dos bandos tienen instructor de Aprendiz
            for side in ("Alliance", "Horde"):
                self.assertTrue(any(t.get("faction") in (side, None) and "Aprendiz" in t["ranks"] for t in ts), (prof, side))
        # la pesca: Experto por libro, Artesano por misión
        fish = page("fishing")["trainer"]
        self.assertTrue(any(t["name"] == "Old Man Heming" and t["ranks"] == ["Experto"] for t in fish))
        self.assertTrue(any(t["name"] == "Nat Pagle" and t["ranks"] == ["Artesano"] for t in fish))

    def test_fishing_water_rule(self):
        z = {z["map"]: z for z in page("fishing")["zone"]}
        self.assertEqual(z[1429]["full"], 25)
        self.assertEqual(z[1434]["full"], 225)
        first = next(b for b in page("fishing")["bracket"] if b["from"] == 1)
        self.assertTrue(all(gg.FISH_FULL[m] <= 1 for m, *_ in first["zones"]) or first["zones"] == [])


class RouteAware(unittest.TestCase):
    def setUp(self):
        self.route = load_toml(KN / "gathering-route.toml")
        self.stops = {}
        for s in self.route["stop"]:
            self.stops.setdefault(s["guide"], []).append(s)

    def zones(self, prof):
        return {z["map"]: z for z in page(prof)["zone"]}

    def test_all_three_guides_have_stops(self):
        for g in ("gnome-warlock", "human-mage", "nightelf-druid"):
            self.assertGreater(len(self.stops.get(g, [])), 10, g)

    def test_druid_gets_teldrassil_then_darkshore_herbs_early(self):
        stops = self.stops["nightelf-druid"]
        herb = self.zones("herbalism")
        order = []
        for s in stops:
            for m in s["maps"]:
                if m in herb and m not in order:
                    order.append(m)
        self.assertEqual(order[0], 1438, "la primera zona con hierbas del druida es Teldrassil")
        self.assertIn(1439, order[:3], "Costa Oscura llega enseguida")
        # los niveles de esas secciones son de la zona de inicio
        first = next(s for s in stops if 1438 in s["maps"])
        self.assertLessEqual(first["levels"][0], 6)

    def test_route_zone_stays_useful_at_the_expected_skill(self):
        herb = self.zones("herbalism")
        for s in self.stops["nightelf-druid"][:8]:
            for m in s["maps"]:
                if m not in herb:
                    continue
                target = min(300, 5 * s["levels"][1])
                if m in (1438, 1439):
                    self.assertGreater(gg.zone_w(herb[m]["nodes"], target), 0, f"{s['section']} {m} a {target}")

    def test_levels_in_range(self):
        for g, stops in self.stops.items():
            for s in stops:
                self.assertTrue(1 <= s["levels"][0] <= s["levels"][1] <= 60, (g, s))
                self.assertTrue(s["maps"])


@unittest.skipUnless(HAVE_CACHE, "sin .cache de forever-db y wago")
class Reproducible(unittest.TestCase):
    def test_same_bytes_twice_and_matches_the_repo(self):
        a, *_ = gg.generate(FDB, WAGO, Paths())
        b, *_ = gg.generate(FDB, WAGO, Paths())
        self.assertEqual(a, b)
        for name, text in a.items():
            self.assertEqual((KN / name).read_text(encoding="utf-8"), text, f"{name} desactualizado: python tools/gen_gathering.py")

    def test_expected_gathers_are_sane(self):
        _pages, d, _stops = gg.generate(FDB, WAGO, Paths())
        for prof in ("herbalism", "mining", "skinning"):
            total = sum(gg.expected_gathers(r[0]["zone"]["nodes"], lo, hi)
                        for lo, hi in gg.bands() if (r := gg.rank_zones(d, d.zones[prof], lo, hi)))
            self.assertTrue(250 < total < 900, (prof, total))


if __name__ == "__main__":
    unittest.main()

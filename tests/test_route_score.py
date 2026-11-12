"""Tests del filtro de eficiencia (tools/route_score.py, tools/routescore/) con casos sintéticos.

    python tests/test_route_score.py            (sin pytest)
    python -m unittest tests.test_route_score -v
    python -m pytest tests/test_route_score.py   (si está instalado)

No necesitan forever-db: el mundo y la guía son de mentira, montados en una carpeta temporal.
"""
from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

from routescore import model as M  # noqa: E402
from routescore.route import (Travel, World, _dungeon_name, decide_guide, score_guide,  # noqa: E402
                              band_stats)

# --------------------------------------------------------------------------------------------
# Mundo sintético: un mapa 9999 en el continente 0 de 1000 x 1000 yardas (1% = 10 yd)
# --------------------------------------------------------------------------------------------

UIMAP = 9999


def wpos(x, y):
    """[uiMap, x%, y%] -> (map, wx, wy) con el marco sintético (left 0, right -1000, top 1000, bottom 0)."""
    return (0, 1000 - y * 10, -x * 10)


def cluster(cx, cy, n, spread=1.0):
    """n apariciones en rejilla alrededor de (cx%, cy%)."""
    side = int(n ** 0.5) + 1
    pts = []
    for i in range(n):
        pts.append(wpos(cx + (i % side - side / 2) * spread, cy + (i // side - side / 2) * spread))
    return pts


class FakeDB:
    def __init__(self):
        self.quests = {}
        self.npcs = {}
        self.objects = {}
        self.items = {}

    def quest(self, q):
        return self.quests.get(q)

    def npc(self, n):
        return self.npcs.get(n)

    def object(self, o):
        return self.objects.get(o)

    def item(self, i):
        return self.items.get(i)

    def add_quest(self, qid, xp, level, objectives=None, pre=None, classes=0, rewards=None):
        self.quests[qid] = {"id": qid, "name": f"Q{qid}", "xp": xp, "level": level, "classes": classes,
                            "objectives": objectives or {}, "preQuestGroup": pre or [], "preQuestSingle": [],
                            "rewards": rewards or {"item": [], "choice": []}}

    def add_npc(self, nid, level, points, rank=0, name="Mob", faction=14):
        self.npcs[nid] = {"id": nid, "name": name, "minLevel": level, "maxLevel": level, "rank": rank,
                          "world": [list(p) for p in points], "factionID": faction}


def fake_world(db, chance=None):
    w = World.__new__(World)
    w.db = db
    w.root = Path(".")
    w.frames = {UIMAP: (0, 0.0, -1000.0, 1000.0, 0.0)}
    w.chance = chance or {}
    w.mechanics = {}
    w.travel = {"taxi": [], "flights": [], "transports": [], "portals": []}
    return w


GUIDE = """
id = "synthetic"
title = "Sintética"
faction = "Alliance"
races = ["Human"]
classes = ["MAGE"]
levels = [10, 10]
sections = ["01-zona"]
"""

SECTION = """
id = "zona"
title = "Zona"
levels = [10, 10]
map = 9999

[[step]]
id = "s01"
do = "accept"
quest = 1
at = [9999, 50, 50]
text = "a"

[[step]]
id = "s02"
do = "accept"
quest = 2
at = [9999, 50, 50]
text = "a"

[[step]]
id = "s03"
do = "accept"
quest = 3
at = [9999, 50, 50]
text = "a"

[[step]]
id = "s04"
do = "accept"
quest = 6
at = [9999, 50, 50]
text = "a"

[[step]]
id = "s05"
do = "turnin"
quest = 1
at = [9999, 52, 50]
text = "t"

[[step]]
id = "s06"
do = "complete"
quest = 3
at = [9999, 60, 60]
text = "c"

[[step]]
id = "s07"
do = "complete"
quest = 6
at = [9999, 60, 60]
text = "c"

[[step]]
id = "s08"
do = "complete"
quest = 2
at = [9999, 90, 90]
text = "c"

[[step]]
id = "s09"
do = "turnin"
quest = 2
at = [9999, 50, 50]
text = "t"

[[step]]
id = "s10"
do = "turnin"
quest = 3
at = [9999, 50, 50]
text = "t"

[[step]]
id = "s11"
do = "turnin"
quest = 6
at = [9999, 50, 50]
text = "t"

[[step]]
id = "s12"
do = "accept"
quest = 4
at = [9999, 50, 50]
text = "a"

[[step]]
id = "s13"
do = "turnin"
quest = 4
at = [9999, 50, 50]
text = "t"

[[step]]
id = "s14"
do = "accept"
quest = 5
at = [9999, 50, 50]
text = "a"

[[step]]
id = "s15"
do = "turnin"
quest = 5
at = [9999, 50, 50]
text = "t"

[[step]]
id = "s16"
do = "accept"
quest = 7
at = [9999, 50, 50]
text = "a"
if = { class = ["WARRIOR"] }

[[step]]
id = "s17"
do = "dungeon"
quests = [8]
at = [9999, 10, 10, "Entrada a las Minas de la Muerte (Arroyo de la Luna)"]
text = "d"
"""


def build_world():
    db = FakeDB()
    # 1: entrega barata (20 yd)
    db.add_quest(1, 500, 10)
    # 2: lejos, 20 muertes en un campamento de 3 apariciones (limitado por la reaparición)
    db.add_npc(100, 10, cluster(90, 90, 3))
    db.add_quest(2, 300, 10, {"creature": [{"id": 100, "count": 20}]})
    # 3: floja (enemigos grises) que abre la 4, muy buena
    db.add_npc(101, 3, cluster(60, 60, 20))
    db.add_quest(3, 50, 10, {"creature": [{"id": 101, "count": 15}]})
    db.add_quest(4, 2000, 10, pre=[3])
    # 5: necesita la 2
    db.add_quest(5, 900, 10, pre=[2])
    # 6: botín sin probabilidad conocida -> no se filtra
    db.add_npc(102, 10, cluster(60, 60, 10))
    db.items[900] = {"id": 900, "name": "Cosa", "questItem": True}
    db.add_quest(6, 400, 10, {"item": [{"id": 900, "count": 5}]})
    # 7: de guerrero (la guía es de mago): no entra
    db.add_quest(7, 100, 10)
    chance = {900: [("npc", 102, None)]}
    return fake_world(db, chance)


def run_synthetic(bands=None):
    with tempfile.TemporaryDirectory() as tmp:
        gdir = Path(tmp) / "guides" / "synthetic"
        gdir.mkdir(parents=True)
        (gdir / "guide.toml").write_text(textwrap.dedent(GUIDE), encoding="utf-8")
        (gdir / "01-zona.toml").write_text(textwrap.dedent(SECTION), encoding="utf-8")
        shared = Path(tmp) / "shared"
        shared.mkdir()
        res = score_guide(gdir, shared, build_world())
    if bands is None:
        bands = {"6-10": {"p25": 100.0, "median": 200.0, "_sorted": [50.0, 100.0, 200.0, 400.0]}}
    decide_guide(res, bands)
    return res


# --------------------------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------------------------

class XPTables(unittest.TestCase):
    def test_level_table(self):
        self.assertEqual(len(M.LEVEL_XP), 60)
        self.assertEqual(M.LEVEL_XP[1], 400)
        self.assertEqual(M.LEVEL_XP[59], 209800)
        self.assertTrue(all(a < b for a, b in zip(M.LEVEL_XP[1:], M.LEVEL_XP[2:])))
        self.assertEqual(M.level_xp(60), M.LEVEL_XP[59])

    def test_quest_share(self):
        self.assertEqual(M.quest_xp_share(15, 10), 1.0)
        self.assertEqual(M.quest_xp_share(16, 10), 0.8)
        self.assertEqual(M.quest_xp_share(19, 10), 0.2)
        self.assertEqual(M.quest_xp_share(30, 10), 0.1)

    def test_mob_xp(self):
        self.assertEqual(M.mob_xp(30, 30), 195)
        self.assertEqual(M.mob_xp(30, 32), round(195 * 1.1))
        self.assertEqual(M.mob_xp(30, 30, elite=True), 390)
        self.assertEqual(M.mob_xp(30, M.grey_level(30)), 0)
        self.assertGreater(M.mob_xp(30, 28), 0)


class Speeds(unittest.TestCase):
    def test_ground_speed(self):
        self.assertEqual(M.ground_speed(39), 7.0)
        self.assertAlmostEqual(M.ground_speed(40), 11.2)
        self.assertEqual(M.ground_speed(60), 14.0)
        self.assertAlmostEqual(M.ground_speed(30, "DRUID"), 9.8)
        self.assertEqual(M.ground_speed(29, "DRUID"), 7.0)

    def test_walk_includes_detour(self):
        self.assertAlmostEqual(M.walk_seconds(700, 10), 700 * 1.25 / 7)

    def test_flights_and_boats(self):
        facts = {
            "taxi": [{"id": 1, "map": 0, "wx": 0, "wy": 0, "faction": 1, "name": "A, Zona"},
                     {"id": 2, "map": 0, "wx": 3000, "wy": 0, "faction": 1, "name": "B, Zona"},
                     {"id": 3, "map": 0, "wx": 6000, "wy": 0, "faction": 3, "name": "C, Zona"},
                     {"id": 4, "map": 0, "wx": 0, "wy": 50, "faction": 2, "name": "H, Zona"}],
            "flights": [[1, 2, 3000], [2, 3, 3000], [1, 3, 9000]],
            "transports": [{"id": "boat", "kind": "boat", "faction": 3, "a": {"map": 0, "wx": 0, "wy": 0},
                            "b": {"map": 1, "wx": 0, "wy": 0}, "ab": 100, "ba": 100, "waitA": 60, "waitB": 60}],
            "portals": []}
        t = Travel(facts, "Alliance", "MAGE")
        self.assertNotIn(4, t.nodes)                     # nodo de la Horda fuera
        self.assertEqual(t.flight_seconds(1, 3), 2 * (100 + 2))  # dos saltos mejor que uno largo
        self.assertEqual(t.node_named("B"), 2)
        secs, mode = t.leg((0, 0, 0), (1, 0, 0), 10)
        self.assertEqual(mode, "boat")
        self.assertAlmostEqual(secs, 30 + 100)           # media espera + viaje
        self.assertEqual(t.leg((0, 0, 0), (5, 0, 0), 10), (0.0, "unknown"))


class Farming(unittest.TestCase):
    def test_density_and_respawn(self):
        dense = M.farm_seconds(10, 30, 100, 20, 20)
        sparse = M.farm_seconds(10, 12, 400, 20, 20)
        self.assertLess(dense, sparse)                   # campamento denso, más rápido
        limited = M.farm_seconds(20, 3, 100, 20, 20)
        self.assertGreater(limited, 17 * M.EST_RESPAWN_SECONDS / 3 * 0.99)  # espera reapariciones
        self.assertEqual(M.farm_seconds(0, 10, 100, 20, 20), 0.0)

    def test_kill_seconds(self):
        base = M.kill_seconds(20, 20)
        self.assertGreater(M.kill_seconds(20, 23), base)
        self.assertLess(M.kill_seconds(20, 15), base)
        self.assertAlmostEqual(M.kill_seconds(20, 20, rank=1), base * 3)

    def test_grind_reference(self):
        self.assertGreater(M.grind_xp_per_min(30), 0)
        self.assertGreater(M.grind_rate(10), M.grind_rate(50))  # el nivel cuesta cada vez más


class Decide(unittest.TestCase):
    band = {"p25": 150.0, "median": 200.0}

    def test_rules(self):
        self.assertEqual(M.decide(160, None, self.band), ("keep", "rate"))
        self.assertEqual(M.decide(10, 160, self.band), ("keep", "chain"))
        self.assertEqual(M.decide(110, None, self.band), ("optional", "weak"))   # >= mitad de la mediana
        self.assertEqual(M.decide(10, None, self.band, grind=50), ("drop", "slow"))
        self.assertEqual(M.decide(60, None, self.band, grind=50), ("optional", "grind"))
        self.assertEqual(M.decide(10, None, self.band, grind=50, has_reward=True), ("optional", "reward"))
        self.assertEqual(M.decide(1, None, self.band, class_quest=True), ("keep", "class"))
        self.assertEqual(M.decide(1, None, self.band, unknown=True), ("keep", "unknown"))
        self.assertEqual(M.decide(1, None, self.band, dungeon=True), ("keep", "dungeon"))

    def test_percentiles(self):
        v = [1.0, 2.0, 3.0, 4.0, 5.0]
        self.assertEqual(M.percentile(v, 0.5), 3.0)
        self.assertEqual(M.percentile(v, 0.25), 2.0)
        self.assertEqual(M.rank_percentile(v, 3.0), 50.0)
        self.assertEqual(M.band_of(1), "1-5")
        self.assertEqual(M.band_of(10), "6-10")
        self.assertEqual(M.band_of(60), "56-60")


class Text(unittest.TestCase):
    def test_spanish_numbers(self):
        self.assertEqual(M.fmt_int(1150), "1.150")
        self.assertEqual(M.fmt_int(23321), "23.321")
        self.assertEqual(M.fmt_minutes(3.0), "~3 min")
        self.assertEqual(M.fmt_minutes(0.4), "<1 min")
        self.assertEqual(M.fmt_minutes(5.5), "~5,5 min")

    def test_why(self):
        self.assertEqual(M.why_line(1150, 3, "keep", "chain", unlocks="Minas de la Muerte"),
                         "+1.150 XP · ~3 min · desbloquea Minas de la Muerte")
        self.assertIn("lenta: 20% de la mediana del 16-20",
                      M.why_line(120, 2, "drop", "slow", band="16-20", rel=0.2))

    def test_dungeon_name(self):
        self.assertEqual(_dungeon_name({"at": [1, 1, 1, "Entrada a las Minas de la Muerte (Arroyo de la Luna)"]}),
                         "Minas de la Muerte")
        self.assertEqual(_dungeon_name({"text": "Opcional (44-54): Zul'Farrak, al noroeste."}), "Zul'Farrak")


class Pipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = run_synthetic()
        cls.q = cls.res["quests"]

    def test_conditions_filter_steps(self):
        self.assertNotIn(7, self.q)                       # paso de guerrero en guía de mago
        self.assertNotIn("s16", self.res["steps"])

    def test_cheap_delivery_kept(self):
        x = self.q[1]
        self.assertEqual(x["decision"], "keep")
        self.assertLess(x["est_minutes"], 1)
        self.assertEqual(x["xp"], 500)

    def test_far_sparse_kill_quest_dropped(self):
        x = self.q[2]
        self.assertGreater(x["est_minutes"], 15)         # 20 muertes con 3 apariciones: reapariciones
        self.assertEqual(x["kills"], 20)
        self.assertEqual(x["xp_kills"], 20 * M.mob_xp(10, 10))
        self.assertEqual(x["decision"], "drop")
        self.assertTrue(x["why"].startswith("+2.200 XP"))

    def test_dependent_of_dropped_is_dropped(self):
        x = self.q[5]
        self.assertEqual((x["decision"], x["reason"]), ("drop", "requires"))
        self.assertEqual(x["blocked_by"], [2])
        self.assertIn("{quest:2}", x["why"])

    def test_weak_opener_kept_by_chain(self):
        x = self.q[3]
        self.assertEqual(x["xp_kills"], 0)                # enemigos grises
        self.assertLess(x["rate"], 100)
        self.assertEqual(x["unlocks"], [4])
        self.assertEqual((x["decision"], x["reason"]), ("keep", "chain"))
        self.assertIn("desbloquea «{quest:4}»", x["why"])
        self.assertEqual(self.q[4]["decision"], "keep")

    def test_unknown_drop_rate_not_filtered(self):
        x = self.q[6]
        self.assertTrue(x["unknown"])
        self.assertIn("drop_rate_unknown:900", x["flags"])
        self.assertEqual((x["decision"], x["reason"]), ("keep", "unknown"))

    def test_estimates_are_marked(self):
        self.assertIn("kill_seconds", self.q[2]["estimated"])

    def test_steps_keyed_by_id(self):
        self.assertEqual(self.res["steps"]["s08"]["quest"], 2)
        self.assertGreater(self.res["steps"]["s08"]["travel_s"], 0)

    def test_band_stats_skip_special_quests(self):
        bands = band_stats([self.res])
        self.assertIn("6-10", bands)
        self.assertEqual(bands["6-10"]["n"], 5)           # 1-5; la 6 (botín desconocido) no cuenta
        self.assertTrue(bands["6-10"]["pooled"])          # menos de MIN_BAND: se juntan bandas vecinas


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Tests de tools/gen_professions.py (solo stdlib).

    python -m unittest discover -s tests -p "test_gen_professions.py" -v

Los que necesitan las fuentes (.cache/wago, el clon de Polestar en SENDA_POLESTAR y forever-db) se saltan si no
están; los de la programación dinámica usan datos sintéticos y se ejecutan siempre.
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import gen_professions as gp  # noqa: E402

GENERAL = REPO / "data" / "knowledge" / "general"
GENERATED = ["alchemy", "blacksmithing", "enchanting", "engineering", "leatherworking", "tailoring", "cooking", "firstaid"]


def _sources():
    wago = gp.wago_dir(None, must_exist=True)
    pol = os.environ.get("SENDA_POLESTAR")
    fdb = gp.default_foreverdb()
    if not (wago / "SkillLineAbility.csv").exists():
        return None
    from fetch_wago import missing
    if missing(wago) or not pol or not (Path(pol) / gp.EXTRACT_REL).exists() or not fdb:
        return None
    return wago, Path(pol), fdb


def _recipe(spell, learn, yellow, grey, reagents=((1, 1),), item=None, ups=1, cost=0):
    green = (yellow + grey) // 2
    return gp.Recipe(spell, "tailoring", f"R{spell}", f"R{spell}", item or 10000 + spell, 1.0, list(reagents), learn,
                     yellow, green, grey, ups, "trainer", "sniffed", cost, None, [], "verified")


def _action(r, raw, once=0.0, inter=()):
    return gp.Action(r, list(inter), raw, once, [])


class SkillChance(unittest.TestCase):
    def test_orange_yellow_green_grey(self):
        r = _recipe(1, 10, 20, 40)
        self.assertEqual(r.p(9), 0.0)          # aún no se aprende
        self.assertEqual(r.p(10), 1.0)         # naranja
        self.assertEqual(r.p(19), 1.0)
        self.assertEqual(r.p(20), 1.0)         # amarillo: (40-20)/(40-20)
        self.assertAlmostEqual(r.p(30), 0.5)   # verde
        self.assertAlmostEqual(r.p(39), 0.05)
        self.assertEqual(r.p(40), 0.0)         # gris

    def test_skill_ups_count(self):
        a = _action(_recipe(1, 1, 10, 20, ups=2), 10.0)
        self.assertEqual(gp.gain(a, 5), 2.0)


class DynamicProgramming(unittest.TestCase):
    def test_picks_orange_then_switches_before_grey(self):
        # A: barata, naranja hasta 20, gris a 30. B: cara, naranja de 15 a 50, gris a 60.
        a = _action(_recipe(1, 1, 20, 30), 10.0)
        b = _action(_recipe(2, 15, 50, 60), 40.0)
        path = gp.solve([a, b], 1, 50)
        by_skill = {s: act.recipe.spell for s, act, _ in path}
        self.assertEqual(len(path), 49)
        self.assertEqual(by_skill[1], 1)
        self.assertEqual(by_skill[19], 1)               # naranja y barata
        self.assertEqual(by_skill[29], 2)               # A está casi gris (p = 0.1): B
        self.assertEqual(by_skill[49], 2)
        segs = gp.segments(path)
        self.assertEqual([(s.frm, s.to, s.action.recipe.spell) for s in segs][0][:2], (1, segs[0].to))
        self.assertEqual(segs[-1].to, 50)

    def test_yellow_cheap_beats_orange_expensive(self):
        # C es amarilla (p = (60 - s) / 40) pero diez veces más barata que D, que es naranja.
        c = _action(_recipe(3, 1, 20, 60), 5.0)
        d = _action(_recipe(4, 1, 100, 120), 50.0)
        path = gp.solve([c, d], 20, 40)
        self.assertTrue(all(act.recipe.spell == 3 for _, act, _ in path))
        crafts, effort, reach = gp.route_cost(path)
        expected = sum((60 - 20) / (60 - s) for s in range(20, 40))
        self.assertAlmostEqual(crafts, expected, places=6)
        self.assertEqual(reach, 40)

    def test_stops_where_nothing_gives_points(self):
        e = _action(_recipe(5, 1, 10, 20), 1.0)
        path = gp.solve([e], 1, 50)
        self.assertEqual(path[-1][0], 19)
        self.assertEqual(gp.route_cost(path)[2], 20)

    def test_segments_split_at_rank_caps(self):
        f = _action(_recipe(6, 1, 200, 220), 1.0)
        segs = gp.segments(gp.solve([f], 1, 160))
        self.assertEqual([(s.frm, s.to) for s in segs], [(1, 75), (75, 150), (150, 160)])

    def test_switch_cost_avoids_flip_flop(self):
        # Dos recetas casi iguales: no se alterna entre ellas punto a punto.
        g = _action(_recipe(7, 1, 100, 120), 10.0)
        h = _action(_recipe(8, 1, 100, 120), 10.01)
        segs = gp.segments(gp.solve([g, h], 1, 70))
        self.assertEqual(len(segs), 1)
        self.assertEqual(segs[0].action.recipe.spell, 7)

    def test_intermediate_adds_points(self):
        bolt = _recipe(9, 1, 25, 50, reagents=((2589, 2),), item=2996)
        cloak = _recipe(10, 1, 35, 60, reagents=((2996, 1),))
        a = gp.Action(cloak, [(bolt, 1.0)], 10.0, 0.0, [])
        self.assertEqual(gp.gain(a, 10), 2.0)                 # capa naranja + madeja naranja
        self.assertAlmostEqual(gp.gain(a, 40), (60 - 40) / 25 + (50 - 40) / 25)


@unittest.skipUnless(_sources(), "sin .cache/wago, SENDA_POLESTAR o forever-db")
class RealData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wago, cls.pol, cls.fdb = _sources()
        cls.t = gp.load_tables(cls.wago)

    # (hechizo, amarillo, gris) leídos del SkillLineAbility de Forever 1.60.1.70888
    KNOWN = [(3839, 110, 120), (18401, 210, 215), (2963, 25, 50), (2387, 35, 60), (2964, 70, 85), (3865, 145, 150),
             (8776, 50, 85), (3275, 30, 60), (2330, None, None), (7421, 5, 10)]

    def test_colours_match_csv(self):
        rows = {r["spell"]: r for r in self.t.sla}
        checked = 0
        for spell, yellow, grey in self.KNOWN:
            row = rows.get(spell)
            self.assertIsNotNone(row, spell)
            if yellow is not None:
                self.assertEqual((row["yellow"], row["grey"]), (yellow, grey), spell)
            checked += 1
        self.assertEqual(checked, 10)
        # y los colores de cada tramo generado son los del CSV (salvo la corrección oficial del Tanning Rack)
        for prof in GENERATED:
            d = tomllib.loads((GENERAL / f"professions-{prof}.toml").read_text(encoding="utf-8"))
            for seg in d["route"]:
                if seg.get("train"):
                    continue
                row = rows[seg["spell"]]
                if seg["spell"] in gp.HOTFIXES:
                    continue
                self.assertEqual(seg["colors"][1], row["yellow"], (prof, seg["spell"]))
                self.assertEqual(seg["colors"][3], row["grey"], (prof, seg["spell"]))

    def test_deterministic_and_up_to_date(self):
        out1, _, _ = gp.build_all(self.wago, self.pol, self.fdb)
        out2, _, _ = gp.build_all(self.wago, self.pol, self.fdb)
        self.assertEqual(out1, out2)
        for path, text in out1.items():
            self.assertEqual(path.read_text(encoding="utf-8"), text, f"{path.name}: ejecuta tools/gen_professions.py")


class GeneratedFiles(unittest.TestCase):
    """Comprobaciones sobre los TOML commiteados (no hacen falta las fuentes)."""

    def test_rank_gates_and_routes(self):
        for prof in GENERATED:
            d = tomllib.loads((GENERAL / f"professions-{prof}.toml").read_text(encoding="utf-8"))
            ranks = d["rank"]
            self.assertEqual([r["max"] for r in ranks], [75, 150, 225, 300], prof)
            self.assertEqual(ranks[0]["level"], 1, prof)                  # Aprendiz a nivel 1 en Forever
            if d["prof_kind"] == "primary":
                self.assertEqual([(r["skill"], r["level"]) for r in ranks], [(0, 1), (50, 10), (125, 20), (200, 35)], prof)
            trains = [s for s in d["route"] if s.get("train")]
            self.assertEqual([s["train"] for s in trains], ["Oficial", "Experto", "Artesano"], prof)
            for s in trains:
                gate = next(r for r in ranks if r["name"] == s["train"])
                self.assertEqual((s["from"], s["level"]), (gate["skill"], gate["level"]), prof)
            segs = sorted((s for s in d["route"] if not s.get("train")), key=lambda s: s["from"])
            self.assertEqual(segs[0]["from"], 1, prof)
            self.assertEqual(segs[-1]["to"], 300, prof)
            for a, b in zip(segs, segs[1:]):
                self.assertEqual(a["to"], b["from"], (prof, a["name"], b["name"]))   # sin huecos
            for s in segs:
                for cap in (75, 150, 225):
                    self.assertFalse(s["from"] < cap < s["to"], (prof, s["name"], "cruza el tope", cap))
                learn, yellow, green, grey = s["colors"]
                self.assertLessEqual(learn, s["from"], (prof, s["name"]))       # se aprende antes de usarla
                self.assertLess(s["from"], grey, (prof, s["name"]))
                self.assertLessEqual(learn, yellow)
                self.assertLessEqual(yellow, green)
                self.assertLessEqual(green, grey)
                self.assertGreaterEqual(s["n"], 1)
                self.assertIn(s["status"], ("verified", "unverified"))
                self.assertTrue(s["sources"])
                self.assertTrue(s["name"])

    def test_trainers_by_faction_with_coordinates(self):
        d = tomllib.loads((GENERAL / "professions-tailoring.toml").read_text(encoding="utf-8"))
        ali = [t for t in d["trainer"] if t["faction"] == "Alliance"]
        names = {t["name"] for t in ali}
        self.assertTrue({"Georgio Bolero", "Jormund Stonebrow", "Timothy Worthington"} <= names, names)
        expert = [t for t in ali if "Experto" in t["ranks"]]
        self.assertEqual({t["name"] for t in expert}, {"Georgio Bolero", "Timothy Worthington"})
        artisan = [t for t in ali if "Artesano" in t["ranks"]]
        self.assertEqual({t["name"] for t in artisan}, {"Timothy Worthington"})
        for t in ali:
            if "at" in t:
                self.assertTrue(0 <= t["at"][1] <= 100 and 0 <= t["at"][2] <= 100, t)
        # Alianza primero: Ventormenta, Forjaz, Darnassus
        self.assertEqual(d["trainer"][0]["faction"], "Alliance")
        self.assertEqual(d["trainer"][0]["at"][0], 1453)


class CheckWithoutSources(unittest.TestCase):
    def test_check_skips_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            err = io.StringIO()
            env = {"SENDA_POLESTAR": "", "SENDA_WAGO": tmp}
            old = {k: os.environ.get(k) for k in env}
            os.environ.update(env)
            try:
                with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                    rc = gp.main(["--check", "--wago", tmp])
            finally:
                for k, v in old.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
            self.assertEqual(rc, 0)
            self.assertIn("sin fuentes", err.getvalue())


if __name__ == "__main__":
    unittest.main()

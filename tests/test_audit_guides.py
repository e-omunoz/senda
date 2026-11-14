"""Tests de tools/audit_guides.py y tools/foreverdb/corrections.py, y la auditoría real de las tres guías.

    python -m unittest discover -s tests -p "test_*.py" -v

La auditoría real (AuditRealGuidesTest) solo corre si está forever-db en .cache/foreverdb
(`python tools/fetch_foreverdb.py`): falla con cualquier error y escribe los avisos en stderr.
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

import audit_guides as A  # noqa: E402
import build  # noqa: E402
from foreverdb import corrections as C  # noqa: E402

FOREVERDB = REPO / ".cache" / "foreverdb"
ALLIANCE = 1 | 4 | 8 | 64 | (1 << 32)


# ------------------------------------------------------------------------------------------- base falsa
def quest(qid, *, races=ALLIANCE, classes=0, min_level=1, starters=None, finishers=None, pre_all=(), pre_any=(),
          crumb_for=0, excl=None):
    return {"id": qid, "name": f"Q{qid}", "races": races, "classes": classes, "requiredLevel": min_level,
            "starters": {"npc": [], "object": [], "item": [], **(starters or {})},
            "finishers": {"npc": [], "object": [], **(finishers or {})},
            "preQuestGroup": list(pre_all), "preQuestSingle": list(pre_any), "breadcrumbFor": crumb_for,
            "exclusiveTo": excl}


class FakeDB:
    def __init__(self, quests=(), npcs=None, objects=None):
        self.quests = {q["id"]: q for q in quests}
        self.npcs = npcs or {}
        self.objects = objects or {}

    def quest(self, q):
        return self.quests.get(q)

    def npc(self, n):
        return self.npcs.get(n)

    def object(self, o):
        return self.objects.get(o)


def npc(nid, *spawns):
    return {"id": nid, "name": f"N{nid}", "spawns": [list(s) + [None] for s in spawns], "altSpawns": []}


GNOME = A.Character("g", "Gnome", "WARLOCK", "Alliance")
HUMAN = A.Character("h", "Human", "MAGE", "Alliance")


def steps(*raw, levels=(10, 12), optional_ids=()):
    out = []
    for i, r in enumerate(raw):
        r = dict(r)
        r.setdefault("id", f"s{i:02d}")
        if r["id"] in optional_ids:
            r["optional"] = True
        out.append(A.FlatStep(i, r, "g/sec", "data/guides/g/sec.toml", False, {}, levels, levels[0]))
    return out


def run(db, sts, ch=GNOME):
    rep = A.Report()
    A.check_entities(db, sts, ch, rep)
    A.check_route(db, sts, ch, rep)
    return rep


def codes(rep, level="error"):
    return sorted(i.code for i in rep.issues if i.level == level)


# ------------------------------------------------------------------------------------------- comprobaciones
class EntityChecks(unittest.TestCase):
    def setUp(self):
        self.db = FakeDB([quest(1, starters={"npc": [10]}, finishers={"npc": [11]})],
                         {10: npc(10, (1426, 30.0, 70.0)), 11: npc(11, (1426, 40.0, 70.0)),
                          12: npc(12, (1453, 50.0, 50.0))})

    def test_good_route_is_clean(self):
        rep = run(self.db, steps({"do": "accept", "quest": 1, "npc": 10, "at": [1426, 30.4, 70.4]},
                                 {"do": "turnin", "quest": 1, "npc": 11, "at": [1426, 40.0, 70.0]}))
        self.assertEqual(rep.issues, [])

    def test_wrong_giver_and_ender(self):
        rep = run(self.db, steps({"do": "accept", "quest": 1, "npc": 11, "at": [1426, 40.0, 70.0]},
                                 {"do": "turnin", "quest": 1, "npc": 10, "at": [1426, 30.0, 70.0]}))
        self.assertEqual(codes(rep), ["wrong-ender", "wrong-giver"])

    def test_missing_npc_and_quest(self):
        rep = run(self.db, steps({"do": "accept", "quest": 2, "npc": 99, "at": [1426, 1, 1]}))
        self.assertIn("npc-missing", codes(rep))
        self.assertIn("quest-missing", codes(rep))

    def test_at_far_and_other_map(self):
        rep = run(self.db, steps({"do": "accept", "quest": 1, "npc": 10, "at": [1426, 32.0, 70.0]},
                                 {"do": "turnin", "quest": 1, "npc": 11, "at": [1453, 40.0, 70.0]}))
        self.assertEqual(codes(rep), ["at-far", "at-other-map"])
        far = [i for i in rep.issues if i.code == "at-far"][0]
        self.assertIn("a 2.0", far.msg)

    def test_unnamed_step_far_from_giver_is_a_warning(self):
        rep = run(self.db, steps({"do": "accept", "quest": 1, "at": [1426, 60.0, 70.0]},
                                 {"do": "turnin", "quest": 1, "npc": 11, "at": [1426, 40.0, 70.0]}))
        self.assertEqual(codes(rep), [])
        self.assertEqual(codes(rep, "warning"), ["at-unnamed-far"])


class RouteChecks(unittest.TestCase):
    def test_race_and_class_masks(self):
        db = FakeDB([quest(1, races=1), quest(2, classes=128)])
        rep = run(db, steps({"do": "accept", "quest": 1}, {"do": "accept", "quest": 2},
                            {"do": "turnin", "quest": 1}, {"do": "turnin", "quest": 2}))
        self.assertEqual(codes(rep), ["class", "race"])
        self.assertEqual(codes(run(db, steps({"do": "accept", "quest": 1}, {"do": "turnin", "quest": 1}), HUMAN)), [])

    def test_prerequisites(self):
        db = FakeDB([quest(1), quest(2, pre_all=[1]), quest(3, pre_any=[1, 4]), quest(4, races=1)])
        ok = steps({"do": "accept", "quest": 1}, {"do": "turnin", "quest": 1},
                   {"do": "accept", "quest": 2}, {"do": "turnin", "quest": 2},
                   {"do": "accept", "quest": 3}, {"do": "turnin", "quest": 3})
        self.assertEqual(codes(run(db, ok)), [])
        late = steps({"do": "accept", "quest": 1}, {"do": "accept", "quest": 2}, {"do": "turnin", "quest": 1},
                     {"do": "turnin", "quest": 2})
        self.assertEqual(codes(run(db, late)), ["pre-order"])
        missing = steps({"do": "accept", "quest": 2}, {"do": "turnin", "quest": 2})
        self.assertEqual(codes(run(db, missing)), ["pre-missing"])
        # opcional: solo aviso
        opt = steps({"do": "accept", "quest": 2}, {"do": "turnin", "quest": 2}, optional_ids=("s00",))
        self.assertEqual(codes(run(db, opt)), [])
        self.assertEqual(codes(run(db, opt), "warning"), ["pre-missing"])
        # obligatoria detrás de una previa que solo se entrega en pasos opcionales
        po = steps({"do": "accept", "quest": 1}, {"do": "turnin", "quest": 1}, {"do": "accept", "quest": 2},
                   {"do": "turnin", "quest": 2}, optional_ids=("s00", "s01"))
        self.assertEqual(codes(run(db, po)), ["pre-optional"])

    def test_prerequisite_of_another_race_is_ignored(self):
        db = FakeDB([quest(1, races=1), quest(2, pre_all=[1])])
        self.assertEqual(codes(run(db, steps({"do": "accept", "quest": 2}, {"do": "turnin", "quest": 2}))), [])

    def test_breadcrumb_after_its_target(self):
        db = FakeDB([quest(1, crumb_for=2), quest(2)])
        rep = run(db, steps({"do": "accept", "quest": 2}, {"do": "accept", "quest": 1},
                            {"do": "turnin", "quest": 1}, {"do": "turnin", "quest": 2}))
        self.assertEqual(codes(rep), ["crumb-late"])

    def test_exclusive(self):
        db = FakeDB([quest(1, excl=[2]), quest(2)])
        rep = run(db, steps({"do": "accept", "quest": 1}, {"do": "accept", "quest": 2},
                            {"do": "turnin", "quest": 1}, {"do": "turnin", "quest": 2}))
        self.assertIn("exclusive", codes(rep))

    def test_order_and_duplicates(self):
        db = FakeDB([quest(1)])
        rep = run(db, steps({"do": "turnin", "quest": 1}, {"do": "accept", "quest": 1},
                            {"do": "complete", "quest": 1}, {"do": "accept", "quest": 1},
                            {"do": "turnin", "quest": 1}))
        self.assertEqual(codes(rep), ["complete-after-turnin", "dup-accept", "dup-turnin", "turnin-before-accept"])

    def test_turnin_without_accept_unless_dungeon_or_item(self):
        db = FakeDB([quest(1), quest(2, starters={"item": [5]}), quest(3)])
        rep = run(db, steps({"do": "turnin", "quest": 1}, {"do": "turnin", "quest": 2},
                            {"do": "dungeon", "quests": [3]}, {"do": "turnin", "quest": 3}))
        self.assertEqual(codes(rep), ["turnin-no-accept"])

    def test_level(self):
        db = FakeDB([quest(1, min_level=14), quest(2, min_level=11)])
        rep = run(db, steps({"do": "accept", "quest": 1}, {"do": "turnin", "quest": 1}))
        self.assertEqual(codes(rep), ["level"])
        rep = run(db, steps({"do": "accept", "quest": 1, "reqlevel": 14}, {"do": "turnin", "quest": 1}))
        self.assertEqual(codes(rep), [])
        self.assertEqual(codes(rep, "warning"), ["level-section"])
        rep = run(db, steps({"do": "accept", "quest": 2, "reqlevel": 9}, {"do": "turnin", "quest": 2}))
        self.assertEqual(codes(rep, "warning"), [])  # la ruta llega al 10... y el paso dice 9: aviso solo si baja
        self.assertEqual(codes(rep), ["level"])

    def test_class_quest_late(self):
        db = FakeDB([quest(1, classes=256, min_level=10)])
        sts = steps({"do": "accept", "quest": 1}, {"do": "turnin", "quest": 1}, levels=(30, 31))
        self.assertEqual(codes(run(db, sts), "warning"), ["class-late"])

    def test_reviewed_doubts(self):
        db = FakeDB([quest(1, classes=256, min_level=10)])
        sts = steps({"do": "accept", "quest": 1, "id": "rev-1"}, {"do": "turnin", "quest": 1}, levels=(30, 31))
        A.REVIEWED[("class-late", "rev-1")] = "probado"
        try:
            rep = run(db, sts)
        finally:
            del A.REVIEWED[("class-late", "rev-1")]
        self.assertEqual(codes(rep, "warning"), [])
        self.assertEqual(codes(rep, "reviewed"), ["class-late"])


class FilterChecks(unittest.TestCase):
    def test_shared_step_needs_race_and_class_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = root / "a.toml"
            p.write_text("", encoding="utf-8")
            db = FakeDB([quest(1, races=64), quest(2, races=64 | 4), quest(3, classes=256)])
            sec = {"step": [{"id": "x1", "do": "accept", "quest": 1},
                            {"id": "x2", "do": "accept", "quest": 2, "if": {"race": ["Gnome"]}},
                            {"id": "x3", "do": "accept", "quest": 3},
                            {"id": "x4", "do": "accept", "quest": 1, "if": {"race": ["Gnome", "Human"]}}]}
            rep = A.Report()
            A.check_filters(db, [("shared:a", p, sec)], root, "Alliance", rep)
            got = sorted((i.step, i.code) for i in rep.errors)
            self.assertEqual(got, [("x1", "needs-race-filter"), ("x3", "needs-class-filter"),
                                   ("x4", "needs-race-filter")])


class FlattenTest(unittest.TestCase):
    def test_section_and_step_filters(self):
        secs = [("g/a", REPO / "x.toml", {"levels": [1, 5], "step": [
                    {"id": "a1", "do": "note"}, {"id": "a2", "do": "note", "if": {"race": ["Human"]}},
                    {"id": "a3", "do": "level", "level": 8}]}),
                ("g/b", REPO / "y.toml", {"levels": [5, 6], "if": {"class": ["MAGE"]}, "step": [{"id": "b1", "do": "note"}]}),
                ("g/c", REPO / "z.toml", {"levels": [6, 7], "step": [{"id": "c1", "do": "note"},
                                                                     {"id": "c2", "do": "note", "if": {"prof": ["x"]}}]})]
        out = A.flatten(REPO, secs, GNOME)
        self.assertEqual([s.id for s in out], ["a1", "a3", "c1"])
        self.assertEqual(out[-1].level, 8)  # no baja de un `do = "level"` anterior


# ------------------------------------------------------------------------------------------- correcciones
class CorrectionsTest(unittest.TestCase):
    def tables(self):
        return {"quest": [{"id": 1, "min_level": 5, "races": 77}, {"id": 2}, {"id": 3}, {"id": 4}, {"id": 5}],
                "quest_start": [{"quest": 1, "kind": "npc", "id": 10}, {"quest": 1, "kind": "object", "id": 7}],
                "quest_end": [], "quest_objective": [],
                "quest_prereq": [{"quest": 2, "pre": 1, "mode": "all"},
                                 {"quest": 3, "pre": 1, "mode": "any", "breadcrumb": True},
                                 {"quest": 3, "pre": 2, "mode": "all"},
                                 {"quest": 4, "pre": 5, "mode": "all"}]}

    def test_set_fields_starts_and_prereqs(self):
        t = self.tables()
        done = C.apply_quests(t, {"quests": {
            "1": {"set": {"minLevel": 8, "start": {"npc": [11], "object": [], "item": []}, "excl": [2]}},
            "2": {"set": {"pre": [], "preAny": [], "breadcrumbs": [1]}},
            "3": {"set": {"pre": [4], "preAny": [4]}}}})
        q1 = [r for r in t["quest"] if r["id"] == 1][0]
        self.assertEqual(q1["min_level"], 8)
        self.assertEqual(t["quest_start"], [{"id": 11, "kind": "npc", "quest": 1}])
        pre = sorted((r["quest"], r["pre"], r["mode"], bool(r.get("breadcrumb"))) for r in t["quest_prereq"])
        # 2: la previa dura pasa a miga; 3: conserva su miga y su previa pasa a 4 (any, como en Polestar)
        self.assertEqual(pre, [(2, 1, "any", True), (3, 1, "any", True), (3, 4, "any", False), (4, 5, "all", False)])
        self.assertEqual(done[1]["extra"], {"excl": [2]})

    def test_remove_and_breadcrumb_for(self):
        t = self.tables()
        C.apply_quests(t, {"quests": {"5": {"remove": True}, "2": {"set": {"breadcrumbFor": 3}}}})
        self.assertNotIn(5, [r["id"] for r in t["quest"]])
        pre = sorted((r["quest"], r["pre"], bool(r.get("breadcrumb"))) for r in t["quest_prereq"])
        self.assertEqual(pre, [(2, 1, False), (3, 1, True), (3, 2, True)])

    def test_senda_layer_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, senda = Path(tmp) / "fdb", Path(tmp) / "senda"
            (root / "corrections").mkdir(parents=True)
            senda.mkdir()
            (root / "corrections" / "quests.json").write_text(json.dumps(
                {"7": {"set": {"pre": [1], "minLevel": 3}, "note": "a"}}), encoding="utf-8")
            (senda / "quests.json").write_text(json.dumps(
                {"_": "x", "7": {"set": {"pre": []}, "note": "b"}}), encoding="utf-8")
            corr = C.load(root, senda)
            self.assertEqual(corr["quests"]["7"]["set"], {"pre": [], "minLevel": 3})
            self.assertEqual(corr["quests"]["7"]["_from"], ["forever-db", "senda"])
            self.assertNotIn("_", corr["quests"])

    def test_spawn_overrides(self):
        ov = C.spawn_overrides({"npcs": {"5": {"addSpawns": {"1420": {"f": "e", "pts": [[61.4, 53.4]]}}}}}, "npcs")
        self.assertEqual(ov, {5: {"maps": {1420: [[61.4, 53.4]]}, "all": False}})

    def test_senda_corrections_file_is_well_formed(self):
        data = json.loads((REPO / "data" / "corrections" / "quests.json").read_text(encoding="utf-8"))
        for k, rec in data.items():
            if k.startswith("_"):
                continue
            self.assertTrue(k.isdigit(), k)
            self.assertTrue(rec.get("note") and rec.get("source"), f"{k}: sin nota o fuente")
            self.assertTrue(rec.get("set") or rec.get("remove"), k)


class FollowupBreadcrumbsTest(unittest.TestCase):
    def test_breadcrumbs_are_not_followups(self):
        """Una miga no es dependiente (saltarla no salta su destino); va aparte, en RegisterBreadcrumbs."""
        fixture = REPO / "tests" / "fixtures" / "repo"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            shutil.copytree(fixture, root)
            p = root / "data/guides/gnome-warlock/01-coldridge.toml"
            extra = ""
            for i, q in enumerate((1717, 1716, 1738)):
                extra += (f'\n[[step]]\nid = "coldridge-y{i:02d}"\ndo = "accept"\nquest = {q}\nnpc = 6122\n'
                          f'at = [1426, 30, 70]\ntext = "x"\nstatus = "unverified"\n')
            p.write_text(p.read_text(encoding="utf-8") + extra, encoding="utf-8")
            (root / "data/prereq.json").write_text(
                json.dumps({"edges": [[1716, 1738]], "breadcrumbs": [[1717, 1716]]}), encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = build.main(["--root", str(root)])
            self.assertEqual(rc, 0, err.getvalue())
            text = (root / "addon/Senda/Guides/Followups.lua").read_text(encoding="utf-8")
            self.assertIn('RegisterFollowups("1716>1738")', text)
            self.assertIn('RegisterBreadcrumbs("1717>1716")', text)


# ------------------------------------------------------------------------------------------- guías reales
NODES = [{"id": 2, "map": 1453, "name": "Stormwind, Elwynn", "faction": "alliance"},
         {"id": 6, "map": 1455, "name": "Ironforge, Dun Morogh", "faction": "alliance"},
         {"id": 8, "map": 1432, "name": "Thelsamar, Loch Modan", "faction": "alliance"},
         {"id": 7, "map": 1437, "name": "Menethil Harbor, Wetlands", "faction": "alliance"},
         {"id": 11, "map": 1411, "name": "Orgrimmar, Durotar", "faction": "horde"}]


def flights(*raw, ch=GNOME, level="error", optional_ids=()):
    rep = A.Report()
    A.check_flights(steps(*raw, optional_ids=optional_ids), ch, rep, NODES, level)
    return rep


class FlightChecks(unittest.TestCase):
    """Cada `fly` va a un nodo que el personaje ya conoce en ese punto de su ruta."""

    def test_fly_to_unknown_node_is_an_error(self):
        rep = flights({"do": "fly", "zone": 1432, "id": "fly-th"})
        self.assertEqual(codes(rep), ["fly-unknown-node"])
        self.assertEqual([i.step for i in rep.errors], ["fly-th"])

    def test_known_after_getfp_by_id_or_name(self):
        for node in ("8", "Thelsamar"):
            rep = flights({"do": "getfp", "node": node}, {"do": "fly", "zone": 1432})
            self.assertEqual(rep.issues, [], node)

    def test_getfp_after_the_fly_does_not_count(self):
        rep = flights({"do": "fly", "zone": 1432}, {"do": "getfp", "node": "8"})
        self.assertEqual(codes(rep), ["fly-unknown-node"])

    def test_optional_getfp_does_not_count(self):
        rep = flights({"do": "getfp", "node": "8", "id": "g"}, {"do": "fly", "zone": 1432}, optional_ids=("g",))
        self.assertEqual(codes(rep), ["fly-unknown-node"])

    def test_fp_filter_on_the_step_is_enough(self):
        self.assertEqual(flights({"do": "fly", "zone": 1432, "if": {"fp": ["8"]}}).issues, [])
        self.assertEqual(flights({"do": "fly", "zone": 1432, "if": {"fp": ["Thelsamar"]}}).issues, [])
        # filtra por otro nodo, o justo al revés (nofp): no vale
        self.assertEqual(codes(flights({"do": "fly", "zone": 1432, "if": {"fp": ["6"]}})), ["fly-unknown-node"])
        self.assertEqual(codes(flights({"do": "fly", "zone": 1432, "if": {"nofp": ["8"]}})), ["fly-unknown-node"])

    def test_node_field_wins_over_zone(self):
        rep = flights({"do": "getfp", "node": "6"}, {"do": "fly", "zone": 1432, "node": "Ironforge"})
        self.assertEqual(rep.issues, [])

    def test_horde_report_level_and_faction_nodes(self):
        orc = A.Character("o", "Orc", "WARRIOR", "Horde")
        rep = flights({"do": "fly", "zone": 1411}, ch=orc, level="warning")
        self.assertEqual(codes(rep, "warning"), ["fly-unknown-node"])
        self.assertEqual(codes(rep), [])
        # un nodo de la Alianza no existe para la Horda
        rep = flights({"do": "fly", "zone": 1432}, ch=orc, level="warning")
        self.assertEqual(codes(rep, "warning"), ["fly-no-node"])

    def test_free_flight_is_exempt(self):
        self.assertEqual(codes(flights({"do": "fly", "zone": 1432, "id": "other-fly"})), ["fly-unknown-node"])
        self.assertEqual(flights({"do": "fly", "zone": 1432, "id": next(iter(A.FREE_FLIGHTS))}).issues, [])

    def test_real_wetlands_entry(self):
        """La entrada de Los Humedales no manda volar a Thelsamar a quien no lo conoce."""
        import tomllib
        data = tomllib.loads((REPO / "data/shared/a26-los-humedales.toml").read_text(encoding="utf-8"))
        by_id = {s["id"]: s for s in data["step"]}
        self.assertEqual(by_id["a26wl-004"]["if"], {"fp": ["8"]})
        self.assertEqual(by_id["a26wl-ne-02"]["do"], "getfp")
        self.assertNotIn("if", by_id["a26wl-ne-02"])
        self.assertEqual(by_id["a26wl-ne-01"]["if"], {"nofp": ["8"]})


@unittest.skipUnless((FOREVERDB / "data" / "quest.jsonl").exists(), "sin forever-db en .cache (tools/fetch_foreverdb.py)")
class AuditRealGuidesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = A.open_foreverdb(FOREVERDB)
        cls.rep = A.audit(cls.db, REPO, A.DEFAULT_GUIDES)

    def test_no_errors(self):
        for w in self.rep.warnings:
            print(f"\n[audit] {w}", file=sys.stderr)
        self.assertEqual([str(e) for e in self.rep.errors], [])

    def test_corrections_are_applied(self):
        q1716 = self.db.quest(1716)
        self.assertEqual(q1716["preQuestGroup"], [])
        self.assertIn(1717, q1716["breadcrumbs"])           # Senda: 1717 es una miga, no un requisito
        self.assertIsNone(self.db.quest(2358))              # forever-db: «remove» (Horns of Nez'ra)
        self.assertEqual(self.db.quest(465)["preQuestSingle"], [98221])  # forever-db: pre de 465

    def test_prereq_snapshot_is_current(self):
        """data/prereq.json es lo que sale hoy de forever-db + correcciones (`build.py --refresh-prereq`)."""
        pre = build.foreverdb_prereq(REPO)
        snap = build.read_prereq_snapshot(build.Paths(REPO))
        self.assertEqual(snap["edges"], [tuple(e) for e in pre["edges"]])
        self.assertEqual(snap["breadcrumbs"], [tuple(e) for e in pre["breadcrumbs"]])
        self.assertIn((1717, 1716), snap["breadcrumbs"])
        self.assertNotIn((1717, 1716), snap["edges"])


if __name__ == "__main__":
    unittest.main()

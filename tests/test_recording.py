"""Tests de tools/ingest_recording.py y tools/route_report.py con SavedVariables sintéticos.

Ejecutar: python -m unittest tests.test_recording -v
Los fixtures se construyen aquí (registros del esquema 2 de addon/Senda/Recorder/Session.lua) para que cada
número esperado se pueda comprobar a mano.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import ingest_recording as ing  # noqa: E402
import route_report as rr  # noqa: E402

EPOCH = 1793000000
CHAR = "abc123def4"


def chunk(seq, epoch, records, char=CHAR):
    """Un fragmento: cabecera + registros (dt, tipo, *campos); dt en décimas de segundo."""
    lines = ["\t".join(map(str, ["c", 0, seq, epoch, char, 2, "1.60.1"]))]
    for dt, kind, *rest in records:
        lines.append("\t".join(map(str, [kind, dt, *rest])))
    return "\n".join(lines)


def lua_db(chunks, maps=None, extra=""):
    """SavedVariables de Senda con `chunks` = {seq: texto}."""
    body = ",\n".join(f"[{k}] = {json.dumps(v)}" for k, v in chunks.items())
    maps_txt = ",\n".join(f"[{m}] = {{ [1] = {w}, [2] = {h} }}" for m, (w, h) in (maps or {}).items())
    return (f'SendaRecorderDB = {{\n["schema"] = 2,\n["install"] = "abcdefghijkl",\n["seq"] = {max(chunks)},\n'
            f'["dropped"] = 0,\n["entries"] = {{}},\n{extra}["maps"] = {{\n{maps_txt}\n}},\n["chunks"] = {{\n{body}\n}},\n}}\n')


def ingest_text(text):
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "Senda.lua"
        f.write_text(text, encoding="utf-8")
        return ing.ingest_db(ing.read_db(f))


def passes_of(doc, step):
    return [p for p in doc["passes"] if p["step"] == step]


class IngestTimes(unittest.TestCase):
    def base_session(self):
        # tiempos en décimas: 0 s paso 1 (login); 60 s paso 2; AFK de 100 s a 500 s; paso 3 a 540 s; fin a 640 s
        return [
            (0, "l"), (0, "s", "g1", "g1-001", "login", 5, 0, 1),
            (600, "s", "g1", "g1-002", "next", 5, 100, 2),
            (1000, "a", 1), (5000, "a", 0), (5100, "x", 200, 5),
            (5400, "s", "g1", "g1-003", "next", 5, 300, 3),
            (5500, "d"), (6400, "o"),
        ]

    def test_afk_counts_zero_and_cap(self):
        doc = ingest_text(lua_db({1: chunk(1, EPOCH, self.base_session())}))
        p2 = passes_of(doc, "g1-002")[0]
        # 40 s antes de ausentarse + 0 (AFK 400 s) + 10 + 30 = 80 s
        self.assertEqual(p2["time"], 80.0)
        self.assertEqual(p2["afk"], 400.0)
        self.assertEqual(p2["xp"], 200)
        self.assertTrue(p2["completed"] and not p2["partial"])
        p1 = passes_of(doc, "g1-001")[0]
        self.assertEqual(p1["time"], 60.0)
        self.assertTrue(p1["partial"], "la entrada al primer paso (login) no se vio")
        p3 = passes_of(doc, "g1-003")[0]
        self.assertEqual((p3["time"], p3["deaths"]), (100.0, 1))  # 10 s hasta la muerte + 90 s hasta salir
        self.assertTrue(p3["open"] and not p3["completed"], "no se llegó a salir del paso 3")

    def test_idle_gap_capped_at_five_minutes(self):
        recs = [(0, "l"), (0, "s", "g1", "g1-001", "next", 1, 0, 1), (6000, "x", 10, 1), (6100, "o")]
        doc = ingest_text(lua_db({1: chunk(1, EPOCH, recs)}))
        p = passes_of(doc, "g1-001")[0]
        self.assertEqual(p["time"], 300.0 + 10.0)
        self.assertEqual(p["idle"], 300.0)  # 600 s - 300 s de tope
        self.assertEqual(doc["sessions"][0]["active"], 310.0)

    def test_xp_per_hour_and_session_totals(self):
        doc = ingest_text(lua_db({1: chunk(1, EPOCH, self.base_session())}))
        s = doc["sessions"][0]
        self.assertEqual(s["active"], 60 + 80 + 10 + 90 - 0)  # = 240: hasta 640 s menos 400 s de AFK
        self.assertEqual(s["xp"], 200)
        self.assertEqual(s["xp_per_hour"], round(200 * 3600 / 240))
        self.assertEqual((s["deaths"], s["afk"]), (1, 400.0))

    def test_chunks_in_order_and_clock_continues(self):
        # el reloj sigue entre fragmentos de una sesión (mismo epoch); se dan en el orden contrario
        c1 = chunk(1, EPOCH, [(0, "l"), (0, "s", "g1", "g1-001", "next", 1, 0, 1)])
        c2 = chunk(2, EPOCH, [(600, "s", "g1", "g1-002", "next", 1, 0, 2), (900, "o")])
        doc = ingest_text(lua_db({2: c2, 1: c1}))
        self.assertEqual(len(doc["sessions"]), 1)
        self.assertEqual(passes_of(doc, "g1-001")[0]["time"], 60.0)
        self.assertEqual(passes_of(doc, "g1-002")[0]["time"], 30.0)

    def test_reload_continues_the_pass_and_offline_time_is_free(self):
        s1 = chunk(1, EPOCH, [(0, "l"), (0, "s", "g1", "g1-005", "next", 1, 0, 5), (300, "o")])
        s2 = chunk(2, EPOCH + 86400, [(0, "l"), (0, "s", "g1", "g1-005", "login", 1, 0, 5),
                                      (200, "s", "g1", "g1-006", "next", 1, 0, 6), (250, "o")])
        doc = ingest_text(lua_db({1: s1, 2: s2}))
        self.assertEqual(len(doc["sessions"]), 2)
        p = passes_of(doc, "g1-005")[0]
        self.assertEqual(p["time"], 50.0)  # 30 s + 20 s; el día entre sesiones no cuenta
        self.assertEqual(p["segments"], 2)
        self.assertFalse(p["partial"])


class IngestPasses(unittest.TestCase):
    def test_back_is_a_revisit_and_skip_is_not_completed(self):
        recs = [(0, "l"), (0, "s", "g1", "g1-001", "next", 1, 0, 1),
                (100, "s", "g1", "g1-002", "next", 1, 0, 2),
                (200, "s", "g1", "g1-001", "back", 1, 0, 1),     # Atrás: revisita
                (250, "s", "g1", "g1-002", "next", 1, 0, 2),     # vuelve a la frontera
                (400, "s", "g1", "g1-003", "skip", 1, 0, 3),     # 002 se abandona con Saltar
                (500, "s", "g1", "g1-004", "next", 1, 0, 4),     # 003 sale con next
                (600, "o")]
        doc = ingest_text(lua_db({1: chunk(1, EPOCH, recs)}))
        p1 = passes_of(doc, "g1-001")
        self.assertEqual(len(p1), 1, "la revisita no abre una pasada nueva")
        self.assertEqual(p1[0]["time"], 10.0)
        self.assertEqual(doc["revisits"], [{"guide": "g1", "step": "g1-001", "time": 5.0, "visits": 1}])
        p2 = passes_of(doc, "g1-002")[0]
        self.assertEqual(p2["time"], 10.0 + 15.0)  # 10 s antes de Atrás + 15 s después
        self.assertEqual(p2["left"], "skip")
        self.assertFalse(p2["completed"])
        self.assertTrue(passes_of(doc, "g1-003")[0]["completed"])

    def test_guide_end_closes_the_pass(self):
        recs = [(0, "l"), (0, "s", "g1", "g1-009", "next", 1, 0, 9), (100, "s", "g1", "-", "end", 1, 0, 9),
                (150, "o")]
        doc = ingest_text(lua_db({1: chunk(1, EPOCH, recs)}))
        p = passes_of(doc, "g1-009")[0]
        self.assertEqual((p["left"], p["completed"], p["time"]), ("end", True, 10.0))

    def test_yards_use_map_size_and_skip_teleports(self):
        # mapa de 5000 x 2000 yd: 0.001 del mapa en x = 5 yd; en y = 2 yd
        recs = [(0, "l"), (0, "s", "g1", "g1-001", "next", 1, 0, 1),
                (10, "p", 7, 1000, 5000), (110, "p", 7, 3000, 5000),    # 1000 yd en 10 s = 100 yd/s: hogar, no cuenta
                (210, "p", 7, 3040, 5000),                               # 20 yd en 10 s: andar
                (310, "p", 8, 3040, 5000),                               # otro mapa: no cuenta
                (410, "p", 8, 3040, 5600),                               # 0.06 * 2000 = 120 yd en 10 s
                (500, "o")]
        doc = ingest_text(lua_db({1: chunk(1, EPOCH, recs)}, maps={7: (5000, 2000), 8: (5000, 2000)}))
        self.assertEqual(passes_of(doc, "g1-001")[0]["yards"], 140.0)
        self.assertEqual(doc["sessions"][0]["yards"], 140)
        self.assertEqual(len(doc["sessions"][0]["trail"]), 5)

    def test_quests_duo_and_combat(self):
        recs = [(0, "l"), (0, "u", 0), (0, "s", "g1", "g1-001", "next", 1, 0, 1),
                (100, "k", 1), (300, "k", 0), (310, "q", "a", 179), (320, "q", "c", 179), (330, "q", "t", 179),
                (340, "u", 1), (400, "o")]
        doc = ingest_text(lua_db({1: chunk(1, EPOCH, recs)}))
        p = passes_of(doc, "g1-001")[0]
        self.assertEqual((p["combat"], p["turnins"], p["duo"]), (20.0, 1, True))
        s = doc["sessions"][0]
        self.assertEqual((s["accepts"], s["completes"], s["turnins"], s["duo"]), (1, 1, 1, True))


class IngestPrivacyAndRobustness(unittest.TestCase):
    def test_bad_records_are_rejected_and_names_cannot_enter(self):
        recs = [(0, "l"), (0, "s", "g1", "g1-001", "next", 1, 0, 1),
                (10, "s", "Zyxwvut de Reino", "g1-002", "next", 1, 0, 2),   # espacios: no es un id
                (20, "z", "algo"), (30, "q", "a", "NombreMision"), (40, "k", 7),
                (50, "x", 5, 1), (100, "o")]
        doc = ingest_text(lua_db({1: chunk(1, EPOCH, recs)}))
        self.assertEqual(doc["stats"]["bad_records"], 4)
        self.assertEqual([p["step"] for p in doc["passes"]], ["g1-001"])
        self.assertNotIn("Zyxwvut", json.dumps(doc))

    def test_ids_are_hashed(self):
        doc = ingest_text(lua_db({1: chunk(1, EPOCH, [(0, "l"), (50, "o")])}))
        text = json.dumps(doc)
        self.assertNotIn(CHAR, text)
        self.assertNotIn("abcdefghijkl", text)  # id de instalación
        self.assertEqual(len(doc["sessions"][0]["char"]), 8)

    def test_no_sessions_returns_none(self):
        self.assertIsNone(ingest_text(lua_db({1: chunk(1, EPOCH, [])})))

    def test_deterministic_output_file(self):
        text = lua_db({1: chunk(1, EPOCH, [(0, "l"), (0, "s", "g1", "g1-001", "next", 1, 0, 1), (90, "o")])})
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "Senda.lua"
            src.write_text(text, encoding="utf-8")
            out1, out2 = Path(d) / "o1", Path(d) / "o2"
            self.assertEqual(ing.main([str(src), "--out", str(out1)]), 0)
            self.assertEqual(ing.main([str(src), "--out", str(out2)]), 0)
            f1, f2 = list(out1.glob("*.json")), list(out2.glob("*.json"))
            self.assertEqual(len(f1), 1)
            self.assertRegex(f1[0].name, r"^2026-\d\d-\d\d-[0-9a-f]{10}\.json$")
            self.assertEqual(f1[0].read_bytes(), f2[0].read_bytes())


def recording(passes, sessions=None, maps=None):
    return {"schema": 2, "id": "x", "date": "2026-11-12", "passes": passes, "sessions": sessions or [], "maps": maps or {}}


def ps(step, idx, minutes, char="c1", start=0, xp=0, **kw):
    p = {"guide": "g1", "step": step, "idx": idx, "char": char, "start": start, "time": minutes * 60.0, "xp": xp,
         "completed": True, "open": False, "partial": False}
    p.update(kw)
    return p


class RouteReport(unittest.TestCase):
    def test_score_formats(self):
        a = rr.parse_score({"guide": "g1", "steps": {"s1": {"est_minutes": 2, "xp": 100}, "s2": 3}})
        b = rr.parse_score({"steps": [{"id": "s1", "minutes": 2.5}]})
        c = rr.parse_score({"s1": {"est_min": 4}})
        self.assertEqual((a["s1"]["min"], a["s1"]["xp"], a["s2"]["min"]), (2.0, 100.0, 3.0))
        self.assertEqual(b["s1"]["min"], 2.5)
        self.assertEqual(c["s1"]["min"], 4.0)
        self.assertEqual(rr.parse_score([1, 2]), {})

    def test_ratio_flags_and_median_error(self):
        docs = [recording([ps("s1", 1, 2.0), ps("s2", 2, 10.0), ps("s2", 2, 14.0, char="c2"), ps("s3", 3, 1.0),
                           ps("s4", 4, 3.0)])]
        scores = {"g1": {"s1": {"min": 2.0, "xp": 50.0}, "s2": {"min": 4.0, "xp": None}, "s3": {"min": 4.0, "xp": None},
                         "s5": {"min": 1.0, "xp": None}}}
        rep = rr.build_report(docs, scores)
        rows = {r["step"]: r for r in rep["guides"][0]["steps"]}
        self.assertEqual(rows["s1"]["ratio"], 1.0)
        self.assertEqual((rows["s2"]["n"], rows["s2"]["measured_min"], rows["s2"]["ratio"]), (2, 12.0, 3.0))
        self.assertTrue(rows["s2"]["off"] and rows["s3"]["off"] and not rows["s1"]["off"])  # 3x y 0.25x
        self.assertIsNone(rows["s4"]["ratio"])
        self.assertEqual(rep["guides"][0]["uncovered"], ["s4"])
        self.assertEqual(rep["guides"][0]["unmeasured"], 1)
        # |1-1| = 0, |3-1| = 2, |0.25-1| = 0.75: mediana 0.75
        self.assertEqual(rep["median_error"], 0.75)
        self.assertEqual(rep["steps_compared"], 3)
        text = rr.format_report(rep)
        self.assertIn("s2", text)
        self.assertIn("NO CUMPLE", text)
        self.assertIn("a más del doble", text)

    def test_partial_open_skipped_and_duplicates_are_left_out(self):
        dup = ps("s1", 1, 2.0, start=100)
        docs = [recording([dup, ps("s1", 1, 50.0, char="c2", partial=True), ps("s1", 1, 60.0, char="c3", open=True),
                           ps("s1", 1, 70.0, char="c4", completed=False, left="skip")]),
                recording([dict(dup)])]  # el mismo paso en otro volcado solapado
        rep = rr.build_report(docs, {"g1": {"s1": {"min": 2.0, "xp": None}}})
        row = rep["guides"][0]["steps"][0]
        self.assertEqual((row["n"], row["measured_min"]), (1, 2.0))
        rep2 = rr.build_report(docs, {"g1": {"s1": {"min": 2.0, "xp": None}}}, include_partial=True)
        self.assertEqual(rep2["guides"][0]["steps"][0]["n"], 2)

    def test_traces_export_walks(self):
        trail = [[0, 7, 1000, 5000], [2, 7, 1040, 5000], [4, 7, 1080, 5000], [6, 7, 1120, 5000],   # 3 x 20 yd a 10 yd/s
                 [100, 7, 1120, 5000],                                                             # hueco largo: otra caminata
                 [102, 7, 1900, 5000]]                                                             # salto: otra
        sess = [{"id": "sess0001", "start": EPOCH, "trail": trail}]
        docs = [recording([], sess, {"7": [5000.0, 2000.0]})]
        with tempfile.TemporaryDirectory() as d:
            out = rr.export_traces(docs, Path(d) / "traces")
            self.assertEqual([f.name for f in out], ["sess0001.json"])
            doc = json.loads(out[0].read_text(encoding="utf-8"))
            self.assertEqual(len(doc["walks"]), 1, "solo la primera caminata llega a 3 puntos y 30 yd")
            self.assertEqual(doc["walks"][0]["yards"], 60)
            self.assertEqual(doc["walks"][0]["points"][0], [0, 1000, 5000])

    def test_main_with_files(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "rec").mkdir()
            (root / "scores").mkdir()
            (root / "rec" / "2026-11-12-aaaa.json").write_text(json.dumps(recording([ps("s1", 1, 3.0)])), encoding="utf-8")
            (root / "scores" / "g1.json").write_text(json.dumps({"steps": {"s1": {"est_minutes": 3.0}}}), encoding="utf-8")
            code = rr.main(["--recordings", str(root / "rec"), "--scores", str(root / "scores"), "--check", "--no-traces"])
            self.assertEqual(code, 0)
            self.assertEqual(rr.main(["--recordings", str(root / "none"), "--scores", str(root / "scores")]), 2)
            (root / "scores" / "g1.json").write_text(json.dumps({"steps": {"s1": {"est_minutes": 30.0}}}), encoding="utf-8")
            self.assertEqual(rr.main(["--recordings", str(root / "rec"), "--scores", str(root / "scores"), "--check",
                                      "--no-traces"]), 1)


if __name__ == "__main__":
    unittest.main()

"""Tests del buscador de objetos: compilación de data/lookup/ a addon/Senda_Lookup (tools/build.py), nombres del
buscador y el viaje de ida y vuelta de /senda volcar (SendaNamesDB.litem) por tools/import_names.py.

    python -m unittest tests.test_lookup -v
"""
from __future__ import annotations

import contextlib
import io
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import build  # noqa: E402
import import_names  # noqa: E402
import localenames as ln  # noqa: E402
from common import Paths  # noqa: E402

FIXTURE = REPO / "tests" / "fixtures" / "repo"

ITEMS = {"meta": {"forever_db_version": "2026.11.1", "client_build": "1.60.1.70532"}, "items": {
    "159": {"s": [["n", 3577, 100], ["o", 3658, 100], ["n", 3141, 10.4]], "n": 257, "v": [[6736]],
            "q": [[8, 1], [381, 0]], "nq": 7},
    "2676": {"s": [["o", 276, 100], ["n", 1397, 75]]},
    "10005": {"o": [3181, 3182], "no": 4},
    "11243": {"g": [[1446, 54, 28.7]], "q": [[4041, 0]]},
    "5000": {"s": [["i", 159]]},
}}
PLACES = {"meta": {}, "places": {"n": {"1397": [1426, 42.2, 36.6, 0, 19], "6736": [1438, 55.6, 59.8, 1, 1]},
                                 "o": {"276": [0, -120.5, 88, 36, 1]}}}

# Lo que escribe el cliente (formato de SavedVariables): UTF-8 sin escapar y algún \ddd.
SAVED = """
SendaNamesDB = {
\t["version"] = 1,
\t["locales"] = {
\t\t["esES"] = {
\t\t\t["build"] = "1.60.2.71000",
\t\t\t["date"] = "2026-11-12",
\t\t\t["done"] = true,
\t\t\t["quest"] = {
\t\t\t},
\t\t\t["item"] = {
\t\t\t\t[159] = "Agua de manantial refrescante",
\t\t\t},
\t\t\t["litem"] = {
\t\t\t\t[2676] = "Brillaverde",
\t\t\t\t[10005] = "Cuerno gigantesco de Margol",
\t\t\t\t[11243] = "Elixir de Videre \\195\\161",
\t\t\t\t[5000] = "Cofre con tilde: \\195\\186nico",
\t\t\t},
\t\t\t["missing"] = {
\t\t\t\t["litem"] = {
\t\t\t\t\t[99999] = true,
\t\t\t\t},
\t\t\t},
\t\t},
\t\t["enUS"] = {
\t\t\t["build"] = "1.60.2.71000",
\t\t\t["date"] = "2026-11-12",
\t\t\t["litem"] = {
\t\t\t\t[2676] = "Brightleaf",
\t\t\t},
\t\t},
\t},
}
"""


def quiet(fn, *a, **kw):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = fn(*a, **kw)
    return rc, out.getvalue(), err.getvalue()


def write_names(path: Path, locale: str, names: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"kind": "item", "locale": locale, "names": names}, ensure_ascii=False),
                    encoding="utf-8")


class Repo:
    """Copia del repositorio de pruebas con un data/lookup/ pequeño."""

    def __enter__(self) -> Path:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name) / "repo"
        shutil.copytree(FIXTURE, root)
        lk = root / "data" / "lookup"
        lk.mkdir(parents=True)
        (lk / "items.json").write_text(json.dumps(ITEMS), encoding="utf-8")
        (lk / "places.json").write_text(json.dumps(PLACES), encoding="utf-8")
        write_names(lk / "locale/enUS/items.json", "enUS", {
            "159": {"name": "Refreshing Spring Water", "source": "forever-db"},
            "2676": {"name": "Brightleaf Old", "source": "forever-db"},
            "10005": {"name": "Margol's Gigantic Horn", "source": "forever-db"},
        })
        return root

    def __exit__(self, *exc):
        self._tmp.cleanup()


class CompileTests(unittest.TestCase):
    def test_entry_encoding(self):
        self.assertEqual(build.lookup_entry(ITEMS["items"]["159"]),
                         "s=n3577:100,o3658:100,n3141:10.4;N=257;v=6736;q=8c,381;Q=7")
        self.assertEqual(build.lookup_entry(ITEMS["items"]["10005"]), "o=3181,3182;O=4")
        self.assertEqual(build.lookup_entry(ITEMS["items"]["11243"]), "g=1446:54:28.7;q=4041")
        self.assertEqual(build.lookup_entry(ITEMS["items"]["5000"]), "s=i159")

    def test_build_writes_the_on_demand_addon(self):
        with Repo() as root:
            rc, out, err = quiet(build.main, ["--root", str(root)])
            self.assertEqual(rc, 0, err)
            d = root / "addon" / "Senda_Lookup"
            self.assertEqual(sorted(p.name for p in d.iterdir()),
                             ["Items.lua", "Names_enUS.lua", "Places.lua", "Senda_Lookup.toc"])
            toc = (d / "Senda_Lookup.toc").read_text(encoding="utf-8")
            self.assertIn("## LoadOnDemand: 1", toc)
            self.assertIn("## Interface: 16001", toc)
            files = [l for l in toc.splitlines() if l.endswith(".lua")]
            self.assertEqual(files, ["Items.lua", "Places.lua", "Names_enUS.lua"])
            items = (d / "Items.lua").read_text(encoding="utf-8")
            self.assertIn('[159] = "s=n3577:100,o3658:100,n3141:10.4;N=257;v=6736;q=8c,381;Q=7",', items)
            self.assertIn('[10005] = "o=3181,3182;O=4",', items)
            self.assertIn("items = 5 }", items)
            places = (d / "Places.lua").read_text(encoding="utf-8")
            self.assertIn('[1397] = "1426,42.2,36.6,0,19",', places)
            self.assertIn('[276] = "0,-120.5,88,36,1",', places)  # mazmorra: uiMap 0 y yardas
            names = (d / "Names_enUS.lua").read_text(encoding="utf-8")
            self.assertIn('Senda_Lookup.names["enUS"] = "159\\tRefreshing Spring Water\\n2676\\tBrightleaf Old', names)
            # solo los objetos del buscador, aunque haya más nombres
            write_names(root / "data/lookup/locale/enUS/items.json", "enUS", {
                "159": {"name": "A", "source": "forever-db"}, "424242": {"name": "No es del buscador", "source": "x"}})
            quiet(build.main, ["--root", str(root)])
            self.assertNotIn("424242", (d / "Names_enUS.lua").read_text(encoding="utf-8"))
            rc, _, err = quiet(build.main, ["--root", str(root), "--check"])
            self.assertEqual(rc, 0, err)

    def test_nothing_without_lookup_data(self):
        with Repo() as root:
            shutil.rmtree(root / "data" / "lookup")
            rc, _, err = quiet(build.main, ["--root", str(root)])
            self.assertEqual(rc, 0, err)
            self.assertEqual(sorted(p.name for p in (root / "addon" / "Senda_Lookup").iterdir()), ["Senda_Lookup.toc"])

    def test_guide_names_win_over_forever_db(self):
        with Repo() as root:
            write_names(root / "data/locale/enUS/items.json", "enUS", {
                "159": {"name": "Refreshing Spring Water (guide)", "source": "senda"}})
            names = build.lookup_names(Paths(root), "enUS")
            self.assertEqual(names[159]["name"], "Refreshing Spring Water (guide)")
            self.assertEqual(names[10005]["name"], "Margol's Gigantic Horn")


class DumpRoundTripTests(unittest.TestCase):
    """/senda volcar -> SendaNamesDB.litem -> tools/import_names.py -> data/lookup/locale -> Senda_Lookup/Names_*.lua."""

    def test_litem_goes_to_the_lookup_not_to_data_locale(self):
        with Repo() as root:
            sv = root / "Senda.lua"
            sv.write_bytes(SAVED.encode("utf-8"))
            db = import_names.read_saved_variables(sv)
            self.assertEqual(db["locales"]["esES"]["litem"][11243], "Elixir de Videre á")
            rc, out, err = quiet(import_names.main, [str(sv), "--root", str(root)])
            self.assertEqual(rc, 0, err)
            src = "ingame:1.60.2.71000:2026-11-12"
            es = json.loads((root / "data/lookup/locale/esES/items.json").read_text(encoding="utf-8"))["names"]
            self.assertEqual(es["2676"], {"name": "Brillaverde", "source": src})
            self.assertEqual(es["11243"]["name"], "Elixir de Videre á")
            self.assertEqual(es["5000"]["name"], "Cofre con tilde: único")
            self.assertEqual(sorted(es), ["10005", "11243", "2676", "5000"])
            # lo que usan las guías (`item`) sigue yendo a data/locale (Senda), sin mezclarse
            guide = json.loads((root / "data/locale/esES/items.json").read_text(encoding="utf-8"))["names"]
            self.assertEqual(list(guide), ["159"])
            # el inglés del juego gana al de forever-db; lo que el volcado no trae se queda
            en = json.loads((root / "data/lookup/locale/enUS/items.json").read_text(encoding="utf-8"))["names"]
            self.assertEqual(en["2676"], {"name": "Brightleaf", "source": src})
            self.assertEqual(en["159"]["source"], "forever-db")
            # informe: nuevos, sin respuesta y cobertura de nombres del buscador
            self.assertIn("Objetos del buscador: nuevos 4", out)
            self.assertIn("litem 1", out)
            self.assertIn("Cobertura de nombres del buscador en esES: 5/5 (100.0 %)", out)  # 159 por la guía + 4 volcados
            self.assertIn("Cobertura de nombres del buscador en enUS: 3/5 (60.0 %)", out)
            # segunda pasada sin cambios
            before = (root / "data/lookup/locale/esES/items.json").read_bytes()
            rc, out2, _ = quiet(import_names.main, [str(sv), "--root", str(root)])
            self.assertEqual(rc, 0)
            self.assertEqual(before, (root / "data/lookup/locale/esES/items.json").read_bytes())
            self.assertIn("nuevos 0; iguales 4", out2)
            self.assertIn("Objetos del buscador: nuevos 4; iguales 0; cambios entre parches 0; respaldos corregidos 0.", out)
            self.assertIn("respaldos corregidos 1", out)

    def test_round_trip_reaches_the_addon_files(self):
        with Repo() as root:
            sv = root / "Senda.lua"
            sv.write_bytes(SAVED.encode("utf-8"))
            quiet(import_names.main, [str(sv), "--root", str(root)])
            rc, _, err = quiet(build.main, ["--root", str(root)])
            self.assertEqual(rc, 0, err)
            d = root / "addon" / "Senda_Lookup"
            self.assertEqual(sorted(p.name for p in d.iterdir()),
                             ["Items.lua", "Names_enUS.lua", "Names_esES.lua", "Places.lua", "Senda_Lookup.toc"])
            es = (d / "Names_esES.lua").read_text(encoding="utf-8")
            self.assertIn("2676\\tBrillaverde", es)
            self.assertIn("5000\\tCofre con tilde: único", es)
            self.assertIn("159\\tAgua de manantial refrescante", es)  # el objeto de la guía también entra
            self.assertIn("Names_esES.lua", (d / "Senda_Lookup.toc").read_text(encoding="utf-8"))
            rc, _, err = quiet(build.main, ["--root", str(root), "--check"])
            self.assertEqual(rc, 0, err)

    def test_dump_without_litem_leaves_lookup_alone(self):
        with Repo() as root:
            sv = root / "Senda.lua"
            sv.write_bytes(SAVED.replace('["litem"] = {', '["nolitem"] = {').encode("utf-8"))
            rc, out, err = quiet(import_names.main, [str(sv), "--root", str(root)])
            self.assertEqual(rc, 0, err)
            self.assertFalse((root / "data/lookup/locale/esES").exists())
            self.assertNotIn("Objetos del buscador", out)


class RepoDataTests(unittest.TestCase):
    """El addon generado que está en el repositorio."""

    def test_committed_data_matches_items_json(self):
        items = json.loads((REPO / "data/lookup/items.json").read_text(encoding="utf-8"))["items"]
        lua = (REPO / "addon/Senda_Lookup/Items.lua").read_text(encoding="utf-8")
        rows = re.findall(r'^  \[(\d+)\] = "([^"]*)",$', lua, re.M)
        self.assertEqual(len(rows), len(items))
        field = re.compile(r"^(?:[sgvqo]=[^;]+|[NQO]=\d+)$")
        for ident, raw in rows:
            self.assertIn(ident, items)
            self.assertTrue(raw, ident)
            for part in raw.split(";"):
                self.assertRegex(part, field, f"{ident}: {raw}")

    def test_names_cover_nearly_every_item(self):
        items = json.loads((REPO / "data/lookup/items.json").read_text(encoding="utf-8"))["items"]
        lua = (REPO / "addon/Senda_Lookup/Names_enUS.lua").read_text(encoding="utf-8")
        named = set(re.findall(r"(?:^|\\n|\")(\d+)\\t", lua))
        self.assertGreaterEqual(len(named & set(items)) / len(items), 0.99)

    def test_toc_is_load_on_demand(self):
        toc = (REPO / "addon/Senda_Lookup/Senda_Lookup.toc").read_text(encoding="utf-8")
        self.assertIn("## LoadOnDemand: 1", toc)
        for f in re.findall(r"^(\w+\.lua)$", toc, re.M):
            self.assertTrue((REPO / "addon/Senda_Lookup" / f).is_file(), f)


if __name__ == "__main__":
    unittest.main()

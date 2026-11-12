"""Tests de los nombres del cliente: tools/import_names.py, tools/localenames.py, la compilación de
data/locale/ en tools/build.py, la ficha de nombre en tools/validate.py y las fichas del importador de Polestar.

    python -m unittest tests.test_import_names -v
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
import import_names  # noqa: E402
import localenames as ln  # noqa: E402
import validate  # noqa: E402
from common import Paths  # noqa: E402
from polestar.spanish import Namer, npc_with  # noqa: E402

FIXTURE = REPO / "tests" / "fixtures" / "repo"

# Lo que escribe el cliente de WoW: varias variables, comentarios `-- [n]`, UTF-8 sin escapar, algún \ddd y
# claves numéricas.
SAVED = """
SendaRecorderDB = {
\t["obs"] = {
\t\t{
\t\t\t["kind"] = "accept",
\t\t}, -- [1]
\t},
}
SendaNamesDB = {
\t["version"] = 1,
\t["locales"] = {
\t\t["esES"] = {
\t\t\t["build"] = "1.60.2.71000",
\t\t\t["date"] = "2026-11-12",
\t\t\t["done"] = true,
\t\t\t["quest"] = {
\t\t\t\t[155] = "El camino de Ventormenta",
\t\t\t\t[456] = "El equilibrio de la naturaleza",
\t\t\t\t[783] = "Una amenaza interior",
\t\t\t\t[900] = "Misi\\195\\179n con escapes",
\t\t\t},
\t\t\t["npc"] = {
\t\t\t\t[467] = "El traidor Defias",
\t\t\t\t[2079] = "Conservador Ilthalaine",
\t\t\t},
\t\t\t["item"] = {
\t\t\t\t[6948] = "Piedra de hogar",
\t\t\t},
\t\t\t["spell"] = {
\t\t\t},
\t\t\t["map"] = {
\t\t\t\t[1438] = "Teldrassil",
\t\t\t},
\t\t\t["missing"] = {
\t\t\t\t["quest"] = {
\t\t\t\t\t[99999] = true,
\t\t\t\t},
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


def write_json(path: Path, kind: str, locale: str, names: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"kind": kind, "locale": locale, "names": names}, ensure_ascii=False),
                    encoding="utf-8")


class TempDir:
    def __enter__(self) -> Path:
        self._tmp = tempfile.TemporaryDirectory()
        return Path(self._tmp.name)

    def __exit__(self, *exc):
        self._tmp.cleanup()


class ImportNamesTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "data").mkdir()
        self.sv = self.root / "Senda.lua"
        self.sv.write_bytes(SAVED.encode("utf-8"))
        # lo que ya había: un volcado de un parche anterior, respaldo de Polestar y uno igual
        write_json(self.root / "data/locale/esES/quests.json", "quest", "esES", {
            "155": {"name": "El camino a Ventormenta", "source": "ingame:1.60.1.70291:2026-10-01"},
            "456": {"name": "El equilibrio de la natura", "source": "polestar-esES"},
            "783": {"name": "Una amenaza interior", "source": "polestar-esES"},
            "1000": {"name": "Solo en Polestar", "source": "polestar-esES"},
        })

    def tearDown(self):
        self._tmp.cleanup()

    def load(self, kind: str) -> dict:
        f = self.root / "data/locale/esES" / f"{ln.KINDS[kind]}.json"
        return json.loads(f.read_text(encoding="utf-8"))["names"]

    def test_reads_saved_variables(self):
        db = import_names.read_saved_variables(self.sv)
        self.assertIsNotNone(db)
        d = db["locales"]["esES"]
        self.assertEqual(d["build"], "1.60.2.71000")
        self.assertEqual(d["quest"][155], "El camino de Ventormenta")
        self.assertEqual(d["quest"][900], "Misión con escapes")  # \ddd = bytes UTF-8
        self.assertEqual(d["npc"][2079], "Conservador Ilthalaine")

    def test_import_writes_files_with_ingame_source(self):
        rc, out, err = quiet(import_names.main, [str(self.sv), "--root", str(self.root)])
        self.assertEqual(rc, 0, err)
        src = "ingame:1.60.2.71000:2026-11-12"
        q = self.load("quest")
        self.assertEqual(q["155"], {"name": "El camino de Ventormenta", "source": src})
        self.assertEqual(q["456"], {"name": "El equilibrio de la naturaleza", "source": src})
        self.assertEqual(q["783"]["source"], src)  # mismo nombre: pasa a verificado en el juego
        self.assertEqual(q["1000"]["source"], "polestar-esES")  # lo que el volcado no trae se queda
        self.assertEqual(self.load("npc")["467"]["name"], "El traidor Defias")
        self.assertEqual(self.load("map")["1438"]["name"], "Teldrassil")
        self.assertEqual(self.load("item")["6948"]["source"], src)
        self.assertFalse((self.root / "data/locale/esES/spells.json").exists(), "tipo vacío: sin archivo")
        self.assertFalse((self.root / "data/locale/esES/objects.json").exists())
        # informe: cambio entre parches y respaldo corregido
        self.assertIn("quest:155: «El camino a Ventormenta» (ingame:1.60.1.70291:2026-10-01) -> «El camino de Ventormenta»",
                      out)
        self.assertIn("Cambios de nombre entre parches", out)
        self.assertIn("quest:456: «El equilibrio de la natura» (polestar-esES) -> «El equilibrio de la naturaleza»", out)
        self.assertIn("Sin respuesta del cliente: quest 1", out)
        # determinista: segunda pasada sin cambios
        before = (self.root / "data/locale/esES/quests.json").read_bytes()
        rc, out2, _ = quiet(import_names.main, [str(self.sv), "--root", str(self.root)])
        self.assertEqual(rc, 0)
        self.assertEqual(before, (self.root / "data/locale/esES/quests.json").read_bytes())
        self.assertNotIn("Escrito", out2)

    def test_file_format_is_stable(self):
        quiet(import_names.main, [str(self.sv), "--root", str(self.root)])
        text = (self.root / "data/locale/esES/quests.json").read_text(encoding="utf-8")
        lines = text.splitlines()
        self.assertEqual(lines[1], '  "kind": "quest",')
        ids = [int(l.split('"')[1]) for l in lines if l.startswith('    "')]
        self.assertEqual(ids, sorted(ids))
        self.assertNotIn("\r", text)

    def test_dry_run_and_report_file(self):
        before = (self.root / "data/locale/esES/quests.json").read_bytes()
        rep = self.root / "rep.md"
        rc, out, _ = quiet(import_names.main, [str(self.sv), "--root", str(self.root), "--dry-run", "--report", str(rep)])
        self.assertEqual(rc, 0)
        self.assertEqual(before, (self.root / "data/locale/esES/quests.json").read_bytes())
        self.assertFalse((self.root / "data/locale/esES/npcs.json").exists())
        self.assertIn("Cambios de nombre entre parches", rep.read_text(encoding="utf-8"))

    def test_missing_variable_or_file(self):
        other = self.root / "Otro.lua"
        other.write_text("SendaDB = {}\n", encoding="utf-8")
        rc, _, err = quiet(import_names.main, [str(other), "--root", str(self.root)])
        self.assertEqual(rc, 1)
        self.assertIn("SendaNamesDB", err)
        rc, _, _ = quiet(import_names.main, [str(self.root / "no-existe.lua"), "--root", str(self.root)])
        self.assertEqual(rc, 1)

    def test_locale_filter(self):
        rc, _, err = quiet(import_names.main, [str(self.sv), "--root", str(self.root), "--locale", "frFR"])
        self.assertEqual(rc, 1)
        self.assertIn("ningún idioma", err)


class LocaleNamesTests(unittest.TestCase):
    def test_priority(self):
        data: dict = {}
        self.assertEqual(ln.merge(data, "quest", 1, "A", "polestar-esES")[0], "new")
        self.assertEqual(ln.merge(data, "quest", 1, "B", "senda")[0], "renamed")
        self.assertEqual(ln.merge(data, "quest", 1, "C", "polestar-esES")[0], "kept")
        self.assertEqual(data["quest"][1]["name"], "B")
        self.assertEqual(ln.merge(data, "quest", 1, "D", "ingame:1:2026-01-01")[0], "renamed")
        self.assertEqual(ln.merge(data, "quest", 1, "Z", "senda")[0], "kept")
        self.assertEqual(ln.merge(data, "quest", 1, "D", "ingame:2:2026-02-01")[0], "same")
        self.assertEqual(ln.merge(data, "bogus", 1, "x", "senda")[0], "kept")

    def test_clean_and_pack(self):
        self.assertEqual(ln.clean_name(" a\tb\nc "), "a b c")
        self.assertIsNone(ln.clean_name("  "))
        entries = {20: {"name": "B"}, 3: {"name": "A"}}
        self.assertEqual(ln.pack(entries), "3\tA\n20\tB")


class BuildLocaleTests(unittest.TestCase):
    def repo(self, tmp: Path) -> Path:
        root = tmp / "repo"
        shutil.copytree(FIXTURE, root)
        return root

    def test_build_compiles_locale(self):
        with TempDir() as tmp:
            root = self.repo(tmp)
            write_json(root / "data/locale/esES/quests.json", "quest", "esES", {
                "179": {"name": "Avituallamiento \"enano\"", "source": "polestar-esES"},
                "7": {"name": "Kobolds en la cantera", "source": "ingame:1.60.1.70291:2026-11-12"},
            })
            write_json(root / "data/locale/esES/npcs.json", "npc", "esES", {
                "658": {"name": "Sten Brazorrecio", "source": "senda"},
            })
            write_json(root / "data/locale/frFR/npcs.json", "npc", "frFR", {})
            rc, out, err = quiet(build.main, ["--root", str(root)])
            self.assertEqual(rc, 0, err)
            loc = root / "addon/Senda/Locale"
            self.assertEqual(sorted(p.name for p in loc.iterdir()), ["Locale.xml", "Names_esES.lua"])
            lua = (loc / "Names_esES.lua").read_text(encoding="utf-8")
            self.assertIn('Senda.Names:WantsLocale("esES")', lua)
            self.assertIn('N:AddFallback("esES", "quest", "7\\tKobolds en la cantera\\n179\\tAvituallamiento \\"enano\\"")', lua)
            self.assertIn('N:AddFallback("esES", "npc", "658\\tSten Brazorrecio")', lua)
            self.assertIn('<Script file="Names_esES.lua"/>', (loc / "Locale.xml").read_text(encoding="utf-8"))
            rc, _, err = quiet(build.main, ["--root", str(root), "--check"])
            self.assertEqual(rc, 0, err)
            # sin data/locale: Locale.xml vacío y el Names_ generado se borra
            shutil.rmtree(root / "data/locale")
            rc, _, err = quiet(build.main, ["--root", str(root)])
            self.assertEqual(rc, 0, err)
            self.assertEqual(sorted(p.name for p in loc.iterdir()), ["Locale.xml"])
            self.assertNotIn("<Script", (loc / "Locale.xml").read_text(encoding="utf-8"))

    def test_build_fails_on_bad_json(self):
        with TempDir() as tmp:
            root = self.repo(tmp)
            f = root / "data/locale/esES/quests.json"
            f.parent.mkdir(parents=True)
            f.write_text('{"kind": "quest"}', encoding="utf-8")
            rc, _, err = quiet(build.main, ["--root", str(root)])
            self.assertEqual(rc, 1)
            self.assertIn("names", err)

    def test_validate_token_kinds(self):
        with TempDir() as tmp:
            root = self.repo(tmp)
            p = root / "data/guides/gnome-warlock/01-coldridge.toml"
            text = p.read_text(encoding="utf-8")
            text = text.replace('text = "Ve a la cueva ]] [[ ]=]."',
                                'text = "Ve a {map:1426} con {npc:658}, {zona:3} y {quest:x}."', 1)
            p.write_text(text, encoding="utf-8")
            ds = validate.load_and_check(Paths(root))
            msgs = [i.msg for i in ds.errors]
            self.assertTrue(any("ficha desconocida {zona:3}" in m for m in msgs), msgs)
            self.assertTrue(any("ficha sin id numérico: {quest:x}" in m for m in msgs), msgs)
            self.assertFalse(any("{map:1426}" in m or "{npc:658}" in m for m in msgs), msgs)


class SiteResolverTests(unittest.TestCase):
    def test_resolver_order_and_placeholder(self):
        with TempDir() as tmp:
            write_json(tmp / "data/locale/esES/npcs.json", "npc", "esES",
                       {"2079": {"name": "Conservador Ilthalaine", "source": "polestar-esES"}})
            write_json(tmp / "data/locale/enUS/npcs.json", "npc", "enUS",
                       {"2079": {"name": "Conservator Ilthalaine", "source": "polestar-enUS"},
                        "3595": {"name": "Shanda", "source": "polestar-enUS"}})
            r = ln.resolver(tmp / "data")
            self.assertEqual(r("Del {npc:2079}, {npc:3595}, {quest:7}, {foo:1}."),
                             "Del Conservador Ilthalaine, Shanda, Misión #7, {foo:1}.")
            self.assertEqual(r("sin fichas"), "sin fichas")


class ImporterTokenTests(unittest.TestCase):
    def namer(self) -> Namer:
        es = {("npc", 2079): "Conservador Ilthalaine", ("quest", 456): "El equilibrio de la naturaleza",
              ("object", 7): "Cofre"}
        return Namer(lambda kind, i: es.get((kind, int(i))),
                     {"npc:3595": "Shanda", "quest:97977": "Nature's Call", "object:8": "Old Chest"})

    def test_tokens_and_fallbacks(self):
        n = self.namer()
        self.assertEqual(n.quest(456), "«{quest:456}»")
        self.assertEqual(n.token("npc", 2079), "{npc:2079}")
        self.assertEqual(n.token("zone", 1438), "{map:1438}")       # zone de Polestar = uiMapID
        self.assertEqual(n.token("area", 186), "{area:186}")         # subzona: C_Map.GetAreaInfo en el cliente
        self.assertEqual(n.fallback["area"][186], ("Dolanaar", "senda"))
        self.assertEqual(n.token("object", 7), "{obj:7}")
        self.assertEqual(n.token("object", 8), "Old Chest")          # objeto sin nombre esES: escrito
        self.assertEqual(n.token("npc", 3595), "{npc:3595}")         # el cliente lo nombra; respaldo en inglés
        self.assertEqual(n.fallback["npc"][2079], ("Conservador Ilthalaine", "polestar-esES"))
        self.assertEqual(n.fallback["map"][1438], ("Teldrassil", "senda"))
        self.assertNotIn(3595, n.fallback.get("npc", {}))
        self.assertEqual(n.fallback_en["npc"][3595], ("Shanda", "polestar-enUS"))
        self.assertIn("npc:3595 Shanda", n.missing)
        self.assertEqual(n.render("Kill {npc:2079} for {quest:456} in {zone:1438}"),
                         "Kill {npc:2079} for «{quest:456}» in {map:1438}")
        self.assertEqual(n.render("{npc:2079}", tokens=False), "Conservador Ilthalaine")
        self.assertEqual(n.unrender("Coge «{quest:456}» del {npc:2079}."),
                         "Coge «El equilibrio de la naturaleza» del Conservador Ilthalaine.")

    def test_article_uses_known_name(self):
        self.assertEqual(npc_with("de", "Conservador Ilthalaine", "{npc:2079}"), "del {npc:2079}")
        self.assertEqual(npc_with("a", "Centinela Shaya", "{npc:2}"), "a la {npc:2}")
        self.assertEqual(npc_with("de", "Shanda", "{npc:3595}"), "de {npc:3595}")

    def test_prototype_uses_tokens(self):
        sec = (REPO / "data/guides/nightelf-druid-ps/01-teldrassil.toml").read_text(encoding="utf-8")
        self.assertIn("{quest:", sec)
        self.assertIn("{npc:", sec)
        fb = ln.load(REPO / "data", "esES")
        self.assertEqual(fb["quest"][456]["source"] in ("polestar-esES",) or
                         fb["quest"][456]["source"].startswith("ingame:"), True)


if __name__ == "__main__":
    unittest.main()

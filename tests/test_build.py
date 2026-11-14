"""Tests de tools/common.py, tools/validate.py, tools/build.py y tools/package.py (solo stdlib).

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
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import build  # noqa: E402
import package  # noqa: E402
import validate  # noqa: E402
from common import GENERATED_HEADER, LuaError, Paths, lua_key, lua_string, to_lua  # noqa: E402

FIXTURE = REPO / "tests" / "fixtures" / "repo"


def quiet(fn, *a, **kw):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = fn(*a, **kw)
    return rc, out.getvalue(), err.getvalue()


class TempRepo:
    """Copia el fixture a un directorio temporal (los tests nunca escriben en el fixture)."""

    def __enter__(self) -> Path:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "repo"
        shutil.copytree(FIXTURE, self.root)
        return self.root

    def __exit__(self, *exc):
        self._tmp.cleanup()


# ---------------------------------------------------------------------------- serializador
class LuaSerializerTests(unittest.TestCase):
    def test_string_escapes(self):
        self.assertEqual(lua_string('a"b'), '"a\\"b"')
        self.assertEqual(lua_string("a\\b"), '"a\\\\b"')
        self.assertEqual(lua_string("l1\nl2\r\tx"), '"l1\\nl2\\r\\tx"')
        self.assertEqual(lua_string("\x00\x01\x7f"), '"\\000\\001\\127"')
        # dígito tras un escape numérico no debe mezclarse
        self.assertEqual(lua_string("\x01" + "2"), '"\\0012"')

    def test_utf8_passthrough(self):
        s = "Misión «Crestanevada»: ¡ñandú!"
        self.assertEqual(lua_string(s), f'"{s}"')

    def test_long_bracket_text_is_safe(self):
        # Como se usan comillas, ]] [[ ]=] no tienen significado especial.
        self.assertEqual(lua_string("]] [[ ]=]"), '"]] [[ ]=]"')

    def test_keys(self):
        self.assertEqual(lua_key("do"), '["do"]')
        self.assertEqual(lua_key("if"), '["if"]')
        self.assertEqual(lua_key("end"), '["end"]')
        self.assertEqual(lua_key("quest"), "quest")
        self.assertEqual(lua_key("my-key"), '["my-key"]')
        self.assertEqual(lua_key("1abc"), '["1abc"]')
        self.assertEqual(lua_key(3), "[3]")

    def test_values(self):
        self.assertEqual(to_lua(True), "true")
        self.assertEqual(to_lua(False), "false")
        self.assertEqual(to_lua(12), "12")
        self.assertEqual(to_lua(29.9), "29.9")
        self.assertEqual(to_lua([]), "{}")
        self.assertEqual(to_lua([1426, 29.9, 71.2]), "{1426, 29.9, 71.2}")
        self.assertEqual(to_lua({"do": "accept", "quest": 1}), '{ ["do"] = "accept", quest = 1 }')
        with self.assertRaises(LuaError):
            to_lua(float("nan"))
        with self.assertRaises(LuaError):
            to_lua(object())

    def test_multiline_for_lists_of_tables(self):
        out = to_lua({"id": "x", "steps": [{"id": "a"}, {"id": "b"}]})
        self.assertEqual(out, '{\n  id = "x",\n  steps = {\n    { id = "a" },\n    { id = "b" },\n  },\n}')

    def test_key_order(self):
        out = to_lua({"text": "t", "id": "i", "do": "goto"}, key_order=["id", "do"])
        self.assertEqual(out, '{ id = "i", ["do"] = "goto", text = "t" }')


# ---------------------------------------------------------------------------- esquema
class SchemaValidatorTests(unittest.TestCase):
    SCHEMA = {
        "type": "object", "required": ["a"], "additionalProperties": False,
        "properties": {
            "a": {"type": "integer", "minimum": 1, "maximum": 5},
            "b": {"$ref": "#/$defs/pt"},
            "c": {"enum": ["x", "y"]},
            "d": {"type": "string", "pattern": "^[a-z]+$"},
            "e": {"type": ["string", "integer"]},
        },
        "$defs": {"pt": {"type": "array", "minItems": 2, "maxItems": 3,
                         "prefixItems": [{"type": "integer"}, {"type": "number", "maximum": 100}]}},
    }

    def errs(self, v):
        return list(validate.schema_errors(v, self.SCHEMA))

    def test_valid(self):
        self.assertEqual(self.errs({"a": 2, "b": [1, 50.5], "c": "x", "d": "abc", "e": 3}), [])

    def test_errors(self):
        self.assertTrue(self.errs({}))                       # required
        self.assertTrue(self.errs({"a": True}))              # bool no es integer
        self.assertTrue(self.errs({"a": 9}))                 # maximum
        self.assertTrue(self.errs({"a": 1, "z": 1}))         # additionalProperties
        self.assertTrue(self.errs({"a": 1, "b": [1]}))       # minItems
        self.assertTrue(self.errs({"a": 1, "b": [1, 101]}))  # prefixItems + maximum
        self.assertTrue(self.errs({"a": 1, "c": "q"}))       # enum
        self.assertTrue(self.errs({"a": 1, "d": "ABC"}))     # pattern
        self.assertTrue(self.errs({"a": 1, "e": 1.5}))       # type list

    def test_real_schemas_supported(self):
        for name in ("section.schema.json", "guide.schema.json", "knowledge.schema.json"):
            schema = json.loads((REPO / "schema" / name).read_text(encoding="utf-8"))
            list(validate.schema_errors({}, schema))  # no lanza SchemaError


# ---------------------------------------------------------------------------- validación
class ValidationTests(unittest.TestCase):
    def check(self, root: Path) -> validate.Dataset:
        return validate.load_and_check(Paths(root))

    def test_fixture_is_valid(self):
        ds = self.check(FIXTURE)
        self.assertEqual([str(i) for i in ds.errors], [])
        summ = validate.summary(ds)
        g = {x["id"]: x for x in summ["guides"]}
        self.assertEqual(g["gnome-warlock"]["steps"], 4)
        self.assertEqual(g["gnome-warlock"]["verified"], 1)
        self.assertEqual(summ["totals"]["steps"], 5)

    def _edit(self, root: Path, rel: str, old: str, new: str) -> None:
        p = root / rel
        text = p.read_text(encoding="utf-8")
        self.assertIn(old, text)
        p.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")

    def assertIssue(self, ds, level, needle, where=None):
        found = [i for i in ds.issues if i.level == level and needle in i.msg and (where is None or where in i.where)]
        self.assertTrue(found, f"no se encontró {level} {needle!r} en:\n" + "\n".join(map(str, ds.issues)))

    def test_semantic_errors(self):
        sec = "data/guides/gnome-warlock/01-coldridge.toml"
        with TempRepo() as root:
            self._edit(root, sec, 'quest = 179\n', '')                                # accept sin quest
            self._edit(root, sec, 'id = "coldridge-002"', 'id = "shared-001"')       # id duplicado
            self._edit(root, sec, 'at = [1426, 30, 70.5]', 'at = [1426, 130, 70.5]')  # fuera de 0-100
            self._edit(root, "data/guides/human-mage/01-northshire.toml",
                       'sources = ["wiki", "observación"]', '')                      # disputed sin fuentes
            self._edit(root, "data/shared/alliance-test.toml", 'level = 10\n', '')   # level sin level
            self._edit(root, "data/guides/human-mage/guide.toml", '"01-northshire"', '"99-nada"')
            ds = self.check(root)
            self.assertIssue(ds, "error", "exige 'quest'", "paso coldridge-001")
            self.assertIssue(ds, "error", "id de paso duplicado")
            self.assertIssue(ds, "error", "máximo 100", "paso shared-001")
            self.assertIssue(ds, "error", "exige 'level'")
            self.assertIssue(ds, "error", "la sección no existe")
            self.assertIssue(ds, "warning", "disputed")
            self.assertIssue(ds, "warning", "ninguna guía usa esta sección")

    def test_fp_filters_validated(self):
        sec = "data/guides/gnome-warlock/01-coldridge.toml"
        with TempRepo() as root:
            self._edit(root, sec, 'quest = 179\n', 'quest = 179\nif = { fp = ["8"], nofp = ["8"] }\n')
            ds = self.check(root)
            self.assertIssue(ds, "error", "'fp' y 'nofp' con el mismo nodo", "paso coldridge-001")
        with TempRepo() as root:
            self._edit(root, sec, 'quest = 179\n', 'quest = 179\nif = { fp = [] }\n')
            self.assertIssue(self.check(root), "error", "lista no vacía de nodos de vuelo")
        with TempRepo() as root:
            self._edit(root, sec, 'quest = 179\n', 'quest = 179\nif = { nofp = "8" }\n')
            self.assertTrue([i for i in self.check(root).errors if "nofp" in i.where])
        with TempRepo() as root:
            self._edit(root, sec, 'quest = 179\n', 'quest = 179\nif = { fp = ["8", "Thelsamar"], nofp = [6] }\n')
            self.assertEqual([str(i) for i in self.check(root).errors], [])

    def test_verified_requires_sources_and_level_order(self):
        with TempRepo() as root:
            self._edit(root, "data/guides/gnome-warlock/01-coldridge.toml",
                       'sources = ["questie:quest/179"]\n', '')
            self._edit(root, "data/shared/alliance-test.toml", "levels = [6, 12]", "levels = [1, 3]")
            self._edit(root, "data/guides/gnome-warlock/01-coldridge.toml", "levels = [1, 6]", "levels = [2, 6]")
            ds = self.check(root)
            self.assertIssue(ds, "error", "exige 'sources'", "paso coldridge-001")
            self.assertIssue(ds, "warning", "los niveles bajan")

    def test_schema_errors_located(self):
        with TempRepo() as root:
            self._edit(root, "data/guides/gnome-warlock/01-coldridge.toml", 'do = "goto"', 'do = "teleport"')
            self._edit(root, "data/guides/gnome-warlock/01-coldridge.toml", 'npc = 658', 'npc = "658"\nfoo = 1')
            ds = self.check(root)
            self.assertIssue(ds, "error", "no permitido", "paso coldridge-002 · campo 'do'")
            self.assertIssue(ds, "error", "tipo incorrecto", "campo 'npc'")
            self.assertIssue(ds, "error", "campo desconocido 'foo'")

    def test_bad_toml_and_knowledge(self):
        with TempRepo() as root:
            (root / "data/shared/broken.toml").write_text('id = "x\n', encoding="utf-8")
            self._edit(root, "data/knowledge/warlock/talents.toml", 'kind = "talents"', 'kind = "page"')
            ds = self.check(root)
            self.assertIssue(ds, "error", "TOML inválido")
            self.assertIssue(ds, "error", "exige al menos un [[block]]")

    def test_cli_json(self):
        rc, out, _ = quiet(validate.main, ["--root", str(FIXTURE), "--json"])
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertTrue(data["ok"])
        self.assertEqual(data["totals"]["guides"], 2)


# ---------------------------------------------------------------------------- build
class BuildTests(unittest.TestCase):
    def test_fp_filters_compiled(self):
        with TempRepo() as root:
            p = root / "data/guides/gnome-warlock/01-coldridge.toml"
            p.write_text(p.read_text(encoding="utf-8").replace(
                'quest = 179\n', 'quest = 179\nif = { fp = ["8", "Thelsamar"], nofp = ["6"] }\n', 1),
                encoding="utf-8", newline="\n")
            rc, out, err = quiet(build.main, ["--root", str(root)])
            self.assertEqual(rc, 0, err)
            text = (root / "addon/Senda/Guides/gnome-warlock.lua").read_text(encoding="utf-8")
            self.assertIn('["if"] = { fp = {"8", "Thelsamar"}, nofp = {"6"} }', text)

    def test_build_fixture(self):
        with TempRepo() as root:
            rc, out, err = quiet(build.main, ["--root", str(root)])
            self.assertEqual(rc, 0, err)
            g = root / "addon/Senda/Guides"
            k = root / "addon/Senda/Knowledge"
            names = sorted(p.name for p in g.iterdir())
            self.assertEqual(names, ["Followups.lua", "Guides.xml", "Shared.lua", "gnome-warlock.lua", "human-mage.lua"])
            self.assertEqual(sorted(p.name for p in k.iterdir()), ["Knowledge.xml", "general.lua", "warlock.lua"])

            gw = (g / "gnome-warlock.lua").read_bytes()
            self.assertNotIn(b"\r\n", gw)
            text = gw.decode("utf-8")
            self.assertTrue(text.startswith(f"-- {GENERATED_HEADER}\n"))
            self.assertIn("local _, Senda = ...", text)
            self.assertIn('Senda.Guides:RegisterSection({', text)
            self.assertIn('{ id = "coldridge-001", ["do"] = "accept", quest = 179, npc = 658, '
                          'at = {1426, 29.9, 71.2}, text = "Habla con Sten \\"Brazorrecio\\" y coge la misión."', text)
            self.assertIn('tip = "Línea 1\\nLínea 2 con barra \\\\ invertida\\ty tab"', text)
            self.assertIn('["if"] = { class = {"WARLOCK"}, minlevel = 2 }', text)
            self.assertIn('sections = {"coldridge", "alliance-test"}', text)
            for stripped in ("sources", "checked", "nota interna"):
                self.assertNotIn(stripped, text)
            # la sección compartida se registra una sola vez, en Shared.lua
            self.assertNotIn('id = "alliance-test",', text)
            shared = (g / "Shared.lua").read_text(encoding="utf-8")
            self.assertEqual(shared.count("RegisterSection"), 1)
            xml = (g / "Guides.xml").read_text(encoding="utf-8")
            self.assertLess(xml.index("Shared.lua"), xml.index("gnome-warlock.lua"))

            kw = (k / "warlock.lua").read_text(encoding="utf-8")
            self.assertIn("Senda.Knowledge:Register({", kw)
            self.assertIn('note = "Visible para el jugador."', kw)  # en conocimiento note se conserva
            self.assertNotIn("sources", kw)
            self.assertNotIn("checked", (k / "general.lua").read_text(encoding="utf-8"))

            toc = (root / "addon/Senda/Senda.toc").read_text(encoding="utf-8")
            self.assertIn("## Version: 1.2.3\n", toc)
            self.assertIn("## Interface: 16001\n", toc)

            # determinista: un segundo build no cambia nada y --check pasa
            before = {p: p.read_bytes() for p in list(g.iterdir()) + list(k.iterdir())}
            rc, out, err = quiet(build.main, ["--root", str(root)])
            self.assertEqual(rc, 0)
            self.assertIn("0 archivos actualizados", out)
            self.assertEqual(before, {p: p.read_bytes() for p in before})
            rc, _, _ = quiet(build.main, ["--root", str(root), "--check"])
            self.assertEqual(rc, 0)

            # --check detecta cambios y archivos generados sobrantes
            (g / "old-guide.lua").write_text(f"-- {GENERATED_HEADER}\n", encoding="utf-8")
            rc, _, err = quiet(build.main, ["--root", str(root), "--check"])
            self.assertEqual(rc, 1)
            self.assertIn("old-guide.lua", err)
            quiet(build.main, ["--root", str(root)])
            self.assertFalse((g / "old-guide.lua").exists())

    # -- índice de misiones dependientes («Saltar esta misión») ----------------------------------
    def _add_quest_steps(self, root, quests):
        """Añade a la guía gnome-warlock del fixture entrega + coger, en ese orden, por misión."""
        p = root / "data/guides/gnome-warlock/01-coldridge.toml"
        extra = ""
        for i, (q, npc, do) in enumerate(quests):
            extra += (f'\n[[step]]\nid = "coldridge-x{i:02d}"\ndo = "{do}"\nquest = {q}\nnpc = {npc}\n'
                      f'at = [1426, 30, 70]\ntext = "x"\nstatus = "unverified"\n')
        p.write_text(p.read_text(encoding="utf-8") + extra, encoding="utf-8")

    def test_followups_from_snapshot(self):
        """Con data/prereq.json: cierre transitivo, también a través de misiones que ninguna guía usa."""
        with TempRepo() as root:
            self._add_quest_steps(root, [(1001, 5, "accept"), (1002, 6, "accept"), (1004, 7, "accept")])
            (root / "data/prereq.json").write_text(
                json.dumps({"edges": [[179, 1001], [1001, 9999], [9999, 1002], [1001, 1004], [1002, 1002]]}),
                encoding="utf-8")
            rc, _, err = quiet(build.main, ["--root", str(root)])
            self.assertEqual(rc, 0, err)
            text = (root / "addon/Senda/Guides/Followups.lua").read_text(encoding="utf-8")
            self.assertTrue(text.startswith(f"-- {GENERATED_HEADER}\n"))
            self.assertIn("-- Fuente: data/prereq.json", text)
            # 179 -> 1001 -> (9999 ->) 1002 y 1004; 9999 no sale (ninguna guía lo usa); 1002 no depende de sí misma
            self.assertIn('RegisterFollowups("179>1001,1002,1004;1001>1002,1004")', text)
            xml = (root / "addon/Senda/Guides/Guides.xml").read_text(encoding="utf-8")
            self.assertIn("Followups.lua", xml)
            rc, _, _ = quiet(build.main, ["--root", str(root), "--check"])
            self.assertEqual(rc, 0)

    def test_followups_fallback_from_guide_order(self):
        """Sin forever-db ni instantánea: B sigue a A si se coge justo después de entregar A al mismo PNJ."""
        with TempRepo() as root:
            self._add_quest_steps(root, [(2001, 77, "turnin"), (2002, 77, "accept"),
                                         (2003, 88, "turnin"), (2004, 99, "accept")])
            rc, _, err = quiet(build.main, ["--root", str(root)])
            self.assertEqual(rc, 0, err)
            text = (root / "addon/Senda/Guides/Followups.lua").read_text(encoding="utf-8")
            self.assertIn("-- Fuente: orden de las guías", text)
            self.assertIn('RegisterFollowups("2001>2002")', text)  # otro PNJ: no hay relación

    def test_refresh_prereq_needs_foreverdb(self):
        with TempRepo() as root:
            rc, _, err = quiet(build.main, ["--root", str(root), "--refresh-prereq"])
            self.assertEqual(rc, 1)
            self.assertIn("forever-db", err)
            self.assertFalse((root / "data/prereq.json").exists())
            # con una caché mínima, guarda las aristas duras (all sin miga de pan, y any con una sola previa)
            d = root / ".cache/foreverdb/data"
            d.mkdir(parents=True)
            rows = [{"mode": "all", "pre": 1, "quest": 2}, {"mode": "all", "pre": 3, "quest": 2, "breadcrumb": True},
                    {"mode": "any", "pre": 4, "quest": 5}, {"mode": "any", "pre": 6, "quest": 7},
                    {"mode": "any", "pre": 8, "quest": 7}]
            (d / "quest_prereq.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            rc, _, err = quiet(build.main, ["--root", str(root), "--refresh-prereq"])
            self.assertEqual(rc, 0, err)
            snap = json.loads((root / "data/prereq.json").read_text(encoding="utf-8"))
            self.assertEqual(snap["edges"], [[1, 2], [4, 5]])

    def test_build_fails_on_invalid(self):
        with TempRepo() as root:
            p = root / "data/guides/gnome-warlock/01-coldridge.toml"
            p.write_text(p.read_text(encoding="utf-8").replace("quest = 179\n", ""), encoding="utf-8")
            rc, _, err = quiet(build.main, ["--root", str(root)])
            self.assertEqual(rc, 1)
            self.assertIn("01-coldridge.toml [paso coldridge-001 · campo 'quest']", err)
            self.assertFalse((root / "addon/Senda/Guides").exists())


# ---------------------------------------------------------------------------- package
class PackageTests(unittest.TestCase):
    def test_zip_and_install_dev(self):
        with TempRepo() as root:
            quiet(build.main, ["--root", str(root)])
            (root / "addon/Senda/.DS_Store").write_text("x")
            (root / "addon/Senda/notes.bak").write_text("x")
            (root / "LICENSE").write_text("GPL")
            rc, out, err = quiet(package.main, ["--root", str(root)])
            self.assertEqual(rc, 0, err)
            z = root / "dist" / "Senda-1.2.3.zip"
            with zipfile.ZipFile(z) as zf:
                names = zf.namelist()
            self.assertIn("Senda/Senda.toc", names)
            self.assertIn("Senda/Guides/Guides.xml", names)
            # los cinco addons en la raíz del zip, cada uno con su licencia
            for addon in package.ADDONS:
                self.assertIn(f"{addon}/{addon}.toc", names)
                self.assertIn(f"{addon}/LICENSE", names)
            self.assertIn("Senda_Nav/SendaNav.lua", names)
            self.assertEqual({n.split("/")[0] for n in names}, set(package.ADDONS))
            self.assertNotIn("Senda/.DS_Store", names)
            self.assertNotIn("Senda/notes.bak", names)

            addons = root / "fake" / "AddOns"
            other = addons / "Questie"
            other.mkdir(parents=True)
            (other / "Questie.toc").write_text("keep")
            # sin --target: se niega
            rc, _, err = quiet(package.main, ["--root", str(root), "--install-dev"])
            self.assertEqual(rc, 2)
            # carpeta Senda ajena (sin Senda.toc): se niega
            (addons / "Senda").mkdir()
            (addons / "Senda" / "foreign.txt").write_text("x")
            rc, _, err = quiet(package.main, ["--root", str(root), "--install-dev", "--target", str(addons)])
            self.assertEqual(rc, 1)
            self.assertTrue((addons / "Senda" / "foreign.txt").exists())
            shutil.rmtree(addons / "Senda")
            # carpeta Senda_Nav ajena: se niega sin instalar ninguno
            (addons / "Senda_Nav").mkdir()
            rc, _, err = quiet(package.main, ["--root", str(root), "--install-dev", "--target", str(addons)])
            self.assertEqual(rc, 1)
            self.assertFalse((addons / "Senda").exists())
            shutil.rmtree(addons / "Senda_Nav")
            # instalación correcta de los cinco; Questie intacto
            rc, out, err = quiet(package.main, ["--root", str(root), "--install-dev", "--target", str(addons)])
            self.assertEqual(rc, 0, err)
            for addon in package.ADDONS:
                self.assertTrue((addons / addon / f"{addon}.toc").exists())
            self.assertTrue((addons / "Senda_Nav" / "SendaNav.lua").exists())
            self.assertEqual((other / "Questie.toc").read_text(), "keep")
            self.assertEqual(sorted(p.name for p in addons.iterdir()), sorted(["Questie", *package.ADDONS]))
            # otra vez: reemplaza las cinco carpetas
            rc, out, err = quiet(package.main, ["--root", str(root), "--install-dev", "--target", str(addons)])
            self.assertEqual(rc, 0, err)
            # el destino debe llamarse AddOns
            rc, _, _ = quiet(package.main, ["--root", str(root), "--install-dev", "--target", str(root / "fake")])
            self.assertEqual(rc, 2)

    def test_zip_needs_nav_addons(self):
        with TempRepo() as root:
            quiet(build.main, ["--root", str(root)])
            shutil.rmtree(root / "addon" / "Senda_Nav_Kalimdor")
            with self.assertRaises(SystemExit) as cm:
                quiet(package.main, ["--root", str(root)])
            self.assertIn("Senda_Nav_Kalimdor.toc", str(cm.exception))

    def test_changelog_section(self):
        with TempRepo() as root:
            (root / "CHANGELOG.md").write_text(
                "# Cambios\n\n## [1.2.3] - 2026-11-11\n- Nuevo\n\n## [1.2.2]\n- Viejo\n", encoding="utf-8")
            self.assertEqual(package.changelog_section(Paths(root), "1.2.3"), "- Nuevo")


if __name__ == "__main__":
    unittest.main()

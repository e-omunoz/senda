"""Tests del generador de la web (tools/site.py) con un fixture mínimo en una carpeta temporal."""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("senda_site", REPO / "tools" / "site.py")
site = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(site)


def write(root: Path, rel: str, text: str):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")


def make_fixture(root: Path):
    write(root, "data/guides/gnome-warlock/guide.toml", """
        id = "gnome-warlock"
        title = "Brujo gnomo 1-60"
        summary = "Guía de prueba."
        faction = "Alliance"
        races = ["Gnome"]
        classes = ["WARLOCK"]
        sections = ["01-coldridge", "shared:alliance-hub"]
    """)
    write(root, "data/guides/gnome-warlock/01-coldridge.toml", """
        id = "coldridge"
        title = "Valle de Crestanevada"
        levels = [1, 6]
        map = 1426
        summary = "Primeros pasos."

        [[step]]
        id = "coldridge-001"
        do = "accept"
        quest = 179
        npc = 658
        at = [1426, 29.9, 71.2]
        text = "Habla con **Sten** y coge la misión."
        tip = "Consejo <b>experto</b>."
        status = "verified"
        sources = ["questie:quest/179"]
        checked = "2026-11-10"
        link = "brujo/10-19#abisario"

        [[step]]
        id = "coldridge-002"
        do = "complete"
        quest = 179
        text = "Mata lobos."
        status = "disputed"
        sources = ["https://example.org/a"]
        link = "brujo/10-19#no-existe"

        [[step]]
        id = "coldridge-003"
        do = "train"
        spells = [348, 172]
        text = "Entrena."
        status = "unverified"
        optional = true
        if = { class = ["WARLOCK"] }
    """)
    write(root, "data/shared/alliance-hub.toml", """
        id = "alliance-hub"
        title = "Forjaz"
        levels = [6, 10]
        map = 1455

        [[step]]
        id = "hub-001"
        do = "fly"
        zone = 1453
        wps = [[1455, 55.5, 47.7, "Grifos"]]
        text = "Vuela a Ventormenta."
        status = "unverified"
    """)
    write(root, "data/knowledge/warlock/bracket-10-19.toml", """
        id = "warlock-bracket-10-19"
        class = "WARLOCK"
        kind = "page"
        title = "Niveles 10-19: el Abisario"
        levels = [10, 19]
        status = "verified"
        sources = ["https://example.org/b"]

        [[block]]
        heading = "Abisario"
        body = "Texto con **negrita** y una lista:\\n- uno\\n- dos\\n\\n<script>alert(1)</script>"
    """)
    write(root, "data/knowledge/warlock/macros.toml", """
        id = "warlock-macros"
        class = "WARLOCK"
        kind = "macros"
        title = "Macros de brujo"
        status = "unverified"

        [[macro]]
        name = "Drenar"
        minlevel = 10
        body = "#showtooltip\\n/cast Drenar alma"
    """)
    write(root, "data/knowledge/general/intro.toml", """
        id = "general-intro"
        class = "ANY"
        kind = "page"
        title = "Consejos generales"
        status = "unverified"

        [[block]]
        heading = "Bolsas"
        body = "Compra bolsas."
    """)
    write(root, "CHANGELOG.md", """
        # Changelog

        ## [0.1.0] - 2026-11-11
        - Primera versión.
    """)
    write(root, "harness/reports/verify-latest.json", json.dumps(
        {"generated": "2026-11-11", "checked": 3, "results": [{"step": "coldridge-001", "result": "ok"}]}))


class SiteBuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / "repo"
        cls.out = Path(cls.tmp.name) / "out"
        make_fixture(cls.root)
        cls.res = site.build(cls.root, cls.out, validate=False, today=dt.date(2026, 11, 11))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def read(self, rel):
        return (self.out / rel).read_text(encoding="utf-8")

    def test_files(self):
        for rel in ["index.html", "404.html", "search.json", ".nojekyll", "sitemap.xml",
                    "guias/gnome-warlock/index.html", "brujo/index.html", "brujo/10-19/index.html",
                    "brujo/macros/index.html", "general/index.html", "estado/index.html",
                    "cambios/index.html", "static/style.css", "static/app.js", "static/favicon.svg"]:
            self.assertTrue((self.out / rel).is_file(), rel)
        self.assertEqual(self.res["guides"], 1)
        self.assertEqual(self.res["knowledge"], 3)

    def test_guide_page(self):
        h = self.read("guias/gnome-warlock/index.html")
        self.assertIn('id="coldridge"', h)
        self.assertIn('id="alliance-hub"', h)
        self.assertIn('id="coldridge-001"', h)
        self.assertIn('id="hub-001"', h)
        self.assertIn(f"{site.WOWHEAD_BASE}/quest=179", h)
        self.assertIn(f"{site.WOWHEAD_BASE}/npc=658", h)
        self.assertIn(f"{site.WOWHEAD_BASE}/spell=348", h)
        self.assertIn("29.9, 71.2 (Dun Morogh)", h)
        self.assertIn("55.5, 47.7 (Forjaz)", h)
        self.assertIn("Destino: Ventormenta", h)
        self.assertIn("badge-verified", h)
        self.assertIn("badge-disputed", h)
        self.assertIn("badge-unverified", h)
        self.assertIn("questie:quest/179", h)  # tooltip con fuentes
        self.assertIn('class="tip"', h)
        self.assertIn("&lt;b&gt;experto&lt;/b&gt;", h)  # el HTML de los datos se escapa
        self.assertIn("<strong>Sten</strong>", h)
        self.assertIn('href="../../brujo/10-19/#abisario"', h)
        self.assertIn('href="../../static/style.css', h)
        self.assertNotIn(site.ROOT, h)
        self.assertIn('<ol class="steps" start="4">', h)  # numeración continua entre secciones

    def test_knowledge_pages(self):
        h = self.read("brujo/10-19/index.html")
        self.assertIn('id="abisario"', h)
        self.assertIn("<li>uno</li>", h)
        self.assertNotIn("<script>alert", h)
        m = self.read("brujo/macros/index.html")
        self.assertIn('data-copy-target="drenar-code"', m)
        self.assertIn("#showtooltip\n/cast Drenar alma", m)
        idx = self.read("brujo/index.html")
        self.assertIn('href="../brujo/10-19/"', idx)

    def test_status_page(self):
        h = self.read("estado/index.html")
        self.assertIn("Brujo gnomo 1-60", h)
        self.assertIn("coldridge-002", h)  # lista de pasos en disputa
        self.assertIn("coldridge-001", h)  # informe de verificación
        self.assertIn("no existe el ancla", h)

    def test_broken_links(self):
        self.assertEqual(len(self.res["broken"]), 1)
        self.assertIn("brujo/10-19#no-existe", self.res["broken"][0])

    def test_changelog(self):
        h = self.read("cambios/index.html")
        self.assertIn('id="0-1-0-2026-11-11"', h)
        self.assertIn("Primera versión.", h)

    def test_search_index(self):
        data = json.loads(self.read("search.json"))
        urls = {e["u"] for e in data}
        self.assertIn("guias/gnome-warlock/#coldridge-001", urls)
        self.assertIn("brujo/10-19/#abisario", urls)
        self.assertIn("brujo/macros/#drenar", urls)
        self.assertTrue(all({"t", "u", "k"} <= set(e) for e in data))

    def test_404_uses_absolute_root(self):
        h = self.read("404.html")
        self.assertIn('href="/senda/static/style.css', h)


class EmptyRepoTest(unittest.TestCase):
    def test_builds_without_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "repo", Path(tmp) / "out"
            root.mkdir()
            res = site.build(root, out, validate=False)
            self.assertEqual(res["guides"], 0)
            home = (out / "index.html").read_text(encoding="utf-8")
            self.assertIn("Instalación", home)
            self.assertIn("_forever_", home)
            self.assertIn("https://github.com/e-omunoz/senda", home)
            self.assertTrue((out / "estado" / "index.html").is_file())
            self.assertEqual(json.loads((out / "search.json").read_text(encoding="utf-8"))[0]["k"], "Proyecto")

    def test_bad_toml_is_a_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "repo", Path(tmp) / "out"
            write(root, "data/guides/x/guide.toml", "id = \n")
            res = site.build(root, out, validate=False)
            self.assertEqual(res["guides"], 0)
            self.assertTrue(any("guide.toml" in w for w in res["warnings"]))

    def test_refuses_to_delete_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            with self.assertRaises(SystemExit):
                site.build(root, root, validate=False)


class HelpersTest(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(site.slugify("El Abisario: ¡ya!"), "el-abisario-ya")
        self.assertEqual(site.slugify("Rotación"), "rotacion")

    def test_site_href(self):
        self.assertEqual(site.site_href("brujo/10-19#abisario"), site.ROOT + "brujo/10-19/#abisario")
        self.assertEqual(site.site_href("/estado/"), site.ROOT + "estado/")
        self.assertEqual(site.site_href("https://x.org/a"), "https://x.org/a")

    def test_inline_md_blocks_js_links(self):
        out = site.inline_md("[x](javascript:alert(1)) `<i>` **b**")
        self.assertNotIn("javascript:", out)
        self.assertIn("<code>&lt;i&gt;</code>", out)
        self.assertIn("<strong>b</strong>", out)

    def test_money(self):
        self.assertEqual(site.money(12345), "1 o 23 p 45 c")
        self.assertEqual(site.money(0), "0 c")


if __name__ == "__main__":
    unittest.main()

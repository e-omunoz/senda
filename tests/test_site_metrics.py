"""Tests de las métricas de la web (tools/site_metrics.py) sobre el propio repositorio."""
from __future__ import annotations

import importlib.util
import json
import re
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("senda_site_metrics", REPO / "tools" / "site_metrics.py")
sm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sm)

VOID = {"meta", "link", "br", "hr", "img", "input"}


class Balanced(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack: list[str] = []
        self.errors: list[str] = []
        self.ids: list[str] = []
        self.external: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.append(a["id"])
        for k in ("src", "href"):
            if str(a.get(k) or "").startswith(("http://", "https://")) and tag != "a":
                self.external.append(a[k])
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"</{tag}> con pila {self.stack[-3:]}")
            if tag in self.stack:
                while self.stack and self.stack.pop() != tag:
                    pass
        else:
            self.stack.pop()


def visible_text(page: str) -> str:
    page = re.sub(r"<(script|style)\b.*?</\1>", "", page, flags=re.S)
    return re.sub(r"<[^>]+>", " ", page)


class MetricsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name)
        cls.m = sm.write(REPO, cls.out)
        cls.page = (cls.out / "metricas" / "index.html").read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_valid_html(self):
        p = Balanced()
        p.feed(self.page)
        p.close()
        self.assertEqual(p.errors, [])
        self.assertEqual(p.stack, [])
        self.assertTrue(self.page.startswith("<!doctype html>"))
        self.assertEqual(len(p.ids), len(set(p.ids)), "ids repetidos")

    def test_no_external_resources_or_trackers(self):
        p = Balanced()
        p.feed(self.page)
        self.assertEqual(p.external, [])
        self.assertNotRegex(self.page, r"<script[^>]+src=")
        self.assertNotRegex(self.page, r"<link[^>]+stylesheet")

    def test_bilingual_theme_and_toggle(self):
        self.assertIn('lang="es"', self.page)
        self.assertIn('lang="en"', self.page)
        self.assertIn('id="m-lang-btn"', self.page)
        self.assertIn("prefers-color-scheme", self.page)
        self.assertIn('[data-theme="light"]', self.page)
        # el español va primero en cada par
        self.assertLess(self.page.index('lang="es"'), self.page.index('lang="en"'))

    def test_every_guide_is_listed_with_its_numbers(self):
        ids = {d.name for d in (REPO / "data" / "guides").iterdir() if d.is_dir()}
        self.assertEqual({g["id"] for g in self.m["guides"]}, ids)
        text = visible_text(self.page)
        for g in self.m["guides"]:
            self.assertIn(f'id="g-{g["id"]}"', self.page)
            self.assertGreater(g["steps"], 0)
            self.assertEqual(g["verified"] + g["unverified"] + g["disputed"], g["steps"])
            self.assertLessEqual(g["with_sources"], g["steps"])
            self.assertIn(g["title"], text)
            if g["scored"]:
                self.assertGreater(g["hours"], 5)
                self.assertLess(g["hours"], 200)
                self.assertGreater(g["xp_per_hour"], 1000)
                self.assertEqual(g["keep"] + g["optional"] + g["drop"], g["quests"])
                # la cifra de horas aparece en la página (en es o en en)
                self.assertTrue(f"{g['hours']:,.1f}" in text or f"{g['hours']:,.1f}".replace(",", "\0")
                                .replace(".", ",").replace("\0", ".") in text)

    def test_three_priority_guides_are_scored(self):
        scored = {g["id"] for g in self.m["guides"] if g["scored"]}
        self.assertTrue({"gnome-warlock", "human-mage", "nightelf-druid"} <= scored)

    def test_nav_numbers_match_reports(self):
        nav = self.m["nav"]
        report = (REPO / "nav" / "eval" / "report.md").read_text(encoding="utf-8")
        found = re.search(r"Routes: (\d+); found: (\d+)", report)
        self.assertEqual((nav["routes"], nav["found"]), (int(found.group(1)), int(found.group(2))))
        lua = (REPO / "nav" / "eval" / "report-lua.md").read_text(encoding="utf-8")
        self.assertEqual(nav["longest_frame_ms"], float(re.search(r"longest frame ([\d.]+) ms", lua).group(1)))
        self.assertEqual(nav["off_links"], 0)
        self.assertTrue(nav["packs"])
        text = visible_text(self.page)
        self.assertEqual(nav["budget_ms"], 2.0)
        self.assertIn(f"{nav['longest_frame_ms']:.2f}", text)  # fotograma más largo medido
        self.assertIn(f"{nav['found']} / {nav['routes']}", text)

    def test_data_coverage(self):
        d = self.m["data"]
        self.assertGreater(d["names_used"], 0)
        self.assertLessEqual(d["names_covered"], d["names_used"])
        self.assertLessEqual(d["names_from_game"], d["names_covered"])
        cov = json.loads((REPO / "data" / "lookup" / "coverage.json").read_text(encoding="utf-8"))
        self.assertEqual(d["lookup"]["all"]["pct"], cov["any_source"]["all"]["pct"])

    def test_changelog_matches_file(self):
        versions = [v["version"] for v in self.m["changelog"]]
        self.assertTrue(versions)
        log = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
        for v in versions:
            self.assertIn(f"## [{v}]", log)
            self.assertIn(v, self.page)

    def test_site_build_includes_metrics_page(self):
        spec = importlib.util.spec_from_file_location("senda_site_t", REPO / "tools" / "site.py")
        site = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(site)
        with tempfile.TemporaryDirectory() as td:
            res = site.build(REPO, Path(td) / "_site", validate=False)
            self.assertEqual(res["broken"], [])
            page = (Path(td) / "_site" / "metricas" / "index.html").read_text(encoding="utf-8")
            self.assertIn('id="m-lang-btn"', page)
            self.assertIn('href="../metricas/"', page)

    def test_runs_on_empty_root(self):
        with tempfile.TemporaryDirectory() as td:
            m = sm.collect(Path(td))
            self.assertEqual(m["guides"], [])
            page = sm.render_page(m)
            p = Balanced()
            p.feed(page)
            self.assertEqual(p.errors, [])


if __name__ == "__main__":
    unittest.main()

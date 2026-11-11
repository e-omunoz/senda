"""propose de punta a punta con data/ y state/ temporales: sin red y sin API."""
import io
import json
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from harness import config, propose, state
from harness.config import load_registry
from harness.evidence import Confirmer

OFFICIAL = "https://worldofwarcraft.blizzard.com/news/24315281/wow-forever-hotfixes-november-10-2026"
REDDIT = "https://www.reddit.com/r/classicwow/comments/abc"

GUIDE = '''id = "gnome-warlock"
title = "Brujo gnomo 1-60"
faction = "Alliance"
races = ["Gnome"]
classes = ["WARLOCK"]
sections = ["01-coldridge"]
'''
SECTION = '''id = "coldridge"
title = "Valle de Crestanevada"
levels = [1, 6]

[[step]]
id = "coldridge-001"
do = "accept"
quest = 179
npc = 658
text = "Habla con Sten Stoutarm."
status = "unverified"
sources = ["questie:quest/179"]

[[step]]
id = "coldridge-002"
do = "turnin"
quest = 179
npc = 658
text = "Entrega la misión."
status = "verified"
sources = ["questie:quest/179", "obs:turnin/179"]
'''
PAGES = {
    OFFICIAL: "Sten Stoutarm now offers Dwarven Outfitters at level 1. Imp Firebolt damage increased by 10%.",
    REDDIT: "Imp Firebolt is way stronger now, use it on everything below 20.",
}


class ProposeEndToEndTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "data/guides/gnome-warlock").mkdir(parents=True)
        (root / "data/guides/gnome-warlock/guide.toml").write_text(GUIDE, encoding="utf-8")
        self.section = root / "data/guides/gnome-warlock/01-coldridge.toml"
        self.section.write_text(SECTION, encoding="utf-8")
        self.state = root / "state"
        (self.state / "inbox").mkdir(parents=True)
        self.patches = [mock.patch.object(config, "DATA", root / "data"),
                        mock.patch.object(config, "STATE", self.state),
                        mock.patch.object(config, "INBOX", self.state / "inbox"),
                        mock.patch.object(config, "REPORTS", root / "reports")]
        for p in self.patches:
            p.start()
        self.reg = load_registry()
        self.confirmer = Confirmer(self.reg, page_text=lambda u: PAGES[u],
                                   lookup_fn=lambda k, i: (True, "{}"), obs_fn=lambda k, i: [])

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_claude_code_inbox_verdicts_and_tips(self):
        # Veredicto de Claude Code que intenta verificar con una cita oficial real...
        (self.state / "inbox" / "verdicts-2026-11-11-coldridge.json").write_text(json.dumps({"verdicts": [
            {"step_id": "coldridge-001", "verdict": "ok", "proposed_status": "verified", "changes": [],
             "evidence": [{"kind": "web", "url": OFFICIAL, "quote": "Sten Stoutarm now offers Dwarven Outfitters",
                           "ref": "", "supports": "supports"}], "tip_es": "", "notes_es": ""},
            # ...y otro que intenta rebajar un paso verificado con una cita de Reddit inventada.
            {"step_id": "coldridge-002", "verdict": "incorrect", "proposed_status": "unverified",
             "changes": [{"field": "npc", "value_json": "1", "reason_es": "x"}],
             "evidence": [{"kind": "web", "url": REDDIT, "quote": "Sten no longer accepts this quest", "ref": "",
                           "supports": "contradicts"}], "tip_es": "", "notes_es": ""},
            {"step_id": "no-existe", "verdict": "ok", "proposed_status": "verified", "changes": [], "evidence": [],
             "tip_es": "", "notes_es": ""},
        ]}), encoding="utf-8")
        (self.state / "inbox" / "tips-warlock.json").write_text(json.dumps({"class": "WARLOCK", "race": "Gnome",
            "tips": [
                {"title_es": "Usa Descarga de fuego", "body_es": "El diablillo pega más desde el hotfix.",
                 "levels": [1, 19], "category": "pet",
                 "citations": [{"url": OFFICIAL, "quote": "Imp Firebolt damage increased by 10%"}]},
                {"title_es": "Consejo inventado", "body_es": "Nada.", "levels": [1, 2], "category": "other",
                 "citations": [{"url": OFFICIAL, "quote": "this sentence is not on the page at all"}]},
            ]}), encoding="utf-8")

        with mock.patch.object(propose, "Confirmer", lambda *a, **k: self.confirmer):
            prop, report = propose.run(self.reg, out=io.StringIO(), cost={"usd": 0.12, "calls": 3})

        steps = {s["id"]: s for s in tomllib.loads(self.section.read_text(encoding="utf-8"))["step"]}
        self.assertEqual(steps["coldridge-001"]["status"], "verified")
        self.assertIn(OFFICIAL, steps["coldridge-001"]["sources"])
        self.assertEqual(steps["coldridge-002"]["status"], "verified")   # intacto
        self.assertEqual(steps["coldridge-002"]["npc"], 658)
        self.assertTrue(any("no-existe" in e for e in prop.errors))

        page = config.DATA / "knowledge/warlock/harness-tips.toml"
        doc = tomllib.loads(page.read_text(encoding="utf-8"))
        self.assertEqual(doc["status"], "unverified")
        self.assertEqual([b["heading"] for b in doc["block"]], ["Usa Descarga de fuego"])
        self.assertIn(OFFICIAL, doc["sources"])

        text = report.read_text(encoding="utf-8")
        self.assertIn("Informe del harness", text)
        self.assertIn("Consejo inventado", text)
        self.assertIn("0.120 USD", text)
        # Las entradas consumidas se archivan y no se vuelven a aplicar.
        self.assertEqual(state.inbox_files("verdicts"), [])
        self.assertEqual(state.inbox_files("tips"), [])
        prop2, _ = propose.run(self.reg, out=io.StringIO())
        self.assertFalse(prop2.has_edits)

    def test_dry_run_writes_nothing(self):
        (self.state / "inbox" / "verdicts-x.json").write_text(json.dumps([
            {"step_id": "coldridge-001", "verdict": "ok", "proposed_status": "verified", "changes": [],
             "evidence": [{"kind": "web", "url": OFFICIAL, "quote": "Sten Stoutarm now offers Dwarven Outfitters",
                           "ref": "", "supports": "supports"}], "tip_es": "", "notes_es": ""}]), encoding="utf-8")
        out = io.StringIO()
        with mock.patch.object(propose, "Confirmer", lambda *a, **k: self.confirmer):
            prop, report = propose.run(self.reg, dry_run=True, out=out)
        self.assertIsNone(report)
        self.assertEqual(self.section.read_text(encoding="utf-8"), SECTION)
        self.assertIn('+status = "verified"', out.getvalue())
        self.assertEqual(len(state.inbox_files("verdicts")), 1)


if __name__ == "__main__":
    unittest.main()

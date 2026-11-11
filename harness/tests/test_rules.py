import unittest

from harness import rules, tomledit
from harness.config import load_registry
from harness.evidence import Confirmer
from harness.propose import apply_verdict, coerce_value
from harness.rules import Evidence, decide, step_status_after, verification_rule

OFFICIAL = "https://worldofwarcraft.blizzard.com/en-us/news/24310000"
WIKI = "https://warcraft.wiki.gg/wiki/Quest:179"
REDDIT = "https://www.reddit.com/r/classicwow/comments/abc"


def web(url, tier, supports="supports", confirmed=True):
    return Evidence("web", supports, url=url, quote="cita literal de prueba", tier=tier, confirmed=confirmed)


def questie(supports="supports", confirmed=True):
    return Evidence("questie", supports, ref="questie:quest/179", confirmed=confirmed)


def obs(confirmed=True):
    return Evidence("observation", "supports", ref="obs:accept/179", confirmed=confirmed)


class VerificationRuleTest(unittest.TestCase):
    def test_a_official(self):
        self.assertEqual(verification_rule([web(OFFICIAL, "official")]), "a")

    def test_b_observation(self):
        self.assertEqual(verification_rule([obs()]), "b")

    def test_c_questie_plus_independent(self):
        self.assertEqual(verification_rule([questie(), web(WIKI, "community_curated")]), "c")

    def test_questie_alone_is_not_enough(self):
        self.assertEqual(verification_rule([questie()]), "")

    def test_questie_plus_unverified_is_not_enough(self):
        self.assertEqual(verification_rule([questie(), web(REDDIT, "community_unverified")]), "")

    def test_curated_alone_is_not_enough(self):
        self.assertEqual(verification_rule([web(WIKI, "community_curated")]), "")

    def test_unconfirmed_never_counts(self):
        self.assertEqual(verification_rule([web(OFFICIAL, "official", confirmed=False)]), "")
        self.assertEqual(verification_rule([obs(confirmed=False)]), "")
        self.assertEqual(verification_rule([questie(confirmed=False), web(WIKI, "community_curated")]), "")

    def test_contradicting_evidence_does_not_verify(self):
        self.assertEqual(verification_rule([web(OFFICIAL, "official", "contradicts")]), "")


class DecideTest(unittest.TestCase):
    def test_model_cannot_force_verified(self):
        d = decide([web(WIKI, "community_curated")], "verified")
        self.assertEqual(d.status, "unverified")

    def test_verified_allowed(self):
        self.assertEqual(decide([web(OFFICIAL, "official")], "verified").status, "verified")

    def test_disputed_when_reliable_sources_disagree(self):
        d = decide([web(OFFICIAL, "official"), web(WIKI, "community_curated", "contradicts")], "verified")
        self.assertEqual(d.status, "disputed")
        self.assertTrue(d.disputed)

    def test_unverified_contradiction_does_not_dispute(self):
        d = decide([web(OFFICIAL, "official"), web(REDDIT, "community_unverified", "contradicts")], "verified")
        self.assertEqual(d.status, "verified")

    def test_only_contradiction(self):
        d = decide([questie("contradicts")], "unverified")
        self.assertTrue(d.contradicted)

    def test_assert_can_verify(self):
        with self.assertRaises(rules.RuleViolation):
            rules.assert_can_verify([])
        with self.assertRaises(rules.RuleViolation):
            rules.assert_can_verify([web(OFFICIAL, "official"), questie("contradicts")])
        self.assertEqual(rules.assert_can_verify([obs()]), "b")


class StatusAfterTest(unittest.TestCase):
    def test_verified_step_contradicted_becomes_disputed(self):
        d = decide([web(OFFICIAL, "official", "contradicts")])
        self.assertEqual(step_status_after("verified", d, value_changes=False), "disputed")

    def test_value_change_without_rule_is_unverified(self):
        d = decide([web(WIKI, "community_curated")], "verified")
        self.assertEqual(step_status_after("verified", d, value_changes=True), "unverified")

    def test_no_reason_to_downgrade(self):
        d = decide([], "unverified")
        self.assertEqual(step_status_after("verified", d, value_changes=False), "verified")
        self.assertEqual(step_status_after("disputed", d, value_changes=False), "disputed")


SECTION = '''id = "coldridge"
title = "Valle"
levels = [1, 6]

[[step]]
id = "coldridge-001"
do = "accept"
quest = 179
npc = 658
at = [1426, 29.9, 71.2]
text = "Habla con Sten."
status = "unverified"
sources = ["questie:quest/179"]
'''


class FakeConfirmer(Confirmer):
    """Confirma sin red: páginas y QuestieDB simulados."""

    def __init__(self, pages=None, questie_ok=True, obs_hits=0):
        super().__init__(load_registry(), page_text=lambda u: (pages or {})[u] if u in (pages or {}) else
                         (_ for _ in ()).throw(OSError("sin red")),
                         lookup_fn=lambda k, i: (questie_ok, "{}"), obs_fn=lambda k, i: [{}] * obs_hits)


def verdict(**kw):
    v = {"step_id": "coldridge-001", "verdict": "ok", "proposed_status": "verified", "changes": [],
         "evidence": [], "tip_es": "", "notes_es": ""}
    v.update(kw)
    return v


class ApplyVerdictTest(unittest.TestCase):
    def test_hallucinated_quote_does_not_verify(self):
        c = FakeConfirmer(pages={OFFICIAL: "Patch notes: nothing about Sten here."})
        v = verdict(evidence=[{"kind": "web", "url": OFFICIAL, "quote": "Sten Stoutarm now offers quest 179.",
                               "ref": "", "supports": "supports"}])
        out, ch = apply_verdict(SECTION, v, c, "2026-11-11")
        self.assertEqual(tomledit.get_step(out, "coldridge-001")["status"], "unverified")
        self.assertFalse(ch.evidence[0].confirmed)
        self.assertEqual(out, SECTION)  # nada confirmado: ni fuentes ni fecha

    def test_official_quote_verifies_and_adds_source(self):
        c = FakeConfirmer(pages={OFFICIAL: "Hotfix: Sten Stoutarm now offers quest 179 at level 1."})
        v = verdict(evidence=[{"kind": "web", "url": OFFICIAL, "quote": "Sten Stoutarm now offers quest 179",
                               "ref": "", "supports": "supports"}])
        out, ch = apply_verdict(SECTION, v, c, "2026-11-11")
        s = tomledit.get_step(out, "coldridge-001")
        self.assertEqual(s["status"], "verified")
        self.assertEqual(ch.rule, "a")
        self.assertIn(OFFICIAL, s["sources"])
        self.assertEqual(s["checked"], "2026-11-11")

    def test_tier_comes_from_url_not_model(self):
        c = FakeConfirmer(pages={REDDIT: "Sten Stoutarm now offers quest 179 trust me"})
        v = verdict(evidence=[{"kind": "web", "url": REDDIT, "quote": "Sten Stoutarm now offers quest 179",
                               "ref": "", "supports": "supports", "tier": "official"}])
        out, _ = apply_verdict(SECTION, v, c, "2026-11-11")
        self.assertEqual(tomledit.get_step(out, "coldridge-001")["status"], "unverified")

    def test_questie_plus_wiki_verifies(self):
        c = FakeConfirmer(pages={WIKI: "Sten Stoutarm offers this quest in Coldridge Valley."})
        v = verdict(evidence=[
            {"kind": "questie", "url": "", "quote": "", "ref": "questie:quest/179", "supports": "supports"},
            {"kind": "web", "url": WIKI, "quote": "Sten Stoutarm offers this quest", "ref": "",
             "supports": "supports"}])
        out, ch = apply_verdict(SECTION, v, c, "2026-11-11")
        self.assertEqual(tomledit.get_step(out, "coldridge-001")["status"], "verified")
        self.assertEqual(ch.rule, "c")

    def test_questie_missing_tool_blocks_rule_c(self):
        c = FakeConfirmer(pages={WIKI: "Sten Stoutarm offers this quest in Coldridge Valley."}, questie_ok=False)
        v = verdict(evidence=[
            {"kind": "questie", "url": "", "quote": "", "ref": "questie:quest/179", "supports": "supports"},
            {"kind": "web", "url": WIKI, "quote": "Sten Stoutarm offers this quest", "ref": "",
             "supports": "supports"}])
        out, _ = apply_verdict(SECTION, v, c, "2026-11-11")
        self.assertEqual(tomledit.get_step(out, "coldridge-001")["status"], "unverified")

    def test_disputed_records_both_sources(self):
        c = FakeConfirmer(pages={OFFICIAL: "Sten Stoutarm now offers quest 179.",
                                 WIKI: "The quest giver was moved to Balir Frosthammer."})
        v = verdict(verdict="uncertain", evidence=[
            {"kind": "web", "url": OFFICIAL, "quote": "Sten Stoutarm now offers quest 179", "ref": "",
             "supports": "supports"},
            {"kind": "web", "url": WIKI, "quote": "The quest giver was moved to Balir Frosthammer", "ref": "",
             "supports": "contradicts"}])
        out, _ = apply_verdict(SECTION, v, c, "2026-11-11")
        s = tomledit.get_step(out, "coldridge-001")
        self.assertEqual(s["status"], "disputed")
        self.assertIn(OFFICIAL, s["sources"])
        self.assertIn(WIKI, s["sources"])

    def test_value_change_needs_confirmed_evidence(self):
        c = FakeConfirmer(pages={})
        v = verdict(verdict="incorrect", proposed_status="unverified",
                    changes=[{"field": "npc", "value_json": "1234", "reason_es": "otro PNJ"}],
                    evidence=[{"kind": "web", "url": WIKI, "quote": "inventada", "ref": "", "supports": "supports"}])
        out, ch = apply_verdict(SECTION, v, c, "2026-11-11")
        self.assertEqual(out, SECTION)
        self.assertTrue(any("sin evidencia confirmada" in s for s in ch.skipped))

    def test_value_change_applied_as_unverified(self):
        c = FakeConfirmer(pages={WIKI: "Quest 179 is now started by Balir Frosthammer."})
        v = verdict(verdict="outdated", proposed_status="verified",
                    changes=[{"field": "npc", "value_json": "713", "reason_es": "PNJ movido"}],
                    evidence=[{"kind": "web", "url": WIKI, "quote": "Quest 179 is now started by Balir Frosthammer",
                               "ref": "", "supports": "supports"}],
                    tip_es="El PNJ está junto a la forja.")
        out, ch = apply_verdict(SECTION, v, c, "2026-11-11")
        s = tomledit.get_step(out, "coldridge-001")
        self.assertEqual(s["npc"], 713)
        self.assertEqual(s["status"], "unverified")  # curada sola no basta para verified
        self.assertEqual(s["tip"], "El PNJ está junto a la forja.")

    def test_verify_py_conflict_blocks_questie(self):
        c = FakeConfirmer(pages={WIKI: "Sten Stoutarm offers this quest in Coldridge Valley."})
        c.verify_verdicts = {"coldridge-001": "conflict"}
        v = verdict(evidence=[
            {"kind": "questie", "url": "", "quote": "", "ref": "questie:quest/179", "supports": "supports"},
            {"kind": "web", "url": WIKI, "quote": "Sten Stoutarm offers this quest", "ref": "",
             "supports": "supports"}])
        out, ch = apply_verdict(SECTION, v, c, "2026-11-11")
        self.assertEqual(tomledit.get_step(out, "coldridge-001")["status"], "unverified")
        self.assertIn("verify.py", ch.evidence[0].detail)

    def test_coordinates_never_copied_from_questie_alone(self):
        c = FakeConfirmer()
        v = verdict(verdict="incorrect", proposed_status="unverified",
                    changes=[{"field": "at", "value_json": "[1426, 30.5, 70.1]", "reason_es": "según QuestieDB"}],
                    evidence=[{"kind": "questie", "url": "", "quote": "", "ref": "questie:npc/658",
                               "supports": "supports"}])
        out, ch = apply_verdict(SECTION, v, c, "2026-11-11")
        self.assertEqual(tomledit.get_step(out, "coldridge-001")["at"], [1426, 29.9, 71.2])
        self.assertTrue(any("QuestieDB" in s for s in ch.skipped))

    def test_observation_verifies(self):
        c = FakeConfirmer(obs_hits=2)
        v = verdict(evidence=[{"kind": "observation", "url": "", "quote": "", "ref": "obs:accept/179",
                               "supports": "supports"}])
        out, ch = apply_verdict(SECTION, v, c, "2026-11-11")
        self.assertEqual(tomledit.get_step(out, "coldridge-001")["status"], "verified")
        self.assertEqual(ch.rule, "b")

    def test_offline_never_verifies_web(self):
        c = Confirmer(load_registry(), offline=True)
        v = verdict(evidence=[{"kind": "web", "url": OFFICIAL, "quote": "Sten Stoutarm now offers quest 179",
                               "ref": "", "supports": "supports"}])
        out, _ = apply_verdict(SECTION, v, c, "2026-11-11")
        self.assertEqual(tomledit.get_step(out, "coldridge-001")["status"], "unverified")


class CoerceTest(unittest.TestCase):
    def test_types(self):
        self.assertEqual(coerce_value("npc", "658"), 658)
        self.assertEqual(coerce_value("at", "[1426, 29.9, 71.2]"), [1426, 29.9, 71.2])
        for fld, raw in (("npc", '"658"'), ("npc", "true"), ("at", "[1426, 129, 50]"), ("spells", "[]"),
                         ("status", '"verified"'), ("sources", "[]"), ("text", '""'), ("at", "{")):
            with self.assertRaises(ValueError, msg=f"{fld}={raw}"):
                coerce_value(fld, raw)


class RegistryTest(unittest.TestCase):
    def test_classify(self):
        reg = load_registry()
        self.assertEqual(reg.classify_url(OFFICIAL)[0], "official")
        self.assertEqual(reg.classify_url(WIKI)[0], "community_curated")
        self.assertEqual(reg.classify_url(REDDIT)[0], "community_unverified")
        self.assertEqual(reg.classify_url("https://us.forums.blizzard.com/en/wow/t/some-player-thread/123")[0],
                         "community_unverified")
        self.assertEqual(reg.classify_url("https://www.wowhead.com/forever/blue-tracker/topic/x")[0], "official")
        self.assertEqual(reg.classify_url("https://www.wowhead.com/forever/guide/x")[0], "community_curated")
        self.assertEqual(reg.classify_url("https://warcraft.wiki.gg.evil.example/x")[0], "community_unverified")
        self.assertEqual(reg.classify_url("https://unknown.example/x")[0], "community_unverified")

    def test_sources_listed_in_forever_md_are_registered(self):
        reg = load_registry()
        for url in ("https://worldofwarcraft.blizzard.com/forever",
                    "https://us.forums.blizzard.com/en/wow/c/wow-forever/347",
                    "https://eu.forums.blizzard.com/en/wow/c/wow-forever/359",
                    "https://us.forums.blizzard.com/en/wow/t/2360696",
                    "https://www.wowhead.com/forever/blue-tracker", "https://warcraft.wiki.gg/wiki/Patch_1.60",
                    "https://www.warcrafttavern.com/forever/", "https://www.icy-veins.com/wow-forever/class-guides",
                    "https://mobalytics.gg/wow-forever", "https://gamer-guides.com/wiki/wow-forever/",
                    "https://kami-labs.fr/en/addons-wow-forever/"):
            self.assertIsNotNone(reg.classify_url(url)[1], url)


if __name__ == "__main__":
    unittest.main()

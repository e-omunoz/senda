import json
import unittest

from harness.claims import CLAIMS_SCHEMA, claim_id, extract_json, normalize_text, parse_claims, quote_in_text
from harness.config import load_registry

ITEM_TEXT = """Hotfixes for November 10, 2026
Warlock: Imp Firebolt damage increased by 10% for characters below level 20.
Quests: "The Troll Cave" (quest 182) now correctly awards experience.
"""
URL = "https://worldofwarcraft.blizzard.com/en-us/news/24310000"


def claim(**kw):
    base = {"category": "hotfix", "summary_es": "Más daño de Descarga de fuego del diablillo por debajo del 20.",
            "quote": "Imp Firebolt damage increased by 10% for characters below level 20.", "url": URL,
            "date": "2026-11-10", "classes": ["warlock"], "races": [], "zones": [], "quest_ids": [],
            "npc_ids": [], "item_ids": [], "spell_ids": [], "levels": [1, 19], "confidence": "high"}
    base.update(kw)
    return base


class ExtractJsonTest(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(extract_json('{"a": 1}'), {"a": 1})

    def test_fenced(self):
        self.assertEqual(extract_json('Aquí va:\n```json\n{"claims": []}\n```\nfin'), {"claims": []})

    def test_embedded_with_braces_in_strings(self):
        txt = 'Resultado: {"claims": [{"quote": "a } b { c"}]} y nada más'
        self.assertEqual(extract_json(txt)["claims"][0]["quote"], "a } b { c")

    def test_invalid(self):
        with self.assertRaises(ValueError):
            extract_json("sin json")


class QuoteTest(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(normalize_text("It’s  a TEST&amp;"), "it's a test&")

    def test_quote_found_despite_whitespace_and_case(self):
        self.assertTrue(quote_in_text("imp firebolt   damage increased by 10%", ITEM_TEXT))

    def test_quote_not_found(self):
        self.assertFalse(quote_in_text("Imp Firebolt damage increased by 50%", ITEM_TEXT))

    def test_short_quote_rejected(self):
        self.assertFalse(quote_in_text("Warlock", ITEM_TEXT))

    def test_ellipsis(self):
        self.assertTrue(quote_in_text("Imp Firebolt damage ... below level 20", ITEM_TEXT))

    def test_id_stable(self):
        self.assertEqual(claim_id(URL, "A  b"), claim_id(URL + " ", "a b"))


class ParseClaimsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = load_registry()

    def parse(self, payload, tier="official", text=ITEM_TEXT, url=URL):
        return parse_claims(payload, item_url=url, item_text=text, item_tier=tier, registry=self.reg,
                            today="2026-11-11")

    def test_valid_claim_keeps_item_tier(self):
        claims, warns = self.parse({"relevant": True, "claims": [claim()]})
        self.assertEqual(len(claims), 1)
        c = claims[0]
        self.assertTrue(c.quote_confirmed)
        self.assertEqual(c.tier, "official")
        self.assertEqual(c.classes, ["WARLOCK"])
        self.assertEqual(c.date, "2026-11-10")
        self.assertEqual(warns, [])

    def test_unfound_quote_downgrades_tier(self):
        claims, _ = self.parse({"claims": [claim(quote="Imp Firebolt damage doubled for everyone forever.")]})
        self.assertEqual(claims[0].tier, "community_unverified")
        self.assertFalse(claims[0].quote_confirmed)
        self.assertTrue(claims[0].notes)

    def test_model_cannot_choose_tier(self):
        # El modelo dice "official" pero la URL es de Reddit y la cita no es del elemento leído.
        claims, _ = self.parse({"claims": [claim(url="https://www.reddit.com/r/classicwow/comments/x",
                                                  tier="official")]}, tier="official")
        self.assertEqual(claims[0].tier, "community_unverified")  # gana el menor (URL de Reddit)
        # Y si el elemento era de un tier menor que la URL citada, también gana el menor.
        claims, _ = self.parse({"claims": [claim(url=URL)]}, tier="community_unverified",
                               url="https://www.reddit.com/r/classicwow/comments/x")
        self.assertEqual(claims[0].tier, "community_unverified")

    def test_drops_claims_without_quote_or_url(self):
        claims, warns = self.parse({"claims": [claim(quote=""), claim(url="ftp://x")]})
        self.assertEqual(claims, [])
        self.assertEqual(len(warns), 2)

    def test_dedup_and_bad_ids(self):
        c = claim(quest_ids=[182, "x", "183"])
        claims, _ = self.parse(json.dumps({"claims": [c, c]}))
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].quest_ids, [182, 183])

    def test_local_item_uses_its_path(self):
        # Exportación de Discord: la "URL" es la ruta local y el tier, el de la fuente.
        claims, _ = self.parse({"claims": [claim(url="")]}, tier="community_unverified",
                               url="harness/inbox/discord/canal.json")
        self.assertEqual(claims[0].url, "harness/inbox/discord/canal.json")
        self.assertEqual(claims[0].tier, "community_unverified")

    def test_unknown_category_becomes_other(self):
        claims, _ = self.parse({"claims": [claim(category="pvp")]})
        self.assertEqual(claims[0].category, "other")

    def test_garbage_payload(self):
        claims, warns = self.parse("no es json")
        self.assertEqual(claims, [])
        self.assertTrue(warns)

    def test_schema_is_strict(self):
        item = CLAIMS_SCHEMA["properties"]["claims"]["items"]
        self.assertFalse(item["additionalProperties"])
        self.assertEqual(set(item["required"]), set(item["properties"]))


if __name__ == "__main__":
    unittest.main()

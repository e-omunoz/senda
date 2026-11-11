import tomllib
import unittest

from harness import tomledit
from harness.rules import Evidence, RuleViolation

SECTION = '''id = "coldridge"
title = "Valle de Crestanevada"
levels = [1, 6]
map = 1426

# Primer paso: comentario que debe sobrevivir
[[step]]
id = "coldridge-001"
do = "accept"
quest = 179
npc = 658
at = [1426, 29.9, 71.2]    # coordenadas aproximadas
text = "Habla con Sten Stoutarm y coge la misión."
status = "unverified"
sources = ["questie:quest/179"]

[[step]]
id = "coldridge-002"
do = "goto"
wps = [
  [1426, 30.0, 70.0, "puente"],
  [1426, 31.5, 69.0, "cueva"],
]
at = [1426, 32.0, 68.0]
text = """Ve a la cueva.
Cuidado con los trogg."""
status = "unverified"
'''


def changed_lines(a: str, b: str) -> int:
    import difflib
    return sum(1 for ln in difflib.ndiff(a.splitlines(), b.splitlines()) if ln[:1] in "+-")


class FormatTest(unittest.TestCase):
    def test_values(self):
        f = tomledit.format_value
        self.assertEqual(f(True), "true")
        self.assertEqual(f(3), "3")
        self.assertEqual(f(29.0), "29.0")
        self.assertEqual(f('Di "hola"\n'), '"Di \\"hola\\"\\n"')
        self.assertEqual(f("ñandú"), '"ñandú"')
        self.assertEqual(f([1426, 29.9, 71.2]), "[1426, 29.9, 71.2]")
        self.assertEqual(tomllib.loads("v = " + f({"class": ["MAGE"], "a b": 1}))["v"],
                         {"class": ["MAGE"], "a b": 1})


class EditTest(unittest.TestCase):
    def test_replace_single_line_minimal(self):
        out = tomledit.set_step_field(SECTION, "coldridge-001", "npc", 659)
        self.assertEqual(changed_lines(SECTION, out), 2)  # una línea quitada, una puesta
        self.assertEqual(tomledit.get_step(out, "coldridge-001")["npc"], 659)
        self.assertIn("# Primer paso: comentario que debe sobrevivir", out)

    def test_keeps_trailing_comment(self):
        out = tomledit.set_step_field(SECTION, "coldridge-001", "at", [1426, 30.1, 71.0])
        self.assertIn("at = [1426, 30.1, 71.0]    # coordenadas aproximadas", out)

    def test_insert_new_key_in_logical_place(self):
        out = tomledit.set_step_field(SECTION, "coldridge-001", "tip", "Mata lobos de camino.")
        self.assertEqual(changed_lines(SECTION, out), 1)
        lines = out.splitlines()
        self.assertEqual(lines.index('tip = "Mata lobos de camino."'), lines.index(
            'text = "Habla con Sten Stoutarm y coge la misión."') + 1)

    def test_replace_multiline_array_and_string(self):
        out = tomledit.set_step_field(SECTION, "coldridge-002", "wps", [[1426, 30.0, 70.0, "puente"]])
        self.assertEqual(tomledit.get_step(out, "coldridge-002")["wps"], [[1426, 30.0, 70.0, "puente"]])
        out = tomledit.set_step_field(out, "coldridge-002", "text", "Ve a la cueva.")
        s = tomledit.get_step(out, "coldridge-002")
        self.assertEqual(s["text"], "Ve a la cueva.")
        self.assertEqual(s["at"], [1426, 32.0, 68.0])
        self.assertNotIn("trogg", out)

    def test_other_steps_untouched(self):
        out = tomledit.set_step_field(SECTION, "coldridge-002", "radius", 20)
        a, b = tomllib.loads(SECTION), tomllib.loads(out)
        self.assertEqual(a["step"][0], b["step"][0])
        self.assertEqual(b["step"][1]["radius"], 20)

    def test_append_unique_sources(self):
        out = tomledit.append_unique(SECTION, "coldridge-001", "sources",
                                     ["questie:quest/179", "https://warcraft.wiki.gg/wiki/Quest:179"])
        self.assertEqual(tomledit.get_step(out, "coldridge-001")["sources"],
                         ["questie:quest/179", "https://warcraft.wiki.gg/wiki/Quest:179"])
        self.assertEqual(tomledit.append_unique(out, "coldridge-001", "sources", ["questie:quest/179"]), out)

    def test_append_tip_concatenates(self):
        out = tomledit.append_tip(SECTION, "coldridge-001", "Primer consejo.")
        out = tomledit.append_tip(out, "coldridge-001", "Segundo consejo.")
        self.assertEqual(tomledit.get_step(out, "coldridge-001")["tip"], "Primer consejo. Segundo consejo.")
        self.assertEqual(tomledit.append_tip(out, "coldridge-001", "Segundo consejo."), out)

    def test_crlf_preserved(self):
        crlf = SECTION.replace("\n", "\r\n")
        out = tomledit.set_step_field(crlf, "coldridge-001", "npc", 1)
        self.assertNotIn("\n", out.replace("\r\n", ""))

    def test_unknown_step_and_id_change(self):
        with self.assertRaises(tomledit.TomlEditError):
            tomledit.set_step_field(SECTION, "nope", "npc", 1)
        with self.assertRaises(tomledit.TomlEditError):
            tomledit.set_step_field(SECTION, "coldridge-001", "id", "x")

    def test_append_block(self):
        page = 'id = "warlock-tips"\nclass = "WARLOCK"\nkind = "page"\nstatus = "unverified"\n'
        out = tomledit.append_table(page, "block", {"heading": "Diablillo", "body": "Usa el diablillo."})
        out = tomledit.append_table(out, "block", {"heading": "Abisario", "body": "Al 10."})
        self.assertEqual([b["heading"] for b in tomllib.loads(out)["block"]], ["Diablillo", "Abisario"])
        out = tomledit.set_top_field(out, "sources", ["https://x.test/a"])
        self.assertEqual(tomllib.loads(out)["sources"], ["https://x.test/a"])
        self.assertLess(out.index("sources ="), out.index("[[block]]"))


class StatusGuardTest(unittest.TestCase):
    def test_verified_requires_rule(self):
        with self.assertRaises(RuleViolation):
            tomledit.set_status(SECTION, "coldridge-001", "verified")
        weak = [Evidence("web", "supports", url="https://reddit.com/x", quote="q", tier="community_unverified",
                         confirmed=True)]
        with self.assertRaises(RuleViolation):
            tomledit.set_status(SECTION, "coldridge-001", "verified", evidence=weak)

    def test_verified_with_official_evidence(self):
        ok = [Evidence("web", "supports", url="https://worldofwarcraft.blizzard.com/en-us/news/1", quote="q",
                       tier="official", confirmed=True)]
        out = tomledit.set_status(SECTION, "coldridge-001", "verified", evidence=ok)
        self.assertEqual(tomledit.get_step(out, "coldridge-001")["status"], "verified")

    def test_invalid_status(self):
        with self.assertRaises(tomledit.TomlEditError):
            tomledit.set_status(SECTION, "coldridge-001", "probable")

    def test_knowledge_page_never_auto_verified(self):
        with self.assertRaises(RuleViolation):
            tomledit.set_top_field('status = "unverified"\n', "status", "verified")


if __name__ == "__main__":
    unittest.main()

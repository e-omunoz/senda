"""Cadenas de Core/Locale.lua: cada clave en español y en inglés, cada `L.CLAVE` del código definida, y ningún
carácter que las fuentes del juego no tienen (→ ← ≈ ≥ ...) en el Lua escrito a mano."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from common import GLYPH_FALLBACK  # noqa: E402
ADDON = ROOT / "addon"
LOCALE = ADDON / "Senda" / "Core" / "Locale.lua"

KEY_RE = re.compile(r"\b([A-Za-z_]\w*)\s*=(?!=)")
# Caracteres que faltan en las fuentes del juego (tools/common.py GLYPH_FALLBACK los cambia en el Lua generado).
BAD_GLYPHS = "".join(GLYPH_FALLBACK) + "✓✔✗"


def strip_lua(src: str) -> str:
    """Quita comentarios y el contenido de las cadenas (deja comillas vacías), para contar llaves y claves."""
    out: list[str] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if src.startswith("--", i):
            m = re.match(r"--\[(=*)\[", src[i:])
            if m:
                end = src.find("]" + m.group(1) + "]", i + len(m.group(0)))
                i = n if end < 0 else end + len(m.group(1)) + 2
            else:
                end = src.find("\n", i)
                i = n if end < 0 else end
            continue
        m = re.match(r"\[(=*)\[", src[i:i + 40]) if c == "[" else None
        if m:
            end = src.find("]" + m.group(1) + "]", i + len(m.group(0)))
            out.append('""')
            i = n if end < 0 else end + len(m.group(1)) + 2
            continue
        if c in "\"'":
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if src[j] == "\\" else 1
            out.append('""')
            i = j + 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def table_keys(body: str) -> set[str]:
    """Claves de primer nivel de una tabla `{ ... }` (sin comentarios ni cadenas)."""
    keys: set[str] = set()
    depth = 0
    buf: list[str] = []
    for c in body:
        if c in "{(":
            depth += 1
        elif c in "})":
            depth -= 1
        elif depth == 0:
            buf.append(c)
            continue
        if depth == 0:
            buf.append(" ")
    for m in KEY_RE.finditer("".join(buf)):
        keys.add(m.group(1))
    return keys


def tables(src: str) -> list[tuple[str, set[str], set[str]]]:
    """[(dónde, claves es, claves en)] de las tablas base (esES/enUS) y de cada Senda:AddLocale({es}, {en})."""
    s = strip_lua(src)

    def block(start: int) -> tuple[str, int]:
        depth = 0
        for j in range(start, len(s)):
            if s[j] == "{":
                depth += 1
            elif s[j] == "}":
                depth -= 1
                if depth == 0:
                    return s[start + 1:j], j + 1
        raise AssertionError("llave sin cerrar")

    out = []
    es_at = s.index("local esES = {")
    en_at = s.index("local enUS = {")
    es, _ = block(s.index("{", es_at))
    en, _ = block(s.index("{", en_at))
    out.append(("esES/enUS", table_keys(es), table_keys(en)))
    for m in re.finditer(r"Senda:AddLocale\(\{", s):
        es, end = block(m.end() - 1)
        rest = s[end:end + 10]
        if not rest.lstrip().startswith(","):
            out.append((f"AddLocale@{s.count(chr(10), 0, m.start()) + 1}", table_keys(es), set()))
            continue
        en, _ = block(s.index("{", end))
        out.append((f"AddLocale@{s.count(chr(10), 0, m.start()) + 1}", table_keys(es), table_keys(en)))
    return out


def handwritten_lua() -> list[Path]:
    out = []
    for p in sorted(ADDON.rglob("*.lua")):
        head = p.read_text(encoding="utf-8", errors="replace")[:200]
        if "GENERADO" in head or "GENERATED" in head:
            continue
        out.append(p)
    return out


class LocaleKeysTest(unittest.TestCase):
    def test_every_key_in_both_languages(self):
        problems = []
        for where, es, en in tables(LOCALE.read_text(encoding="utf-8")):
            if not en:
                continue
            for k in sorted(es - en):
                problems.append(f"{where}: {k} sin inglés")
            for k in sorted(en - es):
                problems.append(f"{where}: {k} sin español")
        self.assertEqual(problems, [], "\n".join(problems))

    def test_used_keys_are_defined(self):
        defined: set[str] = set()
        for _, es, en in tables(LOCALE.read_text(encoding="utf-8")):
            defined |= es | en
        used: dict[str, str] = {}
        for p in handwritten_lua():
            src = strip_lua(p.read_text(encoding="utf-8"))
            for m in re.finditer(r"\bL\.([A-Za-z_]\w*)\b(\s*or\b)?", src):
                if m.group(2):  # `L.X or "respaldo"`: opcional a propósito
                    continue
                used.setdefault(m.group(1), str(p.relative_to(ROOT)))
        missing = sorted(f"{k} ({f})" for k, f in used.items() if k not in defined)
        self.assertEqual(missing, [], "claves usadas sin definir:\n" + "\n".join(missing))

    def test_no_missing_glyphs_in_handwritten_lua(self):
        bad = []
        for p in handwritten_lua():
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if line.lstrip().startswith("--"):
                    continue
                hit = [c for c in BAD_GLYPHS if c in line]
                if hit:
                    bad.append(f"{p.relative_to(ROOT)}:{n}: {''.join(hit)}")
        self.assertEqual(bad, [], "caracteres que las fuentes del juego no tienen:\n" + "\n".join(bad))


if __name__ == "__main__":
    unittest.main()

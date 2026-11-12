"""Comprobación de sintaxis de todo el Lua del addon, sin depender de luacheck.

CI ya corre luac -p y luacheck. En una máquina sin ninguno de los dos este test hace lo que puede:
  1. si hay luac (5.1 mejor) o luajit, compila cada archivo con él (luac -p / luajit -bl);
  2. si no, pasa un analizador léxico de Lua 5.1 en Python puro que comprueba cadenas y comentarios
     cerrados y bloques (function/do/if ... end, repeat ... until) y paréntesis equilibrados.
No sustituye a luacheck (no mira variables globales ni sin uso); solo atrapa un `end` de más o de menos.

    python -m unittest discover -s tests -p "test_lua_syntax.py" -v
"""
from __future__ import annotations

import re
import shutil
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ADDON = REPO / "addon"

IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
NUMBER = re.compile(r"0[xX][0-9a-fA-F]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
LONG_OPEN = re.compile(r"\[(=*)\[")
SPACE = re.compile(r"[ \t\r\n,;=+*/%^#<>~:]+")
STRING = {q: re.compile(q + r"(?:[^" + q + r"\\\n]|\\[\s\S])*" + q) for q in "\"'"}
PAIRS = {")": "(", "]": "[", "}": "{"}


class LuaSyntaxError(Exception):
    pass


def _line(src: str, pos: int) -> int:
    return src.count("\n", 0, pos) + 1


def _skip_long(src: str, pos: int, level: str, what: str) -> int:
    """pos justo tras el `[==[` de apertura; devuelve la posición tras el cierre."""
    end = src.find("]" + level + "]", pos)
    if end < 0:
        raise LuaSyntaxError(f"línea {_line(src, pos)}: {what} sin cerrar")
    return end + len(level) + 2


def check_lua(src: str) -> None:
    """Lanza LuaSyntaxError si el código tiene cadenas/comentarios sin cerrar o bloques desequilibrados."""
    blocks: list[tuple[str, int]] = []  # (palabra que lo abrió, posición)
    brackets: list[tuple[str, int]] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c in " \t\r\n,;=+*/%^#<>~:":
            i = SPACE.match(src, i).end()
        elif src.startswith("--", i):
            m = LONG_OPEN.match(src, i + 2)
            if m:
                i = _skip_long(src, m.end(), m.group(1), "comentario largo")
            else:
                j = src.find("\n", i)
                i = n if j < 0 else j + 1
        elif c in "\"'":
            m = STRING[c].match(src, i)
            if not m:
                raise LuaSyntaxError(f"línea {_line(src, i)}: cadena sin cerrar")
            i = m.end()
        elif c == "[" and LONG_OPEN.match(src, i):
            m = LONG_OPEN.match(src, i)
            i = _skip_long(src, m.end(), m.group(1), "cadena larga")
        elif c.isalpha() or c == "_":
            m = IDENT.match(src, i)
            word = m.group(0)
            i = m.end()
            pos = m.start()
            if word in ("function", "do", "if"):
                blocks.append((word, pos))
            elif word == "repeat":
                blocks.append((word, pos))
            elif word == "end":
                if not blocks or blocks[-1][0] == "repeat":
                    raise LuaSyntaxError(f"línea {_line(src, pos)}: `end` sin bloque abierto"
                                         + (f" (abierto `repeat` en la línea {_line(src, blocks[-1][1])})" if blocks else ""))
                blocks.pop()
            elif word == "until":
                if not blocks or blocks[-1][0] != "repeat":
                    raise LuaSyntaxError(f"línea {_line(src, pos)}: `until` sin `repeat`")
                blocks.pop()
        elif c.isdigit() or (c == "." and i + 1 < n and src[i + 1].isdigit()):
            m = NUMBER.match(src, i)
            i = m.end() if m else i + 1
        else:
            if c in "([{":
                brackets.append((c, i))
            elif c in PAIRS:
                if not brackets or brackets[-1][0] != PAIRS[c]:
                    raise LuaSyntaxError(f"línea {_line(src, i)}: `{c}` sin su pareja")
                brackets.pop()
            i += 1
    if blocks:
        word, pos = blocks[-1]
        raise LuaSyntaxError(f"falta el cierre del bloque `{word}` abierto en la línea {_line(src, pos)}")
    if brackets:
        ch, pos = brackets[-1]
        raise LuaSyntaxError(f"`{ch}` de la línea {_line(src, pos)} sin cerrar")


def lua_files() -> list[Path]:
    return sorted(ADDON.rglob("*.lua"))


def external_compiler() -> list[str] | None:
    """Comando que comprueba la sintaxis de un archivo (se le añade la ruta), o None."""
    for name in ("luac5.1", "luac51", "luac"):
        exe = shutil.which(name)
        if exe:
            return [exe, "-p"]
    exe = shutil.which("luajit")
    if exe:
        return [exe, "-bl"]  # -bl lista el bytecode: compilar basta; la salida se descarta
    return None


class TokenizerSelfTest(unittest.TestCase):
    GOOD = [
        "local x = 1",
        "function f() if a then return 1 elseif b then return 2 else return 3 end end",
        "for i = 1, 3 do while x do repeat y() until z end end",
        "local s = 'don\\'t end' .. \"it's [[not]] a block\" -- function if do",
        "local t = [==[ end ]] if ]==] --[[ do ]] --[=[ function ]=] return t",
        "local f = function(a, b) return { a, [b] = (a + b) } end",
        "local x = 3.5e-2 + .5 + 0xFF",
        "if a then repeat if b then c() end until d end",
        "",
    ]
    BAD = {
        "end": "sin bloque",
        "function f() if a then return 1 end": "falta el cierre",
        "if a then x() end end": "sin bloque",
        "repeat x() end": "sin bloque",
        "do x() until y": "sin `repeat`",
        "local s = 'abc": "cadena sin cerrar",
        "local s = [[abc": "cadena larga sin cerrar",
        "--[[ abc": "comentario largo sin cerrar",
        "local t = { 1, 2": "sin cerrar",
        "local t = (1))": "sin su pareja",
        "x = {(})": "sin su pareja",
    }

    def test_good(self):
        for src in self.GOOD:
            with self.subTest(src=src):
                check_lua(src)

    def test_bad(self):
        for src, expect in self.BAD.items():
            with self.subTest(src=src):
                with self.assertRaises(LuaSyntaxError) as cm:
                    check_lua(src)
                self.assertIn(expect, str(cm.exception))


class AddonSyntax(unittest.TestCase):
    def test_there_are_files(self):
        self.assertGreater(len(lua_files()), 20)

    def test_pure_python_tokenizer(self):
        """Siempre corre: no depende de ningún compilador de Lua."""
        errors = []
        for path in lua_files():
            try:
                check_lua(path.read_text(encoding="utf-8"))
            except LuaSyntaxError as e:
                errors.append(f"{path.relative_to(REPO)}: {e}")
            except UnicodeDecodeError as e:
                errors.append(f"{path.relative_to(REPO)}: no es UTF-8 ({e})")
        self.assertEqual(errors, [], "\n" + "\n".join(errors))

    def test_external_compiler(self):
        cmd = external_compiler()
        if not cmd:
            self.skipTest("no hay luac ni luajit en el PATH (CI sí corre luac -p y luacheck)")
        errors = []
        for path in lua_files():
            r = subprocess.run(cmd + [str(path)], capture_output=True, text=True)
            if r.returncode != 0:
                errors.append(f"{path.relative_to(REPO)}: {(r.stderr or r.stdout).strip()[:300]}")
        self.assertEqual(errors, [], "\n" + "\n".join(errors))


if __name__ == "__main__":
    unittest.main()

"""Analizador de literales de tabla Lua (solo datos, nunca ejecuta código).

Entiende lo que generan los compiladores de Polestar (`Guides.lua`, locales de textos):

- cadenas "..." y '...' con escapes de Lua 5.1, cadenas largas [[...]] / [==[...]==];
- números (enteros, decimales, exponentes, hexadecimales), true / false / nil;
- tablas { a, b, k = v, ["k"] = v, [1] = v } con separadores , y ;
- referencias a locales ya leídas y su índice: `candidateRecords[6]`, `candidateLists[1]`.

`parse_value(text)` lee un único valor; `scan_block(text)` recorre un bloque `do ... end` y devuelve las
asignaciones `local x = <valor>` y los argumentos de cada llamada `Polestar.<Func>(<valor>)`.
Todo lo demás (function, end, register()...) se ignora.
"""
from __future__ import annotations

import re
from typing import Any

_NUM_RE = re.compile(r"0[xX][0-9a-fA-F]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_LONG_OPEN_RE = re.compile(r"\[(=*)\[")

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "f": "\f", "v": "\v",
            "\\": "\\", '"': '"', "'": "'", "\n": "\n"}


class LuaParseError(ValueError):
    pass


class Tok:
    __slots__ = ("kind", "value", "pos")

    def __init__(self, kind: str, value: Any, pos: int):
        self.kind, self.value, self.pos = kind, value, pos

    def __repr__(self) -> str:  # pragma: no cover - depuración
        return f"Tok({self.kind},{self.value!r}@{self.pos})"


def _read_string(src: str, i: int) -> tuple[str, int]:
    quote = src[i]
    i += 1
    out: list[str] = []
    n = len(src)
    while i < n:
        c = src[i]
        if c == quote:
            return "".join(out), i + 1
        if c == "\\":
            i += 1
            e = src[i] if i < n else ""
            if e in _ESCAPES:
                out.append(_ESCAPES[e])
                i += 1
            elif e.isdigit():
                j = i
                while j < n and j - i < 3 and src[j].isdigit():
                    j += 1
                out.append(chr(int(src[i:j])))
                i = j
            else:
                raise LuaParseError(f"escape desconocido \\{e} en {i}")
            continue
        if c == "\n":
            raise LuaParseError(f"cadena sin cerrar en {i}")
        out.append(c)
        i += 1
    raise LuaParseError("cadena sin cerrar al final")


def tokenize(src: str) -> list[Tok]:
    toks: list[Tok] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c in " \t\r\n":
            i += 1
            continue
        if src.startswith("--", i):
            m = _LONG_OPEN_RE.match(src, i + 2)
            if m:
                close = "]" + m.group(1) + "]"
                j = src.find(close, m.end())
                i = n if j < 0 else j + len(close)
            else:
                j = src.find("\n", i)
                i = n if j < 0 else j + 1
            continue
        if c in "\"'":
            s, i2 = _read_string(src, i)
            toks.append(Tok("str", s, i))
            i = i2
            continue
        if c == "[":
            m = _LONG_OPEN_RE.match(src, i)
            if m:
                close = "]" + m.group(1) + "]"
                j = src.find(close, m.end())
                if j < 0:
                    raise LuaParseError(f"cadena larga sin cerrar en {i}")
                body = src[m.end():j]
                if body.startswith("\r\n"):
                    body = body[2:]
                elif body.startswith("\n"):
                    body = body[1:]
                toks.append(Tok("str", body, i))
                i = j + len(close)
                continue
        if c.isdigit() or (c == "." and i + 1 < n and src[i + 1].isdigit()):
            m = _NUM_RE.match(src, i)
            assert m
            t = m.group(0)
            if t[:2].lower() == "0x":
                v: Any = int(t, 16)
            elif re.fullmatch(r"\d+", t):
                v = int(t)
            else:
                v = float(t)
            toks.append(Tok("num", v, i))
            i = m.end()
            continue
        if c.isalpha() or c == "_":
            m = _NAME_RE.match(src, i)
            assert m
            toks.append(Tok("name", m.group(0), i))
            i = m.end()
            continue
        if src.startswith("...", i) or src.startswith("..", i) or src.startswith("==", i) \
                or src.startswith("~=", i) or src.startswith("<=", i) or src.startswith(">=", i):
            w = 3 if src.startswith("...", i) else 2
            toks.append(Tok("op", src[i:i + w], i))
            i += w
            continue
        toks.append(Tok("op", c, i))
        i += 1
    return toks


class _Parser:
    def __init__(self, toks: list[Tok], env: dict[str, Any] | None = None):
        self.toks = toks
        self.i = 0
        self.env = env if env is not None else {}

    def peek(self, k: int = 0) -> Tok | None:
        j = self.i + k
        return self.toks[j] if j < len(self.toks) else None

    def next(self) -> Tok:
        t = self.peek()
        if t is None:
            raise LuaParseError("fin inesperado")
        self.i += 1
        return t

    def expect(self, kind: str, value: Any = None) -> Tok:
        t = self.next()
        if t.kind != kind or (value is not None and t.value != value):
            raise LuaParseError(f"se esperaba {value or kind} en {t.pos}, hay {t.value!r}")
        return t

    def is_op(self, v: str, k: int = 0) -> bool:
        t = self.peek(k)
        return t is not None and t.kind == "op" and t.value == v

    def value(self) -> Any:
        t = self.next()
        if t.kind == "str":
            return t.value
        if t.kind == "num":
            return t.value
        if t.kind == "op" and t.value == "-":
            v = self.value()
            if not isinstance(v, (int, float)):
                raise LuaParseError(f"'-' delante de algo que no es un número en {t.pos}")
            return -v
        if t.kind == "op" and t.value == "{":
            return self.table()
        if t.kind == "name":
            if t.value == "true":
                return True
            if t.value == "false":
                return False
            if t.value == "nil":
                return None
            if t.value not in self.env:
                raise LuaParseError(f"nombre desconocido {t.value!r} en {t.pos} (solo se admiten locales leídas)")
            v = self.env[t.value]
            while self.is_op("["):
                self.next()
                key = self.value()
                self.expect("op", "]")
                v = _index(v, key)
            return v
        raise LuaParseError(f"valor inesperado {t.value!r} en {t.pos}")

    def table(self) -> Any:
        arr: list[Any] = []
        hsh: dict[Any, Any] = {}
        while not self.is_op("}"):
            if self.is_op("["):
                self.next()
                key = self.value()
                self.expect("op", "]")
                self.expect("op", "=")
                hsh[key] = self.value()
            elif (t := self.peek()) is not None and t.kind == "name" and self.is_op("=", 1) \
                    and t.value not in ("true", "false", "nil"):
                self.next()
                self.next()
                hsh[t.value] = self.value()
            else:
                arr.append(self.value())
            if self.is_op(",") or self.is_op(";"):
                self.next()
            elif not self.is_op("}"):
                t = self.peek()
                raise LuaParseError(f"se esperaba ',' o '}}' en {t.pos if t else 'EOF'}")
        self.next()
        if not hsh:
            return arr
        for k, v in enumerate(arr, 1):
            hsh[k] = v
        return hsh


def _index(v: Any, key: Any) -> Any:
    if isinstance(v, list):
        if isinstance(key, int) and 1 <= key <= len(v):
            return v[key - 1]
        return None
    if isinstance(v, dict):
        return v.get(key)
    raise LuaParseError(f"no se puede indexar {type(v).__name__}")


def parse_value(src: str, env: dict[str, Any] | None = None) -> Any:
    """Lee un único valor (opcionalmente precedido de `return`)."""
    p = _Parser(tokenize(src), env)
    t = p.peek()
    if t is not None and t.kind == "name" and t.value == "return":
        p.next()
    return p.value()


def scan_block(src: str) -> tuple[dict[str, Any], list[tuple[str, Any]]]:
    """Recorre un bloque generado. Devuelve (locales, [(función de Polestar, argumento)])."""
    p = _Parser(tokenize(src))
    calls: list[tuple[str, Any]] = []
    while p.peek() is not None:
        t = p.peek()
        if t.kind == "name" and t.value == "local" and (n := p.peek(1)) and n.kind == "name" and p.is_op("=", 2):
            p.i += 3
            p.env[n.value] = p.value()
            continue
        if t.kind == "name" and t.value == "Polestar" and p.is_op(".", 1) and (f := p.peek(2)) \
                and f.kind == "name" and p.is_op("(", 3):
            p.i += 4
            if p.is_op(")"):
                calls.append((f.value, None))
            else:
                calls.append((f.value, p.value()))
            continue
        p.i += 1
    return p.env, calls

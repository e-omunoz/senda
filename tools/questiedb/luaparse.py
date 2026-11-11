"""Safe parser for Lua *data*: table constructors, literals and simple constant expressions.

Nothing is executed. Used for WoW SavedVariables (``Name = { ... }`` assignments) and for
reading literal tables out of QuestieDB/Questie Lua sources (zone tables, corrections).

Supported:
  * nil, true, false, numbers (decimal, hex, exponent), strings ('', "", [[ ]], [==[ ]==])
  * table constructors with ``[k] = v``, ``name = v`` and positional entries
  * names and dotted/indexed names, resolved through an optional ``env`` callable;
    anything unresolvable becomes the ``UNRESOLVED`` sentinel instead of failing
  * unary minus / ``not``, binary ``+ - * /`` and ``..`` on resolved constants
  * function calls are parsed and yield ``UNRESOLVED``

Tables are returned as :class:`LuaTable` (a dict subclass keyed exactly like Lua);
:func:`to_py` converts sequences (keys 1..n) into Python lists recursively.
"""

from __future__ import annotations

import re

__all__ = ["LuaTable", "UNRESOLVED", "LuaParseError", "parse_value", "parse_assignments",
           "parse_table_at", "to_py", "is_resolved"]


class LuaParseError(ValueError):
    pass


class _Unresolved:
    _inst = None

    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst

    def __repr__(self):
        return "UNRESOLVED"

    def __bool__(self):
        return False


UNRESOLVED = _Unresolved()


class LuaTable(dict):
    """A Lua table: a dict whose positional entries use integer keys starting at 1."""


_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<comment>--(?:\[(?P<cl>=*)\[[\s\S]*?\](?P=cl)\]|[^\n]*))
  | (?P<lstring>\[(?P<sl>=*)\[[\s\S]*?\](?P=sl)\])
  | (?P<number>0[xX][0-9a-fA-F]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)
  | (?P<string>"(?:[^"\\\n]|\\[\s\S])*"|'(?:[^'\\\n]|\\[\s\S])*')
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>\.\.\.|\.\.|==|~=|<=|>=|[{}\[\]=,;().+\-*/#<>:%^])
    """,
    re.VERBOSE,
)

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "f": "\f", "v": "\v",
            "\\": "\\", '"': '"', "'": "'", "\n": "\n"}


def _unescape(body: str) -> str:
    out = []
    i = 0
    n = len(body)
    while i < n:
        c = body[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        i += 1
        if i >= n:
            break
        c = body[i]
        if c in _ESCAPES:
            out.append(_ESCAPES[c])
            i += 1
        elif c.isdigit():
            j = i
            while j < n and j - i < 3 and body[j].isdigit():
                j += 1
            out.append(chr(int(body[i:j])))
            i = j
        elif c == "x":
            out.append(chr(int(body[i + 1:i + 3], 16)))
            i += 3
        elif c == "z":
            i += 1
            while i < n and body[i].isspace():
                i += 1
        else:
            out.append(c)
            i += 1
    # Lua strings are bytes; SavedVariables are UTF-8. Re-decode \ddd byte escapes.
    text = "".join(out)
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def _tokenize(src: str, start: int = 0):
    pos = start
    n = len(src)
    while pos < n:
        m = _TOKEN_RE.match(src, pos)
        if not m:
            raise LuaParseError(f"unexpected character {src[pos]!r} at offset {pos}")
        pos = m.end()
        kind = m.lastgroup
        if kind in ("ws", "comment", "cl", "sl"):
            if m.group("ws") is not None or m.group("comment") is not None:
                continue
        if m.group("lstring") is not None:
            text = m.group("lstring")
            eq = len(m.group("sl"))
            body = text[2 + eq:-(2 + eq)]
            if body.startswith("\r\n"):
                body = body[2:]
            elif body.startswith("\n"):
                body = body[1:]
            yield ("string", body, m.start())
        elif m.group("number") is not None:
            t = m.group("number")
            if t.lower().startswith("0x"):
                val = int(t, 16)
            elif re.fullmatch(r"\d+", t):
                val = int(t)
            else:
                val = float(t)
            yield ("number", val, m.start())
        elif m.group("string") is not None:
            yield ("string", _unescape(m.group("string")[1:-1]), m.start())
        elif m.group("name") is not None:
            yield ("name", m.group("name"), m.start())
        elif m.group("op") is not None:
            yield ("op", m.group("op"), m.start())
    yield ("eof", None, n)


class _Parser:
    def __init__(self, src: str, start: int = 0, env=None):
        self.tokens = _tokenize(src, start)
        self.env = env
        self.tok = next(self.tokens)
        self.peeked = None

    def advance(self):
        if self.peeked is not None:
            self.tok, self.peeked = self.peeked, None
        else:
            self.tok = next(self.tokens)

    def peek(self):
        if self.peeked is None:
            self.peeked = next(self.tokens)
        return self.peeked

    def accept(self, kind, value=None):
        if self.tok[0] == kind and (value is None or self.tok[1] == value):
            tok = self.tok
            self.advance()
            return tok
        return None

    def expect(self, kind, value=None):
        tok = self.accept(kind, value)
        if tok is None:
            raise LuaParseError(f"expected {value or kind}, got {self.tok[1]!r} at offset {self.tok[2]}")
        return tok

    # expression := unary (binop unary)*   (left-assoc, constant folding only)
    def expr(self):
        left = self.arith()
        # comparison / logic operators are not folded
        while (self.tok[0] == "op" and self.tok[1] in ("==", "~=", "<", ">", "<=", ">=")) or \
                (self.tok[0] == "name" and self.tok[1] in ("and", "or")):
            self.advance()
            self.arith()
            left = UNRESOLVED
        return left

    def arith(self):
        left = self.unary()
        while self.tok[0] == "op" and self.tok[1] in ("+", "-", "*", "/", ".."):
            op = self.tok[1]
            self.advance()
            right = self.unary()
            left = _binop(op, left, right)
        return left

    def unary(self):
        if self.accept("op", "-"):
            v = self.unary()
            return -v if isinstance(v, (int, float)) and not isinstance(v, bool) else UNRESOLVED
        if self.accept("name", "not"):
            v = self.unary()
            return UNRESOLVED if v is UNRESOLVED else (v is None or v is False)
        if self.accept("op", "#"):
            self.unary()
            return UNRESOLVED
        return self.primary()

    def primary(self):
        kind, val, _ = self.tok
        if kind == "number" or kind == "string":
            self.advance()
            return self.suffixes(val)
        if kind == "name":
            if val == "nil":
                self.advance()
                return None
            if val == "true":
                self.advance()
                return True
            if val == "false":
                self.advance()
                return False
            if val == "function":
                raise LuaParseError("function literals are not data")
            self.advance()
            path = [val]
            value = None
            resolved_path = True
            while True:
                if self.accept("op", "."):
                    path.append(self.expect("name")[1])
                elif self.tok == ("op", "[", self.tok[2]) and resolved_path:
                    self.advance()
                    key = self.expr()
                    self.expect("op", "]")
                    path.append(key)
                elif self.tok[0] == "op" and self.tok[1] in ("(", ":") or self.tok[0] == "string" \
                        or (self.tok[0] == "op" and self.tok[1] == "{"):
                    self.call_args()
                    resolved_path = False
                else:
                    break
            if not resolved_path:
                return UNRESOLVED
            value = self.resolve(path)
            return value
        if kind == "op" and val == "{":
            return self.suffixes(self.table())
        if kind == "op" and val == "(":
            self.advance()
            v = self.expr()
            self.expect("op", ")")
            return self.suffixes(v)
        raise LuaParseError(f"unexpected token {val!r} at offset {self.tok[2]}")

    def suffixes(self, value):
        while True:
            if self.accept("op", "["):
                key = self.expr()
                self.expect("op", "]")
                if isinstance(value, dict) and key is not UNRESOLVED:
                    value = value.get(key)
                else:
                    value = UNRESOLVED
            elif self.accept("op", "."):
                key = self.expect("name")[1]
                value = value.get(key) if isinstance(value, dict) else UNRESOLVED
            elif self.tok[0] == "op" and self.tok[1] in ("(", ":"):
                self.call_args()
                value = UNRESOLVED
            else:
                return value

    def call_args(self):
        if self.accept("op", ":"):
            self.expect("name")
        if self.tok[0] == "string":
            self.advance()
            return
        if self.tok[0] == "op" and self.tok[1] == "{":
            self.table()
            return
        self.expect("op", "(")
        if not self.accept("op", ")"):
            self.expr()
            while self.accept("op", ","):
                self.expr()
            self.expect("op", ")")

    def resolve(self, path):
        if self.env is None:
            return UNRESOLVED
        try:
            return self.env(path)
        except (KeyError, TypeError, IndexError):
            return UNRESOLVED

    def table(self):
        self.expect("op", "{")
        out = LuaTable()
        index = 1
        while not self.accept("op", "}"):
            if self.tok[0] == "op" and self.tok[1] == "[":
                self.advance()
                key = self.expr()
                self.expect("op", "]")
                self.expect("op", "=")
                value = self.expr()
                if key is not None:
                    if isinstance(key, float) and key.is_integer():
                        key = int(key)
                    if value is not None:
                        out[key] = value
            elif self.tok[0] == "name" and self.peek()[0] == "op" and self.peek()[1] == "=":
                key = self.tok[1]
                self.advance()
                self.advance()
                value = self.expr()
                if value is not None:
                    out[key] = value
            else:
                value = self.expr()
                if value is not None:
                    out[index] = value
                index += 1
            if not (self.accept("op", ",") or self.accept("op", ";")):
                self.expect("op", "}")
                break
        return out


def _binop(op, a, b):
    num = (int, float)
    if op == "..":
        if isinstance(a, (str, int, float)) and isinstance(b, (str, int, float)) \
                and not isinstance(a, bool) and not isinstance(b, bool):
            return f"{a}{b}"
        return UNRESOLVED
    if not (isinstance(a, num) and isinstance(b, num)) or isinstance(a, bool) or isinstance(b, bool):
        return UNRESOLVED
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        return a / b if b else UNRESOLVED
    return UNRESOLVED


def parse_value(src: str, env=None):
    """Parse a single Lua expression (typically a table constructor)."""
    p = _Parser(src, 0, env)
    value = p.expr()
    if p.tok[0] != "eof":
        raise LuaParseError(f"trailing input at offset {p.tok[2]}")
    return value


def parse_table_at(src: str, offset: int, env=None):
    """Parse the table constructor whose ``{`` is at ``offset``; returns (value, end_offset)."""
    if src[offset] != "{":
        raise LuaParseError("parse_table_at: offset does not point at '{'")
    p = _Parser(src, offset, env)
    value = p.table()
    return value, p.tok[2]


def parse_assignments(src: str, env=None) -> dict:
    """Parse a SavedVariables-style file: a sequence of ``Name = expr`` statements."""
    p = _Parser(src, 0, env)
    out = {}
    while p.tok[0] != "eof":
        if p.accept("op", ";"):
            continue
        name = p.expect("name")[1]
        if name == "local":
            name = p.expect("name")[1]
        p.expect("op", "=")
        out[name] = p.expr()
    return out


def is_resolved(value) -> bool:
    """True when ``value`` contains no UNRESOLVED anywhere."""
    if value is UNRESOLVED:
        return False
    if isinstance(value, dict):
        return all(is_resolved(k) and is_resolved(v) for k, v in value.items())
    if isinstance(value, list):
        return all(is_resolved(v) for v in value)
    return True


def to_py(value):
    """Convert LuaTables recursively: sequences (keys exactly 1..n) become lists."""
    if isinstance(value, dict):
        keys = list(value.keys())
        if keys and all(isinstance(k, int) and not isinstance(k, bool) for k in keys):
            n = len(keys)
            if min(keys) == 1 and max(keys) == n:
                return [to_py(value[i]) for i in range(1, n + 1)]
        if not keys:
            return []
        return {k: to_py(v) for k, v in value.items()}
    return value

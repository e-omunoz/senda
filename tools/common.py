"""Utilidades compartidas por las herramientas de Senda (solo stdlib).

- Raíz del repositorio y rutas estándar.
- Carga de TOML normalizada (fechas -> cadenas ISO).
- Serializador de valores Python -> Lua 5.1 determinista.
- Escritura de texto UTF-8 con finales de línea LF.
"""
from __future__ import annotations

import datetime as _dt
import math
import re
import sys
import tomllib
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent

GENERATED_HEADER = "GENERADO por tools/build.py — no editar"

LUA_KEYWORDS = frozenset(
    """and break do else elseif end false for function if in local nil not or
    repeat return then true until while goto""".split()
)
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


# --------------------------------------------------------------------------- rutas
class Paths:
    """Rutas estándar relativas a una raíz (el repo o un fixture de tests)."""

    def __init__(self, root: Path | str | None = None):
        self.root = Path(root).resolve() if root else REPO_ROOT
        self.data = self.root / "data"
        self.guides = self.data / "guides"
        self.shared = self.data / "shared"
        self.knowledge = self.data / "knowledge"
        self.locale = self.data / "locale"
        self.schema = self.root / "schema"
        self.addon = self.root / "addon" / "Senda"
        self.out_guides = self.addon / "Guides"
        self.out_knowledge = self.addon / "Knowledge"
        self.out_locale = self.addon / "Locale"
        self.out_data = self.addon / "Data"
        self.travel = self.data / "travel"
        self.rares = self.data / "rares"
        self.toc = self.addon / "Senda.toc"
        self.version_file = self.root / "VERSION"
        self.dist = self.root / "dist"
        # Los esquemas siempre salen del repo real si el fixture no trae los suyos.
        if not (self.schema / "section.schema.json").exists():
            self.schema = REPO_ROOT / "schema"

    def rel(self, p: Path) -> str:
        try:
            return Path(p).resolve().relative_to(self.root).as_posix()
        except ValueError:
            return Path(p).as_posix()


# --------------------------------------------------------------------------- TOML
def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return value.isoformat()
    return value


def load_toml(path: Path) -> dict:
    """Carga un TOML; las fechas TOML se convierten a cadenas ISO."""
    with open(path, "rb") as fh:
        return _normalize(tomllib.load(fh))


def read_version(paths: Paths) -> str:
    if not paths.version_file.exists():
        raise FileNotFoundError(f"falta {paths.rel(paths.version_file)}")
    v = paths.version_file.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", v):
        raise ValueError(f"VERSION no es SemVer: {v!r}")
    return v


# --------------------------------------------------------------------------- Lua
class LuaError(ValueError):
    pass


def lua_string(s: str) -> str:
    """Cadena Lua 5.1 entre comillas dobles con escapes.

    UTF-8 (español: ñ, á, «») se deja tal cual: Lua 5.1 trata las cadenas como bytes y
    el archivo se escribe en UTF-8. Los caracteres de control se escapan como \\ddd.
    """
    out = ['"']
    for ch in s:
        o = ord(ch)
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif o < 32 or o == 127:
            # Tres dígitos siempre, para que un dígito siguiente no se mezcle.
            out.append(f"\\{o:03d}")
        elif 0xD800 <= o <= 0xDFFF:
            raise LuaError(f"sustituto UTF-16 suelto en cadena: {s!r}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def lua_key(k: Any) -> str:
    if isinstance(k, bool):
        raise LuaError(f"clave booleana no admitida: {k!r}")
    if isinstance(k, int):
        return f"[{k}]"
    if not isinstance(k, str):
        raise LuaError(f"clave no admitida: {k!r}")
    if _IDENT_RE.match(k) and k not in LUA_KEYWORDS:
        return k
    return f"[{lua_string(k)}]"


def lua_number(n: int | float) -> str:
    if isinstance(n, bool):
        raise LuaError("bool no es número")
    if isinstance(n, int):
        return str(n)
    if math.isnan(n) or math.isinf(n):
        raise LuaError(f"número no representable en Lua: {n!r}")
    return repr(n)  # '29.9', '30.0', '1e-05': todos válidos en Lua


def _has_list_of_tables(v: Any) -> bool:
    if isinstance(v, list):
        return any(isinstance(x, dict) for x in v) or any(_has_list_of_tables(x) for x in v)
    if isinstance(v, dict):
        return any(_has_list_of_tables(x) for x in v.values())
    return False


def to_lua(value: Any, indent: int = 0, step: str = "  ", key_order: Iterable[str] | None = None,
           multiline: bool = False) -> str:
    """Serializa a Lua. Las tablas que contienen listas de tablas se escriben en varias líneas;
    el resto en una sola línea (un paso = una línea, diffs limpios)."""
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return lua_number(value)
    if isinstance(value, str):
        return lua_string(value)
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return lua_string(value.isoformat())
    if isinstance(value, (list, tuple)):
        if not value:
            return "{}"
        if multiline or _has_list_of_tables(value):
            pad = step * (indent + 1)
            items = [pad + to_lua(x, indent + 1, step) + "," for x in value]
            return "{\n" + "\n".join(items) + "\n" + step * indent + "}"
        return "{" + ", ".join(to_lua(x, indent, step) for x in value) + "}"
    if isinstance(value, dict):
        if not value:
            return "{}"
        keys = ordered_keys(value, key_order)
        if multiline or _has_list_of_tables(value):
            pad = step * (indent + 1)
            items = [f"{pad}{lua_key(k)} = {to_lua(value[k], indent + 1, step)}," for k in keys]
            return "{\n" + "\n".join(items) + "\n" + step * indent + "}"
        return "{ " + ", ".join(f"{lua_key(k)} = {to_lua(value[k], indent, step)}" for k in keys) + " }"
    raise LuaError(f"tipo no serializable a Lua: {type(value).__name__}")


def ordered_keys(d: dict, key_order: Iterable[str] | None = None) -> list:
    """Orden estable: primero las claves de `key_order` (en ese orden), luego el resto
    en el orden original del archivo (tomllib conserva el orden del TOML)."""
    if not key_order:
        return list(d.keys())
    order = list(key_order)
    first = [k for k in order if k in d]
    rest = [k for k in d if k not in order]
    return first + rest


# --------------------------------------------------------------------------- E/S
def write_text_lf(path: Path, text: str) -> bool:
    """Escribe UTF-8 + LF. Devuelve True si el contenido cambió."""
    text = text.replace("\r\n", "\n")
    if not text.endswith("\n"):
        text += "\n"
    data = text.encode("utf-8")
    path = Path(path)
    if path.exists() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    return True


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def setup_stdio() -> None:
    """Fuerza UTF-8 en stdout/stderr (consola de Windows)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

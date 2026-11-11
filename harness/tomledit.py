"""Edición mínima de TOML por líneas.

Objetivo: que el diff del PR sea lo más pequeño posible y respete el formato humano (comentarios,
orden, alineación). No se reescribe el archivo: se sustituye o inserta solo la(s) línea(s) de la clave.

Tras cada edición se vuelve a analizar el archivo con tomllib y se comprueba que solo ha cambiado
lo previsto. Escribir `status = "verified"` exige pasar por rules.assert_can_verify.
"""
from __future__ import annotations

import json
import math
import re
import tomllib

from . import rules


class TomlEditError(Exception):
    pass


_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def format_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            raise TomlEditError("valor no finito")
        r = repr(v)
        return r if ("." in r or "e" in r) else r + ".0"
    if isinstance(v, str):
        # json.dumps produce una cadena básica TOML válida (mismos escapes) con ensure_ascii=False.
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(format_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{_key(k)} = {format_value(x)}" for k, x in v.items()) + " }"
    raise TomlEditError(f"tipo no soportado: {type(v).__name__}")


def _key(k: str) -> str:
    return k if _BARE_KEY.match(k) else json.dumps(k)


def _newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _scan(lines: list[str]):
    """Recorre líneas devolviendo (idx, tipo, info) con tipo en header|kv|other, y el tramo de cada kv.

    Soporta valores multilínea (arrays y cadenas triples). Ignora '[' dentro de cadenas.
    """
    i = 0
    n = len(lines)
    out = []
    while i < n:
        raw = lines[i]
        s = raw.strip()
        if not s or s.startswith("#"):
            out.append((i, i + 1, "other", None))
            i += 1
            continue
        if s.startswith("["):
            out.append((i, i + 1, "header", s))
            i += 1
            continue
        m = re.match(r'^\s*("(?:[^"\\]|\\.)*"|[A-Za-z0-9_.-]+)\s*=\s*(.*)$', raw)
        if not m:
            out.append((i, i + 1, "other", None))
            i += 1
            continue
        key = m.group(1).strip('"')
        end = _value_end(lines, i, m.group(2))
        out.append((i, end, "kv", key))
        i = end
    return out


def _value_end(lines: list[str], start: int, first_value: str) -> int:
    """Índice (exclusivo) de la última línea del valor que empieza en `start`."""
    depth = 0
    in_str: str | None = None  # '"', "'", '"""', "'''"
    i = start
    text = first_value
    while True:
        j = 0
        while j < len(text):
            c = text[j]
            if in_str:
                if in_str in ('"""', "'''"):
                    if text.startswith(in_str, j):
                        in_str = None
                        j += 3
                        continue
                    if in_str == '"""' and c == "\\":
                        j += 2
                        continue
                elif in_str == '"':
                    if c == "\\":
                        j += 2
                        continue
                    if c == '"':
                        in_str = None
                elif in_str == "'" and c == "'":
                    in_str = None
                j += 1
                continue
            if text.startswith('"""', j) or text.startswith("'''", j):
                in_str = text[j:j + 3]
                j += 3
                continue
            if c in "\"'":
                in_str = c
            elif c in "[{":
                depth += 1
            elif c in "]}":
                depth -= 1
            elif c == "#":
                break
            j += 1
        if depth <= 0 and in_str not in ('"""', "'''"):
            return i + 1
        i += 1
        if i >= len(lines):
            raise TomlEditError("valor sin cerrar al final del archivo")
        text = lines[i]


def _step_blocks(lines: list[str], table: str = "step"):
    """[(inicio_header, fin_exclusivo, id, [entradas kv])] de cada [[table]]."""
    scan = _scan(lines)
    blocks = []
    cur = None
    for (a, b, kind, info) in scan:
        if kind == "header":
            if cur:
                blocks.append(cur)
                cur = None
            if re.fullmatch(r"\[\[\s*" + re.escape(table) + r"\s*\]\](\s*#.*)?", info):
                cur = {"start": a, "end": b, "id": None, "kvs": []}
            continue
        if cur is not None:
            cur["end"] = b
            if kind == "kv":
                cur["kvs"].append((a, b, info))
                if info == "id":
                    try:
                        cur["id"] = tomllib.loads("v = " + "".join(lines[a:b]).split("=", 1)[1])["v"]
                    except Exception:
                        pass
    if cur:
        blocks.append(cur)
    return blocks


def _find_block(lines: list[str], step_id: str, table: str = "step") -> dict:
    found = [b for b in _step_blocks(lines, table) if b["id"] == step_id]
    if not found:
        raise TomlEditError(f"paso {step_id!r} no encontrado")
    if len(found) > 1:
        raise TomlEditError(f"paso {step_id!r} duplicado")
    return found[0]


def get_step(text: str, step_id: str) -> dict:
    doc = tomllib.loads(text)
    for s in doc.get("step", []):
        if s.get("id") == step_id:
            return s
    raise TomlEditError(f"paso {step_id!r} no encontrado")


def _check_only_changed(before: str, after: str, step_id: str, key: str, expected) -> None:
    try:
        a = tomllib.loads(before)
        b = tomllib.loads(after)
    except tomllib.TOMLDecodeError as e:
        raise TomlEditError(f"la edición rompe el TOML: {e}") from e
    sa = [s for s in a.get("step", [])]
    sb = [s for s in b.get("step", [])]
    if len(sa) != len(sb) or {k: v for k, v in a.items() if k != "step"} != {k: v for k, v in b.items() if k != "step"}:
        raise TomlEditError("la edición alteró algo fuera del paso")
    for x, y in zip(sa, sb):
        if x.get("id") == step_id:
            x2 = dict(x)
            if expected is _DELETE:
                x2.pop(key, None)
            else:
                x2[key] = expected
            if x2 != y:
                raise TomlEditError(f"resultado inesperado al editar {step_id}.{key}")
        elif x != y:
            raise TomlEditError("la edición alteró otro paso")


_DELETE = object()
# Orden preferido al insertar claves nuevas (cerca de sus vecinas lógicas).
KEY_ORDER = ["id", "do", "quest", "quests", "obj", "npc", "item", "count", "spells", "level", "prof",
             "skill", "at", "wps", "radius", "node", "zone", "if", "optional", "chain", "link", "text",
             "tip", "note", "status", "sources", "checked"]


def set_step_field(text: str, step_id: str, key: str, value, *, evidence=None) -> str:
    """Pone `key = value` en el paso. Sustituye solo las líneas de esa clave o inserta una línea nueva.

    status = "verified" exige `evidence` (lista de rules.Evidence) que cumpla las reglas.
    """
    if key == "status":
        if value not in rules.STATUSES:
            raise TomlEditError(f"status inválido: {value!r}")
        if value == "verified":
            rules.assert_can_verify(evidence or [])
    if key == "id":
        raise TomlEditError("no se cambia el id de un paso (lo usa el progreso guardado)")
    nl = _newline(text)
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith(("\n", "\r")):
        lines[-1] += nl
    blk = _find_block(lines, step_id)
    new_line = f"{_key(key)} = {format_value(value)}{nl}"
    existing = [(a, b) for (a, b, k) in blk["kvs"] if k == key]
    if existing:
        a, b = existing[0]
        # conserva la sangría original
        indent = re.match(r"^\s*", lines[a]).group(0)
        # conserva un comentario de fin de línea en valores de una línea
        comment = ""
        if b - a == 1:
            m = re.search(r"(\s+#[^\"']*)$", lines[a].rstrip("\r\n"))
            if m:
                comment = m.group(1)
        new_line = f"{indent}{_key(key)} = {format_value(value)}{comment}{nl}"
        lines[a:b] = [new_line]
    else:
        # Inserta tras la última clave que vaya antes en KEY_ORDER; si no, tras la última clave.
        pos = None
        order = {k: i for i, k in enumerate(KEY_ORDER)}
        my = order.get(key, len(KEY_ORDER))
        for (a, b, k) in blk["kvs"]:
            if order.get(k, len(KEY_ORDER)) <= my:
                pos = b
        if pos is None:
            pos = blk["kvs"][0][0] if blk["kvs"] else blk["start"] + 1
        indent = re.match(r"^\s*", lines[blk["kvs"][0][0]]).group(0) if blk["kvs"] else ""
        lines.insert(pos, indent + new_line)
    out = "".join(lines)
    _check_only_changed(text, out, step_id, key, value)
    return out


def append_unique(text: str, step_id: str, key: str, items: list) -> str:
    cur = get_step(text, step_id).get(key, [])
    if not isinstance(cur, list):
        raise TomlEditError(f"{step_id}.{key} no es una lista")
    new = list(cur) + [x for x in items if x not in cur]
    if new == cur:
        return text
    return set_step_field(text, step_id, key, new)


def append_tip(text: str, step_id: str, tip: str, sep: str = " ") -> str:
    """Añade un consejo. Si ya hay `tip`, se concatena (no se pisa el del autor)."""
    tip = tip.strip()
    if not tip:
        return text
    cur = get_step(text, step_id).get("tip", "")
    if tip in cur:
        return text
    return set_step_field(text, step_id, "tip", (cur + sep + tip).strip() if cur else tip)


def set_status(text: str, step_id: str, status: str, evidence=None) -> str:
    if get_step(text, step_id).get("status") == status:
        return text
    return set_step_field(text, step_id, "status", status, evidence=evidence)


def append_table(text: str, table: str, values: dict) -> str:
    """Añade un [[table]] al final (p. ej. [[block]] en una página de conocimiento)."""
    nl = _newline(text)
    body = "".join(f"{_key(k)} = {format_value(v)}{nl}" for k, v in values.items())
    sep = "" if text.endswith(nl + nl) or not text else (nl if text.endswith(nl) else nl + nl)
    out = f"{text}{sep}[[{table}]]{nl}{body}"
    try:
        before = tomllib.loads(text) if text.strip() else {}
        after = tomllib.loads(out)
    except tomllib.TOMLDecodeError as e:
        raise TomlEditError(f"la edición rompe el TOML: {e}") from e
    if after.get(table, [])[-1] != values or len(after.get(table, [])) != len(before.get(table, [])) + 1:
        raise TomlEditError("append_table produjo un resultado inesperado")
    return out


def set_top_field(text: str, key: str, value) -> str:
    """Cambia una clave de primer nivel (antes de cualquier tabla). Uso: status/sources de una página."""
    if key == "status" and value == "verified":
        raise rules.RuleViolation("las páginas generadas por el harness no se marcan verified automáticamente")
    nl = _newline(text)
    lines = text.splitlines(keepends=True)
    scan = _scan(lines)
    first_header = next((a for (a, b, k, i) in scan if k == "header"), len(lines))
    for (a, b, k, info) in scan:
        if a >= first_header:
            break
        if k == "kv" and info == key:
            lines[a:b] = [f"{_key(key)} = {format_value(value)}{nl}"]
            out = "".join(lines)
            if tomllib.loads(out).get(key) != value:
                raise TomlEditError("set_top_field produjo un resultado inesperado")
            return out
    lines.insert(first_header, f"{_key(key)} = {format_value(value)}{nl}")
    out = "".join(lines)
    if tomllib.loads(out).get(key) != value:
        raise TomlEditError("set_top_field produjo un resultado inesperado")
    return out

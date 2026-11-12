"""Nombres del cliente por idioma: data/locale/<locale>/<tipo>.json (solo stdlib).

Un archivo por tipo de ficha (`{quest:N}`, `{npc:N}`...), con una entrada por id y su procedencia:

    {
      "kind": "quest",
      "locale": "esES",
      "names": {
        "155": {"name": "El camino de Ventormenta", "source": "ingame:1.60.1.70291:2026-11-12"},
        "456": {"name": "...", "source": "polestar-esES"}
      }
    }

Prioridad de las fuentes (una entrada solo la sustituye otra de prioridad igual o mayor):
  ingame:<build>:<fecha>   lo dijo el cliente (`/senda volcar` + tools/import_names.py)       3
  senda                    tabla propia comprobada (tools/polestar/spanish.py)                 2
  polestar-esES            nombre esES de Polestar (respaldo hasta que haya volcado)           1

tools/build.py compila cada carpeta en addon/Senda/Locale/Names_<locale>.lua (respaldo en el juego hasta que
el cliente responde).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# tipo de ficha -> nombre del archivo
KINDS: dict[str, str] = {
    "quest": "quests", "npc": "npcs", "item": "items", "spell": "spells", "map": "maps", "obj": "objects",
    "area": "areas",
}
# tipos que el cliente sabe nombrar por id (los que pide /senda volcar)
CLIENT_KINDS = ("quest", "npc", "item", "spell", "map", "area")

TOKEN_RE = re.compile(r"\{([a-z]+):(\d+)\}")
LOCALE_RE = re.compile(r"^[a-z]{2}[A-Z]{2}$")

SOURCE_POLESTAR = "polestar-esES"
SOURCE_SENDA = "senda"


def priority(source: str | None) -> int:
    s = source or ""
    if s.startswith("ingame:"):
        return 3
    if s == SOURCE_SENDA:
        return 2
    if s.startswith("polestar"):
        return 1
    return 0


def clean_name(name: Any) -> str | None:
    """Nombre utilizable: cadena sin saltos de línea ni tabuladores (el formato compilado los usa)."""
    if not isinstance(name, str):
        return None
    name = re.sub(r"[\t\r\n]+", " ", name).strip()
    return name or None


def locale_dir(data_root: Path, locale: str) -> Path:
    return Path(data_root) / "locale" / locale


def load(data_root: Path, locale: str) -> dict[str, dict[int, dict[str, str]]]:
    """{tipo: {id: {"name", "source"}}} de data/locale/<locale>/ (tipos sin archivo -> vacío)."""
    out: dict[str, dict[int, dict[str, str]]] = {k: {} for k in KINDS}
    d = locale_dir(data_root, locale)
    for kind, fname in KINDS.items():
        f = d / f"{fname}.json"
        if not f.is_file():
            continue
        doc = json.loads(f.read_text(encoding="utf-8"))
        names = doc.get("names") if isinstance(doc, dict) else None
        if not isinstance(names, dict):
            raise ValueError(f"{f}: falta el objeto 'names'")
        for sid, e in names.items():
            if not str(sid).isdigit() or not isinstance(e, dict):
                raise ValueError(f"{f}: entrada inválida {sid!r}")
            name = clean_name(e.get("name"))
            if name:
                out[kind][int(sid)] = {"name": name, "source": str(e.get("source") or "")}
    return out


def dumps(kind: str, locale: str, entries: dict[int, dict[str, str]]) -> str:
    """JSON estable: ids en orden numérico, una entrada por línea (diffs limpios)."""
    lines = ["{", f'  "kind": {json.dumps(kind)},', f'  "locale": {json.dumps(locale)},', '  "names": {']
    ids = sorted(entries)
    for i, ident in enumerate(ids):
        e = entries[ident]
        body = json.dumps({"name": e["name"], "source": e.get("source", "")}, ensure_ascii=False)
        lines.append(f'    "{ident}": {body}' + ("," if i < len(ids) - 1 else ""))
    lines += ["  }", "}"]
    return "\n".join(lines) + "\n"


def save(data_root: Path, locale: str, data: dict[str, dict[int, dict[str, str]]],
         kinds: list[str] | None = None) -> list[Path]:
    """Escribe los tipos con entradas (o los de `kinds`). Devuelve los archivos que cambiaron."""
    if not LOCALE_RE.match(locale):
        raise ValueError(f"idioma no válido: {locale!r}")
    d = locale_dir(data_root, locale)
    changed = []
    for kind, fname in KINDS.items():
        entries = data.get(kind) or {}
        if kinds is not None and kind not in kinds:
            continue
        if not entries and not (d / f"{fname}.json").exists():
            continue
        f = d / f"{fname}.json"
        text = dumps(kind, locale, entries)
        if f.exists() and f.read_text(encoding="utf-8") == text:
            continue
        d.mkdir(parents=True, exist_ok=True)
        with open(f, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        changed.append(f)
    return changed


def merge(data: dict[str, dict[int, dict[str, str]]], kind: str, ident: int, name: str,
          source: str) -> tuple[str, dict[str, str] | None]:
    """Pone un nombre respetando la prioridad. Devuelve (qué pasó, entrada anterior):
    "new" | "same" | "renamed" (mismo id, otro nombre, sustituido) | "kept" (la que había gana)."""
    name = clean_name(name)
    if kind not in KINDS or not name:
        return "kept", None
    table = data.setdefault(kind, {})
    old = table.get(ident)
    if old is None:
        table[ident] = {"name": name, "source": source}
        return "new", None
    if priority(source) < priority(old.get("source")):
        return "kept", old
    table[ident] = {"name": name, "source": source}
    if old["name"] == name:
        return "same", old
    return "renamed", old


def locales(data_root: Path) -> list[str]:
    base = Path(data_root) / "locale"
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir() and LOCALE_RE.match(p.name))


def pack(entries: dict[int, dict[str, str]]) -> str:
    """"<id>\\t<nombre>" por línea, en orden de id (formato de Names:AddFallback en el addon)."""
    return "\n".join(f"{i}\t{entries[i]['name']}" for i in sorted(entries))


PLACEHOLDER_ES = {"quest": "Misión #{}", "npc": "PNJ #{}", "item": "Objeto #{}", "spell": "Hechizo #{}",
                  "map": "Zona #{}", "obj": "Objeto del mundo #{}", "area": "Lugar #{}"}


def resolver(data_root: Path, locales: tuple[str, ...] = ("esES", "enUS")):
    """Función texto -> texto que sustituye las fichas por los nombres de data/locale/ (para la web, que no
    tiene cliente): el primer idioma que lo tenga; si ninguno, «Misión #N» como en el addon."""
    tables = [load(data_root, loc) for loc in locales if locale_dir(data_root, loc).is_dir()]

    def sub(m: re.Match) -> str:
        kind, ident = m.group(1), int(m.group(2))
        if kind not in KINDS:
            return m.group(0)
        for t in tables:
            e = t.get(kind, {}).get(ident)
            if e:
                return e["name"]
        return PLACEHOLDER_ES[kind].format(ident)

    def resolve(text: str) -> str:
        return TOKEN_RE.sub(sub, text) if isinstance(text, str) and "{" in text else text
    return resolve

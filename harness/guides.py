"""Lectura de guías y secciones TOML (data/)."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from . import config
from .config import rel


@dataclass
class Section:
    guide: str
    file: Path
    doc: dict

    @property
    def id(self) -> str:
        return self.doc.get("id", self.file.stem)

    @property
    def rel(self) -> str:
        return rel(self.file)

    @property
    def steps(self) -> list[dict]:
        return self.doc.get("step", [])

    def text(self) -> str:
        return self.file.read_text(encoding="utf-8")


@dataclass
class Guide:
    id: str
    file: Path
    doc: dict

    @property
    def races(self) -> list[str]:
        return list(self.doc.get("races", []))

    @property
    def classes(self) -> list[str]:
        return list(self.doc.get("classes", []))


def _load(p: Path) -> dict:
    with open(p, "rb") as f:
        return tomllib.load(f)


def list_guides(data: Path | None = None) -> list[Guide]:
    data = data or config.DATA
    out = []
    for p in sorted((data / "guides").glob("*/guide.toml")):
        try:
            doc = _load(p)
        except tomllib.TOMLDecodeError:
            continue
        out.append(Guide(doc.get("id", p.parent.name), p, doc))
    return out


def _resolve_section(guide_dir: Path, ref: str, data: Path) -> Path | None:
    if ref.startswith("shared:"):
        p = data / "shared" / f"{ref[7:]}.toml"
        return p if p.exists() else None
    p = guide_dir / f"{ref}.toml"
    if p.exists():
        return p
    for cand in sorted(guide_dir.glob(f"*{ref}.toml")):
        if cand.name != "guide.toml":
            return cand
    for cand in sorted(guide_dir.glob("*.toml")):
        if cand.name != "guide.toml":
            try:
                if _load(cand).get("id") == ref:
                    return cand
            except tomllib.TOMLDecodeError:
                continue
    return None


def sections_of(guide: Guide, data: Path | None = None) -> list[Section]:
    data = data or config.DATA
    out = []
    refs = guide.doc.get("sections")
    if refs:
        for ref in refs:
            p = _resolve_section(guide.file.parent, ref, data)
            if p:
                out.append(Section(guide.id, p, _load(p)))
    else:
        for p in sorted(guide.file.parent.glob("*.toml")):
            if p.name != "guide.toml":
                out.append(Section(guide.id, p, _load(p)))
    return out


def all_sections(guide_id: str | None = None, data: Path | None = None) -> list[Section]:
    data = data or config.DATA
    seen: set[Path] = set()
    out = []
    for g in list_guides(data):
        if guide_id and g.id != guide_id:
            continue
        for s in sections_of(g, data):
            if s.file not in seen:   # las secciones compartidas se auditan una vez
                seen.add(s.file)
                out.append(s)
    return out


def step_index(data: Path | None = None) -> dict[str, tuple[Path, dict]]:
    """step_id -> (archivo, paso) de todas las secciones (guías y compartidas)."""
    data = data or config.DATA
    idx: dict[str, tuple[Path, dict]] = {}
    files = list((data / "guides").glob("*/*.toml")) + list((data / "shared").glob("*.toml"))
    for p in sorted(files):
        if p.name == "guide.toml":
            continue
        try:
            doc = _load(p)
        except tomllib.TOMLDecodeError:
            continue
        for s in doc.get("step", []):
            if "id" in s:
                idx[s["id"]] = (p, s)
    return idx


def supported_classes_races(data: Path | None = None) -> list[tuple[str, str, str]]:
    """[(guide_id, raza, clase)] de las guías existentes."""
    data = data or config.DATA
    out = []
    for g in list_guides(data):
        for r in g.races or ["*"]:
            for c in g.classes or ["*"]:
                out.append((g.id, r, c))
    if not out:   # aún no hay guías: las previstas en ARCHITECTURE.md
        out = [("gnome-warlock", "Gnome", "WARLOCK"), ("human-mage", "Human", "MAGE")]
    return out

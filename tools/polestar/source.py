"""Acceso de solo lectura a un clon de Polestar: guías compiladas, nombres esES y textos esES.

Rutas (relativas al clon):
  addon/Polestar_Guides*/Guides.lua                       guías compiladas (una RegisterGuide por guía)
  addon/Polestar_esES/Names.lua                           nombres esES por tipo ("<id>\\t<nombre>" por línea)
  guides/locales/esES/<guía>.lua                          traducciones de las notas: { ["inglés"] = "español" }
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from . import luaparse

_SOURCE_RE = re.compile(r"^-- Source: (.+?)\.guide\s*$", re.M)
_CHUNK_RE = re.compile(r'R\("([a-z]+)",\s*\d+,\s*\d+,\s*\[(=*)\[(.*?)\]\2\]\)', re.S)
_PCT_RE = re.compile(r"%([0-9A-Fa-f]{2})")


class PolestarSource:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        if not (self.root / "addon").is_dir():
            raise FileNotFoundError(f"{self.root} no parece un clon de Polestar (falta addon/)")
        self._names: dict[str, dict[int, str]] | None = None

    # --- versión
    def commit(self) -> str:
        try:
            out = subprocess.run(["git", "-C", str(self.root), "rev-parse", "HEAD"], capture_output=True,
                                 text=True, check=True)
            return out.stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return "unknown"

    # --- guías compiladas
    def guide_files(self) -> list[Path]:
        return sorted((self.root / "addon").glob("Polestar_Guides*/Guides.lua"))

    def find_guide_block(self, guide_id: str) -> tuple[Path, str]:
        """Devuelve (archivo, texto del bloque `do ... end`) que registra la guía `guide_id`."""
        for f in self.guide_files():
            text = f.read_text(encoding="utf-8")
            marks = list(_SOURCE_RE.finditer(text))
            for k, m in enumerate(marks):
                if m.group(1) != guide_id:
                    continue
                end = marks[k + 1].start() if k + 1 < len(marks) else len(text)
                return f, text[m.end():end]
        raise KeyError(f"guía {guide_id!r} no encontrada en {', '.join(str(p) for p in self.guide_files())}")

    def load_guide(self, guide_id: str) -> tuple[Path, dict]:
        f, block = self.find_guide_block(guide_id)
        _, calls = luaparse.scan_block(block)
        for fn, arg in calls:
            if fn == "RegisterGuide" and isinstance(arg, dict) and arg.get("id") == guide_id:
                return f, arg
        raise KeyError(f"el bloque de {guide_id!r} no tiene RegisterGuide")

    # --- nombres esES
    def names(self) -> dict[str, dict[int, str]]:
        if self._names is None:
            self._names = {}
            f = self.root / "addon" / "Polestar_esES" / "Names.lua"
            if f.is_file():
                text = f.read_text(encoding="utf-8")
                for m in _CHUNK_RE.finditer(text):
                    kind = m.group(1)
                    d = self._names.setdefault(kind, {})
                    for line in m.group(3).split("\n"):
                        if "\t" not in line:
                            continue
                        sid, name = line.split("\t", 1)
                        if sid.strip().isdigit():
                            d[int(sid)] = _PCT_RE.sub(lambda x: chr(int(x.group(1), 16)), name.rstrip("\r"))
        return self._names

    def name_es(self, kind: str, ident: Any) -> str | None:
        try:
            return self.names().get(kind, {}).get(int(ident))
        except (TypeError, ValueError):
            return None

    # --- textos traducidos de la guía
    def texts_es(self, guide_id: str) -> dict[str, str]:
        f = self.root / "guides" / "locales" / "esES" / (guide_id + ".lua")
        if not f.is_file():
            return {}
        data = luaparse.parse_value(f.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str) and v}

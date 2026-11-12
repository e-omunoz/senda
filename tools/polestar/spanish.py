"""Textos en español para los pasos importados de Polestar.

Plantillas por tipo de objetivo, nombres de zonas y hechizos que no trae Names.lua de Polestar (los pone el
cliente) y artículos para PNJ con título («al Conservador Ilthalaine»). Términos del cliente esES.
"""
from __future__ import annotations

import re
from typing import Any, Callable

# Subzonas (area:N) en el cliente esES. Solo las comprobadas en las guías de Senda o en el cliente; las que
# no estén aquí se quedan en inglés y el informe las señala.
AREAS_ES: dict[int, str] = {
    186: "Dolanaar",
    188: "Cañada Umbría",
    256: "Aldrassil",
    258: "Roca Vil",
    259: "Lago Al'Ameth",
    260: "Villa Brisa Estelar",
    262: "Túmulo de Ban'ethil",
    264: "Claro del Oráculo",
    442: "Auberdine",
    478: "Pozas de Arlithrien",
    493: "Claro de la Luna",
    702: "Aldea Rut'theran",
    1519: "Ventormenta",
    1657: "Darnassus",
    1658: "Enclave Cenarion",
}

# uiMapID -> nombre esES (zonas que aparecen en las rutas de la Alianza).
ZONES_ES: dict[int, str] = {
    1438: "Teldrassil", 1439: "Costa Oscura", 1450: "Claro de la Luna", 1457: "Darnassus",
    1453: "Ventormenta", 1455: "Forjaz", 1426: "Dun Morogh", 1429: "Bosque de Elwynn",
}

# Subzona (area:N) -> uiMapID de la zona que la contiene (para `zone` de fly/hearth/sethearth).
AREA_ZONE: dict[int, int] = {
    186: 1438, 188: 1438, 256: 1438, 260: 1438, 702: 1438, 1657: 1457, 1658: 1457, 442: 1439, 493: 1450,
    2361: 1450, 1519: 1453,
}

SPELLS_ES: dict[int, str] = {
    1259799: "Luz de Elune",
    5487: "Forma de oso",
    18960: "Teletransporte: Claro de la Luna",
    1229451: "Descanso mejorado",
}

PROFS_ES: dict[str, str] = {
    "Alchemy": "Alquimia", "Herbalism": "Herboristería", "First Aid": "Primeros auxilios", "Skinning": "Desuello",
    "Leatherworking": "Peletería", "Cooking": "Cocina", "Fishing": "Pesca", "Mining": "Minería",
    "Tailoring": "Sastrería", "Enchanting": "Encantamiento", "Blacksmithing": "Herrería",
    "Engineering": "Ingeniería", "Staves": "Bastones",
}

# skillLine -> clave de profesión de Senda (Compat.PROF_SKILLLINE). Las armas (136 Bastones...) no son profesión.
SKILLLINE_PROF: dict[int, str] = {
    171: "alchemy", 164: "blacksmithing", 333: "enchanting", 202: "engineering", 182: "herbalism",
    165: "leatherworking", 186: "mining", 393: "skinning", 197: "tailoring", 185: "cooking", 356: "fishing",
    129: "firstaid",
}

_MASC = ("Conservador", "Posadero", "Capitán", "Sargento", "Alguacil", "Guardián", "Maestro", "Hermano",
         "Teniente", "Mensajero", "Instructor", "Archidruida", "Sumo", "Tabernero")
_FEM = ("Centinela", "Sacerdotisa", "Posadera", "Suma", "Guardiana", "Maestra", "Hermana", "Capitana", "Tabernera")


def npc_with(prep: str, name: str) -> str:
    """'de' / 'a' + PNJ, con artículo si el nombre empieza por un título: «del Conservador X», «a la Centinela Y»."""
    first = name.split(" ", 1)[0]
    if first in _MASC:
        return ("del " if prep == "de" else "al ") + name
    if first in _FEM:
        return ("de la " if prep == "de" else "a la ") + name
    return f"{prep} {name}"


TOKEN_RE = re.compile(r"\{([a-z]+):(\d+)\}")
_TOKEN_RE = TOKEN_RE


class Namer:
    """Pone nombres en español a ids de Polestar; recuerda los que se quedan en inglés."""

    def __init__(self, name_es: Callable[[str, Any], str | None], guide_names: dict[str, str]):
        self._es = name_es
        self._en = guide_names or {}
        self.missing: set[str] = set()

    def name(self, kind: str, ident: Any, fallback: str | None = None) -> str:
        try:
            i = int(ident)
        except (TypeError, ValueError):
            return fallback or str(ident)
        es: str | None = None
        if kind == "area":
            es = AREAS_ES.get(i)
        elif kind in ("zone", "map"):
            es = ZONES_ES.get(i)
        elif kind == "spell":
            es = SPELLS_ES.get(i)
        elif kind == "skill":
            en = self._en.get(f"skill:{i}")
            es = PROFS_ES.get(en or "")
        else:
            es = self._es(kind, i)
        if es:
            return es
        en = self._en.get(f"{kind}:{i}") or fallback
        if kind in ("npc", "quest", "item", "object", "area", "spell", "zone", "skill"):
            self.missing.add(f"{kind}:{i} {en or '?'}")
        return en or f"{kind}:{i}"

    def quest(self, ident: Any, fallback: str | None = None) -> str:
        return "«" + self.name("quest", ident, fallback) + "»"

    def render(self, text: str) -> str:
        """Sustituye los {kind:id} de un texto de Polestar por sus nombres."""
        def sub(m: re.Match) -> str:
            kind, i = m.group(1), m.group(2)
            if kind == "quest":
                return self.quest(i)
            return self.name(kind, i)
        return _TOKEN_RE.sub(sub, text)


def sentence(s: str) -> str:
    s = s.strip()
    if not s:
        return s
    s = s[0].upper() + s[1:]
    return s if s[-1] in ".!?:" else s + "."

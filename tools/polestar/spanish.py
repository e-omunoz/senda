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


def npc_with(prep: str, name: str, shown: str | None = None) -> str:
    """'de' / 'a' + PNJ, con artículo si el nombre empieza por un título: «del Conservador X», «a la Centinela Y».
    El artículo se decide con `name` (el nombre conocido); se escribe `shown` (p. ej. la ficha {npc:N})."""
    first = name.split(" ", 1)[0]
    out = shown if shown is not None else name
    if first in _MASC:
        return ("del " if prep == "de" else "al ") + out
    if first in _FEM:
        return ("de la " if prep == "de" else "a la ") + out
    return f"{prep} {out}"


TOKEN_RE = re.compile(r"\{([a-z]+):(\d+)\}")
_TOKEN_RE = TOKEN_RE

# Tipo de ficha de Polestar -> ficha de Senda (Core/Names.lua resuelve estas en el cliente).
# `zone` de Polestar es un uiMapID ({zone:1453} = Ventormenta) -> {map:N}. Las subzonas (area) y las
# habilidades (skill) no tienen ficha: se escriben con su nombre.
SENDA_TOKEN: dict[str, str] = {"quest": "quest", "npc": "npc", "item": "item", "object": "obj", "spell": "spell",
                               "zone": "map"}
_FROM_SENDA = {"quest": "quest", "npc": "npc", "item": "item", "obj": "object", "spell": "spell", "map": "zone"}

SOURCE_POLESTAR = "polestar-esES"
SOURCE_POLESTAR_EN = "polestar-enUS"
SOURCE_SENDA = "senda"


class Namer:
    """Pone nombres en español a ids de Polestar; recuerda los que se quedan en inglés.

    Con `tokens` (por defecto) los textos llevan fichas de Senda ({quest:N}, {npc:N}...): el nombre lo pone el
    cliente al mostrarlo. Los nombres esES conocidos se guardan en `fallback` ({tipo de Senda: {id: (nombre,
    fuente)}}) para escribirlos como respaldo en data/locale/esES/ (fuente polestar-esES o senda)."""

    def __init__(self, name_es: Callable[[str, Any], str | None], guide_names: dict[str, str], tokens: bool = True):
        self._es = name_es
        self._en = guide_names or {}
        self.tokens = tokens
        self.missing: set[str] = set()
        self.fallback: dict[str, dict[int, tuple[str, str]]] = {}
        # nombres en inglés de Polestar (enUS): respaldo de último recurso y el de un cliente en inglés
        self.fallback_en: dict[str, dict[int, tuple[str, str]]] = {}

    def es_name(self, kind: str, i: int) -> tuple[str | None, str]:
        """(nombre esES, fuente) o (None, "")."""
        if kind == "area":
            return AREAS_ES.get(i), SOURCE_SENDA
        if kind in ("zone", "map"):
            return ZONES_ES.get(i), SOURCE_SENDA
        if kind == "spell":
            return SPELLS_ES.get(i), SOURCE_SENDA
        if kind == "skill":
            en = self._en.get(f"skill:{i}")
            return PROFS_ES.get(en or ""), SOURCE_SENDA
        return self._es(kind, i), SOURCE_POLESTAR

    def name(self, kind: str, ident: Any, fallback: str | None = None) -> str:
        """Nombre escrito (esES si se conoce; si no, el inglés de Polestar)."""
        try:
            i = int(ident)
        except (TypeError, ValueError):
            return fallback or str(ident)
        es, _ = self.es_name(kind, i)
        if es:
            return es
        en = self._en.get(f"{kind}:{i}") or fallback
        if kind in ("npc", "quest", "item", "object", "area", "spell", "zone", "skill"):
            self.missing.add(f"{kind}:{i} {en or '?'}")
        return en or f"{kind}:{i}"

    def token(self, kind: str, ident: Any, fallback: str | None = None) -> str:
        """Ficha de Senda ({npc:467}) para el texto, guardando el nombre esES como respaldo. Sin ficha (área,
        habilidad, objeto del mundo sin nombre esES, que el cliente no sabe nombrar) se escribe el nombre."""
        sk = SENDA_TOKEN.get(kind)
        if not self.tokens or not sk:
            return self.name(kind, ident, fallback)
        try:
            i = int(ident)
        except (TypeError, ValueError):
            return self.name(kind, ident, fallback)
        es, src = self.es_name(kind, i)
        en = self._en.get(f"{kind}:{i}") or fallback
        if en and not str(en).isdigit():
            self.fallback_en.setdefault(sk, {})[i] = (str(en), SOURCE_POLESTAR_EN)
        if not es:
            if sk == "obj":
                return self.name(kind, ident, fallback)
            self.name(kind, ident, fallback)  # lo anota en `missing` para el informe
        else:
            self.fallback.setdefault(sk, {})[i] = (es, src)
        return "{%s:%d}" % (sk, i)

    def quest(self, ident: Any, fallback: str | None = None) -> str:
        return "«" + self.token("quest", ident, fallback) + "»"

    def render(self, text: str, tokens: bool | None = None) -> str:
        """Sustituye los {kind:id} de un texto de Polestar por fichas de Senda (o por nombres si tokens=False)."""
        use = self.tokens if tokens is None else tokens

        def sub(m: re.Match) -> str:
            kind, i = m.group(1), m.group(2)
            if kind == "quest":
                return "«" + (self.token(kind, i) if use else self.name(kind, i)) + "»"
            return self.token(kind, i) if use else self.name(kind, i)
        return _TOKEN_RE.sub(sub, text)

    def unrender(self, text: str) -> str:
        """Fichas de Senda -> nombres (para informes legibles)."""
        def sub(m: re.Match) -> str:
            kind = _FROM_SENDA.get(m.group(1))
            return self.name(kind, m.group(2)) if kind else m.group(0)
        return _TOKEN_RE.sub(sub, text or "")


def sentence(s: str) -> str:
    s = s.strip()
    if not s:
        return s
    s = s[0].upper() + s[1:]
    return s if s[-1] in ".!?:" else s + "."

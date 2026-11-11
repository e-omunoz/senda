#!/usr/bin/env python3
"""Generador del sitio estático de Senda (GitHub Pages). Solo stdlib.

    python tools/site.py                  # data/ del repo -> _site/
    python tools/site.py --out /tmp/web   # otra carpeta de salida
    python tools/site.py --root fixture/  # otra raíz (tests)
    python tools/site.py --no-validate    # no ejecutar tools/validate.py --json

Lee (todo opcional, funciona sin datos):
  data/guides/<id>/guide.toml + secciones, data/shared/*.toml, data/knowledge/**.toml,
  CHANGELOG.md, harness/reports/verify-latest.json y la salida de `tools/validate.py --json`.

Rutas publicadas (relativas a la raíz del sitio; los `link` de los pasos apuntan aquí):
  guias/<guide-id>/              una página por guía, ancla por sección y por paso
  <clase>/                       índice de conocimiento de la clase (brujo, mago, ..., general)
  <clase>/<página>/              página de conocimiento (p. ej. brujo/10-19#abisario)
  estado/                        estado de los datos (verificación)
  cambios/                       historial de cambios
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import tomllib
import unicodedata
from pathlib import Path
from string import Template
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_SRC = REPO_ROOT / "site"

SITE_URL = "https://e-omunoz.github.io/senda/"
REPO_URL = "https://github.com/e-omunoz/senda"
RELEASES_URL = REPO_URL + "/releases/latest"
# SIN CONFIRMAR: patrón de URL de Wowhead para WoW Forever. Cambiarlo solo aquí.
WOWHEAD_BASE = "https://www.wowhead.com/forever"

ROOT = "@@ROOT@@"  # marcador que se sustituye por la ruta relativa a la raíz en cada página

STATUSES = ("verified", "unverified", "disputed")
STATUS_ES = {"verified": "Verificado", "unverified": "Sin verificar", "disputed": "En disputa"}
STATUS_HELP = {
    "verified": "Contrastado con una fuente oficial, una observación en juego o la base de datos local "
                "más otra fuente independiente.",
    "unverified": "Pendiente de contrastar. Probablemente correcto, pero confírmalo en el juego.",
    "disputed": "Las fuentes no coinciden. Lee el consejo y compruébalo en el juego.",
}

CLASS_ORDER = ["WARRIOR", "PALADIN", "HUNTER", "ROGUE", "PRIEST", "SHAMAN", "MAGE", "WARLOCK", "DRUID", "ANY"]
CLASS_ES = {"WARRIOR": "Guerrero", "PALADIN": "Paladín", "HUNTER": "Cazador", "ROGUE": "Pícaro",
            "PRIEST": "Sacerdote", "SHAMAN": "Chamán", "MAGE": "Mago", "WARLOCK": "Brujo",
            "DRUID": "Druida", "ANY": "General"}
CLASS_SLUG = {"WARRIOR": "guerrero", "PALADIN": "paladin", "HUNTER": "cazador", "ROGUE": "picaro",
              "PRIEST": "sacerdote", "SHAMAN": "chaman", "MAGE": "mago", "WARLOCK": "brujo",
              "DRUID": "druida", "ANY": "general"}
RACE_ES = {"Human": "Humano", "Dwarf": "Enano", "NightElf": "Elfo de la noche", "Gnome": "Gnomo",
           "Orc": "Orco", "Scourge": "No-muerto", "Tauren": "Tauren", "Troll": "Trol", "Skyborne": "Skyborne"}
FACTION_ES = {"Alliance": "Alianza", "Horde": "Horda"}
PROF_ES = {"alchemy": "Alquimia", "blacksmithing": "Herrería", "enchanting": "Encantamiento",
           "engineering": "Ingeniería", "herbalism": "Herboristería", "leatherworking": "Peletería",
           "mining": "Minería", "skinning": "Desuello", "tailoring": "Sastrería", "cooking": "Cocina",
           "firstaid": "Primeros auxilios", "first_aid": "Primeros auxilios", "fishing": "Pesca",
           "jewelcrafting": "Joyería", "inscription": "Inscripción"}
KIND_ES = {"page": "Guía", "talents": "Talentos", "spells": "Hechizos", "macros": "Macros",
           "professions": "Profesiones", "rotation": "Rotación"}
KIND_SLUG = {"talents": "talentos", "spells": "hechizos", "macros": "macros",
             "professions": "profesiones", "rotation": "rotacion"}

STAT_ES = {"SP": "Poder con hechizos", "SCHOOL": "Escuela", "SCHOOL_W": "Daño de la escuela", "INT": "Intelecto",
           "MP5": "Maná cada 5 s", "STA": "Aguante", "SPI": "Espíritu", "ARMOR": "Armadura", "STR": "Fuerza",
           "AGI": "Agilidad", "AP": "Poder de ataque", "CRIT": "Crítico", "HIT": "Golpe", "SPELL_CRIT": "Crítico con hechizos",
           "SPELL_HIT": "Golpe con hechizos", "WAND_DPS": "DPS de varita", "WAND_DPS_30": "DPS de varita (desde 30)",
           "FROST": "Escarcha", "FIRE": "Fuego", "ARCANE": "Arcano", "SHADOW": "Sombras"}
# Claves de conocimiento que no se pintan como sección (metadatos o datos internos del addon).
KNOWN_KNOWLEDGE_KEYS = {"id", "class", "kind", "title", "summary", "levels", "order", "icon", "link", "race", "faction",
                        "status", "sources", "checked", "note", "alias", "check", "ids", "sellable", "order_profs",
                        "block", "pick", "train", "phase", "hud", "warning", "macro", "bar", "bindings", "weights",
                        "item", "route", "trainer", "rank", "material"}

# do -> (etiqueta, icono, familia de color)
DO_INFO = {
    "goto": ("Ir a", "goto", "travel"),
    "accept": ("Aceptar misión", "accept", "quest"),
    "complete": ("Completar", "complete", "combat"),
    "turnin": ("Entregar misión", "turnin", "quest"),
    "train": ("Entrenar", "train", "class"),
    "learn_prof": ("Aprender profesión", "learn_prof", "class"),
    "skill": ("Subir profesión", "skill", "class"),
    "buy": ("Comprar", "buy", "item"),
    "have": ("Conseguir", "have", "item"),
    "loot": ("Despojar", "loot", "item"),
    "use": ("Usar objeto", "use", "item"),
    "sethearth": ("Vincular piedra de hogar", "sethearth", "travel"),
    "hearth": ("Usar piedra de hogar", "hearth", "travel"),
    "getfp": ("Ruta de vuelo", "getfp", "travel"),
    "fly": ("Volar", "fly", "travel"),
    "level": ("Subir de nivel", "level", "class"),
    "dungeon": ("Mazmorra", "dungeon", "combat"),
    "note": ("Nota", "note", "note"),
}

# uiMapID estilo Classic usados por Forever (ver docs/FOREVER.md). Si falta, se muestra "mapa <id>".
MAP_NAMES = {
    1411: "Durotar", 1412: "Mulgore", 1413: "Los Baldíos", 1414: "Kalimdor", 1415: "Reinos del Este",
    1416: "Montañas de Alterac", 1417: "Tierras Altas de Arathi", 1418: "Tierras Inhóspitas",
    1419: "Las Tierras Devastadas", 1420: "Claros de Tirisfal", 1421: "Bosque de Argénteos",
    1422: "Tierras de la Peste del Oeste", 1423: "Tierras de la Peste del Este",
    1424: "Laderas de Trabalomas", 1425: "Tierras del Interior", 1426: "Dun Morogh",
    1427: "La Garganta de Fuego", 1428: "Las Estepas Ardientes", 1429: "Bosque de Elwynn",
    1430: "Paso de la Muerte", 1431: "Bosque del Ocaso", 1432: "Loch Modan",
    1433: "Montañas Crestagrana", 1434: "Vega de Tuercespina", 1435: "Pantano de las Penas",
    1436: "Páramos de Poniente", 1437: "Los Humedales", 1438: "Teldrassil", 1439: "Costa Oscura",
    1440: "Vallefresno", 1441: "Las Mil Agujas", 1442: "Sierra Espolón", 1443: "Desolace",
    1444: "Feralas", 1445: "Marjal Revolcafango", 1446: "Tanaris", 1447: "Azshara", 1448: "Frondavil",
    1449: "Cráter de Un'Goro", 1450: "Claro de la Luna", 1451: "Silithus", 1452: "Cuna del Invierno",
    1453: "Ventormenta", 1454: "Orgrimmar", 1455: "Forjaz", 1456: "Cima del Trueno",
    1457: "Darnassus", 1458: "Entrañas",
}

# Iconos de trazo (24x24, originales). Se incrustan una vez por página como <symbol>.
ICONS = {
    "goto": '<path d="M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z"/><circle cx="12" cy="10" r="2.5"/>',
    "accept": '<circle cx="12" cy="12" r="9"/><path d="M12 7v6"/><path d="M12 16.5v.5"/>',
    "turnin": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .8-1 1.5v.4"/><path d="M12 16.5v.5"/>',
    "complete": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4"/>',
    "train": '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5z"/><path d="M4 20.5A2.5 2.5 0 0 0 6.5 23H20v-5"/>',
    "learn_prof": '<path d="M14.5 5.5l4 4"/><path d="M3 21l7.5-7.5"/><path d="M12 6l3-3 6 6-3 3z"/><path d="M9.5 11.5l3 3"/>',
    "skill": '<path d="M4 20h16"/><path d="M7 16v-3M12 16V9M17 16V5"/>',
    "buy": '<path d="M5 8h14l-1.2 12H6.2z"/><path d="M9 8V6a3 3 0 0 1 6 0v2"/>',
    "have": '<path d="M4 8l8-4 8 4v8l-8 4-8-4z"/><path d="M4 8l8 4 8-4M12 12v8"/>',
    "loot": '<path d="M6 3h12l3 6-9 12L3 9z"/><path d="M3 9h18M9 3l3 6 3-6"/>',
    "use": '<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',
    "sethearth": '<path d="M3 11l9-7 9 7"/><path d="M5 9.5V20h14V9.5"/><path d="M10 20v-5h4v5"/>',
    "hearth": '<path d="M20 12a8 8 0 1 1-2.3-5.6"/><path d="M20 4v4h-4"/><circle cx="12" cy="12" r="2"/>',
    "getfp": '<path d="M5 21V4"/><path d="M5 4h12l-2.5 4L17 12H5"/>',
    "fly": '<path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4z"/>',
    "level": '<path d="M12 3l2.6 5.6 6.1.6-4.6 4.1 1.3 6L12 16.3 6.6 19.3l1.3-6-4.6-4.1 6.1-.6z"/>',
    "dungeon": '<path d="M4 21V9l2-2 2 2V5h8v4l2-2 2 2v12z"/><path d="M10 21v-4a2 2 0 0 1 4 0v4"/>',
    "note": '<path d="M5 3h10l4 4v14H5z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "moon": '<path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z"/>',
    "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
    "copy": '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h8"/>',
    "link": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7"/>',
    "alert": '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.5"/>',
    "dot": '<circle cx="12" cy="12" r="4"/>',
    "tip": '<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z"/>',
    "external": '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    "download": '<path d="M12 3v12M7 10l5 5 5-5"/><path d="M4 21h16"/>',
    "github": '<path d="M9 19c-4 1.5-4-2-6-2.5M15 22v-3.5c0-1 .1-1.4-.5-2 2.8-.3 5.5-1.4 5.5-6a4.6 4.6 0 0 0-1.3-3.2 4.2 4.2 0 0 0-.1-3.2s-1.1-.3-3.5 1.3a12 12 0 0 0-6.2 0C6.5 2.8 5.4 3.1 5.4 3.1a4.2 4.2 0 0 0-.1 3.2A4.6 4.6 0 0 0 4 9.5c0 4.6 2.7 5.7 5.5 6-.6.6-.6 1.2-.5 2V22"/>',
    "map": '<path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2z"/><path d="M9 4v14M15 6v14"/>',
    "shield": '<path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
    "skull": '<path d="M12 3a8 8 0 0 0-5 14.2V20h10v-2.8A8 8 0 0 0 12 3z"/><circle cx="9" cy="11" r="1.5"/><circle cx="15" cy="11" r="1.5"/><path d="M10 20v-2M14 20v-2"/>',
    "compass": '<circle cx="12" cy="12" r="9"/><path d="M15.5 8.5l-2 5-5 2 2-5z"/>',
    "people": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18.5 20a6.5 6.5 0 0 0-2.5-5.1"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
}


# =========================================================================== utilidades
def esc(v) -> str:
    return html.escape(str(v), quote=True)


def slugify(text) -> str:
    t = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")
    return t or "x"


def is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def as_list(v) -> list:
    return v if isinstance(v, list) else []


def levels_of(obj) -> tuple[int, int] | None:
    lv = obj.get("levels") if isinstance(obj, dict) else None
    if isinstance(lv, list) and len(lv) == 2 and all(is_int(x) for x in lv):
        return lv[0], lv[1]
    return None


def fmt_range(a, b) -> str:
    return f"{a}" if a == b else f"{a}–{b}"


def norm_status(v) -> str:
    return v if v in STATUSES else "unverified"


def map_name(m) -> str:
    return MAP_NAMES.get(m, f"mapa {m}") if is_int(m) else "mapa ?"


def class_es(c) -> str:
    return CLASS_ES.get(str(c).upper(), str(c).title())


def prof_es(p) -> str:
    return PROF_ES.get(str(p).lower(), str(p).capitalize())


def money(copper) -> str:
    if not is_int(copper):
        return ""
    g, rest = divmod(copper, 10000)
    s, c = divmod(rest, 100)
    parts = [f"{g} o"] if g else []
    if s:
        parts.append(f"{s} p")
    if c or not parts:
        parts.append(f"{c} c")
    return " ".join(parts)


def icon(name: str, cls: str = "") -> str:
    return f'<svg class="icon {cls}" aria-hidden="true" focusable="false"><use href="#i-{name}"/></svg>'


def icon_sprite() -> str:
    syms = "".join(f'<symbol id="i-{k}" viewBox="0 0 24 24">{v}</symbol>' for k, v in ICONS.items())
    return f'<svg xmlns="http://www.w3.org/2000/svg" class="sprite" aria-hidden="true">{syms}</svg>'


def wowhead(kind: str, ident) -> str:
    return f"{WOWHEAD_BASE}/{kind}={int(ident)}"


def wh_link(kind: str, ident, label: str) -> str:
    return (f'<a class="wh" href="{esc(wowhead(kind, ident))}" target="_blank" rel="noopener" '
            f'title="Ver en Wowhead">{esc(label)}</a>')


def site_href(link: str) -> str:
    """Convierte una ruta del sitio ("brujo/10-19#abisario") en href con marcador de raíz."""
    link = str(link).strip()
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", link) or link.startswith("//"):
        return link
    path, sep, frag = link.partition("#")
    path = path.strip("/")
    if path.endswith("index.html"):
        path = path[: -len("index.html")].rstrip("/")
    if path and "." not in path.rsplit("/", 1)[-1]:
        path += "/"
    return ROOT + path + (("#" + frag) if sep else "")


def link_key(link: str) -> tuple[str, str] | None:
    """(ruta de página, ancla) de un enlace interno, o None si es externo."""
    link = str(link).strip()
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", link) or link.startswith("//"):
        return None
    path, _, frag = link.partition("#")
    path = path.strip("/")
    if path.endswith("index.html"):
        path = path[: -len("index.html")].rstrip("/")
    return path, frag


def excerpt(text, n=160) -> str:
    t = re.sub(r"\s+", " ", re.sub(r"[*`#\[\]]|\]\([^)]*\)", "", str(text))).strip()
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


class Anchors:
    """Ids únicos dentro de una página."""

    def __init__(self, reserved=()):
        self.used = set(reserved)

    def get(self, base) -> str:
        b = slugify(base)
        a, n = b, 2
        while a in self.used:
            a, n = f"{b}-{n}", n + 1
        self.used.add(a)
        return a


# =========================================================================== markdown mínimo
_MD_CODE = re.compile(r"`([^`]+)`")
_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MD_ITAL = re.compile(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])")


def inline_md(text) -> str:
    """Escapa y aplica **negrita**, *cursiva*, `código` y [texto](url)."""
    parts = str(text).split("`")
    out = []
    for i, part in enumerate(parts):
        if i % 2 == 1 and i < len(parts) - 1:
            out.append(f"<code>{esc(part)}</code>")
            continue
        if i % 2 == 1:  # comilla sin cerrar
            part = "`" + part
        s = esc(part)

        def _link(m):
            label, url = m.group(1), html.unescape(m.group(2))
            if re.match(r"^https?://", url):
                return f'<a href="{esc(url)}" target="_blank" rel="noopener">{label}</a>'
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", url):  # javascript:, data:, ...
                return label
            return f'<a href="{esc(site_href(url))}">{label}</a>'

        s = _MD_LINK.sub(_link, s)
        s = _MD_BOLD.sub(r"<strong>\1</strong>", s)
        s = _MD_ITAL.sub(r"<em>\1</em>", s)
        out.append(s)
    return "".join(out)


def md(text, shift: int = 0, anchors: Anchors | None = None, toc: list | None = None) -> str:
    """Bloques: párrafos, listas '- ' y '1. ', encabezados '#', bloques ``` y citas '>'."""
    lines = str(text).replace("\r\n", "\n").split("\n")
    out: list[str] = []
    para: list[str] = []
    lst: str | None = None
    code: list[str] | None = None

    def flush_para():
        nonlocal para
        if para:
            out.append("<p>" + inline_md(" ".join(para)) + "</p>")
            para = []

    def close_list():
        nonlocal lst
        if lst:
            out.append(f"</{lst}>")
            lst = None

    for raw in lines:
        if code is not None:
            if raw.strip().startswith("```"):
                out.append("<pre><code>" + esc("\n".join(code)) + "</code></pre>")
                code = None
            else:
                code.append(raw)
            continue
        s = raw.strip()
        if s.startswith("```"):
            flush_para(); close_list()
            code = []
            continue
        if not s:
            flush_para(); close_list()
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            flush_para(); close_list()
            level = min(6, max(2, len(m.group(1)) + shift))
            title = m.group(2).strip()
            hid = anchors.get(title) if anchors else slugify(title)
            if toc is not None and level == 2:
                toc.append((hid, excerpt(title, 60)))
            out.append(f'<h{level} id="{hid}">{inline_md(title)}</h{level}>')
            continue
        m = re.match(r"^[-*+]\s+(.*)$", s)
        n = re.match(r"^\d+[.)]\s+(.*)$", s)
        if m or n:
            flush_para()
            want = "ul" if m else "ol"
            if lst != want:
                close_list()
                out.append(f"<{want}>")
                lst = want
            out.append("<li>" + inline_md((m or n).group(1)) + "</li>")
            continue
        if s.startswith(">"):
            flush_para(); close_list()
            out.append("<blockquote><p>" + inline_md(s.lstrip("> ")) + "</p></blockquote>")
            continue
        if lst and raw[:1] in (" ", "\t"):  # continuación de un elemento de lista
            out[-1] = out[-1][: -len("</li>")] + " " + inline_md(s) + "</li>"
            continue
        close_list()
        para.append(s)
    if code is not None:
        out.append("<pre><code>" + esc("\n".join(code)) + "</code></pre>")
    flush_para(); close_list()
    return "\n".join(out)


# =========================================================================== carga de datos
class Data:
    def __init__(self, root: Path):
        self.root = root
        self.warnings: list[str] = []
        self.guides: list[dict] = []
        self.knowledge: dict[str, list[dict]] = {}
        self.version = ""
        self.load()

    def rel(self, p: Path) -> str:
        try:
            return p.resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return p.as_posix()

    def toml(self, path: Path):
        try:
            with open(path, "rb") as fh:
                return tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
            self.warnings.append(f"{self.rel(path)}: no se pudo leer ({e})")
            return None

    def load(self):
        self._load_version()
        self._load_guides()
        self._load_knowledge()

    def _load_version(self):
        for p in (self.root / "VERSION",):
            if p.is_file():
                self.version = p.read_text(encoding="utf-8").strip()
                return
        toc = self.root / "addon" / "Senda" / "Senda.toc"
        if toc.is_file():
            m = re.search(r"^## Version:\s*(\S+)", toc.read_text(encoding="utf-8", errors="replace"), re.M)
            if m:
                self.version = m.group(1)

    def _section(self, path: Path, shared: bool):
        sec = self.toml(path)
        if not isinstance(sec, dict):
            return None
        sec = dict(sec)
        sec.setdefault("id", path.stem)
        sec["_shared"] = shared
        sec["_file"] = self.rel(path)
        sec["step"] = [s for s in as_list(sec.get("step")) if isinstance(s, dict)]
        return sec

    def _load_guides(self):
        gdir = self.root / "data" / "guides"
        if not gdir.is_dir():
            return
        for d in sorted(p for p in gdir.iterdir() if p.is_dir()):
            files = sorted(p for p in d.glob("*.toml") if p.name != "guide.toml")
            meta: dict = {}
            if (d / "guide.toml").is_file():
                m = self.toml(d / "guide.toml")
                if not isinstance(m, dict):
                    continue
                meta = dict(m)
            elif not files:
                continue
            meta.setdefault("id", d.name)
            refs = [r for r in as_list(meta.get("sections")) if isinstance(r, str)]
            if not refs:
                refs = [p.stem for p in files]
            sections = []
            for ref in refs:
                shared = ref.startswith("shared:")
                base = self.root / "data" / "shared" if shared else d
                name = ref[len("shared:"):] if shared else ref
                path = base / f"{name}.toml"
                if not path.is_file():
                    cands = sorted(base.glob(f"*{name}.toml"))
                    if not cands:
                        self.warnings.append(f"{self.rel(d)}: la sección «{ref}» no existe")
                        continue
                    path = cands[0]
                sec = self._section(path, shared)
                if sec:
                    sections.append(sec)
            meta["_sections"] = sections
            self.guides.append(meta)
        self.guides.sort(key=lambda g: (g.get("order") if is_int(g.get("order")) else 999,
                                        str(g.get("title") or g["id"])))

    def _load_knowledge(self):
        kdir = self.root / "data" / "knowledge"
        if not kdir.is_dir():
            return
        dir_class = {c.lower(): c for c in CLASS_ORDER}
        dir_class.update({v: k for k, v in CLASS_SLUG.items()})
        for path in sorted(kdir.rglob("*.toml")):
            doc = self.toml(path)
            if not isinstance(doc, dict):
                continue
            doc = dict(doc)
            doc.setdefault("id", path.stem)
            folder = path.parent.name.lower()
            cls = str(doc.get("class") or dir_class.get(folder, "ANY")).upper()
            if cls not in CLASS_SLUG:
                cls = dir_class.get(folder, "ANY")
            doc["_class"] = cls
            doc["_file"] = self.rel(path)
            self.knowledge.setdefault(cls, []).append(doc)
        for cls, pages in self.knowledge.items():
            pages.sort(key=lambda p: (p.get("order") if is_int(p.get("order")) else 999,
                                      (levels_of(p) or (0, 0)), str(p.get("title") or p["id"])))
            used: set[str] = set()
            cslug = CLASS_SLUG[cls]
            for p in pages:
                path = None
                # id sin el prefijo de clase: "warlock-gear" -> "gear", "general-gold" -> "gold"
                short_id = slugify(re.sub(rf"^({re.escape(cls.lower())}|{cslug}|any)-", "", p["id"]))
                if isinstance(p.get("link"), str) and p["link"].strip():
                    key = link_key(p["link"])
                    if key and key[0] and "." not in key[0]:
                        path = key[0]
                if not path:
                    lv = levels_of(p)
                    kind = p.get("kind", "page")
                    if kind == "page" and lv:
                        slug = f"{lv[0]}-{lv[1]}"
                    elif kind in KIND_SLUG:
                        slug = KIND_SLUG[kind]
                    else:
                        slug = short_id
                    if f"{cslug}/{slug}" in used:
                        slug = short_id
                    path = f"{cslug}/{slug}"
                if path in used:
                    self.warnings.append(f"{p['_file']}: ruta repetida «{path}», se usa el id")
                    path = f"{cslug}/{slugify(p['id'])}"
                used.add(path)
                p["_path"] = path

    # -- consultas
    def all_steps(self, guide) -> list[dict]:
        return [s for sec in guide["_sections"] for s in sec["step"]]


def count_status(items) -> dict:
    c = {s: 0 for s in STATUSES}
    for it in items:
        c[norm_status(it.get("status"))] += 1
    return c


def guide_levels(guide) -> tuple[int, int] | None:
    lv = levels_of(guide)
    if lv:
        return lv
    ls = [levels_of(s) for s in guide["_sections"]]
    ls = [x for x in ls if x]
    return (min(a for a, _ in ls), max(b for _, b in ls)) if ls else None


def guide_path(guide) -> str:
    return f"guias/{slugify(guide['id'])}"


# =========================================================================== componentes HTML
def badge(status, sources=None, checked=None, small=False) -> str:
    st = norm_status(status)
    tip = [STATUS_ES[st] + ". " + STATUS_HELP[st]]
    srcs = [str(s) for s in as_list(sources)]
    if srcs:
        shown = srcs[:3]
        more = f" y {len(srcs) - 3} más" if len(srcs) > 3 else ""
        tip.append("Fuentes: " + ", ".join(shown) + more)
    if checked:
        tip.append(f"Comprobado: {checked}")
    tip_text = " · ".join(tip)
    ic = {"verified": "check", "unverified": "dot", "disputed": "alert"}[st]
    return (f'<span class="badge badge-{st}{" badge-sm" if small else ""}" tabindex="0" role="note" '
            f'data-tip="{esc(tip_text)}" aria-label="{esc(tip_text)}">{icon(ic)}'
            f'<span class="badge-text">{STATUS_ES[st]}</span></span>')


def status_bar(c: dict, label: str = "") -> str:
    total = sum(c.values())
    if not total:
        return '<div class="sbar sbar-empty" role="img" aria-label="Sin pasos"></div>'
    segs = "".join(f'<span class="seg seg-{s}" style="width:{c[s] * 100 / total:.2f}%"></span>'
                   for s in STATUSES if c[s])
    aria = f"{label}{c['verified']} verificados, {c['unverified']} sin verificar, {c['disputed']} en disputa"
    return f'<div class="sbar" role="img" aria-label="{esc(aria)}">{segs}</div>'


def pct(c: dict) -> str:
    total = sum(c.values())
    return f"{c['verified'] * 100 / total:.0f} %" if total else "—"


def filter_text(f) -> str:
    if not isinstance(f, dict):
        return ""
    parts = []
    if as_list(f.get("class")):
        parts.append(", ".join(class_es(c) for c in f["class"]))
    if as_list(f.get("race")):
        parts.append(", ".join(RACE_ES.get(r, str(r)) for r in f["race"]))
    if f.get("faction"):
        parts.append(FACTION_ES.get(f["faction"], str(f["faction"])))
    if as_list(f.get("prof")):
        parts.append(", ".join(prof_es(p) for p in f["prof"]))
    if is_int(f.get("minlevel")) and is_int(f.get("maxlevel")):
        parts.append(f"niveles {f['minlevel']}–{f['maxlevel']}")
    elif is_int(f.get("minlevel")):
        parts.append(f"desde nivel {f['minlevel']}")
    elif is_int(f.get("maxlevel")):
        parts.append(f"hasta nivel {f['maxlevel']}")
    return "; ".join(parts)


def point(p):
    """(texto "x, y (mapa)", etiqueta, x, y) o None."""
    if not isinstance(p, list) or len(p) < 3 or not is_num(p[1]) or not is_num(p[2]):
        return None
    label = p[3] if len(p) > 3 and isinstance(p[3], str) else ""
    return f"{float(p[1]):.1f}, {float(p[2]):.1f} ({map_name(p[0])})", label, float(p[1]), float(p[2])


def coord_chip(p, fallback_label="") -> str:
    pt = point(p)
    if not pt:
        return ""
    text, label, x, y = pt
    way = f"/senda way {x:.1f} {y:.1f}" + (f" {label or fallback_label}" if (label or fallback_label) else "")
    lab = f'<span class="chip-label">{esc(label)}:</span> ' if label else ""
    return (f'<li class="chip chip-coord">{icon("goto")}{lab}<span class="coord">{esc(text)}</span>'
            f'<button type="button" class="mini-copy" data-copy-text="{esc(way)}" '
            f'aria-label="Copiar comando {esc(way)}" title="Copiar «{esc(way)}»">{icon("copy")}</button></li>')


def chip(content_html: str, cls: str = "", ic: str = "") -> str:
    return f'<li class="chip {cls}">{icon(ic) if ic else ""}{content_html}</li>'


def sources_details(srcs) -> str:
    srcs = [str(s) for s in as_list(srcs)]
    if not srcs:
        return ""
    items = []
    for s in srcs:
        if re.match(r"^https?://", s):
            items.append(f'<li><a href="{esc(s)}" target="_blank" rel="noopener">{esc(s)}</a></li>')
        else:
            items.append(f"<li><code>{esc(s)}</code></li>")
    return (f'<details class="sources"><summary>Fuentes ({len(srcs)})</summary>'
            f'<ul>{"".join(items)}</ul></details>')


def code_block(text, cid: str, what: str) -> str:
    return (f'<div class="code-wrap"><pre><code id="{esc(cid)}">{esc(str(text).strip())}</code></pre>'
            f'<button type="button" class="copy" data-copy-target="{esc(cid)}">{icon("copy")}'
            f'<span>Copiar</span><span class="sr-only"> {esc(what)}</span></button></div>')


# =========================================================================== el sitio
class Site:
    def __init__(self, root: Path, out: Path, site_src: Path = SITE_SRC, validate=True,
                 validate_json: Path | None = None, today: dt.date | None = None):
        self.root = Path(root)
        self.out = Path(out)
        self.src = Path(site_src)
        self.data = Data(self.root)
        self.warnings = self.data.warnings
        self.pages: dict[str, str] = {}   # ruta -> HTML final
        self.raw: dict[str, str] = {}     # ruta -> cuerpo (para comprobar anclas)
        self.links: list[tuple[str, str]] = []  # (origen, enlace)
        self.search: list[dict] = []
        self.today = today or dt.date.today()
        self.validate = validate
        self.validate_json = validate_json
        self.template = Template((self.src / "templates" / "base.html").read_text(encoding="utf-8"))
        self.asset_version = self._asset_version()
        self.base_path = urlparse(SITE_URL).path or "/"
        self.broken: list[str] = []
        self.names = self._collect_names()

    def _collect_names(self) -> dict:
        """Nombres de hechizos y objetos que ya aparecen en data/knowledge (la web no tiene cliente)."""
        names: dict[str, dict[int, str]] = {"spell": {}, "item": {}}
        for pages in self.data.knowledge.values():
            for p in pages:
                for t in as_list(p.get("train")):
                    if isinstance(t, dict):
                        for i, n in zip(as_list(t.get("spells")), as_list(t.get("names"))):
                            if is_int(i) and isinstance(n, str):
                                names["spell"].setdefault(i, n)
                for a in as_list(p.get("alias")):
                    if isinstance(a, dict) and is_int(a.get("spell")) and as_list(a.get("names")):
                        names["spell"].setdefault(a["spell"], str(a["names"][0]))
                for c in as_list(p.get("check")):
                    if isinstance(c, dict) and is_int(c.get("spell")) and isinstance(c.get("name"), str):
                        names["spell"].setdefault(c["spell"], c["name"])
                for key in ("item", "material"):
                    for it in as_list(p.get(key)):
                        if isinstance(it, dict) and is_int(it.get("id")) and isinstance(it.get("name"), str):
                            names["item"].setdefault(it["id"], it["name"])
                for r in as_list(p.get("route")):
                    if isinstance(r, dict) and is_int(r.get("craft")) and isinstance(r.get("name"), str):
                        names["item"].setdefault(r["craft"], r["name"])
        return names

    def spell(self, sid, kind="Hechizo", name=None) -> str:
        label = name or self.names["spell"].get(sid) or f"{kind} #{sid}"
        return wh_link("spell", sid, label)

    def item(self, iid, name=None) -> str:
        label = name or self.names["item"].get(iid) or f"Objeto #{iid}"
        return wh_link("item", iid, label)

    def ref(self, v) -> str:
        """"spell:123" / "item:456" -> enlace; cualquier otra cosa, texto."""
        m = re.match(r"^(spell|item):(\d+)$", str(v))
        if m:
            return self.spell(int(m.group(2))) if m.group(1) == "spell" else self.item(int(m.group(2)))
        if is_int(v):
            return self.spell(v)
        return f"<code>{esc(v)}</code>"

    def _asset_version(self) -> str:
        h = hashlib.sha1()
        static = self.src / "static"
        for p in sorted(static.rglob("*")) if static.is_dir() else []:
            if p.is_file():
                h.update(p.read_bytes())
        return h.hexdigest()[:10]

    # ------------------------------------------------------------------ marco
    def sidebar(self, active: str, toc: list | None) -> str:
        def item(path, label, ic="", extra=""):
            cur = ' aria-current="page"' if path == active else ""
            href = ROOT + (path + "/" if path else "")
            return f'<li><a href="{href}"{cur}>{icon(ic) if ic else ""}<span>{esc(label)}</span>{extra}</a></li>'

        out = ['<div class="nav-group"><ul>', item("", "Inicio", "compass")]
        out.append("</ul></div>")
        if self.data.guides:
            out.append('<div class="nav-group"><h2 class="nav-title">Guías</h2><ul>')
            for g in self.data.guides:
                lv = guide_levels(g)
                extra = f'<span class="nav-meta">{fmt_range(*lv)}</span>' if lv else ""
                out.append(item(guide_path(g), str(g.get("title") or g["id"]), "map", extra))
            out.append("</ul></div>")
        if self.data.knowledge:
            out.append('<div class="nav-group"><h2 class="nav-title">Clases</h2><ul>')
            for cls in CLASS_ORDER:
                if cls in self.data.knowledge:
                    out.append(item(CLASS_SLUG[cls], CLASS_ES[cls], "train" if cls != "ANY" else "globe"))
            out.append("</ul></div>")
        out.append('<div class="nav-group"><h2 class="nav-title">Proyecto</h2><ul>')
        out.append(item("estado", "Estado de los datos", "shield"))
        out.append(item("cambios", "Cambios", "note"))
        out.append(f'<li><a href="{REPO_URL}" target="_blank" rel="noopener">{icon("github")}'
                   f'<span>Código en GitHub</span></a></li>')
        out.append("</ul></div>")
        if toc:
            out.append('<div class="nav-group nav-toc"><h2 class="nav-title">En esta página</h2><ul>')
            for hid, label, *meta in toc:
                m = f'<span class="nav-meta">{esc(meta[0])}</span>' if meta and meta[0] else ""
                out.append(f'<li><a href="#{esc(hid)}"><span>{esc(label)}</span>{m}</a></li>')
            out.append("</ul></div>")
        return "\n".join(out)

    def page(self, path: str, title: str, body: str, *, description: str = "", toc=None,
             page_class: str = "", absolute_root: bool = False):
        depth = len([p for p in path.split("/") if p])
        rel = self.base_path if absolute_root else ("../" * depth or "./")
        full_title = "Senda" if not title else f"{title} · Senda"
        html_text = self.template.substitute(
            title=esc(full_title),
            description=esc(description or "Senda: guía de leveo paso a paso para WoW Forever, en español."),
            canonical=esc(SITE_URL + (path + "/" if path else "")),
            root=rel,
            icons=icon_sprite(),
            sidebar=self.sidebar(path, toc),
            content=body,
            page_class=esc(page_class),
            version=esc(self.data.version or "dev"),
            year=str(self.today.year),
            built=self.today.isoformat(),
            asset_version=self.asset_version,
            repo=REPO_URL,
            releases=RELEASES_URL,
        )
        self.raw[path] = body
        self.pages[path] = html_text.replace(ROOT, rel)

    def index(self, title, url, kind, text="", ctx=""):
        e = {"t": excerpt(title, 140), "u": url, "k": kind}
        if text:
            e["x"] = excerpt(text, 180)
        if ctx:
            e["c"] = ctx
        self.search.append(e)

    # ------------------------------------------------------------------ guías
    def render_step(self, s: dict, num: int, anchors: Anchors, guide_title: str, sec_title: str,
                    page_path: str) -> str:
        do = s.get("do") if s.get("do") in DO_INFO else "note"
        label, ic, fam = DO_INFO[do]
        sid = anchors.get(s.get("id") or f"paso-{num}")
        st = norm_status(s.get("status"))
        chips: list[str] = []
        qs = ([s["quest"]] if is_int(s.get("quest")) else []) + [q for q in as_list(s.get("quests")) if is_int(q)]
        for q in qs:
            chips.append(chip(wh_link("quest", q, f"Misión #{q}"), "chip-quest", "accept"))
        if is_int(s.get("obj")):
            chips.append(chip(f"Objetivo {s['obj']}", "chip-obj"))
        if is_int(s.get("npc")):
            chips.append(chip(wh_link("npc", s["npc"], f"PNJ #{s['npc']}"), "chip-npc", "people"))
        if is_int(s.get("item")):
            cnt = f' <span class="count">×{s["count"]}</span>' if is_int(s.get("count")) else ""
            chips.append(chip(self.item(s["item"]) + cnt, "chip-item", "have"))
        elif is_int(s.get("count")):
            chips.append(chip(f"×{s['count']}", "chip-item"))
        for sp in as_list(s.get("spells")):
            if is_int(sp):
                chips.append(chip(self.spell(sp), "chip-spell", "train"))
        if is_int(s.get("level")):
            chips.append(chip(f"Nivel {s['level']}", "chip-level", "level"))
        if s.get("prof"):
            sk = f" {s['skill']}" if is_int(s.get("skill")) else ""
            chips.append(chip(esc(prof_es(s["prof"]) + sk), "chip-prof", "skill"))
        if s.get("at"):
            chips.append(coord_chip(s["at"], ""))
        for wp in as_list(s.get("wps")):
            chips.append(coord_chip(wp))
        if s.get("node"):
            chips.append(chip(f"Nodo: {esc(s['node'])}", "chip-node", "getfp"))
        if is_int(s.get("zone")):
            chips.append(chip(f"Destino: {esc(map_name(s['zone']))}", "chip-zone", "map"))
        ft = filter_text(s.get("if"))
        if ft:
            chips.append(chip(f"Solo: {esc(ft)}", "chip-filter"))
        if s.get("optional") is True:
            chips.append(chip("Opcional", "chip-optional"))
        chips_html = f'<ul class="chips">{"".join(c for c in chips if c)}</ul>' if any(chips) else ""

        extra = ""
        if s.get("tip"):
            extra += (f'<div class="tip">{icon("tip")}<div><strong>Consejo:</strong> '
                      f'{inline_md(s["tip"])}</div></div>')
        if s.get("note"):
            extra += f'<p class="step-note">{inline_md(s["note"])}</p>'
        if s.get("link"):
            self.links.append((f"{page_path} · paso {s.get('id', num)}", str(s["link"])))
            extra += (f'<a class="more" href="{esc(site_href(s["link"]))}">Leer más'
                      f'<span class="sr-only"> sobre el paso {num}</span> →</a>')
        text = str(s.get("text") or "")
        self.index(text or label, f"{page_path}/#{sid}", "Paso", "", f"{guide_title} · {sec_title}")
        checked = s.get("checked")
        return (
            f'<li class="step step-{st}{" step-optional" if s.get("optional") is True else ""}" id="{sid}">'
            f'<div class="step-icon fam-{fam}" title="{esc(label)}">{icon(ic)}</div>'
            f'<div class="step-main">'
            f'<div class="step-top"><span class="step-num">{num}</span>'
            f'<span class="step-kind">{esc(label)}</span>'
            f'{badge(st, s.get("sources"), checked, small=True)}'
            f'<a class="anchor" href="#{sid}" aria-label="Enlace al paso {num}">{icon("link")}</a></div>'
            f'<p class="step-text">{inline_md(text)}</p>{chips_html}{extra}</div></li>'
        )

    def build_guide(self, g: dict):
        path = guide_path(g)
        title = str(g.get("title") or g["id"])
        sections = g["_sections"]
        steps = self.data.all_steps(g)
        c = count_status(steps)
        lv = guide_levels(g)
        anchors = Anchors({"contenido", "top"})
        sec_ids = [anchors.get(sec.get("id")) for sec in sections]

        meta = []
        if g.get("faction"):
            meta.append(FACTION_ES.get(g["faction"], str(g["faction"])))
        if as_list(g.get("races")):
            meta.append(", ".join(RACE_ES.get(r, str(r)) for r in g["races"]))
        if as_list(g.get("classes")):
            meta.append(", ".join(class_es(x) for x in g["classes"]))
        if lv:
            meta.append(f"Niveles {fmt_range(*lv)}")
        meta.append(f"{len(steps)} pasos")

        related = []
        for cls in as_list(g.get("classes")):
            cls = str(cls).upper()
            if cls in self.data.knowledge:
                related.append(f'<a class="btn btn-ghost" href="{ROOT}{CLASS_SLUG[cls]}/">'
                               f'{icon("train")}Conocimiento de {esc(CLASS_ES[cls].lower())}</a>')

        out = [f'<header class="page-head"><p class="eyebrow">Guía de leveo</p><h1>{esc(title)}</h1>',
               f'<p class="meta-line">{" · ".join(esc(m) for m in meta)}</p>']
        if g.get("summary"):
            out.append(f'<p class="lead">{inline_md(g["summary"])}</p>')
        out.append(f'<div class="guide-stats">{status_bar(c)}<p class="legend">'
                   f'<span class="lg lg-verified">{c["verified"]} verificados</span>'
                   f'<span class="lg lg-unverified">{c["unverified"]} sin verificar</span>'
                   f'<span class="lg lg-disputed">{c["disputed"]} en disputa</span></p></div>')
        if related:
            out.append(f'<p class="actions">{"".join(related)}</p>')
        out.append('</header>')

        if not sections:
            out.append('<p class="empty">Esta guía todavía no tiene secciones.</p>')

        toc = []
        num = 0
        self.index(title, f"{path}/", "Guía", g.get("summary", ""), " · ".join(meta[:-1]))
        for sec, sec_id in zip(sections, sec_ids):
            stitle = str(sec.get("title") or sec.get("id"))
            slv = levels_of(sec)
            sc = count_status(sec["step"])
            toc.append((sec_id, stitle, fmt_range(*slv) if slv else ""))
            self.index(stitle, f"{path}/#{sec_id}", "Sección", sec.get("summary", ""), title)
            head_meta = []
            if slv:
                head_meta.append(f'<span class="lvl">Niv. {fmt_range(*slv)}</span>')
            if is_int(sec.get("map")):
                head_meta.append(f'<span>{icon("map")}{esc(map_name(sec["map"]))}</span>')
            head_meta.append(f'<span>{len(sec["step"])} pasos · {pct(sc)} verificado</span>')
            if sec.get("_shared"):
                head_meta.append('<span class="tag">Ruta compartida</span>')
            ft = filter_text(sec.get("if"))
            if ft:
                head_meta.append(f'<span class="tag">Solo: {esc(ft)}</span>')
            out.append(f'<section class="gsection" aria-labelledby="{sec_id}-h">'
                       f'<div class="gsection-head"><h2 id="{sec_id}"><span id="{sec_id}-h">{esc(stitle)}</span>'
                       f'<a class="anchor" href="#{sec_id}" aria-label="Enlace a la sección">{icon("link")}</a></h2>'
                       f'<p class="sec-meta">{"".join(head_meta)}</p>{status_bar(sc)}')
            if sec.get("summary"):
                out.append(f'<p class="sec-summary">{inline_md(sec["summary"])}</p>')
            if sec.get("link"):
                self.links.append((f"{path} · sección {sec.get('id')}", str(sec["link"])))
                out.append(f'<a class="more" href="{esc(site_href(sec["link"]))}">Leer más →</a>')
            out.append(f'</div><ol class="steps" start="{num + 1}">')
            for s in sec["step"]:
                num += 1
                out.append(self.render_step(s, num, anchors, title, stitle, path))
            out.append("</ol></section>")
        self.page(path, title, "\n".join(out), description=g.get("summary") or f"{title}: guía de leveo para WoW Forever.",
                  toc=toc, page_class="page-guide")

    # ------------------------------------------------------------------ conocimiento
    def build_knowledge_page(self, p: dict):
        path = p["_path"]
        cls = p["_class"]
        title = str(p.get("title") or p["id"])
        anchors = Anchors({"contenido", "top"})
        toc: list = []
        kind = p.get("kind", "page")
        lv = levels_of(p)
        ctx = CLASS_ES[cls]
        self.index(title, f"{path}/", "Conocimiento", p.get("summary", ""), CLASS_ES[cls])

        meta = [CLASS_ES[cls], KIND_ES.get(kind, "Guía")]
        if lv:
            meta.append(f"Niveles {fmt_range(*lv)}")
        out = [f'<nav class="crumbs" aria-label="Ruta"><a href="{ROOT}{CLASS_SLUG[cls]}/">{esc(CLASS_ES[cls])}</a>'
               f' <span aria-hidden="true">/</span> <span>{esc(title)}</span></nav>',
               f'<header class="page-head"><p class="eyebrow">{esc(" · ".join(meta))}</p>'
               f'<h1 id="{anchors.get(p["id"])}">{esc(title)}</h1>'
               f'<p class="meta-line">{badge(p.get("status"), p.get("sources"), p.get("checked"))}</p>']
        if p.get("summary"):
            out.append(f'<p class="lead">{inline_md(p["summary"])}</p>')
        out.append(sources_details(p.get("sources")))
        out.append("</header>")
        head_len = len(out)

        def item_badge(it):
            return badge(it.get("status"), it.get("sources"), it.get("checked"), small=True) if it.get("status") else ""

        def section(key, heading, inner, intro=""):
            hid = anchors.get(key)
            toc.append((hid, heading))
            out.append(f'<section class="kblock"><h2 id="{hid}">{esc(heading)}'
                       f'<a class="anchor" href="#{hid}" aria-label="Enlace a esta parte">{icon("link")}</a></h2>'
                       f'{intro}{inner}</section>')

        def table(cols, rows):
            head = "".join(f'<th scope="col"{" class=num" if c in ("Nivel", "Niveles", "Casilla", "Mín.") else ""}>{c}</th>'
                           if c else '<th scope="col"><span class="sr-only">Estado</span></th>' for c in cols)
            return (f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead>'
                    f'<tbody>{"".join(rows)}</tbody></table></div>')

        def rows_of(key):
            return [x for x in as_list(p.get(key)) if isinstance(x, dict)]

        if p.get("note"):
            out.append(f'<p class="page-note">{icon("note")}<span>{inline_md(p["note"])}</span></p>')

        for b in rows_of("block"):
            body = md(b.get("body", ""), shift=1, anchors=anchors)
            note = f'<p class="muted small">{inline_md(b["note"])}</p>' if b.get("note") else ""
            if b.get("heading"):
                hid = anchors.get(b["heading"])
                toc.append((hid, excerpt(b["heading"], 60)))
                blv = levels_of(b)
                lvh = f'<span class="lvl">Niv. {fmt_range(*blv)}</span>' if blv else ""
                meta_html = f'<p class="sec-meta">{lvh}{item_badge(b)}</p>' if (lvh or b.get("status")) else ""
                out.append(f'<section class="kblock"><h2 id="{hid}">{inline_md(b["heading"])}'
                           f'<a class="anchor" href="#{hid}" aria-label="Enlace a esta parte">{icon("link")}</a></h2>'
                           f'{meta_html}{body}{note}</section>')
                self.index(b["heading"], f"{path}/#{hid}", "Conocimiento", b.get("body", ""), f"{ctx} · {title}")
            else:
                out.append(f'<section class="kblock">{item_badge(b)}{body}{note}</section>')

        picks = rows_of("pick")
        if picks:
            rows = []
            for x in picks:
                rid = anchors.get(f"talento-{x.get('level', '')}")
                t = x.get("talent")
                tal = self.spell(t, "Talento") if is_int(t) else f"<strong>{esc(t)}</strong>"
                if is_int(x.get("rank")):
                    mx = f"/{x['max']}" if is_int(x.get("max")) else ""
                    tal += f' <span class="muted">({x["rank"]}{mx})</span>'
                rows.append(f'<tr id="{rid}"><td class="num">{esc(x.get("level", ""))}</td><td>{tal}</td>'
                            f'<td>{esc(x.get("tree", ""))}</td><td>{inline_md(x.get("note", ""))}</td>'
                            f'<td>{item_badge(x)}</td></tr>')
            section("talentos", "Talentos", table(["Nivel", "Talento", "Árbol", "Nota", ""], rows))

        trains = rows_of("train")
        if trains:
            rows = []
            for x in trains:
                rid = anchors.get(f"nivel-{x.get('level', '')}")
                names = as_list(x.get("names"))
                ids = [i for i in as_list(x.get("spells")) if is_int(i)]
                links = [self.spell(i, "Hechizo", names[n] if n < len(names) and isinstance(names[n], str) else None)
                         for n, i in enumerate(ids)]
                links += [esc(nm) for nm in names[len(ids):] if isinstance(nm, str)]
                tags = []
                if x.get("pet") is True:
                    tags.append(' <span class="tag">Mascota</span>')
                if x.get("talent") is True:
                    tags.append(' <span class="tag">Talento</span>')
                cost = f'<span class="muted">{money(x["cost"])}</span>' if is_int(x.get("cost")) else ""
                spans = "".join(f"<span>{lnk}</span>" for lnk in links)
                rows.append(f'<tr id="{rid}"><td class="num">{esc(x.get("level", ""))}</td>'
                            f'<td><span class="spell-list">{spans}</span>{"".join(tags)}</td>'
                            f'<td>{inline_md(x.get("note", ""))} {cost}</td><td>{item_badge(x)}</td></tr>')
            section("hechizos", "Hechizos por nivel", table(["Nivel", "Hechizos", "Nota", ""], rows))

        phases = rows_of("phase")
        if phases:
            items = []
            for x in phases:
                rng = fmt_range(x.get("from", "?"), x.get("to", "?"))
                rid = anchors.get(f"fase-{rng}")
                sp = "".join(f"<span>{self.spell(i)}</span>" for i in as_list(x.get("spells")) if is_int(i))
                note = f'<p class="muted">{inline_md(x["note"])}</p>' if x.get("note") else ""
                items.append(f'<article class="card" id="{rid}"><h3><span class="lvl">Niv. {esc(rng)}</span> {item_badge(x)}</h3>'
                             f'{md(x.get("text", ""), shift=2)}'
                             f'{f"<p class=spell-list>{sp}</p>" if sp else ""}{note}</article>')
            section("rotacion", "Rotación", "".join(items))

        hud = rows_of("hud")
        if hud:
            rows = [f'<tr><td>{inline_md(x.get("when", ""))}</td><td><strong>{inline_md(x.get("suggest", ""))}</strong>'
                    f'{" · " + self.spell(x["spell"]) if is_int(x.get("spell")) else ""}</td></tr>' for x in hud]
            section("sugerencias", "Sugerencias del HUD", table(["Cuándo", "Sugerencia"], rows),
                    '<p class="muted">El addon te sugiere la siguiente acción según estas reglas, en este orden.</p>')

        warns = rows_of("warning")
        if warns:
            rows = [f'<tr><td><strong>{inline_md(x.get("text", ""))}</strong></td><td>{inline_md(x.get("when", ""))}</td></tr>'
                    for x in warns]
            section("avisos", "Avisos", table(["Aviso", "Cuándo"], rows))

        macros = rows_of("macro")
        if macros:
            items = []
            for x in macros:
                name = str(x.get("name") or "Macro")
                rid = anchors.get(name)
                meta_bits = []
                if is_int(x.get("minlevel")):
                    meta_bits.append(f"Desde nivel {x['minlevel']}")
                if x.get("icon") not in (None, ""):
                    meta_bits.append("Icono: " + self.ref(x["icon"]))
                if x.get("pet") is True:
                    meta_bits.append("Con mascota")
                self.index(name, f"{path}/#{rid}", "Macro", x.get("body", ""), f"{ctx} · {title}")
                alts = ""
                fbs = [f for f in as_list(x.get("fallbacks")) if isinstance(f, str)]
                if fbs:
                    alts = (f'<details class="sources"><summary>Alternativas ({len(fbs)})</summary>'
                            + "".join(code_block(f, f"{rid}-alt{n}", f"la alternativa {n} de {name}")
                                      for n, f in enumerate(fbs, 1)) + "</details>")
                meta_html = f'<p class="muted">{" · ".join(meta_bits)}</p>' if meta_bits else ""
                note = f'<p>{inline_md(x["note"])}</p>' if x.get("note") else ""
                items.append(
                    f'<article class="card macro" id="{rid}"><div class="macro-head"><h3>{esc(name)}'
                    f'<a class="anchor" href="#{rid}" aria-label="Enlace a la macro">{icon("link")}</a></h3>'
                    f'{item_badge(x)}</div>{meta_html}'
                    f'{code_block(x.get("body", ""), f"{rid}-code", f"la macro {name}")}{note}{alts}</article>')
            section("macros", "Macros", "".join(items),
                    '<p class="muted">En el juego: escribe <kbd>/macro</kbd>, pulsa «Nueva», pega el texto y arrastra '
                    'el icono a la barra.</p>')

        bars = rows_of("bar")
        if bars:
            items = []
            for bar in bars:
                rows = []
                for sl in [s for s in as_list(bar.get("slot")) if isinstance(s, dict)]:
                    if is_int(sl.get("spell")):
                        what = self.spell(sl["spell"])
                        if is_int(sl.get("alt")):
                            what += f' <span class="muted">o</span> {self.spell(sl["alt"])}'
                    elif sl.get("macro"):
                        what = f'Macro <code>{esc(sl["macro"])}</code>'
                    elif sl.get("item"):
                        what = self.ref(sl["item"])
                    else:
                        what = esc(sl.get("text", ""))
                    rows.append(f'<tr><td class="num">{esc(sl.get("slot", ""))}</td><td><kbd>{esc(sl.get("key", "—"))}</kbd></td>'
                                f'<td>{what}</td><td class="num">{esc(sl.get("level", ""))}</td></tr>')
                items.append(f'<h3>{esc(bar.get("title", "Barra"))}</h3>' + table(["Casilla", "Tecla", "Acción", "Nivel"], rows))
            section("barras", "Barras de acción", "".join(items))
        if isinstance(p.get("bindings"), dict) and p["bindings"]:
            rows = [f"<tr><td><kbd>{esc(k)}</kbd></td><td><code>{esc(v)}</code></td></tr>" for k, v in p["bindings"].items()]
            section("atajos", "Atajos de teclado", table(["Tecla", "Acción"], rows))

        if isinstance(p.get("weights"), dict) and p["weights"]:
            rows = [f'<tr><td>{esc(STAT_ES.get(k, k))}</td><td class="num">{f"{v:g}" if is_num(v) else esc(_scalar(v))}</td></tr>'
                    for k, v in p["weights"].items()]
            section("pesos", "Pesos de estadísticas", table(["Estadística", "Peso"], rows),
                    '<p class="muted">Cuánto vale cada punto al comparar equipo (más alto, mejor).</p>')

        gear = rows_of("item")
        if gear:
            rows = []
            for x in gear:
                lbl = x.get("name") or f"Objeto #{x.get('id')}"
                it = wh_link("item", x["id"], lbl) if is_int(x.get("id")) else esc(lbl)
                cls_t = f' <span class="tag">{esc(class_es(x["class"]))}</span>' if x.get("class") else ""
                rows.append(f'<tr><td class="num">{esc(fmt_range(x.get("from", "?"), x.get("to", "?")))}</td>'
                            f'<td>{it}{cls_t}</td><td>{inline_md(x.get("src", ""))}</td><td>{inline_md(x.get("note", ""))}</td></tr>')
            section("objetos", "Objetos por nivel", table(["Niveles", "Objeto", "Origen", "Nota"], rows))

        routes = rows_of("route")
        if routes:
            items = []
            for x in routes:
                rng = fmt_range(x.get("from", "?"), x.get("to", "?"))
                pname = prof_es(x.get("prof", ""))
                rid = anchors.get(f"{x.get('prof', '')}-{rng}")
                bits = []
                n = f' <span class="count">×{x["n"]}</span>' if is_int(x.get("n")) else ""
                if is_int(x.get("craft")):
                    bits.append(f'<li><span class="k">Fabricar:</span> {self.item(x["craft"], x.get("name"))}{n}</li>')
                elif is_int(x.get("craft_spell")):
                    bits.append(f'<li><span class="k">Fabricar:</span> {self.spell(x["craft_spell"], "Receta", x.get("name"))}{n}</li>')
                elif x.get("name"):
                    bits.append(f'<li><span class="k">Qué hacer:</span> {esc(x["name"])}{n}</li>')
                mats = [f'{self.item(m[0])} <span class="count">×{esc(m[1])}</span>'
                        for m in as_list(x.get("mats")) if isinstance(m, list) and len(m) >= 2 and is_int(m[0])]
                if mats:
                    bits.append(f'<li><span class="k">Materiales:</span> {", ".join(mats)}</li>')
                if x.get("trainer"):
                    tr = point(x["trainer"])
                    if tr:
                        lbl = f"{esc(tr[1])} · " if tr[1] else ""
                        bits.append(f'<li><span class="k">Instructor:</span> {lbl}{esc(tr[0])}</li>')
                if x.get("src"):
                    bits.append(f'<li><span class="k">Receta:</span> {inline_md(x["src"])}</li>')
                if x.get("note"):
                    bits.append(f"<li>{inline_md(x['note'])}</li>")
                items.append(f'<article class="card" id="{rid}"><h3><span class="lvl">{esc(rng)}</span> {esc(pname)} {item_badge(x)}</h3>'
                             f'<ul class="kv">{"".join(bits)}</ul></article>')
            section("ruta", "Ruta de subida", "".join(items))

        trainers = rows_of("trainer")
        if trainers:
            items = []
            for x in trainers:
                bits = []
                if as_list(x.get("ranks")):
                    bits.append(f'<li><span class="k">Rangos:</span> {esc(", ".join(map(str, x["ranks"])))}</li>')
                if x.get("for_class"):
                    bits.append(f'<li><span class="k">Para:</span> {esc(class_es(x["for_class"]))}</li>')
                pt = point(x.get("at"))
                if pt:
                    bits.append(f'<li><span class="k">Dónde:</span> {esc(pt[1] + " · " if pt[1] else "")}{esc(pt[0])}</li>')
                if x.get("text"):
                    bits.append(f"<li>{inline_md(x['text'])}</li>")
                if x.get("note"):
                    bits.append(f'<li class="muted">{inline_md(x["note"])}</li>')
                items.append(f'<article class="card"><h3>{esc(x.get("name", "Instructor"))} '
                             f'<span class="tag">{esc(prof_es(x.get("prof", "")))}</span> {item_badge(x)}</h3>'
                             f'<ul class="kv">{"".join(bits)}</ul></article>')
            section("instructores", "Instructores", "".join(items))

        ranks = rows_of("rank")
        if ranks:
            rows = [f'<tr><td><strong>{esc(x.get("name", ""))}</strong></td><td class="num">{esc(x.get("max", ""))}</td>'
                    f'<td class="num">{esc(x.get("skill", ""))}</td><td class="num">{esc(x.get("level", ""))}</td>'
                    f'<td>{esc(x.get("cost", ""))}</td></tr>' for x in ranks]
            section("rangos", "Rangos de profesión",
                    table(["Rango", "Máximo", "Habilidad mín.", "Nivel mín.", "Coste"], rows))

        materials = rows_of("material")
        if materials:
            rows = []
            for x in materials:
                it = self.item(x["id"], x.get("name")) if is_int(x.get("id")) else esc(x.get("name", ""))
                made = [self.item(m[0]) + (f" ×{esc(m[1])}" if len(m) > 1 else "")
                        for m in as_list(x.get("made_from")) if isinstance(m, list) and m and is_int(m[0])]
                where = inline_md(x.get("where", ""))
                if made:
                    where += f'<br><span class="muted">Se hace con:</span> {", ".join(made)}'
                if is_int(x.get("vendor")):
                    vend = wh_link("npc", x["vendor"], f"PNJ #{x['vendor']}")
                    where += f'<br><span class="muted">Vendedor:</span> {vend}'
                extra = inline_md(x.get("sell", ""))
                if x.get("note"):
                    extra += f' <span class="muted">{inline_md(x["note"])}</span>'
                rows.append(f'<tr><td>{it}</td><td>{where}</td><td class="num">{esc(x.get("min", ""))}</td><td>{extra}</td></tr>')
            section("materiales", "Materiales", table(["Material", "Dónde", "Mín.", "Qué hacer"], rows))

        # Cualquier otra lista de tablas que aún no conozcamos se muestra de forma genérica.
        for key, val in p.items():
            if key.startswith("_") or key in KNOWN_KNOWLEDGE_KEYS:
                continue
            if isinstance(val, list) and val and all(isinstance(v, dict) for v in val):
                section(key, key.replace("_", " ").capitalize(), render_json(val, 1))

        if len(out) == head_len:
            out.append('<p class="empty">Esta página aún no tiene contenido.</p>')
        self.page(path, title, "\n".join(out), description=p.get("summary") or f"{title} ({CLASS_ES[cls]}) para WoW Forever.",
                  toc=toc, page_class="page-knowledge")

    def build_class_index(self, cls: str, pages: list[dict]):
        path = CLASS_SLUG[cls]
        name = CLASS_ES[cls]
        brackets = [p for p in pages if levels_of(p) and p.get("kind", "page") == "page"]
        refs = [p for p in pages if p not in brackets]
        brackets.sort(key=lambda p: levels_of(p))

        def card(p):
            lv = levels_of(p)
            kind = KIND_ES.get(p.get("kind", "page"), "Guía")
            lvh = f'<span class="lvl">Niv. {fmt_range(*lv)}</span>' if lv else ""
            return (f'<li class="card link-card"><a href="{ROOT}{p["_path"]}/"><span class="card-kicker">{esc(kind)} {lvh}</span>'
                    f'<span class="card-title">{esc(p.get("title") or p["id"])}</span>'
                    f'{f"<span class=card-text>{esc(excerpt(p.get("summary", ""), 140))}</span>" if p.get("summary") else ""}'
                    f'</a>{badge(p.get("status"), p.get("sources"), p.get("checked"), small=True)}</li>')

        intro = ("Consejos que valen para cualquier clase." if cls == "ANY"
                 else f"Todo lo que necesitas para subir un {name.lower()} en WoW Forever: etapas por nivel, "
                      "talentos, hechizos, rotación, macros y profesiones.")
        out = [f'<header class="page-head"><p class="eyebrow">Conocimiento</p><h1>{esc(name)}</h1>'
               f'<p class="lead">{esc(intro)}</p></header>']
        toc = []
        if brackets:
            toc.append(("etapas", "Por niveles"))
            out.append(f'<h2 id="etapas">Por niveles</h2><ul class="cards">{"".join(card(p) for p in brackets)}</ul>')
        if refs:
            toc.append(("referencia", "Referencia"))
            out.append(f'<h2 id="referencia">Referencia</h2><ul class="cards">{"".join(card(p) for p in refs)}</ul>')
        self.page(path, name, "\n".join(out), toc=toc, page_class="page-class",
                  description=f"Conocimiento de {name.lower()} para WoW Forever.")
        self.index(name, f"{path}/", "Clase", intro)

    # ------------------------------------------------------------------ otras páginas
    def build_home(self):
        guides = self.data.guides
        cards = []
        for g in guides:
            steps = self.data.all_steps(g)
            c = count_status(steps)
            lv = guide_levels(g)
            kicker = " · ".join(x for x in [FACTION_ES.get(g.get("faction"), ""),
                                             f"Niv. {fmt_range(*lv)}" if lv else ""] if x)
            cards.append(f'<li class="card link-card"><a href="{ROOT}{guide_path(g)}/">'
                         f'<span class="card-kicker">{esc(kicker)}</span>'
                         f'<span class="card-title">{esc(g.get("title") or g["id"])}</span>'
                         f'<span class="card-text">{len(steps)} pasos · {pct(c)} verificado</span></a>'
                         f'{status_bar(c)}</li>')
        guides_html = (f'<ul class="cards">{"".join(cards)}</ul>' if cards else
                       '<p class="empty">Las guías se están escribiendo. Vuelve pronto o sigue el progreso en GitHub.</p>')
        classes = "".join(f'<li><a class="pill" href="{ROOT}{CLASS_SLUG[c]}/">{esc(CLASS_ES[c])}</a></li>'
                          for c in CLASS_ORDER if c in self.data.knowledge)
        features = [
            ("compass", "Paso a paso", "Cada paso se completa solo: misiones aceptadas o entregadas, objetos, "
                                       "hechizos aprendidos, rutas de vuelo, nivel…"),
            ("goto", "Flecha propia", "Distancia, tiempo estimado y giro. Con modo cadáver: al morir te lleva a tu "
                                      "cuerpo. No necesitas TomTom."),
            ("shield", "Datos verificados", "Cada paso indica si está verificado, sin verificar o en disputa, "
                                           "y de qué fuentes sale."),
            ("train", "Conocimiento por clase", "Talentos, hechizos por nivel, rotación, macros listas para copiar "
                                               "y rutas de profesión."),
            ("people", "Convive con Questie", "No duplica sus iconos ni su seguimiento; si está instalado, "
                                             "lo aprovecha para completar coordenadas."),
            ("globe", "En español", "Textos pensados para jugar en español; los nombres salen del propio "
                                    "cliente, así coinciden con tu idioma."),
        ]
        feat_html = "".join(f'<li class="feature">{icon(i)}<h3>{esc(t)}</h3><p>{esc(d)}</p></li>'
                            for i, t, d in features)
        shots = ["La guía en pantalla (HUD)", "La flecha y el modo cadáver", "El panel de conocimiento"]
        shots_html = "".join(f'<figure class="shot"><div class="shot-frame" role="img" '
                             f'aria-label="Captura pendiente: {esc(s)}">{icon("map")}<span>Captura próximamente</span></div>'
                             f'<figcaption>{esc(s)}</figcaption></figure>' for s in shots)
        version = f" {self.data.version}" if self.data.version else ""
        body = f"""
<section class="hero">
  <div class="hero-mark" aria-hidden="true">{logo_svg(96)}</div>
  <div>
    <p class="eyebrow">Addon para WoW Forever{esc(version)}</p>
    <h1>Senda</h1>
    <p class="lead">Guía de leveo paso a paso del 1 al 60, en español. Te dice adónde ir, qué misión coger y
    cuándo entregarla, con una flecha propia y datos que se verifican en el juego.</p>
    <p class="actions">
      <a class="btn btn-primary" href="{RELEASES_URL}" target="_blank" rel="noopener">{icon("download")}Descargar</a>
      <a class="btn btn-ghost" href="#guias">{icon("map")}Ver las guías</a>
      <a class="btn btn-ghost" href="{REPO_URL}" target="_blank" rel="noopener">{icon("github")}GitHub</a>
    </p>
  </div>
</section>

<section aria-labelledby="que-es">
  <h2 id="que-es">Qué es Senda</h2>
  <p>Senda es un addon gratuito y de código abierto para <strong>WoW Forever</strong>. Empieza con el
  <strong>brujo gnomo</strong> y el <strong>mago humano</strong>, y está pensado para añadir cualquier raza y clase.
  Las guías son datos abiertos: cada paso dice de dónde sale y si se ha comprobado. Esta web es la versión
  extendida de lo que ves en el juego; el botón «Leer más» del addon te trae aquí.</p>
</section>

<section aria-labelledby="instalar">
  <h2 id="instalar">Instalación</h2>
  <ol class="install">
    <li><strong>Descarga</strong> el último <code>Senda-x.y.z.zip</code> desde
      <a href="{RELEASES_URL}" target="_blank" rel="noopener">GitHub Releases</a>.</li>
    <li><strong>Cierra el juego</strong> (o sal a la pantalla de personajes).</li>
    <li><strong>Descomprime</strong> el zip en <code>World of Warcraft\\_forever_\\Interface\\AddOns</code>.
      Debe quedar <code>…\\AddOns\\Senda\\Senda.toc</code> (sin carpetas <code>Senda\\Senda</code> anidadas).</li>
    <li>En la pantalla de personajes pulsa <strong>AddOns</strong> y comprueba que Senda está activado.</li>
    <li>Entra en el juego y escribe <kbd>/senda</kbd>.</li>
  </ol>
  <div class="tip">{icon("tip")}<div><strong>Actualizar:</strong> borra la carpeta <code>Senda</code> antigua y
  descomprime la nueva. Tu progreso se guarda aparte y no se pierde.</div></div>
</section>

<section aria-labelledby="funciones">
  <h2 id="funciones">Funciones</h2>
  <ul class="features">{feat_html}</ul>
</section>

<section aria-labelledby="capturas">
  <h2 id="capturas">Capturas</h2>
  <div class="shots">{shots_html}</div>
</section>

<section aria-labelledby="guias">
  <h2 id="guias">Guías</h2>
  {guides_html}
  {f'<h3>Conocimiento por clase</h3><ul class="pills">{classes}</ul>' if classes else ''}
</section>

<section aria-labelledby="colabora">
  <h2 id="colabora">Colabora</h2>
  <p>¿Un paso mal o unas coordenadas que no cuadran? Abre una incidencia o un PR en
  <a href="{REPO_URL}" target="_blank" rel="noopener">github.com/e-omunoz/senda</a>. Consulta el
  <a href="{ROOT}estado/">estado de los datos</a> para ver qué falta por verificar.</p>
</section>
"""
        toc = [("que-es", "Qué es Senda"), ("instalar", "Instalación"), ("funciones", "Funciones"),
               ("capturas", "Capturas"), ("guias", "Guías")]
        self.page("", "", body, toc=toc, page_class="page-home")
        self.index("Instalación", "#instalar", "Ayuda", "Descarga el zip y descomprímelo en Interface\\AddOns")

    def build_changelog(self):
        path = self.root / "CHANGELOG.md"
        toc: list = []
        out = ['<header class="page-head"><p class="eyebrow">Proyecto</p><h1>Historial de cambios</h1></header>']
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            text = re.sub(r"\A\s*#\s[^\n]*\n", "", text)  # el título lo pone la página
            out.append(f'<div class="prose changelog">{md(text, shift=0, anchors=Anchors({"contenido"}), toc=toc)}</div>')
        else:
            out.append('<p class="empty">Aún no hay versiones publicadas.</p>')
        self.page("cambios", "Cambios", "\n".join(out), toc=toc[:30], page_class="page-changelog",
                  description="Historial de versiones de Senda.")
        self.index("Historial de cambios", "cambios/", "Proyecto")

    def _validate_summary(self):
        if self.validate_json and Path(self.validate_json).is_file():
            try:
                return json.loads(Path(self.validate_json).read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                self.warnings.append(f"{self.validate_json}: {e}")
                return None
        script = self.root / "tools" / "validate.py"
        if not self.validate or not script.is_file():
            return None
        try:
            r = subprocess.run([sys.executable, str(script), "--json", "--root", str(self.root)],
                               cwd=self.root, capture_output=True, timeout=180,
                               encoding="utf-8", errors="replace")
            start = r.stdout.find("{")
            return json.loads(r.stdout[start:]) if start >= 0 else None
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            self.warnings.append(f"tools/validate.py --json: {e}")
            return None

    def build_status(self):
        guides = self.data.guides
        out = ['<header class="page-head"><p class="eyebrow">Proyecto</p><h1>Estado de los datos</h1>'
               '<p class="lead">Cada paso de Senda lleva un estado de verificación. Solo se marca como verificado '
               'lo que se ha contrastado con una fuente oficial, con observaciones del juego o con la base de '
               'datos local más otra fuente independiente.</p>'
               '<p class="legend">'
               + "".join(f'<span class="lg lg-{s}" title="{esc(STATUS_HELP[s])}">{STATUS_ES[s]}</span>' for s in STATUSES)
               + f'</p><p class="muted">Generado el {self.today.isoformat()}.</p></header>']
        toc = [("guias", "Guías")]

        # pasos únicos (las secciones compartidas cuentan una vez)
        uniq: dict[str, dict] = {}
        for g in guides:
            for s in self.data.all_steps(g):
                uniq[str(s.get("id") or id(s))] = s
        tc = count_status(uniq.values())
        out.append(f'<h2 id="guias">Guías</h2><div class="stat-total"><p><strong>{sum(tc.values())}</strong> pasos únicos · '
                   f'<strong>{pct(tc)}</strong> verificados</p>{status_bar(tc)}</div>')
        if guides:
            rows = []
            for g in guides:
                c = count_status(self.data.all_steps(g))
                gp = guide_path(g)
                sec_rows = "".join(
                    f'<tr><td><a href="{ROOT}{gp}/#{esc(slugify(sec.get("id")))}">{esc(sec.get("title") or sec.get("id"))}</a></td>'
                    + "".join(f'<td class="num">{count_status(sec["step"])[s]}</td>' for s in STATUSES)
                    + f'<td class="num">{pct(count_status(sec["step"]))}</td></tr>'
                    for sec in g["_sections"])
                rows.append(
                    f'<tr><th scope="row"><a href="{ROOT}{gp}/">{esc(g.get("title") or g["id"])}</a></th>'
                    f'<td class="num">{sum(c.values())}</td>'
                    + "".join(f'<td class="num">{c[s]}</td>' for s in STATUSES)
                    + f'<td class="num">{pct(c)}</td><td class="bar-cell">{status_bar(c)}</td></tr>'
                    + (f'<tr class="sub"><td colspan="7"><details><summary>Por sección</summary>'
                       f'<div class="table-wrap"><table class="compact"><thead><tr><th scope="col">Sección</th>'
                       + "".join(f'<th scope="col" class="num">{STATUS_ES[s]}</th>' for s in STATUSES)
                       + f'<th scope="col" class="num">%</th></tr></thead><tbody>{sec_rows}</tbody></table></div>'
                       f'</details></td></tr>' if sec_rows else ""))
            out.append('<div class="table-wrap"><table class="stats"><thead><tr><th scope="col">Guía</th>'
                       '<th scope="col" class="num">Pasos</th>'
                       + "".join(f'<th scope="col" class="num">{STATUS_ES[s]}</th>' for s in STATUSES)
                       + '<th scope="col" class="num">% verif.</th><th scope="col"><span class="sr-only">Gráfico</span></th>'
                       f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')
            disputed = [(g, s) for g in guides for s in self.data.all_steps(g) if s.get("status") == "disputed"]
            if disputed:
                toc.append(("disputa", "Pasos en disputa"))
                seen = set()
                items = []
                for g, s in disputed:
                    if s.get("id") in seen:
                        continue
                    seen.add(s.get("id"))
                    items.append(f'<li><a href="{ROOT}{guide_path(g)}/#{esc(slugify(s.get("id")))}"><code>{esc(s.get("id"))}</code></a> '
                                 f'{esc(excerpt(s.get("text", ""), 120))}</li>')
                out.append(f'<h2 id="disputa">Pasos en disputa</h2><ul class="plain">{"".join(items[:200])}</ul>')
        else:
            out.append('<p class="empty">Todavía no hay guías publicadas.</p>')

        kpages = [p for cls in CLASS_ORDER for p in self.data.knowledge.get(cls, [])]
        if kpages:
            toc.append(("conocimiento", "Conocimiento"))
            rows = "".join(f'<tr><td><a href="{ROOT}{p["_path"]}/">{esc(p.get("title") or p["id"])}</a></td>'
                           f'<td>{esc(CLASS_ES[p["_class"]])}</td><td>{esc(KIND_ES.get(p.get("kind"), "Guía"))}</td>'
                           f'<td>{badge(p.get("status"), p.get("sources"), p.get("checked"), small=True)}</td></tr>'
                           for p in kpages)
            kc = count_status(kpages)
            out.append(f'<h2 id="conocimiento">Conocimiento</h2>{status_bar(kc)}<div class="table-wrap"><table>'
                       f'<thead><tr><th scope="col">Página</th><th scope="col">Clase</th><th scope="col">Tipo</th>'
                       f'<th scope="col">Estado</th></tr></thead><tbody>{rows}</tbody></table></div>')

        report = self.root / "harness" / "reports" / "verify-latest.json"
        toc.append(("informe", "Último informe"))
        out.append('<h2 id="informe">Último informe de verificación</h2>')
        if report.is_file():
            try:
                rep = json.loads(report.read_text(encoding="utf-8"))
                out.append(f'<div class="report">{render_json(rep)}</div>')
            except (OSError, ValueError) as e:
                out.append(f'<p class="empty">No se pudo leer el informe ({esc(e)}).</p>')
        else:
            out.append('<p class="empty">Todavía no hay informes de verificación publicados.</p>')

        val = self._validate_summary()
        if isinstance(val, dict):
            toc.append(("validacion", "Validación estática"))
            ok = val.get("ok")
            state = ('<span class="badge badge-verified">' + icon("check") + 'Sin errores</span>' if ok
                     else '<span class="badge badge-disputed">' + icon("alert") + 'Con errores</span>')
            out.append(f'<h2 id="validacion">Validación estática</h2><p>{state} '
                       f'{esc(val.get("errors", 0))} errores · {esc(val.get("warnings", 0))} avisos</p>')
            issues = [i for i in as_list(val.get("issues")) if isinstance(i, dict)]
            if issues:
                items = "".join(
                    f'<li class="issue-{esc(i.get("level", ""))}"><span class="tag">{"Error" if i.get("level") == "error" else "Aviso"}</span> '
                    f'<code>{esc(i.get("file", ""))}{(" [" + esc(i.get("where")) + "]") if i.get("where") else ""}</code> '
                    f'{esc(i.get("msg", ""))}</li>' for i in issues[:200])
                more = f'<p class="muted">… y {len(issues) - 200} más.</p>' if len(issues) > 200 else ""
                out.append(f'<details class="issues"><summary>Ver incidencias ({len(issues)})</summary>'
                           f'<ul class="plain">{items}</ul>{more}</details>')

        if self.warnings or self.broken:
            toc.append(("web", "Avisos de la web"))
            items = "".join(f"<li>{esc(w)}</li>" for w in self.warnings + self.broken)
            out.append(f'<h2 id="web">Avisos al generar la web</h2><ul class="plain">{items}</ul>')
        self.page("estado", "Estado de los datos", "\n".join(out), toc=toc, page_class="page-status",
                  description="Estado de verificación de los datos de Senda.")
        self.index("Estado de los datos", "estado/", "Proyecto", "Verificación por guía e informe más reciente")

    def build_404(self):
        body = (f'<header class="page-head"><p class="eyebrow">Error 404</p><h1>Te has salido de la senda</h1>'
                f'<p class="lead">Esta página no existe o ha cambiado de sitio. Prueba con el buscador o vuelve al inicio.</p>'
                f'<p class="actions"><a class="btn btn-primary" href="{ROOT}">{icon("compass")}Volver al inicio</a></p></header>')
        self.page("404", "Página no encontrada", body, absolute_root=True, page_class="page-404")
        html_404 = self.pages.pop("404")
        self.raw.pop("404", None)
        return html_404

    # ------------------------------------------------------------------ comprobación de enlaces
    def check_links(self):
        for origin, link in self.links:
            key = link_key(link)
            if not key:
                continue
            path, frag = key
            if path not in self.raw:
                self.broken.append(f"Enlace roto en {origin}: «{link}» (no existe la página)")
            elif frag and f'id="{frag}"' not in self.raw[path]:
                self.broken.append(f"Enlace roto en {origin}: «{link}» (no existe el ancla)")

    # ------------------------------------------------------------------ build
    def build(self) -> dict:
        for g in self.data.guides:
            self.build_guide(g)
        for cls in CLASS_ORDER:
            pages = self.data.knowledge.get(cls)
            if pages:
                self.build_class_index(cls, pages)
                for p in pages:
                    self.build_knowledge_page(p)
        self.build_changelog()
        self.build_home()
        self.check_links()
        self.build_status()
        html_404 = self.build_404()
        self.write(html_404)
        return {"pages": len(self.pages), "guides": len(self.data.guides),
                "knowledge": sum(len(v) for v in self.data.knowledge.values()),
                "search": len(self.search), "warnings": list(self.warnings), "broken": list(self.broken)}

    def write(self, html_404: str):
        out = self.out
        if out.exists():
            if out.resolve() == self.root.resolve() or (out / "data").is_dir() or (out / ".git").exists():
                raise SystemExit(f"Me niego a borrar {out}: parece un repositorio, no una salida")
            shutil.rmtree(out)
        out.mkdir(parents=True)

        def put(rel: str, text: str):
            p = out / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)

        for path, text in self.pages.items():
            put(f"{path}/index.html" if path else "index.html", text)
        put("404.html", html_404)
        put("search.json", json.dumps(self.search, ensure_ascii=False, separators=(",", ":")))
        put(".nojekyll", "")
        put("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}sitemap.xml\n")
        urls = "".join(f"<url><loc>{esc(SITE_URL + (p + '/' if p else ''))}</loc></url>" for p in sorted(self.pages))
        put("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
                           f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n')
        static = self.src / "static"
        if static.is_dir():
            shutil.copytree(static, out / "static")


def logo_svg(size: int = 32) -> str:
    """Logotipo original: un sendero que serpentea hasta una estrella dentro de un anillo."""
    return (f'<svg class="logo" width="{size}" height="{size}" viewBox="0 0 48 48" aria-hidden="true" focusable="false">'
            '<circle cx="24" cy="24" r="21" fill="none" stroke="currentColor" stroke-width="2.5" opacity=".55"/>'
            '<path d="M14 39c4-5 14-4 14-10s-12-5-12-11 8-7 12-8" fill="none" stroke="currentColor" '
            'stroke-width="3.2" stroke-linecap="round" stroke-dasharray="1 5.2"/>'
            '<path d="M33 7.5l1.6 3.4 3.7.5-2.7 2.6.7 3.7-3.3-1.8-3.3 1.8.7-3.7-2.7-2.6 3.7-.5z" fill="currentColor"/>'
            '</svg>')


def render_json(v, depth: int = 0) -> str:
    """Representación genérica y legible de un JSON (informes del harness)."""
    if isinstance(v, dict):
        if not v:
            return '<span class="muted">—</span>'
        if depth >= 3:
            return f"<code>{esc(excerpt(json.dumps(v, ensure_ascii=False), 200))}</code>"
        rows = "".join(f"<dt>{esc(str(k).replace('_', ' '))}</dt><dd>{render_json(val, depth + 1)}</dd>"
                       for k, val in v.items())
        return f'<dl class="kvlist">{rows}</dl>'
    if isinstance(v, list):
        if not v:
            return '<span class="muted">—</span>'
        if all(isinstance(x, dict) for x in v) and depth < 3:
            cols: list[str] = []
            for x in v:
                for k in x:
                    if k not in cols:
                        cols.append(k)
            cols = cols[:8]
            head = "".join(f'<th scope="col">{esc(c)}</th>' for c in cols)
            body = "".join("<tr>" + "".join(f"<td>{render_json(x.get(c), 3) if isinstance(x.get(c), (dict, list)) else esc(_scalar(x.get(c)))}</td>" for c in cols) + "</tr>"
                           for x in v[:100])
            more = f'<p class="muted">… y {len(v) - 100} filas más.</p>' if len(v) > 100 else ""
            return f'<div class="table-wrap"><table class="compact"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>{more}'
        items = [esc(_scalar(x)) if not isinstance(x, (dict, list)) else render_json(x, depth + 1) for x in v[:50]]
        return ", ".join(items) + (f" … (+{len(v) - 50})" if len(v) > 50 else "")
    if isinstance(v, str) and re.match(r"^https?://\S+$", v):
        return f'<a href="{esc(v)}" target="_blank" rel="noopener">{esc(v)}</a>'
    return esc(_scalar(v))


def _scalar(v) -> str:
    if v is None:
        return "—"
    if v is True:
        return "sí"
    if v is False:
        return "no"
    if isinstance(v, float):
        return f"{v:.1f}"
    return str(v)


def build(root=REPO_ROOT, out=None, site_src=SITE_SRC, validate=True, validate_json=None, today=None) -> dict:
    root = Path(root)
    out = Path(out) if out else root / "_site"
    return Site(root, out, site_src, validate=validate, validate_json=validate_json, today=today).build()


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Genera la web estática de Senda en _site/.")
    ap.add_argument("--root", default=str(REPO_ROOT), help="raíz con data/ (por defecto, el repo)")
    ap.add_argument("--out", help="carpeta de salida (por defecto <root>/_site)")
    ap.add_argument("--no-validate", action="store_true", help="no ejecutar tools/validate.py --json")
    ap.add_argument("--validate-json", help="usar este JSON de validate.py en vez de ejecutarlo")
    ap.add_argument("--strict", action="store_true", help="fallar si hay enlaces rotos o avisos")
    args = ap.parse_args(argv)
    res = build(args.root, args.out, validate=not args.no_validate, validate_json=args.validate_json)
    for w in res["warnings"] + res["broken"]:
        print(f"AVISO {w}", file=sys.stderr)
    out = Path(args.out) if args.out else Path(args.root) / "_site"
    print(f"Web generada en {out}: {res['pages'] + 1} páginas, {res['guides']} guías, "
          f"{res['knowledge']} páginas de conocimiento, {res['search']} entradas de búsqueda, "
          f"{len(res['warnings']) + len(res['broken'])} avisos")
    return 1 if args.strict and (res["warnings"] or res["broken"]) else 0


if __name__ == "__main__":
    sys.exit(main())

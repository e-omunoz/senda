"""Afirmaciones (claims) extraídas de las fuentes: esquema, análisis y normalización.

El modelo devuelve JSON (salida estructurada en la API, o texto en el camino de Claude Code).
Aquí se valida, se descarta lo que no tiene cita y se asigna el tier **desde la URL**, nunca
desde lo que diga el modelo.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

CATEGORIES = (
    "hotfix", "xp_change", "quest_change", "npc_move", "class_change", "talent_change",
    "profession_change", "zone_change", "dungeon_change", "item_change", "new_trick",
    "addon_api", "other",
)

# Esquema JSON para la salida estructurada de `watch` (output_config.format).
CLAIMS_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "relevant": {"type": "boolean"},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": list(CATEGORIES)},
                    "summary_es": {"type": "string"},
                    "quote": {"type": "string"},
                    "url": {"type": "string"},
                    "date": {"type": "string"},
                    "classes": {"type": "array", "items": {"type": "string"}},
                    "races": {"type": "array", "items": {"type": "string"}},
                    "zones": {"type": "array", "items": {"type": "string"}},
                    "quest_ids": {"type": "array", "items": {"type": "integer"}},
                    "npc_ids": {"type": "array", "items": {"type": "integer"}},
                    "item_ids": {"type": "array", "items": {"type": "integer"}},
                    "spell_ids": {"type": "array", "items": {"type": "integer"}},
                    "levels": {"type": "array", "items": {"type": "integer"}},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": ["category", "summary_es", "quote", "url", "date", "classes", "races",
                             "zones", "quest_ids", "npc_ids", "item_ids", "spell_ids", "levels",
                             "confidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["relevant", "claims"],
    "additionalProperties": False,
}

CLASS_TOKENS = ("WARRIOR", "PALADIN", "HUNTER", "ROGUE", "PRIEST", "SHAMAN", "MAGE", "WARLOCK", "DRUID")


@dataclass
class Claim:
    id: str
    category: str
    summary_es: str
    quote: str
    url: str
    date: str
    tier: str
    source_id: str | None
    quote_confirmed: bool
    classes: list[str] = field(default_factory=list)
    races: list[str] = field(default_factory=list)
    zones: list[str] = field(default_factory=list)
    quest_ids: list[int] = field(default_factory=list)
    npc_ids: list[int] = field(default_factory=list)
    item_ids: list[int] = field(default_factory=list)
    spell_ids: list[int] = field(default_factory=list)
    levels: list[int] = field(default_factory=list)
    confidence: str = "medium"
    found: str = ""             # fecha en que lo encontró el harness
    item_url: str = ""          # elemento del que se extrajo
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, d: dict) -> "Claim":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)


class ClaimParseError(ValueError):
    pass


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json(text: str):
    """Saca el primer objeto/array JSON de un texto (admite bloques ```json```)."""
    if isinstance(text, (dict, list)):
        return text
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for m in _FENCE.finditer(text):
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            continue
    # Primer { ... } equilibrado
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        while start != -1:
            depth, in_str, esc = 0, False, False
            for i in range(start, len(text)):
                c = text[i]
                if in_str:
                    if esc:
                        esc = False
                    elif c == "\\":
                        esc = True
                    elif c == '"':
                        in_str = False
                    continue
                if c == '"':
                    in_str = True
                elif c == opener:
                    depth += 1
                elif c == closer:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i + 1])
                        except json.JSONDecodeError:
                            break
            start = text.find(opener, start + 1)
    raise ClaimParseError("no se encontró JSON válido en la respuesta")


def normalize_text(s: str) -> str:
    """Normaliza para comparar citas: entidades HTML, comillas tipográficas, espacios, mayúsculas."""
    s = html.unescape(s or "")
    s = unicodedata.normalize("NFKC", s)
    s = (s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
          .replace("–", "-").replace("—", "-").replace(" ", " ").replace("…", "..."))
    s = re.sub(r"\s+", " ", s)
    return s.strip().casefold()


def quote_in_text(quote: str, text: str, min_len: int = 12) -> bool:
    """La cita debe aparecer literalmente (tras normalizar). Admite '...' como elipsis entre trozos."""
    q = normalize_text(quote)
    t = normalize_text(text)
    if len(q) < min_len:
        return False
    if q in t:
        return True
    parts = [p.strip() for p in re.split(r"\.\.\.|\[\.\.\.\]", q) if p.strip()]
    if len(parts) > 1 and all(len(p) >= 8 for p in parts):
        pos = 0
        for p in parts:
            j = t.find(p, pos)
            if j == -1:
                return False
            pos = j + len(p)
        return True
    return False


def claim_id(url: str, quote: str) -> str:
    return hashlib.sha1((url.strip() + "\n" + normalize_text(quote)).encode("utf-8")).hexdigest()[:12]


def _int_list(v) -> list[int]:
    out = []
    for x in v or []:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return out


def _str_list(v) -> list[str]:
    return [str(x).strip() for x in (v or []) if str(x).strip()]


def _norm_date(s: str, fallback: str) -> str:
    s = (s or "").strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3])).isoformat()
        except ValueError:
            pass
    return fallback


def parse_claims(payload, *, item_url: str, item_text: str, item_tier: str | None,
                 registry=None, today: str | None = None, item_date: str = "") -> tuple[list[Claim], list[str]]:
    """Valida la salida del modelo y devuelve (claims, avisos).

    - Sin URL http(s) o sin cita -> se descarta.
    - Tier: si la cita está literalmente en el elemento leído (`item_text`), se usa el tier del elemento
      (que sabe distinguir, p. ej., mensajes azules). Si la URL citada es otra, se clasifica por URL.
      Si la cita no se encuentra, el tier baja a community_unverified.
    """
    today = today or date.today().isoformat()
    warnings: list[str] = []
    try:
        data = extract_json(payload)
    except ClaimParseError as e:
        return [], [str(e)]
    if isinstance(data, list):
        data = {"relevant": bool(data), "claims": data}
    if not isinstance(data, dict):
        return [], ["la respuesta no es un objeto JSON"]
    raw = data.get("claims") or []
    out: list[Claim] = []
    seen: set[str] = set()
    for i, c in enumerate(raw):
        if not isinstance(c, dict):
            warnings.append(f"claim {i}: no es un objeto")
            continue
        url = str(c.get("url") or item_url or "").strip()
        quote = str(c.get("quote") or "").strip()
        summary = str(c.get("summary_es") or "").strip()
        if not re.match(r"^https?://", url):
            if item_url and not re.match(r"^https?://", item_url):
                url = item_url   # elemento local (Discord): se cita por su ruta
            else:
                warnings.append(f"claim {i}: URL inválida, descartada")
                continue
        if not quote or not summary:
            warnings.append(f"claim {i}: sin cita o sin resumen, descartada")
            continue
        cat = c.get("category") if c.get("category") in CATEGORIES else "other"
        cid = claim_id(url, quote)
        if cid in seen:
            continue
        seen.add(cid)
        confirmed = quote_in_text(quote, item_text)
        notes = []
        same_item = url.rstrip("/") == item_url.rstrip("/") or not re.match(r"^https?://", item_url or "")
        if confirmed and (same_item or registry is None) and item_tier:
            tier, sid = item_tier, None
            if registry is not None:
                sid = registry.classify_url(url)[1]
        elif registry is not None:
            tier, sid = registry.classify_url(url)
            if confirmed and item_tier:
                # La cita está en el elemento leído, pero la URL apunta a otro sitio: gana el menor tier.
                from .config import TIER_RANK
                if TIER_RANK[item_tier] < TIER_RANK[tier]:
                    tier = item_tier
        else:
            tier, sid = "community_unverified", None
        if not confirmed:
            tier = "community_unverified"
            notes.append("cita no encontrada literalmente en la fuente: rebajada a community_unverified")
        classes = [x.upper() for x in _str_list(c.get("classes")) if x.upper() in CLASS_TOKENS]
        out.append(Claim(
            id=cid, category=cat, summary_es=summary, quote=quote, url=url,
            date=_norm_date(str(c.get("date") or ""), _norm_date(item_date, today)),
            tier=tier, source_id=sid, quote_confirmed=confirmed, classes=classes,
            races=_str_list(c.get("races")), zones=_str_list(c.get("zones")),
            quest_ids=_int_list(c.get("quest_ids")), npc_ids=_int_list(c.get("npc_ids")),
            item_ids=_int_list(c.get("item_ids")), spell_ids=_int_list(c.get("spell_ids")),
            levels=_int_list(c.get("levels")),
            confidence=c.get("confidence") if c.get("confidence") in ("high", "medium", "low") else "medium",
            found=today, item_url=item_url, notes=notes,
        ))
    return out, warnings

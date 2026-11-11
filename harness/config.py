"""Configuración del harness: rutas, modelo, precios y registro de fuentes.

Todo se puede sobrescribir con variables de entorno (ver docs/HARNESS.md).
Este módulo solo usa la biblioteca estándar.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "harness"
STATE = HARNESS / "state"
INBOX = STATE / "inbox"          # veredictos/afirmaciones producidos por Claude Code
REPORTS = HARNESS / "reports"
CACHE = ROOT / ".cache" / "harness"   # ignorado por git
DATA = Path(os.environ.get("SENDA_HARNESS_DATA") or ROOT / "data")   # se puede apuntar a fixtures
TOOLS = ROOT / "tools"

TIERS = ("official", "community_curated", "community_unverified")
TIER_RANK = {"official": 3, "community_curated": 2, "community_unverified": 1}

# USD por millón de tokens (entrada, salida). Precios públicos de la API de Anthropic
# (caché de la skill claude-api, 2026-11-03). Revisa https://platform.claude.com/docs/en/about-claude/pricing
PRICING = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-fable-5-2": (8.00, 40.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
}
CACHE_WRITE_MULT = 1.25    # escritura de caché de 5 min
CACHE_READ_MULT = 0.10
WEB_SEARCH_USD = 0.01      # por búsqueda (10 USD / 1000), estimación


def rel(p: Path) -> str:
    """Ruta relativa al repo (o absoluta si está fuera, p. ej. fixtures)."""
    try:
        return Path(p).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return Path(p).as_posix()


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default) or default


@dataclass
class Settings:
    model: str = field(default_factory=lambda: _env("SENDA_HARNESS_MODEL", "claude-opus-5-5"))
    # Esfuerzo por tarea (low | medium | high | xhigh | max). Opus 5.5 usa medium por defecto.
    effort_extract: str = field(default_factory=lambda: _env("SENDA_HARNESS_EFFORT_EXTRACT", "medium"))
    effort_audit: str = field(default_factory=lambda: _env("SENDA_HARNESS_EFFORT_AUDIT", "high"))
    effort_tips: str = field(default_factory=lambda: _env("SENDA_HARNESS_EFFORT_TIPS", "high"))
    max_tokens: int = int(_env("SENDA_HARNESS_MAX_TOKENS", "16000"))
    # Respaldo del servidor ante rechazos (stop_reason "refusal"). "" lo desactiva.
    refusal_fallback: str = field(default_factory=lambda: _env("SENDA_HARNESS_FALLBACK", "default"))
    web_search_max_uses: int = int(_env("SENDA_HARNESS_WEB_SEARCHES", "8"))
    web_fetch_max_uses: int = int(_env("SENDA_HARNESS_WEB_FETCHES", "6"))
    # Restringe búsqueda/lectura web a los dominios del registro de fuentes.
    restrict_domains: bool = _env("SENDA_HARNESS_RESTRICT_DOMAINS", "1") == "1"
    max_turns: int = int(_env("SENDA_HARNESS_MAX_TURNS", "12"))
    steps_per_call: int = int(_env("SENDA_HARNESS_STEPS_PER_CALL", "25"))


def price_for(model: str) -> tuple[float, float]:
    if model in PRICING:
        return PRICING[model]
    # Prefijo (p. ej. un id con sufijo) o desconocido: asume el modelo por defecto, avisa en el informe.
    for k, v in PRICING.items():
        if model.startswith(k):
            return v
    return PRICING["claude-opus-5-5"]


# --------------------------------------------------------------------------- registro de fuentes

@dataclass
class Source:
    id: str
    name: str
    tier: str
    kind: str
    url: str
    match: list[str] = field(default_factory=list)
    cadence: str | int = "daily"
    lang: str = "en"
    link_pattern: str | None = None
    keywords: list[str] = field(default_factory=list)
    blue_only: bool = False
    check: bool = False
    enabled: bool = True
    max_items: int = 10
    max_item_chars: int = 40000

    @property
    def cadence_hours(self) -> float:
        c = self.cadence
        if isinstance(c, (int, float)):
            return float(c)
        return {"hourly": 1, "daily": 20, "weekly": 160}.get(str(c), 20)  # holgura para el cron


@dataclass
class Registry:
    sources: list[Source]
    user_agent: str = "SendaHarness/0.1"

    def get(self, sid: str) -> Source:
        for s in self.sources:
            if s.id == sid:
                return s
        raise KeyError(sid)

    def watched(self) -> list[Source]:
        return [s for s in self.sources if s.enabled and s.kind != "reference"]

    def domains(self) -> list[str]:
        out: list[str] = []
        for s in self.sources:
            for m in s.match + [_strip_scheme(s.url)]:
                host = m.split("/")[0]
                if host and "." in host and host not in out and not host.startswith("harness"):
                    out.append(host)
        return sorted(out)

    def classify_url(self, url: str) -> tuple[str, str | None]:
        """Devuelve (tier, source_id) de una URL por el prefijo más largo. Por defecto: unverified."""
        u = _strip_scheme(url).lower()
        best: tuple[int, str, str | None] = (-1, "community_unverified", None)
        for s in self.sources:
            for m in s.match:
                m = m.lower().rstrip("/")
                if m and _prefix_boundary(u, m) and len(m) > best[0]:
                    best = (len(m), s.tier, s.id)
        return best[1], best[2]


def _strip_scheme(url: str) -> str:
    u = url.strip()
    for p in ("https://", "http://"):
        if u.lower().startswith(p):
            u = u[len(p):]
    return u


def _prefix_boundary(u: str, m: str) -> bool:
    """Evita que 'reddit.com' case con 'notreddit.com.evil' o 'wowhead.com/forever' con '/foreverx'."""
    if not u.startswith(m):
        return False
    rest = u[len(m):]
    if "/" not in m:  # solo host
        return rest == "" or rest[0] in "/?#:"
    return rest == "" or rest[0] in "/?#" or m.endswith(("/", "="))


def load_registry(path: Path | None = None) -> Registry:
    path = path or HARNESS / "sources.toml"
    with open(path, "rb") as f:
        doc = tomllib.load(f)
    d = doc.get("defaults", {})
    out = []
    for raw in doc.get("source", []):
        if raw.get("tier") not in TIERS:
            raise ValueError(f"fuente {raw.get('id')}: tier inválido {raw.get('tier')!r}")
        s = Source(
            id=raw["id"], name=raw.get("name", raw["id"]), tier=raw["tier"], kind=raw["kind"],
            url=raw["url"], match=list(raw.get("match", [])),
            cadence=raw.get("cadence", d.get("cadence", "daily")), lang=raw.get("lang", "en"),
            link_pattern=raw.get("link_pattern"), keywords=list(raw.get("keywords", [])),
            blue_only=bool(raw.get("blue_only", False)), check=bool(raw.get("check", False)),
            enabled=bool(raw.get("enabled", True)),
            max_items=int(raw.get("max_items", d.get("max_items", 10))),
            max_item_chars=int(raw.get("max_item_chars", d.get("max_item_chars", 40000))),
        )
        out.append(s)
    ids = [s.id for s in out]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise ValueError(f"ids de fuente duplicados: {sorted(dup)}")
    return Registry(out, d.get("user_agent", "SendaHarness/0.1"))

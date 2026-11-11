"""Reglas de confianza (única fuente de verdad para `status`).

ARCHITECTURE.md, «Harness de verificación»: `verified` exige
  (a) una fuente oficial, o
  (b) una observación en juego, o
  (c) base de datos local (QuestieDB) + otra fuente independiente.
El resto entra como `unverified` o `disputed`.

Aquí solo cuenta la evidencia **confirmada por el propio harness** (cita encontrada literalmente en la
página, consulta real a QuestieDB, observación presente en data/observations). Lo que diga el modelo
sobre el tier o la verificación se ignora: el tier sale de la URL (sources.toml) y la confirmación,
de comprobaciones deterministas (evidence.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field

STATUSES = ("verified", "unverified", "disputed")
SUPPORTS = ("supports", "contradicts", "neutral")
KINDS = ("web", "questie", "observation")
# Un tier tan bajo no basta para abrir una disputa: solo se anota en el informe.
DISPUTE_MIN_TIERS = ("official", "community_curated")


class RuleViolation(Exception):
    """Se intentó marcar algo como verificado sin cumplir las reglas."""


@dataclass
class Evidence:
    kind: str                    # web | questie | observation
    supports: str                # supports | contradicts | neutral
    url: str = ""                # web
    quote: str = ""              # web: cita literal
    ref: str = ""                # questie:quest/179 | obs:accept/179
    tier: str = "community_unverified"   # solo web; lo asigna el harness por URL
    confirmed: bool = False      # lo pone evidence.py tras comprobarlo
    detail: str = ""             # motivo de (no) confirmación, para el informe

    @property
    def source_key(self) -> str:
        """Identidad de la fuente para comprobar independencia (dominio o base de datos)."""
        if self.kind == "web":
            u = self.url.split("://", 1)[-1]
            return "web:" + u.split("/", 1)[0].lower().removeprefix("www.")
        return self.kind

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in
                ("kind", "supports", "url", "quote", "ref", "tier", "confirmed", "detail")}

    @classmethod
    def from_dict(cls, d: dict) -> "Evidence":
        kind = d.get("kind", "web")
        sup = d.get("supports", "neutral")
        if kind not in KINDS:
            kind = "web"
        if sup not in SUPPORTS:
            sup = "neutral"
        return cls(kind=kind, supports=sup, url=str(d.get("url") or ""), quote=str(d.get("quote") or ""),
                   ref=str(d.get("ref") or ""), tier=str(d.get("tier") or "community_unverified"),
                   confirmed=bool(d.get("confirmed", False)), detail=str(d.get("detail") or ""))


@dataclass
class Decision:
    status: str
    rule: str                    # a | b | c | "" (qué regla permitió verified)
    disputed: bool = False
    contradicted: bool = False   # evidencia fuerte en contra y ninguna a favor
    reasons: list[str] = field(default_factory=list)


def _counts_for_dispute(e: Evidence) -> bool:
    return e.kind in ("questie", "observation") or e.tier in DISPUTE_MIN_TIERS


def verification_rule(evidence: list[Evidence]) -> str:
    """Devuelve 'a', 'b' o 'c' si la evidencia confirmada a favor permite `verified`; '' si no."""
    sup = [e for e in evidence if e.confirmed and e.supports == "supports"]
    if any(e.kind == "web" and e.tier == "official" for e in sup):
        return "a"
    if any(e.kind == "observation" for e in sup):
        return "b"
    if any(e.kind == "questie" for e in sup):
        others = [e for e in sup if e.kind == "web" and e.tier in ("official", "community_curated")]
        if others:
            return "c"
    return ""


def decide(evidence: list[Evidence], proposed: str = "unverified") -> Decision:
    """Calcula el estado permitido. `proposed` (lo que sugiere el modelo) solo puede rebajarse."""
    if proposed not in STATUSES:
        proposed = "unverified"
    conf = [e for e in evidence if e.confirmed]
    sup = [e for e in conf if e.supports == "supports"]
    con = [e for e in conf if e.supports == "contradicts" and _counts_for_dispute(e)]
    reasons = []
    unconfirmed = [e for e in evidence if not e.confirmed]
    if unconfirmed:
        reasons.append(f"{len(unconfirmed)} evidencia(s) sin confirmar no cuentan")
    if sup and con:
        return Decision("disputed", "", disputed=True,
                        reasons=reasons + ["hay fuentes confirmadas a favor y en contra"])
    if con:
        return Decision("unverified", "", contradicted=True,
                        reasons=reasons + ["la evidencia confirmada contradice el dato"])
    rule = verification_rule(evidence)
    if proposed == "verified":
        if rule:
            return Decision("verified", rule, reasons=reasons + [f"regla ({rule})"])
        return Decision("unverified", "", reasons=reasons + ["no cumple (a), (b) ni (c): queda unverified"])
    if proposed == "disputed":
        return Decision("disputed", "", disputed=True, reasons=reasons + ["el auditor lo marca en disputa"])
    return Decision("unverified", "", reasons=reasons)


def assert_can_verify(evidence: list[Evidence]) -> str:
    """Barrera final antes de escribir status = "verified" en un TOML."""
    rule = verification_rule(evidence)
    if not rule:
        raise RuleViolation("status = verified sin evidencia confirmada que cumpla (a), (b) o (c)")
    if any(e.confirmed and e.supports == "contradicts" and _counts_for_dispute(e) for e in evidence):
        raise RuleViolation("status = verified con evidencia confirmada en contra (debe ser disputed)")
    return rule


def step_status_after(current: str, decision: Decision, value_changes: bool) -> str:
    """Estado final de un paso teniendo en cuenta el estado actual.

    - Un paso verificado al que le llega evidencia en contra pasa a `disputed`, nunca a `unverified`
      en silencio: un humano decide.
    - Un cambio de valor sin regla cumplida deja el paso en `unverified`.
    """
    if decision.disputed:
        return "disputed"
    if decision.contradicted:
        return "disputed" if current == "verified" and not value_changes else "unverified"
    if decision.status == "verified":
        return "verified"
    if current == "verified" and not value_changes:
        return "verified"   # no hay motivo para rebajarlo
    if current == "disputed" and not value_changes:
        return "disputed"   # sigue en disputa hasta que un humano lo resuelva o haya regla
    return "unverified"

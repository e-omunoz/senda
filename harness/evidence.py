"""Confirmación determinista de la evidencia que propone el modelo.

Nada cuenta para las reglas hasta pasar por aquí:
- web: la URL se clasifica por sources.toml (tier) y la cita debe aparecer literalmente en la página.
- questie: la referencia (questie:quest/179) se consulta de verdad con tools/lookup.py.
- observation: la referencia (obs:accept/179) debe existir en data/observations.
"""
from __future__ import annotations

from .claims import quote_in_text
from .config import Registry
from .fetch import FetchError, cached_page_text
from .localtools import lookup, observations, parse_ref
from .rules import Evidence


class Confirmer:
    def __init__(self, registry: Registry, *, offline: bool = False, page_text=None, lookup_fn=None,
                 obs_fn=None, verify_verdicts: dict[str, str] | None = None):
        self.registry = registry
        self.offline = offline
        self._page_text = page_text or (lambda url: cached_page_text(url, user_agent=registry.user_agent))
        self._lookup = lookup_fn or lookup
        self._obs = obs_fn or observations
        self._pages: dict[str, str | None] = {}
        # Resultado de tools/verify.py por paso: un "conflict" invalida la evidencia QuestieDB a favor.
        self.verify_verdicts = verify_verdicts or {}

    def page(self, url: str) -> str | None:
        if url not in self._pages:
            try:
                self._pages[url] = self._page_text(url)
            except (FetchError, OSError, ValueError):
                self._pages[url] = None
        return self._pages[url]

    def confirm(self, e: Evidence) -> Evidence:
        e.confirmed = False
        if e.kind == "web":
            e.tier, _ = self.registry.classify_url(e.url) if e.url else ("community_unverified", None)
            if not e.url.startswith(("http://", "https://")):
                e.detail = "URL no válida"
            elif not e.quote:
                e.detail = "sin cita literal"
            elif self.offline:
                e.detail = "sin comprobar (modo offline)"
            else:
                text = self.page(e.url)
                if text is None:
                    e.detail = "no se pudo descargar la página para comprobar la cita"
                elif quote_in_text(e.quote, text):
                    e.confirmed = True
                    e.detail = "cita encontrada en la página"
                else:
                    e.detail = "la cita no aparece literalmente en la página"
        elif e.kind == "questie":
            r = parse_ref(e.ref)
            if not r or r[0] != "questie":
                e.detail = f"referencia QuestieDB no válida: {e.ref!r}"
            else:
                found, out = self._lookup(r[1], r[2])
                e.confirmed = found
                e.detail = "existe en QuestieDB local" if found else f"no confirmado en QuestieDB: {out[:200]}"
        elif e.kind == "observation":
            r = parse_ref(e.ref)
            if not r or r[0] != "obs":
                e.detail = f"referencia de observación no válida: {e.ref!r}"
            else:
                hits = self._obs(r[1], r[2])
                e.confirmed = bool(hits)
                e.detail = f"{len(hits)} observación(es) en partida" if hits else "sin observaciones en partida"
        return e

    def confirm_all(self, items: list[dict | Evidence], step_id: str | None = None) -> list[Evidence]:
        out = []
        for x in items:
            e = x if isinstance(x, Evidence) else Evidence.from_dict(x)
            self.confirm(e)
            if (e.kind == "questie" and e.confirmed and e.supports == "supports" and step_id
                    and self.verify_verdicts.get(step_id) == "conflict"):
                e.confirmed = False
                e.detail = "tools/verify.py informa conflicto con QuestieDB en este paso"
            out.append(e)
        return out

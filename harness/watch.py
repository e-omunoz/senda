"""Pipeline `watch`: vigila fuentes, detecta novedades y extrae afirmaciones con cita."""
from __future__ import annotations

import sys
from datetime import date, datetime, timezone

from . import prompts, state
from .claims import CLAIMS_SCHEMA, Claim, parse_claims
from .config import Registry, Settings
from .fetch import FetchError, fetch_source, load_lazy
from .llm import LLM, BudgetExceeded, LLMError, system_blocks


def _due(src, st: dict, force: bool) -> bool:
    if force:
        return True
    last = st.get("last_run")
    if not last:
        return True
    try:
        dt = datetime.fromisoformat(last)
    except ValueError:
        return True
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600 >= src.cadence_hours


def run(registry: Registry, settings: Settings, llm: LLM, *, limit: int | None = None,
        source_ids: list[str] | None = None, force: bool = False, out=sys.stdout) -> dict:
    """Devuelve un resumen {nuevos, claims, errores}. En dry-run no escribe estado."""
    wstate = state.load("watch.json", {})
    cstate = state.load("claims.json", {"claims": []})
    known = {c["id"] for c in cstate["claims"]}
    system = system_blocks(prompts.WATCH)
    summary = {"items": 0, "claims": 0, "errors": [], "skipped": [], "truncated": [], "warnings": []}
    remaining = limit if limit is not None else 10**9
    today = date.today().isoformat()
    for src in registry.watched():
        if source_ids and src.id not in source_ids:
            continue
        st = wstate.setdefault(src.id, {"seen": {}})
        if not _due(src, st, force):
            summary["skipped"].append(src.id)
            continue
        if remaining <= 0:
            break
        try:
            items = fetch_source(src, user_agent=registry.user_agent)
        except (FetchError, ValueError) as e:
            msg = f"{src.id}: {e}" + (" (URL por confirmar: revisa sources.toml)" if src.check else "")
            summary["errors"].append(msg)
            out.write(f"[watch] ERROR {msg}\n")
            st["last_error"] = str(e)[:300]
            continue
        st.pop("last_error", None)
        new = []
        for it in items:
            prev = st["seen"].get(it.id)
            if it.meta.get("lazy"):
                if prev is not None:
                    continue           # enlace ya visto: no se vuelve a descargar
                try:
                    load_lazy(it, registry.user_agent, src.max_item_chars)
                except FetchError as e:
                    summary["errors"].append(f"{src.id}: {e}")
                    continue
            if prev == it.hash:
                continue
            new.append(it)
            if len(new) >= min(src.max_items, remaining):
                break
        out.write(f"[watch] {src.id}: {len(items)} elementos, {len(new)} nuevos o cambiados\n")
        for it in new:
            if not it.text.strip():
                st["seen"][it.id] = it.hash
                continue
            if it.truncated:
                summary["truncated"].append(it.url)
            tier = it.tier or src.tier
            user = (f"Fecha de hoy: {today}\nFuente: {src.name} (id {src.id}, tier {tier}, idioma {src.lang})\n"
                    f"URL del elemento: {it.url}\nTítulo: {it.title}\nFecha del elemento: {it.date or '?'}\n"
                    + ("AVISO: texto recortado por tamaño.\n" if it.truncated else "")
                    + f"\n<elemento>\n{it.text}\n</elemento>")
            try:
                data = llm.json_call(f"watch {src.id} {it.id}", system, user, CLAIMS_SCHEMA,
                                     settings.effort_extract)
            except BudgetExceeded as e:
                summary["errors"].append(str(e))
                out.write(f"[watch] presupuesto agotado: {e}\n")
                _finish(llm, wstate, cstate, summary)
                return summary
            except LLMError as e:
                summary["errors"].append(str(e))
                continue
            summary["items"] += 1
            remaining -= 1
            if data is None:   # dry-run
                continue
            claims, warns = parse_claims(data, item_url=it.url, item_text=it.title + "\n" + it.text,
                                         item_tier=tier, registry=registry, today=today, item_date=it.date)
            summary["warnings"] += [f"{it.url}: {w}" for w in warns]
            for c in claims:
                if c.id in known:
                    continue
                known.add(c.id)
                d = c.to_dict()
                d["processed"] = False
                d["source_id"] = d.get("source_id") or src.id
                cstate["claims"].append(d)
                summary["claims"] += 1
            st["seen"][it.id] = it.hash
            if remaining <= 0:
                break
        st["last_run"] = state.now_iso()
    _finish(llm, wstate, cstate, summary)
    return summary


def _finish(llm: LLM, wstate, cstate, summary) -> None:
    if llm.dry_run:
        return
    for st in wstate.values():   # limita el tamaño del estado
        if len(st.get("seen", {})) > 2000:
            st["seen"] = dict(list(st["seen"].items())[-2000:])
    state.save("watch.json", wstate)
    state.save("claims.json", cstate)


def pending_claims(registry: Registry | None = None, *, offline: bool = False) -> list[Claim]:
    """Afirmaciones sin procesar: las de `watch` y las que deja Claude Code en state/inbox/claims-*.json.

    Las de Claude Code no se fían: se vuelve a descargar cada URL y se pasa por parse_claims
    (cita literal + tier por URL), igual que en `watch`.
    """
    data = state.load("claims.json", {"claims": []})
    out = [Claim.from_dict(c) for c in data["claims"] if not c.get("processed")]
    known = {c.id for c in out} | {c["id"] for c in data["claims"]}
    if registry is None:
        return out
    from .claims import extract_json
    from .fetch import cached_page_text
    for f in state.inbox_files("claims"):
        try:
            raw = extract_json(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        for c in (raw.get("claims", []) if isinstance(raw, dict) else raw):
            if not isinstance(c, dict):
                continue
            url = str(c.get("url") or "")
            text = ""
            if not offline and url.startswith("http"):
                try:
                    text = cached_page_text(url, user_agent=registry.user_agent)
                except (FetchError, OSError):
                    text = ""
            parsed, _ = parse_claims({"claims": [c]}, item_url=url, item_text=text, item_tier=None,
                                     registry=registry)
            for p in parsed:
                if p.id not in known:
                    p.notes.append(f"aportada por Claude Code ({f.name})")
                    known.add(p.id)
                    out.append(p)
    return out

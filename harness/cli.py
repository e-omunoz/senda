"""Punto de entrada: python -m harness watch|audit|propose|tips [opciones]

Ejemplos:
  python -m harness watch --dry-run --limit 2
  python -m harness audit --guide gnome-warlock --limit 1 --budget-usd 2
  python -m harness propose --dry-run --offline
  python -m harness tips --guide human-mage
  python -m harness daily --open-pr        # watch + propose (+ PR), lo que hace CI
"""
from __future__ import annotations

import argparse
import json
import sys

from . import state
from .config import Settings, load_registry
from .llm import LLM, Budget


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--dry-run", action="store_true",
                   help="imprime los prompts y la estimación sin llamar a la API ni escribir estado")
    p.add_argument("--limit", type=int, help="máximo de elementos (watch), secciones (audit) o razas/clases (tips)")
    p.add_argument("--guide", help="id de guía (data/guides/<id>)")
    p.add_argument("--budget-usd", type=float, help="tope de gasto estimado de esta ejecución (USD)")
    p.add_argument("--model", help="modelo (por defecto SENDA_HARNESS_MODEL o claude-opus-5-5)")
    p.add_argument("--no-cache", action="store_true", help="no reutilizar respuestas guardadas en .cache/harness")
    p.add_argument("--offline", action="store_true",
                   help="propose: no descarga páginas para confirmar citas (nada web cuenta para verified)")
    p.add_argument("--open-pr", action="store_true", help="propose: abre un PR con gh (para CI)")
    p.add_argument("--json", action="store_true", help="imprime el resumen final en JSON")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m harness", description="Harness de IA de Senda")
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("watch", help="vigila fuentes y extrae afirmaciones con cita")
    _common(w)
    w.add_argument("--source", action="append", help="solo esta fuente (repetible)")
    w.add_argument("--force", action="store_true", help="ignora la cadencia de cada fuente")
    a = sub.add_parser("audit", help="audita pasos de las guías (web + QuestieDB)")
    _common(a)
    a.add_argument("--section", help="id o nombre de archivo de una sección")
    p = sub.add_parser("propose", help="convierte resultados en ediciones TOML + informe (+ PR)")
    _common(p)
    t = sub.add_parser("tips", help="investiga trucos de leveo por raza/clase")
    _common(t)
    d = sub.add_parser("daily", help="watch + propose (lo que ejecuta CI a diario)")
    _common(d)
    d.add_argument("--source", action="append")
    d.add_argument("--force", action="store_true")
    wk = sub.add_parser("weekly", help="audit + tips + propose (lo que ejecuta CI cada semana)")
    _common(wk)
    wk.add_argument("--section")
    sub.add_parser("sources", help="lista el registro de fuentes")
    return ap


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    registry = load_registry()
    if args.cmd == "sources":
        for s in registry.sources:
            print(f"{s.id:28} {s.tier:21} {s.kind:10} {s.cadence!s:7} {s.url}")
        return 0
    settings = Settings()
    if args.model:
        settings.model = args.model
    budget = Budget(limit_usd=args.budget_usd)
    llm = LLM(settings, dry_run=args.dry_run, budget=budget, use_cache=not args.no_cache)
    summary: dict = {"cmd": args.cmd, "model": settings.model, "dry_run": args.dry_run}
    rc = 0
    cmd = args.cmd
    if cmd in ("watch", "daily"):
        from . import watch
        summary["watch"] = watch.run(registry, settings, llm, limit=args.limit, source_ids=args.source,
                                     force=args.force)
    if cmd in ("audit", "weekly"):
        from . import audit
        summary["audit"] = audit.run(registry, settings, llm, guide=args.guide,
                                     section=getattr(args, "section", None), limit=args.limit)
    if cmd in ("tips", "weekly"):
        from . import tips
        summary["tips"] = tips.run(registry, settings, llm, guide=args.guide, limit=args.limit)
    if cmd in ("propose", "daily", "weekly"):
        from . import propose
        prop, report = propose.run(registry, dry_run=args.dry_run, offline=args.offline,
                                   cost=budget.summary())
        summary["propose"] = {"steps": len(prop.changes), "files": [r for r, (a, b) in prop.files.items() if a != b],
                              "claims": len(prop.claims), "tips": len(prop.tips_added), "errors": prop.errors,
                              "report": str(report) if report else None}
        if args.open_pr and report and not args.dry_run:
            from .gitops import GitError, open_pr
            interesting = prop.has_edits or prop.claims or prop.tips_added
            if interesting:
                try:
                    summary["propose"]["pr"] = open_pr(report, f"Harness: propuestas del {prop.today}")
                except GitError as e:
                    print(f"[pr] ERROR: {e}", file=sys.stderr)
                    rc = 1
            else:
                print("[pr] nada relevante: no se abre PR")
    summary["cost"] = budget.summary()
    if not args.dry_run and budget.calls:
        log = state.load("costs.json", {"runs": []})
        log["runs"] = (log["runs"] + [{"date": state.now_iso(), "cmd": cmd, "model": settings.model,
                                       **budget.summary()}])[-200:]
        state.save("costs.json", log)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    else:
        c = budget.summary()
        print(f"[harness] {cmd}: {c['calls']} llamadas, ~{c['usd']:.3f} USD"
              + (f" (tope {c['limit_usd']:.2f})" if c["limit_usd"] is not None else ""))
    errs = [e for k in ("watch", "audit", "tips") for e in summary.get(k, {}).get("errors", [])]
    if any("presupuesto" in e for e in errs):
        print("[harness] parado por presupuesto", file=sys.stderr)
    return rc

"""Filtro de eficiencia («ninguna misión porque sí»): puntúa cada misión de las guías de Senda.

    python tools/route_score.py [--guide ID ...] [--foreverdb DIR] [--out data/scores] [--report]

Coste = viaje (repartido por paradas) + objetivo (muertes, botín, clics) + diálogo; beneficio = XP de la
misión y de las muertes, relativa a la XP del nivel, más lo que desbloquea. Decide keep/optional/drop
con umbrales sacados de la distribución de todas las guías por banda de nivel. No escribe en las guías:
deja data/scores/<guía>.json (por id de paso y de misión) y, con --report, data/scores/<guía>.report.md.
Modelo, fuentes y estimaciones: docs/EFFICIENCY.md.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from foreverdb import ForeverDB, resolve_foreverdb  # noqa: E402
from routescore import model as M  # noqa: E402
from routescore.route import REPO, World, band_stats, decide_guide, score_guide  # noqa: E402

FALLBACK_FOREVERDB = None  # se resuelve por --foreverdb / SENDA_FOREVERDB / .cache/foreverdb


def guide_dirs(root: Path, only: list[str] | None) -> list[Path]:
    out = []
    for d in sorted((root / "data" / "guides").iterdir()):
        if (d / "guide.toml").exists() and (not only or d.name in only):
            out.append(d)
    return out


def public(res: dict, bands: dict, info: dict) -> dict:
    meta = res["meta"]
    keep_fields = ("title", "quest_level", "level", "band", "steps", "xp", "xp_quest", "xp_kills", "xp_full",
                   "xp_share", "kills", "est_minutes", "objective_s", "travel_s", "dialog_s",
                   "travel_share_s", "travel_saved_s", "objectives", "xp_per_min", "rate", "grind_rate", "percentile", "rel_median", "chain_rate",
                   "unlocks", "decision", "reason", "why", "why_plain", "class_quest", "dungeon", "unknown",
                   "reward_items", "guide_optional", "flags", "estimated", "blocked_by")
    quests = {}
    for qid in sorted(res["quests"], key=lambda q: (res["quests"][q]["turnin_idx"] or 0, q)):
        x = res["quests"][qid]
        quests[str(qid)] = {k: x[k] for k in keep_fields if k in x and x[k] not in (None, [], "")}
        quests[str(qid)]["xp_per_min"] = x["xp_per_min"]
        for k in ("rate", "xp_share", "grind_rate", "rel_median", "chain_rate"):
            if isinstance(quests[str(qid)].get(k), float):
                quests[str(qid)][k] = round(quests[str(qid)][k], 2)
    counts = {"keep": 0, "optional": 0, "drop": 0}
    for x in res["quests"].values():
        counts[x["decision"]] += 1
    used_bands = sorted({x["band"] for x in res["quests"].values()}, key=lambda b: int(b.split("-")[0]))
    totals = {k: round(v, 1) for k, v in res["totals"].items()}
    return {
        "guide": meta["id"],
        "generated_by": "tools/route_score.py",
        "model": "docs/EFFICIENCY.md",
        "sources": {"forever-db": info, "travel": "tools/routescore/travel_facts.json (Polestar TravelData.lua)",
                    "level_xp": "Polestar tools/lib/game/xp.js (tabla 1.12)"},
        "estimates": {"EST_KILL_BASE": M.EST_KILL_BASE, "EST_KILL_PER_LEVEL": M.EST_KILL_PER_LEVEL,
                      "EST_DOWNTIME": M.EST_DOWNTIME, "GRIND_CAMP": [M.GRIND_SPAWNS, M.GRIND_RADIUS], "EST_RANK_MUL": M.EST_RANK_MUL,
                      "EST_CLICK_SECONDS": M.EST_CLICK_SECONDS, "EST_RESPAWN_SECONDS": M.EST_RESPAWN_SECONDS,
                      "EST_EVENT_SECONDS": M.EST_EVENT_SECONDS, "EST_ESCORT_SECONDS": M.EST_ESCORT_SECONDS,
                      "EST_DIALOG_SECONDS": 5.0, "WALK_DETOUR": M.WALK_DETOUR,
                      "replace_with": "tiempos del Grabador por paso; distancias de la malla de navegación"},
        "thresholds": {"keep": f"rate >= p{int(M.KEEP_PERCENTILE * 100)} de su banda, o su cadena",
                       "optional": f"rate >= {M.DROP_FRACTION_OF_MEDIAN} x mediana de su banda, o con recompensa",
                       "drop": "el resto, y lo que requiere una misión descartada",
                       "rate": "% del nivel por hora (XP / XP del nivel / minutos x 60 x 100)"},
        "bands": {b: {k: (round(v, 2) if isinstance(v, float) else v) for k, v in bands[b].items()
                      if not k.startswith("_")} for b in used_bands if b in bands},
        "summary": {"quests": len(res["quests"]), **counts,
                    "minutes_quests": round(sum(x["est_minutes"] for x in res["quests"].values()), 1),
                    "minutes_dropped": round(sum(x["est_minutes"] for x in res["quests"].values()
                                                 if x["decision"] == "drop"), 1),
                    "xp_dropped": sum(x["xp"] for x in res["quests"].values() if x["decision"] == "drop"),
                    "overhead_s": totals},
        "quests": quests,
        "steps": res["steps"],
    }


def dump_compact(out: dict) -> str:
    """JSON legible y pequeño: una línea por misión y por paso (los diffs muestran qué cambió)."""
    def one(v):
        return json.dumps(v, ensure_ascii=False, separators=(",", ":"))

    lines = ["{"]
    keys = list(out)
    for i, k in enumerate(keys):
        end = "," if i < len(keys) - 1 else ""
        v = out[k]
        if k in ("quests", "steps", "bands") and isinstance(v, dict):
            lines.append(f" {one(k)}: {{")
            items = list(v.items())
            for j, (kk, vv) in enumerate(items):
                lines.append(f"  {one(kk)}: {one(vv)}{',' if j < len(items) - 1 else ''}")
            lines.append(f" }}{end}")
        else:
            lines.append(f" {one(k)}: {one(v)}{end}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def report(out: dict, n: int = 20) -> str:
    qs = [(int(k), v) for k, v in out["quests"].items()
          if v["decision"] != "keep" or v.get("reason") in ("rate", "chain")]
    qs = [(k, v) for k, v in qs if v.get("percentile") is not None and v.get("reason") not in
          ("class", "dungeon", "unknown", "not_turned_in")]
    qs.sort(key=lambda kv: (kv[1]["percentile"], kv[1]["rate"]))
    lines = [f"# Filtro de eficiencia: {out['guide']}", "",
             "GENERADO por tools/route_score.py --report. Notas de experto: docs/EFFICIENCY.md.", "",
             f"Misiones: {out['summary']['quests']} · keep {out['summary']['keep']} · optional "
             f"{out['summary']['optional']} · drop {out['summary']['drop']} · tiempo estimado en misiones "
             f"{out['summary']['minutes_quests']:.0f} min (descartado {out['summary']['minutes_dropped']:.0f} min, "
             f"{out['summary']['xp_dropped']} XP).", ""]

    def table(title, rows):
        lines.append(f"## {title}")
        lines.append("")
        lines.append("| misión | nivel | XP | min | XP/min | %nivel/h | pct banda | decisión | por qué | banderas |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for qid, v in rows:
            lines.append(f"| {qid} {v.get('title', '')} | {v['level']} | {v['xp']} | {v['est_minutes']:.1f} | "
                         f"{v['xp_per_min']:.0f} | {v['rate']:.1f} | {v.get('percentile', 0):.0f} | {v['decision']} | "
                         f"{v['why_plain']} | {', '.join(v.get('flags', []))} |")
        lines.append("")

    table(f"Las {n} con menos rendimiento", qs[:n])
    table(f"Las {n} con más rendimiento", list(reversed(qs[-n:])))
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--guide", action="append", help="id de guía (carpeta de data/guides); por defecto, todas")
    ap.add_argument("--foreverdb", help="carpeta de forever-db (o env SENDA_FOREVERDB; por defecto .cache/foreverdb)")
    ap.add_argument("--out", default=str(REPO / "data" / "scores"))
    ap.add_argument("--report", action="store_true", help="escribe también <guía>.report.md")
    ap.add_argument("--root", default=str(REPO))
    args = ap.parse_args(argv)
    t0 = time.time()
    root = resolve_foreverdb(args.foreverdb)
    db = ForeverDB.open(args.foreverdb)
    world = World(db, root)
    info = {"version": db.info.get("version"), "client_build": db.info.get("client_build"),
            "commit": db.info.get("build_commit")}
    repo = Path(args.root)
    # Las bandas salen de TODAS las guías de la misma facción (las de la Horda no mueven las de la Alianza);
    # --guide solo limita lo que se escribe.
    results = [score_guide(d, repo / "data" / "shared", world) for d in guide_dirs(repo, None)]
    by_faction: dict[str, list] = {}
    for res in results:
        by_faction.setdefault(res["meta"].get("faction") or "Alliance", []).append(res)
    bands_of = {f: band_stats(rs) for f, rs in by_faction.items()}
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    for res in results:
        fb = bands_of[res["meta"].get("faction") or "Alliance"]
        decide_guide(res, fb)
        gid = res["meta"]["id"]
        if args.guide and gid not in args.guide:
            continue
        out = public(res, fb, info)
        (out_dir / f"{gid}.json").write_text(dump_compact(out), encoding="utf-8", newline="\n")
        if args.report:
            (out_dir / f"{gid}.report.md").write_text(report(out), encoding="utf-8", newline="\n")
        s = out["summary"]
        print(f"{gid}: {s['quests']} misiones · keep {s['keep']} · optional {s['optional']} · drop {s['drop']} · "
              f"{s['minutes_quests']:.0f} min en misiones, {s['minutes_dropped']:.0f} min descartables")
    for faction, fb in sorted(bands_of.items()):
        bands_out = {b: {k: (round(v, 2) if isinstance(v, float) else v) for k, v in st.items()
                         if not k.startswith("_")} for b, st in fb.items()}
        if faction == "Alliance":  # el archivo de siempre
            name, doc = "bands.json", {"rate": "% del nivel por hora", "bands": bands_out}
        else:
            name = f"bands-{faction.lower()}.json"
            doc = {"rate": "% del nivel por hora", "faction": faction, "bands": bands_out}
        (out_dir / name).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8",
                                    newline="\n")
    print(f"bandas: {', '.join(f'{f} {len(b)}' for f, b in sorted(bands_of.items()))} · {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Compara el tiempo medido de cada paso (grabaciones) con el estimado por el filtro de eficiencia.

Uso:
    python tools/route_report.py [--guide ID] [--recordings data/recordings] [--scores data/scores]
                                 [--min-samples 1] [--include-partial] [--json] [--check] [--no-traces]

Adaptado de Polestar, tools/lib/recording/report.js (medianas por paso y umbrales de desviación).

Entradas:
  * data/recordings/*.json   salida de tools/ingest_recording.py (campo `passes`).
  * data/scores/<guía>.json  salida de route_score: pasos -> minutos estimados (y XP estimada). Formatos admitidos:
        {"guide": "gnome-warlock", "steps": {"coldridge-001": {"est_minutes": 1.5, "xp": 120}, ...}}
        {"steps": [{"id": "coldridge-001", "est_minutes": 1.5, "xp": 120}, ...]}
        {"coldridge-001": {"est_minutes": 1.5}, ...}            (sin envoltorio)
    Claves de minutos: est_minutes | minutes | est_min | min. De XP: est_xp | xp.

Salida: por paso, tiempo medido (mediana de las pasadas completas), estimado, razón medido/estimado y nº de muestras;
los pasos a más del doble (o menos de la mitad) de lo estimado; y la mediana de |medido/estimado - 1|, que el plan
quiere en 30 % o menos por paso. Con --check, código de salida 1 si la mediana lo supera.

Rastros: cada grabación con posiciones se vuelca como caminatas continuas en data/recordings/traces/<sesión>.json
(para la navegación). Con --no-traces no se escribe nada.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import REPO_ROOT, setup_stdio  # noqa: E402

TARGET = 0.30           # plan 6b: error mediano ≤ 30 % por paso
OFF_FACTOR = 2.0        # "a más del doble" (o menos de la mitad)
TELEPORT_SPEED = 40.0   # yd/s
WALK_GAP = 30           # s: más hueco entre puntos parte la caminata
MIN_WALK_POINTS, MIN_WALK_YARDS = 3, 30.0
MINUTE_KEYS = ("est_minutes", "minutes", "est_min", "min")
XP_KEYS = ("est_xp", "xp")


# --------------------------------------------------------------------------- entradas
def load_recordings(folder: Path) -> list[dict]:
    docs = []
    if folder.is_dir():
        for f in sorted(folder.glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(d, dict) and d.get("schema") == 2 and isinstance(d.get("passes"), list):
                d["_file"] = f.name
                docs.append(d)
    return docs


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def parse_score(data) -> dict[str, dict]:
    """Fichero de puntuación -> {id de paso: {"min": minutos, "xp": xp o None}}."""
    if not isinstance(data, dict):
        return {}
    steps = data.get("steps", data)
    items = []
    if isinstance(steps, dict):
        items = list(steps.items())
    elif isinstance(steps, list):
        items = [(s.get("id"), s) for s in steps if isinstance(s, dict)]
    out = {}
    for sid, v in items:
        if not isinstance(sid, str):
            continue
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[sid] = {"min": float(v), "xp": None}
        elif isinstance(v, dict):
            m = next((_num(v[k]) for k in MINUTE_KEYS if _num(v.get(k)) is not None), None)
            xp = next((_num(v[k]) for k in XP_KEYS if _num(v.get(k)) is not None), None)
            if m is not None:
                out[sid] = {"min": m, "xp": xp}
    return out


def load_scores(folder: Path) -> dict[str, dict]:
    scores = {}
    if folder.is_dir():
        for f in sorted(folder.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            guide = data.get("guide") if isinstance(data, dict) and isinstance(data.get("guide"), str) else f.stem
            parsed = parse_score(data)
            if parsed:
                scores[guide] = parsed
    return scores


# --------------------------------------------------------------------------- cálculo
def collect_passes(docs: list[dict], include_partial: bool = False) -> dict[tuple, list[dict]]:
    """(guía, paso) -> pasadas completas, sin duplicados entre ficheros que se solapan."""
    seen = set()
    out: dict[tuple, list[dict]] = {}
    for d in docs:
        for p in d["passes"]:
            if not (p.get("completed") and not p.get("open")):
                continue
            if p.get("partial") and not include_partial:
                continue
            key = (p.get("char"), p.get("guide"), p.get("step"), round(float(p.get("start", 0))))
            if key in seen:
                continue
            seen.add(key)
            out.setdefault((p["guide"], p["step"]), []).append(p)
    return out


def build_report(docs, scores, guide=None, min_samples=1, include_partial=False) -> dict:
    passes = collect_passes(docs, include_partial)
    guides = sorted({g for g, _ in passes} | set(scores))
    if guide:
        guides = [g for g in guides if g == guide]
    report = {"guides": [], "median_error": None, "steps_compared": 0, "target": TARGET}
    errors = []
    for g in guides:
        est = scores.get(g, {})
        rows = []
        step_ids = {s for (gg, s) in passes if gg == g}
        for sid in sorted(step_ids, key=lambda s: min(p["idx"] for p in passes[(g, s)])):
            ps = passes[(g, sid)]
            times = [p["time"] / 60.0 for p in ps]
            xps = [p["xp"] for p in ps]
            e = est.get(sid)
            row = {"step": sid, "n": len(ps), "measured_min": round(statistics.median(times), 2),
                   "measured_xp": round(statistics.median(xps)), "est_min": e["min"] if e else None,
                   "est_xp": e["xp"] if e else None, "ratio": None, "off": False}
            if e and e["min"] > 0 and len(ps) >= min_samples:
                row["ratio"] = round(row["measured_min"] / e["min"], 3)
                row["off"] = row["ratio"] > OFF_FACTOR or row["ratio"] < 1.0 / OFF_FACTOR
                errors.append(abs(row["measured_min"] / e["min"] - 1.0))
            rows.append(row)
        report["guides"].append({"guide": g, "steps": rows,
                                 "uncovered": sorted(s for s in step_ids if s not in est),
                                 "unmeasured": sum(1 for s in est if s not in step_ids)})
    if errors:
        report["median_error"] = round(statistics.median(errors), 4)
    report["steps_compared"] = len(errors)
    return report


def format_report(report: dict, top: int = 15) -> str:
    lines = []
    for g in report["guides"]:
        lines.append(f"== {g['guide']} ==")
        lines.append(f"{'paso':<22}{'n':>3}{'medido':>9}{'estim.':>9}{'razón':>8}  {'XP med/est':>12}")
        for r in g["steps"]:
            est = "-" if r["est_min"] is None else f"{r['est_min']:.1f}"
            ratio = "-" if r["ratio"] is None else f"{r['ratio']:.2f}"
            xp = f"{r['measured_xp']}/{'-' if r['est_xp'] is None else round(r['est_xp'])}"
            flag = "  <-- más de 2x" if r["off"] else ""
            lines.append(f"{r['step']:<22}{r['n']:>3}{r['measured_min']:>9.1f}{est:>9}{ratio:>8}  {xp:>12}{flag}")
        off = [r for r in g["steps"] if r["off"]]
        off.sort(key=lambda r: -abs(r["ratio"] - 1))
        if off:
            lines.append(f"Pasos a más del doble (o menos de la mitad) de lo estimado: {len(off)}")
            for r in off[:top]:
                lines.append(f"  {r['step']}: medido {r['measured_min']:.1f} min, estimado {r['est_min']:.1f} min "
                             f"(x{r['ratio']:.2f}, n={r['n']})")
        if g["uncovered"]:
            lines.append(f"Medidos sin estimación: {', '.join(g['uncovered'][:top])}")
        if g["unmeasured"]:
            lines.append(f"Estimados sin medir: {g['unmeasured']}")
        lines.append("")
    if report["median_error"] is None:
        lines.append("Sin pasos medidos con estimación: nada que comparar.")
    else:
        ok = report["median_error"] <= report["target"]
        lines.append(f"Error mediano |medido/estimado - 1| = {report['median_error'] * 100:.1f} % "
                     f"en {report['steps_compared']} pasos (objetivo <= {report['target'] * 100:.0f} %): "
                     f"{'CUMPLE' if ok else 'NO CUMPLE'}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- rastros
def export_traces(docs: list[dict], folder: Path) -> list[Path]:
    """Caminatas continuas de cada sesión -> traces/<sesión>.json (puntos [s desde la salida, x, y] en 1/10000 del mapa)."""
    written = []
    for d in docs:
        maps = d.get("maps", {})
        for s in d.get("sessions", []):
            trail = s.get("trail") or []
            if not trail:
                continue
            walks, cur = [], None
            for t, m, x, y in trail:
                w, h = maps.get(str(m), [3500.0, 2333.0])
                if cur is not None and cur["map"] == m:
                    px, py, pt = cur["_last"]
                    dist = (((x - px) / 10000.0 * w) ** 2 + ((y - py) / 10000.0 * h) ** 2) ** 0.5
                    dt = t - pt
                    if dt <= WALK_GAP and (dist / dt <= TELEPORT_SPEED if dt > 0 else dist < TELEPORT_SPEED):
                        cur["yards"] += dist
                        cur["points"].append([t - cur["t0"], x, y])
                        cur["_last"] = (x, y, t)
                        continue
                if cur is not None:
                    walks.append(cur)
                cur = {"map": m, "t0": t, "yards": 0.0, "points": [[0, x, y]], "_last": (x, y, t)}
            if cur is not None:
                walks.append(cur)
            keep = [{"map": c["map"], "t0": c["t0"], "yards": round(c["yards"]), "points": c["points"]}
                    for c in walks if len(c["points"]) >= MIN_WALK_POINTS and c["yards"] >= MIN_WALK_YARDS]
            if not keep:
                continue
            doc = {"schema": 1, "session": s["id"], "start": s["start"],
                   "maps": {str(w["map"]): maps.get(str(w["map"]), [3500.0, 2333.0]) for w in keep}, "walks": keep}
            folder.mkdir(parents=True, exist_ok=True)
            f = folder / f"{s['id']}.json"
            f.write_text(json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
            written.append(f)
    return written


def main(argv=None) -> int:
    setup_stdio()
    ap = argparse.ArgumentParser(description="Tiempo medido frente a tiempo estimado por paso.")
    ap.add_argument("--recordings", type=Path, default=REPO_ROOT / "data" / "recordings")
    ap.add_argument("--scores", type=Path, default=REPO_ROOT / "data" / "scores")
    ap.add_argument("--traces-dir", type=Path, default=None, help="por defecto <recordings>/traces")
    ap.add_argument("--guide", help="solo esta guía")
    ap.add_argument("--min-samples", type=int, default=1)
    ap.add_argument("--include-partial", action="store_true", help="incluye pasadas cuya entrada no se vio")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check", action="store_true", help="código 1 si la mediana supera el 30 %%")
    ap.add_argument("--no-traces", action="store_true")
    args = ap.parse_args(argv)

    docs = load_recordings(args.recordings)
    if not docs:
        print(f"No hay grabaciones en {args.recordings} (usa tools/ingest_recording.py).", file=sys.stderr)
        return 2
    report = build_report(docs, load_scores(args.scores), args.guide, args.min_samples, args.include_partial)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_report(report, args.top))
    if not args.no_traces:
        out = export_traces(docs, args.traces_dir or args.recordings / "traces")
        if out and not args.json:
            print(f"Rastros: {len(out)} fichero(s) en {out[0].parent}")
    if args.check and report["median_error"] is not None and report["median_error"] > TARGET:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

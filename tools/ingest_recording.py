#!/usr/bin/env python3
"""Lee las grabaciones de Senda (SendaRecorderDB, esquema 2) y calcula tiempos reales por paso.

Uso:
    python tools/ingest_recording.py RUTA/SavedVariables/Senda.lua [más ficheros...] [--out DIR] [--stdout]

El fichero está en WTF/Account/<cuenta>/SavedVariables/Senda.lua. La grabación se activa en el juego con
`/senda grabar on` (apagada por defecto); el formato de los registros está en addon/Senda/Recorder/Session.lua.

Qué calcula (por sesión = de un login/recarga hasta el siguiente):
  * Tiempo activo: suma de los huecos entre eventos consecutivos. El hueco mientras el jugador está AFK cuenta
    cero y los huecos de inactividad se recortan a 5 min (IDLE_CAP). El tiempo entre sesiones no cuenta.
  * Por paso ("pasada"): tiempo activo, en combate, XP ganada, yardas recorridas, muertes y entregas. Las pasadas
    siguen la frontera de cada personaje y guía: entrar en un paso posterior a la frontera cierra la pasada
    anterior y abre otra; volver al paso de la frontera (recarga, Atrás/Siguiente) la continúa; un paso por detrás
    es una revisita y no cuenta. Una pasada se marca `partial` si no se vio cómo se entró (primer registro tras
    login/cambio de guía), `open` si no se llegó a salir de ella y `left` es el motivo de salida.
  * Por sesión: XP/hora, yardas, muertes, ausencia.

Los tiempos activos y la frontera de pasadas siguen el método de Polestar (Adaptado de Polestar, tools/lib/recording/report.js).

Escribe data/recordings/<fecha>-<hash>.json, anónimo: sin nombres de personaje ni de reino (el grabador no
los guarda; aquí además solo se aceptan ids de guía/paso con caracteres simples). Los ids de personaje y cuenta
se sustituyen por un hash. Salida determinista: el mismo fichero produce el mismo archivo.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import REPO_ROOT, setup_stdio  # noqa: E402
from questiedb.luaparse import LuaParseError, parse_assignments  # noqa: E402

SCHEMA = 2
IDLE_CAP = 300.0         # s: un hueco sin eventos cuenta como mucho esto
TELEPORT_SPEED = 40.0    # yd/s: saltos más rápidos son hogar/portal/vuelo, no recorrido
FALLBACK_W, FALLBACK_H = 3500.0, 2333.0
ID_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")
KINDS = {"c", "l", "o", "s", "x", "k", "a", "d", "q", "u", "p", "t"}
REASONS = {"next", "skip", "back", "pick", "auto", "guide", "login", "end"}
COMPLETED_LEFT = {"next", "auto", "end"}


# --------------------------------------------------------------------------- lectura
def _short_hash(text: str, n: int) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:n]


def read_db(path: Path) -> dict:
    """SendaRecorderDB como dict Python (tablas Lua sin convertir: las claves enteras se conservan)."""
    src = path.read_text(encoding="utf-8", errors="replace")
    try:
        data = parse_assignments(src)
    except LuaParseError as e:
        raise SystemExit(f"{path}: no se pudo leer el SavedVariables: {e}")
    db = data.get("SendaRecorderDB")
    if not isinstance(db, dict):
        raise SystemExit(f"{path}: no contiene SendaRecorderDB")
    return db


def _int(s: str):
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


def _chunk_items(db: dict):
    """(seq, texto) ordenados por seq. Admite `chunks` como tabla con claves enteras o como lista."""
    chunks = db.get("chunks")
    if not isinstance(chunks, dict):
        return []
    items = []
    for k, v in chunks.items():
        if isinstance(k, int) and isinstance(v, str):
            items.append((k, v))
    items.sort()
    return items


def decode_record(fields: list[str]):
    """Valida un registro; devuelve (tipo, dt, args) o None."""
    if len(fields) < 2 or fields[0] not in KINDS:
        return None
    dt = _int(fields[1])
    if dt is None or dt < 0:
        return None
    kind, args = fields[0], fields[2:]
    ints = lambda a, n: len(a) >= n and all(_int(x) is not None for x in a[:n])  # noqa: E731
    if kind in ("l", "o", "d"):
        return kind, dt, []
    if kind in ("k", "a", "u", "t"):
        return (kind, dt, [_int(args[0])]) if ints(args, 1) and _int(args[0]) in (0, 1) else None
    if kind == "x":
        return (kind, dt, [_int(args[0]), _int(args[1])]) if ints(args, 2) else None
    if kind == "q":
        if len(args) >= 2 and args[0] in ("a", "t", "c") and _int(args[1]) is not None:
            return kind, dt, [args[0], _int(args[1])]
        return None
    if kind == "p":
        return (kind, dt, [_int(a) for a in args[:3]]) if ints(args, 3) else None
    if kind == "s":
        if len(args) < 3 or not ID_RE.match(args[0]) or not (ID_RE.match(args[1]) or args[1] == "-"):
            return None
        if args[2] not in REASONS:
            return None
        lvl = _int(args[3]) if len(args) > 3 else 0
        xp = _int(args[4]) if len(args) > 4 else 0
        idx = _int(args[5]) if len(args) > 5 else 0
        return kind, dt, [args[0], args[1], args[2], lvl or 0, xp or 0, idx or 0]
    return None


def build_sessions(db: dict):
    """Fragmentos -> sesiones de eventos con tiempo absoluto en décimas de segundo.

    Una sesión empieza en un fragmento nuevo con otro epoch/personaje o tras `o`, y en cada `l`.
    """
    stats = {"chunks": 0, "records": 0, "bad_records": 0}
    sessions: list[dict] = []
    cur = None
    for seq, text in _chunk_items(db):
        lines = text.split("\n")
        hdr = lines[0].split("\t") if lines else []
        epoch = _int(hdr[3]) if len(hdr) > 3 and hdr[0] == "c" else None
        char = hdr[4] if len(hdr) > 4 else ""
        if epoch is None or not ID_RE.match(char or "x"):
            stats["bad_records"] += 1
            continue
        stats["chunks"] += 1
        if cur is None or cur["closed"] or cur["epoch"] != epoch or cur["char"] != char:
            cur = {"epoch": epoch, "char": char, "events": [], "closed": False, "seqs": []}
            sessions.append(cur)
        cur["seqs"].append(seq)
        for line in lines[1:]:
            if not line:
                continue
            rec = decode_record(line.split("\t"))
            if rec is None:
                stats["bad_records"] += 1
                continue
            stats["records"] += 1
            kind, dt, args = rec
            if kind == "l" and cur["events"]:
                cur = {"epoch": epoch, "char": char, "events": [], "closed": False, "seqs": [seq]}
                sessions.append(cur)
            cur["events"].append((epoch * 10 + dt, kind, args))
            if kind == "o":
                cur["closed"] = True
    sessions = [s for s in sessions if s["events"]]
    return sessions, stats


# --------------------------------------------------------------------------- análisis
def _map_size(maps: dict, m: int):
    v = maps.get(m)
    if isinstance(v, dict) and 1 in v and 2 in v:
        w, h = v[1], v[2]
        if isinstance(w, (int, float)) and isinstance(h, (int, float)) and w > 0 and h > 0:
            return float(w), float(h)
    return FALLBACK_W, FALLBACK_H


def analyze_session(s: dict, maps: dict) -> dict:
    """Una sesión -> segmentos (un segmento por registro de paso) y totales."""
    events = sorted(s["events"], key=lambda e: e[0])
    segments: list[dict] = []
    cur = None
    combat = False
    afk = False
    duo = False
    duo_seen = False
    last_pos = None
    trail = []
    tot = {"active": 0.0, "combat": 0.0, "afk": 0.0, "idle": 0.0, "xp": 0, "yards": 0.0, "deaths": 0,
           "accepts": 0, "turnins": 0, "completes": 0}
    first_lvl = last_lvl = None
    t0 = events[0][0]
    prev_t = None
    for t, kind, args in events:
        if prev_t is not None:
            gap = max(0.0, (t - prev_t) / 10.0)
            d = 0.0 if afk else min(gap, IDLE_CAP)
            tot["active"] += d
            if combat:
                tot["combat"] += d
            if afk:
                tot["afk"] += gap
            elif gap > IDLE_CAP:
                tot["idle"] += gap - IDLE_CAP
            if cur is not None:
                cur["time"] += d
                if combat:
                    cur["combat"] += d
                if afk:
                    cur["afk"] += gap
                elif gap > IDLE_CAP:
                    cur["idle"] += gap - IDLE_CAP
        prev_t = t
        if kind == "s":
            guide, step, reason, lvl, xp, idx = args
            if first_lvl is None and lvl:
                first_lvl = lvl
            if lvl:
                last_lvl = lvl
            if step == "-":
                cur = {"guide": guide, "step": None, "idx": None, "reason": "end", "start": t / 10.0,
                       "time": 0.0, "combat": 0.0, "afk": 0.0, "idle": 0.0, "xp": 0, "yards": 0.0,
                       "deaths": 0, "turnins": 0, "duo": duo}
                segments.append(cur)
                cur = None  # tras terminar la guía no hay paso al que atribuir tiempo
                segments[-1]["end"] = True
            else:
                cur = {"guide": guide, "step": step, "idx": idx, "reason": reason, "start": t / 10.0,
                       "time": 0.0, "combat": 0.0, "afk": 0.0, "idle": 0.0, "xp": 0, "yards": 0.0,
                       "deaths": 0, "turnins": 0, "duo": duo}
                segments.append(cur)
        elif kind == "k":
            combat = args[0] == 1
        elif kind == "a":
            afk = args[0] == 1
        elif kind == "u":
            duo = args[0] == 1
            duo_seen = duo_seen or duo
            if cur is not None and duo:
                cur["duo"] = True
        elif kind == "x":
            tot["xp"] += args[0]
            last_lvl = args[1] or last_lvl
            if cur is not None:
                cur["xp"] += args[0]
        elif kind == "d":
            tot["deaths"] += 1
            if cur is not None:
                cur["deaths"] += 1
        elif kind == "q":
            if args[0] == "a":
                tot["accepts"] += 1
            elif args[0] == "t":
                tot["turnins"] += 1
                if cur is not None:
                    cur["turnins"] += 1
            else:
                tot["completes"] += 1
        elif kind == "t":
            last_pos = None
        elif kind == "p":
            m, x, y = args
            w, h = _map_size(maps, m)
            if last_pos is not None and last_pos[0] == m:
                dist = math.hypot((x - last_pos[1]) / 10000.0 * w, (y - last_pos[2]) / 10000.0 * h)
                dt = (t - last_pos[3]) / 10.0
                ok = (dist / dt <= TELEPORT_SPEED) if dt > 0 else dist < TELEPORT_SPEED
                if ok:
                    tot["yards"] += dist
                    if cur is not None:
                        cur["yards"] += dist
            last_pos = (m, x, y, t)
            trail.append([int(round((t - t0) / 10.0)), m, x, y])
    return {"segments": segments, "totals": tot, "start": t0 / 10.0, "end": prev_t / 10.0, "trail": trail,
            "duo": duo_seen, "level_from": first_lvl, "level_to": last_lvl}


def build_passes(char_sessions: list[dict]) -> list[dict]:
    """Segmentos de todas las sesiones de un personaje -> pasadas por guía y paso (frontera como en Polestar)."""
    front: dict[str, dict] = {}
    passes: list[dict] = []
    revisits: dict[tuple, dict] = {}

    def finish(f, left):
        p = f["pass"]
        p["left"] = left
        passes.append(p)

    for sess in char_sessions:
        for seg in sess["analysis"]["segments"]:
            g = seg["guide"]
            f = front.get(g)
            if seg.get("end"):
                if f:
                    finish(f, "end")
                    del front[g]
                continue
            if f is None or seg["idx"] > f["idx"]:
                if f:
                    finish(f, seg["reason"])
                p = {"guide": g, "step": seg["step"], "idx": seg["idx"], "char": sess["char"], "start": seg["start"],
                     "time": 0.0, "combat": 0.0, "afk": 0.0, "idle": 0.0, "xp": 0, "yards": 0.0, "deaths": 0,
                     "turnins": 0, "segments": 0, "left": None, "partial": seg["reason"] in ("login", "guide"),
                     "duo": False}
                f = {"idx": seg["idx"], "pass": p}
                front[g] = f
            elif seg["idx"] == f["idx"] and seg["step"] != f["pass"]["step"]:
                # el índice no basta (guía reconstruida): se trata como paso distinto
                finish(f, seg["reason"])
                p = {"guide": g, "step": seg["step"], "idx": seg["idx"], "char": sess["char"], "start": seg["start"],
                     "time": 0.0, "combat": 0.0, "afk": 0.0, "idle": 0.0, "xp": 0, "yards": 0.0, "deaths": 0,
                     "turnins": 0, "segments": 0, "left": None, "partial": False, "duo": False}
                f = {"idx": seg["idx"], "pass": p}
                front[g] = f
            elif seg["idx"] < f["idx"]:
                key = (g, seg["step"])
                r = revisits.setdefault(key, {"guide": g, "step": seg["step"], "visits": 0, "time": 0.0})
                r["visits"] += 1
                r["time"] += seg["time"]
                continue
            p = f["pass"]
            for k in ("time", "combat", "afk", "idle", "xp", "yards", "deaths", "turnins"):
                p[k] += seg[k]
            p["segments"] += 1
            p["duo"] = p["duo"] or bool(seg["duo"])
    for f in front.values():
        p = f["pass"]
        p["left"] = None
        passes.append(p)
    for p in passes:
        p["open"] = p["left"] is None
        p["completed"] = p["left"] in COMPLETED_LEFT
        for k in ("time", "combat", "afk", "idle", "yards"):
            p[k] = round(p[k], 1)
    passes.sort(key=lambda p: (p["start"], p["idx"]))
    return passes, sorted(revisits.values(), key=lambda r: (r["guide"], r["step"] or ""))


def ingest_db(db: dict) -> dict | None:
    """SendaRecorderDB (dict) -> documento de grabación anónimo, o None si no hay sesiones."""
    sessions, stats = build_sessions(db)
    if not sessions:
        return None
    maps = db.get("maps") if isinstance(db.get("maps"), dict) else {}
    for s in sessions:
        s["analysis"] = analyze_session(s, maps)
        s["char"] = _short_hash("senda-char:" + s["char"], 8)
    sessions.sort(key=lambda s: (s["analysis"]["start"], s["char"]))

    by_char: dict[str, list] = {}
    for s in sessions:
        by_char.setdefault(s["char"], []).append(s)
    passes, revisits = [], []
    for char in sorted(by_char):
        p, r = build_passes(by_char[char])
        passes += p
        revisits += r

    used_maps: set[int] = set()
    out_sessions = []
    for s in sessions:
        a = s["analysis"]
        tot = a["totals"]
        for pt in a["trail"]:
            used_maps.add(pt[1])
        sid = _short_hash("senda-session:%s:%d" % (s["char"], int(a["start"] * 10)), 8)
        out_sessions.append({
            "id": sid, "char": s["char"], "start": int(a["start"]), "end": int(a["end"]),
            "active": round(tot["active"], 1), "combat": round(tot["combat"], 1), "afk": round(tot["afk"], 1),
            "idle": round(tot["idle"], 1), "xp": tot["xp"],
            "xp_per_hour": round(tot["xp"] * 3600.0 / tot["active"]) if tot["active"] > 0 else None,
            "yards": round(tot["yards"]), "deaths": tot["deaths"], "accepts": tot["accepts"],
            "turnins": tot["turnins"], "completes": tot["completes"], "duo": a["duo"],
            "level_from": a["level_from"], "level_to": a["level_to"], "trail": a["trail"],
        })
    digest = hashlib.sha256()
    for seq, text in _chunk_items(db):
        digest.update(b"%d\n" % seq)
        digest.update(text.encode("utf-8"))
    first = min(s["start"] for s in out_sessions)
    date = _dt.datetime.fromtimestamp(first, _dt.timezone.utc).strftime("%Y-%m-%d")
    return {
        "schema": SCHEMA, "id": digest.hexdigest()[:10], "date": date, "stats": {**stats, "dropped": int(db.get("dropped") or 0)},
        "maps": {str(m): list(_map_size(maps, m)) for m in sorted(used_maps)},
        "sessions": out_sessions, "passes": passes, "revisits": revisits,
    }


def main(argv=None) -> int:
    setup_stdio()
    ap = argparse.ArgumentParser(description="Calcula tiempos reales por paso desde SendaRecorderDB.")
    ap.add_argument("files", nargs="+", type=Path, help="Senda.lua de WTF/Account/<cuenta>/SavedVariables")
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "data" / "recordings", help="carpeta de salida")
    ap.add_argument("--stdout", action="store_true", help="imprime el JSON en vez de escribir ficheros")
    args = ap.parse_args(argv)
    code = 0
    for f in args.files:
        doc = ingest_db(read_db(f))
        if doc is None:
            print(f"{f}: sin grabaciones (¿está activado /senda grabar on?)", file=sys.stderr)
            code = code or 1
            continue
        text = json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if args.stdout:
            print(text)
            continue
        args.out.mkdir(parents=True, exist_ok=True)
        target = args.out / f"{doc['date']}-{doc['id']}.json"
        target.write_text(text + "\n", encoding="utf-8", newline="\n")
        done = sum(1 for p in doc["passes"] if p["completed"] and not p["partial"])
        print(f"{target}: {len(doc['sessions'])} sesión(es), {len(doc['passes'])} pasadas ({done} completas), "
              f"{doc['stats']['records']} registros, {doc['stats']['bad_records']} descartados")
    return code


if __name__ == "__main__":
    raise SystemExit(main())

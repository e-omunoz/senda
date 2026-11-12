"""Reserva de XP: misiones que no van en la ruta (o que el filtro de eficiencia dejó como opcionales o
descartables) para rellenar cuando te falta nivel. Lo usan tools/build.py y la pestaña «Aparte» del addon.

Dos pasos, como los requisitos de misión (data/prereq.json):

1. ``python tools/build.py --refresh-reserve [--reserve-from RAIZ]`` lee, de la raíz indicada (por defecto el
   repo):
   - data/scores/*.json (tools/route_score.py): decisión keep/optional/drop, XP y minutos estimados por misión,
     de las guías de Senda y, si están en local, de las rutas importadas de Polestar (``ps-*``, ``*-ps``,
     ``*-ps-full``, ignoradas por git);
   - los pasos accept/turnin de esas guías (PNJ y coordenadas comprobadas en la ruta);
   - forever-db (GPL-3; .cache/foreverdb o SENDA_FOREVERDB): nivel mínimo, nivel de la misión, XP completa,
     razas y clases, requisitos, objetivos y, si la guía no lo dice, quién la da y la recoge.
   y guarda la instantánea versionada ``data/reserve.json`` (solo misiones que pueden coger el gnomo brujo, el
   humano mago o el elfo de la noche druida: facción, raza y clase).
2. ``python tools/build.py`` compila esa instantánea en ``addon/Senda/Guides/Reserve.lua`` (una cadena por
   zona; el addon la descodifica bajo demanda). Sin instantánea no se genera nada.

Formato de una línea del Lua (campos separados por «|»):
    misión|nivel mínimo|nivel|XP completa|décimas de minuto|decisión (k/o/d)|máscara de razas|máscara de clases|
    quién la da|quién la recoge|requisitos (todos)|requisitos (uno de)|objetivos|punto de los objetivos
con «quién» = ``n<id>@<mapa>:<x>,<y>`` (PNJ) u ``o<id>@...`` (objeto del mundo), objetivos =
``c<id>x<n>`` (matar), ``i<id>x<n>`` (objeto), ``o<id>x<n>`` (usar objeto), ``t<id>`` (hablar), ``e`` (evento),
separados por comas, y el punto ``<mapa>:<x>,<y>`` (mediana de las apariciones de los objetivos en el mapa más
frecuente) o vacío.
"""
from __future__ import annotations

import json
import statistics
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import GENERATED_HEADER, Paths, lua_string  # noqa: E402

RESERVE_FILE = "reserve.json"
# Los tres personajes de Senda: solo se guarda lo que alguno de ellos puede coger.
CHARACTERS = (("Gnome", "WARLOCK"), ("Human", "MAGE"), ("NightElf", "DRUID"))
FACTION = "Alliance"
# Guías de puntuaciones que se leen: las de Senda y las importadas de Polestar de la Alianza.
SCORE_SKIP_PREFIX = ("ps-horde-",)
DECISION = {"keep": "k", "optional": "o", "drop": "d"}
MAX_DROP_SOURCES = 12  # objetos de botín con más fuentes: sin punto (la mediana no dice nada)


def _is_ps(name: str) -> bool:
    return name.startswith("ps-") or name.endswith("-ps") or name.endswith("-ps-full")


def _guide_steps(guide_dir: Path, shared_dir: Path) -> list[dict]:
    """Pasos de una guía en orden (secciones de guide.toml, también las compartidas)."""
    meta = tomllib.loads((guide_dir / "guide.toml").read_text(encoding="utf-8"))
    out = []
    for sid in meta.get("sections") or []:
        p = shared_dir / f"{sid[7:]}.toml" if sid.startswith("shared:") else guide_dir / f"{sid}.toml"
        if not p.exists():
            continue
        data = tomllib.loads(p.read_text(encoding="utf-8"))
        out.extend(st for st in data.get("step") or [] if isinstance(st, dict))
    return out


def _round(v: float) -> float:
    return round(float(v), 1)


def _who(kind: str, eid: int, at) -> str:
    return f"{kind}{eid}@{int(at[0])}:{_round(at[1])},{_round(at[2])}"


def _first_spawn(db, kind: str, eid: int):
    ent = db.npc(eid) if kind == "n" else db.object(eid)
    if not ent:
        return None
    spawns = [s for s in ent.get("spawns") or [] if s[1] is not None]
    if not spawns:
        return None
    # El mapa con más apariciones; dentro, la primera (las tablas vienen ordenadas).
    maps: dict[int, int] = {}
    for s in spawns:
        maps[s[0]] = maps.get(s[0], 0) + 1
    best = max(maps, key=lambda m: (maps[m], -m))
    return next(s[:3] for s in spawns if s[0] == best)


def _objective_point(db, q: dict, prefer_map: int | None):
    pts = []
    objs = q.get("objectives") or {}
    for o in objs.get("creature", []):
        n = db.npc(o["id"])
        pts += [s for s in (n or {}).get("spawns") or [] if s[1] is not None]
    for o in objs.get("object", []):
        ob = db.object(o["id"])
        pts += [s for s in (ob or {}).get("spawns") or [] if s[1] is not None]
    for o in objs.get("item", []):
        it = db.item(o["id"]) or {}
        npcs, gos = it.get("npcDrops") or [], it.get("objectDrops") or []
        if len(npcs) + len(gos) > MAX_DROP_SOURCES:
            continue
        for nid in npcs:
            pts += [s for s in (db.npc(nid) or {}).get("spawns") or [] if s[1] is not None]
        for oid in gos:
            pts += [s for s in (db.object(oid) or {}).get("spawns") or [] if s[1] is not None]
    if not pts:
        return None
    maps: dict[int, int] = {}
    for s in pts:
        maps[s[0]] = maps.get(s[0], 0) + 1
    m = prefer_map if prefer_map in maps else max(maps, key=lambda k: (maps[k], -k))
    xs = [s[1] for s in pts if s[0] == m]
    ys = [s[2] for s in pts if s[0] == m]
    return [m, statistics.median(xs), statistics.median(ys)]


def _objectives(q: dict) -> str:
    parts = []
    objs = q.get("objectives") or {}
    for kind, letter in (("creature", "c"), ("item", "i"), ("object", "o")):
        for o in objs.get(kind, []):
            if o.get("id"):
                parts.append(f"{letter}{int(o['id'])}x{int(o.get('count') or 1)}")
    for o in objs.get("talk", []):
        if o.get("id"):
            parts.append(f"t{int(o['id'])}")
    if objs.get("event"):
        parts.append("e")
    return ",".join(parts)


def refresh(paths: Paths, src_root: Path | None = None, foreverdb: str | None = None) -> dict:
    """Lee puntuaciones, guías y forever-db y devuelve la instantánea (no escribe)."""
    from foreverdb import ForeverDB  # noqa: E402  (solo al refrescar: necesita la caché local)
    from questiedb.constants import class_allowed, race_allowed  # noqa: E402

    # Las puntuaciones y guías de Senda salen de este repo; las importadas de Polestar (ignoradas por git), de
    # `src_root` (por defecto, también este repo).
    src = Path(src_root).resolve() if src_root else paths.root
    db = ForeverDB.open(foreverdb)

    def files(root: Path, ps: bool):
        d = root / "data" / "scores"
        return sorted(p for p in d.glob("*.json") if p.name != "bands.json" and _is_ps(p.stem) == ps
                      and not p.name.startswith(SCORE_SKIP_PREFIX))

    score_files = [(f, paths.root) for f in files(paths.root, False)] + [(f, src) for f in files(src, True)]
    info: dict[int, dict] = {}
    giver: dict[int, tuple] = {}
    taker: dict[int, tuple] = {}
    used = []
    for f, root in score_files:
        data = json.loads(f.read_text(encoding="utf-8"))
        gid = data.get("guide") or f.stem
        used.append(gid)
        for qs, x in (data.get("quests") or {}).items():
            q = int(qs)
            if q in info:
                # Otra guía de las mismas misiones: el tiempo más corto (otra ruta pasa más cerca).
                if x.get("est_minutes") and x["est_minutes"] < info[q]["est_minutes"]:
                    info[q]["est_minutes"] = x["est_minutes"]
                continue
            info[q] = {"est_minutes": x.get("est_minutes") or 0, "decision": x.get("decision"),
                       "flags": set(x.get("flags") or []), "dungeon": bool(x.get("dungeon")),
                       "unknown": bool(x.get("unknown")), "class_quest": bool(x.get("class_quest")), "guide": gid}
        gdir = root / "data" / "guides" / gid
        if (gdir / "guide.toml").exists():
            for st in _guide_steps(gdir, root / "data" / "shared"):
                q, at, npc = st.get("quest"), st.get("at"), st.get("npc")
                if not isinstance(q, int) or not isinstance(npc, int) or not isinstance(at, list) or len(at) < 3:
                    continue
                if st.get("do") == "accept" and q not in giver:
                    giver[q] = ("n", npc, at)
                elif st.get("do") == "turnin" and q not in taker:
                    taker[q] = ("n", npc, at)

    rows = []
    for q in sorted(info):
        x = info[q]
        fq = db.quest(q)
        if not fq or fq.get("repeatable"):
            continue
        if x["dungeon"] or x["unknown"] or {"dungeon", "group", "raid", "pvp"} & x["flags"]:
            continue
        if not any(race_allowed(fq["races"], r, FACTION) and class_allowed(fq["classes"], c) for r, c in CHARACTERS):
            continue
        xp = int(fq.get("xp") or 0)
        mins = float(x["est_minutes"] or 0)
        if xp <= 0 or mins <= 0:
            continue
        g = giver.get(q)
        if not g:
            for kind, letter in (("npc", "n"), ("object", "o")):
                for eid in fq["starters"].get(kind) or []:
                    at = _first_spawn(db, letter, eid)
                    if at and not g:
                        g = (letter, eid, at)
        t = taker.get(q)
        if not t:
            for kind, letter in (("npc", "n"), ("object", "o")):
                for eid in fq["finishers"].get(kind) or []:
                    at = _first_spawn(db, letter, eid)
                    if at and not t:
                        t = (letter, eid, at)
        if not g or not t:
            continue  # empieza con un objeto del inventario o sin apariciones: no se puede guiar
        pt = _objective_point(db, fq, int(g[2][0]))
        rows.append({
            "quest": q, "reqlevel": int(fq.get("requiredLevel") or 0), "level": int(fq.get("level") or 0),
            "xp": xp, "est_minutes": round(mins, 1), "decision": x["decision"],
            "races": int(fq.get("races") or 0), "classes": int(fq.get("classes") or 0),
            "giver": [g[0], g[1], int(g[2][0]), _round(g[2][1]), _round(g[2][2])],
            "turnin": [t[0], t[1], int(t[2][0]), _round(t[2][1]), _round(t[2][2])],
            "pre_all": sorted(int(p) for p in fq.get("preQuestGroup") or []),
            "pre_any": sorted(int(p) for p in fq.get("preQuestSingle") or []),
            "objectives": _objectives(fq),
            "point": [pt[0], _round(pt[1]), _round(pt[2])] if pt else None,
            "guide": x["guide"],
        })
    return {"_": "Reserva de XP (pestaña «Aparte»): misiones de las puntuaciones de tools/route_score.py con datos de "
                 "forever-db (GPL-3.0) y PNJ y coordenadas de las guías (también las importadas de Polestar, GPL-3.0). "
                 "Ver THIRD_PARTY.md. Se regenera con `python tools/build.py --refresh-reserve`.",
            "forever_db": (db.info or {}).get("version") if hasattr(db, "info") else None,
            "scores": used, "characters": [f"{r} {c}" for r, c in CHARACTERS], "quests": rows}


def write_snapshot(paths: Paths, data: dict) -> None:
    head = {k: v for k, v in data.items() if k != "quests"}
    lines = [json.dumps(head, ensure_ascii=False)[:-1] + ', "quests": [']
    rows = data.get("quests") or []
    for i, r in enumerate(rows):
        lines.append(" " + json.dumps(r, ensure_ascii=False, separators=(",", ":")) + ("," if i < len(rows) - 1 else ""))
    lines.append("]}")
    from common import write_text_lf
    write_text_lf(paths.data / RESERVE_FILE, "\n".join(lines) + "\n")


def read_snapshot(paths: Paths) -> dict | None:
    f = paths.data / RESERVE_FILE
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def _num(v: float) -> str:
    s = f"{float(v):.1f}"
    return s[:-2] if s.endswith(".0") else s


def _who_line(w) -> str:
    return f"{w[0]}{w[1]}@{w[2]}:{_num(w[3])},{_num(w[4])}"


def encode(r: dict) -> str:
    pt = r.get("point")
    fields = [
        str(r["quest"]), str(r["reqlevel"]), str(r["level"]), str(r["xp"]), str(int(round(r["est_minutes"] * 10))),
        DECISION.get(r.get("decision"), "k"), str(r["races"]), str(r["classes"]),
        _who_line(r["giver"]), _who_line(r["turnin"]),
        ",".join(map(str, r.get("pre_all") or [])), ",".join(map(str, r.get("pre_any") or [])),
        r.get("objectives") or "",
        f"{pt[0]}:{_num(pt[1])},{_num(pt[2])}" if pt else "",
    ]
    return "|".join(fields)


def render(paths: Paths) -> str | None:
    """addon/Senda/Guides/Reserve.lua desde data/reserve.json (None si no hay instantánea)."""
    data = read_snapshot(paths)
    if data is None:
        return None
    by_map: dict[int, list[str]] = {}
    for r in sorted(data.get("quests") or [], key=lambda r: r["quest"]):
        by_map.setdefault(int(r["giver"][2]), []).append(encode(r))
    n = sum(len(v) for v in by_map.values())
    head = [f"-- {GENERATED_HEADER}",
            f"-- Fuente: data/{RESERVE_FILE} ({n} misiones en {len(by_map)} zonas; forever-db "
            f"{data.get('forever_db') or '?'}; puntuaciones: {', '.join(data.get('scores') or [])})",
            "local _, Senda = ...",
            "local R = Senda.Reserve",
            "if not R then return end"]
    body = [f"R:RegisterZone({m}, {lua_string(chr(10).join(lines))})" for m, lines in sorted(by_map.items())]
    return "\n".join(head) + "\n\n" + "\n".join(body) + "\n"

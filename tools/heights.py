#!/usr/bin/env python3
"""Alturas (z) de los puntos `at` de las guías, para que la flecha elija el piso bueno (docs/NAV.md, 8.6).

Las coordenadas de mapa (x, y en %) no dicen en qué piso está un punto: en la Mina Abisal el punto de los
kóbolds queda debajo de la colina, en Forjaz bajo la montaña y en Entrañas bajo las Ruinas de Lordaeron.
Senda_Nav guarda varias capas por celda; con la altura del destino escoge la de la mina y no la de la cima.

De dónde sale la altura: de las apariciones de forever-db (`spawn.jsonl`, GPL-3.0, ver THIRD_PARTY.md),
las mismas que dan las coordenadas de las guías (tools/enrich.py, tools/audit_guides.py). Para cada paso
con `at` se buscan los PNJ u objetos que el paso nombra:
  - `npc` del paso;
  - accept / turnin: quien da / recibe la misión (quest_start / quest_end);
  - complete: los objetivos de la misión (`obj` si lo hay): matar (PNJ), objeto del mundo, y quien suelta
    los objetos que pide (item_source);
y se toma la z de la aparición con altura más cercana al punto (en planta) dentro de RADIUS_NPC yardas (PNJ
concretos) o RADIUS_AREA (zonas de objetivos). Sin aparición cerca, el paso no lleva altura y la flecha
usa sus heurísticas (UI/ArrowNav.lua).

Una `z` escrita a mano en el paso (TOML) manda sobre esta instantánea. La instantánea se guarda en
data/heights.json (versionada, para que el resultado no dependa de la caché local) y la lee tools/build.py:

    python tools/build.py --refresh-heights   # relee forever-db (.cache) y reescribe data/heights.json
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from common import Paths, write_text_lf

HEIGHTS_FILE = "heights.json"
RADIUS_NPC = 25.0   # yd: un PNJ concreto está junto a su punto
RADIUS_AREA = 50.0  # yd: el punto de una zona de objetivos queda entre sus apariciones


def _read_jsonl(path: Path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def _pin(root: Path) -> str:
    pf = root / "tools" / "foreverdb" / "PIN"
    if pf.exists():
        m = re.search(r"^version\s*=\s*(\S+)", pf.read_text(encoding="utf-8"), re.MULTILINE)
        return m.group(1) if m else ""
    return ""


def _quests(step: dict) -> list[int]:
    out = [step["quest"]] if isinstance(step.get("quest"), int) else []
    return out + [q for q in (step.get("quests") or []) if isinstance(q, int)]


def point_key(at: list) -> list:
    """[uiMap, x, y] del punto tal y como está en la guía (para saber si la altura sigue valiendo)."""
    return [int(at[0]), float(at[1]), float(at[2])]


def refresh(paths: Paths, db_root: Path | None = None) -> dict:
    """{step_id: [uiMap, x, y, z]} desde forever-db. FileNotFoundError si no hay caché."""
    import validate  # noqa: E402 (tools/)

    db = Path(db_root) if db_root else paths.root / ".cache" / "foreverdb"
    data = db / "data"
    if not (data / "spawn.jsonl").exists():
        raise FileNotFoundError(f"no hay forever-db en {db} (ejecuta `python tools/fetch_foreverdb.py`)")
    frames = {int(r["ui_map"]): r for r in _read_jsonl(data / "ui_map.jsonl")}
    spawns: dict[tuple[str, int], list[tuple[int, float, float, float]]] = {}
    for s in _read_jsonl(data / "spawn.jsonl"):
        if s.get("z") is None:
            continue
        spawns.setdefault((s["kind"], int(s["id"])), []).append((int(s["map"]), float(s["x"]), float(s["y"]), float(s["z"])))
    starts: dict[int, list] = {}
    ends: dict[int, list] = {}
    for r in _read_jsonl(data / "quest_start.jsonl"):
        if r["kind"] in ("npc", "object"):
            starts.setdefault(int(r["quest"]), []).append((r["kind"], int(r["id"])))
    for r in _read_jsonl(data / "quest_end.jsonl"):
        if r["kind"] in ("npc", "object"):
            ends.setdefault(int(r["quest"]), []).append((r["kind"], int(r["id"])))
    drops: dict[int, list] = {}
    for r in _read_jsonl(data / "item_source.jsonl"):
        if r["kind"] in ("npc", "object"):
            drops.setdefault(int(r["item"]), []).append((r["kind"], int(r["id"])))
    objectives: dict[int, list] = {}
    for r in _read_jsonl(data / "quest_objective.jsonl"):
        objectives.setdefault(int(r["quest"]), []).append(r)

    def entities(step: dict) -> tuple[list, float]:
        ents = []
        if isinstance(step.get("npc"), int):
            ents.append(("npc", step["npc"]))
        do = step.get("do")
        qs = _quests(step)
        if do == "accept":
            for q in qs:
                ents += starts.get(q, [])
        elif do == "turnin":
            for q in qs:
                ents += ends.get(q, [])
        if ents:
            return ents, RADIUS_NPC
        if do == "complete":
            for q in qs:
                for o in objectives.get(q, []):
                    if isinstance(step.get("obj"), int) and o.get("n") != step["obj"]:
                        continue
                    k, t = o.get("kind"), o.get("target")
                    if not isinstance(t, int):
                        continue
                    if k in ("kill", "talk"):
                        ents.append(("npc", t))
                    elif k == "object":
                        ents.append(("object", t))
                    elif k == "item":
                        ents += drops.get(t, [])
        return ents, RADIUS_AREA

    ds = validate.collect(paths)
    out: dict[str, list] = {}
    for sec in ds.sections:
        for st in sec.data.get("step") or []:
            at, sid = st.get("at"), st.get("id")
            if not (isinstance(sid, str) and isinstance(at, list) and len(at) >= 3) or "z" in st:
                continue
            f = frames.get(at[0])
            if not f:
                continue
            wx = f["top"] + (f["bottom"] - f["top"]) * at[2] / 100
            wy = f["left"] + (f["right"] - f["left"]) * at[1] / 100
            ents, radius = entities(st)
            best = None
            for e in dict.fromkeys(ents):
                for m, x, y, z in spawns.get(e, []):
                    if m != f["map"]:
                        continue
                    d = math.hypot(x - wx, y - wy)
                    if d <= radius and (best is None or d < best[0]):
                        best = (d, z)
            if best is not None:
                out[sid] = point_key(at) + [round(best[1], 1)]
    return dict(sorted(out.items()))


def read(paths: Paths) -> dict[str, list]:
    f = paths.data / HEIGHTS_FILE
    if not f.exists():
        return {}
    with open(f, encoding="utf-8") as fh:
        return json.load(fh).get("steps", {})


def write(paths: Paths, steps: dict[str, list]) -> None:
    head = {"_": "Altura (z, yardas del mundo) del punto `at` de cada paso, de la aparición más cercana del PNJ u "
                 "objeto que el paso nombra en forever-db (GPL-3.0, ver THIRD_PARTY.md): [uiMap, x, y, z]. Solo vale "
                 "mientras el `at` del paso sea ese punto. La lee tools/build.py (campo `z` del paso); se regenera "
                 "con `python tools/build.py --refresh-heights`. Ver tools/heights.py y docs/NAV.md (8.6).",
            "forever_db": _pin(paths.root)}
    rows = [f'  "{k}": [{v[0]}, {json.dumps(v[1])}, {json.dumps(v[2])}, {json.dumps(v[3])}]' for k, v in steps.items()]
    text = json.dumps(head, ensure_ascii=False)[:-1] + ', "steps": {\n' + ",\n".join(rows) + "\n}}\n"
    write_text_lf(paths.data / HEIGHTS_FILE, text)


def height_for(step: dict, heights: dict[str, list]) -> float | None:
    """La z del paso: la suya (TOML) o la de la instantánea si su `at` sigue siendo el mismo punto."""
    if isinstance(step.get("z"), (int, float)):
        return step["z"]
    at, row = step.get("at"), heights.get(step.get("id"))
    if not (isinstance(at, list) and len(at) >= 3 and row):
        return None
    try:
        if point_key(at) != [int(row[0]), float(row[1]), float(row[2])]:
            return None
    except (TypeError, ValueError, IndexError):
        return None
    return row[3]

#!/usr/bin/env python3
"""Genera data/rares/: raros (rank 4) y raros elite (rank 2) de forever-db con sus apariciones.

    python tools/gen_rares.py [--foreverdb RUTA] [--out data/rares]

Fuente: forever-db (Polestar, GPL-3.0 / CC BY 4.0), tablas ``npc`` (rank, niveles, faction_template),
``spawn`` (yardas del mundo) y ``ui_map`` (marcos). Las yardas se pasan a [uiMapId, x%, y%] con
tools/foreverdb (Frames, adaptado de Polestar lib.ToUiMap). Solo lectura de forever-db; no se escribe
nada fuera de --out. Salidas: rares.json (lista plana), by_zone.json (por zona y banda de nivel),
no_spawns.json (raros sin aparicion conocida) y meta.json (fuente, version, metricas).
Reproducible: mismas entradas, mismos bytes.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from foreverdb.db import Frames, read_jsonl, resolve_foreverdb  # noqa: E402

RANKS = {4: "rare", 2: "rareelite"}
CONTINENTS = {0: "Reinos del Este", 1: "Kalimdor"}
# uiMapId de Forever (mismo reparto que tools/site.py MAP_NAMES). Si falta: "mapa <id>".
UIMAP_NAMES = {
    1411: "Durotar", 1412: "Mulgore", 1413: "Los Baldíos", 1414: "Kalimdor", 1415: "Reinos del Este",
    1416: "Montañas de Alterac", 1417: "Tierras Altas de Arathi", 1418: "Tierras Inhóspitas",
    1419: "Las Tierras Devastadas", 1420: "Claros de Tirisfal", 1421: "Bosque de Argénteos",
    1422: "Tierras de la Peste del Oeste", 1423: "Tierras de la Peste del Este",
    1424: "Laderas de Trabalomas", 1425: "Tierras del Interior", 1426: "Dun Morogh",
    1427: "La Garganta de Fuego", 1428: "Las Estepas Ardientes", 1429: "Bosque de Elwynn",
    1430: "Paso de la Muerte", 1431: "Bosque del Ocaso", 1432: "Loch Modan",
    1433: "Montañas Crestagrana", 1434: "Vega de Tuercespina", 1435: "Pantano de las Penas",
    1436: "Páramos de Poniente", 1437: "Los Humedales", 1438: "Teldrassil", 1439: "Costa Oscura",
    1440: "Vallefresno", 1441: "Las Mil Agujas", 1442: "Sierra Espolón", 1443: "Desolace",
    1444: "Feralas", 1445: "Marjal Revolcafango", 1446: "Tanaris", 1447: "Azshara", 1448: "Frondavil",
    1449: "Cráter de Un'Goro", 1450: "Claro de la Luna", 1451: "Silithus", 1452: "Cuna del Invierno",
    1453: "Ventormenta", 1454: "Orgrimmar", 1455: "Forjaz", 1456: "Cima del Trueno",
    1457: "Darnassus", 1458: "Entrañas",
}
BAND = 10


def band(level: int) -> str:
    lo = max(1, (max(level, 1) - 1) // BAND * BAND + 1)
    return f"{lo}-{lo + BAND - 1}"


def zone_name(ui: int) -> str:
    return UIMAP_NAMES.get(ui, f"mapa {ui}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--foreverdb", default=None)
    ap.add_argument("--out", default=str(ROOT / "data" / "rares"))
    a = ap.parse_args()

    root = resolve_foreverdb(a.foreverdb)
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    data = root / "data"
    frames = Frames(list(read_jsonl(data / "ui_map.jsonl")))

    npcs = {}
    for r in read_jsonl(data / "npc.jsonl"):
        if r.get("rank") in RANKS:
            npcs[int(r["id"])] = r
    raw = defaultdict(list)
    for s in sorted(read_jsonl(data / "spawn.jsonl"), key=lambda r: (r["id"], r["map"], r["n"])):
        if s["kind"] == "npc" and int(s["id"]) in npcs:
            raw[int(s["id"])].append(s)

    rares = []
    for nid in sorted(npcs):
        r = npcs[nid]
        lo, hi = int(r.get("level_min") or 0), int(r.get("level_max") or 0)
        pts, world_maps, unframed = [], set(), 0
        for s in raw.get(nid, []):
            world_maps.add(int(s["map"]))
            hit = frames.to_uimap(s["map"], float(s["x"]), float(s["y"]))
            if hit:
                pts.append([hit[0], round(hit[1], 1), round(hit[2], 1)])
            else:
                unframed += 1
        seen, uniq = set(), []
        for p in pts:
            if tuple(p) not in seen:
                seen.add(tuple(p))
                uniq.append(p)
        zones = Counter(p[0] for p in uniq)
        main_ui = min(zones, key=lambda u: (-zones[u], u)) if zones else None
        cont = next((m for m in sorted(world_maps) if m in CONTINENTS), None)
        rec = {
            "id": nid,
            "name": r.get("name"),
            "rank": RANKS[r["rank"]],
            "level": [lo, hi],
            "faction_template": r.get("faction_template"),
            "map": cont if cont is not None else (sorted(world_maps)[0] if world_maps else None),
            "uimap": main_ui,
            "spawns": uniq,
        }
        if unframed:
            rec["spawns_unframed"] = unframed  # puntos del mundo sin marco de mapa (mazmorras, etc.)
        if r.get("subname"):
            rec["subname"] = r["subname"]
        rares.append(rec)

    with_sp = [x for x in rares if x["spawns"]]
    without = [x for x in rares if not x["spawns"]]
    per_cont = {}
    for key, name in CONTINENTS.items():
        sub = [x for x in rares if x["map"] == key]
        per_cont[name] = {"total": len(sub), "with_spawns": sum(1 for x in sub if x["spawns"])}
    other = [x for x in rares if x["map"] not in CONTINENTS]
    per_cont["Otros mapas (instancias o sin mapa)"] = {
        "total": len(other), "with_spawns": sum(1 for x in other if x["spawns"])}

    by_zone: dict[str, dict] = {}
    for x in with_sp:
        z = by_zone.setdefault(str(x["uimap"]), {"name": zone_name(x["uimap"]), "bands": {}})
        z["bands"].setdefault(band(x["level"][1]), []).append(x["id"])
    for z in by_zone.values():
        z["bands"] = {k: sorted(v) for k, v in sorted(z["bands"].items(), key=lambda kv: int(kv[0].split("-")[0]))}
    by_zone = dict(sorted(by_zone.items(), key=lambda kv: int(kv[0])))

    meta = {
        "dataset": "rares",
        "source": {
            "name": "forever-db (Polestar data for WoW: Forever)",
            "dataset": index.get("dataset"), "version": index.get("version"),
            "clientBuild": index.get("clientBuild"), "producerCommit": index.get("producerCommit"),
            "tables": ["npc", "spawn", "ui_map"],
            "licence": "GPL-3.0-only (tablas) / CC BY 4.0 (capa propia); ver THIRD_PARTY.md",
        },
        "rank_filter": {"4": "rare", "2": "rareelite"},
        "level_band_size": BAND,
        "counts": {
            "total": len(rares),
            "rare": sum(1 for x in rares if x["rank"] == "rare"),
            "rareelite": sum(1 for x in rares if x["rank"] == "rareelite"),
            "with_spawns": len(with_sp),
            "without_spawns": len(without),
            "spawn_points": sum(len(x["spawns"]) for x in rares),
            "zones": len(by_zone),
        },
        "per_continent": per_cont,
        "faction_friendliness": "no disponible: forever-db solo trae faction_template (id de cliente); "
                                "no se inventa amistad por faccion (ver docs/RARES.md)",
    }

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    def dump(name, obj):
        (out / name).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n",
                                encoding="utf-8")

    dump("rares.json", rares)
    dump("by_zone.json", by_zone)
    dump("no_spawns.json", [{"id": x["id"], "name": x["name"], "rank": x["rank"], "level": x["level"],
                              "map": x["map"], "spawns_unframed": x.get("spawns_unframed", 0)} for x in without])
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    c = meta["counts"]
    print(f"raros: {c['total']} (rare {c['rare']}, rareelite {c['rareelite']}); con apariciones {c['with_spawns']}, "
          f"sin {c['without_spawns']}; puntos {c['spawn_points']}; zonas {c['zones']}")
    for k, v in per_cont.items():
        print(f"  {k}: {v['total']} / con apariciones {v['with_spawns']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

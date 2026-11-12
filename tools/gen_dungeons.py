#!/usr/bin/env python3
"""Genera data/dungeons/: diario de mazmorras de WoW: Forever (niveles, entrada, misiones).

Entradas (solo datos abiertos o del cliente, cada resultado dice de dónde sale):
  - forever-db (GPL-3.0 / CC BY 4.0): misiones, PNJ, objetos, objetos de misión, apariciones, marcos de mapa.
    Se lee con --foreverdb, SENDA_FOREVERDB o <repo>/.cache/foreverdb (tools/fetch_foreverdb.py).
  - Tablas del cliente de Forever en CSV (wago.tools, build 1.60.1.70450): Map, LFGDungeons,
    ContentTuning, MapDifficulty, DungeonEncounter, AreaTable. Se leen con --client-tables o
    SENDA_CLIENT_TABLES (carpeta con los .csv). Solo salen hechos derivados, no las tablas.

No usa: QuestieDB, DingDB, AtlasLoot, RareScanner, DungeonJournal, el Codex de Polestar ni mapas de Leffe.

Uso:
    python tools/gen_dungeons.py [--foreverdb DIR] [--client-tables DIR] [--out data/dungeons] [--check]

Salida: data/dungeons/dungeons.json, quests.json, meta.json. Es reproducible: mismas entradas, mismos bytes.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

from foreverdb import resolve_foreverdb  # noqa: E402
from foreverdb.db import Frames, read_jsonl  # noqa: E402
from questiedb.constants import ALLIANCE_MASK, HORDE_MASK  # noqa: E402

SCHEMA = 1
MAX_LEVEL = 60
BUILD_HINT = "1.60.1.70450"

# --------------------------------------------------------------------------------------------
# Reglas curadas (cada una con su motivo)
# --------------------------------------------------------------------------------------------

# Misiones de mazmorra del cliente antiguas se clasifican por "zona o clase" con ids de AreaTable que
# la rebanada de tablas no trae (o que son la zona exterior). Se confirman por el título de las misiones
# (ver docs/DUNGEONS.md, "Zonas heredadas"): 133 Gnomeregan (Rig Wars, Tinkmaster Overspark...),
# 978 Zul'Farrak (Gahz'rilla, Tran'rek...), 1517 Uldaman (Uldaman Reagent Run, Agmond's Fate...),
# 1717 Razorfen Kraul (The Crone of the Kraul...).
LEGACY_SORT_AREAS = {90: [133], 209: [978], 70: [1517], 47: [1717]}

# Zonas compartidas que no se pueden asignar a una sola mazmorra: 25 Montaña Roca Negra
# (Profundidades, Cumbre y Núcleo de Magma). Esas misiones quedan "sin colocar" con sus candidatas.
SHARED_AREAS = {25: [230, 229]}

# Mapas que existen como mazmorra de 5 personas pero no se incluyen (motivo en la salida).
NOT_LEVELING_MAPS = {
    13: "mapa de pruebas", 29: "mapa de pruebas", 44: "Monasterio sin usar (no es la instancia viva)",
    269: "Cavernas del Tiempo: entrada nivel 65, fuera del tope de Forever",
}

# Alias del texto de las notas (forever-db step/mechanic, CC BY 4.0) para colocar misiones que ninguna
# zona coloca. Solo "dentro de X" / "en X" + la palabra mazmorra/jefe/élite/grupo. Los textos que citan
# varias mazmorras de golpe se anotan en todas con via "text" y multi=true.
TEXT_ALIASES = {
    36: [r"Deadmines"], 34: [r"Stockade"], 43: [r"Wailing Caverns"], 33: [r"Shadowfang Keep"],
    48: [r"Blackfathom Deeps"], 90: [r"Gnomeregan"], 47: [r"Razorfen Kraul"], 129: [r"Razorfen Downs"],
    189: [r"Scarlet Monastery"], 70: [r"Uldaman"], 209: [r"Zul'Farrak"], 349: [r"Maraudon"],
    109: [r"Sunken Temple"], 230: [r"Blackrock Depths"], 229: [r"(?:Lower |Upper )?Blackrock Spire"],
    289: [r"Scholomance"], 329: [r"Stratholme"], 429: [r"Dire Maul"], 389: [r"Ragefire Chasm"],
    2959: [r"City of Dalaran", r"Ruins of Dalaran"], 2999: [r"Ruins of Lordaeron"],
    3065: [r"Hall of Thanes"], 2998: [r"Excavation Site"],
}
TEXT_CONTEXT = re.compile(r"\b(inside|within|dungeon|elite|boss|group|end of)\b", re.I)
TEXT_LOC = r"(?:inside|within|in|at the end of|from|of)\s+(?:the\s+)?(?:{names})"


def slug(name: str) -> str:
    s = name.lower().replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def norm(name: str) -> str:
    s = re.sub(r"^the\s+", "", name.strip().lower())
    return re.sub(r"[^a-z0-9]+", "", s)


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def num(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def find_client_tables(arg: str | None) -> Path:
    p = arg or os.environ.get("SENDA_CLIENT_TABLES")
    if not p:
        sys.exit("faltan las tablas del cliente: usa --client-tables DIR o SENDA_CLIENT_TABLES "
                 f"(carpeta con Map.csv, LFGDungeons.csv, ContentTuning.csv, MapDifficulty.csv, DungeonEncounter.csv, "
                 f"AreaTable.csv de wago.tools, build {BUILD_HINT})")
    root = Path(p)
    if not (root / "Map.csv").exists():
        sys.exit(f"no hay Map.csv en {root}")
    return root


# --------------------------------------------------------------------------------------------
# Mazmorras desde el cliente
# --------------------------------------------------------------------------------------------

def build_dungeons(T: Path, frames: Frames):
    maps = {num(r["ID"]): r for r in read_csv(T / "Map.csv")}
    lfg = [r for r in read_csv(T / "LFGDungeons.csv") if num(r["TypeID"]) == 0]
    mdiff = read_csv(T / "MapDifficulty.csv")
    tuning = {num(r["ID"]): r for r in read_csv(T / "ContentTuning.csv")}
    enc = read_csv(T / "DungeonEncounter.csv")
    areas = read_csv(T / "AreaTable.csv")

    entry_level: dict[int, int] = {}
    ct_to_map: dict[int, int] = {}
    for r in mdiff:
        mid = num(r["MapID"])
        m = re.search(r"at least level (\d+)", r.get("Message_lang") or "", re.I)
        if m and mid not in entry_level:
            entry_level[mid] = int(m.group(1))
        ct = num(r["ContentTuningID"])
        if ct and mid in maps:
            ct_to_map.setdefault(ct, mid)

    map_by_name = {norm(r["MapName_lang"]): mid for mid, r in maps.items() if num(r["InstanceType"]) == 1}

    # LFGDungeons -> mapa: primero por ContentTuning compartido con MapDifficulty; si no, por nombre.
    wings: dict[int, list[dict]] = defaultdict(list)
    for r in lfg:
        ct = num(r["ContentTuningID"])
        mid = ct_to_map.get(ct) if ct and ct != 4509 else None
        how = "content-tuning"
        if mid is None or maps[mid]["InstanceType"] != "1":
            mid, how = map_by_name.get(norm(r["Name_lang"])), "name"
        if mid is None or num(maps[mid]["InstanceType"]) != 1:
            continue
        t = tuning.get(ct, {})
        wings[mid].append({"lfg": num(r["ID"]), "name": r["Name_lang"], "faction": num(r["Faction"]),
                           "rec_level": num(t.get("MinLevelSquish")) or None, "matched_by": how})

    out, excluded = [], []
    for mid in sorted(maps):
        m = maps[mid]
        if num(m["InstanceType"]) != 1:
            continue
        name = m["MapName_lang"]
        if mid in NOT_LEVELING_MAPS:
            excluded.append({"map": mid, "name": name, "reason": NOT_LEVELING_MAPS[mid]})
            continue
        if mid not in wings and mid not in entry_level:
            excluded.append({"map": mid, "name": name, "reason": "sin fila en LFGDungeons ni nivel de entrada en MapDifficulty"})
            continue
        if entry_level.get(mid, 0) > MAX_LEVEL:
            excluded.append({"map": mid, "name": name, "reason": "nivel de entrada por encima del tope de Forever"})
            continue
        w = sorted(wings.get(mid, []), key=lambda x: x["lfg"])
        rec = sorted({x["rec_level"] for x in w if x["rec_level"]})
        d = {
            "key": slug(name), "map": mid, "name": name, "directory": m["Directory"],
            "max_players": num(m["MaxPlayers"]) or next((num(r["MaxPlayers"]) for r in mdiff if num(r["MapID"]) == mid and num(r["MaxPlayers"])), None),
            "forever_only": num(maps[mid]["ID"]) >= 2900,
            "levels": {"entry": entry_level.get(mid), "recommended": rec[0] if len(rec) == 1 else (rec or None),
                       "source": "client MapDifficulty message (entry) + LFGDungeons -> ContentTuning MinLevelSquish (recommended)"},
            "lfg_faction": sorted({"A" if x["faction"] == 1 else "H" if x["faction"] == 0 else "AH" for x in w}) or None,
            "wings": [{"lfg": x["lfg"], "name": x["name"], "recommended": x["rec_level"]} for x in w] if len(w) > 1 or (w and norm(w[0]["name"]) != norm(name)) else [],
            "area_ids": sorted(num(a["ID"]) for a in areas if num(a["ContinentID"]) == mid and num(a["ID"]) not in (206, 207, 208, 210, 16113, 16114, 16115, 16116, 16117, 16118, 16119, 16562, 16560) and a["AreaName_lang"] != "***On Map Dungeon***"),
            "encounters": [{"name": e["Name_lang"], "id": num(e["ID"]), "order": num(e["OrderIndex"])}
                           for e in sorted((e for e in enc if num(e["MapID"]) == mid), key=lambda e: (num(e["OrderIndex"]), num(e["ID"])))],
            "match": "lfg+mapdifficulty" if w and mid in entry_level else "lfg" if w else "mapdifficulty",
        }
        if not d["lfg_faction"]:
            d.pop("lfg_faction")
        # Entrada: punto de cadáver del cliente (donde reaparece el fantasma), cerca de la puerta.
        cm, cx, cy = num(m["CorpseMapID"], -1), float(m["Corpse_0"] or 0), float(m["Corpse_1"] or 0)
        if cm >= 0 and (cx or cy):
            hits = frames.all(cm, cx, cy)
            if hits:
                ui, px, py = hits[0]
                area = {f[0]: f[5] for f in frames.by_map[cm]}
                zone_hits = [h for h in hits[1:] if area.get(h[0], 0) <= Frames.CONTINENT]  # continent maps always overlap: not ambiguity
                d["entrance"] = {"uiMapId": ui, "x": round(px, 1), "y": round(py, 1), "world": {"map": cm, "x": round(cx, 1), "y": round(cy, 1)},
                                 "other_frames": [[h[0], round(h[1], 1), round(h[2], 1)] for h in zone_hits[:4]],
                                 "ambiguous_frame": bool(zone_hits),
                                 "source": "client Map CorpseMapID/Corpse_0/Corpse_1 -> forever-db ui_map frame",
                                 "kind": "corpse-point"}
            else:
                d["entrance"] = None
        else:
            d["entrance"] = None
        if d["entrance"] is None:
            d["entrance_status"] = "no client corpse point (Forever-only instance): entrance not derivable from the open sources"
        out.append(d)
    return out, excluded, maps


# --------------------------------------------------------------------------------------------
# Misiones
# --------------------------------------------------------------------------------------------

def faction_of(q: dict) -> str:
    side = q.get("side", 0)
    if side == 1:
        return "A"
    if side == 2:
        return "H"
    races = q.get("races", 0)
    if races:
        if races & ~HORDE_MASK == 0:
            return "H"
        if races & ~ALLIANCE_MASK == 0:
            return "A"
    return "AH"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--foreverdb")
    ap.add_argument("--client-tables")
    ap.add_argument("--out", default=str(REPO / "data" / "dungeons"))
    ap.add_argument("--check", action="store_true", help="no escribe: compara con lo que hay y falla si difiere")
    args = ap.parse_args()

    root = resolve_foreverdb(args.foreverdb)
    D = root / "data"
    T = find_client_tables(args.client_tables)
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    frames = Frames(list(read_jsonl(D / "ui_map.jsonl")))

    dungeons, excluded, maps = build_dungeons(T, frames)
    by_map = {d["map"]: d for d in dungeons}

    quest = {r["id"]: r for r in read_jsonl(D / "quest.jsonl")}
    starts, ends = defaultdict(list), defaultdict(list)
    for r in read_jsonl(D / "quest_start.jsonl"):
        starts[r["quest"]].append(r)
    for r in read_jsonl(D / "quest_end.jsonl"):
        ends[r["quest"]].append(r)
    objs = defaultdict(list)
    for r in read_jsonl(D / "quest_objective.jsonl"):
        objs[r["quest"]].append(r)
    pre = defaultdict(lambda: {"all": [], "any": [], "crumb": []})
    child = defaultdict(set)
    for r in read_jsonl(D / "quest_prereq.jsonl"):
        key = "crumb" if r.get("breadcrumb") else r["mode"]
        pre[r["quest"]][key].append(r["pre"])
        child[r["pre"]].add(r["quest"])
    npc = {r["id"]: r for r in read_jsonl(D / "npc.jsonl")}
    obj = {r["id"]: r for r in read_jsonl(D / "object.jsonl")}
    item = {r["id"]: r for r in read_jsonl(D / "item.jsonl")}
    item_src = defaultdict(list)
    for r in read_jsonl(D / "item_source.jsonl"):
        item_src[r["item"]].append(r)
    spawn_first: dict[tuple, dict] = {}
    spawn_n = Counter()
    for r in read_jsonl(D / "spawn.jsonl"):
        k = (r["kind"], r["id"])
        spawn_n[k] += 1
        if k not in spawn_first:
            spawn_first[k] = r

    def place(kind: str, i: int):
        """(pos [uiMap, x, y] | None, nspawns)."""
        s = spawn_first.get((kind, i))
        if not s:
            return None, 0
        hit = frames.to_uimap(s["map"], float(s["x"]), float(s["y"]))
        return ([hit[0], round(hit[1], 1), round(hit[2], 1)] if hit else None), spawn_n[(kind, i)]

    def entity(kind: str, i: int) -> dict:
        tbl = {"npc": npc, "object": obj, "item": item}[kind]
        name = (tbl.get(i) or {}).get("name")
        e = {"kind": kind, "id": i, "name": name}
        if kind in ("npc", "object"):
            pos, n = place(kind, i)
            e["pos"], e["spawns"] = pos, n
        else:
            srcs = item_src.get(i, [])
            e["dropped_by"] = sorted({(s["kind"], s["id"]) for s in srcs})[:6]
            e["dropped_by"] = [{"kind": k, "id": j, "name": ((npc if k == "npc" else obj).get(j) or {}).get("name"),
                                "spawns": spawn_n.get((k, j), 0)} for k, j in e["dropped_by"]]
        return e

    # ---- zonas -> mazmorra ------------------------------------------------------------------
    area_to_map: dict[int, int] = {}
    area_basis: dict[int, str] = {}
    for d in dungeons:
        for a in d["area_ids"]:
            area_to_map[a] = d["map"]
            area_basis[a] = "client AreaTable (ContinentID = instance map)"
    for mid, al in LEGACY_SORT_AREAS.items():
        if mid in by_map:
            for a in al:
                area_to_map[a] = mid
                area_basis[a] = "legacy quest sort area, confirmed by quest titles"
    # El id de zona de Dire Maul (2557) y Blackrock Spire/Depths (1583/1584) estan en AreaTable con
    # ContinentID de la instancia: ya cubiertos. 1584 = Profundidades, 1583 = Cumbre.
    for a, m in {1584: 230, 1583: 229}.items():
        if m in by_map:
            area_to_map.setdefault(a, m)
            area_basis.setdefault(a, "client AreaTable (Blackrock Depths / Blackrock Spire sub-zone)")
    # Zonas "exterior" que aparecen en AreaTable con ContinentID de otra mazmorra
    area_to_map.pop(1581, None) if 36 not in by_map else area_to_map.setdefault(1581, 36)

    # ---- misiones colocadas -----------------------------------------------------------------
    placed: dict[int, dict[int, dict]] = defaultdict(dict)  # map -> qid -> {scope, via}
    for qid, q in quest.items():
        z = q.get("zone_area")
        if z in area_to_map:
            placed[area_to_map[z]][qid] = {"scope": "zone", "via": f"zone_area {z}: {area_basis[z]}"}

    # texto de notas (forever-db step/mechanic, CC BY 4.0)
    texts = defaultdict(list)
    for tbl in ("step", "mechanic", "note"):
        p = D / f"{tbl}.jsonl"
        if p.exists():
            for r in read_jsonl(p):
                t = r.get("text") or ""
                if t:
                    texts[r["quest"]].append(t)
    text_res = {mid: re.compile(TEXT_LOC.format(names="|".join(a)), re.I) for mid, a in TEXT_ALIASES.items() if mid in by_map}
    zoned = {qid for d in placed.values() for qid in d}

    # Jefes: el nombre de un encuentro del cliente (DungeonEncounter) coincide con un PNJ de forever-db
    # que no tiene aparicion (las instancias no estan en spawn.jsonl). Una mision que mata a ese PNJ, o
    # pide un objeto que ese PNJ suelta, se hace dentro de esa mazmorra.
    boss_map: dict[str, set] = defaultdict(set)
    for d in dungeons:
        for e in d["encounters"]:
            boss_map[norm(e["name"])].add(d["map"])
    boss_npc: dict[int, tuple] = {}
    for nid, n in npc.items():
        ms = boss_map.get(norm(n.get("name") or ""))
        if ms and len(ms) == 1 and not spawn_n.get(("npc", nid)):
            boss_npc[nid] = (next(iter(ms)), n["name"])
    obj_hits: dict[int, dict] = defaultdict(dict)
    for qid, rows in objs.items():
        q = quest.get(qid)
        if not q or q.get("level", 0) > MAX_LEVEL:
            continue
        for r in rows:
            if r["kind"] == "kill" and r.get("target") in boss_npc:
                mid, nm = boss_npc[r["target"]]
                obj_hits[qid].setdefault(mid, f"objective kills {nm}")
            elif r["kind"] == "item":
                # El objeto solo se cuenta si todas sus fuentes (a lo sumo 4) son jefes sin aparicion de la
                # misma mazmorra: un objeto comun (paño, mena) con tablas de botin amplias no cuenta.
                srcs = {(x["kind"], x["id"]) for x in item_src.get(r.get("target"), [])}
                if srcs and len(srcs) <= 4 and all(k == "npc" and i in boss_npc for k, i in srcs):
                    maps_ = {boss_npc[i][0] for _, i in srcs}
                    if len(maps_) == 1:
                        mid = next(iter(maps_))
                        nm = ", ".join(sorted({boss_npc[i][1] for _, i in srcs}))
                        obj_hits[qid].setdefault(mid, f"objective item drops only from {nm}")
    for qid, mids in obj_hits.items():
        for mid, why in sorted(mids.items()):
            if qid not in placed[mid]:
                placed[mid][qid] = {"scope": "objective", "via": why + " (client DungeonEncounter name = forever-db NPC with no spawn)",
                                    "multi": len(mids) > 1}

    zoned = {qid for d in placed.values() for qid in d}
    text_hits: dict[int, set] = defaultdict(set)
    for qid, ts in texts.items():
        q = quest.get(qid)
        if not q or qid in zoned or q.get("level", 0) > MAX_LEVEL:
            continue
        for t in ts:
            if re.search(r"raid", t, re.I) or not TEXT_CONTEXT.search(t):
                continue
            for mid, rx in text_res.items():
                if rx.search(t):
                    text_hits[qid].add(mid)
    ambiguous_text = {}
    for qid, mids in text_hits.items():
        if len(mids) > 2:
            ambiguous_text[qid] = sorted(mids)
            continue
        for mid in sorted(mids):
            placed[mid][qid] = {"scope": "text", "via": "forever-db step/mechanic text names the dungeon", "multi": len(mids) > 1}

    # misiones tipo "Dungeon" (81) que siguen sin mazmorra
    placed_all = {qid for d in placed.values() for qid in d}
    unplaced = []
    for qid, q in sorted(quest.items()):
        if q.get("type") == 81 and qid not in placed_all and q.get("level", 0) <= MAX_LEVEL:
            unplaced.append({"id": qid, "title": q.get("title"), "level": q.get("level"), "zone_area": q.get("zone_area"),
                             "candidates": [by_map[m]["key"] for m in (SHARED_AREAS.get(q.get("zone_area")) or ambiguous_text.get(qid, [])) if m in by_map]})

    # ---- cadenas: antecesoras y sucesoras de las misiones ya colocadas ----------------------
    core_all = {qid for d in placed.values() for qid in d}

    def parents(x):
        p = pre.get(x)
        return (p["all"] + p["any"] + p["crumb"]) if p else []

    def closure(seed: set[int], edges, blocked: set[int], depth: int = 99) -> set[int]:
        seen, frontier = set(), set(seed)
        for _ in range(depth):
            nxt = set()
            for x in frontier:
                for y in edges(x):
                    if y not in seen and y in quest and y not in blocked:
                        seen.add(y)
                        nxt.add(y)
            frontier = nxt
        return seen

    for mid, members in list(placed.items()):
        core = {qid for qid, t in members.items() if not t.get("multi")}
        blocked = core_all - set(members)
        # Antecesoras sin limite (la cadena que lleva a la mazmorra); sucesoras hasta 2 pasos (lo que se
        # abre al entregar), para no arrastrar cadenas de nivel 60 enteras.
        around = (closure(core, parents, blocked) | closure(core, lambda x: child.get(x, ()), blocked, 2)) - set(members)
        for qid in sorted(around):
            q = quest[qid]
            if q.get("level", 0) > MAX_LEVEL or q.get("type") == 62:
                continue
            members[qid] = {"scope": "chain", "via": "prerequisite chain of a quest placed in this dungeon (ancestors, or successors up to 2 steps)"}

    # ---- registro de cada misión ------------------------------------------------------------
    def record(qid: int, tag: dict, d: dict) -> dict:
        q = quest[qid]
        st = [entity(r["kind"], r["id"]) for r in sorted(starts.get(qid, []), key=lambda r: (r["kind"], r["id"]))]
        en = [entity(r["kind"], r["id"]) for r in sorted(ends.get(qid, []), key=lambda r: (r["kind"], r["id"]))]
        inst_own = tag["scope"] == "zone" and q.get("zone_area") in set(d["area_ids"])

        def where(e: dict) -> tuple[str, str]:
            if e["kind"] in ("npc", "object"):
                if e["spawns"] and e.get("pos"):
                    return "outside", "forever-db spawn on a continent map"
                if inst_own:
                    return "inside", "no spawn in forever-db and the quest's zone is the instance's own area"
                return "unknown", "no spawn in forever-db"
            srcs = e["dropped_by"]
            if any(s["spawns"] for s in srcs):
                return "outside", "item dropped by a creature that has a continent spawn"
            if srcs and inst_own:
                return "inside", "item dropped by creatures with no spawn; the quest's zone is the instance's own area"
            return "unknown", "item source not known"

        for e in st + en:
            e["where"], e["basis"] = where(e)
        started_inside = (None if not st else
                          "inside" if all(e["where"] == "inside" for e in st) else
                          "outside" if any(e["where"] == "outside" for e in st) else "unknown")
        o = []
        for r in sorted(objs.get(qid, []), key=lambda r: r["n"]):
            kind = r["kind"]
            tgt = r.get("target")
            tbl = {"kill": npc, "talk": npc, "object": obj, "item": item}.get(kind, {})
            o.append({"kind": kind, "target": tgt, "name": (tbl.get(tgt) or {}).get("name") if tgt else None, "count": r.get("count", 1)})
        p = pre.get(qid, {"all": [], "any": [], "crumb": []})
        rec = {
            "id": qid, "title": q.get("title"), "level": q.get("level"), "min_level": q.get("min_level"),
            "faction": faction_of(q), "scope": tag["scope"], "via": tag["via"],
            "giver": st, "turnin": en, "started": started_inside,
            "requires": {"all": sorted(p["all"]), "any": sorted(p["any"]), "breadcrumb_of": sorted(p["crumb"])},
            "objectives": o,
        }
        if tag.get("multi"):
            rec["multi_dungeon"] = True
        if q.get("classes"):
            rec["classes"] = q["classes"]
        if q.get("races"):
            rec["races"] = q["races"]
        if q.get("type") is not None:
            rec["type"] = q["type"]
        if q.get("xp"):
            rec["xp"] = q["xp"]
        if q.get("repeatable"):
            rec["repeatable"] = True
        if q.get("zone_area") is not None:
            rec["zone_area"] = q["zone_area"]
        return rec

    quests_out: dict[str, list] = {}
    stats = {}
    for d in dungeons:
        members = placed.get(d["map"], {})
        recs = [record(qid, tag, d) for qid, tag in sorted(members.items(), key=lambda kv: (quest[kv[0]].get("level") or 0, kv[0]))]
        quests_out[d["key"]] = recs
        core = [r for r in recs if r["scope"] != "chain"]
        lv = [r["level"] for r in core if r.get("level")]
        ent = [e for r in recs for e in r["giver"]]
        st = {
            "quests": len(recs), "in_dungeon_quests": len(core), "chain_quests": len(recs) - len(core),
            "alliance": sum(1 for r in recs if r["faction"] in ("A", "AH")), "horde": sum(1 for r in recs if r["faction"] in ("H", "AH")),
            "giver_no_spawn": sum(1 for r in recs if any(e["kind"] in ("npc", "object") and not e["spawns"] for e in r["giver"])),
            "giver_missing": sum(1 for r in recs if not r["giver"]),
            "started_inside": sum(1 for r in recs if r["started"] == "inside"),
            "started_outside": sum(1 for r in recs if r["started"] == "outside"),
            "started_unknown": sum(1 for r in recs if r["started"] == "unknown"),
            "quest_level_range": [min(lv), max(lv)] if lv else None,
        }
        d["quest_stats"] = st
        stats[d["key"]] = st
        # intervalo de nivel resumido
        rl = d["levels"]["recommended"]
        d["levels"]["quest_range"] = st["quest_level_range"]
        d["levels"]["range_note"] = ("recommended es un nivel (el cliente no trae rango); quest_range sale de las misiones de la mazmorra"
                                     if rl else "el cliente no trae nivel recomendado; quest_range sale de las misiones")

    # ---- metricas y validaciones ------------------------------------------------------------
    total_q = sum(len(v) for v in quests_out.values())
    uniq_q = len({r["id"] for v in quests_out.values() for r in v})
    no_spawn_ids = sorted({r["id"] for v in quests_out.values() for r in v
                           if any(e["kind"] in ("npc", "object") and not e["spawns"] for e in r["giver"])})
    errors = []
    ids = set(quest)
    for key, recs in quests_out.items():
        for r in recs:
            for k in ("all", "any", "breadcrumb_of"):
                for x in r["requires"][k]:
                    if x not in ids:
                        errors.append(f"{key}:{r['id']} requires unknown quest {x}")
            if r["level"] and r["min_level"] and r["min_level"] > r["level"] + 5:
                errors.append(f"{key}:{r['id']} min_level {r['min_level']} > level {r['level']}")
    ent_ok = sum(1 for d in dungeons if d["entrance"])
    meta = {
        "schema": SCHEMA,
        "generator": "tools/gen_dungeons.py",
        "sources": {
            "forever-db": {"version": index.get("version"), "clientBuild": index.get("clientBuild"), "licence": "GPL-3.0 (tables), CC BY 4.0 (step/mechanic text)",
                           "url": "https://github.com/fitzforge/polestar (folder forever-db)"},
            "client-tables": {"build": BUILD_HINT, "tables": ["Map", "LFGDungeons", "ContentTuning", "MapDifficulty", "DungeonEncounter", "AreaTable"],
                              "origin": "wago.tools CSV exports of the Forever client's DB2 tables (facts only)"},
        },
        "not_used": ["QuestieDB", "DingDB", "AtlasLoot", "RareScanner", "DungeonJournal", "Polestar Codex", "Leffe nav maps", "ForeverLevelingBiS (loot not included)"],
        "metrics": {
            "dungeons": len(dungeons), "excluded_maps": len(excluded), "entrances": ent_ok, "entrances_missing": len(dungeons) - ent_ok,
            "quest_rows": total_q, "quests_unique": uniq_q, "givers_without_spawn_quests": len(no_spawn_ids),
            "type81_unplaced": len(unplaced), "validation_errors": len(errors),
        },
        "per_dungeon": stats,
        "excluded": excluded,
        "unplaced_dungeon_quests": unplaced,
        "givers_without_spawn": no_spawn_ids,
        "validation_errors": errors,
    }
    files = {
        "dungeons.json": {"schema": SCHEMA, "dungeons": dungeons},
        "quests.json": {"schema": SCHEMA, "quests": quests_out},
        "meta.json": meta,
    }
    out = Path(args.out)
    rendered = {n: json.dumps(v, ensure_ascii=False, indent=1, sort_keys=False) + "\n" for n, v in files.items() if n != "quests.json"}
    # quests.json: una mision por linea (compacto y con diffs legibles).
    lines = []
    for key, recs in quests_out.items():
        body = ",\n".join("   " + json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in recs)
        lines.append(f'  {json.dumps(key)}: [\n{body}\n  ]' if recs else f'  {json.dumps(key)}: []')
    rendered["quests.json"] = '{\n "schema": %d,\n "quests": {\n%s\n }\n}\n' % (SCHEMA, ",\n".join(lines))
    if args.check:
        bad = [n for n, s in rendered.items() if not (out / n).exists() or (out / n).read_text(encoding="utf-8") != s]
        print("coincide" if not bad else f"difiere: {', '.join(bad)}")
        return 1 if bad else 0
    out.mkdir(parents=True, exist_ok=True)
    for n, s in rendered.items():
        (out / n).write_text(s, encoding="utf-8", newline="\n")
    print(f"mazmorras: {len(dungeons)} (excluidas {len(excluded)}); entradas {ent_ok}/{len(dungeons)}")
    for d in dungeons:
        s = d["quest_stats"]
        print(f"  {d['key']:28s} map {d['map']:<5} entrada {str(d['levels']['entry']):>4} rec {str(d['levels']['recommended']):>8} "
              f"misiones {s['quests']:3d} (zona/texto {s['in_dungeon_quests']:3d}, cadena {s['chain_quests']:3d}) A {s['alliance']:3d} H {s['horde']:3d} "
              f"sin spawn {s['giver_no_spawn']:3d} dentro {s['started_inside']:3d}")
    print(f"misiones: {total_q} filas, {uniq_q} unicas; giver sin aparicion: {len(no_spawn_ids)}; tipo 81 sin colocar: {len(unplaced)}; errores: {len(errors)}")
    for e in errors[:20]:
        print("  ERROR", e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

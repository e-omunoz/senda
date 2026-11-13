#!/usr/bin/env python3
"""Genera las páginas de recolección y pesca: data/knowledge/general/professions-{herbalism,mining,skinning,fishing}.toml
y data/knowledge/general/gathering-route.toml (qué zona de tu guía te sube cada recolección).

    python tools/gen_gathering.py [--foreverdb RUTA] [--wago RUTA] [--out data/knowledge/general]
    python tools/gen_gathering.py --report [--polestar RUTA]     # tabla para docs/PROFESSIONS.md (no escribe)

Fuentes (todas de solo lectura; nada en bruto se commitea):
  - Cliente de Forever (``tools/fetch_wago.py``, build fijada): ``Lock`` (las habilidades mínimas de los nodos que
    el cliente conoce: se comprueba que cada habilidad de nuestras tablas exista) e ``ItemSparse``/esES (nombres).
  - forever-db (GPL-3, Polestar): ``object``/``spawn``/``npc``/``ui_map``; las yardas pasan a % de mapa con
    tools/foreverdb. Dan la coordenada central de cada zona y la de cada instructor.
  - Polestar (GPL-3, commit de THIRD_PARTY.md): ``tools/gathering/node-abundance.json`` (nodos que mantiene a la vez
    cada zona según las reservas de aparición de la base de datos de Forever: ``up``), ``tools/gathering/beasts.json``
    (bestias desollables por zona; forever-db no trae el tipo de criatura) y las listas de instructores, que están
    en este archivo (TRAINERS), adaptadas de ``forge-data/src/professions/trainers.rs``.
  - Las guías de ``data/guides`` y ``data/shared``: de cada sección, su mapa y los mapas de sus pasos.

Modelo (docs/PROFESSIONS.md, «Recolección»):
  - Un nodo de habilidad mínima ``req`` sube la habilidad siempre mientras ``habilidad < req+25`` (naranja), el
    75 % de las veces hasta ``req+50`` (amarillo), el 25 % hasta ``req+100`` (verde) y nunca después (gris).
    Es la fórmula de Classic (SkillGainChance); Forever no la cambia que se sepa: «sin verificar».
  - Una zona vale, para una habilidad s, W(s) = suma de (nodos a la vez * probabilidad de subida) y se ordena por
    densidad W / área del marco del mapa, exigiendo al menos MIN_W subidas por barrido.
  - Desuello: una bestia de nivel L pide habilidad 1 (L <= 10), (L-10)*10 (11-20) o L*5 (>20).
  - Pesca: cada captura sube la habilidad por debajo de 75; después, una de cada (hab-50)/25.

Reproducible: mismas entradas, mismos bytes.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from common import GLYPH_FALLBACK, Paths, load_toml  # noqa: E402
from foreverdb.db import Frames, read_jsonl, resolve_foreverdb  # noqa: E402
from gen_rares import UIMAP_NAMES  # noqa: E402

GATHER_DIR = ROOT / "tools" / "gathering"
BUILD = "1.60.1.70888"
POLESTAR_COMMIT = "19bd636e7d6f33231770f6029c76d2d4dfc63798"
CHECKED = "2026-11-13"
BAND = 25
MIN_W = 6.0           # subidas por barrido mínimas para listar una zona sin relajar
TOP_ZONES = 4
CLUSTER = 5.0         # lado de la rejilla (en % de mapa) para hallar el punto más denso

# Probabilidad de subida por color (Classic; sin verificar en Forever).
WEIGHT = {"orange": 1.0, "yellow": 0.75, "green": 0.25, "grey": 0.0}

# --------------------------------------------------------------------------- tablas curadas
# nombre del objeto (forever-db / Polestar) -> (habilidad mínima, id del objeto que da, verificado en el cliente)
HERBS = {
    "Peacebloom": (1, 2447), "Silverleaf": (1, 765), "Wilted Peacebloom": (1, 2447), "Stunted Silverleaf": (1, 765),
    "Earthroot": (15, 2449), "Mageroyal": (50, 785), "Briarthorn": (70, 2450), "Stranglekelp": (85, 3820),
    "Bruiseweed": (100, 2453), "Wild Steelbloom": (115, 3355), "Grave Moss": (120, 3369), "Kingsblood": (125, 3356),
    "Liferoot": (150, 3357), "Fadeleaf": (160, 3818), "Goldthorn": (170, 3821), "Khadgar's Whisker": (185, 3358),
    "Wintersbite": (195, 3819), "Firebloom": (205, 4625), "Purple Lotus": (210, 8831), "Arthas' Tears": (220, 8836),
    "Sungrass": (230, 8838), "Blindweed": (235, 8839), "Ghost Mushroom": (245, 8845), "Gromsblood": (250, 8846),
    "Golden Sansam": (260, 13464), "Dreamfoil": (270, 13463), "Mountain Silversage": (280, 13465),
    "Plaguebloom": (285, 13466), "Icecap": (290, 13467), "Black Lotus": (300, 13468),
}
ORES = {
    "Copper Vein": (1, 2770), "Poor Copper Vein": (1, 2770), "Tin Vein": (65, 2771),
    "Incendicite Mineral Vein": (65, 3340), "Silver Vein": (75, 2775), "Lesser Bloodstone Deposit": (75, 4278),
    "Iron Deposit": (125, 2772), "Gold Vein": (155, 2776), "Mithril Deposit": (175, 3858),
    "Truesilver Deposit": (230, 7911), "Dark Iron Deposit": (230, 11370), "Small Thorium Vein": (245, 10620),
    "Rich Thorium Vein": (275, 10620),
}
# Nodos propios de Forever (no salen en el cliente ni en Classic): habilidad 1 por la cerradura del Cobre/Flor de paz.
FOREVER_ONLY = {"Poor Copper Vein", "Wilted Peacebloom", "Stunted Silverleaf"}
LOCK_TYPE = {"herbalism": 2, "mining": 3}

# Zonas abiertas: (nivel mínimo, nivel máximo, bando A/H/AH). Niveles de Classic (tabla de Polestar, tables.js).
ZONES = {
    1429: (1, 10, "A"), 1426: (1, 10, "A"), 1438: (1, 10, "A"), 1411: (1, 10, "H"), 1412: (1, 10, "H"),
    1420: (1, 10, "H"), 2521: (1, 15, "AH"), 1436: (10, 20, "A"), 1432: (10, 20, "A"), 1439: (10, 20, "A"),
    1413: (10, 25, "H"), 1421: (10, 20, "H"), 1442: (15, 27, "AH"), 1431: (18, 30, "A"), 1440: (18, 30, "AH"),
    1433: (15, 25, "A"), 1437: (20, 30, "A"), 1424: (20, 30, "AH"), 1441: (25, 35, "AH"), 1416: (30, 40, "AH"),
    1417: (30, 40, "AH"), 1443: (30, 40, "AH"), 1434: (30, 45, "AH"), 1418: (35, 45, "AH"), 1435: (35, 45, "AH"),
    1445: (35, 45, "AH"), 1444: (40, 50, "AH"), 1446: (40, 50, "AH"), 1425: (40, 50, "AH"), 1427: (43, 50, "AH"),
    1419: (45, 55, "AH"), 1447: (45, 55, "AH"), 1448: (48, 55, "AH"), 1449: (48, 55, "AH"), 1428: (50, 58, "AH"),
    1422: (51, 58, "AH"), 1423: (53, 60, "AH"), 1452: (55, 60, "AH"), 1451: (55, 60, "AH"),
}
EXTRA_NAMES = {2521: "Isla de Zephras"}
ZONE_NAME_FIX = {1427: "La Garganta de Fuego"}

# Pesca: habilidad a partir de la cual el agua no pierde peces (Polestar fishing.js, skill_fishing_base_level de
# Classic; sin verificar en Forever). Solo las zonas que Polestar usa.
FISH_FULL = {
    1429: 25, 1426: 25, 1438: 25, 1411: 25, 1412: 25, 1420: 25,
    1436: 75, 1432: 75, 1439: 75, 1413: 75, 1421: 75,
    1437: 150, 1440: 150, 1442: 150, 1424: 150,
    1434: 225, 1443: 225, 1435: 225, 1444: 300,
}
# Instructores de pesca con la orilla donde empezar (id de PNJ de Polestar fishing.js START_SPOTS).
FISH_SHORES = {1429: 1651, 1426: 1700, 1438: 3607, 1411: 5941, 1412: 5938, 1420: 5690}

RANK_NAMES = ["Aprendiz", "Oficial", "Experto", "Artesano"]
RANK_LEARN_SKILL = [0, 50, 125, 200]
RANK_MAX = [75, 150, 225, 300]
PROFS = ["herbalism", "mining", "skinning", "fishing"]
LABEL = {"herbalism": "Herboristería", "mining": "Minería", "skinning": "Desuello", "fishing": "Pesca"}
SKILL_LINE = {"herbalism": 182, "mining": 186, "skinning": 393, "fishing": 356}
ORDER = {"herbalism": 215, "mining": 216, "skinning": 217, "fishing": 218}

# Cuero que da el desuello, para el icono del tramo.
LEATHER_BY_SKILL = [(75, 2318), (125, 2319), (175, 4234), (225, 4304), (301, 8170)]

# Instructores (Polestar, trainers.rs, listas «train» de Forever): todos enseñan los cuatro rangos de recolección;
# los de pesca, Aprendiz y Oficial. «junior» = solo Aprendiz (zonas de inicio). Alianza, Horda.
TRAINERS = {
    "herbalism": {
        "train": (["Tannysa", "Shylamiir", "Reyna Stonebranch", "Firodren Mooncaller", "Malorne Bladeleaf", "Alma Jainrose",
                   "Kali Healtouch", "Herbalist Pomeroy", "Telurinon Moonshadow", "Cylania Rootstalker",
                   "Brant Jasperbloom", "Flora Silverwind", "Malvor"],
                  ["Jandi", "Komin Winterhoof", "Martha Alliestar", "Faruza", "Aranae Venomblood", "Mishiki", "Angrun",
                   "Ruw", "Flora Silverwind", "Malvor"]),
        "junior": (["Nancy Songflower", "Emrys Flintbeard", "Eleyna Duskbreeze"],
                   ["Zor'la", "Garan Sunstrider", "Florence Nightshade"]),
    },
    "mining": {
        "train": (["Gelman Stonehand", "Geofram Bouldertoe", "Yarr Hammerstone", "Brock Stoneseeker", "Kurdram Stonehammer",
                   "Dank Drizzlecut", "Matt Johnson", "Pikkle"],
                  ["Makaru", "Krunn", "Brek Stonehoof", "Brom Killian", "Johan Focht", "Pikkle"]),
        "junior": (["Kelsey Fargo", "Sally Swiftwrench", "Fanorran Stilloak"], ["Norzsh", "Vartha Rockmane", "Walter Mason"]),
    },
    "skinning": {
        "train": (["Maris Granger", "Helene Peltskinner", "Balthus Stoneflayer", "Radnaal Maneweaver", "Jayla", "Eladriel",
                   "Wilma Ranthal"],
                  ["Thuwd", "Mooranta", "Rand Rhobart", "Killian Hagey", "Yonn Deepcut", "Dranh", "Kulleg Stonehorn", "Malux"]),
        "junior": (["Riley Peltskinner", "Brighid Stormflayer", "Terunne Bearshaper"],
                   ["Kagil", "Nawka Wildsong", "Margaret Weaver"]),
    },
    "fishing": {
        "train": (["Arnold Leland", "Lee Brown", "Grimnur Stonebrand", "Paxton Ganter", "Astaia", "Androl Oakhand",
                   "Warg Deepwater", "Harold Riggs", "Matthew Hooper", "Donald Rabonne", "Brannock", "Myizz Luckycatch"],
                  ["Lumak", "Kah Mistrunner", "Armand Cromwell", "Clyde Kellen", "Lau'Tiki", "Uthan Stillwater", "Lui'Mala",
                   "Kil'Hiwana", "Katoom the Angler", "Myizz Luckycatch"]),
        "book": (["Old Man Heming"], ["Old Man Heming"]),     # Pescador experto (libro), Bahía del Botín
        "quest": (["Nat Pagle"], ["Nat Pagle"]),               # Pescador artesano, Marjal Revolcafango
    },
}


# --------------------------------------------------------------------------- reglas puras
def color(skill: float, req: int) -> str | None:
    """Color de un nodo para una habilidad: None = no se puede recoger (rojo)."""
    if skill < req:
        return None
    if skill < req + 25:
        return "orange"
    if skill < req + 50:
        return "yellow"
    if skill < req + 100:
        return "green"
    return "grey"


def weight(skill: float, req: int) -> float:
    c = color(skill, req)
    return WEIGHT[c] if c else 0.0


def skinning_req(level: float) -> int:
    level = int(round(level))
    if level <= 10:
        return 1
    if level <= 20:
        return (level - 10) * 10
    return level * 5


def catches(lo: int, hi: int) -> float:
    """Capturas esperadas de la habilidad lo a hi (Classic: todas por debajo de 75, después 1 de cada (s-50)/25)."""
    return sum(1.0 if s < 75 else (s - 50) / 25.0 for s in range(lo, hi))


def zone_w(nodes: list, skill: float) -> float:
    return sum(n[2] * weight(skill, n[1]) for n in nodes)


def band_w(nodes: list, lo: int, hi: int) -> float:
    pts = range(lo, hi)
    return sum(zone_w(nodes, s) for s in pts) / max(1, len(pts))


MIN_UP = {"herbalism": 3, "mining": 3, "skinning": 10}  # nodos (o apariciones) para que una clase de nodo cuente
RANK_EXCLUDE = {2521}  # Isla de Zephras: sus datos son apariciones sin reserva (up = spawns), solo para razas nuevas
# Zonas de Forever que la tabla de abundancia no trae (Polestar, mining.guide: Chunk of Amber de Teldrassil, habilidad 1).
EXTRA_ZONES = {
    ("mining", 1438): {"nodes": [[2770, 1, 7]], "pts": [(53.0, 79.3, 1), (44.2, 59.5, 1), (46.3, 51.8, 1), (37.3, 23.4, 1),
                                                         (56.8, 27.8, 1), (56.7, 31.9, 1), (53.0, 50.6, 1)]},
}


def eff_caps(nodes: list, prof: str = "herbalism") -> tuple[int, int]:
    """(hasta qué habilidad rinde bien, hasta cuál sube algo): el final del amarillo y del verde del mejor nodo
    que la zona mantiene en cantidad (MIN_UP)."""
    min_up = MIN_UP.get(prof, 3)
    reqs = [n[1] for n in nodes if n[2] >= min_up] or [n[1] for n in nodes]
    if not reqs:
        return 0, 0
    return min(300, max(reqs) + 50), min(300, max(reqs) + 100)


def level_for_skill(skill: float) -> float:
    return skill / 5.0


def zone_ok(map_id: int, skill_mid: float, faction: str | None = None) -> bool:
    lo, hi, side = ZONES[map_id]
    if faction == "Alliance" and "A" not in side:
        return False
    if faction == "Horde" and "H" not in side:
        return False
    return lo <= level_for_skill(skill_mid) + 8


# --------------------------------------------------------------------------- lectura
def zone_name(ui: int) -> str:
    return ZONE_NAME_FIX.get(ui) or EXTRA_NAMES.get(ui) or UIMAP_NAMES.get(ui, f"mapa {ui}")


def read_csv(path: Path):
    with open(path, encoding="utf-8", newline="") as fh:
        yield from csv.DictReader(fh)


def lock_skills(wago: Path) -> dict[int, set[int]]:
    """Habilidades mínimas que el cliente tiene en ``Lock`` por tipo de cerradura (2 = Herboristería, 3 = Minería)."""
    out: dict[int, set[int]] = defaultdict(set)
    p = wago / "Lock.csv"
    if not p.exists():
        return out
    for r in read_csv(p):
        for i in range(8):
            if r.get(f"Type_{i}") == "2":
                out[int(r[f"_Index_{i}"])].add(int(r[f"Skill_{i}"]))
    return out


def item_names(wago: Path, ids: set[int]) -> dict[int, str]:
    p = wago / "ItemSparse_esES.csv"
    out: dict[int, str] = {}
    if p.exists():
        for r in read_csv(p):
            i = int(r["ID"])
            if i in ids:
                out[i] = r["Display_lang"]
    return out


class Data:
    """Todo lo leído: abundancia, bestias, spawns por zona y mapas de las guías."""

    def __init__(self, foreverdb: Path, wago: Path):
        self.wago = wago
        ab = json.loads((GATHER_DIR / "node-abundance.json").read_text(encoding="utf-8"))
        self.abundance = {int(k): v for k, v in ab["maps"].items()}
        self.beasts = {int(k): v for k, v in json.loads((GATHER_DIR / "beasts.json").read_text(encoding="utf-8")).items()}
        data = foreverdb / "data"
        self.index = json.loads((foreverdb / "index.json").read_text(encoding="utf-8")) if (foreverdb / "index.json").exists() else {}
        frames_rows = list(read_jsonl(data / "ui_map.jsonl"))
        self.frames = Frames(frames_rows)
        self.area = {int(r["ui_map"]): abs((r["right"] - r["left"]) * (r["bottom"] - r["top"])) for r in frames_rows}
        self.npcs = {int(r["id"]): r for r in read_jsonl(data / "npc.jsonl")}
        self.npc_by_name: dict[str, list[int]] = defaultdict(list)
        for i, r in sorted(self.npcs.items()):
            self.npc_by_name[r.get("name", "")].append(i)
        self.obj_by_name: dict[str, set[int]] = defaultdict(set)
        for r in read_jsonl(data / "object.jsonl"):
            if r.get("name"):
                self.obj_by_name[r["name"]].add(int(r["id"]))
        # spawns: solo los que se pueden necesitar (nodos, bestias, instructores)
        want_obj = {i for n in list(HERBS) + list(ORES) for i in self.obj_by_name.get(n, ())}
        beast_names = {n for names in self.beasts.values() for n in names}
        want_npc = {i for n in beast_names for i in self.npc_by_name.get(n, ())}
        trainer_names = {n for t in TRAINERS.values() for lists in t.values() for side in lists for n in side}
        want_npc |= {i for n in trainer_names for i in self.npc_by_name.get(n, ())}
        want_npc |= set(FISH_SHORES.values())
        self.obj_spawns: dict[int, list] = defaultdict(list)
        self.npc_spawns: dict[int, list] = defaultdict(list)
        for s in sorted(read_jsonl(data / "spawn.jsonl"), key=lambda r: (r["kind"], r["id"], r["map"], r["n"])):
            i = int(s["id"])
            if s["kind"] == "object" and i in want_obj:
                tgt = self.obj_spawns
            elif s["kind"] == "npc" and i in want_npc:
                tgt = self.npc_spawns
            else:
                continue
            hit = self.frames.to_uimap(s["map"], float(s["x"]), float(s["y"]))
            if hit:
                tgt[i].append((hit[0], hit[1], hit[2]))


# --------------------------------------------------------------------------- zonas
def densest(points: list[tuple[float, float, float]]) -> tuple[float, float] | None:
    """Punto central del grupo más denso: rejilla de CLUSTER % de lado, bloque 3x3, centroide ponderado."""
    pts = [p for p in points if p[2] > 0]
    if not pts:
        return None
    cells: dict[tuple[int, int], float] = defaultdict(float)
    for x, y, w in pts:
        cells[(int(x // CLUSTER), int(y // CLUSTER))] += w
    best = max(sorted(cells), key=lambda c: sum(cells.get((c[0] + dx, c[1] + dy), 0.0) for dx in (-1, 0, 1) for dy in (-1, 0, 1)))
    sx = sy = sw = 0.0
    for x, y, w in pts:
        if abs(int(x // CLUSTER) - best[0]) <= 1 and abs(int(y // CLUSTER) - best[1]) <= 1:
            sx, sy, sw = sx + x * w, sy + y * w, sw + w
    return round(sx / sw, 1), round(sy / sw, 1)


def _num(v: float):
    v = round(v, 1)
    return int(v) if v == int(v) else v


def gather_zones(d: Data, prof: str) -> dict[int, dict]:
    """{uimap: {nodes: [[item, req, up]], pts: [(x, y, req)], ...}} para herbalism / mining."""
    table = HERBS if prof == "herbalism" else ORES
    out: dict[int, dict] = {}
    for ui, kinds in sorted(d.abundance.items()):
        if ui not in ZONES:
            continue
        nodes, pts = {}, []
        for name, v in kinds.items():
            if name not in table:
                continue
            req, item = table[name]
            key = (item, req)
            nodes[key] = nodes.get(key, 0.0) + float(v["up"])
            for oid in sorted(d.obj_by_name.get(name, ())):
                pts += [(x, y, req) for (m, x, y) in d.obj_spawns.get(oid, ()) if m == ui]
        if nodes:
            out[ui] = {"nodes": [[k[0], k[1], _num(u)] for k, u in sorted(nodes.items(), key=lambda kv: (kv[0][1], kv[0][0]))],
                       "pts": pts}
    return out


def skin_zones(d: Data) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for ui, names in sorted(d.beasts.items()):
        if ui not in ZONES:
            continue
        by_req: Counter = Counter()
        pts = []
        for name in names:
            for nid in d.npc_by_name.get(name, ()):
                r = d.npcs[nid]
                if r.get("rank"):
                    continue
                lvl = (int(r.get("level_min") or 1) + int(r.get("level_max") or 1)) / 2
                req = skinning_req(lvl)
                for (m, x, y) in d.npc_spawns.get(nid, ()):
                    if m == ui:
                        by_req[req] += 1
                        pts.append((x, y, req))
        if by_req:
            out[ui] = {"nodes": [[0, req, n] for req, n in sorted(by_req.items())], "pts": pts}
    return out


def zone_point(z: dict, skill: float | None = None) -> tuple[float, float] | None:
    if skill is None:
        return densest([(x, y, 1.0) for x, y, _ in z["pts"]])
    return densest([(x, y, weight(skill, req)) for x, y, req in z["pts"]])


def rank_zones(d: Data, zones: dict[int, dict], lo: int, hi: int, faction: str | None = None) -> list[dict]:
    """Zonas de la banda [lo, hi) por densidad de subidas; relaja el mínimo si no hay ninguna."""
    mid = (lo + hi - 1) / 2
    rows = []
    for ui, z in zones.items():
        if ui in RANK_EXCLUDE or not zone_ok(ui, mid, faction):
            continue
        w = band_w(z["nodes"], lo, hi)
        if w <= 0:
            continue
        area = d.area.get(ui) or 6e6
        rows.append({"map": ui, "w": w, "density": w / area * 1e6, "zone": z})
    strong = [r for r in rows if r["w"] >= MIN_W]
    pool = strong or sorted(rows, key=lambda r: -r["w"])[:TOP_ZONES]
    pool.sort(key=lambda r: (-r["density"], r["map"]))
    return pool[:TOP_ZONES]


def bands() -> list[tuple[int, int]]:
    return [(1, 25)] + [(a, a + BAND) for a in range(25, 300, BAND)]


def expected_gathers(nodes: list, lo: int, hi: int) -> float:
    """Recogidas esperadas para subir de lo a hi cogiendo solo nodos que aún suben (sin grises ni rojos)."""
    total = 0.0
    for s in range(lo, hi):
        usable = [(n[2], weight(s, n[1])) for n in nodes if weight(s, n[1]) > 0]
        up = sum(u for u, _ in usable)
        if up <= 0:
            continue
        p = sum(u * w for u, w in usable) / up
        total += 1.0 / p
    return total


# --------------------------------------------------------------------------- instructores
def trainer_entries(d: Data, prof: str) -> list[dict]:
    spec = TRAINERS[prof]
    out: list[dict] = []
    seen: set[tuple] = set()
    warnings: list[str] = []

    def add(names_by_side, ranks, label):
        for side_i, side in enumerate(("Alliance", "Horde")):
            for name in names_by_side[side_i]:
                spot = None
                for nid in d.npc_by_name.get(name, ()):
                    sp = d.npc_spawns.get(nid)
                    if sp:
                        # el primer punto en una zona o ciudad conocida
                        spot = sp[0]
                        break
                if not spot:
                    warnings.append(f"{prof}/{side}: {name} sin aparición")
                    continue
                key = (name, tuple(ranks))
                if key in seen:
                    continue
                seen.add(key)
                ui, x, y = spot
                out.append({"prof": prof, "faction": side, "ranks": ranks, "name": name,
                            "at": [ui, round(x, 1), round(y, 1), f"{name} ({zone_name(ui)})"], "label": label})
    if "train" in spec:
        add(spec["train"], RANK_NAMES[:2] if prof == "fishing" else RANK_NAMES, "train")
    if "junior" in spec:
        add(spec["junior"], RANK_NAMES[:1], "junior")
    if "book" in spec:
        add(spec["book"], [RANK_NAMES[2]], "book")
    if "quest" in spec:
        add(spec["quest"], [RANK_NAMES[3]], "quest")
    # los de nombre repetido para ambos bandos (Flora Silverwind, Malvor, Pikkle...): una sola línea sin bando
    by_key: dict[tuple, list[dict]] = defaultdict(list)
    for t in out:
        by_key[(t["name"], tuple(t["ranks"]), tuple(t["at"][:3]))].append(t)
    merged = []
    for k in sorted(by_key, key=lambda k: (k[0], k[1])):
        rows = by_key[k]
        if len(rows) > 1:
            rows[0] = dict(rows[0], faction=None)
        merged.append(rows[0])
    d.warnings = getattr(d, "warnings", []) + warnings
    return merged


# --------------------------------------------------------------------------- guías
def guide_stops(paths: Paths, zone_maps: set[int]) -> list[dict]:
    """Por guía y sección: nivel y mapas con zonas de recolección (por pasos que pasan allí)."""
    stops = []
    for gdir in sorted(p for p in paths.guides.iterdir() if (p / "guide.toml").exists()):
        g = load_toml(gdir / "guide.toml")
        for i, ref in enumerate(g.get("sections", [])):
            if ref.startswith("shared:"):
                f = paths.shared / f"{ref[7:]}.toml"
            else:
                f = gdir / f"{ref}.toml"
            if not f.exists():
                continue
            sec = load_toml(f)
            counts: Counter = Counter()
            for st in sec.get("step", []):
                at = st.get("at")
                if isinstance(at, list) and len(at) >= 3 and at[0] in zone_maps:
                    counts[int(at[0])] += 1
            if sec.get("map") in zone_maps:
                counts[int(sec["map"])] += 1
            maps = [m for m, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])) if c >= 2][:3]
            if not maps and counts:
                maps = [sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]]
            lv = sec.get("levels") or [1, 60]
            if maps:
                stops.append({"guide": g["id"], "section": sec["id"], "levels": [int(lv[0]), int(lv[1])], "maps": maps,
                              "title": sec.get("title", sec["id"])})
    return stops


# --------------------------------------------------------------------------- salida TOML
def q(s: str) -> str:
    for a, b in GLYPH_FALLBACK.items():
        s = s.replace(a, b)
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def arr(vals) -> str:
    out = []
    for v in vals:
        if isinstance(v, str):
            out.append(q(v))
        elif isinstance(v, (list, tuple)):
            out.append(arr(v))
        else:
            out.append(str(v))
    return "[" + ", ".join(out) + "]"


def kv(lines: list[str], key: str, val) -> None:
    if val is None:
        return
    lines.append(f"{key} = {q(val) if isinstance(val, str) else arr(val) if isinstance(val, (list, tuple)) else val}")


def page_header(prof: str, note: str, sources: list[str], title: str) -> list[str]:
    lines = [
        f"# {title} (GENERADO por tools/gen_gathering.py: no editar; se regenera con `python tools/gen_gathering.py`).",
        "# [[route]]: un tramo por banda de 25 de habilidad (prof, from, to, craft = id del objeto que da, name, n = recogidas",
        "#   esperadas, note = mejores zonas). [[zone]]: nodos por zona, nodes = [[objeto, habilidad mínima, nodos a la vez]],",
        "#   at = punto central del grupo más denso. [[bracket]]: mejores zonas por banda, zones = [[mapa, x, y, subidas por barrido]].",
        "# [[trainer]]: instructores por bando con coordenadas.",
        f'id = "general-professions-{prof}"',
        'class = "ANY"',
        'kind = "professions"',
        f"title = {q(title)}",
        f"order = {ORDER[prof]}",
        'status = "unverified"',
        f"sources = {arr(sources)}",
        f'checked = "{CHECKED}"',
        f"note = {q(note)}",
    ]
    return lines


def build_pages(d: Data, paths: Paths) -> dict[str, str]:
    names = item_names(d.wago, {i for t in (HERBS, ORES) for _, i in t.values()} | {i for _, i in LEATHER_BY_SKILL})
    locks = lock_skills(d.wago)
    pages: dict[str, str] = {}
    all_zones: dict[str, dict[int, dict]] = {
        "herbalism": gather_zones(d, "herbalism"),
        "mining": gather_zones(d, "mining"),
        "skinning": skin_zones(d),
    }
    for (p_, ui_), z_ in EXTRA_ZONES.items():
        if ui_ not in all_zones[p_]:
            all_zones[p_][ui_] = z_
    d.zones = all_zones

    def src(extra: list[str]) -> list[str]:
        return ["foreverdb:object,spawn,npc,ui_map", f"wago:Lock@{BUILD}", f"polestar:{POLESTAR_COMMIT[:8]}/gathering",
                *extra]

    notes = {
        "herbalism": "Zonas, bandas y rutas calculadas con las reglas de Classic (naranja < req+25, amarillo < req+50, verde < req+100, gris después) y los nodos que mantiene cada zona a la vez (reservas de aparición de la base de datos de Forever, vía Polestar). Las habilidades mínimas de las hierbas son las de Classic y todas existen en la tabla Lock del cliente de Forever; Marefoil, Demonsage y Loto de la muerte (hierbas nuevas de Forever) no tienen datos y no entran. Wilted Peacebloom y Stunted Silverleaf (zonas de inicio de Forever) se tratan como habilidad 1. Los rangos de Forever no piden nivel de personaje a partir de Aprendiz (listas de instructor capturadas): Oficial se aprende a 50, Experto a 125 y Artesano a 200.",
        "mining": "Zonas, bandas y rutas con las reglas de Classic y los nodos que mantiene cada zona a la vez (reservas de aparición de Forever, vía Polestar). Cobre 1; Estaño e Incendicita 65; Plata y Petrosangre 75; Hierro 125; Oro 155; Mitril 175; Veraplata y Hierro Negro 230; Torio pequeño 245; Torio rico 275; todas esas habilidades existen en la tabla Lock del cliente de Forever. Poor Copper Vein (zonas de inicio de Forever) cuenta como habilidad 1. En Teldrassil Forever usa Chunk of Amber (sin datos de cantidad aquí: Senda no los cuenta). Rangos sin nivel de personaje, como Herboristería. Hace falta un Pico de minero en las bolsas.",
        "skinning": "Bestias desollables por zona de la lista curada de Polestar (forever-db no trae el tipo de criatura), con nivel y apariciones de forever-db. Habilidad exigida por bestia: nivel <= 10: 1; 11-20: (nivel-10)*10; después nivel*5. Mismas probabilidades de subida que la recolección (Classic, sin verificar). Rangos sin nivel de personaje. Necesitas un Cuchillo de desollar en las bolsas.",
    }
    titles = {"herbalism": "Herboristería 1-300", "mining": "Minería 1-300", "skinning": "Desuello 1-300"}
    for prof in ("herbalism", "mining", "skinning"):
        zones = all_zones[prof]
        lines = page_header(prof, notes[prof], src([f"polestar:{POLESTAR_COMMIT[:8]}/node-abundance"]), titles[prof])
        for t in trainer_entries(d, prof):
            lines += ["", "[[trainer]]", f'prof = "{prof}"']
            kv(lines, "faction", t["faction"])
            kv(lines, "ranks", t["ranks"])
            kv(lines, "name", t["name"])
            kv(lines, "at", t["at"])
            if t["label"] == "junior":
                kv(lines, "note", "Instructor de la zona de inicio: solo enseña Aprendiz.")
            lines.append('status = "unverified"')
        # tramos [[route]]
        for lo, hi in bands():
            rows = rank_zones(d, zones, lo, hi)
            if not rows:
                continue
            best = rows[0]
            mid = (lo + hi - 1) / 2
            ranked = sorted(best["zone"]["nodes"], key=lambda n: -n[2] * weight(mid, n[1]))
            main = [n for n in ranked if n[2] * weight(mid, n[1]) > 0][:3]
            if prof == "skinning":
                craft = next(i for lim, i in LEATHER_BY_SKILL if lo < lim)
                label = "Bestias desollables de nivel " + f"{max(1, int(lo / 5))}-{max(2, int(hi / 5) + 2)}"
            else:
                craft = main[0][0]
                label = " y ".join(names.get(n[0], f"#{n[0]}") for n in main[:3]) if main else "?"
            n_exp = expected_gathers(best["zone"]["nodes"], lo, hi)
            zlist = ", ".join(f"{zone_name(r['map'])}" for r in rows[:3])
            lines += ["", "[[route]]", f'prof = "{prof}"', f"from = {lo}", f"to = {hi}", f"craft = {craft}",
                      f"name = {q(label)}", f"n = {int(round(n_exp))}",
                      f"note = {q('Mejores zonas: ' + zlist + '. Naranja = sube siempre; amarillo, casi siempre.')}",
                      'status = "unverified"']
        # [[zone]]
        for ui in sorted(zones):
            z = zones[ui]
            lo_l, hi_l, side = ZONES[ui]
            at = zone_point(z)
            lines += ["", "[[zone]]", f'prof = "{prof}"', f"map = {ui}", f"name = {q(zone_name(ui))}", f'side = "{side}"',
                      f"levels = [{lo_l}, {hi_l}]"]
            if at:
                kv(lines, "at", [ui, at[0], at[1]])
            kv(lines, "nodes", z["nodes"])
        # [[bracket]]
        for lo, hi in bands():
            rows = rank_zones(d, zones, lo, hi)
            zl = []
            for r in rows:
                pt = zone_point(r["zone"], (lo + hi - 1) / 2) or (0, 0)
                zl.append([r["map"], pt[0], pt[1], _num(r["w"])])
            lines += ["", "[[bracket]]", f'prof = "{prof}"', f"from = {lo}", f"to = {hi}"]
            kv(lines, "zones", zl)
        pages[f"professions-{prof}.toml"] = "\n".join(lines) + "\n"
    pages["professions-fishing.toml"] = build_fishing(d)
    return pages


def build_fishing(d: Data) -> str:
    note = ("Pesca (sin verificar en Forever; reglas de Classic como las usa Polestar). Cada captura sube la habilidad por debajo de 75; "
            "después, una de cada (habilidad-50)/25: unas 1.300 capturas hasta 300. Una captura cuenta igual en cualquier agua: lo que cambia "
            "es que el agua dura pierde peces hasta la habilidad `full` de cada zona (base de la zona de Classic + 95). Oficial se aprende con el "
            "instructor a 50 y nivel 10; Experto es un libro (Old Man Heming, Bahía del Botín; habilidad 125); Artesano es la misión de Nat Pagle "
            "(Marjal Revolcafango; habilidad 200). Se necesita una caña de pescar.")
    lines = page_header("fishing", note, ["foreverdb:npc,spawn,ui_map", f"polestar:{POLESTAR_COMMIT[:8]}/fishing"], "Pesca 1-300")
    for t in trainer_entries(d, "fishing"):
        lines += ["", "[[trainer]]", 'prof = "fishing"']
        kv(lines, "faction", t["faction"])
        kv(lines, "ranks", t["ranks"])
        kv(lines, "name", t["name"])
        kv(lines, "at", t["at"])
        if t["label"] == "book":
            kv(lines, "note", "Vende el libro «Pescador experto» (Experto): habilidad 125 y nivel 20 (sin verificar).")
        elif t["label"] == "quest":
            kv(lines, "note", "Misión de Artesano: habilidad 200 (sin verificar).")
        lines.append('status = "unverified"')
    for lo, hi in bands():
        zone_rows = [(ui, f) for ui, f in sorted(FISH_FULL.items()) if f <= lo and zone_ok(ui, (lo + hi - 1) / 2)]
        zone_rows.sort(key=lambda r: (-ZONES[r[0]][0], r[0]))
        names_z = ", ".join(zone_name(u) for u, _ in zone_rows[:3]) or "cualquier orilla"
        c = catches(lo, hi)
        lines += ["", "[[route]]", 'prof = "fishing"', f"from = {lo}", f"to = {hi}", 'craft = 6256',
                  f"name = {q('Pescar en agua que no pierda peces')}", f"n = {int(round(c))}",
                  f"note = {q('Agua sin pérdida de peces: ' + names_z + '. Una captura cuenta igual en cualquier agua.')}",
                  'status = "unverified"']
    for ui in sorted(FISH_FULL):
        lo_l, hi_l, side = ZONES[ui]
        lines += ["", "[[zone]]", 'prof = "fishing"', f"map = {ui}", f"name = {q(zone_name(ui))}", f'side = "{side}"',
                  f"levels = [{lo_l}, {hi_l}]", f"full = {FISH_FULL[ui]}"]
        shore = FISH_SHORES.get(ui)
        if shore and d.npc_spawns.get(shore):
            m, x, y = d.npc_spawns[shore][0]
            kv(lines, "at", [m, round(x, 1), round(y, 1)])
    for lo, hi in bands():
        zl = []
        for ui, f in sorted(FISH_FULL.items()):
            if f <= lo and zone_ok(ui, (lo + hi - 1) / 2):
                shore = FISH_SHORES.get(ui)
                x = y = 0
                if shore and d.npc_spawns.get(shore):
                    _, x, y = d.npc_spawns[shore][0]
                zl.append([ui, round(x, 1), round(y, 1), _num(catches(lo, hi))])
        zl.sort(key=lambda r: (-ZONES[r[0]][0], r[0]))
        lines += ["", "[[bracket]]", 'prof = "fishing"', f"from = {lo}", f"to = {hi}"]
        kv(lines, "zones", zl[:TOP_ZONES])
    return "\n".join(lines) + "\n"


def build_route(stops: list[dict]) -> str:
    lines = [
        "# En qué zona de tu guía recolectas (GENERADO por tools/gen_gathering.py: no editar).",
        "# [[stop]]: guide, section, levels, maps = mapas de la sección con zonas de recolección (los que más pasos tienen).",
        "# Modules/Gathering.lua cruza esto con los nodos de cada zona ([[zone]] de professions-*.toml) y tu habilidad.",
        'id = "general-gathering-route"',
        'class = "ANY"',
        'kind = "gathering_route"',
        'title = "Recolección en tu ruta"',
        "order = 219",
        'status = "unverified"',
        f'sources = ["senda:data/guides", "foreverdb:ui_map", "polestar:{POLESTAR_COMMIT[:8]}/node-abundance"]',
        f'checked = "{CHECKED}"',
        'note = "Calculado a partir de los pasos de cada sección (el mapa de cada paso con coordenadas)."',
    ]
    for s in stops:
        lines += ["", "[[stop]]", f"guide = {q(s['guide'])}", f"section = {q(s['section'])}", f"levels = {arr(s['levels'])}",
                  f"maps = {arr(s['maps'])}"]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- informe
def route_report(d: Data, stops: list[dict], guide: str, prof: str) -> list[dict]:
    """Para tests y docs: por sección de una guía, la habilidad esperada al final y el estado de sus zonas."""
    zones = d.zones[prof]
    rows = []
    for s in stops:
        if s["guide"] != guide:
            continue
        target = min(300, 5 * s["levels"][1])
        info = []
        for m in s["maps"]:
            z = zones.get(m)
            if z:
                info.append({"map": m, "name": zone_name(m), "caps": eff_caps(z["nodes"], prof), "w": zone_w(z["nodes"], target)})
        if info:
            rows.append({"section": s["section"], "levels": s["levels"], "target": target, "zones": info})
    return rows


def generate(foreverdb: Path, wago: Path, paths: Paths | None = None) -> tuple[dict[str, str], Data, list[dict]]:
    paths = paths or Paths()
    d = Data(foreverdb, wago)
    pages = build_pages(d, paths)
    zone_maps = {ui for z in d.zones.values() for ui in z}
    stops = guide_stops(paths, zone_maps)
    pages["gathering-route.toml"] = build_route(stops)
    return pages, d, stops


# --------------------------------------------------------------------------- comparación (docs)
def polestar_nodes(polestar: Path, prof: str, race: str = "NightElf") -> int | None:
    f = polestar / "guides" / "forever" / "professions" / f"{ {'herbalism': 'herbalism', 'mining': 'mining', 'skinning': 'skinning', 'fishing': 'fishing'}[prof] }.guide"
    if not f.exists():
        return None
    text = f.read_text(encoding="utf-8")
    if prof == "fishing":
        m = re.search(r"About ([\d,]+) catches", text)
        return int(m.group(1).replace(",", "")) if m else None
    # «Expect about N nodes» de cada paso que aplica a la raza (sin `only` o con ella en la lista)
    total = 0
    for block in re.split(r"\n(?=step )", text):
        only = re.search(r"^\s+only (.+)$", block, re.M)
        if only and race not in [x.strip() for x in only.group(1).split(",")]:
            continue
        m = re.search(r"Expect about (\d+) ", block)
        if m:
            total += int(m.group(1))
    return total or None


def report(d: Data, stops: list[dict], polestar: Path | None) -> str:
    out = ["| Profesión | Recogidas esperadas (Senda) | Polestar | Antes (Senda) |", "|---|---:|---:|---:|"]
    old = {"herbalism": 315, "mining": None, "skinning": None, "fishing": None}
    for prof in PROFS:
        if prof == "fishing":
            ours = int(round(catches(1, 300)))
        else:
            ours = int(round(sum(expected_gathers(rank_zones(d, d.zones[prof], lo, hi)[0]["zone"]["nodes"], lo, hi)
                                 for lo, hi in bands() if rank_zones(d, d.zones[prof], lo, hi))))
        ps = polestar_nodes(polestar, prof) if polestar else None
        out.append(f"| {LABEL[prof]} | {ours} | {ps if ps else '-'} | {old[prof] if old[prof] else '-'} |")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--foreverdb", default=None)
    ap.add_argument("--wago", default=str(ROOT / ".cache" / "wago"))
    ap.add_argument("--out", default=str(ROOT / "data" / "knowledge" / "general"))
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--polestar", default=None)
    ap.add_argument("--check", action="store_true", help="falla si los archivos de --out no coinciden con lo generado")
    a = ap.parse_args(argv)
    fdb = resolve_foreverdb(a.foreverdb)
    pages, d, stops = generate(fdb, Path(a.wago))
    if a.report:
        print(report(d, stops, Path(a.polestar) if a.polestar else None))
        for prof in ("herbalism", "mining", "skinning"):
            print(f"\n## {prof}")
            for g in ("nightelf-druid", "human-mage", "gnome-warlock"):
                for r in route_report(d, stops, g, prof):
                    print(g, r["section"], r["levels"], "hab", r["target"],
                          "; ".join(f"{z['name']} {z['caps']}" for z in r["zones"]))
        return 0
    out = Path(a.out)
    bad = 0
    for name, text in sorted(pages.items()):
        p = out / name
        if a.check:
            if not p.exists() or p.read_text(encoding="utf-8") != text:
                print(f"desactualizado: {p}")
                bad += 1
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print(f"{p.name}: {len(text) // 1024} KB")
    for w in getattr(d, "warnings", []):
        print("aviso:", w, file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

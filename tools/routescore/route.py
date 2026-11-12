"""Puntuación de las misiones de una guía de Senda: coste (tiempo) frente a beneficio (XP).

Fuera del juego, en Python, al compilar. Lee las guías TOML (sin escribirlas), forever-db (a través de
tools/foreverdb, solo lectura) y los hechos de viaje de Polestar (travel_facts.json). El modelo está en
model.py; la explicación y las cifras, en docs/EFFICIENCY.md.
"""
from __future__ import annotations

import heapq
import json
import math
import re
import tomllib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import model as M

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TRAVEL_FACTS = HERE / "travel_facts.json"

#: pasos a menos de esto de la primera de una parada forman la misma parada (yardas)
STOP_RADIUS = 40.0
#: ESTIMACIÓN: segundos de diálogo por aceptar o entregar
EST_DIALOG_SECONDS = 5.0
#: dos objetivos de misiones distintas sobre el mismo enemigo se hacen a la vez si sus pasos están a
#: menos de estas posiciones de ruta y dentro del área del objetivo
OVERLAP_STEPS = 8

FACTION_MASK = {"Alliance": 1, "Horde": 2}
#: un objeto que no es de misión y que sueltan más de estos enemigos es botín común (tela, carne...)
GENERIC_DROPPERS = 25
#: ids de sección de clase (mago, druida, brujo, guerrero, paladín, cazador, pícaro, sacerdote, chamán)
CLASS_SECTION_RE = re.compile(r"^(mg|dr|wl|wr|pa|hu|ro|pr|sh)-")


# --------------------------------------------------------------------------------------------
# Datos del mundo
# --------------------------------------------------------------------------------------------

class World:
    """forever-db + marcos de mapa + hechos de viaje, con las consultas que necesita el modelo."""

    def __init__(self, db, root: Path, travel: dict | None = None):
        self.db = db
        self.root = Path(root)
        self.frames: dict[int, tuple] = {}
        for r in _jsonl(self.root / "data" / "ui_map.jsonl"):
            self.frames[int(r["ui_map"])] = (int(r["map"]), float(r["left"]), float(r["right"]),
                                             float(r["top"]), float(r["bottom"]))
        self.chance: dict[int, list] = defaultdict(list)  # item -> [(kind, id, chance|None)]
        for r in _jsonl(self.root / "data" / "item_source.jsonl"):
            self.chance[int(r["item"])].append((r["kind"], int(r["id"]), r.get("chance")))
        self.mechanics: dict[int, set] = defaultdict(set)
        p = self.root / "data" / "mechanic.jsonl"
        if p.exists():
            for r in _jsonl(p):
                self.mechanics[int(r["quest"])].add(r["kind"])
        self.travel = travel if travel is not None else json.loads(TRAVEL_FACTS.read_text(encoding="utf-8"))

    # -- coordenadas -------------------------------------------------------------------------
    def to_world(self, at) -> tuple | None:
        """[uiMap, x%, y%] -> (map, wx, wy) en yardas de mundo."""
        if not at or len(at) < 3:
            return None
        f = self.frames.get(int(at[0]))
        if not f:
            return None
        m, left, right, top, bottom = f
        return (m, top + float(at[2]) / 100 * (bottom - top), left + float(at[1]) / 100 * (right - left))

    def points(self, kind: str, eid: int) -> list[tuple]:
        ent = self.db.npc(eid) if kind == "npc" else self.db.object(eid)
        if not ent:
            return []
        return [(int(p[0]), float(p[1]), float(p[2])) for p in ent.get("world") or []]


def _jsonl(path: Path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def dist(a, b) -> float:
    if a is None or b is None or a[0] != b[0]:
        return math.inf
    return math.hypot(a[1] - b[1], a[2] - b[2])


# --------------------------------------------------------------------------------------------
# Viaje
# --------------------------------------------------------------------------------------------

class Travel:
    """Andar (línea recta x desvío), vuelos (Dijkstra sobre los vuelos directos) y transportes."""

    def __init__(self, facts: dict, faction: str, cls: str | None):
        mask = FACTION_MASK.get(faction, 3)
        self.nodes = {n["id"]: n for n in facts["taxi"]
                      if n["faction"] & mask and (not n.get("class") or n.get("class") == cls)}
        self.edges: dict[int, list] = defaultdict(list)
        for a, b, yards in facts["flights"]:
            if a in self.nodes and b in self.nodes:
                self.edges[a].append((b, yards / M.FLIGHT_SPEED + M.FLIGHT_STOP))
        self.links = []  # (from pos, to pos, seconds) de barcos, zepelines, tranvía y portales
        for t in facts["transports"]:
            if not t["faction"] & mask:
                continue
            a = (t["a"]["map"], t["a"]["wx"], t["a"]["wy"])
            b = (t["b"]["map"], t["b"]["wx"], t["b"]["wy"])
            self.links.append((a, b, t["waitA"] / 2 + t["ab"], t["id"]))
            self.links.append((b, a, t["waitB"] / 2 + t["ba"], t["id"]))
        for p in facts.get("portals", []):
            self.links.append(((p["a"]["map"], p["a"]["wx"], p["a"]["wy"]),
                               (p["b"]["map"], p["b"]["wx"], p["b"]["wy"]), p["seconds"], p["id"]))
        self.cls = cls
        self._cache: dict = {}

    def node_pos(self, nid):
        n = self.nodes[nid]
        return (n["map"], n["wx"], n["wy"])

    def nearest_node(self, pos):
        key = ("n", pos)
        if key in self._cache:
            return self._cache[key]
        best = None
        for nid in self.nodes:
            d = dist(pos, self.node_pos(nid))
            if d < math.inf and (best is None or d < best[0]):
                best = (d, nid)
        self._cache[key] = best[1] if best else None
        return self._cache[key]

    def node_named(self, name: str | None):
        if not name:
            return None
        key = name.lower().split(",")[0].strip()
        for nid, n in sorted(self.nodes.items()):
            if n["name"].lower().split(",")[0].strip() == key:
                return nid
        for nid, n in sorted(self.nodes.items()):
            if key in n["name"].lower():
                return nid
        return None

    def flight_seconds(self, a: int, b: int) -> float | None:
        if a == b:
            return 0.0
        key = ("f", a, b)
        if key in self._cache:
            return self._cache[key]
        best = {a: 0.0}
        heap = [(0.0, a)]
        res = None
        while heap:
            d, u = heapq.heappop(heap)
            if u == b:
                res = d
                break
            if d > best.get(u, math.inf):
                continue
            for v, w in self.edges.get(u, ()):
                nd = d + w
                if nd < best.get(v, math.inf):
                    best[v] = nd
                    heapq.heappush(heap, (nd, v))
        self._cache[key] = res
        return res

    #: un tramo más largo que esto (yardas) prueba también el vuelo
    TAXI_MIN_YARDS = 800.0

    def same_map(self, a, b, level: int) -> tuple[float, str]:
        """Andar, o andar hasta el maestro de vuelo más cercano, volar y andar desde el del destino.

        Supone conocidos todos los vuelos de la facción (cota optimista: la ruta real puede no tenerlos).
        """
        d = dist(a, b)
        walk = M.walk_seconds(d, level, self.cls)
        if d < self.TAXI_MIN_YARDS:
            return walk, "walk"
        na, nb = self.nearest_node(a), self.nearest_node(b)
        if na is None or nb is None or na == nb:
            return walk, "walk"
        f = self.flight_seconds(na, nb)
        if f is None:
            return walk, "walk"
        t = (M.walk_seconds(dist(a, self.node_pos(na)), level, self.cls) + f
             + M.walk_seconds(dist(self.node_pos(nb), b), level, self.cls))
        return (t, "taxi") if t < walk else (walk, "walk")

    def leg(self, a, b, level: int) -> tuple[float, str]:
        """Segundos de a a b (andando, en vuelo o con un transporte si cambian de continente) -> (s, modo)."""
        if a is None or b is None:
            return 0.0, "unknown"
        key = (a, b, level)
        if key in self._cache:
            return self._cache[key]
        if a[0] == b[0]:
            res = self.same_map(a, b, level)
        else:
            best = None
            for s, e, secs, tid in self.links:
                if s[0] == a[0] and e[0] == b[0]:
                    t = self.same_map(a, s, level)[0] + secs + self.same_map(e, b, level)[0]
                    if best is None or t < best[0]:
                        best = (t, tid)
            res = best if best else (0.0, "unknown")
        self._cache[key] = res
        return res


# --------------------------------------------------------------------------------------------
# Guía
# --------------------------------------------------------------------------------------------

@dataclass
class Step:
    idx: int
    raw: dict
    section: str
    level: int
    arrive: tuple | None = None
    leave: tuple | None = None
    action_s: float = 0.0
    travel_s: float = 0.0          # viaje que le toca (repartido por parada)
    leg_s: float = 0.0             # tramo completo que llega a su parada
    mode: str = ""
    class_section: bool = False    # sección de clase (su `if.class` o un id mg-/dr-/wl-...)

    @property
    def id(self):
        return self.raw.get("id")

    @property
    def do(self):
        return self.raw.get("do")

    @property
    def quest(self):
        q = self.raw.get("quest")
        return int(q) if q else None


def load_guide(guide_dir: Path, shared_dir: Path) -> tuple[dict, list[tuple[str, dict]]]:
    meta = tomllib.loads((guide_dir / "guide.toml").read_text(encoding="utf-8"))
    sections = []
    for name in meta.get("sections", []):
        path = shared_dir / f"{name[7:]}.toml" if name.startswith("shared:") else guide_dir / f"{name}.toml"
        sections.append((name, tomllib.loads(path.read_text(encoding="utf-8"))))
    return meta, sections


def _allowed(cond: dict | None, meta: dict, level: int) -> bool:
    if not cond:
        return True
    if "class" in cond and not set(cond["class"]) & set(meta.get("classes", [])):
        return False
    if "race" in cond and not set(cond["race"]) & set(meta.get("races", [])):
        return False
    if "faction" in cond and cond["faction"] != meta.get("faction"):
        return False
    if "prof" in cond:
        return False  # pasos de profesión: fuera de la ruta base
    if "maxlevel" in cond and level > int(cond["maxlevel"]):
        return False
    return True


def flatten(meta: dict, sections: list) -> list[Step]:
    steps: list[Step] = []
    floor = 1
    prev_hi = int(meta.get("levels", [1, 60])[0])
    for name, sec in sections:
        lv = sec.get("levels") or [prev_hi, prev_hi]
        lo, hi = int(lv[0]), int(lv[1])
        prev_hi = hi
        raw = sec.get("step", [])
        n = max(len(raw) - 1, 1)
        class_sec = bool((sec.get("if") or {}).get("class")) or bool(CLASS_SECTION_RE.match(str(sec.get("id", ""))))
        for i, r in enumerate(raw):
            level = max(floor, int(round(lo + (hi - lo) * i / n)))
            if not _allowed(r.get("if"), meta, level):
                continue
            steps.append(Step(len(steps), r, name, level, class_section=class_sec))
            if r.get("do") == "level" and r.get("level"):
                floor = max(floor, int(r["level"]))
    return steps


# --------------------------------------------------------------------------------------------
# Posiciones, paradas y viaje repartido
# --------------------------------------------------------------------------------------------

def place_steps(steps: list[Step], world: World, travel: Travel) -> dict:
    """Rellena arrive/leave/action_s y reparte el viaje por paradas. Devuelve totales de la guía."""
    hearth = None
    positional = []
    for s in steps:
        r = s.raw
        if s.do == "hearth":
            s.arrive = None
            s.leave = hearth
            s.action_s = M.HEARTH_SECONDS
            positional.append(s)
            continue
        s.arrive = world.to_world(r.get("at"))
        s.leave = s.arrive
        if s.do == "sethearth" and s.arrive:
            hearth = s.arrive
        if s.arrive:
            positional.append(s)
    # destinos de vuelo (necesitan el paso siguiente)
    for i, s in enumerate(positional):
        if s.do != "fly" or not s.arrive:
            continue
        origin = travel.nearest_node(s.arrive)
        nxt = next((p.arrive for p in positional[i + 1:] if p.arrive), None)
        dest = travel.node_named(s.raw.get("node"))
        if dest is None and nxt is not None:
            dest = travel.nearest_node(nxt)
        if origin is None or dest is None:
            s.mode = "fly?"
            continue
        secs = travel.flight_seconds(origin, dest)
        if secs is None:  # nodos sin vuelo conocido: recta a 30 yd/s
            d = dist(travel.node_pos(origin), travel.node_pos(dest))
            secs = d / M.FLIGHT_SPEED if d < math.inf else 0.0
            s.mode = "fly~"
        else:
            s.mode = "fly"
        s.action_s = secs
        s.leave = travel.node_pos(dest)

    totals = defaultdict(float)
    cur = None
    cur_step: Step | None = None
    pending = 0.0
    stop: list[Step] = []
    stop_leg = 0.0

    def close():
        nonlocal stop, stop_leg
        if stop:
            share = stop_leg / len(stop)
            for p in stop:
                p.travel_s = share
                p.leg_s = stop_leg
        stop, stop_leg = [], 0.0

    def overhead_leg(prev: Step | None, s: Step, mode: str) -> bool:
        """Tramos de ruta que no son de ninguna misión: cambio de zona o de sección, transportes y el
        primer tramo tras un vuelo o la piedra."""
        if prev is None or mode not in ("walk", "unknown"):
            return True
        if prev.do in ("fly", "hearth") or prev.section != s.section:
            return True
        za, zb = (prev.raw.get("at") or [None])[0], (s.raw.get("at") or [None])[0]
        return za is not None and zb is not None and za != zb

    for s in positional:
        if s.do == "hearth":
            close()
            totals["hearth"] += s.action_s
            totals["overhead_travel"] += pending
            pending = 0.0
            cur = s.leave if s.leave else cur
            cur_step = s
            continue
        secs, mode = travel.leg(cur, s.arrive, s.level)
        if mode == "unknown" and cur is not None:
            totals["unknown_legs"] += 1
        if not s.mode:
            s.mode = mode
        if overhead_leg(cur_step, s, mode):
            totals["overhead_travel"] += secs + pending
            secs, pending = 0.0, 0.0
            close()
        if s.do == "goto":
            close()
            pending += secs
            cur, cur_step = s.leave, s
            continue
        if stop and dist(stop[0].arrive, s.arrive) <= STOP_RADIUS:
            stop.append(s)
            stop_leg += secs
        else:
            close()
            stop = [s]
            stop_leg = secs + pending
            pending = 0.0
        if s.do == "fly":
            totals["flights"] += s.action_s
        cur, cur_step = s.leave, s
    close()
    totals["overhead_travel"] += pending
    return dict(totals)


def marginal_travel(steps: list[Step], qid: int, travel: Travel) -> float:
    """Segundos de viaje que se ahorran quitando de la ruta los pasos de esta misión."""
    pos = [s for s in steps if s.arrive is not None or s.do == "hearth"]
    saved = 0.0
    i = 0
    while i < len(pos):
        if pos[i].quest == qid and pos[i].do in ("accept", "complete", "turnin", "loot", "use"):
            j = i
            while j + 1 < len(pos) and pos[j + 1].quest == qid:
                j += 1
            prev = pos[i - 1].leave if i > 0 else None
            nxt = pos[j + 1].arrive if j + 1 < len(pos) else None
            lvl = pos[i].level
            old = travel.leg(prev, pos[i].arrive, lvl)[0]
            for k in range(i, j):
                old += travel.leg(pos[k].leave, pos[k + 1].arrive, lvl)[0]
            old += travel.leg(pos[j].leave, nxt, lvl)[0] if nxt else 0.0
            new = travel.leg(prev, nxt, lvl)[0] if nxt else 0.0
            saved += max(0.0, old - new)
            i = j + 1
        else:
            i += 1
    return saved


# --------------------------------------------------------------------------------------------
# Objetivos
# --------------------------------------------------------------------------------------------

@dataclass
class Demand:
    """Muertes (o clics) que pide un objetivo sobre un grupo de enemigos u objetos."""
    quest: int
    kind: str                 # npc | object
    ids: tuple
    count: float              # muertes o clics necesarios
    n_spawns: int
    radius: float
    per_unit: float           # segundos por muerte/clic (sin moverse)
    xp_each: float
    center: tuple | None
    idx: int
    level: int
    estimated: list = field(default_factory=list)
    share: float = 1.0        # parte que se carga a esta misión (objetivos solapados)


def _area(points: list[tuple], center: tuple | None) -> tuple[list, tuple | None, float]:
    """Apariciones dentro del área del objetivo -> (puntos, centro usado, yardas extra hasta el área)."""
    if not points:
        return [], center, 0.0
    if center is not None:
        near = [p for p in points if dist(p, center) <= M.AREA_RADIUS]
        if near:
            return near, center, 0.0
        same = [p for p in points if p[0] == center[0]]
        if same:
            c = min(same, key=lambda p: dist(p, center))
            return [p for p in same if dist(p, c) <= M.AREA_RADIUS], c, dist(c, center)
    # sin centro: la celda (de lado AREA_RADIUS) con más apariciones, y su centroide
    cells = defaultdict(list)
    for p in points:
        cells[(p[0], int(p[1] // M.AREA_RADIUS), int(p[2] // M.AREA_RADIUS))].append(p)
    cell = max(cells.values(), key=len)
    c = (cell[0][0], sum(p[1] for p in cell) / len(cell), sum(p[2] for p in cell) / len(cell))
    return [p for p in points if dist(p, c) <= M.AREA_RADIUS], c, 0.0


def _radius(points, center) -> float:
    if not points or center is None:
        return M.AREA_RADIUS
    return max(30.0, max(dist(p, center) for p in points))


def objective_demands(world: World, qid: int, center: tuple | None, idx: int,
                      level: int, escort_step: bool = False) -> tuple[list[Demand], float, list]:
    """-> (demandas de muertes/clics, segundos fijos, banderas)."""
    q = world.db.quest(qid) or {}
    objs = q.get("objectives") or {}
    mech = world.mechanics.get(qid, set())
    demands: list[Demand] = []
    fixed = 0.0
    flags: list[str] = []
    extra_yards = 0.0

    def grow(pts, area, c, need):
        """Si hacen falta más que las apariciones del área, se amplía el área alrededor del mismo centro."""
        r = M.AREA_RADIUS
        for r2 in M.AREA_GROWTH:
            if len(area) >= need:
                break
            wider = [p for p in pts if dist(p, c) <= r2]
            if len(wider) > len(area):
                area, r = wider, r2
        return area

    def npc_demand(ids, count, chances=None, est=None):
        nonlocal extra_yards
        pts, per, info = [], {}, {}
        for nid in ids:
            n = world.db.npc(nid) or {}
            ps = world.points("npc", nid)
            per[nid] = set(ps)
            pts += ps
            info[nid] = n
        area, c, extra = _area(pts, center)
        if not area:
            return None
        extra_yards = max(extra_yards, extra)

        def used_in(area):
            a = set(area)
            return {nid: len(ps & a) for nid, ps in per.items() if ps & a}

        used = used_in(area)
        need = count
        p = 1.0
        if chances is not None:
            # probabilidad media ponderada por apariciones dentro del área
            num = den = 0.0
            for nid, k in used.items():
                ch = chances.get(nid)
                if ch is None:
                    continue
                num += k * ch / 100
                den += k
            if den == 0:
                return "unknown"
            p = min(1.0, num / den)
            if p <= 0:
                return "unknown"
            need = count / p
        area = grow(pts, area, c, need)
        used = used_in(area)
        # tiempo y XP por muerte, ponderados por las apariciones de cada enemigo en el área
        tot = sum(used.values())
        per_kill = xp_each = 0.0
        for nid, k in used.items():
            n = info[nid]
            mlv = round((n["minLevel"] + n["maxLevel"]) / 2) if n.get("minLevel") else level
            rank = int(n.get("rank") or 0)
            per_kill += k / tot * M.kill_seconds(level, mlv, rank)
            xp_each += k / tot * M.mob_xp(level, mlv, rank in (1, 2))
        return Demand(qid, "npc", tuple(sorted(used)), need, len(area), _radius(area, c),
                      per_kill, xp_each, c, idx, level, list(est or []))

    def object_demand(ids, count, chances=None):
        nonlocal extra_yards
        pts = []
        for oid in ids:
            pts += world.points("object", oid)
        area, c, extra = _area(pts, center)
        if not area:
            return None
        extra_yards = max(extra_yards, extra)
        est = []
        p = 1.0
        if chances:
            known = [v for v in chances.values() if v is not None]
            if known:
                p = min(1.0, max(known) / 100)
            else:
                est.append("object_chance_assumed_100")
        if p <= 0:
            return None
        need = count / p
        area = grow(pts, area, c, need)
        return Demand(qid, "object", tuple(sorted(ids)), need, len(area),
                      _radius(area, c), M.EST_CLICK_SECONDS, 0.0, c, idx, level, est)

    for o in objs.get("creature", []):
        n = world.db.npc(o["id"]) or {}
        if _is_credit(n):
            # crédito de evento (visitar un punto, hablar, usar un objeto): no es un combate
            pts = world.points("npc", o["id"])
            area, c, extra = _area(pts, center)
            extra_yards = max(extra_yards, extra)
            demands.append(Demand(qid, "visit", (o["id"],), o.get("count") or 1, max(len(area), 1),
                                  _radius(area, c), M.EST_EVENT_SECONDS, 0.0, c, idx, level))
            continue
        d = npc_demand([o["id"]], o.get("count") or 1)
        if d is None:
            flags.append(f"kill_no_spawns:{o['id']}")
            continue
        demands.append(d)
    for o in objs.get("object", []):
        d = object_demand([o["id"]], o.get("count") or 1)
        if d is None:
            fixed += M.EST_EVENT_SECONDS
            flags.append(f"object_no_spawns:{o['id']}")
            continue
        demands.append(d)
    for o in objs.get("item", []):
        iid, count = o["id"], o.get("count") or 1
        srcs = world.chance.get(iid, [])
        item = world.db.item(iid) or {}
        if not item.get("questItem") and sum(1 for k, _, _ in srcs if k == "npc") > GENERIC_DROPPERS:
            # tela, botín común: se trae de la bolsa (o se compra); su tiempo no se puede medir aquí
            flags.append(f"inventory_item:{iid}")
            continue
        npcs = {sid: ch for kind, sid, ch in srcs if kind == "npc"}
        objs_ = {sid: ch for kind, sid, ch in srcs if kind == "object"}
        options = []
        if npcs:
            d = npc_demand(list(npcs), count, chances=npcs)
            if d == "unknown":
                flags.append(f"drop_rate_unknown:{iid}")
            elif d is not None:
                options.append(d)
        if objs_:
            d = object_demand(list(objs_), count, chances=objs_)
            if d is not None:
                options.append(d)
        if options:
            demands.append(min(options, key=lambda d: d.count * d.per_unit))
        elif any(k == "item" for k, _, _ in srcs):
            flags.append(f"container_item:{iid}")
        elif not srcs:
            if "item-from-other-quest" in mech:
                pass  # lo da otra misión
            elif "vendor-buy" in mech:
                fixed += M.EST_EVENT_SECONDS
            elif "crafted" in mech:
                flags.append(f"crafted_item:{iid}")
            elif count > 1:
                flags.append(f"item_no_source:{iid}")  # varios objetos sin fuente conocida: no se mide
            else:
                pass  # un objeto que te dan al aceptar (o el que inicia la misión): entrega
        elif npcs or objs_:
            flags.append(f"no_source_in_area:{iid}")
    for kind in ("event", "talk"):
        fixed += M.EST_EVENT_SECONDS * len(objs.get(kind, []))
    if "escort" in mech or escort_step:
        fixed += M.EST_ESCORT_SECONDS
        flags.append("escort")
    if "group/elite" in mech:
        flags.append("group")
    if "timed" in mech:
        flags.append("timed")
    if "use-item-at-place" in mech or "use-item-on-mob" in mech:
        fixed += M.EST_EVENT_SECONDS / 2
    if extra_yards:
        fixed += M.walk_seconds(extra_yards, level) * 2
        flags.append("area_moved")
    return demands, fixed, flags


_CREDIT_RE = re.compile(r"credit|trigger|doodad|DNT|counter|marker|KC Creature|bunny", re.I)


def _is_credit(npc: dict) -> bool:
    """Objetivo «matar» que en realidad es un crédito de evento o un PNJ amistoso (facción 35)."""
    name = npc.get("name") or ""
    return bool(_CREDIT_RE.search(name)) or npc.get("factionID") == 35


def resolve_overlaps(demands: list[Demand]):
    """Objetivos sobre los mismos enemigos (de la misma misión o de otras juntas en la ruta) se hacen a la vez.

    Las muertes compartidas son el máximo, no la suma; cada misión carga su parte proporcional.
    """
    by_id = defaultdict(list)
    for d in demands:
        if d.kind == "npc":
            for i in d.ids:
                by_id[i].append(d)
    seen = set()
    for nid, ds in by_id.items():
        ds = sorted(ds, key=lambda d: d.idx)
        groups = []
        for d in ds:
            if groups and d.idx - groups[-1][-1].idx <= OVERLAP_STEPS and dist(d.center, groups[-1][0].center) <= M.AREA_RADIUS:
                groups[-1].append(d)
            else:
                groups.append([d])
        for g in groups:
            if len(g) < 2:  # objetivos sobre los mismos enemigos, de una o de varias misiones
                continue
            key = tuple(sorted(id(d) for d in g))
            if key in seen:
                continue
            seen.add(key)
            total = sum(d.count for d in g)
            joint = max(d.count for d in g)
            for d in g:
                d.share = min(d.share, joint / total)


def demand_seconds(d: Demand, cls: str | None) -> float:
    return M.farm_seconds(d.count, d.n_spawns, d.radius, d.per_unit, d.level, cls) * d.share


# --------------------------------------------------------------------------------------------
# Puntuación de una guía (sin decisión: la decisión necesita las bandas de todas las guías)
# --------------------------------------------------------------------------------------------

def score_guide(guide_dir: Path, shared_dir: Path, world: World) -> dict:
    meta, sections = load_guide(guide_dir, shared_dir)
    if len(meta.get("classes") or []) > 1:
        # Guía para varias clases (las de la Horda, para cualquier clase): se puntúa la ruta común, sin los
        # pasos de una clase concreta.
        meta = {k: v for k, v in meta.items() if k != "classes"}
    cls = (meta.get("classes") or [None])[0]
    travel = Travel(world.travel, meta.get("faction", "Alliance"), cls)
    steps = flatten(meta, sections)
    totals = place_steps(steps, world, travel)

    dungeon_of: dict[int, str] = {}
    for s in steps:
        if s.do == "dungeon":
            name = _dungeon_name(s.raw)
            for q in s.raw.get("quests", []):
                dungeon_of.setdefault(int(q), name)

    by_q: dict[int, list[Step]] = defaultdict(list)
    for s in steps:
        if s.quest and s.do in ("accept", "complete", "turnin", "loot", "use"):
            by_q[s.quest].append(s)

    quests = {}
    all_demands: list[Demand] = []
    fixed_of, flags_of = {}, {}
    for qid, qs in by_q.items():
        comp = [s for s in qs if s.do in ("complete", "loot", "use")]
        turn = [s for s in qs if s.do == "turnin"]
        anchor = comp[0] if comp else (turn[0] if turn else qs[0])
        center = next((s.arrive for s in comp if s.arrive), None)
        if center is None:  # sin paso de objetivo: el área más cercana a donde se entrega o se coge
            center = next((s.arrive for s in turn + qs if s.arrive), None)
        if qid in dungeon_of:
            demands, fixed, flags = [], 0.0, ["dungeon"]
        else:
            demands, fixed, flags = objective_demands(world, qid, center, anchor.idx, anchor.level,
                                                      escort_step=any(s.raw.get("escort") for s in qs))
        for d in demands:
            all_demands.append(d)
        fixed_of[qid] = fixed
        flags_of[qid] = flags
    resolve_overlaps(all_demands)
    dem_of = defaultdict(list)
    for d in all_demands:
        dem_of[d.quest].append(d)

    for qid, qs in by_q.items():
        q = world.db.quest(qid) or {}
        turn = [s for s in qs if s.do == "turnin"]
        accept = [s for s in qs if s.do == "accept"]
        lvl = (turn[-1] if turn else qs[-1]).level
        flags = list(flags_of[qid])
        estimated = ["kill_seconds", "dialog_seconds"]
        obj_s = fixed_of[qid]
        kills = 0.0
        kill_xp = 0.0
        for d in dem_of[qid]:
            obj_s += demand_seconds(d, cls)
            estimated += d.estimated
            if d.kind == "npc":
                kills += d.count * d.share
                kill_xp += d.count * d.share * d.xp_each
        if any(f.startswith(("drop_rate_unknown", "inventory_item", "item_no_source", "container_item", "crafted_item", "kill_no_spawns",
                             "no_source_in_area")) for f in flags):
            unknown = True
        else:
            unknown = False
        if math.isinf(obj_s):
            obj_s, unknown = 0.0, True
        share_s = sum(s.travel_s for s in qs)
        saved_s = marginal_travel(steps, qid, travel)
        travel_s = max(share_s, saved_s)
        dialog_s = EST_DIALOG_SECONDS * (len(turn) + len(accept))
        total_s = obj_s + travel_s + dialog_s
        full = q.get("xp")
        share = M.quest_xp_share(lvl, int(q.get("level") or lvl)) if full else 0.0
        qxp = round((full or 0) * share) if turn else 0
        if not full:
            flags.append("xp_unknown")
            unknown = True
        classes = int(q.get("classes") or 0)
        class_quest = (bool(classes) or any((s.raw.get("if") or {}).get("class") for s in qs)
                       or any(s.class_section for s in qs))
        rewards = (q.get("rewards") or {})
        quests[qid] = {
            "quest": qid,
            "title": q.get("name"),
            "quest_level": q.get("level"),
            "level": lvl,
            "band": M.band_of(lvl),
            "steps": [s.id for s in qs],
            "turnin_idx": turn[-1].idx if turn else None,
            "scored": bool(turn),
            "xp_quest": qxp,
            "xp_full": full,
            "xp_share": share,
            "xp_kills": round(kill_xp),
            "xp": qxp + round(kill_xp),
            "kills": round(kills, 1),
            "objective_s": round(obj_s, 1),
            "travel_s": round(travel_s, 1),
            "dialog_s": dialog_s,
            "est_seconds": round(total_s, 1),
            "est_minutes": round(total_s / 60, 2),
            "travel_share_s": round(share_s, 1),
            "travel_saved_s": round(saved_s, 1),
            "objectives": [_demand_row(d, cls) for d in dem_of[qid]],
            "class_quest": class_quest,
            "dungeon": dungeon_of.get(qid),
            "unknown": unknown,
            "reward_items": sorted(set(rewards.get("item", []) + rewards.get("choice", []))),
            "guide_optional": any(s.raw.get("optional") for s in qs),
            "flags": sorted(set(flags)),
            "estimated": sorted(set(estimated)),
            "prereq_all": [p for p in q.get("preQuestGroup", [])],
            "prereq_any": [p for p in q.get("preQuestSingle", [])],
        }
        x = quests[qid]
        x["xp_per_min"] = round(x["xp"] / max(x["est_minutes"], 1 / 60), 1)
        x["rate"] = _rate(x["xp"], lvl, x["est_minutes"])

    step_rows = {}
    for s in steps:
        if not s.id:
            continue
        step_rows[s.id] = {"idx": s.idx, "do": s.do, "quest": s.quest, "level": s.level,
                           "travel_s": round(s.travel_s, 1), "action_s": round(s.action_s, 1),
                           "mode": s.mode or None}
    return {"meta": meta, "steps": step_rows, "quests": quests, "totals": totals, "class": cls}


def _demand_row(d: Demand, cls) -> dict:
    return {"kind": d.kind, "ids": list(d.ids), "need": round(d.count, 1), "spawns": d.n_spawns,
            "radius": round(d.radius), "per_unit_s": round(d.per_unit, 1), "share": round(d.share, 2),
            "seconds": round(demand_seconds(d, cls), 1)}


def _rate(xp: float, level: int, minutes: float) -> float:
    """% del nivel por hora."""
    return 100.0 * xp / M.level_xp(level) / max(minutes, 1 / 60) * 60


def _dungeon_name(raw: dict) -> str:
    """Nombre de la mazmorra de un paso `dungeon`: la etiqueta de `at` o el principio del texto."""
    at = raw.get("at") or []
    if len(at) > 3 and isinstance(at[3], str):
        name = re.sub(r"^Entrada (?:a|de)(?: las| los| la| el)? ", "", at[3])
    else:
        name = re.sub(r"^Opcional(?: \([^)]*\))?: ", "", raw.get("text", ""))
    name = re.split(r" \(|[,.]| con | en grupo| si ", name, maxsplit=1)[0]
    return name.strip()


# --------------------------------------------------------------------------------------------
# Bandas y decisión (todas las guías juntas)
# --------------------------------------------------------------------------------------------

MIN_BAND = 8


def band_stats(results: list[dict]) -> dict:
    """Distribución de la tasa normalizada por banda, sin repetir misiones entre guías."""
    vals = defaultdict(dict)
    for r in results:
        for qid, x in r["quests"].items():
            if _comparable(x):
                vals[x["band"]].setdefault(qid, x["rate"])
    order = sorted(vals, key=lambda b: int(b.split("-")[0]))
    out = {}
    for i, b in enumerate(order):
        v = sorted(vals[b].values())
        pooled = v
        if len(v) < MIN_BAND:
            pooled = sorted(sum((list(vals[o].values()) for o in order[max(0, i - 1):i + 2]), []))
        out[b] = {"n": len(v), "pooled": len(v) < MIN_BAND,
                  "p10": M.percentile(pooled, .10), "p25": M.percentile(pooled, .25),
                  "median": M.percentile(pooled, .5), "p75": M.percentile(pooled, .75),
                  "p90": M.percentile(pooled, .90), "_sorted": pooled}
    return out


def _comparable(x: dict) -> bool:
    return x["scored"] and not x["class_quest"] and not x["dungeon"] and not x["unknown"] and x["xp"] > 0


def decide_guide(res: dict, bands: dict) -> None:
    quests = res["quests"]
    # grafo de requisitos dentro de la guía
    children = defaultdict(list)
    for qid, x in quests.items():
        for p in x["prereq_all"] + x["prereq_any"]:
            if p in quests and p != qid:
                children[p].append(qid)
    fallback = {"p25": 0.0, "median": 0.0, "_sorted": []}

    def band(x):
        return bands.get(x["band"], fallback)

    # valor de cadena: la misión más las subcadenas que compensan, de abajo arriba
    order = sorted(quests, key=lambda q: -(quests[q]["turnin_idx"] or -1))
    chain = {}
    for qid in order:
        x = quests[qid]
        nxp = 100.0 * x["xp"] / M.level_xp(x["level"])
        mins = x["est_minutes"]
        # subcadenas de mejor a peor; cada una entra si sube la tasa de la cadena (mochila fraccional)
        subs = sorted((chain[c] for c in children[qid] if c in chain),
                      key=lambda cm: -(cm[0] / max(cm[1], 1 / 60)))
        for cx, cm in subs:
            if cx / max(cm, 1 / 60) > nxp / max(mins, 1 / 60):
                nxp += cx
                mins += cm
        chain[qid] = (nxp, mins)

    def descendants(qid):
        seen, stack = [], list(children[qid])
        while stack:
            c = stack.pop(0)
            if c not in seen:
                seen.append(c)
                stack.extend(children[c])
        return seen

    for qid, x in quests.items():
        b = band(x)
        cx, cm = chain[qid]
        x["chain_rate"] = round(cx / max(cm, 1 / 60) * 60, 2) if children[qid] else None
        x["unlocks"] = descendants(qid)
        x["percentile"] = round(M.rank_percentile(b["_sorted"], x["rate"]), 1) if b["_sorted"] else None
        x["rel_median"] = round(x["rate"] / b["median"], 3) if b["median"] else None
    for qid, x in quests.items():
        if not x["scored"]:
            x["decision"], x["reason"] = "keep", "not_turned_in"
            continue
        b = band(x)
        x["decision"], x["reason"] = M.decide(x["rate"], x["chain_rate"], b, class_quest=x["class_quest"],
                                              unknown=x["unknown"], dungeon=bool(x["dungeon"]),
                                              has_reward=bool(x["reward_items"]),
                                              grind=M.grind_rate(x["level"], res["class"]))
        x["grind_rate"] = round(M.grind_rate(x["level"], res["class"]), 2)
    # lo que abre una mazmorra de la guía se queda (la mazmorra se decide aparte)
    for qid, x in quests.items():
        if x["decision"] != "keep" and x["scored"] and any(quests[c]["dungeon"] for c in x["unlocks"]):
            x["decision"], x["reason"] = "keep", "chain"
    # una misión que necesita otra descartada también sale (iterar hasta estable)
    changed = True
    while changed:
        changed = False
        for qid, x in quests.items():
            if x["decision"] == "drop" or not x["scored"]:
                continue
            allp = [p for p in x["prereq_all"] if p in quests]
            anyp = [p for p in x["prereq_any"] if p in quests]
            blocked = [p for p in allp if quests[p]["decision"] == "drop"]
            if anyp and all(quests[p]["decision"] == "drop" for p in anyp):
                blocked += anyp
            if blocked and not x["class_quest"]:
                x["decision"], x["reason"], x["blocked_by"] = "drop", "requires", blocked
                changed = True
    for qid, x in quests.items():
        x["why"] = _why(x, quests, bands)
        x["why_plain"] = _plain(x["why"], quests, res)


def _unlock_label(x: dict, quests: dict) -> str | None:
    if not x["unlocks"]:
        return None
    for c in x["unlocks"]:
        if quests[c]["dungeon"]:
            return quests[c]["dungeon"]
    best = max(x["unlocks"], key=lambda c: quests[c]["xp"])
    more = len(x["unlocks"]) - 1
    return f"«{{quest:{best}}}»" + (f" y {more} más" if more else "")


def _why(x: dict, quests: dict, bands: dict) -> str:
    unlocks = _unlock_label(x, quests)
    requires = None
    if x.get("blocked_by"):
        requires = f"«{{quest:{x['blocked_by'][0]}}}»"
    rel = x.get("rel_median")
    if x["reason"] == "not_turned_in":
        return "se entrega fuera de esta guía"
    return M.why_line(x["xp"], x["est_minutes"], x["decision"], x["reason"], unlocks=unlocks,
                      band=x["band"], rel=rel, requires=requires)


def _plain(why: str, quests: dict, res: dict) -> str:
    import re
    return re.sub(r"\{quest:(\d+)\}", lambda m: (quests.get(int(m.group(1))) or {}).get("title") or m.group(1), why)

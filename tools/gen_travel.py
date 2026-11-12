#!/usr/bin/env python3
"""Travel planner dataset for Senda: data/travel/*.json.

Reads Polestar's generated Nav/TravelData.lua (flight masters, flights, boats, zeppelins, the tram,
lifts, timetables, portals, inns, class teleports; GPL-3.0, after Shortest Path Forever by Cillian
Berragan, GPL-3.0-or-later), writes plain JSON, cross-checks it against forever-db and runs a
Dijkstra self-test. Nothing here needs the game, the network or Lua.

    python tools/gen_travel.py --polestar <polestar clone> [--foreverdb <forever-db or its data/>]
                               [--out data/travel] [--check]

--foreverdb falls back to env SENDA_FOREVERDB, then <repo>/.cache/foreverdb.
--polestar falls back to env SENDA_POLESTAR. --check writes nothing and exits 1 on any failed test.
Sources, licences, schema and metrics: docs/TRAVEL.md.

Parts of this file adapt Polestar's Nav/Travel.lua cost model (constants below), Copyright (C) 2026
Polestar contributors, and, through it, Shortest Path Forever, Copyright (C) 2026 Cillian Berragan,
both GPL-3.0-or-later.
"""
from __future__ import annotations

import argparse
import heapq
import json
import math
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "data" / "travel"

# ---------------------------------------------------------------- planner constants (Polestar Nav/Travel.lua)
RUN_SPEED = 7.0        # yd/s unmounted
WALK_DETOUR = 1.25     # straight lines are not walkable
FLIGHT_SPEED = 30.0    # yd/s along a flight path
FLIGHT_STOP = 2.0      # s per hop (take-off, landing)
TAKE_OFF = 4.0         # s from reaching a master to take-off, when the previous leg was not a flight
HEARTH_ITEM = 6948
HEARTH_CAST = 10.0
HEARTH_SECONDS = 15.0  # cast plus loading screen
HEARTH_COOLDOWN = 3600
HEARTH_MARGIN = 120.0  # seconds hearthing must save
HEARTH_MIN_TRIP = 180.0
TELEPORT_MARGIN, TELEPORT_SHARE = 60.0, 0.2
FACTION = {1: "alliance", 2: "horde", 3: "both"}
TELEPORT_META = {  # annotation by Senda from the spell's well-known class and city (not in Polestar's file)
    556: ("SHAMAN", "both"), 3561: ("MAGE", "alliance"), 3562: ("MAGE", "alliance"), 3563: ("MAGE", "horde"),
    3565: ("MAGE", "alliance"), 3566: ("MAGE", "horde"), 3567: ("MAGE", "horde"), 18960: ("DRUID", "both"),
}
FLIGHT_MASTER_SUBNAME = re.compile(
    r"^(Flight Master|Flight Mistress|Wind Rider Master|Gryphon Master|Hippogryph Master|Bat Handler|"
    r"Darnassus Flight Master|Thunder Bluff Flight Master)$")


# ---------------------------------------------------------------- Lua table literal reader
class LuaReader:
    """Reads the Lua table constructors Polestar generates (literals only: numbers, strings, booleans,
    nested tables, `k=v` and `["k"]=v`). No code is executed."""

    def __init__(self, text: str):
        self.s, self.i = text, 0

    def ws(self):
        s = self.s
        while self.i < len(s):
            c = s[self.i]
            if c in " \t\r\n":
                self.i += 1
            elif s.startswith("--", self.i):
                j = s.find("\n", self.i)
                self.i = len(s) if j < 0 else j
            else:
                break

    def value(self):
        self.ws()
        c = self.s[self.i]
        if c == "{":
            return self.table()
        if c == '"':
            return self.string()
        m = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|nil").match(self.s, self.i)
        if not m:
            raise ValueError("bad Lua value at %d: %r" % (self.i, self.s[self.i:self.i + 40]))
        self.i = m.end()
        t = m.group(0)
        if t in ("true", "false"):
            return t == "true"
        if t == "nil":
            return None
        return float(t) if re.search(r"[.eE]", t) else int(t)

    def string(self):
        s, i, out = self.s, self.i + 1, []
        while s[i] != '"':
            if s[i] == "\\":
                i += 1
                out.append({"n": "\n", "t": "\t"}.get(s[i], s[i]))
            else:
                out.append(s[i])
            i += 1
        self.i = i + 1
        return "".join(out)

    def table(self):
        self.i += 1
        arr, keyed = [], {}
        while True:
            self.ws()
            c = self.s[self.i]
            if c == "}":
                self.i += 1
                break
            if c in ",;":
                self.i += 1
                continue
            m = re.compile(r'\[\s*"([^"]*)"\s*\]\s*=|([A-Za-z_]\w*)\s*=(?!=)').match(self.s, self.i)
            if m:
                self.i = m.end()
                keyed[m.group(1) if m.group(1) is not None else m.group(2)] = self.value()
            else:
                arr.append(self.value())
        if arr and keyed:
            raise ValueError("mixed Lua table")
        return keyed if keyed else arr


def lua_arg(text: str, marker: str):
    k = text.index(marker)
    j = text.index("{", k)
    return LuaReader(text[j:]).value()


# ---------------------------------------------------------------- JSON output
def dump(path: Path, obj, rows_key=None):
    """One record per line for lists of records, so diffs stay readable."""
    def enc(v):
        return json.dumps(v, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        if rows_key is None:
            f.write(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
            return
        meta = {k: v for k, v in obj.items() if k != rows_key}
        f.write("{\n")
        for k, v in meta.items():
            f.write(" %s: %s,\n" % (json.dumps(k), json.dumps(v, ensure_ascii=False, sort_keys=True)))
        f.write(" %s: [\n" % json.dumps(rows_key))
        rows = obj[rows_key]
        f.write(",\n".join("  " + enc(r) for r in rows))
        f.write("\n ]\n}\n")


def r1(x):
    return round(x, 1)


# ---------------------------------------------------------------- build the tables
def git_head(repo: Path):
    import subprocess
    try:
        return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=20).stdout.strip() or None
    except Exception:
        return None


def build(polestar: Path):
    src = polestar / "addon" / "Polestar" / "Nav" / "TravelData.lua"
    text = src.read_text(encoding="utf-8")
    td = lua_arg(text, "N.RegisterTravelData(")
    tr = lua_arg(text, "ns.Transit.Register(")
    return td, tr


def end_row(e):
    """A transport/portal end: name, continent, wx, wy, uiMap, x, y, frame, area[, z or board]."""
    d = {"name": e[0], "c": e[1], "wx": e[2], "wy": e[3], "map": e[4], "x": e[5], "y": e[6],
         "frame": e[7], "area": e[8]}
    if len(e) > 9:
        extra = e[9]
        if isinstance(extra, dict):
            d["board"] = {"wx": extra["wx"], "wy": extra["wy"], "z": extra["z"]}
        else:
            d["z"] = extra
    return d


def tables(td, tr):
    taxi = []
    for t in td["taxi"]:
        row = {"id": t[0], "name": t[8], "c": t[1], "wx": t[2], "wy": t[3], "map": t[4], "x": t[5], "y": t[6],
               "mask": t[7], "faction": FACTION[t[7]]}
        if len(t) > 9:
            row["class"] = t[9]
        taxi.append(row)
    f = td["flights"]
    flights = []
    for i in range(0, len(f), 3):
        a, b, yd = f[i], f[i + 1], f[i + 2]
        flights.append({"from": a, "to": b, "yards": yd, "seconds": r1(yd / FLIGHT_SPEED + FLIGHT_STOP)})
    transports, lifts = [], []
    svc = tr["services"]
    for t in td["transports"]:
        s = svc.get(t["id"], {})
        row = {"id": t["id"], "kind": t["kind"], "faction": FACTION[t["faction"]], "mask": t["faction"],
               "a": end_row(t["a"]), "b": end_row(t["b"]),
               "ride_ab_s": t["ab"], "ride_ba_s": t["ba"], "wait_a_s": t["waitA"], "wait_b_s": t["waitB"]}
        if s:
            row["board_s"] = s["board"]
            row["pre_s"], row["post_s"] = s["pre"], s["post"]
            row["routes"] = s["routes"]  # timetable route ids and the stop indices (1-based) at each end
            if "area" in s:
                row["area"] = s["area"]
        transports.append(row)
    for sid, s in sorted(svc.items()):
        if s["kind"] != "lift":
            continue
        lifts.append({"id": sid, "name": s["name"], "area": s["area"], "c": s["c"], "wx": s["wx"], "wy": s["wy"],
                      "top_z": s["top"], "bottom_z": s["bottom"], "dir": s.get("dir"), "board_s": s["board"],
                      "ride_s": s["ride"]["a"], "wait_s": s["wait"]["a"], "routes": s["routes"]})
    portals = []
    for p in td["portals"]:
        portals.append({"id": p["id"], "name": p["name"], "a": end_row(p["a"]), "b": end_row(p["b"]),
                        "seconds": p["seconds"], "area": p["area"], "mask": 3})
    inns = []
    for i in td["inns"]:
        inns.append({"area": i["area"], "c": i["c"], "frame": i["f"], "map": i["map"], "names": i["names"],
                     "npc": i["npc"], "wx": i["wx"], "wy": i["wy"], "x": i["x"], "y": i["y"]})
    tele = []
    for t in tr["teleports"]:
        cls, fac = TELEPORT_META[t["spell"]]
        row = {"spell": t["spell"], "name": t["name"], "class": cls, "faction": fac, "cast_s": t["cast"]}
        if "reagents" in t:
            row["reagents"] = [{"item": t["reagents"][k], "count": t["reagents"][k + 1]}
                               for k in range(0, len(t["reagents"]), 2)]
        if t.get("bind"):
            row["to"] = "bind"
        else:
            row["to"] = end_row(t["to"])
        tele.append(row)
    timetables = []
    for rid, r in sorted(tr["routes"].items()):
        stops = []
        for s in r["stops"]:
            st = {"arrive_ms": s[0], "depart_ms": s[1], "c": s[2], "wx": s[3], "wy": s[4]}
            if len(s) > 5:
                st["z"] = s[5]
            if len(s) > 6:
                st["car"] = s[6]
            stops.append(st)
        timetables.append({"id": rid, "kind": r["kind"], "period_ms": r["period"], "stops": stops})
    return taxi, flights, transports, lifts, portals, inns, tele, timetables


# ---------------------------------------------------------------- forever-db cross-checks
def resolve_foreverdb(arg):
    root = Path(arg or os.environ.get("SENDA_FOREVERDB") or REPO / ".cache" / "foreverdb")
    if (root / "data" / "spawn.jsonl").exists():
        return root / "data"
    if (root / "spawn.jsonl").exists():
        return root
    return None


def jsonl(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def load_forever(data: Path):
    npcs = {}
    for n in jsonl(data / "npc.jsonl"):
        npcs[n["id"]] = n
    fm_ids = {i for i, n in npcs.items()
              if FLIGHT_MASTER_SUBNAME.match(n.get("subname", "")) and "NYI" not in n.get("name", "")}
    spawns = {}
    for s in jsonl(data / "spawn.jsonl"):
        if s["kind"] == "npc":
            spawns.setdefault(s["id"], []).append(s)
    ui = {m["ui_map"]: m for m in jsonl(data / "ui_map.jsonl")}
    try:
        index = json.loads((data.parent / "index.json").read_text(encoding="utf-8"))
    except Exception:
        index = {}
    return npcs, fm_ids, spawns, ui, index


def validate_forever(taxi, inns, npcs, fm_ids, spawns, ui):
    """Every taxi node within 1.0 map percent (of its UiMap's width in yards) of a flight-master spawn."""
    fm_pts = []
    for nid in fm_ids:
        for s in spawns.get(nid, []):
            fm_pts.append((s["map"], s["x"], s["y"], nid))
    rows, bad = [], []
    for t in taxi:
        best = None
        for m, x, y, nid in fm_pts:
            if m != t["c"]:
                continue
            d = math.hypot(x - t["wx"], y - t["wy"])
            if best is None or d < best[0]:
                best = (d, nid, x, y)
        frame = ui.get(t["map"])
        width = abs(frame["left"] - frame["right"]) if frame else None
        height = abs(frame["top"] - frame["bottom"]) if frame else None
        # percent of the frame's larger side: a distance in yards read as map percent
        scale = max(width, height) if frame else None
        row = {"id": t["id"], "name": t["name"], "nearest_npc": best[1] if best else None,
               "npc_name": npcs[best[1]]["name"] if best else None,
               "yards": r1(best[0]) if best else None,
               "percent": round(best[0] / scale * 100, 2) if best and scale else None}
        row["ok"] = bool(best) and row["percent"] is not None and row["percent"] <= 1.0
        rows.append(row)
        if not row["ok"]:
            bad.append(row)
    # inns: the innkeeper's spawn
    inn_bad = []
    for i in inns:
        sp = [s for s in spawns.get(i["npc"], []) if s["map"] == i["c"]]
        if not sp:
            inn_bad.append({"npc": i["npc"], "names": i["names"], "why": "innkeeper not in forever-db spawns"})
            continue
        d = min(math.hypot(s["x"] - i["wx"], s["y"] - i["wy"]) for s in sp)
        if d > 30:
            inn_bad.append({"npc": i["npc"], "names": i["names"], "why": "nearest spawn %.0f yd away" % d})
    return rows, bad, inn_bad


# ---------------------------------------------------------------- symmetry
def validate_symmetry(taxi, flights, transports, portals, lifts, timetables):
    out = {}
    by = {(f["from"], f["to"]): f for f in flights}
    one_way, lopsided = [], []
    names = {t["id"]: t["name"] for t in taxi}
    for (a, b), f in sorted(by.items()):
        r = by.get((b, a))
        if r is None:
            one_way.append([a, b, names[a], names[b]])
        else:
            ratio = max(f["yards"], r["yards"]) / max(1, min(f["yards"], r["yards"]))
            if ratio > 1.6:
                lopsided.append([a, b, f["yards"], r["yards"]])
    ids = set(names)
    unknown = [f for f in flights if f["from"] not in ids or f["to"] not in ids]
    cross_faction = []
    mask = {t["id"]: t["mask"] for t in taxi}
    for f in flights:
        a, b = mask[f["from"]], mask[f["to"]]
        if a != 3 and b != 3 and a != b:
            cross_faction.append([f["from"], f["to"]])
    # transports: every end pair has its own two rides and waits; the reverse is the same service (ba)
    tr_issues = []
    for t in transports:
        for k in ("ride_ab_s", "ride_ba_s", "wait_a_s", "wait_b_s"):
            if not t[k] or t[k] <= 0:
                tr_issues.append([t["id"], "missing " + k])
        if t["kind"] == "tram" and t["ride_ab_s"] != t["ride_ba_s"]:
            tr_issues.append([t["id"], "tram rides differ"])
    # portals: a pair, each way present
    pmap = {(p["a"]["name"], p["b"]["name"]) for p in portals}
    # portals on other continents (Forever's new one) form a chain, not pairs: list one-way ones
    p_oneway = sorted({"%s -> %s" % (a, b) for (a, b) in pmap if (b, a) not in pmap})
    tt_ids = {t["id"] for t in timetables}
    bad_route_ref = []
    for t in transports + lifts:
        for r in t.get("routes", []):
            if r["route"] not in tt_ids:
                bad_route_ref.append([t["id"], r["route"]])
    return {"flights_total": len(flights), "flights_one_way": one_way, "flights_lopsided_over_1_6x": lopsided,
            "flights_unknown_node": unknown, "flights_between_opposite_factions": cross_faction,
            "transport_issues": tr_issues, "portals_one_way": p_oneway, "bad_timetable_refs": bad_route_ref}


# ---------------------------------------------------------------- planner (Dijkstra self-test)
class Planner:
    """The planner as Polestar's Travel.lua prices it, reduced to what the tests need: walking in straight
    lines (x1.25 at 7 yd/s), hops between flight masters, boats, zeppelins and the tram with their mean
    wait, walk-in portals, the Hearthstone and class teleports (only from the start)."""

    def __init__(self, taxi, flights, transports, portals, inns, teleports):
        self.taxi = {t["id"]: t for t in taxi}
        self.flights = flights
        self.transports = transports
        self.portals = portals
        self.inns = inns
        self.teleports = teleports

    def allowed_mask(self, mask, faction):
        return mask == 3 or mask == {"alliance": 1, "horde": 2}[faction]

    def plan(self, start, target, faction, cls=None, bind=None, hearth=False, teleports=False,
             forever_transports=True):
        """start/target: (continent, wx, wy). bind: an inn dict. Returns (seconds, legs)."""
        nodes = []  # (key, c, wx, wy)
        edges = {}  # key -> [(key, secs, how, label)]

        def add(key, c, wx, wy):
            nodes.append((key, c, wx, wy))
            edges.setdefault(key, [])

        def link(a, b, secs, how, label, ref=None):
            edges[a].append((b, secs, how, label, ref))

        add("start", *start)
        add("target", *target)
        for t in self.taxi.values():
            if not self.allowed_mask(t["mask"], faction):
                continue
            if t.get("class") and t["class"] != cls:
                continue
            add("fp:%d" % t["id"], t["c"], t["wx"], t["wy"])
        for f in self.flights:
            a, b = "fp:%d" % f["from"], "fp:%d" % f["to"]
            if a in edges and b in edges:
                link(a, b, f["yards"] / FLIGHT_SPEED + FLIGHT_STOP, "fly", "%s -> %s" % (
                    self.taxi[f["from"]]["name"], self.taxi[f["to"]]["name"]), (f["from"], f["to"]))
        for t in self.transports:
            if not self.allowed_mask(t["mask"], faction):
                continue
            if not forever_transports and t["id"] == "boat-stormwind-auberdine":
                continue
            for end, key in (("a", "dock:%s:a"), ("b", "dock:%s:b")):
                add(key % t["id"], t[end]["c"], t[end]["wx"], t[end]["wy"])
            link("dock:%s:a" % t["id"], "dock:%s:b" % t["id"], t["wait_a_s"] + t["ride_ab_s"], "ride", t["id"], t["id"])
            link("dock:%s:b" % t["id"], "dock:%s:a" % t["id"], t["wait_b_s"] + t["ride_ba_s"], "ride", t["id"], t["id"])
        for p in self.portals:
            if p["a"]["c"] not in (0, 1):
                continue
            add("portal:%s:a" % p["id"], p["a"]["c"], p["a"]["wx"], p["a"]["wy"])
            add("portal:%s:b" % p["id"], p["b"]["c"], p["b"]["wx"], p["b"]["wy"])
            link("portal:%s:a" % p["id"], "portal:%s:b" % p["id"], p["seconds"], "portal", p["id"])
        if bind is not None:
            add("bind", bind["c"], bind["wx"], bind["wy"])
        if hearth and bind is not None:
            link("start", "bind", HEARTH_SECONDS, "hearth", "Hearthstone")
        if teleports:
            for t in self.teleports:
                if t["class"] != cls or t["faction"] not in ("both", faction) or t["to"] == "bind":
                    continue
                key = "tele:%d" % t["spell"]
                add(key, t["to"]["c"], t["to"]["wx"], t["to"]["wy"])
                link("start", key, t["cast_s"] + 5, "teleport", t["name"])
        # walking between every pair of nodes on one continent (straight lines x1.25)
        pos = {k: (c, x, y) for k, c, x, y in nodes}
        keys = list(pos)
        for a in keys:
            for b in keys:
                if a == b or pos[a][0] != pos[b][0] or pos[a][0] not in (0, 1):
                    continue
                d = math.hypot(pos[a][1] - pos[b][1], pos[a][2] - pos[b][2])
                link(a, b, d * WALK_DETOUR / RUN_SPEED, "walk", "", None)
        # Dijkstra; state = (key, arrived by flight?) so the take-off delay is charged once per flight
        dist = {("start", False): 0.0}
        prev = {}
        heap = [(0.0, "start", False)]
        while heap:
            d, u, by_fly = heapq.heappop(heap)
            if d > dist.get((u, by_fly), 1e18):
                continue
            if u == "target":
                break
            for v, secs, how, label, ref in edges[u]:
                extra = TAKE_OFF if (how == "fly" and not by_fly) else 0.0
                nd, st = d + secs + extra, (v, how == "fly")
                if nd < dist.get(st, 1e18):
                    dist[st] = nd
                    prev[st] = ((u, by_fly), how, label, secs + extra, ref)
                    heapq.heappush(heap, (nd, v, how == "fly"))
        best = min(((dist[s], s) for s in dist if s[0] == "target"), default=None)
        if best is None:
            return None, []
        legs, st = [], best[1]
        while st in prev:
            p, how, label, secs, ref = prev[st]
            legs.append({"how": how, "label": label, "seconds": r1(secs), "ref": ref})
            st = p
        legs.reverse()
        return best[0], legs


def selftest(taxi, flights, transports, portals, inns, teleports):
    P = Planner(taxi, flights, transports, portals, inns, teleports)
    T = {t["id"]: t for t in taxi}
    pt = lambda i: (T[i]["c"], T[i]["wx"], T[i]["wy"])
    inn = lambda area: next(i for i in inns if i["area"] == area)
    ip = lambda area: (inn(area)["c"], inn(area)["wx"], inn(area)["wy"])
    results = []

    def run(name, expect_desc, check, **kw):
        secs, legs = P.plan(kw.pop("start"), kw.pop("target"), kw.pop("faction"), **kw)
        ok = secs is not None and check(legs, secs)
        results.append({"name": name, "expect": expect_desc, "ok": bool(ok),
                        "seconds": None if secs is None else r1(secs),
                        "legs": [(l["how"], l["label"]) for l in legs if l["how"] != "walk"]})

    used = lambda legs, how, frag="": any(l["how"] == how and frag in l["label"] for l in legs)
    # 1 Stormwind -> Auberdine: Forever's harbour boat
    run("Stormwind -> Auberdine (Forever)", "Stormwind Harbor boat",
        lambda l, s: used(l, "ride", "boat-stormwind-auberdine"), start=pt(2), target=pt(26), faction="alliance")
    # 2 the same without Forever's boat: Menethil boat or a flight, never walking
    run("Stormwind -> Auberdine (Era transports)", "routes through Menethil (boat or flight), not the harbour boat",
        lambda l, s: any("Menethil" in g["label"] or "menethil" in g["label"] for g in l)
        and not used(l, "ride", "stormwind"),
        start=pt(2), target=pt(26), faction="alliance", forever_transports=False)
    # 3 Ironforge -> Stormwind by tram: from the tram's own gate in Ironforge to Stormwind's Trade District
    # (inn to inn the flight wins by ~20 s: the inns lie close to the flight masters and far from the tram)
    tram = next(t for t in transports if t["id"] == "tram-stormwind-ironforge")
    run("Ironforge tram gate -> Stormwind Trade District", "Deeprun Tram", lambda l, s: used(l, "ride", "tram-stormwind-ironforge"),
        start=(0, tram["b"]["wx"], tram["b"]["wy"] + 150), target=(0, tram["a"]["wx"], tram["a"]["wy"] - 200),
        faction="alliance")
    # 4 and back, city centre to city centre
    run("Stormwind inn -> Ironforge inn", "Deeprun Tram", lambda l, s: used(l, "ride", "tram-stormwind-ironforge"),
        start=ip(1519), target=ip(1537), faction="alliance")
    # 5 walk beats fly under 400 yd: a target 350 yd from Darkshire's flight master
    c, x, y = pt(12)
    run("Short hop under 400 yd (350 yd)", "walk only", lambda l, s: all(g["how"] == "walk" for g in l),
        start=(c, x, y), target=(c, x + 350, y), faction="alliance")
    # 6 ... and at 399 yd still walking, whichever way the target lies
    run("Short hop under 400 yd (399 yd)", "walk only", lambda l, s: all(g["how"] == "walk" for g in l),
        start=(c, x, y), target=(c, x, y - 399), faction="alliance")
    # 7 Orgrimmar -> Undercity: the zeppelin, a Horde service
    run("Orgrimmar -> Undercity", "zeppelin", lambda l, s: used(l, "ride", "zeppelin-orgrimmar-undercity"),
        start=ip(1637), target=ip(1497), faction="horde")
    # 8 Booty Bay -> Ratchet: the neutral boat, for either faction
    for fac in ("alliance", "horde"):
        run("Booty Bay -> Ratchet (%s)" % fac, "boat-bootybay-ratchet",
            lambda l, s: used(l, "ride", "bootybay-ratchet"), start=ip(35), target=ip(392), faction=fac)
    # 9 Menethil -> Theramore: Alliance boat
    run("Menethil Harbor -> Theramore", "boat-menethil-theramore",
        lambda l, s: used(l, "ride", "menethil-theramore"), start=ip(2104), target=ip(513), faction="alliance")
    # 10 Hearthstone: Southshore -> bind in Stormwind
    run("Hearthstone Southshore -> Stormwind inn", "hearth",
        lambda l, s: used(l, "hearth") and s <= HEARTH_SECONDS + 1,
        start=ip(271), target=ip(1519), faction="alliance", bind=inn(1519), hearth=True)
    # 11 Mage teleport from Undercity to Thunder Bluff (Kalimdor, no direct flight, zeppelin + long)
    run("Mage Undercity -> Thunder Bluff", "Teleport: Thunder Bluff",
        lambda l, s: used(l, "teleport", "Thunder Bluff"),
        start=ip(1497), target=ip(1638), faction="horde", cls="MAGE", teleports=True)
    # 12 Druid: Teleport: Moonglade to Nighthaven (druid-only node 62 for Alliance)
    run("Druid Stormwind -> Nighthaven", "Teleport: Moonglade or the class flight master",
        lambda l, s: used(l, "teleport", "Moonglade") or any("Nighthaven" in g["label"] for g in l),
        start=ip(1519), target=pt(62), faction="alliance", cls="DRUID", teleports=True)
    # 13 a non-druid never uses Nighthaven's class node
    run("Non-druid never lands at Nighthaven", "no Nighthaven leg",
        lambda l, s: not any("Nighthaven" in g["label"] for g in l),
        start=pt(49), target=ip(1519), faction="alliance")
    # 14 a faction never rides or flies another faction's service, over a fixed sample of pairs
    for fac, other in (("horde", 1), ("alliance", 2)):
        own = [t for t in taxi if t["mask"] in (3, {"alliance": 1, "horde": 2}[fac]) and not t.get("class")]
        pairs = [(own[i], own[(i * 7 + 3) % len(own)]) for i in range(0, len(own), 2)]
        bad = n = 0
        for a, b in pairs:
            if a["id"] == b["id"]:
                continue
            _, legs = P.plan((a["c"], a["wx"], a["wy"]), (b["c"], b["wx"], b["wy"]), fac)
            n += 1
            for g in legs:
                if g["how"] == "ride" and any(t["id"] == g["ref"] and t["mask"] == other for t in transports):
                    bad += 1
                if g["how"] == "fly" and any(T[i]["mask"] == other for i in g["ref"]):
                    bad += 1
        results.append({"name": "%s never uses %s-only services (%d sampled pairs)" % (
            fac, "alliance" if other == 1 else "horde", n), "expect": "0 violations", "ok": bad == 0 and n > 0,
            "seconds": None, "legs": [], "violations": bad})
    return results


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--polestar", default=os.environ.get("SENDA_POLESTAR"), help="Polestar clone")
    ap.add_argument("--foreverdb", help="forever-db folder (or its data/); env SENDA_FOREVERDB")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--check", action="store_true", help="validate only, write nothing")
    a = ap.parse_args()
    if not a.polestar or not (Path(a.polestar) / "addon" / "Polestar" / "Nav" / "TravelData.lua").exists():
        sys.exit("need --polestar <clone> (or SENDA_POLESTAR) containing addon/Polestar/Nav/TravelData.lua")
    polestar = Path(a.polestar)
    td, tr = build(polestar)
    taxi, flights, transports, lifts, portals, inns, tele, timetables = tables(td, tr)

    fdata = resolve_foreverdb(a.foreverdb)
    fv, fv_bad, inn_bad, fv_index = [], [], [], {}
    if fdata:
        npcs, fm_ids, spawns, ui, fv_index = load_forever(fdata)
        fv, fv_bad, inn_bad = validate_forever(taxi, inns, npcs, fm_ids, spawns, ui)
    else:
        print("warning: forever-db not found; flight-master cross-check skipped", file=sys.stderr)
    sym = validate_symmetry(taxi, flights, transports, portals, lifts, timetables)
    tests = selftest(taxi, flights, transports, portals, inns, tele)

    counts = {"taxi_nodes": len(taxi), "flights": len(flights), "transports": len(transports),
              "lifts": len(lifts), "portals": len(portals), "inns": len(inns), "teleports": len(tele),
              "timetable_routes": len(timetables), "timetable_stops": sum(len(t["stops"]) for t in timetables)}
    by_kind = {}
    for t in transports:
        by_kind[t["kind"]] = by_kind.get(t["kind"], 0) + 1
    counts["transports_by_kind"] = by_kind
    meta = {
        "name": "senda-travel", "schema": 1,
        "sources": {
            "polestar": {"file": "addon/Polestar/Nav/TravelData.lua", "commit": git_head(polestar), "licence": "GPL-3.0-or-later",
                         "header": "Blizzard Classic Era client tables (wago.tools build %s) + WoW Forever client "
                                   "TaxiPathNode/TransportAnimation/spell tables (build 1.60.1.70532) + CMaNGOS "
                                   "classic-db 22b5146, after Shortest Path Forever (C) 2026 Cillian Berragan" % td["build"]},
            "era_client_build": td["build"],
            "forever_db": {"version": fv_index.get("version"), "clientBuild": fv_index.get("clientBuild"),
                           "licence": "GPL-3.0 / CC BY 4.0 (own layer)"} if fv_index else None,
        },
        "constants": {"run_speed_yd_s": RUN_SPEED, "walk_detour": WALK_DETOUR, "flight_speed_yd_s": FLIGHT_SPEED,
                      "flight_stop_s": FLIGHT_STOP, "take_off_s": TAKE_OFF, "hearth_item": HEARTH_ITEM,
                      "hearth_cast_s": HEARTH_CAST, "hearth_total_s": HEARTH_SECONDS,
                      "hearth_cooldown_s": HEARTH_COOLDOWN, "hearth_margin_s": HEARTH_MARGIN,
                      "hearth_min_trip_s": HEARTH_MIN_TRIP, "teleport_margin_s": TELEPORT_MARGIN,
                      "teleport_share": TELEPORT_SHARE,
                      "faction_mask": {"1": "alliance", "2": "horde", "3": "both"},
                      "flight_seconds": "yards / flight_speed + flight_stop; add take_off once per journey leg"},
        "frames": "map/x/y: UiMap id and map percent; frame 'e' = Classic Era map, 'l' = WoW Forever redrawn map. "
                  "c/wx/wy: continent id and world yards (wx north-south, wy east-west, as forever-db spawns).",
        "counts": counts,
    }
    report = {
        "forever_db_flight_masters": {
            "nodes": len(taxi), "checked": len(fv), "within_1_percent": sum(1 for r in fv if r["ok"]),
            "mismatches": fv_bad,
            "median_yards": sorted(r["yards"] for r in fv if r["yards"] is not None)[len(fv) // 2] if fv else None},
        "forever_db_innkeepers": {"inns": len(inns), "mismatches": inn_bad},
        "symmetry": sym,
        "dijkstra_selftest": {"total": len(tests), "passed": sum(1 for t in tests if t["ok"]), "cases": tests},
    }

    print("taxi nodes %d | flights %d | transports %d (%s) | lifts %d | portals %d | inns %d | teleports %d" % (
        len(taxi), len(flights), len(transports), by_kind, len(lifts), len(portals), len(inns), len(tele)))
    print("timetable routes %d (%d stops)" % (len(timetables), counts["timetable_stops"]))
    if fv:
        print("forever-db: %d/%d taxi nodes within 1.0 percent of a flight master; %d innkeeper mismatch(es)" % (
            report["forever_db_flight_masters"]["within_1_percent"], len(fv), len(inn_bad)))
        for r in fv_bad:
            print("   mismatch node %-3d %-45s %s" % (r["id"], r["name"], "%s yd (%s%%)" % (r["yards"], r["percent"])
                                                      if r["yards"] is not None else "no flight master spawn"))
    print("flights: %d one-way, %d lopsided, %d unknown, %d cross-faction" % (
        len(sym["flights_one_way"]), len(sym["flights_lopsided_over_1_6x"]), len(sym["flights_unknown_node"]),
        len(sym["flights_between_opposite_factions"])))
    for t in tests:
        print("  [%s] %-46s %s %s" % ("ok" if t["ok"] else "FAIL", t["name"], t["seconds"], t["legs"]))
    print("self-test: %d/%d" % (report["dijkstra_selftest"]["passed"], len(tests)))

    if not a.check:
        out = Path(a.out)
        dump(out / "meta.json", meta)
        dump(out / "taxi_nodes.json", {"rows": taxi}, "rows")
        dump(out / "flights.json", {"rows": flights}, "rows")
        dump(out / "transports.json", {"rows": transports}, "rows")
        dump(out / "lifts.json", {"rows": lifts}, "rows")
        dump(out / "portals.json", {"rows": portals}, "rows")
        dump(out / "inns.json", {"rows": inns}, "rows")
        dump(out / "teleports.json", {"rows": tele}, "rows")
        dump(out / "timetables.json", {"note": "periods and stops only; the motion frames of Polestar's file are "
                                       "not kept", "rows": timetables}, "rows")
        dump(out / "validation.json", report)
        print("wrote", out)
    return 0 if report["dijkstra_selftest"]["passed"] == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())

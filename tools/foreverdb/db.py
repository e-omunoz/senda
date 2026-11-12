"""forever-db (Polestar's open quest data for WoW: Forever) behind the QuestDB interface.

forever-db publishes JSONL tables (one JSON object per line; an absent field is omitted). This
module reads the ones Senda needs and shapes them like ``questiedb.QuestDB`` so that
tools/enrich.py, tools/verify.py and tools/lookup.py can use either source unchanged.

Licence: the tables are GPL-3.0 (forever-db/LICENSE), its own layer CC BY 4.0. Credits in
THIRD_PARTY.md. The data is downloaded by tools/fetch_foreverdb.py into ``<repo>/.cache/foreverdb``.

Corrections: forever-db's ``corrections/{quests,npcs,objects}.json`` (hand-checked fixes, many not yet in
the tables) and then Senda's own ``data/corrections/*.json`` are applied on load
(tools/foreverdb/corrections.py; ``ForeverDB.open(corrections=False)`` reads the raw tables).

What forever-db does not have (returned as ``None`` and listed in ``ForeverDB.MISSING``):
``exclusiveTo``, ``requiredSkill``, ``npcFlags``, vendors and NPC waypoints. QuestieDB, read
locally, stays the source for those; Senda keeps the facts it needs in its TOML (``reqskill``).
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

from questiedb.constants import ALLIANCE_MASK, HORDE_MASK
from questiedb.db import QuestDB

from . import corrections as C

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIR = REPO_ROOT / ".cache" / "foreverdb"
TABLES = ("quest", "quest_start", "quest_end", "quest_objective", "quest_prereq", "quest_reward",
          "npc", "object", "spawn", "ui_map", "item", "item_source")
REQUIRED = ("quest", "quest_start", "quest_end", "quest_prereq", "npc", "object", "spawn", "ui_map")


def resolve_foreverdb(path: str | os.PathLike | None = None) -> Path:
    """forever-db root (the folder with ``datapackage.json`` and ``data/``).

    Accepts the root itself or its ``data/`` folder. Order: argument, env SENDA_FOREVERDB,
    ``<repo>/.cache/foreverdb``.
    """
    root = Path(path or os.environ.get("SENDA_FOREVERDB") or DEFAULT_DIR)
    if root.name == "data" and not (root / "data").is_dir():
        root = root.parent
    if not (root / "data" / "quest.jsonl").exists():
        raise FileNotFoundError(f"forever-db not found under {root} (run `python tools/fetch_foreverdb.py`, "
                                f"or use --foreverdb / SENDA_FOREVERDB)")
    return root


def read_jsonl(path: Path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


# --------------------------------------------------------------------------------------------
# World yards -> map percent
# --------------------------------------------------------------------------------------------

class Frames:
    """The ``ui_map`` frames: each UiMap's edges in world yards on its client Map.

    ``left``/``right`` are world y (west) at x = 0% / 100%; ``top``/``bottom`` world x (north) at
    y = 0% / 100%. The formula is adaptado de Polestar, rust/crates/forge-data/src/publish/lua_core.lua
    (``lib.ToUiMap``).

    Zone frames are rectangles and overlap near borders, and forever-db does not say which zone a
    spawn is in. Polestar keeps the smallest frame; against QuestieDB's zones (8.4k NPCs) that
    agrees 74% of the time. Senda picks, in order: a city frame that holds the point (< CITY yd²),
    else the zone frame where the point lies nearest the centre (continents, > CONTINENT yd², only
    if nothing else), ties to the lowest uiMap id: 88% agreement. The other frames that hold the
    point are kept too (``all``), so a coordinate in the neighbouring zone still matches.
    """

    CITY = 2.1e6
    CONTINENT = 1e8

    def __init__(self, rows):
        self.by_map: dict[int, list[tuple]] = {}
        for r in rows:
            f = (int(r["ui_map"]), float(r["left"]), float(r["right"]), float(r["top"]), float(r["bottom"]))
            area = abs((f[2] - f[1]) * (f[4] - f[3]))
            self.by_map.setdefault(int(r["map"]), []).append(f + (area,))
        for frames in self.by_map.values():
            frames.sort(key=lambda f: (f[5], f[0]))  # smallest first
        self.uimaps = sorted(f[0] for fs in self.by_map.values() for f in fs)

    def all(self, map_id: int, x: float, y: float) -> list[list]:
        """Every frame holding the point, best first: [[uiMapId, x%, y%], ...]."""
        hits = []
        for ui, left, right, top, bottom, area in self.by_map.get(int(map_id), []):
            px = (y - left) / (right - left) * 100
            py = (x - top) / (bottom - top) * 100
            if 0 <= px <= 100 and 0 <= py <= 100:
                hits.append((ui, round(px, 2), round(py, 2), area))
        if not hits:
            return []

        def rank(h):
            if h[3] < self.CITY:
                return (0, h[3], h[0])
            centre = round((h[1] - 50) ** 2 + (h[2] - 50) ** 2)
            return (1 if h[3] <= self.CONTINENT else 2, centre, h[0])

        return [[h[0], h[1], h[2]] for h in sorted(hits, key=rank)]

    def to_uimap(self, map_id: int, x: float, y: float) -> list | None:
        hits = self.all(map_id, x, y)
        return hits[0] if hits else None


# --------------------------------------------------------------------------------------------
# Build the QuestDB-shaped data dict
# --------------------------------------------------------------------------------------------

def _load(root: Path, apply_corrections: bool = True, senda_corrections: Path | None = C.SENDA_DIR) -> dict:
    data_dir = root / "data"
    tables = {}
    for t in TABLES:
        p = data_dir / f"{t}.jsonl"
        if not p.exists():
            if t in REQUIRED:
                raise FileNotFoundError(f"forever-db table missing: {p}")
            tables[t] = []
            continue
        tables[t] = list(read_jsonl(p))
    index = {}
    if (root / "index.json").exists():
        index = json.loads((root / "index.json").read_text(encoding="utf-8"))

    # -- corrections: forever-db's corrections/*.json, then Senda's data/corrections/*.json -----
    corr = C.load(root, senda_corrections) if apply_corrections else {"quests": {}, "npcs": {}, "objects": {}}
    q_fixed = C.apply_quests(tables, corr)

    frames = Frames(tables["ui_map"])

    # -- spawns ------------------------------------------------------------------------------
    spawns: dict[tuple[str, int], list] = {}
    alt: dict[tuple[str, int], list] = {}
    world: dict[tuple[str, int], list] = {}
    for s in sorted(tables["spawn"], key=lambda r: (r["kind"], r["id"], r["map"], r["n"])):
        key = (s["kind"], int(s["id"]))
        world.setdefault(key, []).append([int(s["map"]), s["x"], s["y"]])
        hits = frames.all(s["map"], float(s["x"]), float(s["y"]))
        if not hits:  # instance or a map without a frame: only the world point is kept
            continue
        ui, px, py = hits[0]
        spawns.setdefault(key, []).append([ui, px, py, None])
        # Zone frames overlap near borders: keep the point in every other frame too, so a guide
        # coordinate in the neighbouring zone (or on the continent map) can still be matched.
        alt.setdefault(key, []).extend(h + [None] for h in hits[1:])

    # corrected spawns (map percent): `addSpawns` replaces that map's points, `set.spawns` all of them
    for kind, ck in (("npc", "npcs"), ("object", "objects")):
        for eid, ov in C.spawn_overrides(corr, ck).items():
            key = (kind, eid)
            if ov["all"]:
                spawns.pop(key, None)
                alt.pop(key, None)
            for ui, pts in ov["maps"].items():
                spawns[key] = [s for s in spawns.get(key, []) if s[0] != ui] + [[ui, x, y, None] for x, y in pts]
                alt[key] = [s for s in alt.get(key, []) if s[0] != ui]

    # -- quests ------------------------------------------------------------------------------
    starts: dict[int, dict[str, list]] = {}
    ends: dict[int, dict[str, list]] = {}
    for r in tables["quest_start"]:
        starts.setdefault(int(r["quest"]), {"npc": [], "object": [], "item": []})[r["kind"]].append(int(r["id"]))
    for r in tables["quest_end"]:
        ends.setdefault(int(r["quest"]), {"npc": [], "object": []}).setdefault(r["kind"], []).append(int(r["id"]))
    pre_all: dict[int, list] = {}
    pre_any: dict[int, list] = {}
    crumbs: dict[int, list] = {}
    crumb_for: dict[int, int] = {}
    for r in tables["quest_prereq"]:
        q, p = int(r["quest"]), int(r["pre"])
        if r.get("breadcrumb"):
            # «the earlier quest only leads to this one»: not required (QuestieDB: breadcrumbs).
            crumbs.setdefault(q, []).append(p)
            crumb_for.setdefault(p, q)
        elif r["mode"] == "any":
            pre_any.setdefault(q, []).append(p)
        else:
            pre_all.setdefault(q, []).append(p)
    objectives: dict[int, list] = {}
    for r in sorted(tables["quest_objective"], key=lambda r: (r["quest"], r["n"])):
        objectives.setdefault(int(r["quest"]), []).append(r)
    rewards: dict[int, list] = {}
    for r in tables["quest_reward"]:
        rewards.setdefault(int(r["quest"]), []).append(r)

    side_mask = {1: ALLIANCE_MASK, 2: HORDE_MASK}
    quests = {}
    for r in tables["quest"]:
        qid = int(r["id"])
        objs = {"creature": [], "object": [], "item": [], "event": [], "talk": []}
        for o in objectives.get(qid, []):
            kind = {"kill": "creature"}.get(o["kind"], o["kind"])
            row = {"id": int(o.get("target") or 0), "text": None, "count": o.get("count")}
            objs.setdefault(kind, []).append(row)
        objs = {k: v for k, v in objs.items() if v}
        races = int(r.get("races") or 0)
        if not races and r.get("side") in side_mask:
            races = side_mask[r["side"]]
        st = starts.get(qid, {"npc": [], "object": [], "item": []})
        fi = ends.get(qid, {"npc": [], "object": []})
        rw = rewards.get(qid, [])
        fx = q_fixed.get(qid, {})
        quests[qid] = {
            "id": qid,
            "name": r.get("title"),
            "level": int(r.get("level") or 0),
            "requiredLevel": int(r.get("min_level") or 0),
            "requiredMaxLevel": 0,
            "races": races,
            "classes": int(r.get("classes") or 0),
            "side": r.get("side"),
            "starters": {"npc": sorted(st.get("npc", [])), "object": sorted(st.get("object", [])),
                         "item": sorted(st.get("item", []))},
            "finishers": {"npc": sorted(fi.get("npc", [])), "object": sorted(fi.get("object", []))},
            "preQuestGroup": sorted(pre_all.get(qid, [])),
            "preQuestSingle": sorted(pre_any.get(qid, [])),
            "childQuests": [],
            "inGroupWith": [],
            # not in forever-db's tables (QuestieDB has it); its corrections give some (`excl`)
            "exclusiveTo": fx.get("extra", {}).get("excl"),
            "nextQuestInChain": 0,
            "parentQuest": 0,
            "breadcrumbFor": crumb_for.get(qid, 0),
            "breadcrumbs": sorted(crumbs.get(qid, [])),
            "zone": {"areaId": int(r["zone_area"]), "uiMapId": None, "name": None} if r.get("zone_area") else None,
            "objectivesText": [],
            "objectives": objs,
            "trigger": None,
            "extraObjectives": 0,
            "sourceItemId": 0,
            "requiredSkill": None,        # not in forever-db: QuestieDB (local) only
            "requiredMinRep": None,
            "requiredMaxRep": None,
            "requiredSpell": 0,
            "questFlags": 0,
            "specialFlags": 0,
            "availableStartingWith": 0,
            "availableUntilCompleted": 0,
            "hidden": None,
            "corrected": sorted(set(fx.get("fields", []))),
            # forever-db extras
            "xp": r.get("xp"),
            "money": r.get("money_copper"),
            "type": r.get("type"),
            "repeatable": bool(r.get("repeatable")),
            "escort": bool(fx.get("extra", {}).get("escort")),
            "correctedBy": fx.get("from", []),
            "rewards": {"item": [int(x["id"]) for x in rw if x["kind"] == "item"],
                        "choice": [int(x["id"]) for x in rw if x["kind"] == "choice"],
                        "rep": [[int(x["id"]), x.get("count")] for x in rw if x["kind"] == "rep"]},
        }

    npc_quests: dict[int, dict[str, set]] = {}
    obj_quests: dict[int, dict[str, set]] = {}
    item_quests: dict[int, set] = {}
    for qid, q in quests.items():
        for n in q["starters"]["npc"]:
            npc_quests.setdefault(n, {"starts": set(), "ends": set()})["starts"].add(qid)
        for o in q["starters"]["object"]:
            obj_quests.setdefault(o, {"starts": set(), "ends": set()})["starts"].add(qid)
        for i in q["starters"]["item"]:
            item_quests.setdefault(i, set()).add(qid)
        for n in q["finishers"]["npc"]:
            npc_quests.setdefault(n, {"starts": set(), "ends": set()})["ends"].add(qid)
        for o in q["finishers"]["object"]:
            obj_quests.setdefault(o, {"starts": set(), "ends": set()})["ends"].add(qid)
    npc_quests = {k: {kk: sorted(vv) for kk, vv in v.items()} for k, v in npc_quests.items()}
    obj_quests = {k: {kk: sorted(vv) for kk, vv in v.items()} for k, v in obj_quests.items()}

    # -- npcs, objects -----------------------------------------------------------------------
    npcs = {}
    for r in tables["npc"]:
        nid = int(r["id"])
        nq = npc_quests.get(nid, {"starts": [], "ends": []})
        nset = (corr["npcs"].get(str(nid)) or {}).get("set") or {}
        r = {**r, **{k: v for k, v in nset.items() if k in ("name", "rank")}}
        npcs[nid] = {
            "id": nid,
            "name": r.get("name"),
            "subName": r.get("subname"),
            "minLevel": int(r.get("level_min") or 0),
            "maxLevel": int(r.get("level_max") or 0),
            "rank": int(r.get("rank") or 0),
            "spawns": spawns.get(("npc", nid), []),
            "altSpawns": alt.get(("npc", nid), []),
            "world": world.get(("npc", nid), []),
            "waypoints": [],
            "zone": None,
            "questStarts": nq["starts"],
            "questEnds": nq["ends"],
            "factionID": int(r.get("faction_template") or 0),
            "friendlyTo": None,
            "npcFlags": None,             # not in forever-db: QuestieDB (local) only
            "corrected": sorted(set(nset) | set((corr["npcs"].get(str(nid)) or {}).get("addSpawns") or {})),
        }
    objects = {}
    for r in tables["object"]:
        oid = int(r["id"])
        oq = obj_quests.get(oid, {"starts": [], "ends": []})
        objects[oid] = {
            "id": oid,
            "name": r.get("name"),
            "type": r.get("type"),
            "spawns": spawns.get(("object", oid), []),
            "altSpawns": alt.get(("object", oid), []),
            "world": world.get(("object", oid), []),
            "zone": None,
            "questStarts": oq["starts"],
            "questEnds": oq["ends"],
            "factionID": 0,
            "corrected": [],
        }

    # -- items -------------------------------------------------------------------------------
    drops: dict[int, dict[str, list]] = {}
    for r in tables["item_source"]:
        drops.setdefault(int(r["item"]), {"npc": [], "object": []}).setdefault(r["kind"], []).append(int(r["id"]))
    rewarded: dict[int, set] = {}
    related: dict[int, set] = {}
    for qid, q in quests.items():
        for i in q["rewards"]["item"] + q["rewards"]["choice"]:
            rewarded.setdefault(i, set()).add(qid)
        for o in q["objectives"].get("item", []):
            related.setdefault(o["id"], set()).add(qid)
    items = {}
    for r in tables["item"]:
        iid = int(r["id"])
        d = drops.get(iid, {"npc": [], "object": []})
        sq = sorted(item_quests.get(iid, []))
        items[iid] = {
            "id": iid,
            "name": r.get("name"),
            "questItem": bool(r.get("quest_item")),
            "npcDrops": sorted(set(d.get("npc", []))),
            "objectDrops": sorted(set(d.get("object", []))),
            "itemDrops": [],
            "startQuest": sq[0] if sq else 0,
            "questRewards": sorted(rewarded.get(iid, [])),
            "vendors": [],                # not in forever-db
            "relatedQuests": sorted(related.get(iid, [])),
            "itemLevel": 0,
            "requiredLevel": 0,
            "class": 0,
            "subClass": 0,
            "teachesSpell": 0,
            "corrected": [],
        }

    info = {
        "source": "foreverdb",
        "flavor": "forever-db",
        "faction": None,
        "version": index.get("version"),
        "build_commit": index.get("producerCommit"),
        "build_time": None,
        "client_build": index.get("clientBuild"),
        "schema_version": index.get("schemaVersion"),
        "root": str(root),
        "missing": sorted(ForeverDB.MISSING),
        "corrections": {k: len(v) for k, v in corr.items()},
    }
    zones = {"area_to_uimap": {}, "sub_to_parent": {}, "uimap_names": {}, "area_names": {},
             "uimaps": frames.uimaps}
    return {"info": info, "quests": quests, "npcs": npcs, "objects": objects, "items": items,
            "npc_quests": npc_quests, "object_quests": obj_quests,
            "item_quests": {k: sorted(v) for k, v in item_quests.items()}, "zones": zones,
            "_frames": frames}


# --------------------------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------------------------

class ForeverDB(QuestDB):
    """Read-only forever-db with the ``QuestDB`` interface. Use :meth:`open`."""

    SOURCE = "foreverdb"
    # Fields QuestieDB has and forever-db does not: returned as None (or empty) here.
    MISSING = frozenset({"exclusiveTo", "requiredSkill", "npcFlags", "vendors", "waypoints"})

    def __init__(self, data: dict):
        super().__init__(data)
        self.frames: Frames = data["_frames"]

    @classmethod
    def open(cls, foreverdb=None, faction: str = "Alliance", rebuild: bool = False,
             verbose: bool = False, corrections: bool = True, **_ignored) -> "ForeverDB":
        """Load forever-db. ``faction`` is accepted for compatibility (the data covers both).

        ``corrections``: apply forever-db's corrections/*.json and Senda's data/corrections/*.json
        (tools/foreverdb/corrections.py). Default on; False reads the published tables as they are."""
        return cls(_load(resolve_foreverdb(foreverdb), apply_corrections=corrections))

    def to_uimap(self, map_id: int, x: float, y: float) -> list | None:
        """World yards (client Map id, x north, y west) -> [uiMapId, x%, y%] or None."""
        return self.frames.to_uimap(map_id, x, y)

    def _points(self, kind: str, eid: int, alt: bool = True) -> list[tuple[list, str]]:
        ent = self.npc(eid) if kind == "npc" else self.object(eid)
        if not ent:
            return []
        pts = [(s, "spawn") for s in ent["spawns"] if s[1] is not None]
        if alt:
            pts += [(s, "spawn") for s in ent.get("altSpawns", [])]
        return pts

    def entity_points(self, kind: str, eid: int, include_waypoints: bool = True) -> list[list]:
        return [p[:3] for p, _ in self._points(kind, eid, alt=False)]

    def nearest(self, kind: str, eid: int, uimap: int, x: float, y: float):
        best = None
        for p, src in self._points(kind, eid):
            if p[0] != uimap:
                continue
            d = math.hypot(p[1] - x, p[2] - y)
            if best is None or d < best[0]:
                best = (round(d, 2), p[:3], src)
        return best

"""Decoded, cached view of the locally installed QuestieDB (Forever flavor).

LICENSE: QuestieDB data is "all rights reserved". The decoded cache is written ONLY to
``<repo>/.cache/questiedb/`` (gitignored). Never copy decoded data anywhere else in the repo.
"""

from __future__ import annotations

import math
import os
import pickle
import sys
import time
from pathlib import Path

from . import schema as schema_mod
from . import sources, toc
from .constants import class_allowed, classes_in_mask, race_allowed, races_in_mask

CACHE_VERSION = 3
DEFAULT_QUESTIEDB = Path(r"E:\World of Warcraft\_forever_\Interface\AddOns\QuestieDB")
REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = REPO_ROOT / ".cache" / "questiedb"
FLAVOR = "Forever"


def resolve_questiedb(path: str | os.PathLike | None = None) -> Path:
    candidate = path or os.environ.get("SENDA_QUESTIEDB") or DEFAULT_QUESTIEDB
    root = Path(candidate)
    if root.is_file():
        root = root.parent
    if not (root / f"QuestieDB_{FLAVOR}.toc").exists():
        raise FileNotFoundError(f"QuestieDB_{FLAVOR}.toc not found under {root} "
                                f"(use --questiedb or SENDA_QUESTIEDB)")
    return root


# --------------------------------------------------------------------------------------------
# Lua-shaped value helpers (CBOR arrays are Lua sequences starting at key 1)
# --------------------------------------------------------------------------------------------

def lua_get(value, key):
    if isinstance(value, list):
        if isinstance(key, int) and 1 <= key <= len(value):
            return value[key - 1]
        return None
    if isinstance(value, dict):
        return value.get(key)
    return None


def lua_items(value):
    if isinstance(value, list):
        return [(i, v) for i, v in enumerate(value, 1) if v is not None]
    if isinstance(value, dict):
        return sorted(((k, v) for k, v in value.items() if v is not None), key=lambda kv: (str(type(kv[0])), kv[0]))
    return []


def seq(value) -> list:
    return [v for _, v in lua_items(value)]


def ids(value) -> list[int]:
    return [int(v) for v in seq(value) if isinstance(v, (int, float)) and not isinstance(v, bool)]


def num(value, default=0):
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, (int, float)):
        return int(value) if float(value).is_integer() else value
    return default


def pair(value):
    a, b = lua_get(value, 1), lua_get(value, 2)
    if (a or 0) == 0 and (b or 0) == 0:
        return None
    return [a, b]


def faction_norm(value):
    if value in (None, ""):
        return None
    if value in ("A", "H"):
        return value
    return "AH"


# --------------------------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------------------------

def _signature(root: Path, faction: str) -> dict:
    files = [root / f"QuestieDB_{FLAVOR}.toc"]
    files += sorted((root / "src" / "meta").glob("*Meta.lua"))
    files += sorted((root / "src" / "corrections").rglob("*.lua"))
    files += sorted((root / "support" / "Forever" / "Zones").glob("*.lua"))
    bl = root.parent / "Questie" / "Database" / "Corrections" / "QuestieQuestBlacklist.lua"
    if bl.exists():
        files.append(bl)
    stamp = {str(f.relative_to(root.parent)): (f.stat().st_size, f.stat().st_mtime_ns) for f in files}
    return {"version": CACHE_VERSION, "root": str(root), "faction": faction, "files": stamp}


class _Builder:
    def __init__(self, root: Path, faction: str, log=None):
        self.root = root
        self.faction = faction
        self.log = log or (lambda msg: None)

    def build(self) -> dict:
        t0 = time.time()
        schemas = schema_mod.load_schema(self.root)
        self.zones = sources.Zones(self.root)
        enums = sources.load_enums(self.root)
        corrections, skipped = sources.load_dynamic_corrections(self.root, schemas, enums, self.faction)
        questie_root = self.root.parent / "Questie"
        blacklist = sources.load_questie_blacklist(questie_root if questie_root.exists() else None)
        self.log(f"reading {FLAVOR} TOC ...")
        meta = toc.read_metadata(self.root / f"QuestieDB_{FLAVOR}.toc")
        store = toc.MetaStore(meta)
        self.sort_names = {v: k for k, v in enums.get("sortKeys", {}).items() if isinstance(v, int)}

        raw: dict[str, dict[int, dict]] = {}
        for entity, sch in schemas.items():
            ids_list = store.ids(sch.prefix)
            rows = {}
            for eid in ids_list:
                fields = store.entity(sch.prefix, eid, sch.types)
                if fields is not None:
                    rows[eid] = fields
            for eid, fix in corrections.get(entity, {}).items():
                row = rows.setdefault(eid, {})
                for field, value in fix.items():
                    if value in ([], {}, None):
                        row.pop(field, None)
                    else:
                        row[field] = value
                row.setdefault("_corrected", []).extend(sorted(fix))
            raw[entity] = rows
            self.log(f"decoded {len(rows)} {entity} rows")

        quests = {qid: self.quest(qid, r, schemas["Quest"].keys, blacklist.get(qid)) for qid, r in raw["Quest"].items()}
        npcs = {nid: self.npc(nid, r, schemas["Npc"].keys) for nid, r in raw["Npc"].items()}
        objects = {oid: self.object(oid, r, schemas["Object"].keys) for oid, r in raw["Object"].items()}
        items = {iid: self.item(iid, r, schemas["Item"].keys) for iid, r in raw["Item"].items()}

        npc_quests: dict[int, dict[str, set]] = {}
        obj_quests: dict[int, dict[str, set]] = {}
        item_quests: dict[int, set] = {}

        def add(index, key, kind, qid):
            index.setdefault(key, {"starts": set(), "ends": set()})[kind].add(qid)

        for qid, q in quests.items():
            for n in q["starters"]["npc"]:
                add(npc_quests, n, "starts", qid)
            for o in q["starters"]["object"]:
                add(obj_quests, o, "starts", qid)
            for i in q["starters"]["item"]:
                item_quests.setdefault(i, set()).add(qid)
            for n in q["finishers"]["npc"]:
                add(npc_quests, n, "ends", qid)
            for o in q["finishers"]["object"]:
                add(obj_quests, o, "ends", qid)
        npc_quests = {k: {kk: sorted(vv) for kk, vv in v.items()} for k, v in npc_quests.items()}
        obj_quests = {k: {kk: sorted(vv) for kk, vv in v.items()} for k, v in obj_quests.items()}

        info = {
            "flavor": FLAVOR,
            "faction": self.faction,
            "version": meta.get("Contract-Version"),
            "build_commit": meta.get("BUILD-COMMIT"),
            "build_time": meta.get("BUILD-TIME"),
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "build_seconds": round(time.time() - t0, 1),
            "dynamic_corrections": {k: len(v) for k, v in corrections.items()},
            "skipped_corrections": [list(s) for s in skipped],
            "blacklisted": len(blacklist),
        }
        return {"info": info, "quests": quests, "npcs": npcs, "objects": objects, "items": items,
                "npc_quests": npc_quests, "object_quests": obj_quests,
                "item_quests": {k: sorted(v) for k, v in item_quests.items()},
                "zones": self.zones.to_dict()}

    # -- entity shapers ---------------------------------------------------------------------

    def zone_of(self, zone_or_sort):
        z = num(zone_or_sort)
        if z > 0:
            return {"areaId": z, "uiMapId": self.zones.uimap(z), "name": self.zones.area_names.get(z)}
        if z < 0:
            return {"sort": z, "name": self.sort_names.get(z)}
        return None

    def spawns(self, value):
        out = []
        for area, rows in lua_items(value):
            if not isinstance(area, int):
                continue
            uimap = self.zones.uimap(area)
            for _, row in lua_items(rows):
                x, y = lua_get(row, 1), lua_get(row, 2)
                if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                    continue
                if x == -1 and y == -1:
                    out.append([uimap, None, None, area])
                    continue
                out.append([uimap, round(float(x), 2), round(float(y), 2), area])
        return out

    def waypoints(self, value):
        out = []
        for area, paths in lua_items(value):
            if not isinstance(area, int):
                continue
            uimap = self.zones.uimap(area)
            for _, path in lua_items(paths):
                for _, row in lua_items(path):
                    x, y = lua_get(row, 1), lua_get(row, 2)
                    if isinstance(x, (int, float)) and isinstance(y, (int, float)) and x >= 0:
                        out.append([uimap, round(float(x), 2), round(float(y), 2), area])
        return out

    def quest(self, qid, r, k, hidden):
        def f(name):
            return r.get(k.get(name))

        sb, fb = f("startedBy"), f("finishedBy")
        obj = f("objectives")
        objectives = {
            "creature": [{"id": num(lua_get(o, 1)), "text": lua_get(o, 2)} for o in seq(lua_get(obj, 1))],
            "object": [{"id": num(lua_get(o, 1)), "text": lua_get(o, 2)} for o in seq(lua_get(obj, 2))],
            "item": [{"id": num(lua_get(o, 1)), "text": lua_get(o, 2)} for o in seq(lua_get(obj, 3))],
            "reputation": pair(lua_get(obj, 4)),
            "killCredit": [{"ids": ids(lua_get(o, 1)), "baseId": num(lua_get(o, 2)), "text": lua_get(o, 3)}
                           for o in seq(lua_get(obj, 5))],
            "spell": [{"id": num(lua_get(o, 1)), "text": lua_get(o, 2), "item": num(lua_get(o, 3))}
                      for o in seq(lua_get(obj, 6))],
        }
        objectives = {kk: v for kk, v in objectives.items() if v}
        trig = f("triggerEnd")
        trigger = None
        if trig:
            trigger = {"text": lua_get(trig, 1), "spawns": self.spawns(lua_get(trig, 2))}
        extra = f("extraObjectives")
        return {
            "id": qid,
            "name": f("name"),
            "level": num(f("questLevel")),
            "requiredLevel": num(f("requiredLevel")),
            "requiredMaxLevel": num(f("requiredMaxLevel")),
            "races": num(f("requiredRaces")),
            "classes": num(f("requiredClasses")),
            "starters": {"npc": ids(lua_get(sb, 1)), "object": ids(lua_get(sb, 2)), "item": ids(lua_get(sb, 3))},
            "finishers": {"npc": ids(lua_get(fb, 1)), "object": ids(lua_get(fb, 2))},
            "preQuestGroup": ids(f("preQuestGroup")),
            "preQuestSingle": ids(f("preQuestSingle")),
            "childQuests": ids(f("childQuests")),
            "inGroupWith": ids(f("inGroupWith")),
            "exclusiveTo": ids(f("exclusiveTo")),
            "nextQuestInChain": num(f("nextQuestInChain")),
            "parentQuest": num(f("parentQuest")),
            "breadcrumbFor": num(f("breadcrumbForQuestId")),
            "breadcrumbs": ids(f("breadcrumbs")),
            "zone": self.zone_of(f("zoneOrSort")),
            "objectivesText": [s for s in seq(f("objectivesText")) if isinstance(s, str)],
            "objectives": objectives,
            "trigger": trigger,
            "extraObjectives": len(seq(extra)),
            "sourceItemId": num(f("sourceItemId")),
            "requiredSkill": pair(f("requiredSkill")),
            "requiredMinRep": pair(f("requiredMinRep")),
            "requiredMaxRep": pair(f("requiredMaxRep")),
            "requiredSpell": num(f("requiredSpell")),
            "questFlags": num(f("questFlags")),
            "specialFlags": num(f("specialFlags")),
            "availableStartingWith": num(f("availableStartingWith")),
            "availableUntilCompleted": num(f("availableUntilCompleted")),
            "hidden": hidden,
            "corrected": r.get("_corrected", []),
        }

    def npc(self, nid, r, k):
        def f(name):
            return r.get(k.get(name))

        zone_area = num(f("zoneID"))
        return {
            "id": nid,
            "name": f("name"),
            "subName": f("subName"),
            "minLevel": num(f("minLevel")),
            "maxLevel": num(f("maxLevel")),
            "rank": num(f("rank")),
            "spawns": self.spawns(f("spawns")),
            "waypoints": self.waypoints(f("waypoints")),
            "zone": {"areaId": zone_area, "uiMapId": self.zones.uimap(zone_area)} if zone_area else None,
            "questStarts": ids(f("questStarts")),
            "questEnds": ids(f("questEnds")),
            "factionID": num(f("factionID")),
            "friendlyTo": faction_norm(f("friendlyToFaction")),
            "npcFlags": num(f("npcFlags")),
            "corrected": r.get("_corrected", []),
        }

    def object(self, oid, r, k):
        def f(name):
            return r.get(k.get(name))

        zone_area = num(f("zoneID"))
        return {
            "id": oid,
            "name": f("name"),
            "spawns": self.spawns(f("spawns")),
            "zone": {"areaId": zone_area, "uiMapId": self.zones.uimap(zone_area)} if zone_area else None,
            "questStarts": ids(f("questStarts")),
            "questEnds": ids(f("questEnds")),
            "factionID": num(f("factionID")),
            "corrected": r.get("_corrected", []),
        }

    def item(self, iid, r, k):
        def f(name):
            return r.get(k.get(name))

        return {
            "id": iid,
            "name": f("name"),
            "npcDrops": ids(f("npcDrops")),
            "objectDrops": ids(f("objectDrops")),
            "itemDrops": ids(f("itemDrops")),
            "startQuest": num(f("startQuest")),
            "questRewards": ids(f("questRewards")),
            "vendors": ids(f("vendors")),
            "relatedQuests": ids(f("relatedQuests")),
            "itemLevel": num(f("itemLevel")),
            "requiredLevel": num(f("requiredLevel")),
            "class": num(f("class")),
            "subClass": num(f("subClass")),
            "teachesSpell": num(f("teachesSpell")),
            "corrected": r.get("_corrected", []),
        }


# --------------------------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------------------------

class QuestDB:
    """Read-only access to decoded QuestieDB data. Use :meth:`open`."""

    def __init__(self, data: dict):
        self.data = data
        self.info = data["info"]
        self.quests: dict[int, dict] = data["quests"]
        self.npcs: dict[int, dict] = data["npcs"]
        self.objects: dict[int, dict] = data["objects"]
        self.items: dict[int, dict] = data["items"]
        self.zones = data["zones"]

    @classmethod
    def open(cls, questiedb=None, faction: str = "Alliance", rebuild: bool = False,
             cache_dir: Path | None = None, verbose: bool = False) -> "QuestDB":
        root = resolve_questiedb(questiedb)
        faction = "Horde" if faction.lower().startswith("h") else "Alliance"
        cache_dir = Path(cache_dir or CACHE_DIR)
        cache_file = cache_dir / f"{FLAVOR.lower()}-{faction.lower()}.pickle"
        sig = _signature(root, faction)
        if not rebuild and cache_file.exists():
            try:
                with open(cache_file, "rb") as fh:
                    cached = pickle.load(fh)
                if cached.get("signature") == sig:
                    return cls(cached["data"])
            except Exception:  # corrupt/old cache: rebuild
                pass
        log = (lambda m: print(f"[questiedb] {m}", file=sys.stderr)) if verbose else None
        if verbose is False:
            print("[questiedb] building decoded cache (first run or QuestieDB changed) ...", file=sys.stderr)
        data = _Builder(root, faction, log).build()
        cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = cache_file.with_suffix(".tmp")
        with open(tmp, "wb") as fh:
            pickle.dump({"signature": sig, "data": data}, fh, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, cache_file)
        return cls(data)

    # -- entities ----------------------------------------------------------------------------

    def quest(self, qid: int) -> dict | None:
        return self.quests.get(int(qid))

    def npc(self, nid: int) -> dict | None:
        return self.npcs.get(int(nid))

    def object(self, oid: int) -> dict | None:
        return self.objects.get(int(oid))

    def item(self, iid: int) -> dict | None:
        return self.items.get(int(iid))

    def npc_quests(self, nid: int) -> dict:
        """Reverse index: {"starts": [questIds], "ends": [questIds]} (from quest starters/finishers)."""
        base = self.data["npc_quests"].get(int(nid), {"starts": [], "ends": []})
        n = self.npc(nid)
        if n:  # union with the NPC's own questStarts/questEnds fields
            return {"starts": sorted(set(base["starts"]) | set(n["questStarts"])),
                    "ends": sorted(set(base["ends"]) | set(n["questEnds"]))}
        return base

    def object_quests(self, oid: int) -> dict:
        base = self.data["object_quests"].get(int(oid), {"starts": [], "ends": []})
        o = self.object(oid)
        if o:
            return {"starts": sorted(set(base["starts"]) | set(o["questStarts"])),
                    "ends": sorted(set(base["ends"]) | set(o["questEnds"]))}
        return base

    def is_starter(self, qid: int, npc: int) -> bool:
        q = self.quest(qid)
        return bool(q) and (npc in q["starters"]["npc"] or qid in self.npc_quests(npc)["starts"])

    def is_finisher(self, qid: int, npc: int) -> bool:
        q = self.quest(qid)
        return bool(q) and (npc in q["finishers"]["npc"] or qid in self.npc_quests(npc)["ends"])

    # -- zones -------------------------------------------------------------------------------

    def uimap_for_area(self, area: int) -> int | None:
        a2u = self.zones["area_to_uimap"]
        if area in a2u:
            return a2u[area] or None
        parent = self.zones["sub_to_parent"]
        seen = set()
        while area in parent and area not in seen:
            seen.add(area)
            area = parent[area]
            if area in a2u:
                return a2u[area] or None
        return None

    def map_name(self, uimap: int | None) -> str | None:
        return self.zones["uimap_names"].get(uimap) if uimap else None

    # -- derived helpers ---------------------------------------------------------------------

    def can_take(self, qid: int, race: str | None = None, cls: str | None = None, faction: str | None = None) -> bool:
        q = self.quest(qid)
        if not q:
            return False
        if race and not race_allowed(q["races"], race, faction):
            return False
        if cls and not class_allowed(q["classes"], cls):
            return False
        return True

    def entity_points(self, kind: str, eid: int, include_waypoints: bool = True) -> list[list]:
        """[[uiMapId, x, y], ...] for an npc/object (spawns, then waypoint path points)."""
        ent = self.npc(eid) if kind == "npc" else self.object(eid)
        if not ent:
            return []
        pts = [s[:3] for s in ent["spawns"] if s[1] is not None]
        if include_waypoints and kind == "npc":
            pts += [w[:3] for w in ent.get("waypoints", [])]
        return pts

    def nearest(self, kind: str, eid: int, uimap: int, x: float, y: float):
        """(distance in map %, [uiMap, x, y], source) of the closest point on the same map, or None."""
        best = None
        ent = self.npc(eid) if kind == "npc" else self.object(eid)
        if not ent:
            return None
        cands = [(s, "spawn") for s in ent["spawns"] if s[1] is not None]
        if kind == "npc":
            cands += [(w, "waypoint") for w in ent.get("waypoints", [])]
        for p, src in cands:
            if p[0] != uimap:
                continue
            d = math.hypot(p[1] - x, p[2] - y)
            if best is None or d < best[0]:
                best = (round(d, 2), p[:3], src)
        return best

    def starter_locations(self, qid: int, uimap: int | None = None) -> list[dict]:
        q = self.quest(qid)
        out = []
        if not q:
            return out
        for kind in ("npc", "object"):
            for eid in q["starters"][kind]:
                ent = self.npc(eid) if kind == "npc" else self.object(eid)
                spawns = [s for s in (ent["spawns"] if ent else []) if s[1] is not None]
                if uimap is not None:
                    spawns = [s for s in spawns if s[0] == uimap]
                out.append({"kind": kind, "id": eid, "name": ent["name"] if ent else None,
                            "spawns": [s[:3] for s in spawns]})
        for iid in q["starters"]["item"]:
            it = self.item(iid)
            out.append({"kind": "item", "id": iid, "name": it["name"] if it else None, "spawns": []})
        return out

    def search(self, text: str, kinds=("quest", "npc", "object", "item", "zone"), limit: int = 50) -> list[dict]:
        needle = text.lower().strip()
        out = []
        num_id = int(needle) if needle.isdigit() else None
        tables = {"quest": self.quests, "npc": self.npcs, "object": self.objects, "item": self.items}
        for kind in kinds:
            if kind == "zone":
                for area, name in self.zones["area_names"].items():
                    if needle in name.lower():
                        out.append({"kind": "zone", "areaId": area, "uiMapId": self.uimap_for_area(area), "name": name})
                for uimap, name in self.zones["uimap_names"].items():
                    if needle in name.lower():
                        out.append({"kind": "map", "uiMapId": uimap, "name": name})
                continue
            for eid, ent in tables[kind].items():
                name = ent.get("name") or ""
                if needle in name.lower() or (num_id is not None and eid == num_id):
                    row = {"kind": kind, "id": eid, "name": name}
                    if kind == "quest":
                        row["level"] = ent["level"]
                        row["requiredLevel"] = ent["requiredLevel"]
                    elif kind == "npc":
                        row["maps"] = sorted({s[0] for s in ent["spawns"] if s[0]})
                    out.append(row)
        exact = [r for r in out if (r.get("name") or "").lower() == needle]
        rest = [r for r in out if r not in exact]
        return (exact + rest)[:limit] if limit else exact + rest

    def chain(self, qid: int, max_depth: int = 30) -> dict:
        """Prerequisites (backward) and follow-ups (forward) around a quest."""
        if not self.quest(qid):
            return {}
        followers: dict[int, set] = {}
        for oid, q in self.quests.items():
            for p in q["preQuestSingle"] + q["preQuestGroup"]:
                followers.setdefault(p, set()).add(oid)

        def back(i, depth, seen):
            q = self.quest(i)
            if not q or depth > max_depth or i in seen:
                return []
            seen = seen | {i}
            out = []
            for p in q["preQuestGroup"]:
                out.append({"id": p, "name": (self.quest(p) or {}).get("name"), "mode": "all",
                            "pre": back(p, depth + 1, seen)})
            for p in q["preQuestSingle"]:
                out.append({"id": p, "name": (self.quest(p) or {}).get("name"), "mode": "any",
                            "pre": back(p, depth + 1, seen)})
            return out

        def fwd(i, depth, seen):
            q = self.quest(i)
            if not q or depth > max_depth or i in seen:
                return []
            seen = seen | {i}
            nxt = set(followers.get(i, set())) | set(q["childQuests"])
            if q["nextQuestInChain"]:
                nxt.add(q["nextQuestInChain"])
            return [{"id": n, "name": (self.quest(n) or {}).get("name"), "next": fwd(n, depth + 1, seen)}
                    for n in sorted(nxt)]

        q = self.quest(qid)
        return {"id": qid, "name": q["name"], "prerequisites": back(qid, 0, set()), "followups": fwd(qid, 0, set()),
                "exclusiveTo": q["exclusiveTo"], "breadcrumbs": q["breadcrumbs"], "breadcrumbFor": q["breadcrumbFor"]}

    def zone_quests(self, uimap: int, race: str | None = None, cls: str | None = None, faction: str | None = None,
                    max_level: int | None = None, min_level: int | None = None, include_hidden: bool = False) -> list[dict]:
        """Quests whose starter spawns in ``uimap`` (or whose zone is ``uimap``), filtered."""
        out = []
        for qid, q in self.quests.items():
            if q["hidden"] == "hidden" and not include_hidden:
                continue
            if race and not race_allowed(q["races"], race, faction):
                continue
            if cls and not class_allowed(q["classes"], cls):
                continue
            if max_level is not None and q["requiredLevel"] > max_level:
                continue
            if min_level is not None and q["requiredMaxLevel"] and q["requiredMaxLevel"] < min_level:
                continue
            starters = self.starter_locations(qid, uimap)
            in_zone_start = any(s["spawns"] for s in starters)
            zone_match = bool(q["zone"] and q["zone"].get("uiMapId") == uimap)
            if not in_zone_start and not zone_match:
                continue
            if not in_zone_start and (q["starters"]["npc"] or q["starters"]["object"]):
                # zone tag says this map but starters are elsewhere: still list, flagged
                pass
            out.append({
                "id": qid, "name": q["name"], "level": q["level"], "requiredLevel": q["requiredLevel"],
                "races": races_in_mask(q["races"]), "classes": classes_in_mask(q["classes"]),
                "starters": starters, "startsInZone": in_zone_start, "zoneTagMatch": zone_match,
                "preQuestSingle": q["preQuestSingle"], "preQuestGroup": q["preQuestGroup"],
                "hidden": q["hidden"],
            })
        out.sort(key=lambda r: (r["requiredLevel"], r["level"], r["id"]))
        return out

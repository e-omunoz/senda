#!/usr/bin/env python3
"""Item lookup dataset ("Se consigue en: ...") from forever-db. Writes data/lookup/.

Reads forever-db (Polestar's open quest data, GPL-3; its own layer CC BY 4.0; credits in
THIRD_PARTY.md and forever-db/NOTICE.md): item_source (drops by npc/object, container items,
loot chance), quest_reward (item/choice), spawn + ui_map (one representative place per source).
Nothing else is read from outside the repo: no QuestieDB, no Leffe maps, no DingDB.

Outputs (deterministic, sorted keys):
  data/lookup/items.json     item -> sources and rewarding quests
  data/lookup/places.json    npc/object -> one representative place (uiMap, x%, y%, map, spawns)
  data/lookup/coverage.json  coverage of the items Senda's guides use, with the misses
  data/lookup/locale/enUS/items.json  English item names of forever-db for the lookup items (source
                             "forever-db", the lowest priority: names that /senda volcar read in the game and
                             tools/import_names.py ingested (data/lookup/locale/<locale>/) always win)

Usage: python -I tools/gen_lookup.py [--foreverdb DIR] [--out DIR] [--check]
forever-db root: --foreverdb, env SENDA_FOREVERDB, or <repo>/.cache/foreverdb.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
import tomllib
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import localenames as ln  # noqa: E402
from foreverdb.db import Frames, read_jsonl, resolve_foreverdb  # noqa: E402

MAX_SOURCES = 8       # sources kept per item (best chance first); the true total goes in "n"
MAX_QUESTS = 6        # rewarding quests kept per item; the true total goes in "nq"
GUIDE_DIRS = ("data/guides", "data/shared")
NAME_SOURCE = "forever-db"


def dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def num(v):
    """Trim floats: 6.0 -> 6, 6.64 -> 6.6."""
    v = round(float(v), 1)
    return int(v) if v.is_integer() else v


def medoid(points):
    """The spawn closest to the centroid of the points on the busiest map: one representative
    spot for an entity (a real position, never an average that could lie in a wall)."""
    by_map = defaultdict(list)
    for m, x, y in points:
        by_map[m].append((x, y))
    m = max(sorted(by_map), key=lambda k: len(by_map[k]))
    pts = by_map[m]
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    x, y = min(pts, key=lambda p: ((p[0] - cx) ** 2 + (p[1] - cy) ** 2, p))
    return m, x, y, len(points)


def guide_usage():
    """Quests and items that Senda's guides mention (read-only)."""
    quests, items, files = set(), set(), 0
    vendors, loots = {}, {}   # item -> {npc: (ui, x, y)} / {(ui, x, y)}, from steps sourced by Polestar
    for d in GUIDE_DIRS:
        for f in sorted((REPO / d).rglob("*.toml")):
            try:
                doc = tomllib.loads(f.read_text(encoding="utf-8"))
            except Exception as e:  # a half-written file from another workflow: skip, say so
                print(f"  skipped {f.relative_to(REPO)}: {str(e)[:60]}", file=sys.stderr)
                continue
            files += 1
            for s in doc.get("step", []):
                if isinstance(s.get("quest"), int):
                    quests.add(s["quest"])
                for q in s.get("quests") or []:
                    if isinstance(q, int):
                        quests.add(q)
                if isinstance(s.get("item"), int):
                    items.add(s["item"])
                    # only facts the guide took from Polestar (GPL-3); steps sourced only from
                    # QuestieDB are not turned into dataset rows (nothing from QuestieDB is committed)
                    polestar = any(str(x).startswith("polestar:") for x in s.get("sources", []))
                    at = s.get("at")
                    if polestar and isinstance(at, list) and len(at) == 3:
                        place = (int(at[0]), num(at[1]), num(at[2]))
                        if s.get("do") == "buy" and isinstance(s.get("npc"), int):
                            vendors.setdefault(s["item"], {}).setdefault(s["npc"], place)
                        elif s.get("do") in ("loot", "use") and not s.get("npc"):
                            loots.setdefault(s["item"], set()).add(place)
    return quests, items, files, vendors, loots


def write_names(out, names, ids):
    """English names for the lookup (search by name before the game has told us the real ones). Merged through
    localenames, so a name read in the game (source ingame:..., tools/import_names.py) is never overwritten."""
    nm = ln.load(out, "enUS")
    for it in ids:
        if names.get(it):
            ln.merge(nm, "item", it, names[it], NAME_SOURCE)
    return ln.save(out, "enUS", nm, kinds=["item"])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--foreverdb")
    ap.add_argument("--out", default=str(REPO / "data" / "lookup"))
    ap.add_argument("--check", action="store_true", help="exit 1 if coverage < 95%%")
    ap.add_argument("--names-only", action="store_true",
                    help="only (re)write data/lookup/locale/enUS/items.json for the items already in "
                         "data/lookup/items.json (no guides needed)")
    a = ap.parse_args()

    root = resolve_foreverdb(a.foreverdb)
    dd = root / "data"
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    version, build = index.get("version"), index.get("clientBuild")

    names = {r["id"]: r["name"] for r in read_jsonl(dd / "item.jsonl")}
    if a.names_only:
        out = Path(a.out)
        ids = [int(i) for i in json.loads((out / "items.json").read_text(encoding="utf-8"))["items"]]
        changed = write_names(out, names, ids)
        print(f"names: {sum(1 for i in ids if i in names)}/{len(ids)} items named by forever-db "
              f"({len(changed)} file written)")
        return
    sources = defaultdict(list)       # item -> [(kind, id, chance|None)]
    for r in read_jsonl(dd / "item_source.jsonl"):
        sources[r["item"]].append((r["kind"], r["id"], r.get("chance")))
    # hand-checked fixes of forever-db (corrections/items.json), applied on top of the tables: the
    # release can predate them. removeDrops drops a wrong source, addDrops adds one (no rate).
    fixes = {}
    cf = root / "corrections" / "items.json"
    if cf.exists():
        fixes = json.loads(cf.read_text(encoding="utf-8"))
    n_removed = n_added = 0
    for it_s, fx in fixes.items():
        it = int(it_s)
        for kind in ("npc", "object"):
            gone = set(fx.get("removeDrops", {}).get(kind, []))
            before = len(sources[it])
            sources[it] = [s for s in sources[it] if not (s[0] == kind and s[1] in gone)]
            n_removed += before - len(sources[it])
            have = {(s[0], s[1]) for s in sources[it]}
            for eid in fx.get("addDrops", {}).get(kind, []):
                if (kind, eid) not in have:
                    sources[it].append((kind, eid, None))
                    n_added += 1
    rewards = defaultdict(list)       # item -> [(quest, kind, count)]
    q_reward = defaultdict(set)       # quest -> reward items
    for r in read_jsonl(dd / "quest_reward.jsonl"):
        if r["kind"] in ("item", "choice"):
            rewards[r["id"]].append((r["quest"], r["kind"], r.get("count", 1)))
            q_reward[r["quest"]].add(r["id"])
    q_objective = defaultdict(set)    # quest -> items it asks for
    q_item_obj = defaultdict(set)     # item -> quests that ask for it
    for r in read_jsonl(dd / "quest_objective.jsonl"):
        if r["kind"] == "item":
            q_objective[r["quest"]].add(r["target"])
            q_item_obj[r["target"]].add(r["quest"])
    forever_quests = {r["id"] for r in read_jsonl(dd / "quest.jsonl")}

    spawns = defaultdict(list)
    for r in read_jsonl(dd / "spawn.jsonl"):
        spawns[(r["kind"], r["id"])].append((r["map"], r["x"], r["y"]))
    frames = Frames(read_jsonl(dd / "ui_map.jsonl"))

    gq, step_items, nfiles, vendors, loots = guide_usage()

    # ---- items.json ----
    items = {}
    wanted = {"npc": set(), "object": set()}
    for it in sorted(set(sources) | set(rewards) | set(vendors) | set(loots) | set(q_item_obj)):
        e = {}
        srcs = sorted(sources.get(it, []), key=lambda s: (-(s[2] if s[2] is not None else -1), s[0], s[1]))
        if srcs:
            e["s"] = []
            for kind, sid, ch in srcs[:MAX_SOURCES]:
                e["s"].append([kind[0], sid] + ([num(ch)] if ch is not None else []))
                if kind in wanted:
                    wanted[kind].add(sid)
            if len(srcs) > MAX_SOURCES:
                e["n"] = len(srcs)
        rw = sorted(rewards.get(it, []))
        if rw:
            e["q"] = [[q, 1 if k == "choice" else 0] for q, k, _ in rw[:MAX_QUESTS]]
            if len(rw) > MAX_QUESTS:
                e["nq"] = len(rw)
        if it in vendors:   # sold by an npc, from the guides' "buy" steps
            e["v"] = [[n] for n in sorted(vendors[it])]
            wanted["npc"].update(vendors[it])
        if it in loots and "s" not in e and it not in vendors:   # only a place in the route
            e["g"] = [list(p) for p in sorted(loots[it])[:2]]
        if "s" not in e and "v" not in e and "q" not in e and "g" not in e:   # only an objective link
            e["o"] = sorted(q_item_obj[it])[:3]
            if len(q_item_obj[it]) > 3:
                e["no"] = len(q_item_obj[it])
        items[str(it)] = e

    # container items: resolve one level so the line can say where the container drops
    kmap = {"n": "npc", "o": "object"}
    for e in items.values():
        for row in e.get("s", []):
            if row[0] == "i":
                for r2 in items.get(str(row[1]), {}).get("s", []):
                    if r2[0] in kmap:
                        wanted[kmap[r2[0]]].add(r2[1])

    # ---- places.json ----
    places = {"n": {}, "o": {}}
    no_spawn = Counter()
    for kind, key in (("npc", "n"), ("object", "o")):
        for eid in sorted(wanted[kind]):
            pts = spawns.get((kind, eid))
            if not pts:
                fb = next((v[eid] for v in vendors.values() if eid in v), None) if kind == "npc" else None
                if fb:   # a vendor without a spawn row: the place the guide step gives
                    places[key][str(eid)] = [fb[0], fb[1], fb[2], -1, 0]
                    continue
                no_spawn[kind] += 1
                continue
            m, x, y, total = medoid(pts)
            hit = frames.to_uimap(m, float(x), float(y))
            if hit:
                places[key][str(eid)] = [hit[0], num(hit[1]), num(hit[2]), m, total]
            else:  # instance or no frame: keep world yards
                places[key][str(eid)] = [0, num(x), num(y), m, total]

    # ---- coverage over the items Senda's guides use ----
    cats = {"step_item": set(step_items),
            "objective": set().union(*(q_objective[q] for q in gq)),
            "reward": set().union(*(q_reward[q] for q in gq))}
    all_g = set().union(*cats.values())

    def cov(s, f):
        ok = sum(1 for i in s if f(i))
        return {"total": len(s), "with_source": ok, "pct": round(100 * ok / len(s), 2) if s else None,
                "misses": [[i, names.get(i, "?")] for i in sorted(s) if not f(i)]}

    def any_src(i):      # tier 1: a real way to get it (drop, object, vendor, quest reward, route place)
        e = items.get(str(i), {})
        return any(k in e for k in ("s", "v", "q", "g"))

    def world_src(i):    # tier 1 without quest rewards
        e = items.get(str(i), {})
        return any(k in e for k in ("s", "v", "g"))

    def line_ok(i):      # tier 1 or tier 2: the tooltip line has something to say
        return any_src(i) or "o" in items.get(str(i), {})

    def placed(i):       # tier 1 and the first source resolves to a map place
        e = items.get(str(i), {})
        for r in e.get("s", []):
            if r[0] == "i" or str(r[1]) in places.get(r[0], {}):
                return True
        if any(str(r[0]) in places["n"] for r in e.get("v", [])):
            return True
        return bool(e.get("g") or e.get("q"))

    coverage = {
        "forever_db": {"version": version, "client_build": build},
        "guides": {"toml_files": nfiles, "quests_used": len(gq),
                   "quests_missing_in_forever_db": sorted(gq - forever_quests)},
        "any_source": {"all": cov(all_g, any_src), **{k: cov(v, any_src) for k, v in cats.items()}},
        "drop_or_object_source": {"all": cov(all_g, world_src),
                                  **{k: cov(v, world_src) for k, v in cats.items() if k != "reward"}},
        "with_place_or_reward": cov(all_g, placed),
        "tier1_or_quest_objective_link": cov(all_g, line_ok),
        "places": {"npc_sources": len(wanted["npc"]), "object_sources": len(wanted["object"]),
                   "without_spawn": dict(no_spawn),
                   "resolved": {"n": len(places["n"]), "o": len(places["o"])}},
    }

    meta = {"source": "forever-db (fitzforge/polestar), GPL-3.0; CC BY 4.0 layer; see docs/LOOKUP.md",
            "forever_db_version": version, "client_build": build,
            "max_sources_per_item": MAX_SOURCES, "max_quests_per_item": MAX_QUESTS,
            "schema": "items: {itemId: {s:[[kind n|o|i, id, chance%?]] drops, n?:total drop sources, "
                      "v:[[npcId]] vendors, g:[[uiMap,x,y]] place in the route, "
                      "q:[[questId, 1 if choice]] rewards, nq?, o:[questId] objective only, no?}}; places: {n|o: {id: "
                      "[uiMapId, x%, y%, mapId, spawnCount]}} (uiMap 0 = no frame: x/y in world yards; mapId -1 = place taken from a guide step)"}

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    files = {"items.json": {"meta": meta, "items": items},
             "places.json": {"meta": meta, "places": places},
             "coverage.json": coverage}
    for name, obj in files.items():
        (out / name).write_text(dump(obj) + "\n", encoding="utf-8", newline="\n")

    write_names(out, names, [int(i) for i in items])

    kinds = Counter(r[0] for e in items.values() for r in e.get("s", []))
    print(f"forever-db {version} (client {build})")
    print(f"items: {len(items)} ({sum(1 for e in items.values() if 's' in e)} with drop/object source, "
          f"{sum(1 for e in items.values() if 'q' in e)} with quest reward); source rows by kind: {dict(kinds)}")
    print(f"corrections applied: {n_removed} drop rows removed, {n_added} added")
    print(f"truncated: {sum(1 for e in items.values() if 'n' in e)} items with >{MAX_SOURCES} sources")
    print(f"places: {len(places['n'])} npcs, {len(places['o'])} objects; without spawn: {dict(no_spawn)}")
    for n in files:
        p = out / n
        print(f"  {n}: {p.stat().st_size / 1024:.0f} KB raw, {len(gzip.compress(p.read_bytes())) / 1024:.0f} KB gzip")
    g = coverage["any_source"]
    print(f"guides: {nfiles} files, {len(gq)} quests ({len(coverage['guides']['quests_missing_in_forever_db'])} "
          f"not in forever-db), {g['all']['total']} items")
    for k in ("all", "step_item", "objective", "reward"):
        print(f"  any source / {k}: {g[k]['with_source']}/{g[k]['total']} = {g[k]['pct']}%")
    for k, v in coverage["drop_or_object_source"].items():
        print(f"  drop/object source / {k}: {v['with_source']}/{v['total']} = {v['pct']}%")
    w = coverage["tier1_or_quest_objective_link"]
    print(f"  tier1 or objective link (the line always says something): {w['with_source']}/{w['total']} = {w['pct']}%")
    w = coverage["with_place_or_reward"]
    print(f"  with a place or reward quest: {w['with_source']}/{w['total']} = {w['pct']}%")
    if a.check and g["all"]["pct"] < 95:
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Query the local QuestieDB (WoW Forever), or forever-db, from the command line.

Examples:
  python tools/lookup.py quest 179
  python tools/lookup.py npc 658
  python tools/lookup.py object 31 | item 750
  python tools/lookup.py search "Coldridge"
  python tools/lookup.py zone-quests 1426 --race Gnome --class WARLOCK --max-level 12
  python tools/lookup.py chain 179
  python tools/lookup.py info
Add --json for machine-readable output (for agents). Data is read from the user's
installed QuestieDB ("all rights reserved"): print it, never commit it. Without QuestieDB (or with
--db foreverdb) it reads forever-db (GPL-3, tools/fetch_foreverdb.py), which lacks exclusiveTo,
requiredSkill, npcFlags, vendors and waypoints.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from foreverdb import add_db_arguments, open_db  # noqa: E402
from questiedb.constants import classes_in_mask, races_in_mask  # noqa: E402


def _fmt_pts(pts, limit=4):
    s = ", ".join(f"{p[0]} ({p[1]:.2f}, {p[2]:.2f})" for p in pts[:limit])
    if len(pts) > limit:
        s += f", ... (+{len(pts) - limit})"
    return s or "no coordinates"


def _ent_line(db, kind, eid):
    ent = db.npc(eid) if kind == "npc" else db.object(eid) if kind == "object" else db.item(eid)
    if not ent:
        return f"{kind} {eid} (not in DB)"
    if kind == "item":
        return f"item {eid} {ent['name']}"
    pts = [s[:3] for s in ent["spawns"] if s[1] is not None]
    return f"{kind} {eid} {ent['name']} @ {_fmt_pts(pts)}"


def _qname(db, qid):
    q = db.quest(qid)
    return f"{qid} {q['name']}" if q else f"{qid} (unknown)"


def quest_view(db, qid):
    q = db.quest(qid)
    if not q:
        return None
    out = dict(q)
    out["racesText"] = races_in_mask(q["races"])
    out["classesText"] = classes_in_mask(q["classes"])
    out["starterLocations"] = db.starter_locations(qid)
    fin = []
    for kind in ("npc", "object"):
        for eid in q["finishers"][kind]:
            ent = db.npc(eid) if kind == "npc" else db.object(eid)
            fin.append({"kind": kind, "id": eid, "name": ent["name"] if ent else None,
                        "spawns": [s[:3] for s in (ent["spawns"] if ent else []) if s[1] is not None]})
    out["finisherLocations"] = fin
    named = {}
    for kind in ("creature", "object", "item"):
        for o in q["objectives"].get(kind, []):
            ent = {"creature": db.npc, "object": db.object, "item": db.item}[kind](o["id"])
            named[f"{kind}:{o['id']}"] = ent["name"] if ent else None
    out["objectiveNames"] = named
    return out


def print_quest(db, qid):
    q = quest_view(db, qid)
    if not q:
        print(f"quest {qid}: not found")
        return 1
    z = q["zone"] or {}
    print(f"Quest {qid}: {q['name']}  [level {q['level']}, requires {q['requiredLevel']}"
          + (f", max {q['requiredMaxLevel']}" if q["requiredMaxLevel"] else "") + "]")
    if z.get("areaId"):
        print(f"  zone: {z.get('name')} (area {z['areaId']}) -> uiMap {z.get('uiMapId')}")
    elif z.get("sort"):
        print(f"  sort: {z.get('name')} ({z['sort']})")
    print(f"  races: {', '.join(q['racesText'])}   classes: {', '.join(q['classesText'])}")
    for s in q["starterLocations"]:
        print(f"  starts: {s['kind']} {s['id']} {s['name']} @ {_fmt_pts(s['spawns'])}")
    for s in q["finisherLocations"]:
        print(f"  ends:   {s['kind']} {s['id']} {s['name']} @ {_fmt_pts(s['spawns'])}")
    if q["preQuestGroup"]:
        print("  requires ALL of: " + "; ".join(_qname(db, p) for p in q["preQuestGroup"]))
    if q["preQuestSingle"]:
        print("  requires ANY of: " + "; ".join(_qname(db, p) for p in q["preQuestSingle"]))
    if q["nextQuestInChain"]:
        print(f"  next in chain: {_qname(db, q['nextQuestInChain'])}")
    if q["exclusiveTo"]:
        print("  exclusive with: " + "; ".join(_qname(db, p) for p in q["exclusiveTo"]))
    if q["breadcrumbFor"]:
        print(f"  breadcrumb for: {_qname(db, q['breadcrumbFor'])}")
    for t in q["objectivesText"]:
        print(f"  text: {t}")
    for kind, rows in q["objectives"].items():
        if kind in ("creature", "object", "item"):
            for o in rows:
                print(f"  objective {kind} {o['id']} {q['objectiveNames'].get(f'{kind}:{o['id']}')}"
                      + (f" ({o['text']})" if o.get("text") else ""))
        else:
            print(f"  objective {kind}: {rows}")
    if q["sourceItemId"]:
        print(f"  provided item: {_ent_line(db, 'item', q['sourceItemId'])}")
    if q["hidden"]:
        print(f"  questie blacklist: {q['hidden']}")
    if q["corrected"]:
        print(f"  dynamic corrections applied to fields: {q['corrected']}")
    return 0


def npc_view(db, nid):
    n = db.npc(nid)
    if not n:
        return None
    out = dict(n)
    out["quests"] = db.npc_quests(nid)
    out["mapNames"] = {m: db.map_name(m) for m in sorted({s[0] for s in n["spawns"] if s[0]})}
    return out


def print_npc(db, nid):
    n = npc_view(db, nid)
    if not n:
        print(f"npc {nid}: not found")
        return 1
    lvl = f"{n['minLevel']}" if n["minLevel"] == n["maxLevel"] else f"{n['minLevel']}-{n['maxLevel']}"
    print(f"NPC {nid}: {n['name']}" + (f" <{n['subName']}>" if n["subName"] else "")
          + f"  [level {lvl}, friendly to {n['friendlyTo'] or 'none'}, flags {n['npcFlags']}]")
    for s in n["spawns"]:
        where = f"({s[1]:.2f}, {s[2]:.2f})" if s[1] is not None else "(instance)"
        print(f"  spawn: uiMap {s[0]} {db.map_name(s[0]) or ''} {where}  [area {s[3]}]")
    if n["waypoints"]:
        print(f"  waypoints: {len(n['waypoints'])} path points")
    for kind in ("starts", "ends"):
        if n["quests"][kind]:
            print(f"  {kind}: " + "; ".join(_qname(db, q) for q in n["quests"][kind]))
    return 0


def print_object(db, oid):
    o = db.object(oid)
    if not o:
        print(f"object {oid}: not found")
        return 1
    print(f"Object {oid}: {o['name']}")
    for s in o["spawns"][:20]:
        where = f"({s[1]:.2f}, {s[2]:.2f})" if s[1] is not None else "(instance)"
        print(f"  spawn: uiMap {s[0]} {db.map_name(s[0]) or ''} {where}")
    if len(o["spawns"]) > 20:
        print(f"  ... {len(o['spawns']) - 20} more spawns")
    oq = db.object_quests(oid)
    for kind in ("starts", "ends"):
        if oq[kind]:
            print(f"  {kind}: " + "; ".join(_qname(db, q) for q in oq[kind]))
    return 0


def print_item(db, iid):
    it = db.item(iid)
    if not it:
        print(f"item {iid}: not found")
        return 1
    print(f"Item {iid}: {it['name']}  [ilvl {it['itemLevel']}, req {it['requiredLevel']}]")
    for key in ("npcDrops", "objectDrops", "itemDrops", "vendors"):
        if it[key]:
            kind = "npc" if key in ("npcDrops", "vendors") else "object" if key == "objectDrops" else "item"
            getter = {"npc": db.npc, "object": db.object, "item": db.item}[kind]
            names = [f"{i} {(getter(i) or {}).get('name')}" for i in it[key][:10]]
            more = f" (+{len(it[key]) - 10})" if len(it[key]) > 10 else ""
            print(f"  {key}: " + "; ".join(names) + more)
    if it["startQuest"]:
        print(f"  starts quest: {_qname(db, it['startQuest'])}")
    for key in ("questRewards", "relatedQuests"):
        if it[key]:
            print(f"  {key}: " + "; ".join(_qname(db, q) for q in it[key]))
    if it["teachesSpell"]:
        print(f"  teaches spell {it['teachesSpell']}")
    return 0


def print_chain(db, data, indent=0, key="pre"):
    for node in data:
        mode = f" [{node['mode']}]" if "mode" in node else ""
        print("  " * indent + f"- {node['id']} {node['name']}{mode}")
        print_chain(db, node.get(key, []), indent + 1, key)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--questiedb", help="QuestieDB addon folder (default: env SENDA_QUESTIEDB or the WoW install)")
    ap.add_argument("--faction", default="Alliance", help="faction for dynamic corrections (Alliance/Horde)")
    ap.add_argument("--json", action="store_true", help="JSON output (also accepted after the subcommand)")
    ap.add_argument("--rebuild", action="store_true", help="force rebuilding the decoded cache")
    add_db_arguments(ap)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="JSON output")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("quest", "npc", "object", "item", "chain"):
        p = sub.add_parser(name, parents=[common])
        p.add_argument("id", type=int)
    p = sub.add_parser("search", parents=[common])
    p.add_argument("text")
    p.add_argument("--kind", action="append", choices=["quest", "npc", "object", "item", "zone"])
    p.add_argument("--limit", type=int, default=50)
    p = sub.add_parser("zone-quests", parents=[common])
    p.add_argument("uimap", type=int)
    p.add_argument("--race")
    p.add_argument("--class", dest="cls")
    p.add_argument("--max-level", type=int)
    p.add_argument("--min-level", type=int)
    p.add_argument("--include-hidden", action="store_true", help="include Questie-blacklisted quests")
    sub.add_parser("info", parents=[common])
    args = ap.parse_args(argv)

    db = open_db(args, faction=args.faction, rebuild=args.rebuild)
    js = args.json

    def emit(obj):
        print(json.dumps(obj, ensure_ascii=False, indent=1, default=list))

    if args.cmd == "info":
        emit(db.info)
        return 0
    if args.cmd == "quest":
        if js:
            emit(quest_view(db, args.id))
            return 0 if db.quest(args.id) else 1
        return print_quest(db, args.id)
    if args.cmd == "npc":
        if js:
            emit(npc_view(db, args.id))
            return 0 if db.npc(args.id) else 1
        return print_npc(db, args.id)
    if args.cmd == "object":
        if js:
            o = db.object(args.id)
            emit(o and {**o, "quests": db.object_quests(args.id)})
            return 0 if o else 1
        return print_object(db, args.id)
    if args.cmd == "item":
        if js:
            emit(db.item(args.id))
            return 0 if db.item(args.id) else 1
        return print_item(db, args.id)
    if args.cmd == "chain":
        data = db.chain(args.id)
        if js:
            emit(data)
            return 0 if data else 1
        if not data:
            print(f"quest {args.id}: not found")
            return 1
        print(f"Chain for {args.id} {data['name']}")
        print("prerequisites:")
        print_chain(db, data["prerequisites"], 1, "pre")
        print("follow-ups:")
        print_chain(db, data["followups"], 1, "next")
        if data["exclusiveTo"]:
            print("exclusive with: " + "; ".join(_qname(db, q) for q in data["exclusiveTo"]))
        return 0
    if args.cmd == "search":
        kinds = tuple(args.kind) if args.kind else ("quest", "npc", "object", "item", "zone")
        rows = db.search(args.text, kinds, args.limit)
        if js:
            emit(rows)
            return 0
        for r in rows:
            extra = ""
            if r["kind"] == "quest":
                extra = f" [lvl {r['level']}, req {r['requiredLevel']}]"
            elif r["kind"] == "npc" and r.get("maps"):
                extra = f" maps {r['maps']}"
            elif r["kind"] == "zone":
                extra = f" -> uiMap {r['uiMapId']}"
            ident = r.get("id", r.get("areaId", r.get("uiMapId")))
            print(f"{r['kind']:6} {ident:>7}  {r['name']}{extra}")
        if not rows:
            print("no matches")
        return 0
    if args.cmd == "zone-quests":
        rows = db.zone_quests(args.uimap, race=args.race, cls=args.cls, faction=args.faction,
                              max_level=args.max_level, min_level=args.min_level,
                              include_hidden=args.include_hidden)
        if js:
            emit(rows)
            return 0
        print(f"{len(rows)} quests in uiMap {args.uimap} {db.map_name(args.uimap) or ''}"
              f" (race={args.race or 'any'}, class={args.cls or 'any'}, max-level={args.max_level or '-'})")
        for r in rows:
            flag = "" if r["startsInZone"] else " (zone tag only)"
            hid = f" [questie:{r['hidden']}]" if r["hidden"] else ""
            print(f"  [{r['requiredLevel']:>2}/{r['level']:>2}] {r['id']:>6} {r['name']}{flag}{hid}")
            for s in r["starters"]:
                print(f"           {s['kind']} {s['id']} {s['name']} @ {_fmt_pts(s['spawns'], 2)}")
            pre = r["preQuestGroup"] + r["preQuestSingle"]
            if pre:
                print(f"           requires: {pre}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())

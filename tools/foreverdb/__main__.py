"""Quick look at forever-db through the adapter.

    python tools/foreverdb [--foreverdb DIR] [--quest ID ...] [--npc ID ...] [--json]

Without ids it prints the dataset info, three quests and three NPCs with their spawns converted
from world yards to [uiMapId, x%, y%]. For full queries use ``python tools/lookup.py --db foreverdb``.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # tools/

from foreverdb import ForeverDB  # noqa: E402

SAMPLE_QUESTS = (33, 64, 109)     # Wolves Across the Border, The Forgotten Heirloom, Report to Gryan Stoutmantle
SAMPLE_NPCS = (234, 197, 6774)    # Gryan Stoutmantle, Marshal McBride, Falkhaan Isenstrider


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--foreverdb", help="forever-db folder (default env SENDA_FOREVERDB or .cache/foreverdb)")
    ap.add_argument("--quest", type=int, action="append")
    ap.add_argument("--npc", type=int, action="append")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    t0 = time.time()
    db = ForeverDB.open(args.foreverdb)
    quests = [db.quest(q) for q in (args.quest or SAMPLE_QUESTS)]
    npcs = [db.npc(n) for n in (args.npc or SAMPLE_NPCS)]
    if args.json:
        print(json.dumps({"info": db.info, "quests": quests, "npcs": npcs}, ensure_ascii=False, indent=1))
        return 0
    i = db.info
    print(f"forever-db {i['version']} (client {i['client_build']}, commit {str(i['build_commit'])[:10]}): "
          f"{len(db.quests)} quests, {len(db.npcs)} npcs, {len(db.objects)} objects, "
          f"{len(db.zones['uimaps'])} map frames; loaded in {time.time() - t0:.1f}s")
    print(f"missing (QuestieDB only): {', '.join(i['missing'])}")
    for qid, q in zip(args.quest or SAMPLE_QUESTS, quests):
        if not q:
            print(f"quest {qid}: not found")
            continue
        print(f"quest {qid} {q['name']}: level {q['level']}, requiredLevel {q['requiredLevel']}, xp {q['xp']}, "
              f"starters {q['starters']}, finishers {q['finishers']}, preQuestSingle {q['preQuestSingle']}, "
              f"preQuestGroup {q['preQuestGroup']}, breadcrumbs {q['breadcrumbs']}, objectives {q['objectives']}")
    for nid, n in zip(args.npc or SAMPLE_NPCS, npcs):
        if not n:
            print(f"npc {nid}: not found")
            continue
        pts = ", ".join(f"[{s[0]}, {s[1]:.2f}, {s[2]:.2f}]" for s in n["spawns"][:4]) or "no map coordinates"
        print(f"npc {nid} {n['name']}: spawns {pts} (world {n['world'][:2]}); quests "
              f"{db.npc_quests(nid)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

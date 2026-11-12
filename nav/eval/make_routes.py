#!/usr/bin/env python3
"""Builds nav/eval/routes.json: Senda's navigation validation corpus (docs/NAV.md).

Every end is uiMapId + percent, converted from a sourced point:
  - "npc:<id>": the NPC's first spawn in forever-db (spawn.jsonl, world yards);
  - "w:x,y,z": a world point taken as a fact from Polestar's nav acceptance corpus
    (tools/lib/nav/eval/acceptance.json and routes.json, GPL-3; only the coordinates);
  - "m:<uiMap>,x,y": a point already on a zone map (Senda's guides or Polestar's corpus).
Flight master -> guide goal routes are read from Senda's own guides (data/**/*.toml, read-only):
after each `do = "fly"` step, the first step with `at` in the destination zone, from that zone's
flight master.

Run: python -I nav/eval/make_routes.py  (needs .cache/foreverdb: python tools/fetch_foreverdb.py)
"""
import json
import pathlib
import re
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[2]
DB = ROOT / ".cache" / "foreverdb" / "data"

frames = {}
for line in (DB / "ui_map.jsonl").read_text(encoding="utf8").splitlines():
    r = json.loads(line)
    frames[r["ui_map"]] = r

spawn = {}
for line in (DB / "spawn.jsonl").read_text(encoding="utf8").splitlines():
    r = json.loads(line)
    if r["kind"] == "npc" and r["id"] not in spawn:
        spawn[r["id"]] = r


def pct(ui, wx, wy):
    f = frames[ui]
    return round((wy - f["left"]) / (f["right"] - f["left"]) * 100, 2), round((wx - f["top"]) / (f["bottom"] - f["top"]) * 100, 2)


def end(spec, ui):
    if spec.startswith("npc:"):
        s = spawn[int(spec[4:])]
        x, y = pct(ui, s["x"], s["y"])
        return {"uiMap": ui, "x": x, "y": y, "z": s.get("z"), "src": f"forever-db spawn npc {spec[4:]}"}
    if spec.startswith("w:"):
        p = [float(v) if v != "null" else None for v in spec[2:].split(",")]
        x, y = pct(ui, p[0], p[1])
        return {"uiMap": ui, "x": x, "y": y, "z": p[2] if len(p) > 2 else None, "src": "Polestar nav corpus (coordinates)"}
    if spec.startswith("m:"):
        u, x, y = spec[2:].split(",")
        return {"uiMap": int(u), "x": float(x), "y": float(y), "z": None, "src": "zone map point"}
    raise ValueError(spec)


# id, kind, (from spec, uiMap), (to spec, uiMap), note
EK, WF, SW, DM, LM, WL, AH, RR, DW, EL, TF, UC, SV, SG, BL, BS = 0, 1436, 1453, 1426, 1432, 1437, 1417, 1433, 1431, 1429, 1420, 1458, 1421, 1427, 1418, 1428
STV, HB, IF, MU, TB, TN, DS, TD, DN, BA, DU, OG, TA, AS = 1434, 1424, 1455, 1412, 1456, 1441, 1439, 1438, 1457, 1413, 1411, 1454, 1446, 1440
R = [
    ("deadmines-from-sentinel-hill", "dungeon", ("npc:234", WF), ("m:1436,42.6,71.7", WF), "Senda guide a21: Deadmines entrance in Moonbrook"),
    ("sentinel-hill-thor-to-deadmines", "dungeon", ("npc:523", WF), ("m:1436,42.6,71.7", WF), "flight master to the dungeon"),
    ("thelsamar-to-menethil-dun-algaz", "tunnel", ("npc:1572", LM), ("npc:1571", WL), "Loch Modan -> Wetlands through Dun Algaz"),
    ("menethil-to-refuge-pointe-thandol", "bridge", ("npc:1571", WL), ("npc:2835", AH), "Wetlands -> Arathi over Thandol Span"),
    ("kharanos-to-thelsamar", "tunnel", ("w:-5617.25,-497.892,401.493", DM), ("npc:1572", LM), "Dun Morogh -> Loch Modan tunnel"),
    ("kharanos-to-ironforge-great-forge", "gate", ("w:-5617.25,-497.892,401.493", DM), ("npc:1573", IF), "through the gates to the flight master"),
    ("ironforge-forge-to-kharanos", "gate", ("npc:1573", IF), ("w:-5617.25,-497.892,401.493", DM), "out through the gates"),
    ("ironforge-to-gnomeregan-vator", "lift", ("m:1426,53,35", DM), ("w:-5100.6,750.3,260.6", DM), "Gnomeregan's lift"),
    ("darnassus-ruttheran-portal", "portal", ("m:1438,56.73,61.9", TD), ("w:8799.4,969.8,30.4", TD), "Dolanaar -> Rut'theran portal"),
    ("ruttheran-dock-to-dolanaar", "portal", ("w:8544.8,1026,5.9", TD), ("m:1438,56.73,61.9", TD), "Rut'theran dock -> Dolanaar (up the tree)"),
    ("dolanaar-to-darnassus", "city", ("m:1438,56.73,61.9", TD), ("w:9838.5,2431.6,1315.8", DN), "into Darnassus"),
    ("ruttheran-fm-to-dock", "portal", ("npc:3838", TD), ("w:8544.8,1026,5.9", TD), "Vesprystus -> dock"),
    ("auberdine-to-coast-north", "coast", ("npc:3841", DS), ("w:6878.8,-655.6,null", DS), "Darkshore coast north of Auberdine"),
    ("auberdine-to-coast-south", "coast", ("npc:3841", DS), ("m:1439,38.6,86.2", DS), "Darkshore coast south (Senda guide point)"),
    ("sw-trade-to-harbor-boat", "canals", ("m:1453,68.48,75.35", SW), ("m:1453,22.46,56.44", SW), "across the canals to the harbour"),
    ("sw-cathedral-to-harbor", "canals", ("m:1453,55.9,56.9", SW), ("w:-8649.5,1337.4,6", SW), "Cathedral Square -> harbour"),
    ("sw-dwarven-to-tram", "canals", ("w:-8451.868,575.472,95", SW), ("w:-8346.5,514,91.8", SW), "Dwarven District -> Deeprun Tram"),
    ("sw-fm-to-mage-quarter", "canals", ("npc:352", SW), ("m:1453,39.2,85.2", SW), "Dungar -> Mage Quarter over the canals (Senda guide point)"),
    ("goldshire-to-sw-trade", "city", ("w:-9462.579,16.233,56.963", EL), ("w:-8821.495,659.915,98.351", SW), "Goldshire -> Trade District"),
    ("goldshire-to-fargodeep", "cave", ("w:-9444.062,77.667,57.353", EL), ("w:-9791.249,164.438,27.373", EL), "Fargodeep Mine"),
    ("eastvale-to-lakeshire-bridge", "bridge", ("m:1429,81,66", EL), ("npc:6727", RR), "Eastvale -> Lakeshire over the bridge"),
    ("lakeshire-fm-to-town-hall", "bridge", ("npc:931", RR), ("npc:344", RR), "Lakeshire flight master -> town hall"),
    ("redridge-ridge-murlocs", "bridge", ("m:1433,32.42,43.39", RR), ("m:1433,40.2,51.8", RR), "Polestar report #-: Redridge ridge to the lake"),
    ("darkshire-to-sentinel-hill", "zones", ("npc:2409", DW), ("npc:234", WF), "Duskwood -> Westfall"),
    ("sven-to-sentinel-hill", "zones", ("m:1431,7.78,34.07", DW), ("w:-10628.3,1037.3,34.2", WF), "Duskwood west -> Westfall"),
    ("darkshire-to-lakeshire", "zones", ("npc:2409", DW), ("npc:931", RR), "Duskwood -> Redridge"),
    ("brill-to-undercity-undervator", "lift", ("w:2249.1,236.8,41.3", TF), ("w:1567.11,266.388,-59.285", UC), "Brill -> Undercity by the lifts"),
    ("ruins-to-undercity-trade", "lift", ("w:1713.688,231.708,62.598", TF), ("npc:4551", UC), "ruins of Lordaeron -> bat handler"),
    ("undercity-trade-to-royal", "city", ("w:1635.4,223.3,-43", UC), ("w:1290.4,316.2,-57.2", UC), "Trade Quarter -> Royal Quarter"),
    ("undercity-apothecarium-to-canal", "city", ("w:1516.99,379.403,-61.4", UC), ("w:1435.6,72,-62.2", UC), "Apothecarium -> lower canal"),
    ("tarrenmill-to-brill", "zones", ("m:1424,60.79,19.92", HB), ("w:2246.1,239.8,34.3", TF), "Hillsbrad -> Tirisfal"),
    ("stv-booty-bay-inn", "town", ("m:1434,28,70.5", STV), ("npc:2858", STV), "into Booty Bay"),
    ("badlands-kargath-to-angor", "zones", ("w:-6660.708,-2178.667,244.617", BL), ("w:-6362.208,-3111.48,285.278", BL), "Badlands"),
    ("searing-cauldron-upper-lower", "lift", ("w:-6864,-1174.1,240.3", SG), ("w:-6906.8,-1215.3,178.4", SG), "Cauldron, upper to lower"),
    ("menethil-dock-to-town", "town", ("w:-3709.5,-575.1,null", WL), ("w:-3743.2,-797.6,11.5", WL), "Menethil"),
    ("lakeshire-to-booty-bay", "long", ("npc:931", RR), ("npc:2858", STV), "continent-scale walk"),
    ("goldshire-to-thelsamar", "long", ("w:-9462.579,16.233,56.963", EL), ("npc:1572", LM), "continent-scale walk (Elwynn -> Loch Modan)"),
    ("tb-bottom-to-top", "lift", ("w:-2378.767,-399.137,-3.866", MU), ("w:-1300.274,38.525,129.209", TB), "Bloodhoof -> Thunder Bluff by the lift"),
    ("tb-central-to-elder-rise", "lift", ("w:-1300.3,38.5,129.3", TB), ("w:-1048.7,-304,159.1", TB), "rope bridges"),
    ("tb-central-to-spirit-rise", "lift", ("w:-1300.3,38.5,129.3", TB), ("w:-996.9,278.5,138.1", TB), "rope bridges"),
    ("tb-top-to-mulgore", "lift", ("npc:2995", TB), ("w:-2259.417,-366.708,-9.425", MU), "Tal -> Bloodhoof, down the lift"),
    ("tn-freewind-inn-to-nyse", "bridge", ("w:-5477.8,-2460.4,89.4", TN), ("npc:4317", TN), "Freewind Post bridges"),
    ("tn-canyon-to-freewind", "lift", ("w:-5556.1,-2343.8,-44", TN), ("npc:4317", TN), "canyon floor -> Freewind Post"),
    ("tn-canyon-to-darkcloud", "bridge", ("w:-5307.3,-3199,-45.6", TN), ("w:-4744.8,-2099,83.7", TN), "Darkcloud Pinnacle"),
    ("orgrimmar-tunnel", "city", ("m:1411,45.5,12", DU), ("w:1633.959,-4439.41,15.48", OG), "Durotar -> Valley of Strength"),
    ("razorhill-to-orgrimmar", "zones", ("w:340.523,-4686.091,16.458", DU), ("w:1633.959,-4439.41,15.48", OG), "Razor Hill -> Orgrimmar"),
    ("crossroads-to-northwatch", "zones", ("npc:3615", BA), ("w:-2103.438,-3558.417,97.703", BA), "the Barrens"),
    ("ratchet-to-northwatch", "zones", ("npc:16227", BA), ("w:-2103.438,-3558.417,97.703", BA), "the Barrens"),
    ("tanaris-riggercove-southbreak", "zones", ("w:-8037,-5186.75,2.325", TA), ("w:-8773,-4565.75,39.635", TA), "Tanaris"),
    ("crossroads-to-orgrimmar", "long", ("npc:3615", BA), ("npc:3310", OG), "continent-scale walk"),
    ("teldrassil-banethil-oben", "cave", ("m:1438,44.92,55.02", TD), ("w:9741,1526.2,1280.4", TD), "barrow"),
]

# Flight master of each destination zone (forever-db NPC ids).
FM = {1436: 523, 1453: 352, 1432: 1572, 1437: 1571, 1455: 1573, 1433: 931, 1431: 2409, 1417: 2835, 1439: 3841,
      1438: 3838, 1440: 4267, 1434: 2858, 1428: 2299, 1427: 3305, 1446: 7823, 1444: 8019}
CONT = {u: f["map"] for u, f in frames.items()}


def guide_routes(limit=9):
    out = []
    seen = set()
    files = sorted((ROOT / "data").rglob("*.toml"))
    for f in files:
        try:
            doc = tomllib.loads(f.read_text(encoding="utf8"))
        except Exception:
            continue
        steps = doc.get("step", [])
        for i, s in enumerate(steps):
            if s.get("do") != "fly" or s.get("zone") not in FM:
                continue
            z = s["zone"]
            for t in steps[i + 1:i + 6]:
                at = t.get("at")
                if isinstance(at, list) and len(at) >= 3 and at[0] == z and CONT.get(z) is not None:
                    key = (z, round(at[1]), round(at[2]))
                    if key in seen:
                        break
                    seen.add(key)
                    fm = spawn.get(FM[z])
                    if fm and fm["map"] == CONT[z]:
                        out.append((f"fm{FM[z]}-to-{t.get('id', 'goal')}", "flight", (f"npc:{FM[z]}", z), (f"m:{z},{at[1]},{at[2]}", z),
                                    f"guide {f.relative_to(ROOT).as_posix()} step {t.get('id')}"))
                    break
    return out[:limit]


routes = []
for rid, kind, a, b, note in R + guide_routes():
    fa, fb = end(*a), end(*b)
    m = CONT[fa["uiMap"]]
    if CONT[fb["uiMap"]] != m:
        print("skip (two continents)", rid, file=sys.stderr)
        continue
    routes.append({"id": rid, "kind": kind, "map": m, "from": fa, "to": fb, "note": note, "expect": "found"})
out = ROOT / "nav" / "eval" / "routes.json"
out.write_text(json.dumps({"note": __doc__.strip().splitlines()[0], "routes": routes}, indent=1, ensure_ascii=False) + "\n", encoding="utf8")
print(f"{len(routes)} routes -> {out}")

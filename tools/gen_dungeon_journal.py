#!/usr/bin/env python3
"""Genera data/dungeons/journal.json: botín, jefes y piedra de encuentro de cada mazmorra (diario de mazmorras).

Completa data/dungeons/dungeons.json y quests.json (tools/gen_dungeons.py) con lo que el diario del juego necesita y
que ese generador no trae:

  - Botín de equipo por mazmorra, con sus estadísticas en las claves de los pesos de Senda (weights.toml), para que
    el addon elija en el juego lo que mejora a la build del jugador:
      · ForeverLevelingBiS v0.12.0-beta de Thunder (MIT, datos 13-oct-2026), tal como lo redistribuye Polestar
        (GPL-3.0) en addon/Polestar_ItemDB/Forever.lua: botín `d<pnj>x<pct*10>z<zona>` cuya zona es un área de la
        mazmorra (la misma lectura que tools/gen_bis.py; solo versiones MIT).
      · forever-db (GPL-3.0) item_source.jsonl: objetos que sueltan los jefes de la mazmorra (PNJ sin aparición en el
        mundo cuyo nombre es el de un encuentro del cliente de esa mazmorra, la regla de gen_dungeons.py).
    Estadísticas: las de Forever en Forever.lua; si el objeto no está ahí, las de la tabla de objetos del cliente
    Classic Era que Polestar publica en addon/Polestar_ItemDB/Items.lua (hechos del cliente, como las tablas que usa
    gen_dungeons.py). Cada objeto dice de dónde salen (`stats_from`).
  - Jefes: los encuentros del cliente con el id de PNJ de forever-db cuando el nombre coincide (para {npc:N}).
  - Piedra de encuentro: la aparición de forever-db (objeto tipo 23, «Meeting Stone») más cercana a la entrada en el
    mismo continente, a menos de STONE_MAX_YD yardas. La asociación es por distancia (forever-db no dice a qué
    mazmorra sirve cada piedra): se guarda la distancia.

Uso:
    python tools/gen_dungeon_journal.py --polestar RUTA/polestar [--foreverdb DIR]           # escribe
    python tools/gen_dungeon_journal.py --polestar RUTA/polestar [--foreverdb DIR] --check   # falla si cambiaría

No usa QuestieDB, AtlasLoot (GPL-2.0, Polestar solo lo lee en local), DungeonJournal ni el Codex de Polestar.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import REPO_ROOT, setup_stdio, write_text_lf  # noqa: E402
from foreverdb import resolve_foreverdb  # noqa: E402
from foreverdb.db import Frames, read_jsonl  # noqa: E402
import gen_bis  # noqa: E402

SCHEMA = 1
ERA = Path("addon/Polestar_ItemDB/Items.lua")
STONE_TYPE = 23
STONE_MAX_YD = 1000.0
# Zonas de ForeverLevelingBiS que no son el área de la instancia en dungeons.json pero sí esa mazmorra
# (nombres de la propia tabla `zones` de Forever.lua): 1583 «Blackrock Spire: Upper», 1584 «Blackrock Depths»,
# 1477 «The Temple of Atal'Hakkar».
ZONE_ALIAS = {1583: "blackrock-spire", 1584: "blackrock-depths", 1477: "sunken-temple"}
# Ranuras equipables (inventoryType del cliente). Fuera: 0 no equipable, 4 camisa, 18 bolsa, 19 tabardo, 24 munición.
EQUIP = {1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 20, 21, 22, 23, 25, 26, 28}
STAT = {"str": "STR", "agi": "AGI", "sta": "STA", "int": "INT", "spi": "SPI", "armor": "ARMOR", "sp": "SP",
        "mpr": "MP5", "ap": "AP", "rap": "RAP", "hit": "HIT", "crit": "CRIT", "spellHit": "SPELL_HIT",
        "spellCrit": "SPELL_CRIT", "defense": "DEFENSE", "dodge": "DODGE", "spShadow": "SP_SHADOW",
        "spFrost": "SP_FROST", "spFire": "SP_FIRE", "spArcane": "SP_ARCANE", "spNature": "SP_NATURE",
        "spHoly": "SP_HOLY"}
_ENTRY = re.compile(r'^\[(\d+)\]="(\d+ \d+ \d+ \d+ \d+ \d+[^"]*)",?$')


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def read_era(path: Path) -> dict[int, str]:
    out = {}
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            m = _ENTRY.match(raw.strip())
            if m:
                out[int(m.group(1))] = m.group(2)
    return out


def item_stats(raw: str) -> dict:
    """Entrada «inv ilvl req calidad clase subclase tokens» -> objeto con estadísticas en claves de Senda."""
    it = gen_bis.parse_item(raw)
    st: dict[str, float] = {}
    for tok, v in it["stats"].items():
        key = STAT.get(tok)
        if key and v:
            st[key] = st.get(key, 0) + v
    if it["class"] == 2:
        dps = gen_bis.weapon_dps(it)
        if dps > 0:
            st["DPS"] = round(dps, 1)
    out = {"inv": it["inv"], "ilvl": it["ilvl"], "req": it["req"], "q": it["quality"], "class": it["class"],
           "sub": it["sub"], "stats": {k: (int(v) if float(v).is_integer() else round(v, 1)) for k, v in sorted(st.items())}}
    cls = int(it["stats"].get("cls", 0))
    if cls:
        out["cls"] = cls
    return out


def equippable(e: dict) -> bool:
    return e["inv"] in EQUIP and e["class"] in (2, 4)


def build(dungeons: list[dict], forever: dict, era: dict[int, str], fdb: Path) -> dict:
    D = fdb / "data"
    frames = Frames(list(read_jsonl(D / "ui_map.jsonl")))
    # --- PNJ de forever-db: con aparición o no, por nombre
    spawned_npc: set[int] = set()
    stones: list[dict] = []
    stone_ids = {o["id"] for o in read_jsonl(D / "object.jsonl") if o.get("type") == STONE_TYPE}
    for s in read_jsonl(D / "spawn.jsonl"):
        if s["kind"] == "npc":
            spawned_npc.add(s["id"])
        elif s["kind"] == "object" and s["id"] in stone_ids:
            stones.append(s)
    by_name: dict[str, list[int]] = defaultdict(list)
    for n in read_jsonl(D / "npc.jsonl"):
        if n.get("name"):
            by_name[norm(n["name"])].append(n["id"])
    fdb_src: dict[int, list[dict]] = defaultdict(list)
    for s in read_jsonl(D / "item_source.jsonl"):
        if s["kind"] == "npc":
            fdb_src[s["id"]].append(s)

    area_to_key = dict(ZONE_ALIAS)
    for d in dungeons:
        for a in d["area_ids"]:
            area_to_key[a] = d["key"]
    loot: dict[str, dict[int, dict]] = defaultdict(dict)

    def stats_of(iid: int) -> tuple[dict | None, str | None]:
        if iid in forever["items"]:
            return item_stats(forever["items"][iid]), "flb"
        if iid in era:
            return item_stats(era[iid]), "era"
        return None, None

    def add(key: str, iid: int, npc: int, pct, src: str) -> None:
        e, frm = stats_of(iid)
        if not e or not equippable(e):
            return
        cur = loot[key].get(iid)
        if cur:  # el mismo objeto por dos fuentes: se queda la probabilidad mayor y se anota la otra fuente
            if src not in cur["src"]:
                cur["src"] = sorted(set(cur["src"]) | {src})
            if (pct or 0) > (cur.get("pct") or 0):
                cur["npc"], cur["pct"] = npc, pct
            return
        e.update(id=iid, npc=npc, pct=pct, src=[src], stats_from=frm)
        loot[key][iid] = e

    # ForeverLevelingBiS: botín con zona de la mazmorra
    for iid, raw in sorted(forever["src"].items()):
        for s in gen_bis.parse_sources(raw):
            if s["kind"] == "drop" and s["zone"] in area_to_key:
                add(area_to_key[s["zone"]], iid, s["npc"], s["pct"], "flb")

    bosses: dict[str, list[list]] = {}
    for d in dungeons:
        rows, seen = [], set()
        for enc in d["encounters"]:
            if norm(enc["name"]) in seen:  # el cliente repite encuentros (dificultades o alas): uno por nombre
                continue
            seen.add(norm(enc["name"]))
            ids = [i for i in by_name.get(norm(enc["name"]), []) if i not in spawned_npc]
            npc = min(ids) if ids else 0
            rows.append([enc["name"], npc])
            for i in ids:
                for s in fdb_src.get(i, []):
                    add(d["key"], s["item"], i, s.get("chance"), "fdb")
        bosses[d["key"]] = rows

    # Piedras de encuentro
    stone_out: dict[str, dict] = {}
    for d in dungeons:
        e = d.get("entrance")
        if not e:
            continue
        w = e["world"]
        best = None
        for s in stones:
            if s["map"] != w["map"]:
                continue
            dist = math.hypot(s["x"] - w["x"], s["y"] - w["y"])
            if dist <= STONE_MAX_YD and (best is None or dist < best[0] or (dist == best[0] and s["id"] < best[1]["id"])):
                best = (dist, s)
        if not best:
            continue
        dist, s = best
        hits = frames.all(s["map"], s["x"], s["y"])
        pick = next((h for h in hits if h[0] == e["uiMapId"]), hits[0] if hits else None)
        if not pick:
            continue
        stone_out[d["key"]] = {"object": s["id"], "uiMapId": pick[0], "x": round(pick[1], 1), "y": round(pick[2], 1),
                               "world": {"map": s["map"], "x": s["x"], "y": s["y"]}, "yards": round(dist)}

    out_loot = {}
    for d in dungeons:
        items = sorted(loot.get(d["key"], {}).values(), key=lambda e: e["id"])
        if items:
            out_loot[d["key"]] = [{k: e[k] for k in ("id", "inv", "class", "sub", "req", "ilvl", "q", "npc", "pct", "src",
                                                     "stats_from", "cls", "stats") if k in e} for e in items]
    return {"bosses": bosses, "stones": stone_out, "loot": out_loot}


def main(argv: list[str] | None = None) -> int:
    setup_stdio()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--polestar", required=True, help="raíz del clon de Polestar (solo se lee)")
    ap.add_argument("--foreverdb", help="carpeta de forever-db (o SENDA_FOREVERDB, o .cache/foreverdb)")
    ap.add_argument("--root", default=str(REPO_ROOT))
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.root)
    pole = Path(args.polestar)
    flb_path = pole / gen_bis.REL
    era_path = pole / ERA
    for p in (flb_path, era_path):
        if not p.exists():
            print(f"gen_dungeon_journal: no existe {p}", file=sys.stderr)
            return 2
    fdb = resolve_foreverdb(args.foreverdb)
    forever = gen_bis.read_forever(flb_path)
    meta = gen_bis.polestar_meta(pole, flb_path, forever)  # falla si el ForeverLevelingBiS no es MIT
    era = read_era(era_path)
    era_head = era_path.read_text(encoding="utf-8").split("\n", 3)[:3]
    era_build = next((m.group(1) for ln in era_head for m in [re.search(r"build (\d[\d.]+)", ln)] if m), "?")
    with open(fdb / "datapackage.json", encoding="utf-8") as fh:
        fdb_version = json.load(fh).get("version", "?")
    with open(root / "data" / "dungeons" / "dungeons.json", encoding="utf-8") as fh:
        dungeons = json.load(fh)["dungeons"]
    res = build(dungeons, forever, era, fdb)
    n_items = sum(len(v) for v in res["loot"].values())
    doc = {
        "schema": SCHEMA,
        "generator": "tools/gen_dungeon_journal.py",
        "sources": {
            "ForeverLevelingBiS": {"version": meta["flb"], "data": meta["flb_date"], "licence": "MIT (Copyright (c) 2026 Thunder)",
                                   "via": f"polestar {meta['commit'][:8]} {gen_bis.REL.as_posix()} (sha256 {meta['sha'][:16]})"},
            "client-items": {"build": era_build, "via": f"polestar {meta['commit'][:8]} {ERA.as_posix()} "
                                                        f"(sha256 {hashlib.sha256(era_path.read_bytes()).hexdigest()[:16]})",
                             "licence": "hechos del cliente (Blizzard Classic Era ItemSparse/Item), publicados por Polestar (GPL-3.0)"},
            "forever-db": {"version": fdb_version, "licence": "GPL-3.0", "tables": ["item_source", "npc", "object", "spawn", "ui_map"]},
        },
        "rules": {
            "loot": "ForeverLevelingBiS: botín cuya zona es un área de la mazmorra (más ZONE_ALIAS); forever-db: item_source "
                    "de los PNJ sin aparición cuyo nombre es el de un encuentro del cliente. Solo armas y armaduras equipables.",
            "stats": "Claves de los pesos de Senda (weights.toml); SP_<ESCUELA> = poder de una escuela; DPS = daño por segundo del arma. "
                     "stats_from: flb (estadísticas de Forever) o era (tabla del cliente Classic Era).",
            "stones": f"Piedra de encuentro de forever-db más cercana a la entrada, en el mismo continente y a menos de {STONE_MAX_YD:g} yardas.",
        },
        "metrics": {"dungeons_with_loot": len(res["loot"]), "items": n_items,
                    "items_flb": sum(1 for v in res["loot"].values() for e in v if "flb" in e["src"]),
                    "items_fdb": sum(1 for v in res["loot"].values() for e in v if "fdb" in e["src"]),
                    "stones": len(res["stones"]),
                    "bosses_with_npc": sum(1 for v in res["bosses"].values() for b in v if b[1]),
                    "bosses": sum(len(v) for v in res["bosses"].values())},
        **res,
    }
    text = json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=False) + "\n"
    out = root / "data" / "dungeons" / "journal.json"
    old = out.read_text(encoding="utf-8") if out.exists() else None
    for key in [d["key"] for d in dungeons]:
        print(f"{key:28s} botín {len(res['loot'].get(key, [])):3d}  piedra "
              f"{('%d yd' % res['stones'][key]['yards']) if key in res['stones'] else '-':>7s}")
    print(f"data/dungeons/journal.json: {n_items} objetos, {len(res['stones'])} piedras"
          f"{' (cambia)' if old != text else ''}")
    if args.check:
        return 1 if old != text else 0
    if old != text:
        write_text_lf(out, text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

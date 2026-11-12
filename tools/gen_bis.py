#!/usr/bin/env python3
"""Genera data/knowledge/<clase>/bis-forever.toml: la mejor pieza conocida por ranura y tramo de nivel.

Fuente de los objetos: ForeverLevelingBiS v0.12.0-beta de Thunder (MIT, datos del 13-oct-2026), tal como lo
redistribuye Polestar (GPL-3.0) en `addon/Polestar_ItemDB/Forever.lua` (`forge data gear`, que solo lee versiones
MIT de ForeverLevelingBiS; aviso MIT en `addon/Polestar_ItemDB/LICENSE-DATA.txt`). Las versiones nuevas de
ForeverLevelingBiS en CurseForge son «All Rights Reserved»: no se usan. Se leen solo hechos:

    items   "<inv> <ilvl> <req> <calidad> <clase> <subclase> [estadísticas]"
    src     q<misión> | d<pnj>x<pct*10>z<zona> | c<hechizo>p<profesión>s<habilidad>
    quests  "<nivel> <req> <bando> <zona> <razas> <clases> <mazmorra>|<elecciones>|<objetos>|<nombre>"

La elección es de Senda: para cada clase y build de data/knowledge/<clase>/weights.toml, tramo de 10 niveles y
ranura, el objeto que más puntúa con los pesos de ese tramo entre los que esa clase puede llevar (armadura,
armas que aprende, máscara de clase del objeto), que se consigue en el tramo (nivel requerido; si no tiene, el de
la misión) y que la Alianza puede conseguir (misiones de la Alianza o de ambos bandos, botín, recetas de las
profesiones del plan de la clase; botín solo con al menos un 5 % de probabilidad). No es una lista «BiS» de nadie: es la mejor pieza conocida con esos datos.

Uso:
    python tools/gen_bis.py --polestar RUTA/polestar           # escribe los bis-forever.toml
    python tools/gen_bis.py --polestar RUTA/polestar --check   # solo dice si cambiaría algo (sale con 1)
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import REPO_ROOT, setup_stdio, write_text_lf  # noqa: E402

REL = Path("addon/Polestar_ItemDB/Forever.lua")
# Botín por debajo de esta probabilidad (%) no se propone: criterio de Senda, para no mandar a farmear un 1 %.
MIN_DROP_PCT = 5.0
BANDS = [(1, 10), (11, 20), (21, 30), (31, 40), (41, 50), (51, 60)]
# Profesiones de Forever.lua (índice 1 en adelante, como las lee Polestar en Gear/ItemDB.lua).
PROFS = ["Alchemy", "Blacksmithing", "Enchanting", "Engineering", "Leatherworking", "Tailoring", "Jewelcrafting",
         "Mining", "Herbalism", "Skinning", "Cooking", "First Aid", "Fishing"]
PROF_KEY = {"Tailoring": "tailoring", "Enchanting": "enchanting", "Leatherworking": "leatherworking",
            "Alchemy": "alchemy", "Blacksmithing": "blacksmithing", "Engineering": "engineering"}
RACE_BIT = {"Human": 1, "Orc": 2, "Dwarf": 4, "NightElf": 8, "Scourge": 16, "Tauren": 32, "Gnome": 64, "Troll": 128}

# Lo que cada clase puede llevar (las mismas reglas que Modules/Gear.lua) y de dónde puede sacar piezas.
CLASSES = {
    "WARLOCK": {"folder": "warlock", "mask": 256, "races": ["Human", "Gnome"], "armor": 1,
                "weapons": {7, 10, 15, 19}, "relic": None, "profs": {"Tailoring", "Enchanting"}},
    "MAGE": {"folder": "mage", "mask": 128, "races": ["Human", "Gnome"], "armor": 1,
             "weapons": {7, 10, 15, 19}, "relic": None, "profs": {"Tailoring", "Enchanting"}},
    "DRUID": {"folder": "druid", "mask": 1024, "races": ["NightElf"], "armor": 2,
              "weapons": {4, 5, 6, 10, 13, 15}, "relic": 8, "profs": set()},
}
# inventoryType -> ranura de Senda (G.SLOTS). Anillos y abalorios: los dos mejores.
INV_SLOT = {1: 1, 2: 2, 3: 3, 5: 5, 20: 5, 6: 6, 7: 7, 8: 8, 9: 9, 10: 10, 16: 15, 11: 11, 12: 13}
ONE_HAND = {13, 21}
TWO_HAND = 17
HOLDABLE = 23
RANGED_RIGHT = 26
RELIC = 28
STAT_KEY = {"str": "STR", "agi": "AGI", "sta": "STA", "int": "INT", "spi": "SPI", "armor": "ARMOR", "sp": "SP",
            "mpr": "MP5", "ap": "AP", "hit": "HIT", "crit": "CRIT", "spellHit": "SPELL_HIT",
            "spellCrit": "SPELL_CRIT", "defense": "DEFENSE", "dodge": "DODGE"}
SCHOOL_TOKEN = {"SHADOW": "spShadow", "FROST": "spFrost", "FIRE": "spFire", "ARCANE": "spArcane",
                "NATURE": "spNature", "HOLY": "spHoly"}


# --------------------------------------------------------------------------- lectura
_ENTRY = re.compile(r'^\[(\d+)\]="(.*)",?$')
_SECTION = re.compile(r"^([a-z]+) = \{$")


def read_forever(path: Path) -> dict:
    """Secciones de Forever.lua: items (DB.Register), src, quests (y la cabecera de RegisterLeveling)."""
    out: dict = {"items": {}, "src": {}, "quests": {}, "meta": ""}
    section = None
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if line.startswith("DB.Register(nil"):
                section = "items"
                continue
            if line.startswith("DB.RegisterLeveling("):
                out["meta"] = line
                section = None
                continue
            m = _SECTION.match(line)
            if m:
                section = m.group(1) if m.group(1) in ("src", "quests") else None
                continue
            if line in ("},", "})"):
                section = None
                continue
            if section:
                m = _ENTRY.match(line)
                if m:
                    out[section][int(m.group(1))] = m.group(2)
    return out


def parse_item(s: str) -> dict:
    parts = s.split()
    it = {"inv": int(parts[0]), "ilvl": int(parts[1]), "req": int(parts[2]), "quality": int(parts[3]),
          "class": int(parts[4]), "sub": int(parts[5]), "stats": {}}
    for tok in parts[6:]:
        m = re.match(r"^([A-Za-z]+)(-?\d+(?:\.\d+)?)$", tok)
        if m:
            it["stats"][m.group(1)] = float(m.group(2))
    return it


def parse_quest(s: str) -> dict:
    head, choices, items, name = (s.split("|") + ["", "", ""])[:4]
    lv, req, side, zone, race, cls, dungeon = (int(x) for x in head.split())
    return {"level": lv, "req": req, "side": side, "zone": zone, "race": race, "class": cls, "dungeon": dungeon}


def parse_sources(s: str) -> list[dict]:
    out = []
    for tok in s.split():
        if m := re.match(r"^q(\d+)$", tok):
            out.append({"kind": "quest", "quest": int(m.group(1))})
        elif m := re.match(r"^d(\d+)x(\d+)z(\d+)$", tok):
            out.append({"kind": "drop", "npc": int(m.group(1)), "pct": int(m.group(2)) / 10, "zone": int(m.group(3))})
        elif m := re.match(r"^c(\d+)p(\d+)s(\d+)$", tok):
            p = int(m.group(2))
            out.append({"kind": "craft", "spell": int(m.group(1)), "prof": PROFS[p - 1] if 1 <= p <= len(PROFS) else "?",
                        "skill": int(m.group(3))})
    return out


# --------------------------------------------------------------------------- reglas
def usable(it: dict, cfg: dict) -> bool:
    cmask = int(it["stats"].get("cls", 0))
    if cmask and not cmask & cfg["mask"]:
        return False
    if it["class"] == 4:
        if it["inv"] == RELIC:
            return cfg["relic"] is not None and it["sub"] == cfg["relic"]
        if it["sub"] == 6:  # escudo
            return False
        if 1 <= it["sub"] <= 4 and it["sub"] > cfg["armor"]:
            return False
        return True
    if it["class"] == 2:
        return it["sub"] in cfg["weapons"]
    return False


def weapon_dps(it: dict) -> float:
    st = it["stats"]
    if not st.get("speed"):
        return 0.0
    return (st.get("dmin", 0) + st.get("dmax", 0)) / 2 / (st["speed"] / 1000)


def score(it: dict, w: dict, school: str | None) -> float:
    s = 0.0
    for tok, v in it["stats"].items():
        key = STAT_KEY.get(tok)
        if key:
            s += v * w.get(key, 0)
        elif school and tok == SCHOOL_TOKEN.get(school):
            s += v * w.get("SCHOOL_W", w.get("SP", 0))
    if it["class"] == 2:
        d = weapon_dps(it)
        if it["sub"] == 19:
            s += d * w.get("WAND_DPS", 0)
        elif it["sub"] in (2, 3, 16, 18):
            s += d * w.get("RANGED_DPS", 0)
        else:
            s += d * w.get("DPS", 0)
    return s


def band_weights(weights: dict, build: str, level: int) -> dict:
    for b in weights.get("band", []):
        if b["build"] == build and b["from"] <= level <= b["to"]:
            return b["w"]
    raise ValueError(f"sin tramo de pesos para {build} al nivel {level}")


def pick_source(item_id: int, srcs: list[dict], quests: dict, cfg: dict) -> tuple[dict | None, int | None, str | None]:
    """(fuente elegida, nivel efectivo, raza exigida) o (None, None, None) si la Alianza no la consigue."""
    allowed = sum(RACE_BIT[r] for r in cfg["races"])
    best = None
    for s in srcs:
        if s["kind"] == "quest":
            q = quests.get(s["quest"])
            if not q or q["side"] not in (1, 3):
                continue
            if q["class"] and not q["class"] & cfg["mask"]:
                continue
            if q["race"] and not q["race"] & allowed:
                continue
            race = None
            if q["race"] and (q["race"] & allowed) != allowed:
                race = next(r for r in cfg["races"] if RACE_BIT[r] & q["race"])
            cand = (0, s, max(1, q["level"]), race)
        elif s["kind"] == "drop":
            if s["pct"] < MIN_DROP_PCT:
                continue
            cand = (1, s, None, None)
        elif s["kind"] == "craft":
            if s["prof"] not in cfg["profs"]:
                continue
            cand = (2, s, None, None)
        else:
            continue
        if best is None or cand[0] < best[0] or (cand[0] == best[0] == 1 and s["pct"] > best[1]["pct"]):
            best = cand
    if not best:
        return None, None, None
    return best[1], best[2], best[3]


def candidates(data: dict, cfg: dict) -> list[dict]:
    quests = {k: parse_quest(v) for k, v in data["quests"].items()}
    out = []
    for iid, raw in data["items"].items():
        if iid not in data["src"]:
            continue
        it = parse_item(raw)
        if not usable(it, cfg):
            continue
        src, qlevel, race = pick_source(iid, parse_sources(data["src"][iid]), quests, cfg)
        if not src:
            continue
        eff = it["req"] if it["req"] > 0 else qlevel
        if not eff:
            continue
        it.update(id=iid, src=src, eff=eff, race=race)
        out.append(it)
    return out


def best_for_band(cands: list[dict], w: dict, school: str | None, lo: int, hi: int, cfg: dict) -> list[tuple[int, dict, float]]:
    """[(ranura, objeto, puntos)] de un tramo."""
    pool = [c for c in cands if lo <= c["eff"] <= hi]
    scored = [(score(c, w, school), -c["id"], c) for c in pool]
    scored = [x for x in scored if x[0] > 0]
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

    def top(pred, n=1):
        res = []
        for sc, _, c in scored:
            if pred(c):
                res.append((c, sc))
                if len(res) >= n:
                    break
        return res

    picks: list[tuple[int, dict, float]] = []
    for inv_set, slot in (((1,), 1), ((2,), 2), ((3,), 3), ((16,), 15), ((5, 20), 5), ((9,), 9), ((10,), 10),
                          ((6,), 6), ((7,), 7), ((8,), 8)):
        for c, sc in top(lambda c: c["inv"] in inv_set):
            picks.append((slot, c, sc))
    for i, (c, sc) in enumerate(top(lambda c: c["inv"] == 11, 2)):
        picks.append((11 + i, c, sc))
    for i, (c, sc) in enumerate(top(lambda c: c["inv"] == 12, 2)):
        picks.append((13 + i, c, sc))
    two = top(lambda c: c["inv"] == TWO_HAND)
    one = top(lambda c: c["inv"] in ONE_HAND)
    off = top(lambda c: c["inv"] == HOLDABLE)
    two_sc = two[0][1] if two else 0
    combo = (one[0][1] if one else 0) + (off[0][1] if off else 0)
    if two and two_sc >= combo:
        picks.append((16, two[0][0], two_sc))
    else:
        if one:
            picks.append((16, one[0][0], one[0][1]))
        if off:
            picks.append((17, off[0][0], off[0][1]))
    if cfg["relic"] is not None:
        rng = top(lambda c: c["inv"] == RELIC)
    else:
        rng = top(lambda c: c["inv"] == RANGED_RIGHT and c["class"] == 2 and c["sub"] == 19)
    for c, sc in rng:
        picks.append((18, c, sc))
    picks.sort(key=lambda x: x[0])
    return picks


# --------------------------------------------------------------------------- salida
def _src_fields(src: dict) -> list[str]:
    if src["kind"] == "quest":
        return [f"quest = {src['quest']}"]
    if src["kind"] == "drop":
        f = []
        if src["npc"]:
            f.append(f"npc = {src['npc']}")
        f.append(f"zone = {src['zone']}")
        f.append(f"pct = {src['pct']:g}")
        return f
    return [f"craft = {src['spell']}", f"prof = \"{PROF_KEY.get(src['prof'], src['prof'].lower())}\"",
            f"skill = {src['skill']}"]


def render(cls: str, cfg: dict, data: dict, weights: dict, meta: dict) -> tuple[str, int]:
    cands = candidates(data, cfg)
    builds = [b for b in weights.get("build", [])]
    lines = [
        "# GENERADO por tools/gen_bis.py — no editar a mano: vuelve a ejecutarlo (docs/GEAR.md).",
        f"# Objetos: ForeverLevelingBiS {meta['flb']} de Thunder (MIT, datos {meta['flb_date']}), redistribuido por Polestar",
        f"# (GPL-3.0, commit {meta['commit'][:8]}) en {REL.as_posix()} (sha256 {meta['sha'][:16]}).",
        "# Elección: Senda, con los pesos de weights.toml de esta carpeta (no es una lista BiS publicada por nadie).",
        "# [[bis]]: from/to = tramo; build; slot = ranura (1 cabeza ... 16 arma, 17 mano izquierda, 18 a distancia o",
        "#   reliquia); id = objeto; quest = misión de la Alianza que lo da; npc/zone/pct = botín (pnj 0: suelto;",
        "#   zone = id de área del cliente; pct = probabilidad, como mínimo 5); craft/prof/skill = receta; race = solo esa raza.",
        f'id = "{cfg["folder"]}-bis-forever"',
        f'class = "{cls}"',
        'kind = "bis"',
        f'title = "Mejor pieza conocida por tramo"',
        "order = 142",
        'status = "unverified"',
        f'sources = ["flb:{meta["flb"]}", "polestar:{meta["commit"][:8]}/{REL.as_posix()}", '
        f'"https://www.curseforge.com/wow/addons/forever-leveling-bis"]',
        f'checked = "{meta["checked"]}"',
        'note = "Objetos y de dónde salen: ForeverLevelingBiS (MIT) a través de Polestar. La elección por ranura y tramo la '
        'hace Senda con sus pesos."',
    ]
    n = 0
    for b in builds:
        for lo, hi in BANDS:
            w = band_weights(weights, b["key"], hi)
            for slot, c, sc in best_for_band(cands, w, b.get("school"), lo, hi, cfg):
                lines += ["", "[[bis]]", f"from = {lo}", f"to = {hi}", f'build = "{b["key"]}"', f"slot = {slot}",
                          f"id = {c['id']}"]
                lines += _src_fields(c["src"])
                if c["race"]:
                    lines.append(f'race = "{c["race"]}"')
                n += 1
    return "\n".join(lines) + "\n", n


def polestar_meta(root: Path, forever: Path, data: dict) -> dict:
    commit = "?"
    head = root / ".git" / "HEAD"
    if head.exists():
        ref = head.read_text(encoding="utf-8").strip()
        if ref.startswith("ref: "):
            rp = root / ".git" / ref[5:]
            if rp.exists():
                commit = rp.read_text(encoding="utf-8").strip()
            else:
                packed = root / ".git" / "packed-refs"
                if packed.exists():
                    for line in packed.read_text(encoding="utf-8").splitlines():
                        if line.endswith(" " + ref[5:]):
                            commit = line.split()[0]
        else:
            commit = ref
    m = re.search(r'version = "([^"]+)", generated = "([^"]+)", licence = "([^"]+)"', data["meta"])
    if not m or m.group(3) != "MIT":
        raise SystemExit("gen_bis: Forever.lua no dice que su ForeverLevelingBiS sea MIT; no se usa.")
    sha = hashlib.sha256(forever.read_bytes()).hexdigest()
    return {"commit": commit, "flb": m.group(1), "flb_date": m.group(2), "sha": sha, "checked": m.group(2)}


def main(argv: list[str] | None = None) -> int:
    setup_stdio()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--polestar", required=True, help="raíz del clon de Polestar (solo se lee)")
    ap.add_argument("--root", default=str(REPO_ROOT), help="raíz de Senda (por defecto, el repo)")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    pole = Path(args.polestar)
    forever = pole / REL
    if not forever.exists():
        print(f"gen_bis: no existe {forever}", file=sys.stderr)
        return 2
    data = read_forever(forever)
    meta = polestar_meta(pole, forever, data)
    root = Path(args.root)
    changed = 0
    for cls, cfg in CLASSES.items():
        folder = root / "data" / "knowledge" / cfg["folder"]
        wfile = folder / "weights.toml"
        if not wfile.exists():
            continue
        with open(wfile, "rb") as fh:
            weights = tomllib.load(fh)
        text, n = render(cls, cfg, data, weights, meta)
        out = folder / "bis-forever.toml"
        old = out.read_text(encoding="utf-8") if out.exists() else None
        if old != text:
            changed += 1
            if not args.check:
                write_text_lf(out, text)
        print(f"{out.relative_to(root).as_posix()}: {n} piezas{' (cambia)' if old != text else ''}")
    return 1 if (args.check and changed) else 0


if __name__ == "__main__":
    sys.exit(main())

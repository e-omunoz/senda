#!/usr/bin/env python3
"""Genera las rutas de subida de las profesiones de fabricación de Forever con datos reales del cliente.

Escribe data/knowledge/general/professions-<prof>.toml (Alquimia, Herrería, Encantamiento, Ingeniería, Peletería,
Sastrería, Cocina y Primeros auxilios) y data/knowledge/general/professions-materials.toml.

Fuentes (solo lectura; nada de esto se commitea en bruto):

- **Tablas del cliente de Forever** (producto `wowf`, build fijado en tools/fetch_wago.py) en .cache/wago/:
  SkillLineAbility (recetas, colores: TrivialSkillLineRankLow = amarillo, TrivialSkillLineRankHigh = gris,
  AcquireMethod 1 = se sabe al aprender la profesión, 3 = retirada, NumSkillUps), SpellEffect (24 crea objeto,
  53 encanta), SpellReagents, SpellTotems (herramientas), SpellCastingRequirements + SpellFocusObject (yunque,
  forja, fuego; rueca y telar no), SpellName(+esES), ItemSparse(+esES: nombres, precios, RequiredSkillRank de las
  recetas), Item (clase y subclase), ItemEffect + ItemXItemEffect (receta -> hechizo que enseña), FactionTemplate
  (bando de los PNJ). Classic Era SkillLineAbility solo para estimar la habilidad de aprendizaje que ninguna lista
  de Forever da (como hace Polestar).
- **Polestar** (GPL-3.0, clon local; --polestar o SENDA_POLESTAR): las listas de instructor de profesión de
  Forever capturadas del servidor (`rust/tests/fixtures/data/sources/forever-tdb/extract.json`: professionSpells
  = habilidad y precio con que el instructor enseña cada receta; vendors / currencyVendors = lo que venden por oro
  o por Favor del mercader), CHECKED_LEARN y HOTFIXES de `forge-data/src/professions/extract.rs`, los nombres de
  instructor por rango y bando de `trainers.rs`, y las rutas de `guides/forever/professions/*.guide` (las compras
  `buy` dicen qué vende un vendedor; las rutas se comparan con la nuestra).
- **forever-db** (GPL-3.0 / CC BY 4.0, .cache/foreverdb o SENDA_FOREVERDB): PNJ, apariciones y marcos de mapa para
  las coordenadas de los instructores; item_source para saber qué receta cae de un PNJ (botín: opcional, nunca se
  exige).

Modelo de eficiencia (docs/PROFESSIONS.md): probabilidad de subir por fabricación 1 en naranja, (gris - habilidad) /
(gris - amarillo) entre amarillo y gris, 0 en gris; fabricaciones esperadas = suma de 1/p. Se minimiza el esfuerzo
esperado con programación dinámica sobre la habilidad 1..300: material de vendedor por su precio, material de
recolección o botín por un esfuerzo por unidad según su nivel (la mitad si el personaje lo recoge solo mientras sube:
paño para todos, hierbas para el alquimista herborista, metal para herreros e ingenieros mineros, cuero para el
peletero desollador, carne para la cocina, polvos para el encantador), productos intermedios de la misma profesión
(madejas) con sus propios puntos, y un pequeño premio a lo útil (bolsas, equipo verde, consumibles) como desempate.

Uso:
    python tools/gen_professions.py [--polestar RUTA] [--wago DIR] [--foreverdb DIR]   # escribe
    python tools/gen_professions.py --check     # sale con 1 si algo cambiaría (sin fuentes: avisa y sale con 0)
    python tools/gen_professions.py --compare   # tabla Senda / Polestar / ruta anterior (docs/PROFESSIONS.md)
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from common import setup_stdio, write_text_lf  # noqa: E402
from fetch_wago import BUILD, wago_dir  # noqa: E402

OUT_DIR = ROOT / "data" / "knowledge" / "general"
EXTRACT_REL = Path("rust/tests/fixtures/data/sources/forever-tdb/extract.json")
GUIDES_REL = Path("guides/forever/professions")
EXTRACT_RS = Path("rust/crates/forge-data/src/professions/extract.rs")
TRAINERS_RS = Path("rust/crates/forge-data/src/professions/trainers.rs")
csv.field_size_limit(1 << 24)

# --------------------------------------------------------------------------------------------- profesiones
@dataclass(frozen=True)
class Prof:
    key: str
    line: int
    kind: str          # primary | secondary
    label: str         # esES
    stem: str          # archivo y guía de Polestar
    natural: frozenset  # categorías de material que el personaje consigue solo mientras sube
    order: int
    why: str           # por qué esta profesión supone esa recolección


PROFS: list[Prof] = [
    Prof("alchemy", 171, "primary", "Alquimia", "alchemy", frozenset({"cloth", "herb"}), 200,
         "supone Herboristería (las hierbas las recoges tú)"),
    Prof("blacksmithing", 164, "primary", "Herrería", "blacksmithing", frozenset({"cloth", "metal"}), 201,
         "supone Minería (mineral y barras los sacas tú)"),
    Prof("enchanting", 333, "primary", "Encantamiento", "enchanting", frozenset({"cloth", "enchanting"}), 202,
         "supone que desencantas los verdes que te caen y los que fabricas con Sastrería"),
    Prof("engineering", 202, "primary", "Ingeniería", "engineering", frozenset({"cloth", "metal"}), 203,
         "supone Minería (mineral, barras y piedra los sacas tú)"),
    Prof("leatherworking", 165, "primary", "Peletería", "leatherworking", frozenset({"cloth", "leather"}), 204,
         "supone Desuello (el cuero lo sacas tú)"),
    Prof("tailoring", 197, "primary", "Sastrería", "tailoring", frozenset({"cloth"}), 205,
         "el paño lo sueltan los humanoides mientras subes: no hace falta recolección"),
    Prof("cooking", 185, "secondary", "Cocina", "cooking", frozenset({"cloth", "meat"}), 206,
         "la carne la sueltan las bestias que matas mientras subes"),
    Prof("firstaid", 129, "secondary", "Primeros auxilios", "first-aid", frozenset({"cloth"}), 207,
         "el paño lo sueltan los humanoides mientras subes"),
]
PROF_BY_KEY = {p.key: p for p in PROFS}
PROF_BY_LINE = {p.line: p for p in PROFS}
MINING = 186
SOD_SPELL_MIN = 400000

RANK_NAMES = ["Aprendiz", "Oficial", "Experto", "Artesano"]
CAPS = [75, 150, 225, 300]
# (habilidad mínima, nivel mínimo) para entrenar cada rango en Forever: Polestar trainers.rs (RANKS y rank_level):
# Aprendiz pide nivel 1 en Forever (Classic: 5); Oficial 10; Experto 20 y Artesano 35 son los de Classic (sin
# confirmar en Forever). Cocina y Primeros auxilios: Oficial sin nivel, Experto es un libro y Artesano una misión
# (habilidad 225).
RANK_GATES = {
    "primary": [(0, 1), (50, 10), (125, 20), (200, 35)],
    "secondary": [(0, 1), (50, 0), (125, 20), (225, 35)],
    "gathering": [(0, 1), (50, 0), (125, 0), (200, 0)],
}
GATES_STATUS = ["verified", "verified", "unverified", "unverified"]

# --------------------------------------------------------------------------------------------- Polestar (copiado)
# extract.rs CHECKED_LEARN: habilidad de aprendizaje vista en Forever para recetas que ninguna lista capturada
# enseña: (hechizo, habilidad, de dónde). in-game/recordings cuentan como comprobadas; classic no.
CHECKED_LEARN = {
    20650: (175, "in-game"), 10482: (175, "in-game"), 10487: (175, "in-game"), 7156: (165, "in-game"),
    9201: (170, "in-game"),
    1255131: (75, "recordings"), 1255132: (75, "recordings"), 1255133: (75, "recordings"),
    1255134: (75, "recordings"), 1255135: (75, "recordings"), 1255136: (75, "recordings"),
    1255110: (100, "recordings"), 1255111: (100, "recordings"), 1255112: (100, "recordings"),
    1255113: (100, "recordings"), 1255114: (100, "recordings"), 1255115: (100, "recordings"),
    1249631: (120, "recordings"), 13028: (175, "classic"),
}
# extract.rs HOTFIXES: (hechizo) -> (aprendizaje, amarillo, verde, gris). Tanning Rack bajó a 125 (6-nov-2026).
HOTFIXES = {1263031: (125, 125, 127, 130)}
# Especializaciones de Ingeniería (no se usan para subir).
SPECIALIZATION = {12715, 12716, 12717, 12718, 12720, 12722, 12755, 12758, 12760, 12908, 13240, 23078, 23489,
                  12759, 12897, 12899, 12902, 12903, 12904, 12905, 12906, 12907, 23129, 23486}

# trainers.rs CURATED: instructores por profesión, bando y grupo (train = Aprendiz y Oficial; novice = solo
# Aprendiz; expert = también Experto; artisan = Artesano). Nombres comprobados por Polestar contra sus datos.
CURATED: dict[str, dict] = {
    "alchemy": {
        "train": (["Lilyssia Nightbreeze", "Tally Berryfizz", "Ainethil", "Sylvanna Forestmoon", "Kylanna", "Alchemist Narett", "Jaxin Chong"],
                  ["Yelmak", "Bena Winterhoof", "Doctor Herbert Halsey", "Doctor Marsh", "Serge Hinott", "Jaxin Chong"]),
        "novice": (["Alchemist Mallory", "Tel'Athir", "Vosur Brakthel", "Ghak Healtouch", "Cyndra Kindwhisper", "Milla Fairancora"],
                   ["Miao'zan", "Whuut", "Kray", "Carolai Anise", "Doctor Martin Felben"]),
        "expert": (["Ainethil", "Kylanna Windwhisper"], ["Doctor Herbert Halsey", "Rogvar"]),
        "artisan": (["Kylanna Windwhisper"], ["Rogvar"]),
    },
    "blacksmithing": {
        "train": (["Therum Deepforge", "Bengus Deepforge", "Rotgath Stonebeard", "Clarise Gnarltree", "Brikk Keencraft"],
                  ["Saru Steelfury", "Karn Stonehoof", "James Van Brunt", "Snarl", "Traugh", "Brikk Keencraft", "Angus Hammerhand"]),
        "novice": (["Smith Argus", "Groum Stonebeard", "Tognus Flintfire", "Dane Lindgren", "Delfrum Flintbeard"],
                   ["Dwukk", "Thrag Stonehoof", "Basil Frye"]),
        "expert": (["Bengus Deepforge", "Brikk Keencraft"], ["Saru Steelfury", "Brikk Keencraft"]),
        "artisan": (["Brikk Keencraft"], ["Brikk Keencraft"]),
    },
    "enchanting": {
        "train": (["Lucan Cordell", "Kitta Firewind", "Gimble Thistlefuzz", "Taladan", "Xylinnia Starshine"],
                  ["Godan", "Teg Dawnstrider", "Lavinia Crowe", "Hgarth"]),
        "novice": (["Betty Quin", "Thonys Pillarstone", "Lalina Summermoon", "Alanna Raveneye"],
                   ["Jhag", "Mot Dawnstrider", "Malcomb Wynn", "Vance Undergloom", "Pa'zula"]),
        "expert": (["Kitta Firewind"], ["Hgarth"]),
        "artisan": (["Annora"], ["Annora"]),
    },
    "engineering": {
        "train": (["Lilliam Sparkspindle", "Springspindle Fizzlegear", "Trixie Quikswitch", "Finbus Geargrind", "Buzzek Bracketswing"],
                  ["Nogg", "Roxxik", "Franklin Lloyd", "Buzzek Bracketswing"]),
        "novice": (["Sprite Jumpsprocket", "Jemma Quikswitch", "Bronk Guzzlegear", "Jenna Lemkenilli", "Twizwick Sprocketgrind"],
                   ["Mukdrak", "Graham Van Talen", "Twizwick Sprocketgrind"]),
        "expert": (["Springspindle Fizzlegear", "Buzzek Bracketswing"], ["Roxxik", "Buzzek Bracketswing"]),
        "artisan": (["Buzzek Bracketswing"], ["Buzzek Bracketswing"]),
    },
    "leatherworking": {
        "train": (["Simon Tanner", "Fimble Finespindle", "Telonis", "Faldron", "Aayndia Floralwind"],
                  ["Karolek", "Una", "Tarn", "Arthur Moore", "Brawn", "Krulmoo Fullmoon", "Narv Hidecrafter"]),
        "novice": (["Adele Fielder", "Randal Worth", "Darianna", "Nadyia Maneweaver", "Gretta Finespindle"],
                   ["Chaw Stronghide", "Kamari", "Dan Golthas", "Shelene Rhobart"]),
        "expert": (["Telonis", "Drakk Stonehand"], ["Una", "Hahrana Ironhide"]),
        "artisan": (["Drakk Stonehand"], ["Hahrana Ironhide"]),
    },
    "tailoring": {
        "train": (["Georgio Bolero", "Sellandus", "Jormund Stonebrow", "Me'lynn", "Grarnik Goodstitch"],
                  ["Magar", "Rhiannon Davis", "Mahani", "Josef Gregorian", "Tepa", "Grarnik Goodstitch"]),
        "novice": (["Eldrin", "Lawrence Schneider", "Uthrar Threx", "Trianna", "Grondal Moonbreeze"],
                   ["Snang", "Victor Ward", "Bowen Brisboise", "Vhan"]),
        "expert": (["Georgio Bolero", "Timothy Worthington"], ["Josef Gregorian", "Daryl Stack"]),
        "artisan": (["Timothy Worthington"], ["Daryl Stack"]),
    },
    "cooking": {
        "train": (["Stephen Ryback", "Tomas", "Daryl Riknussun", "Gremlock Pilsnor", "Alegorn", "Zarrin", "Cook Ghilm", "Crystal Boughman"],
                  ["Zamja", "Aska Mistrunner", "Eunice Burch", "Duhng", "Pyall Silentstride", "Mudduk"]),
        "novice": ([], ["Cook Torka"]),
        "book": (16072, ["Shandrina"], ["Wulan"]),
        "quest": (["Dirge Quikcleave"], ["Dirge Quikcleave"]),
    },
    "firstaid": {
        "train": (["Shaina Fuller", "Michelle Belle", "Nissa Firestone", "Thamner Pol", "Byancie", "Dannelor", "Fremal Doohickey"],
                  ["Arnok", "Rawrk", "Pand Stonebinder", "Mary Edras", "Nurse Neela", "Vira Younghoof"]),
        "book": (16084, ["Deneb Walker"], ["Balai Lok'Wein"]),
        "quest": (["Doctor Gustaf VanHowzen"], ["Doctor Gregory Victor"]),
    },
}

# --------------------------------------------------------------------------------------------- vendedores
# Bienes de comercio que venden los proveedores de suministros por oro en Classic y en Forever (conocimiento
# general; el precio sale de ItemSparse.BuyPrice). Se suman a lo que las listas capturadas y las compras de las
# guías de Polestar dicen que se vende.
TRADE_GOODS = {
    2320, 2321, 4291, 8343, 14341,              # hilos
    2604, 6260, 2605, 4340, 2324, 6261, 4342, 10290,  # tintes y blanqueador
    3371, 3372, 8925, 18256,                    # viales
    2880, 3466,                                 # fundente
    6217, 6338, 11128, 11144,                   # varas
    4470, 4399, 4400,                           # madera
    4289,                                       # sal
    2678, 2692, 3713, 159, 1179, 2596, 30817,   # especias, agua, leche, cerveza
    5956, 2901, 7005,                           # martillo, pico, cuchillo
}
ALLIANCE_RACES = 1 | 4 | 8 | 64      # Humano, Enano, Elfo de la noche, Gnomo (bit id_raza - 1)
ALLOWED_FOCUS = {1, 3, 4, 9}         # Yunque, Forja, Fuego de cocina, Fuego tribal

# Esfuerzo (cobre equivalente) de una fabricación: constantes del modelo (docs/PROFESSIONS.md).
NATURAL_FACTOR = 0.5
SWITCH_COST = 60.0       # cambiar de receta: un viaje al instructor o al vendedor, aprender, otra pila de material
USEFUL_FACTOR = 0.92     # desempate a favor de lo útil

CAT = {5: "cloth", 6: "leather", 7: "metal", 8: "meat", 9: "herb", 10: "elemental", 12: "enchanting"}


# --------------------------------------------------------------------------------------------- lectura
def _rows(path: Path, cols: list[str] | None = None):
    with open(path, encoding="utf-8", newline="") as fh:
        rd = csv.reader(fh)
        head = next(rd)
        idx = {h: i for i, h in enumerate(head)}
        want = cols or head
        pos = [idx[c] for c in want]
        for r in rd:
            if len(r) < len(head):
                continue
            yield dict(zip(want, (r[i] for i in pos)))


def _i(v: str) -> int:
    try:
        return int(v)
    except ValueError:
        try:
            return int(float(v))
        except ValueError:
            return 0


@dataclass
class Tables:
    sla: list[dict]
    era_yellow: dict[int, int]
    effects: dict[int, list[tuple[int, int, float]]]      # spell -> [(effect, itemType, basePointsF)]
    reagents: dict[int, list[tuple[int, int]]]
    totems: dict[int, list[int]]                          # spell -> categorías de herramienta
    focus: dict[int, int]                                 # spell -> SpellFocusObject
    cast_req: set[int]                                    # hechizos con reputación o zona exigida
    spell_en: dict[int, str]
    spell_es: dict[int, str]
    items: dict[int, dict]                                # id -> ItemSparse reducido
    item_es: dict[int, str]
    item_cls: dict[int, tuple[int, int, int]]             # id -> (ClassID, SubclassID, InventoryType)
    taught_by: dict[int, list[int]]                       # hechizo -> objetos de receta
    tool_items: dict[int, list[int]]                      # categoría -> objetos
    faction_side: dict[int, str]                          # faction template -> "A" | "H" | "AH" | ""


def load_tables(wago: Path) -> Tables:
    sla = [dict(spell=_i(r["Spell"]), line=_i(r["SkillLine"]), min=_i(r["MinSkillLineRank"]),
                cls=_i(r["ClassMask"]), acq=_i(r["AcquireMethod"]), grey=_i(r["TrivialSkillLineRankHigh"]),
                yellow=_i(r["TrivialSkillLineRankLow"]), ups=_i(r["NumSkillUps"]), race=_i(r["RaceMasks_0"]) & 0xFFFFFFFF)
           for r in _rows(wago / "SkillLineAbility.csv",
                          ["Spell", "SkillLine", "MinSkillLineRank", "ClassMask", "AcquireMethod",
                           "TrivialSkillLineRankHigh", "TrivialSkillLineRankLow", "NumSkillUps", "RaceMasks_0"])]
    era_yellow = {}
    for r in _rows(wago / "SkillLineAbility_era.csv", ["Spell", "TrivialSkillLineRankLow"]):
        era_yellow[_i(r["Spell"])] = _i(r["TrivialSkillLineRankLow"])
    effects: dict[int, list] = {}
    for r in _rows(wago / "SpellEffect.csv", ["SpellID", "Effect", "EffectItemType", "EffectBasePointsF", "DifficultyID",
                                               "EffectIndex"]):
        if r["DifficultyID"] != "0":
            continue
        e = _i(r["Effect"])
        if e in (24, 53):
            effects.setdefault(_i(r["SpellID"]), []).append((e, _i(r["EffectItemType"]), float(r["EffectBasePointsF"] or 0),
                                                             _i(r["EffectIndex"])))
    for v in effects.values():
        v.sort(key=lambda t: t[3])
    reagents = {}
    for r in _rows(wago / "SpellReagents.csv"):
        lst = []
        for k in range(8):
            it, n = _i(r[f"Reagent_{k}"]), _i(r[f"ReagentCount_{k}"])
            if it > 0 and n > 0:
                lst.append((it, n))
        reagents[_i(r["SpellID"])] = lst
    totems = {}
    for r in _rows(wago / "SpellTotems.csv"):
        cats = [c for c in (_i(r["RequiredTotemCategoryID_0"]), _i(r["RequiredTotemCategoryID_1"])) if c > 0]
        tots = [-t for t in (_i(r["Totem_0"]), _i(r["Totem_1"])) if t > 0]  # objeto concreto: negativo
        if cats or tots:
            totems[_i(r["SpellID"])] = cats + tots
    focus, cast_req = {}, set()
    for r in _rows(wago / "SpellCastingRequirements.csv"):
        s = _i(r["SpellID"])
        if _i(r["RequiresSpellFocus"]):
            focus[s] = _i(r["RequiresSpellFocus"])
        if _i(r["MinFactionID"]) or _i(r["RequiredAreasID"]) > 0:
            cast_req.add(s)
    spell_en = {_i(r["ID"]): r["Name_lang"] for r in _rows(wago / "SpellName.csv", ["ID", "Name_lang"])}
    spell_es = {_i(r["ID"]): r["Name_lang"] for r in _rows(wago / "SpellName_esES.csv", ["ID", "Name_lang"])}
    items = {}
    for r in _rows(wago / "ItemSparse.csv", ["ID", "Display_lang", "BuyPrice", "SellPrice", "VendorStackCount",
                                              "OverallQualityID", "RequiredSkillRank", "RequiredSkill", "RequiredAbility",
                                              "MinFactionID", "Bonding", "TotemCategoryID", "ItemLevel", "RequiredLevel"]):
        items[_i(r["ID"])] = dict(name=r["Display_lang"], buy=_i(r["BuyPrice"]), sell=_i(r["SellPrice"]),
                                  stack=max(1, _i(r["VendorStackCount"])), q=_i(r["OverallQualityID"]),
                                  req_rank=_i(r["RequiredSkillRank"]), req_skill=_i(r["RequiredSkill"]),
                                  ability=_i(r["RequiredAbility"]), rep=_i(r["MinFactionID"]), bond=_i(r["Bonding"]),
                                  totem=_i(r["TotemCategoryID"]), ilvl=_i(r["ItemLevel"]), level=_i(r["RequiredLevel"]))
    item_es = {_i(r["ID"]): r["Display_lang"] for r in _rows(wago / "ItemSparse_esES.csv", ["ID", "Display_lang"])}
    item_cls = {_i(r["ID"]): (_i(r["ClassID"]), _i(r["SubclassID"]), _i(r["InventoryType"]))
                for r in _rows(wago / "Item.csv", ["ID", "ClassID", "SubclassID", "InventoryType"])}
    eff_spell = {}
    for r in _rows(wago / "ItemEffect.csv", ["ID", "TriggerType", "SpellID"]):
        if r["TriggerType"] == "6":
            eff_spell[_i(r["ID"])] = _i(r["SpellID"])
    taught_by: dict[int, list[int]] = {}
    for r in _rows(wago / "ItemXItemEffect.csv", ["ItemEffectID", "ItemID"]):
        sp = eff_spell.get(_i(r["ItemEffectID"]))
        if sp:
            taught_by.setdefault(sp, []).append(_i(r["ItemID"]))
    for v in taught_by.values():
        v.sort()
    tool_items: dict[int, list[int]] = {}
    for iid, it in items.items():
        if it["totem"]:
            tool_items.setdefault(it["totem"], []).append(iid)
    for v in tool_items.values():
        v.sort()
    faction_side = {}
    for r in _rows(wago / "FactionTemplate.csv", ["ID", "FriendGroup", "EnemyGroup", "FactionGroup"]):
        fr, en, grp = _i(r["FriendGroup"]), _i(r["EnemyGroup"]), _i(r["FactionGroup"])
        a = (fr & 2 or grp & 2) and not en & 2
        h = (fr & 4 or grp & 4) and not en & 4
        neutral = not en & 6 and not (fr & 6 or grp & 6)
        faction_side[_i(r["ID"])] = "AH" if (a and h) or neutral else ("A" if a else ("H" if h else ""))
    return Tables(sla, era_yellow, effects, reagents, totems, focus, cast_req, spell_en, spell_es, items, item_es,
                  item_cls, taught_by, tool_items, faction_side)


@dataclass
class Polestar:
    commit: str
    trained: dict[int, tuple[int, int]]          # hechizo -> (habilidad, cobre)
    trained_classic: dict[int, tuple[int, int]]
    trainer_any: set[int]                        # hechizos que alguna lista enseña
    vendors: dict[int, list[int]]                # pnj -> objetos (por oro)
    currency: set[int]                           # objetos que solo se venden por moneda (Favor del mercader)
    currency_npc: dict[int, list[int]]
    guide_buys: set[int]
    guides: dict[str, str]
    tdb_release: str
    limited: set[int] = field(default_factory=set)   # objetos que los vendedores tienen en cantidad limitada


def load_polestar(root: Path) -> Polestar:
    ex = json.loads((root / EXTRACT_REL).read_text(encoding="utf-8"))
    trained = {int(k): (int(v[0]), int(v[1])) for k, v in ex["professionSpells"].items()}
    classic = {int(k): (int(v[0]), int(v[1])) for k, v in ex["professionSpellsClassic"].items()}
    any_ = {int(s) for lst in ex["professionTrainersAny"].values() for s in lst}
    any_ |= {int(s) for lst in ex["professionTrainers"].values() for s in lst}
    cur_rows = {(int(n), int(i)) for n, lst in ex["currencyVendors"].items() for i in lst}
    gold = {(int(n), int(i)) for n, lst in ex["vendors"].items() for i in lst}
    gold_items = {i for (n, i) in gold if (n, i) not in cur_rows}
    currency = {i for (_, i) in cur_rows if i not in gold_items}
    vendors = {int(n): sorted(int(i) for i in lst if (int(n), int(i)) not in cur_rows) for n, lst in ex["vendors"].items()}
    currency_npc = {int(n): sorted(int(i) for i in lst) for n, lst in ex["currencyVendors"].items()}
    guides, buys = {}, set()
    for p in sorted((root / GUIDES_REL).glob("*.guide")):
        text = p.read_text(encoding="utf-8")
        guides[p.stem] = text
        for m in re.finditer(r"^  buy (\d+)(.*)$", text, re.M):
            if "only Horde" not in m.group(2):
                buys.add(int(m.group(1)))
    limited = {int(i) for lst in ex.get("vendorLimits", {}).values() for i in lst}
    return Polestar(git_head(root), trained, classic, any_, vendors, currency, currency_npc, buys, guides,
                    ex.get("meta", {}).get("release", "?"), limited)


def git_head(root: Path) -> str:
    try:
        return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "?"


@dataclass
class ForeverDB:
    version: str
    npc: dict[int, dict]
    by_name: dict[str, list[int]]
    spawns: dict[int, list[tuple[int, float, float]]]
    drops: set[int]                    # objetos que sueltan PNJ u objetos del mundo
    frames: object


def load_foreverdb(path: str | None) -> ForeverDB:
    from foreverdb.db import Frames, read_jsonl, resolve_foreverdb
    root = resolve_foreverdb(path)
    data = root / "data"
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    npc, by_name = {}, {}
    for r in read_jsonl(data / "npc.jsonl"):
        npc[int(r["id"])] = r
        by_name.setdefault(str(r.get("name") or "").lower(), []).append(int(r["id"]))
    spawns: dict[int, list] = {}
    for r in read_jsonl(data / "spawn.jsonl"):
        if r["kind"] == "npc":
            spawns.setdefault(int(r["id"]), []).append((int(r["map"]), float(r["x"]), float(r["y"])))
    drops = {int(r["item"]) for r in read_jsonl(data / "item_source.jsonl")}
    frames = Frames(list(read_jsonl(data / "ui_map.jsonl")))
    return ForeverDB(str(index.get("version", "?")), npc, by_name, spawns, drops, frames)


def default_foreverdb() -> str | None:
    env = os.environ.get("SENDA_FOREVERDB")
    if env:
        return env
    own = ROOT / ".cache" / "foreverdb"
    if (own / "data" / "quest.jsonl").exists():
        return str(own)
    from fetch_wago import _main_checkout
    main = _main_checkout()
    if main and (main / ".cache" / "foreverdb" / "data" / "quest.jsonl").exists():
        return str(main / ".cache" / "foreverdb")
    return None


# --------------------------------------------------------------------------------------------- recetas
@dataclass
class Recipe:
    spell: int
    prof: str
    name_en: str
    name_es: str
    item: int | None             # objeto creado (None: encantamiento)
    count: float                 # objetos por fabricación
    reagents: list[tuple[int, int]]
    learn: int
    yellow: int
    green: int
    grey: int
    ups: int
    source: str                  # trainer | known | vendor | currency | drop | unknown
    learn_from: str              # client | sniffed | in-game | recordings | recipe-item | classic | estimate | hotfix
    cost: int                    # precio de aprenderla (cobre; 0 si no se sabe o es gratis)
    recipe_item: int | None
    tools: list[int]             # categorías (positivas) u objetos (negativos)
    status: str
    usable: bool = True          # se puede usar en la ruta (Alianza, sin rueca, sin especialización...)
    why_not: str = ""

    def p(self, s: int) -> float:
        """Probabilidad de subir un punto fabricando con habilidad s."""
        if s < self.learn or s >= self.grey:
            return 0.0
        if s < self.yellow:
            return 1.0
        return (self.grey - s) / max(1, self.grey - self.yellow)


def recipe_source_of_item(ri: int, ps: Polestar, fdb: ForeverDB, t: Tables) -> str:
    if ri in ps.currency:
        return "currency"
    alliance_vendor = False
    for npc, lst in ps.vendors.items():
        if ri in lst and npc_side(npc, fdb, t) in ("A", "AH"):
            alliance_vendor = True
    if alliance_vendor or ri in ps.guide_buys:
        return "vendor"
    if ri in fdb.drops:
        return "drop"
    return "unknown"


def npc_side(npc: int, fdb: ForeverDB, t: Tables) -> str:
    r = fdb.npc.get(npc)
    if not r:
        return ""
    return t.faction_side.get(int(r.get("faction_template") or 0), "")


def extract_recipes(t: Tables, ps: Polestar, fdb: ForeverDB, prof: Prof) -> list[Recipe]:
    out, seen = [], set()
    for row in t.sla:
        if row["line"] != prof.line:
            continue
        sp = row["spell"]
        effs = t.effects.get(sp, [])
        create = next((e for e in effs if e[0] == 24 and e[1] > 0), None)
        enchant = any(e[0] == 53 for e in effs)
        if (not create and not enchant) or row["acq"] == 3 or sp in seen:
            continue
        seen.add(sp)
        item = create[1] if create else None
        count = max(1.0, round(create[2])) if create else 1.0
        yellow, grey = row["yellow"], row["grey"]
        if sp >= SOD_SPELL_MIN and sp in t.era_yellow:
            continue  # Season of Discovery: no existe en Forever
        recipe_items = [i for i in t.taught_by.get(sp, []) if i in t.items and t.item_cls.get(i, (0,))[0] == 9]
        best = None
        for ri in recipe_items:
            src = recipe_source_of_item(ri, ps, fdb, t)
            rank = {"vendor": 0, "currency": 1, "drop": 2, "unknown": 3}[src]
            if best is None or rank < best[0]:
                best = (rank, ri, src)
        cost, recipe_item, status = 0, None, "verified"
        if row["acq"] == 1:
            learn, source, frm = 1, "known", "client"
        elif sp in ps.trained:
            learn, cost = max(1, ps.trained[sp][0]), ps.trained[sp][1]
            source, frm = "trainer", "sniffed"
        elif sp in CHECKED_LEARN:
            learn, frm = CHECKED_LEARN[sp]
            source = "trainer"
            if frm == "classic":
                status = "unverified"
        elif best and best[2] == "vendor":
            # un vendedor de la Alianza la vende por oro (lista capturada o compra de una guía de Polestar)
            _, recipe_item, source = best
            learn, frm = max(1, t.items[recipe_item]["req_rank"]), "recipe-item"
            cost = t.items[recipe_item]["buy"]
        elif sp in ps.trained_classic and yellow > 0:
            # La lista de instructor de la base de datos del servidor de Forever (TrinityCore, la de Classic) la
            # enseña; su habilidad se mueve tanto como Forever movió el amarillo (método de Polestar).
            era_y = t.era_yellow.get(sp, yellow)
            learn = max(1, min(yellow, yellow - max(0, era_y - ps.trained_classic[sp][0])))
            source, frm, status = "trainer", "classic", "unverified"
        elif best:
            _, recipe_item, source = best
            learn, frm = max(1, t.items[recipe_item]["req_rank"]), "recipe-item"
        elif row["min"] > 1:
            learn, source, frm = row["min"], "trainer", "client"
        elif yellow > 0:
            learn, source, frm, status = yellow, "trainer", "estimate", "unverified"
        else:
            learn, source, frm, status = 1, "trainer", "estimate", "unverified"
        if sp in HOTFIXES:
            learn, yellow, _g, grey = HOTFIXES[sp]
            frm = "hotfix"
        green = (yellow + grey) // 2 if grey else 0
        r = Recipe(sp, prof.key, t.spell_en.get(sp, f"Spell {sp}"), t.spell_es.get(sp) or t.spell_en.get(sp, ""),
                   item, count, t.reagents.get(sp, []), learn, yellow or learn, green, grey, max(1, row["ups"]),
                   source, frm, cost, recipe_item, t.totems.get(sp, []), status)
        # ¿Se puede usar para subir con un personaje de la Alianza?
        if grey <= 0:
            r.usable, r.why_not = False, "sin colores"
        elif row["cls"]:
            r.usable, r.why_not = False, "de una clase"
        elif row["race"] and (row["race"] & ALLIANCE_RACES) != ALLIANCE_RACES:
            r.usable, r.why_not = False, "de otra raza o bando"
        elif sp in SPECIALIZATION:
            r.usable, r.why_not = False, "especialización"
        elif sp in t.cast_req:
            r.usable, r.why_not = False, "pide reputación o un sitio"
        elif sp in t.focus and t.focus[sp] not in ALLOWED_FOCUS:
            r.usable, r.why_not = False, "pide rueca, telar u otro sitio"
        elif source in ("currency", "drop", "unknown"):
            r.usable, r.why_not = False, {"currency": "patrón por Favor del mercader", "drop": "receta de botín",
                                          "unknown": "receta sin origen conocido"}[source]
        elif source == "trainer" and frm == "estimate" and sp not in ps.trainer_any and sp < 1_000_000:
            r.usable, r.why_not = False, "ningún instructor la enseña"
        elif recipe_item and t.items[recipe_item]["ability"]:
            r.usable, r.why_not = False, "especialización"
        elif recipe_item and t.items[recipe_item]["rep"]:
            r.usable, r.why_not = False, "pide reputación"
        out.append(r)
    out.sort(key=lambda r: (r.learn, r.yellow, r.spell))
    return out


# --------------------------------------------------------------------------------------------- materiales
@dataclass
class Valuer:
    t: Tables
    ps: Polestar
    fdb: ForeverDB
    prof: Prof
    by_item: dict[int, Recipe]          # objeto -> receta de esta profesión que lo crea
    smelt: dict[int, Recipe]            # objeto -> receta de Minería (fundir)
    vendor_goods: set[int]
    cache: dict = field(default_factory=dict)

    def category(self, item: int) -> str:
        c, sc, _ = self.t.item_cls.get(item, (0, 0, 0))
        if c != 7:
            return "other"
        if sc == 8 and self.t.items.get(item, {}).get("name", "").startswith("Raw "):
            return "fish"   # pescado: solo es «natural» para quien pesca
        return CAT.get(sc, "other")

    def is_vendor(self, item: int) -> bool:
        return item in self.vendor_goods and self.t.items.get(item, {}).get("buy", 0) > 0

    def vendor_price(self, item: int) -> float:
        it = self.t.items[item]
        return it["buy"] / it["stack"]

    def gathered(self, item: int) -> float:
        it = self.t.items.get(item)
        if not it:
            return 100.0
        base = max(4.0 * it["sell"], 2.0 * max(1, it["ilvl"]) ** 1.5, 5.0)
        return base * (NATURAL_FACTOR if self.category(item) in self.prof.natural else 1.0)

    def unit(self, item: int, depth: int = 0) -> float:
        """Esfuerzo de una unidad de material (cobre equivalente)."""
        if item in self.cache:
            return self.cache[item]
        if self.is_vendor(item):
            v = self.vendor_price(item)
        elif item in self.by_item and depth < 4:
            v = self.crafted(item, depth)
            if self.gatherable(item):
                v = min(v, self.gathered(item))
        elif item in self.smelt and depth < 4:
            r = self.smelt[item]
            v = min(self.gathered(item), sum(self.unit(i, depth + 1) * n for i, n in r.reagents) / r.count)
        else:
            v = self.gathered(item)
        self.cache[item] = v
        return v

    def crafted(self, item: int, depth: int = 0) -> float:
        r = self.by_item[item]
        return sum(self.unit(i, depth + 1) * n for i, n in r.reagents) / r.count

    def gatherable(self, item: int) -> bool:
        """¿Se consigue sin fabricarlo (botín, recolección)? Las madejas y las barras no."""
        cat = self.category(item)
        if cat == "cloth":
            return False
        return item in self.fdb.drops or cat in ("herb", "meat", "fish", "enchanting", "elemental")

    def made_here(self, item: int) -> bool:
        """¿Conviene fabricar este material con la propia profesión (madejas, cuero curtido)?"""
        if item not in self.by_item or self.is_vendor(item):
            return False
        return not self.gatherable(item) or self.crafted(item) < self.gathered(item)

    def raw(self, item: int, n: float, out: dict, depth: int = 0) -> None:
        """Material en bruto (recursivo por lo que se fabrica aquí) de n unidades."""
        if depth < 4 and self.made_here(item):
            r = self.by_item[item]
            for i, m in r.reagents:
                self.raw(i, n * m / r.count, out, depth + 1)
        else:
            out[item] = out.get(item, 0.0) + n

    def where(self, item: int) -> str:
        if self.is_vendor(item):
            return "vendedor"
        if item in self.by_item:
            return "fabricado"
        cat = self.category(item)
        return {"cloth": "paño de humanoides", "leather": "desuello", "metal": "minería", "herb": "herboristería",
                "meat": "bestias", "enchanting": "desencantar", "elemental": "botín elemental"}.get(cat, "botín o subasta")


def vendor_goods(t: Tables, ps: Polestar, fdb: ForeverDB) -> set[int]:
    goods = set(TRADE_GOODS) | set(ps.guide_buys)
    for npc, lst in ps.vendors.items():
        if npc_side(npc, fdb, t) in ("A", "AH"):
            goods.update(lst)
    goods -= ps.currency
    # Lo que se vende en cantidad limitada (Polvo extraño, Esencia mágica inferior: 1-4 cada vez) no cuenta como
    # bien de vendedor: para subir hacen falta decenas.
    goods -= ps.limited - TRADE_GOODS
    # Las recetas no son material: fuera.
    return {g for g in goods if t.item_cls.get(g, (0,))[0] != 9}


def useful(r: Recipe, t: Tables) -> bool:
    if r.item is None:
        return r.prof == "enchanting"   # encantamientos: se los pones a tu equipo
    c, sc, inv = t.item_cls.get(r.item, (0, 0, 0))
    q = t.items.get(r.item, {}).get("q", 1)
    if c == 1:                    # bolsas
        return True
    if c in (2, 4) and q >= 2:    # equipo verde: se usa o se desencanta
        return True
    if c == 0:                    # consumibles: pociones, comida, vendas
        return True
    return False


# --------------------------------------------------------------------------------------------- programación dinámica
@dataclass
class Action:
    recipe: Recipe
    inter: list[tuple[Recipe, float]]     # intermedios de esta profesión: (receta, fabricaciones por fabricación)
    raw: float                            # esfuerzo de material por fabricación (con intermedios)
    once: float                           # coste una vez (aprender, herramienta)
    tool_recipes: list[Recipe]


def make_actions(recipes: list[Recipe], val: Valuer) -> list[Action]:
    usable = [r for r in recipes if r.usable]
    by_item = {r.item: r for r in usable if r.item}
    acts = []
    for r in usable:
        inter, raw = [], 0.0
        for it, n in r.reagents:
            b = by_item.get(it)
            if b and b is not r and val.made_here(it):
                per = n / b.count
                inter.append((b, per))
                raw += per * sum(val.unit(i) * m for i, m in b.reagents)
            else:
                raw += val.unit(it) * n
        once = float(r.cost)
        tool_recipes, ok = [], True
        for tool in r.tools:
            ids = [-tool] if tool < 0 else val.t.tool_items.get(tool, [])
            if any(val.is_vendor(i) for i in ids):
                once += min(val.vendor_price(i) for i in ids if val.is_vendor(i))
                continue
            made = [by_item[i] for i in ids if i in by_item]
            if made:
                tr = min(made, key=lambda x: x.learn)
                tool_recipes.append(tr)
                once += sum(val.unit(i) * m for i, m in tr.reagents)
                continue
            if ids:
                once += min(val.gathered(i) for i in ids)
            else:
                ok = False
        if not ok:
            continue
        if useful(r, val.t):
            raw *= USEFUL_FACTOR
        acts.append(Action(r, inter, raw, once, tool_recipes))
    return acts


def gain(a: Action, s: int) -> float:
    g = a.recipe.p(s) * a.recipe.ups
    if g <= 0:
        return 0.0
    for b, per in a.inter:
        if b.learn > s:
            return 0.0
        g += per * b.p(s) * b.ups
    for tr in a.tool_recipes:
        if tr.learn > s:
            return 0.0
    return g


def solve(acts: list[Action], lo: int = 1, hi: int = 300) -> list[tuple[int, Action | None, float]]:
    """Ruta óptima de lo a hi: lista de (habilidad, acción, ganancia esperada por fabricación) por punto.

    Estado: (habilidad, receta actual). Seguir con la misma receta cuesta su material / ganancia; cambiar suma
    SWITCH_COST y el coste de una vez de la nueva (aprenderla, su herramienta)."""
    INF = float("inf")
    n = len(acts)
    prev_best, prev_arg = 0.0, -1
    V = [0.0] * n
    back: list[list[int]] = []
    for s in range(lo, hi):
        newV = [INF] * n
        choice = [-1] * n
        for k, a in enumerate(acts):
            g = gain(a, s)
            if g <= 0:
                continue
            step = a.raw / g
            stay = V[k] if s > lo and V[k] < INF else INF
            switch = prev_best + SWITCH_COST + a.once
            if stay <= switch:
                newV[k], choice[k] = stay + step, k
            else:
                newV[k], choice[k] = switch + step, prev_arg
        back.append(choice)
        V = newV
        best = min(range(n), key=lambda k: (V[k], acts[k].recipe.spell)) if n else -1
        if best < 0 or V[best] == INF:
            # nada sube aquí: se corta
            back.pop()
            return _walk(acts, back, lo, s, V_last=None, last=prev_arg)
        prev_best, prev_arg = V[best], best
    return _walk(acts, back, lo, hi, V_last=V, last=prev_arg)


def _walk(acts, back, lo, end, V_last, last):
    path = []
    k = last
    for idx in range(len(back) - 1, -1, -1):
        s = lo + idx
        path.append((s, acts[k] if k >= 0 else None, gain(acts[k], s) if k >= 0 else 0.0))
        k = back[idx][k] if k >= 0 else -1
        # back[idx][k] es el estado de s-1: si es otra receta, cambiamos ahí
    path.reverse()
    return path


# --------------------------------------------------------------------------------------------- segmentos
@dataclass
class Segment:
    frm: int
    to: int
    action: Action
    crafts: float
    inter_crafts: dict[int, float]


def segments(path) -> list[Segment]:
    segs: list[Segment] = []
    for s, a, g in path:
        if a is None:
            break
        cap_break = segs and segs[-1].to in CAPS[:-1]
        if segs and segs[-1].action is a and segs[-1].to == s and not cap_break:
            seg = segs[-1]
        else:
            seg = Segment(s, s, a, 0.0, {})
            segs.append(seg)
        seg.to = s + 1
        seg.crafts += 1.0 / g
        for b, per in a.inter:
            seg.inter_crafts[b.spell] = seg.inter_crafts.get(b.spell, 0.0) + per / g
    return segs


def route_cost(path) -> tuple[float, float, int]:
    """Fabricaciones esperadas, esfuerzo (material + aprender + cambios de receta) y habilidad alcanzada."""
    crafts = sum(1.0 / g for _, a, g in path if a)
    effort = sum(a.raw / g for _, a, g in path if a)
    prev = None
    for _, a, _ in path:
        if a is not None and a is not prev:
            effort += SWITCH_COST + a.once
        prev = a
    reached = path[-1][0] + 1 if path and path[-1][1] else 1
    return crafts, effort, reached


MIN_RUN = 3


def smooth(path):
    """Quita los tramos de 1-2 puntos entre dos recetas (215-216 de otra cosa y vuelta): si la receta de al lado
    también da puntos ahí, los hace ella. Cuesta un poco más de material pero ahorra un cambio de receta."""
    path = list(path)
    changed = True
    while changed:
        changed = False
        runs, i = [], 0
        while i < len(path):
            j = i
            while j + 1 < len(path) and path[j + 1][1] is path[i][1]:
                j += 1
            runs.append((i, j))
            i = j + 1
        for k, (i, j) in enumerate(runs):
            if j - i + 1 >= MIN_RUN or len(runs) == 1:
                continue
            for nb in ([runs[k - 1]] if k > 0 else []) + ([runs[k + 1]] if k + 1 < len(runs) else []):
                a = path[nb[0]][1]
                if a is None:
                    continue
                gains = [gain(a, path[x][0]) for x in range(i, j + 1)]
                if all(g > 0 for g in gains):
                    for x, g in zip(range(i, j + 1), gains):
                        path[x] = (path[x][0], a, g)
                    changed = True
                    break
            if changed:
                break
    return path


# --------------------------------------------------------------------------------------------- instructores
UIMAP_ES = {
    1453: "Ventormenta", 1455: "Forjaz", 1457: "Darnassus", 1429: "Bosque de Elwynn", 1426: "Dun Morogh",
    1438: "Teldrassil", 1432: "Loch Modan", 1439: "Costa Oscura", 1436: "Páramos de Poniente", 1433: "Montañas Crestagrana",
    1431: "Bosque del Ocaso", 1437: "Los Humedales", 1440: "Vallefresno", 1445: "Marjal Revolcafango",
    1434: "Vega de Tuercespina", 1417: "Tierras Altas de Arathi", 1424: "Laderas de Trabalomas", 1446: "Tanaris",
    1443: "Desolace", 1444: "Feralas", 1418: "Tierras Inhóspitas", 1454: "Orgrimmar", 1456: "Cima del Trueno",
    1458: "Entrañas", 1413: "Los Baldíos", 1411: "Durotar", 1412: "Mulgore", 1420: "Claros de Tirisfal",
    1421: "Bosque de Argénteos", 1442: "Sierra Espolón", 1441: "Las Mil Agujas", 1447: "Azshara",
}
try:  # el resto de zonas, con los mismos nombres que usa la web y los raros
    from gen_rares import UIMAP_NAMES as _UIMAP_NAMES
    for _k, _v in _UIMAP_NAMES.items():
        UIMAP_ES.setdefault(_k, _v)
except ImportError:  # pragma: no cover
    pass
CITY_ORDER = {1453: 0, 1455: 1, 1457: 2}   # Ventormenta, Forjaz, Darnassus primero


def trainer_entries(prof: Prof, fdb: ForeverDB, t: Tables) -> tuple[list[dict], list[str]]:
    cur = CURATED.get(prof.key, {})
    warnings = []
    groups = {g: cur.get(g, ([], [])) for g in ("train", "novice", "expert", "artisan")}
    out: dict[tuple[str, int], dict] = {}
    for side_i, side in enumerate(("Alliance", "Horde")):
        code = "A" if side_i == 0 else "H"
        for g, names in groups.items():
            for name in names[side_i]:
                ids = [i for i in fdb.by_name.get(name.lower(), [])
                       if npc_side(i, fdb, t) in (code, "AH") and fdb.spawns.get(i)]
                if not ids:
                    if g == "artisan" and fdb.by_name.get(name.lower()):
                        ids = fdb.by_name[name.lower()][:1]
                    else:
                        warnings.append(f"{prof.label} {side}: «{name}» sin PNJ con apariciones en forever-db")
                        continue
                npc = min(ids)
                key = (side, npc)
                e = out.setdefault(key, {"npc": npc, "name": fdb.npc[npc]["name"], "faction": side, "ranks": set()})
                if g == "train":
                    e["ranks"].update(["Aprendiz", "Oficial"])
                elif g == "novice":
                    e["ranks"].add("Aprendiz")
                elif g == "expert":
                    e["ranks"].update(["Aprendiz", "Oficial", "Experto"])
                elif g == "artisan":
                    e["ranks"].add("Artesano")
    res = []
    for (side, npc), e in out.items():
        sp = sorted(fdb.spawns.get(npc, []))
        at = None
        if sp:
            m, x, y = sp[0]
            hit = fdb.frames.to_uimap(m, x, y)
            if hit:
                place = UIMAP_ES.get(hit[0], f"mapa {hit[0]}")
                at = [hit[0], round(hit[1], 1), round(hit[2], 1), f"{e['name']} ({place})"]
        ranks = [r for r in RANK_NAMES if r in e["ranks"]]
        ent = {"prof": prof.key, "npc": npc, "name": e["name"], "faction": side, "ranks": ranks}
        if at:
            ent["at"] = at
        else:
            ent["text"] = {"Annora": "Dentro de Uldaman (Tierras Inhóspitas): aparece al limpiar su zona."}.get(
                e["name"], "Sin coordenadas en forever-db.")
        res.append(ent)
    res.sort(key=lambda e: (e["faction"] != "Alliance", CITY_ORDER.get((e.get("at") or [0])[0], 9),
                            -len(e["ranks"]), e["npc"]))
    return res, warnings


def book_quest(prof: Prof, fdb: ForeverDB, t: Tables) -> list[dict]:
    cur = CURATED.get(prof.key, {})
    out = []
    if "book" in cur:
        item, a, h = cur["book"]
        for side, names in (("Alliance", a), ("Horde", h)):
            for name in names:
                ids = [i for i in fdb.by_name.get(name.lower(), []) if fdb.spawns.get(i)]
                if not ids:
                    continue
                npc = min(ids)
                m, x, y = sorted(fdb.spawns[npc])[0]
                hit = fdb.frames.to_uimap(m, x, y)
                ent = {"prof": prof.key, "npc": npc, "name": fdb.npc[npc]["name"], "faction": side, "ranks": ["Experto"],
                       "book": item}
                if hit:
                    ent["at"] = [hit[0], round(hit[1], 1), round(hit[2], 1),
                                 f"{fdb.npc[npc]['name']} ({UIMAP_ES.get(hit[0], 'mapa %d' % hit[0])})"]
                out.append(ent)
    if "quest" in cur:
        a, h = cur["quest"]
        for side, names in (("Alliance", a), ("Horde", h)):
            for name in names:
                ids = [i for i in fdb.by_name.get(name.lower(), []) if fdb.spawns.get(i)]
                if not ids:
                    continue
                npc = min(ids)
                m, x, y = sorted(fdb.spawns[npc])[0]
                hit = fdb.frames.to_uimap(m, x, y)
                ent = {"prof": prof.key, "npc": npc, "name": fdb.npc[npc]["name"], "faction": side, "ranks": ["Artesano"],
                       "quest": True}
                if hit:
                    ent["at"] = [hit[0], round(hit[1], 1), round(hit[2], 1),
                                 f"{fdb.npc[npc]['name']} ({UIMAP_ES.get(hit[0], 'mapa %d' % hit[0])})"]
                out.append(ent)
    return out


# --------------------------------------------------------------------------------------------- TOML
def q(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(round(v, 1)) if v != int(v) else str(int(v))
    if isinstance(v, str):
        return q(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(toml_value(x) for x in v) + "]"
    raise TypeError(type(v))


def money(c: int) -> str:
    g, s, cc = c // 10000, (c // 100) % 100, c % 100
    parts = []
    if g:
        parts.append(f"{g} o")
    if s:
        parts.append(f"{s} p")
    if cc or not parts:
        parts.append(f"{cc} c")
    return " ".join(parts)


LEARN_TEXT = {
    "known": "la sabes al aprender la profesión",
    "sniffed": "instructor (lista capturada de Forever)",
    "in-game": "instructor (visto en el juego)",
    "recordings": "instructor (grabaciones de jugadores)",
    "client": "instructor",
    "classic": "instructor (habilidad estimada desde Classic: sin confirmar)",
    "estimate": "instructor (habilidad estimada: sin confirmar)",
    "hotfix": "instructor (corrección oficial de Forever)",
}


def learn_text(r: Recipe, t: Tables) -> str:
    if r.source == "vendor" and r.recipe_item:
        return f"receta «{t.item_es.get(r.recipe_item) or t.items[r.recipe_item]['name']}» del vendedor ({money(r.cost)}), desde {r.learn}"
    if r.source == "known":
        return LEARN_TEXT["known"]
    txt = LEARN_TEXT.get(r.learn_from, "instructor")
    return f"{txt}, desde {r.learn}" + (f" ({money(r.cost)})" if r.cost else "")


def seg_sources(r: Recipe, ps: Polestar) -> list[str]:
    src = [f"wago:{BUILD}/SkillLineAbility/{r.spell}"]
    if r.learn_from == "sniffed":
        src.append(f"polestar:{ps.commit[:12]}/forever-tdb:{ps.tdb_release}/professionSpells/{r.spell}")
    elif r.learn_from in ("in-game", "recordings", "classic", "hotfix"):
        src.append(f"polestar:{ps.commit[:12]}/{EXTRACT_RS.as_posix()}")
    elif r.learn_from == "recipe-item":
        src.append(f"wago:{BUILD}/ItemSparse/{r.recipe_item}")
    return src


def render_prof(prof: Prof, segs: list[Segment], recipes: list[Recipe], val: Valuer, trainers: list[dict],
                ps: Polestar, fdb: ForeverDB, summary: dict) -> str:
    t = val.t
    L = []
    L.append(f"# GENERADO por tools/gen_professions.py: no editar a mano (regenerar; docs/PROFESSIONS.md).")
    L.append(f"# Tablas del cliente de Forever {BUILD} (wago.tools), Polestar {ps.commit[:12]} (listas de instructor de "
             f"{ps.tdb_release}, trainers.rs) y forever-db {fdb.version}.")
    L.append(f"id = {q('general-professions-' + prof.key)}")
    L.append('class = "ANY"')
    L.append('kind = "professions"')
    L.append(f"title = {q(prof.label + ' 1-300')}")
    L.append(f"prof = {q(prof.key)}")
    L.append(f"prof_kind = {q(prof.kind)}")
    L.append(f"order = {prof.order}")
    verified = all(s.action.recipe.status == "verified" for s in segs)
    L.append(f"status = {q('verified' if verified else 'unverified')}")
    L.append(f"sources = {toml_value(['wago:' + BUILD, 'polestar:' + ps.commit, 'foreverdb:' + fdb.version])}")
    L.append(f"assumes = {q(prof.why)}")
    L.append(f"crafts = {round(summary['crafts'])}")
    L.append(f"reach = {summary['reach']}")
    note = (f"Ruta calculada: unas {round(summary['crafts'])} fabricaciones esperadas de 1 a {summary['reach']}. "
            f"Esfuerzo mínimo con material de vendedor por su precio y recolectado por su nivel; {prof.why}.")
    if summary["reach"] < 300:
        note += f" Más allá de {summary['reach']} ninguna receta de la Alianza que se pueda conseguir sin botín sube puntos."
    L.append(f"note = {q(note)}")
    # rangos
    gates = RANK_GATES[prof.kind]
    for i, (name, cap) in enumerate(zip(RANK_NAMES, CAPS)):
        L.append("")
        L.append("[[rank]]")
        L.append(f"name = {q(name)}")
        L.append(f"max = {cap}")
        L.append(f"skill = {gates[i][0]}")
        L.append(f"level = {gates[i][1]}")
        how = "trainer"
        if prof.kind == "secondary" and i == 2:
            how = "book"
            L.append(f"item = {CURATED[prof.key]['book'][0]}")
        elif prof.kind == "secondary" and i == 3:
            how = "quest"
        L.append(f"how = {q(how)}")
        L.append(f"status = {q(GATES_STATUS[i])}")
        L.append(f"sources = {toml_value(['polestar:' + ps.commit[:12] + '/' + TRAINERS_RS.as_posix()])}")
    # instructores
    for e in trainers:
        L.append("")
        L.append("[[trainer]]")
        for k in ("prof", "npc", "name", "faction", "ranks", "at", "text", "book", "quest"):
            if k in e:
                L.append(f"{k} = {toml_value(e[k])}")
        L.append('status = "verified"' if "at" in e else 'status = "unverified"')
        L.append(f"sources = {toml_value(['polestar:' + ps.commit[:12] + '/' + TRAINERS_RS.as_posix(), 'foreverdb:npc/' + str(e['npc'])])}")
    # pasos de rango
    for i in range(1, 4):
        cap_prev = CAPS[i - 1]
        if segs and segs[-1].to <= cap_prev:
            break
        L.append("")
        L.append("[[route]]")
        L.append(f"prof = {q(prof.key)}")
        L.append(f"from = {gates[i][0]}")
        L.append(f"to = {cap_prev}")
        L.append(f"train = {q(RANK_NAMES[i])}")
        L.append(f"level = {gates[i][1]}")
        how = ({2: "book", 3: "quest"}.get(i) if prof.kind == "secondary" else None) or "trainer"
        gate = f"habilidad {gates[i][0]}" + (f", nivel {gates[i][1]}" if gates[i][1] > 1 else "")
        book = CURATED.get(prof.key, {}).get("book")
        book_name = (t.item_es.get(book[0]) or t.items.get(book[0], {}).get("name", "")) if book else ""
        txt = {"trainer": f"Entrena {RANK_NAMES[i]} ({gate}) antes de llegar a {cap_prev}: los puntos por encima del tope se pierden.",
               "book": f"{RANK_NAMES[i]} es un libro, «{book_name}» ({gate}): cómpralo y léelo antes de llegar a {cap_prev}.",
               "quest": f"{RANK_NAMES[i]} es una misión ({gate}): hazla en cuanto llegues a {cap_prev}, que es el tope."}[how]
        L.append(f"note = {q(txt)}")
        L.append(f"status = {q(GATES_STATUS[i])}")
        L.append(f"sources = {toml_value(['polestar:' + ps.commit[:12] + '/' + TRAINERS_RS.as_posix()])}")
    # tramos
    for sg in segs:
        r = sg.action.recipe
        L.append("")
        L.append("[[route]]")
        L.append(f"prof = {q(prof.key)}")
        L.append(f"from = {sg.frm}")
        L.append(f"to = {sg.to}")
        if r.item:
            L.append(f"craft = {r.item}")
        else:
            L.append(f"craft_spell = {r.spell}")
        L.append(f"spell = {r.spell}")
        L.append(f"name = {q(r.name_es)}")
        L.append(f"n = {max(1, math.ceil(sg.crafts - 1e-9))}")
        mats = []
        for it, n in r.reagents:
            b = val.by_item.get(it)
            if b and val.made_here(it) and len(b.reagents) == 1 and b.count == 1:
                mats.append([it, n, b.reagents[0][0], b.reagents[0][1]])
            else:
                mats.append([it, n])
        L.append(f"mats = {toml_value(mats)}")
        L.append(f"colors = {toml_value([r.learn, r.yellow, r.green, r.grey])}")
        L.append(f"learn = {q(learn_text(r, t))}")
        L.append(f"learn_skill = {r.learn}")
        if r.recipe_item:
            L.append(f"recipe_item = {r.recipe_item}")
        notes = []
        for b, per in sg.action.inter:
            k = sg.inter_crafts.get(b.spell, 0)
            notes.append(f"Fabrica antes unas {math.ceil(k)} x {b.name_es}: también suben puntos mientras no son grises.")
        for tr in sg.action.tool_recipes:
            notes.append(f"Necesitas la herramienta {t.item_es.get(tr.item) or tr.name_es}: fabrícala una vez ({tr.name_es}).")
        if r.learn_from in ("classic", "estimate"):
            notes.append("Comprueba en el instructor la habilidad a la que la enseña (estimada).")
        if notes:
            L.append(f"note = {q(' '.join(notes))}")
        L.append(f"status = {q(r.status)}")
        L.append(f"sources = {toml_value(seg_sources(r, ps))}")
    return "\n".join(L) + "\n"


def render_materials(mats: dict[int, dict], ps: Polestar) -> str:
    L = ["# GENERADO por tools/gen_professions.py: no editar a mano.",
         "# [[rank]]: rangos de las profesiones de fabricación (los de cada profesión van en su archivo).",
         "# [[material]]: lo que piden las rutas generadas: id, name (esES del cliente), vendor = precio en cobre",
         "#   (por unidad) si lo vende un proveedor de la Alianza, where = de dónde sale, made_from = [id, cantidad].",
         'id = "general-professions-materials"', 'class = "ANY"', 'kind = "professions"',
         'title = "Rangos y materiales de las profesiones"', "order = 220", 'status = "verified"',
         f"sources = {toml_value(['wago:' + BUILD, 'polestar:' + ps.commit])}",
         'order_profs = ["tailoring", "enchanting"]',
         "sellable = [2589, 2592, 4306, 4338, 14047, 10940, 10938, 10939, 11176]"]
    gates = RANK_GATES["primary"]
    for i, (name, cap) in enumerate(zip(RANK_NAMES, CAPS)):
        L += ["", "[[rank]]", f"name = {q(name)}", f"max = {cap}", f"skill = {gates[i][0]}", f"level = {gates[i][1]}"]
    for iid in sorted(mats):
        m = mats[iid]
        L += ["", "[[material]]", f"id = {iid}", f"name = {q(m['name'])}"]
        if m.get("vendor"):
            L.append(f"vendor = {m['vendor']}")
        L.append(f"where = {q(m['where'])}")
        if m.get("made_from"):
            L.append(f"made_from = {toml_value(m['made_from'])}")
        L.append(f"profs = {toml_value(sorted(m['profs']))}")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------------------------- comparar
def polestar_route(text: str) -> list[tuple[int, int, int]]:
    """Tramos de una guía de Polestar: (desde, hasta, hechizo), solo el primer camino ascendente."""
    out, skill = [], 1
    for m in re.finditer(r"^  craft (\d+) until (\d+)", text, re.M):
        sp, to = int(m.group(1)), int(m.group(2))
        if to <= skill:
            continue
        out.append((skill, to, sp))
        skill = to
    return out


def evaluate(route: list[tuple[int, int, int]], acts_all: dict[int, Action]) -> tuple[float, float, int]:
    """Coste de una ruta ajena con nuestro modelo: (fabricaciones, esfuerzo, puntos sin cubrir de 1 a 300)."""
    crafts = effort = 0.0
    covered: set[int] = set()
    for frm, to, sp in route:
        a = acts_all.get(sp)
        if not a:
            continue
        first = True
        for s in range(frm, to):
            if s in covered:
                continue
            g = gain(a, s)
            if g <= 0:
                continue
            if first:
                effort += SWITCH_COST + a.once
                first = False
            crafts += 1.0 / g
            effort += a.raw / g
            covered.add(s)
    return crafts, effort, 299 - len(covered)


def old_route(path: Path, recipes: list[Recipe]) -> list[tuple[int, int, int]]:
    if not path.exists():
        return []
    d = tomllib.loads(path.read_text(encoding="utf-8"))
    by_item = {r.item: r.spell for r in recipes if r.item}
    out = []
    for s in d.get("route", []):
        if s.get("train"):
            continue
        sp = s.get("craft_spell") or by_item.get(s.get("craft"))
        if sp:
            out.append((int(s["from"]), int(s["to"]), int(sp)))
    out.sort()
    return out


# --------------------------------------------------------------------------------------------- principal
def build_all(wago: Path, polestar: Path, fdb_path: str | None, compare_old: Path | None = None) -> tuple[dict[Path, str], list[str], list[dict]]:
    t = load_tables(wago)
    ps = load_polestar(polestar)
    fdb = load_foreverdb(fdb_path)
    goods = vendor_goods(t, ps, fdb)
    mining = None
    outputs: dict[Path, str] = {}
    warnings: list[str] = []
    table: list[dict] = []
    all_mats: dict[int, dict] = {}
    for prof in PROFS:
        recipes = extract_recipes(t, ps, fdb, prof)
        if mining is None:
            mining = extract_recipes(t, ps, fdb, Prof("mining", MINING, "gathering", "Minería", "mining",
                                                     frozenset(), 0, ""))
        val = Valuer(t, ps, fdb, prof, {r.item: r for r in recipes if r.item and r.usable},
                     {r.item: r for r in mining if r.item}, goods)
        acts = make_actions(recipes, val)
        path = smooth(solve(acts))
        segs = segments(path)
        crafts, effort, reach = route_cost(path)
        summary = {"crafts": crafts, "effort": effort, "reach": reach}
        trainers, warn = trainer_entries(prof, fdb, t)
        trainers += book_quest(prof, fdb, t)
        warnings += warn
        outputs[OUT_DIR / f"professions-{prof.key}.toml"] = render_prof(prof, segs, recipes, val, trainers, ps, fdb, summary)
        for sg in segs:
            for it, n in sg.action.recipe.reagents:
                m = all_mats.setdefault(it, {"name": t.item_es.get(it) or t.items.get(it, {}).get("name", f"#{it}"),
                                             "where": val.where(it), "profs": set()})
                m["profs"].add(prof.key)
                if val.is_vendor(it):
                    m["vendor"] = round(val.vendor_price(it))
                b = val.by_item.get(it)
                if b and val.made_here(it) and len(b.reagents) == 1:
                    m["made_from"] = [b.reagents[0][0], b.reagents[0][1]]
        # comparación
        acts_all = {a.recipe.spell: a for a in make_actions(
            [r if r.usable else _force(r) for r in recipes], val)}
        pr = polestar_route(ps.guides.get(prof.stem, ""))
        pc = evaluate(pr, acts_all)
        oc = evaluate(old_route(compare_old / f"professions-{prof.key}.toml", recipes), acts_all) if compare_old else None
        mat_tot: dict[int, float] = {}
        for sg in segs:
            for it, n in sg.action.recipe.reagents:
                val.raw(it, n * sg.crafts, mat_tot)
        table.append({"prof": prof.label, "ours": (crafts, effort, reach), "polestar": pc, "old": oc,
                      "segs": len(segs), "mats": mat_tot, "names": {i: t.item_es.get(i, str(i)) for i in mat_tot},
                      "pol_route": pr, "our_route": [(s.frm, s.to, s.action.recipe.spell, s.action.recipe.name_es) for s in segs],
                      "spell_es": t.spell_es, "why_not": {r.spell: (r.why_not or ("" if r.learn_from not in ("classic", "estimate") else "aprendizaje estimado")) for r in recipes}})
    outputs[OUT_DIR / "professions-materials.toml"] = render_materials(all_mats, ps)
    return outputs, warnings, table


def _force(r: Recipe) -> Recipe:
    from dataclasses import replace
    return replace(r, usable=True)


def main(argv: list[str] | None = None) -> int:
    setup_stdio()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--polestar", default=os.environ.get("SENDA_POLESTAR"), help="clon de Polestar (o SENDA_POLESTAR)")
    ap.add_argument("--wago", help="carpeta de los CSV (por defecto .cache/wago; ver tools/fetch_wago.py)")
    ap.add_argument("--foreverdb", help="forever-db (por defecto .cache/foreverdb o SENDA_FOREVERDB)")
    ap.add_argument("--check", action="store_true", help="no escribe; sale con 1 si algo cambiaría")
    ap.add_argument("--compare", action="store_true", help="imprime la comparación con Polestar y la ruta anterior")
    ap.add_argument("--old", help="carpeta con las rutas anteriores (para --compare)")
    a = ap.parse_args(argv)
    wago = wago_dir(a.wago, must_exist=True)
    fdb = a.foreverdb or default_foreverdb()
    missing = []
    if not (wago / "SkillLineAbility.csv").exists():
        missing.append(f"tablas del cliente en {wago} (python tools/fetch_wago.py)")
    else:
        from fetch_wago import missing as wago_missing
        if wago_missing(wago):
            missing.append(f"faltan tablas en {wago}: {', '.join(wago_missing(wago))} (python tools/fetch_wago.py)")
    if not a.polestar or not (Path(a.polestar) / EXTRACT_REL).exists():
        missing.append("clon de Polestar (--polestar o SENDA_POLESTAR)")
    if not fdb:
        missing.append("forever-db (python tools/fetch_foreverdb.py o SENDA_FOREVERDB)")
    if missing:
        msg = "gen_professions: sin fuentes, no se comprueba nada: " + "; ".join(missing)
        print(msg, file=sys.stderr)
        return 0 if a.check else 1
    outputs, warnings, table = build_all(wago, Path(a.polestar), fdb, Path(a.old) if a.old else None)
    for w in warnings:
        print("aviso:", w, file=sys.stderr)
    if a.compare:
        print_compare(table)
        return 0
    changed = []
    for path, text in sorted(outputs.items()):
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            changed.append(path)
            if not a.check:
                write_text_lf(path, text)
    rel = lambda p: p.relative_to(ROOT).as_posix()  # noqa: E731
    if a.check:
        if changed:
            print("gen_professions --check: cambiaría " + ", ".join(rel(p) for p in changed), file=sys.stderr)
            return 1
        print("gen_professions --check: al día.")
        return 0
    for row in table:
        c, e, r = row["ours"]
        print(f"  {row['prof']:<18} {c:6.0f} fabricaciones, hasta {r}, {row['segs']} tramos")
    for p in changed:
        print(f"  escrito {rel(p)}")
    return 0


def print_compare(table: list[dict]) -> None:
    def f(x, ours=False):
        if not x or not x[0]:
            return "-"
        tail = f"hasta {x[2]}" if ours else (f"{x[2]} puntos sin cubrir" if x[2] else "cubre 1-300")
        return f"{x[0]:.0f} ({x[1] / 10000:.1f} o eq., {tail})"
    print("| Profesión | Senda (nueva) | Polestar | Senda anterior |")
    print("|---|---|---|---|")
    for row in table:
        print(f"| {row['prof']} | {f(row['ours'], True)} | {f(row['polestar'])} | {f(row['old'])} |")
    for row in table:
        print(f"\n### {row['prof']}")
        print("Nuestra ruta: " + "; ".join(f"{a}-{b} {n}" for a, b, _, n in row["our_route"]))
        print("Polestar: " + "; ".join(f"{a}-{b} {row['spell_es'].get(s, s)}" + (f" [{row['why_not'].get(s)}]" if row["why_not"].get(s) else "") for a, b, s in row["pol_route"]))
        top = sorted(row["mats"].items(), key=lambda kv: -kv[1])[:8]
        print("Material: " + ", ".join(f"{round(n)} {row['names'][i]}" for i, n in top))


if __name__ == "__main__":
    sys.exit(main())

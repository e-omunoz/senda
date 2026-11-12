#!/usr/bin/env python3
"""Auditoría de datos de las guías contra forever-db (con sus correcciones y las de Senda).

Que la guía nunca mande al jugador a una misión que no está. Recorre cada guía en el orden en que la juega
cada personaje (secciones compartidas incluidas, con los filtros `if` de sección y de paso aplicados) y
comprueba cada paso:

- el PNJ (`npc`) y la misión existen en forever-db, y la misión no se ha quitado en Forever (`remove`);
- en `accept` el PNJ es quien la da (quest_start) y en `turnin` quien la recibe (quest_end);
- `at` está a ≤ 1,0 de mapa de una aparición del PNJ en ese uiMap (marcos de ui_map, correcciones de
  posición incluidas);
- raza y clase: la misión se la pueden dar a ese personaje (máscaras de forever-db), y en una sección
  compartida un paso de misión solo para ciertas razas o clases lleva su filtro `if`;
- requisitos (quest_prereq, modos all/any, migas de pan): la previa se entrega antes en la misma guía, o el
  paso es opcional; una miga de pan no se coge después de la misión a la que lleva;
- nivel: el nivel mínimo de la misión frente al nivel estimado en ese punto de la ruta y el `reqlevel` del paso;
- misiones cogidas o entregadas dos veces, entregas antes de coger o de completar, misiones de clase tarde.

Niveles: «error» (la guía manda a algo que no está o no se puede hacer: falla `python -m unittest`) y
«aviso» (dudas: revisar). Las dudas ya revisadas van en REVIEWED con su motivo y se muestran como «revisado».

    python tools/audit_guides.py                       # las tres guías: gnome-warlock, human-mage, nightelf-druid
    python tools/audit_guides.py --guide ps-alliance-gnome
    python tools/audit_guides.py --json                # para agentes
    python tools/audit_guides.py --warnings            # también los avisos, uno por línea

Sale con 1 si hay errores. Ver docs/AUDIT.md.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from common import REPO_ROOT, load_toml, setup_stdio  # noqa: E402

DEFAULT_GUIDES = ("gnome-warlock", "human-mage", "nightelf-druid")

RACE_BITS = {"Human": 1, "Orc": 2, "Dwarf": 4, "NightElf": 8, "Scourge": 16, "Tauren": 32, "Gnome": 64,
             "Troll": 128, "Skyborne": 1 << 32}
CLASS_BITS = {"WARRIOR": 1, "PALADIN": 2, "HUNTER": 4, "ROGUE": 8, "PRIEST": 16, "SHAMAN": 64, "MAGE": 128,
              "WARLOCK": 256, "DRUID": 1024}
FACTION_RACES = {"Alliance": ("Human", "Dwarf", "NightElf", "Gnome", "Skyborne"),
                 "Horde": ("Orc", "Scourge", "Tauren", "Troll")}
ALL_CLASSES = sum(CLASS_BITS.values())

MAX_AT_DISTANCE = 1.0      # % de mapa entre `at` y la aparición más cercana del PNJ
CLASS_LATE_LEVELS = 10     # una misión de clase cogida más de N niveles después de su mínimo: aviso

# Dudas revisadas a mano: (código, id de paso) -> motivo. Se muestran como «revisado», no como aviso.
REVIEWED: dict[tuple[str, str], str] = {
    ("class-late", "mg-20-library-003"): "pide antes un libro de biblioteca; la ruta pasa por la Torre de Azora al 20 (docs/AUDIT.md)",
    ("class-late", "mg-40-needles-005"): "la cadena de Tabetha (1947) empieza en Marjal Revolcafango, adonde la ruta llega al 38",
    ("class-late", "mg-42-wand-005"): "la cadena de Tabetha (1947) empieza en Marjal Revolcafango, adonde la ruta llega al 38",
    ("class-late", "mg-45-celestial-005"): "sigue a «Power in Uldaman» (1956) y «Mana Surges» (1957), que la ruta hace tras Uldaman (44-46)",
    ("npc-no-spawn", "dr-11-lunaclaw-001"): "forever-db no sitúa al Espíritu de Lunaclaw (aparece al vencer a Lunaclaw); `at` de QuestieDB (Forever)",
    ("reqlevel-differs", "a38-valle-de-huesos-001"): "QuestieDB (Forever) dice 30; la sección es del 38-40: se llega con nivel de sobra",
    ("reqlevel-differs", "a38-valle-de-huesos-003"): "QuestieDB (Forever) dice 30; la sección es del 38-40: se llega con nivel de sobra",
    ("reqlevel-differs", "a38-valle-de-huesos-004"): "QuestieDB (Forever) dice 30; la sección es del 38-40: se llega con nivel de sobra",
    ("reqlevel-differs", "a38-valle-de-huesos-005"): "QuestieDB (Forever) dice 30; la sección es del 38-40: se llega con nivel de sobra",
    ("no-ender-data", "a50-ungoro-046"): "Ringo (9999): forever-db no publica quién la recibe; Senda lleva el PNJ de QuestieDB (Forever)",
    ("no-giver-data", "a50-ungoro-047"): "la escolta de Ringo (9999): forever-db no publica quién la da; Senda lleva el PNJ de QuestieDB (Forever)",
}


# --------------------------------------------------------------------------------------------
# Modelo
# --------------------------------------------------------------------------------------------

@dataclass
class Character:
    guide: str
    race: str
    cls: str
    faction: str

    @property
    def label(self) -> str:
        return self.guide


@dataclass
class FlatStep:
    idx: int
    raw: dict
    section: str        # clave de sección: "shared:a12-loch-modan" o "<guía>/<stem>"
    path: str           # archivo, relativo al repo
    shared: bool
    sec_if: dict
    sec_levels: tuple[int, int]
    level: int          # nivel estimado del personaje en este punto

    @property
    def id(self) -> str:
        return str(self.raw.get("id"))

    @property
    def do(self) -> str:
        return str(self.raw.get("do"))

    @property
    def optional(self) -> bool:
        return bool(self.raw.get("optional"))

    def quests(self) -> list[int]:
        out = []
        if isinstance(self.raw.get("quest"), int):
            out.append(self.raw["quest"])
        out += [q for q in (self.raw.get("quests") or []) if isinstance(q, int)]
        return out


@dataclass
class Issue:
    level: str          # "error" | "warning" | "reviewed"
    code: str
    step: str
    path: str
    msg: str
    guides: set[str] = field(default_factory=set)

    def key(self):
        return (self.level, self.code, self.step, self.msg)

    def as_dict(self) -> dict:
        return {"level": self.level, "code": self.code, "step": self.step, "file": self.path, "msg": self.msg,
                "guides": sorted(self.guides)}

    def __str__(self) -> str:
        tag = {"error": "ERROR", "warning": "AVISO", "reviewed": "REVISADO"}[self.level]
        who = ",".join(sorted(self.guides))
        return f"{tag} {self.code} {self.path} [{self.step}] ({who}): {self.msg}"


class Report:
    def __init__(self):
        self._by_key: dict[tuple, Issue] = {}

    def add(self, level: str, code: str, st: FlatStep | None, msg: str, guide: str | None = None,
            step_id: str | None = None, path: str | None = None) -> None:
        sid = step_id or (st.id if st else "")
        if level != "error" and (code, sid) in REVIEWED:
            level, msg = "reviewed", f"{msg} — {REVIEWED[(code, sid)]}"
        iss = Issue(level, code, sid, path or (st.path if st else ""), msg)
        cur = self._by_key.setdefault(iss.key(), iss)
        if guide:
            cur.guides.add(guide)

    @property
    def issues(self) -> list[Issue]:
        order = {"error": 0, "warning": 1, "reviewed": 2}
        return sorted(self._by_key.values(), key=lambda i: (order[i.level], i.path, i.step, i.code, i.msg))

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warning"]


# --------------------------------------------------------------------------------------------
# Guías aplanadas por personaje
# --------------------------------------------------------------------------------------------

def _allowed(cond: dict | None, ch: Character) -> bool:
    """Filtros `if` de sección o de paso para este personaje. Los de nivel no quitan el paso (el motor lo
    muestra cuando toca); los de profesión sí (fuera de la ruta base, como tools/route_score.py)."""
    if not cond:
        return True
    if "class" in cond and ch.cls not in cond["class"]:
        return False
    if "race" in cond and ch.race not in cond["race"]:
        return False
    if "faction" in cond and cond["faction"] != ch.faction:
        return False
    if "prof" in cond:
        return False
    return True


def load_guide(root: Path, guide_id: str) -> tuple[dict, list[tuple[str, Path, dict]]]:
    gdir = root / "data" / "guides" / guide_id
    meta = load_toml(gdir / "guide.toml")
    secs = []
    for name in meta.get("sections", []):
        path = (root / "data" / "shared" / f"{name[7:]}.toml") if name.startswith("shared:") else gdir / f"{name}.toml"
        secs.append((name if name.startswith("shared:") else f"{guide_id}/{name}", path, load_toml(path)))
    return meta, secs


def characters(meta: dict) -> list[Character]:
    races = meta.get("races") or list(FACTION_RACES.get(meta.get("faction", "Alliance"), ()))
    classes = meta.get("classes") or list(CLASS_BITS)
    return [Character(meta["id"], r, c, meta.get("faction", "Alliance")) for r in races for c in classes]


def flatten(root: Path, secs: list[tuple[str, Path, dict]], ch: Character) -> list[FlatStep]:
    """Pasos en el orden de juego del personaje, con el nivel estimado (como tools/routescore/route.py:
    interpolado en el rango de la sección, sin bajar de un `do = "level"` anterior)."""
    out: list[FlatStep] = []
    floor = 1
    prev_hi = 1
    for key, path, sec in secs:
        lv = sec.get("levels") or [prev_hi, prev_hi]
        lo, hi = int(lv[0]), int(lv[1])
        prev_hi = hi
        if not _allowed(sec.get("if"), ch):
            continue
        raw = sec.get("step", [])
        n = max(len(raw) - 1, 1)
        rel = path.resolve().relative_to(root.resolve()).as_posix() if path.resolve().is_relative_to(root.resolve()) else str(path)
        for i, r in enumerate(raw):
            level = max(floor, int(round(lo + (hi - lo) * i / n)))
            if not _allowed(r.get("if"), ch):
                continue
            out.append(FlatStep(len(out), r, key, rel, key.startswith("shared:"), sec.get("if") or {}, (lo, hi), level))
            if r.get("do") == "level" and r.get("level"):
                floor = max(floor, int(r["level"]))
    return out


# --------------------------------------------------------------------------------------------
# Consultas a la base
# --------------------------------------------------------------------------------------------

def race_ok(mask: int, race: str) -> bool:
    return not mask or bool(mask & RACE_BITS[race])


def class_ok(mask: int, cls: str) -> bool:
    return not mask or bool(mask & CLASS_BITS[cls])


def available(q: dict | None, ch: Character) -> bool:
    if not q:
        return False
    return race_ok(int(q.get("races") or 0), ch.race) and class_ok(int(q.get("classes") or 0), ch.cls)


def _name(db, kind: str, eid: int) -> str:
    ent = db.npc(eid) if kind == "npc" else (db.object(eid) if kind == "object" else db.quest(eid))
    nm = ent and (ent.get("name"))
    return f"{nm} ({eid})" if nm else str(eid)


def nearest_spawn(db, npc_id: int, uimap: int, x: float, y: float):
    """(distancia, [uiMap, x, y]) a la aparición más cercana del PNJ en ese uiMap (también las alternativas
    de marcos solapados), o None si no tiene ninguna en ese mapa."""
    ent = db.npc(npc_id)
    if not ent:
        return None
    best = None
    for p in list(ent.get("spawns") or []) + list(ent.get("altSpawns") or []):
        if not p or p[0] != uimap or p[1] is None:
            continue
        d = math.hypot(float(p[1]) - x, float(p[2]) - y)
        if best is None or d < best[0]:
            best = (round(d, 2), [p[0], p[1], p[2]])
    return best


def spawn_maps(db, npc_id: int) -> list[int]:
    ent = db.npc(npc_id) or {}
    return sorted({p[0] for p in list(ent.get("spawns") or []) + list(ent.get("altSpawns") or []) if p})


def prereqs(q: dict) -> tuple[list[int], list[int]]:
    """(todas, alguna) de las previas duras de una misión (sin migas de pan)."""
    return list(q.get("preQuestGroup") or []), list(q.get("preQuestSingle") or [])


# --------------------------------------------------------------------------------------------
# Comprobaciones
# --------------------------------------------------------------------------------------------

def check_entities(db, steps: list[FlatStep], ch: Character, rep: Report) -> None:
    """PNJ y misiones que existen; quién da y recibe; `at` junto al PNJ."""
    for st in steps:
        npc = st.raw.get("npc")
        if isinstance(npc, int) and not db.npc(npc):
            rep.add("error", "npc-missing", st, f"el PNJ {npc} no está en forever-db", ch.guide)
            npc = None
        for qid in st.quests():
            q = db.quest(qid)
            if not q:
                rep.add("error", "quest-missing", st,
                        f"la misión {qid} no está en forever-db (o sus correcciones la quitan: no existe en Forever)",
                        ch.guide)
                continue
            if st.do in ("accept", "turnin") and isinstance(npc, int):
                side = "starters" if st.do == "accept" else "finishers"
                who = q.get(side) or {}
                npcs = list(who.get("npc") or [])
                others = list(who.get("object") or []) + list(who.get("item") or [])
                if npc not in npcs:
                    if not npcs and not others:
                        rep.add("warning", "no-giver-data" if st.do == "accept" else "no-ender-data", st,
                                f"forever-db no dice quién {'da' if st.do == 'accept' else 'recibe'} "
                                f"{_name(db, 'quest', qid)}", ch.guide)
                    else:
                        names = ", ".join([_name(db, "npc", n) for n in npcs]
                                          + [f"objeto {o}" for o in who.get("object") or []]
                                          + [f"objeto de inventario {i}" for i in who.get("item") or []])
                        verb = "la da" if st.do == "accept" else "la recibe"
                        rep.add("error", "wrong-giver" if st.do == "accept" else "wrong-ender", st,
                                f"{_name(db, 'npc', npc)} no es quien {verb.split()[1]} "
                                f"{_name(db, 'quest', qid)}: {verb} {names}", ch.guide)
        at = st.raw.get("at")
        if npc is None and "npc" not in st.raw and st.do in ("accept", "turnin") and len(st.quests()) == 1 \
                and isinstance(at, list) and len(at) >= 3:
            _check_unnamed(db, st, ch, rep, int(at[0]), float(at[1]), float(at[2]))
        if isinstance(npc, int) and isinstance(at, list) and len(at) >= 3:
            ui, x, y = int(at[0]), float(at[1]), float(at[2])
            near = nearest_spawn(db, npc, ui, x, y)
            if near is None:
                maps = spawn_maps(db, npc)
                if maps:
                    rep.add("error", "at-other-map", st,
                            f"{_name(db, 'npc', npc)} no aparece en el uiMap {ui} del paso (aparece en {maps})",
                            ch.guide)
                else:
                    rep.add("warning", "npc-no-spawn", st,
                            f"forever-db no tiene apariciones de {_name(db, 'npc', npc)}", ch.guide)
            elif near[0] > MAX_AT_DISTANCE:
                p = near[1]
                rep.add("error", "at-far", st,
                        f"`at` {ui}, {x}, {y} está a {near[0]} de {_name(db, 'npc', npc)} "
                        f"(aparece en {p[1]}, {p[2]})", ch.guide)


def _check_unnamed(db, st: FlatStep, ch: Character, rep: Report, ui: int, x: float, y: float) -> None:
    """Paso `accept`/`turnin` sin `npc`: `at` debería estar junto a quien da o recibe la misión (PNJ u objeto).
    Es un aviso: el paso puede apuntar a la entrada de un edificio o a otro sitio a propósito."""
    q = db.quest(st.quests()[0])
    if not q:
        return
    who = q.get("starters" if st.do == "accept" else "finishers") or {}
    best = None
    for kind in ("npc", "object"):
        for eid in who.get(kind) or []:
            ent = db.npc(eid) if kind == "npc" else db.object(eid)
            for p in list((ent or {}).get("spawns") or []) + list((ent or {}).get("altSpawns") or []):
                if p and p[0] == ui and p[1] is not None:
                    d = math.hypot(float(p[1]) - x, float(p[2]) - y)
                    if best is None or d < best[0]:
                        best = (round(d, 2), kind, eid, p)
    if best is None:
        if who.get("npc") or who.get("object"):
            names = ", ".join([_name(db, "npc", n) for n in who.get("npc") or []]
                              + [f"objeto {_name(db, 'object', o)}" for o in who.get("object") or []])
            rep.add("warning", "at-unnamed-map", st,
                    f"paso sin `npc`: {names} no aparece en el uiMap {ui} del paso", ch.guide)
        return
    if best[0] > MAX_AT_DISTANCE:
        rep.add("warning", "at-unnamed-far", st,
                f"paso sin `npc`: `at` {ui}, {x}, {y} está a {best[0]} de "
                f"{'objeto ' if best[1] == 'object' else ''}{_name(db, best[1], best[2])} "
                f"(aparece en {best[3][1]}, {best[3][2]})", ch.guide)


def check_filters(db, secs: list[tuple[str, Path, dict]], root: Path, faction: str, rep: Report) -> None:
    """En una sección compartida, un paso de misión solo para ciertas razas o clases lleva su filtro `if`
    (si no, otra raza o clase de la facción verá un paso que no puede hacer)."""
    races_all = 0
    for r in FACTION_RACES[faction]:
        races_all |= RACE_BITS[r]
    for key, path, sec in secs:
        if not key.startswith("shared:"):
            continue
        rel = path.resolve().relative_to(root.resolve()).as_posix()
        sif = sec.get("if") or {}
        for r in sec.get("step", []):
            if r.get("do") not in ("accept", "turnin", "complete"):
                continue
            cond = {**sif, **(r.get("if") or {})}
            for qid in ([r["quest"]] if isinstance(r.get("quest"), int) else []):
                q = db.quest(qid)
                if not q:
                    continue
                rm = int(q.get("races") or 0) & races_all
                if rm and rm != races_all:
                    ok_races = [x for x in FACTION_RACES[faction] if rm & RACE_BITS[x]]
                    have = cond.get("race")
                    if not have or not set(have) <= set(ok_races):
                        rep.add("error", "needs-race-filter", None,
                                f"{_name(db, 'quest', qid)} es solo para {', '.join(ok_races)}: el paso necesita "
                                f"`if = {{ race = {json.dumps(ok_races)} }}`", step_id=r.get("id"), path=rel)
                cm = int(q.get("classes") or 0) & ALL_CLASSES
                if cm and cm != ALL_CLASSES:
                    ok_cls = [c for c, b in CLASS_BITS.items() if cm & b]
                    have = cond.get("class")
                    if not have or not set(have) <= set(ok_cls):
                        rep.add("error", "needs-class-filter", None,
                                f"{_name(db, 'quest', qid)} es solo para {', '.join(ok_cls)}: el paso necesita "
                                f"`if = {{ class = {json.dumps(ok_cls)} }}`", step_id=r.get("id"), path=rel)


def check_route(db, steps: list[FlatStep], ch: Character, rep: Report) -> None:
    """Máscaras, requisitos, orden de coger/completar/entregar, duplicados, niveles."""
    accepts: dict[int, list[FlatStep]] = {}
    turnins: dict[int, list[FlatStep]] = {}
    completes: dict[int, list[FlatStep]] = {}
    for st in steps:
        for qid in st.quests():
            if st.do == "accept":
                accepts.setdefault(qid, []).append(st)
            elif st.do == "turnin":
                turnins.setdefault(qid, []).append(st)
            elif st.do in ("complete", "dungeon"):
                completes.setdefault(qid, []).append(st)

    def first(d, qid):
        return d.get(qid, [None])[0]

    for qid, sts in accepts.items():
        q = db.quest(qid)
        st = sts[0]
        if len(sts) > 1:
            rep.add("error", "dup-accept", sts[1],
                    f"{_name(db, 'quest', qid)} se coge otra vez (ya en {st.id})", ch.guide)
        if not q:
            continue
        # raza y clase
        if not race_ok(int(q.get("races") or 0), ch.race):
            rep.add("error", "race", st, f"{_name(db, 'quest', qid)} no se ofrece a {ch.race}", ch.guide)
        if not class_ok(int(q.get("classes") or 0), ch.cls):
            rep.add("error", "class", st, f"{_name(db, 'quest', qid)} no se ofrece a {ch.cls}", ch.guide)
        # requisitos
        need_all, need_any = prereqs(q)
        for p in need_all:
            pq = db.quest(p)
            if not available(pq, ch):
                continue  # de otra raza, clase o facción (forever-db junta las variantes)
            _check_pre(db, rep, ch, st, qid, [p], turnins, steps)
        alts = [p for p in need_any if available(db.quest(p), ch)]
        if alts:
            _check_pre(db, rep, ch, st, qid, alts, turnins, steps)
        # migas de pan: no se pueden coger después de la misión a la que llevan
        target = q.get("breadcrumbFor")
        if target and first(accepts, target) and first(accepts, target).idx < st.idx:
            rep.add("error", "crumb-late", st,
                    f"{_name(db, 'quest', qid)} es una miga de pan de {_name(db, 'quest', target)}, que ya se cogió "
                    f"en {first(accepts, target).id}: el PNJ ya no la ofrece", ch.guide)
        for ex in q.get("exclusiveTo") or []:
            if ex in accepts:
                rep.add("error", "exclusive", st,
                        f"{_name(db, 'quest', qid)} y {_name(db, 'quest', ex)} se excluyen: la guía coge las dos",
                        ch.guide)
        # nivel
        min_lv = int(q.get("requiredLevel") or 0)
        req = st.raw.get("reqlevel")
        if min_lv > st.level and (not isinstance(req, int) or req < min_lv):
            rep.add("error", "level", st,
                    f"{_name(db, 'quest', qid)} pide nivel {min_lv}; la ruta llega aquí a nivel ~{st.level} y el paso "
                    f"no lleva `reqlevel = {min_lv}` para esperarlo", ch.guide)
        elif isinstance(req, int) and req < min_lv:
            rep.add("warning", "reqlevel-differs", st,
                    f"`reqlevel = {req}` pero forever-db pide nivel {min_lv} para {_name(db, 'quest', qid)}", ch.guide)
        if min_lv > st.sec_levels[1] + 1:
            rep.add("warning", "level-section", st,
                    f"{_name(db, 'quest', qid)} pide nivel {min_lv} y la sección es del {st.sec_levels[0]}-"
                    f"{st.sec_levels[1]}", ch.guide)
        if int(q.get("classes") or 0) and class_ok(int(q.get("classes") or 0), ch.cls) \
                and min_lv and st.level > min_lv + CLASS_LATE_LEVELS:
            rep.add("warning", "class-late", st,
                    f"misión de clase {_name(db, 'quest', qid)} (nivel {min_lv}) cogida a ~{st.level}", ch.guide)

    for qid, sts in turnins.items():
        st = sts[0]
        if len(sts) > 1:
            rep.add("error", "dup-turnin", sts[1],
                    f"{_name(db, 'quest', qid)} se entrega otra vez (ya en {st.id})", ch.guide)
        acc = first(accepts, qid)
        inside = [c for c in completes.get(qid, []) if c.do == "dungeon" and c.idx < st.idx]
        if acc is None and not inside:
            q = db.quest(qid) or {}
            if not (q.get("starters") or {}).get("item"):
                rep.add("error", "turnin-no-accept", st,
                        f"se entrega {_name(db, 'quest', qid)} pero la guía no la coge", ch.guide)
        elif acc is not None and acc.idx > st.idx:
            rep.add("error", "turnin-before-accept", st,
                    f"se entrega {_name(db, 'quest', qid)} antes de cogerla ({acc.id})", ch.guide)
        for c in completes.get(qid, []):
            if c.idx > st.idx:
                rep.add("error", "complete-after-turnin", c,
                        f"se completa {_name(db, 'quest', qid)} después de entregarla ({st.id})", ch.guide)

    for qid, sts in completes.items():
        acc = first(accepts, qid)
        if acc is not None and acc.idx > sts[0].idx and sts[0].do == "complete":
            rep.add("error", "complete-before-accept", sts[0],
                    f"se completa {_name(db, 'quest', qid)} antes de cogerla ({acc.id})", ch.guide)

    for qid, sts in accepts.items():
        dungeon = any(c.do == "dungeon" for c in completes.get(qid, []))
        if qid not in turnins and not dungeon and not any(s.optional for s in sts):
            q = db.quest(qid) or {}
            rep.add("warning", "never-turned-in", sts[0],
                    f"se coge {_name(db, 'quest', qid)} y la guía no la entrega", ch.guide)


def _check_pre(db, rep: Report, ch: Character, st: FlatStep, qid: int, alts: list[int],
               turnins: dict[int, list[FlatStep]], steps: list[FlatStep]) -> None:
    """Alguna de `alts` (una sola = obligatoria) se entrega antes de coger `qid` en el paso `st`."""
    before = [p for p in alts if any(t.idx < st.idx for t in turnins.get(p, []))]
    label = " o ".join(_name(db, "quest", p) for p in alts)
    if before:
        if not st.optional and all(all(t.optional for t in turnins[p] if t.idx < st.idx) for p in before):
            rep.add("error", "pre-optional", st,
                    f"{_name(db, 'quest', qid)} (obligatoria) pide {label}, que la guía solo entrega en pasos opcionales",
                    ch.guide)
        return
    later = [t for p in alts for t in turnins.get(p, []) if t.idx > st.idx]
    if later:
        rep.add("error", "pre-order", st,
                f"{_name(db, 'quest', qid)} pide {label}, que la guía entrega después ({later[0].id})", ch.guide)
    else:
        rep.add("warning" if st.optional else "error", "pre-missing", st,
                f"{_name(db, 'quest', qid)} pide {label}, que la guía no hace", ch.guide)


# --------------------------------------------------------------------------------------------
# Entrada
# --------------------------------------------------------------------------------------------

def audit(db, root: Path = REPO_ROOT, guides=DEFAULT_GUIDES) -> Report:
    rep = Report()
    for gid in guides:
        meta, secs = load_guide(root, gid)
        check_filters(db, secs, root, meta.get("faction", "Alliance"), rep)
        for ch in characters(meta):
            steps = flatten(root, secs, ch)
            check_entities(db, steps, ch, rep)
            check_route(db, steps, ch, rep)
    return rep


def open_foreverdb(path=None):
    from foreverdb import ForeverDB
    return ForeverDB.open(path)


def main(argv: list[str] | None = None) -> int:
    setup_stdio()
    ap = argparse.ArgumentParser(description="Audita las guías contra forever-db (ver docs/AUDIT.md).")
    ap.add_argument("--guide", action="append", help="id de guía (repetible); por defecto las tres de personaje")
    ap.add_argument("--foreverdb", help="carpeta de forever-db (o SENDA_FOREVERDB; por defecto .cache/foreverdb)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--warnings", action="store_true", help="lista también los avisos y los revisados")
    args = ap.parse_args(argv)
    db = open_foreverdb(args.foreverdb)
    rep = audit(db, REPO_ROOT, tuple(args.guide or DEFAULT_GUIDES))
    if args.json:
        print(json.dumps({"forever_db": db.info.get("version"), "issues": [i.as_dict() for i in rep.issues]},
                         ensure_ascii=False, indent=1))
    else:
        shown = rep.issues if args.warnings else rep.errors
        for i in shown:
            print(i)
        n_rev = sum(1 for i in rep.issues if i.level == "reviewed")
        print(f"audit_guides: forever-db {db.info.get('version')}: {len(rep.errors)} errores, "
              f"{len(rep.warnings)} avisos, {n_rev} revisados")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())

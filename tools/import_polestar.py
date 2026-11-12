#!/usr/bin/env python3
"""Importa una guía compilada de Polestar (GPL-3) a una guía de Senda (TOML) y la compara con la nuestra.

Lee las guías **compiladas** (`addon/Polestar_Guides*/Guides.lua`), que llevan PNJ, mapa y coordenadas, con un
analizador de literales Lua propio (tools/polestar/luaparse.py): nunca ejecuta código de Polestar.

Cada objetivo (goal) de Polestar pasa a ser un paso de Senda (una acción por paso). Los `accept`/`turnin`
seguidos en el mismo PNJ dentro de un paso de Polestar se agrupan con `chain` (una sola conversación).
Lo que Senda no sabe expresar va a `tip` (visible) o `note` (interna) y al informe. Ver docs/IMPORT.md.

Uso:
    python tools/import_polestar.py --polestar RUTA --guide forever/alliance/nightelf/01-teldrassil \\
        --out data/guides/nightelf-druid-ps --race NightElf --class DRUID
Opciones:
    --id ID              id de la guía de Senda (por defecto, el nombre de la carpeta de --out)
    --prefix P           prefijo de ids de paso (por defecto ps-teld)
    --compare GUÍA       guía de Senda con la que comparar y fusionar (por defecto nightelf-druid)
    --compare-sections   secciones de esa guía para el informe (por defecto 01-shadowglen,02-teldrassil)
    --report RUTA        informe Markdown (por defecto <out>/REPORT.md)
    --dry-run            no escribe; imprime el informe
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import REPO_ROOT, load_toml, setup_stdio, write_text_lf  # noqa: E402
import localenames  # noqa: E402
from polestar.source import PolestarSource  # noqa: E402
from polestar.spanish import (  # noqa: E402
    AREA_ZONE, PROFS_ES, SKILLLINE_PROF, ZONES_ES, Namer, TOKEN_RE as _TOKEN_RE, npc_with, sentence,
)

CLASSES = ["WARRIOR", "PALADIN", "HUNTER", "ROGUE", "PRIEST", "SHAMAN", "MAGE", "WARLOCK", "DRUID"]
RACES = ["Human", "Dwarf", "NightElf", "Gnome", "Orc", "Scourge", "Tauren", "Troll", "Skyborne"]

# Marcos de mapa: f = "e" es el marco de Classic Era. En Forever solo cambian cuatro zonas (docs/FOREVER.md).
# forever = era * escala + desplazamiento. Solo conocemos la transformación de Ventormenta; las otras tres se
# importan sin convertir y el informe lo avisa.
ERA_TO_FOREVER: dict[int, tuple[tuple[float, float], tuple[float, float]]] = {
    1453: ((0.7737, 19.68), (0.7738, 24.43)),
}
ERA_DIFFERS = {1453, 1433, 1412, 1423}

STEP_KEYS = ["id", "do", "quest", "quests", "obj", "npc", "item", "count", "spells", "level", "prof", "skill",
             "node", "zone", "at", "wps", "radius", "if", "optional", "escort", "chain", "reqlevel", "text", "tip",
             "status", "sources", "note"]

ESCORT_TIP = "Escolta: si el PNJ no está, alguien la está haciendo; espera a que reaparezca."


# ---------------------------------------------------------------------------
# TOML
# ---------------------------------------------------------------------------

def toml_str(s: str) -> str:
    out = ['"']
    for c in s:
        if c == "\\":
            out.append("\\\\")
        elif c == '"':
            out.append('\\"')
        elif c == "\n":
            out.append("\\n")
        elif c == "\t":
            out.append("\\t")
        elif ord(c) < 0x20:
            out.append(f"\\u{ord(c):04x}")
        else:
            out.append(c)
    out.append('"')
    return "".join(out)


def toml_val(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        r = round(v, 2)
        return str(int(r)) + ".0" if r == int(r) else repr(r)
    if isinstance(v, str):
        return toml_str(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(toml_val(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k} = {toml_val(x)}" for k, x in v.items()) + " }"
    raise TypeError(type(v))


def toml_kv(k: str, v: Any) -> str:
    return f"{k} = {toml_val(v)}"


# ---------------------------------------------------------------------------
# Conversión
# ---------------------------------------------------------------------------

def to_forever(map_id: int | None, x: float, y: float, frame: str | None, log: dict) -> tuple[float, float]:
    if frame == "e" and map_id in ERA_DIFFERS:
        t = ERA_TO_FOREVER.get(map_id)
        if t:
            log["frames_converted"] += 1
            return x * t[0][0] + t[0][1], y * t[1][0] + t[1][1]
        log["frames_unconverted"].add(map_id)
    return x, y


def point(obj: dict, log: dict, label: str | None = None) -> list | None:
    if not isinstance(obj, dict) or obj.get("map") is None or obj.get("x") is None or obj.get("y") is None:
        return None
    x, y = to_forever(obj["map"], float(obj["x"]), float(obj["y"]), obj.get("f"), log)
    pt: list = [int(obj["map"]), round(x, 2), round(y, 2)]
    if label:
        pt.append(label)
    return pt


def spots(goal: dict, at: list | None, label: str, log: dict, limit: int = 3) -> list:
    """Camps principales (no alternativos) de `spotsPacked`: "x,y,z,r,n[,alt[,...]]" separados por ';'."""
    packed = goal.get("spotsPacked")
    if not isinstance(packed, str) or not at:
        return []
    out = []
    for part in packed.split(";"):
        f = part.split(",")
        if len(f) < 2:
            continue
        alt = f[5] if len(f) > 5 else ""
        if alt not in ("", "0"):
            continue
        try:
            x, y = to_forever(goal.get("map"), float(f[0]), float(f[1]), goal.get("f"), log)
        except ValueError:
            continue
        if abs(x - at[1]) < 1.0 and abs(y - at[2]) < 1.0:
            continue
        if any(abs(x - p[1]) < 1.0 and abs(y - p[2]) < 1.0 for p in out):
            continue
        out.append([at[0], round(x, 2), round(y, 2), label])
        if len(out) >= limit:
            break
    return out


def merge_only(*onlys: dict | None) -> dict:
    """Une `only` de paso y de objetivo (Y entre claves, O dentro de cada lista)."""
    res: dict[str, set] = {}
    for o in onlys:
        if not isinstance(o, dict):
            continue
        for key in ("classes", "races", "factions"):
            vals = o.get(key)
            if not vals:
                continue
            s = set(vals)
            res[key] = res[key] & s if key in res else s
    return res


def filter_of(only: dict) -> dict:
    f: dict[str, Any] = {}
    if only.get("classes"):
        f["class"] = [c for c in CLASSES if c in only["classes"]]
    if only.get("races"):
        f["race"] = [r for r in RACES if r in only["races"]]
    if only.get("factions") and len(only["factions"]) == 1:
        f["faction"] = next(iter(only["factions"]))
    return f


def translate_when(when: list | None, goal_quests: set[int]) -> tuple[dict, list[str], bool]:
    """`when` de Polestar -> (filtro if, condiciones no expresables, ¿hace el paso opcional?)."""
    f: dict[str, Any] = {}
    lost: list[str] = []
    optional = False
    for c in when or []:
        if not isinstance(c, dict):
            continue
        k, neg = c.get("k"), bool(c.get("neg"))
        if k == "level" and not neg and isinstance(c.get("n"), int):
            op, n = c.get("op", ">="), c["n"]
            if op == ">=":
                f["minlevel"] = n
            elif op == ">":
                f["minlevel"] = n + 1
            elif op == "<":
                f["maxlevel"] = n - 1
            elif op == "<=":
                f["maxlevel"] = n
            else:
                lost.append(f"level {op} {n}")
                optional = True
            continue
        if k == "skill" and not neg and SKILLLINE_PROF.get(c.get("skillLine")):
            f.setdefault("prof", []).append(SKILLLINE_PROF[c["skillLine"]])
            continue
        desc = describe_cond(c)
        if k == "onquest" and set(c.get("q") or []) <= goal_quests:
            lost.append(desc + " (implícita: el paso es de esa misión)")
            continue
        if k == "knows" and neg:
            lost.append(desc + " (si ya lo sabes, la misión ya estará hecha)")
            continue
        lost.append(desc)
        optional = True
    return f, lost, optional


def describe_cond(c: dict) -> str:
    k = c.get("k")
    neg = "no " if c.get("neg") else ""
    if k == "skill":
        return f"{neg}tienes {c.get('name')} {c.get('n', 1)}+"
    if k == "knows":
        return f"{neg}conoces el hechizo {c.get('spell')}"
    if k == "onquest":
        return f"{neg}llevas la misión {', '.join(map(str, c.get('q') or []))}"
    if k == "money":
        return f"{neg}dinero {c.get('op', '>=')} {c.get('n')} cobre"
    if k == "group":
        return f"{neg}vas en grupo para la misión {c.get('q')}"
    if k == "complete":
        return f"{neg}tienes lista la misión {c.get('q')}"
    if k == "level":
        return f"{neg}nivel {c.get('op', '>=')} {c.get('n')}"
    return f"{neg}{k} {c}"


class Importer:
    def __init__(self, src: PolestarSource, guide_id: str, prefix: str, race: str | None, klass: str | None):
        self.src = src
        self.guide_id = guide_id
        self.prefix = prefix
        self.race = race
        self.klass = klass
        self.commit = src.commit()
        self.file, self.guide = src.load_guide(guide_id)
        names = dict(self.guide.get("names") or {})
        for pst in self.guide.get("steps") or []:  # títulos en inglés de las misiones, de respaldo
            for g in pst.get("goals") or []:
                if isinstance(g, dict) and isinstance(g.get("quest"), int) and g.get("title"):
                    names.setdefault(f"quest:{g['quest']}", g["title"])
        self.namer = Namer(src.name_es, names)
        self.texts = src.texts_es(guide_id)
        self.log: dict[str, Any] = {
            "frames_converted": 0, "frames_unconverted": set(), "dropped": [], "lost_when": [],
            "untranslated": [], "manual": [], "flags": [], "chains": 0, "dedup": 0,
        }
        self.steps: list[dict] = []
        self.last_at: list | None = None

    # --- textos
    def tr(self, en: str | None) -> tuple[str | None, bool]:
        """Traducción esES de un texto de Polestar (con sus {kind:id} ya resueltos). (texto, ¿traducido?)."""
        if not en:
            return None, True
        es = self.texts.get(en)
        if es:
            return self.namer.render(es), True
        return self.namer.render(en), False

    def note_text(self, en: str | None, where: str) -> str | None:
        txt, ok = self.tr(en)
        if not txt:
            return None
        if not ok:
            self.log["untranslated"].append(f"{where}: {self.namer.unrender(txt)}")
            return "[EN] " + sentence(txt)
        return sentence(txt)

    def npc_name(self, goal: dict) -> str | None:
        """Nombre escrito del PNJ (para decidir el artículo y para etiquetas de puntos)."""
        if goal.get("npc"):
            return self.namer.name("npc", goal["npc"], goal.get("npcName"))
        return None

    def npc_token(self, goal: dict) -> str | None:
        """Ficha {npc:N} del PNJ para el texto (el cliente pone el nombre)."""
        if goal.get("npc"):
            return self.namer.token("npc", goal["npc"], goal.get("npcName"))
        return None

    # --- objetivos -> pasos
    def allowed(self, only: dict) -> bool:
        if self.klass and only.get("classes") and self.klass not in only["classes"]:
            return False
        if self.race and only.get("races") and self.race not in only["races"]:
            return False
        return True

    def run(self) -> list[dict]:
        for si, pst in enumerate(self.guide.get("steps") or [], 1):
            self.import_step(si, pst)
        return self.steps

    def import_step(self, si: int, pst: dict) -> None:
        goals = [g for g in pst.get("goals") or [] if isinstance(g, dict)]
        step_only = pst.get("only")
        goal_quests = {g["quest"] for g in goals if isinstance(g.get("quest"), int)}
        wfilter, lost, w_optional = translate_when(pst.get("when"), goal_quests)
        extra_notes = []
        for key in ("along", "label", "skipto"):
            if pst.get(key) is not None:
                extra_notes.append(f"{key} = {pst[key]!r}")
        if lost:
            self.log["lost_when"].append((si, self.namer.render(pst.get("title") or "", tokens=False), lost))
        if extra_notes:
            self.log["flags"].append((si, "paso: " + ", ".join(extra_notes)))
        title_en = pst.get("title")
        title, _ = self.tr(title_en) if title_en else (None, True)
        step_tip = self.note_text(pst.get("note"), f"paso {si} (nota)")
        made: list[dict] = []
        for gi, g in enumerate(goals, 1):
            only = merge_only(step_only, g.get("only"))
            if not self.allowed(only):
                self.log["dropped"].append((si, gi, g.get("t"), g.get("quest"), sorted(only.get("classes") or [])
                                            + sorted(only.get("races") or [])))
                continue
            st = self.goal_step(si, gi, g)
            if st is None:
                continue
            f = filter_of(only)
            f.update({k: v for k, v in wfilter.items() if k != "prof"})
            profs = list(wfilter.get("prof") or [])
            if g.get("profLine") and SKILLLINE_PROF.get(g["profLine"]):
                profs.append(SKILLLINE_PROF[g["profLine"]])
            if profs:
                f["prof"] = sorted(set(profs))
            if f:
                st["if"] = f
            if g.get("optional") or w_optional:
                st["optional"] = True
            notes = [f"Polestar paso {si}" + (f" «{self.namer.render(title_en, tokens=False)}»" if title_en else "")
                     + f", objetivo {gi} ({g.get('t')})"]
            if g.get("f") == "e" and g.get("map") in ERA_DIFFERS:
                notes.append("coordenadas del marco de Era" + (" convertidas a Forever"
                                                              if g.get("map") in ERA_TO_FOREVER else " SIN convertir"))
            if lost:
                notes.append("condición no expresable: " + "; ".join(lost))
            notes += extra_notes
            st["_notes"] = notes + st.get("_notes", [])
            st["_ps"] = (si, gi)
            st["_title"] = title
            made.append(st)
        # dedupe: mismo do/quest/obj/item seguido (p. ej. «usa el vial» y «llena el vial» del mismo objetivo)
        dedup: list[dict] = []
        for st in made:
            prev = dedup[-1] if dedup else None
            if prev and all(prev.get(k) == st.get(k) for k in ("do", "quest", "obj", "item")) \
                    and prev["do"] not in ("goto", "note", "fly"):
                prev["_tips"] = prev.get("_tips", []) + [st["text"]] + st.get("_tips", [])
                self.log["dedup"] += 1
                continue
            dedup.append(st)
        # chain: accept/turnin seguidos con el mismo PNJ
        i = 0
        while i < len(dedup):
            j = i
            npc = dedup[i].get("npc")
            while j + 1 < len(dedup) and npc and dedup[j + 1].get("npc") == npc \
                    and dedup[i]["do"] in ("accept", "turnin") and dedup[j + 1]["do"] in ("accept", "turnin"):
                j += 1
            if j > i:
                cid = f"{self.prefix}-s{si:03d}-{npc}"
                for k in range(i, j + 1):
                    dedup[k]["chain"] = cid
                self.log["chains"] += 1
            i = j + 1
        if dedup and step_tip:
            dedup[0]["_tips"] = [step_tip] + dedup[0].get("_tips", [])
        for st in dedup:
            self.finish(st)

    def finish(self, st: dict) -> None:
        n = len(self.steps) + 1
        si, gi = st.pop("_ps")
        st.pop("_title", None)
        tips = [t for t in st.pop("_tips", []) if t]
        notes = st.pop("_notes", [])
        out: dict[str, Any] = {"id": f"{self.prefix}-{n:03d}"}
        out.update(st)
        if tips:
            out["tip"] = " ".join(tips)
        out["status"] = "unverified"
        out["sources"] = [f"polestar:{self.commit}/{self.guide_id}#{si}"]
        if notes:
            out["note"] = " · ".join(notes)
        if out["do"] in ("note", "use"):
            self.log["manual"].append((out["id"], out["do"], self.namer.unrender(out["text"])))
        if out.get("at"):
            self.last_at = out["at"]
        self.steps.append(out)

    def goal_step(self, si: int, gi: int, g: dict) -> dict | None:
        t = g.get("t")
        log = self.log
        at = point(g, log)
        q = g.get("quest")
        qn = self.namer.quest(q, g.get("title")) if q else None
        npc = self.npc_name(g)
        npc_t = self.npc_token(g)
        st: dict[str, Any] = {}
        tips: list[str] = []
        escort = False
        goal_note = g.get("note")
        note_txt, note_ok = self.tr(goal_note) if goal_note else (None, True)
        suffix = ""
        # Una nota hecha solo de nombres («{npc:2079}: {quest:3120}») repite el texto del paso: fuera.
        if goal_note and not re.search(r"[A-Za-z]", _TOKEN_RE.sub("", goal_note)):
            note_txt = None
        # «{npc:X}, junto al sendero» -> se añade al texto del paso cuando habla del mismo PNJ
        if note_txt and g.get("npc") and npc_t and goal_note.startswith(f"{{npc:{g['npc']}}}") and note_ok \
                and note_txt.startswith(npc_t):
            rest = note_txt[len(npc_t):].lstrip(" ,:;")
            if rest:
                suffix = ", " + rest.rstrip(".")
            note_txt = None
        if note_txt:
            if not note_ok:
                log["untranslated"].append(f"paso {si}.{gi}: {self.namer.unrender(note_txt)}")
                tips.append("[EN] " + sentence(note_txt))
            else:
                tips.append(sentence(note_txt))
        if g.get("escort"):
            # El campo `escort` del esquema (se pone abajo, en accept/complete): el HUD pone él mismo la nota.
            escort = True
            log["flags"].append((si, f"objetivo {gi}: escolta (quest {q})"))
        if g.get("group"):
            grp = g["group"]
            tips.append("Élite: mejor en grupo." if isinstance(grp, dict) and grp.get("kind") == "elite"
                        else "Contenido de grupo.")
            log["flags"].append((si, f"objetivo {gi}: grupo {grp}"))
        if g.get("limit"):
            tips.append(f"Misión con tiempo: {round(g['limit'] / 60)} min desde que la coges.")
            log["flags"].append((si, f"objetivo {gi}: misión con tiempo ({g['limit']} s)"))
        if g.get("rewards"):
            log["flags"].append((si, f"objetivo {gi}: recompensas {g['rewards']}"))
        lost_fields = [k for k in ("pre", "preAll", "closedBy", "parent") if g.get(k)]
        notes: list[str] = []
        if lost_fields:
            notes.append("datos no importados: " + ", ".join(lost_fields))

        def item_name(label: bool = False) -> str:
            """Ficha del objeto para el texto; con label=True, su nombre escrito (etiqueta de un punto)."""
            fn = self.namer.name if label else self.namer.token
            return fn("item", g.get("item"), g.get("itemName"))

        def from_text() -> str:
            if g.get("fromKind") == "npc" and g.get("fromNpcs"):
                names = [self.namer.token("npc", n.get("npc"), n.get("npcName")) for n in g["fromNpcs"]
                         if isinstance(n, dict)]
                return " de " + " y ".join(dict.fromkeys(names)) if names else ""
            if g.get("fromKind") == "object" and g.get("fromId"):
                return " de " + self.namer.token("object", g["fromId"], g.get("from"))
            return ""

        if t == "accept":
            st = {"do": "accept", "quest": q}
            if g.get("npc"):
                st["npc"] = g["npc"]
                text = f"Coge {qn} {npc_with('de', npc, npc_t)}{suffix}."
            elif g.get("object"):
                text = f"Coge {qn} ({self.namer.token('object', g['object'], g.get('objName'))}){suffix}."
            elif g.get("item"):
                text = f"Usa {item_name()} para empezar {qn}."
            else:
                text = f"Coge {qn}."
            if isinstance(g.get("minLevel"), int) and g["minLevel"] > 1:
                st["reqlevel"] = g["minLevel"]
        elif t == "turnin":
            st = {"do": "turnin", "quest": q}
            if g.get("npc"):
                st["npc"] = g["npc"]
                text = f"Entrega {qn} {npc_with('a', npc, npc_t)}{suffix}."
            elif g.get("object"):
                text = f"Entrega {qn} en {self.namer.token('object', g['object'], g.get('objName'))}{suffix}."
            else:
                text = f"Entrega {qn}."
        elif t == "kill":
            target = self.namer.name("npc", g.get("npc"), g.get("target")) if g.get("npc") else g.get("target")
            target_t = self.namer.token("npc", g.get("npc"), g.get("target")) if g.get("npc") else g.get("target")
            count = f" ({g['count']})" if g.get("count") else ""
            if q:
                st = {"do": "complete", "quest": q}
                if g.get("oi"):
                    st["obj"] = g["oi"]
                text = f"Mata {target_t}{count} para {qn}."
            else:
                st = {"do": "note"}
                text = f"Mata {target_t}{count}."
            if at:
                st["wps"] = spots(g, at, target, log)
        elif t == "collect":
            count = f" ({g['count']})" if g.get("count") else ""
            verb = "Recoge" if g.get("fromKind") == "object" else "Consigue"
            if q:
                st = {"do": "complete", "quest": q}
                if g.get("oi"):
                    st["obj"] = g["oi"]
                text = f"{verb} {item_name()}{count}{from_text()} para {qn}."
            else:
                st = {"do": "loot", "item": g.get("item"), "count": int(g.get("count") or 1)}
                text = f"{verb} {item_name()}{count}{from_text()}."
            if at:
                st["wps"] = spots(g, at, item_name(label=True), log)
        elif t in ("complete", "interact"):
            st = {"do": "complete", "quest": q} if q else {"do": "note"}
            if q and g.get("oi"):
                st["obj"] = g["oi"]
            if g.get("startItem"):
                text = f"Usa {self.namer.token('item', g['startItem'], g.get('startItemName'))} y completa {qn}."
            elif t == "interact" and g.get("object"):
                text = f"Usa {self.namer.token('object', g['object'], g.get('objName'))}" + (f" para {qn}." if q else ".")
            else:
                text = f"Completa {qn}." if q else "Completa el objetivo."
            objs = [o.get("text") for o in g.get("objs") or [] if isinstance(o, dict) and o.get("text")]
            if objs:
                notes.append("objetivos (EN): " + "; ".join(objs))
        elif t == "use":
            if q and g.get("oi"):
                st = {"do": "complete", "quest": q, "obj": g["oi"]}
                text = f"Usa {item_name()} para {qn}."
            else:
                st = {"do": "use", "item": g.get("item")}
                text = f"Usa {item_name()}" + (f" para {qn}." if q else ".")
        elif t == "goto":
            dest = None
            if g.get("text"):
                dest, ok = self.tr(g["text"])
                if not ok and re.search(r"[A-Za-z]", _TOKEN_RE.sub("", g["text"])):
                    log["untranslated"].append(f"paso {si}.{gi} (destino): {self.namer.unrender(dest)}")
            elif g.get("area"):
                dest = self.namer.name("area", g["area"])
            st = {"do": "goto"}
            text = f"Ve a {dest}." if dest else "Ve al punto marcado."
        elif t == "getfp":
            st = {"do": "getfp", "node": str(g.get("node") or g.get("location") or "")}
            if g.get("npc"):
                st["npc"] = g["npc"]
            loc = self.place(g)
            text = f"Coge la ruta de vuelo de {loc}" + (f" con {npc_t}." if npc_t else ".")
        elif t == "fly":
            zone = self.zone_for(g, si)
            st = {"do": "fly"}
            if zone:
                st["zone"] = zone
            text = f"Vuela a {self.place(g)}."
        elif t == "sethome":
            st = {"do": "sethearth"}
            if g.get("npc"):
                st["npc"] = g["npc"]
            zone = g.get("map") or self.zone_for(g, si)
            if zone:
                st["zone"] = zone
            text = f"Pon la piedra de hogar en {self.place(g)}" + (f" con {npc_t}." if npc_t else ".")
        elif t == "hearth":
            st = {"do": "hearth"}
            zone = self.zone_for(g, si)
            if zone:
                st["zone"] = zone
            text = f"Usa la piedra de hogar para volver a {self.place(g)}."
        elif t == "train":
            if g.get("skill") and SKILLLINE_PROF.get(g.get("skillLine")):
                st = {"do": "learn_prof", "prof": SKILLLINE_PROF[g["skillLine"]]}
                if g.get("npc"):
                    st["npc"] = g["npc"]
                prof = PROFS_ES.get(g["skill"], g["skill"])
                text = f"Aprende {prof} con {npc_t}." if npc_t else f"Aprende {prof}."
            elif g.get("class"):
                cand = self.pick_trainer(g)
                st = {"do": "note"}
                if cand:
                    st["npc"] = cand["npc"]
                    at = point(cand, log)
                    tname = self.namer.token("npc", cand["npc"], cand.get("npcName"))
                    text = f"Entrena tus hechizos de clase con {tname}."
                else:
                    text = "Entrena tus hechizos de clase."
                notes.append("train class: Senda necesita la lista de hechizos (spells) para detectarlo solo")
            else:
                st = {"do": "note"}
                if g.get("npc"):
                    st["npc"] = g["npc"]
                text = f"Entrena con {npc_t}." if npc_t else (self.namer.render(g.get("text") or "") or "Entrena.")
                notes.append("train sin hechizos: manual")
        elif t == "buy":
            st = {"do": "buy", "item": g.get("item"), "count": int(g.get("count") or 1)}
            if g.get("npc"):
                st["npc"] = g["npc"]
            count = f" ({g['count']})" if g.get("count") and g["count"] > 1 else ""
            text = f"Compra {item_name()}{count}" + (f" {npc_with('a', npc, npc_t)}." if npc else ".")
        elif t == "level":
            st = {"do": "level", "level": int(g.get("level") or 1)}
            text = f"Sube al nivel {st['level']}."
        elif t == "note":
            st = {"do": "note"}
            txt, ok = self.tr(g.get("text"))
            if not ok:
                log["untranslated"].append(f"paso {si}.{gi}: {self.namer.unrender(txt or '')}")
                text = "[EN] " + sentence(txt or "")
            else:
                text = sentence(txt or "Nota.")
        else:
            st = {"do": "note"}
            text = self.namer.render(g.get("text") or f"{t}")
            notes.append(f"tipo de objetivo de Polestar sin equivalente: {t}")
            log["flags"].append((si, f"objetivo {gi}: tipo {t} importado como nota"))
        if at:
            st["at"] = at
        st["text"] = sentence(text)
        if escort and st.get("do") in ("accept", "complete"):
            st["escort"] = True
        elif escort:
            tips.append(ESCORT_TIP)
        st["_tips"] = tips
        st["_notes"] = notes
        return {k: v for k, v in st.items() if v is not None and v != []}

    def place(self, g: dict) -> str:
        if g.get("area"):
            return self.namer.name("area", g["area"], g.get("location"))
        if g.get("node"):
            taxi = self.src.name_es("taxi", g["node"])
            if taxi:
                return taxi.split(",")[0]
        return g.get("location") or "el destino"

    def zone_for(self, g: dict, si: int) -> int | None:
        """uiMapID de llegada: la subzona conocida, si no el mapa del siguiente objetivo con coordenadas."""
        if g.get("area") in AREA_ZONE:
            return AREA_ZONE[g["area"]]
        found = False
        for pst in (self.guide.get("steps") or [])[si - 1:]:
            for gg in pst.get("goals") or []:
                if gg is g:
                    found = True
                    continue
                if found and isinstance(gg, dict) and gg.get("map"):
                    return int(gg["map"])
        return None

    def pick_trainer(self, g: dict) -> dict | None:
        cands = [c for c in g.get("candidates") or [] if isinstance(c, dict)]
        if self.klass:
            cands = [c for c in cands if not c.get("classes") or self.klass in c["classes"]]
        if g.get("zone"):
            same = [c for c in cands if c.get("map") == g["zone"]]
            cands = same or cands
        if not cands:
            return None
        if self.last_at:
            lm, lx, ly = self.last_at[0], self.last_at[1], self.last_at[2]

            def dist(c: dict) -> float:
                if c.get("map") != lm:
                    return 1e9
                return math.hypot(c["x"] - lx, c["y"] - ly)
            cands.sort(key=dist)
        return cands[0]


# ---------------------------------------------------------------------------
# Fusión con Senda y comparación
# ---------------------------------------------------------------------------

def step_quests(s: dict) -> list[int]:
    if isinstance(s.get("quests"), list):
        return [q for q in s["quests"] if isinstance(q, int)]
    return [s["quest"]] if isinstance(s.get("quest"), int) else []


def senda_index(steps: list[dict]) -> dict[tuple[str, int], list[dict]]:
    idx: dict[tuple[str, int], list[dict]] = {}
    for s in steps:
        if s.get("do") in ("accept", "turnin", "complete"):
            for q in step_quests(s):
                idx.setdefault((s["do"], q), []).append(s)
    return idx


def merge_with_senda(steps: list[dict], senda_steps: list[dict]) -> list[tuple[dict, dict, str]]:
    """Regla «lo hecho a mano gana». Para cada paso importado con un paso de Senda de la misma misión y acción,
    conserva el texto y el truco de Senda (y lo anota). Devuelve [(paso importado, paso de Senda, tipo)] con
    tipo "igual" (misma acción y objetivo) o "agrupa" (Senda hace la misión entera en un paso y Polestar la
    parte por objetivos: se mantiene el texto generado y solo se toma el truco en el primero)."""
    idx = senda_index(senda_steps)
    out = []
    tip_used: set[str] = set()
    for st in steps:
        if st.get("do") not in ("accept", "turnin", "complete") or not isinstance(st.get("quest"), int):
            continue
        cands = idx.get((st["do"], st["quest"]))
        if not cands:
            continue
        same = [s for s in cands if s.get("obj") == st.get("obj")]
        if same:
            s = same[0]
            st["text"] = s["text"]
            if s.get("tip"):
                st["tip"] = s["tip"]
            kind = "igual"
        else:
            s = cands[0]
            if s.get("tip") and s["id"] not in tip_used:
                st["tip"] = s["tip"] + (" " + st["tip"] if st.get("tip") else "")
            kind = "agrupa"
        tip_used.add(s["id"])
        st["note"] = (st.get("note", "") + f" · ya en Senda: {s['id']}").lstrip(" ·")
        out.append((st, s, kind))
    return out


def lcs_keys(a: list, b: list) -> set:
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            dp[i][j] = dp[i + 1][j + 1] + 1 if a[i] == b[j] else max(dp[i + 1][j], dp[i][j + 1])
    i = j = 0
    keep = set()
    while i < n and j < m:
        if a[i] == b[j]:
            keep.add(a[i])
            i += 1
            j += 1
        elif dp[i + 1][j] >= dp[i][j + 1]:
            i += 1
        else:
            j += 1
    return keep


def load_senda_guide(guide_dir: Path) -> tuple[dict[str, list[dict]], list[str]]:
    g = load_toml(guide_dir / "guide.toml")
    secs: dict[str, list[dict]] = {}
    for sid in g.get("sections", []):
        if sid.startswith("shared:"):
            p = REPO_ROOT / "data" / "shared" / (sid[7:] + ".toml")
        else:
            p = guide_dir / (sid + ".toml")
        if p.is_file():
            secs[sid] = load_toml(p).get("step", [])
    return secs, list(secs)


def build_report(imp: Importer, steps: list[dict], merges: list, senda_secs: dict[str, list[dict]],
                 compare: list[str], senda_guide: str) -> str:
    log = imp.log
    lines: list[str] = []
    w = lines.append
    g = imp.guide
    w(f"# Informe de importación: {imp.guide_id}")
    w("")
    w(f"- Polestar `{imp.commit}`, archivo `{imp.file.relative_to(imp.src.root).as_posix()}`.")
    w(f"- Guía de Polestar: {len(g.get('steps') or [])} pasos, "
      f"{sum(len(s.get('goals') or []) for s in g.get('steps') or [])} objetivos, niveles "
      f"{g.get('minLevel')}-{g.get('maxLevel')}.")
    w(f"- Filtro: raza {imp.race or 'todas'}, clase {imp.klass or 'todas'}. Objetivos descartados por el filtro: "
      f"{len(log['dropped'])}.")
    w(f"- Pasos de Senda generados: {len(steps)} ({sum(1 for s in steps if s.get('chain'))} en {log['chains']} "
      f"cadenas; {log['dedup']} objetivos repetidos fusionados).")
    w(f"- Coordenadas de Era convertidas: {log['frames_converted']}; mapas de Era sin transformación conocida: "
      f"{sorted(log['frames_unconverted']) or 'ninguno'}.")
    w("")

    # comparación
    cmp_steps = [s for sid in compare for s in senda_secs.get(sid, [])]
    all_steps = [s for ss in senda_secs.values() for s in ss]
    where = {}
    for sid, ss in senda_secs.items():
        for s in ss:
            for q in step_quests(s):
                where.setdefault(q, sid)
    ps_q = {s["quest"] for s in steps if isinstance(s.get("quest"), int)}
    sd_q = {q for s in cmp_steps for q in step_quests(s)}
    w(f"## Comparación con `{senda_guide}` ({', '.join(compare)})")
    w("")
    eq = sum(1 for m in merges if m[2] == "igual")
    ag = sum(1 for m in merges if m[2] == "agrupa")
    w(f"- Misiones en Polestar: {len(ps_q)}; en esas secciones de Senda: {len(sd_q)}; en las dos: {len(ps_q & sd_q)}.")
    w(f"- Pasos importados que ya están en Senda (misma misión y acción, en toda la guía): {len(merges)} "
      f"({eq} iguales: se usa el texto de Senda; {ag} donde Senda agrupa objetivos que Polestar separa).")
    w("")
    only_ps = sorted(ps_q - sd_q)
    w(f"### Solo en Polestar ({len(only_ps)})")
    w("")
    if only_ps:
        w("| Misión | Nombre | ¿En otra sección de Senda? |")
        w("|---|---|---|")
        for q in only_ps:
            w(f"| {q} | {imp.namer.name('quest', q)} | {where.get(q, 'no')} |")
    else:
        w("Ninguna.")
    w("")
    only_sd = sorted(sd_q - ps_q)
    w(f"### Solo en Senda ({len(only_sd)})")
    w("")
    if only_sd:
        names = {}
        for s in cmp_steps:
            for q in step_quests(s):
                names.setdefault(q, s)
        w("| Misión | Paso de Senda | Texto |")
        w("|---|---|---|")
        for q in only_sd:
            s = names[q]
            w(f"| {q} | {s['id']} | {s['text'].replace('|', '/')} |")
    else:
        w("Ninguna.")
    w("")
    # orden
    def seq(ss: list[dict]) -> list[tuple[str, int]]:
        out, seen = [], set()
        for s in ss:
            if s.get("do") in ("accept", "turnin"):
                for q in step_quests(s):
                    k = (s["do"], q)
                    if k not in seen:
                        seen.add(k)
                        out.append(k)
        return out
    a, b = seq(steps), seq(cmp_steps)
    common = set(a) & set(b)
    a2, b2 = [k for k in a if k in common], [k for k in b if k in common]
    keep = lcs_keys(a2, b2)
    moved = [k for k in a2 if k not in keep]
    w(f"### Diferencias de orden ({len(moved)} de {len(common)} cogidas/entregas comunes)")
    w("")
    w("Cogidas y entregas comunes fuera de la subsecuencia común más larga: Polestar las hace en otro momento.")
    w("")
    if moved:
        w("| Acción | Misión | Posición Polestar | Posición Senda |")
        w("|---|---|---|---|")
        for k in moved:
            w(f"| {k[0]} | {k[1]} {imp.namer.name('quest', k[1])} | {a2.index(k) + 1} | {b2.index(k) + 1} |")
    else:
        w("Ninguna.")
    w("")
    # coordenadas
    sidx = senda_index(cmp_steps)
    diffs = []
    for st in steps:
        if st.get("do") not in ("accept", "turnin") or not st.get("at"):
            continue
        for s in sidx.get((st["do"], st.get("quest")), [])[:1]:
            if not s.get("at"):
                continue
            pa, pb = st["at"], s["at"]
            if pa[0] != pb[0]:
                diffs.append((st, s, "mapa distinto"))
                continue
            d = math.hypot(pa[1] - pb[1], pa[2] - pb[2])
            if d > 1.0:
                diffs.append((st, s, f"{d:.2f}"))
    w(f"### Coordenadas que difieren más de 1.0 ({len(diffs)})")
    w("")
    if diffs:
        w("| Acción | Misión | Polestar | Senda | Distancia |")
        w("|---|---|---|---|---|")
        for st, s, d in diffs:
            w(f"| {st['do']} | {st['quest']} | {st['at'][0]} {st['at'][1]}, {st['at'][2]} | "
              f"{s['at'][0]} {s['at'][1]}, {s['at'][2]} ({s['id']}) | {d} |")
    else:
        w("Ninguna.")
    w("")
    # pérdidas
    w("## Lo que no se ha podido expresar")
    w("")
    w(f"### Condiciones `when` ({len(log['lost_when'])} pasos)")
    w("")
    for si, title, lost in log["lost_when"]:
        w(f"- Paso {si} ({title}): {'; '.join(lost)}")
    w("")
    w(f"### Marcas de objetivo y de paso ({len(log['flags'])})")
    w("")
    for si, msg in log["flags"]:
        w(f"- Paso {si}: {msg}")
    w("")
    manual = log["manual"]
    w(f"### Pasos manuales (Hecho a mano) ({len(manual)})")
    w("")
    for sid, d, text in manual:
        w(f"- `{sid}` ({d}): {text}")
    w("")
    w(f"### Textos sin traducción en Polestar ({len(log['untranslated'])}, quedan en inglés con [EN])")
    w("")
    for t in log["untranslated"]:
        w(f"- {t}")
    w("")
    w(f"### Nombres sin versión esES ({len(imp.namer.missing)}, quedan en inglés)")
    w("")
    w(", ".join(sorted(imp.namer.missing)) or "Ninguno.")
    w("")
    if log["dropped"]:
        w(f"### Objetivos de otras clases o razas descartados ({len(log['dropped'])})")
        w("")
        for si, gi, t, q, who in log["dropped"]:
            w(f"- Paso {si}.{gi}: {t} {q or ''} ({', '.join(who)})")
        w("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Salida
# ---------------------------------------------------------------------------

def section_toml(sec: dict, steps: list[dict], header: list[str]) -> str:
    out = [f"# {h}" if h else "#" for h in header]
    for k in ("id", "title", "levels", "map", "summary"):
        if k in sec:
            out.append(toml_kv(k, sec[k]))
    for st in steps:
        out.append("")
        out.append("[[step]]")
        for k in STEP_KEYS:
            if k in st:
                out.append(toml_kv(k, st[k]))
    return "\n".join(out) + "\n"


def guide_toml(meta: dict, header: list[str]) -> str:
    out = [f"# {h}" if h else "#" for h in header]
    for k in ("id", "title", "summary", "faction", "races", "classes", "levels", "order", "status", "sources",
              "note"):
        if k in meta:
            out.append(toml_kv(k, meta[k]))
    out.append("sections = [")
    for s in meta["sections"]:
        out.append(f"  {toml_str(s)},")
    out.append("]")
    return "\n".join(out) + "\n"


def write_fallback_names(namer, data_root: Path) -> tuple[int, list[Path]]:
    """Los nombres que el importador conoce van a data/locale/ como respaldo de las fichas del texto: los esES
    (Polestar o tabla propia) a esES/ y los ingleses de Polestar a enUS/ (cliente en inglés, y último recurso
    si no hay nombre esES). Nunca pisan un nombre sacado del juego (prioridad, ver localenames.py)."""
    changed, files = 0, []
    for locale, table in (("esES", namer.fallback), ("enUS", namer.fallback_en)):
        if not table:
            continue
        data = localenames.load(data_root, locale)
        for kind, entries in table.items():
            for ident, (name, source) in entries.items():
                what, _ = localenames.merge(data, kind, ident, name, source)
                if what in ("new", "renamed"):
                    changed += 1
        files += localenames.save(data_root, locale, data, kinds=sorted(table))
    return changed, files


def main(argv: list[str] | None = None) -> int:
    setup_stdio()
    ap = argparse.ArgumentParser(description="Importa una guía compilada de Polestar a Senda.")
    ap.add_argument("--polestar", required=True, help="clon de Polestar (solo lectura)")
    ap.add_argument("--guide", required=True, help="id de la guía de Polestar")
    ap.add_argument("--out", required=True, help="carpeta de la guía de Senda a escribir")
    ap.add_argument("--id", help="id de la guía de Senda (por defecto, el nombre de --out)")
    ap.add_argument("--prefix", default="ps-teld", help="prefijo de ids de paso")
    ap.add_argument("--race", help="raza (raceFile), p. ej. NightElf")
    ap.add_argument("--class", dest="klass", help="clase (classFile), p. ej. DRUID")
    ap.add_argument("--compare", default="nightelf-druid", help="guía de Senda para fusionar y comparar")
    ap.add_argument("--compare-sections", default="01-shadowglen,02-teldrassil")
    ap.add_argument("--report", help="informe Markdown (por defecto <out>/REPORT.md)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-names", action="store_true",
                    help="no escribir los nombres esES de respaldo en data/locale/esES/")
    args = ap.parse_args(argv)

    src = PolestarSource(args.polestar)
    imp = Importer(src, args.guide, args.prefix, args.race, args.klass)
    steps = imp.run()

    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir
    gid = args.id or out_dir.name
    senda_dir = REPO_ROOT / "data" / "guides" / args.compare
    senda_secs, _ = load_senda_guide(senda_dir) if (senda_dir / "guide.toml").is_file() else ({}, [])
    merges = merge_with_senda(steps, [s for ss in senda_secs.values() for s in ss])
    compare = [s.strip() for s in args.compare_sections.split(",") if s.strip()]
    report = build_report(imp, steps, merges, senda_secs, compare, args.compare)

    g = imp.guide
    lo, hi = int(g.get("minLevel") or 1), int(g.get("maxLevel") or 60)
    zone = g.get("zone")
    zone_name = ZONES_ES.get(zone, g.get("zoneName") or "")
    sec_id = f"ps-{args.guide.rsplit('/', 1)[-1].split('-', 1)[-1]}"
    sec_file = args.guide.rsplit("/", 1)[-1]
    src_tag = f"polestar:{imp.commit}/{args.guide}"
    header = [
        f"GENERADO por tools/import_polestar.py desde Polestar (GPL-3), {args.guide}",
        f"commit {imp.commit}. Adaptado de Polestar: ruta, coordenadas y notas; textos en español",
        "de plantilla (o de la traducción esES de Polestar) salvo los pasos que ya estaban en Senda, que conservan",
        "su texto. Los nombres van como fichas ({quest:N}, {npc:N}...) que pone el cliente al mostrarlas; el",
        "respaldo esES está en data/locale/esES/. No editar a mano: vuelve a importar. Ver docs/IMPORT.md y REPORT.md.",
    ]
    sec = {
        "id": sec_id,
        "title": f"{zone_name} (ruta de Polestar)",
        "levels": [lo, hi],
        "map": zone,
        "summary": f"Prototipo: la ruta de Polestar para {zone_name} ({lo}-{hi}), importada sin verificar.",
    }
    meta = {
        "id": gid,
        "title": f"Druida elfo de la noche: {zone_name} (prototipo Polestar)" if args.klass == "DRUID"
        and args.race == "NightElf" else f"{zone_name} (prototipo Polestar)",
        "summary": "Ruta importada de Polestar para compararla en el juego con la guía de Senda. Solo se elige a "
                   f"mano: /senda guide {gid}.",
        "faction": g.get("faction") or "Alliance",
        "races": [args.race] if args.race else list(g.get("races") or RACES[:4]),
        "classes": [args.klass] if args.klass else CLASSES,
        "levels": [lo, hi],
        "order": -1,
        "status": "unverified",
        "sources": [src_tag],
        "note": "order = -1: guía de prueba, nunca se elige sola (Engine:AutoSelect). Ver docs/IMPORT.md.",
        "sections": [sec_file],
    }
    if args.dry_run:
        print(report)
        return 0
    write_text_lf(out_dir / "guide.toml", guide_toml(meta, header))
    write_text_lf(out_dir / f"{sec_file}.toml", section_toml(sec, steps, header))
    rep = Path(args.report) if args.report else out_dir / "REPORT.md"
    write_text_lf(rep, report)
    if not args.no_names:
        n_new, files = write_fallback_names(imp.namer, REPO_ROOT / "data")
        print(f"nombres de respaldo (data/locale/esES y enUS): {n_new} nuevos o cambiados en {len(files)} archivos")
    print(f"{gid}: {len(steps)} pasos en {out_dir.relative_to(REPO_ROOT).as_posix() if out_dir.is_relative_to(REPO_ROOT) else out_dir}")
    print(f"ya en Senda: {len(merges)} · sin traducir: {len(imp.log['untranslated'])} · "
          f"condiciones perdidas: {len(imp.log['lost_when'])} · informe: {rep}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

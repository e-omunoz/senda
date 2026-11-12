#!/usr/bin/env python3
"""Rutas de la Horda (plan, fase 4): de las guías de Polestar a guías de Senda con el filtro de eficiencia.

    python tools/gen_horde.py --polestar RUTA [--foreverdb DIR] [--dry-run]

Qué hace, en orden (docs/ROUTE-HORDE.md lo explica con las cifras):

1. Importa con el importador de siempre (tools/import_polestar.py, clase Importer) las cinco salidas de raza de la
   Horda (orco y trol en Durotar, tauren en Mulgore, no-muerto en Claros de Tirisfal, Skyborne en la isla de
   Zephras) y la cadena común de la Horda (25 guías, 12-60). La cadena se importa sin raza ni clase: los pasos de
   una clase o raza llevan su `if`.
2. Completa lo que el importador deja manual:
   - «Entrena tu clase» -> un paso `train` por clase con los hechizos que vende el instructor entre el
     entrenamiento anterior y el nivel de ese punto de la ruta (data/knowledge/trainer/<clase>.json, datos de
     Forever) y el instructor más cercano de esa clase de los candidatos de Polestar.
   - Objetivos «hablar» de una misión -> `complete` con `obj`; «vendedor» y «morir» -> notas en español.
   - Coordenadas del marco de Era que Polestar no convierte (Mulgore, Tierras de la Peste del Este): el centro de
     las apariciones en forever-db del objetivo; si no hay objetivo con aparición, el paso `goto` sale y los
     demás se quedan sin `at`.
   - Consejos sin traducción de Polestar ([EN]): fuera del texto visible (quedan en `note`).
3. Filtro de eficiencia (tools/route_score.py, docs/EFFICIENCY.md) con bandas calculadas solo con las guías de la
   Horda (la Alianza no cambia) y los requisitos de `corrections/quests.json` de forever-db: `drop` sale,
   `optional` lleva `optional = true` y el motivo en `tip`, `keep` lleva `why` en su primer paso. En una sección
   compartida cuenta la decisión más favorable de las guías que la usan (keep > optional > drop). Dos pasadas,
   como en la Alianza (docs/ROUTE-CHANGES.md).
4. Escribe data/shared/h*.toml, data/guides/<raza>-horde/, data/scores/<guía>.json y la tabla antes/después.

Todo lo que sale es GPL-3 derivado de Polestar (ruta, coordenadas y notas; cada paso cita su origen en `sources`).
Adaptado de Polestar: guías forever/horde/** (forge/seed/guides), commit en `sources`.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import import_polestar as IP  # noqa: E402
from common import REPO_ROOT, setup_stdio, write_text_lf  # noqa: E402
from foreverdb import ForeverDB, resolve_foreverdb  # noqa: E402
from polestar.source import PolestarSource  # noqa: E402
from polestar.spanish import sentence  # noqa: E402
from routescore import model as M  # noqa: E402
from routescore.route import World, band_stats, decide_guide, score_guide  # noqa: E402

FACTION = "Horde"
CLASSES = ["WARRIOR", "PALADIN", "HUNTER", "ROGUE", "PRIEST", "SHAMAN", "MAGE", "WARLOCK", "DRUID"]
# Bit de raza (id de raza - 1) de las listas del instructor (data/knowledge/trainer/*.json); Skyborne no tiene.
RACE_BIT = {"Orc": 1, "Scourge": 4, "Tauren": 5, "Troll": 7}
HORDE_RACES = ["Orc", "Scourge", "Tauren", "Troll", "Skyborne"]

# Salidas de raza: carpeta -> (guía de Polestar, raza, nombre, sección, prefijo de paso, título de la sección)
STARTS: dict[str, tuple[str, str, str, str, str, str]] = {
    "orc-horde": ("forever/horde/orc/01-durotar", "Orc", "Orco", "01-durotar", "orc", "Durotar: el Valle de los Retos"),
    "troll-horde": ("forever/horde/troll/01-durotar", "Troll", "Trol", "01-durotar", "trl", "Durotar: el Valle de los Retos"),
    "tauren-horde": ("forever/horde/tauren/01-mulgore", "Tauren", "Tauren", "01-mulgore", "tau", "Mulgore: Campamento Narache"),
    "undead-horde": ("forever/horde/undead/01-tirisfal-glades", "Scourge", "No-muerto", "01-claros-de-tirisfal", "und",
                     "Claros de Tirisfal: Camposanto"),
    "skyborne-horde": ("forever/horde/skyborne/01-zephras-isle", "Skyborne", "Skyborne", "01-isla-de-zephras", "sky",
                       "Isla de Zephras"),
}

# Cadena común de la Horda, en el orden de `next` de Polestar: guía -> (id de sección compartida, título)
CHAIN: list[tuple[str, str, str]] = [
    ("forever/horde/03-silverpine-forest", "h12-argenteos", "Bosque de Argénteos"),
    ("forever/horde/02-the-barrens", "h14-los-baldios", "Los Baldíos"),
    ("forever/horde/05-stonetalon-mountains", "h21-vallefresno-argenteos", "Vallefresno y Bosque de Argénteos"),
    ("forever/horde/06-hillsbrad-foothills", "h22-trabalomas", "Laderas de Trabalomas"),
    ("forever/horde/04-the-barrens", "h24-baldios-espolon", "Los Baldíos y Sierra Espolón"),
    ("forever/horde/07-ashenvale", "h26-vallefresno-mil-agujas", "Vallefresno y Las Mil Agujas"),
    ("forever/horde/30-40/01-hillsbrad-foothills", "h29-trabalomas-arathi", "Laderas de Trabalomas y Tierras Altas de Arathi"),
    ("forever/horde/30-40/02-thousand-needles", "h32-mil-agujas-desolace", "Las Mil Agujas y Desolace"),
    ("forever/horde/30-40/03-stranglethorn-vale", "h34-tuercespina", "Vega de Tuercespina"),
    ("forever/horde/30-40/04-dustwallow-marsh", "h36-revolcafango-desolace", "Marjal Revolcafango y Desolace"),
    ("forever/horde/30-40/05-arathi-highlands", "h38-alterac-arathi", "Montañas de Alterac y Tierras Altas de Arathi"),
    ("forever/horde/30-40/06-badlands", "h39-tierras-inhospitas", "Tierras Inhóspitas"),
    ("forever/horde/40-50/01-stranglethorn-vale", "h40-tuercespina-penas", "Vega de Tuercespina y Pantano de las Penas"),
    ("forever/horde/40-50/02-feralas", "h43-feralas-tanaris", "Feralas y Tanaris"),
    ("forever/horde/40-50/03-feralas", "h45-feralas-revolcafango", "Feralas, Marjal Revolcafango y Pantano de las Penas"),
    ("forever/horde/40-50/04-tanaris", "h46-tanaris-garganta", "Tanaris y La Garganta de Fuego"),
    ("forever/horde/40-50/05-the-hinterlands", "h48-interior-devastadas", "Tierras del Interior y Las Tierras Devastadas"),
    ("forever/horde/40-50/06-azshara", "h50-azshara-feralas", "Azshara, Feralas y Vega de Tuercespina"),
    ("forever/horde/50-60/01-un-goro-crater", "h51-ungoro-estepas", "Cráter de Un'Goro, Las Estepas Ardientes y Tierras de la Peste del Oeste"),
    ("forever/horde/50-60/02-felwood", "h53-frondavil-peste-oeste", "Frondavil y Tierras de la Peste del Oeste"),
    ("forever/horde/50-60/03-winterspring", "h55-cuna-del-invierno", "Cuna del Invierno"),
    ("forever/horde/50-60/04-azshara", "h56-azshara-baldios", "Azshara y Los Baldíos"),
    ("forever/horde/50-60/05-eastern-plaguelands", "h56-peste-del-este", "Tierras de la Peste del Este, Cuna del Invierno y Tanaris"),
    ("forever/horde/50-60/06-silithus", "h57-silithus-pestes", "Silithus y las Tierras de la Peste"),
    ("forever/horde/50-60/07-felwood", "h59-frondavil-claro", "Frondavil, Claro de la Luna y Cuna del Invierno"),
]

# Mapas cuyo marco de Era no coincide con el de Forever y para los que no hay transformación (docs/FOREVER.md).
ERA_UNCONVERTED = {1412, 1423, 1433}

KEY_ORDER = ["id", "do", "quest", "quests", "obj", "npc", "item", "count", "spells", "level", "prof", "skill",
             "node", "zone", "at", "wps", "radius", "if", "optional", "escort", "chain", "reqlevel", "text", "tip",
             "why", "status", "sources", "note"]

CLASS_CODE = {"WARRIOR": "wr", "PALADIN": "pa", "HUNTER": "hu", "ROGUE": "ro", "PRIEST": "pr", "SHAMAN": "sh",
              "MAGE": "mg", "WARLOCK": "wl", "DRUID": "dr"}
CLASS_ES = {"WARRIOR": "guerrero", "PALADIN": "paladín", "HUNTER": "cazador", "ROGUE": "pícaro",
            "PRIEST": "sacerdote", "SHAMAN": "chamán", "MAGE": "mago", "WARLOCK": "brujo", "DRUID": "druida"}

HEADER = [
    "GENERADO por tools/gen_horde.py desde Polestar (GPL-3), {src}",
    "commit {commit}. Adaptado de Polestar: ruta, coordenadas y notas. Textos en español con fichas ({{quest:N}},",
    "{{npc:N}}...); entrenamiento de clase con data/knowledge/trainer; filtro de eficiencia de tools/route_score.py",
    "(misiones quitadas, opcionales y `why`). No editar a mano: vuelve a generar. Ver docs/ROUTE-HORDE.md.",
]


# ---------------------------------------------------------------------------
# Datos auxiliares
# ---------------------------------------------------------------------------

class Trainer:
    """Listas del instructor de Forever por clase (data/knowledge/trainer/<clase>.json)."""

    def __init__(self, root: Path):
        self.spells: dict[str, list[dict]] = {}
        for c in CLASSES:
            p = root / "data" / "knowledge" / "trainer" / f"{c.lower()}.json"
            data = json.loads(p.read_text(encoding="utf-8"))
            rows = data["spells"]
            sold = {r["spell"]: r for r in rows}

            def root_sold(r: dict) -> bool:
                # Un rango cuyo primer rango no vende el instructor viene de un talento o de una misión: el
                # instructor solo lo enseña a quien lo tiene, así que no se pide.
                seen = set()
                p = r.get("prev") or 0
                while p:
                    if p not in sold or p in seen:
                        return False
                    seen.add(p)
                    p = sold[p].get("prev") or 0
                return True
            self.spells[c] = [r for r in rows if root_sold(r)]

    def between(self, cls: str, lo: int, hi: int, race: str | None) -> tuple[list[dict], dict[str, list[dict]]]:
        """Hechizos de nivel lo < n <= hi: (los de todas las razas, {raza: los solo de esa raza})."""
        common, by_race = [], defaultdict(list)
        for r in self.spells.get(cls, []):
            if not (lo < r["level"] <= hi):
                continue
            mask = int(r.get("racemask") or 0)
            if not mask:
                common.append(r)
                continue
            for rc, bit in RACE_BIT.items():
                if mask & (1 << bit) and (race is None or race == rc):
                    by_race[rc].append(r)
        return common, dict(by_race)


def taxi_places(src: PolestarSource) -> dict[str, str]:
    """Nombre inglés de un nodo de vuelo (data/travel/taxi_nodes.json) -> esES (nombres de Polestar_esES)."""
    out: dict[str, str] = {}
    p = REPO_ROOT / "data" / "travel" / "taxi_nodes.json"
    for r in json.loads(p.read_text(encoding="utf-8")).get("rows", []):
        es = src.name_es("taxi", r["id"])
        if not es:
            continue
        en = r["name"].split(",")[0].strip().lower()
        out.setdefault(en, es.split(",")[0].strip())
        out.setdefault(re.sub(r"^the ", "", en), es.split(",")[0].strip())
    return out


def load_corrections(fdb_root: Path) -> dict[int, dict]:
    p = fdb_root / "corrections" / "quests.json"
    if not p.exists():
        return {}
    return {int(k): v for k, v in json.loads(p.read_text(encoding="utf-8")).items() if k.isdigit()}


# ---------------------------------------------------------------------------
# Importador
# ---------------------------------------------------------------------------

# Destinos de `goto` que Polestar escribe en inglés sin traducción esES: patrón -> plantilla en español ({0} es
# el lugar, que se pasa a ficha o a nombre esES). Lo que no encaja queda «Ve al punto marcado.» (inglés en `note`).
GOTO_PATTERNS: list[tuple[str, str]] = [
    (r"^(?:the )?(.+?) flight master$", "Ve al maestro de vuelo de {0}"),
    (r"^maestro de vuelo de (.+)$", "Ve al maestro de vuelo de {0}"),
    (r"^(?:the )?zeppelin to (.+)$", "Ve al zepelín a {0}"),
    (r"^zepel[ií]n a (.+)$", "Ve al zepelín a {0}"),
    (r"^(?:the )?boat to (.+)$", "Ve al barco a {0}"),
    (r"^the middle of (.+)$", "Ve al centro de {0}"),
    (r"^into (.+)$", "Entra en {0}"),
    (r"^(.+)'s camp$", "Ve al campamento de {0}"),
    (r"^the road (north|south|east|west) to (.+)$", "Sigue el camino del {d} hacia {1}"),
    (r"^the road (north|south|east|west) through (.+)$", "Sigue el camino del {d} por {1}"),
    (r"^(.+)$", "Ve a {0}"),
]
FIXED_GOTO = {
    "the zeppelin towers": "Ve a las torres del zepelín",
    "the zeppelin tower": "Ve a la torre del zepelín",
    "the top of the great lift": "Sube a lo alto del Gran Elevador",
}
DIR_ES = {"north": "norte", "south": "sur", "east": "este", "west": "oeste"}

# Notas de Polestar sin traducción esES (Polestar_esES no las trae): un trozo del inglés -> texto de Senda.
EN_NOTES: list[tuple[str, str]] = [
    ("donations are handed in later in the route",
     "Las dos donaciones de {item:14047} se entregan más adelante en la ruta: guarda sesenta {item:14047} para cada una si las vas a hacer."),
    ("next errand, Into the Maw of Madness",
     "El siguiente encargo de Mar'alith lleva a Colmen'Regal, lleno de élites: sáltalo."),
    ("Poison chain unfinished?",
     "¿Tienes a medias la cadena de venenos? Sigue por la etapa en la que estés (lo entregado no se repite), busca grupo para Gallywix, termina lo de Hinott y vuelve a esta ruta."),
    ("Riding and Galestriders:",
     "Equitación y monturas de Zephras: {npc:265756}, en los establos de Valanaar, en la isla de Zephras."),
    ("Run Gnomeregan with a group",
     "Haz Gnomeregan en grupo cuando te venga bien: {npc:7800}, al final, suelta la combinación de su caja fuerte; ábrela tras el pilar de bombas del norte para conseguir {item:9153}."),
    ("The magus offers a dungeon errand next",
     "El magus ofrece después un encargo de mazmorra: déjalo."),
    ("crosses the Thandol Span",
     "La ruta sigue por el Paso de Thandol hacia {map:1437} y luego a {map:1418}."),
    ("flies from Kargath to Grom'gol",
     "La ruta sigue en vuelo de Kargath a Grom'gol."),
    ("flies on from here to the Crossroads",
     "La ruta sigue en vuelo desde aquí a El Cruce y {map:1454}."),
    ("goes north-east across the",
     "La ruta sigue al nordeste por {map:1413} hasta el Baluarte de Mor'shan y {map:1440}."),
    ("from the tower on the west side of the camp",
     "La ruta sigue en el zepelín a {map:1454}, desde la torre del lado oeste del campamento."),
    ("zeppelin from the tower outside the main gate",
     "La ruta sigue en el zepelín a {map:1458}, desde la torre de fuera de la puerta principal."),
    ("walks south from Brill",
     "La ruta sigue a pie hacia el sur desde Rémol, hasta {map:1421}."),
    ("next task needs Fozruk",
     "La siguiente tarea de la piedra pide a Fozruk, élite de nivel 42 que ronda al oeste de Sentencia: déjala."),
    ("Portals of the Legion",
     "Los portales de la Legión de {npc:11624} y las demás misiones 38-40 de {map:1443} esperan a la segunda visita, al 38: la ruta vuela a {map:1454} y coge el zepelín a {map:1434}."),
    ("hunt targets (Ursangous",
     "Las presas de {npc:12696} (Ursangous, Shadumbra y Garrafilada) son para la próxima visita a {map:1440}, al 26."),
    ("(level 36): leave it for the 38-39 visit",
     "{npc:2229} ofrece ahora la misión de {npc:2316} (nivel 36): déjala para la visita del 38-39."),
    ("Guile of the Raptor",
     "Las misiones de raptores de {npc:2706}, «{quest:677}» de {npc:2771} y el reabastecimiento del doctor esperan a la visita del 38-39."),
    ("next study wants bracers",
     "El siguiente estudio de {npc:2921} pide brazales de los elementales de roca superiores (42-44) de las cañadas del suroeste, muy por encima de tu nivel: déjalo."),
    ("is a level 55 quest: leave it",
     "La misión de {npc:950} que da {npc:7643} es de nivel 55: déjala."),
    ("is for level 23 or more: the tower's drones",
     "«{quest:2478}» es para nivel 23 o más: los zánganos de la torre son de nivel 25 y Gallywix es élite de nivel 23. Hazla cuando puedas, en grupo."),
    ("return to Marshal's Refuge: keep it",
     "«{quest:3941}» se entrega a {npc:9117}, en la cueva de aquí, al volver al Refugio de Marshal: guárdala."),
    ("on a later trip: keep it",
     "«{quest:5086}» se hace en {map:1448}, en un viaje posterior: guárdala."),
]
# Traducciones esES de Polestar que nombran sus guías de clase (Senda no las tiene): se reescriben.
ES_FIXES: list[tuple[str, str]] = [
    (r" La guía de clase de guerrero «\{quest:1838\}» la cubre\.", ""),
    (r"^(\{npc:\d+\}) también inicia Elemental Aid \((\{area:\d+\})\), la cadena de 33-40 hasta las armas de la "
     r"Tempestad: forever/class/shaman/call-of-air-horde\.$",
     r"\1 también inicia la cadena de chamán de 33-40 en \2, hasta las armas de la Tempestad."),
]


def polish(st: dict) -> None:
    for k in ("text", "tip"):
        v = st.get(k)
        if not isinstance(v, str):
            continue
        for pat, rep in ES_FIXES:
            v = re.sub(pat, rep, v)
        st[k] = v


_ONLY_TOKENS = re.compile(r"^(?:[«»\s,.']|\{[a-z]+:\d+\})+$")


class HordeImporter(IP.Importer):
    """El importador de Polestar con lo que la Horda necesita (ver el docstring del módulo)."""

    def __init__(self, src, guide_id, prefix, race, db: ForeverDB, stats: dict, places: dict[str, str]):
        super().__init__(src, guide_id, prefix, race, None)
        self.db = db
        self.stats = stats
        self.places = places  # nombre inglés (minúsculas) -> esES o ficha
        for k, v in (self.guide.get("names") or {}).items():
            if k.startswith("area:") and isinstance(v, str):
                self.places.setdefault(v.lower(), "{area:%s}" % k[5:])
                self.places.setdefault(re.sub(r"^the ", "", v.lower()), "{area:%s}" % k[5:])

    # --- lugares en español
    def place_es(self, en: str) -> str | None:
        """Un lugar escrito por Polestar (inglés o fichas) en español o como ficha; None si no se sabe."""
        en = en.strip().rstrip(".")
        if _ONLY_TOKENS.match(en):
            return en
        key = en.lower()
        for k in (key, re.sub(r"^the ", "", key)):
            if k in self.places:
                v = self.places[k]
                if v.startswith("{area:"):
                    aid = int(v[6:-1])
                    return self.namer.token("area", aid, self.guide.get("names", {}).get(f"area:{aid}"))
                return v
        return None

    def place(self, g: dict) -> str:
        if g.get("node"):
            es = self.src.name_es("taxi", g["node"])
            if es:
                return es.split(",")[0]
        if g.get("area"):
            return self.namer.token("area", g["area"], g.get("location"))
        if g.get("location"):
            es = self.place_es(g["location"])
            if es:
                return es
            self.stats["place_en"] += 1
            return g["location"]
        return "el destino"

    def goto_text(self, g: dict) -> tuple[str, str | None]:
        """(texto en español, inglés original si no se pudo traducir)."""
        if g.get("text"):
            dest, ok = self.tr(g["text"])
            dest = (dest or "").strip().rstrip(".")
            plain = IP._TOKEN_RE.sub("", dest)
            if not re.search(r"[A-Za-z]{2,}", plain):
                return sentence(f"Ve a {dest}"), None
            if dest.lower() in FIXED_GOTO:
                return sentence(FIXED_GOTO[dest.lower()]), None
            if ok and not re.match(r"^(maestro de vuelo|zepel)", dest, re.I):
                low = dest[0].lower() + dest[1:]
                return sentence(f"Ve {low}" if low.startswith(("al ", "a la ", "a los ", "a las ")) else f"Ve a {low}"), None
            for pat, fmt in GOTO_PATTERNS:
                m = re.match(pat, dest, re.I)
                if not m:
                    continue
                parts = list(m.groups())
                if "{d}" in fmt:
                    there = self.place_es(parts[1])
                    if there:
                        return sentence(fmt.replace("{d}", DIR_ES[parts[0].lower()]).replace("{1}", there)), None
                    continue
                conv = [self.place_es(x) for x in parts]
                if all(conv):
                    return sentence(fmt.format(*conv)), None
            return "Ve al punto marcado.", self.namer.unrender(dest)
        if g.get("area"):
            return sentence(f"Ve a {self.namer.token('area', g['area'], g.get('location'))}"), None
        return "Ve al punto marcado.", None

    def _era_fix(self, g: dict, st: dict) -> dict | None:
        """Coordenadas de Era en un mapa sin transformación: centro de las apariciones del objetivo o nada."""
        if g.get("f") != "e" or g.get("map") not in ERA_UNCONVERTED or "at" not in st:
            return st
        m = int(g["map"])
        ids: list[tuple[str, int]] = []
        for n in g.get("fromNpcs") or []:
            if isinstance(n, dict) and n.get("npc"):
                ids.append(("npc", int(n["npc"])))
        if g.get("fromKind") == "object" and g.get("fromId"):
            ids.append(("object", int(g["fromId"])))
        if g.get("object"):
            ids.append(("object", int(g["object"])))
        if g.get("npc"):
            ids.append(("npc", int(g["npc"])))
        pts = []
        for kind, i in ids:
            ent = self.db.npc(i) if kind == "npc" else self.db.object(i)
            for s in (ent or {}).get("spawns") or []:
                if s[0] == m and s[1] is not None:
                    pts.append((s[1], s[2]))
        st.pop("wps", None)
        if pts:
            st["at"] = [m, round(statistics.median(p[0] for p in pts), 2), round(statistics.median(p[1] for p in pts), 2)]
            st.setdefault("_notes", []).append("coordenadas de Era sin transformación: centro de las apariciones en forever-db")
            self.stats["era_fixed"] += 1
            return st
        if st.get("do") == "goto":
            self.stats["era_goto_dropped"] += 1
            return None
        st.pop("at", None)
        st.setdefault("_notes", []).append("coordenadas de Era sin transformación: sin punto (ni aparición en forever-db)")
        self.stats["era_no_point"] += 1
        return st

    def goal_step(self, si: int, gi: int, g: dict) -> dict | None:
        t = g.get("t")
        if t in ("money", "rep", "skill"):
            self.stats[f"skip_{t}"] += 1
            return None
        if t == "task":
            txt, ok = self.tr(g.get("text"))
            if not ok or not txt:
                self.stats["skip_task_en"] += 1
                return None
            st = {"do": "note", "text": sentence(txt), "_tips": [], "_notes": []}
            if g.get("optional"):
                st["optional"] = True
            return st
        if t == "talk" and g.get("quest"):
            st = {"do": "complete", "quest": g["quest"]}
            if g.get("oi"):
                st["obj"] = g["oi"]
            at = IP.point(g, self.log)
            if at:
                st["at"] = at
            if g.get("npc"):
                st["npc"] = g["npc"]
            who = self.npc_token(g) or "el PNJ"
            st["text"] = f"Habla con {who} para {self.namer.quest(g['quest'], g.get('title'))}."
            st["_tips"], st["_notes"] = [], []
            self.stats["talk_objective"] += 1
            return self._era_fix(g, st)
        if t == "talk":
            st = {"do": "note", "text": f"Habla con {self.npc_token(g) or 'el PNJ'}.", "_tips": [], "_notes": []}
            at = IP.point(g, self.log)
            if at:
                st["at"] = at
            if g.get("npc"):
                st["npc"] = g["npc"]
            return self._era_fix(g, st)
        if t == "vendor":
            st = {"do": "note", "text": f"Vende lo que no sirve y repara con {self.npc_token(g) or 'el vendedor'}.",
                  "_tips": [], "_notes": [], "optional": True}
            at = IP.point(g, self.log)
            if at:
                st["at"] = at
            if g.get("npc"):
                st["npc"] = g["npc"]
            self.stats["vendor"] += 1
            return self._era_fix(g, st)
        if t == "die":
            st = {"do": "note", "_tips": [], "_notes": [], "optional": True,
                  "text": "Truco de la muerte: déjate matar aquí y reaparece en el cementerio de destino; ahorras el camino."}
            at = IP.point(g, self.log)
            if at:
                st["at"] = at
            self.stats["die"] += 1
            return self._era_fix(g, st)
        if t == "train" and g.get("class"):
            cands = [c for c in g.get("candidates") or [] if isinstance(c, dict) and c.get("faction") in (None, "H")]
            st = {"do": "note", "text": "Entrena tu clase.", "_tips": [], "_notes": [],
                  "_train": {"cands": cands, "zone": g.get("zone"), "last_at": self.last_at}}
            return st
        st = super().goal_step(si, gi, g)
        if st is None:
            return None
        if t == "note" and str(st.get("text", "")).startswith("[EN] "):
            en = st["text"][5:]
            es = next((v for k, v in EN_NOTES if k in en), None)
            if es is None:
                self.stats["note_en_dropped"] += 1
                return None
            st["text"] = es
            st.setdefault("_notes", []).append(f"nota de Polestar traducida por Senda: {self.namer.unrender(en)}")
            self.stats["note_en_translated"] += 1
        if t == "goto":
            txt, en = self.goto_text(g)
            st["text"] = txt
            if en:
                st.setdefault("_notes", []).append(f"destino de Polestar sin traducir: {en}")
                self.stats["goto_generic"] += 1
        # Consejos sin traducción: fuera del texto visible.
        tips = st.get("_tips") or []
        en = [x for x in tips if x.startswith("[EN] ")]
        if en:
            st["_tips"] = [x for x in tips if not x.startswith("[EN] ")]
            st.setdefault("_notes", []).append("consejo de Polestar sin traducir: " + " ".join(x[5:] for x in en))
            self.stats["tip_en_hidden"] += len(en)
        return self._era_fix(g, st)

    def finish(self, st: dict) -> None:
        # consejos del paso de Polestar sin traducción: fuera del texto visible (quedan en `note`)
        tips = st.get("_tips") or []
        en = [x for x in tips if isinstance(x, str) and x.startswith("[EN] ")]
        if en:
            st["_tips"] = [x for x in tips if x not in en]
            st.setdefault("_notes", []).append("consejo de Polestar sin traducir: " + " ".join(x[5:] for x in en))
            self.stats["tip_en_hidden"] += len(en)
        train = st.pop("_train", None)
        super().finish(st)
        if train is not None:
            self.steps[-1]["_train"] = train


# ---------------------------------------------------------------------------
# Entrenamiento de clase
# ---------------------------------------------------------------------------

def level_at(sec_levels: tuple[int, int], i: int, n: int, floor: int) -> int:
    lo, hi = sec_levels
    return max(floor, int(lo + (hi - lo) * i / max(n - 1, 1)))


def nearest_trainer(cands: list[dict], cls: str, zone: int | None, last_at: list | None) -> dict | None:
    cs = [c for c in cands if not c.get("classes") or cls in c["classes"]]
    if not cs:
        return None
    if zone:
        same = [c for c in cs if c.get("map") == zone]
        cs = same or cs
    if last_at:
        def d(c):
            if c.get("map") != last_at[0]:
                return 1e9
            return (c["x"] - last_at[1]) ** 2 + (c["y"] - last_at[2]) ** 2
        cs = sorted(cs, key=d)
    return cs[0]


def expand_training(steps: list[dict], sec_levels: tuple[int, int], prev: dict[str, int], trainer: Trainer,
                    race: str | None, namer, stats: dict) -> list[dict]:
    """Sustituye cada «entrena tu clase» por un paso `train` por clase (y raza, si hay hechizos de raza)."""
    out: list[dict] = []
    floor = sec_levels[0]
    n = len(steps)
    for i, st in enumerate(steps):
        if st.get("do") == "level" and st.get("level"):
            floor = max(floor, int(st["level"]))
        train = st.pop("_train", None)
        if train is None:
            out.append(st)
            continue
        lvl = level_at(sec_levels, i, n, floor)
        allowed = (st.get("if") or {}).get("class") or CLASSES
        made = 0
        for cls in CLASSES:
            if cls not in allowed:
                continue
            lo = prev.get(cls, 0)
            if lvl <= lo:
                continue
            common, by_race = trainer.between(cls, lo, lvl, race)
            groups = [(None, common)] + sorted(by_race.items())
            cand = nearest_trainer(train["cands"], cls, train.get("zone"), train.get("last_at"))
            if cand is None or not (common or by_race):
                continue
            prev[cls] = lvl
            for rc, rows in groups:
                if not rows:
                    continue
                spells = sorted({r["spell"] for r in rows})
                req = max(r["level"] for r in rows)
                tok = namer.token("npc", cand["npc"], cand.get("npcName"))
                new = {k: v for k, v in st.items() if k not in ("do", "text", "tip", "npc", "at", "if", "note")}
                new["id"] = st["id"] + f"-{CLASS_CODE[cls]}" + (f"-{rc.lower()[:3]}" if rc else "")
                new["do"] = "train"
                new["spells"] = spells
                new["npc"] = cand["npc"]
                at = IP.point(cand, {"frames_converted": 0, "frames_unconverted": set()})
                if at:
                    new["at"] = at
                f = dict(st.get("if") or {})
                f["class"] = [cls]
                if rc:
                    f["race"] = [rc]
                new["if"] = f
                new["reqlevel"] = req
                new["text"] = f"Entrena con {tok}, el instructor de {CLASS_ES[cls]}."
                shown = [f"{{spell:{s}}}" for s in sorted({r['spell'] for r in rows if not r.get('prev')})][:3]
                tip = f"{len(spells)} hechizo{'s' if len(spells) != 1 else ''} hasta el nivel {req}"
                if shown:
                    tip += ": nuevos " + ", ".join(shown) + (" y más" if len(shown) == 3 else "")
                new["tip"] = sentence(tip)
                new["note"] = (st.get("note") or "") + f" · entrenamiento de clase: data/knowledge/trainer/{cls.lower()}.json, niveles {lo + 1}-{lvl}"
                srcs = list(st.get("sources") or []) + [f"trainer:{cls.lower()}"]
                new["sources"] = srcs
                out.append(new)
                made += 1
        stats["train_points"] += 1
        stats["train_steps"] += made
        if not made:
            stats["train_points_empty"] += 1
    return out


# ---------------------------------------------------------------------------
# TOML
# ---------------------------------------------------------------------------

def section_toml(sec: dict, steps: list[dict], header: list[str], extra: list[str] | None = None) -> str:
    out = [f"# {h}" if h else "#" for h in header]
    for k in ("id", "title", "levels", "map", "summary", "if"):
        if k in sec:
            out.append(IP.toml_kv(k, sec[k]))
    for line in extra or []:
        out.append(line)
    for st in steps:
        out.append("")
        out.append("[[step]]")
        for k in KEY_ORDER:
            if k in st and st[k] is not None:
                out.append(IP.toml_kv(k, st[k]))
    return "\n".join(out) + "\n"


def guide_toml(meta: dict, header: list[str]) -> str:
    out = [f"# {h}" if h else "#" for h in header]
    for k in ("id", "title", "summary", "faction", "races", "classes", "levels", "status", "sources", "note"):
        if k in meta:
            out.append(IP.toml_kv(k, meta[k]))
    out.append("sections = [")
    for s in meta["sections"]:
        out.append(f"  {IP.toml_str(s)},")
    out.append("]")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Filtro de eficiencia
# ---------------------------------------------------------------------------

RANK = {"drop": 0, "optional": 1, "keep": 2}


def apply_corrections(res: dict, corr: dict[int, dict]) -> int:
    """Requisitos de corrections/quests.json (forever-db) sobre los que puntuó route_score (que no los lee)."""
    n = 0
    for qid, x in res["quests"].items():
        c = (corr.get(int(qid)) or {}).get("set") or {}
        if "pre" in c or "preAll" in c:
            x["prereq_all"] = sorted(set(int(p) for p in (c.get("pre") or []) + (c.get("preAll") or [])))
            n += 1
        if "preAny" in c:
            x["prereq_any"] = sorted(set(int(p) for p in c["preAny"]))
            n += 1
    return n


def score_all(guide_ids: list[str], world: World, corr: dict) -> dict[str, dict]:
    results = {}
    for gid in guide_ids:
        res = score_guide(REPO_ROOT / "data" / "guides" / gid, REPO_ROOT / "data" / "shared", world)
        apply_corrections(res, corr)
        results[gid] = res
    bands = band_stats(list(results.values()))  # solo la Horda: las bandas de la Alianza no cambian
    for res in results.values():
        decide_guide(res, bands)
    for res in results.values():
        res["_bands"] = bands
    return results


def totals_of(res: dict, skip_optional: bool = False) -> dict:
    qs = [x for x in res["quests"].values() if x["scored"]]
    if skip_optional:
        qs = [x for x in qs if not x.get("guide_optional")]
    over = sum(v for k, v in res["totals"].items() if k in ("hearth", "overhead_travel", "flights"))
    return {"quests": len(qs), "minutes": sum(x["est_minutes"] for x in qs) + over / 60.0,
            "xp": sum(x["xp"] for x in qs)}


def optional_tip(x: dict) -> str:
    base = f"+{M.fmt_int(x['xp'])} XP · {M.fmt_minutes(x['est_minutes'])}: por debajo de la media del tramo"
    if x["reason"] == "reward":
        return base + "; hazla si te interesa la recompensa."
    if x["reason"] == "grind":
        return base + ", aunque rinde más que matar bichos."
    return base + "."


# ---------------------------------------------------------------------------
# Programa
# ---------------------------------------------------------------------------

class Build:
    def __init__(self, polestar: Path, fdb: Path):
        self.src = PolestarSource(polestar)
        self.commit = self.src.commit()
        self.fdb_root = resolve_foreverdb(str(fdb) if fdb else None)
        self.db = ForeverDB.open(str(self.fdb_root))
        self.trainer = Trainer(REPO_ROOT)
        self.corr = load_corrections(self.fdb_root)
        self.stats: dict[str, int] = defaultdict(int)
        self.namers = []
        self.sections: dict[str, dict] = {}     # id -> {"meta":..., "steps": [...], "file": Path, "src": guide}
        self.guides: dict[str, dict] = {}       # carpeta -> meta
        self.decisions_log: list[dict] = []
        self.places = taxi_places(self.src)

    # --- importar
    def import_guide(self, gid: str, prefix: str, race: str | None) -> tuple[dict, list[dict]]:
        imp = HordeImporter(self.src, gid, prefix, race, self.db, self.stats, self.places)
        steps = imp.run()
        self.namers.append(imp.namer)
        g = imp.guide
        lo, hi = int(g.get("minLevel") or 1), int(g.get("maxLevel") or 60)
        return {"levels": [lo, hi], "map": g.get("zone"), "imp": imp}, steps

    def run_import(self) -> None:
        start_prev: dict[str, dict[str, int]] = {}
        for folder, (gid, race, race_es, sec_file, prefix, title) in STARTS.items():
            info, steps = self.import_guide(gid, prefix, race)
            prev: dict[str, int] = {}
            steps = expand_training(steps, tuple(info["levels"]), prev, self.trainer, race, info["imp"].namer,
                                    self.stats)
            start_prev[folder] = prev
            sid = f"{prefix}-{sec_file.split('-', 1)[1]}"
            meta = {"id": sid, "title": title, "levels": info["levels"], "map": info["map"],
                    "summary": f"Salida de {race_es.lower() if race != 'Skyborne' else 'Skyborne'} ({info['levels'][0]}-{info['levels'][1]}): "
                               "misiones de la zona de inicio, entrenamiento de clase y viaje al Bosque de Argénteos."}
            self.sections[f"{folder}/{sec_file}"] = {"meta": meta, "steps": steps, "src": gid,
                                                     "file": REPO_ROOT / "data" / "guides" / folder / f"{sec_file}.toml"}
        # La cadena común: el último entrenamiento de cada clase es el más bajo de las cinco salidas.
        prev = {}
        for cls in CLASSES:
            vals = [p.get(cls, 0) for p in start_prev.values()]
            prev[cls] = min(vals) if vals else 0
        for gid, sid, title in CHAIN:
            info, steps = self.import_guide(gid, sid, None)
            steps = expand_training(steps, tuple(info["levels"]), prev, self.trainer, None, info["imp"].namer,
                                    self.stats)
            meta = {"id": sid, "title": title, "levels": info["levels"], "map": info["map"],
                    "summary": f"Ruta común de la Horda, {info['levels'][0]}-{info['levels'][1]}: {title}.",
                    "if": {"faction": FACTION}}
            self.sections[f"shared:{sid}"] = {"meta": meta, "steps": steps, "src": gid,
                                              "file": REPO_ROOT / "data" / "shared" / f"{sid}.toml"}
        for folder, (gid, race, race_es, sec_file, prefix, title) in STARTS.items():
            self.guides[folder] = {
                "id": folder,
                "title": f"{race_es} 1-60 (Horda)",
                "summary": "Ruta de la Horda para cualquier clase: salida de raza y ruta común 12-60 "
                           "(Polestar filtrada con el filtro de eficiencia de Senda).",
                "faction": FACTION,
                "races": [race],
                "levels": [1, 60],
                "status": "unverified",
                "sources": [f"polestar:{self.commit}/{gid}", f"polestar:{self.commit}/forever/horde"],
                "sections": [sec_file] + [f"shared:{sid}" for _, sid, _ in CHAIN],
            }

    # --- escribir
    def write(self, final: bool = False) -> list[Path]:
        """final=False: guide.toml sin `classes` (route_score puntúa la ruta sin los pasos de clase)."""
        written = []
        for key, sec in self.sections.items():
            hdr = [h.format(src=sec["src"], commit=self.commit) for h in HEADER]
            steps = [{k: v for k, v in st.items() if not k.startswith("_")} for st in sec["steps"]]
            for st in steps:
                polish(st)
            write_text_lf(sec["file"], section_toml(sec["meta"], steps, hdr))
            written.append(sec["file"])
        for folder, meta in self.guides.items():
            hdr = [h.format(src="forever/horde/**", commit=self.commit) for h in HEADER]
            p = REPO_ROOT / "data" / "guides" / folder / "guide.toml"
            m = dict(meta)
            if final:
                m["classes"] = list(CLASSES)
            write_text_lf(p, guide_toml(m, hdr))
            written.append(p)
        return written

    # --- filtro
    def sections_of(self, folder: str) -> list[str]:
        sec_file = STARTS[folder][3]
        return [f"{folder}/{sec_file}"] + [f"shared:{sid}" for _, sid, _ in CHAIN]

    def filter_pass(self, world: World, tag: str) -> dict[str, dict]:
        results = score_all(list(self.guides), world, self.corr)
        # decisión por paso: la más favorable de las guías que lo ven
        best: dict[str, tuple[str, dict]] = {}
        for folder, res in results.items():
            for qid, x in res["quests"].items():
                for sid in x["steps"]:
                    cur = best.get(sid)
                    if cur is None or RANK[x["decision"]] > RANK[cur[0]]:
                        best[sid] = (x["decision"], x | {"_guide": folder})
        # misión quitada en todas las guías que la puntúan: también salen sus pasos de una clase (no puntuados)
        qbest: dict[int, tuple[str, dict]] = {}
        for res in results.values():
            for qid, x in res["quests"].items():
                cur = qbest.get(int(qid))
                if cur is None or RANK[x["decision"]] > RANK[cur[0]]:
                    qbest[int(qid)] = (x["decision"], x)
        dropped, optional = 0, 0
        for key, sec in self.sections.items():
            keep_steps = []
            for st in sec["steps"]:
                d = best.get(st["id"])
                if d is None and st.get("quest") and st.get("do") in ("accept", "complete", "turnin") \
                        and qbest.get(int(st["quest"]), ("keep",))[0] == "drop":
                    d = qbest[int(st["quest"])]
                if d is None:
                    keep_steps.append(st)
                    continue
                dec, x = d
                if dec == "drop":
                    self.decisions_log.append({"pass": tag, "step": st["id"], "quest": x["quest"], "title": x.get("title"),
                                               "section": sec["meta"]["id"], "decision": "drop", "reason": x["reason"],
                                               "why": x.get("why_plain"), "xp": x["xp"], "minutes": x["est_minutes"]})
                    dropped += 1
                    continue
                if dec == "optional" and not st.get("optional"):
                    st["optional"] = True
                    st["_opt_tip"] = optional_tip(x)
                    optional += 1
                keep_steps.append(st)
            sec["steps"] = keep_steps
        self.stats[f"dropped_steps_{tag}"] = dropped
        self.stats[f"optional_steps_{tag}"] = optional
        return results

    def finish_texts(self, results: dict[str, dict]) -> None:
        """`why` en el primer paso de cada misión que se queda; motivo de las opcionales en el primero."""
        best: dict[int, tuple[str, dict]] = {}
        for folder in self.guides:  # orden fijo: la primera guía que la ve da la línea
            for qid, x in results[folder]["quests"].items():
                cur = best.get(int(qid))
                if cur is None or RANK[x["decision"]] > RANK[cur[0]]:
                    best[int(qid)] = (x["decision"], x)
        seen: set[tuple[str, int]] = set()
        for key, sec in self.sections.items():
            scope = "shared" if key.startswith("shared:") else key
            for st in sec["steps"]:
                q = st.get("quest")
                tip_opt = st.pop("_opt_tip", None)
                if not q or st.get("do") not in ("accept", "complete", "turnin"):
                    continue
                k = (scope, int(q))
                if k in seen:
                    continue
                seen.add(k)
                dec = best.get(int(q))
                if not dec:
                    continue
                dec_name, x = dec
                if dec_name == "optional" or st.get("optional"):
                    if tip_opt:
                        st["tip"] = (st.get("tip") + " " if st.get("tip") else "") + tip_opt
                    continue
                if dec_name == "keep" and x.get("why") and x["reason"] != "not_turned_in" and x["xp"] > 0:
                    st["why"] = x["why"]

    def write_scores(self, results: dict[str, dict], info: dict) -> None:
        import route_score as RS
        out_dir = REPO_ROOT / "data" / "scores"
        for gid, res in results.items():
            out = RS.public(res, res["_bands"], info)
            (out_dir / f"{gid}.json").write_text(RS.dump_compact(out), encoding="utf-8", newline="\n")
            (out_dir / f"{gid}.report.md").write_text(RS.report(out), encoding="utf-8", newline="\n")
        bands = next(iter(results.values()))["_bands"]
        bands_out = {b: {k: (round(v, 2) if isinstance(v, float) else v) for k, v in st.items() if not k.startswith("_")}
                     for b, st in bands.items()}
        (out_dir / "bands-horde.json").write_text(json.dumps({"rate": "% del nivel por hora", "faction": FACTION,
                                                              "bands": bands_out}, ensure_ascii=False, indent=1) + "\n",
                                                  encoding="utf-8", newline="\n")

    def names(self) -> int:
        n = 0
        for nm in self.namers:
            k, _ = IP.write_fallback_names(nm, REPO_ROOT / "data")
            n += k
        return n


def main(argv=None) -> int:
    setup_stdio()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--polestar", required=True, help="clon de Polestar (solo lectura)")
    ap.add_argument("--foreverdb", help="forever-db (o SENDA_FOREVERDB; por defecto .cache/foreverdb)")
    ap.add_argument("--summary", help="JSON con antes/después y decisiones (para docs/ROUTE-HORDE.md)")
    args = ap.parse_args(argv)
    t0 = time.time()
    b = Build(Path(args.polestar), Path(args.foreverdb) if args.foreverdb else None)
    b.run_import()
    b.write()
    world = World(b.db, b.fdb_root)
    info = {"version": b.db.info.get("version"), "client_build": b.db.info.get("client_build"),
            "commit": b.db.info.get("build_commit")}
    before = score_all(list(b.guides), world, b.corr)
    summary: dict[str, Any] = {"before": {g: {"all": totals_of(r), "noopt": totals_of(r, True)} for g, r in before.items()}}
    b.filter_pass(world, "1")
    b.write()
    b.filter_pass(world, "2")
    b.write()
    final = score_all(list(b.guides), world, b.corr)
    b.finish_texts(final)
    b.write()
    final = score_all(list(b.guides), world, b.corr)
    b.write_scores(final, info)
    b.write(final=True)
    summary["after"] = {g: {"all": totals_of(r), "noopt": totals_of(r, True),
                            "drop_left": sum(1 for x in r["quests"].values() if x["decision"] == "drop")}
                        for g, r in final.items()}
    summary["decisions"] = b.decisions_log
    summary["stats"] = dict(b.stats)
    summary["commit"] = b.commit
    summary["foreverdb"] = info
    n_names = b.names()
    summary["stats"]["fallback_names"] = n_names
    if args.summary:
        Path(args.summary).write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    for g in b.guides:
        bf, af = summary["before"][g]["all"], summary["after"][g]["all"]
        print(f"{g}: {bf['quests']} -> {af['quests']} misiones · {bf['minutes']:.0f} -> {af['minutes']:.0f} min")
    print("stats:", dict(b.stats))
    print(f"{time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())

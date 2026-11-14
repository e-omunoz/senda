#!/usr/bin/env python3
"""Compila data/ (TOML) a Lua para el addon.

Genera:
  addon/Senda/Guides/<guide-id>.lua   secciones propias de la guía + RegisterGuide
  addon/Senda/Guides/Shared.lua       secciones de data/shared usadas por alguna guía (una vez cada una)
  addon/Senda/Guides/SharedHorde.lua  las que solo usan guías de la Horda (el archivo no carga nada para la Alianza)
  addon/Senda/Guides/Followups.lua    índice misión -> misiones que dependen de ella (para «Saltar esta misión»)
  addon/Senda/Guides/Reserve.lua      Reserva de XP de la pestaña «Aparte», desde data/reserve.json (tools/reserve.py)
  addon/Senda/Guides/Guides.xml
  addon/Senda/Knowledge/<carpeta>.lua una por carpeta de data/knowledge (warlock, mage, general...)
  addon/Senda/Knowledge/Knowledge.xml
  addon/Senda/Locale/Names_<locale>.lua  nombres del cliente de respaldo, desde data/locale/<locale>/*.json
  addon/Senda/Locale/Locale.xml       (siempre, aunque no haya idiomas: el .toc lo carga)
  addon/Senda/Data/Travel.lua         datos de data/travel/ en cadenas compactas (el planificador de viaje las decodifica
                                      bajo demanda, Modules/Travel.lua); solo si existe data/travel/
  addon/Senda/Data/TravelWalk.lua     el grafo de andar del planificador (data/travel/walk_<c>.json, senda-nav walkgraph)
  addon/Senda/Data/Rares.lua          raros compactos desde data/rares/rares.json (id, niveles, rango, apariciones)
  addon/Senda/Data/Dungeons.lua       diario de mazmorras desde data/dungeons/ (fichas, misiones, botín y pasos de guía)
  addon/Senda/Data/Data.xml           (siempre: el .toc lo carga; incluye Travel.lua y Rares.lua si existen)
  addon/Senda_Lookup/{Items,Places,Names_<locale>}.lua + Senda_Lookup.toc
                                      el buscador de objetos (addon bajo demanda) desde data/lookup/ (docs/LOOKUP.md);
                                      solo si existe data/lookup/items.json
Y estampa la versión de VERSION en la línea `## Version:` de Senda.toc.

Uso:
    python tools/build.py             # valida y genera
    python tools/build.py --check     # no escribe; falla si lo generado difiere de lo que hay en disco
    python tools/build.py --root RUTA # otra raíz (fixtures)
    python tools/build.py --refresh-prereq  # relee los requisitos de forever-db y guarda data/prereq.json
    python tools/build.py --refresh-reserve [--reserve-from RAIZ]  # rehace data/reserve.json (tools/reserve.py)

Requisitos de misión («Saltar esta misión»): el índice sale de data/prereq.json (instantánea de los requisitos
de forever-db, versionada para que el resultado no dependa de la caché local); sin ese archivo, de la caché
de forever-db si está (tools/foreverdb); y sin ninguna, del orden de coger/entregar y los `chain` de las guías.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    GENERATED_HEADER, Paths, lua_string, read_version, setup_stdio, to_lua, write_text_lf,
)
import localenames  # noqa: E402
import reserve  # noqa: E402
import validate  # noqa: E402

# Campos que no viajan al addon.
STRIP_GUIDE = {"sources", "checked", "note"}
STRIP_KNOWLEDGE = {"sources", "checked"}  # en conocimiento `note` es texto visible (talentos, macros...)

SECTION_ORDER = ["id", "title", "levels", "map", "summary", "link", "if", "parkable", "later_hint", "later_level",
                 "later_map", "steps"]
GUIDE_ORDER = ["id", "title", "summary", "faction", "races", "classes", "levels", "order", "icon",
               "link", "author", "status", "sections"]
# Orden de claves de un paso en el Lua (como en el contrato de docs/ARCHITECTURE.md);
# las claves no listadas van al final en el orden del esquema.
STEP_ORDER = ["id", "do", "quest", "quests", "obj", "npc", "item", "count", "spells", "level", "prof", "skill",
              "at", "wps", "radius", "node", "zone", "if", "optional", "escort", "chain", "text", "tip", "link", "status"]
KNOWLEDGE_ORDER = ["id", "class", "kind", "title", "summary", "levels", "order", "icon", "link", "status"]


def _step_order(paths: Paths) -> list[str]:
    with open(paths.schema / "section.schema.json", encoding="utf-8") as fh:
        schema_keys = list(json.load(fh)["$defs"]["step"]["properties"].keys())
    return STEP_ORDER + [k for k in schema_keys if k not in STEP_ORDER]


def _strip(value, keys: set[str]):
    if isinstance(value, dict):
        return {k: _strip(v, keys) for k, v in value.items() if k not in keys}
    if isinstance(value, list):
        return [_strip(v, keys) for v in value]
    return value


# Facciones cuyas guías van en archivos que solo cargan para esa facción. La Alianza no lleva guarda: sus
# archivos no cambian. Si el cliente aún no sabe la facción al cargar (nil), se carga todo, como antes.
GATED_FACTIONS = {"Horde"}


def _faction_gate(faction: str | None) -> list[str]:
    if faction not in GATED_FACTIONS:
        return []
    return [f"-- Solo personajes de la facción {faction}: para el resto, este archivo no registra nada.",
            "local faction = Senda.Compat and Senda.Compat.PlayerFaction and Senda.Compat.PlayerFaction()",
            f'if faction and faction ~= "{faction}" then return end']


def _lua_file(source: str, body: list[str], faction: str | None = None) -> str:
    head = [f"-- {GENERATED_HEADER}", f"-- Fuente: {source}", "local _, Senda = ..."] + _faction_gate(faction)
    return "\n".join(head) + "\n\n" + "\n\n".join(body) + "\n"


def _xml(files: list[str]) -> str:
    lines = [
        f"<!-- {GENERATED_HEADER} -->",
        '<Ui xmlns="http://www.blizzard.com/wow/ui/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:schemaLocation="http://www.blizzard.com/wow/ui/ ..\\FrameXML\\UI.xsd">',
    ]
    lines += [f'  <Script file="{f}"/>' for f in files]
    lines.append("</Ui>")
    return "\n".join(lines) + "\n"


def _section_table(sec: validate.Section, step_order: list[str]) -> str:
    d = _strip(sec.data, STRIP_GUIDE)
    steps = d.pop("step", [])
    d["steps"] = [{k: st[k] for k in step_order if k in st} | {k: v for k, v in st.items() if k not in step_order}
                  for st in steps]
    return f"Senda.Guides:RegisterSection({to_lua(d, key_order=SECTION_ORDER, multiline=True)})"


# ---------------------------------------------------------------- requisitos de misión
PREREQ_FILE = "prereq.json"


def _step_quests(step: dict) -> list[int]:
    out = []
    if isinstance(step.get("quest"), int):
        out.append(step["quest"])
    out += [q for q in (step.get("quests") or []) if isinstance(q, int)]
    return out


def foreverdb_prereq(root: Path, senda_corrections: Path | None = None) -> dict | None:
    """Requisitos de forever-db con sus correcciones (corrections/*.json) y las de Senda (data/corrections):
    {"edges": aristas duras (previa, misión): `all` sin migas de pan y `any` con una sola previa (con varias
    previas alternativas, saltar una no pierde la misión); "breadcrumbs": (miga, misión a la que lleva)}.
    None si no hay forever-db."""
    db_root = root / ".cache" / "foreverdb"
    if not (db_root / "data" / "quest_prereq.jsonl").exists():
        return None
    from foreverdb import corrections  # tools/foreverdb (solo hace falta al refrescar)
    tables = corrections.load_tables_corrected(
        db_root, ("quest_prereq",), senda_corrections if senda_corrections is not None else root / "data" / "corrections")
    rows: dict[int, dict[str, list[int]]] = {}
    crumbs: set[tuple[int, int]] = set()
    for r in tables["quest_prereq"]:
        if r.get("breadcrumb"):
            crumbs.add((int(r["pre"]), int(r["quest"])))
            continue
        rows.setdefault(int(r["quest"]), {"all": [], "any": []})[r["mode"]].append(int(r["pre"]))
    edges = set()
    for q, m in rows.items():
        for p in m["all"]:
            edges.add((p, q))
        if len(m["any"]) == 1:
            edges.add((m["any"][0], q))
    return {"edges": sorted(edges), "breadcrumbs": sorted(crumbs - edges)}


def foreverdb_prereq_edges(root: Path) -> list[tuple[int, int]] | None:
    pre = foreverdb_prereq(root)
    return None if pre is None else pre["edges"]


def read_prereq_snapshot(paths: Paths) -> dict | None:
    f = paths.data / PREREQ_FILE
    if not f.exists():
        return None
    with open(f, encoding="utf-8") as fh:
        data = json.load(fh)
    return {"edges": sorted((int(a), int(b)) for a, b in data.get("edges", [])),
            "breadcrumbs": sorted((int(a), int(b)) for a, b in data.get("breadcrumbs", []))}


def write_prereq_snapshot(paths: Paths, pre: dict) -> None:
    pin = ""
    pf = paths.root / "tools" / "foreverdb" / "PIN"
    if pf.exists():
        m = re.search(r"^version\s*=\s*(\S+)", pf.read_text(encoding="utf-8"), re.MULTILINE)
        pin = m.group(1) if m else ""
    head = {"_": "Requisitos duros de misión de forever-db (GPL-3.0, ver THIRD_PARTY.md) con sus correcciones "
                 "(corrections/*.json) y las de Senda (data/corrections/); los lee tools/build.py. `breadcrumbs`: "
                 "[miga, misión a la que lleva]. Se regenera con `python tools/build.py --refresh-prereq`.",
            "forever_db": pin}
    text = (json.dumps(head, ensure_ascii=False)[:-1]
            + ', "edges": [' + ",".join(f"[{a},{b}]" for a, b in pre["edges"]) + "]"
            + ', "breadcrumbs": [' + ",".join(f"[{a},{b}]" for a, b in pre.get("breadcrumbs", [])) + "]}\n")
    write_text_lf(paths.data / PREREQ_FILE, text)


def guide_prereq_edges(ds: validate.Dataset) -> list[tuple[int, int]]:
    """Respaldo sin forever-db: con el orden de las guías. B sigue a A si comparten `chain` (en orden de coger)
    o si B se coge justo después de entregar A al mismo PNJ."""
    edges: set[tuple[int, int]] = set()
    for g in ds.guides:
        if g.data.get("ship") is False:
            continue
        steps = [st for sec in g.sections for st in (sec.data.get("step") or [])]
        by_chain: dict[str, list[int]] = {}
        for i, st in enumerate(steps):
            if st.get("do") == "accept" and isinstance(st.get("quest"), int) and st.get("chain"):
                by_chain.setdefault(st["chain"], []).append(st["quest"])
            if st.get("do") == "accept" and isinstance(st.get("quest"), int) and i > 0:
                prev = steps[i - 1]
                if (prev.get("do") == "turnin" and isinstance(prev.get("quest"), int) and prev["quest"] != st["quest"]
                        and prev.get("npc") is not None and prev.get("npc") == st.get("npc")):
                    edges.add((prev["quest"], st["quest"]))
        for qs in by_chain.values():
            for a, b in zip(qs, qs[1:]):
                if a != b:
                    edges.add((a, b))
    return sorted(edges)


def render_followups(ds: validate.Dataset) -> str:
    """Guides/Followups.lua: para cada misión de las guías, las misiones de las guías que dependen de ella
    (cierre transitivo, también a través de misiones que ninguna guía usa). Cadena «q>d1,d2;...»."""
    paths = ds.paths
    pre = read_prereq_snapshot(paths)
    source = f"data/{PREREQ_FILE}"
    if pre is None:
        pre = foreverdb_prereq(paths.root)
        source = "forever-db (.cache)"
    if pre is None:
        pre = {"edges": guide_prereq_edges(ds), "breadcrumbs": []}
        source = "orden de las guías"
    edges = pre["edges"]
    mine: set[int] = set()
    for g in ds.guides:
        if g.data.get("ship") is False:
            continue
        for sec in g.sections:
            for st in sec.data.get("step") or []:
                mine.update(_step_quests(st))
    child: dict[int, list[int]] = {}
    for a, b in edges:
        child.setdefault(a, []).append(b)
    parts = []
    n_pairs = 0
    for q in sorted(mine):
        seen: set[int] = set()
        todo = list(child.get(q, ()))
        while todo:
            x = todo.pop()
            if x in seen or x == q:
                continue
            seen.add(x)
            todo.extend(child.get(x, ()))
        d = sorted(x for x in seen if x in mine)
        if d:
            n_pairs += len(d)
            parts.append(f"{q}>" + ",".join(map(str, d)))
    # Migas de pan: la miga deja de hacer falta (y de ofrecerse) cuando ya tienes o has entregado la misión a la
    # que lleva (Engine/Conditions.lua); saltarla no salta esa misión, así que no van en el índice de dependientes.
    lead: dict[int, list[int]] = {}
    for a, b in pre.get("breadcrumbs", []):
        if a in mine and b in mine:
            lead.setdefault(a, []).append(b)
    crumbs = [f"{a}>" + ",".join(map(str, sorted(lead[a]))) for a in sorted(lead)]
    head = [f"-- {GENERATED_HEADER}",
            f"-- Fuente: {source}; {len(parts)} misiones con dependientes ({n_pairs} pares); "
            f"{len(crumbs)} migas de pan",
            "local _, Senda = ..."]
    return ("\n".join(head) + "\n\nSenda.Guides:RegisterFollowups(" + lua_string(";".join(parts)) + ")\n"
            + "Senda.Guides:RegisterBreadcrumbs(" + lua_string(";".join(crumbs)) + ")\n")


def render_locale(paths: Paths) -> dict[Path, str]:
    """data/locale/<locale>/*.json -> addon/Senda/Locale/Names_<locale>.lua (+ Locale.xml).

    Compacto: una cadena "<id>\\t<nombre>" por línea y tipo; el addon la lee bajo demanda (Core/Names.lua) y solo
    la del idioma del cliente (el archivo de otro idioma sale en la primera línea)."""
    out: dict[Path, str] = {}
    files = []
    for loc in localenames.locales(paths.root / "data"):
        data = localenames.load(paths.root / "data", loc)
        body = [f"if not (Senda.Names and Senda.Names:WantsLocale({lua_string(loc)})) then return end",
                "local N = Senda.Names"]
        count = 0
        for kind in localenames.KINDS:
            entries = data.get(kind) or {}
            if not entries:
                continue
            count += len(entries)
            body.append(f"N:AddFallback({lua_string(loc)}, {lua_string(kind)}, {lua_string(localenames.pack(entries))})")
        if count == 0:
            continue
        name = f"Names_{loc}.lua"
        head = [f"-- {GENERATED_HEADER}", f"-- Fuente: data/locale/{loc}/ ({count} nombres)", "local _, Senda = ..."]
        out[paths.out_locale / name] = "\n".join(head + body) + "\n"
        files.append(name)
    out[paths.out_locale / "Locale.xml"] = _xml(files)
    return out


# ---------------------------------------------------------------- viaje
TRAVEL_SCHEMA = 1
TRAVEL_FRAMES = (0, 1)  # continentes con yardas reales; el continente nuevo de Forever (2991) no entra en el planificador


def _n(v, digits: int = 1) -> str:
    """Número compacto: sin ceros ni punto final (1.0 -> «1», 12.50 -> «12.5»)."""
    if v is None:
        return ""
    s = f"{float(v):.{digits}f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def _tpoint(p: dict) -> str:
    return ",".join([str(p["c"]), _n(p["wx"]), _n(p["wy"]), str(p.get("map", "")), _n(p.get("x"), 2), _n(p.get("y"), 2),
                     str(p.get("area", ""))])


def _tname(s: str) -> str:
    if "|" in s or "\n" in s or "\r" in s:
        raise ValueError(f"data/travel: carácter reservado en {s!r}")
    return s


def render_travel(paths: Paths) -> str | None:
    """data/travel/*.json -> Data/Travel.lua: una tabla con una cadena por clase de dato, una fila por línea y
    campos separados por «|» (los puntos son «continente,wx,wy,mapa,x,y»; wx es norte-sur y wy este-oeste, en yardas,
    como las posiciones de mundo del cliente). Nada se decodifica al cargar el addon: lo hace Modules/Travel.lua
    la primera vez que hace falta y fuera de combate."""
    tdir = paths.travel
    if not (tdir / "meta.json").exists():
        return None

    def rows(name: str) -> list[dict]:
        with open(tdir / f"{name}.json", encoding="utf-8") as fh:
            return json.load(fh)["rows"]

    mask_of = {"alliance": 1, "horde": 2, "both": 3}
    with open(tdir / "meta.json", encoding="utf-8") as fh:
        meta = json.load(fh)
    consts = meta["constants"]
    nodes = [f"{t['id']}|{t['mask']}|{t.get('class') or ''}|{_tpoint(t)}|{_tname(t['name'])}"
             for t in sorted(rows("taxi_nodes"), key=lambda t: t["id"]) if t["c"] in TRAVEL_FRAMES]
    ids = {t["id"] for t in rows("taxi_nodes") if t["c"] in TRAVEL_FRAMES}
    flights = [f"{f['from']}|{f['to']}|{_n(f['seconds'])}" for f in sorted(rows("flights"), key=lambda f: (f["from"], f["to"]))
               if f["from"] in ids and f["to"] in ids]

    def board(e: dict) -> str:
        b = e.get("board")
        return f"{_n(b['wx'])},{_n(b['wy'])}" if b else ""

    rides = []
    for t in rows("transports"):
        a, b = t["a"], t["b"]
        if a["c"] not in TRAVEL_FRAMES or b["c"] not in TRAVEL_FRAMES:
            continue
        rides.append("|".join([_tname(t["id"]), t["kind"], str(t["mask"]), _n(t["ride_ab_s"]), _n(t["ride_ba_s"]),
                               _n(t["wait_a_s"]), _n(t["wait_b_s"]), _n(t["board_s"] + t["pre_s"] + t["post_s"]),
                               _tpoint(a), board(a), _tname(a["name"]), _tpoint(b), board(b), _tname(b["name"])]))
    portals = []
    for p in rows("portals"):
        if p["a"]["c"] not in TRAVEL_FRAMES or p["b"]["c"] not in TRAVEL_FRAMES:
            continue
        portals.append("|".join([_tname(p["id"]), str(p["mask"]), _n(p["seconds"]), _tpoint(p["a"]), _tname(p["a"]["name"]),
                                 _tpoint(p["b"]), _tname(p["b"]["name"])]))
    inns = [f"{i['area']}|{i['npc']}|{_tpoint(i)}|{';'.join(_tname(n) for n in i['names'])}"
            for i in sorted(rows("inns"), key=lambda i: (i["area"], i["npc"])) if i["c"] in TRAVEL_FRAMES]
    tele = []
    for t in rows("teleports"):
        dest = t["to"]
        if dest != "bind" and dest["c"] not in TRAVEL_FRAMES:
            continue
        reag = ";".join(f"{r['item']}:{r['count']}" for r in t.get("reagents") or [])
        tele.append("|".join([str(t["spell"]), t["class"], str(mask_of[t["faction"]]), _n(t["cast_s"]), reag,
                              "bind" if dest == "bind" else _tpoint(dest), _tname(t["name"])]))

    def blob(lines: list[str]) -> str:
        if any("]==]" in ln for ln in lines):
            raise ValueError("data/travel: «]==]» en una fila")
        return "[==[\n" + "\n".join(lines) + "\n]==]"

    const_names = {"run_speed_yd_s": "run", "walk_detour": "detour", "flight_speed_yd_s": "flySpeed",
                   "flight_stop_s": "flyStop", "take_off_s": "takeOff", "hearth_item": "hearthItem",
                   "hearth_total_s": "hearthSecs", "hearth_min_trip_s": "hearthMinTrip",
                   "hearth_margin_s": "hearthMargin", "teleport_margin_s": "teleMargin", "teleport_share": "teleShare"}
    k = ", ".join(f"{lua} = {_n(consts[key], 3)}" for key, lua in const_names.items())
    counts = (f"{len(nodes)} nodos de vuelo, {len(flights)} vuelos, {len(rides)} transportes, {len(portals)} portales, "
              f"{len(inns)} posadas, {len(tele)} teletransportes")
    body = "\n".join([
        f"-- {GENERATED_HEADER}",
        f"-- Fuente: data/travel/ (tools/gen_travel.py, GPL-3.0-or-later; ver docs/TRAVEL.md y THIRD_PARTY.md): {counts}",
        "-- Filas «a|b|c», puntos «continente,wx,wy,mapa,x,y,zona» (yardas de mundo, % de mapa y AreaTable). Se decodifica bajo demanda.",
        "local _, Senda = ...",
        "",
        "Senda.TravelData = {",
        f"  schema = {TRAVEL_SCHEMA},",
        f"  consts = {{ {k} }},",
        f"  nodes = {blob(nodes)},",
        f"  flights = {blob(flights)},",
        f"  rides = {blob(rides)},",
        f"  portals = {blob(portals)},",
        f"  inns = {blob(inns)},",
        f"  teleports = {blob(tele)},",
        "}",
    ])
    return body + "\n"
# ---------------------------------------------------------------- viaje: andar por el terreno real
WALK_SCHEMA = 1
WALK_B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
WALK_OFF = 20000      # se suma a las yardas de mundo para que sean positivas (3 dígitos: hasta 262143)
WALK_NONE = 64 ** 3 - 1  # en la matriz: no se llega andando


def _b64n(v: int, width: int) -> str:
    """Entero >= 0 en `width` dígitos de base 64 (de más a menos significativo)."""
    if not 0 <= v < 64 ** width:
        raise ValueError(f"data/travel/walk: {v} no cabe en {width} dígitos")
    out = []
    for _ in range(width):
        out.append(WALK_B64[v & 63])
        v >>= 6
    return "".join(reversed(out))


def render_walk(paths: Paths) -> str | None:
    """data/travel/walk_<c>.json (senda-nav walkgraph) -> Data/TravelWalk.lua: por continente, el grafo de andar del
    planificador en cadenas de dígitos de base 64 (Modules/Travel.lua las decodifica la primera vez que planifica en ese
    continente). `g`: una línea por nodo, «x y» (3 + 3 dígitos, yardas de mundo + 20000) y sus aristas hacia nodos
    posteriores, 6 dígitos cada una: salto al otro nodo (2), yardas de ida (2) y de vuelta (2), 0 = sin paso en ese
    sentido. `keys`: los lugares del planificador («fp:2», «ride:<id>:a», «inn:<pnj>»...) y `nodes` su nodo (3 dígitos,
    desde 0). `m`: la matriz de yardas a pie entre lugares, una línea por lugar (3 dígitos; 262143 = no se llega)."""
    files = [(c, paths.travel / f"walk_{c}.json") for c in TRAVEL_FRAMES]
    files = [(c, f) for c, f in files if f.exists()]
    if not files:
        return None
    parts, counts = [], []
    for c, f in files:
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        nodes = d["nodes"]
        pairs: dict[tuple[int, int], list[int]] = {}
        for a, b, y in d["edges"]:
            lo, hi = (a, b) if a < b else (b, a)
            if lo == hi:
                continue
            p = pairs.setdefault((lo, hi), [0, 0])
            p[0 if a == lo else 1] = int(y)
        by_node: dict[int, list[str]] = {}
        for (lo, hi), (ab, ba) in sorted(pairs.items()):
            if hi - lo >= 64 ** 2 or ab >= 64 ** 2 or ba >= 64 ** 2:
                raise ValueError(f"data/travel/walk_{c}.json: arista {lo}-{hi} fuera de rango")
            by_node.setdefault(lo, []).append(_b64n(hi - lo, 2) + _b64n(ab, 2) + _b64n(ba, 2))
        g = [_b64n(int(x) + WALK_OFF, 3) + _b64n(int(y) + WALK_OFF, 3) + "".join(by_node.get(i, []))
             for i, (x, y) in enumerate(nodes)]
        keys = d["matrix"]["keys"]
        for k in keys:
            if ";" in k or "]==]" in k:
                raise ValueError(f"data/travel/walk_{c}.json: clave {k!r}")
        pnodes = "".join(_b64n(d["places"][k], 3) for k in keys)
        m = ["".join(_b64n(WALK_NONE if v is None else int(v), 3) for v in row) for row in d["matrix"]["yards"]]
        meta = d.get("meta", {})
        counts.append(f"{c}: {len(nodes)} nodos, {len(pairs)} pares de aristas, {len(keys)} lugares")
        parts += [
            f"  [{c}] = {{",
            f"    n = {len(nodes)}, np = {len(keys)}, build = {lua_string(str(meta.get('client_build', '?')))},",
            "    g = [==[\n" + "\n".join(g) + "\n]==],",
            f"    keys = [==[{';'.join(keys)}]==],",
            f"    nodes = [==[{pnodes}]==],",
            "    m = [==[\n" + "\n".join(m) + "\n]==],",
            "  },",
        ]
    body = [
        f"-- {GENERATED_HEADER}",
        "-- Fuente: data/travel/walk_<c>.json (senda-nav walkgraph sobre la malla propia de Senda, nav/; ver docs/TRAVEL.md,"
        " «Andar»): " + "; ".join(counts),
        "-- Dígitos de base 64 (A-Z a-z 0-9 + /); se decodifica bajo demanda en Modules/Travel.lua.",
        "local _, Senda = ...",
        "",
        "Senda.TravelWalk = {",
        f"  schema = {WALK_SCHEMA}, off = {WALK_OFF}, none = {WALK_NONE},",
        *parts,
        "}",
    ]
    return "\n".join(body) + "\n"


def render_rares(paths: Paths, extra: list[str] | None = None) -> dict[Path, str]:
    """data/rares/rares.json -> addon/Senda/Data/Rares.lua (+ Data.xml).

    Un raro por clave numérica (su id de PNJ) con una cadena "<niv. mín>-<niv. máx> <r|e> <mapa>:<x>,<y>;<x>,<y> ...":
    r = raro, e = raro élite; x e y en décimas de % del mapa (509 = 50,9 %). Nivel 0-0: desconocido (forever-db da
    nivel 1 a ocho raros que son marcadores o de nivel escalado; no se corrige, el cliente da el real al verlos).
    Solo entran los que tienen alguna aparición conocida. El addon decodifica cada cadena al usarla."""
    out: dict[Path, str] = {}
    files: list[str] = list(extra or [])  # otros datos de Data/ que carga el mismo Data.xml (Travel.lua)
    src = paths.rares / "rares.json"
    if src.exists():
        with open(src, encoding="utf-8") as fh:
            rares = json.load(fh)
        meta = {}
        mf = paths.rares / "meta.json"
        if mf.exists():
            with open(mf, encoding="utf-8") as fh:
                meta = json.load(fh).get("source", {})
        lines = []
        for r in sorted(rares, key=lambda r: r["id"]):
            if not r.get("spawns"):
                continue
            lo, hi = r["level"]
            if lo <= 1 and hi <= 1:
                lo = hi = 0
            groups: dict[int, list[str]] = {}
            for m, x, y in r["spawns"]:
                groups.setdefault(int(m), []).append(f"{round(x * 10)},{round(y * 10)}")
            pts = " ".join(f"{m}:" + ";".join(v) for m, v in groups.items())
            kind = "e" if r["rank"] == "rareelite" else "r"
            lines.append(f'  [{r["id"]}] = "{lo}-{hi} {kind} {pts}",')
        head = [f"-- {GENERATED_HEADER}",
                f"-- Fuente: data/rares/ ({len(lines)} raros con aparición; {meta.get('name', 'forever-db')} "
                f"{meta.get('version', '?')}, GPL-3.0)",
                "local _, Senda = ..."]
        body = ['-- [idNPC] = "nivelMín-nivelMáx r|e mapa:x,y;x,y ..." (x e y en décimas de %; ver tools/build.py)',
                "Senda.RaresData = {"] + lines + ["}"]
        out[paths.out_data / "Rares.lua"] = "\n".join(head + [""] + body) + "\n"
        files.append("Rares.lua")
    out[paths.out_data / "Data.xml"] = _xml(files)
    return out


# ---------------------------------------------------------------- mazmorras
DUNGEONS_SCHEMA = 1
# Nombres con que las guías citan cada mazmorra (español del cliente esES e inglés), para unir los pasos
# `do = "dungeon"` con su ficha cuando el texto la nombra. El orden importa: «Cumbre de Roca Negra» antes que
# las Profundidades no hace falta porque los nombres no se contienen entre sí.
DUNGEON_ALIASES = {
    "shadowfang-keep": ["Castillo de Colmillo Oscuro", "Shadowfang Keep"],
    "stormwind-stockade": ["Las Mazmorras", "Stockade"],
    "deadmines": ["Minas de la Muerte", "Deadmines"],
    "wailing-caverns": ["Cuevas de los Lamentos", "Wailing Caverns"],
    "razorfen-kraul": ["Horado Rajacieno", "Razorfen Kraul"],
    "blackfathom-deeps": ["Cavernas de Brazanegra", "Blackfathom Deeps"],
    "uldaman": ["Uldaman"],
    "gnomeregan": ["Gnomeregan"],
    "sunken-temple": ["Templo de Atal'Hakkar", "Templo Sumergido", "Sunken Temple"],
    "razorfen-downs": ["Zahúrda Rajacieno", "Razorfen Downs"],
    "scarlet-monastery": ["Monasterio Escarlata", "Scarlet Monastery"],
    "zulfarrak": ["Zul'Farrak"],
    "blackrock-spire": ["Cumbre de Roca Negra", "Blackrock Spire"],
    "blackrock-depths": ["Profundidades de Roca Negra", "Blackrock Depths"],
    "scholomance": ["Scholomance"],
    "stratholme": ["Stratholme"],
    "maraudon": ["Maraudon"],
    "ragefire-chasm": ["Sima Ígnea", "Ragefire Chasm"],
    "dire-maul": ["La Masacre", "Dire Maul"],
    "city-of-dalaran": ["City of Dalaran"],
    "excavation-site-wetlands": ["Excavation Site: Wetlands"],
    "ruins-of-lordaeron": ["Ruins of Lordaeron"],
    "the-hall-of-thanes": ["Hall of Thanes"],
}
# Mapa de zona con que se muestra la entrada cuando el punto del cliente cae en el solape de dos zonas
# (`other_frames` de dungeons.json; el punto es el mismo, solo cambia la zona que se nombra): la zona donde está la
# puerta en el mapa del juego, la misma que usan los pasos de las guías (Uldaman en Tierras Inhóspitas).
PREFERRED_FRAME = {"uldaman": 1418, "razorfen-kraul": 1413, "razorfen-downs": 1413, "blackfathom-deeps": 1440}
STARTED = {"inside": "i", "outside": "o", "unknown": "u"}
SCOPE = {"zone": "z", "objective": "o", "text": "t", "chain": "c"}
GIVER_KIND = {"npc": "n", "object": "o", "item": "i"}


def _dfield(s) -> str:
    s = "" if s is None else str(s)
    if "|" in s or "\n" in s or "]==]" in s or ";" in s:
        raise ValueError(f"data/dungeons: carácter reservado en {s!r}")
    return s


def dungeon_steps(sections: list, dungeons: list[dict], quests: dict) -> dict[str, str]:
    """Paso `do = "dungeon"` -> clave de mazmorra. Por orden: el texto o la etiqueta del punto nombran la mazmorra;
    el paso pide misiones propias de una mazmorra (no las de cadena); su punto está a menos de 3 % de la entrada."""
    own: dict[str, set[int]] = {}
    for d in dungeons:
        own[d["key"]] = {q["id"] for q in quests.get(d["key"], []) if q.get("scope") != "chain"}
    out: dict[str, str] = {}
    for sec in sections:
        for st in sec.data.get("step") or []:
            if st.get("do") != "dungeon":
                continue
            at = st.get("at") or []
            label = " ".join(str(x) for x in [st.get("text", ""), at[3] if len(at) > 3 else ""])
            key = None
            for d in dungeons:
                if any(a.lower() in label.lower() for a in DUNGEON_ALIASES.get(d["key"], [d["name"]])):
                    key = d["key"]
                    break
            if not key:
                qs = set(_step_quests(st))
                best = max(dungeons, key=lambda d: len(qs & own[d["key"]]))
                if qs & own[best["key"]]:
                    key = best["key"]
            if not key and len(at) >= 3:
                for d in dungeons:
                    e = d.get("entrance")
                    if e and e["uiMapId"] == at[0] and math.hypot(e["x"] - at[1], e["y"] - at[2]) <= 3:
                        key = d["key"]
                        break
            if key:
                out[st["id"]] = key
    return out


def render_dungeons(paths: Paths, sections: list) -> str | None:
    """data/dungeons/{dungeons,quests,journal}.json -> Data/Dungeons.lua (diario de mazmorras, Modules/Dungeons.lua).

    Una tabla con cadenas «a|b|c», una fila por línea, que el addon decodifica la primera vez que abre el diario y
    fuera de combate (solo `steps` se lee al cargar: une los pasos de mazmorra de las guías con su ficha):
      list   clave|mapa|área|nombre|entrada|recomendado|misiones mín-máx|facción|forever|entrada|piedra|jefes
             entrada = uiMap,x,y,origen (c: punto del cliente, g: punto del paso de la guía); piedra = uiMap,x,y,yardas
             jefes = pnj=nombre;...
      quests clave|id|nivel|mín|facción|clases|razas|alcance|empieza|dador|requisitos|alguno|xp
             dador = n|o|i<id>@uiMap,x,y ; razas = máscara & 255 (las razas clásicas)
      loot   clave|id|ranura|clase|subclase|nivel|calidad|pnj|prob|máscara de clase|estadísticas (CLAVE=v,...)
    """
    ddir = paths.data / "dungeons"
    if not (ddir / "dungeons.json").exists():
        return None
    with open(ddir / "dungeons.json", encoding="utf-8") as fh:
        dungeons = json.load(fh)["dungeons"]
    quests: dict = {}
    if (ddir / "quests.json").exists():
        with open(ddir / "quests.json", encoding="utf-8") as fh:
            quests = json.load(fh)["quests"]
    journal: dict = {}
    if (ddir / "journal.json").exists():
        with open(ddir / "journal.json", encoding="utf-8") as fh:
            journal = json.load(fh)
    steps = dungeon_steps(sections, dungeons, quests)
    # Entrada de respaldo: el punto del primer paso de la guía que lleva a esa mazmorra (si el cliente no da ninguna).
    guide_at: dict[str, list] = {}
    for sec in sections:
        for st in sec.data.get("step") or []:
            k = steps.get(st.get("id"))
            if k and k not in guide_at and len(st.get("at") or []) >= 3:
                guide_at[k] = st["at"]
    stones = journal.get("stones", {})
    bosses = journal.get("bosses", {})
    lines = []
    for d in dungeons:
        k = d["key"]
        lv = d["levels"]
        e = d.get("entrance")
        if e:
            frames = [[e["uiMapId"], e["x"], e["y"]]] + [f for f in e.get("other_frames") or []]
            want = PREFERRED_FRAME.get(k) or (guide_at[k][0] if k in guide_at else None)
            f = next((f for f in frames if f[0] == want), frames[0])
            ent = f"{f[0]},{_n(f[1])},{_n(f[2])},c"
        elif k in guide_at:
            a = guide_at[k]
            ent = f"{a[0]},{_n(a[1])},{_n(a[2])},g"
        else:
            ent = ""
        s = stones.get(k)
        stone = f"{s['uiMapId']},{_n(s['x'])},{_n(s['y'])},{s['yards']}" if s else ""
        qr = lv.get("quest_range") or []
        boss = ";".join(f"{npc}={_dfield(name)}" for name, npc in bosses.get(k, []))
        lines.append("|".join([k, str(d["map"]), str((d.get("area_ids") or [0])[0]), _dfield(d["name"]),
                               str(lv.get("entry") or ""), str(lv.get("recommended") or ""),
                               f"{qr[0]}-{qr[1]}" if len(qr) == 2 else "", "".join(d.get("lfg_faction") or ["AH"]),
                               "1" if d.get("forever_only") else "0", ent, stone, boss]))
    qlines = []
    for d in dungeons:
        for q in sorted(quests.get(d["key"], []), key=lambda q: (q["level"], q["id"])):
            giver = ""
            for g in q.get("giver") or []:
                pos = g.get("pos")
                giver = GIVER_KIND.get(g["kind"], "n") + str(g["id"])
                if pos:
                    giver += f"@{pos[0]},{_n(pos[1])},{_n(pos[2])}"
                    break
            req = q.get("requires") or {}
            qlines.append("|".join([d["key"], str(q["id"]), str(q.get("level") or 0), str(q.get("min_level") or 0),
                                    q.get("faction") or "AH", str(q.get("classes") or 0), str((q.get("races") or 0) & 255),
                                    SCOPE.get(q.get("scope"), "z"), STARTED.get(q.get("started"), "-"), giver,
                                    ";".join(str(x) for x in req.get("all") or []),
                                    ";".join(str(x) for x in req.get("any") or []), str(q.get("xp") or 0)]))
    llines = []
    for d in dungeons:
        for it in journal.get("loot", {}).get(d["key"], []):
            stats = ",".join(f"{k2}={_n(v, 1)}" for k2, v in sorted(it["stats"].items()))
            pct = "" if it.get("pct") is None else _n(it["pct"], 1)
            llines.append("|".join([d["key"], str(it["id"]), str(it["inv"]), str(it["class"]), str(it["sub"]),
                                    str(it["req"]), str(it["q"]), str(it.get("npc") or 0), pct, str(it.get("cls") or 0), stats]))

    def blob(rows: list[str]) -> str:
        return "[==[\n" + "\n".join(rows) + "\n]==]"

    src = journal.get("sources", {})
    flb = src.get("ForeverLevelingBiS", {})
    fdb = src.get("forever-db", {})
    step_lines = [f"    [{lua_string(sid)}] = {lua_string(k)}," for sid, k in sorted(steps.items())]
    body = "\n".join([
        f"-- {GENERATED_HEADER}",
        f"-- Fuente: data/dungeons/ (tools/gen_dungeons.py y tools/gen_dungeon_journal.py; ver docs/DUNGEONS.md): "
        f"{len(lines)} mazmorras, {len(qlines)} misiones, {len(llines)} objetos de botín, {len(steps)} pasos de guía.",
        f"-- Botín: ForeverLevelingBiS {flb.get('version', '?')} (MIT, Copyright (c) 2026 Thunder) vía Polestar (GPL-3.0) y "
        f"forever-db {fdb.get('version', '?')} (GPL-3.0); estadísticas de Forever o del cliente Classic Era. Ver THIRD_PARTY.md.",
        "-- Filas «a|b|c» (formato en tools/build.py, render_dungeons). Se decodifica bajo demanda.",
        "local _, Senda = ...",
        "",
        "Senda.DungeonsData = {",
        f"  schema = {DUNGEONS_SCHEMA},",
        "  steps = {",
        *step_lines,
        "  },",
        f"  list = {blob(lines)},",
        f"  quests = {blob(qlines)},",
        f"  loot = {blob(llines)},",
        "}",
    ])
    return body + "\n"


# ---------------------------------------------------------------- buscador de objetos (Senda_Lookup)
def _lk(v) -> str:
    """Número de data/lookup/*.json sin ceros de más (6.0 -> 6)."""
    return str(int(v)) if float(v).is_integer() else str(v)


def lookup_entry(e: dict) -> str:
    """Una cadena por objeto: campos `k=valor` separados por `;` (el addon los lee solo al consultar ese objeto).
      s=n3577:100,o3658,i12     botín: n PNJ, o objeto del mundo, i objeto contenedor; id y :probabilidad %
      N=257                     total real de fuentes si se cortó la lista
      v=6736,6737               vendedores (PNJ)
      g=1429:52.4:61.2          sitio de la ruta donde la guía recoge el objeto (mapa:x:y)
      q=8c,9                    recompensa de misión (c = a elegir); Q = total
      o=3181,3182               objetivo de misión (solo enlace); O = total"""
    parts = []
    if e.get("s"):
        parts.append("s=" + ",".join(f"{r[0]}{r[1]}" + (f":{_lk(r[2])}" if len(r) > 2 else "") for r in e["s"]))
    if e.get("n"):
        parts.append(f"N={e['n']}")
    if e.get("v"):
        parts.append("v=" + ",".join(str(r[0]) for r in e["v"]))
    if e.get("g"):
        parts.append("g=" + ",".join(f"{p[0]}:{_lk(p[1])}:{_lk(p[2])}" for p in e["g"]))
    if e.get("q"):
        parts.append("q=" + ",".join(f"{q}{'c' if ch else ''}" for q, ch in e["q"]))
    if e.get("nq"):
        parts.append(f"Q={e['nq']}")
    if e.get("o"):
        parts.append("o=" + ",".join(str(q) for q in e["o"]))
    if e.get("no"):
        parts.append(f"O={e['no']}")
    return ";".join(parts)


LOOKUP_TOC = """## Interface: 16001
## Title: Senda Lookup
## Notes: Buscador de objetos de Senda: de dónde sale cada objeto de las guías (botín, vendedores, misiones). Se carga bajo demanda.
## Notes-enUS: Senda's item finder: where each guide item comes from (drops, vendors, quests). Loads on demand.
## Author: omunoz
## Version: {version}
## LoadOnDemand: 1
## X-License: GPL-3.0

# {header}
{files}
"""


def lookup_names(paths: Paths, locale: str) -> dict[int, dict[str, str]]:
    """Nombres de objeto de un idioma para el buscador: los de data/lookup/locale (fuente forever-db en inglés, o
    volcados del juego) y los de data/locale (los objetos de las guías); a igual prioridad gana el de la guía."""
    merged: dict[str, dict[int, dict[str, str]]] = {"item": {}}
    for root in (paths.lookup, paths.data):
        for ident, e in localenames.load(root, locale)["item"].items():
            localenames.merge(merged, "item", ident, e["name"], e["source"])
    return merged["item"]


def render_lookup(paths: Paths) -> dict[Path, str]:
    """data/lookup/{items,places}.json + nombres -> addon/Senda_Lookup/ (un addon aparte, LoadOnDemand: no pesa
    hasta que alguien mira un objeto). Datos globales `Senda_Lookup.items|places|names`; ver lookup_entry."""
    src = paths.lookup / "items.json"
    if not src.exists():
        return {}
    with open(src, encoding="utf-8") as fh:
        items_doc = json.load(fh)
    places_doc = {}
    pf = paths.lookup / "places.json"
    if pf.exists():
        with open(pf, encoding="utf-8") as fh:
            places_doc = json.load(fh)
    meta = items_doc.get("meta", {})
    out: dict[Path, str] = {}
    head = [f"-- {GENERATED_HEADER}",
            f"-- Fuente: data/lookup/ (forever-db {meta.get('forever_db_version', '?')}, cliente "
            f"{meta.get('client_build', '?')}, GPL-3.0; docs/LOOKUP.md)"]
    files: list[str] = []

    items = items_doc.get("items", {})
    lines = [f'  [{i}] = "{lookup_entry(items[str(i)])}",' for i in sorted(int(k) for k in items)]
    body = ["Senda_Lookup = Senda_Lookup or {}",
            f"Senda_Lookup.meta = {{ forever_db = {lua_string(str(meta.get('forever_db_version', '?')))}, "
            f"build = {lua_string(str(meta.get('client_build', '?')))}, items = {len(lines)} }}",
            '-- [idObjeto] = "s=n3577:100,o3658;N=257;v=6736;g=mapa:x:y;q=8c;Q=9;o=3181;O=4" (ver tools/build.py)',
            "Senda_Lookup.items = {"] + lines + ["}"]
    out[paths.out_lookup / "Items.lua"] = "\n".join(head + [""] + body) + "\n"
    files.append("Items.lua")

    places = places_doc.get("places", {})
    body = ["Senda_Lookup = Senda_Lookup or {}",
            '-- n = PNJ, o = objetos del mundo: [id] = "uiMapa,x%,y%,mapa,apariciones" (uiMapa 0 = mazmorra: x, y en yardas)',
            "Senda_Lookup.places = {"]
    for kind in ("n", "o"):
        body.append(f"  {kind} = {{")
        for i in sorted(int(k) for k in places.get(kind, {})):
            p = places[kind][str(i)]
            body.append(f'    [{i}] = "{",".join(_lk(v) for v in p)}",')
        body.append("  },")
    body.append("}")
    out[paths.out_lookup / "Places.lua"] = "\n".join(head + [""] + body) + "\n"
    files.append("Places.lua")

    for loc in sorted(set(localenames.locales(paths.lookup)) | set(localenames.locales(paths.data))):
        names = {i: e for i, e in lookup_names(paths, loc).items() if str(i) in items}
        if not names:
            continue
        name = f"Names_{loc}.lua"
        body = ["Senda_Lookup = Senda_Lookup or {}", "Senda_Lookup.names = Senda_Lookup.names or {}",
                f'-- "<id>\\t<nombre>" por línea ({len(names)} objetos); el addon la recorre bajo demanda',
                f"Senda_Lookup.names[{lua_string(loc)}] = {lua_string(localenames.pack(names))}"]
        out[paths.out_lookup / name] = "\n".join(head + [""] + body) + "\n"
        files.append(name)

    out[paths.out_lookup / "Senda_Lookup.toc"] = LOOKUP_TOC.format(
        version="0.1.0", header=GENERATED_HEADER, files="\n".join(files))
    return out


def render(ds: validate.Dataset) -> dict[Path, str]:
    """Devuelve {ruta: contenido} de todo lo generado. Determinista."""
    paths = ds.paths
    step_order = _step_order(paths)
    out: dict[Path, str] = {}

    # --- guías
    shared_used: dict[str, validate.Section] = {}
    shared_factions: dict[str, set] = {}
    guide_files: list[str] = []
    for g in sorted(ds.guides, key=lambda g: g.data["id"]):
        # ship = false: datos de trabajo (p. ej. rutas importadas en bruto) que no van en el addon.
        if g.data.get("ship") is False:
            continue
        body = []
        for sec in g.sections:
            if sec.shared:
                shared_used.setdefault(sec.key, sec)
                shared_factions.setdefault(sec.key, set()).add(g.data.get("faction"))
            else:
                body.append(_section_table(sec, step_order))
        gd = _strip(g.data, STRIP_GUIDE)
        gd["sections"] = [s.id for s in g.sections]
        body.append(f"Senda.Guides:RegisterGuide({to_lua(gd, key_order=GUIDE_ORDER, multiline=True)})")
        name = f"{g.data['id']}.lua"
        out[paths.out_guides / name] = _lua_file(paths.rel(g.dir) + "/", body, g.data.get("faction"))
        guide_files.append(name)

    xml_files = []
    out[paths.out_guides / "Followups.lua"] = render_followups(ds)
    xml_files.append("Followups.lua")
    res = reserve.render(paths)
    if res is not None:
        out[paths.out_guides / "Reserve.lua"] = res
        xml_files.append("Reserve.lua")
    # Secciones compartidas que solo usan guías de una facción con guarda: en su propio archivo.
    gated: dict[str, dict] = {}
    for key, sec in sorted(shared_used.items()):
        fs = shared_factions.get(key, set())
        only = next(iter(fs)) if len(fs) == 1 else None
        gated.setdefault(only if only in GATED_FACTIONS else "", {})[key] = sec
    if gated.get(""):
        body = [_section_table(sec, step_order) for _, sec in sorted(gated[""].items())]
        out[paths.out_guides / "Shared.lua"] = _lua_file("data/shared/", body)
        xml_files.append("Shared.lua")
    for faction in sorted(f for f in gated if f):
        body = [_section_table(sec, step_order) for _, sec in sorted(gated[faction].items())]
        name = f"Shared{faction}.lua"
        out[paths.out_guides / name] = _lua_file("data/shared/", body, faction)
        xml_files.append(name)
    xml_files += guide_files
    out[paths.out_guides / "Guides.xml"] = _xml(xml_files)

    # --- conocimiento
    groups: dict[str, list[validate.KnowledgePage]] = {}
    for kp in ds.knowledge:
        groups.setdefault(kp.group, []).append(kp)
    kfiles = []
    for group in sorted(groups):
        pages = sorted(groups[group], key=lambda k: (k.data.get("order", 0), k.data["id"]))
        body = [f"Senda.Knowledge:Register({to_lua(_strip(kp.data, STRIP_KNOWLEDGE), key_order=KNOWLEDGE_ORDER, multiline=True)})"
                for kp in pages]
        name = f"{group}.lua"
        out[paths.out_knowledge / name] = _lua_file(f"data/knowledge/{group}/", body)
        kfiles.append(name)
    out[paths.out_knowledge / "Knowledge.xml"] = _xml(kfiles)
    out.update(render_locale(paths))
    travel = render_travel(paths)
    data_files: list[str] = []
    if travel is not None:
        out[paths.out_data / "Travel.lua"] = travel
        data_files.append("Travel.lua")
    walk = render_walk(paths)
    if walk is not None:
        out[paths.out_data / "TravelWalk.lua"] = walk
        data_files.append("TravelWalk.lua")
    dungeons = render_dungeons(paths, ds.sections)
    if dungeons is not None:
        out[paths.out_data / "Dungeons.lua"] = dungeons
        data_files.append("Dungeons.lua")
    out.update(render_rares(paths, data_files))
    out.update(render_lookup(paths))
    return out


def stamp_toc(paths: Paths, version: str, check: bool) -> tuple[bool, str]:
    """Sustituye solo la línea `## Version:` del .toc. Devuelve (cambiaría/cambió, mensaje)."""
    if not paths.toc.exists():
        return False, f"aviso: no existe {paths.rel(paths.toc)}; no se estampa la versión"
    raw = paths.toc.read_bytes()
    text = raw.decode("utf-8-sig")
    pat = re.compile(r"^## Version:[^\r\n]*", re.MULTILINE)
    if not pat.search(text):
        return False, f"aviso: {paths.rel(paths.toc)} no tiene línea '## Version:'; no se toca"
    new = pat.sub(f"## Version: {version}", text, count=1)
    if new == text:
        return False, ""
    if not check:
        bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
        paths.toc.write_bytes(bom + new.encode("utf-8"))  # conserva finales de línea originales
    return True, f"{paths.rel(paths.toc)}: ## Version: {version}"


def _is_generated(p: Path) -> bool:
    try:
        with open(p, encoding="utf-8") as fh:
            return GENERATED_HEADER in fh.readline()
    except (OSError, UnicodeDecodeError):
        return False


def build(paths: Paths, check: bool = False, quiet: bool = False) -> int:
    ds = validate.load_and_check(paths)
    for i in ds.issues:
        print(str(i), file=sys.stderr)
    if ds.errors:
        print(f"build: {len(ds.errors)} errores de validación; no se genera nada.", file=sys.stderr)
        return 1

    try:
        version = read_version(paths)
    except (OSError, ValueError) as exc:
        print(f"build: {exc}", file=sys.stderr)
        return 1

    try:
        outputs = render(ds)
    except (ValueError, OSError) as exc:  # data/locale/*.json mal formado
        print(f"build: {exc}", file=sys.stderr)
        return 1
    changed: list[str] = []
    for path, text in sorted(outputs.items()):
        data = text.encode("utf-8")
        if not path.exists() or path.read_bytes() != data:
            changed.append(paths.rel(path))
            if not check:
                write_text_lf(path, text)

    # Archivos generados que ya no corresponden a nada (solo los que llevan nuestra cabecera).
    stale: list[str] = []
    for d in (paths.out_guides, paths.out_knowledge, paths.out_locale, paths.out_data, paths.out_lookup):
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if p.is_file() and p not in outputs and p.suffix in (".lua", ".xml"):
                if _is_generated(p):
                    stale.append(paths.rel(p))
                    if not check:
                        p.unlink()
                else:
                    print(f"aviso: {paths.rel(p)} no es generado y no está en el .xml", file=sys.stderr)

    toc_changed, toc_msg = stamp_toc(paths, version, check)
    if toc_msg and not quiet:
        print(toc_msg, file=sys.stderr if toc_msg.startswith("aviso") else sys.stdout)

    if check:
        problems = changed + [f"{s} (sobrante)" for s in stale] + ([paths.rel(paths.toc)] if toc_changed else [])
        if problems:
            print("build --check: lo generado no está al día:", file=sys.stderr)
            for p in problems:
                print(f"  {p}", file=sys.stderr)
            print("Ejecuta: python tools/build.py", file=sys.stderr)
            return 1
        if not quiet:
            print("build --check: todo al día.")
        return 0

    if not quiet:
        n_steps = sum(len(s.data.get("step") or []) for s in ds.sections)
        print(f"build {version}: {len(ds.guides)} guías, {len(ds.sections)} secciones, {n_steps} pasos, "
              f"{len(ds.knowledge)} páginas de conocimiento; {len(changed)} archivos actualizados"
              + (f", {len(stale)} borrados" if stale else ""))
        for c in changed:
            print(f"  escrito  {c}")
        for s in stale:
            print(f"  borrado  {s}")
    return 0


def main(argv: list[str] | None = None) -> int:
    setup_stdio()
    ap = argparse.ArgumentParser(description="Compila data/ a addon/Senda/{Guides,Knowledge}.")
    ap.add_argument("--root", help="raíz alternativa (por defecto, el repo)")
    ap.add_argument("--check", action="store_true", help="no escribir; fallar si hay diferencias")
    ap.add_argument("--refresh-prereq", action="store_true",
                    help="relee los requisitos de forever-db (.cache) y guarda data/prereq.json")
    ap.add_argument("--refresh-reserve", action="store_true",
                    help="rehace data/reserve.json (puntuaciones, guías y forever-db; ver tools/reserve.py)")
    ap.add_argument("--reserve-from", help="raíz de donde leer las rutas importadas de Polestar y sus puntuaciones")
    ap.add_argument("--foreverdb", help="carpeta de forever-db para --refresh-reserve (o SENDA_FOREVERDB)")
    ap.add_argument("-q", "--quiet", action="store_true")
    args = ap.parse_args(argv)
    if args.refresh_reserve:
        paths = Paths(args.root)
        try:
            snap = reserve.refresh(paths, args.reserve_from, args.foreverdb)
        except FileNotFoundError as exc:
            print(f"build: {exc}", file=sys.stderr)
            return 1
        reserve.write_snapshot(paths, snap)
        print(f"data/{reserve.RESERVE_FILE}: {len(snap['quests'])} misiones ({', '.join(snap['scores'])})")
    if args.refresh_prereq:
        paths = Paths(args.root)
        pre = foreverdb_prereq(paths.root)
        if pre is None:
            print("build: no hay forever-db en .cache (ejecuta `python tools/fetch_foreverdb.py`).", file=sys.stderr)
            return 1
        write_prereq_snapshot(paths, pre)
        print(f"data/{PREREQ_FILE}: {len(pre['edges'])} requisitos, {len(pre['breadcrumbs'])} migas de pan")
    return build(Paths(args.root), check=args.check, quiet=args.quiet)


if __name__ == "__main__":
    sys.exit(main())

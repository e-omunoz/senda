"""Extrae los hechos de viaje de Polestar (TravelData.lua) a tools/routescore/travel_facts.json.

    python tools/routescore/extract_travel.py <ruta a Polestar>/addon/Polestar/Nav/TravelData.lua

Solo toma hechos: nodos de vuelo (id, continente, coordenadas de mundo, facción, nombre), vuelos
directos (origen, destino, yardas) y transportes (barcos, zepelines, tranvía: extremos, segundos de
viaje y de espera) y portales. No toma nada de los mapas de navegación (ni de Leffe ni de Polestar).

Origen y licencia: Polestar (GPL-3.0, Copyright (c) 2026 The Polestar authors), TravelData.lua generado
desde las tablas del cliente (TaxiNodes, TaxiPath, TaxiPathNode), CMaNGOS classic-db y el modelo de
transportes de CMaNGOS, «after Shortest Path Forever by Cillian Berragan (GPL-3.0-or-later, used with
permission)»; Portions Copyright (C) 2026 Cillian Berragan. Ver THIRD_PARTY.md.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent / "travel_facts.json"


def _block(text: str, name: str) -> str:
    """Cuerpo de `name = { ... }` (primer nivel de llaves, cuidando cadenas)."""
    m = re.search(r"\n\t" + re.escape(name) + r" = \{", text)
    if not m:
        raise ValueError(f"no encuentro el bloque {name}")
    i = m.end()
    depth, in_str = 1, False
    j = i
    while depth:
        c = text[j]
        if in_str:
            if c == "\\":
                j += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        j += 1
    return text[i:j - 1]


def _lua_to_py(src: str):
    """Convierte una tabla Lua de literales (números, cadenas, tablas, claves simples) en Python."""
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[A-Za-z_][A-Za-z0-9_]*|-?\d+(?:\.\d+)?|[{}=,]|\[|\]', src)
    pos = 0

    def value():
        nonlocal pos
        t = tokens[pos]
        if t == "{":
            pos += 1
            arr, obj = [], {}
            while tokens[pos] != "}":
                if pos + 1 < len(tokens) and tokens[pos + 1] == "=" and re.match(r"[A-Za-z_]", tokens[pos]):
                    k = tokens[pos]
                    pos += 2
                    obj[k] = value()
                else:
                    arr.append(value())
                if tokens[pos] == ",":
                    pos += 1
            pos += 1
            if obj and arr:
                obj["_"] = arr
                return obj
            return obj if obj else arr
        pos += 1
        if t.startswith('"'):
            return json.loads(t)
        if t in ("true", "false"):
            return t == "true"
        if t == "nil":
            return None
        return float(t) if "." in t else int(t)

    out = []
    while pos < len(tokens):
        out.append(value())
        if pos < len(tokens) and tokens[pos] == ",":
            pos += 1
    return out


def extract(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    taxi = []
    for row in _lua_to_py(_block(text, "taxi")):
        node = {"id": row[0], "map": row[1], "wx": row[2], "wy": row[3], "faction": row[7], "name": row[8]}
        if len(row) > 9:
            node["class"] = row[9]
        taxi.append(node)
    flat = _lua_to_py(_block(text, "flights"))
    flights = [flat[i:i + 3] for i in range(0, len(flat), 3)]
    transports = []
    for t in _lua_to_py(_block(text, "transports")):
        end = lambda e: {"name": e[0], "map": e[1], "wx": e[2], "wy": e[3]}  # noqa: E731
        transports.append({"id": t["id"], "kind": t["kind"], "faction": t["faction"], "a": end(t["a"]),
                           "b": end(t["b"]), "ab": t["ab"], "ba": t["ba"], "waitA": t["waitA"],
                           "waitB": t["waitB"]})
    portals = []
    for p in _lua_to_py(_block(text, "portals")):
        portals.append({"id": p["id"], "a": {"map": p["a"][1], "wx": p["a"][2], "wy": p["a"][3]},
                        "b": {"map": p["b"][1], "wx": p["b"][2], "wy": p["b"][3]}, "seconds": p["seconds"]})
    commit = None
    try:
        commit = subprocess.run(["git", "-C", str(path.parent), "rev-parse", "HEAD"], capture_output=True,
                                text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    header = "\n".join(line[3:] for line in text.splitlines()[:10] if line.startswith("-- "))
    return {
        "source": f"Polestar {commit or '?'} addon/Polestar/Nav/TravelData.lua",
        "licence": "GPL-3.0 (Polestar); Portions Copyright (C) 2026 Cillian Berragan (Shortest Path Forever, "
                   "GPL-3.0-or-later). Solo hechos: nodos, vuelos, transportes y portales.",
        "upstream_header": header,
        "flight_speed_yd_s": 30,
        "flight_stop_s": 2,
        "taxi": taxi,
        "flights": flights,
        "transports": transports,
        "portals": portals,
    }


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 1:
        print(__doc__)
        return 2
    data = extract(Path(argv[0]))
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"{OUT}: {len(data['taxi'])} nodos, {len(data['flights'])} vuelos, {len(data['transports'])} transportes, "
          f"{len(data['portals'])} portales")
    return 0


if __name__ == "__main__":
    sys.exit(main())

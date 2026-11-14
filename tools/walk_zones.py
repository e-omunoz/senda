#!/usr/bin/env python3
"""Quita del grafo de andar del planificador los pasos entre zonas que el juego no da (docs/TRAVEL.md, «Andar»).

La malla de Senda deja subir casi cualquier ladera de menos de 50°, así que el grafo de `senda-nav walkgraph` cruza
las sierras entre zonas (Elwynn - Las Estepas Ardientes, Dun Morogh - La Garganta de Fuego, Mulgore - Desolace...).
Este paso, después de `walkgraph`:

1. Lee la zona de cada nodo: el área del trozo de terreno (`senda-nav zprof` sobre la rejilla, nav/out/grid) y, si es
   una subzona, la zona de los trozos de terreno que la rodean (la mayoría de su frontera en la rejilla de trozos de
   33 yd de todo el continente; `areas` de walk_zones.json corrige a mano las que votan mal). Sin área: la mayoría de
   sus vecinos del grafo.
2. Quita las aristas entre dos zonas distintas que no estén en `links` de nav/data/walk_zones.json (revisión propia de
   la geografía de Classic).
3. Rehace la matriz de yardas entre lugares: los pares cuyo camino no pasaba por una arista quitada guardan su valor
   exacto; los demás toman el camino por el grafo que queda (null si ya no se llega andando).
4. Guarda en el JSON la zona de cada nodo (`zone`, índice en `meta.zones.names`) para las pruebas sin la rejilla.

Uso (desde la raíz del repo, con la rejilla horneada, ver docs/TRAVEL.md):
    python tools/walk_zones.py                 # data/travel/walk_0.json y walk_1.json en su sitio
    python tools/walk_zones.py --continents 0 -v
"""
from __future__ import annotations

import argparse
import heapq
import json
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


ADT = 1600.0 / 3.0   # yardas de un ADT (forge-navbuild format.rs)
CHUNK = ADT / 16     # un trozo de terreno: 16 x 16 por ADT, cada uno con su área
SEA_CHUNKS = 3000    # un área de más trozos que esto y que no es zona es el mar (The Great Sea, Veiled Sea...)


def zprof(binary: Path, grid: Path, c: int, points: list) -> list[int]:
    """Área del trozo de terreno de cada punto (senda-nav zprof)."""
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "points.txt"
        f.write_text("\n".join(f"p {x:.1f} {y:.1f}" for x, y in points) + "\n", encoding="utf-8")
        out = subprocess.run([str(binary), "zprof", "--grid", str(grid), "--map", str(c), "--file", str(f)],
                             check=True, capture_output=True, text=True, encoding="utf-8").stdout
    areas = [int(line.split()[3]) for line in out.splitlines() if line.strip()]
    if len(areas) != len(points):
        raise SystemExit(f"zprof: {len(areas)} áreas para {len(points)} puntos")
    return areas


def subzone_map(binary: Path, grid: Path, c: int, zones: dict[int, str]) -> tuple[dict[int, str], set[int]]:
    """Zona de cada subzona por la rejilla de trozos de terreno de todo el continente: la de la mayoría de los trozos
    de zona que la rodean (una subzona sin vecinos de zona espera a que los tengan sus vecinas). Las áreas enormes que no
    son zona son el mar: no votan (sus nodos toman la zona de sus vecinos del grafo, ver label)."""
    tiles = sorted({tuple(int(v) for v in p.name.split(".")[0].split("_"))
                    for p in (grid / "tiles" / str(c)).glob("*.nav.gz")})
    keys, points = [], []
    for col, row in tiles:
        for cj in range(16):
            for ci in range(16):
                keys.append((col * 16 + ci, row * 16 + cj))
                points.append(((32 - row) * ADT - (cj + 0.5) * CHUNK, (32 - col) * ADT - (ci + 0.5) * CHUNK))
    area = dict(zip(keys, zprof(binary, grid, c, points)))
    size = Counter(area.values())
    sea = {a for a, k in size.items() if k >= SEA_CHUNKS and a not in zones}  # el mar: ni zona ni voto
    border = defaultdict(Counter)  # subzona -> área vecina -> trozos de frontera
    for (gx, gy), a in area.items():
        if a == 0 or a in zones or a in sea:
            continue
        for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            b = area.get((gx + d[0], gy + d[1]))
            if b and b != a and b not in sea:
                border[a][b] += 1
    out: dict[int, str] = {}
    for _ in range(50):
        # por rondas: votan las zonas y las subzonas de rondas anteriores, no las de esta
        known = dict(out)
        for a, cnt in sorted(border.items()):
            if a in out:
                continue
            votes = Counter()
            for b, k in cnt.items():
                z = zones.get(b) or known.get(b)
                if z:
                    votes[z] += k
            if votes:
                out[a] = sorted(votes.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        if len(out) == len(known):
            break
    return out, sea


def label(nodes: list, edges: list, areas: list[int], zones: dict[int, str], sub: dict[int, str],
          sea: set[int]) -> list[str | None]:
    """Zona de cada nodo: la de su área (zona o subzona); sin área (0) o en el mar, la de la mayoría de sus vecinos del
    grafo (la costa de cada zona es suya: nadar de una costa a otra que no se tocan tampoco vale)."""
    nb = defaultdict(list)
    for a, b, _ in edges:
        if a != b:
            nb[a].append(b)
            nb[b].append(a)
    lab: list[str | None] = [zones.get(a) or sub.get(a) for a in areas]
    for _ in range(50):
        changed = False
        for i in range(len(nodes)):
            if lab[i] is None:
                votes = Counter(lab[j] for j in nb[i] if lab[j] is not None)
                if votes:
                    lab[i] = sorted(votes.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
                    changed = True
        if not changed:
            break
    return lab


def dijkstra(n: int, adj: dict, src: int) -> list[float]:
    dist = [float("inf")] * n
    dist[src] = 0.0
    h = [(0.0, src)]
    while h:
        d, u = heapq.heappop(h)
        if d > dist[u]:
            continue
        for v, y in adj.get(u, ()):
            nd = d + y
            if nd < dist[v]:
                dist[v] = nd
                heapq.heappush(h, (nd, v))
    return dist


def write(path: Path, d: dict) -> None:
    """El mismo formato que senda-nav walkgraph: una fila por línea."""
    j = lambda v: json.dumps(v, ensure_ascii=False, separators=(",", ":"))  # noqa: E731
    s = "{\n"
    s += f' "meta": {j(d["meta"])},\n'
    s += ' "nodes": [\n  ' + ",\n  ".join(j(x) for x in d["nodes"]) + "\n ],\n"
    s += ' "edges": [\n  ' + ",\n  ".join(j(x) for x in d["edges"]) + "\n ],\n"
    s += f' "places": {j(d["places"])},\n'
    s += f' "zone": {j(d["zone"])},\n'
    s += ' "matrix": {\n  "keys": ' + j(d["matrix"]["keys"]) + ',\n  "yards": [\n   '
    s += ",\n   ".join(j(r) for r in d["matrix"]["yards"]) + "\n  ]\n }\n}\n"
    path.write_text(s, encoding="utf-8", newline="\n")


def run(c: int, walk: Path, cfg: dict, binary: Path, grid: Path, verbose: bool) -> None:
    d = json.loads(walk.read_text(encoding="utf-8"))
    nodes, edges = d["nodes"], d["edges"]
    zones = {int(k): v for k, v in cfg["zones"][str(c)].items()}
    links = {frozenset(p) for p in cfg["links"][str(c)]}
    names = sorted(set(zones.values()))
    for z in cfg.get("areas", {}).get(str(c), {}).values():
        if z not in names:
            raise SystemExit(f"walk_zones.json: zona desconocida {z!r}")
    for p in links:
        for z in p:
            if z not in names:
                raise SystemExit(f"walk_zones.json: zona desconocida {z!r} en links[{c}]")
    areas = zprof(binary, grid, c, nodes)
    over = {int(k): v for k, v in cfg.get("areas", {}).get(str(c), {}).items()}
    sub, sea = subzone_map(binary, grid, c, {a: z for a, z in zones.items() if a not in over})
    sub.update(over)
    lab = label(nodes, edges, areas, zones, sub, sea)
    keep, cut = [], Counter()
    for a, b, y in edges:
        za, zb = lab[a], lab[b]
        if za is None or zb is None or za == zb or frozenset((za, zb)) in links:
            keep.append([a, b, y])
        else:
            cut[" - ".join(sorted((za, zb)))] += 1
    n = len(nodes)

    def adjacency(es):
        adj = defaultdict(list)
        for a, b, y in es:
            adj[a].append((b, y))
        return adj

    old_adj, new_adj = adjacency(edges), adjacency(keep)
    keys = d["matrix"]["keys"]
    pnode = [d["places"][k] for k in keys]
    yards = d["matrix"]["yards"]
    changed = lost = 0
    for i, s in enumerate(pnode):
        old_d, new_d = dijkstra(n, old_adj, s), dijkstra(n, new_adj, s)
        for jx, t in enumerate(pnode):
            if i == jx or yards[i][jx] is None:
                continue
            if new_d[t] <= old_d[t] + 0.5:
                continue  # el camino no usaba ninguna arista quitada: el valor exacto sigue
            if new_d[t] == float("inf"):
                yards[i][jx] = None
                lost += 1
            else:
                yards[i][jx] = max(int(round(new_d[t])), yards[i][jx])
                changed += 1
    d["edges"] = keep
    d["zone"] = [names.index(z) if z is not None else -1 for z in lab]
    meta = d["meta"]
    meta["counts"]["edges"] = len(keep)
    prev = meta.get("zones")
    if prev and not cut and prev.get("names") == names:
        pass  # otra pasada sobre un grafo ya podado: nada que quitar, se quedan las cuentas de la primera
    else:
        meta["zones"] = {"file": "nav/data/walk_zones.json", "names": names, "cut_edges": sum(cut.values()),
                         "cut": dict(sorted(cut.items())), "matrix_longer": changed, "matrix_lost": lost}
    write(walk, d)
    print(f"walk_zones {c}: {sum(cut.values())} aristas quitadas entre {len(cut)} pares de zonas; matriz: "
          f"{changed} pares más largos, {lost} sin camino; {sum(1 for z in lab if z is None)} nodos sin zona")
    if verbose:
        for k, v in sorted(cut.items(), key=lambda kv: -kv[1]):
            print(f"  {v:4d}  {k}")
        sub = defaultdict(Counter)
        for i, a in enumerate(areas):
            if a not in zones:
                sub[a][lab[i]] += 1
        for a, cnt in sorted(sub.items()):
            print(f"  área {a}: {dict(cnt)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--continents", default="0,1")
    ap.add_argument("--travel", default=str(ROOT / "data" / "travel"))
    ap.add_argument("--zones", default=str(ROOT / "nav" / "data" / "walk_zones.json"))
    ap.add_argument("--grid", default=str(ROOT / "nav" / "out" / "grid"))
    exe = "senda-nav.exe" if sys.platform == "win32" else "senda-nav"
    ap.add_argument("--senda-nav", default=str(ROOT / "nav" / "target" / "release" / exe))
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    cfg = json.loads(Path(a.zones).read_text(encoding="utf-8"))
    for c in (int(x) for x in a.continents.split(",")):
        run(c, Path(a.travel) / f"walk_{c}.json", cfg, Path(a.senda_nav), Path(a.grid), a.verbose)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Genera data/knowledge/trainer/<clase>.json: lo que enseña cada instructor de clase en Forever, por nivel.

Fuente: `addon/Polestar/QoL/ClassSpells.lua` de Polestar (GPL-3.0), que `forge data classspells` genera de las
listas de entrenamiento de la base de datos de TrinityCore para Forever (advocaite/TrinityCore, rama `forever`,
capturadas del servidor; GPL-2.0, usadas como hechos) y de las tablas SpellName, Spell y SkillLineAbility del
cliente de Forever. Formato por clase:

    "<nivel>=<hechizo>:<coste en cobre>:<rango>[:<rango anterior>[:<máscara de razas>]],...;..."

rango 0: sin rango. Máscara de razas: bit (id de raza - 1) (1 Humano, 2 Orco, 3 Enano, 4 Elfo de la noche,
5 No-muerto, 6 Tauren, 7 Gnomo, 8 Trol); 0 = todas (así lo lee Polestar en QoL/Spells.lua, raceOk).

Con --rewrite reescribe además los [[train]] generados de data/knowledge/<clase>/spells.toml (las clases de
data/knowledge/trainer/policy.json) para la raza del personaje de cada guía, con los nombres esES de
names.esES.json (nav/crates/senda-spellnames) y las decisiones de policy.json (opcionales, talentos de la build,
huecos de la lista). Un [[train]] generado lleva `sources = ["trainer:..."]`; los demás (mascota, misión, talento,
hechizos que no vende el instructor de clase) se escriben a mano, se conservan tal cual y sus hechizos no se
repiten en los generados.

Uso:
    python tools/gen_trainer.py --polestar RUTA/polestar        # el clon de Polestar (raíz del repo)
    python tools/gen_trainer.py --rewrite                       # los spells.toml, con los JSON ya hechos
    python tools/gen_trainer.py ... --check                     # solo dice si cambiaría algo (sale con 1)
Orden completo y política de opcionales: docs/TRAINER.md.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import REPO_ROOT, setup_stdio  # noqa: E402

REL = Path("addon/Polestar/QoL/ClassSpells.lua")
OUT = REPO_ROOT / "data" / "knowledge" / "trainer"
RACES = {1: "Human", 2: "Orc", 3: "Dwarf", 4: "NightElf", 5: "Scourge", 6: "Tauren", 7: "Gnome", 8: "Troll"}
TRAINER_SRC = "trainer:"

_CLASS_RE = re.compile(r'^\s*([A-Z]+)\s*=\s*"([^"]*)"\s*,?\s*$', re.M)
_ENTRY_RE = re.compile(r"^(\d+):(\d+):(\d+):?(\d*):?(\d*)$")
_HEAD_RE = re.compile(r"^\[\[?[^\]]+\]\]?\s*(#.*)?$")
_RANK_RE = re.compile(r"^(?:Rango|Rank)\s+(\d+)$")


# =========================================================================== --polestar
def parse(text: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for cls, body in _CLASS_RE.findall(text):
        rows = []
        for chunk in body.split(";"):
            if not chunk:
                continue
            lvl, _, lst = chunk.partition("=")
            for e in lst.split(","):
                m = _ENTRY_RE.match(e)
                if not m:
                    raise SystemExit(f"{cls}: entrada ilegible {e!r}")
                sid, cost, rank, prev, races = m.groups()
                rows.append({"level": int(lvl), "spell": int(sid), "cost": int(cost), "rank": int(rank),
                             "prev": int(prev or 0), "racemask": int(races or 0)})
        out[cls] = rows
    if not out:
        raise SystemExit("ClassSpells.lua: no hay clases (¿cambió el formato?)")
    return out


def race_ok(mask: int, race_id: int) -> bool:
    return mask == 0 or bool(mask >> (race_id - 1) & 1)


def gen_json(root: Path, check: bool) -> int:
    text = (root / REL).read_text(encoding="utf-8")
    try:
        commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True,
                                check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "desconocido"
    changed = []
    for cls, rows in sorted(parse(text).items()):
        doc = {
            "class": cls,
            "source": f"polestar:{commit}/{REL.as_posix()}",
            "licence": ("Listas de entrenamiento de TrinityCore `forever` (advocaite/TrinityCore, GPL-2.0, capturadas "
                        "del servidor; usadas como hechos) y tablas del cliente de Forever, a través de Polestar "
                        "(GPL-3.0). Regenerar con tools/gen_trainer.py; no editar a mano."),
            "format": "level, spell, cost (cobre), rank (0: sin rango), prev (rango anterior; 0: ninguno), "
                      "racemask (bit id_raza-1; 0: todas)",
            "races": {str(k): v for k, v in RACES.items()},
            "spells": sorted(rows, key=lambda r: (r["level"], r["spell"])),
        }
        body = json.dumps(doc, ensure_ascii=False, indent=1)
        # Una fila por hechizo: legible y con diffs pequeños.
        body = re.sub(r"\{\n\s+(\"level\"[^}]*?)\n\s+\}", lambda m: "{" + re.sub(r"\n\s+", " ", m.group(1)) + "}", body)
        body += "\n"
        f = OUT / f"{cls.lower()}.json"
        old = f.read_text(encoding="utf-8") if f.exists() else None
        if old != body:
            changed.append(f)
            if not check:
                OUT.mkdir(parents=True, exist_ok=True)
                f.write_text(body, encoding="utf-8", newline="\n")
        print(f"{cls:8} {len(rows):4} hechizos, {len({r['level'] for r in rows}):2} niveles")
    print(f"{len(changed)} archivos {'cambiarían' if check else 'escritos'} en {OUT.relative_to(REPO_ROOT).as_posix()}")
    return 1 if check and changed else 0


# =========================================================================== --rewrite
def _q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _arr(xs: list) -> str:
    return "[" + ", ".join(_q(x) if isinstance(x, str) else str(x) for x in xs) + "]"


def _chunks(text: str) -> list[str]:
    """Trozos del TOML: el preámbulo y luego uno por cabecera de tabla ([x] o [[x]]); los comentarios justo
    encima de una cabecera van con ella."""
    out: list[str] = []
    cur: list[str] = []
    for line in text.splitlines(keepends=True):
        if _HEAD_RE.match(line) and cur:
            lead: list[str] = []
            while cur and cur[-1].lstrip().startswith("#"):
                lead.insert(0, cur.pop())
            out.append("".join(cur))
            cur = lead
        cur.append(line)
    if cur:
        out.append("".join(cur))
    return out


def _header(chunk: str) -> str:
    return next((ln.strip() for ln in chunk.splitlines() if ln.strip() and not ln.lstrip().startswith("#")), "")


def _is_train(chunk: str) -> bool:
    return _header(chunk) == "[[train]]"


def _is_generated(chunk: str) -> bool:
    return _is_train(chunk) and re.search(r'^sources\s*=\s*\[\s*"' + TRAINER_SRC, chunk, re.M) is not None


def _label(sid: int, names: dict, row: dict) -> str:
    """«Corrupción (rango 4)»: nombre del cliente y el número de su «Rango N» (sin sufijo en el rango 1)."""
    info = names.get(str(sid))
    if not info:
        return f"#{sid} (sin nombre en el cliente)"
    m = _RANK_RE.match(info.get("rank", ""))
    n = int(m.group(1)) if m else row.get("rank") or 0
    return info["name"] + (f" (rango {n})" if n > 1 else "")


def rewrite_all(check: bool) -> int:
    policy = json.loads((OUT / "policy.json").read_text(encoding="utf-8"))
    names_doc = json.loads((OUT / "names.esES.json").read_text(encoding="utf-8"))
    rc = 0
    for key, pol in policy.items():
        if not key.startswith("_"):
            rc |= rewrite_class(key, pol, names_doc["spells"], names_doc.get("source", ""), check)
    return rc


def rewrite_class(key: str, pol: dict, names: dict, names_src: str, check: bool) -> int:
    doc = json.loads((OUT / f"{key}.json").read_text(encoding="utf-8"))
    commit = doc["source"].split("/")[0].removeprefix("polestar:")[:8]
    src_tag = f"{TRAINER_SRC}polestar-{commit}"
    path = REPO_ROOT / "data" / "knowledge" / key / "spells.toml"
    text = path.read_text(encoding="utf-8")
    chunks = _chunks(text)
    manual_ids: set[int] = set()
    for c in chunks:
        if _is_train(c) and not _is_generated(c):
            manual_ids.update(tomllib.loads(c.replace("[[train]]", "", 1)).get("spells", []))

    rows = [r for r in doc["spells"] if race_ok(r["racemask"], pol["race"]) and r["spell"] not in manual_ids]
    for sid in pol.get("extra", []):
        if sid in manual_ids:
            continue
        lvl = (names.get(str(sid)) or {}).get("level")
        if not lvl:
            raise SystemExit(f"{key}: extra {sid} sin nivel en names.esES.json (pásalo a senda-spellnames)")
        rows.append({"level": lvl, "spell": sid, "cost": None, "rank": 0, "prev": 0, "racemask": 0, "extra": True})
    byid = {r["spell"]: r for r in rows}

    def root(r: dict) -> int:
        """Raíz de la cadena de rangos: el rango más bajo al que se llega por `prev`."""
        seen: set[int] = set()
        while r["prev"] and r["prev"] not in seen:
            seen.add(r["prev"])
            if r["prev"] not in byid:
                return r["prev"]
            r = byid[r["prev"]]
        return r["spell"]

    talents = {int(k): v for k, v in pol.get("talents", {}).items()}
    optional = {int(k): v for k, v in pol.get("optional", {}).items()}
    level_notes = {int(k): v for k, v in pol.get("level_notes", {}).items()}
    req: dict[int, list[dict]] = {}
    opt: list[tuple[int, dict, str]] = []
    moved: dict[int, list[str]] = {}
    for r in sorted(rows, key=lambda r: (r["level"], r["spell"])):
        k = root(r)
        if k in optional or r["spell"] in optional:
            opt.append((r["level"], r, optional.get(k) or optional[r["spell"]]))
        elif talents.get(k) == 0:
            tname = (names.get(str(k)) or {}).get("name", f"#{k}")
            opt.append((r["level"], r, f"Opcional: solo con el talento «{tname}», que esta build no coge."))
        else:
            lvl = r["level"]
            if talents.get(k, 0) > lvl:
                lvl = talents[k]
                moved.setdefault(lvl, []).append(f"{_label(r['spell'], names, r)} lo tiene el instructor al "
                                                 f"{r['level']}, pero pide el talento, que la build coge al {lvl}")
            req.setdefault(lvl, []).append(r)

    gen: list[tuple[int, int, str]] = []  # (nivel, 0 obligatorio / 1 opcional, texto)
    for lvl, rs in req.items():
        lines = ["[[train]]", f"level = {lvl}", f"names = {_arr([_label(r['spell'], names, r) for r in rs])}",
                 f"spells = {_arr([r['spell'] for r in rs])}"]
        if all(r["cost"] is not None for r in rs):
            lines.append(f"cost = {sum(r['cost'] for r in rs)}")
        if any(r.get("extra") for r in rs):
            lines.append('status = "unverified"')
        lines.append(f"sources = {_arr([src_tag, names_src])}")
        notes = [level_notes.get(lvl, "")]
        if lvl in moved:
            notes.append("Rango de talento: " + "; ".join(moved[lvl]) + ".")
        note = " ".join(x for x in notes if x)
        if note:
            lines.append(f"note = {_q(note)}")
        gen.append((lvl, 0, "\n".join(lines) + "\n"))
    for lvl, r, note in opt:
        lines = ["[[train]]", f"level = {lvl}", f"names = {_arr([_label(r['spell'], names, r)])}",
                 f"spells = {_arr([r['spell']])}"]
        if r["cost"] is not None:
            lines.append(f"cost = {r['cost']}")
        lines += ["optional = true", f"sources = {_arr([src_tag, names_src])}", f"note = {_q(note)}"]
        gen.append((lvl, 1, "\n".join(lines) + "\n"))
    gen.sort(key=lambda g: (g[0], g[1]))

    # Los generados van donde estaba el primer [[train]] (o tras el preámbulo); lo demás no se toca.
    kept = [c for c in chunks if not _is_generated(c)]
    first = 1 if len(kept) > 1 else len(kept)  # tras el preámbulo, delante de la primera tabla
    pre = "".join(kept[:first]).rstrip("\n") + "\n\n"
    rest = "".join(kept[first:])
    new = pre + "\n".join(g[2] for g in gen) + ("\n" + rest if rest else "")
    new = re.sub(r"\n{3,}", "\n\n", new)
    tomllib.loads(new)  # sigue siendo TOML válido
    n_req = sum(len(v) for v in req.values())
    n_up = sum(1 for v in req.values() for r in v if r["prev"]) + sum(1 for _, r, _ in opt if r["prev"])
    print(f"{key:8} {len(req):2} niveles, {n_req:3} obligatorios, {len(opt):3} opcionales "
          f"({n_up} subidas de rango); {len(manual_ids)} hechizos a mano")
    if new != text:
        if check:
            print(f"  {path.relative_to(REPO_ROOT).as_posix()} cambiaría")
            return 1
        path.write_text(new, encoding="utf-8", newline="\n")
    return 0


def main() -> int:
    setup_stdio()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--polestar", help="clon de Polestar (raíz del repo): regenera data/knowledge/trainer/<clase>.json")
    ap.add_argument("--rewrite", action="store_true", help="reescribe los [[train]] generados de los spells.toml")
    ap.add_argument("--check", action="store_true", help="no escribe; sale con 1 si algo cambiaría")
    a = ap.parse_args()
    if not a.polestar and not a.rewrite:
        ap.error("di --polestar RUTA, --rewrite o los dos")
    rc = 0
    if a.polestar:
        rc |= gen_json(Path(a.polestar), a.check)
    if a.rewrite:
        rc |= rewrite_all(a.check)
    return rc


if __name__ == "__main__":
    sys.exit(main())

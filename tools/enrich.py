#!/usr/bin/env python3
"""Añade a los pasos datos de juego que el cliente no puede consultar por sí solo.

Hoy: `reqlevel` (nivel mínimo) en:
- pasos `do = "accept"`: nivel para coger la misión, leído de la QuestieDB local;
- pasos `do = "train"`: nivel al que el instructor enseña esos hechizos, sacado de
  data/knowledge/<clase>/spells.toml (el mayor de los hechizos del paso), del `if.minlevel` o, si no hay
  más remedio, del texto del paso («lo del 18», «Nivel 20»...). Es un hecho del juego (como un id), no texto de QuestieDB, así que se puede guardar
en `data/`. El motor lo usa para aplazar las misiones que todavía no puedes coger (exclamación
plateada) y avisarte cuando subes al nivel necesario.

Y `reqskill = [línea, rango]` en pasos `accept` cuya misión pide una profesión (las lecciones
«Camping 101» de oficio exigen saberlo ya): el motor salta el paso si no llegas a ese rango.

Fuente: la QuestieDB local si está instalada; si no, forever-db (`--db`, ver tools/README.md). Con
forever-db no se toca `reqskill` (no tiene ese dato).

Edición mínima por líneas: inserta o actualiza `reqlevel = N` justo después de `quest = X` y respeta
los comentarios y el formato.

    python tools/enrich.py            # aplica los cambios
    python tools/enrich.py --check    # solo informa; sale con 1 si faltan o sobran datos
"""
from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from questiedb import QuestDB  # noqa: E402
from foreverdb import add_db_arguments, missing, open_db  # noqa: E402

STEP_RE = re.compile(r"^\[\[step\]\]\s*$")
TABLE_RE = re.compile(r"^\[")
DO_RE = re.compile(r'^do\s*=\s*"([a-z_]+)"')
QUEST_RE = re.compile(r"^quest\s*=\s*(\d+)")
REQ_RE = re.compile(r"^reqlevel\s*=\s*(\d+)")
SKILL_RE = re.compile(r"^reqskill\s*=")
SPELLS_RE = re.compile(r"^spells\s*=\s*\[([^\]]*)\]")
CLASS_RE = re.compile(r'class\s*=\s*\[\s*"([A-Z]+)"')
MINLEVEL_RE = re.compile(r"minlevel\s*=\s*(\d+)")
TEXT_RE = re.compile(r'^text\s*=\s*"(.*)"')
TIP_RE = re.compile(r'^tip\s*=\s*"(.*)"')
# «3 hechizos hasta el nivel 12: ...» (pasos de entrenamiento generados por tools/gen_horde.py, para las clases sin
# data/knowledge/<clase>/spells.toml).
TIP_LEVEL_RE = re.compile(r"hasta el nivel (\d{1,2})")
TEXT_LEVEL_RE = re.compile(r"(?:lo del|[Nn]ivel|[Ee]ntrena el|[Ee]ntrena del|[Aa]l)\s+(\d{1,2})")

CLASS_DIR = {"WARLOCK": "warlock", "MAGE": "mage", "DRUID": "druid", "WARRIOR": "warrior", "PALADIN": "paladin",
             "HUNTER": "hunter", "ROGUE": "rogue", "PRIEST": "priest", "SHAMAN": "shaman"}


def spell_levels() -> dict[str, dict[int, int]]:
    """clase -> {id de hechizo -> nivel al que se entrena}, desde data/knowledge/<clase>/spells.toml."""
    out: dict[str, dict[int, int]] = {}
    for cls, d in CLASS_DIR.items():
        f = ROOT / "data" / "knowledge" / d / "spells.toml"
        if not f.exists():
            continue
        data = tomllib.loads(f.read_text(encoding="utf-8"))
        m: dict[int, int] = {}
        for tr in data.get("train", []):
            lvl = tr.get("level")
            for sid in tr.get("spells", []) or []:
                if isinstance(sid, int) and isinstance(lvl, int):
                    m[sid] = min(m.get(sid, lvl), lvl)
        out[cls] = m
    return out


def guide_class(path: Path) -> str | None:
    g = path.parent / "guide.toml"
    if path.parent.parent.name != "guides" or not g.exists():
        return None
    classes = tomllib.loads(g.read_text(encoding="utf-8")).get("classes") or []
    return classes[0] if len(classes) == 1 else None


def train_level(block: list[str], cls: str | None, levels: dict[str, dict[int, int]]) -> int | None:
    found: list[int] = []
    for l in block:
        if (m := CLASS_RE.search(l)) and l.startswith("if"):
            cls = m.group(1)
    known = levels.get(cls or "", {})
    for l in block:
        if (m := SPELLS_RE.match(l)):
            for sid in re.findall(r"\d+", m.group(1)):
                if int(sid) in known:
                    found.append(known[int(sid)])
        if l.startswith("if") and (m := MINLEVEL_RE.search(l)):
            found.append(int(m.group(1)))
    if not found:
        for l in block:
            if (m := TEXT_RE.match(l)):
                nums = [int(n) for n in TEXT_LEVEL_RE.findall(m.group(1)) if 2 <= int(n) <= 60]
                if nums:
                    found.append(max(nums))
    if not found:
        for l in block:
            if (m := TIP_RE.match(l)):
                found += [int(n) for n in TIP_LEVEL_RE.findall(m.group(1)) if 2 <= int(n) <= 60]
    lvl = max(found) if found else None
    return lvl if lvl and lvl > 1 else None


def files() -> list[Path]:
    out = sorted((ROOT / "data" / "guides").glob("*/*.toml")) + sorted((ROOT / "data" / "shared").glob("*.toml"))
    return [p for p in out if p.name != "guide.toml"]


def process(path: Path, db: QuestDB, levels: dict[str, dict[int, int]]) -> tuple[str, int]:
    cls = guide_class(path)
    lines = path.read_text(encoding="utf-8").split("\n")
    out: list[str] = []
    changes = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        if not STEP_RE.match(line):
            out.append(line)
            i += 1
            continue
        # bloque del paso: hasta la siguiente tabla
        j = i + 1
        while j < len(lines) and not TABLE_RE.match(lines[j]):
            j += 1
        block = lines[i:j]
        do = next((m.group(1) for l in block if (m := DO_RE.match(l))), None)
        qline = next((k for k, l in enumerate(block) if QUEST_RE.match(l)), None)
        rline = next((k for k, l in enumerate(block) if REQ_RE.match(l)), None)
        want = None
        anchor = qline
        if do == "train":
            want = train_level(block, cls, levels)
            anchor = next((k for k, l in enumerate(block) if DO_RE.match(l)), 0)
        if do == "accept" and qline is not None:
            q = db.quest(int(QUEST_RE.match(block[qline]).group(1)))
            lvl = int(q.get("requiredLevel") or 0) if q else 0
            if lvl > 1:
                want = lvl
        if want is None and rline is not None:
            del block[rline]
            changes += 1
        elif want is not None:
            text = f"reqlevel = {want}"
            if rline is None:
                block.insert(anchor + 1, text)
                changes += 1
            elif block[rline] != text:
                block[rline] = text
                changes += 1
        if do == "accept" and qline is not None and "requiredSkill" not in missing(db):
            # forever-db no tiene la profesión requerida: con ella se deja `reqskill` como esté.
            q = db.quest(int(QUEST_RE.match(block[qline]).group(1)))
            rs = q.get("requiredSkill") if q else None
            sline = next((k for k, l in enumerate(block) if SKILL_RE.match(l)), None)
            want_s = f"reqskill = [{int(rs[0])}, {int(rs[1])}]" if rs and len(rs) >= 2 and rs[0] else None
            if want_s is None and sline is not None:
                del block[sline]
                changes += 1
            elif want_s is not None and sline is None:
                rl = next((k for k, l in enumerate(block) if REQ_RE.match(l)), qline)
                block.insert(rl + 1, want_s)
                changes += 1
            elif want_s is not None and block[sline] != want_s:
                block[sline] = want_s
                changes += 1
        out.extend(block)
        i = j
    return "\n".join(out), changes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="no escribe; sale con 1 si hay cambios pendientes")
    ap.add_argument("--questiedb", help="carpeta de QuestieDB (por defecto, la del juego)")
    add_db_arguments(ap)   # --db auto|questiedb|foreverdb, --foreverdb
    args = ap.parse_args()
    db = open_db(args)
    levels = spell_levels()
    total = 0
    for path in files():
        text, n = process(path, db, levels)
        if n:
            total += n
            rel = path.relative_to(ROOT).as_posix()
            print(f"{'pendiente' if args.check else 'actualizado'}  {rel}: {n} cambio(s)")
            if not args.check:
                path.write_text(text, encoding="utf-8", newline="\n")
    print(f"enrich: {total} cambio(s){' pendientes' if args.check and total else ''}")
    return 1 if args.check and total else 0


if __name__ == "__main__":
    sys.exit(main())

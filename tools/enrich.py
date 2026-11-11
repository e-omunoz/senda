#!/usr/bin/env python3
"""Añade a los pasos datos de juego que el cliente no puede consultar por sí solo.

Hoy: `reqlevel` (nivel mínimo para coger la misión) en los pasos `do = "accept"`, leído de la
QuestieDB local. Es un hecho del juego (como un id), no texto de QuestieDB, así que se puede guardar
en `data/`. El motor lo usa para aplazar las misiones que todavía no puedes coger (exclamación
plateada) y avisarte cuando subes al nivel necesario.

Edición mínima por líneas: inserta o actualiza `reqlevel = N` justo después de `quest = X` y respeta
los comentarios y el formato.

    python tools/enrich.py            # aplica los cambios
    python tools/enrich.py --check    # solo informa; sale con 1 si faltan o sobran datos
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from questiedb import QuestDB  # noqa: E402

STEP_RE = re.compile(r"^\[\[step\]\]\s*$")
TABLE_RE = re.compile(r"^\[")
DO_RE = re.compile(r'^do\s*=\s*"([a-z_]+)"')
QUEST_RE = re.compile(r"^quest\s*=\s*(\d+)")
REQ_RE = re.compile(r"^reqlevel\s*=\s*(\d+)")


def files() -> list[Path]:
    out = sorted((ROOT / "data" / "guides").glob("*/*.toml")) + sorted((ROOT / "data" / "shared").glob("*.toml"))
    return [p for p in out if p.name != "guide.toml"]


def process(path: Path, db: QuestDB) -> tuple[str, int]:
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
                block.insert(qline + 1, text)
                changes += 1
            elif block[rline] != text:
                block[rline] = text
                changes += 1
        out.extend(block)
        i = j
    return "\n".join(out), changes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="no escribe; sale con 1 si hay cambios pendientes")
    ap.add_argument("--questiedb", help="carpeta de QuestieDB (por defecto, la del juego)")
    args = ap.parse_args()
    db = QuestDB.open(args.questiedb)
    total = 0
    for path in files():
        text, n = process(path, db)
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

#!/usr/bin/env python3
"""Descarga de wago.tools las tablas del cliente de Forever que usan las herramientas de profesiones.

    python tools/fetch_wago.py                 # las que falten, en .cache/wago
    python tools/fetch_wago.py --force         # todas de nuevo
    python tools/fetch_wago.py --check         # solo dice cuáles faltan (código 2 si falta alguna)
    python tools/fetch_wago.py --build 1.60.1.70888 --dest RUTA

Las tablas son las del cliente de Forever (producto ``wowf``), build fijada abajo (BUILD) para que los
generadores den siempre los mismos bytes. Cada tabla sale en inglés y, las que llevan nombres, también
en esES (``<Tabla>_esES.csv``). ``.cache/`` está en .gitignore: los volcados en bruto no se commitean;
lo que pase a ``data/`` lo cita como ``wago:<Tabla>@<build>``.

Sin red no falla si ya hay copia: avisa y sale con 0 (con 2 si falta algo).
"""
from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / ".cache" / "wago"
BUILD = "1.60.1.70888"  # cliente de Forever (producto wowf)
UA = "senda-build"
TIMEOUT = 120

# tabla -> ¿también en esES? (solo las que tienen texto traducible)
TABLES = {
    "SkillLine": False,
    "SkillLineAbility": False,
    "SpellReagents": False,
    "SpellEffect": False,
    "SpellName": True,
    "ItemSparse": True,
    "ItemEffect": False,
    "Lock": False,
}


def url_for(table: str, build: str, locale: str | None) -> str:
    u = f"https://wago.tools/db2/{table}/csv?build={build}"
    return u + (f"&locale={locale}" if locale else "")


def wanted() -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    for t, loc in TABLES.items():
        out.append((t, None))
        if loc:
            out.append((t, "esES"))
    return out


def filename(table: str, locale: str | None) -> str:
    return f"{table}_{locale}.csv" if locale else f"{table}.csv"


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--build", default=BUILD)
    ap.add_argument("--dest", default=str(DEST))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    dest = Path(a.dest)
    dest.mkdir(parents=True, exist_ok=True)
    missing = 0
    for table, loc in wanted():
        path = dest / filename(table, loc)
        if path.exists() and path.stat().st_size > 0 and not a.force:
            continue
        if a.check:
            print(f"falta {path.name}")
            missing += 1
            continue
        try:
            data = fetch(url_for(table, a.build, loc))
        except (urllib.error.URLError, OSError) as e:
            print(f"no se pudo bajar {path.name}: {e}", file=sys.stderr)
            missing += 1
            continue
        if not data.startswith(b"ID") and b"," not in data[:400]:
            print(f"respuesta rara para {path.name}; se ignora", file=sys.stderr)
            missing += 1
            continue
        path.write_bytes(data)
        print(f"{path.name}: {len(data) // 1024} KB")
    return 2 if missing else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Descarga a .cache/wago/ las tablas del cliente de Forever que usa tools/gen_professions.py.

Fuente: wago.tools (exportación CSV de las tablas DB2 del cliente). El build está fijado para que la generación sea
reproducible: Forever (producto `wowf`) 1.60.1.70888 y, solo para estimar la habilidad de aprendizaje de las recetas
que ninguna lista de instructor de Forever enseña, Classic Era (`wow_classic_era`) 1.15.9.70576 (su
SkillLineAbility). Al subir de build: cambia BUILD/ERA_BUILD, `python tools/fetch_wago.py --force` y
`python tools/gen_professions.py`, y revisa el diff de data/knowledge/general/professions-*.toml.

.cache/ está en .gitignore: los CSV nunca se commitean (son datos del cliente; Senda solo publica los hechos que
saca de ellos: colores, materiales y nombres de las recetas).

Uso:
    python tools/fetch_wago.py              # descarga lo que falte
    python tools/fetch_wago.py --force      # vuelve a descargar todo
    python tools/fetch_wago.py --out DIR    # otra carpeta (por defecto la de wago_dir())
    python tools/fetch_wago.py --check      # solo dice cuáles faltan (código 2 si falta alguna)

Las usan tools/gen_professions.py (fabricación) y tools/gen_gathering.py (recolección: Lock e ItemSparse_esES).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BUILD = "1.60.1.70888"        # Forever (wowf)
ERA_BUILD = "1.15.9.70576"    # Classic Era: solo SkillLineAbility
URL = "https://wago.tools/db2/{table}/csv?build={build}{locale}"
USER_AGENT = "senda-build"

# (tabla, archivo, build, locale)
TABLES: list[tuple[str, str, str, str]] = [
    ("SkillLine", "SkillLine.csv", BUILD, ""),
    ("SkillLineAbility", "SkillLineAbility.csv", BUILD, ""),
    ("SpellReagents", "SpellReagents.csv", BUILD, ""),
    ("SpellEffect", "SpellEffect.csv", BUILD, ""),
    ("SpellName", "SpellName.csv", BUILD, ""),
    ("SpellName", "SpellName_esES.csv", BUILD, "esES"),
    ("ItemSparse", "ItemSparse.csv", BUILD, ""),
    ("ItemSparse", "ItemSparse_esES.csv", BUILD, "esES"),
    ("Item", "Item.csv", BUILD, ""),
    ("ItemEffect", "ItemEffect.csv", BUILD, ""),
    ("ItemXItemEffect", "ItemXItemEffect.csv", BUILD, ""),
    ("Lock", "Lock.csv", BUILD, ""),
    ("SpellTotems", "SpellTotems.csv", BUILD, ""),
    ("SpellCastingRequirements", "SpellCastingRequirements.csv", BUILD, ""),
    ("SpellFocusObject", "SpellFocusObject.csv", BUILD, ""),
    ("FactionTemplate", "FactionTemplate.csv", BUILD, ""),
    ("SkillLineAbility", "SkillLineAbility_era.csv", ERA_BUILD, ""),
]


def _main_checkout() -> Path | None:
    """Raíz del checkout principal si estamos en un worktree de git (su .cache es la compartida)."""
    git = ROOT / ".git"
    if git.is_file():
        try:
            line = git.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if line.startswith("gitdir:"):
            gitdir = Path(line.split(":", 1)[1].strip())
            # <main>/.git/worktrees/<nombre>
            if gitdir.parent.name == "worktrees":
                return gitdir.parent.parent.parent
    return None


def wago_dir(path: str | os.PathLike | None = None, must_exist: bool = False) -> Path:
    """Carpeta de los CSV: argumento, SENDA_WAGO, <repo>/.cache/wago o la del checkout principal."""
    if path:
        return Path(path)
    env = os.environ.get("SENDA_WAGO")
    if env:
        return Path(env)
    own = ROOT / ".cache" / "wago"
    if (own / "SkillLineAbility.csv").exists() or not must_exist:
        main = _main_checkout()
        if not (own / "SkillLineAbility.csv").exists() and main and (main / ".cache" / "wago" / "SkillLineAbility.csv").exists():
            return main / ".cache" / "wago"
        return own
    main = _main_checkout()
    if main and (main / ".cache" / "wago").is_dir():
        return main / ".cache" / "wago"
    return own


def missing(out: Path) -> list[str]:
    return [f for _, f, _, _ in TABLES if not (out / f).exists()]


def fetch(out: Path, force: bool = False) -> int:
    out.mkdir(parents=True, exist_ok=True)
    errors = 0
    for table, fname, build, locale in TABLES:
        dest = out / fname
        if dest.exists() and dest.stat().st_size > 0 and not force:
            continue
        url = URL.format(table=table, build=build, locale=f"&locale={locale}" if locale else "")
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read()
        except OSError as exc:
            print(f"error: {fname}: {exc}", file=sys.stderr)
            errors += 1
            continue
        if not data.lstrip().startswith(b"ID") and b"," not in data[:200]:
            print(f"error: {fname}: la respuesta no es un CSV", file=sys.stderr)
            errors += 1
            continue
        tmp = dest.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(dest)
        print(f"  {fname}  ({len(data) // 1024} KB, build {build}{' ' + locale if locale else ''})")
        time.sleep(0.5)  # sin prisa: es un servicio gratuito
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", help="carpeta de destino (por defecto .cache/wago)")
    ap.add_argument("--force", action="store_true", help="vuelve a descargar aunque ya estén")
    ap.add_argument("--check", action="store_true", help="no descarga: dice cuáles faltan (código 2 si falta alguna)")
    a = ap.parse_args(argv)
    out = wago_dir(a.out)
    if a.check:
        falta = missing(out)
        for f in falta:
            print(f"falta {f}")
        return 2 if falta else 0
    print(f"wago.tools -> {out} (Forever {BUILD}, Classic Era {ERA_BUILD})")
    return fetch(out, a.force)


if __name__ == "__main__":
    sys.exit(main())

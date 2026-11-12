#!/usr/bin/env python3
"""Pasa a data/locale/<locale>/ los nombres que el cliente dio con `/senda volcar`.

Lee la variable `SendaNamesDB` del archivo de SavedVariables de Senda (la ruta se pasa como argumento; nunca
se adivina la cuenta), y para cada idioma volcado escribe data/locale/<locale>/{quests,npcs,items,spells,maps}.json
con la fuente `ingame:<build>:<fecha>` (la prioridad más alta: sustituye a `senda` y a `polestar-esES`).

Informa de las diferencias con lo que ya había: nombres nuevos, nombres que cambian entre parches (una entrada
`ingame` anterior con otro nombre) y respaldos corregidos (Polestar o tabla propia distintos del cliente).

Los objetos del buscador de objetos (`litem` del volcado: los que no usan las guías, ~5.600 en total) no van a
data/locale/ (eso se compila dentro de Senda y pesaría en cada inicio) sino a data/lookup/locale/<idioma>/items.json,
que tools/build.py compila en el addon bajo demanda Senda_Lookup (addon/Senda_Lookup/Names_<idioma>.lua). El informe
dice cuántos objetos del buscador tienen ya nombre en ese idioma.

Uso:
    python tools/import_names.py "RUTA/WTF/Account/<cuenta>/SavedVariables/Senda.lua"
    python tools/import_names.py RUTA --dry-run          # solo informa
    python tools/import_names.py RUTA --report informe.md
Después: python tools/build.py (compila addon/Senda/Locale/Names_<locale>.lua y addon/Senda_Lookup/Names_<locale>.lua).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import localenames as ln  # noqa: E402
from common import REPO_ROOT, setup_stdio  # noqa: E402
from polestar import luaparse  # noqa: E402

VAR = "SendaNamesDB"
_VAR_RE = re.compile(r"^\s*" + VAR + r"\s*=", re.M)
_BUILD_RE = re.compile(r"^[0-9][0-9A-Za-z.\-]*$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _utf8(v: Any) -> Any:
    """Las cadenas se leyeron byte a byte (latin-1): se recomponen como UTF-8."""
    if isinstance(v, str):
        try:
            return v.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return v
    if isinstance(v, dict):
        return {_utf8(k): _utf8(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_utf8(x) for x in v]
    return v


def read_saved_variables(path: Path) -> dict | None:
    """Devuelve la tabla SendaNamesDB del archivo (o None si no está). No ejecuta Lua."""
    raw = Path(path).read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    text = raw.decode("latin-1")  # sin pérdida: cada byte es un carácter; los escapes \ddd también
    m = _VAR_RE.search(text)
    if not m:
        return None
    value = luaparse.parse_value(text[m.end():])
    value = _utf8(value)
    return value if isinstance(value, dict) else None


def _as_map(v: Any) -> dict:
    if isinstance(v, dict):
        return v
    if isinstance(v, list):  # ids 1..n contiguos: el lector los devuelve como lista
        return {i: x for i, x in enumerate(v, 1)}
    return {}


def dumps_of(db: dict) -> dict[str, dict]:
    """{locale: volcado} con build, fecha y nombres por tipo."""
    out = {}
    for loc, d in _as_map(db.get("locales")).items():
        if isinstance(loc, str) and ln.LOCALE_RE.match(loc) and isinstance(d, dict):
            out[loc] = d
    return out


def source_of(dump: dict, today: str | None = None) -> str:
    build = str(dump.get("build") or "?")
    if not _BUILD_RE.match(build):
        build = "?"
    date = str(dump.get("date") or "")
    if not _DATE_RE.match(date):
        date = today or _dt.date.today().isoformat()
    return f"ingame:{build}:{date}"


def import_dump(data_root: Path, locale: str, dump: dict, write: bool = True,
                today: str | None = None) -> dict:
    """Fusiona un volcado en data/locale/<locale>/. Devuelve el resumen de cambios."""
    source = source_of(dump, today)
    data = ln.load(data_root, locale)
    res: dict[str, Any] = {"locale": locale, "source": source, "new": [], "renamed": [], "fixed": [],
                           "same": 0, "missing": {}, "files": [], "lookup_new": [], "lookup_renamed": [],
                           "lookup_fixed": [], "lookup_same": 0, "lookup_cov": None}
    touched: set[str] = set()
    for kind in ln.CLIENT_KINDS:
        names = _as_map(dump.get(kind))
        for ident in sorted(k for k in names if isinstance(k, int)):
            name = ln.clean_name(names[ident])
            if not name:
                continue
            what, old = ln.merge(data, kind, ident, name, source)
            touched.add(kind)
            if what == "new":
                res["new"].append((kind, ident, name))
            elif what == "same":
                res["same"] += 1
            elif what == "renamed" and old is not None:
                key = "renamed" if str(old.get("source", "")).startswith("ingame:") else "fixed"
                res[key].append((kind, ident, old["name"], old.get("source", ""), name))
        miss = _as_map(_as_map(dump.get("missing")).get(kind))
        n_miss = sum(1 for k, v in miss.items() if isinstance(k, int) and v)
        if n_miss:
            res["missing"][kind] = n_miss
    # Objetos del buscador: data/lookup/locale/<idioma>/items.json (nombres de lo que el cliente ya conocía o dio)
    lookup_root = Path(data_root) / "lookup"
    litems = _as_map(dump.get("litem"))
    lk = ln.load(lookup_root, locale)
    for ident in sorted(k for k in litems if isinstance(k, int)):
        name = ln.clean_name(litems[ident])
        if not name:
            continue
        what, old = ln.merge(lk, "item", ident, name, source)
        if what == "new":
            res["lookup_new"].append(ident)
        elif what == "same":
            res["lookup_same"] += 1
        elif what == "renamed" and old is not None:
            key = "lookup_renamed" if str(old.get("source", "")).startswith("ingame:") else "lookup_fixed"
            res[key].append((ident, old["name"], old.get("source", ""), name))
    lmiss = _as_map(_as_map(dump.get("missing")).get("litem"))
    n_lmiss = sum(1 for k, v in lmiss.items() if isinstance(k, int) and v)
    if n_lmiss:
        res["missing"]["litem"] = n_lmiss
    res["lookup_cov"] = lookup_coverage(Path(data_root), locale, lk, data["item"])
    if write:
        res["files"] = ln.save(data_root, locale, data, kinds=sorted(touched))
        if litems:
            res["files"] += ln.save(lookup_root, locale, lk, kinds=["item"])
    return res


def lookup_coverage(data_root: Path, locale: str, lk: dict | None = None,
                    guide: dict | None = None) -> tuple[int, int] | None:
    """(objetos del buscador con nombre en este idioma, objetos del buscador) o None si no hay data/lookup/items.json.
    Cuenta los nombres de data/lookup/locale (volcados y forever-db) y los de data/locale (objetos de las guías)."""
    f = Path(data_root) / "lookup" / "items.json"
    if not f.is_file():
        return None
    ids = {int(k) for k in json.loads(f.read_text(encoding="utf-8")).get("items", {})}
    if lk is None:
        lk = ln.load(Path(data_root) / "lookup", locale)
    if guide is None:
        guide = ln.load(Path(data_root), locale)["item"]
    named = set(lk["item"]) | set(guide)
    return len(ids & named), len(ids)


def report(results: list[dict], root: Path) -> str:
    lines: list[str] = []
    w = lines.append
    for r in results:
        w(f"## {r['locale']} ({r['source']})")
        w("")
        w(f"- Nuevos: {len(r['new'])}; iguales: {r['same']}; cambios entre parches: {len(r['renamed'])}; "
          f"respaldos corregidos: {len(r['fixed'])}.")
        if r["lookup_new"] or r["lookup_same"] or r["lookup_renamed"] or r["lookup_fixed"]:
            w(f"- Objetos del buscador: nuevos {len(r['lookup_new'])}; iguales {r['lookup_same']}; "
              f"cambios entre parches {len(r['lookup_renamed'])}; respaldos corregidos {len(r['lookup_fixed'])}.")
        if r["lookup_cov"]:
            named, total = r["lookup_cov"]
            w(f"- Cobertura de nombres del buscador en {r['locale']}: {named}/{total} ({100 * named / total:.1f} %).")
        if r["missing"]:
            w("- Sin respuesta del cliente: " + ", ".join(f"{k} {n}" for k, n in sorted(r["missing"].items())) + ".")
        for p in r["files"]:
            try:
                rel = Path(p).resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                rel = Path(p).as_posix()
            w(f"- Escrito {rel}")
        if r["renamed"]:
            w("")
            w("### Cambios de nombre entre parches")
            w("")
            for kind, ident, old, src, new in r["renamed"]:
                w(f"- {kind}:{ident}: «{old}» ({src}) -> «{new}»")
        for key, title in (("lookup_renamed", "Cambios de nombre de objetos del buscador entre parches"),
                           ("lookup_fixed", "Nombres de objetos del buscador que no coincidían con el cliente")):
            if r[key]:
                w("")
                w(f"### {title}")
                w("")
                for ident, old, src, new in r[key]:
                    w(f"- item:{ident}: «{old}» ({src}) -> «{new}»")
        if r["fixed"]:
            w("")
            w("### Respaldos que no coincidían con el cliente")
            w("")
            for kind, ident, old, src, new in r["fixed"]:
                w(f"- {kind}:{ident}: «{old}» ({src}) -> «{new}»")
        w("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    setup_stdio()
    ap = argparse.ArgumentParser(description="Importa SendaNamesDB (de /senda volcar) a data/locale/.")
    ap.add_argument("savedvariables", help="archivo SavedVariables de Senda (WTF/Account/<cuenta>/SavedVariables/Senda.lua)")
    ap.add_argument("--locale", action="append", help="solo este idioma (se puede repetir)")
    ap.add_argument("--root", help="raíz del repositorio (por defecto, este)")
    ap.add_argument("--report", help="escribe además el informe en este archivo Markdown")
    ap.add_argument("--dry-run", action="store_true", help="no escribe; solo informa")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve() if args.root else REPO_ROOT
    path = Path(args.savedvariables)
    if not path.is_file():
        print(f"import_names: no existe {path}", file=sys.stderr)
        return 1
    try:
        db = read_saved_variables(path)
    except luaparse.LuaParseError as exc:
        print(f"import_names: {path} no se puede leer: {exc}", file=sys.stderr)
        return 1
    if db is None:
        print(f"import_names: {path} no tiene {VAR} (¿has hecho /senda volcar y salido del juego?)", file=sys.stderr)
        return 1
    dumps = dumps_of(db)
    if args.locale:
        dumps = {k: v for k, v in dumps.items() if k in args.locale}
    if not dumps:
        print("import_names: el volcado no tiene ningún idioma con nombres", file=sys.stderr)
        return 1
    results = [import_dump(root / "data", loc, dumps[loc], write=not args.dry_run) for loc in sorted(dumps)]
    text = report(results, root)
    print(text, end="")
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8")
    if not args.dry_run:
        print("Siguiente paso: python tools/build.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Compila data/ (TOML) a Lua para el addon.

Genera:
  addon/Senda/Guides/<guide-id>.lua   secciones propias de la guía + RegisterGuide
  addon/Senda/Guides/Shared.lua       secciones de data/shared usadas por alguna guía (una vez cada una)
  addon/Senda/Guides/Guides.xml
  addon/Senda/Knowledge/<carpeta>.lua una por carpeta de data/knowledge (warlock, mage, general...)
  addon/Senda/Knowledge/Knowledge.xml
Y estampa la versión de VERSION en la línea `## Version:` de Senda.toc.

Uso:
    python tools/build.py             # valida y genera
    python tools/build.py --check     # no escribe; falla si lo generado difiere de lo que hay en disco
    python tools/build.py --root RUTA # otra raíz (fixtures)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    GENERATED_HEADER, Paths, read_version, setup_stdio, to_lua, write_text_lf,
)
import validate  # noqa: E402

# Campos que no viajan al addon.
STRIP_GUIDE = {"sources", "checked", "note"}
STRIP_KNOWLEDGE = {"sources", "checked"}  # en conocimiento `note` es texto visible (talentos, macros...)

SECTION_ORDER = ["id", "title", "levels", "map", "summary", "link", "if", "steps"]
GUIDE_ORDER = ["id", "title", "summary", "faction", "races", "classes", "levels", "order", "icon",
               "link", "author", "status", "sections"]
# Orden de claves de un paso en el Lua (como en el contrato de docs/ARCHITECTURE.md);
# las claves no listadas van al final en el orden del esquema.
STEP_ORDER = ["id", "do", "quest", "quests", "obj", "npc", "item", "count", "spells", "level", "prof", "skill",
              "at", "wps", "radius", "node", "zone", "if", "optional", "chain", "text", "tip", "link", "status"]
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


def _lua_file(source: str, body: list[str]) -> str:
    head = [f"-- {GENERATED_HEADER}", f"-- Fuente: {source}", "local _, Senda = ..."]
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


def render(ds: validate.Dataset) -> dict[Path, str]:
    """Devuelve {ruta: contenido} de todo lo generado. Determinista."""
    paths = ds.paths
    step_order = _step_order(paths)
    out: dict[Path, str] = {}

    # --- guías
    shared_used: dict[str, validate.Section] = {}
    guide_files: list[str] = []
    for g in sorted(ds.guides, key=lambda g: g.data["id"]):
        body = []
        for sec in g.sections:
            if sec.shared:
                shared_used.setdefault(sec.key, sec)
            else:
                body.append(_section_table(sec, step_order))
        gd = _strip(g.data, STRIP_GUIDE)
        gd["sections"] = [s.id for s in g.sections]
        body.append(f"Senda.Guides:RegisterGuide({to_lua(gd, key_order=GUIDE_ORDER, multiline=True)})")
        name = f"{g.data['id']}.lua"
        out[paths.out_guides / name] = _lua_file(paths.rel(g.dir) + "/", body)
        guide_files.append(name)

    xml_files = []
    if shared_used:
        body = [_section_table(sec, step_order) for _, sec in sorted(shared_used.items())]
        out[paths.out_guides / "Shared.lua"] = _lua_file("data/shared/", body)
        xml_files.append("Shared.lua")
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

    outputs = render(ds)
    changed: list[str] = []
    for path, text in sorted(outputs.items()):
        data = text.encode("utf-8")
        if not path.exists() or path.read_bytes() != data:
            changed.append(paths.rel(path))
            if not check:
                write_text_lf(path, text)

    # Archivos generados que ya no corresponden a nada (solo los que llevan nuestra cabecera).
    stale: list[str] = []
    for d in (paths.out_guides, paths.out_knowledge):
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
    ap.add_argument("-q", "--quiet", action="store_true")
    args = ap.parse_args(argv)
    return build(Paths(args.root), check=args.check, quiet=args.quiet)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Empaquetado e instalación de desarrollo de Senda.

    python tools/package.py                         # dist/Senda-<versión>.zip (carpeta Senda/ en la raíz del zip)
    python tools/package.py --changelog 0.1.0       # imprime la sección de CHANGELOG.md de esa versión
    python tools/package.py --install-dev --target "C:/.../_forever_/Interface/AddOns"

`--install-dev` copia addon/Senda a <target>/Senda. Por seguridad:
  - exige --target explícito (no hay ruta por defecto);
  - el destino debe existir y llamarse AddOns (salvo --allow-any-dir);
  - solo crea/reemplaza <target>/Senda; nunca toca otras carpetas;
  - se niega si <target>/Senda existe y no es una instalación de Senda (sin Senda.toc),
    o si es un enlace simbólico/unión (podría apuntar al repo).
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import Paths, read_version, setup_stdio  # noqa: E402

ADDON_NAME = "Senda"
# Fecha fija en las entradas del zip: el paquete es reproducible.
ZIP_DATE = (2026, 1, 1, 0, 0, 0)

EXCLUDE_DIRS = {"tests", "test", "__pycache__", "node_modules"}
EXCLUDE_SUFFIXES = {".bak", ".tmp", ".orig", ".rej", ".swp", ".psd", ".xcf", ".kra", ".py", ".pyc", ".log"}
EXCLUDE_NAMES = {"Thumbs.db", "desktop.ini", ".DS_Store"}


def is_dev_file(rel: Path) -> bool:
    for part in rel.parts[:-1]:
        if part.startswith(".") or part in EXCLUDE_DIRS:
            return True
    name = rel.name
    return (name.startswith(".") or name in EXCLUDE_NAMES or name.endswith("~")
            or Path(name).suffix.lower() in EXCLUDE_SUFFIXES)


def addon_files(addon_dir: Path) -> list[Path]:
    files = []
    for p in sorted(addon_dir.rglob("*"), key=lambda x: x.relative_to(addon_dir).as_posix()):
        if p.is_file() and not is_dev_file(p.relative_to(addon_dir)):
            files.append(p)
    return files


def toc_version(paths: Paths) -> str | None:
    if not paths.toc.exists():
        return None
    m = re.search(r"^## Version:\s*(\S+)", paths.toc.read_text(encoding="utf-8-sig"), re.MULTILINE)
    return m.group(1) if m else None


def make_zip(paths: Paths, out_dir: Path | None = None) -> Path:
    version = read_version(paths)
    if not paths.toc.exists():
        raise SystemExit(f"package: falta {paths.rel(paths.toc)}")
    for needed in (paths.out_guides / "Guides.xml", paths.out_knowledge / "Knowledge.xml"):
        if not needed.exists():
            raise SystemExit(f"package: falta {paths.rel(needed)}; ejecuta antes tools/build.py")
    tv = toc_version(paths)
    if tv != version:
        raise SystemExit(f"package: el .toc dice {tv!r} y VERSION {version!r}; ejecuta tools/build.py")

    out_dir = out_dir or paths.dist
    out_dir.mkdir(parents=True, exist_ok=True)
    zpath = out_dir / f"{ADDON_NAME}-{version}.zip"
    files = addon_files(paths.addon)
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for p in files:
            arc = f"{ADDON_NAME}/{p.relative_to(paths.addon).as_posix()}"
            info = zipfile.ZipInfo(arc, date_time=ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, p.read_bytes())
        # GPL-3: la licencia y los créditos de terceros viajan dentro del paquete.
        for extra in ("LICENSE", "THIRD_PARTY.md"):
            src = paths.root / extra
            if src.exists():
                info = zipfile.ZipInfo(f"{ADDON_NAME}/{extra}", date_time=ZIP_DATE)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                zf.writestr(info, src.read_bytes())
    print(f"package: {paths.rel(zpath)} ({len(files)} archivos, {zpath.stat().st_size} bytes)")
    return zpath


def changelog_section(paths: Paths, version: str) -> str:
    """Sección '## [x.y.z]' o '## x.y.z' de CHANGELOG.md, sin el título."""
    cl = paths.root / "CHANGELOG.md"
    if not cl.exists():
        return f"Senda {version}"
    lines = cl.read_text(encoding="utf-8").splitlines()
    head = re.compile(r"^##\s+\[?v?" + re.escape(version) + r"\]?(\s|$)")
    out: list[str] = []
    inside = False
    for line in lines:
        if line.startswith("## "):
            if inside:
                break
            inside = bool(head.match(line))
            continue
        if inside:
            out.append(line)
    text = "\n".join(out).strip()
    return text or f"Senda {version}"


def _is_link(p: Path) -> bool:
    if p.is_symlink():
        return True
    is_junction = getattr(p, "is_junction", None)
    return bool(is_junction and is_junction())


def install_dev(paths: Paths, target: str, allow_any_dir: bool = False) -> int:
    tgt = Path(target).expanduser()
    if not tgt.is_absolute():
        print("install-dev: --target debe ser una ruta absoluta a la carpeta AddOns", file=sys.stderr)
        return 2
    if not tgt.is_dir():
        print(f"install-dev: {tgt} no existe o no es una carpeta; no se crea nada", file=sys.stderr)
        return 2
    if tgt.name.lower() == ADDON_NAME.lower():
        print("install-dev: --target debe ser la carpeta AddOns, no la propia carpeta Senda", file=sys.stderr)
        return 2
    if tgt.name.lower() != "addons" and not allow_any_dir:
        print(f"install-dev: {tgt} no se llama 'AddOns'; usa --allow-any-dir si es intencionado", file=sys.stderr)
        return 2
    src = paths.addon.resolve()
    if not (src / "Senda.toc").exists():
        print(f"install-dev: no existe {src / 'Senda.toc'}", file=sys.stderr)
        return 1

    dest = tgt / ADDON_NAME
    if _is_link(dest):
        print(f"install-dev: {dest} es un enlace/unión; se deja como está (bórralo tú si quieres copiar)",
              file=sys.stderr)
        return 1
    if dest.exists():
        if not dest.is_dir() or not (dest / "Senda.toc").exists():
            print(f"install-dev: {dest} existe pero no parece Senda (sin Senda.toc); no se toca", file=sys.stderr)
            return 1
        rdest = dest.resolve()
        if rdest == src or src in rdest.parents or rdest in src.parents:
            print(f"install-dev: {dest} se solapa con el repositorio; no se toca", file=sys.stderr)
            return 1

    # Solo se toca <target>/Senda: se vacía (era Senda, comprobado arriba) y se copia de nuevo.
    files = addon_files(src)
    if dest.exists():
        shutil.rmtree(dest)
    for p in files:
        d = dest / p.relative_to(src)
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, d)
    print(f"install-dev: {len(files)} archivos copiados a {dest}")
    return 0


def main(argv: list[str] | None = None) -> int:
    setup_stdio()
    ap = argparse.ArgumentParser(description="Empaqueta Senda o lo instala para desarrollo.")
    ap.add_argument("--root", help="raíz alternativa (por defecto, el repo)")
    ap.add_argument("--out", help="carpeta de salida del zip (por defecto dist/)")
    ap.add_argument("--changelog", metavar="VERSION", help="imprime la sección del CHANGELOG y sale")
    ap.add_argument("--install-dev", action="store_true", help="copia addon/Senda a --target/Senda")
    ap.add_argument("--target", help="ruta ABSOLUTA de la carpeta Interface/AddOns (obligatoria con --install-dev)")
    ap.add_argument("--allow-any-dir", action="store_true", help="permite un --target que no se llame AddOns")
    args = ap.parse_args(argv)
    paths = Paths(args.root)

    if args.changelog:
        print(changelog_section(paths, args.changelog.lstrip("v")))
        return 0
    if args.install_dev:
        if not args.target:
            print("install-dev: falta --target <ruta a Interface/AddOns>. No hay ruta por defecto.", file=sys.stderr)
            return 2
        return install_dev(paths, args.target, args.allow_any_dir)
    if args.target:
        print("--target solo se usa con --install-dev", file=sys.stderr)
        return 2
    make_zip(paths, Path(args.out) if args.out else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())

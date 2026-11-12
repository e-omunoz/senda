#!/usr/bin/env python3
"""Descarga la versión fijada de forever-db (datos abiertos de Polestar) en .cache/foreverdb.

    python tools/fetch_foreverdb.py                  # versión de tools/foreverdb/PIN, desde GitHub
    python tools/fetch_foreverdb.py --from RUTA      # copia una carpeta forever-db/ o un .zip local
    python tools/fetch_foreverdb.py --latest         # solo dice cuál es la última data-v* publicada
    python tools/fetch_foreverdb.py --check          # comprueba la copia de .cache sin descargar

El release se etiqueta ``data-v<versión>`` en fitzforge/polestar y trae ``forever-db-<versión>.zip``
y ``SHA256SUMS``. Se comprueba el sha256 del zip (SHA256SUMS) y el de cada tabla contra su
``datapackage.json``, y se extrae en ``.cache/foreverdb`` (ignorada por git). Sin red no falla: avisa
y sale con 0 si ya hay una copia válida (o con 2 si no la hay).

forever-db es GPL-3.0 (tablas) y CC BY 4.0 (su capa propia): ver THIRD_PARTY.md.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIN_FILE = ROOT / "tools" / "foreverdb" / "PIN"
DEST = ROOT / ".cache" / "foreverdb"
UA = "senda-fetch-foreverdb"
TIMEOUT = 60


def read_pin(path: Path = PIN_FILE) -> dict:
    pin = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if "=" in line:
            k, v = line.split("=", 1)
            pin[k.strip()] = v.strip().strip('"')
    if not pin.get("version") or not pin.get("repo"):
        raise SystemExit(f"{path}: faltan `repo` o `version`")
    return pin


def _get(url: str) -> bytes:
    headers = {"User-Agent": UA, "Accept": "application/octet-stream"}
    if url.startswith("https://api.github.com/"):
        headers["Accept"] = "application/vnd.github+json"
        tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if tok:
            headers["Authorization"] = f"Bearer {tok}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT) as r:
        return r.read()


def latest_release(repo: str) -> str | None:
    """Versión de la data-v* más reciente publicada (no borrador), o None."""
    rels = json.loads(_get(f"https://api.github.com/repos/{repo}/releases?per_page=100"))
    versions = [r["tag_name"][len("data-v"):] for r in rels
                if r.get("tag_name", "").startswith("data-v") and not r.get("draft")]
    return max(versions, key=version_key) if versions else None


def version_key(v: str) -> tuple:
    return tuple(int(p) if p.isdigit() else 0 for p in v.split("."))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_tree(root: Path, want_version: str | None = None) -> list[str]:
    """Errores de una carpeta forever-db: versión y sha256/bytes de cada recurso de datapackage.json."""
    errs = []
    dp = root / "datapackage.json"
    if not dp.exists():
        return [f"falta {dp}"]
    pkg = json.loads(dp.read_text(encoding="utf-8"))
    if want_version and pkg.get("version") != want_version:
        errs.append(f"versión {pkg.get('version')} y PIN dice {want_version}")
    for res in pkg.get("resources", []):
        path = root / res["path"]
        if not path.exists():
            errs.append(f"falta {res['path']}")
            continue
        data = path.read_bytes()
        algo, _, want = str(res.get("hash", "")).partition(":")
        if algo != "sha256" or not want:
            errs.append(f"{res['path']}: sin hash sha256 en datapackage.json")
        elif sha256(data) != want:
            errs.append(f"{res['path']}: sha256 no coincide")
        if res.get("bytes") is not None and len(data) != res["bytes"]:
            errs.append(f"{res['path']}: {len(data)} bytes, datapackage.json dice {res['bytes']}")
    return errs


def _package_root(base: Path) -> Path:
    """La carpeta con datapackage.json dentro de lo extraído (el zip puede traer forever-db/ o no)."""
    if (base / "datapackage.json").exists():
        return base
    hits = sorted(base.glob("*/datapackage.json")) + sorted(base.glob("*/*/datapackage.json"))
    if not hits:
        raise SystemExit("el paquete no contiene datapackage.json")
    return hits[0].parent


def _safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    dest = dest.resolve()
    for m in zf.infolist():
        target = (dest / m.filename).resolve()
        if dest != target and dest not in target.parents:
            raise SystemExit(f"ruta peligrosa en el zip: {m.filename}")
    zf.extractall(dest)


def install(src_root: Path, version: str, dest: Path = DEST) -> None:
    """Comprueba ``src_root`` y lo copia a ``dest`` (sustituye la copia anterior)."""
    errs = verify_tree(src_root, version)
    if errs:
        raise SystemExit("forever-db no válida:\n  " + "\n  ".join(errs))
    tmp = dest.with_name(dest.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    shutil.copytree(src_root, tmp, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    if dest.exists():
        shutil.rmtree(dest)
    tmp.rename(dest)
    idx = json.loads((dest / "index.json").read_text(encoding="utf-8")) if (dest / "index.json").exists() else {}
    print(f"forever-db {version} lista en {dest.relative_to(ROOT) if dest.is_relative_to(ROOT) else dest} "
          f"(cliente {idx.get('clientBuild')}, commit {str(idx.get('producerCommit'))[:10]})")


def from_zip_bytes(data: bytes, version: str, dest: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="foreverdb-") as td:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            _safe_extract(zf, Path(td))
        install(_package_root(Path(td)), version, dest)


def download(repo: str, version: str, dest: Path) -> int:
    base = f"https://github.com/{repo}/releases/download/data-v{version}"
    name = f"forever-db-{version}.zip"
    try:
        data = _get(f"{base}/{name}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"No se pudo descargar {base}/{name}: {e}", file=sys.stderr)
        if not verify_tree(dest, version):
            print(f"Se sigue con la copia que ya hay en {dest} (forever-db {version}).", file=sys.stderr)
            return 0
        print("Sin red y sin copia válida: verify/enrich/lookup no tendrán forever-db. Prueba más tarde "
              "o usa --from con una carpeta forever-db/ local.", file=sys.stderr)
        return 2
    try:
        sums = _get(f"{base}/SHA256SUMS").decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"Aviso: sin SHA256SUMS ({e}); se comprueban solo las tablas.", file=sys.stderr)
        sums = ""
    want = next((ln.split()[0] for ln in sums.splitlines() if ln.split()[-1:] == [name]
                 or ln.split()[-1:] == [f"*{name}"]), None)
    if sums and not want:
        raise SystemExit(f"SHA256SUMS no lista {name}")
    if want and sha256(data) != want:
        raise SystemExit(f"{name}: sha256 no coincide con SHA256SUMS")
    from_zip_bytes(data, version, dest)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from", dest="src", help="carpeta forever-db/ o forever-db-<versión>.zip local")
    ap.add_argument("--dest", default=str(DEST), help="destino (por defecto .cache/foreverdb)")
    ap.add_argument("--version", help="otra versión en vez de la de PIN")
    ap.add_argument("--latest", action="store_true", help="imprime la última data-v* publicada y sale")
    ap.add_argument("--check", action="store_true", help="solo comprueba la copia de --dest")
    ap.add_argument("--force", action="store_true", help="descarga aunque ya esté la versión fijada")
    args = ap.parse_args(argv)
    pin = read_pin()
    version = args.version or pin["version"]
    dest = Path(args.dest).resolve()

    if args.latest:
        try:
            latest = latest_release(pin["repo"])
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"No se pudo consultar GitHub: {e}", file=sys.stderr)
            return 2
        print(f"fijada {pin['version']} · última {latest or '(ninguna)'}")
        return 0
    if args.check:
        errs = verify_tree(dest, version)
        for e in errs:
            print(f"ERROR {e}")
        print(f"forever-db {version} en {dest}: {'OK' if not errs else f'{len(errs)} error(es)'}")
        return 1 if errs else 0
    if args.src:
        src = Path(args.src)
        if src.is_file() and src.suffix == ".zip":
            from_zip_bytes(src.read_bytes(), version, dest)
        else:
            install(_package_root(src), version, dest)
        return 0
    if not args.force and not verify_tree(dest, version):
        print(f"forever-db {version} ya está en {dest} (usa --force para descargarla otra vez)")
        return 0
    return download(pin["repo"], version, dest)


if __name__ == "__main__":
    sys.exit(main())

"""Herramientas locales que el harness expone al modelo o usa para confirmar evidencia.

Todas llaman a los scripts de tools/ por subproceso y solo si existen (los mantienen otros equipos):
  - tools/lookup.py  (QuestieDB local, `python tools/lookup.py quest <id> --json`)
  - tools/verify.py  (comprobaciones deterministas contra QuestieDB)
  - tools/validate.py, tools/build.py (antes de abrir un PR)
Las observaciones de juego se leen directamente de data/observations/*.json.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from . import config
from .config import ROOT, TOOLS, rel

LOOKUP_KINDS = ("quest", "npc", "item", "object")   # subcomandos de tools/lookup.py
_REF = re.compile(r"^(questie|obs):([a-z_]+)/(\d+)$")


def tool_exists(name: str) -> bool:
    return (TOOLS / name).is_file()


def run_tool(name: str, *args: str, timeout: int = 300) -> tuple[int, str, str]:
    if not tool_exists(name):
        return 127, "", f"tools/{name} no existe todavía"
    p = subprocess.run([sys.executable, str(TOOLS / name), *args], cwd=ROOT, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=timeout)
    return p.returncode, p.stdout, p.stderr


@lru_cache(maxsize=2048)
def lookup(kind: str, ident: int) -> tuple[bool, str]:
    """(encontrado, salida). `encontrado` es False si la herramienta falta, falla o dice que no existe."""
    if kind not in LOOKUP_KINDS:
        return False, f"tipo no soportado: {kind}"
    rc, out, err = run_tool("lookup.py", kind, str(int(ident)), "--json", timeout=120)
    if rc != 0:
        return False, (err or out or f"lookup.py salió con {rc}").strip()[:2000]
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return bool(out.strip()), out.strip()[:8000]
    found = bool(data)
    if isinstance(data, dict) and (data.get("found") is False or "error" in data):
        found = False
    return found, json.dumps(data, ensure_ascii=False)[:8000]


def parse_ref(ref: str) -> tuple[str, str, int] | None:
    """'questie:quest/179' -> ('questie', 'quest', 179); 'obs:accept/179' -> ('obs', 'accept', 179)."""
    m = _REF.match((ref or "").strip())
    if not m:
        return None
    return m.group(1), m.group(2), int(m.group(3))


def _iter_observations():
    d = config.DATA / "observations"
    if not d.is_dir():
        return
    for f in sorted(d.rglob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        stack = [data]
        while stack:
            x = stack.pop()
            if isinstance(x, dict):
                if "kind" in x:
                    yield f, x
                stack.extend(v for v in x.values() if isinstance(v, (dict, list)))
            elif isinstance(x, list):
                stack.extend(x)


def observations(kind: str, ident: int, limit: int = 20) -> list[dict]:
    """Observaciones de juego (`SendaRecorderDB` ingerido) que mencionan ese id.

    kind: accept | turnin | npc_seen | fp | bind | quest (cualquiera con ese quest) | npc
    """
    out = []
    for f, o in _iter_observations():
        if kind in ("quest", "npc"):
            if o.get(kind) == ident:
                out.append({**o, "_file": rel(f)})
        elif o.get("kind") == kind and (o.get("quest") == ident or o.get("npc") == ident):
            out.append({**o, "_file": rel(f)})
        if len(out) >= limit:
            break
    return out


def verify_report(guide: str | None = None) -> dict | list | None:
    """Salida JSON de tools/verify.py si existe (opcional)."""
    if not tool_exists("verify.py"):
        return None
    args = ["--json", "--no-report"] + (["--guide", guide] if guide else [])
    if config.DATA.resolve() != (ROOT / "data").resolve():
        args += ["--root", str(config.DATA.parent)]
    rc, out, err = run_tool("verify.py", *args, timeout=600)
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"error": (err or out)[:2000], "exit": rc}


def verify_verdicts(report) -> dict[str, str]:
    """step_id -> confirm | conflict | unknown, de la salida JSON de verify.py."""
    out: dict[str, str] = {}
    if isinstance(report, dict):
        for r in report.get("results", []) or []:
            if isinstance(r, dict) and isinstance(r.get("step"), str):
                out[r["step"]] = str(r.get("verdict", "unknown"))
    return out


def findings_for_steps(report, step_ids: set[str], limit_chars: int = 12000) -> str:
    """Filtra la salida de verify.py a las entradas que mencionan los pasos dados (formato libre)."""
    if report is None:
        return "(tools/verify.py no disponible)"
    hits = []

    def walk(x):
        if isinstance(x, dict):
            sid = x.get("step") or x.get("step_id") or x.get("id")
            if isinstance(sid, str) and sid in step_ids:
                hits.append(x)
                return
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(report)
    if not hits:
        if isinstance(report, dict) and "error" in report:
            return f"(verify.py falló: {report['error'][:500]})"
        return "(verify.py no informa nada sobre estos pasos)"
    return json.dumps(hits, ensure_ascii=False, indent=1)[:limit_chars]


def guide_paths() -> list[Path]:
    d = config.DATA / "guides"
    return sorted(d.glob("*/guide.toml")) if d.is_dir() else []

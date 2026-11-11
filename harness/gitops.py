"""Apertura del PR (solo CI o con --open-pr). Nunca empuja a main ni fusiona.

Pasos: validate.py -> build.py -> rama harness/<fecha>-<n> -> commit -> push de la rama -> gh pr create.
Si CI ha continuado la rama de un PR del harness que sigue abierto, se añade un commit y se actualiza ese PR
(un único PR «rodante» en vez de uno por día).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .config import ROOT, rel
from .localtools import run_tool, tool_exists

PROTECTED = {"main", "master"}
PATHS = ["data", "addon/Senda/Guides", "addon/Senda/Knowledge", "harness/state", "harness/reports"]


class GitError(Exception):
    pass


def _run(*cmd: str, check: bool = True) -> str:
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and p.returncode != 0:
        raise GitError(f"{' '.join(cmd)}: {p.stderr.strip() or p.stdout.strip()}")
    return p.stdout.strip()


def preflight(out=sys.stdout) -> list[str]:
    """Ejecuta validate.py y build.py si existen. Devuelve la lista de fallos."""
    fails = []
    for name in ("validate.py", "build.py"):
        if not tool_exists(name):
            out.write(f"[pr] tools/{name} no existe; se omite\n")
            continue
        rc, so, se = run_tool(name, timeout=900)
        out.write(f"[pr] tools/{name}: {'OK' if rc == 0 else f'FALLO ({rc})'}\n")
        if rc != 0:
            fails.append(f"tools/{name} ({rc}):\n{(se or so)[-3000:]}")
    return fails


def _body_file(report: Path) -> Path:
    body = report.read_text(encoding="utf-8")
    if len(body) > 60000:   # límite de GitHub para el cuerpo del PR
        body = body[:60000] + f"\n\n…(recortado; informe completo en `{rel(report)}`)\n"
    f = ROOT / ".cache" / "harness" / "pr-body.md"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(body, encoding="utf-8")
    return f


def _open_pr_for(branch: str) -> str:
    """URL del PR abierto cuya rama es `branch` ('' si no hay)."""
    try:
        return _run("gh", "pr", "view", branch, "--json", "url,state", "-q",
                    'select(.state == "OPEN") | .url')
    except GitError:
        return ""


def open_pr(report: Path, title: str, *, base: str = "main", label: str = "harness", out=sys.stdout) -> str:
    """Abre un PR nuevo o actualiza el PR abierto de la rama actual. Devuelve su URL ('' si no hay cambios)."""
    fails = preflight(out)
    if fails:
        raise GitError("validación o build fallidos; no se abre el PR:\n" + "\n".join(fails))
    status = _run("git", "status", "--porcelain", "--untracked-files=all", "--", *PATHS)
    if not status:
        out.write("[pr] no hay cambios que proponer\n")
        return ""
    current = _run("git", "rev-parse", "--abbrev-ref", "HEAD")
    existing = _open_pr_for(current) if current.startswith("harness/") else ""
    if existing:
        branch = current
    else:
        run_id = os.environ.get("GITHUB_RUN_ID", "")
        branch = f"harness/{report.stem}" + (f"-{run_id}" if run_id else "")
        _run("git", "checkout", "-B", branch)
    if branch in PROTECTED or not branch.startswith("harness/"):
        raise GitError(f"rama no permitida: {branch}")
    _run("git", "add", "--", *PATHS)
    _run("git", "-c", "user.name=senda-harness", "-c", "user.email=senda-harness@users.noreply.github.com",
         "commit", "-m", f"{title}\n\nInforme: {rel(report)}")
    if _run("git", "rev-parse", "--abbrev-ref", "HEAD") in PROTECTED:
        raise GitError("protección: el harness nunca empuja a main")
    _run("git", "push", "--set-upstream", "origin", f"HEAD:refs/heads/{branch}")
    body = _body_file(report)
    if existing:
        _run("gh", "pr", "edit", branch, "--body-file", str(body), "--title", title)
        _run("gh", "pr", "comment", branch, "--body", f"Actualizado por el harness con `{rel(report)}`.",
             check=False)
        out.write(f"[pr] PR actualizado: {existing}\n")
        return existing
    _run("gh", "label", "create", label, "--color", "5319e7", "--description",
         "Propuesto por el harness de IA", "--force", check=False)
    url = _run("gh", "pr", "create", "--base", base, "--head", branch, "--title", title,
               "--body-file", str(body), "--label", label)
    out.write(f"[pr] PR abierto: {url}\n")
    return url

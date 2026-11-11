"""Estado persistente del harness (harness/state/*.json, se commitea en los PR).

JSON con claves ordenadas e indentación fija para que los diffs sean legibles.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import config


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load(name: str, default=None):
    f = config.STATE / name
    if not f.exists():
        return {} if default is None else default
    with open(f, encoding="utf-8") as fh:
        return json.load(fh)


def save(name: str, data) -> Path:
    config.STATE.mkdir(parents=True, exist_ok=True)
    f = config.STATE / name
    tmp = f.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    tmp.replace(f)
    return f


def inbox_files(prefix: str) -> list[Path]:
    """Archivos que deja Claude Code (camino local sin API): harness/state/inbox/<prefix>-*.json"""
    if not config.INBOX.is_dir():
        return []
    return sorted(config.INBOX.glob(f"{prefix}-*.json"))

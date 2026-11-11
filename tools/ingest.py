#!/usr/bin/env python3
"""Ingest in-game observations (SendaRecorderDB) from WoW SavedVariables.

Usage:
  python tools/ingest.py "E:/World of Warcraft/_forever_/WTF"            # searches */SavedVariables/Senda.lua
  python tools/ingest.py path/to/SavedVariables/Senda.lua [--dry-run]

The SavedVariables file is parsed with a safe Lua *data* parser (nothing is executed).
Only whitelisted fields are kept: kind, quest, npc, map, x, y, level, race, class, build,
plus the day of the observation (t rounded down to 00:00 UTC) and a repeat count ``n``.
Character, realm and account names never leave the WTF folder.

Output: data/observations/<build>.json (merged and deduplicated with what is already there).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from questiedb import luaparse  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "data" / "observations"
KINDS = {"accept", "turnin", "npc_seen", "fp", "bind"}
INT_FIELDS = ("quest", "npc", "map", "level")
MAX_BYTES = 64 * 1024 * 1024
DAY = 86400
_BUILD_RE = re.compile(r"^[0-9][0-9A-Za-z._-]{0,40}$")


def find_savedvariables(path: Path) -> list[Path]:
    path = Path(path)
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise FileNotFoundError(path)
    found = sorted(path.rglob("SavedVariables/Senda.lua"))
    return [p for p in found if p.is_file()]


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        try:
            return float(v) if "." in v else int(v)
        except ValueError:
            return None
    return None


def clean(obs: dict) -> dict | None:
    """Whitelist + normalize one raw observation; None if unusable."""
    kind = obs.get("kind")
    if kind not in KINDS:
        return None
    out: dict = {"kind": kind}
    for key in INT_FIELDS:
        v = _num(obs.get(key))
        if v is not None:
            out[key] = int(v)
    x, y = _num(obs.get("x")), _num(obs.get("y"))
    if x is not None and y is not None:
        if 0 <= x <= 1 and 0 <= y <= 1:  # recorder may store 0-1 map fractions
            x, y = x * 100, y * 100
        if 0 <= x <= 100 and 0 <= y <= 100:
            out["x"], out["y"] = round(x, 2), round(y, 2)
    race = obs.get("race")
    if isinstance(race, str) and re.fullmatch(r"[A-Za-z]{2,20}", race):
        out["race"] = race
    cls = obs.get("class")
    if isinstance(cls, str) and re.fullmatch(r"[A-Za-z_]{2,20}", cls):
        out["class"] = cls.upper()
    build = obs.get("build")
    if isinstance(build, (int, float)) and not isinstance(build, bool):
        build = str(int(build))
    out["build"] = build if isinstance(build, str) and _BUILD_RE.match(build) else "unknown"
    t = _num(obs.get("t"))
    if t is not None and t > 0:
        out["t"] = int(t) // DAY * DAY
    return out


def dedupe_key(o: dict) -> tuple:
    return (o["kind"], o.get("quest"), o.get("npc"), o.get("map"),
            round(o["x"], 1) if "x" in o else None, round(o["y"], 1) if "y" in o else None,
            o.get("race"), o.get("class"), o["build"])


def extract(data) -> list[dict]:
    """Every table with a ``kind`` key anywhere under SendaRecorderDB."""
    out = []
    stack = [data]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            if "kind" in x and isinstance(x.get("kind"), str):
                out.append(x)
            else:
                stack.extend(v for v in x.values() if isinstance(v, (dict, list)))
        elif isinstance(x, list):
            stack.extend(x)
    return out


def parse_file(path: Path) -> list[dict]:
    raw = Path(path).read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError(f"{path}: file too large ({len(raw)} bytes)")
    text = raw.decode("utf-8", errors="replace")
    assigns = luaparse.parse_assignments(text)
    db = assigns.get("SendaRecorderDB")
    if db is None:
        return []
    return extract(luaparse.to_py(db))


def merge(existing: list[dict], new: list[dict]) -> list[dict]:
    by_key: dict[tuple, dict] = {}
    for o in existing + new:
        k = dedupe_key(o)
        n = int(o.get("n", 1))
        if k in by_key:
            cur = by_key[k]
            cur["n"] = cur.get("n", 1) + n
            if "t" in o and ("t" not in cur or o["t"] < cur["t"]):
                cur["t"] = o["t"]
            if "level" in o and ("level" not in cur or o["level"] < cur["level"]):
                cur["level"] = o["level"]
        else:
            by_key[k] = {**o, "n": n}
    return sorted(by_key.values(), key=lambda o: (o["kind"], o.get("quest") or 0, o.get("npc") or 0,
                                                    o.get("map") or 0, o.get("t") or 0))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="WTF folder or SavedVariables/Senda.lua file (must be given explicitly)")
    ap.add_argument("--out", default=str(OUT_DIR), help="output folder (default data/observations)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    files = find_savedvariables(Path(args.path))
    if not files:
        print("no SavedVariables/Senda.lua found", file=sys.stderr)
        return 1
    cleaned = []
    skipped = 0
    for f in files:
        try:
            rows = parse_file(f)
        except (luaparse.LuaParseError, ValueError) as exc:
            print(f"skip {f.name}: {exc}", file=sys.stderr)
            continue
        for r in rows:
            c = clean(r)
            if c is None:
                skipped += 1
            else:
                cleaned.append(c)
    by_build: dict[str, list[dict]] = {}
    for o in cleaned:
        by_build.setdefault(o["build"], []).append(o)
    out_dir = Path(args.out)
    for build, rows in sorted(by_build.items()):
        target = out_dir / f"{build}.json"
        existing = []
        if target.exists():
            try:
                existing = json.loads(target.read_text(encoding="utf-8")).get("observations", [])
            except (json.JSONDecodeError, OSError):
                existing = []
        merged = merge(existing, rows)
        print(f"build {build}: {len(rows)} read, {len(merged)} unique (was {len(existing)}) -> "
              f"{target.relative_to(REPO_ROOT) if target.is_relative_to(REPO_ROOT) else target}")
        if not args.dry_run:
            out_dir.mkdir(parents=True, exist_ok=True)
            doc = {"build": build, "count": len(merged), "observations": merged}
            target.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(files)} file(s), {len(cleaned)} observations kept, {skipped} discarded")
    return 0


if __name__ == "__main__":
    sys.exit(main())

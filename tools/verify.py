#!/usr/bin/env python3
"""Check guide steps (data/) against the local QuestieDB and in-game observations.

  python tools/verify.py                       # all guides -> harness/reports/verify-latest.{md,json}
  python tools/verify.py --guide gnome-warlock --json      # JSON on stdout (used by harness/)
  python tools/verify.py --apply-status [--dry-run]        # promote unverified -> verified when allowed

Per step and per guide the verdict is ``confirm`` / ``conflict`` / ``unknown`` with evidence.
``--apply-status`` only ever upgrades ``unverified`` to ``verified`` (ARCHITECTURE.md rules):
  (b) an in-game observation matches the step, or
  (c) QuestieDB confirms every checkable claim AND the step's sources include another independent
      source (URL classified official/community_curated by harness/sources.toml).
It never downgrades: conflicts on verified steps are reported as suggestions.
Reports contain ids, verdicts and distances only (QuestieDB is "all rights reserved").
Without a local QuestieDB (CI) it checks against forever-db (``--db``, see tools/README.md); forever-db
has no npcFlags, so NPC roles are then "unknown", and promoted steps cite ``foreverdb:`` instead of ``questie:``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from questiedb import QuestDB  # noqa: E402
from foreverdb import add_db_arguments, open_db, source_of  # noqa: E402
from questiedb.constants import (NPC_FLAGS, class_allowed, classes_in_mask, race_allowed,  # noqa: E402
                                 races_in_mask)

REPO_ROOT = Path(__file__).resolve().parents[1]
QUEST_STEPS = {"accept", "turnin", "complete"}
CORE_CHECKS = {"quest_exists", "starter", "finisher", "npc_exists", "coords", "npc_role", "item_exists",
               "vendor", "observation"}
ROLE_FOR_STEP = {"sethearth": "INNKEEPER", "getfp": "FLIGHT_MASTER", "fly": "FLIGHT_MASTER",
                 "train": "TRAINER", "learn_prof": "TRAINER", "buy": "VENDOR"}


# --------------------------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------------------------

def load_toml(path: Path) -> dict:
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def load_guides(root: Path, only: str | None = None) -> list[dict]:
    guides = []
    gdir = root / "data" / "guides"
    for gfile in sorted(gdir.glob("*/guide.toml")):
        meta = load_toml(gfile)
        gid = meta.get("id", gfile.parent.name)
        if only and gid != only and gfile.parent.name != only:
            continue
        sections = []
        for ref in meta.get("sections", []):
            if ref.startswith("shared:"):
                path = root / "data" / "shared" / f"{ref[7:]}.toml"
            else:
                path = gfile.parent / f"{ref}.toml"
            if not path.exists():
                sections.append({"ref": ref, "file": path, "missing": True, "data": {}, "steps": []})
                continue
            data = load_toml(path)
            sections.append({"ref": ref, "file": path, "missing": False, "data": data,
                             "steps": data.get("step", [])})
        guides.append({"id": gid, "file": gfile, "meta": meta, "sections": sections})
    return guides


def load_observations(root: Path) -> list[dict]:
    out = []
    odir = root / "data" / "observations"
    if not odir.is_dir():
        return out
    for f in sorted(odir.glob("*.json")):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        rows = doc.get("observations", doc) if isinstance(doc, dict) else doc
        for o in rows if isinstance(rows, list) else []:
            if isinstance(o, dict) and "kind" in o:
                out.append({**o, "_file": f.name})
    return out


class TierClassifier:
    """Classify a source URL with harness/sources.toml (longest prefix wins)."""

    def __init__(self, root: Path):
        self.prefixes: list[tuple[str, str]] = []
        path = root / "harness" / "sources.toml"
        if not path.exists():
            path = REPO_ROOT / "harness" / "sources.toml"
        if path.exists():
            try:
                cfg = load_toml(path)
            except tomllib.TOMLDecodeError:
                cfg = {}
            for src in cfg.get("source", []):
                for m in src.get("match", []) + ([src["url"].split("://", 1)[-1]] if src.get("url") else []):
                    self.prefixes.append((m.lower().removeprefix("www."), src.get("tier", "community_unverified")))
        self.prefixes.sort(key=lambda p: -len(p[0]))

    def tier(self, source: str) -> str | None:
        if not re.match(r"^https?://", source or ""):
            return None
        u = source.split("://", 1)[1].lower().removeprefix("www.")
        for prefix, tier in self.prefixes:
            if u.startswith(prefix):
                return tier
        return "community_unverified"


# --------------------------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------------------------

def _chk(name, result, evidence, suggestion=None):
    c = {"check": name, "result": result, "evidence": evidence}
    if suggestion:
        c["suggestion"] = suggestion
    return c


def step_applies(guide_meta, section_data, step):
    """False si el filtro `if` (raza/clase) del paso o de la sección excluye a todos los personajes de la guía:
    ese paso no existe para esta guía (el motor del addon tampoco lo muestra)."""
    races = set(guide_meta.get("races", []) or [])
    classes = set(guide_meta.get("classes", []) or [])
    for flt in (section_data.get("if") or {}, step.get("if") or {}):
        if flt.get("race") and races and not races & set(flt["race"]):
            return False
        if flt.get("class") and classes and not classes & set(flt["class"]):
            return False
        if flt.get("faction") and guide_meta.get("faction") and flt["faction"] != guide_meta["faction"]:
            return False
    return True


def step_combos(guide_meta, section_data, step):
    races = list(guide_meta.get("races", []))
    classes = list(guide_meta.get("classes", []))
    for flt in (section_data.get("if") or {}, step.get("if") or {}):
        if flt.get("race"):
            races = [r for r in races if r in flt["race"]] or list(flt["race"])
        if flt.get("class"):
            classes = [c for c in classes if c in flt["class"]] or list(flt["class"])
    return races, classes


def coords_check(db, kind, eid, at, tol, label):
    uimap, x, y = int(at[0]), float(at[1]), float(at[2])
    near = db.nearest(kind, eid, uimap, x, y)
    pts = db.entity_points(kind, eid)
    if near is None:
        if pts:
            maps = sorted({p[0] for p in pts if p[0]})
            return _chk("coords", "conflict", f"{label} {kind} {eid} has no spawn on uiMap {uimap} (maps: {maps})",
                        f"check uiMapID in `at`; QuestieDB places {kind} {eid} on {maps}")
        return _chk("coords", "unknown", f"{label} {kind} {eid} has no coordinates in QuestieDB")
    d, p, src = near
    ev = f"{label} {kind} {eid}: nearest {src} {p[0]} ({p[1]:.2f}, {p[2]:.2f}), distance {d:.2f} (tol {tol})"
    if d <= tol:
        return _chk("coords", "confirm", ev)
    return _chk("coords", "conflict", ev, f"move `at` to [{p[0]}, {p[1]:.1f}, {p[2]:.1f}]")


def check_step(db, guide, section, step, state, observations, tol):
    do = step.get("do")
    quest_ids = []
    if isinstance(step.get("quest"), int):
        quest_ids.append(step["quest"])
    quest_ids += [q for q in step.get("quests", []) or [] if isinstance(q, int)]
    npc = step.get("npc") if isinstance(step.get("npc"), int) else None
    item = step.get("item") if isinstance(step.get("item"), int) else None
    at = step.get("at") if isinstance(step.get("at"), list) and len(step.get("at")) >= 3 else None
    faction = guide["meta"].get("faction")
    races, classes = step_combos(guide["meta"], section["data"], step)
    checks = []

    # --- entities exist --------------------------------------------------------------------
    for q in quest_ids:
        qd = db.quest(q)
        checks.append(_chk("quest_exists", "confirm" if qd else "conflict",
                           f"quest {q} {'found' if qd else 'not found'} in QuestieDB"))
    if npc is not None:
        nd = db.npc(npc)
        checks.append(_chk("npc_exists", "confirm" if nd else "conflict",
                           f"npc {npc} {'found' if nd else 'not found'} in QuestieDB"))
    if item is not None:
        it = db.item(item)
        checks.append(_chk("item_exists", "confirm" if it else "unknown",
                           f"item {item} {'found' if it else 'not in QuestieDB (only quest-related items are)'}"))

    # --- quest givers ----------------------------------------------------------------------
    for q in quest_ids:
        qd = db.quest(q)
        if not qd:
            continue
        if do == "accept":
            role, members = "starter", qd["starters"]
            ok = npc is not None and db.is_starter(q, npc)
        elif do == "turnin":
            role, members = "finisher", qd["finishers"]
            ok = npc is not None and db.is_finisher(q, npc)
        else:
            role = None
        if role:
            listing = {k: v for k, v in members.items() if v}
            if npc is None:
                checks.append(_chk(role, "unknown", f"step has no npc; quest {q} {role}s: {listing}"))
            elif ok:
                checks.append(_chk(role, "confirm", f"npc {npc} is a {role} of quest {q}"))
            else:
                checks.append(_chk(role, "conflict", f"npc {npc} is not a {role} of quest {q}; {role}s: {listing}",
                                   f"use npc {members['npc'][0]}" if members.get("npc") else None))
            # coordinates against the quest giver when the step has no npc
            if at and npc is None:
                best = None
                for kind in ("npc", "object"):
                    for eid in members.get(kind, []):
                        c = coords_check(db, kind, eid, at, tol, role)
                        if best is None or (c["result"] == "confirm") or (best["result"] == "unknown"):
                            best = c
                        if c["result"] == "confirm":
                            break
                if best:
                    checks.append(best)

        # --- race / class --------------------------------------------------------------------
        bad = []
        for r in races:
            for c in classes:
                try:
                    if not (race_allowed(qd["races"], r, faction) and class_allowed(qd["classes"], c)):
                        bad.append(f"{r}/{c}")
                except KeyError:
                    pass
        if races or classes:
            if bad:
                checks.append(_chk("race_class", "conflict",
                                   f"quest {q} races {races_in_mask(qd['races'])} classes {classes_in_mask(qd['classes'])}"
                                   f" excludes {bad}", "add an `if` filter (race/class) to the step"))
            else:
                checks.append(_chk("race_class", "confirm", f"quest {q} available to {races}x{classes}"))

        # --- prerequisites -------------------------------------------------------------------
        if do == "accept" or (do in ("turnin", "complete") and q not in state["accepted"]):
            def avail(p):
                return any(db.can_take(p, r, c, faction) for r in races for c in classes) if races and classes \
                    else bool(db.quest(p))
            missing_all = [p for p in qd["preQuestGroup"] if p not in state["turned_in"] and avail(p)]
            single = qd["preQuestSingle"]
            single_ok = (not single) or any(p in state["turned_in"] for p in single)
            single_avail = [p for p in single if avail(p)]
            if missing_all or (not single_ok and single_avail):
                ev = []
                if missing_all:
                    ev.append(f"needs ALL of {qd['preQuestGroup']} turned in; missing {missing_all}")
                if not single_ok and single_avail:
                    ev.append(f"needs ANY of {single}; none turned in earlier in the route")
                checks.append(_chk("prereqs", "conflict", f"quest {q}: " + "; ".join(ev),
                                   "add the prerequisite turn-in earlier or reorder the route"))
            elif qd["preQuestGroup"] or single:
                checks.append(_chk("prereqs", "confirm", f"quest {q}: prerequisites turned in earlier"))

        if do in ("turnin", "complete") and q not in state["accepted"]:
            if qd["starters"]["item"] and not (qd["starters"]["npc"] or qd["starters"]["object"]):
                checks.append(_chk("route_order", "unknown", f"quest {q} is started by an item; no accept step"))
            else:
                checks.append(_chk("route_order", "conflict", f"quest {q} {do} before any accept step in the route",
                                   "add/move the accept step earlier"))

        # --- level sanity --------------------------------------------------------------------
        levels = section["data"].get("levels")
        if isinstance(levels, list) and len(levels) == 2:
            lo, hi = levels
            req, ql = qd["requiredLevel"], qd["level"]
            if do == "accept" and req and req > hi:
                checks.append(_chk("level", "conflict", f"quest {q} requires level {req}; section is {lo}-{hi}",
                                   "move the step to a later section or fix `levels`"))
            elif ql and ql > hi + 5:
                checks.append(_chk("level", "conflict", f"quest {q} level {ql} far above section {lo}-{hi}"))
            else:
                note = f"quest {q} level {ql} (req {req}) vs section {lo}-{hi}"
                if ql and ql < lo - 6:
                    note += " (likely gray)"
                checks.append(_chk("level", "confirm", note))

    # --- NPC coordinates / roles -----------------------------------------------------------------
    if npc is not None and db.npc(npc):
        if at:
            checks.append(coords_check(db, "npc", npc, at, tol, "step"))
        role = ROLE_FOR_STEP.get(do)
        if role and db.npc(npc).get("npcFlags") is None:
            checks.append(_chk("npc_role", "unknown", f"npc {npc}: no npc flags in {source_of(db)}"))
        elif role:
            flags = db.npc(npc)["npcFlags"]
            ok = bool(flags & NPC_FLAGS[role])
            checks.append(_chk("npc_role", "confirm" if ok else "conflict",
                               f"npc {npc} flags {flags} {'include' if ok else 'lack'} {role}"))
    if do == "buy" and item is not None and npc is not None and db.item(item):
        vendors = db.item(item)["vendors"]
        if vendors:
            checks.append(_chk("vendor", "confirm" if npc in vendors else "conflict",
                               f"item {item} vendors {vendors[:10]}"))
    if do == "train" and step.get("spells"):
        checks.append(_chk("spells", "unknown", "QuestieDB has no spell data; spells not checked"))

    # --- observations --------------------------------------------------------------------------
    obs_kind = {"accept": "accept", "turnin": "turnin", "getfp": "fp", "sethearth": "bind"}.get(do)
    matched = []
    if obs_kind:
        for o in observations:
            if o.get("kind") != obs_kind:
                continue
            if quest_ids and o.get("quest") not in quest_ids:
                continue
            if not quest_ids and at and o.get("map") != int(at[0]):
                continue
            if not quest_ids and not at:
                continue
            matched.append(o)
    elif npc is not None:
        matched = [o for o in observations if o.get("kind") == "npc_seen" and o.get("npc") == npc]
    if matched:
        good, bad = [], []
        for o in matched:
            problems = []
            if npc is not None and o.get("npc") not in (None, npc):
                problems.append(f"npc {o.get('npc')}")
            if at and "x" in o and "y" in o and o.get("map") is not None:
                if o["map"] != int(at[0]):
                    problems.append(f"map {o['map']}")
                else:
                    d = math.hypot(o["x"] - float(at[1]), o["y"] - float(at[2]))
                    if d > tol:
                        problems.append(f"position ({o['x']:.1f}, {o['y']:.1f}) at {d:.2f}")
            (bad if problems else good).append((o, problems))
        if good:
            o = good[0][0]
            checks.append(_chk("observation", "confirm",
                               f"{len(good)} in-game {obs_kind or 'npc_seen'} observation(s) match"
                               f" (build {o.get('build')}, {o.get('_file')})"))
        if bad and not good:
            o, problems = bad[0]
            sugg = None
            if "x" in o and o.get("map") is not None:
                sugg = f"observed at [{o['map']}, {o['x']:.1f}, {o['y']:.1f}]"
            checks.append(_chk("observation", "conflict",
                               f"in-game observation differs: {', '.join(problems)} (build {o.get('build')})", sugg))

    # --- route state -------------------------------------------------------------------------------
    if do == "accept":
        state["accepted"].update(quest_ids)
    if do == "turnin":
        state["turned_in"].update(quest_ids)
        state["accepted"].update(quest_ids)

    results = [c["result"] for c in checks]
    if "conflict" in results:
        verdict = "conflict"
    elif "confirm" in results:
        verdict = "confirm"
    else:
        verdict = "unknown"
    core = [c for c in checks if c["check"] in CORE_CHECKS and c["check"] != "observation"]
    db_confirmed = bool(core) and all(c["result"] == "confirm" for c in core) and verdict == "confirm" and \
        (do not in QUEST_STEPS or any(c["check"] in ("starter", "finisher") for c in core) or do == "complete")
    obs_confirmed = any(c["check"] == "observation" and c["result"] == "confirm" for c in checks) and \
        verdict == "confirm"
    return {
        "step": step.get("id"), "guide": guide["id"], "section": section["data"].get("id", section["ref"]),
        "file": section["file"].as_posix(), "do": do, "status": step.get("status"),
        "quest": quest_ids or None, "npc": npc, "verdict": verdict, "checks": checks,
        "db_confirmed": db_confirmed, "obs_confirmed": obs_confirmed,
        "sources": list(step.get("sources", []) or []),
    }


# --------------------------------------------------------------------------------------------
# TOML line-level editing
# --------------------------------------------------------------------------------------------

_HEADER_RE = re.compile(r"^\s*\[\[?\s*[A-Za-z_][A-Za-z0-9_.\-]*\s*\]\]?\s*(#.*)?$")
_KEY_RE = r"^(?P<indent>\s*){key}\s*=\s*"


def _toml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def _bracket_delta(line: str) -> int:
    depth, in_str, quote, i = 0, False, "", 0
    while i < len(line):
        ch = line[i]
        if in_str:
            if ch == "\\" and quote == '"':
                i += 2
                continue
            if ch == quote:
                in_str = False
        elif ch in "\"'":
            in_str, quote = True, ch
        elif ch == "#":
            break
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        i += 1
    return depth


def find_step_block(lines: list[str], step_id: str) -> tuple[int, int] | None:
    i = 0
    n = len(lines)
    while i < n:
        if lines[i].strip().startswith("[[step]]"):
            start = i
            j = i + 1
            depth = 0
            found = False
            while j < n:
                if depth == 0 and _HEADER_RE.match(lines[j]):
                    break
                m = re.match(r"^\s*id\s*=\s*\"([^\"]*)\"", lines[j]) if depth == 0 else None
                if m and m.group(1) == step_id:
                    found = True
                depth += _bracket_delta(lines[j])
                j += 1
            if found:
                return start, j
            i = j
        else:
            i += 1
    return None


def edit_step(text: str, step_id: str, status: str, add_sources: list[str], checked: str) -> str | None:
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    block = find_step_block(lines, step_id)
    if not block:
        return None
    start, end = block

    def find_key(key):
        for k in range(start + 1, end):
            if re.match(_KEY_RE.format(key=key), lines[k]):
                return k
        return None

    s_idx = find_key("status")
    if s_idx is None:
        return None
    lines[s_idx] = re.sub(r'(=\s*)"[^"]*"', lambda m: f'{m.group(1)}"{status}"', lines[s_idx], count=1)

    src_idx = find_key("sources")
    last_idx = s_idx
    if src_idx is None:
        indent = re.match(r"^\s*", lines[s_idx]).group(0)
        lines.insert(s_idx + 1, f"{indent}sources = [{', '.join(_toml_str(s) for s in add_sources)}]")
        end += 1
        last_idx = s_idx + 1
    else:
        depth = _bracket_delta(lines[src_idx])
        close = src_idx
        while depth > 0 and close + 1 < end:
            close += 1
            depth += _bracket_delta(lines[close])
        chunk = "\n".join(lines[src_idx:close + 1])
        try:
            current = tomllib.loads(chunk.strip())["sources"]
        except (tomllib.TOMLDecodeError, KeyError):
            return None
        missing = [s for s in add_sources if s not in current]
        if close == src_idx:
            m = re.match(r"^(?P<head>\s*sources\s*=\s*)\[.*\](?P<tail>\s*(#.*)?)$", lines[src_idx])
            if not m:
                return None
            lines[src_idx] = f"{m.group('head')}[{', '.join(_toml_str(s) for s in current + missing)}]{m.group('tail')}"
        elif missing:
            prev = close - 1
            while prev > src_idx and not lines[prev].strip():
                prev -= 1
            elem_indent = re.match(r"^\s*", lines[prev]).group(0) if prev > src_idx else "  "
            if prev > src_idx and not lines[prev].split("#")[0].rstrip().endswith((",", "[")):
                code, sep, comment = lines[prev].partition("#")
                lines[prev] = code.rstrip() + "," + ((" " + sep + comment) if sep else "")
            for k, s in enumerate(missing):
                lines.insert(close + k, f"{elem_indent}{_toml_str(s)},")
            end += len(missing)
            close += len(missing)
        last_idx = close

    c_idx = find_key("checked")
    if c_idx is not None:
        lines[c_idx] = re.sub(r"=\s*.*$", f'= "{checked}"', lines[c_idx], count=1)
    else:
        indent = re.match(r"^\s*", lines[s_idx]).group(0)
        lines.insert(last_idx + 1, f'{indent}checked = "{checked}"')
    out = nl.join(lines) + (nl if text.endswith(("\n", "\r\n")) else "")
    return out


def _find_step(doc: dict, step_id: str) -> dict | None:
    for s in doc.get("step", []):
        if s.get("id") == step_id:
            return s
    return None


# --------------------------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------------------------

def render_markdown(report: dict) -> str:
    s = report["summary"]
    db = report["questiedb"]
    name = (f"forever-db {db.get('version')}" if db.get("source") == "foreverdb"
            else f"QuestieDB {db.get('flavor')}")
    out = [f"# Verificación contra {name.split(' ')[0]} — {report['generated']}", "",
           f"{name} (commit {str(db.get('build_commit'))[:10]}),"
           f" tolerancia {report['tolerance']} % de mapa, {report['observations']} observaciones de juego.", "",
           "| Guía | Pasos | confirm | conflict | unknown |", "|---|---:|---:|---:|---:|"]
    for gid, g in s["by_guide"].items():
        out.append(f"| {gid} | {g['steps']} | {g['confirm']} | {g['conflict']} | {g['unknown']} |")
    out.append("")
    if report.get("applied"):
        out += ["## Estados promovidos a `verified`", ""]
        out += [f"- `{a['step']}` ({a['file']}): regla {a['rule']}" for a in report["applied"]]
        out.append("")
    conflicts = [r for r in report["results"] if r["verdict"] == "conflict"]
    out += [f"## Conflictos ({len(conflicts)})", ""]
    for r in conflicts:
        out.append(f"### `{r['step']}` — {r['do']} ({r['guide']} / {r['section']}, status {r['status']})")
        for c in r["checks"]:
            if c["result"] == "conflict":
                out.append(f"- **{c['check']}**: {c['evidence']}" + (f" → sugerencia: {c['suggestion']}"
                                                                      if c.get("suggestion") else ""))
        out.append("")
    if report["suggestions"]:
        out += ["## Sugerencias", ""] + [f"- {x}" for x in report["suggestions"]] + [""]
    unknown = [r for r in report["results"] if r["verdict"] == "unknown"]
    if unknown:
        out += [f"## Sin evidencia ({len(unknown)})", ""]
        out += [f"- `{r['step']}` ({r['do']}): " + "; ".join(c["evidence"] for c in r["checks"])
                if r["checks"] else f"- `{r['step']}` ({r['do']}): nada que comprobar" for r in unknown]
        out.append("")
    out += ["## Confirmados", ""]
    out += [f"- `{r['step']}` ({r['do']}) " + ("[db] " if r["db_confirmed"] else "") +
            ("[juego] " if r["obs_confirmed"] else "") + f"status {r['status']}"
            for r in report["results"] if r["verdict"] == "confirm"]
    out += ["", "_Datos de QuestieDB («all rights reserved»): solo ids, veredictos y distancias._", ""]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(REPO_ROOT), help="repository root (default: this repo)")
    ap.add_argument("--guide", help="only this guide id")
    ap.add_argument("--questiedb", help="QuestieDB addon folder (or env SENDA_QUESTIEDB)")
    add_db_arguments(ap)
    ap.add_argument("--tolerance", type=float, default=2.0, help="coordinate tolerance in map %% (default 2.0)")
    ap.add_argument("--json", action="store_true", help="print the JSON report on stdout")
    ap.add_argument("--apply-status", action="store_true", help="promote unverified -> verified where allowed")
    ap.add_argument("--dry-run", action="store_true", help="with --apply-status: show edits, write nothing")
    ap.add_argument("--out-dir", help="report folder (default <root>/harness/reports)")
    ap.add_argument("--no-report", action="store_true", help="do not write report files")
    ap.add_argument("--today", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    today = args.today or dt.date.today().isoformat()
    guides = load_guides(root, args.guide)
    observations = load_observations(root)
    tiers = TierClassifier(root)
    dbs: dict[str, QuestDB] = {}

    results = []
    suggestions = []
    for g in guides:
        faction = g["meta"].get("faction", "Alliance")
        if faction not in dbs:
            dbs[faction] = open_db(args, faction=faction)
        db = dbs[faction]
        state = {"accepted": set(), "turned_in": set()}
        for sec in g["sections"]:
            if sec["missing"]:
                suggestions.append(f"guide {g['id']}: section `{sec['ref']}` not found ({sec['file'].as_posix()})")
                continue
            for step in sec["steps"]:
                if not step_applies(g["meta"], sec["data"], step):
                    continue
                r = check_step(db, g, sec, step, state, observations, args.tolerance)
                try:
                    r["file"] = sec["file"].relative_to(root).as_posix()
                except ValueError:
                    pass
                results.append(r)
                if r["verdict"] == "conflict" and r["status"] == "verified":
                    suggestions.append(f"`{r['step']}` is verified but conflicts with QuestieDB/observations: "
                                       f"review and consider status = \"disputed\" (not changed automatically)")

    # ---- apply status -------------------------------------------------------------------------
    applied = []
    by_step: dict[tuple[str, str], list[dict]] = {}
    for r in results:
        by_step.setdefault((r["file"], r["step"]), []).append(r)
    if args.apply_status:
        edits: dict[str, list[tuple[str, str, list[str]]]] = {}
        for (file, sid), rs in by_step.items():
            if any(r["status"] != "unverified" for r in rs) or any(r["verdict"] != "confirm" for r in rs):
                continue
            first = rs[0]
            add = []
            rule = ""
            if all(r["obs_confirmed"] for r in rs):
                rule = "b"
                add.append("ingame:obs")
            if all(r["db_confirmed"] for r in rs):
                # Una URL citada no basta: las guías de leveo genéricas no confirman cada misión/coordenada.
                # Cuenta como independiente una fuente oficial o una cita comprobada por el harness
                # (entradas "harness:..." que propose solo escribe tras encontrar la cita literal en la página).
                independent = [s for s in first["sources"]
                               if tiers.tier(s) == "official" or s.startswith("harness:")]
                if independent or rule:
                    rule = rule or "c"
                    tag = "questie" if source_of(next(iter(dbs.values()))) == "questiedb" else "foreverdb"
                    if first["quest"]:
                        add += [f"{tag}:quest/{q}" for q in first["quest"]]
                    elif first["npc"]:
                        add.append(f"{tag}:npc/{first['npc']}")
            if not rule:
                continue
            edits.setdefault(file, []).append((sid, rule, add))
        for file, items in edits.items():
            path = root / file
            text = path.read_text(encoding="utf-8")
            new = text
            done = []
            for sid, rule, add in items:
                edited = edit_step(new, sid, "verified", add, today)
                if edited is None:
                    suggestions.append(f"`{sid}`: could not edit {file} at line level; promote by hand (rule {rule})")
                    continue
                try:
                    doc = tomllib.loads(edited)
                    st = _find_step(doc, sid)
                    assert st and st["status"] == "verified" and all(a in st["sources"] for a in add)
                except (tomllib.TOMLDecodeError, AssertionError):
                    suggestions.append(f"`{sid}`: edit would break {file}; skipped")
                    continue
                new = edited
                done.append({"step": sid, "file": file, "rule": rule, "added": add})
            if done and new != text:
                if not args.dry_run:
                    with open(path, "w", encoding="utf-8", newline="") as fh:
                        fh.write(new)
                applied += done

    summary = {"steps": len(results), "by_guide": {}}
    for r in results:
        g = summary["by_guide"].setdefault(r["guide"], {"steps": 0, "confirm": 0, "conflict": 0, "unknown": 0})
        g["steps"] += 1
        g[r["verdict"]] += 1
    if not dbs:
        dbs["Alliance"] = open_db(args, faction="Alliance")
    any_db = next(iter(dbs.values()), None)
    info = {k: any_db.info.get(k) for k in ("flavor", "faction", "build_commit", "build_time", "version")} if any_db else {}
    if any_db:
        info["source"] = source_of(any_db)
    report = {"generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "root": root.name,
              "questiedb": info, "tolerance": args.tolerance, "observations": len(observations),
              "summary": summary, "applied": applied, "dry_run": bool(args.dry_run and args.apply_status),
              "suggestions": suggestions, "results": results}

    if not args.no_report:
        out_dir = Path(args.out_dir) if args.out_dir else root / "harness" / "reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "verify-latest.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n",
                                                    encoding="utf-8", newline="\n")
        (out_dir / "verify-latest.md").write_text(render_markdown(report), encoding="utf-8", newline="\n")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        for gid, g in summary["by_guide"].items():
            print(f"{gid}: {g['steps']} steps, {g['confirm']} confirm, {g['conflict']} conflict, {g['unknown']} unknown")
        if applied:
            verb = "would promote" if args.dry_run else "promoted"
            print(f"{verb} {len(applied)} step(s) to verified: " + ", ".join(a["step"] for a in applied))
        for s in suggestions[:20]:
            print(f"suggestion: {s}")
        if not guides:
            print("no guides found under data/guides")
    return 1 if any(r["verdict"] == "conflict" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())

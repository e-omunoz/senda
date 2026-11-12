"""forever-db's hand-checked corrections (``corrections/*.json``) applied to its tables.

forever-db 2026.11.x publishes ``corrections/{quests,npcs,objects}.json`` beside its tables, and many of
them are not yet in ``data/*.jsonl`` (prerequisites above all: 104 of 111 ``pre`` records). Polestar
applies them when it builds its data; Senda applies them here, when it reads the tables, so that
tools/foreverdb/db.py, tools/build.py (``data/prereq.json``, ``Guides/Followups.lua``) and
tools/audit_guides.py see the same facts.

After forever-db's own records come Senda's, in the same format, from ``data/corrections/*.json``: facts
checked by Senda's players or tools that forever-db does not have yet (each with ``source`` and ``note``;
candidates to send upstream). A Senda record for the same id is applied after forever-db's.

The rules follow Polestar's ``forge-data`` (GPL-3.0): rust/crates/forge-data/src/corrections.rs (``set``
replaces fields, ``remove`` takes the quest and every link to it out, ``addSpawns`` replaces one map's
spawns) and src/publish/tables.rs (``preAll`` -> mode all, then ``preAny`` -> any, then ``pre`` -> all,
``breadcrumbs`` -> any + breadcrumb). Adaptado de Polestar (GPL-3.0), ver THIRD_PARTY.md.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SENDA_DIR = REPO_ROOT / "data" / "corrections"

# quests.json `set` keys -> quest.jsonl fields (the rest go to `extra`)
QUEST_FIELDS = {"title": "title", "level": "level", "minLevel": "min_level", "races": "races",
                "classes": "classes", "xp": "xp", "side": "side"}
PREREQ_KEYS = ("pre", "preAny", "preAll")


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load(root: Path | None, senda_dir: Path | None = SENDA_DIR) -> dict[str, dict]:
    """{"quests": {id: record}, "npcs": {...}, "objects": {...}}: forever-db's records, then Senda's.

    A Senda record for an id forever-db also corrects is merged on top (its `set` keys win; `remove`
    and `addSpawns` are taken as they are). Each record keeps where it came from in ``_from``.
    """
    out: dict[str, dict] = {"quests": {}, "npcs": {}, "objects": {}}
    layers = []
    if root is not None:
        layers.append(("forever-db", Path(root) / "corrections"))
    if senda_dir is not None:
        layers.append(("senda", Path(senda_dir)))
    for origin, d in layers:
        for kind in out:
            for k, rec in _read(d / f"{kind}.json").items():
                if k.startswith("_") or not isinstance(rec, dict):
                    continue
                cur = out[kind].get(k)
                if cur is None:
                    out[kind][k] = dict(rec, _from=[origin])
                    continue
                merged = dict(cur)
                merged["set"] = {**cur.get("set", {}), **rec.get("set", {})}
                for key in ("remove", "addSpawns", "note", "source"):
                    if key in rec:
                        merged[key] = rec[key] if key != "addSpawns" else {**cur.get("addSpawns", {}), **rec[key]}
                merged["_from"] = cur["_from"] + [origin]
                out[kind][k] = merged
    return out


def _prereq_rows(qid: int, rec: dict) -> list[dict]:
    """quest_prereq rows from a quest record {pre, preAny, preAll, breadcrumbs} (tables.rs order)."""
    pre: dict[int, list] = {}
    for p in rec.get("preAll") or []:
        pre[int(p)] = ["all", False]
    for p in rec.get("preAny") or []:
        pre.setdefault(int(p), ["any", False])
    for p in rec.get("pre") or []:
        pre.setdefault(int(p), ["all", False])
    for b in rec.get("breadcrumbs") or []:
        pre.setdefault(int(b), ["any", True])[1] = True
    rows = []
    for p, (mode, bc) in sorted(pre.items()):
        if p == qid:
            continue
        r = {"quest": qid, "pre": p, "mode": mode}
        if bc:
            r["breadcrumb"] = True
        rows.append(r)
    return rows


def apply_quests(tables: dict[str, list], corr: dict[str, dict]) -> dict[int, dict]:
    """Apply quest records to the tables in place (quest, quest_start, quest_end, quest_prereq,
    quest_objective). Returns {quest id: {"fields": [...], "extra": {...}, "from": [...]}} for the
    quests it touched; ``extra`` holds the keys with no column (excl, next, escort, limit, ...)."""
    done: dict[int, dict] = {}
    quests = {int(r["id"]): r for r in tables.get("quest", [])}
    removed: set[int] = set()
    by_quest: dict[str, dict[int, list]] = {}
    for t in ("quest_start", "quest_end", "quest_prereq", "quest_objective"):
        idx: dict[int, list] = {}
        for r in tables.get(t, []):
            idx.setdefault(int(r["quest"]), []).append(r)
        by_quest[t] = idx

    for k, rec in corr.get("quests", {}).items():
        qid = int(k)
        info = {"fields": [], "extra": {}, "from": rec.get("_from", [])}
        if rec.get("remove"):
            removed.add(qid)
            info["fields"].append("remove")
            done[qid] = info
            continue
        s = rec.get("set") or {}
        if not s:
            continue
        q = quests.get(qid)
        if q is None:  # a quest the tables do not have: created with the fields it sets
            q = {"id": qid}
            quests[qid] = q
            tables.setdefault("quest", []).append(q)
        for key, val in s.items():
            if key in QUEST_FIELDS:
                if val is None:
                    q.pop(QUEST_FIELDS[key], None)
                else:
                    q[QUEST_FIELDS[key]] = val
            elif key in ("start", "end"):
                t = "quest_start" if key == "start" else "quest_end"
                by_quest[t][qid] = [{"id": int(i), "kind": kind, "quest": qid}
                                    for kind in ("npc", "object", "item") for i in (val or {}).get(kind, [])]
            elif key == "objectives":
                by_quest["quest_objective"][qid] = [
                    {"quest": qid, "n": n + 1, "kind": o.get("type"), "target": o.get("id"), "count": o.get("count")}
                    for n, o in enumerate(val or [])]
            elif key in PREREQ_KEYS or key == "breadcrumbs":
                continue  # below, all together
            else:
                info["extra"][key] = val
            info["fields"].append(key)
        if any(key in s for key in PREREQ_KEYS + ("breadcrumbs",)):
            old = by_quest["quest_prereq"].get(qid, [])
            base = {
                "pre": [r["pre"] for r in old if not r.get("breadcrumb") and r["mode"] == "all"],
                "preAny": [r["pre"] for r in old if not r.get("breadcrumb") and r["mode"] == "any"],
                "breadcrumbs": [r["pre"] for r in old if r.get("breadcrumb")],
            }
            if any(key in s for key in PREREQ_KEYS):
                base = {"breadcrumbs": base["breadcrumbs"]}
            for key in PREREQ_KEYS + ("breadcrumbs",):
                if key in s:
                    base[key] = s[key] or []
                    info["fields"].append(key)
            by_quest["quest_prereq"][qid] = _prereq_rows(qid, base)
        done[qid] = info

    # breadcrumbFor: X leads to Y (a breadcrumb row on Y), or null: X is nobody's breadcrumb
    for k, rec in corr.get("quests", {}).items():
        s = rec.get("set") or {}
        if "breadcrumbFor" not in s:
            continue
        x, y = int(k), s["breadcrumbFor"]
        for q, rows in by_quest["quest_prereq"].items():
            if y is None or q != int(y):
                by_quest["quest_prereq"][q] = [r for r in rows if not (r["pre"] == x and r.get("breadcrumb"))]
        if y is not None:
            rows = by_quest["quest_prereq"].setdefault(int(y), [])
            for r in rows:
                if r["pre"] == x:
                    r["breadcrumb"] = True
                    break
            else:
                rows.append({"quest": int(y), "pre": x, "mode": "any", "breadcrumb": True})

    # remove: the quest and every link to it
    if removed:
        for t in by_quest:
            for q in list(by_quest[t]):
                if q in removed:
                    del by_quest[t][q]
        for q, rows in by_quest["quest_prereq"].items():
            by_quest["quest_prereq"][q] = [r for r in rows if r["pre"] not in removed]
        tables["quest"] = [r for r in tables.get("quest", []) if int(r["id"]) not in removed]

    for t, idx in by_quest.items():
        tables[t] = [r for q in sorted(idx) for r in idx[q]]
    return done


def spawn_overrides(corr: dict[str, dict], kind: str) -> dict[int, dict]:
    """{id: {"maps": {uiMap: [[x%, y%], ...]}, "all": bool}} from `addSpawns` (replaces that map's
    spawns) and `set.spawns` (replaces every spawn), for kind "npcs" or "objects"."""
    out: dict[int, dict] = {}
    for k, rec in corr.get(kind, {}).items():
        maps: dict[int, list] = {}
        whole = False
        s = (rec.get("set") or {}).get("spawns")
        if isinstance(s, dict):
            whole = True
            for ui, v in s.items():
                maps[int(ui)] = [list(map(float, p[:2])) for p in (v or {}).get("pts", [])]
        for ui, v in (rec.get("addSpawns") or {}).items():
            maps[int(ui)] = [list(map(float, p[:2])) for p in (v or {}).get("pts", [])]
        if maps or whole:
            out[int(k)] = {"maps": maps, "all": whole}
    return out


def load_tables_corrected(root: Path, tables: tuple[str, ...], senda_dir: Path | None = SENDA_DIR) -> dict[str, list]:
    """Read forever-db tables (data/<name>.jsonl) and apply the quest corrections. Light: for tools
    that need the quest tables only (tools/build.py --refresh-prereq)."""
    out: dict[str, list] = {}
    for t in set(tables) | {"quest", "quest_start", "quest_end", "quest_prereq", "quest_objective"}:
        p = Path(root) / "data" / f"{t}.jsonl"
        rows = []
        if p.exists():
            with open(p, encoding="utf-8") as fh:
                rows = [json.loads(line) for line in fh if line.strip()]
        out[t] = rows
    apply_quests(out, load(root, senda_dir))
    return out

"""Pipeline `tips`: investiga trucos y estrategias de leveo por raza/clase, con citas."""
from __future__ import annotations

import hashlib
import sys
from datetime import date

from . import prompts, state
from .claims import normalize_text
from .config import Registry, Settings
from .guides import supported_classes_races
from .llm import LLM, BudgetExceeded, LLMError, system_blocks, web_tools

TIP_CATEGORIES = ("route", "quests", "spells", "talents", "macros", "pet", "professions", "gear", "group",
                  "mistakes", "other")

SUBMIT_TIPS = {
    "name": "submit_tips",
    "description": "Entrega los consejos encontrados (puede ser una lista vacía). Llámala una sola vez al final.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "tips": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title_es": {"type": "string"},
                        "body_es": {"type": "string"},
                        "levels": {"type": "array", "items": {"type": "integer"}},
                        "category": {"type": "string", "enum": list(TIP_CATEGORIES)},
                        "citations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {"url": {"type": "string"}, "quote": {"type": "string"}},
                                "required": ["url", "quote"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["title_es", "body_es", "levels", "category", "citations"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["tips"],
        "additionalProperties": False,
    },
}


def tip_id(cls: str, title: str) -> str:
    return hashlib.sha1(f"{cls}\n{normalize_text(title)}".encode()).hexdigest()[:12]


def _validate(inp: dict) -> str | None:
    bad = [t.get("title_es", "?") for t in inp.get("tips", []) if not t.get("citations")]
    if bad:
        return "Cada consejo necesita al menos una cita (url + cita literal). Sin cita: " + ", ".join(bad)
    return None


def run(registry: Registry, settings: Settings, llm: LLM, *, guide: str | None = None,
        limit: int | None = None, out=sys.stdout) -> dict:
    tstate = state.load("tips.json", {"tips": []})
    known = {t["id"] for t in tstate["tips"]}
    targets = []
    for gid, race, cls in supported_classes_races():
        if guide and gid != guide:
            continue
        if (race, cls) not in [(r, c) for _, r, c in targets]:
            targets.append((gid, race, cls))
    if limit is not None:
        targets = targets[:limit]
    system = system_blocks(prompts.TIPS)
    tools = web_tools(settings, registry.domains()) + [SUBMIT_TIPS]
    summary = {"targets": len(targets), "tips": 0, "errors": []}
    today = date.today().isoformat()
    for gid, race, cls in targets:
        existing = [t["title_es"] for t in tstate["tips"] if t["class"] == cls]
        user = (f"Fecha de hoy: {today}\nRaza: {race}\nClase: {cls}\nGuía de Senda: {gid}\n"
                f"Consejos que ya tenemos (no los repitas):\n"
                + ("\n".join(f"- {t}" for t in existing) or "- (ninguno)")
                + "\n\nBusca entre 3 y 8 consejos nuevos, útiles y verificables.")
        try:
            res = llm.tool_loop(f"tips {race} {cls}", system, user, tools, {}, "submit_tips",
                                settings.effort_tips, _validate)
        except BudgetExceeded as e:
            summary["errors"].append(str(e))
            break
        except LLMError as e:
            summary["errors"].append(str(e))
            continue
        if res is None:
            continue
        for t in res["tips"]:
            tid = tip_id(cls, t["title_es"])
            if tid in known:
                continue
            known.add(tid)
            tstate["tips"].append({**t, "id": tid, "class": cls, "race": race, "guide": gid, "found": today,
                                   "processed": False})
            summary["tips"] += 1
        out.write(f"[tips] {race} {cls}: {len(res['tips'])} consejos\n")
    if not llm.dry_run:
        state.save("tips.json", tstate)
    return summary

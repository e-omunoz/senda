"""Pipeline `audit`: Claude revisa cada paso contra fuentes web y QuestieDB y emite veredictos.

Los veredictos se guardan en bruto (state/verdicts.json). La evidencia se confirma y el `status` se
decide en `propose`, que aplica las reglas igual para la API y para Claude Code.
"""
from __future__ import annotations

import json
import sys
import tomllib
from datetime import date

from . import localtools, prompts, state
from .config import Registry, Settings
from .guides import Section, all_sections
from .llm import LLM, BudgetExceeded, LLMError, system_blocks, web_tools

VERDICTS = ("ok", "incorrect", "outdated", "uncertain")
CHANGEABLE = ("text", "tip", "quest", "npc", "item", "count", "spells", "level", "at", "wps", "radius",
              "node", "zone", "obj", "prof", "skill")

EVIDENCE_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["web", "questie", "observation"]},
        "url": {"type": "string"},
        "quote": {"type": "string"},
        "ref": {"type": "string"},
        "supports": {"type": "string", "enum": ["supports", "contradicts", "neutral"]},
    },
    "required": ["kind", "url", "quote", "ref", "supports"],
    "additionalProperties": False,
}

SUBMIT_VERDICTS = {
    "name": "submit_verdicts",
    "description": "Entrega el resultado final de la auditoría: un veredicto por cada paso recibido. "
                   "Llámala una sola vez, al terminar.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "verdicts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "step_id": {"type": "string"},
                        "verdict": {"type": "string", "enum": list(VERDICTS)},
                        "proposed_status": {"type": "string", "enum": ["verified", "unverified", "disputed"]},
                        "changes": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "field": {"type": "string", "enum": list(CHANGEABLE)},
                                    "value_json": {"type": "string"},
                                    "reason_es": {"type": "string"},
                                },
                                "required": ["field", "value_json", "reason_es"],
                                "additionalProperties": False,
                            },
                        },
                        "evidence": {"type": "array", "items": EVIDENCE_SCHEMA},
                        "tip_es": {"type": "string"},
                        "notes_es": {"type": "string"},
                    },
                    "required": ["step_id", "verdict", "proposed_status", "changes", "evidence", "tip_es",
                                 "notes_es"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["verdicts"],
        "additionalProperties": False,
    },
}

QUESTIE_LOOKUP = {
    "name": "questie_lookup",
    "description": "Consulta la base de datos local QuestieDB (Forever) por id. Úsala para comprobar que una "
                   "misión, PNJ, objeto u objeto del mundo existe y ver sus datos (quién la da/recibe, "
                   "coordenadas, nivel, prerrequisitos, razas/clases). Úsala antes de citar `questie:`.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": list(localtools.LOOKUP_KINDS)},
            "id": {"type": "integer"},
        },
        "required": ["kind", "id"],
        "additionalProperties": False,
    },
}

OBS_LOOKUP = {
    "name": "observations_lookup",
    "description": "Busca observaciones registradas en partida por el addon (misión aceptada/entregada, PNJ "
                   "visto, punto de vuelo, hogar). Úsala para saber si un paso está confirmado en el juego.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["accept", "turnin", "npc_seen", "fp", "bind", "quest", "npc"]},
            "id": {"type": "integer"},
        },
        "required": ["kind", "id"],
        "additionalProperties": False,
    },
}


def validate_verdicts(expected: set[str]):
    def check(inp: dict) -> str | None:
        vs = inp.get("verdicts")
        if not isinstance(vs, list):
            return "Falta `verdicts` (lista)."
        got = {v.get("step_id") for v in vs if isinstance(v, dict)}
        missing = sorted(expected - got)
        extra = sorted(got - expected)
        problems = []
        if missing:
            problems.append("faltan veredictos para: " + ", ".join(missing))
        if extra:
            problems.append("ids que no estaban en la sección: " + ", ".join(extra))
        for v in vs:
            for ch in v.get("changes", []):
                try:
                    json.loads(ch.get("value_json", ""))
                except (json.JSONDecodeError, TypeError):
                    problems.append(f"{v.get('step_id')}: value_json no es JSON válido en {ch.get('field')}")
        return ("Corrige y vuelve a llamar a submit_verdicts: " + "; ".join(problems)) if problems else None
    return check


def _section_chunk_toml(section: Section, step_ids: list[str]) -> str:
    """Texto TOML de la sección limitado a los pasos del trozo (cabecera + esos [[step]])."""
    text = section.text()
    if len(step_ids) == len(section.steps):
        return text
    lines = text.splitlines()
    out, header_done = [], False
    block: list[str] = []

    def flush():
        if block:
            body = "\n".join(block)
            try:
                sid = tomllib.loads(body.replace("[[step]]", "", 1)).get("id")
            except tomllib.TOMLDecodeError:
                sid = None
            if sid in step_ids:
                out.extend(block)
    for ln in lines:
        if ln.strip().startswith("[[step]]"):
            flush()
            block = [ln]
            header_done = True
            continue
        if header_done:
            block.append(ln)
        else:
            out.append(ln)
    flush()
    return "\n".join(out)


def _relevant_claims(steps: list[dict], limit: int = 25) -> str:
    data = state.load("claims.json", {"claims": []})["claims"]
    qs = {s.get("quest") for s in steps} | {q for s in steps for q in s.get("quests", [])}
    ns = {s.get("npc") for s in steps}
    items = {s.get("item") for s in steps}
    hits = [c for c in data if set(c.get("quest_ids", [])) & qs or set(c.get("npc_ids", [])) & ns
            or set(c.get("item_ids", [])) & items]
    hits = sorted(hits, key=lambda c: c.get("date", ""), reverse=True)[:limit]
    if not hits:
        return "(ninguna afirmación reciente menciona estos ids)"
    return "\n".join(f"- [{c['tier']}] {c['date']} {c['summary_es']} — «{c['quote'][:300]}» ({c['url']})"
                     for c in hits)


def _prioritize(sections: list[Section]) -> list[Section]:
    """Primero las secciones con pasos en cola (afirmaciones nuevas), luego las menos revisadas."""
    queue = state.load("audit_queue.json", {"steps": {}})["steps"]

    def key(s: Section):
        queued = sum(1 for st in s.steps if st.get("id") in queue)
        checked = min((st.get("checked", "0000-00-00") for st in s.steps), default="0000-00-00")
        unverified = sum(1 for st in s.steps if st.get("status") != "verified")
        return (-queued, checked, -unverified)
    return sorted(sections, key=key)


def run(registry: Registry, settings: Settings, llm: LLM, *, guide: str | None = None,
        section: str | None = None, limit: int | None = None, out=sys.stdout) -> dict:
    sections = all_sections(guide)
    if section:
        sections = [s for s in sections if s.id == section or s.file.stem == section]
    sections = _prioritize(sections)
    if limit is not None:
        sections = sections[:limit]
    summary = {"sections": 0, "steps": 0, "errors": [], "runs": []}
    if not sections:
        out.write("[audit] no hay secciones que auditar (¿data/guides vacío o --guide incorrecto?)\n")
        return summary
    verify = localtools.verify_report(guide)   # local y gratis: también en dry-run
    system = system_blocks(prompts.AUDIT)
    tools = web_tools(settings, registry.domains()) + [QUESTIE_LOOKUP, OBS_LOOKUP, SUBMIT_VERDICTS]
    vstate = state.load("verdicts.json", {"runs": []})
    today = date.today().isoformat()
    for sec in sections:
        steps = [s for s in sec.steps if "id" in s]
        for i in range(0, len(steps), settings.steps_per_call):
            chunk = steps[i:i + settings.steps_per_call]
            ids = [s["id"] for s in chunk]
            tool_log: list[dict] = []

            def h_lookup(inp, _log=tool_log):
                found, text = localtools.lookup(inp["kind"], int(inp["id"]))
                _log.append({"tool": "questie_lookup", "kind": inp["kind"], "id": inp["id"], "found": found})
                return text, False

            def h_obs(inp, _log=tool_log):
                hits = localtools.observations(inp["kind"], int(inp["id"]))
                _log.append({"tool": "observations_lookup", "kind": inp["kind"], "id": inp["id"],
                             "hits": len(hits)})
                return json.dumps(hits, ensure_ascii=False)[:6000] or "[]", False

            user = (f"Fecha de hoy: {today}\nGuía: {sec.guide}\nArchivo: {sec.rel}\n"
                    f"Pasos a auditar ({len(ids)}): {', '.join(ids)}\n\n"
                    f"<seccion_toml>\n{_section_chunk_toml(sec, ids)}\n</seccion_toml>\n\n"
                    f"<verify_py>\n{localtools.findings_for_steps(verify, set(ids)) if verify is not None else '(no ejecutado)'}\n</verify_py>\n\n"
                    f"<afirmaciones_recientes>\n{_relevant_claims(chunk)}\n</afirmaciones_recientes>")
            label = f"audit {sec.guide}/{sec.id} [{i + 1}-{i + len(chunk)}]"
            try:
                res = llm.tool_loop(label, system, user, tools, {"questie_lookup": h_lookup,
                                    "observations_lookup": h_obs}, "submit_verdicts", settings.effort_audit,
                                    validate_verdicts(set(ids)))
            except BudgetExceeded as e:
                summary["errors"].append(str(e))
                out.write(f"[audit] presupuesto agotado: {e}\n")
                _save(llm, vstate)
                return summary
            except LLMError as e:
                summary["errors"].append(str(e))
                out.write(f"[audit] ERROR {e}\n")
                continue
            summary["steps"] += len(ids)
            if res is None:
                continue
            run_rec = {"run": f"{today}:{sec.guide}:{sec.id}:{i}", "date": today, "guide": sec.guide,
                       "section": sec.id, "file": sec.rel, "model": settings.model, "origin": "api",
                       "verdicts": res["verdicts"], "tool_log": tool_log, "processed": False}
            vstate["runs"].append(run_rec)
            summary["runs"].append(run_rec["run"])
            out.write(f"[audit] {label}: {len(res['verdicts'])} veredictos\n")
        summary["sections"] += 1
    _save(llm, vstate)
    return summary


def _save(llm: LLM, vstate) -> None:
    if not llm.dry_run:
        state.save("verdicts.json", vstate)

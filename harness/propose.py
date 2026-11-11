"""Pipeline `propose`: convierte veredictos, afirmaciones y consejos en ediciones TOML + informe.

Es el único punto que escribe en data/. No llama a la API: sirve igual para el camino de la API
(audit/watch/tips) y para el de Claude Code (archivos en harness/state/inbox/).
"""
from __future__ import annotations

import difflib
import json
import shutil
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from . import rules, state, tomledit
from .claims import Claim
from . import config
from .config import ROOT, Registry, rel
from .evidence import Confirmer
from .guides import step_index
from .rules import Evidence

INT_FIELDS = ("quest", "npc", "item", "count", "level", "skill", "zone", "obj")
STR_FIELDS = ("text", "tip", "node", "prof")
APPLY_ON = ("incorrect", "outdated")


@dataclass
class StepChange:
    step_id: str
    file: str
    verdict: str
    before_status: str
    after_status: str
    rule: str
    applied: list[str] = field(default_factory=list)      # descripciones en español
    skipped: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    notes: str = ""
    origin: str = "api"


@dataclass
class Proposal:
    today: str
    changes: list[StepChange] = field(default_factory=list)
    claims: list[tuple[Claim, list[str]]] = field(default_factory=list)   # (claim, step_ids afectados)
    tips_added: list[dict] = field(default_factory=list)
    tips_skipped: list[tuple[dict, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    files: dict[str, tuple[str, str]] = field(default_factory=dict)       # rel -> (antes, después)

    @property
    def has_edits(self) -> bool:
        return any(a != b for a, b in self.files.values())


# --------------------------------------------------------------------------- validación de valores

def _is_num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _is_point(v) -> bool:
    return (isinstance(v, list) and len(v) in (3, 4) and isinstance(v[0], int) and not isinstance(v[0], bool)
            and _is_num(v[1]) and _is_num(v[2]) and 0 <= v[1] <= 100 and 0 <= v[2] <= 100
            and (len(v) == 3 or isinstance(v[3], str)))


def coerce_value(fld: str, raw: str):
    """Decodifica value_json y comprueba el tipo del campo. Lanza ValueError si no encaja."""
    try:
        v = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError as e:
        raise ValueError(f"value_json inválido: {e}") from e
    if fld in INT_FIELDS:
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise ValueError(f"{fld} debe ser entero positivo")
    elif fld in STR_FIELDS:
        if not isinstance(v, str) or not v.strip():
            raise ValueError(f"{fld} debe ser texto")
        v = v.strip()
    elif fld == "radius":
        if not _is_num(v) or v < 1:
            raise ValueError("radius debe ser un número >= 1")
    elif fld == "spells":
        if not isinstance(v, list) or not v or not all(isinstance(x, int) and not isinstance(x, bool) for x in v):
            raise ValueError("spells debe ser una lista de enteros")
    elif fld == "at":
        if not _is_point(v):
            raise ValueError("at debe ser [uiMapID, x, y] con x/y en 0-100")
    elif fld == "wps":
        if not isinstance(v, list) or not all(_is_point(p) for p in v):
            raise ValueError("wps debe ser una lista de puntos [uiMapID, x, y, \"etiqueta\"]")
    else:
        raise ValueError(f"campo no editable: {fld}")
    return v


def source_strings(evidence: list[Evidence]) -> list[str]:
    out = []
    for e in evidence:
        if not e.confirmed or e.supports == "neutral":
            continue
        s = e.url if e.kind == "web" else e.ref
        if s and s not in out:
            out.append(s)
    return out


# --------------------------------------------------------------------------- carga de entradas

def _pending_verdict_runs() -> list[tuple[dict, Path | None]]:
    runs = [(r, None) for r in state.load("verdicts.json", {"runs": []})["runs"] if not r.get("processed")]
    from .claims import extract_json
    for f in state.inbox_files("verdicts"):
        try:
            raw = extract_json(f.read_text(encoding="utf-8"))
        except ValueError as e:
            runs.append(({"run": f.name, "verdicts": [], "error": str(e), "origin": "claude-code"}, f))
            continue
        if isinstance(raw, list):
            raw = {"verdicts": raw}
        raw.setdefault("run", f.name)
        raw["origin"] = "claude-code"
        runs.append((raw, f))
    return runs


# --------------------------------------------------------------------------- núcleo

def apply_verdict(text: str, v: dict, confirmer: Confirmer, today: str, *, origin: str = "api",
                  file_rel: str = "") -> tuple[str, StepChange]:
    """Aplica un veredicto a un texto TOML. Devuelve (texto_nuevo, resumen). Pura salvo la confirmación."""
    sid = v["step_id"]
    step = tomledit.get_step(text, sid)
    current = step.get("status", "unverified")
    evidence = confirmer.confirm_all(v.get("evidence", []), step_id=sid)
    verdict = v.get("verdict", "uncertain")
    decision = rules.decide(evidence, v.get("proposed_status", "unverified"))
    ch = StepChange(sid, file_rel, verdict, current, current, "", evidence=evidence,
                    notes=v.get("notes_es", ""), origin=origin)
    ch.skipped += decision.reasons and [f"reglas: {'; '.join(decision.reasons)}"] or []
    confirmed_any = any(e.confirmed and e.supports != "neutral" for e in evidence)

    # 1) cambios de valor
    new_values = {}
    if verdict in APPLY_ON:
        for c in v.get("changes", []):
            fld = c.get("field", "")
            try:
                val = coerce_value(fld, c.get("value_json", ""))
            except ValueError as e:
                ch.skipped.append(f"{fld}: {e}")
                continue
            if step.get(fld) == val:
                continue
            if not confirmed_any:
                ch.skipped.append(f"{fld} → {json.dumps(val, ensure_ascii=False)}: sin evidencia confirmada, "
                                  "no se aplica (revisión manual)")
                continue
            if fld in ("at", "wps") and not any(e.confirmed and e.supports == "supports" and e.kind != "questie"
                                                for e in evidence):
                # No se copian coordenadas de QuestieDB ("all rights reserved"): hace falta web u observación.
                ch.skipped.append(f"{fld}: coordenadas sin fuente web ni observación confirmada; no se copian "
                                  "de QuestieDB")
                continue
            new_values[fld] = (val, c.get("reason_es", ""))
    elif v.get("changes"):
        ch.skipped.append(f"veredicto «{verdict}» con cambios: no se aplican")

    for fld, (val, reason) in new_values.items():
        before = step.get(fld)
        text = tomledit.set_step_field(text, sid, fld, val)
        ch.applied.append(f"`{fld}`: {json.dumps(before, ensure_ascii=False)} → "
                          f"{json.dumps(val, ensure_ascii=False)}" + (f" ({reason})" if reason else ""))

    # 2) estado
    after = rules.step_status_after(current, decision, bool(new_values))
    if after == "verified" and current != "verified":
        ch.rule = rules.assert_can_verify(evidence)
    elif after == "verified":
        ch.rule = decision.rule or "(ya estaba verificado)"
    if after != current:
        text = tomledit.set_status(text, sid, after, evidence=evidence if after == "verified" else None)
        ch.applied.append(f"`status`: {current} → {after}" + (f" (regla {ch.rule})" if after == "verified" else ""))
    ch.after_status = after

    # 3) fuentes y fecha de revisión
    srcs = source_strings(evidence)
    if srcs:
        before_src = list(tomledit.get_step(text, sid).get("sources", []))
        text = tomledit.append_unique(text, sid, "sources", srcs)
        added = [s for s in srcs if s not in before_src]
        if added:
            ch.applied.append("`sources` += " + ", ".join(added))
    if confirmed_any:
        if tomledit.get_step(text, sid).get("checked") != today:
            text = tomledit.set_step_field(text, sid, "checked", today)

    # 4) consejo
    tip = (v.get("tip_es") or "").strip()
    if tip:
        if confirmed_any:
            t2 = tomledit.append_tip(text, sid, tip)
            if t2 != text:
                ch.applied.append(f"`tip` += «{tip}»")
                text = t2
        else:
            ch.skipped.append(f"consejo sin evidencia confirmada: «{tip}»")
    return text, ch


def _match_claims(claims: list[Claim], idx: dict) -> list[tuple[Claim, list[str]]]:
    by_q: dict[int, list[str]] = {}
    by_n: dict[int, list[str]] = {}
    by_i: dict[int, list[str]] = {}
    for sid, (_, s) in idx.items():
        for q in [s.get("quest")] + list(s.get("quests", [])):
            if q:
                by_q.setdefault(q, []).append(sid)
        if s.get("npc"):
            by_n.setdefault(s["npc"], []).append(sid)
        if s.get("item"):
            by_i.setdefault(s["item"], []).append(sid)
    out = []
    for c in claims:
        hit: list[str] = []
        for q in c.quest_ids:
            hit += by_q.get(q, [])
        for n in c.npc_ids:
            hit += by_n.get(n, [])
        for i in c.item_ids:
            hit += by_i.get(i, [])
        out.append((c, sorted(set(hit))))
    return out


def knowledge_tip_block(tip: dict, cites: list[Evidence]) -> dict:
    lv = tip.get("levels") or []
    lvl = f"Niveles {lv[0]}-{lv[-1]}. " if len(lv) >= 1 else ""
    best = max((rules_tier_rank(e.tier) for e in cites), default=1)
    prefix = "" if best >= 2 else "(Sin verificar, fuente comunitaria) "
    links = " ".join(f"[{_short(e.url)}]({e.url})" for e in cites)
    return {"heading": tip["title_es"], "body": f"{prefix}{lvl}{tip['body_es'].strip()}\n\nFuentes: {links}"}


def rules_tier_rank(t: str) -> int:
    from .config import TIER_RANK
    return TIER_RANK.get(t, 1)


def _short(url: str) -> str:
    return url.split("://", 1)[-1].split("/", 1)[0].removeprefix("www.")


def _knowledge_file(cls: str) -> Path:
    return config.DATA / "knowledge" / cls.lower() / "harness-tips.toml"


def _new_knowledge_page(cls: str) -> str:
    return (f'id = "{cls.lower()}-harness-tips"\nclass = "{cls}"\nkind = "page"\n'
            f'title = "Trucos de la comunidad"\norder = 900\nstatus = "unverified"\nsources = []\n')


def build(registry: Registry, *, offline: bool = False, confirmer: Confirmer | None = None,
          today: str | None = None) -> tuple[Proposal, dict]:
    """Calcula todas las ediciones en memoria. Devuelve (propuesta, marcas para guardar estado)."""
    today = today or date.today().isoformat()
    prop = Proposal(today)
    if confirmer is None:
        from .localtools import verify_report, verify_verdicts
        vv = {} if offline else verify_verdicts(verify_report())
        confirmer = Confirmer(registry, offline=offline, verify_verdicts=vv)
    idx = step_index()
    texts: dict[Path, str] = {}

    def get_text(p: Path) -> str:
        if p not in texts:
            texts[p] = p.read_text(encoding="utf-8")
        return texts[p]

    marks = {"runs": [], "inbox": [], "claims": [], "tips": []}
    # Veredictos
    for run, f in _pending_verdict_runs():
        if run.get("error"):
            prop.errors.append(f"{run['run']}: {run['error']}")
        for v in run.get("verdicts", []):
            sid = v.get("step_id")
            if sid not in idx:
                prop.errors.append(f"{run.get('run')}: paso {sid!r} no existe en data/")
                continue
            p = idx[sid][0]
            try:
                new, ch = apply_verdict(get_text(p), v, confirmer, today, origin=run.get("origin", "api"),
                                        file_rel=rel(p))
            except (tomledit.TomlEditError, rules.RuleViolation) as e:
                prop.errors.append(f"{sid}: {e}")
                continue
            texts[p] = new
            prop.changes.append(ch)
        (marks["inbox"] if f else marks["runs"]).append(f or run.get("run"))

    # Afirmaciones
    from .watch import pending_claims
    claims = pending_claims(registry, offline=offline)
    prop.claims = _match_claims(claims, idx)
    marks["claims"] = claims
    marks["inbox"] += state.inbox_files("claims")

    # Consejos -> páginas de conocimiento (de `tips` y de Claude Code: state/inbox/tips-*.json)
    tstate = state.load("tips.json", {"tips": []})
    pending = [t for t in tstate["tips"] if not t.get("processed")]
    known_tips = {t["id"] for t in tstate["tips"]}
    marks["tips_new"] = []
    from .claims import extract_json
    from .tips import tip_id
    for f in state.inbox_files("tips"):
        try:
            raw = extract_json(f.read_text(encoding="utf-8"))
        except ValueError as e:
            prop.errors.append(f"{f.name}: {e}")
            continue
        meta = raw if isinstance(raw, dict) else {}
        for t in (raw.get("tips", []) if isinstance(raw, dict) else raw):
            if not isinstance(t, dict) or not t.get("title_es") or not t.get("body_es"):
                continue
            cls = str(t.get("class") or meta.get("class") or "").upper()
            if not cls:
                prop.errors.append(f"{f.name}: consejo sin clase: {t.get('title_es')}")
                continue
            t = {"levels": [], "category": "other", "citations": [], **t, "class": cls,
                 "race": t.get("race") or meta.get("race", ""), "guide": t.get("guide") or meta.get("guide", ""),
                 "found": today, "origin": "claude-code"}
            t["id"] = tip_id(cls, t["title_es"])
            if t["id"] in known_tips:
                continue
            known_tips.add(t["id"])
            pending.append(t)
            marks["tips_new"].append(t)
        marks["inbox"].append(f)
    for t in pending:
        cites = confirmer.confirm_all([{"kind": "web", "url": c["url"], "quote": c["quote"],
                                        "supports": "supports"} for c in t.get("citations", [])])
        ok = [e for e in cites if e.confirmed]
        marks["tips"].append(t["id"])
        if not ok:
            prop.tips_skipped.append((t, "ninguna cita se pudo confirmar en su página"))
            continue
        p = _knowledge_file(t["class"])
        text = texts.get(p) or (p.read_text(encoding="utf-8") if p.exists() else _new_knowledge_page(t["class"]))
        try:
            text = tomledit.append_table(text, "block", knowledge_tip_block(t, ok))
            import tomllib
            srcs = list(tomllib.loads(text).get("sources", []))
            srcs += [e.url for e in ok if e.url not in srcs]
            text = tomledit.set_top_field(text, "sources", srcs)
        except (tomledit.TomlEditError, rules.RuleViolation) as e:
            prop.errors.append(f"consejo {t['id']}: {e}")
            continue
        texts[p] = text
        prop.tips_added.append({**t, "_file": rel(p),
                                "_tiers": sorted({e.tier for e in ok})})

    for p, after in texts.items():
        before = p.read_text(encoding="utf-8") if p.exists() else ""
        prop.files[rel(p)] = (before, after)
    return prop, marks


def write_files(prop: Proposal) -> list[str]:
    written = []
    for rel, (before, after) in prop.files.items():
        if before == after:
            continue
        p = ROOT / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(after)
        written.append(rel)
    return written


def diff_text(prop: Proposal) -> str:
    out = []
    for rel, (before, after) in prop.files.items():
        if before != after:
            out += difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                        f"a/{rel}", f"b/{rel}")
    return "".join(out)


def commit_state(prop: Proposal, marks: dict) -> None:
    """Marca como procesado lo consumido y actualiza la cola de auditoría."""
    vs = state.load("verdicts.json", {"runs": []})
    for r in vs["runs"]:
        if r.get("run") in marks["runs"]:
            r["processed"] = True
    vs["runs"] = vs["runs"][-500:]
    state.save("verdicts.json", vs)
    done = config.INBOX / "processed"
    for f in marks["inbox"]:
        done.mkdir(parents=True, exist_ok=True)
        shutil.move(str(f), str(done / f.name))
    cs = state.load("claims.json", {"claims": []})
    ids = {c["id"] for c in cs["claims"]}
    for c in marks["claims"]:
        if c.id not in ids:
            cs["claims"].append({**c.to_dict(), "processed": True})
    for c in cs["claims"]:
        c["processed"] = True
    state.save("claims.json", cs)
    q = state.load("audit_queue.json", {"steps": {}})
    for c, sids in prop.claims:
        for sid in sids:
            q["steps"].setdefault(sid, [])
            if c.id not in q["steps"][sid]:
                q["steps"][sid].append(c.id)
    for ch in prop.changes:   # los pasos auditados salen de la cola
        q["steps"].pop(ch.step_id, None)
    state.save("audit_queue.json", q)
    ts = state.load("tips.json", {"tips": []})
    ts["tips"] += [dict(t) for t in marks.get("tips_new", [])]
    for t in ts["tips"]:
        if t["id"] in marks["tips"]:
            t["processed"] = True
    state.save("tips.json", ts)


def run(registry: Registry, *, dry_run: bool = False, offline: bool = False, out=sys.stdout,
        cost: dict | None = None) -> tuple[Proposal, Path | None]:
    from .report import render
    prop, marks = build(registry, offline=offline)
    report = render(prop, cost=cost)
    if dry_run:
        out.write(diff_text(prop) or "[propose] sin cambios en data/\n")
        out.write("\n" + report)
        return prop, None
    written = write_files(prop)
    reports = config.REPORTS
    reports.mkdir(parents=True, exist_ok=True)
    rp = reports / f"{prop.today}.md"
    n = 2
    while rp.exists():
        rp = reports / f"{prop.today}-{n}.md"
        n += 1
    rp.write_text(report, encoding="utf-8", newline="\n")
    commit_state(prop, marks)
    out.write(f"[propose] {len(written)} archivo(s) de datos modificados; informe: {rel(rp)}\n")
    return prop, rp

#!/usr/bin/env python3
"""Métricas de Senda para la web (GitHub Pages). Solo stdlib.

    python tools/site_metrics.py --out _site     # escribe _site/metricas/index.html (autónoma) y metrics.json
    python tools/site_metrics.py --json          # solo imprime las cifras

La página sale en español con un interruptor a inglés (sin recargar), tema claro/oscuro y ningún recurso
externo. `tools/site.py` la incorpora al sitio con el marco normal (página `metricas/`); este módulo también
la genera por sí solo para CI y para los tests.

Cifras (todas leídas de lo que hay en el repo, nada inventado):
  - por guía: misiones, horas estimadas y XP por hora (data/scores/<guía>.json de tools/route_score.py),
    pasos verificados / sin verificar / en disputa, cobertura de fuentes, pasos opcionales y misiones
    opcionales / descartadas por el filtro de eficiencia;
  - malla de navegación: nav/eval/report.md y report-lua.md (rutas halladas, tiempo de fotograma);
  - datos: nombres del juego (data/locale) frente a los {quest:N} {npc:N}... que usan las guías, y la
    cobertura de data/lookup/coverage.json;
  - historial de cambios (CHANGELOG.md).
"""
from __future__ import annotations

import argparse
import html
import importlib.util
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import localenames  # noqa: E402

TOKEN_FIELDS = ("text", "tip", "why", "note")
CHANGELOG_VERSIONS = 3


# ------------------------------------------------------------------ recogida
def _json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_site_module():
    """tools/site.py (se llama como el módulo `site` de la stdlib: se carga por ruta)."""
    spec = importlib.util.spec_from_file_location("senda_site_for_metrics", TOOLS / "site.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _distinct_quests(steps) -> int:
    return len({s["quest"] for s in steps if isinstance(s.get("quest"), int) and s.get("do") == "accept"})


def guide_metrics(guide: dict, steps: list[dict], score: dict | None) -> dict:
    status = {"verified": 0, "unverified": 0, "disputed": 0}
    for s in steps:
        st = str(s.get("status") or "unverified").lower()
        status[st if st in status else "unverified"] += 1
    n = len(steps)
    with_src = sum(1 for s in steps if s.get("sources"))
    m = {
        "id": guide["id"], "title": str(guide.get("title") or guide["id"]),
        "steps": n, **status,
        "with_sources": with_src,
        "sources_pct": round(100 * with_src / n, 1) if n else 0.0,
        "optional_steps": sum(1 for s in steps if s.get("optional")),
        "quests": _distinct_quests(steps),
        "scored": False,
    }
    if score and isinstance(score.get("summary"), dict):
        sm = score["summary"]
        quest_s = float(sm.get("minutes_quests", 0)) * 60
        overhead_s = sum(float(v) for v in (sm.get("overhead_s") or {}).values())
        hours = (quest_s + overhead_s) / 3600
        xp = sum(int(q.get("xp") or 0) for q in score.get("quests", {}).values())
        m.update({
            "scored": True, "quests": int(sm.get("quests", m["quests"])),
            "keep": int(sm.get("keep", 0)), "optional": int(sm.get("optional", 0)), "drop": int(sm.get("drop", 0)),
            "hours_quests": round(quest_s / 3600, 1), "hours_overhead": round(overhead_s / 3600, 1),
            "hours": round(hours, 1), "xp": xp,
            "xp_per_hour": round(xp / hours) if hours else 0,
            "hours_saved": round(float(sm.get("minutes_dropped", 0)) / 60, 1),
            "xp_dropped": int(sm.get("xp_dropped", 0)),
        })
    return m


def nav_metrics(root: Path) -> dict:
    """Cifras de nav/eval/report.md y report-lua.md (las escribe `senda-nav eval` / `senda-nav-lua`)."""
    out: dict = {"available": False}
    rep = root / "nav" / "eval" / "report.md"
    lua = root / "nav" / "eval" / "report-lua.md"
    text = rep.read_text(encoding="utf-8", errors="replace") if rep.is_file() else ""
    ltext = lua.read_text(encoding="utf-8", errors="replace") if lua.is_file() else ""

    def num(rx: str, src: str, cast=float):
        m = re.search(rx, src)
        return cast(m.group(1).rstrip(".")) if m else None

    m = re.search(r"Routes:\s*(\d+);\s*found:\s*(\d+)", text)
    if m:
        out.update(available=True, routes=int(m.group(1)), found=int(m.group(2)))
    m = re.search(r"Walks found:\s*(\d+) of (\d+)", ltext)
    if m:
        out.update(available=True, lua_found=int(m.group(1)), lua_routes=int(m.group(2)))
    out["off_links"] = num(r"leaving the coarse grid's links: \*\*(\d+)\*\*", text, int)
    out["fine_off_pct"] = num(r"\(([\d.]+) %\)", text)
    out["ratio_median"] = num(r"Line length / straight line: median ([\d.]+)", text)
    out["ratio_max"] = num(r"Line length / straight line: median [\d.]+, max ([\d.]+)", text)
    out["longest_frame_ms"] = num(r"longest frame ([\d.]+) ms", ltext)
    out["p99_frame_ms"] = num(r"99th percentile ([\d.]+) ms", ltext)
    out["frames"] = num(r"over (\d+) frames", ltext, int)
    out["slice_ms"] = num(r"`Step\(([\d.]+)\)`", ltext)
    out["max_frames_walk"] = num(r"Most frames for one walk: (\d+)", ltext, int)
    out["lua_mem_mb"] = num(r"at most ([\d.]+) MB", ltext)
    out["budget_ms"] = 2.0
    packs = []
    for m in re.finditer(r"^\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*([\d.]+) MB\s*\|\s*([\d.]+) MB\s*\|"
                         r"\s*([\d.]+) MB\s*\|", text, re.M):
        packs.append({"map": int(m.group(1)), "sectors": int(m.group(2)), "nodes": int(m.group(4)),
                      "mb": float(m.group(7))})
    out["packs"] = packs
    return out


def data_metrics(root: Path, steps_by_guide: dict[str, list[dict]]) -> dict:
    """Nombres: fichas de los textos frente a data/locale/esES; búsquedas: data/lookup/coverage.json."""
    data_root = root / "data"
    used: dict[str, set[int]] = {k: set() for k in localenames.KINDS}
    seen_steps: set[int] = set()
    for steps in steps_by_guide.values():
        for s in steps:
            if id(s) in seen_steps:
                continue
            seen_steps.add(id(s))
            for f in TOKEN_FIELDS:
                v = s.get(f)
                if isinstance(v, str):
                    for kind, ident in localenames.TOKEN_RE.findall(v):
                        if kind in used:
                            used[kind].add(int(ident))
    have = localenames.load(data_root, "esES") if data_root.is_dir() else {}
    kinds = []
    tot_used = tot_have = tot_game = 0
    for kind in localenames.KINDS:
        entries = have.get(kind, {})
        u = used[kind]
        covered = sum(1 for i in u if i in entries)
        game = sum(1 for i in u if str(entries.get(i, {}).get("source", "")).startswith("ingame:"))
        tot_used += len(u)
        tot_have += covered
        tot_game += game
        kinds.append({"kind": kind, "used": len(u), "covered": covered, "from_game": game, "known": len(entries)})
    lookup = _json(data_root / "lookup" / "coverage.json") or {}
    anysrc = (lookup.get("any_source") or {})
    return {
        "names_used": tot_used, "names_covered": tot_have, "names_from_game": tot_game,
        "names_covered_pct": round(100 * tot_have / tot_used, 1) if tot_used else 0.0,
        "names_game_pct": round(100 * tot_game / tot_used, 1) if tot_used else 0.0,
        "kinds": kinds,
        "lookup": {
            "available": bool(anysrc),
            "all": anysrc.get("all") and {k: anysrc["all"][k] for k in ("pct", "total", "with_source")},
            "objective": anysrc.get("objective") and {k: anysrc["objective"][k] for k in ("pct", "total", "with_source")},
            "reward": anysrc.get("reward") and {k: anysrc["reward"][k] for k in ("pct", "total", "with_source")},
            "quests_used": (lookup.get("guides") or {}).get("quests_used"),
            "forever_db": (lookup.get("forever_db") or {}).get("version"),
        },
    }


def changelog_versions(root: Path, limit: int = CHANGELOG_VERSIONS) -> list[dict]:
    p = root / "CHANGELOG.md"
    if not p.is_file():
        return []
    out: list[dict] = []
    cur = None
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^##\s+\[([^\]]+)\](?:\s*-\s*(\S+))?", line)
        if m:
            if cur and cur["items"]:
                out.append(cur)
            if m.group(1).lower().startswith("sin publicar"):
                cur = None
                continue
            cur = {"version": m.group(1), "date": m.group(2) or "", "items": []}
            if len(out) >= limit:
                cur = None
                break
            continue
        if cur is None:
            continue
        m = re.match(r"^###\s+(.*)", line)
        if m:
            cur["items"].append(("h", m.group(1).strip()))
        elif re.match(r"^- ", line):
            cur["items"].append(("li", line[2:].strip()))
        elif line.startswith("  ") and cur["items"] and cur["items"][-1][0] == "li" and line.strip():
            cur["items"][-1] = ("li", cur["items"][-1][1] + " " + line.strip())
    if cur and cur["items"] and len(out) < limit:
        out.append(cur)
    return out


def collect(root: Path = REPO_ROOT, data=None) -> dict:
    root = Path(root)
    if data is None:
        data = load_site_module().Data(root)
    steps_by_guide = {g["id"]: data.all_steps(g) for g in data.guides}
    guides = []
    for g in data.guides:
        score = _json(root / "data" / "scores" / f"{g['id']}.json")
        guides.append(guide_metrics(g, steps_by_guide[g["id"]], score))
    uniq: dict[str, dict] = {}
    for steps in steps_by_guide.values():
        for s in steps:
            uniq[str(s.get("id") or id(s))] = s
    return {
        "version": data.version, "guides": guides,
        "unique_steps": len(uniq),
        "unique_verified": sum(1 for s in uniq.values() if str(s.get("status")).lower() == "verified"),
        "nav": nav_metrics(root),
        "data": data_metrics(root, steps_by_guide),
        "changelog": changelog_versions(root),
    }


# ------------------------------------------------------------------ texto
T = {
    "eyebrow": ("Proyecto", "Project"),
    "title": ("Métricas de Senda", "Senda metrics"),
    "lead": ("Cifras medidas sobre los datos del repositorio, regeneradas con cada publicación. Los tiempos son "
             "estimaciones del modelo de eficiencia, no cronometrajes.",
             "Figures measured on the repository data, regenerated on every release. Times are estimates from the "
             "efficiency model, not stopwatch runs."),
    "lang_btn": ("English", "Español"),
    "s_guides": ("Guías", "Guides"),
    "s_nav": ("Malla de navegación", "Navigation mesh"),
    "s_data": ("Cobertura de datos", "Data coverage"),
    "s_changes": ("Cambios recientes", "Recent changes"),
    "guide": ("Guía", "Guide"), "quests": ("Misiones", "Quests"), "hours": ("Horas", "Hours"),
    "xph": ("XP/hora", "XP/hour"), "verified": ("Verificados", "Verified"),
    "unverified": ("Sin verificar", "Unverified"), "disputed": ("En disputa", "Disputed"),
    "sources": ("Con fuente", "Sourced"), "opt_steps": ("Pasos opc.", "Optional steps"),
    "opt_q": ("Misiones opc.", "Optional quests"), "drop_q": ("Descartadas", "Dropped"),
    "steps": ("Pasos", "Steps"),
    "guides_note": ("Horas = misiones + desplazamientos, según data/scores (tools/route_score.py, "
                    "docs/EFFICIENCY.md). XP/hora = XP total de las misiones entre esas horas. «Descartadas» y "
                    "«opcionales» son decisiones del filtro de eficiencia; los pasos opcionales los marca la guía. "
                    "Hasta que se contraste en el juego, los pasos siguen sin verificar.",
                    "Hours = quests + travel, from data/scores (tools/route_score.py, docs/EFFICIENCY.md). XP/hour = "
                    "total quest XP over those hours. Dropped and optional are decisions of the efficiency filter; "
                    "optional steps are flagged by the guide. Until checked in game, steps stay unverified."),
    "unique": ("pasos únicos", "unique steps"), "verified_l": ("verificados", "verified"),
    "nav_none": ("Aún no hay informe de navegación en este repositorio (nav/eval).",
                 "There is no navigation report in this repository yet (nav/eval)."),
    "routes_found": ("Rutas halladas (Rust)", "Routes found (Rust)"),
    "lua_found": ("Rutas halladas (router Lua)", "Routes found (Lua router)"),
    "off_links": ("Segmentos fuera de los enlaces", "Segments off the links"),
    "fine_off": ("Muestras sobre suelo inalcanzable", "Samples over unreachable ground"),
    "ratio": ("Longitud / línea recta (mediana, máx.)", "Length / straight line (median, max)"),
    "frame_max": ("Fotograma más largo", "Longest frame"),
    "frame_p99": ("Percentil 99 del fotograma", "99th percentile frame"),
    "frame_budget": ("Presupuesto de fotograma", "Frame budget"),
    "slice": ("Trozo por fotograma (Step)", "Slice per frame (Step)"),
    "walk_frames": ("Fotogramas de la ruta más larga", "Frames of the longest walk"),
    "lua_mem": ("Memoria de Lua con los dos continentes", "Lua memory with both continents"),
    "packs": ("Paquetes por continente", "Packs per continent"),
    "map": ("Mapa", "Map"), "sectors": ("Sectores", "Sectors"), "nodes": ("Nodos", "Nodes"), "size": ("Tamaño", "Size"),
    "nav_note": ("Medido en la máquina de desarrollo; la memoria y el tiempo reales dependen del cliente "
                 "(docs/NAV.md). El presupuesto es de 2 ms por fotograma.",
                 "Measured on the development machine; real memory and time depend on the client "
                 "(docs/NAV.md). The budget is 2 ms per frame."),
    "names_game": ("Nombres que ya dijo el cliente", "Names already given by the client"),
    "names_any": ("Nombres con respaldo (esES)", "Names with a fallback (esES)"),
    "kind": ("Tipo", "Kind"), "used": ("Usados en guías", "Used in guides"), "covered": ("Con nombre", "Named"),
    "from_game": ("Del juego", "From game"),
    "lk_all": ("Búsqueda: todo con fuente", "Lookup: everything sourced"),
    "lk_obj": ("Búsqueda: objetivos de misión", "Lookup: quest objectives"),
    "lk_rew": ("Búsqueda: recompensas", "Lookup: rewards"),
    "data_note": ("Los nombres «del juego» llegan con /senda volcar y tools/import_names.py; mientras tanto el "
                  "addon usa el respaldo de Polestar o de Senda. La búsqueda es la de data/lookup/coverage.json.",
                  "«From game» names arrive with /senda volcar and tools/import_names.py; until then the addon "
                  "uses the Polestar or Senda fallback. Lookup is from data/lookup/coverage.json."),
    "kind_quest": ("Misiones", "Quests"), "kind_npc": ("PNJ", "NPCs"), "kind_item": ("Objetos", "Items"),
    "kind_spell": ("Hechizos", "Spells"), "kind_map": ("Mapas", "Maps"), "kind_obj": ("Objetos del mundo", "World objects"),
    "kind_area": ("Lugares", "Places"),
    "full_log": ("Historial completo", "Full history"),
    "log_note": ("El historial está escrito en español.", "The changelog is written in Spanish."),
}

CSS = """
.m-wrap { max-width: 1100px; }
.m-lang { float: right; margin: 0 0 8px 12px; }
.m-btn { font: inherit; cursor: pointer; padding: 6px 12px; border-radius: 6px; border: 1px solid var(--border-strong, #888);
  background: var(--surface-2, transparent); color: var(--text, inherit); }
.m-btn:focus-visible { outline: 2px solid var(--focus, #c90); outline-offset: 2px; }
:root:not([data-lang="en"]) .m [lang="en"] { display: none; }
:root[data-lang="en"] .m [lang="es"] { display: none; }
.m-scroll { overflow-x: auto; border: 1px solid var(--border, #888); border-radius: 10px; margin: 0 0 1rem; background: var(--surface, transparent); }
.m table { border-collapse: collapse; width: 100%; font-size: .92rem; }
.m th, .m td { padding: 8px 12px; text-align: right; border-bottom: 1px solid var(--border, #888); white-space: nowrap; }
.m th:first-child, .m td:first-child { text-align: left; }
.m tr:last-child td { border-bottom: 0; }
.m .m-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; margin: 0 0 1rem; padding: 0; list-style: none; }
.m .m-card { border: 1px solid var(--border, #888); border-radius: 10px; padding: 12px 14px; background: var(--surface, transparent); }
.m .m-num { display: block; font-size: 1.6rem; font-weight: 700; color: var(--accent, inherit); }
.m .m-lab { color: var(--muted, inherit); font-size: .85rem; }
.m .m-bar { display: inline-block; width: 90px; height: 8px; border-radius: 4px; background: var(--surface-3, #ccc); vertical-align: middle; overflow: hidden; }
.m .m-bar > i { display: block; height: 100%; background: var(--verified, #3a3); }
.m .m-muted { color: var(--muted, inherit); }
.m ul.m-log { padding-left: 1.2rem; }
.m h3 { margin: 1rem 0 .3rem; }
"""

SCRIPT = """
(function () {
  var d = document.documentElement, key = "senda-lang", l = null;
  try { l = localStorage.getItem(key); } catch (e) {}
  if (l !== "en" && l !== "es") l = "es";
  function apply(v) {
    d.setAttribute("data-lang", v);
    var b = document.getElementById("m-lang-btn");
    if (b) b.setAttribute("aria-pressed", v === "en" ? "true" : "false");
  }
  apply(l);
  var b = document.getElementById("m-lang-btn");
  if (b) b.addEventListener("click", function () {
    l = d.getAttribute("data-lang") === "en" ? "es" : "en";
    apply(l);
    try { localStorage.setItem(key, l); } catch (e) {}
  });
})();
"""


def t(key: str) -> str:
    es, en = T[key]
    return f'<span lang="es">{html.escape(es)}</span><span lang="en">{html.escape(en)}</span>'


def raw(es: str, en: str) -> str:
    return f'<span lang="es">{es}</span><span lang="en">{en}</span>'


def n(v, dec: int = 0) -> str:
    """Número en formato neutro con separador de miles ('.' en es, ',' en en) vía los dos idiomas."""
    if v is None:
        return "-"
    s_en = f"{v:,.{dec}f}"
    s_es = s_en.replace(",", "\0").replace(".", ",").replace("\0", ".")
    return raw(s_es, s_en) if s_es != s_en else s_en


def inline(text: str, limit: int = 220) -> str:
    if len(text) > limit:  # resumen: el texto completo está en el historial
        text = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:.(") + "…"
        if text.count("`") % 2:
            text += "`"
        if text.count("**") % 2:
            text += "**"
    s = html.escape(text, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s


def bar(pct: float) -> str:
    return f'<span class="m-bar" aria-hidden="true"><i style="width:{max(0, min(100, pct)):.0f}%"></i></span>'


def card(num_html: str, label_key: str) -> str:
    return f'<li class="m-card"><span class="m-num">{num_html}</span><span class="m-lab">{t(label_key)}</span></li>'


# ------------------------------------------------------------------ HTML
def render_guides(m: dict) -> str:
    rows = []
    for g in m["guides"]:
        if g["scored"]:
            hours = n(g["hours"], 1)
            xph = n(g["xp_per_hour"])
            optq, dropq = n(g["optional"]), n(g["drop"])
        else:
            hours = xph = optq = dropq = "-"
        pct = round(100 * g["verified"] / g["steps"], 1) if g["steps"] else 0
        rows.append(
            f'<tr id="g-{html.escape(g["id"])}"><td>{html.escape(g["title"])}</td><td>{n(g["quests"])}</td>'
            f'<td>{hours}</td><td>{xph}</td><td>{n(g["steps"])}</td>'
            f'<td>{n(g["verified"])} {bar(pct)}</td><td>{n(g["unverified"])}</td><td>{n(g["disputed"])}</td>'
            f'<td>{n(g["with_sources"])} ({n(g["sources_pct"], 1)} %)</td><td>{n(g["optional_steps"])}</td>'
            f'<td>{optq}</td><td>{dropq}</td></tr>')
    head = "".join(f"<th scope=\"col\">{t(k)}</th>" for k in (
        "guide", "quests", "hours", "xph", "steps", "verified", "unverified", "disputed", "sources",
        "opt_steps", "opt_q", "drop_q"))
    return (f'<h2 id="guias">{t("s_guides")}</h2>'
            f'<p><strong>{n(m["unique_steps"])}</strong> {t("unique")} · '
            f'<strong>{n(m["unique_verified"])}</strong> {t("verified_l")}</p>'
            f'<div class="m-scroll"><table><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
            f'<p class="m-muted">{t("guides_note")}</p>')


def render_nav(m: dict) -> str:
    v = m["nav"]
    out = [f'<h2 id="malla">{t("s_nav")}</h2>']
    if not v.get("available"):
        return out[0] + f'<p>{t("nav_none")}</p>'
    cards = []
    if v.get("routes") is not None:
        cards.append(card(f'{n(v["found"])} / {n(v["routes"])}', "routes_found"))
    if v.get("lua_found") is not None:
        cards.append(card(f'{n(v["lua_found"])} / {n(v["lua_routes"])}', "lua_found"))
    if v.get("off_links") is not None:
        cards.append(card(n(v["off_links"]), "off_links"))
    if v.get("fine_off_pct") is not None:
        cards.append(card(f'{n(v["fine_off_pct"], 2)} %', "fine_off"))
    if v.get("ratio_median") is not None:
        cards.append(card(f'{n(v["ratio_median"], 2)} / {n(v["ratio_max"], 2)}', "ratio"))
    if v.get("longest_frame_ms") is not None:
        cards.append(card(f'{n(v["longest_frame_ms"], 2)} ms', "frame_max"))
    if v.get("p99_frame_ms") is not None:
        cards.append(card(f'{n(v["p99_frame_ms"], 2)} ms', "frame_p99"))
    cards.append(card(f'{n(v["budget_ms"], 1)} ms', "frame_budget"))
    if v.get("slice_ms") is not None:
        cards.append(card(f'{n(v["slice_ms"], 1)} ms', "slice"))
    if v.get("max_frames_walk") is not None:
        cards.append(card(n(v["max_frames_walk"]), "walk_frames"))
    if v.get("lua_mem_mb") is not None:
        cards.append(card(f'{n(v["lua_mem_mb"], 1)} MB', "lua_mem"))
    out.append(f'<ul class="m-cards">{"".join(cards)}</ul>')
    if v.get("packs"):
        rows = "".join(f'<tr><td>{p["map"]}</td><td>{n(p["sectors"])}</td><td>{n(p["nodes"])}</td>'
                       f'<td>{n(p["mb"], 2)} MB</td></tr>' for p in v["packs"])
        out.append(f'<h3>{t("packs")}</h3><div class="m-scroll"><table><thead><tr>'
                   f'<th scope="col">{t("map")}</th><th scope="col">{t("sectors")}</th>'
                   f'<th scope="col">{t("nodes")}</th><th scope="col">{t("size")}</th></tr></thead>'
                   f'<tbody>{rows}</tbody></table></div>')
    out.append(f'<p class="m-muted">{t("nav_note")}</p>')
    return "".join(out)


def render_data(m: dict) -> str:
    d = m["data"]
    cards = [card(f'{n(d["names_game_pct"], 1)} %', "names_game"),
             card(f'{n(d["names_covered_pct"], 1)} %', "names_any")]
    lk = d["lookup"]
    for key, lab in (("all", "lk_all"), ("objective", "lk_obj"), ("reward", "lk_rew")):
        if lk.get(key):
            cards.append(card(f'{n(lk[key]["pct"], 1)} %', lab))
    rows = "".join(
        f'<tr><td>{t("kind_" + k["kind"])}</td><td>{n(k["used"])}</td><td>{n(k["covered"])}</td>'
        f'<td>{n(k["from_game"])}</td></tr>' for k in d["kinds"])
    return (f'<h2 id="datos">{t("s_data")}</h2><ul class="m-cards">{"".join(cards)}</ul>'
            f'<div class="m-scroll"><table><thead><tr><th scope="col">{t("kind")}</th>'
            f'<th scope="col">{t("used")}</th><th scope="col">{t("covered")}</th>'
            f'<th scope="col">{t("from_game")}</th></tr></thead><tbody>{rows}</tbody></table></div>'
            f'<p class="m-muted">{t("data_note")}</p>')


def render_changes(m: dict, changelog_href: str) -> str:
    out = [f'<h2 id="cambios-recientes">{t("s_changes")}</h2>']
    for ver in m["changelog"]:
        out.append(f'<h3>{html.escape(ver["version"])} <span class="m-muted">{html.escape(ver["date"])}</span></h3>'
                   '<ul class="m-log">')
        for kind, text in ver["items"]:
            out.append(f'<li><strong>{inline(text)}</strong></li>' if kind == "h" else f"<li>{inline(text)}</li>")
        out.append("</ul>")
    out.append(f'<p><a href="{html.escape(changelog_href)}">{t("full_log")}</a> '
               f'<span class="m-muted">· {t("log_note")}</span></p>')
    return "".join(out)


def render_body(m: dict, changelog_href: str = "../cambios/") -> str:
    return (f'<style>{CSS}</style><div class="m m-wrap">'
            f'<div class="m-lang"><button type="button" class="m-btn" id="m-lang-btn" aria-pressed="false">'
            f'<span lang="es">English</span><span lang="en">Español</span></button></div>'
            f'<header class="page-head"><p class="eyebrow">{t("eyebrow")}</p><h1>{t("title")}</h1>'
            f'<p class="lead">{t("lead")}</p></header>'
            f'{render_guides(m)}{render_nav(m)}{render_data(m)}{render_changes(m, changelog_href)}'
            f'</div><script>{SCRIPT}</script>')


def render_page(m: dict) -> str:
    """Página autónoma: tema por prefers-color-scheme y por el botón, todo inline, sin recursos externos."""
    css = """
:root { --bg:#121419; --surface:#1a1d24; --surface-2:#222631; --surface-3:#2a2f3c; --border:#303644;
  --border-strong:#454c5e; --text:#ece7da; --muted:#a39e90; --accent:#dcb15a; --focus:#f0c873; --verified:#6fcf8e;
  color-scheme: dark; }
:root[data-theme="light"] { --bg:#f6f2e8; --surface:#fffdf8; --surface-2:#f1ebdd; --surface-3:#e7dfcc;
  --border:#ddd4c0; --border-strong:#bdb299; --text:#2a2418; --muted:#6b6454; --accent:#8a5a00; --focus:#8a5a00;
  --verified:#2a8a4a; color-scheme: light; }
body { margin:0; background:var(--bg); color:var(--text); font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }
main { padding: 16px; margin: 0 auto; max-width: 1100px; }
a { color: var(--accent); }
.m-theme { float:right; margin-left:8px; }
"""
    theme = """
(function(){var d=document.documentElement,t=null;try{t=localStorage.getItem("senda-theme");}catch(e){}
if(t!=="light"&&t!=="dark"){t=window.matchMedia&&window.matchMedia("(prefers-color-scheme: light)").matches?"light":"dark";}
d.setAttribute("data-theme",t);
document.addEventListener("DOMContentLoaded",function(){var b=document.getElementById("m-theme-btn");
if(b)b.addEventListener("click",function(){var n=d.getAttribute("data-theme")==="light"?"dark":"light";
d.setAttribute("data-theme",n);try{localStorage.setItem("senda-theme",n);}catch(e){}});});})();
"""
    body = render_body(m, changelog_href="https://github.com/e-omunoz/senda/blob/main/CHANGELOG.md")
    body = body.replace('<div class="m-lang">', '<div class="m-lang"><button type="button" class="m-btn m-theme" '
                        'id="m-theme-btn" aria-label="Tema / Theme">&#9680;</button>', 1)
    return ("<!doctype html>\n<html lang=\"es\" data-theme=\"dark\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            "<meta name=\"color-scheme\" content=\"dark light\">\n"
            "<title>Métricas de Senda</title>\n"
            f"<script>{theme}</script>\n<style>{css}</style>\n</head>\n<body>\n<main>\n{body}\n</main>\n</body>\n</html>\n")


def write(root: Path, out: Path) -> dict:
    m = collect(root)
    d = Path(out) / "metricas"
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text(render_page(m), encoding="utf-8", newline="\n")
    (d / "metrics.json").write_text(json.dumps(m, ensure_ascii=False, indent=1, default=list), encoding="utf-8",
                                    newline="\n")
    return m


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Métricas de Senda para la web.")
    ap.add_argument("--root", default=str(REPO_ROOT))
    ap.add_argument("--out", help="carpeta de salida (escribe <out>/metricas/index.html)")
    ap.add_argument("--json", action="store_true", help="imprime las cifras en JSON")
    args = ap.parse_args(argv)
    if args.out:
        m = write(Path(args.root), Path(args.out))
        print(f"Métricas en {Path(args.out) / 'metricas'}: {len(m['guides'])} guías, {m['unique_steps']} pasos únicos")
    if args.json or not args.out:
        print(json.dumps(collect(Path(args.root)), ensure_ascii=False, indent=1, default=list))
    return 0


if __name__ == "__main__":
    sys.exit(main())

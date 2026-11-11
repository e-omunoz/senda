"""Informe en español (harness/reports/<fecha>.md), que también es el cuerpo del PR."""
from __future__ import annotations

from .propose import Proposal

TIER_ES = {"official": "oficial", "community_curated": "comunitaria curada",
           "community_unverified": "comunitaria sin verificar"}
VERDICT_ES = {"ok": "correcto", "incorrect": "incorrecto", "outdated": "obsoleto", "uncertain": "sin datos"}
CAT_ES = {"hotfix": "hotfix", "xp_change": "experiencia", "quest_change": "misiones", "npc_move": "PNJ",
          "class_change": "clase", "talent_change": "talentos", "profession_change": "profesiones",
          "zone_change": "zonas", "dungeon_change": "mazmorras", "item_change": "objetos",
          "new_trick": "truco", "addon_api": "API de addons", "other": "otros"}


def _ev_line(e) -> str:
    mark = "✔" if e.confirmed else "✘"
    rel = {"supports": "a favor", "contradicts": "en contra", "neutral": "neutral"}[e.supports]
    if e.kind == "web":
        q = e.quote.replace("\n", " ")
        q = q if len(q) <= 240 else q[:240] + "…"
        return f"  - {mark} {rel} · {TIER_ES.get(e.tier, e.tier)} · <{e.url}> — «{q}» ({e.detail})"
    return f"  - {mark} {rel} · `{e.ref}` ({e.detail})"


def render(prop: Proposal, cost: dict | None = None) -> str:
    L: list[str] = []
    w = L.append
    edited = [c for c in prop.changes if c.applied]
    disputed = [c for c in prop.changes if c.after_status == "disputed" and c.before_status != "disputed"]
    newly_verified = [c for c in prop.changes if c.after_status == "verified" and c.before_status != "verified"]
    attention = [c for c in prop.changes if c.verdict in ("incorrect", "outdated") and c.skipped]
    w(f"# Informe del harness — {prop.today}\n")
    w("> Generado automáticamente. **Revisión humana obligatoria**: nada de esto se publica hasta que "
      "apruebes y fusiones el PR. Ver `docs/HARNESS.md` → «Cómo revisar un PR del harness».\n")
    w("## Resumen\n")
    w(f"- Pasos revisados: **{len(prop.changes)}** · con cambios: **{len(edited)}** · "
      f"nuevos verificados: **{len(newly_verified)}** · nuevos en disputa: **{len(disputed)}**")
    w(f"- Afirmaciones nuevas de fuentes: **{len(prop.claims)}** "
      f"(afectan a pasos: {sum(1 for _, s in prop.claims if s)})")
    w(f"- Consejos añadidos a conocimiento: **{len(prop.tips_added)}** · descartados: {len(prop.tips_skipped)}")
    files = [r for r, (a, b) in prop.files.items() if a != b]
    w(f"- Archivos de datos modificados: {', '.join(f'`{f}`' for f in files) if files else 'ninguno'}")
    if cost:
        w(f"- Coste estimado de esta ejecución: **{cost.get('usd', 0):.3f} USD** "
          f"({cost.get('calls', 0)} llamadas, {cost.get('web_searches', 0)} búsquedas web, "
          f"{cost.get('cache_read_tokens', 0)} tokens leídos de caché)")
    w("")
    if attention or disputed:
        w("## Requiere tu atención\n")
        for c in disputed:
            w(f"- **{c.step_id}** (`{c.file}`) pasa a **disputed**: hay fuentes que se contradicen. {c.notes}")
        for c in attention:
            w(f"- **{c.step_id}** (`{c.file}`) parece {VERDICT_ES.get(c.verdict)} pero hay cambios sin aplicar: "
              + "; ".join(c.skipped))
        w("")
    if prop.changes:
        w("## Pasos auditados\n")
        for c in prop.changes:
            w(f"### `{c.step_id}` — {VERDICT_ES.get(c.verdict, c.verdict)} · {c.before_status} → "
              f"**{c.after_status}**" + (" · vía Claude Code" if c.origin == "claude-code" else ""))
            w(f"Archivo: `{c.file}`" + (f" · regla de verificación: ({c.rule})" if c.rule else ""))
            if c.notes:
                w(f"\n{c.notes}")
            if c.applied:
                w("\nCambios aplicados:")
                for a in c.applied:
                    w(f"- {a}")
            if c.skipped:
                w("\nNo aplicado / avisos:")
                for s in c.skipped:
                    w(f"- {s}")
            if c.evidence:
                w("\nEvidencia (✔ confirmada por el harness, ✘ no cuenta):")
                for e in c.evidence:
                    w(_ev_line(e))
            w("")
    if prop.claims:
        w("## Novedades en las fuentes\n")
        order = {"official": 0, "community_curated": 1, "community_unverified": 2}
        for c, sids in sorted(prop.claims, key=lambda x: (order.get(x[0].tier, 3), x[0].date)):
            q = c.quote.replace("\n", " ")
            q = q if len(q) <= 300 else q[:300] + "…"
            w(f"- **[{CAT_ES.get(c.category, c.category)}]** {c.summary_es} "
              f"— _{TIER_ES.get(c.tier, c.tier)}_, {c.date or 's/f'}  \n"
              f"  «{q}» <{c.url}>"
              + (f"  \n  Pasos afectados (en cola para la próxima auditoría): {', '.join(sids)}" if sids else "")
              + ("".join(f"  \n  ⚠ {n}" for n in c.notes)))
        w("")
    if prop.tips_added or prop.tips_skipped:
        w("## Consejos de leveo\n")
        for t in prop.tips_added:
            w(f"- ➕ **{t['title_es']}** ({t['race']} {t['class']}) → `{t['_file']}` · fuentes: "
              + ", ".join(TIER_ES.get(x, x) for x in t["_tiers"]))
        for t, why in prop.tips_skipped:
            w(f"- ✘ {t['title_es']} ({t['class']}): {why}")
        w("")
    if prop.errors:
        w("## Errores\n")
        for e in prop.errors:
            w(f"- {e}")
        w("")
    w("## Reglas aplicadas\n")
    w("- `verified` solo con (a) fuente oficial, (b) observación en partida o (c) QuestieDB + otra fuente "
      "independiente oficial o curada, **y solo con evidencia confirmada por el harness** (cita literal "
      "encontrada en la página, consulta real a QuestieDB, observación presente).")
    w("- Fuentes fiables que se contradicen → `disputed`, con ambas en `sources`.")
    w("- Cambios de valor sin evidencia confirmada → no se aplican; se listan arriba.")
    w("- Un paso `verified` nunca se rebaja en silencio: pasa a `disputed`.")
    return "\n".join(L) + "\n"

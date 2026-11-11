"""Capa fina sobre el SDK `anthropic` (importación perezosa).

- `--dry-run`: imprime los prompts y no llama a la API (ni importa el SDK).
- Presupuesto: estimación previa por llamada y contabilidad real con `usage`; se para al superar --budget-usd.
- Caché de prompts (cache_control en el bloque de sistema estable) y caché local de respuestas
  para llamadas sin herramientas (misma petición => misma respuesta, coste cero).
- Bucle de herramientas manual: necesitamos cortar por presupuesto entre turnos, manejar
  `pause_turn` de las herramientas de servidor y terminar cuando el modelo llama a la herramienta final.
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from typing import Callable

from .config import CACHE, CACHE_READ_MULT, CACHE_WRITE_MULT, WEB_SEARCH_USD, Settings, price_for

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class BudgetExceeded(Exception):
    pass


class LLMError(Exception):
    pass


@dataclass
class Budget:
    limit_usd: float | None = None
    spent_usd: float = 0.0
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    web_searches: int = 0
    log: list[dict] = field(default_factory=list)

    def check(self, estimate_usd: float, label: str) -> None:
        if self.limit_usd is not None and self.spent_usd + estimate_usd > self.limit_usd:
            raise BudgetExceeded(
                f"{label}: gastado {self.spent_usd:.3f} USD + estimado {estimate_usd:.3f} USD "
                f"> presupuesto {self.limit_usd:.2f} USD")

    def charge(self, model: str, usage, label: str) -> float:
        p_in, p_out = price_for(model)
        it = getattr(usage, "input_tokens", 0) or 0
        ot = getattr(usage, "output_tokens", 0) or 0
        cw = getattr(usage, "cache_creation_input_tokens", 0) or 0
        cr = getattr(usage, "cache_read_input_tokens", 0) or 0
        stu = getattr(usage, "server_tool_use", None)
        ws = (getattr(stu, "web_search_requests", 0) or 0) if stu is not None else 0
        cost = (it * p_in + cw * p_in * CACHE_WRITE_MULT + cr * p_in * CACHE_READ_MULT + ot * p_out) / 1e6
        cost += ws * WEB_SEARCH_USD
        self.spent_usd += cost
        self.calls += 1
        self.input_tokens += it
        self.output_tokens += ot
        self.cache_read_tokens += cr
        self.cache_write_tokens += cw
        self.web_searches += ws
        self.log.append({"label": label, "model": model, "usd": round(cost, 5), "in": it, "out": ot,
                         "cache_read": cr, "cache_write": cw, "web_searches": ws})
        return cost

    def summary(self) -> dict:
        return {"usd": round(self.spent_usd, 4), "calls": self.calls, "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens, "cache_read_tokens": self.cache_read_tokens,
                "cache_write_tokens": self.cache_write_tokens, "web_searches": self.web_searches,
                "limit_usd": self.limit_usd}


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 3)   # conservador (texto mixto inglés/español/JSON)


def system_blocks(*parts: str) -> list[dict]:
    """Bloques de sistema; el último bloque estable lleva cache_control (prefijo cacheable)."""
    blocks = [{"type": "text", "text": p} for p in parts if p]
    if blocks:
        blocks[-1]["cache_control"] = {"type": "ephemeral"}
    return blocks


class LLM:
    def __init__(self, settings: Settings, *, dry_run: bool = False, budget: Budget | None = None,
                 use_cache: bool = True, out=sys.stdout, show_chars: int = 6000):
        self.s = settings
        self.dry_run = dry_run
        self.budget = budget or Budget()
        self.use_cache = use_cache
        self.out = out
        self.show_chars = show_chars
        self._client = None

    # ------------------------------------------------------------------ cliente
    @property
    def client(self):
        if self._client is None:
            try:
                import anthropic  # noqa: WPS433 (importación perezosa a propósito)
            except ImportError as e:
                raise LLMError("falta el paquete `anthropic`: pip install -r harness/requirements.txt "
                               "(o usa --dry-run / el camino de Claude Code)") from e
            # Credenciales: ANTHROPIC_API_KEY (CI) o el perfil de `ant auth login` (local).
            self._client = anthropic.Anthropic(max_retries=4)
        return self._client

    def _common(self, effort: str, output_format: dict | None) -> dict:
        kw: dict = {"model": self.s.model, "max_tokens": self.s.max_tokens}
        oc: dict = {"effort": effort}
        if output_format:
            oc["format"] = {"type": "json_schema", "schema": output_format}
        kw["output_config"] = oc
        if self.s.refusal_fallback:
            kw["betas"] = [FALLBACK_BETA]
            kw["fallbacks"] = self.s.refusal_fallback
        return kw

    def _print_dry(self, label: str, system: list[dict], messages: list, tools: list | None, effort: str,
                   schema: dict | None) -> None:
        w = self.out.write
        w(f"\n{'=' * 78}\n[dry-run] {label}\n  modelo={self.s.model} effort={effort} "
          f"max_tokens={self.s.max_tokens} fallback={self.s.refusal_fallback or 'no'}\n")
        if tools:
            w("  herramientas: " + ", ".join(t.get("name", t.get("type", "?")) for t in tools) + "\n")
        if schema:
            w("  salida estructurada: json_schema (" + ", ".join(schema.get("required", [])) + ")\n")
        for b in system:
            t = b["text"]
            w(f"--- system ({len(t)} car.{', cache' if 'cache_control' in b else ''}) ---\n")
            w(t[: self.show_chars] + ("\n[...]\n" if len(t) > self.show_chars else "\n"))
        for m in messages:
            c = m["content"] if isinstance(m["content"], str) else json.dumps(m["content"], ensure_ascii=False)
            w(f"--- {m['role']} ({len(c)} car.) ---\n")
            w(c[: self.show_chars] + ("\n[...]\n" if len(c) > self.show_chars else "\n"))
        est_in = sum(estimate_tokens(b["text"]) for b in system) + sum(
            estimate_tokens(m["content"] if isinstance(m["content"], str) else json.dumps(m["content"]))
            for m in messages)
        p_in, p_out = price_for(self.s.model)
        w(f"--- estimación: ~{est_in} tokens de entrada, ~{est_in * p_in / 1e6 + 4000 * p_out / 1e6:.3f} USD "
          f"por turno (sin búsquedas) ---\n")

    def _estimate(self, system, messages) -> float:
        p_in, p_out = price_for(self.s.model)
        n = sum(estimate_tokens(b["text"]) for b in system) + estimate_tokens(
            json.dumps(messages, default=str, ensure_ascii=False))
        return n * p_in / 1e6 + 4000 * p_out / 1e6

    def _send(self, kw: dict):
        create = self.client.beta.messages.create if "betas" in kw else self.client.messages.create
        try:
            return create(**kw)
        except TypeError as e:
            # SDK algo antiguo que aún no conoce algún parámetro nuevo: se envía tal cual en el cuerpo.
            extra = {k: kw.pop(k) for k in ("fallbacks", "cache_control") if k in kw and k in str(e)}
            if not extra:
                raise
            return create(**kw, extra_body=extra)

    def _create(self, label: str, **kw):
        try:
            import anthropic
        except ImportError:   # cliente simulado en tests
            anthropic = None
        if anthropic is None:
            resp = self._send(kw)
        else:
            try:
                resp = self._send(kw)
            except anthropic.BadRequestError as e:
                raise LLMError(f"{label}: petición inválida: {e.message}") from e
            except anthropic.AuthenticationError as e:
                raise LLMError("credenciales inválidas (ANTHROPIC_API_KEY o `ant auth login`)") from e
            except anthropic.RateLimitError as e:
                raise LLMError(f"{label}: límite de peticiones; reintenta más tarde") from e
            except anthropic.APIStatusError as e:
                raise LLMError(f"{label}: error de la API {e.status_code}: {e.message}") from e
            except anthropic.APIConnectionError as e:
                raise LLMError(f"{label}: error de red con la API") from e
        self.budget.charge(getattr(resp, "model", self.s.model), resp.usage, label)
        return resp

    # ------------------------------------------------------------------ llamada simple (JSON)
    def json_call(self, label: str, system: list[dict], user: str, schema: dict, effort: str) -> dict | None:
        """Una llamada con salida estructurada. Devuelve el objeto JSON o None (dry-run / rechazo)."""
        messages = [{"role": "user", "content": user}]
        if self.dry_run:
            self._print_dry(label, system, messages, None, effort, schema)
            return None
        kw = self._common(effort, schema)
        kw.update(system=system, messages=messages)
        key = hashlib.sha256(json.dumps(kw, sort_keys=True, default=str).encode()).hexdigest()
        cf = CACHE / "responses" / f"{key}.json"
        if self.use_cache and cf.exists():
            return json.loads(cf.read_text(encoding="utf-8"))
        self.budget.check(self._estimate(system, messages), label)
        resp = self._create(label, **kw)
        if resp.stop_reason == "refusal":
            raise LLMError(f"{label}: el modelo rechazó la petición ({getattr(resp, 'stop_details', None)})")
        if resp.stop_reason == "max_tokens":
            raise LLMError(f"{label}: respuesta cortada por max_tokens; sube SENDA_HARNESS_MAX_TOKENS")
        text = next((b.text for b in resp.content if b.type == "text"), "")
        data = json.loads(text)
        cf.parent.mkdir(parents=True, exist_ok=True)
        cf.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data

    # ------------------------------------------------------------------ bucle con herramientas
    def tool_loop(self, label: str, system: list[dict], user: str, tools: list[dict],
                  handlers: dict[str, Callable[[dict], tuple[str, bool]]], finish_tool: str,
                  effort: str, validate_finish: Callable[[dict], str | None] | None = None) -> dict | None:
        """Ejecuta el bucle hasta que el modelo llame a `finish_tool`. Devuelve su input (dict).

        handlers: nombre -> función(input) -> (texto_resultado, es_error).
        validate_finish: devuelve un mensaje de error si el input final no es válido (se le pide corregir).
        """
        messages: list = [{"role": "user", "content": user}]
        if self.dry_run:
            self._print_dry(label, system, messages, tools, effort, None)
            return None
        kw = self._common(effort, None)
        # Caché automática del historial: cada turno reenvía todo lo anterior (búsquedas incluidas).
        kw["cache_control"] = {"type": "ephemeral"}
        nudged = False
        for turn in range(self.s.max_turns):
            self.budget.check(self._estimate(system, messages), f"{label} (turno {turn + 1})")
            resp = self._create(f"{label} t{turn + 1}", system=system, messages=messages, tools=tools, **kw)
            if resp.stop_reason == "refusal":
                raise LLMError(f"{label}: el modelo rechazó la petición")
            # Se devuelve el contenido tal cual (incluye bloques de pensamiento y de herramientas de servidor).
            messages.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason == "pause_turn":
                continue
            if resp.stop_reason == "max_tokens":
                messages.append({"role": "user", "content": "Te has quedado sin espacio. Resume y llama ya a "
                                 f"`{finish_tool}` con lo que tengas."})
                continue
            uses = [b for b in resp.content if b.type == "tool_use"]
            if not uses:
                if nudged:
                    raise LLMError(f"{label}: el modelo terminó sin llamar a {finish_tool}")
                nudged = True
                messages.append({"role": "user", "content": f"Llama a la herramienta `{finish_tool}` con el "
                                 "resultado final. No respondas con texto."})
                continue
            results = []
            final = None
            for u in uses:
                inp = u.input if isinstance(u.input, dict) else {}
                if u.name == finish_tool:
                    err = validate_finish(inp) if validate_finish else None
                    if err:
                        results.append({"type": "tool_result", "tool_use_id": u.id, "content": err,
                                        "is_error": True})
                    else:
                        final = inp
                        results.append({"type": "tool_result", "tool_use_id": u.id, "content": "recibido"})
                    continue
                h = handlers.get(u.name)
                if h is None:
                    results.append({"type": "tool_result", "tool_use_id": u.id,
                                    "content": f"herramienta desconocida: {u.name}", "is_error": True})
                    continue
                try:
                    text, is_err = h(inp)
                except Exception as e:  # una herramienta local rota no debe tumbar la auditoría
                    text, is_err = f"error: {type(e).__name__}: {e}", True
                results.append({"type": "tool_result", "tool_use_id": u.id, "content": text,
                                "is_error": is_err})
            if final is not None:
                return final
            messages.append({"role": "user", "content": results})
        raise LLMError(f"{label}: sin resultado tras {self.s.max_turns} turnos")


def web_tools(settings: Settings, domains: list[str] | None) -> list[dict]:
    """Herramientas de servidor de búsqueda y lectura web (variantes con filtrado dinámico)."""
    ws: dict = {"type": "web_search_20260209", "name": "web_search", "max_uses": settings.web_search_max_uses}
    wf: dict = {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": settings.web_fetch_max_uses}
    if settings.restrict_domains and domains:
        ws["allowed_domains"] = list(domains)
        wf["allowed_domains"] = list(domains)
    return [ws, wf]

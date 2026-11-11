"""Bucle de herramientas, presupuesto y dry-run con un cliente simulado (sin el paquete anthropic)."""
import io
import unittest
from types import SimpleNamespace as NS

from harness.config import Settings
from harness.llm import LLM, Budget, BudgetExceeded, LLMError, system_blocks


def usage(i=1000, o=500, ws=0):
    return NS(input_tokens=i, output_tokens=o, cache_creation_input_tokens=0, cache_read_input_tokens=0,
              server_tool_use=NS(web_search_requests=ws))


def msg(blocks, stop="tool_use", **u):
    return NS(content=blocks, stop_reason=stop, usage=usage(**u), model="claude-opus-5-5")


def tool_use(name, inp, i="t1"):
    return NS(type="tool_use", name=name, input=inp, id=i)


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.beta = NS(messages=NS(create=self.create))
        self.messages = NS(create=self.create)

    def create(self, **kw):
        self.calls.append({**kw, "messages": list(kw["messages"])})  # instantánea
        return self.responses.pop(0)


def make(responses, budget=None):
    llm = LLM(Settings(), budget=budget or Budget(), out=io.StringIO())
    llm._client = FakeClient(responses)
    return llm


class ToolLoopTest(unittest.TestCase):
    def test_lookup_then_submit(self):
        llm = make([
            msg([tool_use("questie_lookup", {"kind": "quest", "id": 179})], ws=2),
            msg([NS(type="text", text="..."), tool_use("submit_verdicts", {"verdicts": [1]}, "t2")]),
        ])
        seen = []
        res = llm.tool_loop("t", system_blocks("sys"), "u", [], {"questie_lookup": lambda i: (seen.append(i) or
                            ("{}", False))}, "submit_verdicts", "high")
        self.assertEqual(res, {"verdicts": [1]})
        self.assertEqual(seen, [{"kind": "quest", "id": 179}])
        kw = llm._client.calls[0]
        self.assertEqual(kw["model"], "claude-opus-5-5")
        self.assertEqual(kw["output_config"], {"effort": "high"})
        self.assertNotIn("thinking", kw)                     # adaptativo por defecto en Opus 5.5
        self.assertNotIn("tool_choice", kw)                  # forzar herramienta da 400 en Opus 5.5
        self.assertEqual(kw["fallbacks"], "default")
        self.assertIn("cache_control", kw["system"][-1])
        # Segundo turno: se devolvió el contenido del asistente y el resultado de la herramienta.
        second = llm._client.calls[1]["messages"]
        self.assertEqual(second[-1]["content"][0]["type"], "tool_result")
        self.assertEqual(llm.budget.web_searches, 2)
        self.assertAlmostEqual(llm.budget.spent_usd, 2 * (1000 * 4 + 500 * 20) / 1e6 + 0.02)

    def test_pause_turn_and_invalid_finish(self):
        llm = make([
            msg([NS(type="server_tool_use")], stop="pause_turn"),
            msg([tool_use("submit_verdicts", {"verdicts": "mal"})]),
            msg([tool_use("submit_verdicts", {"verdicts": []}, "t3")]),
        ])
        res = llm.tool_loop("t", system_blocks("s"), "u", [], {}, "submit_verdicts", "high",
                            lambda inp: None if isinstance(inp["verdicts"], list) else "debe ser lista")
        self.assertEqual(res, {"verdicts": []})
        errs = llm._client.calls[2]["messages"][-1]["content"]
        self.assertTrue(errs[0]["is_error"])

    def test_text_only_is_nudged_once_then_fails(self):
        llm = make([msg([NS(type="text", text="hola")], stop="end_turn")] * 2)
        with self.assertRaises(LLMError):
            llm.tool_loop("t", system_blocks("s"), "u", [], {}, "submit_verdicts", "high")

    def test_refusal(self):
        llm = make([msg([], stop="refusal")])
        with self.assertRaises(LLMError):
            llm.tool_loop("t", system_blocks("s"), "u", [], {}, "submit_verdicts", "high")

    def test_budget_stops_before_call(self):
        llm = make([], budget=Budget(limit_usd=0.001))
        with self.assertRaises(BudgetExceeded):
            llm.tool_loop("t", system_blocks("s"), "u", [], {}, "submit_verdicts", "high")
        self.assertEqual(llm._client.calls, [])


class DryRunTest(unittest.TestCase):
    def test_dry_run_prints_and_never_touches_client(self):
        out = io.StringIO()
        llm = LLM(Settings(), dry_run=True, out=out)
        self.assertIsNone(llm.json_call("x", system_blocks("SISTEMA"), "USUARIO", {"required": ["a"]}, "medium"))
        self.assertIsNone(llm.tool_loop("y", system_blocks("S"), "U", [{"name": "submit"}], {}, "submit", "high"))
        self.assertIsNone(llm._client)
        self.assertIn("SISTEMA", out.getvalue())
        self.assertIn("[dry-run] y", out.getvalue())


if __name__ == "__main__":
    unittest.main()

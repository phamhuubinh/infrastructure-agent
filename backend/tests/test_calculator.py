"""Calculator resource and serialization regressions; no network or application state."""

from __future__ import annotations

import unittest

from orion.contracts import RuntimeScope, ToolCall
from orion.tool_runtime.calculator import calculate, calculator_definition


class CalculatorBoundsTests(unittest.TestCase):
    def result(self, expression):
        return calculate(
            ToolCall(
                call_id="test",
                tool_name="calculator.evaluate",
                arguments={"expression": expression},
                runtime_scope=RuntimeScope(
                    session_id="test", principal_id="test", workspace_id="test"
                ),
            )
        )

    def test_normal_arithmetic_and_powers(self):
        for expression, expected in (
            ("(12 + 8) / 5", 4),
            ("-3 * +7", -21),
            ("2**100", 2**100),
            ("2**-2", 0.25),
            ("17//3 + 17%3", 7),
            ("0**0", 1),
        ):
            with self.subTest(expression=expression):
                result = self.result(expression)
                self.assertEqual(result.status, "success")
                self.assertEqual(result.data["value"], expected)
                result.model_dump_json()

    def test_growth_is_rejected_before_large_power_allocation(self):
        result = self.result("((9**100)**100)**100")
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error.code, "invalid_input")

    def test_nonfinite_complex_and_nonarithmetic_results_are_rejected(self):
        for expression in (
            "1e309",
            "1e308*10",
            "(-1)**0.5",
            "True",
            "1j",
            "abs(1)",
            "[1]",
            "1/0",
            "2**101",
            "__import__('os')",
        ):
            with self.subTest(expression=expression):
                result = self.result(expression)
                self.assertEqual(result.status, "error")
                self.assertEqual(result.error.code, "invalid_input")
                result.model_dump_json()

    def test_length_depth_and_node_limits(self):
        for expression in ("1" * 4097, "+" * 100 + "1", "+".join(["1"] * 100), ""):
            with self.subTest(length=len(expression)):
                self.assertEqual(self.result(expression).status, "error")

    def test_schema_exposes_expression_bounds(self):
        schema = calculator_definition().input_schema["properties"]["expression"]
        self.assertEqual(schema["maxLength"], 4096)
        self.assertEqual(schema["minLength"], 1)

    def test_canonical_tool_dispatch_keeps_bounds_and_correlation(self):
        from orion.contracts import ModelToolCall
        from orion.tool_runtime.registry import ToolRegistryBuilder
        from orion.tool_runtime.runner import ToolRunner

        registry = ToolRegistryBuilder()
        registry.register(calculator_definition(), calculate)
        runner = ToolRunner(registry.freeze())
        scope = RuntimeScope(session_id="test", principal_id="test", workspace_id="test")
        for expression, status in (
            ("6*7", "success"),
            ("9**100**2", "error"),
            ("1" * 4097, "error"),
        ):
            with self.subTest(length=len(expression)):
                result = runner.run(
                    ModelToolCall(
                        call_id="canonical",
                        tool_name="calculator.evaluate",
                        arguments={"expression": expression},
                    ),
                    scope,
                )
                self.assertEqual(result.status, status)
                self.assertEqual(result.call_id, "canonical")
                result.model_dump_json()


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sys
import unittest


PROTOTYPE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROTOTYPE_ROOT))

from demo import build_demo_runtime, build_plan  # noqa: E402
from jidan import (  # noqa: E402
    Capability,
    CapabilityRegistry,
    Effect,
    JidanRuntime,
    PolicyEngine,
    ReceiptLog,
    Step,
    TaskPlan,
    issue_grant,
)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.runtime, self.secret, self.shopping_list = build_demo_runtime()
        self.plan = build_plan()

    def grant(self, **overrides):
        values = {
            "secret": self.secret,
            "task_id": self.plan,
            "capabilities": [step.capability for step in self.plan.steps],
            "scopes": {"mail.content.read", "local.inference", "shopping.list.write"},
            "max_effect": Effect.WRITE,
            "approved_steps": (),
        }
        values.update(overrides)
        return issue_grant(**values)

    def test_confirmation_gate_prevents_partial_execution(self):
        result = self.runtime.execute(self.plan, self.grant())
        self.assertEqual("awaiting_confirmation", result.status)
        self.assertEqual([], self.shopping_list)
        self.assertEqual(0, len(self.runtime.receipts.all()))

    def test_approved_task_executes_dataflow_and_receipts(self):
        result = self.runtime.execute(
            self.plan,
            self.grant(approved_steps={"add_to_list"}),
        )
        self.assertEqual("completed", result.status)
        self.assertEqual(["noodles", "bok choy", "sesame oil", "soy sauce"], self.shopping_list)
        self.assertEqual(3, len(result.receipts))
        self.assertTrue(self.runtime.receipts.verify())

    def test_capability_outside_grant_is_rejected(self):
        grant = self.grant(capabilities={"mail.search", "system.extract_recipe"})
        result = self.runtime.execute(
            self.plan,
            grant,
        )
        self.assertEqual("rejected", result.status)
        self.assertEqual([], self.shopping_list)

    def test_tampered_grant_is_rejected(self):
        grant = replace(self.grant(), max_effect=Effect.IRREVERSIBLE)
        result = self.runtime.execute(
            self.plan,
            grant,
        )
        self.assertEqual("rejected", result.status)
        self.assertTrue(all(item.outcome == "denied" for item in result.decisions))

    def test_receipt_tampering_is_detected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "receipts.jsonl"
            runtime, secret, _ = build_demo_runtime(path)
            plan = build_plan()
            grant = issue_grant(
                secret,
                plan,
                [step.capability for step in plan.steps],
                {"mail.content.read", "local.inference", "shopping.list.write"},
                Effect.WRITE,
                approved_steps={"add_to_list"},
            )
            runtime.execute(plan, grant)
            # The write approval is bound into a signed grant, never supplied
            # as caller-controlled execute() data.
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            records[0]["output"]["sender"] = "Mallory"
            path.write_text("\n".join(json.dumps(item) for item in records) + "\n", encoding="utf-8")
            self.assertFalse(ReceiptLog(path).verify())

    def test_grant_is_bound_to_exact_plan_arguments(self):
        changed = TaskPlan.from_dict(
            {
                "id": self.plan.id,
                "goal": self.plan.goal,
                "steps": [
                    {
                        "id": step.id,
                        "capability": step.capability,
                        "arguments": (
                            {"items": ["silently changed"]}
                            if step.id == "add_to_list"
                            else step.arguments
                        ),
                    }
                    for step in self.plan.steps
                ],
            }
        )

        result = self.runtime.execute(
            changed,
            self.grant(approved_steps={"add_to_list"}),
        )

        self.assertEqual("rejected", result.status)
        self.assertEqual([], self.shopping_list)

    def test_grant_nonce_cannot_replay_a_write_plan(self):
        grant = self.grant(approved_steps={"add_to_list"})
        first = self.runtime.execute(
            self.plan,
            grant,
        )
        snapshot = list(self.shopping_list)
        second = self.runtime.execute(
            self.plan,
            grant,
        )

        self.assertEqual("completed", first.status)
        self.assertEqual("rejected", second.status)
        self.assertEqual(snapshot, self.shopping_list)

    def test_mutating_returned_output_does_not_rewrite_receipts(self):
        result = self.runtime.execute(
            self.plan,
            self.grant(approved_steps={"add_to_list"}),
        )
        result.outputs["add_to_list"]["list"].append("tampered")

        self.assertTrue(self.runtime.receipts.verify())
        self.assertNotIn("tampered", self.runtime.receipts.all()[-1]["output"]["list"])

    def test_capability_input_schema_is_enforced_before_side_effect(self):
        malformed = TaskPlan.from_dict(
            {
                "id": "schema-negative",
                "goal": "Attempt a malformed shopping write",
                "steps": [
                    {
                        "id": "bad_write",
                        "capability": "shopping.add_items",
                        "arguments": {"items": "abc"},
                    }
                ],
            }
        )
        grant = issue_grant(
            self.secret,
            malformed,
            {"shopping.add_items"},
            {"shopping.list.write"},
            Effect.WRITE,
            approved_steps={"bad_write"},
        )

        result = self.runtime.execute(malformed, grant)

        self.assertEqual("rejected", result.status)
        self.assertEqual([], self.shopping_list)
        self.assertIn("must be array", result.decisions[0].reason)

    def test_invalid_output_after_write_is_committed_unverified(self):
        committed: list[str] = []
        registry = CapabilityRegistry()
        capability = Capability(
            id="test.write_bad_output",
            app="test",
            description="Writes, then returns a malformed result",
            effect=Effect.WRITE,
            scopes=frozenset({"test.write"}),
            requires_confirmation=True,
            reversible=False,
            input_schema={"type": "object"},
            output_schema={
                "type": "object",
                "required": ["ok"],
                "properties": {"ok": {"type": "boolean"}},
            },
        )

        def write_then_return_bad_output(arguments):
            committed.append(str(arguments["value"]))
            return {"ok": "not-a-boolean"}

        registry.register(capability, write_then_return_bad_output)
        runtime = JidanRuntime(registry, PolicyEngine(self.secret))
        plan = TaskPlan(
            "output-unknown",
            "Prove post-commit output failures are not ordinary failures",
            (Step("write", capability.id, {"value": "committed"}),),
        )
        grant = issue_grant(
            self.secret,
            plan,
            {capability.id},
            capability.scopes,
            Effect.WRITE,
            approved_steps={"write"},
        )

        result = runtime.execute(plan, grant)

        self.assertEqual(["committed"], committed)
        self.assertEqual("unknown", result.status)
        self.assertEqual("committed_unverified", result.receipts[0]["status"])
        self.assertEqual("not-a-boolean", result.outputs["write"]["unverified_output"]["ok"])

    def test_write_adapter_exception_after_invocation_is_outcome_unknown(self):
        committed: list[str] = []
        registry = CapabilityRegistry()
        capability = Capability(
            id="test.write_then_timeout",
            app="test",
            description="Simulates a transport timeout after commit",
            effect=Effect.WRITE,
            scopes=frozenset({"test.write"}),
            requires_confirmation=True,
            reversible=False,
            input_schema={"type": "object"},
        )

        def commit_then_timeout(arguments):
            committed.append(str(arguments["value"]))
            raise TimeoutError("transport lost after provider commit")

        registry.register(capability, commit_then_timeout)
        runtime = JidanRuntime(registry, PolicyEngine(self.secret))
        plan = TaskPlan(
            "adapter-unknown",
            "Do not retry an ambiguous write",
            (Step("write", capability.id, {"value": "committed"}),),
        )
        grant = issue_grant(
            self.secret,
            plan,
            {capability.id},
            capability.scopes,
            Effect.WRITE,
            approved_steps={"write"},
        )

        result = runtime.execute(plan, grant)

        self.assertEqual(["committed"], committed)
        self.assertEqual("unknown", result.status)
        self.assertEqual("outcome_unknown", result.receipts[0]["status"])


if __name__ == "__main__":
    unittest.main()

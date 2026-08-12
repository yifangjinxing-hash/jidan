from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest


PROTOTYPE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROTOTYPE_ROOT.parent
sys.path.insert(0, str(PROTOTYPE_ROOT))

from jidan.models import Effect, Step, TaskPlan  # noqa: E402
from jidan.ninelights import (  # noqa: E402
    NINELIGHTS_PRESS_CAPABILITY_ID,
    NINELIGHTS_RULES_VERSION,
    NINELIGHTS_START_CAPABILITY_ID,
    ninelights_mcp_tools,
    ninelights_press,
    ninelights_start,
    register_ninelights,
)
from jidan.policy import PolicyEngine, issue_grant  # noqa: E402
from jidan.registry import CapabilityRegistry  # noqa: E402
from jidan.runtime import JidanRuntime  # noqa: E402


CONFORMANCE_PATH = (
    REPOSITORY_ROOT / "profiles" / "conformance" / "game.ninelights.vectors.json"
)


class NineLightsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.vectors = json.loads(CONFORMANCE_PATH.read_text(encoding="utf-8"))

    def registry(self) -> CapabilityRegistry:
        registry = CapabilityRegistry()
        register_ninelights(registry)
        return registry

    def runtime(self) -> tuple[JidanRuntime, bytes]:
        secret = b"nine-lights-test-secret"
        return JidanRuntime(self.registry(), PolicyEngine(secret)), secret

    def grant(self, secret: bytes, plan: TaskPlan):
        return issue_grant(
            secret,
            plan,
            capabilities={step.capability for step in plan.steps},
            scopes=(),
            max_effect=Effect.READ,
            capability_digests=self.registry().definition_digests(
                {step.capability for step in plan.steps}
            ),
        )

    def test_checked_in_profiles_match_runtime_exports(self) -> None:
        checked_in = {
            name: json.loads(
                (REPOSITORY_ROOT / "profiles" / f"{name}.tool.json").read_text(
                    encoding="utf-8"
                )
            )
            for name in (
                NINELIGHTS_START_CAPABILITY_ID,
                NINELIGHTS_PRESS_CAPABILITY_ID,
            )
        }
        exported = {tool["name"]: tool for tool in ninelights_mcp_tools()}

        self.assertEqual(checked_in, exported)

    def test_all_33_checked_in_conformance_vectors_match(self) -> None:
        self.assertEqual("JCL/0.1", self.vectors["profile"])
        self.assertEqual(NINELIGHTS_RULES_VERSION, self.vectors["rulesVersion"])
        self.assertEqual(
            NINELIGHTS_START_CAPABILITY_ID,
            self.vectors["startCapability"],
        )
        self.assertEqual(
            NINELIGHTS_PRESS_CAPABILITY_ID,
            self.vectors["pressCapability"],
        )
        self.assertEqual(
            33,
            sum(
                len(self.vectors[key])
                for key in ("startCases", "pressCases", "solutionCases")
            ),
        )

        registry = self.registry()
        for case in self.vectors["startCases"]:
            with self.subTest(kind="start", level=case["levelId"]):
                actual = registry.invoke(
                    NINELIGHTS_START_CAPABILITY_ID,
                    {"levelId": case["levelId"]},
                )
                self.assertEqual(case["expected"], actual)

        for case in self.vectors["pressCases"]:
            with self.subTest(
                kind="press",
                level=case["levelId"],
                cell=case["cell"],
            ):
                initial = registry.invoke(
                    NINELIGHTS_START_CAPABILITY_ID,
                    {"levelId": case["levelId"]},
                )
                output = registry.invoke(
                    NINELIGHTS_PRESS_CAPABILITY_ID,
                    {"state": initial, "cell": case["cell"]},
                )
                actual = {
                    "cells": output["state"]["cells"],
                    "moveCount": output["state"]["moveCount"],
                    "status": output["state"]["status"],
                    "changedCells": output["changedCells"],
                    "event": output["event"],
                }
                self.assertEqual(case["expected"], actual)

        for case in self.vectors["solutionCases"]:
            with self.subTest(kind="solution", level=case["levelId"]):
                state = registry.invoke(
                    NINELIGHTS_START_CAPABILITY_ID,
                    {"levelId": case["levelId"]},
                )
                for cell in case["cells"]:
                    state = registry.invoke(
                        NINELIGHTS_PRESS_CAPABILITY_ID,
                        {"state": state, "cell": cell},
                    )["state"]
                self.assertEqual(case["expectedStatus"], state["status"])

    def test_each_cell_toggles_only_itself_and_orthogonal_neighbors(self) -> None:
        expected_neighbors = (
            [0, 1, 3],
            [0, 1, 2, 4],
            [1, 2, 5],
            [0, 3, 4, 6],
            [1, 3, 4, 5, 7],
            [2, 4, 5, 8],
            [3, 6, 7],
            [4, 6, 7, 8],
            [5, 7, 8],
        )
        state = ninelights_start({"levelId": "full"})

        for cell, expected in enumerate(expected_neighbors):
            with self.subTest(cell=cell):
                output = ninelights_press({"state": state, "cell": cell})
                self.assertEqual(expected, output["changedCells"])
                changed = [
                    index
                    for index, (before, after) in enumerate(
                        zip(state["cells"], output["state"]["cells"])
                    )
                    if before != after
                ]
                self.assertEqual(expected, changed)

    def test_same_transition_is_deterministic_100_times(self) -> None:
        arguments = {
            "state": ninelights_start({"levelId": "corners"}),
            "cell": 4,
        }
        original = deepcopy(arguments)
        expected = ninelights_press(deepcopy(arguments))

        outputs = [ninelights_press(arguments) for _ in range(100)]

        self.assertTrue(all(output == expected for output in outputs))
        self.assertEqual(original, arguments)

    def test_schema_invalid_plans_are_rejected_without_receipts(self) -> None:
        runtime, secret = self.runtime()
        valid_state = ninelights_start({"levelId": "cross"})
        cases = (
            (NINELIGHTS_START_CAPABILITY_ID, {}),
            (NINELIGHTS_START_CAPABILITY_ID, {"levelId": "unknown"}),
            (
                NINELIGHTS_PRESS_CAPABILITY_ID,
                {"state": valid_state, "cell": 9},
            ),
            (
                NINELIGHTS_PRESS_CAPABILITY_ID,
                {
                    "state": {
                        **valid_state,
                        "cells": valid_state["cells"][:-1],
                    },
                    "cell": 0,
                },
            ),
            (
                NINELIGHTS_PRESS_CAPABILITY_ID,
                {"state": valid_state, "cell": 0, "unexpected": True},
            ),
        )

        for index, (capability, arguments) in enumerate(cases):
            with self.subTest(capability=capability, arguments=arguments):
                plan = TaskPlan(
                    id=f"schema-invalid-{index}",
                    goal="reject malformed game input before invocation",
                    steps=(Step("action", capability, arguments),),
                )
                result = runtime.execute(plan, self.grant(secret, plan))

                self.assertEqual("rejected", result.status)
                self.assertEqual("denied", result.decisions[0].outcome)
                self.assertEqual({}, result.outputs)
                self.assertEqual((), result.receipts)

        self.assertEqual((), runtime.receipts.all())

    def test_semantically_invalid_states_emit_failed_read_receipts(self) -> None:
        runtime, secret = self.runtime()
        valid_state = ninelights_start({"levelId": "cross"})
        cases = (
            (
                {
                    "rulesVersion": NINELIGHTS_RULES_VERSION,
                    "levelId": "cross",
                    "cells": [0] * 9,
                    "moveCount": 1,
                    "status": "won",
                },
                "terminal",
            ),
            ({**valid_state, "moveCount": -1}, "non-negative"),
            ({**valid_state, "status": "won"}, "does not match"),
        )

        for index, (state, error_fragment) in enumerate(cases):
            with self.subTest(state=state):
                arguments = {"state": state, "cell": 4}
                plan = TaskPlan(
                    id=f"semantic-invalid-{index}",
                    goal="reject a semantically invalid game state",
                    steps=(
                        Step(
                            "press",
                            NINELIGHTS_PRESS_CAPABILITY_ID,
                            arguments,
                        ),
                    ),
                )

                result = runtime.execute(plan, self.grant(secret, plan))

                self.assertEqual("failed", result.status)
                self.assertEqual("allowed", result.decisions[0].outcome)
                self.assertIn(error_fragment, result.outputs["press"]["error"])
                self.assertEqual(1, len(result.receipts))
                receipt = result.receipts[0]
                self.assertEqual("failed", receipt["status"])
                self.assertEqual("read", receipt["effect"])
                self.assertEqual(arguments, receipt["arguments"])
                self.assertEqual(result.outputs["press"], receipt["output"])

        self.assertEqual(3, len(runtime.receipts.all()))
        self.assertTrue(runtime.receipts.verify())

    def test_won_state_shape_is_valid_but_press_is_terminal(self) -> None:
        terminal_state = {
            "rulesVersion": NINELIGHTS_RULES_VERSION,
            "levelId": "cross",
            "cells": [0] * 9,
            "moveCount": 1,
            "status": "won",
        }
        registry = self.registry()

        registry.validate_input(
            NINELIGHTS_PRESS_CAPABILITY_ID,
            {"state": terminal_state, "cell": 4},
        )
        with self.assertRaisesRegex(ValueError, "terminal"):
            registry.invoke(
                NINELIGHTS_PRESS_CAPABILITY_ID,
                {"state": terminal_state, "cell": 4},
            )

    def test_successful_runtime_actions_form_a_verified_receipt_chain(self) -> None:
        runtime, secret = self.runtime()
        start_plan = TaskPlan(
            id="runtime-start",
            goal="start a local Nine Lights level",
            steps=(
                Step(
                    "start",
                    NINELIGHTS_START_CAPABILITY_ID,
                    {"levelId": "cross"},
                ),
            ),
        )
        started = runtime.execute(start_plan, self.grant(secret, start_plan))
        press_plan = TaskPlan(
            id="runtime-press",
            goal="apply one local Nine Lights move",
            steps=(
                Step(
                    "press",
                    NINELIGHTS_PRESS_CAPABILITY_ID,
                    {"state": started.outputs["start"], "cell": 4},
                ),
            ),
        )

        pressed = runtime.execute(press_plan, self.grant(secret, press_plan))

        self.assertEqual("completed", started.status)
        self.assertEqual("completed", pressed.status)
        self.assertEqual("won", pressed.outputs["press"]["state"]["status"])
        self.assertEqual("won", pressed.outputs["press"]["event"])
        receipts = runtime.receipts.all()
        self.assertEqual(2, len(receipts))
        self.assertTrue(all(receipt["status"] == "succeeded" for receipt in receipts))
        self.assertTrue(all(receipt["effect"] == "read" for receipt in receipts))
        self.assertEqual(receipts[0]["hash"], receipts[1]["previous_hash"])
        self.assertTrue(runtime.receipts.verify())

    def test_grant_nonce_cannot_replay_even_a_read_action(self) -> None:
        runtime, secret = self.runtime()
        plan = TaskPlan(
            id="read-replay",
            goal="start a deterministic local game once",
            steps=(
                Step(
                    "start",
                    NINELIGHTS_START_CAPABILITY_ID,
                    {"levelId": "full"},
                ),
            ),
        )
        grant = self.grant(secret, plan)

        first = runtime.execute(plan, grant)
        second = runtime.execute(plan, grant)

        self.assertEqual("completed", first.status)
        self.assertEqual("rejected", second.status)
        self.assertEqual("denied", second.decisions[0].outcome)
        self.assertIn("already been consumed", second.decisions[0].reason)
        self.assertEqual(1, len(runtime.receipts.all()))
        self.assertEqual((), second.receipts)
        self.assertTrue(runtime.receipts.verify())


if __name__ == "__main__":
    unittest.main()

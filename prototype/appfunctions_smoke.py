from __future__ import annotations

from collections.abc import Sequence
from typing import Any
import json

from jidan import CapabilityRegistry, Effect, JidanRuntime, PolicyEngine, Step, TaskPlan, issue_grant
from jidan.android_appfunctions import AdbAppFunctionsAdapter, CommandResult
from jidan.console import configure_utf8_stdio


PACKAGE = "com.example.notes"
FUNCTION = "com.example.notes.NoteFunctions#createNote"


class FakeAdbRunner:
    """Deterministic adb transcript for the no-device end-to-end smoke."""

    def __init__(self, responses: Sequence[CommandResult]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv: Sequence[str], *, timeout_seconds: float) -> CommandResult:
        del timeout_seconds
        self.calls.append(tuple(argv))
        if not self._responses:
            raise AssertionError("fake adb received an unexpected command")
        return self._responses.pop(0)


def run_smoke() -> dict[str, Any]:
    discovery = {
        PACKAGE: [
            {
                "AppFunctionStaticMetadata": {
                    "description": ["Create a note with an explicit title."],
                    "parameters": [
                        {
                            "name": ["title"],
                            "isRequired": [True],
                            "dataType": [{"type": ["string"]}],
                        }
                    ],
                    "response": [{"valueType": [{"type": [8]}]}],
                },
                "AppFunctionRuntimeMetadata": {
                    "packageName": [PACKAGE],
                    "functionId": [FUNCTION],
                },
            }
        ]
    }
    fake_adb = FakeAdbRunner(
        [
            CommandResult(0, json.dumps(discovery), ""),
            CommandResult(0, '{"androidAppfunctionsReturnValue":["note-42"]}', ""),
        ]
    )
    adapter = AdbAppFunctionsAdapter(fake_adb)
    registry = CapabilityRegistry()
    records = adapter.register_discovered(registry, package_name=PACKAGE)
    capability = records[0].capability

    secret = b"jidan-appfunctions-smoke-key"
    runtime = JidanRuntime(registry, PolicyEngine(secret))
    plan = TaskPlan(
        id="appfunctions.smoke",
        goal="Create one note through a discovered Android AppFunction",
        steps=(
            Step(
                id="create_note",
                capability=capability.id,
                arguments={"title": "Jidan roadmap"},
            ),
        ),
    )
    initial_grant = issue_grant(
        secret,
        plan,
        [capability.id],
        capability.scopes,
        Effect.EXTERNAL,
    )

    waiting = runtime.execute(plan, initial_grant)
    if waiting.status != "awaiting_confirmation":
        raise AssertionError(f"expected confirmation gate, got {waiting.status}")
    if len(fake_adb.calls) != 1 or runtime.receipts.all():
        raise AssertionError("preflight executed the adapter or emitted a receipt")

    # Issue a fresh, plan-bound grant with the approved step in its HMAC payload.
    approved_grant = issue_grant(
        secret,
        plan,
        [capability.id],
        capability.scopes,
        Effect.EXTERNAL,
        approved_steps={"create_note"},
    )
    completed = runtime.execute(plan, approved_grant)
    if completed.status != "completed":
        raise AssertionError(f"approved JGraph failed: {completed.status}")
    if len(fake_adb.calls) != 2:
        raise AssertionError("approved graph did not execute exactly one AppFunction")
    if not runtime.receipts.verify() or len(completed.receipts) != 1:
        raise AssertionError("receipt chain verification failed")

    return {
        "discovered_capability": capability.id,
        "preflight_status": waiting.status,
        "approved_status": completed.status,
        "execute_output": completed.outputs["create_note"],
        "receipt_chain_valid": runtime.receipts.verify(),
        "fake_adb_calls": len(fake_adb.calls),
    }


if __name__ == "__main__":
    configure_utf8_stdio()
    print(json.dumps(run_smoke(), ensure_ascii=False, indent=2))

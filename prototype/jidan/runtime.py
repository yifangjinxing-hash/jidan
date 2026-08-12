from __future__ import annotations

from typing import Any, Mapping
from copy import deepcopy

from .audit import ReceiptLog
from .models import Decision, Effect, Grant, RunResult, TaskPlan
from .policy import PolicyEngine
from .registry import CapabilityOutputError, CapabilityRegistry


class JidanRuntime:
    """Validates untrusted plans, gates effects, invokes adapters, and emits receipts."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        policy: PolicyEngine,
        receipts: ReceiptLog | None = None,
    ) -> None:
        self.registry = registry
        self.policy = policy
        self.receipts = receipts or ReceiptLog()

    def preflight(
        self,
        plan: TaskPlan,
        grant: Grant,
    ) -> tuple[Decision, ...]:
        decisions: list[Decision] = []
        prior_steps: set[str] = set()
        for step in plan.steps:
            try:
                capability = self.registry.get(step.capability)
                # A Grant may bind only an executable, sealed Registry entry.
                self.registry.definition_digest(step.capability)
                self._validate_refs(step.arguments, prior_steps)
                self.registry.validate_input(
                    step.capability,
                    step.arguments,
                    allow_refs=True,
                )
            except (KeyError, RuntimeError, ValueError) as exc:
                decisions.append(Decision(step.id, step.capability, "denied", str(exc)))
                prior_steps.add(step.id)
                continue
            decisions.append(self.policy.decide(plan, step, capability, grant))
            prior_steps.add(step.id)
        return tuple(decisions)

    def execute(
        self,
        plan: TaskPlan,
        grant: Grant,
    ) -> RunResult:
        # Planner-owned mappings are mutable even though the dataclass is frozen.
        # Execute an isolated snapshot so later caller mutations cannot race the
        # plan hash check and adapter invocation.
        plan = deepcopy(plan)
        decisions = self.preflight(plan, grant)
        if any(item.outcome == "denied" for item in decisions):
            return RunResult(status="rejected", decisions=decisions)
        if any(item.outcome == "needs_confirmation" for item in decisions):
            return RunResult(status="awaiting_confirmation", decisions=decisions)

        consumed, reason = self.policy.consume_grant(grant, plan)
        if not consumed:
            replay_decisions = tuple(
                Decision(step.id, step.capability, "denied", reason)
                for step in plan.steps
            )
            return RunResult(status="rejected", decisions=replay_decisions)

        outputs: dict[str, Mapping[str, Any]] = {}
        new_receipts: list[Mapping[str, Any]] = []
        for step in plan.steps:
            capability = self.registry.get(step.capability)
            invocation_started = False
            try:
                arguments = self._resolve_refs(step.arguments, outputs)
                self.registry.validate_input(step.capability, arguments)
                invocation_started = True
                output = self.registry.invoke(step.capability, arguments)
                status = "succeeded"
            except CapabilityOutputError as exc:
                output = {
                    "error": f"CapabilityOutputError: {exc}",
                    "unverified_output": exc.output,
                }
                status = "committed_unverified"
            except Exception as exc:  # Adapter failures become data and stop the task.
                if not invocation_started:
                    arguments = deepcopy(dict(step.arguments))
                output = {"error": f"{type(exc).__name__}: {exc}"}
                status = (
                    "outcome_unknown"
                    if invocation_started
                    and capability.effect.at_least(Effect.NAVIGATION)
                    else "failed"
                )
            receipt = self.receipts.append(
                task_id=plan.id,
                step_id=step.id,
                capability=capability.id,
                capability_digest=self.registry.definition_digest(capability.id),
                effect=capability.effect.label(),
                status=status,
                arguments=arguments,
                output=output,
            )
            new_receipts.append(receipt)
            outputs[step.id] = deepcopy(dict(output))
            if status in {"committed_unverified", "outcome_unknown"}:
                return RunResult(
                    status="unknown",
                    decisions=decisions,
                    outputs=outputs,
                    receipts=tuple(new_receipts),
                )
            if status == "failed":
                return RunResult(
                    status="failed",
                    decisions=decisions,
                    outputs=outputs,
                    receipts=tuple(new_receipts),
                )
        return RunResult(
            status="completed",
            decisions=decisions,
            outputs=outputs,
            receipts=tuple(new_receipts),
        )

    def _validate_refs(self, value: Any, prior_steps: set[str]) -> None:
        if isinstance(value, Mapping):
            if set(value) == {"$ref"}:
                reference = str(value["$ref"])
                source = reference.split(".", 1)[0]
                if source not in prior_steps:
                    raise ValueError(f"reference must target an earlier step: {reference}")
                return
            for child in value.values():
                self._validate_refs(child, prior_steps)
        elif isinstance(value, (list, tuple)):
            for child in value:
                self._validate_refs(child, prior_steps)

    def _resolve_refs(
        self,
        value: Any,
        outputs: Mapping[str, Mapping[str, Any]],
    ) -> Any:
        if isinstance(value, Mapping):
            if set(value) == {"$ref"}:
                reference = str(value["$ref"])
                parts = reference.split(".")
                current: Any = outputs
                try:
                    for part in parts:
                        current = current[part]
                except (KeyError, TypeError) as exc:
                    raise ValueError(f"unresolvable reference: {reference}") from exc
                return current
            return {key: self._resolve_refs(child, outputs) for key, child in value.items()}
        if isinstance(value, list):
            return [self._resolve_refs(child, outputs) for child in value]
        if isinstance(value, tuple):
            return tuple(self._resolve_refs(child, outputs) for child in value)
        return value

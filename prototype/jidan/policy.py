from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, replace
from typing import Any
import hashlib
import hmac
import json
import secrets
import time

from .grant_ledger import (
    GrantConsumption,
    GrantLedger,
    GrantLedgerError,
    InMemoryGrantLedger,
)
from .models import Capability, Decision, Effect, Grant, Step, TaskPlan


def plan_digest(plan: TaskPlan) -> str:
    """Bind authorization to the exact immutable task graph and arguments."""

    payload = {
        "id": plan.id,
        "goal": plan.goal,
        "steps": [
            {
                "id": step.id,
                "capability": step.capability,
                "arguments": step.arguments,
            }
            for step in plan.steps
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _canonical_payload(grant: Grant) -> bytes:
    raw = asdict(replace(grant, signature=""))
    raw["capabilities"] = sorted(raw["capabilities"])
    raw["scopes"] = sorted(raw["scopes"])
    raw["approved_steps"] = sorted(raw["approved_steps"])
    raw["max_effect"] = int(grant.max_effect)
    return json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def issue_grant(
    secret: bytes,
    task_id: TaskPlan | str,
    capabilities: Iterable[str],
    scopes: Iterable[str],
    max_effect: Effect | str = Effect.WRITE,
    ttl_seconds: int = 300,
    now: int | None = None,
    plan_hash: str | None = None,
    approved_steps: Iterable[str] = (),
) -> Grant:
    if isinstance(task_id, TaskPlan):
        task = task_id
        task_id_value = task.id
        digest = plan_digest(task)
        if plan_hash is not None and not hmac.compare_digest(plan_hash, digest):
            raise ValueError("provided plan_hash does not match the task plan")
    else:
        task_id_value = task_id
        if plan_hash is None:
            raise ValueError("plan_hash is required; preferably pass the TaskPlan as task_id")
        digest = plan_hash
    issued_at = int(time.time()) if now is None else now
    unsigned = Grant(
        task_id=task_id_value,
        plan_hash=digest,
        capabilities=frozenset(capabilities),
        scopes=frozenset(scopes),
        approved_steps=frozenset(approved_steps),
        max_effect=Effect.parse(max_effect),
        expires_at=issued_at + ttl_seconds,
        nonce=secrets.token_hex(16),
        signature="",
    )
    signature = hmac.new(secret, _canonical_payload(unsigned), hashlib.sha256).hexdigest()
    return replace(unsigned, signature=signature)


class PolicyEngine:
    """Deterministic policy boundary. No model output is trusted here."""

    def __init__(
        self,
        secret: bytes,
        clock: Any = time.time,
        grant_ledger: GrantLedger | None = None,
    ) -> None:
        self._secret = secret
        self._clock = clock
        self.grant_ledger = (
            grant_ledger if grant_ledger is not None else InMemoryGrantLedger()
        )

    def verify_grant(self, grant: Grant, plan: TaskPlan) -> tuple[bool, str]:
        expected = hmac.new(self._secret, _canonical_payload(grant), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, grant.signature):
            return False, "grant signature is invalid"
        if grant.task_id != plan.id:
            return False, "grant belongs to a different task"
        if not hmac.compare_digest(grant.plan_hash, plan_digest(plan)):
            return False, "grant belongs to a different task plan"
        if int(self._clock()) >= grant.expires_at:
            return False, "grant has expired"
        return True, "grant is valid"

    def consume_grant(self, grant: Grant, plan: TaskPlan) -> tuple[bool, str]:
        """Atomically make a grant single-use immediately before side effects."""

        valid, reason = self.verify_grant(grant, plan)
        if not valid:
            return False, reason
        record = GrantConsumption(
            nonce=grant.nonce,
            task_id=grant.task_id,
            plan_hash=grant.plan_hash,
            signature_sha256=hashlib.sha256(grant.signature.encode("ascii")).hexdigest(),
            consumed_at_ms=int(float(self._clock()) * 1000),
        )
        try:
            consumed = self.grant_ledger.consume(record)
        except (GrantLedgerError, ValueError) as exc:
            return False, f"grant ledger rejected consumption: {exc}"
        if not consumed:
            return False, "grant has already been consumed"
        return True, "grant consumed"

    def decide(
        self,
        plan: TaskPlan,
        step: Step,
        capability: Capability,
        grant: Grant,
    ) -> Decision:
        valid, reason = self.verify_grant(grant, plan)
        if not valid:
            return Decision(step.id, capability.id, "denied", reason)
        if capability.id not in grant.capabilities:
            return Decision(step.id, capability.id, "denied", "capability is outside this task grant")
        missing_scopes = capability.scopes - grant.scopes
        if missing_scopes:
            missing = ", ".join(sorted(missing_scopes))
            return Decision(step.id, capability.id, "denied", f"missing scopes: {missing}")
        if capability.effect > grant.max_effect:
            return Decision(
                step.id,
                capability.id,
                "denied",
                f"effect {capability.effect.label()} exceeds grant ceiling {grant.max_effect.label()}",
            )
        confirmation_required = (
            capability.requires_confirmation
            or capability.effect >= Effect.EXTERNAL
            or not capability.reversible
        )
        if confirmation_required and step.id not in grant.approved_steps:
            return Decision(
                step.id,
                capability.id,
                "needs_confirmation",
                f"{capability.effect.label()} effect requires explicit approval",
            )
        return Decision(step.id, capability.id, "allowed", "policy conditions satisfied")

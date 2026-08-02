from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, replace
from typing import Any, Mapping
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
from .registry import capability_digest


_LOWER_HEX = frozenset("0123456789abcdef")


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
    raw["capability_digests"] = [
        list(item) for item in sorted(grant.capability_digests)
    ]
    raw["max_effect"] = int(grant.max_effect)
    return json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _is_lower_hex(value: Any, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in _LOWER_HEX for character in value)
    )


def _validate_grant_shape(grant: Grant) -> None:
    """Reject malformed deserialized Grants before canonicalization or HMAC."""

    if not isinstance(grant.task_id, str) or not grant.task_id:
        raise ValueError("invalid task_id")
    if not _is_lower_hex(grant.plan_hash, 64):
        raise ValueError("invalid plan_hash")
    if not _is_lower_hex(grant.nonce, 32):
        raise ValueError("invalid nonce")
    if not _is_lower_hex(grant.signature, 64):
        raise ValueError("invalid signature")
    if not isinstance(grant.max_effect, Effect):
        raise ValueError("invalid max_effect")
    if (
        isinstance(grant.expires_at, bool)
        or not isinstance(grant.expires_at, int)
    ):
        raise ValueError("invalid expires_at")
    for name, values in (
        ("capabilities", grant.capabilities),
        ("scopes", grant.scopes),
        ("approved_steps", grant.approved_steps),
    ):
        if not isinstance(values, frozenset) or not all(
            isinstance(value, str) for value in values
        ):
            raise ValueError(f"invalid {name}")
    if not isinstance(grant.capability_digests, tuple):
        raise ValueError("invalid capability_digests")
    digest_map: dict[str, str] = {}
    for item in grant.capability_digests:
        if not isinstance(item, tuple) or len(item) != 2:
            raise ValueError("invalid capability digest entry")
        capability_id, definition_digest = item
        if not isinstance(capability_id, str) or not _is_lower_hex(
            definition_digest, 64
        ):
            raise ValueError("invalid capability digest entry")
        if capability_id in digest_map:
            raise ValueError("duplicate capability digest entry")
        digest_map[capability_id] = definition_digest
    if set(digest_map) != set(grant.capabilities):
        raise ValueError("capability digest set does not match grant")


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
    capability_digests: Mapping[str, str] | None = None,
) -> Grant:
    if isinstance(task_id, TaskPlan):
        task = task_id
        task_id_value = task.id
        task_plan_digest = plan_digest(task)
        if plan_hash is not None and not hmac.compare_digest(plan_hash, task_plan_digest):
            raise ValueError("provided plan_hash does not match the task plan")
    else:
        task_id_value = task_id
        if plan_hash is None:
            raise ValueError("plan_hash is required; preferably pass the TaskPlan as task_id")
        task_plan_digest = plan_hash
    capability_set = frozenset(capabilities)
    if capability_digests is None:
        raise ValueError(
            "capability_digests are required; bind the grant to the trusted registry"
        )
    supplied = {
        str(key): str(value).lower() for key, value in capability_digests.items()
    }
    if set(supplied) != set(capability_set):
        raise ValueError("capability_digests must bind every granted capability exactly")
    for capability_id, definition_digest in supplied.items():
        if len(definition_digest) != 64 or any(
            character not in "0123456789abcdef"
            for character in definition_digest
        ):
            raise ValueError(f"invalid capability digest for {capability_id}")
    digest_pairs = tuple(sorted(supplied.items()))

    issued_at = int(time.time()) if now is None else now
    unsigned = Grant(
        task_id=task_id_value,
        plan_hash=task_plan_digest,
        capabilities=capability_set,
        scopes=frozenset(scopes),
        approved_steps=frozenset(approved_steps),
        max_effect=Effect.parse(max_effect),
        expires_at=issued_at + ttl_seconds,
        nonce=secrets.token_hex(16),
        signature="",
        capability_digests=digest_pairs,
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
        try:
            _validate_grant_shape(grant)
            expected = hmac.new(
                self._secret,
                _canonical_payload(grant),
                hashlib.sha256,
            ).hexdigest()
        except (TypeError, ValueError, OverflowError, RecursionError):
            return False, "grant format is invalid"
        if not hmac.compare_digest(expected, grant.signature):
            return False, "grant signature is invalid"
        if grant.task_id != plan.id:
            return False, "grant belongs to a different task"
        try:
            actual_plan_hash = plan_digest(plan)
        except (TypeError, ValueError, OverflowError, RecursionError):
            return False, "task plan cannot be canonicalized"
        if not hmac.compare_digest(grant.plan_hash, actual_plan_hash):
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
        bound_digests = dict(grant.capability_digests)
        expected_digest = bound_digests.get(capability.id)
        if expected_digest is None:
            return Decision(
                step.id,
                capability.id,
                "denied",
                "capability definition is not bound by this task grant",
            )
        actual_digest = capability_digest(capability)
        if not hmac.compare_digest(expected_digest, actual_digest):
            return Decision(
                step.id,
                capability.id,
                "denied",
                "capability definition changed after grant issuance",
            )
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

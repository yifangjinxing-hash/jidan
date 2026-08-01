from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Mapping
import re


_ID_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]{0,127}$")


class Effect(IntEnum):
    """The maximum external effect a capability may have."""

    READ = 0
    WRITE = 1
    EXTERNAL = 2
    IRREVERSIBLE = 3

    @classmethod
    def parse(cls, value: str | int | "Effect") -> "Effect":
        if isinstance(value, cls):
            return value
        if isinstance(value, int):
            return cls(value)
        return cls[value.strip().upper()]

    def label(self) -> str:
        return self.name.lower()


@dataclass(frozen=True)
class Capability:
    id: str
    app: str
    description: str
    effect: Effect
    scopes: frozenset[str] = field(default_factory=frozenset)
    requires_confirmation: bool = False
    reversible: bool = True
    input_schema: Mapping[str, Any] = field(default_factory=dict)
    output_schema: Mapping[str, Any] = field(default_factory=dict)
    adapter: str = "demo"

    def __post_init__(self) -> None:
        if not _ID_PATTERN.match(self.id):
            raise ValueError(f"invalid capability id: {self.id!r}")
        if not _ID_PATTERN.match(self.app):
            raise ValueError(f"invalid app id: {self.app!r}")
        if self.effect is Effect.IRREVERSIBLE and self.reversible:
            raise ValueError("an irreversible capability cannot be marked reversible")

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Capability":
        return cls(
            id=str(raw["id"]),
            app=str(raw["app"]),
            description=str(raw["description"]),
            effect=Effect.parse(raw.get("effect", "read")),
            scopes=frozenset(str(item) for item in raw.get("scopes", [])),
            requires_confirmation=bool(raw.get("requires_confirmation", False)),
            reversible=bool(raw.get("reversible", True)),
            input_schema=raw.get("input_schema", {}),
            output_schema=raw.get("output_schema", {}),
            adapter=str(raw.get("adapter", "demo")),
        )


@dataclass(frozen=True)
class Step:
    id: str
    capability: str
    arguments: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not _ID_PATTERN.match(self.id):
            raise ValueError(f"invalid step id: {self.id!r}")
        if not _ID_PATTERN.match(self.capability):
            raise ValueError(f"invalid capability reference: {self.capability!r}")

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Step":
        return cls(
            id=str(raw["id"]),
            capability=str(raw["capability"]),
            arguments=raw.get("arguments", {}),
        )


@dataclass(frozen=True)
class TaskPlan:
    id: str
    goal: str
    steps: tuple[Step, ...]

    def __post_init__(self) -> None:
        if not _ID_PATTERN.match(self.id):
            raise ValueError(f"invalid task id: {self.id!r}")
        if not self.goal.strip():
            raise ValueError("task goal must not be empty")
        step_ids = [step.id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("step ids must be unique")

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "TaskPlan":
        return cls(
            id=str(raw["id"]),
            goal=str(raw["goal"]),
            steps=tuple(Step.from_dict(item) for item in raw.get("steps", [])),
        )


@dataclass(frozen=True)
class Grant:
    task_id: str
    plan_hash: str
    capabilities: frozenset[str]
    scopes: frozenset[str]
    approved_steps: frozenset[str]
    max_effect: Effect
    expires_at: int
    nonce: str
    signature: str


@dataclass(frozen=True)
class Decision:
    step_id: str
    capability: str
    outcome: str
    reason: str


@dataclass(frozen=True)
class RunResult:
    status: str
    decisions: tuple[Decision, ...]
    outputs: Mapping[str, Any] = field(default_factory=dict)
    receipts: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)

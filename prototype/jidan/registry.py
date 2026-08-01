from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping
import json

from .models import Capability


CapabilityHandler = Callable[[Mapping[str, Any]], Mapping[str, Any]]


class CapabilityInputError(ValueError):
    """Arguments do not satisfy the capability contract before invocation."""


class CapabilityOutputError(RuntimeError):
    """The provider returned after invocation, but its output is unverified."""

    def __init__(self, message: str, output: Any) -> None:
        super().__init__(message)
        self.output = deepcopy(output)


class CapabilityRegistry:
    """Trusted mapping from declarative capability IDs to concrete adapters."""

    def __init__(self) -> None:
        self._capabilities: dict[str, Capability] = {}
        self._handlers: dict[str, CapabilityHandler] = {}

    def load_directory(self, directory: str | Path) -> None:
        for path in sorted(Path(directory).glob("*.json")):
            raw = json.loads(path.read_text(encoding="utf-8"))
            entries = raw.get("capabilities", [raw])
            for entry in entries:
                self.register(Capability.from_dict(entry))

    def register(
        self,
        capability: Capability,
        handler: CapabilityHandler | None = None,
    ) -> None:
        if capability.id in self._capabilities:
            raise ValueError(f"duplicate capability: {capability.id}")
        self._capabilities[capability.id] = capability
        if handler is not None:
            self._handlers[capability.id] = handler

    def bind(self, capability_id: str, handler: CapabilityHandler) -> None:
        if capability_id not in self._capabilities:
            raise KeyError(f"unknown capability: {capability_id}")
        self._handlers[capability_id] = handler

    def get(self, capability_id: str) -> Capability:
        try:
            return self._capabilities[capability_id]
        except KeyError as exc:
            raise KeyError(f"unknown capability: {capability_id}") from exc

    def validate_input(
        self,
        capability_id: str,
        arguments: Mapping[str, Any],
        *,
        allow_refs: bool = False,
    ) -> None:
        capability = self.get(capability_id)
        try:
            _validate_schema(
                arguments,
                capability.input_schema,
                path="$input",
                allow_refs=allow_refs,
            )
        except (TypeError, ValueError) as exc:
            raise CapabilityInputError(str(exc)) from exc

    def invoke(self, capability_id: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        if capability_id not in self._handlers:
            raise RuntimeError(f"capability has no bound adapter: {capability_id}")
        capability = self.get(capability_id)
        self.validate_input(capability_id, arguments)
        result = self._handlers[capability_id](arguments)
        if not isinstance(result, Mapping):
            raise CapabilityOutputError(
                f"handler {capability_id} must return a mapping",
                result,
            )
        normalized = dict(result)
        try:
            _validate_schema(normalized, capability.output_schema, path="$output")
        except (TypeError, ValueError) as exc:
            raise CapabilityOutputError(str(exc), normalized) from exc
        return normalized

    def list(self) -> tuple[Capability, ...]:
        return tuple(self._capabilities[key] for key in sorted(self._capabilities))


def _validate_schema(
    value: Any,
    schema: Mapping[str, Any],
    *,
    path: str,
    allow_refs: bool = False,
) -> None:
    """Validate the small JSON Schema subset used by JCC v0 manifests."""

    if not schema:
        return
    if allow_refs and isinstance(value, Mapping) and set(value) == {"$ref"}:
        return
    declared = schema.get("type")
    if declared is not None:
        allowed = {declared} if isinstance(declared, str) else set(declared)
        actual = _json_type(value)
        if actual not in allowed and not (actual == "integer" and "number" in allowed):
            expected = " or ".join(sorted(str(item) for item in allowed))
            raise ValueError(f"{path} must be {expected}, got {actual}")

    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path} is outside the declared enum")
    if "const" in schema and value != schema["const"]:
        raise ValueError(f"{path} does not match the declared constant")

    if isinstance(value, Mapping):
        required = schema.get("required", ())
        for key in required:
            if key not in value:
                raise ValueError(f"{path}.{key} is required")
        properties = schema.get("properties", {})
        if isinstance(properties, Mapping):
            for key, child in value.items():
                child_schema = properties.get(key)
                if isinstance(child_schema, Mapping):
                    _validate_schema(
                        child,
                        child_schema,
                        path=f"{path}.{key}",
                        allow_refs=allow_refs,
                    )
                elif schema.get("additionalProperties") is False:
                    raise ValueError(f"{path}.{key} is not an allowed property")

    if isinstance(value, (list, tuple)):
        if "minItems" in schema and len(value) < int(schema["minItems"]):
            raise ValueError(f"{path} has fewer than minItems")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise ValueError(f"{path} has more than maxItems")
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, child in enumerate(value):
                _validate_schema(
                    child,
                    item_schema,
                    path=f"{path}[{index}]",
                    allow_refs=allow_refs,
                )

    if isinstance(value, str):
        if "minLength" in schema and len(value) < int(schema["minLength"]):
            raise ValueError(f"{path} is shorter than minLength")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise ValueError(f"{path} is longer than maxLength")


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, (list, tuple)):
        return "array"
    return type(value).__name__

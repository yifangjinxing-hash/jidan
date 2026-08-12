from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .models import Capability, Effect
from .registry import CapabilityRegistry


NINELIGHTS_START_CAPABILITY_ID = "game.ninelights.start"
NINELIGHTS_PRESS_CAPABILITY_ID = "game.ninelights.press"
NINELIGHTS_RULES_VERSION = "ninelights/1"
JCL_META_KEY = "dev.jidan/capability-v0.1"

LEVELS: Mapping[str, tuple[int, ...]] = {
    "cross": (0, 1, 0, 1, 1, 1, 0, 1, 0),
    "corners": (1, 1, 0, 1, 0, 1, 0, 1, 1),
    "full": (1, 1, 1, 1, 1, 1, 1, 1, 1),
}

TOGGLE_MAP: tuple[tuple[int, ...], ...] = tuple(
    tuple(
        sorted(
            candidate
            for candidate in range(9)
            if (
                candidate == cell
                or (
                    abs((candidate // 3) - (cell // 3))
                    + abs((candidate % 3) - (cell % 3))
                    == 1
                )
            )
        )
    )
    for cell in range(9)
)

STATE_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "rulesVersion": {"const": NINELIGHTS_RULES_VERSION},
        "levelId": {"enum": list(LEVELS)},
        "cells": {
            "type": "array",
            "minItems": 9,
            "maxItems": 9,
            "items": {"type": "integer", "enum": [0, 1]},
        },
        "moveCount": {"type": "integer"},
        "status": {"enum": ["playing", "won"]},
    },
    "required": ["rulesVersion", "levelId", "cells", "moveCount", "status"],
    "additionalProperties": False,
}

NINELIGHTS_START_INPUT_SCHEMA: Mapping[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {"levelId": {"enum": list(LEVELS)}},
    "required": ["levelId"],
    "additionalProperties": False,
}

NINELIGHTS_START_OUTPUT_SCHEMA: Mapping[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    **STATE_SCHEMA,
}

NINELIGHTS_PRESS_INPUT_SCHEMA: Mapping[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "state": STATE_SCHEMA,
        "cell": {"type": "integer", "enum": list(range(9))},
    },
    "required": ["state", "cell"],
    "additionalProperties": False,
}

NINELIGHTS_PRESS_OUTPUT_SCHEMA: Mapping[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "state": STATE_SCHEMA,
        "changedCells": {
            "type": "array",
            "minItems": 3,
            "maxItems": 5,
            "items": {"type": "integer", "enum": list(range(9))},
        },
        "event": {"enum": ["pressed", "won"]},
    },
    "required": ["state", "changedCells", "event"],
    "additionalProperties": False,
}


def ninelights_capabilities() -> tuple[Capability, Capability]:
    """Return the two stateless capabilities that form the complete game API."""

    common = {
        "app": "jidan.game",
        "effect": Effect.READ,
        "scopes": frozenset(),
        "requires_confirmation": False,
        "reversible": True,
    }
    return (
        Capability(
            id=NINELIGHTS_START_CAPABILITY_ID,
            description="Start one of the fixed Nine Lights levels.",
            input_schema=NINELIGHTS_START_INPUT_SCHEMA,
            output_schema=NINELIGHTS_START_OUTPUT_SCHEMA,
            adapter="jidan.ninelights.reference.start",
            **common,
        ),
        Capability(
            id=NINELIGHTS_PRESS_CAPABILITY_ID,
            description=(
                "Press one Nine Lights cell and return the complete next state. "
                "No state is retained by the capability."
            ),
            input_schema=NINELIGHTS_PRESS_INPUT_SCHEMA,
            output_schema=NINELIGHTS_PRESS_OUTPUT_SCHEMA,
            adapter="jidan.ninelights.reference.press",
            **common,
        ),
    )


def ninelights_mcp_tools() -> tuple[dict[str, Any], dict[str, Any]]:
    """Export both capabilities through JCL 0.1's MCP-compatible encoding."""

    return tuple(_mcp_tool(capability) for capability in ninelights_capabilities())


def register_ninelights(registry: CapabilityRegistry) -> tuple[Capability, Capability]:
    """Register the dependency-free Python reference implementation."""

    start_capability, press_capability = ninelights_capabilities()
    registry.register(start_capability, ninelights_start)
    registry.register(press_capability, ninelights_press)
    return start_capability, press_capability


def ninelights_start(arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return a fresh, explicit state snapshot for a fixed level."""

    level_id = arguments.get("levelId")
    if not isinstance(level_id, str) or level_id not in LEVELS:
        raise ValueError("levelId must name a built-in Nine Lights level")
    return {
        "rulesVersion": NINELIGHTS_RULES_VERSION,
        "levelId": level_id,
        "cells": list(LEVELS[level_id]),
        "moveCount": 0,
        "status": "playing",
    }


def ninelights_press(arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    """Apply one pure, deterministic state transition."""

    state = _validated_state(arguments.get("state"))
    if state["status"] == "won":
        raise ValueError("a won game is terminal; start a new level before pressing")

    cell = arguments.get("cell")
    if isinstance(cell, bool) or not isinstance(cell, int) or not 0 <= cell <= 8:
        raise ValueError("cell must be an integer from 0 through 8")

    cells = list(state["cells"])
    changed_cells = TOGGLE_MAP[cell]
    for changed in changed_cells:
        cells[changed] = 1 - cells[changed]
    won = all(value == 0 for value in cells)
    next_state = {
        "rulesVersion": NINELIGHTS_RULES_VERSION,
        "levelId": state["levelId"],
        "cells": cells,
        "moveCount": state["moveCount"] + 1,
        "status": "won" if won else "playing",
    }
    return {
        "state": next_state,
        "changedCells": list(changed_cells),
        "event": "won" if won else "pressed",
    }


def _validated_state(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError("state must be an object")
    if set(raw) != {"rulesVersion", "levelId", "cells", "moveCount", "status"}:
        raise ValueError("state fields do not match the Nine Lights contract")
    if raw.get("rulesVersion") != NINELIGHTS_RULES_VERSION:
        raise ValueError("state rulesVersion is unsupported")
    level_id = raw.get("levelId")
    if not isinstance(level_id, str) or level_id not in LEVELS:
        raise ValueError("state levelId is unsupported")
    cells = raw.get("cells")
    if not isinstance(cells, (list, tuple)) or len(cells) != 9:
        raise ValueError("state cells must contain exactly 9 values")
    if any(isinstance(value, bool) or value not in {0, 1} for value in cells):
        raise ValueError("state cells must contain only integer 0 or 1")
    move_count = raw.get("moveCount")
    if isinstance(move_count, bool) or not isinstance(move_count, int) or move_count < 0:
        raise ValueError("state moveCount must be a non-negative integer")
    status = raw.get("status")
    is_won = all(value == 0 for value in cells)
    if status not in {"playing", "won"} or (status == "won") != is_won:
        raise ValueError("state status does not match its cells")
    return {
        "rulesVersion": NINELIGHTS_RULES_VERSION,
        "levelId": level_id,
        "cells": list(cells),
        "moveCount": move_count,
        "status": status,
    }


def _mcp_tool(capability: Capability) -> dict[str, Any]:
    return {
        "name": capability.id,
        "description": capability.description,
        "inputSchema": deepcopy(dict(capability.input_schema)),
        "outputSchema": deepcopy(dict(capability.output_schema)),
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        "_meta": {
            JCL_META_KEY: {
                "riskLevel": "READ",
                "executionMode": "COMPUTE",
                "reversible": True,
                "stateModel": "STATELESS",
            }
        },
    }

from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys


PROTOTYPE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROTOTYPE_ROOT))

from jidan import (
    Capability,
    CapabilityRegistry,
    Effect,
    Grant,
    JidanRuntime,
    PolicyEngine,
    SqliteGrantLedger,
    Step,
    TaskPlan,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--grant", required=True)
    parser.add_argument("--secret-hex", required=True)
    parser.add_argument("--side-effect", required=True)
    args = parser.parse_args()

    raw = json.loads(Path(args.grant).read_text(encoding="utf-8"))
    grant = Grant(
        task_id=raw["task_id"],
        plan_hash=raw["plan_hash"],
        capabilities=frozenset(raw["capabilities"]),
        scopes=frozenset(raw["scopes"]),
        approved_steps=frozenset(raw["approved_steps"]),
        max_effect=Effect(raw["max_effect"]),
        expires_at=raw["expires_at"],
        nonce=raw["nonce"],
        signature=raw["signature"],
    )
    capability = Capability(
        id="test.process_write",
        app="test",
        description="Append exactly one durable cross-process test marker",
        effect=Effect.WRITE,
        scopes=frozenset({"test.process.write"}),
        requires_confirmation=True,
        reversible=False,
        input_schema={"type": "object", "additionalProperties": False},
        output_schema={
            "type": "object",
            "required": ["ok"],
            "properties": {"ok": {"type": "boolean"}},
            "additionalProperties": False,
        },
    )
    registry = CapabilityRegistry()

    def write_marker(arguments):
        del arguments
        with Path(args.side_effect).open("a", encoding="utf-8", newline="\n") as handle:
            handle.write("invoked\n")
            handle.flush()
        return {"ok": True}

    registry.register(capability, write_marker)
    plan = TaskPlan(
        id="cross.process.runtime",
        goal="Prove persistent replay rejection",
        steps=(Step("write", capability.id, {}),),
    )
    runtime = JidanRuntime(
        registry,
        PolicyEngine(
            bytes.fromhex(args.secret_hex),
            grant_ledger=SqliteGrantLedger.open_existing(args.ledger),
        ),
    )
    result = runtime.execute(plan, grant)
    print(
        json.dumps(
            {
                "status": result.status,
                "reasons": [decision.reason for decision in result.decisions],
                "receipts": len(result.receipts),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

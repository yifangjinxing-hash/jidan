from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
import argparse
import json
import secrets
import time

from jidan import (
    AdbSemanticSurfaceProbe,
    CapabilityRegistry,
    Effect,
    GrantLedgerError,
    JidanRuntime,
    PolicyEngine,
    ReceiptLog,
    SemanticSurfaceProbeError,
    SqliteGrantLedger,
    Step,
    TaskPlan,
    issue_grant,
)
from jidan.console import configure_utf8_stdio


def _emit(summary: Mapping[str, Any], output: str | None) -> None:
    encoded = json.dumps(summary, ensure_ascii=False, indent=2)
    if output is not None:
        destination = Path(output).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory app-authored Android semantic surfaces through Jidan's "
            "read-only capability and receipt pipeline"
        ),
    )
    parser.add_argument("--adb-path", required=True)
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--package", required=True)
    parser.add_argument("--receipt-log", required=True)
    parser.add_argument("--grant-ledger", required=True)
    parser.add_argument("--initialize-grant-ledger", action="store_true")
    parser.add_argument("--summary")
    return parser


def main() -> int:
    configure_utf8_stdio()
    args = _parser().parse_args()
    adb_path = Path(args.adb_path)
    if not adb_path.is_absolute() or not adb_path.is_file():
        raise SystemExit("--adb-path must be an existing absolute file path")

    receipt_path = Path(args.receipt_log).resolve()
    ledger_path = Path(args.grant_ledger).resolve()
    reserved = {
        ledger_path,
        *(Path(str(ledger_path) + suffix) for suffix in ("-wal", "-shm", "-journal")),
    }
    if receipt_path in reserved:
        raise SystemExit("--receipt-log must not overlap the SQLite grant ledger")

    receipts = ReceiptLog(receipt_path)
    if not receipts.verify():
        raise SystemExit("existing receipt log failed hash-chain verification")
    try:
        ledger = (
            SqliteGrantLedger.create_new(ledger_path)
            if args.initialize_grant_ledger
            else SqliteGrantLedger.open_existing(ledger_path)
        )
    except GrantLedgerError as exc:
        raise SystemExit(f"persistent grant ledger is unavailable: {exc}") from exc

    probe = AdbSemanticSurfaceProbe(
        args.package,
        adb_path=str(adb_path),
        serial=args.serial,
    )
    registry = CapabilityRegistry()
    capability = probe.register(registry)
    secret = secrets.token_bytes(32)
    runtime = JidanRuntime(registry, PolicyEngine(secret, grant_ledger=ledger), receipts)
    task_id = f"jidan.semantic-inspect.{int(time.time() * 1000)}.{secrets.token_hex(3)}"
    plan = TaskPlan(
        id=task_id,
        goal=f"Inspect deterministic semantic surfaces exposed by {args.package}",
        steps=(
            Step(
                "inspect_surfaces",
                capability.id,
                {"packageName": args.package},
            ),
        ),
    )
    grant = issue_grant(
        secret,
        plan,
        {capability.id},
        capability.scopes,
        Effect.READ,
        capability_digests=registry.definition_digests({capability.id}),
    )
    try:
        result = runtime.execute(plan, grant)
    except SemanticSurfaceProbeError as exc:
        _emit(
            {
                "ok": False,
                "stage": "semantic_surface_probe",
                "error": str(exc),
            },
            args.summary,
        )
        return 2

    ledger.checkpoint()
    output = result.outputs.get("inspect_surfaces")
    summary = {
        "ok": result.status == "completed" and receipts.verify() and ledger.verify(),
        "executedExternalAction": False,
        "taskId": task_id,
        "execution": result.status,
        "output": output,
        "receiptChainValid": receipts.verify(),
        "receiptHashes": [receipt["hash"] for receipt in result.receipts],
        "receiptLog": str(receipt_path),
        "grantLedger": {
            "path": str(ledger_path),
            "entries": ledger.count(),
            "integrityCheck": "ok" if ledger.verify() else "failed",
        },
    }
    _emit(summary, args.summary)
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

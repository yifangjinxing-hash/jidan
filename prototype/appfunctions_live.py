from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any
import argparse
import json
import secrets
import time

from jidan import (
    CapabilityRegistry,
    Effect,
    GrantLedgerError,
    JidanRuntime,
    PolicyEngine,
    ReceiptLog,
    SqliteGrantLedger,
    Step,
    TaskPlan,
    issue_grant,
)
from jidan.android_appfunctions import AdbAppFunctionsAdapter, AppFunctionsAdapterError
from jidan.console import configure_utf8_stdio


def _substitute_run(value: Any, run_number: int, run_id: str) -> Any:
    if isinstance(value, str):
        return value.replace("${RUN}", str(run_number)).replace("${RUN_ID}", run_id)
    if isinstance(value, Mapping):
        return {key: _substitute_run(child, run_number, run_id) for key, child in value.items()}
    if isinstance(value, list):
        return [_substitute_run(child, run_number, run_id) for child in value]
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a controlled Android AppFunction through Jidan's task-graph gate",
    )
    parser.add_argument("--adb-path", required=True, help="absolute path to the reviewed adb binary")
    parser.add_argument("--serial", required=True, help="exact serial from adb devices -l")
    parser.add_argument("--package", required=True, help="controlled reference-app package")
    parser.add_argument("--function", required=True, help="exact discovered AppFunction ID")
    parser.add_argument("--parameters", required=True, help="JSON object; ${RUN} and ${RUN_ID} are replaced")
    parser.add_argument("--runs", type=int, default=1, help="1-30 fail-fast executions")
    parser.add_argument("--receipt-log", default="jidan-live-receipts.jsonl")
    parser.add_argument(
        "--grant-ledger",
        required=True,
        help="persistent SQLite ledger used to atomically consume grant nonces",
    )
    parser.add_argument(
        "--initialize-grant-ledger",
        action="store_true",
        help="provision a new ledger once; otherwise an existing ledger is required",
    )
    parser.add_argument(
        "--approve",
        action="store_true",
        help="explicitly approve this external test action after preflight",
    )
    return parser


def main() -> int:
    configure_utf8_stdio()
    args = _parser().parse_args()
    adb_path = Path(args.adb_path)
    if not adb_path.is_absolute() or not adb_path.is_file():
        raise SystemExit("--adb-path must be an existing absolute file path")
    if not 1 <= args.runs <= 30:
        raise SystemExit("--runs must be from 1 to 30")
    try:
        parameters = json.loads(args.parameters)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--parameters is invalid JSON: {exc}") from exc
    if not isinstance(parameters, Mapping):
        raise SystemExit("--parameters must decode to a JSON object")

    adapter = AdbAppFunctionsAdapter(
        adb_path=str(adb_path),
        serial=args.serial,
    )
    try:
        probe = adapter.probe()
        discovered = adapter.discover(args.package)
    except AppFunctionsAdapterError as exc:
        print(json.dumps({"ok": False, "kind": exc.kind.value, "message": str(exc)}))
        return 2

    matches = [record for record in discovered if record.function_id == args.function]
    if len(matches) != 1:
        available = sorted(record.function_id for record in discovered)
        print(
            json.dumps(
                {
                    "ok": False,
                    "kind": "function_not_discovered",
                    "requested": args.function,
                    "available": available,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    registry = CapabilityRegistry()
    target = matches[0]
    adapter.register_discovered(registry, records=(target,), package_name=args.package)
    receipt_path = Path(args.receipt_log).resolve()
    ledger_path = Path(args.grant_ledger).resolve()
    ledger_reserved_paths = {
        ledger_path,
        *(Path(str(ledger_path) + suffix) for suffix in ("-wal", "-shm", "-journal")),
    }
    if receipt_path in ledger_reserved_paths:
        raise SystemExit(
            "--receipt-log must not equal the grant ledger or a SQLite sidecar path"
        )
    receipts = ReceiptLog(receipt_path)
    if not receipts.verify():
        raise SystemExit("existing receipt log failed hash-chain verification")
    try:
        grant_ledger = (
            SqliteGrantLedger.create_new(ledger_path)
            if args.initialize_grant_ledger
            else SqliteGrantLedger.open_existing(ledger_path)
        )
    except GrantLedgerError as exc:
        raise SystemExit(f"persistent grant ledger is unavailable: {exc}") from exc
    secret = secrets.token_bytes(32)
    runtime = JidanRuntime(
        registry,
        PolicyEngine(secret, grant_ledger=grant_ledger),
        receipts,
    )

    base_id = f"android-live-{int(time.time())}"
    preflight_plan = TaskPlan(
        id=f"{base_id}-preflight",
        goal=f"Preflight {args.package} {args.function}",
        steps=(Step("call", target.capability.id, dict(parameters)),),
    )
    unapproved = issue_grant(
        secret,
        preflight_plan,
        {target.capability.id},
        target.capability.scopes,
        Effect.EXTERNAL,
    )
    preflight = runtime.execute(preflight_plan, unapproved)
    if preflight.status != "awaiting_confirmation":
        print(json.dumps({"ok": False, "kind": "preflight_failed", "status": preflight.status}))
        return 2
    if not args.approve:
        print(
            json.dumps(
                {
                    "ok": True,
                    "device": probe.to_dict(),
                    "preflight": preflight.status,
                    "executed": 0,
                    "message": "rerun with --approve to execute the exact package/function/parameters",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    runs: list[dict[str, Any]] = []
    for index in range(1, args.runs + 1):
        run_id = f"{base_id}-{index:02d}-{secrets.token_hex(4)}"
        run_parameters = _substitute_run(parameters, index, run_id)
        plan = TaskPlan(
            id=run_id,
            goal=f"Controlled AppFunctions smoke run {index}/{args.runs}",
            steps=(Step("call", target.capability.id, run_parameters),),
        )
        grant = issue_grant(
            secret,
            plan,
            {target.capability.id},
            target.capability.scopes,
            Effect.EXTERNAL,
            approved_steps={"call"},
        )
        result = runtime.execute(plan, grant)
        runs.append(
            {
                "run": index,
                "task_id": run_id,
                "status": result.status,
                "output": result.outputs.get("call"),
                "receipt_hashes": [receipt["hash"] for receipt in result.receipts],
            }
        )
        # Never auto-retry an ambiguous external action.
        if result.status != "completed":
            break

    completed = sum(item["status"] == "completed" for item in runs)
    grant_ledger.checkpoint()
    summary = {
        "ok": completed == args.runs,
        "device": probe.to_dict(),
        "package": args.package,
        "function": args.function,
        "requested_runs": args.runs,
        "completed_runs": completed,
        "receipt_chain_valid": receipts.verify(),
        "receipt_log": str(receipt_path),
        "grant_ledger": {
            "path": str(ledger_path),
            "backend": "sqlite",
            "entries": grant_ledger.count(),
            "integrity_check": "ok" if grant_ledger.verify() else "failed",
        },
        "runs": runs,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["ok"] and summary["receipt_chain_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

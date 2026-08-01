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
    NlpParseError,
    PolicyEngine,
    ReceiptLog,
    SqliteGrantLedger,
    Step,
    TaskPlan,
    issue_grant,
    parse_memo_command,
)
from jidan.android_appfunctions import AdbAppFunctionsAdapter, AppFunctionsAdapterError
from jidan.console import configure_utf8_stdio


PACKAGE = "dev.jidan.reference"
PUT_MEMO_FUNCTION = "dev.jidan.reference.appfunctions.BaseMemoAppFunctionService#putMemo"
GET_MEMO_FUNCTION = "dev.jidan.reference.appfunctions.BaseMemoAppFunctionService#getMemoState"
NLP_MEMO_ID = "jidan.nlp.latest"
RETURN_KEY = "androidAppfunctionsReturnValue"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Parse one memo instruction and execute it through Jidan AppFunctions. "
            "The 'memo:' prefix accepts content in any Unicode language."
        ),
    )
    parser.add_argument("instruction", help="one natural-language instruction")
    parser.add_argument(
        "--locale",
        default="auto",
        help="BCP 47 locale hint; defaults to auto",
    )
    parser.add_argument("--adb-path", required=True)
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--receipt-log", required=True)
    parser.add_argument("--grant-ledger", required=True)
    parser.add_argument("--initialize-grant-ledger", action="store_true")
    parser.add_argument("--summary", help="optional JSON evidence output")
    parser.add_argument(
        "--approve",
        action="store_true",
        help="approve the exact parsed write after the side-effect-free preflight",
    )
    return parser


def _provider_state(output: Mapping[str, Any]) -> dict[str, Any]:
    values = output.get(RETURN_KEY)
    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], str):
        raise ValueError("AppFunctions response did not contain one string return value")
    state = json.loads(values[0])
    if not isinstance(state, dict):
        raise ValueError("putMemo return value was not a JSON object")
    return state


def _emit(summary: Mapping[str, Any], path: str | None) -> None:
    encoded = json.dumps(summary, ensure_ascii=False, indent=2)
    if path is not None:
        destination = Path(path).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


def main() -> int:
    configure_utf8_stdio()
    args = _parser().parse_args()
    try:
        semantic = parse_memo_command(args.instruction, locale_hint=args.locale)
    except NlpParseError as exc:
        _emit({"ok": False, "stage": "semantic_parse", "error": str(exc)}, args.summary)
        return 2

    adb_path = Path(args.adb_path)
    if not adb_path.is_absolute() or not adb_path.is_file():
        raise SystemExit("--adb-path must be an existing absolute file path")

    adapter = AdbAppFunctionsAdapter(adb_path=str(adb_path), serial=args.serial)
    try:
        probe = adapter.probe()
        records = adapter.discover(PACKAGE)
    except AppFunctionsAdapterError as exc:
        _emit(
            {"ok": False, "stage": "appfunctions_discovery", "error": str(exc)},
            args.summary,
        )
        return 2

    matches = [record for record in records if record.function_id == PUT_MEMO_FUNCTION]
    read_matches = [record for record in records if record.function_id == GET_MEMO_FUNCTION]
    if len(matches) != 1 or len(read_matches) != 1:
        _emit(
            {
                "ok": False,
                "stage": "capability_resolution",
                "requested": PUT_MEMO_FUNCTION,
                "available": sorted(record.function_id for record in records),
            },
            args.summary,
        )
        return 2

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

    target = matches[0]
    registry = CapabilityRegistry()
    adapter.register_discovered(registry, records=(target,), package_name=PACKAGE)
    secret = secrets.token_bytes(32)
    runtime = JidanRuntime(registry, PolicyEngine(secret, grant_ledger=ledger), receipts)

    timestamp = int(time.time() * 1000)
    operation_id = f"jidan.nlp.{timestamp}.{secrets.token_hex(4)}"
    task_id = f"jidan.nlp.{timestamp}.{secrets.token_hex(3)}"
    parameters = {
        "operationId": operation_id,
        "memoId": NLP_MEMO_ID,
        "content": semantic.content,
    }
    plan = TaskPlan(
        id=task_id,
        goal=args.instruction,
        steps=(Step("write_memo", target.capability.id, parameters),),
    )
    grant_scope = set(target.capability.scopes)
    grant_capabilities = {target.capability.id}
    preview_grant = issue_grant(
        secret,
        plan,
        grant_capabilities,
        grant_scope,
        Effect.EXTERNAL,
    )
    preflight = runtime.execute(plan, preview_grant)
    if preflight.status != "awaiting_confirmation":
        _emit(
            {
                "ok": False,
                "stage": "preflight",
                "status": preflight.status,
                "semantic": semantic.to_dict(),
            },
            args.summary,
        )
        return 2

    if not args.approve:
        _emit(
            {
                "ok": True,
                "executed": False,
                "preflight": preflight.status,
                "semantic": semantic.to_dict(),
                "parameters": parameters,
            },
            args.summary,
        )
        return 0

    grant = issue_grant(
        secret,
        plan,
        grant_capabilities,
        grant_scope,
        Effect.EXTERNAL,
        approved_steps={"write_memo"},
    )
    result = runtime.execute(plan, grant)
    state: dict[str, Any] | None = None
    readback_state: dict[str, Any] | None = None
    error: str | None = None
    if result.status == "completed":
        try:
            state = _provider_state(result.outputs["write_memo"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            error = str(exc)

    if state is not None:
        try:
            readback_output = adapter.execute(PACKAGE, GET_MEMO_FUNCTION, {"memoId": NLP_MEMO_ID})
            if not isinstance(readback_output, Mapping):
                raise ValueError("getMemoState response was not an object")
            readback_state = _provider_state(readback_output)
        except (AppFunctionsAdapterError, TypeError, ValueError, json.JSONDecodeError) as exc:
            error = str(exc)

    verified = bool(
        state is not None
        and state.get("status") == "applied"
        and state.get("memoId") == NLP_MEMO_ID
        and state.get("operationId") == operation_id
        and state.get("content") == semantic.content
        and readback_state is not None
        and readback_state.get("status") == "present"
        and readback_state.get("memoId") == NLP_MEMO_ID
        and readback_state.get("operationId") == operation_id
        and readback_state.get("content") == semantic.content
    )
    ledger.checkpoint()
    summary = {
        "ok": result.status == "completed" and verified and receipts.verify() and ledger.verify(),
        "input": args.instruction,
        "semantic": semantic.to_dict(),
        "task_graph": {
            "task_id": task_id,
            "goal": plan.goal,
            "steps": [
                {
                    "id": "write_memo",
                    "capability": target.capability.id,
                    "provider_function": PUT_MEMO_FUNCTION,
                    "parameters": parameters,
                }
            ],
        },
        "device": probe.to_dict(),
        "preflight": preflight.status,
        "execution": result.status,
        "content_verified": verified,
        "provider_state": state,
        "readback_state": readback_state,
        "provider_error": error,
        "receipt_chain_valid": receipts.verify(),
        "receipt_log": str(receipt_path),
        "receipt_hashes": [receipt["hash"] for receipt in result.receipts],
        "grant_ledger": {
            "path": str(ledger_path),
            "entries": ledger.count(),
            "integrity_check": "ok" if ledger.verify() else "failed",
        },
    }
    _emit(summary, args.summary)
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

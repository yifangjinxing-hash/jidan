from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
import argparse
import base64
import binascii
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
from jidan.android_alarm import AdbAlarmClockAdapter, AlarmClockAdapterError
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
        description="Set a Google Clock alarm through Jidan's capability and policy gate",
    )
    parser.add_argument("--adb-path", required=True)
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--hour", type=int, required=True)
    parser.add_argument("--minutes", type=int, required=True)
    message_group = parser.add_mutually_exclusive_group(required=True)
    message_group.add_argument("--message")
    message_group.add_argument(
        "--message-utf8-base64",
        metavar="BASE64",
        help="ASCII-safe transport for a UTF-8 label when the host shell corrupts Unicode",
    )
    parser.add_argument("--show-ui", action="store_true")
    parser.add_argument("--receipt-log", required=True)
    parser.add_argument("--grant-ledger", required=True)
    parser.add_argument("--initialize-grant-ledger", action="store_true")
    parser.add_argument("--summary")
    parser.add_argument("--approve", action="store_true")
    return parser


def _decode_message(message: str | None, encoded: str | None) -> str:
    if message is not None:
        return message
    if encoded is None:
        raise ValueError("one message representation is required")
    try:
        raw = base64.b64decode(encoded, validate=True)
        decoded = raw.decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("--message-utf8-base64 must contain valid base64-encoded UTF-8") from exc
    if base64.b64encode(raw).decode("ascii") != encoded:
        raise ValueError("--message-utf8-base64 must use canonical padded base64")
    return decoded


def main() -> int:
    configure_utf8_stdio()
    args = _parser().parse_args()
    try:
        message = _decode_message(args.message, args.message_utf8_base64)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
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

    adapter = AdbAlarmClockAdapter(adb_path=str(adb_path), serial=args.serial)
    try:
        handler = adapter.probe_handler()
    except AlarmClockAdapterError as exc:
        _emit({"ok": False, "stage": "handler_probe", "error": str(exc)}, args.summary)
        return 2

    registry = CapabilityRegistry()
    capability = adapter.register(registry)
    secret = secrets.token_bytes(32)
    runtime = JidanRuntime(registry, PolicyEngine(secret, grant_ledger=ledger), receipts)
    parameters = {
        "hour": args.hour,
        "minutes": args.minutes,
        "message": message,
        "skipUi": not args.show_ui,
    }
    message_transport = (
        "utf8-base64" if args.message_utf8_base64 is not None else "plain"
    )
    task_id = f"jidan.alarm.{int(time.time() * 1000)}.{secrets.token_hex(3)}"
    plan = TaskPlan(
        id=task_id,
        goal=f"Set a real Google Clock alarm for {args.hour:02d}:{args.minutes:02d}",
        steps=(Step("set_alarm", capability.id, parameters),),
    )
    preview = issue_grant(
        secret,
        plan,
        {capability.id},
        capability.scopes,
        Effect.EXTERNAL,
    )
    preflight = runtime.execute(plan, preview)
    if preflight.status != "awaiting_confirmation":
        _emit(
            {"ok": False, "stage": "preflight", "status": preflight.status},
            args.summary,
        )
        return 2
    if not args.approve:
        _emit(
            {
                "ok": True,
                "executed": False,
                "preflight": preflight.status,
                "handler": handler,
                "parameters": parameters,
                "message_transport": message_transport,
            },
            args.summary,
        )
        return 0

    grant = issue_grant(
        secret,
        plan,
        {capability.id},
        capability.scopes,
        Effect.EXTERNAL,
        approved_steps={"set_alarm"},
    )
    result = runtime.execute(plan, grant)
    ledger.checkpoint()
    summary = {
        "ok": result.status == "completed" and receipts.verify() and ledger.verify(),
        "transport": "android.intent.action.SET_ALARM",
        "note": "Google Clock exposes no AppFunction on this image; this is the public Intent fallback.",
        "task_id": task_id,
        "handler": handler,
        "preflight": preflight.status,
        "execution": result.status,
        "parameters": parameters,
        "message_transport": message_transport,
        "output": result.outputs.get("set_alarm"),
        "receipt_chain_valid": receipts.verify(),
        "receipt_hashes": [receipt["hash"] for receipt in result.receipts],
        "receipt_log": str(receipt_path),
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

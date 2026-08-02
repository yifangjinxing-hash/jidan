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
    AdbWeChatShareAdapter,
    CapabilityRegistry,
    Effect,
    GrantLedgerError,
    JidanRuntime,
    PolicyEngine,
    ReceiptLog,
    SqliteGrantLedger,
    Step,
    TaskPlan,
    WeChatShareAdapterError,
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


def _decode_text(plain: str | None, encoded: str | None) -> str:
    if plain is not None:
        return plain
    if encoded is None:
        raise ValueError("one text representation is required")
    try:
        raw = base64.b64decode(encoded, validate=True)
        decoded = raw.decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("--text-utf8-base64 must encode valid UTF-8") from exc
    if base64.b64encode(raw).decode("ascii") != encoded:
        raise ValueError("--text-utf8-base64 must use canonical padded base64")
    return decoded


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Open WeChat's own recipient picker through Jidan's confirmed "
            "text-share handoff capability"
        ),
    )
    parser.add_argument("--adb-path", required=True)
    parser.add_argument("--serial", default="emulator-5554")
    text_group = parser.add_mutually_exclusive_group(required=True)
    text_group.add_argument("--text")
    text_group.add_argument(
        "--text-utf8-base64",
        metavar="BASE64",
        help="ASCII-safe transport for UTF-8 text",
    )
    parser.add_argument("--receipt-log", required=True)
    parser.add_argument("--grant-ledger", required=True)
    parser.add_argument("--initialize-grant-ledger", action="store_true")
    parser.add_argument("--summary")
    parser.add_argument("--approve", action="store_true")
    return parser


def main() -> int:
    configure_utf8_stdio()
    args = _parser().parse_args()
    try:
        text = _decode_text(args.text, args.text_utf8_base64)
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

    adapter = AdbWeChatShareAdapter(adb_path=str(adb_path), serial=args.serial)
    registry = CapabilityRegistry()
    capability = adapter.register(registry)
    secret = secrets.token_bytes(32)
    runtime = JidanRuntime(registry, PolicyEngine(secret, grant_ledger=ledger), receipts)
    task_id = f"jidan.wechat-share.{int(time.time() * 1000)}.{secrets.token_hex(3)}"
    plan = TaskPlan(
        id=task_id,
        goal="Hand text to WeChat and open WeChat's own recipient picker",
        steps=(Step("open_wechat_handoff", capability.id, {"text": text}),),
    )
    preview_grant = issue_grant(
        secret,
        plan,
        {capability.id},
        capability.scopes,
        Effect.WRITE,
        capability_digests=registry.definition_digests({capability.id}),
    )
    preflight = runtime.execute(plan, preview_grant)
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
                "transport": "android.intent.action.SEND",
                "jidanSelectedRecipient": False,
                "jidanIssuedSend": False,
            },
            args.summary,
        )
        return 0

    grant = issue_grant(
        secret,
        plan,
        {capability.id},
        capability.scopes,
        Effect.WRITE,
        approved_steps={"open_wechat_handoff"},
        capability_digests=registry.definition_digests({capability.id}),
    )
    try:
        result = runtime.execute(plan, grant)
    except WeChatShareAdapterError as exc:
        _emit(
            {"ok": False, "stage": "wechat_share_handoff", "error": str(exc)},
            args.summary,
        )
        return 2

    ledger.checkpoint()
    output = result.outputs.get("open_wechat_handoff")
    summary = {
        "ok": result.status == "completed" and receipts.verify() and ledger.verify(),
        "taskId": task_id,
        "execution": result.status,
        "preflight": preflight.status,
        "transport": "android.intent.action.SEND",
        "openedRecipientPicker": (
            isinstance(output, Mapping) and output.get("status") == "handoff_opened"
        ),
        "jidanSelectedRecipient": False,
        "jidanIssuedSend": False,
        "deliveryState": "not_attempted_by_jidan",
        "nextAction": "Choose the recipient in WeChat and confirm Send yourself.",
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

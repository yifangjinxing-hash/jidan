"""Run the pinned Alipay front-door handoff through Jidan's full authority path.

This is a controlled Android/ADB lab harness, not an ordinary-user payment app.
It opens only a host-pinned launcher surface and never accepts payment data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
import argparse
import json
import os
import secrets
import time

from jidan import (
    ALIPAY_HANDOFF_CAPABILITY_ID,
    ALIPAY_PACKAGE,
    AdbAlipayHandoffAdapter,
    CapabilityRegistry,
    Effect,
    FixedAndroidFrontDoor,
    GrantLedgerError,
    JidanRuntime,
    PolicyEngine,
    ReceiptLog,
    SqliteGrantLedger,
    Step,
    TaskPlan,
    issue_grant,
)
from jidan.android_appfunctions import CommandRunner
from jidan.console import configure_utf8_stdio


def _emit(summary: Mapping[str, Any], output: Path | None) -> None:
    encoded = json.dumps(summary, ensure_ascii=False, indent=2)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


def _existing_absolute_file(
    value: str,
    *,
    option: str,
    windows_executable: bool = False,
    required_suffix: str | None = None,
) -> Path:
    path = Path(value)
    if not path.is_absolute() or not path.is_file():
        raise SystemExit(f"{option} must be an existing absolute file path")
    path = path.resolve()
    if windows_executable and os.name == "nt" and path.suffix.lower() != ".exe":
        raise SystemExit(f"{option} must name a .exe file on Windows")
    if required_suffix is not None and path.suffix.lower() != required_suffix:
        raise SystemExit(f"{option} must name a {required_suffix} file")
    return path


def _same_target(left: Path, right: Path) -> bool:
    if left == right:
        return True
    try:
        return left.exists() and right.exists() and left.samefile(right)
    except OSError:
        return False


def _assert_distinct_targets(named_paths: Mapping[str, Path]) -> None:
    entries = list(named_paths.items())
    for index, (left_name, left_path) in enumerate(entries):
        for right_name, right_path in entries[index + 1 :]:
            if _same_target(left_path, right_path):
                raise SystemExit(
                    f"{left_name} must not overlap {right_name}"
                )


def _prepare_summary_output(path: Path) -> None:
    """Prove the optional local summary is writable before any handoff."""

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        os.close(descriptor)
    except OSError as exc:
        raise SystemExit("--summary must be a writable file path") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Open a host-pinned Alipay launcher surface through Jidan. "
            "No recipient, amount, QR, order, or payment data is accepted."
        )
    )
    parser.add_argument("--adb-path", required=True)
    parser.add_argument("--java-path", required=True)
    parser.add_argument("--apksigner-jar", required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--version-code", required=True, type=int)
    parser.add_argument("--certificate-sha256", required=True)
    parser.add_argument(
        "--launcher-component",
        action="append",
        required=True,
        help="host-reviewed exact component; repeat only for an intentional allowlist",
    )
    parser.add_argument(
        "--foreground-component",
        action="append",
        required=True,
        help="host-reviewed exact foreground component; may be repeated",
    )
    parser.add_argument("--receipt-log", required=True)
    parser.add_argument("--grant-ledger", required=True)
    parser.add_argument("--initialize-grant-ledger", action="store_true")
    parser.add_argument("--summary")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate the pinned navigation policy without opening Alipay",
    )
    return parser


def main(*, runner: CommandRunner | None = None) -> int:
    configure_utf8_stdio()
    args = _parser().parse_args()
    adb_path = _existing_absolute_file(
        args.adb_path,
        option="--adb-path",
        windows_executable=True,
    )
    java_path = _existing_absolute_file(
        args.java_path,
        option="--java-path",
        windows_executable=True,
    )
    apksigner_jar_path = _existing_absolute_file(
        args.apksigner_jar,
        option="--apksigner-jar",
        required_suffix=".jar",
    )

    try:
        front_door = FixedAndroidFrontDoor(
            package_name=ALIPAY_PACKAGE,
            version_code=args.version_code,
            certificate_sha256=args.certificate_sha256,
            launcher_components=frozenset(args.launcher_component),
            foreground_components=frozenset(args.foreground_component),
        )
    except ValueError as exc:
        raise SystemExit(f"invalid trusted Alipay front-door policy: {exc}") from exc

    receipt_path = Path(args.receipt_log).resolve()
    receipt_lock_path = Path(str(receipt_path) + ".lock").resolve()
    ledger_path = Path(args.grant_ledger).resolve()
    ledger_sidecars = {
        suffix: Path(str(ledger_path) + suffix).resolve()
        for suffix in ("-wal", "-shm", "-journal")
    }
    summary_path = Path(args.summary).resolve() if args.summary is not None else None
    protected_paths = {
        "--receipt-log": receipt_path,
        "receipt lock": receipt_lock_path,
        "--grant-ledger": ledger_path,
        **{
            f"grant ledger {suffix} sidecar": path
            for suffix, path in ledger_sidecars.items()
        },
        "--adb-path": adb_path,
        "--java-path": java_path,
        "--apksigner-jar": apksigner_jar_path,
    }
    if summary_path is not None:
        protected_paths["--summary"] = summary_path
    _assert_distinct_targets(protected_paths)
    if summary_path is not None:
        _prepare_summary_output(summary_path)

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

    adapter = AdbAlipayHandoffAdapter(
        front_door,
        runner,
        adb_path=str(adb_path),
        java_path=str(java_path),
        apksigner_jar_path=str(apksigner_jar_path),
        serial=args.serial,
    )
    registry = CapabilityRegistry()
    capability = adapter.register(registry)
    secret = secrets.token_bytes(32)
    runtime = JidanRuntime(registry, PolicyEngine(secret, grant_ledger=ledger), receipts)
    task_id = f"jidan.alipay-handoff.{int(time.time() * 1000)}.{secrets.token_hex(3)}"
    plan = TaskPlan(
        id=task_id,
        goal="Open only the host-pinned Alipay front door and return control to the user",
        steps=(
            Step(
                id="open_alipay_handoff",
                capability=ALIPAY_HANDOFF_CAPABILITY_ID,
                arguments={},
            ),
        ),
    )
    digests = registry.definition_digests({capability.id})
    grant = issue_grant(
        secret,
        plan,
        {capability.id},
        capability.scopes,
        Effect.NAVIGATION,
        capability_digests=digests,
    )
    preflight = runtime.preflight(plan, grant)
    if any(decision.outcome != "allowed" for decision in preflight):
        _emit(
            {
                "ok": False,
                "executed": False,
                "stage": "preflight",
                "status": [decision.outcome for decision in preflight],
            },
            summary_path,
        )
        return 2

    zero_payment = {
        "amountSetByJidan": False,
        "recipientSelectedByJidan": False,
        "paymentAttemptedByJidan": False,
        "paid": False,
        "committed": False,
        "verified": False,
    }
    if args.dry_run:
        _emit(
            {
                "ok": True,
                "executed": False,
                "preflight": "ready",
                "capability": capability.id,
                "effect": capability.effect.label(),
                "targetPackage": ALIPAY_PACKAGE,
                "payment": zero_payment,
                "notice": (
                    "Dry run only. Remove --dry-run to issue the explicit "
                    "low-risk navigation command."
                ),
            },
            summary_path,
        )
        return 0

    result = runtime.execute(plan, grant)
    ledger.checkpoint()
    output = result.outputs.get("open_alipay_handoff")
    output_is_safe = (
        isinstance(output, Mapping)
        and output.get("status") == "handoff_opened"
        and output.get("hostPinsMatched") is True
        and output.get("bindingAuthority") == "os_frontdoor"
        and output.get("guaranteeLevel") == "adb_verified_foreground"
        and output.get("amountSetByJidan") is False
        and output.get("recipientSelectedByJidan") is False
        and output.get("paymentAttemptedByJidan") is False
        and output.get("paid") is False
        and output.get("committed") is False
        and output.get("verified") is False
    )
    receipt_chain_valid = receipts.verify()
    ledger_valid = ledger.verify()
    ok = (
        result.status == "completed"
        and output_is_safe
        and receipt_chain_valid
        and ledger_valid
    )
    summary = {
        "ok": ok,
        "taskId": task_id,
        "execution": result.status,
        "preflight": "ready",
        "handoffOpened": output_is_safe,
        "payment": zero_payment,
        "nextAction": (
            "Choose the recipient, verify the real name, enter the amount, "
            "and confirm entirely inside Alipay. Jidan cannot verify payment."
        ),
        "evidence": {
            "status": output.get("status") if isinstance(output, Mapping) else None,
            "hostPinsMatched": (
                output.get("hostPinsMatched") if isinstance(output, Mapping) else False
            ),
            "bindingAuthority": (
                output.get("bindingAuthority") if isinstance(output, Mapping) else None
            ),
            "guaranteeLevel": (
                output.get("guaranteeLevel") if isinstance(output, Mapping) else None
            ),
        },
        "receiptChainValid": receipt_chain_valid,
        "receiptHashes": [receipt["hash"] for receipt in result.receipts],
        "grantLedger": {
            "entries": ledger.count(),
            "integrityCheck": "ok" if ledger_valid else "failed",
        },
        "automaticRetry": False,
    }
    _emit(summary, summary_path)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

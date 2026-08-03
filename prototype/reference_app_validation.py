from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence
import argparse
import gc
import hashlib
import json
import re
import secrets
import subprocess
import time
import weakref

from jidan import (
    CapabilityRegistry,
    Effect,
    JidanRuntime,
    PolicyEngine,
    ReceiptLog,
    SqliteGrantLedger,
    Step,
    TaskPlan,
    issue_grant,
)
from jidan.android_appfunctions import (
    AdbAppFunctionsAdapter,
    AppFunctionCapabilityRecord,
    AppFunctionsAdapterError,
)
from jidan.console import configure_utf8_stdio


PACKAGE = "dev.jidan.reference"
BASE_FUNCTION = "dev.jidan.reference.appfunctions.BaseMemoAppFunctionService"
PUT_FUNCTION = f"{BASE_FUNCTION}#putMemo"
GET_FUNCTION = f"{BASE_FUNCTION}#getMemoState"
STATS_FUNCTION = f"{BASE_FUNCTION}#getStoreStats"
RETURN_KEY = "androidAppfunctionsReturnValue"
ZERO_HASH = "0" * 64
CERTIFICATE_PATTERN = re.compile(
    r"(?:^|\n)(?:[A-Za-z0-9.]+\s+)?Signer(?:\s+#\d+)?: certificate SHA-256 digest:\s*"
    r"([0-9a-fA-F]{64})(?:\r?$)",
    re.MULTILINE,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate 30 real idempotent read/write rounds against Jidan Reference Memo",
    )
    parser.add_argument("--adb-path", required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--apk", required=True)
    parser.add_argument("--java-path", required=True)
    parser.add_argument("--apksigner-jar", required=True)
    parser.add_argument("--receipt-log", required=True)
    parser.add_argument("--event-log", required=True)
    parser.add_argument("--grant-ledger", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--rounds", type=int, default=30)
    parser.add_argument("--suite-id", default=f"jidan-{int(time.time())}")
    parser.add_argument(
        "--reset-package-data",
        action="store_true",
        help="clear only dev.jidan.reference after APK identity verification",
    )
    parser.add_argument(
        "--approve",
        action="store_true",
        help="approve the exact write steps after every zero-execution preflight",
    )
    return parser


def _checked_process(argv: Sequence[str], *, timeout: float = 60.0) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(argv),
        shell=False,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if completed.returncode != 0:
        diagnostic = " ".join((completed.stderr + "\n" + completed.stdout).split())
        raise RuntimeError(f"command failed ({completed.returncode}): {diagnostic[:600]}")
    return completed


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _certificate_digest(java_path: Path, apksigner_jar: Path, apk_path: Path) -> str:
    result = _checked_process(
        (str(java_path), "-jar", str(apksigner_jar), "verify", "--print-certs", str(apk_path)),
    )
    match = CERTIFICATE_PATTERN.search(result.stdout + "\n" + result.stderr)
    if match is None:
        raise RuntimeError("apksigner did not report a signer SHA-256 certificate digest")
    return match.group(1).lower()


def _verify_installed_apk(
    *,
    adb_path: Path,
    serial: str,
    apk_path: Path,
    java_path: Path,
    apksigner_jar: Path,
) -> dict[str, str]:
    local_sha256 = _sha256_file(apk_path)
    local_certificate = _certificate_digest(java_path, apksigner_jar, apk_path)
    path_result = _checked_process(
        (str(adb_path), "-s", serial, "shell", "pm", "path", PACKAGE),
    )
    candidates = [
        line.removeprefix("package:").strip()
        for line in path_result.stdout.splitlines()
        if line.startswith("package:")
    ]
    if len(candidates) != 1 or not candidates[0].endswith("/base.apk"):
        raise RuntimeError(f"expected one installed base APK for {PACKAGE}, got {candidates!r}")

    with TemporaryDirectory(prefix="jidan-installed-apk-") as temporary:
        pulled_apk = Path(temporary) / "installed-base.apk"
        _checked_process(
            (str(adb_path), "-s", serial, "pull", candidates[0], str(pulled_apk)),
            timeout=120.0,
        )
        installed_sha256 = _sha256_file(pulled_apk)
        installed_certificate = _certificate_digest(java_path, apksigner_jar, pulled_apk)

    if local_sha256 != installed_sha256:
        raise RuntimeError("installed base APK bytes do not match the reviewed local APK")
    if local_certificate != installed_certificate:
        raise RuntimeError("installed APK signer does not match the reviewed local APK signer")
    return {
        "local_apk_sha256": local_sha256,
        "installed_apk_sha256": installed_sha256,
        "signer_certificate_sha256": local_certificate,
        "installed_base_path": candidates[0],
    }


def _extract_return_string(output: Mapping[str, Any]) -> str:
    value: Any = output.get(RETURN_KEY)
    while isinstance(value, list) and len(value) == 1:
        value = value[0]
    if not isinstance(value, str):
        raise AssertionError(f"expected one string in {RETURN_KEY}, got {value!r}")
    return value


def _extract_state(output: Mapping[str, Any]) -> dict[str, Any]:
    decoded = json.loads(_extract_return_string(output))
    if not isinstance(decoded, dict):
        raise AssertionError("reference provider returned non-object JSON state")
    return decoded


def _content_for_round(suite_id: str, round_number: int) -> str:
    content = (
        f"Jidan round {round_number:02d}/30 | suite={suite_id} | 中文备忘 ✅ | "
        '"double" | \'single\'\n$() ; & | < > \\ backslash'
    )
    if round_number == 17:
        content += "\nLARGE-PAYLOAD:" + ("测Z" * 1800)
    return content


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _assert_state(
    state: Mapping[str, Any],
    *,
    status: str,
    operation_id: str,
    memo_id: str,
    content: str,
    revision: int,
    physical_mutations: int,
    put_invocations: int,
) -> None:
    expected = {
        "status": status,
        "operationId": operation_id,
        "memoId": memo_id,
        "content": content,
        "revision": revision,
        "physicalMutationCount": physical_mutations,
        "putInvocationCount": put_invocations,
        "memoCount": 1,
    }
    for key, value in expected.items():
        _require(state.get(key) == value, f"{key}: expected {value!r}, got {state.get(key)!r}")


def _trusted_record(
    record: AppFunctionCapabilityRecord,
    *,
    effect: Effect,
    signer_digest: str,
) -> AppFunctionCapabilityRecord:
    signer_scope = f"android.signer.sha256.{signer_digest}"
    capability = replace(
        record.capability,
        effect=effect,
        requires_confirmation=effect.at_least(Effect.WRITE),
        reversible=not effect.at_least(Effect.WRITE),
        scopes=frozenset((*record.capability.scopes, signer_scope)),
    )
    return replace(record, capability=capability)


def _find_one(
    records: Sequence[AppFunctionCapabilityRecord],
    function_id: str,
) -> AppFunctionCapabilityRecord:
    matches = [record for record in records if record.function_id == function_id]
    if len(matches) != 1:
        raise AssertionError(
            f"expected exactly one {function_id}, discovered {[item.function_id for item in records]!r}"
        )
    return matches[0]


def _tamper_is_detected(receipt_path: Path) -> bool:
    with TemporaryDirectory(prefix="jidan-tamper-") as temporary:
        tampered = Path(temporary) / "tampered.jsonl"
        lines = receipt_path.read_text(encoding="utf-8").splitlines()
        if not lines:
            raise AssertionError("receipt log is empty")
        first = json.loads(lines[0])
        first["status"] = "tampered"
        lines[0] = json.dumps(first, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        tampered.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return not ReceiptLog(tampered).verify()


def _append_event(
    events: list[dict[str, Any]],
    kind: str,
    details: Mapping[str, Any],
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "sequence": len(events) + 1,
        "kind": kind,
        "details": dict(details),
        "previous_hash": events[-1]["hash"] if events else ZERO_HASH,
    }
    canonical = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    event["hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    events.append(event)
    return event


def _verify_event_chain(events: Sequence[Mapping[str, Any]]) -> bool:
    previous_hash = ZERO_HASH
    for expected_sequence, source in enumerate(events, start=1):
        event = dict(source)
        recorded_hash = event.pop("hash", None)
        if event.get("sequence") != expected_sequence or event.get("previous_hash") != previous_hash:
            return False
        canonical = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        expected_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if recorded_hash != expected_hash:
            return False
        previous_hash = expected_hash
    return bool(events)


def _write_event_log(path: Path, events: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


def _read_event_log(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        decoded = json.loads(line)
        if not isinstance(decoded, dict):
            raise AssertionError("test event log contains a non-object entry")
        events.append(decoded)
    return events


def main(argv: Sequence[str] | None = None) -> int:
    configure_utf8_stdio()
    args = _parser().parse_args(argv)
    started = time.monotonic()
    adb_path = Path(args.adb_path).resolve()
    apk_path = Path(args.apk).resolve()
    java_path = Path(args.java_path).resolve()
    apksigner_jar = Path(args.apksigner_jar).resolve()
    receipt_path = Path(args.receipt_log).resolve()
    event_path = Path(args.event_log).resolve()
    ledger_path = Path(args.grant_ledger).resolve()
    summary_path = Path(args.summary).resolve()

    try:
        output_paths = {
            "receipt log": receipt_path,
            "test event log": event_path,
            "grant ledger": ledger_path,
            "summary": summary_path,
        }
        _require(
            len(set(output_paths.values())) == len(output_paths),
            "receipt, event, ledger, and summary paths must be pairwise distinct",
        )
        ledger_sidecars = {
            Path(str(ledger_path) + suffix)
            for suffix in ("-wal", "-shm", "-journal")
        }
        for label, path in output_paths.items():
            if label != "grant ledger":
                _require(
                    path not in ledger_sidecars,
                    f"{label} must not use a SQLite grant-ledger sidecar path",
                )
        _require(
            not any(path.exists() for path in ledger_sidecars),
            "a stale SQLite grant-ledger sidecar already exists",
        )
        for label, path in (
            ("adb", adb_path),
            ("APK", apk_path),
            ("java", java_path),
            ("apksigner jar", apksigner_jar),
        ):
            _require(path.is_file(), f"{label} path is not a file: {path}")
        _require(1 <= args.rounds <= 100, "rounds must be from 1 to 100")
        _require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", args.suite_id) is not None, "invalid suite-id")
        _require(not receipt_path.exists(), f"receipt log already exists: {receipt_path}")
        _require(not event_path.exists(), f"event log already exists: {event_path}")
        _require(not ledger_path.exists(), f"grant ledger already exists: {ledger_path}")
        _require(not summary_path.exists(), f"summary already exists: {summary_path}")

        identity = _verify_installed_apk(
            adb_path=adb_path,
            serial=args.serial,
            apk_path=apk_path,
            java_path=java_path,
            apksigner_jar=apksigner_jar,
        )
        if args.reset_package_data:
            cleared = _checked_process(
                (str(adb_path), "-s", args.serial, "shell", "pm", "clear", PACKAGE),
            )
            _require(cleared.stdout.strip() == "Success", "controlled package data clear failed")

        adapter = AdbAppFunctionsAdapter(adb_path=str(adb_path), serial=args.serial)
        probe = adapter.probe()
        discovered = adapter.discover(PACKAGE)
        put_record = _trusted_record(
            _find_one(discovered, PUT_FUNCTION),
            effect=Effect.WRITE,
            signer_digest=identity["signer_certificate_sha256"],
        )
        get_record = _trusted_record(
            _find_one(discovered, GET_FUNCTION),
            effect=Effect.READ,
            signer_digest=identity["signer_certificate_sha256"],
        )
        stats_record = _trusted_record(
            _find_one(discovered, STATS_FUNCTION),
            effect=Effect.READ,
            signer_digest=identity["signer_certificate_sha256"],
        )

        registry = CapabilityRegistry()
        adapter.register_discovered(
            registry,
            records=(put_record, get_record, stats_record),
            package_name=PACKAGE,
        )
        receipt_log = ReceiptLog(receipt_path)
        secret = secrets.token_bytes(32)
        grant_ledger = SqliteGrantLedger.create_new(ledger_path)
        runtime = JidanRuntime(
            registry,
            PolicyEngine(secret, grant_ledger=grant_ledger),
            receipt_log,
        )
        capabilities = {put_record.capability.id, get_record.capability.id}
        scopes = put_record.capability.scopes | get_record.capability.scopes

        baseline = _extract_state(adapter.execute(PACKAGE, STATS_FUNCTION, {}))
        _require(
            baseline == {"physicalMutationCount": 0, "putInvocationCount": 0, "memoCount": 0},
            f"expected a clean controlled store, got {baseline!r}",
        )
        _require(args.approve, "--approve is required after reviewing this exact controlled suite")

        memo_id = f"{args.suite_id}-memo"
        rounds: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        preflight_blocks = 0
        kernel_replay_rejections = 0
        provider_replays = 0
        persistent_runtime_recreation_replay_rejected = False

        for round_number in range(1, args.rounds + 1):
            operation_id = f"{args.suite_id}-round-{round_number:02d}"
            content = _content_for_round(args.suite_id, round_number)
            put_arguments = {
                "operationId": operation_id,
                "memoId": memo_id,
                "content": content,
            }
            read_arguments = {"memoId": memo_id}
            primary = TaskPlan(
                id=f"{args.suite_id}-r{round_number:02d}-primary",
                goal=f"Physically persist and verify controlled memo round {round_number}",
                steps=(
                    Step("put", put_record.capability.id, put_arguments),
                    Step("read", get_record.capability.id, read_arguments),
                ),
            )
            receipt_count_before = len(receipt_log.all())
            unapproved = issue_grant(
                secret,
                primary,
                capabilities,
                scopes,
                Effect.WRITE,
                capability_digests=registry.definition_digests(capabilities),
            )
            preflight = runtime.execute(primary, unapproved)
            _require(preflight.status == "awaiting_confirmation", "write preflight did not stop")
            _require(not preflight.receipts, "preflight emitted receipts")
            _require(len(receipt_log.all()) == receipt_count_before, "preflight changed receipt log")
            preflight_stats = _extract_state(adapter.execute(PACKAGE, STATS_FUNCTION, {}))
            expected_preflight_stats = {
                "physicalMutationCount": round_number - 1,
                "putInvocationCount": 2 * (round_number - 1),
                "memoCount": 0 if round_number == 1 else 1,
            }
            _require(
                preflight_stats == expected_preflight_stats,
                f"preflight reached provider in round {round_number}: {preflight_stats!r}",
            )
            preflight_ledger_count = grant_ledger.count()
            _require(
                preflight_ledger_count == 2 * (round_number - 1),
                "unapproved preflight consumed a persistent grant nonce",
            )
            _append_event(
                events,
                "preflight_zero_execution",
                {
                    "round": round_number,
                    "task_id": primary.id,
                    "runtime_status": preflight.status,
                    "receipts_emitted": len(preflight.receipts),
                    "receipt_count_before": receipt_count_before,
                    "receipt_count_after": len(receipt_log.all()),
                    "provider_stats": preflight_stats,
                    "grant_ledger_count": preflight_ledger_count,
                },
            )
            preflight_blocks += 1

            approved = issue_grant(
                secret,
                primary,
                capabilities,
                scopes,
                Effect.WRITE,
                approved_steps={"put"},
                capability_digests=registry.definition_digests(capabilities),
            )
            primary_result = runtime.execute(primary, approved)
            _require(primary_result.status == "completed", f"primary round failed: {primary_result.status}")
            _require(
                [item["status"] for item in primary_result.receipts] == ["succeeded", "succeeded"],
                "primary round receipts were not both succeeded",
            )
            put_state = _extract_state(primary_result.outputs["put"])
            read_state = _extract_state(primary_result.outputs["read"])
            _assert_state(
                put_state,
                status="applied",
                operation_id=operation_id,
                memo_id=memo_id,
                content=content,
                revision=round_number,
                physical_mutations=round_number,
                put_invocations=(2 * round_number) - 1,
            )
            _assert_state(
                read_state,
                status="present",
                operation_id=operation_id,
                memo_id=memo_id,
                content=content,
                revision=round_number,
                physical_mutations=round_number,
                put_invocations=(2 * round_number) - 1,
            )

            receipt_count_after_primary = len(receipt_log.all())
            ledger_count_before_replay = grant_ledger.count()
            _require(
                ledger_count_before_replay == (2 * (round_number - 1)) + 1,
                "approved primary plan did not consume exactly one persistent grant",
            )
            kernel_replay_stats_before = _extract_state(
                adapter.execute(PACKAGE, STATS_FUNCTION, {})
            )
            ledger_integrity_before_replay = grant_ledger.verify()
            _require(ledger_integrity_before_replay, "grant ledger failed before replay")
            runtime_recreated = False
            old_runtime_released = False
            old_policy_released = False
            old_ledger_released = False
            event_kind = "kernel_grant_replay_rejected"
            if round_number == 1:
                old_runtime_reference = weakref.ref(runtime)
                old_policy_reference = weakref.ref(runtime.policy)
                old_ledger_reference = weakref.ref(grant_ledger)
                del runtime
                del grant_ledger
                gc.collect()
                old_runtime_released = old_runtime_reference() is None
                old_policy_released = old_policy_reference() is None
                old_ledger_released = old_ledger_reference() is None
                _require(old_runtime_released, "old JidanRuntime was not released")
                _require(old_policy_released, "old PolicyEngine was not released")
                _require(old_ledger_released, "old persistent grant ledger was not released")
                grant_ledger = SqliteGrantLedger.open_existing(ledger_path)
                runtime = JidanRuntime(
                    registry,
                    PolicyEngine(secret, grant_ledger=grant_ledger),
                    receipt_log,
                )
                runtime_recreated = True
                event_kind = "persistent_grant_replay_after_runtime_recreation_rejected"
            kernel_replay = runtime.execute(primary, approved)
            _require(kernel_replay.status == "rejected", "consumed Jidan grant was not rejected")
            _require(not kernel_replay.receipts, "kernel replay emitted a receipt")
            _require(
                all("already been consumed" in decision.reason for decision in kernel_replay.decisions),
                "kernel replay was rejected for an unexpected reason",
            )
            _require(
                len(receipt_log.all()) == receipt_count_after_primary,
                "kernel replay changed receipt log",
            )
            ledger_count_after_replay = grant_ledger.count()
            _require(
                ledger_count_after_replay == ledger_count_before_replay,
                "kernel replay changed persistent grant ledger count",
            )
            ledger_integrity_after_replay = grant_ledger.verify()
            _require(ledger_integrity_after_replay, "grant ledger failed after replay")
            kernel_replay_stats = _extract_state(adapter.execute(PACKAGE, STATS_FUNCTION, {}))
            expected_kernel_replay_stats = {
                "physicalMutationCount": round_number,
                "putInvocationCount": (2 * round_number) - 1,
                "memoCount": 1,
            }
            _require(
                kernel_replay_stats == expected_kernel_replay_stats,
                f"consumed grant replay reached provider in round {round_number}",
            )
            _require(
                kernel_replay_stats == kernel_replay_stats_before,
                f"consumed grant replay changed provider stats in round {round_number}",
            )
            if runtime_recreated:
                persistent_runtime_recreation_replay_rejected = True
            _append_event(
                events,
                event_kind,
                {
                    "round": round_number,
                    "task_id": primary.id,
                    "runtime_status": kernel_replay.status,
                    "decision_reasons": [decision.reason for decision in kernel_replay.decisions],
                    "receipts_emitted": len(kernel_replay.receipts),
                    "receipt_count_before": receipt_count_after_primary,
                    "receipt_count_after": len(receipt_log.all()),
                    "provider_stats_before": kernel_replay_stats_before,
                    "provider_stats_after": kernel_replay_stats,
                    "physical_mutation_delta": (
                        kernel_replay_stats["physicalMutationCount"]
                        - kernel_replay_stats_before["physicalMutationCount"]
                    ),
                    "put_invocation_delta": (
                        kernel_replay_stats["putInvocationCount"]
                        - kernel_replay_stats_before["putInvocationCount"]
                    ),
                    "grant_nonce_sha256": hashlib.sha256(approved.nonce.encode()).hexdigest(),
                    "grant_ledger_count_before": ledger_count_before_replay,
                    "grant_ledger_count_after": ledger_count_after_replay,
                    "grant_ledger_integrity_before": ledger_integrity_before_replay,
                    "grant_ledger_integrity_after": ledger_integrity_after_replay,
                    "runtime_recreated": runtime_recreated,
                    "old_runtime_released": old_runtime_released,
                    "old_policy_released": old_policy_released,
                    "old_ledger_released": old_ledger_released,
                },
            )
            kernel_replay_rejections += 1

            provider_replay_plan = TaskPlan(
                id=f"{args.suite_id}-r{round_number:02d}-provider-replay",
                goal=f"Verify provider idempotency for controlled memo round {round_number}",
                steps=(
                    Step("put", put_record.capability.id, put_arguments),
                    Step("read", get_record.capability.id, read_arguments),
                ),
            )
            provider_grant = issue_grant(
                secret,
                provider_replay_plan,
                capabilities,
                scopes,
                Effect.WRITE,
                approved_steps={"put"},
                capability_digests=registry.definition_digests(capabilities),
            )
            provider_result = runtime.execute(provider_replay_plan, provider_grant)
            _require(provider_result.status == "completed", "provider replay plan failed")
            replay_state = _extract_state(provider_result.outputs["put"])
            replay_read_state = _extract_state(provider_result.outputs["read"])
            _assert_state(
                replay_state,
                status="replayed",
                operation_id=operation_id,
                memo_id=memo_id,
                content=content,
                revision=round_number,
                physical_mutations=round_number,
                put_invocations=2 * round_number,
            )
            _assert_state(
                replay_read_state,
                status="present",
                operation_id=operation_id,
                memo_id=memo_id,
                content=content,
                revision=round_number,
                physical_mutations=round_number,
                put_invocations=2 * round_number,
            )
            provider_replays += 1
            rounds.append(
                {
                    "round": round_number,
                    "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
                    "content_characters": len(content),
                    "revision": replay_read_state["revision"],
                    "physical_mutation_count": replay_read_state["physicalMutationCount"],
                    "put_invocation_count": replay_read_state["putInvocationCount"],
                    "primary_receipt_hashes": [item["hash"] for item in primary_result.receipts],
                    "provider_replay_receipt_hashes": [item["hash"] for item in provider_result.receipts],
                }
            )

        final_content = _content_for_round(args.suite_id, args.rounds)
        final_state = _extract_state(adapter.execute(PACKAGE, GET_FUNCTION, {"memoId": memo_id}))
        final_stats_before_collision = _extract_state(adapter.execute(PACKAGE, STATS_FUNCTION, {}))
        _assert_state(
            final_state,
            status="present",
            operation_id=f"{args.suite_id}-round-{args.rounds:02d}",
            memo_id=memo_id,
            content=final_content,
            revision=args.rounds,
            physical_mutations=args.rounds,
            put_invocations=2 * args.rounds,
        )
        _require(
            final_stats_before_collision
            == {
                "physicalMutationCount": args.rounds,
                "putInvocationCount": 2 * args.rounds,
                "memoCount": 1,
            },
            f"unexpected final positive-suite stats: {final_stats_before_collision!r}",
        )

        _checked_process(
            (
                str(adb_path),
                "-s",
                args.serial,
                "shell",
                "am",
                "start",
                "-W",
                "-n",
                f"{PACKAGE}/.MainActivity",
            )
        )
        pid_before_restart = _checked_process(
            (str(adb_path), "-s", args.serial, "shell", "pidof", PACKAGE),
        ).stdout.strip()
        _require(bool(pid_before_restart), "reference app had no process before restart test")
        _checked_process((str(adb_path), "-s", args.serial, "shell", "am", "force-stop", PACKAGE))
        _checked_process(
            (
                str(adb_path),
                "-s",
                args.serial,
                "shell",
                "am",
                "start",
                "-W",
                "-n",
                f"{PACKAGE}/.MainActivity",
            )
        )
        pid_after_restart = _checked_process(
            (str(adb_path), "-s", args.serial, "shell", "pidof", PACKAGE),
        ).stdout.strip()
        _require(bool(pid_after_restart), "reference app did not restart")
        _require(pid_after_restart != pid_before_restart, "reference app PID did not change after force-stop")
        _checked_process((str(adb_path), "-s", args.serial, "shell", "input", "keyevent", "3"))
        post_restart_stats = _extract_state(adapter.execute(PACKAGE, STATS_FUNCTION, {}))
        _require(
            post_restart_stats == final_stats_before_collision,
            "process restart changed persistent provider state",
        )
        _append_event(
            events,
            "provider_process_restart",
            {
                "pid_before": pid_before_restart,
                "pid_after": pid_after_restart,
                "persistent_stats_before": final_stats_before_collision,
                "persistent_stats_after": post_restart_stats,
            },
        )

        first_operation_id = f"{args.suite_id}-round-01"
        first_content = _content_for_round(args.suite_id, 1)
        delayed_replay_plan = TaskPlan(
            id=f"{args.suite_id}-delayed-round-01-replay",
            goal="Replay the first operation after 29 later writes and a provider process restart",
            steps=(
                Step(
                    "put",
                    put_record.capability.id,
                    {
                        "operationId": first_operation_id,
                        "memoId": memo_id,
                        "content": first_content,
                    },
                ),
                Step("read", get_record.capability.id, {"memoId": memo_id}),
            ),
        )
        delayed_replay_grant = issue_grant(
            secret,
            delayed_replay_plan,
            capabilities,
            scopes,
            Effect.WRITE,
            approved_steps={"put"},
            capability_digests=registry.definition_digests(capabilities),
        )
        delayed_replay_result = runtime.execute(delayed_replay_plan, delayed_replay_grant)
        _require(delayed_replay_result.status == "completed", "delayed operation replay failed")
        delayed_operation_state = _extract_state(delayed_replay_result.outputs["put"])
        delayed_current_state = _extract_state(delayed_replay_result.outputs["read"])
        _assert_state(
            delayed_operation_state,
            status="replayed",
            operation_id=first_operation_id,
            memo_id=memo_id,
            content=first_content,
            revision=1,
            physical_mutations=args.rounds,
            put_invocations=(2 * args.rounds) + 1,
        )
        _assert_state(
            delayed_current_state,
            status="present",
            operation_id=f"{args.suite_id}-round-{args.rounds:02d}",
            memo_id=memo_id,
            content=final_content,
            revision=args.rounds,
            physical_mutations=args.rounds,
            put_invocations=(2 * args.rounds) + 1,
        )
        provider_replays += 1
        _append_event(
            events,
            "delayed_old_operation_replay_succeeded",
            {
                "operation_id": first_operation_id,
                "writes_since_original": args.rounds - 1,
                "provider_process_restarted": True,
                "operation_snapshot": delayed_operation_state,
                "current_memo_state": delayed_current_state,
                "receipt_hashes": [item["hash"] for item in delayed_replay_result.receipts],
            },
        )

        collision_rejected = False
        collision_message = ""
        try:
            adapter.execute(
                PACKAGE,
                PUT_FUNCTION,
                {
                    "operationId": f"{args.suite_id}-round-{args.rounds:02d}",
                    "memoId": memo_id,
                    "content": final_content + "-MUST-NOT-OVERWRITE",
                },
            )
        except AppFunctionsAdapterError as exc:
            collision_rejected = True
            collision_message = str(exc)
        _require(collision_rejected, "idempotency-key collision was not rejected")
        after_collision = _extract_state(adapter.execute(PACKAGE, GET_FUNCTION, {"memoId": memo_id}))
        _require(after_collision["content"] == final_content, "collision overwrote memo content")
        _require(after_collision["revision"] == args.rounds, "collision changed revision")
        _require(
            after_collision["physicalMutationCount"] == args.rounds,
            "collision caused a physical mutation",
        )
        _require(
            after_collision["putInvocationCount"] == (2 * args.rounds) + 2,
            "collision did not reach the provider exactly once",
        )
        _append_event(
            events,
            "idempotency_key_collision_rejected",
            {
                "operation_id": f"{args.suite_id}-round-{args.rounds:02d}",
                "provider_error": collision_message,
                "current_memo_state": after_collision,
                "physical_mutation_delta": 0,
                "put_invocation_delta": 1,
            },
        )

        expected_ledger_entries = (args.rounds * 2) + 1
        _require(
            persistent_runtime_recreation_replay_rejected,
            "persistent replay was not tested after Runtime recreation",
        )
        ledger_entries = grant_ledger.count()
        _require(
            ledger_entries == expected_ledger_entries,
            f"expected {expected_ledger_entries} consumed grants, got {ledger_entries}",
        )
        _require(grant_ledger.verify(), "persistent grant ledger integrity check failed")
        grant_ledger.checkpoint()
        _require(grant_ledger.verify(), "grant ledger failed verification after checkpoint")
        ledger_sha256 = _sha256_file(ledger_path)

        receipts = receipt_log.all()
        expected_receipts = (args.rounds * 4) + 2
        _require(len(receipts) == expected_receipts, f"expected {expected_receipts} receipts")
        _require(all(item["status"] == "succeeded" for item in receipts), "receipt status failure")
        _require(receipt_log.verify(), "receipt hash chain failed verification")
        tamper_detected = _tamper_is_detected(receipt_path)
        _require(tamper_detected, "tampered receipt copy was not detected")
        expected_events = (args.rounds * 2) + 3
        _require(len(events) == expected_events, f"expected {expected_events} test events")
        _require(_verify_event_chain(events), "in-memory test event hash chain is invalid")
        _write_event_log(event_path, events)
        persisted_events = _read_event_log(event_path)
        _require(_verify_event_chain(persisted_events), "persisted test event hash chain is invalid")
        tampered_events = json.loads(json.dumps(persisted_events))
        tampered_events[0]["kind"] = "tampered"
        event_tamper_detected = not _verify_event_chain(tampered_events)
        _require(event_tamper_detected, "tampered test event chain was not detected")

        fingerprint = _checked_process(
            (str(adb_path), "-s", args.serial, "shell", "getprop", "ro.build.fingerprint"),
        ).stdout.strip()
        summary = {
            "ok": True,
            "device": probe.to_dict(),
            "android_fingerprint": fingerprint,
            "package": PACKAGE,
            "apk_identity": identity,
            "trusted_capability_refinement": {
                PUT_FUNCTION: "write",
                GET_FUNCTION: "read",
                STATS_FUNCTION: "read",
                "pinned_signer_scope": f"android.signer.sha256.{identity['signer_certificate_sha256']}",
            },
            "suite_id": args.suite_id,
            "rounds_requested": args.rounds,
            "rounds_completed": len(rounds),
            "preflight_zero_execution_blocks": preflight_blocks,
            "kernel_grant_replays_rejected": kernel_replay_rejections,
            "provider_immediate_idempotent_replays": args.rounds,
            "provider_idempotent_replays": provider_replays,
            "delayed_round_01_replay_after_29_writes_and_restart": True,
            "provider_process_restart": {
                "pid_before": pid_before_restart,
                "pid_after": pid_after_restart,
                "persistent_state_preserved": True,
            },
            "persistent_grant_ledger": {
                "backend": "sqlite",
                "schema_version": 1,
                "journal_mode": "WAL",
                "synchronous": "FULL",
                "path": str(ledger_path),
                "entries": ledger_entries,
                "integrity_check": "ok",
                "sha256_after_checkpoint": ledger_sha256,
                "runtime_recreation_replay_rejected": (
                    persistent_runtime_recreation_replay_rejected
                ),
            },
            "physical_mutations": after_collision["physicalMutationCount"],
            "provider_put_invocations": after_collision["putInvocationCount"],
            "final_revision": after_collision["revision"],
            "final_content_sha256": hashlib.sha256(final_content.encode()).hexdigest(),
            "idempotency_key_collision_rejected": collision_rejected,
            "idempotency_key_collision_error": collision_message,
            "successful_receipts": len(receipts),
            "receipt_chain_valid": True,
            "receipt_tamper_detected": tamper_detected,
            "receipt_head_hash": receipts[-1]["hash"],
            "receipt_log": str(receipt_path),
            "test_events": len(persisted_events),
            "test_event_chain_valid": True,
            "test_event_tamper_detected": event_tamper_detected,
            "test_event_head_hash": persisted_events[-1]["hash"],
            "test_event_log": str(event_path),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "rounds": rounds,
        }
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({key: value for key, value in summary.items() if key != "rounds"}, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        failure = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "receipt_log": str(receipt_path),
            "event_log": str(event_path),
            "grant_ledger": str(ledger_path),
        }
        print(json.dumps(failure, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

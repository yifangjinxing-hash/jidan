from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import os
import sys
import unittest


PROTOTYPE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROTOTYPE_ROOT))

from alipay_handoff_live import _parser, main  # noqa: E402
from jidan.alipay_handoff import ALIPAY_PACKAGE  # noqa: E402
from jidan.android_appfunctions import CommandResult  # noqa: E402


CERTIFICATE = "ab" * 32
LAUNCHER = f"{ALIPAY_PACKAGE}/.AlipayLogin"
FOREGROUND = f"{ALIPAY_PACKAGE}/.AlipayHome"
VERSION_CODE = 123456
DEVICE_SDK = 35
ANDROID_USER = 0
BASE_APK = "/data/app/alipay/base.apk"


class FakeRunner:
    def __init__(self, *responses: CommandResult) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[tuple[str, ...], float]] = []

    def run(self, argv, *, timeout_seconds):
        self.calls.append((tuple(argv), timeout_seconds))
        if not self.responses:
            raise AssertionError("unexpected command")
        return self.responses.pop(0)


def identity_responses() -> list[CommandResult]:
    return [
        CommandResult(0, "device\n", ""),
        CommandResult(0, f"{DEVICE_SDK}\n", ""),
        CommandResult(0, f"{ANDROID_USER}\n", ""),
        CommandResult(0, f"versionCode={VERSION_CODE}\n", ""),
        CommandResult(0, f"package:{BASE_APK}\n", ""),
        CommandResult(0, "1 file pulled\n", ""),
        CommandResult(
            0,
            f"Signer #1 certificate SHA-256 digest: {CERTIFICATE}\n",
            "",
        ),
    ]


def activity(component: str) -> CommandResult:
    return CommandResult(
        0,
        f"topResumedActivity=ActivityRecord{{abc u{ANDROID_USER} {component} t7}}\n",
        "",
    )


def window(component: str) -> CommandResult:
    return CommandResult(
        0,
        f"mCurrentFocus=Window{{def u{ANDROID_USER} {component}}}\n",
        "",
    )


def success_responses() -> list[CommandResult]:
    handoff = [
        CommandResult(0, f"{LAUNCHER}\n", ""),
        CommandResult(0, f"Status: ok\nActivity: {LAUNCHER}\n", ""),
        activity(FOREGROUND),
        window(FOREGROUND),
        activity(FOREGROUND),
        window(FOREGROUND),
    ]
    return [*identity_responses(), *handoff, *identity_responses()]


class AlipayHandoffLiveTests(unittest.TestCase):
    def _arguments(self, directory: Path) -> list[str]:
        adb = directory / "adb-test.exe"
        java = directory / "java-test.exe"
        apksigner = directory / "apksigner-test.jar"
        adb.write_bytes(b"")
        java.write_bytes(b"")
        apksigner.write_bytes(b"")
        return [
            "alipay_handoff_live.py",
            "--adb-path",
            str(adb.resolve()),
            "--java-path",
            str(java.resolve()),
            "--apksigner-jar",
            str(apksigner.resolve()),
            "--serial",
            "emulator-5554",
            "--version-code",
            str(VERSION_CODE),
            "--certificate-sha256",
            CERTIFICATE,
            "--launcher-component",
            LAUNCHER,
            "--foreground-component",
            FOREGROUND,
            "--receipt-log",
            str(directory / "receipts.jsonl"),
            "--grant-ledger",
            str(directory / "grants.sqlite3"),
            "--initialize-grant-ledger",
        ]

    def test_default_run_stops_before_any_adb_or_apksigner_command(self) -> None:
        with TemporaryDirectory() as directory_name:
            arguments = self._arguments(Path(directory_name))
            output = StringIO()
            runner = FakeRunner()

            with patch.object(sys, "argv", arguments), redirect_stdout(output):
                exit_code = main(runner=runner)

            payload = json.loads(output.getvalue())
            self.assertEqual(0, exit_code)
            self.assertTrue(payload["ok"])
            self.assertFalse(payload["executed"])
            self.assertEqual("awaiting_confirmation", payload["preflight"])
            self.assertEqual("external", payload["effect"])
            self.assertEqual(
                {
                    "amountSetByJidan": False,
                    "recipientSelectedByJidan": False,
                    "paymentAttemptedByJidan": False,
                    "paid": False,
                    "committed": False,
                    "verified": False,
                },
                payload["payment"],
            )
            self.assertEqual([], runner.calls)

    def test_approved_run_reports_only_verified_handoff_summary(self) -> None:
        with TemporaryDirectory() as directory_name:
            arguments = self._arguments(Path(directory_name))
            arguments.append("--approve-open-ui")
            runner = FakeRunner(*success_responses())
            output = StringIO()

            with patch.object(sys, "argv", arguments), redirect_stdout(output):
                exit_code = main(runner=runner)

            payload = json.loads(output.getvalue())
            self.assertEqual(0, exit_code)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["handoffOpened"])
            self.assertEqual(
                {
                    "status": "handoff_opened",
                    "hostPinsMatched": True,
                    "bindingAuthority": "os_frontdoor",
                    "guaranteeLevel": "adb_verified_foreground",
                },
                payload["evidence"],
            )
            self.assertNotIn("output", payload)
            self.assertNotIn("path", payload["grantLedger"])
            self.assertEqual([], runner.responses)
            self.assertEqual(20, len(runner.calls))

    def test_summary_cannot_overwrite_logs_ledger_sidecars_or_tools(self) -> None:
        target_options = (
            "--receipt-log",
            "--grant-ledger",
            "--adb-path",
            "--java-path",
            "--apksigner-jar",
        )
        for target_option in target_options:
            with self.subTest(target_option=target_option):
                with TemporaryDirectory() as directory_name:
                    directory = Path(directory_name)
                    arguments = self._arguments(directory)
                    target = Path(
                        arguments[arguments.index(target_option) + 1]
                    )
                    with patch.object(
                        sys,
                        "argv",
                        arguments + ["--summary", str(target)],
                    ):
                        with self.assertRaises(SystemExit):
                            main(runner=FakeRunner())

                    self.assertFalse((directory / "receipts.jsonl").exists())
                    self.assertFalse((directory / "grants.sqlite3").exists())

        for suffix in (".lock", "-wal", "-shm", "-journal"):
            with self.subTest(sidecar=suffix):
                with TemporaryDirectory() as directory_name:
                    directory = Path(directory_name)
                    arguments = self._arguments(directory)
                    base_option = (
                        "--receipt-log" if suffix == ".lock" else "--grant-ledger"
                    )
                    base = arguments[arguments.index(base_option) + 1]
                    with patch.object(
                        sys,
                        "argv",
                        arguments + ["--summary", base + suffix],
                    ):
                        with self.assertRaises(SystemExit):
                            main(runner=FakeRunner())

                    self.assertFalse((directory / "receipts.jsonl").exists())
                    self.assertFalse((directory / "grants.sqlite3").exists())

    def test_existing_hardlink_alias_is_rejected_before_writes(self) -> None:
        with TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            arguments = self._arguments(directory)
            adb = Path(arguments[arguments.index("--adb-path") + 1])
            alias = directory / "summary-hardlink.json"
            os.link(adb, alias)

            with patch.object(
                sys,
                "argv",
                arguments + ["--summary", str(alias)],
            ):
                with self.assertRaises(SystemExit):
                    main(runner=FakeRunner())

            self.assertEqual(b"", adb.read_bytes())
            self.assertFalse((directory / "receipts.jsonl").exists())
            self.assertFalse((directory / "grants.sqlite3").exists())

    def test_summary_directory_is_rejected_before_local_or_external_writes(self) -> None:
        with TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            arguments = self._arguments(directory)
            summary_directory = directory / "summary-directory"
            summary_directory.mkdir()
            runner = FakeRunner()

            with patch.object(
                sys,
                "argv",
                arguments + ["--summary", str(summary_directory)],
            ):
                with self.assertRaises(SystemExit):
                    main(runner=runner)

            self.assertEqual([], runner.calls)
            self.assertFalse((directory / "receipts.jsonl").exists())
            self.assertFalse((directory / "grants.sqlite3").exists())

    def test_parser_has_no_payment_or_private_uri_arguments(self) -> None:
        with TemporaryDirectory() as directory_name:
            arguments = self._arguments(Path(directory_name))[1:]
            for forbidden in (
                "--amount",
                "--recipient",
                "--url",
                "--scheme",
                "--apksigner-path",
            ):
                with self.subTest(forbidden=forbidden):
                    with redirect_stderr(StringIO()):
                        with self.assertRaises(SystemExit):
                            _parser().parse_args(arguments + [forbidden, "unsafe"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
import json
import math
import shlex
import subprocess
import sys
import unittest


PROTOTYPE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROTOTYPE_ROOT))

from jidan.android_appfunctions import (  # noqa: E402
    AdbAppFunctionsAdapter,
    AdbMissingError,
    AppFunctionsParseError,
    CommandResult,
    DeviceOfflineError,
    PermissionDeniedError,
    SubprocessCommandRunner,
    UnsupportedAppFunctionsError,
)
from jidan.models import Effect  # noqa: E402
from jidan.registry import CapabilityRegistry  # noqa: E402
from appfunctions_smoke import run_smoke  # noqa: E402


PACKAGE = "com.example.notes"
FUNCTION = "com.example.notes.NoteFunctions#createNote"
LIST_RESPONSE = {
    PACKAGE: [
        {
            "AppFunctionStaticMetadata": {
                "description": ["Create a note after the user chooses its title."],
                "parameters": [
                    {
                        "name": ["title"],
                        "isRequired": [True],
                        "dataType": [{"type": ["string"]}],
                    }
                ],
                "response": [{"valueType": [{"type": [8]}]}],
            },
            "AppFunctionRuntimeMetadata": {
                "functionId": [FUNCTION],
                "packageName": [PACKAGE],
                "enabled": [1],
            },
        }
    ]
}


class FakeRunner:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls: list[tuple[tuple[str, ...], float]] = []

    def run(self, argv, *, timeout_seconds):
        self.calls.append((tuple(argv), timeout_seconds))
        if not self.responses:
            raise AssertionError("unexpected command")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class AndroidAppFunctionsTests(unittest.TestCase):
    def test_fake_adb_jgraph_smoke_is_end_to_end(self):
        summary = run_smoke()

        self.assertEqual("awaiting_confirmation", summary["preflight_status"])
        self.assertEqual("completed", summary["approved_status"])
        self.assertTrue(summary["receipt_chain_valid"])
        self.assertEqual(2, summary["fake_adb_calls"])

    def test_probe_checks_device_then_service(self):
        runner = FakeRunner(
            CommandResult(0, "device\n", ""),
            CommandResult(
                0,
                "App function service commands:\n"
                "  list-app-functions\n"
                "  execute-app-function\n",
                "",
            ),
        )
        adapter = AdbAppFunctionsAdapter(runner, serial="emulator-5554")

        probe = adapter.probe()

        self.assertEqual("device", probe.state)
        self.assertTrue(probe.app_function_service)
        self.assertEqual("emulator-5554", probe.serial)
        self.assertEqual(
            ("adb", "-s", "emulator-5554", "get-state"),
            runner.calls[0][0],
        )
        self.assertEqual(
            (
                "adb",
                "-s",
                "emulator-5554",
                "shell",
                "cmd",
                "app_function",
                "help",
            ),
            runner.calls[1][0],
        )

    def test_probe_accepts_android17_help_written_to_stderr(self):
        runner = FakeRunner(
            CommandResult(0, "device\n", ""),
            CommandResult(
                255,
                "",
                "AppFunctionManagerService commands:\n"
                "  list-app-functions\n"
                "  execute-app-function\n"
                "Error executing app function: <documented diagnostic>\n",
            ),
        )
        adapter = AdbAppFunctionsAdapter(runner, serial="emulator-5554")

        probe = adapter.probe()

        self.assertTrue(probe.app_function_service)

    def test_discovery_accepts_android17_platform_simple_function_id(self):
        response = json.loads(json.dumps(LIST_RESPONSE))
        simple_id = "getPermissionsDeviceState"
        response[PACKAGE][0]["AppFunctionRuntimeMetadata"]["functionId"] = [simple_id]
        adapter = AdbAppFunctionsAdapter(
            FakeRunner(CommandResult(0, json.dumps(response), ""))
        )

        records = adapter.discover(PACKAGE)

        self.assertEqual(1, len(records))
        self.assertEqual(simple_id, records[0].function_id)

    def test_discovery_normalizes_android_metadata_conservatively(self):
        runner = FakeRunner(CommandResult(0, json.dumps(LIST_RESPONSE), ""))
        adapter = AdbAppFunctionsAdapter(runner)

        records = adapter.discover()

        self.assertEqual(1, len(records))
        record = records[0]
        self.assertEqual(PACKAGE, record.package_name)
        self.assertEqual(FUNCTION, record.function_id)
        self.assertEqual(PACKAGE, record.capability.app)
        self.assertEqual(Effect.EXTERNAL, record.capability.effect)
        self.assertTrue(record.capability.requires_confirmation)
        self.assertFalse(record.capability.reversible)
        self.assertIn("android.appfunctions.execute", record.capability.scopes)
        self.assertIn("x-android-appfunctions-parameters", record.capability.input_schema)
        self.assertEqual(["title"], record.capability.input_schema["required"])
        self.assertEqual(
            "string",
            record.capability.input_schema["properties"]["title"]["type"],
        )
        self.assertEqual(
            "string",
            record.capability.output_schema["properties"]
            ["androidAppfunctionsReturnValue"]["items"]["type"],
        )
        self.assertEqual(
            (
                "adb",
                "shell",
                "cmd",
                "app_function",
                "list-app-functions",
            ),
            runner.calls[0][0],
        )
        normalized = record.to_dict()
        self.assertEqual(PACKAGE, normalized["provider"]["package"])
        self.assertEqual(FUNCTION, normalized["provider"]["function"])

    def test_uncompilable_android_input_contract_is_not_registered(self):
        response = json.loads(json.dumps(LIST_RESPONSE))
        parameter = response[PACKAGE][0]["AppFunctionStaticMetadata"]["parameters"][0]
        parameter["dataType"] = [{"type": [11], "dataTypeReference": ["SecretType"]}]
        adapter = AdbAppFunctionsAdapter(FakeRunner(CommandResult(0, json.dumps(response), "")))

        self.assertEqual((), adapter.discover(PACKAGE))

    def test_execute_passes_one_remote_quoted_json_argv(self):
        runner = FakeRunner(CommandResult(0, '{"created":true}', ""))
        adapter = AdbAppFunctionsAdapter(runner)
        arguments = {
            "title": "quote ' and $(touch /tmp/not-run); newline\nnext",
            "labels": ["a b", "c"],
        }

        output = adapter.execute(PACKAGE, FUNCTION, arguments)

        self.assertEqual({"created": True}, output)
        encoded = json.dumps(
            arguments,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        self.assertEqual(
            (
                "adb",
                "shell",
                "cmd",
                "app_function",
                "execute-app-function",
                "--timeout-duration",
                "30",
                "--package",
                shlex.quote(PACKAGE),
                "--function",
                shlex.quote(FUNCTION),
                "--parameters",
                shlex.quote(encoded),
            ),
            runner.calls[0][0],
        )

    def test_discovered_record_binds_as_jgraph_registry_adapter(self):
        runner = FakeRunner(
            CommandResult(0, json.dumps(LIST_RESPONSE), ""),
            CommandResult(0, '{"androidAppfunctionsReturnValue":["note-42"]}', ""),
        )
        adapter = AdbAppFunctionsAdapter(runner)
        registry = CapabilityRegistry()

        records = adapter.register_discovered(registry, package_name=PACKAGE)
        output = registry.invoke(records[0].capability.id, {"title": "Roadmap"})

        self.assertEqual({"androidAppfunctionsReturnValue": ["note-42"]}, output)
        self.assertEqual(records[0].capability, registry.get(records[0].capability.id))
        with self.assertRaisesRegex(ValueError, "title is required"):
            registry.validate_input(records[0].capability.id, {})
        with self.assertRaisesRegex(ValueError, "must be string"):
            registry.validate_input(records[0].capability.id, {"title": 42})

    def test_record_injection_cannot_cross_explicit_package_boundary(self):
        runner = FakeRunner(CommandResult(0, json.dumps(LIST_RESPONSE), ""))
        adapter = AdbAppFunctionsAdapter(runner)
        record = adapter.discover(PACKAGE)[0]

        with self.assertRaisesRegex(ValueError, "outside the allowed package"):
            adapter.register_discovered(
                CapabilityRegistry(),
                records=(record,),
                package_name="com.example.other",
            )

    def test_error_kinds_are_distinct_without_real_adb(self):
        cases = [
            (
                "missing",
                FileNotFoundError("adb"),
                AdbMissingError,
            ),
            (
                "offline",
                CommandResult(1, "", "error: device offline"),
                DeviceOfflineError,
            ),
            (
                "permission",
                CommandResult(
                    255,
                    "",
                    "java.lang.SecurityException: Permission Denial: requires "
                    "android.permission.EXECUTE_APP_FUNCTIONS",
                ),
                PermissionDeniedError,
            ),
            (
                "unsupported",
                CommandResult(0, "cmd: Can't find service: app_function\n", ""),
                UnsupportedAppFunctionsError,
            ),
            (
                "parse",
                CommandResult(0, "not-json", ""),
                AppFunctionsParseError,
            ),
        ]
        for label, response, expected in cases:
            with self.subTest(label=label):
                adapter = AdbAppFunctionsAdapter(FakeRunner(response))
                with self.assertRaises(expected):
                    adapter.discover()

    def test_no_device_is_reported_by_probe_before_service_check(self):
        runner = FakeRunner(CommandResult(1, "", "adb: no devices/emulators found"))
        adapter = AdbAppFunctionsAdapter(runner)

        with self.assertRaises(DeviceOfflineError) as raised:
            adapter.probe()

        self.assertEqual("device_offline", raised.exception.kind.value)
        self.assertEqual(1, len(runner.calls))

    def test_missing_requested_serial_is_device_offline(self):
        runner = FakeRunner(CommandResult(1, "", "error: device 'missing' not found"))
        adapter = AdbAppFunctionsAdapter(runner, serial="missing")

        with self.assertRaises(DeviceOfflineError):
            adapter.probe()

    def test_parameter_validation_happens_before_runner(self):
        runner = FakeRunner()
        adapter = AdbAppFunctionsAdapter(runner)

        with self.assertRaises(ValueError):
            adapter.execute(PACKAGE, FUNCTION, {"amount": math.nan})
        with self.assertRaises(TypeError):
            adapter.execute(PACKAGE, FUNCTION, {1: "not a string key"})
        with self.assertRaises(TypeError):
            adapter.execute(PACKAGE, FUNCTION, {"mixed": [1, "two"]})
        with self.assertRaises(ValueError):
            adapter.execute(PACKAGE, FUNCTION, {"nested": [[1], []]})

        self.assertEqual([], runner.calls)

    def test_dynamic_registration_requires_explicit_package_filter(self):
        runner = FakeRunner(CommandResult(0, json.dumps(LIST_RESPONSE), ""))
        adapter = AdbAppFunctionsAdapter(runner)

        with self.assertRaisesRegex(ValueError, "explicit package filter"):
            adapter.register_discovered(CapabilityRegistry())

        self.assertEqual([], runner.calls)

    def test_quoted_command_budget_is_enforced_before_runner(self):
        runner = FakeRunner(CommandResult(0, "[]", ""))
        adapter = AdbAppFunctionsAdapter(runner)

        with self.assertRaisesRegex(ValueError, "quoted AppFunction command exceeds"):
            adapter.execute(PACKAGE, FUNCTION, {"text": "'" * 6000})

        self.assertEqual([], runner.calls)

    def test_null_and_empty_array_fields_are_rejected_before_execution(self):
        runner = FakeRunner(CommandResult(0, "[]", ""))
        adapter = AdbAppFunctionsAdapter(runner)

        with self.assertRaisesRegex(ValueError, "must be omitted before approval"):
            adapter.execute_with_raw(
                PACKAGE,
                FUNCTION,
                {"optional": None, "empty": [], "ids": [1, 2]},
            )

        self.assertEqual([], runner.calls)

    def test_error_words_inside_valid_json_are_not_transport_errors(self):
        runner = FakeRunner(CommandResult(0, '{"message":"permission denied by note owner"}', ""))
        adapter = AdbAppFunctionsAdapter(runner)

        output = adapter.execute(PACKAGE, FUNCTION, {})

        self.assertEqual({"message": "permission denied by note owner"}, output)

    def test_package_filtered_raw_list_preserves_stdout(self):
        raw = json.dumps(LIST_RESPONSE, indent=2)
        runner = FakeRunner(CommandResult(0, raw, ""))
        adapter = AdbAppFunctionsAdapter(runner)

        self.assertEqual(raw, adapter.list_raw(PACKAGE))
        self.assertEqual(
            (
                "adb",
                "shell",
                "cmd",
                "app_function",
                "list-app-functions",
                "--package",
                PACKAGE,
            ),
            runner.calls[0][0],
        )

    def test_subprocess_runner_explicitly_disables_shell(self):
        completed = subprocess.CompletedProcess(["adb", "version"], 0, "ok", "")
        with patch("jidan.android_appfunctions.subprocess.run", return_value=completed) as run:
            result = SubprocessCommandRunner().run(
                ["adb", "version"],
                timeout_seconds=3.0,
            )

        self.assertEqual("ok", result.stdout)
        positional, keyword = run.call_args
        self.assertEqual(["adb", "version"], positional[0])
        self.assertIs(False, keyword["shell"])
        self.assertIs(False, keyword["check"])


if __name__ == "__main__":
    unittest.main()

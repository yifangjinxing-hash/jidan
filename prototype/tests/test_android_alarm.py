from __future__ import annotations

from pathlib import Path
import shlex
import sys
import unittest


PROTOTYPE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROTOTYPE_ROOT))

from jidan.android_alarm import (  # noqa: E402
    ACTION_SET_ALARM,
    AdbAlarmClockAdapter,
    AlarmClockHandlerUnavailable,
)
from jidan.android_appfunctions import CommandResult  # noqa: E402
from jidan.registry import CapabilityRegistry  # noqa: E402


class FakeRunner:
    def __init__(self, results: list[CommandResult]) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv, *, timeout_seconds):
        self.calls.append(tuple(argv))
        return self.results.pop(0)


class AlarmClockAdapterTests(unittest.TestCase):
    def test_dispatches_public_set_alarm_intent(self) -> None:
        message = "Jidan 中文 ' & 🚀"
        runner = FakeRunner(
            [
                CommandResult(
                    0,
                    stdout=(
                        "priority=0 preferredOrder=0 match=0x108000 specificIndex=-1 "
                        "isDefault=true\n"
                        "com.google.android.deskclock/com.android.deskclock.HandleSetApiCalls\n"
                    ),
                ),
                CommandResult(0, stdout="Starting: Intent { act=android.intent.action.SET_ALARM }\nStatus: ok\n"),
            ]
        )
        adapter = AdbAlarmClockAdapter(runner, adb_path="adb", serial="emulator-5554")
        registry = CapabilityRegistry()
        capability = adapter.register(registry)

        output = registry.invoke(
            capability.id,
            {"hour": 8, "minutes": 30, "message": message, "skipUi": False},
        )

        self.assertEqual("dispatched", output["status"])
        self.assertEqual(2, len(runner.calls))
        self.assertIn(ACTION_SET_ALARM, runner.calls[1])
        self.assertIn(shlex.quote(message), runner.calls[1])
        self.assertEqual(message, output["message"])

    def test_rejects_invalid_clock_time_before_dispatch(self) -> None:
        adapter = AdbAlarmClockAdapter(FakeRunner([]), adb_path="adb")

        with self.assertRaisesRegex(ValueError, "hour"):
            adapter.set_alarm(
                {"hour": 24, "minutes": 0, "message": "invalid", "skipUi": True},
            )

    def test_rejects_non_google_clock_handler(self) -> None:
        runner = FakeRunner(
            [CommandResult(0, stdout="com.example.clock/.SetAlarmActivity\n")]
        )
        adapter = AdbAlarmClockAdapter(runner, adb_path="adb")

        with self.assertRaises(AlarmClockHandlerUnavailable):
            adapter.probe_handler()


if __name__ == "__main__":
    unittest.main()

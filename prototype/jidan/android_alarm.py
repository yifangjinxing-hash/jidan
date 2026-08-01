from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
import re
import shlex
import subprocess

from .android_appfunctions import CommandResult, CommandRunner, SubprocessCommandRunner
from .models import Capability, Effect
from .registry import CapabilityRegistry


ACTION_SET_ALARM = "android.intent.action.SET_ALARM"
EXTRA_HOUR = "android.intent.extra.alarm.HOUR"
EXTRA_MINUTES = "android.intent.extra.alarm.MINUTES"
EXTRA_MESSAGE = "android.intent.extra.alarm.MESSAGE"
EXTRA_SKIP_UI = "android.intent.extra.alarm.SKIP_UI"
CLOCK_PACKAGE = "com.google.android.deskclock"
CLOCK_CAPABILITY_ID = "android.intent.alarm.set"
_ADB_SERIAL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")


class AlarmClockAdapterError(RuntimeError):
    pass


class AlarmClockHandlerUnavailable(AlarmClockAdapterError):
    pass


class AdbAlarmClockAdapter:
    """Jidan adapter for Android's public AlarmClock ACTION_SET_ALARM contract."""

    def __init__(
        self,
        runner: CommandRunner | None = None,
        *,
        adb_path: str = "adb",
        serial: str | None = None,
        timeout_seconds: float = 35.0,
    ) -> None:
        if not adb_path or "\x00" in adb_path:
            raise ValueError("adb_path must be a non-empty executable path")
        if serial is not None and not _ADB_SERIAL.fullmatch(serial):
            raise ValueError(f"invalid adb serial: {serial!r}")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._runner = runner or SubprocessCommandRunner()
        self._adb_path = adb_path
        self._serial = serial
        self._timeout_seconds = timeout_seconds

    @staticmethod
    def capability() -> Capability:
        return Capability(
            id=CLOCK_CAPABILITY_ID,
            app=CLOCK_PACKAGE,
            description=(
                "Set a real alarm in Google Clock through Android's public "
                "AlarmClock ACTION_SET_ALARM intent contract."
            ),
            effect=Effect.EXTERNAL,
            scopes=frozenset({ACTION_SET_ALARM, f"android.package.{CLOCK_PACKAGE}"}),
            requires_confirmation=True,
            reversible=False,
            input_schema={
                "type": "object",
                "properties": {
                    "hour": {"type": "integer"},
                    "minutes": {"type": "integer"},
                    "message": {"type": "string", "minLength": 1, "maxLength": 128},
                    "skipUi": {"type": "boolean"},
                },
                "required": ["hour", "minutes", "message", "skipUi"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "status": {"const": "dispatched"},
                    "package": {"const": CLOCK_PACKAGE},
                    "handler": {"type": "string"},
                    "hour": {"type": "integer"},
                    "minutes": {"type": "integer"},
                    "message": {"type": "string"},
                    "skipUi": {"type": "boolean"},
                    "raw_stdout": {"type": "string"},
                },
                "required": [
                    "status",
                    "package",
                    "handler",
                    "hour",
                    "minutes",
                    "message",
                    "skipUi",
                    "raw_stdout",
                ],
                "additionalProperties": False,
            },
            adapter="android.intent.adb-shell",
        )

    def register(self, registry: CapabilityRegistry) -> Capability:
        capability = self.capability()
        registry.register(capability, self.set_alarm)
        return capability

    def probe_handler(self) -> str:
        result = self._run(
            self._adb_argv(
                "shell",
                "cmd",
                "package",
                "resolve-activity",
                "--brief",
                "-a",
                ACTION_SET_ALARM,
            )
        )
        self._require_success(result, operation="resolve SET_ALARM handler")
        lines = [line.strip() for line in result.stdout.splitlines() if "/" in line]
        handler = lines[-1] if lines else ""
        if not handler.startswith(f"{CLOCK_PACKAGE}/"):
            raise AlarmClockHandlerUnavailable(
                f"SET_ALARM did not resolve to Google Clock: {handler or 'no handler'}"
            )
        return handler

    def set_alarm(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        hour = arguments.get("hour")
        minutes = arguments.get("minutes")
        message = arguments.get("message")
        skip_ui = arguments.get("skipUi")
        if isinstance(hour, bool) or not isinstance(hour, int) or not 0 <= hour <= 23:
            raise ValueError("hour must be an integer from 0 to 23")
        if (
            isinstance(minutes, bool)
            or not isinstance(minutes, int)
            or not 0 <= minutes <= 59
        ):
            raise ValueError("minutes must be an integer from 0 to 59")
        if (
            not isinstance(message, str)
            or not 1 <= len(message) <= 128
            or "\x00" in message
        ):
            raise ValueError("message must contain 1..128 characters and no NUL")
        if not isinstance(skip_ui, bool):
            raise ValueError("skipUi must be boolean")

        handler = self.probe_handler()
        result = self._run(
            self._adb_argv(
                "shell",
                "am",
                "start",
                "-W",
                "-a",
                ACTION_SET_ALARM,
                "-p",
                CLOCK_PACKAGE,
                "--ei",
                EXTRA_HOUR,
                str(hour),
                "--ei",
                EXTRA_MINUTES,
                str(minutes),
                "--es",
                EXTRA_MESSAGE,
                shlex.quote(message),
                "--ez",
                EXTRA_SKIP_UI,
                "true" if skip_ui else "false",
            )
        )
        self._require_success(result, operation="dispatch SET_ALARM")
        combined = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
        if re.search(r"(?im)^\s*error(?: type \d+)?:", combined):
            raise AlarmClockAdapterError(f"SET_ALARM was rejected: {combined}")
        return {
            "status": "dispatched",
            "package": CLOCK_PACKAGE,
            "handler": handler,
            "hour": hour,
            "minutes": minutes,
            "message": message,
            "skipUi": skip_ui,
            "raw_stdout": combined,
        }

    def _adb_argv(self, *tail: str) -> tuple[str, ...]:
        argv = [self._adb_path]
        if self._serial is not None:
            argv.extend(("-s", self._serial))
        argv.extend(tail)
        return tuple(argv)

    def _run(self, argv: Sequence[str]) -> CommandResult:
        try:
            return self._runner.run(argv, timeout_seconds=self._timeout_seconds)
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
            raise AlarmClockAdapterError(f"ADB command failed before completion: {exc}") from exc

    @staticmethod
    def _require_success(result: CommandResult, *, operation: str) -> None:
        if result.returncode != 0:
            diagnostic = "\n".join(
                part.strip() for part in (result.stdout, result.stderr) if part.strip()
            )
            raise AlarmClockAdapterError(
                f"{operation} failed with exit {result.returncode}: {diagnostic or 'no output'}"
            )

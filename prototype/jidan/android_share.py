from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
import hashlib
import re
import shlex
import subprocess
import time

from .android_appfunctions import CommandResult, CommandRunner, SubprocessCommandRunner
from .models import Capability, Effect
from .registry import CapabilityRegistry


ACTION_SEND = "android.intent.action.SEND"
EXTRA_TEXT = "android.intent.extra.TEXT"
TEXT_MIME_TYPE = "text/plain"
WECHAT_PACKAGE = "com.tencent.mm"
WECHAT_SHARE_COMPONENT = "com.tencent.mm/.ui.tools.ShareImgUI"
WECHAT_PICKER_COMPONENT = "com.tencent.mm/.ui.transmit.SelectConversationUI"
WECHAT_SHARE_CAPABILITY_ID = "android.intent.wechat.share_text_handoff"
_ADB_SERIAL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_TOP_ACTIVITY = re.compile(
    r"topResumedActivity=.*?\bu\d+\s+(?P<activity>\S+)",
    re.IGNORECASE,
)


class WeChatShareAdapterError(RuntimeError):
    pass


class WeChatShareHandlerUnavailable(WeChatShareAdapterError):
    pass


class AdbWeChatShareAdapter:
    """Open WeChat's own recipient picker through Android's public share contract.

    This adapter deliberately stops before recipient selection and sending. WeChat,
    rather than Jidan, remains the authority for contact identity.
    """

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
            id=WECHAT_SHARE_CAPABILITY_ID,
            app=WECHAT_PACKAGE,
            description=(
                "Hand text to WeChat's exported Android share surface and open "
                "WeChat's own recipient picker. This capability never chooses a "
                "recipient and never sends the message."
            ),
            effect=Effect.WRITE,
            scopes=frozenset(
                {
                    ACTION_SEND,
                    f"android.package.{WECHAT_PACKAGE}",
                    "wechat.share_text.handoff",
                }
            ),
            requires_confirmation=True,
            reversible=False,
            input_schema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "minLength": 1, "maxLength": 1000},
                },
                "required": ["text"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "status": {"const": "handoff_opened"},
                    "package": {"const": WECHAT_PACKAGE},
                    "handler": {"const": WECHAT_SHARE_COMPONENT},
                    "pickerActivity": {"const": WECHAT_PICKER_COMPONENT},
                    "textSha256": {
                        "type": "string",
                        "minLength": 64,
                        "maxLength": 64,
                    },
                    "jidanSelectedRecipient": {"const": False},
                    "jidanIssuedSend": {"const": False},
                    "deliveryState": {"const": "not_attempted_by_jidan"},
                    "nextAction": {
                        "const": "user_select_recipient_and_confirm_send"
                    },
                    "raw_stdout": {"type": "string"},
                },
                "required": [
                    "status",
                    "package",
                    "handler",
                    "pickerActivity",
                    "textSha256",
                    "jidanSelectedRecipient",
                    "jidanIssuedSend",
                    "deliveryState",
                    "nextAction",
                    "raw_stdout",
                ],
                "additionalProperties": False,
            },
            adapter="android.intent.adb-shell.wechat-share-handoff",
        )

    def register(self, registry: CapabilityRegistry) -> Capability:
        capability = self.capability()
        registry.register(capability, self.open_handoff)
        return capability

    def probe_handler(self) -> str:
        result = self._run(
            self._adb_argv(
                "shell",
                "cmd",
                "package",
                "query-activities",
                "--brief",
                "--components",
                "-a",
                ACTION_SEND,
                "-t",
                TEXT_MIME_TYPE,
                "-p",
                WECHAT_PACKAGE,
            )
        )
        self._require_success(result, operation="query WeChat text-share handlers")
        handlers = {line.strip() for line in result.stdout.splitlines() if line.strip()}
        if WECHAT_SHARE_COMPONENT not in handlers:
            raise WeChatShareHandlerUnavailable(
                "WeChat did not expose its expected Android text-share handler"
            )
        return WECHAT_SHARE_COMPONENT

    def open_handoff(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        text = arguments.get("text")
        if (
            not isinstance(text, str)
            or not 1 <= len(text) <= 1000
            or "\x00" in text
        ):
            raise ValueError("text must contain 1..1000 characters and no NUL")

        handler = self.probe_handler()
        dispatch = self._run(
            self._adb_argv(
                "shell",
                "am",
                "start",
                "-W",
                "-a",
                ACTION_SEND,
                "-t",
                TEXT_MIME_TYPE,
                "--es",
                EXTRA_TEXT,
                shlex.quote(text),
                "-n",
                handler,
            )
        )
        self._require_success(dispatch, operation="open WeChat share handoff")
        combined = "\n".join(
            part.strip() for part in (dispatch.stdout, dispatch.stderr) if part.strip()
        )
        status_match = re.search(r"(?im)^\s*Status:\s*(\S+)\s*$", combined)
        activity_match = re.search(r"(?im)^\s*Activity:\s*(\S+)\s*$", combined)
        if (
            status_match is None
            or status_match.group(1).lower() != "ok"
            or activity_match is None
            or activity_match.group(1) != handler
            or re.search(r"(?im)^\s*(?:error|exception)(?: type \d+)?:", combined)
        ):
            raise WeChatShareAdapterError(f"WeChat share handoff was rejected: {combined}")

        foreground = ""
        for attempt in range(8):
            foreground_result = self._run(
                self._adb_argv("shell", "dumpsys", "activity", "activities")
            )
            self._require_success(
                foreground_result,
                operation="verify WeChat recipient picker foreground",
            )
            match = _TOP_ACTIVITY.search(foreground_result.stdout)
            foreground = match.group("activity") if match is not None else ""
            if foreground == WECHAT_PICKER_COMPONENT:
                break
            if foreground != WECHAT_SHARE_COMPONENT:
                raise WeChatShareAdapterError(
                    "WeChat's exact recipient picker did not reach the foreground"
                )
            if attempt < 7:
                time.sleep(0.25)
        else:
            raise WeChatShareAdapterError(
                "WeChat's recipient picker did not appear before the timeout"
            )

        return {
            "status": "handoff_opened",
            "package": WECHAT_PACKAGE,
            "handler": handler,
            "pickerActivity": foreground,
            "textSha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "jidanSelectedRecipient": False,
            "jidanIssuedSend": False,
            "deliveryState": "not_attempted_by_jidan",
            "nextAction": "user_select_recipient_and_confirm_send",
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
            raise WeChatShareAdapterError(
                f"ADB command failed before completion: {exc}"
            ) from exc

    @staticmethod
    def _require_success(result: CommandResult, *, operation: str) -> None:
        if result.returncode != 0:
            diagnostic = "\n".join(
                part.strip() for part in (result.stdout, result.stderr) if part.strip()
            )
            raise WeChatShareAdapterError(
                f"{operation} failed with exit {result.returncode}: "
                f"{diagnostic or 'no output'}"
            )

from __future__ import annotations

from pathlib import Path
import hashlib
import shlex
import sys
import unittest


PROTOTYPE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROTOTYPE_ROOT))

from jidan.android_appfunctions import CommandResult  # noqa: E402
from jidan.android_share import (  # noqa: E402
    ACTION_SEND,
    EXTRA_TEXT,
    TEXT_MIME_TYPE,
    WECHAT_PACKAGE,
    WECHAT_PICKER_COMPONENT,
    WECHAT_SHARE_COMPONENT,
    AdbWeChatShareAdapter,
    WeChatShareAdapterError,
    WeChatShareHandlerUnavailable,
)
from jidan.models import Effect  # noqa: E402
from jidan.registry import CapabilityRegistry  # noqa: E402


class FakeRunner:
    def __init__(self, results: list[CommandResult]) -> None:
        self.results = list(results)
        self.calls: list[tuple[tuple[str, ...], float]] = []

    def run(self, argv, *, timeout_seconds):
        self.calls.append((tuple(argv), timeout_seconds))
        if not self.results:
            raise AssertionError(f"unexpected command: {argv!r}")
        return self.results.pop(0)


def _successful_runner() -> FakeRunner:
    return FakeRunner(
        [
            CommandResult(
                0,
                stdout=(
                    f"{WECHAT_SHARE_COMPONENT}\n"
                    f"{WECHAT_PACKAGE}/.ui.tools.AddFavoriteUI\n"
                ),
            ),
            CommandResult(
                0,
                stdout=(
                    "Starting: Intent {...}\nStatus: ok\n"
                    f"Activity: {WECHAT_SHARE_COMPONENT}\nComplete\n"
                ),
            ),
            CommandResult(
                0,
                stdout=(
                    "topResumedActivity=ActivityRecord{123 u0 "
                    f"{WECHAT_PACKAGE}/.ui.transmit.SelectConversationUI t9}}\n"
                ),
            ),
        ]
    )


class AdbWeChatShareAdapterTests(unittest.TestCase):
    def test_capability_requires_confirmation_for_cross_app_handoff(self) -> None:
        capability = AdbWeChatShareAdapter.capability()

        self.assertEqual(Effect.WRITE, capability.effect)
        self.assertTrue(capability.requires_confirmation)
        self.assertFalse(capability.reversible)
        self.assertEqual(WECHAT_PACKAGE, capability.app)
        self.assertIn("never sends", capability.description)

    def test_opens_wechat_picker_with_text_and_never_selects_or_sends(self) -> None:
        runner = _successful_runner()
        adapter = AdbWeChatShareAdapter(
            runner,
            adb_path="adb-test",
            serial="emulator-5554",
        )
        registry = CapabilityRegistry()
        capability = adapter.register(registry)

        output = registry.invoke(capability.id, {"text": "你好"})

        self.assertEqual("handoff_opened", output["status"])
        self.assertFalse(output["jidanSelectedRecipient"])
        self.assertFalse(output["jidanIssuedSend"])
        self.assertEqual("not_attempted_by_jidan", output["deliveryState"])
        self.assertEqual(
            hashlib.sha256("你好".encode("utf-8")).hexdigest(),
            output["textSha256"],
        )
        self.assertEqual(
            WECHAT_PICKER_COMPONENT,
            output["pickerActivity"],
        )

        calls = [argv for argv, _ in runner.calls]
        self.assertEqual(
            (
                "adb-test",
                "-s",
                "emulator-5554",
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
            ),
            calls[0],
        )
        self.assertEqual(
            (
                "adb-test",
                "-s",
                "emulator-5554",
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
                "'你好'",
                "-n",
                WECHAT_SHARE_COMPONENT,
            ),
            calls[1],
        )
        flattened = {token for argv in calls for token in argv}
        self.assertTrue(
            {"input", "tap", "swipe", "screencap", "SelectConversationUI"}.isdisjoint(
                flattened
            )
        )
        self.assertTrue(all(timeout == 35.0 for _, timeout in runner.calls))
        self.assertEqual([], runner.results)

    def test_missing_expected_share_handler_fails_closed(self) -> None:
        runner = FakeRunner(
            [CommandResult(0, stdout=f"{WECHAT_PACKAGE}/.ui.tools.AddFavoriteUI\n")]
        )
        adapter = AdbWeChatShareAdapter(runner)

        with self.assertRaises(WeChatShareHandlerUnavailable):
            adapter.open_handoff({"text": "hello"})

        self.assertEqual(1, len(runner.calls))

    def test_shell_metacharacters_remain_one_quoted_extra_value(self) -> None:
        runner = _successful_runner()
        adapter = AdbWeChatShareAdapter(runner)
        payload = "hello'; input tap 1 1; echo $HOME"

        adapter.open_handoff({"text": payload})

        dispatch_argv = runner.calls[1][0]
        text_index = dispatch_argv.index(EXTRA_TEXT) + 1
        self.assertEqual(shlex.quote(payload), dispatch_argv[text_index])
        self.assertNotIn("input", dispatch_argv)
        self.assertNotIn("tap", dispatch_argv)

    def test_invalid_text_is_rejected_before_adb(self) -> None:
        runner = FakeRunner([])
        adapter = AdbWeChatShareAdapter(runner)

        for value in ("", "x" * 1001, "bad\x00text", None, 12):
            with self.subTest(value=repr(value)):
                with self.assertRaises(ValueError):
                    adapter.open_handoff({"text": value})

        self.assertEqual([], runner.calls)

    def test_non_wechat_foreground_fails_closed(self) -> None:
        runner = _successful_runner()
        runner.results[-1] = CommandResult(
            0,
            stdout=(
                "topResumedActivity=ActivityRecord{123 u0 "
                "com.android.launcher/.Launcher t2}\n"
            ),
        )
        adapter = AdbWeChatShareAdapter(runner)

        with self.assertRaises(WeChatShareAdapterError):
            adapter.open_handoff({"text": "hello"})

    def test_non_ok_activity_manager_status_fails_closed(self) -> None:
        runner = _successful_runner()
        runner.results[1] = CommandResult(
            0,
            stdout=(
                "Starting: Intent {...}\nStatus: timeout\n"
                f"Activity: {WECHAT_SHARE_COMPONENT}\nComplete\n"
            ),
        )
        adapter = AdbWeChatShareAdapter(runner)

        with self.assertRaises(WeChatShareAdapterError):
            adapter.open_handoff({"text": "hello"})

        self.assertEqual(2, len(runner.calls))


if __name__ == "__main__":
    unittest.main()

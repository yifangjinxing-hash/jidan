from __future__ import annotations

from pathlib import Path
import sys
import unittest


PROTOTYPE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROTOTYPE_ROOT))

from jidan.android_appfunctions import CommandResult  # noqa: E402
from jidan.models import Effect  # noqa: E402
from jidan.registry import CapabilityRegistry  # noqa: E402
from jidan.semantic_surfaces import AdbSemanticSurfaceProbe  # noqa: E402


PACKAGE_NAME = "com.tencent.mm"


class FakeRunner:
    def __init__(self, results: list[CommandResult]) -> None:
        self.results = list(results)
        self.calls: list[tuple[tuple[str, ...], float]] = []

    def run(self, argv, *, timeout_seconds):
        self.calls.append((tuple(argv), timeout_seconds))
        if not self.results:
            raise AssertionError(f"unexpected command: {argv!r}")
        return self.results.pop(0)


WECHAT_SHORTCUTS = """ShortcutInfo {id=launch_type_my_qrcode, packageName=com.tencent.mm, activity=com.tencent.mm/.ui.LauncherUI, flags=0x21
  shortLabel=My QR Code, resId=0
  longLabel=null, resId=0
  categories=null
  persons=null
ShortcutInfo {id=launch_type_offline_wallet, packageName=com.tencent.mm, activity=com.tencent.mm/.ui.LauncherUI, flags=0x21
  shortLabel=Money, resId=0
  longLabel=null, resId=0
  categories=null
  persons=null
ShortcutInfo {id=launch_type_scan_qrcode, packageName=com.tencent.mm, activity=com.tencent.mm/.ui.LauncherUI, flags=0x21
  shortLabel=Scan, resId=0
  longLabel=null, resId=0
  categories=null
  persons=null
Success
"""


CONVERSATION_SHORTCUT = """ShortcutInfo {id=conversation_alice, packageName=com.tencent.mm, activity=com.tencent.mm/.ui.LauncherUI, flags=0x21
  shortLabel=Alice, resId=0
  longLabel=null, resId=0
  categories=[android.shortcut.conversation]
  persons=[Person {name=Alice, key=alice}]
Success
"""


def _notification_dump(
    *,
    package_name: str = PACKAGE_NAME,
    include_remote_input: bool = False,
    importance: str = "DEFAULT",
) -> str:
    remote_input = " actions=[RemoteInput {resultKey=reply}]" if include_remote_input else ""
    return f"""Notification List:
  NotificationRecord(0x1234: pkg={package_name} user=UserHandle{{0}} id=7 tag=null{remote_input}
    key=0|{package_name}|7|null|10123)
  Ranking Config:
    AppSettings: {package_name} (10123) importance={importance} userSet=true
"""


def _run_probe(
    *,
    app_functions: str = "{}\n",
    shortcuts: str = "Success\n",
    notifications: str | None = None,
) -> tuple[dict, FakeRunner, AdbSemanticSurfaceProbe]:
    runner = FakeRunner(
        [
            CommandResult(0, stdout="device\n"),
            CommandResult(0, stdout=f"package:/data/app/{PACKAGE_NAME}/base.apk\n"),
            CommandResult(0, stdout=app_functions),
            CommandResult(0, stdout=shortcuts),
            CommandResult(
                0,
                stdout=notifications
                if notifications is not None
                else (
                    "Ranking Config:\n"
                    f"  AppSettings: {PACKAGE_NAME} (10123) "
                    "importance=NONE userSet=true\n"
                ),
            ),
        ]
    )
    probe = AdbSemanticSurfaceProbe(
        PACKAGE_NAME,
        runner,
        adb_path="adb-test",
        serial="emulator-5554",
    )
    registry = CapabilityRegistry()
    capability = probe.register(registry)
    output = registry.invoke(
        capability.id,
        {"packageName": PACKAGE_NAME},
    )
    return dict(output), runner, probe


class SemanticSurfaceProbeTests(unittest.TestCase):
    def test_real_wechat_shortcuts_are_not_conversations_and_probe_is_read_only(self) -> None:
        output, runner, probe = _run_probe(shortcuts=WECHAT_SHORTCUTS)

        self.assertEqual(Effect.READ, probe.capability().effect)
        self.assertEqual(0, output["appFunctions"]["count"])
        self.assertEqual(3, output["shortcuts"]["count"])
        self.assertEqual(0, output["shortcuts"]["conversationCount"])
        self.assertEqual(
            [
                "launch_type_my_qrcode",
                "launch_type_offline_wallet",
                "launch_type_scan_qrcode",
            ],
            [item["id"] for item in output["shortcuts"]["items"]],
        )
        self.assertTrue(
            all(not item["hasPersons"] for item in output["shortcuts"]["items"])
        )
        self.assertEqual("NONE", output["notifications"]["importance"])
        self.assertEqual("blocked_no_semantic_surface", output["routing"]["selected"])
        self.assertFalse(output["routing"]["guiFallbackIsAuthoritative"])
        self.assertEqual(64, len(output["evidenceSha256"]))

        expected_calls = [
            ("adb-test", "-s", "emulator-5554", "get-state"),
            (
                "adb-test",
                "-s",
                "emulator-5554",
                "shell",
                "pm",
                "path",
                PACKAGE_NAME,
            ),
            (
                "adb-test",
                "-s",
                "emulator-5554",
                "shell",
                "cmd",
                "app_function",
                "list-app-functions",
                "--package",
                PACKAGE_NAME,
            ),
            (
                "adb-test",
                "-s",
                "emulator-5554",
                "shell",
                "cmd",
                "shortcut",
                "get-shortcuts",
                "--user",
                "0",
                "--flags",
                "31",
                PACKAGE_NAME,
            ),
            (
                "adb-test",
                "-s",
                "emulator-5554",
                "shell",
                "dumpsys",
                "notification",
            ),
        ]
        calls = [argv for argv, _ in runner.calls]
        self.assertEqual(expected_calls, calls)
        tokens = {token for argv in calls for token in argv}
        self.assertTrue({"am", "start", "input", "tap", "screencap"}.isdisjoint(tokens))
        self.assertTrue(all(timeout == 35.0 for _, timeout in runner.calls))
        self.assertEqual([], runner.results)

    def test_appfunctions_have_priority_over_every_other_surface(self) -> None:
        output, _, _ = _run_probe(
            app_functions=(
                '{"com.tencent.mm":[{"functionId":"sendMessage"},'
                '{"functionIdentifier":"openConversation"}]}\n'
            ),
            shortcuts=CONVERSATION_SHORTCUT,
            notifications=_notification_dump(include_remote_input=True),
        )

        self.assertEqual(
            ["openConversation", "sendMessage"],
            output["appFunctions"]["ids"],
        )
        self.assertEqual("appfunctions", output["routing"]["selected"])

    def test_remote_input_has_priority_over_conversation_shortcut(self) -> None:
        output, _, _ = _run_probe(
            shortcuts=CONVERSATION_SHORTCUT,
            notifications=_notification_dump(include_remote_input=True),
        )

        self.assertEqual(1, output["shortcuts"]["conversationCount"])
        self.assertEqual(1, output["notifications"]["activeCount"])
        self.assertEqual(1, output["notifications"]["remoteInputCount"])
        self.assertEqual(
            "notification_remote_input",
            output["routing"]["selected"],
        )

    def test_person_bound_shortcut_is_selected_when_no_stronger_surface_exists(self) -> None:
        output, _, _ = _run_probe(shortcuts=CONVERSATION_SHORTCUT)

        self.assertEqual(1, output["shortcuts"]["conversationCount"])
        self.assertTrue(output["shortcuts"]["items"][0]["hasPersons"])
        self.assertTrue(output["shortcuts"]["items"][0]["hasCategories"])
        self.assertEqual("conversation_shortcut", output["routing"]["selected"])

    def test_notification_package_matching_rejects_substring_packages(self) -> None:
        lookalike_dump = (
            _notification_dump(
                package_name="com.tencent.mm.beta",
                include_remote_input=True,
                importance="HIGH",
            )
            + _notification_dump(
                package_name="com.tencent.mmhelper",
                include_remote_input=True,
                importance="HIGH",
            )
        )
        output, _, _ = _run_probe(notifications=lookalike_dump)

        self.assertEqual("UNKNOWN", output["notifications"]["importance"])
        self.assertEqual(0, output["notifications"]["activeCount"])
        self.assertEqual(0, output["notifications"]["remoteInputCount"])
        self.assertEqual("blocked_no_semantic_surface", output["routing"]["selected"])


if __name__ == "__main__":
    unittest.main()

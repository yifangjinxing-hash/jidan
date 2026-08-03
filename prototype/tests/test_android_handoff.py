from __future__ import annotations

from pathlib import Path
import sys
import unittest


PROTOTYPE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROTOTYPE_ROOT))

from jidan.android_appfunctions import CommandResult  # noqa: E402
from jidan.android_handoff import (  # noqa: E402
    AdbFixedAndroidFrontDoor,
    AndroidForegroundVerificationError,
    AndroidHandoffError,
    AndroidPackageIdentityError,
    FixedAndroidFrontDoor,
)


PACKAGE = "com.example.pay"
VERSION_CODE = 123
DEVICE_SDK = 35
ANDROID_USER = 10
CERTIFICATE = "ab" * 32
OLD_CERTIFICATE = "cd" * 32
LAUNCHER = f"{PACKAGE}/.MainActivity$Launcher"
FOREGROUND = f"{PACKAGE}/.PayHomeActivity$Home"
BASE_APK = "/data/app/example/base.apk"


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


def front_door() -> FixedAndroidFrontDoor:
    return FixedAndroidFrontDoor(
        package_name=PACKAGE,
        version_code=VERSION_CODE,
        certificate_sha256=CERTIFICATE,
        launcher_components=frozenset({LAUNCHER}),
        foreground_components=frozenset({FOREGROUND}),
    )


def legacy_signer(digest: str = CERTIFICATE) -> str:
    return f"Signer #1 certificate SHA-256 digest: {digest.upper()}\n"


def ranged_signers() -> str:
    return (
        "Signer (minSdkVersion=1, maxSdkVersion=32) certificate SHA-256 "
        f"digest: {OLD_CERTIFICATE}\n"
        "Signer (minSdkVersion=33, maxSdkVersion=2147483647) certificate "
        f"SHA-256 digest: {CERTIFICATE}\n"
    )


def identity_responses(
    *,
    version_code: int = VERSION_CODE,
    certificate_output: str | None = None,
    base_apk: str = BASE_APK,
    user: int = ANDROID_USER,
) -> list[CommandResult]:
    return [
        CommandResult(0, "device\n", ""),
        CommandResult(0, f"{DEVICE_SDK}\n", ""),
        CommandResult(0, f"{user}\n", ""),
        CommandResult(0, f"versionCode={version_code} minSdk=23\n", ""),
        CommandResult(
            0,
            f"package:{base_apk}\n"
            "package:/data/app/example/split_config.en.apk\n",
            "",
        ),
        CommandResult(0, "1 file pulled\n", ""),
        CommandResult(0, certificate_output or legacy_signer(), ""),
    ]


def activity(component: str, *, user: int = ANDROID_USER) -> CommandResult:
    return CommandResult(
        0,
        f"topResumedActivity=ActivityRecord{{abc u{user} {component} t42}}\n",
        "",
    )


def window(component: str, *, user: int = ANDROID_USER) -> CommandResult:
    return CommandResult(
        0,
        f"mCurrentFocus=Window{{def u{user} {component}}}\n",
        "",
    )


def handoff_responses() -> list[CommandResult]:
    return [
        CommandResult(0, f"{LAUNCHER}\n", ""),
        CommandResult(0, f"Status: OK\nActivity: {LAUNCHER}\n", ""),
        activity(FOREGROUND),
        window(FOREGROUND),
        activity(FOREGROUND),
        window(FOREGROUND),
    ]


def success_responses(*, certificate_output: str | None = None) -> list[CommandResult]:
    return [
        *identity_responses(certificate_output=certificate_output),
        *handoff_responses(),
        *identity_responses(certificate_output=certificate_output),
    ]


class FixedAndroidFrontDoorTests(unittest.TestCase):
    def test_exact_identity_explicit_launch_and_post_launch_reverification(self):
        runner = FakeRunner(*success_responses())
        evidence = AdbFixedAndroidFrontDoor(
            front_door(),
            runner,
            sleeper=lambda _: None,
        ).open()

        self.assertEqual(PACKAGE, evidence.package_name)
        self.assertEqual(VERSION_CODE, evidence.version_code)
        self.assertEqual(CERTIFICATE, evidence.certificate_sha256)
        self.assertEqual(DEVICE_SDK, evidence.device_sdk)
        self.assertEqual(ANDROID_USER, evidence.android_user_id)
        self.assertIsNone(evidence.signer_minimum_sdk)
        self.assertIsNone(evidence.signer_maximum_sdk)
        self.assertEqual(LAUNCHER, evidence.launcher_component)
        self.assertEqual(FOREGROUND, evidence.foreground_component)
        self.assertEqual(64, len(evidence.base_apk_path_sha256))
        self.assertEqual(64, len(evidence.evidence_sha256))
        self.assertFalse(hasattr(evidence, "raw_stdout"))

        commands = [call[0] for call in runner.calls]
        signer_commands = [command for command in commands if command[0] == "java"]
        self.assertEqual(2, len(signer_commands))
        for signer in signer_commands:
            self.assertEqual(("-jar", "apksigner.jar", "verify"), signer[1:4])
            self.assertEqual(
                str(DEVICE_SDK),
                signer[signer.index("--min-sdk-version") + 1],
            )
            self.assertEqual(
                str(DEVICE_SDK),
                signer[signer.index("--max-sdk-version") + 1],
            )
        launch = next(
            command
            for command in commands
            if command[:4] == ("adb", "shell", "am", "start")
        )
        self.assertEqual(
            LAUNCHER.replace("$", r"\$"),
            launch[launch.index("-n") + 1],
        )
        self.assertNotIn("'", launch[launch.index("-n") + 1])
        self.assertNotIn("--es", launch)
        self.assertNotIn("--ei", launch)
        self.assertEqual(2, sum("activities" in command for command in commands))
        self.assertEqual(2, sum("windows" in command for command in commands))

    def test_v31_sdk_ranged_signer_selects_only_current_device_certificate(self):
        runner = FakeRunner(*success_responses(certificate_output=ranged_signers()))

        evidence = AdbFixedAndroidFrontDoor(
            front_door(),
            runner,
            sleeper=lambda _: None,
        ).open()

        self.assertEqual(33, evidence.signer_minimum_sdk)
        self.assertEqual(2147483647, evidence.signer_maximum_sdk)
        self.assertEqual(CERTIFICATE, evidence.certificate_sha256)

    def test_malformed_or_overlapping_ranged_signers_fail_closed(self):
        malformed = (
            "Signer (minSdkVersion=1, maxSdkVersion=40) certificate SHA-256 "
            f"digest: {CERTIFICATE}\n"
            "Signer (minSdkVersion=35, maxSdkVersion=99) certificate SHA-256 "
            f"digest: {CERTIFICATE}\n"
        )
        runner = FakeRunner(*identity_responses(certificate_output=malformed))

        with self.assertRaisesRegex(AndroidPackageIdentityError, "overlapping"):
            AdbFixedAndroidFrontDoor(front_door(), runner).open()

    def test_shell_metacharacters_and_batch_java_are_rejected(self):
        with self.assertRaises(ValueError):
            FixedAndroidFrontDoor(
                package_name="com.example.pay;id",
                version_code=1,
                certificate_sha256=CERTIFICATE,
                launcher_components=frozenset({LAUNCHER}),
                foreground_components=frozenset({FOREGROUND}),
            )
        with self.assertRaises(ValueError):
            FixedAndroidFrontDoor(
                package_name=PACKAGE,
                version_code=1,
                certificate_sha256=CERTIFICATE,
                launcher_components=frozenset({f"{LAUNCHER};echo pwned"}),
                foreground_components=frozenset({FOREGROUND}),
            )
        with self.assertRaises(ValueError):
            AdbFixedAndroidFrontDoor(front_door(), FakeRunner(), serial="x;whoami")
        with self.assertRaises(ValueError):
            AdbFixedAndroidFrontDoor(
                front_door(),
                FakeRunner(),
                adb_path="adb.cmd",
            )
        with self.assertRaises(ValueError):
            AdbFixedAndroidFrontDoor(
                front_door(),
                FakeRunner(),
                java_path="java.cmd",
            )
        with self.assertRaises(ValueError):
            AdbFixedAndroidFrontDoor(
                front_door(),
                FakeRunner(),
                apksigner_jar_path="apksigner.bat",
            )

    def test_version_mismatch_fails_before_pull_or_launch(self):
        runner = FakeRunner(*identity_responses(version_code=124))

        with self.assertRaises(AndroidPackageIdentityError):
            AdbFixedAndroidFrontDoor(front_door(), runner).open()

        self.assertEqual(4, len(runner.calls))

    def test_certificate_mismatch_fails_before_resolve_or_launch(self):
        runner = FakeRunner(
            *identity_responses(certificate_output=legacy_signer(OLD_CERTIFICATE))
        )

        with self.assertRaises(AndroidPackageIdentityError):
            AdbFixedAndroidFrontDoor(front_door(), runner).open()

        self.assertEqual(7, len(runner.calls))

    def test_wrong_dispatch_activity_is_not_a_fake_success(self):
        handoff = handoff_responses()
        handoff[1] = CommandResult(
            0,
            "Status: ok\nActivity: com.example.attacker/.Overlay\n",
            "",
        )
        runner = FakeRunner(*identity_responses(), *handoff)

        with self.assertRaises(AndroidHandoffError):
            AdbFixedAndroidFrontDoor(front_door(), runner).open()

        self.assertEqual(9, len(runner.calls))

    def test_unexpected_foreground_is_not_a_success(self):
        handoff = handoff_responses()
        unexpected = "com.example.attacker/.Overlay"
        handoff[2] = activity(unexpected)
        handoff[3] = window(unexpected)
        runner = FakeRunner(*identity_responses(), *handoff)

        with self.assertRaises(AndroidForegroundVerificationError):
            AdbFixedAndroidFrontDoor(
                front_door(),
                runner,
                sleeper=lambda _: None,
            ).open()

    def test_foreground_must_belong_to_current_android_user(self):
        handoff = handoff_responses()
        handoff[2] = activity(FOREGROUND, user=0)
        handoff[3] = window(FOREGROUND, user=0)
        runner = FakeRunner(*identity_responses(), *handoff)

        with self.assertRaisesRegex(
            AndroidForegroundVerificationError,
            "different Android user",
        ):
            AdbFixedAndroidFrontDoor(
                front_door(),
                runner,
                sleeper=lambda _: None,
            ).open()

    def test_activity_window_mismatch_must_reset_stability(self):
        foreground_samples = [
            activity(FOREGROUND),
            window(LAUNCHER),
            activity(FOREGROUND),
            window(FOREGROUND),
            activity(FOREGROUND),
            window(FOREGROUND),
        ]
        runner = FakeRunner(
            *identity_responses(),
            *handoff_responses()[:2],
            *foreground_samples,
            *identity_responses(),
        )

        evidence = AdbFixedAndroidFrontDoor(
            front_door(),
            runner,
            foreground_attempts=3,
            sleeper=lambda _: None,
        ).open()

        self.assertEqual(FOREGROUND, evidence.foreground_component)

    def test_base_apk_snapshot_change_after_dispatch_is_outcome_unknown(self):
        runner = FakeRunner(
            *identity_responses(),
            *handoff_responses(),
            *identity_responses(base_apk="/data/app/reinstalled/base.apk"),
        )

        with self.assertRaisesRegex(AndroidPackageIdentityError, "changed during"):
            AdbFixedAndroidFrontDoor(
                front_door(),
                runner,
                sleeper=lambda _: None,
            ).open()

        self.assertTrue(
            any(
                call[0][:4] == ("adb", "shell", "am", "start")
                for call in runner.calls
            )
        )


if __name__ == "__main__":
    unittest.main()

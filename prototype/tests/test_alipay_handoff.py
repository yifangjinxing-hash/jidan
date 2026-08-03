from __future__ import annotations

from pathlib import Path
import inspect
import sys
import unittest


PROTOTYPE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROTOTYPE_ROOT))

import jidan  # noqa: E402
from jidan.alipay_handoff import (  # noqa: E402
    ALIPAY_HANDOFF_CAPABILITY_ID,
    ALIPAY_HANDOFF_OPENED,
    ALIPAY_NEXT_ACTION,
    ALIPAY_PACKAGE,
    AdbAlipayHandoffAdapter,
)
from jidan.android_appfunctions import CommandResult  # noqa: E402
from jidan.android_handoff import (  # noqa: E402
    AdbFixedAndroidFrontDoor,
    FixedAndroidFrontDoor,
)
from jidan.models import Effect, Step, TaskPlan  # noqa: E402
from jidan.policy import PolicyEngine, issue_grant  # noqa: E402
from jidan.registry import CapabilityOutputError, CapabilityRegistry  # noqa: E402
from jidan.runtime import JidanRuntime  # noqa: E402


VERSION_CODE = 20260803
DEVICE_SDK = 35
ANDROID_USER = 0
CERTIFICATE = "12" * 32
LAUNCHER = f"{ALIPAY_PACKAGE}/.AlipayLogin"
FOREGROUND = f"{ALIPAY_PACKAGE}/.AlipayHome"
BASE_APK = "/data/app/alipay/base.apk"


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


def front_door(*, version_code: int = VERSION_CODE) -> FixedAndroidFrontDoor:
    return FixedAndroidFrontDoor(
        package_name=ALIPAY_PACKAGE,
        version_code=version_code,
        certificate_sha256=CERTIFICATE,
        launcher_components=frozenset({LAUNCHER}),
        foreground_components=frozenset({FOREGROUND}),
    )


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


def handoff_responses(*, foreground: str = FOREGROUND) -> list[CommandResult]:
    return [
        CommandResult(0, f"{LAUNCHER}\n", ""),
        CommandResult(0, f"Status: ok\nActivity: {LAUNCHER}\n", ""),
        activity(foreground),
        window(foreground),
        activity(foreground),
        window(foreground),
    ]


def success_responses() -> list[CommandResult]:
    return [*identity_responses(), *handoff_responses(), *identity_responses()]


class AlipayHandoffTests(unittest.TestCase):
    def adapter(self, *responses):
        runner = FakeRunner(*responses)
        return AdbAlipayHandoffAdapter(front_door(), runner), runner

    def test_capability_is_empty_input_confirmed_external_handoff(self):
        adapter, _ = self.adapter()
        capability = adapter.capability()

        self.assertNotIn(
            "opener",
            inspect.signature(AdbAlipayHandoffAdapter).parameters,
        )
        self.assertIsInstance(
            adapter._front_door_opener,
            AdbFixedAndroidFrontDoor,
        )
        self.assertEqual(ALIPAY_HANDOFF_CAPABILITY_ID, capability.id)
        self.assertEqual(Effect.EXTERNAL, capability.effect)
        self.assertTrue(capability.requires_confirmation)
        self.assertFalse(capability.reversible)
        self.assertEqual({}, capability.input_schema["properties"])
        self.assertFalse(capability.input_schema["additionalProperties"])
        properties = capability.output_schema["properties"]
        self.assertEqual(VERSION_CODE, properties["versionCode"]["const"])
        self.assertEqual(CERTIFICATE, properties["certificateSha256"]["const"])
        self.assertEqual([LAUNCHER], properties["launcherComponent"]["enum"])
        self.assertEqual([FOREGROUND], properties["foregroundComponent"]["enum"])
        self.assertEqual("os_frontdoor", properties["bindingAuthority"]["const"])
        self.assertEqual(
            "adb_verified_foreground",
            properties["guaranteeLevel"]["const"],
        )
        self.assertTrue(properties["hostPinsMatched"]["const"])
        self.assertNotIn("identityVerified", properties)
        self.assertFalse(properties["paid"]["const"])

    def test_output_proves_only_opened_handoff_and_never_payment_success(self):
        adapter, runner = self.adapter(*success_responses())
        registry = CapabilityRegistry()
        adapter.register(registry)

        output = registry.invoke(ALIPAY_HANDOFF_CAPABILITY_ID, {})

        self.assertEqual([], runner.responses)
        self.assertEqual(ALIPAY_HANDOFF_OPENED, output["status"])
        self.assertEqual(ALIPAY_NEXT_ACTION, output["nextAction"])
        self.assertTrue(output["hostPinsMatched"])
        self.assertNotIn("identityVerified", output)
        self.assertEqual(DEVICE_SDK, output["deviceSdk"])
        self.assertEqual(ANDROID_USER, output["androidUserId"])
        self.assertEqual("os_frontdoor", output["bindingAuthority"])
        self.assertEqual("adb_verified_foreground", output["guaranteeLevel"])
        for key in (
            "amountSetByJidan",
            "recipientSelectedByJidan",
            "paymentAttemptedByJidan",
            "paid",
            "committed",
            "verified",
        ):
            self.assertIs(False, output[key])
        self.assertFalse(any("raw" in key.lower() for key in output))

    def test_amount_recipient_uri_and_qr_injection_are_rejected_before_runner(self):
        adapter, runner = self.adapter()
        registry = CapabilityRegistry()
        adapter.register(registry)

        for arguments in (
            {"amount": "0.01"},
            {"recipient": "attacker"},
            {"uri": "alipays://platformapi/startapp?appId=evil"},
            {"qr": "data"},
            {"orderToken": "token"},
        ):
            with self.subTest(arguments=arguments):
                with self.assertRaises(ValueError):
                    registry.invoke(ALIPAY_HANDOFF_CAPABILITY_ID, arguments)
        self.assertEqual([], runner.calls)

    def test_confirmation_gate_prevents_runner_until_step_is_approved(self):
        adapter, runner = self.adapter(*success_responses())
        registry = CapabilityRegistry()
        capability = adapter.register(registry)
        runtime = JidanRuntime(registry, PolicyEngine(b"alipay-test-secret"))
        plan = TaskPlan(
            "open-alipay",
            "Open Alipay and let the user take over",
            (Step("handoff", capability.id, {}),),
        )

        grant = issue_grant(
            b"alipay-test-secret",
            plan,
            {capability.id},
            capability.scopes,
            Effect.EXTERNAL,
            capability_digests=registry.definition_digests({capability.id}),
        )
        pending = runtime.execute(plan, grant)
        self.assertEqual("awaiting_confirmation", pending.status)
        self.assertEqual([], runner.calls)

        approved_grant = issue_grant(
            b"alipay-test-secret",
            plan,
            {capability.id},
            capability.scopes,
            Effect.EXTERNAL,
            approved_steps={"handoff"},
            capability_digests=registry.definition_digests({capability.id}),
        )
        completed = runtime.execute(plan, approved_grant)
        self.assertEqual("completed", completed.status)
        self.assertEqual([], runner.responses)

    def test_foreground_verification_failure_is_unknown_not_success_or_retry(self):
        unexpected = "com.example.attacker/.Overlay"
        adapter, runner = self.adapter(
            *identity_responses(),
            *handoff_responses(foreground=unexpected),
        )
        registry = CapabilityRegistry()
        capability = adapter.register(registry)
        runtime = JidanRuntime(registry, PolicyEngine(b"unknown-test-secret"))
        plan = TaskPlan(
            "unknown-alipay",
            "Do not call a failed handoff successful",
            (Step("handoff", capability.id, {}),),
        )
        grant = issue_grant(
            b"unknown-test-secret",
            plan,
            {capability.id},
            capability.scopes,
            Effect.EXTERNAL,
            approved_steps={"handoff"},
            capability_digests=registry.definition_digests({capability.id}),
        )

        result = runtime.execute(plan, grant)

        self.assertEqual("unknown", result.status)
        self.assertEqual("outcome_unknown", result.receipts[0]["status"])
        self.assertEqual(11, len(runner.calls))

    def test_provider_cannot_fake_paid_true_against_constant_output_contract(self):
        adapter, _ = self.adapter(*success_responses())
        forged = dict(adapter.open_handoff({}))
        forged["paid"] = True
        forged["verified"] = True
        registry = CapabilityRegistry()
        capability = adapter.capability()
        registry.register(capability, lambda _: forged)

        with self.assertRaises(CapabilityOutputError):
            registry.invoke(capability.id, {})

    def test_public_package_exports_are_available(self):
        self.assertIs(AdbAlipayHandoffAdapter, jidan.AdbAlipayHandoffAdapter)
        self.assertIs(FixedAndroidFrontDoor, jidan.FixedAndroidFrontDoor)
        self.assertEqual(
            ALIPAY_HANDOFF_CAPABILITY_ID,
            jidan.ALIPAY_HANDOFF_CAPABILITY_ID,
        )


if __name__ == "__main__":
    unittest.main()

"""A deliberately narrow Alipay handoff built on the fixed Android front door.

This capability opens a host-pinned, user-controlled Alipay surface.  It cannot
receive an amount, recipient, QR code, URI, order token, or payment command, and
it never claims that a payment was attempted or completed.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .android_appfunctions import CommandRunner
from .android_handoff import (
    ACTION_MAIN,
    AdbFixedAndroidFrontDoor,
    AndroidHandoffEvidence,
    FixedAndroidFrontDoor,
)
from .models import Capability, Effect
from .registry import CapabilityRegistry


ALIPAY_PACKAGE = "com.eg.android.AlipayGphone"
ALIPAY_HANDOFF_CAPABILITY_ID = "android.alipay.open_user_handoff"
ALIPAY_HANDOFF_OPENED = "handoff_opened"
ALIPAY_NEXT_ACTION = (
    "user_choose_recipient_enter_amount_and_confirm_in_alipay"
)


class AlipayHandoffError(RuntimeError):
    """Pinned Alipay handoff evidence was missing or internally inconsistent."""


class AdbAlipayHandoffAdapter:
    """Open Alipay's fixed front door and hand all choices back to the user."""

    def __init__(
        self,
        front_door: FixedAndroidFrontDoor,
        runner: CommandRunner | None = None,
        *,
        adb_path: str = "adb",
        java_path: str = "java",
        apksigner_jar_path: str = "apksigner.jar",
        serial: str | None = None,
        timeout_seconds: float = 35.0,
        foreground_attempts: int = 8,
        poll_interval_seconds: float = 0.25,
    ) -> None:
        if front_door.package_name != ALIPAY_PACKAGE:
            raise ValueError(
                f"Alipay handoff must pin package {ALIPAY_PACKAGE!r}"
            )
        self.front_door = front_door
        self._front_door_opener = AdbFixedAndroidFrontDoor(
            front_door,
            runner,
            adb_path=adb_path,
            java_path=java_path,
            apksigner_jar_path=apksigner_jar_path,
            serial=serial,
            timeout_seconds=timeout_seconds,
            foreground_attempts=foreground_attempts,
            poll_interval_seconds=poll_interval_seconds,
        )

    def capability(self) -> Capability:
        digest_schema = {
            "type": "string",
            "minLength": 64,
            "maxLength": 64,
        }
        properties: dict[str, Mapping[str, Any]] = {
            "status": {"const": ALIPAY_HANDOFF_OPENED},
            "packageName": {"const": self.front_door.package_name},
            "versionCode": {"const": self.front_door.version_code},
            "certificateSha256": {
                "const": self.front_door.certificate_sha256,
            },
            "launcherComponent": {
                "type": "string",
                "enum": sorted(self.front_door.launcher_components),
            },
            "foregroundComponent": {
                "type": "string",
                "enum": sorted(self.front_door.foreground_components),
            },
            "deviceSdk": {"type": "integer"},
            "androidUserId": {"type": "integer"},
            "signerMinimumSdk": {"type": ["integer", "null"]},
            "signerMaximumSdk": {"type": ["integer", "null"]},
            "baseApkPathSha256": digest_schema,
            "hostPinsMatched": {"const": True},
            "bindingAuthority": {"const": "os_frontdoor"},
            "guaranteeLevel": {"const": "adb_verified_foreground"},
            "amountSetByJidan": {"const": False},
            "recipientSelectedByJidan": {"const": False},
            "paymentAttemptedByJidan": {"const": False},
            "paid": {"const": False},
            "committed": {"const": False},
            "verified": {"const": False},
            "nextAction": {"const": ALIPAY_NEXT_ACTION},
            "dispatchSha256": digest_schema,
            "foregroundEvidenceSha256": digest_schema,
            "evidenceSha256": digest_schema,
        }
        return Capability(
            id=ALIPAY_HANDOFF_CAPABILITY_ID,
            app=ALIPAY_PACKAGE,
            description=(
                "Open a host-pinned Alipay launcher surface, then hand recipient, "
                "amount, and final payment confirmation entirely to the user."
            ),
            # Opening a launcher surface changes no user data. Treat it as
            # low-risk navigation, distinct from a WRITE or payment action.
            effect=Effect.NAVIGATION,
            scopes=frozenset(
                {
                    ACTION_MAIN,
                    f"android.package.{ALIPAY_PACKAGE}",
                    "alipay.user_handoff.open",
                }
            ),
            requires_confirmation=False,
            reversible=True,
            input_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": properties,
                "required": list(properties),
                "additionalProperties": False,
            },
            adapter="android.adb.fixed-front-door.alipay",
        )

    def register(self, registry: CapabilityRegistry) -> Capability:
        capability = self.capability()
        registry.register(capability, self.open_handoff)
        return capability

    def open_handoff(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        if not isinstance(arguments, Mapping):
            raise TypeError("Alipay handoff arguments must be an object")
        if arguments:
            raise ValueError(
                "Alipay handoff accepts no amount, recipient, URI, QR, or payment data"
            )

        evidence = self._front_door_opener.open()
        if not isinstance(evidence, AndroidHandoffEvidence):
            raise AlipayHandoffError("front-door opener returned invalid evidence")
        if (
            evidence.package_name != self.front_door.package_name
            or evidence.version_code != self.front_door.version_code
            or evidence.certificate_sha256 != self.front_door.certificate_sha256
            or evidence.launcher_component not in self.front_door.launcher_components
            or evidence.foreground_component
            not in self.front_door.foreground_components
        ):
            raise AlipayHandoffError(
                "front-door evidence does not match the pinned Alipay policy"
            )

        return {
            "status": ALIPAY_HANDOFF_OPENED,
            "packageName": evidence.package_name,
            "versionCode": evidence.version_code,
            "certificateSha256": evidence.certificate_sha256,
            "launcherComponent": evidence.launcher_component,
            "foregroundComponent": evidence.foreground_component,
            "deviceSdk": evidence.device_sdk,
            "androidUserId": evidence.android_user_id,
            "signerMinimumSdk": evidence.signer_minimum_sdk,
            "signerMaximumSdk": evidence.signer_maximum_sdk,
            "baseApkPathSha256": evidence.base_apk_path_sha256,
            "hostPinsMatched": True,
            "bindingAuthority": "os_frontdoor",
            "guaranteeLevel": "adb_verified_foreground",
            "amountSetByJidan": False,
            "recipientSelectedByJidan": False,
            "paymentAttemptedByJidan": False,
            "paid": False,
            "committed": False,
            "verified": False,
            "nextAction": ALIPAY_NEXT_ACTION,
            "dispatchSha256": evidence.dispatch_sha256,
            "foregroundEvidenceSha256": evidence.foreground_evidence_sha256,
            "evidenceSha256": evidence.evidence_sha256,
        }

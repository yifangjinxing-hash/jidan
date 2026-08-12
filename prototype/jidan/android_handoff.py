"""Verified, fixed Android front-door handoffs over an argv-only ADB runner.

The helper intentionally supports only a host-configured launcher surface.  It
does not accept a caller supplied Intent, URI, component, extra, amount, or
recipient.  A successful result proves only that an APK with the pinned
identity was resolved, explicitly started, and observed in both Android's
resumed-activity and focused-window views for two consecutive samples.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
import re
import subprocess
import time

from .android_appfunctions import CommandResult, CommandRunner, SubprocessCommandRunner


ACTION_MAIN = "android.intent.action.MAIN"
CATEGORY_LAUNCHER = "android.intent.category.LAUNCHER"

_ANDROID_PACKAGE = re.compile(
    r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$"
)
_ANDROID_COMPONENT = re.compile(
    r"^(?P<package>[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+)"
    r"/(?P<activity>\.?[A-Za-z][A-Za-z0-9_.$]*(?:\.[A-Za-z0-9_.$]+)*)$"
)
_ADB_SERIAL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_VERSION_CODE = re.compile(r"(?m)^\s*versionCode=(\d+)\b")
_LEGACY_CERTIFICATE_DIGEST = re.compile(
    r"^Signer #(?P<number>[1-9]\d*) certificate SHA-256 digest:\s*"
    r"(?P<digest>[0-9a-f]{64})$",
    re.IGNORECASE,
)
_RANGED_CERTIFICATE_DIGEST = re.compile(
    r"^Signer \(minSdkVersion=(?P<minimum>\d+)"
    r"(?: \(dev release=true\))?, maxSdkVersion=(?P<maximum>\d+)\) "
    r"certificate SHA-256 digest:\s*(?P<digest>[0-9a-f]{64})$",
    re.IGNORECASE,
)
_AM_STATUS = re.compile(r"(?im)^\s*Status:\s*(\S+)\s*$")
_AM_ACTIVITY = re.compile(r"(?im)^\s*Activity:\s*(\S+)\s*$")
_AM_ERROR = re.compile(r"(?im)^\s*(?:Error|Exception)(?: type \d+)?:")
_TOP_RESUMED_ACTIVITY = re.compile(
    r"(?im)^\s*topResumedActivity=.*?\bu(?P<user>\d+)\s+(?P<activity>\S+)"
)
_CURRENT_FOCUS = re.compile(
    r"(?im)^\s*mCurrentFocus=Window\{[^\n]*?\bu(?P<user>\d+)\s+"
    r"(?P<activity>\S+)\}"
)


class AndroidHandoffError(RuntimeError):
    """A fixed Android handoff could not be proven safely."""


class AndroidPackageIdentityError(AndroidHandoffError):
    """The installed package did not match the host's exact identity pin."""


class AndroidFrontDoorUnavailable(AndroidHandoffError):
    """The configured launcher component could not be resolved exactly."""


class AndroidForegroundVerificationError(AndroidHandoffError):
    """Android did not provide consistent allowlisted foreground evidence."""


@dataclass(frozen=True, slots=True)
class _SignerCertificate:
    digest: str
    minimum_sdk: int | None
    maximum_sdk: int | None

    def __post_init__(self) -> None:
        digest = self.digest.lower()
        if _HEX_SHA256.fullmatch(digest) is None:
            raise ValueError("signer digest is invalid")
        object.__setattr__(self, "digest", digest)
        if (self.minimum_sdk is None) != (self.maximum_sdk is None):
            raise ValueError("signer SDK range must be wholly present or absent")
        if self.minimum_sdk is not None and (
            self.minimum_sdk < 1
            or self.maximum_sdk is None
            or self.maximum_sdk < self.minimum_sdk
        ):
            raise ValueError("signer SDK range is invalid")

    def covers(self, sdk: int) -> bool:
        return (
            self.minimum_sdk is None
            or self.maximum_sdk is None
            or self.minimum_sdk <= sdk <= self.maximum_sdk
        )


@dataclass(frozen=True, slots=True)
class _PackageIdentityEvidence:
    device_sdk: int
    android_user_id: int
    version_code: int
    certificate_sha256: str
    signer_minimum_sdk: int | None
    signer_maximum_sdk: int | None
    base_apk_path_sha256: str


@dataclass(frozen=True, slots=True)
class FixedAndroidFrontDoor:
    """Host-owned identity and component policy for one installed app version."""

    package_name: str
    version_code: int
    certificate_sha256: str
    launcher_components: frozenset[str]
    foreground_components: frozenset[str]

    def __post_init__(self) -> None:
        if _ANDROID_PACKAGE.fullmatch(self.package_name) is None:
            raise ValueError(f"invalid Android package name: {self.package_name!r}")
        if (
            isinstance(self.version_code, bool)
            or not isinstance(self.version_code, int)
            or self.version_code < 1
        ):
            raise ValueError("version_code must be a positive integer")
        certificate = self.certificate_sha256.replace(":", "").lower()
        if _HEX_SHA256.fullmatch(certificate) is None:
            raise ValueError("certificate_sha256 must be exactly 32 bytes of hex")
        object.__setattr__(self, "certificate_sha256", certificate)

        launchers = frozenset(self.launcher_components)
        foregrounds = frozenset(self.foreground_components)
        if not launchers:
            raise ValueError("launcher_components must not be empty")
        if not foregrounds:
            raise ValueError("foreground_components must not be empty")
        for label, components in (
            ("launcher", launchers),
            ("foreground", foregrounds),
        ):
            for component in components:
                match = _ANDROID_COMPONENT.fullmatch(component)
                if match is None or match.group("package") != self.package_name:
                    raise ValueError(
                        f"invalid {label} component for {self.package_name}: {component!r}"
                    )
        object.__setattr__(self, "launcher_components", launchers)
        object.__setattr__(self, "foreground_components", foregrounds)


@dataclass(frozen=True, slots=True)
class AndroidHandoffEvidence:
    """Redacted evidence for an opened front door; no raw shell output."""

    package_name: str
    version_code: int
    certificate_sha256: str
    device_sdk: int
    android_user_id: int
    signer_minimum_sdk: int | None
    signer_maximum_sdk: int | None
    base_apk_path_sha256: str
    launcher_component: str
    foreground_component: str
    dispatch_sha256: str
    foreground_evidence_sha256: str

    def __post_init__(self) -> None:
        if _ANDROID_PACKAGE.fullmatch(self.package_name) is None:
            raise ValueError("evidence package_name is invalid")
        if (
            isinstance(self.version_code, bool)
            or not isinstance(self.version_code, int)
            or self.version_code < 1
        ):
            raise ValueError("evidence version_code must be a positive integer")
        if (
            isinstance(self.device_sdk, bool)
            or not isinstance(self.device_sdk, int)
            or self.device_sdk < 1
        ):
            raise ValueError("evidence device_sdk must be a positive integer")
        if (
            isinstance(self.android_user_id, bool)
            or not isinstance(self.android_user_id, int)
            or self.android_user_id < 0
        ):
            raise ValueError("evidence android_user_id must not be negative")
        certificate = self.certificate_sha256.replace(":", "").lower()
        if _HEX_SHA256.fullmatch(certificate) is None:
            raise ValueError("evidence certificate_sha256 is invalid")
        object.__setattr__(self, "certificate_sha256", certificate)
        signer = _SignerCertificate(
            certificate,
            self.signer_minimum_sdk,
            self.signer_maximum_sdk,
        )
        if not signer.covers(self.device_sdk):
            raise ValueError("evidence signer range does not cover the device SDK")
        base_apk_digest = self.base_apk_path_sha256.lower()
        if _HEX_SHA256.fullmatch(base_apk_digest) is None:
            raise ValueError("evidence base APK path digest is invalid")
        object.__setattr__(self, "base_apk_path_sha256", base_apk_digest)
        for label, component in (
            ("launcher", self.launcher_component),
            ("foreground", self.foreground_component),
        ):
            match = _ANDROID_COMPONENT.fullmatch(component)
            if match is None or match.group("package") != self.package_name:
                raise ValueError(f"evidence {label} component is invalid")
        dispatch_digest = self.dispatch_sha256.lower()
        foreground_digest = self.foreground_evidence_sha256.lower()
        if _HEX_SHA256.fullmatch(dispatch_digest) is None:
            raise ValueError("evidence dispatch digest is invalid")
        if _HEX_SHA256.fullmatch(foreground_digest) is None:
            raise ValueError("evidence foreground digest is invalid")
        object.__setattr__(self, "dispatch_sha256", dispatch_digest)
        object.__setattr__(
            self,
            "foreground_evidence_sha256",
            foreground_digest,
        )

    @property
    def evidence_sha256(self) -> str:
        payload = {
            "packageName": self.package_name,
            "versionCode": self.version_code,
            "certificateSha256": self.certificate_sha256,
            "deviceSdk": self.device_sdk,
            "androidUserId": self.android_user_id,
            "signerMinimumSdk": self.signer_minimum_sdk,
            "signerMaximumSdk": self.signer_maximum_sdk,
            "baseApkPathSha256": self.base_apk_path_sha256,
            "launcherComponent": self.launcher_component,
            "foregroundComponent": self.foreground_component,
            "dispatchSha256": self.dispatch_sha256,
            "foregroundEvidenceSha256": self.foreground_evidence_sha256,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class AdbFixedAndroidFrontDoor:
    """Open and verify one fixed Android launcher surface."""

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
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not adb_path or "\x00" in adb_path:
            raise ValueError("adb_path must be a non-empty executable path")
        if Path(adb_path).suffix.lower() in {".bat", ".cmd"}:
            raise ValueError("adb_path must not be a batch or command script")
        if not java_path or "\x00" in java_path:
            raise ValueError("java_path must be a non-empty executable path")
        if Path(java_path).suffix.lower() in {".bat", ".cmd"}:
            raise ValueError("java_path must not be a batch or command script")
        if not apksigner_jar_path or "\x00" in apksigner_jar_path:
            raise ValueError("apksigner_jar_path must be a non-empty JAR path")
        if Path(apksigner_jar_path).suffix.lower() != ".jar":
            raise ValueError("apksigner_jar_path must name a .jar file")
        if serial is not None and _ADB_SERIAL.fullmatch(serial) is None:
            raise ValueError(f"invalid adb serial: {serial!r}")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if (
            isinstance(foreground_attempts, bool)
            or not isinstance(foreground_attempts, int)
            or foreground_attempts < 2
        ):
            raise ValueError("foreground_attempts must be an integer of at least 2")
        if poll_interval_seconds < 0:
            raise ValueError("poll_interval_seconds must not be negative")
        if not callable(sleeper):
            raise TypeError("sleeper must be callable")
        self.front_door = front_door
        self._runner = runner or SubprocessCommandRunner()
        self._adb_path = adb_path
        self._java_path = java_path
        self._apksigner_jar_path = apksigner_jar_path
        self._serial = serial
        self._timeout_seconds = float(timeout_seconds)
        self._foreground_attempts = foreground_attempts
        self._poll_interval_seconds = float(poll_interval_seconds)
        self._sleeper = sleeper

    def open(self) -> AndroidHandoffEvidence:
        """Verify identity, start an explicit component, and prove foreground."""

        identity_before = self._verify_package_identity()
        launcher = self._resolve_launcher_component()
        dispatch = self._run_checked(
            self._adb_argv(
                "shell",
                "am",
                "start",
                "-W",
                "--user",
                "current",
                "-a",
                ACTION_MAIN,
                "-c",
                CATEGORY_LAUNCHER,
                "-n",
                _encode_adb_shell_component(launcher),
            ),
            operation="start fixed Android front door",
        )
        dispatch_text = _joined_output(dispatch)
        statuses = _AM_STATUS.findall(dispatch_text)
        activities = _AM_ACTIVITY.findall(dispatch_text)
        allowed_dispatch = (
            self.front_door.launcher_components
            | self.front_door.foreground_components
        )
        if (
            len(statuses) != 1
            or statuses[0].lower() != "ok"
            or len(activities) != 1
            or activities[0] not in allowed_dispatch
            or _AM_ERROR.search(dispatch_text) is not None
        ):
            raise AndroidHandoffError(
                "Android did not acknowledge the explicit front door safely"
            )

        foreground, foreground_digest = self._verify_foreground(
            identity_before.android_user_id
        )
        identity_after = self._verify_package_identity()
        if identity_after != identity_before:
            raise AndroidPackageIdentityError(
                "installed package identity changed during the handoff"
            )
        return AndroidHandoffEvidence(
            package_name=self.front_door.package_name,
            version_code=self.front_door.version_code,
            certificate_sha256=self.front_door.certificate_sha256,
            device_sdk=identity_after.device_sdk,
            android_user_id=identity_after.android_user_id,
            signer_minimum_sdk=identity_after.signer_minimum_sdk,
            signer_maximum_sdk=identity_after.signer_maximum_sdk,
            base_apk_path_sha256=identity_after.base_apk_path_sha256,
            launcher_component=launcher,
            foreground_component=foreground,
            dispatch_sha256=hashlib.sha256(dispatch_text.encode("utf-8")).hexdigest(),
            foreground_evidence_sha256=foreground_digest,
        )

    def _verify_package_identity(self) -> _PackageIdentityEvidence:
        state = self._run_checked(
            self._adb_argv("get-state"),
            operation="check ADB device state",
        )
        if state.stdout.strip().lower() != "device":
            raise AndroidPackageIdentityError("ADB target is not in the device state")

        device_sdk_result = self._run_checked(
            self._adb_argv("shell", "getprop", "ro.build.version.sdk"),
            operation="read Android SDK level",
        )
        device_sdk_text = device_sdk_result.stdout.strip()
        if re.fullmatch(r"[1-9]\d{0,3}", device_sdk_text) is None:
            raise AndroidPackageIdentityError("Android SDK level is unavailable")
        device_sdk = int(device_sdk_text)

        current_user_result = self._run_checked(
            self._adb_argv("shell", "am", "get-current-user"),
            operation="read current Android user",
        )
        current_user_text = current_user_result.stdout.strip()
        if re.fullmatch(r"(?:0|[1-9]\d{0,9})", current_user_text) is None:
            raise AndroidPackageIdentityError("current Android user is unavailable")
        current_user = int(current_user_text)

        package = self.front_door.package_name
        package_dump = self._run_checked(
            self._adb_argv("shell", "dumpsys", "package", package),
            operation="inspect Android package version",
        )
        version_codes = {int(value) for value in _VERSION_CODE.findall(package_dump.stdout)}
        if version_codes != {self.front_door.version_code}:
            raise AndroidPackageIdentityError(
                "installed package versionCode does not match the exact host pin"
            )

        package_paths = self._run_checked(
            self._adb_argv("shell", "pm", "path", package),
            operation="locate installed base APK",
        )
        apk_paths = [
            line[len("package:") :].strip()
            for line in package_paths.stdout.splitlines()
            if line.startswith("package:")
        ]
        base_apks = [path for path in apk_paths if path.endswith("/base.apk")]
        if len(base_apks) != 1 or "\x00" in base_apks[0] or "\n" in base_apks[0]:
            raise AndroidPackageIdentityError(
                "installed package did not expose exactly one base APK"
            )
        base_apk_path_sha256 = hashlib.sha256(base_apks[0].encode("utf-8")).hexdigest()

        with TemporaryDirectory(prefix="jidan-apk-identity-") as directory:
            local_apk = Path(directory) / "base.apk"
            self._run_checked(
                self._adb_argv("pull", base_apks[0], str(local_apk)),
                operation="copy installed base APK for certificate verification",
            )
            verified = self._run_checked(
                (
                    self._java_path,
                    "-jar",
                    self._apksigner_jar_path,
                    "verify",
                    "--print-certs",
                    "--min-sdk-version",
                    str(device_sdk),
                    "--max-sdk-version",
                    str(device_sdk),
                    str(local_apk),
                ),
                operation="verify installed APK certificate with apksigner",
            )
        signer = _select_signer_certificate(
            _joined_output(verified),
            device_sdk=device_sdk,
            expected_digest=self.front_door.certificate_sha256,
        )
        return _PackageIdentityEvidence(
            device_sdk=device_sdk,
            android_user_id=current_user,
            version_code=self.front_door.version_code,
            certificate_sha256=signer.digest,
            signer_minimum_sdk=signer.minimum_sdk,
            signer_maximum_sdk=signer.maximum_sdk,
            base_apk_path_sha256=base_apk_path_sha256,
        )

    def _resolve_launcher_component(self) -> str:
        result = self._run_checked(
            self._adb_argv(
                "shell",
                "cmd",
                "package",
                "resolve-activity",
                "--brief",
                "--components",
                "--user",
                "current",
                "-a",
                ACTION_MAIN,
                "-c",
                CATEGORY_LAUNCHER,
                "-p",
                self.front_door.package_name,
            ),
            operation="resolve fixed Android launcher component",
        )
        components = {
            line.strip()
            for line in result.stdout.splitlines()
            if _ANDROID_COMPONENT.fullmatch(line.strip()) is not None
        }
        if len(components) != 1:
            raise AndroidFrontDoorUnavailable(
                "Android did not resolve exactly one launcher component"
            )
        component = next(iter(components))
        if component not in self.front_door.launcher_components:
            raise AndroidFrontDoorUnavailable(
                "resolved launcher component is outside the host allowlist"
            )
        return component

    def _verify_foreground(self, expected_user: int) -> tuple[str, str]:
        permitted = (
            self.front_door.launcher_components
            | self.front_door.foreground_components
        )
        stable_component: str | None = None
        stable_samples = 0
        evidence_hashes: list[dict[str, str]] = []

        for attempt in range(self._foreground_attempts):
            activities = self._run_checked(
                self._adb_argv("shell", "dumpsys", "activity", "activities"),
                operation="inspect top resumed Android activity",
            )
            windows = self._run_checked(
                self._adb_argv("shell", "dumpsys", "window", "windows"),
                operation="inspect focused Android window",
            )
            activity_text = activities.stdout
            window_text = windows.stdout
            activity_records = {
                (int(user), component)
                for user, component in _TOP_RESUMED_ACTIVITY.findall(activity_text)
            }
            window_records = {
                (int(user), component)
                for user, component in _CURRENT_FOCUS.findall(window_text)
            }
            evidence_hashes.append(
                {
                    "activity": hashlib.sha256(activity_text.encode("utf-8")).hexdigest(),
                    "window": hashlib.sha256(window_text.encode("utf-8")).hexdigest(),
                }
            )
            if len(activity_records) != 1 or len(window_records) != 1:
                stable_component = None
                stable_samples = 0
            else:
                activity_user, activity = next(iter(activity_records))
                window_user, window = next(iter(window_records))
                if activity_user != expected_user or window_user != expected_user:
                    raise AndroidForegroundVerificationError(
                        "foreground evidence belongs to a different Android user"
                    )
                if activity not in permitted or window not in permitted:
                    raise AndroidForegroundVerificationError(
                        "an unexpected package or activity reached the foreground"
                    )
                if activity != window:
                    stable_component = None
                    stable_samples = 0
                elif activity in self.front_door.foreground_components:
                    if activity == stable_component:
                        stable_samples += 1
                    else:
                        stable_component = activity
                        stable_samples = 1
                    if stable_samples >= 2:
                        encoded = json.dumps(
                            evidence_hashes,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8")
                        return activity, hashlib.sha256(encoded).hexdigest()
                else:
                    stable_component = None
                    stable_samples = 0
            if attempt < self._foreground_attempts - 1:
                self._sleeper(self._poll_interval_seconds)

        raise AndroidForegroundVerificationError(
            "activity and focused-window evidence did not converge twice"
        )

    def _adb_argv(self, *tail: str) -> tuple[str, ...]:
        argv = [self._adb_path]
        if self._serial is not None:
            argv.extend(("-s", self._serial))
        argv.extend(tail)
        return tuple(argv)

    def _run_checked(self, argv: Sequence[str], *, operation: str) -> CommandResult:
        try:
            result = self._runner.run(argv, timeout_seconds=self._timeout_seconds)
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
            raise AndroidHandoffError(f"{operation} failed before completion") from exc
        if not isinstance(result, CommandResult):
            raise TypeError("CommandRunner.run() must return CommandResult")
        if result.returncode != 0:
            digest = hashlib.sha256(_joined_output(result).encode("utf-8")).hexdigest()
            raise AndroidHandoffError(
                f"{operation} failed with exit {result.returncode}; diagnostic sha256={digest}"
            )
        return result


def _select_signer_certificate(
    output: str,
    *,
    device_sdk: int,
    expected_digest: str,
) -> _SignerCertificate:
    legacy: list[_SignerCertificate] = []
    ranged: list[_SignerCertificate] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        lowered = line.lower()
        if not (
            lowered.startswith("signer ")
            and "certificate sha-256 digest:" in lowered
        ):
            continue
        legacy_match = _LEGACY_CERTIFICATE_DIGEST.fullmatch(line)
        if legacy_match is not None:
            legacy.append(
                _SignerCertificate(
                    legacy_match.group("digest"),
                    None,
                    None,
                )
            )
            continue
        ranged_match = _RANGED_CERTIFICATE_DIGEST.fullmatch(line)
        if ranged_match is not None:
            try:
                ranged.append(
                    _SignerCertificate(
                        ranged_match.group("digest"),
                        int(ranged_match.group("minimum")),
                        int(ranged_match.group("maximum")),
                    )
                )
            except ValueError as exc:
                raise AndroidPackageIdentityError(
                    "apksigner emitted an invalid SDK signer range"
                ) from exc
            continue
        raise AndroidPackageIdentityError(
            "apksigner emitted an unsupported SHA-256 signer record"
        )

    if legacy and ranged:
        raise AndroidPackageIdentityError(
            "apksigner mixed legacy and SDK-ranged signer records"
        )
    if legacy:
        if len(legacy) != 1 or legacy[0].digest != expected_digest:
            raise AndroidPackageIdentityError(
                "installed APK signing certificate does not match the exact host pin"
            )
        return legacy[0]
    if not ranged:
        raise AndroidPackageIdentityError(
            "apksigner did not emit a supported SHA-256 signer record"
        )

    ordered = sorted(
        ranged,
        key=lambda item: (
            item.minimum_sdk if item.minimum_sdk is not None else -1,
            item.maximum_sdk if item.maximum_sdk is not None else -1,
        ),
    )
    for previous, current in zip(ordered, ordered[1:]):
        if (
            previous.maximum_sdk is None
            or current.minimum_sdk is None
            or previous.maximum_sdk >= current.minimum_sdk
        ):
            raise AndroidPackageIdentityError(
                "apksigner emitted overlapping SDK signer ranges"
            )
    effective = [item for item in ordered if item.covers(device_sdk)]
    if len(effective) != 1 or effective[0].digest != expected_digest:
        raise AndroidPackageIdentityError(
            "effective APK signing certificate does not match the exact host pin"
        )
    return effective[0]


def _encode_adb_shell_component(component: str) -> str:
    """Protect inner-class `$` when adb joins argv for the remote shell."""

    return component.replace("$", r"\$")


def _joined_output(result: CommandResult) -> str:
    return "\n".join(
        part.strip() for part in (result.stdout, result.stderr) if part.strip()
    )

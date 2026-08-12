from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
import hashlib
import json
import re
import subprocess

from .android_appfunctions import CommandResult, CommandRunner, SubprocessCommandRunner
from .models import Capability, Effect
from .registry import CapabilityRegistry


SEMANTIC_SURFACE_CAPABILITY_ID = "android.semantic_surfaces.inspect"
_ANDROID_PACKAGE = re.compile(
    r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$"
)
_ADB_SERIAL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_SHORTCUT_BLOCK = re.compile(
    r"ShortcutInfo \{id=(.*?)(?=\nShortcutInfo \{|\nSuccess\s*$|\Z)",
    re.DOTALL,
)
_NOTIFICATION_BLOCK = re.compile(
    r"NotificationRecord\((.*?)(?=\n\s*NotificationRecord\(|\n\s*Ranking Config|\Z)",
    re.DOTALL,
)
_KNOWN_TEXT_SHARE_HANDOFFS = {
    "com.tencent.mm": frozenset({"com.tencent.mm/.ui.tools.ShareImgUI"}),
}


class SemanticSurfaceProbeError(RuntimeError):
    pass


class AdbSemanticSurfaceProbe:
    """Inventory deterministic Android semantic surfaces before considering GUI control."""

    def __init__(
        self,
        package_name: str,
        runner: CommandRunner | None = None,
        *,
        adb_path: str = "adb",
        serial: str = "emulator-5554",
        timeout_seconds: float = 35.0,
    ) -> None:
        if _ANDROID_PACKAGE.fullmatch(package_name) is None:
            raise ValueError(f"invalid Android package name: {package_name!r}")
        if not adb_path or "\x00" in adb_path:
            raise ValueError("adb_path must be a non-empty executable path")
        if _ADB_SERIAL.fullmatch(serial) is None:
            raise ValueError(f"invalid adb serial: {serial!r}")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.package_name = package_name
        self._runner = runner or SubprocessCommandRunner()
        self._adb_path = adb_path
        self._serial = serial
        self._timeout_seconds = timeout_seconds

    def capability(self) -> Capability:
        return Capability(
            id=SEMANTIC_SURFACE_CAPABILITY_ID,
            app=self.package_name,
            description=(
                "Inspect AppFunctions, conversation shortcuts, and notification "
                "RemoteInput surfaces plus public text-share handoffs without "
                "opening or controlling the target app."
            ),
            effect=Effect.READ,
            scopes=frozenset(
                {
                    f"android.package.{self.package_name}",
                    "device.semantic_surfaces.read",
                }
            ),
            requires_confirmation=False,
            reversible=True,
            input_schema={
                "type": "object",
                "properties": {
                    "packageName": {"const": self.package_name},
                },
                "required": ["packageName"],
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {
                    "status": {"const": "inspected"},
                    "packageName": {"const": self.package_name},
                    "appFunctions": {
                        "type": "object",
                        "properties": {
                            "count": {"type": "integer"},
                            "ids": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["count", "ids"],
                        "additionalProperties": False,
                    },
                    "shortcuts": {
                        "type": "object",
                        "properties": {
                            "count": {"type": "integer"},
                            "conversationCount": {"type": "integer"},
                            "items": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "shortLabel": {"type": "string"},
                                        "hasPersons": {"type": "boolean"},
                                        "hasCategories": {"type": "boolean"},
                                    },
                                    "required": [
                                        "id",
                                        "shortLabel",
                                        "hasPersons",
                                        "hasCategories",
                                    ],
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "required": ["count", "conversationCount", "items"],
                        "additionalProperties": False,
                    },
                    "notifications": {
                        "type": "object",
                        "properties": {
                            "importance": {"type": "string"},
                            "activeCount": {"type": "integer"},
                            "remoteInputCount": {"type": "integer"},
                        },
                        "required": [
                            "importance",
                            "activeCount",
                            "remoteInputCount",
                        ],
                        "additionalProperties": False,
                    },
                    "shareTextHandoff": {
                        "type": "object",
                        "properties": {
                            "count": {"type": "integer"},
                            "handlers": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "sendsWithoutUser": {"const": False},
                        },
                        "required": ["count", "handlers", "sendsWithoutUser"],
                        "additionalProperties": False,
                    },
                    "routing": {
                        "type": "object",
                        "properties": {
                            "selected": {
                                "enum": [
                                    "appfunctions",
                                    "notification_remote_input",
                                    "conversation_shortcut",
                                    "public_share_handoff",
                                    "blocked_no_semantic_surface",
                                ]
                            },
                            "reason": {"type": "string"},
                            "guiFallbackIsAuthoritative": {"const": False},
                        },
                        "required": [
                            "selected",
                            "reason",
                            "guiFallbackIsAuthoritative",
                        ],
                        "additionalProperties": False,
                    },
                    "evidenceSha256": {
                        "type": "string",
                        "minLength": 64,
                        "maxLength": 64,
                    },
                },
                "required": [
                    "status",
                    "packageName",
                    "appFunctions",
                    "shortcuts",
                    "notifications",
                    "shareTextHandoff",
                    "routing",
                    "evidenceSha256",
                ],
                "additionalProperties": False,
            },
            adapter="android.adb.semantic-surface-probe",
        )

    def register(self, registry: CapabilityRegistry) -> Capability:
        capability = self.capability()
        registry.register(capability, self.inspect)
        return capability

    def inspect(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        if arguments.get("packageName") != self.package_name:
            raise ValueError("packageName is outside this probe's fixed target")
        state = self._run(self._adb_argv("get-state"), "check device state")
        if state.stdout.strip() != "device":
            raise SemanticSurfaceProbeError("ADB target is not in the device state")
        installed = self._run(
            self._adb_argv("shell", "pm", "path", self.package_name),
            "find target package",
        )
        if "package:" not in installed.stdout:
            raise SemanticSurfaceProbeError("target package path was not returned")
        functions_raw = self._run(
            self._adb_argv(
                "shell",
                "cmd",
                "app_function",
                "list-app-functions",
                "--package",
                self.package_name,
            ),
            "list AppFunctions",
        ).stdout
        shortcuts_raw = self._run(
            self._adb_argv(
                "shell",
                "cmd",
                "shortcut",
                "get-shortcuts",
                "--user",
                "0",
                "--flags",
                "31",
                self.package_name,
            ),
            "list Android shortcuts",
        ).stdout
        notifications_raw = self._run(
            self._adb_argv("shell", "dumpsys", "notification"),
            "inspect notification surfaces",
        ).stdout
        share_handlers_raw = self._run(
            self._adb_argv(
                "shell",
                "cmd",
                "package",
                "query-activities",
                "--brief",
                "--components",
                "-a",
                "android.intent.action.SEND",
                "-t",
                "text/plain",
                "-p",
                self.package_name,
            ),
            "inspect public text-share handoffs",
        ).stdout

        app_function_ids = _parse_app_function_ids(functions_raw)
        shortcuts = _parse_shortcuts(shortcuts_raw)
        notifications = _parse_notifications(notifications_raw, self.package_name)
        share_handlers = _parse_share_handlers(share_handlers_raw, self.package_name)
        conversation_count = sum(item["hasPersons"] for item in shortcuts)
        route = _select_route(
            app_function_count=len(app_function_ids),
            remote_input_count=notifications["remoteInputCount"],
            conversation_shortcut_count=conversation_count,
            share_handoff_count=len(share_handlers),
        )
        evidence_digest = hashlib.sha256(
            json.dumps(
                {
                    "appFunctions": functions_raw,
                    "shortcuts": shortcuts_raw,
                    "notifications": notifications_raw,
                    "shareTextHandoff": share_handlers_raw,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return {
            "status": "inspected",
            "packageName": self.package_name,
            "appFunctions": {
                "count": len(app_function_ids),
                "ids": app_function_ids,
            },
            "shortcuts": {
                "count": len(shortcuts),
                "conversationCount": conversation_count,
                "items": shortcuts,
            },
            "notifications": notifications,
            "shareTextHandoff": {
                "count": len(share_handlers),
                "handlers": share_handlers,
                "sendsWithoutUser": False,
            },
            "routing": route,
            "evidenceSha256": evidence_digest,
        }

    def _adb_argv(self, *tail: str) -> tuple[str, ...]:
        return (self._adb_path, "-s", self._serial, *tail)

    def _run(self, argv: Sequence[str], operation: str) -> CommandResult:
        try:
            result = self._runner.run(
                argv,
                timeout_seconds=self._timeout_seconds,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
            raise SemanticSurfaceProbeError(
                f"{operation} failed before completion: {exc}"
            ) from exc
        if result.returncode != 0:
            raw = (result.stdout + "\n" + result.stderr).encode(
                "utf-8",
                errors="replace",
            )
            raise SemanticSurfaceProbeError(
                f"{operation} failed with exit {result.returncode}; "
                f"bytes={len(raw)} sha256={hashlib.sha256(raw).hexdigest()}"
            )
        return result


def _parse_app_function_ids(raw: str) -> list[str]:
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SemanticSurfaceProbeError(
            "AppFunctions inventory did not return valid JSON"
        ) from exc
    found: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if key in {"functionId", "functionIdentifier", "function_id"}:
                    if isinstance(child, str) and child not in found:
                        found.append(child)
                visit(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child)

    visit(document)
    return sorted(found)


def _parse_shortcuts(raw: str) -> list[dict[str, Any]]:
    shortcuts: list[dict[str, Any]] = []
    for match in _SHORTCUT_BLOCK.finditer(raw):
        block = match.group(1)
        first_line, _, remainder = block.partition("\n")
        shortcut_id = first_line.split(",", 1)[0].strip()
        label_match = re.search(r"(?m)^\s*shortLabel=(.*?), resId=", remainder)
        persons_match = re.search(r"(?m)^\s*persons=(.*?)\s*$", remainder)
        categories_match = re.search(r"(?m)^\s*categories=(.*?)\s*$", remainder)
        label = label_match.group(1).strip() if label_match is not None else ""
        persons = persons_match.group(1).strip() if persons_match is not None else "null"
        categories = (
            categories_match.group(1).strip()
            if categories_match is not None
            else "null"
        )
        shortcuts.append(
            {
                "id": shortcut_id,
                "shortLabel": label,
                "hasPersons": persons not in {"", "null", "[]"},
                "hasCategories": categories not in {"", "null", "[]"},
            }
        )
    return shortcuts


def _parse_notifications(raw: str, package_name: str) -> dict[str, Any]:
    escaped = re.escape(package_name)
    importance_match = re.search(
        rf"(?m)^\s*AppSettings:\s+{escaped}\s+\([^)]*\)\s+importance=([A-Z_0-9-]+)",
        raw,
    )
    importance = importance_match.group(1) if importance_match is not None else "UNKNOWN"
    blocks = [
        match.group(1)
        for match in _NOTIFICATION_BLOCK.finditer(raw)
        if re.search(rf"(?<![A-Za-z0-9_.])pkg={escaped}(?![A-Za-z0-9_.])", match.group(1))
    ]
    remote_input_count = sum(
        len(re.findall(r"\bRemoteInput\b", block)) for block in blocks
    )
    return {
        "importance": importance,
        "activeCount": len(blocks),
        "remoteInputCount": remote_input_count,
    }


def _parse_share_handlers(raw: str, package_name: str) -> list[str]:
    allowed = _KNOWN_TEXT_SHARE_HANDOFFS.get(package_name, frozenset())
    return sorted(
        {
            line.strip()
            for line in raw.splitlines()
            if line.strip() in allowed
        }
    )


def _select_route(
    *,
    app_function_count: int,
    remote_input_count: int,
    conversation_shortcut_count: int,
    share_handoff_count: int,
) -> dict[str, Any]:
    if app_function_count:
        selected = "appfunctions"
        reason = "The app exposes a typed OS capability contract."
    elif remote_input_count:
        selected = "notification_remote_input"
        reason = (
            "An active app-authored notification exposes a semantic reply PendingIntent."
        )
    elif conversation_shortcut_count:
        selected = "conversation_shortcut"
        reason = (
            "The app publishes person-bound conversation shortcuts; launching still "
            "requires a shortcut-host or Sharesheet route."
        )
    elif share_handoff_count:
        selected = "public_share_handoff"
        reason = (
            "The app accepts Android's public text-share contract; the app owns "
            "recipient identity and the user must select and confirm the target."
        )
    else:
        selected = "blocked_no_semantic_surface"
        reason = (
            "No app-authored semantic send surface is available; pixels alone cannot "
            "authorize an external message target."
        )
    return {
        "selected": selected,
        "reason": reason,
        "guiFallbackIsAuthoritative": False,
    }

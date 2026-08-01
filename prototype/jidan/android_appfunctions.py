from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol
import argparse
import hashlib
import json
import math
import re
import shlex
import subprocess
import sys

from .models import Capability, Effect
from .registry import CapabilityRegistry
from .console import configure_utf8_stdio


_ANDROID_PACKAGE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$")
_ADB_SERIAL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_SAFE_ID_CHARS = re.compile(r"[^A-Za-z0-9_.-]+")
_ADAPTER_NAME = "android.appfunctions.adb-shell"
_EXECUTE_SCOPE = "android.appfunctions.execute"
_RETURN_KEY = "androidAppfunctionsReturnValue"
_MAX_PARAMETERS_BYTES = 16_384
_MAX_REMOTE_COMMAND_BYTES = 24_576


@dataclass(frozen=True)
class CommandResult:
    """Captured result from one argv-only process invocation."""

    returncode: int
    stdout: str = ""
    stderr: str = ""


class CommandRunner(Protocol):
    """Injection boundary used by the adapter and its device-free tests."""

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout_seconds: float,
    ) -> CommandResult:
        ...


class SubprocessCommandRunner:
    """Runs a fixed argv vector without a host shell."""

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout_seconds: float,
    ) -> CommandResult:
        completed = subprocess.run(
            list(argv),
            shell=False,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)


class AdapterErrorKind(str, Enum):
    ADB_MISSING = "adb_missing"
    DEVICE_OFFLINE = "device_offline"
    PERMISSION_DENIED = "permission_denied"
    UNSUPPORTED = "unsupported"
    PARSE_FAILURE = "parse_failure"
    COMMAND_FAILED = "command_failed"


class AppFunctionsAdapterError(RuntimeError):
    kind = AdapterErrorKind.COMMAND_FAILED

    def __init__(self, message: str) -> None:
        super().__init__(message)


class AdbMissingError(AppFunctionsAdapterError):
    kind = AdapterErrorKind.ADB_MISSING


class DeviceOfflineError(AppFunctionsAdapterError):
    kind = AdapterErrorKind.DEVICE_OFFLINE


class PermissionDeniedError(AppFunctionsAdapterError):
    kind = AdapterErrorKind.PERMISSION_DENIED


class UnsupportedAppFunctionsError(AppFunctionsAdapterError):
    kind = AdapterErrorKind.UNSUPPORTED


class AppFunctionsParseError(AppFunctionsAdapterError):
    kind = AdapterErrorKind.PARSE_FAILURE


class AppFunctionsCommandError(AppFunctionsAdapterError):
    kind = AdapterErrorKind.COMMAND_FAILED


@dataclass(frozen=True)
class DeviceProbe:
    state: str
    serial: str | None
    app_function_service: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "serial": self.serial,
            "app_function_service": self.app_function_service,
        }


@dataclass(frozen=True)
class AppFunctionCapabilityRecord:
    """A platform target paired with its conservative Jidan capability."""

    capability: Capability
    package_name: str
    function_id: str
    metadata: tuple[Mapping[str, Any], ...]

    def to_dict(self, *, include_metadata: bool = False) -> dict[str, Any]:
        record: dict[str, Any] = {
            "id": self.capability.id,
            "app": self.capability.app,
            "description": self.capability.description,
            "effect": self.capability.effect.label(),
            "scopes": sorted(self.capability.scopes),
            "requires_confirmation": self.capability.requires_confirmation,
            "reversible": self.capability.reversible,
            "input_schema": dict(self.capability.input_schema),
            "output_schema": dict(self.capability.output_schema),
            "adapter": self.capability.adapter,
            "provider": {
                "package": self.package_name,
                "function": self.function_id,
            },
        }
        if include_metadata:
            record["android_metadata"] = list(self.metadata)
        return record


@dataclass(frozen=True)
class AppFunctionExecutionResult:
    value: Any
    raw_stdout: str


class AdbAppFunctionsAdapter:
    """Android AppFunctions discovery/execution over the official adb shell CLI."""

    def __init__(
        self,
        runner: CommandRunner | None = None,
        *,
        adb_path: str = "adb",
        serial: str | None = None,
        timeout_seconds: float = 35.0,
        remote_timeout_seconds: int = 30,
    ) -> None:
        if not adb_path or "\x00" in adb_path:
            raise ValueError("adb_path must be a non-empty executable path")
        if serial is not None and not _ADB_SERIAL.fullmatch(serial):
            raise ValueError(f"invalid adb serial: {serial!r}")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not isinstance(remote_timeout_seconds, int) or not 1 <= remote_timeout_seconds <= 300:
            raise ValueError("remote_timeout_seconds must be an integer from 1 to 300")
        self._runner = runner or SubprocessCommandRunner()
        self._adb_path = adb_path
        self._serial = serial
        self._timeout_seconds = timeout_seconds
        self._remote_timeout_seconds = remote_timeout_seconds

    def probe(self) -> DeviceProbe:
        """Check that a device is online and exposes the app_function service."""

        state_result = self._run_checked(self._adb_argv("get-state"))
        state = state_result.stdout.strip().lower()
        if state != "device":
            raise DeviceOfflineError(
                f"ADB device is unavailable (reported state: {state or 'empty'})"
            )

        service_result = self._run(
            self._adb_argv("shell", "cmd", "app_function", "help")
        )
        # Android 17 writes the normal help page to stderr, and that page itself
        # contains phrases such as "Error executing app function".  Treat the
        # documented command names as the success signal before classifying the
        # remaining text as a transport/service failure.
        service_help = "\n".join((service_result.stdout, service_result.stderr)).lower()
        if not (
            "list-app-functions" in service_help
            and "execute-app-function" in service_help
        ):
            known_error = _classify_diagnostic(service_help)
            if known_error is not None:
                raise known_error
            raise UnsupportedAppFunctionsError(
                "the connected Android build did not return app_function command help"
            )
        return DeviceProbe(
            state="device",
            serial=self._serial,
            app_function_service=True,
        )

    def discover(
        self,
        package_name: str | None = None,
    ) -> tuple[AppFunctionCapabilityRecord, ...]:
        """List AppFunctions and normalize them into Jidan capability records."""

        document = self._parse_json(
            self.list_raw(package_name),
            operation="list-app-functions",
        )
        return _normalize_discovery(document)

    def list_raw(self, package_name: str | None = None) -> str:
        """Return the platform JSON verbatim for diagnostics and schema evolution."""

        tail = [
            "shell",
            "cmd",
            "app_function",
            "list-app-functions",
        ]
        if package_name is not None:
            _validate_package(package_name)
            tail.extend(("--package", shlex.quote(package_name)))
        result = self._run_checked(
            self._adb_argv(*tail)
        )
        return result.stdout

    def execute(
        self,
        package_name: str,
        function_id: str,
        arguments: Mapping[str, Any],
    ) -> Any:
        """Execute one explicit AppFunction target with a strict JSON object payload."""

        return self.execute_with_raw(package_name, function_id, arguments).value

    def execute_with_raw(
        self,
        package_name: str,
        function_id: str,
        arguments: Mapping[str, Any],
    ) -> AppFunctionExecutionResult:
        """Execute and retain both the parsed value and exact platform stdout."""

        raw_stdout = self.execute_raw(package_name, function_id, arguments)
        value = self._parse_json(raw_stdout, operation="execute-app-function")
        return AppFunctionExecutionResult(value=value, raw_stdout=raw_stdout)

    def execute_raw(
        self,
        package_name: str,
        function_id: str,
        arguments: Mapping[str, Any],
    ) -> str:
        """Execute one target and return the platform response without transformation."""

        _validate_package(package_name)
        _validate_function_id(function_id)
        parameters_json = _encode_parameters(arguments)

        # `adb shell` invokes a device-side POSIX shell. shlex.quote keeps every
        # dynamic value one remote argument while the host process still uses argv
        # and shell=False.
        remote_tail = (
            "cmd",
            "app_function",
            "execute-app-function",
            "--timeout-duration",
            str(self._remote_timeout_seconds),
            "--package",
            shlex.quote(package_name),
            "--function",
            shlex.quote(function_id),
            "--parameters",
            shlex.quote(parameters_json),
        )
        if len(" ".join(remote_tail).encode("utf-8")) > _MAX_REMOTE_COMMAND_BYTES:
            raise ValueError("quoted AppFunction command exceeds the 24 KiB prototype limit")
        result = self._run_checked(self._adb_argv("shell", *remote_tail))
        return result.stdout

    def register_discovered(
        self,
        registry: CapabilityRegistry,
        records: Sequence[AppFunctionCapabilityRecord] | None = None,
        *,
        package_name: str | None = None,
    ) -> tuple[AppFunctionCapabilityRecord, ...]:
        """Bind discovered targets behind the registry used by JGraph execution."""

        if package_name is None:
            raise ValueError("dynamic registration requires an explicit package filter")
        _validate_package(package_name)
        if records is None:
            normalized = self.discover(package_name)
        else:
            normalized = tuple(records)
        mismatched = sorted(
            {record.package_name for record in normalized if record.package_name != package_name}
        )
        if mismatched:
            raise ValueError(
                "discovered record is outside the allowed package: " + ", ".join(mismatched)
            )
        for record in normalized:
            registry.register(record.capability, self._handler_for(record))
        return normalized

    def _handler_for(self, record: AppFunctionCapabilityRecord):
        def handler(arguments: Mapping[str, Any]) -> Mapping[str, Any]:
            output = self.execute(record.package_name, record.function_id, arguments)
            if isinstance(output, Mapping):
                return dict(output)
            return {"value": output}

        return handler

    def _adb_argv(self, *tail: str) -> tuple[str, ...]:
        prefix = [self._adb_path]
        if self._serial is not None:
            prefix.extend(("-s", self._serial))
        prefix.extend(tail)
        return tuple(prefix)

    def _run(self, argv: Sequence[str]) -> CommandResult:
        """Run adb and normalize host-process failures without interpreting output."""

        try:
            result = self._runner.run(argv, timeout_seconds=self._timeout_seconds)
        except FileNotFoundError as exc:
            raise AdbMissingError(f"adb executable was not found: {self._adb_path}") from exc
        except subprocess.TimeoutExpired as exc:
            raise AppFunctionsCommandError("adb command timed out") from exc
        except OSError as exc:
            raise AppFunctionsCommandError(f"failed to start adb: {exc}") from exc

        if not isinstance(result, CommandResult):
            raise TypeError("CommandRunner.run() must return CommandResult")
        return result

    def _run_checked(
        self,
        argv: Sequence[str],
        *,
        classify_success_stderr: bool = True,
    ) -> CommandResult:
        result = self._run(argv)

        diagnostic = "\n".join((result.stderr, result.stdout)).strip()
        if result.returncode != 0 or classify_success_stderr:
            known_error = _classify_diagnostic(result.stderr)
            if known_error is not None:
                raise known_error
        if result.returncode != 0:
            known_error = _classify_diagnostic(diagnostic)
            if known_error is not None:
                raise known_error
            message = _compact_diagnostic(diagnostic) or f"adb exited with {result.returncode}"
            raise AppFunctionsCommandError(message)
        if _looks_like_cli_error(result.stdout):
            known_error = _classify_diagnostic(result.stdout)
            if known_error is not None:
                raise known_error
        return result

    @staticmethod
    def _parse_json(stdout: str, *, operation: str) -> Any:
        payload = stdout.strip().lstrip("\ufeff")
        if not payload:
            raise AppFunctionsParseError(f"{operation} returned an empty response")
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            diagnostic = _classify_diagnostic(payload)
            if diagnostic is not None:
                raise diagnostic from exc
            raise AppFunctionsParseError(
                f"{operation} returned invalid JSON at line {exc.lineno}, column {exc.colno}"
            ) from exc


def _classify_diagnostic(text: str) -> AppFunctionsAdapterError | None:
    lowered = text.lower()
    if not lowered:
        return None

    if any(
        marker in lowered
        for marker in (
            "device offline",
            "no devices/emulators found",
            "device unauthorized",
            "more than one device/emulator",
        )
    ) or ("device '" in lowered and "not found" in lowered):
        return DeviceOfflineError("ADB device is unavailable, offline, or unauthorized")

    if any(
        marker in lowered
        for marker in (
            "permission denial",
            "permission denied",
            "securityexception",
            "android.permission.execute_app_functions",
        )
    ):
        return PermissionDeniedError(
            "shell identity is not permitted to discover or execute AppFunctions"
        )

    if (
        "can't find service: app_function" in lowered
        or "cannot find service: app_function" in lowered
        or ("unknown command" in lowered and "app-function" in lowered)
        or ("unknown command" in lowered and "app_function" in lowered)
    ):
        return UnsupportedAppFunctionsError(
            "the connected Android build does not expose the requested app_function command"
        )

    if "error executing app function" in lowered or lowered.strip() == "timed out":
        return AppFunctionsCommandError(_compact_diagnostic(text))
    return None


def _looks_like_cli_error(text: str) -> bool:
    lowered = text.lstrip().lower()
    return lowered.startswith(
        (
            "adb:",
            "cmd:",
            "error:",
            "error executing app function",
            "java.lang.securityexception",
            "permission denial",
            "securityexception",
            "timed out",
            "unknown command",
        )
    )


def _compact_diagnostic(text: str, *, limit: int = 400) -> str:
    compact = " ".join(text.split())
    if len(compact) > limit:
        return compact[: limit - 1] + "…"
    return compact


def _validate_package(package_name: str) -> None:
    if not isinstance(package_name, str) or not _ANDROID_PACKAGE.fullmatch(package_name):
        raise ValueError(f"invalid Android package name: {package_name!r}")


def _validate_function_id(function_id: str) -> None:
    if not isinstance(function_id, str):
        raise TypeError("function_id must be a string")
    # AndroidX-generated identifiers commonly use ``Class#method``, while
    # platform providers in the Android 17 emulator also publish simple IDs such
    # as ``getPermissionsDeviceState``.  Both are valid opaque identifiers.
    if not function_id or len(function_id) > 1024:
        raise ValueError(f"invalid AppFunction identifier: {function_id!r}")
    if any(character.isspace() or ord(character) < 32 for character in function_id):
        raise ValueError(f"invalid AppFunction identifier: {function_id!r}")


def _encode_parameters(arguments: Mapping[str, Any]) -> str:
    if not isinstance(arguments, Mapping):
        raise TypeError("AppFunction parameters must be a mapping")
    normalized = _normalize_json_value(arguments, path="$")
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(encoded.encode("utf-8")) > _MAX_PARAMETERS_BYTES:
        raise ValueError("AppFunction parameters exceed the 16 KiB prototype limit")
    return encoded


def _normalize_json_value(value: Any, *, path: str) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite number at {path}")
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError(f"JSON object key at {path} must be a string")
            # Android's GenericDocument converter cannot represent JSON null or
            # an untyped empty array. Reject them instead of silently changing a
            # plan after its arguments have been approved and hash-bound.
            if child is None:
                raise ValueError(f"null field at {path}.{key} must be omitted before approval")
            if isinstance(child, (list, tuple)) and not child:
                raise ValueError(f"empty array at {path}.{key} must be omitted before approval")
            normalized[key] = _normalize_json_value(child, path=f"{path}.{key}")
        return normalized
    if isinstance(value, (list, tuple)):
        if not value:
            raise ValueError(f"empty array at {path} must be omitted")
        normalized_items: list[Any] = []
        kinds: set[str] = set()
        for index, child in enumerate(value):
            item_path = f"{path}[{index}]"
            if child is None:
                raise ValueError(f"null array item at {item_path} is unsupported")
            if isinstance(child, (list, tuple)) and not child:
                raise ValueError(f"empty nested array at {item_path} is unsupported")
            normalized_child = _normalize_json_value(child, path=item_path)
            normalized_items.append(normalized_child)
            kinds.add(_json_kind(normalized_child))
        if len(kinds) != 1:
            raise TypeError(f"array at {path} must contain one JSON value type")
        return normalized_items
    raise TypeError(f"unsupported JSON value at {path}: {type(value).__name__}")


def _json_kind(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, list):
        return "array"
    raise TypeError(f"unsupported normalized JSON value: {type(value).__name__}")


def _normalize_discovery(document: Any) -> tuple[AppFunctionCapabilityRecord, ...]:
    containers = _discovery_containers(document)
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}

    for package_hint, container in containers:
        function_ids = _find_string_fields(
            container,
            {"functionId", "functionIdentifier", "function_id"},
        )
        if not function_ids:
            function_ids = [
                value
                for value in _find_string_fields(container, {"id"})
                if "#" in value
            ]
        packages = _find_string_fields(
            container,
            {"packageName", "package", "package_name"},
        )
        package_name = package_hint or (packages[0] if packages else None)
        if package_name is None:
            continue
        try:
            _validate_package(package_name)
        except ValueError:
            continue

        for function_id in function_ids:
            try:
                _validate_function_id(function_id)
            except (TypeError, ValueError):
                continue
            key = (package_name, function_id)
            grouped.setdefault(key, []).append(container)

    if not grouped:
        if document == {} or document == [] or _contains_only_empty_lists(document):
            return ()
        raise AppFunctionsParseError(
            "list-app-functions JSON did not contain recognizable package/function records"
        )

    records: list[AppFunctionCapabilityRecord] = []
    for (package_name, function_id), metadata_items in sorted(grouped.items()):
        metadata = tuple(metadata_items)
        description = _first_string_field(metadata, {"description"})
        if not description:
            description = f"Android AppFunction {function_id}"

        parameters = _first_field_value(metadata, {"parameters", "inputSchema", "input_schema"})
        response = _first_field_value(metadata, {"response", "outputSchema", "output_schema"})
        input_schema = _compile_parameters_schema(parameters)
        if input_schema is None:
            # A function without a machine-checkable input contract is not a
            # Jidan capability, even if its prose description looks useful.
            continue
        output_schema = _compile_response_schema(response) or {}
        if parameters is not None:
            input_schema["x-android-appfunctions-parameters"] = parameters
        if response is not None:
            output_schema["x-android-appfunctions-response"] = response

        capability = Capability(
            id=_capability_id(package_name, function_id),
            app=_app_id(package_name),
            description=description,
            # Android metadata does not carry a Jidan-verifiable effect or
            # compensation contract. Unknown platform functions are therefore
            # gated as external, non-reversible actions.
            effect=Effect.EXTERNAL,
            scopes=frozenset(
                {
                    _EXECUTE_SCOPE,
                    f"android.package.{package_name}",
                }
            ),
            requires_confirmation=True,
            reversible=False,
            input_schema=input_schema,
            output_schema=output_schema,
            adapter=_ADAPTER_NAME,
        )
        records.append(
            AppFunctionCapabilityRecord(
                capability=capability,
                package_name=package_name,
                function_id=function_id,
                metadata=metadata,
            )
        )
    return tuple(records)


def _compile_parameters_schema(parameters: Any) -> dict[str, Any] | None:
    """Compile Android GenericDocument parameter metadata into JCC v0 schema."""

    if parameters is None:
        return {"type": "object", "properties": {}, "additionalProperties": False}
    raw_parameters = parameters if isinstance(parameters, (list, tuple)) else [parameters]
    properties: dict[str, Any] = {}
    required: list[str] = []
    for raw_parameter in raw_parameters:
        parameter = _unwrap_single(raw_parameter)
        if not isinstance(parameter, Mapping):
            return None
        name = _unwrap_single(parameter.get("name"))
        required_flag = _unwrap_single(parameter.get("isRequired", False))
        data_type = parameter.get("dataTypeMetadata", parameter.get("dataType"))
        if not isinstance(name, str) or not name or data_type is None:
            return None
        compiled = _compile_android_data_type(data_type)
        if compiled is None or name in properties:
            return None
        properties[name] = compiled
        if required_flag is True or required_flag == 1:
            required.append(name)
        elif required_flag not in (False, 0, None):
            return None
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def _compile_response_schema(response: Any) -> dict[str, Any] | None:
    """Compile a response value into the GenericDocument shell result envelope."""

    if response is None:
        return None
    metadata = _unwrap_single(response)
    if not isinstance(metadata, Mapping):
        return None
    raw_type = metadata.get(
        "valueType",
        metadata.get("dataTypeMetadata", metadata.get("dataType", metadata)),
    )
    compiled = _compile_android_data_type(raw_type)
    if compiled is None:
        return None
    return {
        "type": "object",
        "properties": {
            _RETURN_KEY: {
                "type": "array",
                "items": compiled,
                "minItems": 1,
                "maxItems": 1,
            }
        },
        "required": [_RETURN_KEY],
        "additionalProperties": False,
    }


def _compile_android_data_type(raw: Any) -> dict[str, Any] | None:
    metadata = _unwrap_single(raw)
    if not isinstance(metadata, Mapping):
        return None
    type_value = _unwrap_single(metadata.get("type"))
    if isinstance(type_value, str):
        normalized_type: int | str = type_value.strip().lower().replace("-", "_")
    elif isinstance(type_value, int) and not isinstance(type_value, bool):
        normalized_type = type_value
    else:
        return None

    primitive_types: dict[int | str, str] = {
        1: "boolean",
        "bool": "boolean",
        "boolean": "boolean",
        2: "string",
        "bytes": "string",
        4: "number",
        "double": "number",
        5: "number",
        "float": "number",
        6: "integer",
        "long": "integer",
        7: "integer",
        "int": "integer",
        "integer": "integer",
        8: "string",
        "string": "string",
    }
    json_type = primitive_types.get(normalized_type)
    if json_type is not None:
        schema: dict[str, Any] = {"type": json_type}
        enum_values = _flatten_scalars(metadata.get("enumValues"))
        if enum_values:
            try:
                if json_type == "integer":
                    schema["enum"] = [int(item) for item in enum_values]
                elif json_type == "number":
                    schema["enum"] = [float(item) for item in enum_values]
                elif json_type == "boolean":
                    schema["enum"] = [bool(item) for item in enum_values]
                else:
                    schema["enum"] = [str(item) for item in enum_values]
            except (TypeError, ValueError):
                return None
        return schema

    if normalized_type in (10, "array"):
        item_type = metadata.get("itemType")
        compiled_item = _compile_android_data_type(item_type)
        return None if compiled_item is None else {"type": "array", "items": compiled_item}

    if normalized_type in (3, "object"):
        raw_properties = metadata.get("properties")
        property_items = [] if raw_properties is None else (
            raw_properties if isinstance(raw_properties, (list, tuple)) else [raw_properties]
        )
        properties: dict[str, Any] = {}
        for raw_property in property_items:
            item = _unwrap_single(raw_property)
            if not isinstance(item, Mapping):
                return None
            name = _unwrap_single(item.get("name"))
            child = item.get("dataTypeMetadata", item.get("dataType"))
            compiled_child = _compile_android_data_type(child)
            if not isinstance(name, str) or compiled_child is None or name in properties:
                return None
            properties[name] = compiled_child
        required_names = [str(item) for item in _flatten_scalars(metadata.get("required"))]
        if any(name not in properties for name in required_names):
            return None
        schema = {
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
        }
        if required_names:
            schema["required"] = required_names
        return schema

    # Unit, reference, all-of, and PendingIntent require semantics that this
    # dependency-free JCC compiler cannot safely infer.
    return None


def _unwrap_single(value: Any) -> Any:
    while isinstance(value, (list, tuple)) and len(value) == 1:
        value = value[0]
    return value


def _flatten_scalars(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        flattened: list[Any] = []
        for child in value:
            flattened.extend(_flatten_scalars(child))
        return flattened
    if isinstance(value, Mapping):
        return []
    return [value]


def _discovery_containers(document: Any) -> list[tuple[str | None, Mapping[str, Any]]]:
    containers: list[tuple[str | None, Mapping[str, Any]]] = []
    if isinstance(document, list):
        containers.extend((None, item) for item in document if isinstance(item, Mapping))
        return containers
    if not isinstance(document, Mapping):
        return containers

    direct_ids = _find_string_fields(
        document,
        {"functionId", "functionIdentifier", "function_id"},
        recursive=False,
    )
    if direct_ids or any("#" in value for value in _find_string_fields(document, {"id"}, recursive=False)):
        containers.append((None, document))

    for key, value in document.items():
        if isinstance(value, list):
            package_hint = key if _ANDROID_PACKAGE.fullmatch(str(key)) else None
            for item in value:
                if isinstance(item, Mapping):
                    containers.append((package_hint, item))
        elif isinstance(value, Mapping) and key in {"functions", "appFunctions", "app_functions"}:
            containers.extend(_discovery_containers(value))
    return containers


def _find_string_fields(
    value: Any,
    names: set[str],
    *,
    recursive: bool = True,
) -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in names:
                found.extend(_as_strings(child))
            if recursive:
                found.extend(_find_string_fields(child, names))
    elif recursive and isinstance(value, (list, tuple)):
        for child in value:
            found.extend(_find_string_fields(child, names))
    return list(dict.fromkeys(found))


def _as_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [item for item in value if isinstance(item, str)]
    return []


def _first_string_field(values: Any, names: set[str]) -> str | None:
    found = _find_string_fields(values, names)
    return found[0] if found else None


def _first_field_value(value: Any, names: set[str]) -> Any:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in names:
                return child
            found = _first_field_value(child, names)
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for child in value:
            found = _first_field_value(child, names)
            if found is not None:
                return found
    return None


def _contains_only_empty_lists(value: Any) -> bool:
    return isinstance(value, Mapping) and bool(value) and all(
        isinstance(child, list) and not child for child in value.values()
    )


def _capability_id(package_name: str, function_id: str) -> str:
    method = function_id.rsplit("#", 1)[-1]
    digest = hashlib.sha256(f"{package_name}\0{function_id}".encode()).hexdigest()[:12]
    prefix = _SAFE_ID_CHARS.sub("-", f"android.appfunction.{package_name}.{method}")
    maximum_prefix = 128 - len(digest) - 1
    prefix = prefix[:maximum_prefix].rstrip("._-") or "android.appfunction"
    return f"{prefix}.{digest}"


def _app_id(package_name: str) -> str:
    if len(package_name) <= 128:
        return package_name
    digest = hashlib.sha256(package_name.encode()).hexdigest()[:16]
    return f"android.package.{digest}"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Jidan Android AppFunctions adb adapter")
    parser.add_argument("--adb-path", default="adb", help="adb executable path")
    parser.add_argument("--serial", help="optional adb device serial")
    parser.add_argument("--timeout", type=float, default=35.0, help="host command timeout in seconds")
    parser.add_argument(
        "--remote-timeout",
        type=int,
        default=30,
        help="Android execute timeout in seconds",
    )
    subparsers = parser.add_subparsers(dest="operation", required=True)
    subparsers.add_parser("probe", help="check device and app_function service")

    list_parser = subparsers.add_parser("list", help="print normalized capabilities")
    list_parser.add_argument("--metadata", action="store_true", help="include raw Android metadata")
    list_parser.add_argument("--package", help="filter by Android package")

    execute_parser = subparsers.add_parser("execute", help="execute an explicit test function")
    execute_parser.add_argument("package")
    execute_parser.add_argument("function")
    execute_parser.add_argument("parameters", help="JSON object")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    configure_utf8_stdio()
    arguments = _build_parser().parse_args(argv)
    adapter = AdbAppFunctionsAdapter(
        adb_path=arguments.adb_path,
        serial=arguments.serial,
        timeout_seconds=arguments.timeout,
        remote_timeout_seconds=arguments.remote_timeout,
    )
    try:
        if arguments.operation == "probe":
            payload: Any = adapter.probe().to_dict()
        elif arguments.operation == "list":
            payload = [
                record.to_dict(include_metadata=arguments.metadata)
                for record in adapter.discover(arguments.package)
            ]
        else:
            parsed_parameters = json.loads(arguments.parameters)
            if not isinstance(parsed_parameters, Mapping):
                raise ValueError("parameters must decode to a JSON object")
            payload = adapter.execute(arguments.package, arguments.function, parsed_parameters)
    except (AppFunctionsAdapterError, ValueError, TypeError, json.JSONDecodeError) as exc:
        kind = (
            exc.kind.value
            if isinstance(exc, AppFunctionsAdapterError)
            else "invalid_input"
        )
        print(
            json.dumps({"ok": False, "error": {"kind": kind, "message": str(exc)}}),
            file=sys.stderr,
        )
        return 2

    print(json.dumps({"ok": True, "result": payload}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

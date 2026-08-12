from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import json
import re


_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,159}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ANDROID_PACKAGE = re.compile(
    r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$"
)
_TRUSTED_STATES = {
    "OWNED_RUNTIME_LOCAL_VERIFIED",
    "VENDOR_CONTRACT_VERIFIED",
}
_KNOWN_TRUST_STATES = _TRUSTED_STATES | {"CANDIDATE_UNBOUND"}
_KNOWN_PROVIDER_KINDS = {"OWNED", "VENDOR", "CANDIDATE"}
_KNOWN_TRANSPORTS = {
    "LOCAL_ACCESSIBILITY",
    "MCP_LOCAL",
    "MCP_REMOTE",
    "HANDOFF_ONLY",
}
_KNOWN_LANES = {"SANDBOX", "OWNED_APP", "SHADOW", "HANDOFF"}
_KNOWN_CAPABILITIES = {
    "SEMANTIC_TREE",
    "NODE_ACTIONS",
    "GESTURES",
    "TEXT_INPUT",
    "SCREENSHOT",
    "OCR",
    "SCRIPT_ENGINE",
    "APP_LAUNCH",
}
_KNOWN_EFFECT_CEILINGS = {
    "SYNTHETIC_ONLY",
    "OWNED_LOCAL_APP",
    "HANDOFF_ONLY",
    "PROVIDER_DECLARED",
}
_KNOWN_IDENTITY_MODES = {
    "RUNTIME_SIGNER_AND_CONTRACT",
    "STATIC_ARTIFACT",
}


class HandProviderError(RuntimeError):
    """A hand provider cannot be registered, selected, or called safely."""


class _LoadedToolProfile(dict[str, Any]):
    """A normal Tool mapping that retains the trusted schema file location."""

    def __init__(self, raw: Mapping[str, Any], source_path: Path) -> None:
        super().__init__(deepcopy(dict(raw)))
        self.source_path = source_path.resolve()

    def __deepcopy__(self, memo: dict[int, Any]) -> "_LoadedToolProfile":
        return _LoadedToolProfile(deepcopy(dict(self), memo), self.source_path)


HandExecutor = Callable[[Mapping[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True)
class HandProviderManifest:
    provider_id: str
    display_name: str
    provider_kind: str
    trust_state: str
    transport: str
    target_package: str
    declared_plan_profile: str
    supported_lanes: tuple[str, ...]
    observed_capabilities: tuple[str, ...]
    execution_enabled: bool
    public_contract_available: bool
    public_contract_protocol: str | None
    public_contract_sha256: str | None
    host_adapter_available: bool
    host_adapter_profile_sha256: str | None
    identity_binding: Mapping[str, Any]
    real_world_effect_ceiling: str
    notes: tuple[str, ...]
    source: Mapping[str, Any]

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "HandProviderManifest":
        if not isinstance(raw, Mapping):
            raise TypeError("hand provider manifest must be an object")
        expected = {
            "profile",
            "providerId",
            "displayName",
            "providerKind",
            "trustState",
            "transport",
            "targetPackage",
            "declaredPlanProfile",
            "supportedLanes",
            "observedCapabilities",
            "executionEnabled",
            "publicContract",
            "hostAdapter",
            "identityBinding",
            "realWorldEffectCeiling",
            "notes",
        }
        if set(raw) != expected:
            raise ValueError("hand provider manifest fields do not match the contract")
        if raw["profile"] != "JCL-Hand-Provider/0.1":
            raise ValueError("unsupported hand provider profile")
        provider_id = str(raw["providerId"])
        if _ID.fullmatch(provider_id) is None:
            raise ValueError("invalid hand provider id")
        display_name = raw["displayName"]
        if not isinstance(display_name, str) or not 1 <= len(display_name) <= 80:
            raise ValueError("invalid hand provider display name")
        provider_kind = raw["providerKind"]
        trust_state = raw["trustState"]
        transport = raw["transport"]
        target_package = raw["targetPackage"]
        effect_ceiling = raw["realWorldEffectCeiling"]
        if not isinstance(provider_kind, str) or provider_kind not in _KNOWN_PROVIDER_KINDS:
            raise ValueError("unknown hand provider kind")
        if not isinstance(trust_state, str) or trust_state not in _KNOWN_TRUST_STATES:
            raise ValueError("unknown hand provider trust state")
        if not isinstance(transport, str) or transport not in _KNOWN_TRANSPORTS:
            raise ValueError("unknown hand provider transport")
        if (
            not isinstance(target_package, str)
            or _ANDROID_PACKAGE.fullmatch(target_package) is None
        ):
            raise ValueError("invalid hand provider target package")
        if (
            not isinstance(effect_ceiling, str)
            or effect_ceiling not in _KNOWN_EFFECT_CEILINGS
        ):
            raise ValueError("unknown real-world effect ceiling")
        if not isinstance(raw["supportedLanes"], list):
            raise ValueError("hand provider lanes must be an array")
        lanes = tuple(raw["supportedLanes"])
        if not all(isinstance(value, str) for value in lanes):
            raise ValueError("hand provider lanes must be strings")
        if not lanes or len(lanes) != len(set(lanes)) or not set(lanes) <= _KNOWN_LANES:
            raise ValueError("invalid or duplicate hand provider lanes")
        if not isinstance(raw["observedCapabilities"], list):
            raise ValueError("observed capabilities must be an array")
        observed_capabilities = tuple(raw["observedCapabilities"])
        if (
            len(observed_capabilities) > 8
            or len(observed_capabilities) != len(set(observed_capabilities))
            or not all(isinstance(value, str) for value in observed_capabilities)
            or not set(observed_capabilities) <= _KNOWN_CAPABILITIES
        ):
            raise ValueError("invalid or duplicate observed capabilities")
        if type(raw["executionEnabled"]) is not bool:
            raise ValueError("executionEnabled must be a boolean")
        public_contract = raw["publicContract"]
        host_adapter = raw["hostAdapter"]
        identity = raw["identityBinding"]
        if (
            not isinstance(public_contract, Mapping)
            or not isinstance(host_adapter, Mapping)
            or not isinstance(identity, Mapping)
        ):
            raise ValueError("provider contract and identity binding must be objects")
        if set(public_contract) != {"available", "protocol", "definitionSha256"}:
            raise ValueError("public contract fields do not match the contract")
        if set(host_adapter) != {"available", "profileSha256"}:
            raise ValueError("Host adapter fields do not match the contract")
        if set(identity) != {
            "mode",
            "versionCode",
            "certificateSha256",
            "artifactSha256",
            "contractId",
        }:
            raise ValueError("identity binding fields do not match the contract")
        if type(public_contract.get("available")) is not bool:
            raise ValueError("public contract availability must be a boolean")
        if type(host_adapter.get("available")) is not bool:
            raise ValueError("Host adapter availability must be a boolean")
        contract_protocol = public_contract.get("protocol")
        if contract_protocol is not None and (
            not isinstance(contract_protocol, str)
            or not contract_protocol
            or len(contract_protocol) > 80
        ):
            raise ValueError("invalid public contract protocol")
        contract_hash = public_contract.get("definitionSha256")
        if contract_hash is not None and (
            not isinstance(contract_hash, str)
            or _SHA256.fullmatch(contract_hash) is None
        ):
            raise ValueError("invalid public contract digest")
        adapter_hash = host_adapter.get("profileSha256")
        if adapter_hash is not None and (
            not isinstance(adapter_hash, str)
            or _SHA256.fullmatch(adapter_hash) is None
        ):
            raise ValueError("invalid host adapter profile digest")
        identity_mode = identity.get("mode")
        if (
            not isinstance(identity_mode, str)
            or identity_mode not in _KNOWN_IDENTITY_MODES
        ):
            raise ValueError("invalid identity binding mode")
        version_code = identity.get("versionCode")
        if (
            isinstance(version_code, bool)
            or not isinstance(version_code, int)
            or version_code < 1
        ):
            raise ValueError("identity versionCode must be a positive integer")
        for field_name in ("certificateSha256", "artifactSha256"):
            digest = identity.get(field_name)
            if digest is not None and (
                not isinstance(digest, str) or _SHA256.fullmatch(digest) is None
            ):
                raise ValueError(f"invalid identity {field_name}")
        contract_id = identity.get("contractId")
        if contract_id is not None and (
            not isinstance(contract_id, str)
            or not contract_id
            or len(contract_id) > 160
        ):
            raise ValueError("invalid identity contractId")
        if not isinstance(raw["notes"], list):
            raise ValueError("provider notes must be an array")
        notes = tuple(raw["notes"])
        if len(notes) > 8 or not all(
            isinstance(value, str) and 1 <= len(value) <= 240 for value in notes
        ):
            raise ValueError("invalid provider notes")
        manifest = cls(
            provider_id=provider_id,
            display_name=display_name,
            provider_kind=provider_kind,
            trust_state=trust_state,
            transport=transport,
            target_package=target_package,
            declared_plan_profile=str(raw["declaredPlanProfile"]),
            supported_lanes=lanes,
            observed_capabilities=observed_capabilities,
            execution_enabled=raw["executionEnabled"],
            public_contract_available=public_contract["available"],
            public_contract_protocol=contract_protocol,
            public_contract_sha256=contract_hash,
            host_adapter_available=host_adapter["available"],
            host_adapter_profile_sha256=adapter_hash,
            identity_binding=deepcopy(dict(identity)),
            real_world_effect_ceiling=effect_ceiling,
            notes=notes,
            source=deepcopy(dict(raw)),
        )
        manifest._validate_trust_boundary()
        return manifest

    @classmethod
    def from_file(cls, path: str | Path) -> "HandProviderManifest":
        with Path(path).open("r", encoding="utf-8") as stream:
            return cls.from_dict(json.load(stream))

    @property
    def manifest_sha256(self) -> str:
        encoded = json.dumps(
            self.source,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @property
    def executor_eligible(self) -> bool:
        return (
            self.execution_enabled
            and self.trust_state in _TRUSTED_STATES
            and self.host_adapter_available
            and self.transport != "HANDOFF_ONLY"
        )

    def _validate_trust_boundary(self) -> None:
        if self.declared_plan_profile not in {
            "JCL-UI-Action-Plan/0.1",
            "JCL-Owned-Action-Plan/0.1",
        }:
            raise ValueError("provider declares an unknown plan profile")
        if self.public_contract_available:
            if self.public_contract_protocol is None or self.public_contract_sha256 is None:
                raise ValueError("an available public contract must be fully pinned")
        elif (
            self.public_contract_protocol is not None
            or self.public_contract_sha256 is not None
        ):
            raise ValueError("an unavailable public contract cannot carry claims")
        if self.host_adapter_available:
            if self.host_adapter_profile_sha256 is None:
                raise ValueError("an available Host adapter must be digest-bound")
        elif self.host_adapter_profile_sha256 is not None:
            raise ValueError("an unavailable Host adapter cannot carry a digest")

        identity_mode = self.identity_binding["mode"]
        certificate = self.identity_binding["certificateSha256"]
        artifact = self.identity_binding["artifactSha256"]
        contract_id = self.identity_binding["contractId"]
        if identity_mode == "STATIC_ARTIFACT":
            if certificate is None or artifact is None or contract_id is not None:
                raise ValueError("a static artifact identity must pin signer and artifact only")
        elif certificate is not None or artifact is not None or contract_id is None:
            raise ValueError("a runtime identity must bind its local contract only")

        if self.trust_state == "CANDIDATE_UNBOUND":
            if self.provider_kind != "CANDIDATE":
                raise ValueError("an unbound candidate must use CANDIDATE kind")
            if self.transport != "HANDOFF_ONLY" or self.execution_enabled:
                raise ValueError("an unbound candidate can only be a disabled handoff")
            if self.public_contract_available:
                raise ValueError("candidate self-description is not a trusted contract")
            if self.host_adapter_available:
                raise ValueError("candidate cannot self-register a Host adapter")
            if self.real_world_effect_ceiling != "HANDOFF_ONLY":
                raise ValueError("candidate effect ceiling must remain handoff-only")
            if self.supported_lanes != ("HANDOFF",):
                raise ValueError("candidate can only declare the HANDOFF lane")
            if identity_mode != "STATIC_ARTIFACT":
                raise ValueError("candidate identity must be a pinned static artifact")
        elif self.trust_state == "OWNED_RUNTIME_LOCAL_VERIFIED":
            if self.provider_kind != "OWNED":
                raise ValueError("an owned runtime must use OWNED kind")
        elif self.trust_state == "VENDOR_CONTRACT_VERIFIED":
            if self.provider_kind != "VENDOR":
                raise ValueError("a verified vendor must use VENDOR kind")
            if not self.public_contract_available:
                raise ValueError("a verified vendor requires a pinned public contract")

        if self.execution_enabled:
            if self.trust_state not in _TRUSTED_STATES:
                raise ValueError("only a trusted provider may enable execution")
            if not self.host_adapter_available:
                raise ValueError("execution requires a Host-owned adapter")
            if self.transport == "HANDOFF_ONLY" or "HANDOFF" in self.supported_lanes:
                raise ValueError("an executor cannot use the handoff-only path")


class HandProviderCatalog:
    """Host-owned provider registry. Provider manifests can never grant themselves trust."""

    def __init__(self) -> None:
        self._manifests: dict[str, HandProviderManifest] = {}
        self._executors: dict[str, HandExecutor] = {}

    def load_directory(self, directory: str | Path) -> None:
        for path in sorted(Path(directory).glob("*.json")):
            self.register(HandProviderManifest.from_file(path))

    def register(self, manifest: HandProviderManifest) -> None:
        # The dataclass constructor is public for typing convenience. Rebuild
        # from the canonical source so a caller cannot supply fields that do
        # not match the bytes whose digest will be bound into plans.
        normalized = HandProviderManifest.from_dict(manifest.source)
        if normalized != manifest:
            raise HandProviderError("provider fields do not match its canonical source")
        if manifest.provider_id in self._manifests:
            raise ValueError(f"duplicate hand provider: {manifest.provider_id}")
        self._manifests[manifest.provider_id] = normalized

    def bind(self, provider_id: str, executor: HandExecutor) -> None:
        manifest = self.get(provider_id)
        if not manifest.executor_eligible:
            raise HandProviderError(f"provider is not executor-eligible: {provider_id}")
        if not callable(executor):
            raise TypeError("hand executor must be callable")
        if provider_id in self._executors:
            raise ValueError(f"hand provider is already bound: {provider_id}")
        self._executors[provider_id] = executor

    def get(self, provider_id: str) -> HandProviderManifest:
        try:
            return deepcopy(self._manifests[provider_id])
        except KeyError as exc:
            raise KeyError(f"unknown hand provider: {provider_id}") from exc

    def list(self) -> tuple[HandProviderManifest, ...]:
        return tuple(self.get(key) for key in sorted(self._manifests))

    def is_bound(self, provider_id: str) -> bool:
        return provider_id in self._executors

    def require_executor(self, provider_id: str, lane: str) -> HandProviderManifest:
        manifest = self.get(provider_id)
        if lane not in manifest.supported_lanes:
            raise HandProviderError(
                f"provider {provider_id} does not support lane {lane}"
            )
        if not manifest.executor_eligible or provider_id not in self._executors:
            raise HandProviderError(f"provider is not a bound executor: {provider_id}")
        return manifest

    def execute(
        self,
        provider_id: str,
        lane: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        manifest = self.require_executor(provider_id, lane)
        plan = arguments.get("plan")
        if not isinstance(plan, Mapping):
            raise HandProviderError("a bound UI plan is required")
        if plan.get("handProviderId") != manifest.provider_id:
            raise HandProviderError("the plan cannot replace its host-bound hand provider")
        if plan.get("handProviderRegistrationSha256") != manifest.manifest_sha256:
            raise HandProviderError("the plan does not match the reviewed provider registration")
        if plan.get("lane") != lane:
            raise HandProviderError("the plan lane does not match the provider call")
        output = self._executors[provider_id](deepcopy(dict(arguments)))
        if not isinstance(output, Mapping):
            raise HandProviderError("hand executor returned a non-object result")
        return deepcopy(dict(output))

    def discovery_output(self) -> Mapping[str, Any]:
        providers = [
            {
                "providerId": manifest.provider_id,
                "displayName": manifest.display_name,
                "trustState": manifest.trust_state,
                "transport": manifest.transport,
                "targetPackage": manifest.target_package,
                "supportedLanes": list(manifest.supported_lanes),
                "executionEnabled": manifest.execution_enabled,
                "executorBound": self.is_bound(manifest.provider_id),
                "manifestSha256": manifest.manifest_sha256,
            }
            for manifest in self.list()
        ]
        return {
            "state": "inspected",
            "providers": providers,
            "privateInterfaceInvoked": False,
        }


class McpHandGateway:
    """Transport-neutral MCP Tool adapter; authorization stays outside MCP."""

    INSPECT_TOOL = "android.hand.providers.inspect"
    SANDBOX_TOOL = "android.ui.sandbox_execute"

    def __init__(
        self,
        catalog: HandProviderCatalog,
        tool_profiles: Mapping[str, Mapping[str, Any]],
    ) -> None:
        self._catalog = catalog
        self._profiles: dict[str, Mapping[str, Any]] = {}
        self._profile_paths: dict[str, Path | None] = {}
        for name, profile in tool_profiles.items():
            source_path = getattr(profile, "source_path", None)
            copied = deepcopy(dict(profile))
            if copied.get("name") != name:
                raise ValueError("MCP Tool registry key does not match profile name")
            self._profiles[name] = copied
            self._profile_paths[name] = (
                source_path.resolve() if isinstance(source_path, Path) else None
            )

    def _is_registered(self, name: str) -> bool:
        profile = self._profiles[name]
        metadata = profile.get("_meta")
        if not isinstance(metadata, Mapping):
            return False
        capability = metadata.get("dev.jidan/capability-v0.1")
        return isinstance(capability, Mapping) and capability.get("registered") is True

    def list_tools(self) -> tuple[Mapping[str, Any], ...]:
        visible: list[Mapping[str, Any]] = []
        for name in sorted(self._profiles):
            if not self._is_registered(name):
                continue
            if name == self.INSPECT_TOOL:
                visible.append(deepcopy(self._profiles[name]))
                continue
            if name == self.SANDBOX_TOOL and self._catalog.is_bound(
                "android.hand.jidan.accessibility.v0.1"
            ):
                visible.append(deepcopy(self._profiles[name]))
        return tuple(visible)

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        if name not in self._profiles:
            raise KeyError(f"unknown MCP Tool: {name}")
        if not isinstance(arguments, Mapping):
            raise HandProviderError("MCP Tool arguments must be an object")
        if not self._is_registered(name):
            raise HandProviderError(f"MCP Tool is not registered: {name}")
        self._validate_tool_value(name, "inputSchema", arguments)
        if name == self.INSPECT_TOOL:
            if arguments:
                raise HandProviderError("provider inspection accepts empty input")
            output = self._catalog.discovery_output()
        elif name == self.SANDBOX_TOOL:
            output = self._catalog.execute(
                "android.hand.jidan.accessibility.v0.1",
                "SANDBOX",
                arguments,
            )
        else:
            raise HandProviderError(f"MCP Tool is not bound: {name}")
        self._validate_tool_value(name, "outputSchema", output)
        return output

    def _validate_tool_value(
        self,
        name: str,
        schema_field: str,
        value: Any,
    ) -> None:
        source_path = self._profile_paths[name]
        if source_path is None:
            raise HandProviderError(
                f"registered MCP Tool has no trusted schema source: {name}"
            )
        schema = self._profiles[name].get(schema_field)
        if not isinstance(schema, Mapping):
            raise HandProviderError(f"MCP Tool has no {schema_field}: {name}")
        try:
            _validate_json_schema(value, schema, source_path)
        except (TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
            surface = "input" if schema_field == "inputSchema" else "output"
            raise HandProviderError(
                f"MCP Tool {surface} violates its registered contract: {name}: {exc}"
            ) from exc


def load_tool_profile(path: str | Path) -> Mapping[str, Any]:
    source_path = Path(path).resolve()
    with source_path.open("r", encoding="utf-8") as stream:
        raw = json.load(stream)
    name = raw.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("MCP Tool profile has no name")
    if not isinstance(raw.get("inputSchema"), Mapping):
        raise ValueError("MCP Tool profile has no input schema")
    if not isinstance(raw.get("outputSchema"), Mapping):
        raise ValueError("MCP Tool profile has no output schema")
    metadata = raw.get("_meta")
    capability = (
        metadata.get("dev.jidan/capability-v0.1")
        if isinstance(metadata, Mapping)
        else None
    )
    if not isinstance(capability, Mapping) or type(capability.get("registered")) is not bool:
        raise ValueError("MCP Tool profile must declare a boolean registration state")
    return _LoadedToolProfile(raw, source_path)


def _validate_json_schema(
    value: Any,
    schema: Mapping[str, Any] | bool,
    schema_path: Path,
    path: str = "$",
) -> None:
    """Validate the closed JSON Schema subset used by checked-in JCL Tools."""

    if schema is True:
        return
    if schema is False:
        raise ValueError(f"{path} matched a forbidden schema")
    if not isinstance(schema, Mapping):
        raise TypeError(f"{path} schema must be an object or boolean")

    reference = schema.get("$ref")
    if reference is not None:
        if not isinstance(reference, str) or reference.startswith(
            ("http://", "https://", "#")
        ):
            raise ValueError(f"{path} has an unsupported schema reference")
        referenced_path = (schema_path.parent / reference).resolve()
        with referenced_path.open("r", encoding="utf-8") as stream:
            referenced_schema = json.load(stream)
        _validate_json_schema(value, referenced_schema, referenced_path, path)

    for child_schema in schema.get("allOf", ()):
        _validate_json_schema(value, child_schema, schema_path, path)

    condition = schema.get("if")
    if isinstance(condition, Mapping):
        branch = "then" if _schema_matches(value, condition, schema_path) else "else"
        if branch in schema:
            _validate_json_schema(value, schema[branch], schema_path, path)

    forbidden = schema.get("not")
    if isinstance(forbidden, Mapping) and _schema_matches(
        value, forbidden, schema_path
    ):
        raise ValueError(f"{path} matched a forbidden schema")

    if "const" in schema and value != schema["const"]:
        raise ValueError(f"{path} does not match its constant")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path} is outside its enum")

    expected_type = schema.get("type")
    if expected_type is not None:
        expected = (
            (expected_type,)
            if isinstance(expected_type, str)
            else tuple(expected_type)
        )
        if not any(_json_type_matches(value, candidate) for candidate in expected):
            raise ValueError(f"{path} has the wrong JSON type")

    if isinstance(value, Mapping):
        for key in schema.get("required", ()):
            if key not in value:
                raise ValueError(f"{path}.{key} is required")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extras = set(value) - set(properties)
            if extras:
                raise ValueError(f"{path} contains additional properties")
        if isinstance(properties, Mapping):
            for key, child in value.items():
                child_schema = properties.get(key)
                if isinstance(child_schema, (Mapping, bool)):
                    _validate_json_schema(
                        child,
                        child_schema,
                        schema_path,
                        f"{path}.{key}",
                    )

    if isinstance(value, (list, tuple)):
        if "minItems" in schema and len(value) < int(schema["minItems"]):
            raise ValueError(f"{path} has too few items")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise ValueError(f"{path} has too many items")
        if schema.get("uniqueItems"):
            normalized = [
                json.dumps(
                    item,
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                for item in value
            ]
            if len(normalized) != len(set(normalized)):
                raise ValueError(f"{path} items must be unique")
        item_schema = schema.get("items")
        if isinstance(item_schema, (Mapping, bool)):
            for index, child in enumerate(value):
                _validate_json_schema(
                    child,
                    item_schema,
                    schema_path,
                    f"{path}[{index}]",
                )

    if isinstance(value, str):
        if "minLength" in schema and len(value) < int(schema["minLength"]):
            raise ValueError(f"{path} is shorter than minLength")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise ValueError(f"{path} is longer than maxLength")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, value) is None:
            raise ValueError(f"{path} does not match its pattern")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ValueError(f"{path} is below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValueError(f"{path} is above maximum")


def _schema_matches(value: Any, schema: Mapping[str, Any], schema_path: Path) -> bool:
    try:
        _validate_json_schema(value, schema, schema_path)
    except (TypeError, ValueError, OSError, json.JSONDecodeError):
        return False
    return True


def _json_type_matches(value: Any, expected: str) -> bool:
    return {
        "null": value is None,
        "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "string": isinstance(value, str),
        "array": isinstance(value, (list, tuple)),
        "object": isinstance(value, Mapping),
    }.get(expected, False)

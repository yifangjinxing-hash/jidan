from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import json
import re


BRAIN_ACTION_PROFILE = "Jidan-Brain-Action/0.1"
JCL_HAND_INTENT_PROFILE = "JCL-Hand-Intent/0.1-dev"
JCL_HAND_IR_PROFILE = "JCL-Hand-IR/0.1-dev"
HAND_ADAPTER_PROFILE = "JCL-Hand-Adapter/0.1"
ACCESSIBILITY_PAYLOAD_PROFILE = "Jidan-Accessibility-Hand-Payload/0.1-dev"

ACCESSIBILITY_ADAPTER_ID = "android.hand.adapter.jidan.accessibility.dev.v0.1"
MOBILEANJIAN_ADAPTER_ID = "android.hand.adapter.cyjh.mobileanjian.reserved.v0.1"

HAND_IR_ACCESSIBILITY_COMPILER_ID = "compiler.jidan.hand-ir.accessibility-payload.v0.1"
MOBILEANJIAN_PROVIDER_ID = "android.hand.candidate.cyjh.mobileanjian.v0.1"

_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,159}$")
_ANDROID_PACKAGE = re.compile(
    r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$"
)
_LOCALE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

_ACTION_KINDS = {
    "LAUNCH_APP",
    "CLICK",
    "SET_TEXT",
    "SCROLL_FORWARD",
    "BACK",
    "WAIT",
}
_SENSITIVITIES = {
    "NONE",
    "PAYMENT",
    "PASSWORD",
    "OTP",
    "BIOMETRIC",
    "SYSTEM_SECURITY",
}
_SELECTOR_ROLES = {
    "BUTTON",
    "EDIT_TEXT",
    "TEXT",
    "LIST",
    "LIST_ITEM",
    "CHECKBOX",
    "SWITCH",
    "CONTAINER",
}
_IR_OPCODES = {
    "OPEN_PACKAGE",
    "FIND_CLICK",
    "FIND_SET_TEXT",
    "FIND_SCROLL_FORWARD",
    "GLOBAL_BACK",
    "WAIT_MS",
}
_ACCESSIBILITY_OPERATIONS = {
    "OPEN_PACKAGE",
    "FIND_AND_CLICK",
    "FIND_AND_SET_TEXT",
    "FIND_AND_SCROLL_FORWARD",
    "GLOBAL_BACK",
    "WAIT_MS",
}
_ADAPTER_STATES = {"COMPILER_READY", "RESERVED_UNBOUND"}
_CONTENT_POLICY = "DEVELOPMENT_PASS_THROUGH"


class HandCompileError(ValueError):
    """A brain command, JCL intent, Hand IR, or adapter binding is malformed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class _CanonicalDocument:
    _json: str

    @classmethod
    def _from_validated(cls, value: Mapping[str, Any]) -> "_CanonicalDocument":
        return cls(_canonical_json(value))

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self._json)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self._json.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class JclHandIntent(_CanonicalDocument):
    """Content-neutral JCL intent emitted by the Jidan brain boundary."""

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "JclHandIntent":
        _validate_jcl_intent(raw)
        return cls(_canonical_json(raw))


@dataclass(frozen=True)
class HandIrProgram(_CanonicalDocument):
    """Provider-neutral Hand IR. It has no device execution authority."""

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "HandIrProgram":
        _validate_hand_ir(raw)
        return cls(_canonical_json(raw))


@dataclass(frozen=True)
class AdapterCompilation(_CanonicalDocument):
    """A compiler result, including honest unbound adapter reservations."""

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "AdapterCompilation":
        _validate_adapter_compilation(raw)
        return cls(_canonical_json(raw))


@dataclass(frozen=True)
class HandAdapterProfile:
    adapter_id: str
    binding_kind: str
    binding_id: str
    binding_registration_sha256: str
    state: str
    compiler: str | None
    input_profile: str
    output_profile: str | None
    supported_opcodes: tuple[str, ...]
    content_policy: str
    device_consumer_available: bool
    private_interface_available: bool
    notes: tuple[str, ...]
    source: Mapping[str, Any]

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "HandAdapterProfile":
        if not isinstance(raw, Mapping):
            raise TypeError("hand adapter profile must be an object")
        expected = {
            "profile",
            "adapterId",
            "bindingKind",
            "bindingId",
            "bindingRegistrationSha256",
            "state",
            "compiler",
            "inputProfile",
            "outputProfile",
            "supportedOpcodes",
            "contentPolicy",
            "deviceConsumerAvailable",
            "privateInterfaceAvailable",
            "notes",
        }
        if set(raw) != expected or raw.get("profile") != HAND_ADAPTER_PROFILE:
            raise HandCompileError("invalid_adapter_profile", "adapter profile fields do not match")
        adapter_id = raw["adapterId"]
        binding_kind = raw["bindingKind"]
        binding_id = raw["bindingId"]
        binding_registration_sha256 = raw["bindingRegistrationSha256"]
        state = raw["state"]
        compiler = raw["compiler"]
        input_profile = raw["inputProfile"]
        output_profile = raw["outputProfile"]
        opcodes = raw["supportedOpcodes"]
        content_policy = raw["contentPolicy"]
        notes = raw["notes"]
        if not isinstance(adapter_id, str) or _ID.fullmatch(adapter_id) is None:
            raise HandCompileError("invalid_adapter_profile", "invalid adapter id")
        if binding_kind not in {"COMPILER_ONLY", "HAND_PROVIDER"}:
            raise HandCompileError("invalid_adapter_profile", "invalid binding kind")
        if not isinstance(binding_id, str) or _ID.fullmatch(binding_id) is None:
            raise HandCompileError("invalid_adapter_profile", "invalid binding id")
        if (
            not isinstance(binding_registration_sha256, str)
            or _SHA256.fullmatch(binding_registration_sha256) is None
        ):
            raise HandCompileError("invalid_adapter_profile", "invalid binding registration digest")
        if state not in _ADAPTER_STATES:
            raise HandCompileError("invalid_adapter_profile", "invalid adapter state")
        if input_profile != JCL_HAND_IR_PROFILE:
            raise HandCompileError("invalid_adapter_profile", "unsupported adapter input profile")
        if content_policy != _CONTENT_POLICY:
            raise HandCompileError("invalid_adapter_profile", "adapter may not rewrite command content")
        if not isinstance(opcodes, list) or len(opcodes) != len(set(opcodes)):
            raise HandCompileError("invalid_adapter_profile", "invalid supported opcodes")
        if not all(isinstance(item, str) and item in _IR_OPCODES for item in opcodes):
            raise HandCompileError("invalid_adapter_profile", "adapter declares unknown opcodes")
        if type(raw["deviceConsumerAvailable"]) is not bool:
            raise HandCompileError("invalid_adapter_profile", "device consumer flag must be boolean")
        if type(raw["privateInterfaceAvailable"]) is not bool:
            raise HandCompileError("invalid_adapter_profile", "private interface flag must be boolean")
        if not isinstance(notes, list) or not all(
            isinstance(item, str) and 1 <= len(item) <= 300 for item in notes
        ):
            raise HandCompileError("invalid_adapter_profile", "invalid adapter notes")

        if state == "COMPILER_READY":
            if binding_kind != "COMPILER_ONLY":
                raise HandCompileError("invalid_adapter_profile", "ready compiler needs compiler binding")
            if not isinstance(compiler, str) or not compiler:
                raise HandCompileError("invalid_adapter_profile", "ready adapter needs a compiler")
            if not isinstance(output_profile, str) or not output_profile:
                raise HandCompileError("invalid_adapter_profile", "ready adapter needs an output profile")
        else:
            if binding_kind != "HAND_PROVIDER":
                raise HandCompileError("invalid_adapter_profile", "reserved hand needs provider binding")
            if compiler is not None or output_profile is not None or opcodes:
                raise HandCompileError(
                    "invalid_adapter_profile",
                    "reserved adapter cannot claim a compiler, output, or opcodes",
                )
            if raw["deviceConsumerAvailable"] or raw["privateInterfaceAvailable"]:
                raise HandCompileError(
                    "invalid_adapter_profile",
                    "reserved adapter cannot claim an executable interface",
                )

        return cls(
            adapter_id=adapter_id,
            binding_kind=binding_kind,
            binding_id=binding_id,
            binding_registration_sha256=binding_registration_sha256,
            state=state,
            compiler=compiler,
            input_profile=input_profile,
            output_profile=output_profile,
            supported_opcodes=tuple(opcodes),
            content_policy=content_policy,
            device_consumer_available=raw["deviceConsumerAvailable"],
            private_interface_available=raw["privateInterfaceAvailable"],
            notes=tuple(notes),
            source=deepcopy(dict(raw)),
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "HandAdapterProfile":
        with Path(path).open("r", encoding="utf-8") as stream:
            return cls.from_dict(json.load(stream))


class BrainToJclCompiler:
    """Normalize a structured brain result without applying keyword policy."""

    def compile(self, command: Mapping[str, Any]) -> JclHandIntent:
        _validate_brain_command(command)
        intent = {
            "profile": JCL_HAND_INTENT_PROFILE,
            "requestId": command["requestId"],
            "locale": command["locale"],
            "goal": command["goal"],
            "targetPackage": command["targetPackage"],
            "actions": deepcopy(command["actions"]),
            "source": {
                "profile": BRAIN_ACTION_PROFILE,
                "contentPolicy": _CONTENT_POLICY,
            },
        }
        return JclHandIntent.from_dict(intent)


class JclToHandIrCompiler:
    """Lower JCL actions into a small, provider-neutral instruction set."""

    _OPCODES = {
        "LAUNCH_APP": "OPEN_PACKAGE",
        "CLICK": "FIND_CLICK",
        "SET_TEXT": "FIND_SET_TEXT",
        "SCROLL_FORWARD": "FIND_SCROLL_FORWARD",
        "BACK": "GLOBAL_BACK",
        "WAIT": "WAIT_MS",
    }

    def compile(self, intent: JclHandIntent | Mapping[str, Any]) -> HandIrProgram:
        document = intent if isinstance(intent, JclHandIntent) else JclHandIntent.from_dict(intent)
        source = document.to_dict()
        instructions: list[dict[str, Any]] = []
        for action in source["actions"]:
            operand: str | int | None
            if action["actionKind"] == "SET_TEXT":
                operand = action["value"]
            elif action["actionKind"] == "WAIT":
                operand = action["durationMs"]
            elif action["actionKind"] == "LAUNCH_APP":
                operand = source["targetPackage"]
            else:
                operand = None
            instructions.append(
                {
                    "instructionId": action["actionId"],
                    "opcode": self._OPCODES[action["actionKind"]],
                    "sensitivity": action["sensitivity"],
                    "selector": deepcopy(action.get("selector")),
                    "operand": operand,
                }
            )
        program = {
            "profile": JCL_HAND_IR_PROFILE,
            "programId": source["requestId"],
            "sourceIntentSha256": document.sha256,
            "targetPackage": source["targetPackage"],
            "contentPolicy": _CONTENT_POLICY,
            "instructions": instructions,
            "executionAuthority": "NONE",
        }
        return HandIrProgram.from_dict(program)


class HandAdapterRegistry:
    """Compile Hand IR for reviewed adapters; never invent an unavailable API."""

    def __init__(self) -> None:
        self._profiles: dict[str, HandAdapterProfile] = {}

    def load_directory(self, directory: str | Path) -> None:
        for path in sorted(Path(directory).glob("*.json")):
            self.register(HandAdapterProfile.from_file(path))

    def register(self, profile: HandAdapterProfile) -> None:
        normalized = HandAdapterProfile.from_dict(profile.source)
        if normalized != profile:
            raise HandCompileError(
                "adapter_profile_mismatch",
                "adapter fields do not match canonical source",
            )
        if profile.adapter_id in self._profiles:
            raise HandCompileError("duplicate_adapter", "duplicate hand adapter")
        self._profiles[profile.adapter_id] = normalized

    def get(self, adapter_id: str) -> HandAdapterProfile:
        try:
            return deepcopy(self._profiles[adapter_id])
        except KeyError as exc:
            raise HandCompileError("unknown_adapter", f"unknown hand adapter: {adapter_id}") from exc

    def compile(
        self,
        adapter_id: str,
        program: HandIrProgram | Mapping[str, Any],
    ) -> AdapterCompilation:
        ir = program if isinstance(program, HandIrProgram) else HandIrProgram.from_dict(program)
        profile = self.get(adapter_id)
        if profile.state == "RESERVED_UNBOUND":
            return AdapterCompilation.from_dict(
                {
                    "status": "ADAPTER_UNBOUND",
                    "adapterId": profile.adapter_id,
                    "bindingKind": profile.binding_kind,
                    "bindingId": profile.binding_id,
                    "bindingRegistrationSha256": profile.binding_registration_sha256,
                    "sourceIrSha256": ir.sha256,
                    "payloadProfile": None,
                    "payload": None,
                    "deviceExecutionAttempted": False,
                    "privateInterfaceInvoked": False,
                    "reasonCode": "NO_VERIFIED_VENDOR_CONTRACT",
                }
            )
        if profile.compiler != "jidan.accessibility.semantic-dev-v0.1":
            raise HandCompileError("compiler_unavailable", "reviewed adapter compiler is unavailable")
        unknown = {
            item["opcode"] for item in ir.to_dict()["instructions"]
        } - set(profile.supported_opcodes)
        if unknown:
            raise HandCompileError(
                "unsupported_opcode",
                f"adapter does not support Hand IR opcodes: {sorted(unknown)}",
            )
        payload = self._compile_accessibility(ir)
        return AdapterCompilation.from_dict(
            {
                "status": "COMPILED",
                "adapterId": profile.adapter_id,
                "bindingKind": profile.binding_kind,
                "bindingId": profile.binding_id,
                "bindingRegistrationSha256": profile.binding_registration_sha256,
                "sourceIrSha256": ir.sha256,
                "payloadProfile": profile.output_profile,
                "payload": payload,
                "deviceExecutionAttempted": False,
                "privateInterfaceInvoked": False,
                "reasonCode": None,
            }
        )

    @staticmethod
    def _compile_accessibility(program: HandIrProgram) -> dict[str, Any]:
        operation_names = {
            "OPEN_PACKAGE": "OPEN_PACKAGE",
            "FIND_CLICK": "FIND_AND_CLICK",
            "FIND_SET_TEXT": "FIND_AND_SET_TEXT",
            "FIND_SCROLL_FORWARD": "FIND_AND_SCROLL_FORWARD",
            "GLOBAL_BACK": "GLOBAL_BACK",
            "WAIT_MS": "WAIT_MS",
        }
        source = program.to_dict()
        operations = [
            {
                "operationId": instruction["instructionId"],
                "operation": operation_names[instruction["opcode"]],
                "sensitivity": instruction["sensitivity"],
                "selector": deepcopy(instruction["selector"]),
                "argument": instruction["operand"],
            }
            for instruction in source["instructions"]
        ]
        return {
            "profile": ACCESSIBILITY_PAYLOAD_PROFILE,
            "targetPackage": source["targetPackage"],
            "contentPolicy": _CONTENT_POLICY,
            "operations": operations,
        }


class BrainToHandCompiler:
    """Convenience facade for Brain -> JCL -> Hand IR -> adapter compilation."""

    def __init__(self, adapters: HandAdapterRegistry) -> None:
        self.brain = BrainToJclCompiler()
        self.hand_ir = JclToHandIrCompiler()
        self.adapters = adapters

    def compile(
        self,
        command: Mapping[str, Any],
        *,
        adapter_id: str = ACCESSIBILITY_ADAPTER_ID,
    ) -> tuple[JclHandIntent, HandIrProgram, AdapterCompilation]:
        intent = self.brain.compile(command)
        program = self.hand_ir.compile(intent)
        artifact = self.adapters.compile(adapter_id, program)
        return intent, program, artifact


def _validate_brain_command(raw: Mapping[str, Any]) -> None:
    _validate_action_document(raw, BRAIN_ACTION_PROFILE, include_source=False)


def _validate_jcl_intent(raw: Mapping[str, Any]) -> None:
    _validate_action_document(raw, JCL_HAND_INTENT_PROFILE, include_source=True)


def _validate_action_document(
    raw: Mapping[str, Any],
    expected_profile: str,
    *,
    include_source: bool,
) -> None:
    if not isinstance(raw, Mapping):
        raise TypeError("brain/JCL document must be an object")
    expected = {"profile", "requestId", "locale", "goal", "targetPackage", "actions"}
    if include_source:
        expected.add("source")
    if set(raw) != expected or raw.get("profile") != expected_profile:
        raise HandCompileError("invalid_intent", "brain/JCL document fields do not match")
    request_id = raw["requestId"]
    locale = raw["locale"]
    goal = raw["goal"]
    package = raw["targetPackage"]
    actions = raw["actions"]
    if not isinstance(request_id, str) or _ID.fullmatch(request_id) is None:
        raise HandCompileError("invalid_intent", "invalid request id")
    if not isinstance(locale, str) or _LOCALE.fullmatch(locale) is None:
        raise HandCompileError("invalid_intent", "invalid locale")
    if not isinstance(goal, str) or not goal or "\x00" in goal or len(goal) > 4096:
        raise HandCompileError("invalid_intent", "invalid goal text")
    if not isinstance(package, str) or _ANDROID_PACKAGE.fullmatch(package) is None:
        raise HandCompileError("invalid_intent", "invalid Android package")
    if not isinstance(actions, list) or not 1 <= len(actions) <= 64:
        raise HandCompileError("invalid_intent", "actions must contain 1 to 64 steps")
    ids: list[str] = []
    for action in actions:
        _validate_action(action)
        ids.append(action["actionId"])
    if len(ids) != len(set(ids)):
        raise HandCompileError("invalid_intent", "action ids must be unique")
    if include_source:
        source = raw["source"]
        if not isinstance(source, Mapping) or set(source) != {"profile", "contentPolicy"}:
            raise HandCompileError("invalid_intent", "invalid intent source")
        if source.get("profile") != BRAIN_ACTION_PROFILE or source.get("contentPolicy") != _CONTENT_POLICY:
            raise HandCompileError("invalid_intent", "intent source boundary does not match")


def _validate_action(action: Any) -> None:
    if not isinstance(action, Mapping):
        raise HandCompileError("invalid_action", "action must be an object")
    required = {"actionId", "actionKind", "sensitivity"}
    optional = {"selector", "value", "durationMs"}
    if not required <= set(action) or not set(action) <= required | optional:
        raise HandCompileError("invalid_action", "action fields do not match")
    action_id = action["actionId"]
    kind = action["actionKind"]
    sensitivity = action["sensitivity"]
    if not isinstance(action_id, str) or _ID.fullmatch(action_id) is None:
        raise HandCompileError("invalid_action", "invalid action id")
    if kind not in _ACTION_KINDS or sensitivity not in _SENSITIVITIES:
        raise HandCompileError("invalid_action", "unknown action kind or sensitivity")
    needs_selector = kind in {"CLICK", "SET_TEXT", "SCROLL_FORWARD"}
    if needs_selector != ("selector" in action):
        raise HandCompileError("invalid_action", f"{kind} selector requirement does not match")
    if "selector" in action:
        _validate_selector(action["selector"])
    if kind == "SET_TEXT":
        value = action.get("value")
        if not isinstance(value, str) or "\x00" in value or len(value) > 65536:
            raise HandCompileError("invalid_action", "SET_TEXT requires finite text")
    elif "value" in action:
        raise HandCompileError("invalid_action", "only SET_TEXT accepts a value")
    if kind == "WAIT":
        duration = action.get("durationMs")
        if isinstance(duration, bool) or not isinstance(duration, int) or duration < 0:
            raise HandCompileError("invalid_action", "WAIT requires durationMs")
    elif "durationMs" in action:
        raise HandCompileError("invalid_action", "only WAIT accepts durationMs")


def _validate_selector(selector: Any) -> None:
    if not isinstance(selector, Mapping):
        raise HandCompileError("invalid_selector", "selector must be an object")
    allowed = {"viewId", "className", "semanticRole", "text", "contentDescription"}
    if not selector or not set(selector) <= allowed:
        raise HandCompileError("invalid_selector", "selector fields do not match")
    for name, value in selector.items():
        if not isinstance(value, str) or not value or "\x00" in value or len(value) > 1024:
            raise HandCompileError("invalid_selector", f"invalid selector {name}")
    if "semanticRole" in selector and selector["semanticRole"] not in _SELECTOR_ROLES:
        raise HandCompileError("invalid_selector", "unknown semantic role")


def _validate_hand_ir(raw: Mapping[str, Any]) -> None:
    expected = {
        "profile",
        "programId",
        "sourceIntentSha256",
        "targetPackage",
        "contentPolicy",
        "instructions",
        "executionAuthority",
    }
    if not isinstance(raw, Mapping) or set(raw) != expected:
        raise HandCompileError("invalid_ir", "Hand IR fields do not match")
    if raw.get("profile") != JCL_HAND_IR_PROFILE or raw.get("contentPolicy") != _CONTENT_POLICY:
        raise HandCompileError("invalid_ir", "unsupported Hand IR profile or content policy")
    if raw.get("executionAuthority") != "NONE":
        raise HandCompileError("invalid_ir", "Hand IR cannot grant execution authority")
    if not isinstance(raw["programId"], str) or _ID.fullmatch(raw["programId"]) is None:
        raise HandCompileError("invalid_ir", "invalid Hand IR program id")
    if not isinstance(raw["sourceIntentSha256"], str) or _SHA256.fullmatch(raw["sourceIntentSha256"]) is None:
        raise HandCompileError("invalid_ir", "invalid source intent digest")
    if not isinstance(raw["targetPackage"], str) or _ANDROID_PACKAGE.fullmatch(raw["targetPackage"]) is None:
        raise HandCompileError("invalid_ir", "invalid Hand IR target package")
    instructions = raw["instructions"]
    if not isinstance(instructions, list) or not 1 <= len(instructions) <= 64:
        raise HandCompileError("invalid_ir", "invalid Hand IR instructions")
    ids: list[str] = []
    for instruction in instructions:
        if not isinstance(instruction, Mapping) or set(instruction) != {
            "instructionId",
            "opcode",
            "sensitivity",
            "selector",
            "operand",
        }:
            raise HandCompileError("invalid_ir", "Hand IR instruction fields do not match")
        instruction_id = instruction["instructionId"]
        if not isinstance(instruction_id, str) or _ID.fullmatch(instruction_id) is None:
            raise HandCompileError("invalid_ir", "invalid Hand IR instruction id")
        ids.append(instruction_id)
        if instruction["opcode"] not in _IR_OPCODES or instruction["sensitivity"] not in _SENSITIVITIES:
            raise HandCompileError("invalid_ir", "unknown Hand IR opcode or sensitivity")
        selector = instruction["selector"]
        if selector is not None:
            _validate_selector(selector)
        operand = instruction["operand"]
        if not (operand is None or (isinstance(operand, (str, int)) and not isinstance(operand, bool))):
            raise HandCompileError("invalid_ir", "invalid Hand IR operand")
        opcode = instruction["opcode"]
        requires_selector = opcode in {
            "FIND_CLICK",
            "FIND_SET_TEXT",
            "FIND_SCROLL_FORWARD",
        }
        if requires_selector != (selector is not None):
            raise HandCompileError("invalid_ir", f"{opcode} selector requirement does not match")
        if opcode == "FIND_SET_TEXT" and not isinstance(operand, str):
            raise HandCompileError("invalid_ir", "FIND_SET_TEXT requires a text operand")
        if opcode == "WAIT_MS" and (
            isinstance(operand, bool)
            or not isinstance(operand, int)
            or operand < 0
        ):
            raise HandCompileError("invalid_ir", "WAIT_MS requires an integer operand")
        if opcode == "OPEN_PACKAGE" and (
            not isinstance(operand, str)
            or operand != raw["targetPackage"]
        ):
            raise HandCompileError("invalid_ir", "OPEN_PACKAGE must use the target package")
        if opcode in {"FIND_CLICK", "FIND_SCROLL_FORWARD", "GLOBAL_BACK"} and operand is not None:
            raise HandCompileError("invalid_ir", f"{opcode} does not accept an operand")
    if len(ids) != len(set(ids)):
        raise HandCompileError("invalid_ir", "Hand IR instruction ids must be unique")


def _validate_adapter_compilation(raw: Mapping[str, Any]) -> None:
    expected = {
        "status",
        "adapterId",
        "bindingKind",
        "bindingId",
        "bindingRegistrationSha256",
        "sourceIrSha256",
        "payloadProfile",
        "payload",
        "deviceExecutionAttempted",
        "privateInterfaceInvoked",
        "reasonCode",
    }
    if not isinstance(raw, Mapping) or set(raw) != expected:
        raise HandCompileError("invalid_compilation", "adapter compilation fields do not match")
    if raw["status"] not in {"COMPILED", "ADAPTER_UNBOUND"}:
        raise HandCompileError("invalid_compilation", "invalid adapter compilation status")
    for key in ("adapterId", "bindingId"):
        if not isinstance(raw[key], str) or _ID.fullmatch(raw[key]) is None:
            raise HandCompileError("invalid_compilation", f"invalid {key}")
    if raw["bindingKind"] not in {"COMPILER_ONLY", "HAND_PROVIDER"}:
        raise HandCompileError("invalid_compilation", "invalid binding kind")
    if (
        not isinstance(raw["bindingRegistrationSha256"], str)
        or _SHA256.fullmatch(raw["bindingRegistrationSha256"]) is None
    ):
        raise HandCompileError("invalid_compilation", "invalid binding registration digest")
    if not isinstance(raw["sourceIrSha256"], str) or _SHA256.fullmatch(raw["sourceIrSha256"]) is None:
        raise HandCompileError("invalid_compilation", "invalid Hand IR digest")
    if raw["deviceExecutionAttempted"] is not False or raw["privateInterfaceInvoked"] is not False:
        raise HandCompileError("invalid_compilation", "prototype compilation cannot claim device execution")
    if raw["status"] == "COMPILED":
        if raw["bindingKind"] != "COMPILER_ONLY":
            raise HandCompileError("invalid_compilation", "compiled result needs compiler binding")
        if raw["payloadProfile"] != ACCESSIBILITY_PAYLOAD_PROFILE:
            raise HandCompileError("invalid_compilation", "unknown compiled payload profile")
        _validate_accessibility_payload(raw["payload"])
        if raw["reasonCode"] is not None:
            raise HandCompileError("invalid_compilation", "compiled result cannot carry a failure reason")
    else:
        if raw["bindingKind"] != "HAND_PROVIDER":
            raise HandCompileError("invalid_compilation", "unbound result needs provider binding")
        if raw["payloadProfile"] is not None or raw["payload"] is not None:
            raise HandCompileError("invalid_compilation", "unbound adapter cannot return a payload")
        if raw["reasonCode"] != "NO_VERIFIED_VENDOR_CONTRACT":
            raise HandCompileError("invalid_compilation", "unbound adapter reason is not explicit")


def _validate_accessibility_payload(raw: Any) -> None:
    expected = {"profile", "targetPackage", "contentPolicy", "operations"}
    if not isinstance(raw, Mapping) or set(raw) != expected:
        raise HandCompileError("invalid_payload", "accessibility payload fields do not match")
    if raw["profile"] != ACCESSIBILITY_PAYLOAD_PROFILE or raw["contentPolicy"] != _CONTENT_POLICY:
        raise HandCompileError("invalid_payload", "unsupported accessibility payload")
    if not isinstance(raw["targetPackage"], str) or _ANDROID_PACKAGE.fullmatch(raw["targetPackage"]) is None:
        raise HandCompileError("invalid_payload", "invalid accessibility target package")
    operations = raw["operations"]
    if not isinstance(operations, list) or not operations:
        raise HandCompileError("invalid_payload", "accessibility operations are empty")
    for operation in operations:
        if not isinstance(operation, Mapping) or set(operation) != {
            "operationId",
            "operation",
            "sensitivity",
            "selector",
            "argument",
        }:
            raise HandCompileError("invalid_payload", "accessibility operation fields do not match")
        if operation["operation"] not in _ACCESSIBILITY_OPERATIONS:
            raise HandCompileError("invalid_payload", "unknown accessibility operation")
        if operation["sensitivity"] not in _SENSITIVITIES:
            raise HandCompileError("invalid_payload", "unknown accessibility sensitivity")
        if not isinstance(operation["operationId"], str) or _ID.fullmatch(operation["operationId"]) is None:
            raise HandCompileError("invalid_payload", "invalid accessibility operation id")
        selector = operation["selector"]
        if selector is not None:
            _validate_selector(selector)
        needs_selector = operation["operation"] in {
            "FIND_AND_CLICK",
            "FIND_AND_SET_TEXT",
            "FIND_AND_SCROLL_FORWARD",
        }
        if needs_selector != (selector is not None):
            raise HandCompileError("invalid_payload", "accessibility selector requirement does not match")
        argument = operation["argument"]
        if operation["operation"] == "FIND_AND_SET_TEXT" and not isinstance(argument, str):
            raise HandCompileError("invalid_payload", "text operation needs a string argument")
        if operation["operation"] == "WAIT_MS" and (
            isinstance(argument, bool)
            or not isinstance(argument, int)
            or argument < 0
        ):
            raise HandCompileError("invalid_payload", "wait operation needs milliseconds")
        if operation["operation"] == "OPEN_PACKAGE" and (
            not isinstance(argument, str) or argument != raw["targetPackage"]
        ):
            raise HandCompileError("invalid_payload", "open operation must use target package")
        if operation["operation"] in {
            "FIND_AND_CLICK",
            "FIND_AND_SCROLL_FORWARD",
            "GLOBAL_BACK",
        } and argument is not None:
            raise HandCompileError("invalid_payload", "operation does not accept an argument")


def _canonical_json(value: Mapping[str, Any]) -> str:
    try:
        return json.dumps(
            deepcopy(dict(value)),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise HandCompileError("non_json_value", "compiler input must be finite JSON") from exc

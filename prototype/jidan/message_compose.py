from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Protocol
import hashlib
import hmac
import re

from .models import Capability, Effect
from .registry import CapabilityRegistry


MESSAGE_COMPOSE_CAPABILITY_ID = "message.compose"
JCL_PROFILE = "JCL/0.1"
JCL_META_KEY = "dev.jidan/capability-v0.1"

HANDOFF_PLANNED = "handoff_planned"
HANDOFF_OPENED = "handoff_opened"

_ID_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]{0,127}$")
_RESERVED_BINDING_KEYS = frozenset(
    {
        "capability",
        "delivery",
        "executionMode",
        "finalStatus",
        "outcome",
        "profile",
        "riskLevel",
        "sent",
        "state",
        "verified",
    }
)

MessageComposeHandler = Callable[[Mapping[str, Any]], Mapping[str, Any]]


class MessageComposeBindingError(RuntimeError):
    """A platform binding failed or crossed the profile trust boundary."""


class WeChatHandoffAdapter(Protocol):
    @staticmethod
    def capability() -> Capability: ...

    def open_handoff(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]: ...


MESSAGE_COMPOSE_INPUT_SCHEMA: Mapping[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "recipient": {
            "type": "string",
            "maxLength": 256,
            "description": (
                "Display-only hint. It is never passed to the platform binding "
                "and cannot preselect a recipient."
            ),
        },
        "content": {
            "type": "string",
            "minLength": 1,
            "maxLength": 4000,
        },
    },
    "required": ["content"],
    "additionalProperties": False,
}


MESSAGE_COMPOSE_OUTPUT_SCHEMA: Mapping[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "state": {"enum": [HANDOFF_PLANNED, HANDOFF_OPENED]},
        "artifact": {
            "type": "object",
            "properties": {
                "mimeType": {"const": "text/plain"},
                "textSha256": {
                    "type": "string",
                    "minLength": 64,
                    "maxLength": 64,
                },
                "recipientHint": {"type": "string", "maxLength": 256},
            },
            "required": ["mimeType", "textSha256"],
            "additionalProperties": False,
        },
        "delivery": {
            "type": "object",
            "properties": {
                "attempted": {"const": False},
                "sent": {"const": False},
                "verified": {"const": False},
            },
            "required": ["attempted", "sent", "verified"],
            "additionalProperties": False,
        },
        "adapter": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "minLength": 1},
                "platform": {"type": "string", "minLength": 1},
                "surface": {"type": "string", "minLength": 1},
                "binding": {"type": "object"},
            },
            "required": ["id", "platform", "surface", "binding"],
            "additionalProperties": False,
        },
        "nextAction": {"const": "user_review_and_send"},
    },
    "required": ["state", "artifact", "delivery", "adapter", "nextAction"],
    "additionalProperties": False,
}


def message_compose_capability(
    *,
    app: str = "jidan.host",
    scopes: frozenset[str] = frozenset(),
    adapter: str = "jcl.platform-handoff",
    reversible: bool = False,
) -> Capability:
    """Build the host capability; a concrete binding may only make it stricter."""

    return Capability(
        id=MESSAGE_COMPOSE_CAPABILITY_ID,
        app=app,
        description=(
            "Prepare an editable message or open a user-controlled handoff "
            "surface. Never choose a recipient and never send the message."
        ),
        effect=Effect.WRITE,
        scopes=frozenset(scopes) | {"message.compose.handoff"},
        requires_confirmation=True,
        reversible=reversible,
        input_schema=MESSAGE_COMPOSE_INPUT_SCHEMA,
        output_schema=MESSAGE_COMPOSE_OUTPUT_SCHEMA,
        adapter=adapter,
    )

def message_compose_mcp_tool() -> dict[str, Any]:
    """Export the capability as an MCP Tool plus namespaced Jidan metadata."""

    capability = message_compose_capability()
    return {
        "name": capability.id,
        "description": capability.description,
        "inputSchema": deepcopy(dict(capability.input_schema)),
        "outputSchema": deepcopy(dict(capability.output_schema)),
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
        "_meta": {
            JCL_META_KEY: {
                "riskLevel": "WRITE",
                "executionMode": "HANDOFF",
                "reversible": capability.reversible,
            }
        },
    }


@dataclass(frozen=True)
class MessageComposeBinding:
    """Bind ``message.compose`` to one locally selected platform adapter.

    The caller invokes only the capability ID. The host chooses this binding at
    startup. The adapter receives message content but never the recipient hint,
    and it cannot author delivery or success claims.
    """

    platform: str
    adapter_id: str
    surface: str
    handler: MessageComposeHandler = field(repr=False, compare=False)
    handoff_state: str = HANDOFF_PLANNED
    app: str = "jidan.host"
    scopes: frozenset[str] = field(default_factory=frozenset)
    reversible: bool = False

    def __post_init__(self) -> None:
        for label, value in (
            ("platform", self.platform),
            ("adapter_id", self.adapter_id),
            ("surface", self.surface),
            ("app", self.app),
        ):
            if not _ID_PATTERN.fullmatch(value):
                raise ValueError(f"invalid {label}: {value!r}")
        if self.handoff_state not in {HANDOFF_PLANNED, HANDOFF_OPENED}:
            raise ValueError(f"invalid handoff state: {self.handoff_state!r}")
        if not callable(self.handler):
            raise TypeError("handler must be callable")

    def capability(self) -> Capability:
        return message_compose_capability(
            app=self.app,
            scopes=self.scopes,
            adapter=self.adapter_id,
            reversible=self.reversible,
        )

    def register(self, registry: CapabilityRegistry) -> Capability:
        capability = self.capability()
        registry.register(capability, self.invoke)
        return capability

    def invoke(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        content = arguments.get("content")
        if not isinstance(content, str) or not 1 <= len(content) <= 4000 or "\x00" in content:
            raise ValueError("content must contain 1..4000 characters and no NUL")

        # Recipient is intentionally absent: it is a display hint, not authority.
        try:
            binding = self.handler({"content": content})
        except Exception as exc:
            if isinstance(exc, MessageComposeBindingError):
                raise
            raise MessageComposeBindingError(
                f"{self.adapter_id} failed before a verified handoff result"
            ) from exc

        if not isinstance(binding, Mapping):
            raise MessageComposeBindingError("binding handler must return an object")
        forbidden = _RESERVED_BINDING_KEYS.intersection(binding)
        if forbidden:
            fields = ", ".join(sorted(forbidden))
            raise MessageComposeBindingError(
                f"binding attempted to author reserved outcome fields: {fields}"
            )

        artifact: dict[str, Any] = {
            "mimeType": "text/plain",
            "textSha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        }
        recipient = arguments.get("recipient")
        if recipient:
            artifact["recipientHint"] = recipient

        return {
            "state": self.handoff_state,
            "artifact": artifact,
            "delivery": {
                "attempted": False,
                "sent": False,
                "verified": False,
            },
            "adapter": {
                "id": self.adapter_id,
                "platform": self.platform,
                "surface": self.surface,
                "binding": deepcopy(dict(binding)),
            },
            "nextAction": "user_review_and_send",
        }


def _android_plan(arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "type": "android.intent",
        "action": "android.intent.action.SEND",
        "mimeType": "text/plain",
        "extras": {"android.intent.extra.TEXT": arguments["content"]},
        "useChooser": True,
    }


def _ios_plan(arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "type": "apple.shortcut",
        "shortcut": "ShareText",
        "input": {"text": arguments["content"]},
        "opensShareSheet": True,
    }


def _web_plan(arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "type": "web.draft",
        "draft": {"body": arguments["content"], "editable": True},
    }


_PLANNED_BINDINGS: Mapping[str, tuple[str, str, MessageComposeHandler]] = {
    "android": ("android.intent.send-plan", "android_share_sheet", _android_plan),
    "ios": ("apple.shortcut.share-text-plan", "apple_share_sheet", _ios_plan),
    "web": ("web.editable-draft-plan", "web_draft", _web_plan),
}


def planned_message_compose_binding(platform: str) -> MessageComposeBinding:
    """Return a data-only built-in plan; it does not claim the UI was opened."""

    platform_id = platform.strip().lower()
    try:
        adapter_id, surface, handler = _PLANNED_BINDINGS[platform_id]
    except KeyError as exc:
        raise KeyError(f"no built-in message.compose plan for {platform!r}") from exc
    return MessageComposeBinding(
        platform=platform_id,
        adapter_id=adapter_id,
        surface=surface,
        handler=handler,
        handoff_state=HANDOFF_PLANNED,
    )


def wechat_message_compose_binding(
    adapter: WeChatHandoffAdapter,
) -> MessageComposeBinding:
    """Wrap the verified Android WeChat handoff behind ``message.compose``."""

    underlying = adapter.capability()

    def open_verified(arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        content = str(arguments["content"])
        output = adapter.open_handoff({"text": content})
        if not isinstance(output, Mapping):
            raise MessageComposeBindingError("WeChat handoff returned no verified object")
        expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        safe = (
            output.get("status") == HANDOFF_OPENED
            and output.get("jidanSelectedRecipient") is False
            and output.get("jidanIssuedSend") is False
            and output.get("deliveryState") == "not_attempted_by_jidan"
            and output.get("nextAction") == "user_select_recipient_and_confirm_send"
            and isinstance(output.get("textSha256"), str)
            and hmac.compare_digest(output["textSha256"], expected_hash)
        )
        if not safe:
            raise MessageComposeBindingError(
                "WeChat handoff did not prove the required no-send invariants"
            )
        return {
            "type": "android.intent.verified-handoff",
            "package": output.get("package"),
            "handler": output.get("handler"),
            "pickerActivity": output.get("pickerActivity"),
            "textSha256": output["textSha256"],
        }

    return MessageComposeBinding(
        platform="android",
        adapter_id="android.intent.wechat.message-compose",
        surface="wechat_recipient_picker",
        handler=open_verified,
        handoff_state=HANDOFF_OPENED,
        app=underlying.app,
        scopes=underlying.scopes,
        reversible=False,
    )

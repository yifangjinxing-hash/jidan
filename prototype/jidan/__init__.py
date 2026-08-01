"""Jidan capability-kernel prototype."""

from .audit import ReceiptLog
from .grant_ledger import (
    GrantConsumption,
    GrantLedgerError,
    InMemoryGrantLedger,
    SqliteGrantLedger,
)
from .models import Capability, Effect, Grant, Step, TaskPlan
from .nlp import NlpParseError, SemanticAction, parse_memo_command, parse_zh_memo_command
from .policy import PolicyEngine, issue_grant
from .registry import CapabilityRegistry
from .runtime import JidanRuntime
from .android_share import (
    AdbWeChatShareAdapter,
    WeChatShareAdapterError,
    WeChatShareHandlerUnavailable,
)
from .semantic_surfaces import (
    SEMANTIC_SURFACE_CAPABILITY_ID,
    AdbSemanticSurfaceProbe,
    SemanticSurfaceProbeError,
)
from .message_compose import (
    HANDOFF_OPENED,
    HANDOFF_PLANNED,
    JCL_META_KEY,
    JCL_PROFILE,
    MESSAGE_COMPOSE_CAPABILITY_ID,
    MessageComposeBinding,
    MessageComposeBindingError,
    message_compose_mcp_tool,
    planned_message_compose_binding,
    wechat_message_compose_binding,
)

__all__ = [
    "Capability",
    "CapabilityRegistry",
    "AdbWeChatShareAdapter",
    "AdbSemanticSurfaceProbe",
    "Effect",
    "Grant",
    "GrantConsumption",
    "GrantLedgerError",
    "InMemoryGrantLedger",
    "JidanRuntime",
    "JCL_META_KEY",
    "JCL_PROFILE",
    "HANDOFF_OPENED",
    "HANDOFF_PLANNED",
    "MESSAGE_COMPOSE_CAPABILITY_ID",
    "MessageComposeBinding",
    "MessageComposeBindingError",
    "NlpParseError",
    "PolicyEngine",
    "ReceiptLog",
    "SemanticAction",
    "SemanticSurfaceProbeError",
    "SEMANTIC_SURFACE_CAPABILITY_ID",
    "SqliteGrantLedger",
    "Step",
    "TaskPlan",
    "WeChatShareAdapterError",
    "WeChatShareHandlerUnavailable",
    "issue_grant",
    "message_compose_mcp_tool",
    "parse_memo_command",
    "parse_zh_memo_command",
    "planned_message_compose_binding",
    "wechat_message_compose_binding",
]

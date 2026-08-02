"""Pure discovery-response classification for protocol adapters.

This module deliberately performs no I/O.  An adapter supplies either an HTTP
response that it already received or a transport exception that it already
caught.  Keeping the classifier separate prevents a valid JSON-RPC call error
from being promoted to a permanent connection/session failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from typing import Any, Mapping


class DiscoveryErrorKind(str, Enum):
    """Stable error categories exposed to discovery callers."""

    AUTH_REQUIRED = "auth_required"
    DISCOVERY_UNSUPPORTED = "discovery_unsupported"
    CALL_ERROR = "call_error"
    PROTOCOL_ERROR = "protocol_error"
    TRANSPORT_ERROR = "transport_error"


@dataclass(frozen=True, slots=True)
class DiscoveryError:
    """A classified discovery failure with no implicit connection mutation."""

    kind: DiscoveryErrorKind
    message: str
    http_status: int | None = None
    rpc_code: int | None = None
    rpc_id: Any = None

    @property
    def is_call_scoped(self) -> bool:
        """Whether the server rejected one JSON-RPC call, not the transport."""

        return self.kind is DiscoveryErrorKind.CALL_ERROR

    @property
    def is_transport_failure(self) -> bool:
        """Whether the failure came from I/O rather than an HTTP response."""

        return self.kind is DiscoveryErrorKind.TRANSPORT_ERROR


class _BodyState(Enum):
    EMPTY = "empty"
    JSON = "json"
    NON_JSON = "non_json"
    MALFORMED = "malformed"


def classify_discovery_response(
    http_status: int,
    body: Any = None,
) -> DiscoveryError | None:
    """Classify an already-received discovery response.

    ``None`` means a valid JSON-RPC success response.  HTTP authentication
    status takes precedence over the response body.  A decodable JSON-RPC
    error is call-scoped even when transported with HTTP 400 or 404; only a
    bare 404 means that the discovery endpoint is unsupported.
    """

    if isinstance(http_status, bool) or not isinstance(http_status, int):
        return _protocol_error(None, "HTTP status must be an integer")
    if not 100 <= http_status <= 599:
        return _protocol_error(http_status, "HTTP status is outside 100..599")

    body_state, payload = _decode_body(body)

    if http_status in {401, 403}:
        return DiscoveryError(
            kind=DiscoveryErrorKind.AUTH_REQUIRED,
            message=f"authentication required (HTTP {http_status})",
            http_status=http_status,
        )

    rpc_error = _parse_jsonrpc_error(payload) if body_state is _BodyState.JSON else None
    if rpc_error is not None:
        return DiscoveryError(
            kind=DiscoveryErrorKind.CALL_ERROR,
            message=rpc_error[1],
            http_status=http_status,
            rpc_code=rpc_error[0],
            rpc_id=rpc_error[2],
        )

    if http_status == 404 and body_state in {_BodyState.EMPTY, _BodyState.NON_JSON}:
        return DiscoveryError(
            kind=DiscoveryErrorKind.DISCOVERY_UNSUPPORTED,
            message="discovery endpoint is unsupported (bare HTTP 404)",
            http_status=http_status,
        )

    if body_state is _BodyState.EMPTY:
        return _protocol_error(http_status, "JSON-RPC response body is empty")
    if body_state is _BodyState.MALFORMED:
        return _protocol_error(http_status, "response body is not valid JSON")
    if not _is_jsonrpc_success(payload):
        return _protocol_error(http_status, "response is not a valid JSON-RPC result or error")
    if not 200 <= http_status <= 299:
        return _protocol_error(
            http_status,
            "JSON-RPC success was returned with a non-success HTTP status",
        )
    return None


def classify_transport_error(error: BaseException) -> DiscoveryError:
    """Classify an already-caught timeout or connection failure.

    The function does not close, invalidate, or retain a connection.  That
    lifecycle decision remains with the adapter that owns the transport.
    """

    if not isinstance(error, (TimeoutError, ConnectionError)):
        raise TypeError("error must be a TimeoutError or ConnectionError")
    detail = str(error).strip()
    label = type(error).__name__
    return DiscoveryError(
        kind=DiscoveryErrorKind.TRANSPORT_ERROR,
        message=f"{label}: {detail}" if detail else label,
    )


def _decode_body(body: Any) -> tuple[_BodyState, Any]:
    if body is None:
        return _BodyState.EMPTY, None
    if isinstance(body, (bytes, bytearray)):
        try:
            body = bytes(body).decode("utf-8")
        except UnicodeDecodeError:
            return _BodyState.MALFORMED, None
    if isinstance(body, str):
        if not body.strip():
            return _BodyState.EMPTY, None
        try:
            return _BodyState.JSON, json.loads(body)
        except (json.JSONDecodeError, RecursionError):
            if body.lstrip().startswith(("{", "[")):
                return _BodyState.MALFORMED, None
            return _BodyState.NON_JSON, None
    if isinstance(body, (Mapping, list, tuple, int, float, bool)):
        return _BodyState.JSON, body
    return _BodyState.MALFORMED, None


def _parse_jsonrpc_error(payload: Any) -> tuple[int, str, Any] | None:
    if not isinstance(payload, Mapping):
        return None
    if payload.get("jsonrpc") != "2.0" or "id" not in payload:
        return None
    if "error" not in payload or "result" in payload:
        return None
    error = payload["error"]
    if not isinstance(error, Mapping):
        return None
    code = error.get("code")
    message = error.get("message")
    if isinstance(code, bool) or not isinstance(code, int) or not isinstance(message, str):
        return None
    return code, message, payload["id"]


def _is_jsonrpc_success(payload: Any) -> bool:
    return (
        isinstance(payload, Mapping)
        and payload.get("jsonrpc") == "2.0"
        and "id" in payload
        and "result" in payload
        and "error" not in payload
    )


def _protocol_error(http_status: int | None, message: str) -> DiscoveryError:
    return DiscoveryError(
        kind=DiscoveryErrorKind.PROTOCOL_ERROR,
        message=message,
        http_status=http_status,
    )

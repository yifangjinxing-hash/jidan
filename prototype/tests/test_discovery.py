from __future__ import annotations

from pathlib import Path
import json
import sys
import unittest


PROTOTYPE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROTOTYPE_ROOT))

from jidan.discovery import (  # noqa: E402
    DiscoveryErrorKind,
    classify_discovery_response,
    classify_transport_error,
)


def rpc_error(code=-32601, message="Method not found", request_id=1):
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }
    )


class DiscoveryClassificationTests(unittest.TestCase):
    def test_401_and_403_are_auth_required(self):
        for status in (401, 403):
            with self.subTest(status=status):
                result = classify_discovery_response(status, rpc_error())

                self.assertEqual(DiscoveryErrorKind.AUTH_REQUIRED, result.kind)
                self.assertEqual(status, result.http_status)
                self.assertFalse(result.is_transport_failure)

    def test_bare_404_is_discovery_unsupported(self):
        for body in (None, "", "Not Found", b"<html>missing</html>"):
            with self.subTest(body=body):
                result = classify_discovery_response(404, body)

                self.assertEqual(
                    DiscoveryErrorKind.DISCOVERY_UNSUPPORTED,
                    result.kind,
                )

    def test_truncated_json_404_is_a_protocol_error_not_a_downgrade(self):
        result = classify_discovery_response(404, '{"jsonrpc":"2.0"')

        self.assertEqual(DiscoveryErrorKind.PROTOCOL_ERROR, result.kind)

    def test_decodable_jsonrpc_error_is_call_scoped_even_on_http_error(self):
        for status in (400, 404):
            with self.subTest(status=status):
                result = classify_discovery_response(
                    status,
                    rpc_error(-32601, "server/discover is unknown", "probe-1"),
                )

                self.assertEqual(DiscoveryErrorKind.CALL_ERROR, result.kind)
                self.assertEqual(-32601, result.rpc_code)
                self.assertEqual("probe-1", result.rpc_id)
                self.assertTrue(result.is_call_scoped)
                self.assertFalse(result.is_transport_failure)

    def test_malformed_responses_are_protocol_errors(self):
        cases = (
            (200, "not-json"),
            (200, {"result": {}}),
            (200, {"jsonrpc": "2.0", "id": 1, "result": {}, "error": {}}),
            (400, {"jsonrpc": "2.0", "id": 1, "error": {"code": "bad"}}),
            (500, None),
        )
        for status, body in cases:
            with self.subTest(status=status, body=body):
                result = classify_discovery_response(status, body)

                self.assertEqual(DiscoveryErrorKind.PROTOCOL_ERROR, result.kind)

    def test_timeout_and_disconnect_are_transport_errors(self):
        for error in (TimeoutError("deadline exceeded"), ConnectionResetError("reset")):
            with self.subTest(error=error):
                result = classify_transport_error(error)

                self.assertEqual(DiscoveryErrorKind.TRANSPORT_ERROR, result.kind)
                self.assertTrue(result.is_transport_failure)
                self.assertFalse(result.is_call_scoped)

    def test_transport_classifier_rejects_programming_errors(self):
        with self.assertRaises(TypeError):
            classify_transport_error(ValueError("not a network failure"))

    def test_call_error_does_not_poison_a_later_success(self):
        first = classify_discovery_response(400, rpc_error(-32602, "bad arguments"))
        second = classify_discovery_response(
            200,
            {"jsonrpc": "2.0", "id": 2, "result": {"tools": []}},
        )

        self.assertEqual(DiscoveryErrorKind.CALL_ERROR, first.kind)
        self.assertTrue(first.is_call_scoped)
        self.assertIsNone(second)


if __name__ == "__main__":
    unittest.main()

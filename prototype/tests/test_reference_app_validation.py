from __future__ import annotations

from pathlib import Path
import hashlib
import json
import sys
import unittest


PROTOTYPE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROTOTYPE_ROOT))

from reference_app_validation import (  # noqa: E402
    CERTIFICATE_PATTERN,
    RETURN_KEY,
    _append_event,
    _content_for_round,
    _extract_state,
    _verify_event_chain,
)


class ReferenceAppValidationTests(unittest.TestCase):
    def test_event_chain_detects_negative_event_tampering(self) -> None:
        events = []
        _append_event(events, "preflight_zero_execution", {"round": 1, "invocations": 0})
        _append_event(events, "kernel_grant_replay_rejected", {"round": 1, "invocations": 1})

        self.assertTrue(_verify_event_chain(events))
        events[0]["details"]["invocations"] = 99
        self.assertFalse(_verify_event_chain(events))

    def test_certificate_pattern_accepts_build_tools_37_v2_prefix(self) -> None:
        output = (
            "Number of signers: 1\n"
            "V2 Signer: certificate SHA-256 digest: "
            "1c02f509017fe3c37124722d1579dbb0c009556b86120f38fddac724b6332f09\n"
        )

        match = CERTIFICATE_PATTERN.search(output)

        self.assertIsNotNone(match)
        self.assertEqual(
            "1c02f509017fe3c37124722d1579dbb0c009556b86120f38fddac724b6332f09",
            match.group(1),
        )

    def test_platform_string_return_is_unwrapped_and_decoded(self):
        state = {"status": "applied", "revision": 1}
        output = {RETURN_KEY: [json.dumps(state)]}

        self.assertEqual(state, _extract_state(output))

    def test_round_content_is_deterministic_and_exercises_shell_characters(self):
        content = _content_for_round("suite-1", 3)

        self.assertEqual(content, _content_for_round("suite-1", 3))
        self.assertIn("中文", content)
        self.assertIn("$() ; & | < >", content)
        self.assertIn("\n", content)
        self.assertEqual(
            hashlib.sha256(content.encode()).hexdigest(),
            hashlib.sha256(_content_for_round("suite-1", 3).encode()).hexdigest(),
        )

    def test_round_17_contains_large_but_contract_safe_payload(self):
        content = _content_for_round("suite-1", 17)

        self.assertGreater(len(content), 3500)
        self.assertLessEqual(len(content), 4096)


if __name__ == "__main__":
    unittest.main()

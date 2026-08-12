from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path


PROTOTYPE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROTOTYPE_ROOT))

from tests.test_ui_action_profiles import SchemaValidationError, _validate


REPOSITORY_ROOT = PROTOTYPE_ROOT.parent
PROFILES = REPOSITORY_ROOT / "profiles"
TOOL_PATH = PROFILES / "daily.note.create.tool.json"
PLAN_PATH = PROFILES / "schemas" / "jcl.owned-action-plan-v0.1.schema.json"
PROVIDER_PATH = (
    PROFILES
    / "providers"
    / "android.hand.jidan.accessibility.daily.v0.1.json"
)
BUILTIN = "android.hand.jidan.accessibility.daily.v0.1"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class DailyNoteProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tool = load(TOOL_PATH)
        cls.plan = load(PLAN_PATH)
        cls.provider = load(PROVIDER_PATH)

    def test_tool_accepts_a_short_note_and_pins_the_builtin_hand(self) -> None:
        _validate({"text": "明天买鸡蛋"}, self.tool["inputSchema"], TOOL_PATH)
        self.assertNotIn("handPreference", self.tool["inputSchema"]["properties"])
        self.assertEqual(
            self.tool["outputSchema"]["properties"]["handProviderId"]["const"],
            BUILTIN,
        )
        meta = self.tool["_meta"]["dev.jidan/capability-v0.1"]
        self.assertEqual(meta["executionMode"], "OWNED_APP")
        self.assertTrue(meta["realWorldEffects"])
        self.assertFalse(meta["externalMcpEndpointAvailable"])

    def test_saved_output_requires_the_owned_hand_and_a_receipt(self) -> None:
        saved = {
            "state": "saved_local",
            "requestId": "123e4567-e89b-12d3-a456-426614174000",
            "noteDigestSha256": "a" * 64,
            "handProviderId": BUILTIN,
            "noteSaved": True,
            "automationAttempted": True,
            "receiptHash": "b" * 64,
        }
        _validate(saved, self.tool["outputSchema"], TOOL_PATH)
        forged = copy.deepcopy(saved)
        forged["handProviderId"] = "android.hand.candidate.cyjh.mobileanjian.v0.1"
        with self.assertRaises(SchemaValidationError):
            _validate(forged, self.tool["outputSchema"], TOOL_PATH)

    def test_caller_cannot_select_an_unwired_candidate_hand(self) -> None:
        with self.assertRaises(SchemaValidationError):
            _validate(
                {
                    "text": "明天买鸡蛋",
                    "handPreference": "MOBILEANJIAN_CANDIDATE",
                },
                self.tool["inputSchema"],
                TOOL_PATH,
            )

    def test_owned_plan_has_exactly_two_semantic_actions_and_no_raw_text(self) -> None:
        self.assertEqual(self.plan["properties"]["lane"]["const"], "OWNED_APP")
        self.assertEqual(
            self.plan["properties"]["handProviderId"]["const"], BUILTIN
        )
        actions = self.plan["properties"]["actions"]
        self.assertEqual(actions["minItems"], 2)
        self.assertEqual(actions["maxItems"], 2)
        serialized = json.dumps(self.plan, ensure_ascii=False)
        for forbidden in ('"x"', '"y"', '"coordinates"', '"rawText"'):
            self.assertNotIn(forbidden, serialized)
        self.assertIn("ephemeralValueRef", serialized)

    def test_provider_pins_the_owned_plan_schema_and_local_effect_scope(self) -> None:
        actual = hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest()
        self.assertEqual(self.provider["hostAdapter"]["profileSha256"], actual)
        self.assertEqual(self.provider["supportedLanes"], ["OWNED_APP"])
        self.assertEqual(self.provider["realWorldEffectCeiling"], "OWNED_LOCAL_APP")
        self.assertEqual(
            self.provider["identityBinding"]["contractId"],
            "jidan.daily.demo.v0.1.note-form.1",
        )


if __name__ == "__main__":
    unittest.main()

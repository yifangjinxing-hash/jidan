from __future__ import annotations

from pathlib import Path
import hashlib
import json
import sys
import unittest


PROTOTYPE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROTOTYPE_ROOT.parent
sys.path.insert(0, str(PROTOTYPE_ROOT))

from jidan.message_compose import (  # noqa: E402
    HANDOFF_OPENED,
    HANDOFF_PLANNED,
    JCL_META_KEY,
    MESSAGE_COMPOSE_CAPABILITY_ID,
    MessageComposeBinding,
    MessageComposeBindingError,
    message_compose_mcp_tool,
    planned_message_compose_binding,
    wechat_message_compose_binding,
)
from jidan.models import Effect, Step, TaskPlan  # noqa: E402
from jidan.policy import PolicyEngine, issue_grant  # noqa: E402
from jidan.registry import CapabilityInputError, CapabilityRegistry  # noqa: E402
from jidan.runtime import JidanRuntime  # noqa: E402


class FakeWeChatAdapter:
    def __init__(self, *, unsafe: bool = False) -> None:
        self.unsafe = unsafe
        self.arguments = None

    @staticmethod
    def capability():
        from jidan.android_share import AdbWeChatShareAdapter

        return AdbWeChatShareAdapter.capability()

    def open_handoff(self, arguments):
        self.arguments = dict(arguments)
        content_hash = hashlib.sha256(arguments["text"].encode("utf-8")).hexdigest()
        return {
            "status": HANDOFF_OPENED,
            "package": "com.tencent.mm",
            "handler": "com.tencent.mm/.ui.tools.ShareImgUI",
            "pickerActivity": "com.tencent.mm/.ui.transmit.SelectConversationUI",
            "textSha256": content_hash,
            "jidanSelectedRecipient": False,
            "jidanIssuedSend": self.unsafe,
            "deliveryState": "not_attempted_by_jidan",
            "nextAction": "user_select_recipient_and_confirm_send",
        }


class MessageComposeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = {
            "recipient": "VIP客户群",
            "content": "老板通知：今日特惠三文鱼套餐仅需 12 美金，欢迎预约！",
        }

    def test_one_capability_contract_drives_all_planned_platforms(self) -> None:
        for platform in ("android", "ios", "web"):
            with self.subTest(platform=platform):
                registry = CapabilityRegistry()
                capability = planned_message_compose_binding(platform).register(registry)
                output = registry.invoke(MESSAGE_COMPOSE_CAPABILITY_ID, self.payload)

                self.assertEqual(MESSAGE_COMPOSE_CAPABILITY_ID, capability.id)
                self.assertEqual(Effect.WRITE, capability.effect)
                self.assertTrue(capability.requires_confirmation)
                self.assertFalse(capability.reversible)
                self.assertEqual(HANDOFF_PLANNED, output["state"])
                self.assertEqual(platform, output["adapter"]["platform"])
                self.assertEqual(
                    hashlib.sha256(self.payload["content"].encode("utf-8")).hexdigest(),
                    output["artifact"]["textSha256"],
                )
                self.assertEqual("VIP客户群", output["artifact"]["recipientHint"])
                self.assertEqual(
                    {"attempted": False, "sent": False, "verified": False},
                    output["delivery"],
                )

    def test_upper_layer_never_passes_platform_to_invoke(self) -> None:
        registry = CapabilityRegistry()
        planned_message_compose_binding("ios").register(registry)

        output = registry.invoke(MESSAGE_COMPOSE_CAPABILITY_ID, {"content": "hello"})

        self.assertEqual("ios", output["adapter"]["platform"])

    def test_normal_runtime_stops_for_confirmation_before_handoff(self) -> None:
        registry = CapabilityRegistry()
        capability = planned_message_compose_binding("web").register(registry)
        plan = TaskPlan(
            id="compose-task",
            goal="prepare a message draft",
            steps=(
                Step(
                    id="compose",
                    capability=MESSAGE_COMPOSE_CAPABILITY_ID,
                    arguments={"content": "hello"},
                ),
            ),
        )
        secret = b"message-compose-test-secret"
        policy = PolicyEngine(secret)
        runtime = JidanRuntime(registry, policy)
        unapproved = issue_grant(
            secret,
            plan,
            capabilities={capability.id},
            scopes=capability.scopes,
            max_effect=Effect.WRITE,
        )

        stopped = runtime.execute(plan, unapproved)

        self.assertEqual("awaiting_confirmation", stopped.status)
        self.assertEqual("needs_confirmation", stopped.decisions[0].outcome)

        approved = issue_grant(
            secret,
            plan,
            capabilities={capability.id},
            scopes=capability.scopes,
            max_effect=Effect.WRITE,
            approved_steps={"compose"},
        )
        completed = runtime.execute(plan, approved)
        self.assertEqual("completed", completed.status)
        self.assertFalse(completed.outputs["compose"]["delivery"]["sent"])

    def test_recipient_hint_is_never_visible_to_the_binding(self) -> None:
        received = {}

        def harmony_plan(arguments):
            received.update(arguments)
            return {"type": "harmony.want", "text": arguments["content"]}

        registry = CapabilityRegistry()
        MessageComposeBinding(
            platform="harmonyos",
            adapter_id="harmony.want.share-text-plan",
            surface="harmony_share_sheet",
            handler=harmony_plan,
        ).register(registry)

        output = registry.invoke(MESSAGE_COMPOSE_CAPABILITY_ID, self.payload)

        self.assertEqual({"content": self.payload["content"]}, received)
        self.assertNotIn("VIP客户群", str(output["adapter"]["binding"]))

    def test_invalid_content_is_rejected_before_binding(self) -> None:
        called = False

        def handler(_):
            nonlocal called
            called = True
            return {}

        registry = CapabilityRegistry()
        MessageComposeBinding(
            platform="test",
            adapter_id="test.plan",
            surface="test_surface",
            handler=handler,
        ).register(registry)

        for payload in ({}, {"content": ""}, {"content": 7}, {"content": "ok", "x": 1}):
            with self.subTest(payload=payload):
                with self.assertRaises(CapabilityInputError):
                    registry.invoke(MESSAGE_COMPOSE_CAPABILITY_ID, payload)
        self.assertFalse(called)

    def test_binding_cannot_author_delivery_or_success_fields(self) -> None:
        unsafe_bindings = (
            {"sent": True},
            {"evidence": {"sent": True}},
            {"events": [{"status": "success"}]},
        )
        for unsafe_binding in unsafe_bindings:
            with self.subTest(unsafe_binding=unsafe_binding):
                registry = CapabilityRegistry()
                MessageComposeBinding(
                    platform="unsafe",
                    adapter_id="unsafe.plan",
                    surface="unsafe_surface",
                    handler=lambda _, value=unsafe_binding: value,
                ).register(registry)

                with self.assertRaises(MessageComposeBindingError):
                    registry.invoke(MESSAGE_COMPOSE_CAPABILITY_ID, {"content": "hello"})

    def test_generic_binding_cannot_select_opened_state(self) -> None:
        with self.assertRaises(TypeError):
            MessageComposeBinding(
                platform="unsafe",
                adapter_id="unsafe.plan",
                surface="unsafe_surface",
                handler=lambda _: {},
                handoff_state=HANDOFF_OPENED,
            )

        registry = CapabilityRegistry()
        MessageComposeBinding(
            platform="community",
            adapter_id="community.plan",
            surface="community_surface",
            handler=lambda _: {},
        ).register(registry)
        output = registry.invoke(MESSAGE_COMPOSE_CAPABILITY_ID, {"content": "hello"})
        self.assertEqual(HANDOFF_PLANNED, output["state"])

    def test_wechat_binding_maps_only_a_verified_open_handoff(self) -> None:
        adapter = FakeWeChatAdapter()
        registry = CapabilityRegistry()
        capability = wechat_message_compose_binding(adapter).register(registry)

        output = registry.invoke(MESSAGE_COMPOSE_CAPABILITY_ID, self.payload)

        self.assertEqual(HANDOFF_OPENED, output["state"])
        self.assertEqual({"text": self.payload["content"]}, adapter.arguments)
        self.assertEqual("com.tencent.mm", capability.app)
        self.assertFalse(capability.reversible)
        self.assertFalse(output["delivery"]["sent"])
        self.assertNotIn("raw_stdout", output["adapter"]["binding"])

    def test_wechat_false_success_is_rejected(self) -> None:
        registry = CapabilityRegistry()
        wechat_message_compose_binding(FakeWeChatAdapter(unsafe=True)).register(registry)

        with self.assertRaises(MessageComposeBindingError):
            registry.invoke(MESSAGE_COMPOSE_CAPABILITY_ID, {"content": "hello"})

    def test_checked_in_mcp_profile_matches_runtime_export(self) -> None:
        checked_in = json.loads(
            (REPOSITORY_ROOT / "profiles" / "message.compose.tool.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(checked_in, message_compose_mcp_tool())
        self.assertEqual(
            "HANDOFF",
            checked_in["_meta"][JCL_META_KEY]["executionMode"],
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import argparse
from dataclasses import asdict
import json

from jidan.message_compose import (
    MESSAGE_COMPOSE_CAPABILITY_ID,
    planned_message_compose_binding,
)
from jidan.models import Effect, Step, TaskPlan
from jidan.policy import PolicyEngine, issue_grant
from jidan.registry import CapabilityRegistry
from jidan.runtime import JidanRuntime


parser = argparse.ArgumentParser(
    description="Show the message.compose confirmation gate for each planned binding."
)
parser.add_argument(
    "--simulate-approval",
    action="store_true",
    help=(
        "issue a demo-only approved Grant and execute the data plan; this is not "
        "evidence of a real user's confirmation"
    ),
)
args = parser.parse_args()

payload = {
    "recipient": "VIP客户群",
    "content": "老板通知：今日特惠三文鱼套餐仅需 12 美金，欢迎预约！",
}

outputs = []
for platform in ("android", "ios", "web"):
    registry = CapabilityRegistry()
    capability = planned_message_compose_binding(platform).register(registry)
    plan = TaskPlan(
        id=f"message-compose-{platform}",
        goal=f"prepare a reviewable message draft through {platform}",
        steps=(
            Step(
                id="compose",
                capability=MESSAGE_COMPOSE_CAPABILITY_ID,
                arguments=payload,
            ),
        ),
    )
    secret = f"local-message-compose-demo-{platform}".encode("ascii")
    runtime = JidanRuntime(registry, PolicyEngine(secret))

    unapproved = issue_grant(
        secret,
        plan,
        capabilities={capability.id},
        scopes=capability.scopes,
        max_effect=Effect.WRITE,
        capability_digests=registry.definition_digests({capability.id}),
    )
    stopped = runtime.execute(plan, unapproved)

    simulated_result = None
    if args.simulate_approval:
        approved = issue_grant(
            secret,
            plan,
            capabilities={capability.id},
            scopes=capability.scopes,
            max_effect=Effect.WRITE,
            approved_steps={"compose"},
            capability_digests=registry.definition_digests({capability.id}),
        )
        simulated_result = asdict(runtime.execute(plan, approved))

    outputs.append(
        {
            "platform": platform,
            "withoutApproval": asdict(stopped),
            "afterSimulatedApproval": simulated_result,
            "approvalNotice": (
                "demo_only_not_user_confirmation"
                if args.simulate_approval
                else "not_approved_use_--simulate-approval_to_demo_remaining_stages"
            ),
        }
    )

print(json.dumps(outputs, ensure_ascii=False, indent=2))

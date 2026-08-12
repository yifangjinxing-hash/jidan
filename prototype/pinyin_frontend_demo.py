from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from jidan.message_compose import planned_message_compose_binding
from jidan.models import Effect, Step, TaskPlan
from jidan.pinyin_frontend import PinyinCompiler
from jidan.policy import PolicyEngine, issue_grant
from jidan.registry import CapabilityRegistry
from jidan.runtime import JidanRuntime


parser = argparse.ArgumentParser(
    description="Compile a Pinyin alias, then stop at the normal confirmation gate."
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

repository_root = Path(__file__).resolve().parent.parent
profile_path = (
    repository_root
    / "profiles"
    / "frontends"
    / "zh-Latn-pinyin.frontend.json"
)
profile = json.loads(profile_path.read_text(encoding="utf-8"))
compiler = PinyinCompiler.from_profile(profile)

proposal = compiler.compile(
    "chuàng-jiàn.cǎo-gǎo",
    {"content": "下午三点见。"},
)

registry = CapabilityRegistry()
capability = planned_message_compose_binding("web").register(registry)
plan = TaskPlan(
    id="pinyin-compose-demo",
    goal="compile a Pinyin control alias into a reviewed message draft",
    steps=(
        Step(
            id="compose",
            capability=proposal.capability,
            arguments=proposal.arguments,
        ),
    ),
)

secret = b"local-pinyin-frontend-demo-key"
policy = PolicyEngine(secret)
runtime = JidanRuntime(registry, policy)
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

print(
    json.dumps(
        {
            "compiled": proposal.to_dict(),
            "unapprovedRun": asdict(stopped),
            "afterSimulatedApproval": simulated_result,
            "approvalNotice": (
                "demo_only_not_user_confirmation"
                if args.simulate_approval
                else "not_approved_use_--simulate-approval_to_demo_remaining_stages"
            ),
        },
        ensure_ascii=False,
        indent=2,
    )
)

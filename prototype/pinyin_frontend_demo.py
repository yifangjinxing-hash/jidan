from __future__ import annotations

from pathlib import Path
from dataclasses import asdict
import json

from jidan.message_compose import planned_message_compose_binding
from jidan.models import Effect, Step, TaskPlan
from jidan.pinyin_frontend import PinyinCompiler
from jidan.policy import PolicyEngine, issue_grant
from jidan.registry import CapabilityRegistry
from jidan.runtime import JidanRuntime


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
    goal="compile Pinyin control source into a reviewed message draft",
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
)
stopped = runtime.execute(plan, unapproved)

approved = issue_grant(
    secret,
    plan,
    capabilities={capability.id},
    scopes=capability.scopes,
    max_effect=Effect.WRITE,
    approved_steps={"compose"},
)
completed = runtime.execute(plan, approved)

print(
    json.dumps(
        {
            "compiled": proposal.to_dict(),
            "unapprovedRun": asdict(stopped),
            "approvedRun": asdict(completed),
        },
        ensure_ascii=False,
        indent=2,
    )
)

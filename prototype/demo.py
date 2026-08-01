from __future__ import annotations

from pathlib import Path
import argparse
import json

from jidan import (
    CapabilityRegistry,
    Effect,
    JidanRuntime,
    PolicyEngine,
    ReceiptLog,
    TaskPlan,
    issue_grant,
)
from jidan.console import configure_utf8_stdio


ROOT = Path(__file__).resolve().parent


def build_demo_runtime(receipt_path: Path | None = None):
    registry = CapabilityRegistry()
    registry.load_directory(ROOT / "manifests")

    shopping_list: list[str] = []
    messages = [
        {
            "sender": "Lisa",
            "subject": "Noodle recipe",
            "body": "For dinner: noodles, bok choy, sesame oil, soy sauce.",
        }
    ]

    def search_mail(arguments):
        query = str(arguments["query"]).lower()
        match = next(
            item
            for item in messages
            if all(token in (item["sender"] + " " + item["subject"]).lower() for token in query.split())
        )
        return {"body": match["body"], "sender": match["sender"]}

    def extract_recipe(arguments):
        text = str(arguments["text"])
        _, ingredients = text.split(":", 1)
        return {"items": [item.strip().rstrip(".") for item in ingredients.split(",")]}

    def add_items(arguments):
        shopping_list.extend(str(item) for item in arguments["items"])
        return {"list": list(shopping_list), "added": len(arguments["items"])}

    registry.bind("mail.search", search_mail)
    registry.bind("system.extract_recipe", extract_recipe)
    registry.bind("shopping.add_items", add_items)

    secret = b"jidan-demo-secret-replace-with-hardware-backed-key"
    runtime = JidanRuntime(registry, PolicyEngine(secret), ReceiptLog(receipt_path))
    return runtime, secret, shopping_list


def build_plan() -> TaskPlan:
    return TaskPlan.from_dict(
        {
            "id": "dinner.shopping.001",
            "goal": "找到 Lisa 邮件里的面条食谱，把食材加入购物清单",
            "steps": [
                {
                    "id": "find_recipe",
                    "capability": "mail.search",
                    "arguments": {"query": "Lisa noodle"},
                },
                {
                    "id": "extract_ingredients",
                    "capability": "system.extract_recipe",
                    "arguments": {"text": {"$ref": "find_recipe.body"}},
                },
                {
                    "id": "add_to_list",
                    "capability": "shopping.add_items",
                    "arguments": {"items": {"$ref": "extract_ingredients.items"}},
                },
            ],
        }
    )


def summarize(result) -> dict:
    return {
        "status": result.status,
        "decisions": [
            {
                "step": item.step_id,
                "capability": item.capability,
                "outcome": item.outcome,
                "reason": item.reason,
            }
            for item in result.decisions
        ],
        "outputs": result.outputs,
        "receipt_hashes": [item["hash"] for item in result.receipts],
    }


def main() -> None:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Run the Jidan capability-kernel demo")
    parser.add_argument(
        "--approve",
        action="store_true",
        help="approve the shopping-list write after showing the preflight gate",
    )
    parser.add_argument("--receipts", type=Path, help="optional JSONL receipt path")
    args = parser.parse_args()

    runtime, secret, shopping_list = build_demo_runtime(args.receipts)
    plan = build_plan()
    grant = issue_grant(
        secret=secret,
        task_id=plan,
        capabilities=(step.capability for step in plan.steps),
        scopes={"mail.content.read", "local.inference", "shopping.list.write"},
        max_effect=Effect.WRITE,
    )

    gated = runtime.execute(plan, grant)
    print("PRE-FLIGHT")
    print(json.dumps(summarize(gated), ensure_ascii=False, indent=2))
    print(f"SIDE EFFECTS: shopping_list={shopping_list}")

    if args.approve:
        approved_grant = issue_grant(
            secret=secret,
            task_id=plan,
            capabilities=(step.capability for step in plan.steps),
            scopes={"mail.content.read", "local.inference", "shopping.list.write"},
            max_effect=Effect.WRITE,
            approved_steps={"add_to_list"},
        )
        completed = runtime.execute(plan, approved_grant)
        print("\nAFTER EXPLICIT APPROVAL")
        print(json.dumps(summarize(completed), ensure_ascii=False, indent=2))
        print(f"SIDE EFFECTS: shopping_list={shopping_list}")
        print(f"RECEIPT CHAIN VALID: {runtime.receipts.verify()}")


if __name__ == "__main__":
    main()

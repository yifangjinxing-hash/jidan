from __future__ import annotations

import argparse
import json
from typing import Any, Mapping

from jidan.models import Effect, Step, TaskPlan
from jidan.ninelights import (
    NINELIGHTS_PRESS_CAPABILITY_ID,
    NINELIGHTS_START_CAPABILITY_ID,
    register_ninelights,
)
from jidan.policy import PolicyEngine, issue_grant
from jidan.registry import CapabilityRegistry
from jidan.runtime import JidanRuntime


class NineLightsHost:
    """Small CLI Host that routes every game action through the real Runtime."""

    def __init__(self, secret: bytes = b"local-ninelights-demo-secret") -> None:
        self.secret = secret
        self.registry = CapabilityRegistry()
        register_ninelights(self.registry)
        self.runtime = JidanRuntime(self.registry, PolicyEngine(secret))
        self._sequence = 0

    def start(self, level_id: str) -> Mapping[str, Any]:
        return self._run(NINELIGHTS_START_CAPABILITY_ID, {"levelId": level_id})

    def press(self, state: Mapping[str, Any], cell: int) -> Mapping[str, Any]:
        output = self._run(
            NINELIGHTS_PRESS_CAPABILITY_ID,
            {"state": state, "cell": cell},
        )
        return output["state"]

    def summary(self, state: Mapping[str, Any]) -> dict[str, Any]:
        receipts = self.runtime.receipts.all()
        return {
            "capabilities": [
                NINELIGHTS_START_CAPABILITY_ID,
                NINELIGHTS_PRESS_CAPABILITY_ID,
            ],
            "state": dict(state),
            "receiptCount": len(receipts),
            "lastReceiptHash": receipts[-1]["hash"] if receipts else None,
            "receiptChainVerified": self.runtime.receipts.verify(),
        }

    def _run(self, capability_id: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        self._sequence += 1
        step_id = "start" if capability_id == NINELIGHTS_START_CAPABILITY_ID else "press"
        plan = TaskPlan(
            id=f"ninelights-{self._sequence:04d}",
            goal="play one deterministic Nine Lights action",
            steps=(
                Step(
                    id=step_id,
                    capability=capability_id,
                    arguments=arguments,
                ),
            ),
        )
        grant = issue_grant(
            self.secret,
            plan,
            capabilities={capability_id},
            scopes=(),
            max_effect=Effect.READ,
            capability_digests=self.registry.definition_digests({capability_id}),
        )
        result = self.runtime.execute(plan, grant)
        if result.status != "completed":
            details = result.outputs.get(step_id, {})
            raise ValueError(details.get("error", f"game action {result.status}"))
        return result.outputs[step_id]


def play_script(level_id: str, moves: tuple[int, ...]) -> dict[str, Any]:
    host = NineLightsHost()
    state = host.start(level_id)
    for cell in moves:
        state = host.press(state, cell)
    return host.summary(state)


def _render(state: Mapping[str, Any]) -> str:
    symbols = ["●" if value else "·" for value in state["cells"]]
    rows = ["  ".join(symbols[index : index + 3]) for index in range(0, 9, 3)]
    status = "完成 / WON" if state["status"] == "won" else "进行中 / PLAYING"
    return (
        f"\n九灯 · {state['levelId']} · {state['moveCount']} 步 · {status}\n\n"
        + "\n".join(rows)
        + "\n"
    )


def _parse_moves(raw: str) -> tuple[int, ...]:
    if not raw.strip():
        return ()
    moves: list[int] = []
    for token in raw.replace(",", " ").split():
        value = int(token)
        if not 1 <= value <= 9:
            raise argparse.ArgumentTypeError("moves must use board numbers 1 through 9")
        moves.append(value - 1)
    return tuple(moves)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Play Nine Lights through JCL TaskPlan, Grant, Runtime, and Receipt."
    )
    parser.add_argument("--level", choices=("cross", "corners", "full"), default="cross")
    parser.add_argument(
        "--moves",
        type=_parse_moves,
        help="scripted 1-based cells, for example: --moves 1,9",
    )
    parser.add_argument("--json", action="store_true", help="print the final state as JSON")
    args = parser.parse_args()

    if args.moves is not None:
        summary = play_script(args.level, args.moves)
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print(_render(summary["state"]))
            print(f"Receipt chain: {summary['receiptCount']} · {summary['lastReceiptHash'][:12]}")
        return

    host = NineLightsHost()
    level_id = args.level
    state = host.start(level_id)
    while True:
        print(_render(state))
        print("1–9 翻灯 · L 选关 · R 重开 · Q 退出")
        command = input("> ").strip().lower()
        if command == "q":
            break
        if command == "r":
            state = host.start(level_id)
            continue
        if command == "l":
            selected = input("cross / corners / full > ").strip().lower()
            if selected not in {"cross", "corners", "full"}:
                print("未知关卡，保持当前关卡。")
                continue
            level_id = selected
            state = host.start(level_id)
            continue
        if command not in {str(value) for value in range(1, 10)}:
            print("请输入 1–9、L、R 或 Q。")
            continue
        try:
            state = host.press(state, int(command) - 1)
        except ValueError as exc:
            print(f"动作被拒绝：{exc}")
            continue
        if state["status"] == "won":
            print(_render(state))
            summary = host.summary(state)
            print(f"Receipt chain: {summary['receiptCount']} · {summary['lastReceiptHash'][:12]}")
            break


if __name__ == "__main__":
    main()

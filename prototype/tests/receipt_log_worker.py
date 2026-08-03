from __future__ import annotations

from pathlib import Path
import sys
import time


PROTOTYPE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROTOTYPE_ROOT))

from jidan.audit import ReceiptLog  # noqa: E402


def main() -> int:
    receipt_path = Path(sys.argv[1])
    ready_path = Path(sys.argv[2])
    start_path = Path(sys.argv[3])
    worker_id = sys.argv[4]
    log = ReceiptLog(receipt_path)
    ready_path.touch()
    deadline = time.monotonic() + 15.0
    while not start_path.exists():
        if time.monotonic() >= deadline:
            return 2
        time.sleep(0.01)
    log.append(
        task_id=f"concurrent-{worker_id}",
        step_id="append",
        capability="test.concurrent_receipt",
        capability_digest="ab" * 32,
        effect="read",
        status="succeeded",
        arguments={},
        output={"worker": worker_id},
    )
    return 0 if log.verify() else 3


if __name__ == "__main__":
    raise SystemExit(main())

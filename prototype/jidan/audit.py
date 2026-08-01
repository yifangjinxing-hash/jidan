from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
from copy import deepcopy
import hashlib
import json
import time


def _canonical(raw: Mapping[str, Any]) -> str:
    return json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class ReceiptLog:
    """Append-only, hash-chained execution receipts."""

    GENESIS = "0" * 64

    def __init__(self, path: str | Path | None = None, clock: Any = time.time) -> None:
        self.path = Path(path) if path is not None else None
        self._clock = clock
        self._receipts: list[dict[str, Any]] = []
        if self.path is not None and self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self._receipts.append(json.loads(line))

    def append(
        self,
        task_id: str,
        step_id: str,
        capability: str,
        effect: str,
        status: str,
        arguments: Mapping[str, Any],
        output: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        previous_hash = self._receipts[-1]["hash"] if self._receipts else self.GENESIS
        body = {
            "task_id": task_id,
            "step_id": step_id,
            "capability": capability,
            "effect": effect,
            "status": status,
            "arguments": deepcopy(dict(arguments)),
            "output": deepcopy(dict(output)),
            "timestamp_ms": int(self._clock() * 1000),
            "previous_hash": previous_hash,
        }
        receipt = dict(body)
        receipt["hash"] = hashlib.sha256(_canonical(body).encode()).hexdigest()
        self._receipts.append(deepcopy(receipt))
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(_canonical(receipt) + "\n")
        return deepcopy(receipt)

    def all(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(deepcopy(item) for item in self._receipts)

    def verify(self) -> bool:
        previous_hash = self.GENESIS
        for receipt in self._receipts:
            if receipt.get("previous_hash") != previous_hash:
                return False
            body = {key: value for key, value in receipt.items() if key != "hash"}
            expected = hashlib.sha256(_canonical(body).encode()).hexdigest()
            if not hmac_safe_equal(expected, str(receipt.get("hash", ""))):
                return False
            previous_hash = receipt["hash"]
        return True


def hmac_safe_equal(left: str, right: str) -> bool:
    # Constant-time comparison without coupling receipt hashing to grant signing.
    import hmac

    return hmac.compare_digest(left, right)

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
from copy import deepcopy
from contextlib import contextmanager
import hashlib
import json
import os
import threading
import time


def _canonical(raw: Mapping[str, Any]) -> str:
    return json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


_LOCAL_LOCKS_GUARD = threading.Lock()
_LOCAL_LOCKS: dict[str, threading.RLock] = {}


def _local_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _LOCAL_LOCKS_GUARD:
        return _LOCAL_LOCKS.setdefault(key, threading.RLock())


@contextmanager
def _exclusive_file_lock(path: Path):
    """Serialize a local receipt file across threads and processes."""

    lock_path = Path(str(path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with _local_lock(lock_path):
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
                os.fsync(descriptor)
            with os.fdopen(descriptor, "r+b", closefd=False) as handle:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    handle.seek(0)
                    if os.name == "nt":
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


class ReceiptLog:
    """Append-only, hash-chained execution receipts."""

    GENESIS = "0" * 64

    def __init__(self, path: str | Path | None = None, clock: Any = time.time) -> None:
        self.path = Path(path) if path is not None else None
        self._clock = clock
        self._receipts: list[dict[str, Any]] = []
        if self.path is not None:
            with _exclusive_file_lock(self.path):
                self._receipts = self._read_disk()

    def append(
        self,
        task_id: str,
        step_id: str,
        capability: str,
        capability_digest: str,
        effect: str,
        status: str,
        arguments: Mapping[str, Any],
        output: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if self.path is None:
            receipt = self._build_receipt(
                self._receipts,
                task_id=task_id,
                step_id=step_id,
                capability=capability,
                capability_digest=capability_digest,
                effect=effect,
                status=status,
                arguments=arguments,
                output=output,
            )
            self._receipts.append(deepcopy(receipt))
            return deepcopy(receipt)

        with _exclusive_file_lock(self.path):
            disk_receipts = self._read_disk()
            if not self._verify_records(disk_receipts):
                raise RuntimeError("receipt log failed disk verification before append")
            receipt = self._build_receipt(
                disk_receipts,
                task_id=task_id,
                step_id=step_id,
                capability=capability,
                capability_digest=capability_digest,
                effect=effect,
                status=status,
                arguments=arguments,
                output=output,
            )
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(_canonical(receipt) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            disk_receipts.append(deepcopy(receipt))
            self._receipts = disk_receipts
        return deepcopy(receipt)

    def all(self) -> tuple[Mapping[str, Any], ...]:
        if self.path is not None:
            with _exclusive_file_lock(self.path):
                self._receipts = self._read_disk()
        return tuple(deepcopy(item) for item in self._receipts)

    def verify(self) -> bool:
        if self.path is not None:
            try:
                with _exclusive_file_lock(self.path):
                    records = self._read_disk()
                    valid = self._verify_records(records)
                    if valid:
                        self._receipts = records
                    return valid
            except (OSError, ValueError, json.JSONDecodeError):
                return False
        return self._verify_records(self._receipts)

    def _read_disk(self) -> list[dict[str, Any]]:
        if self.path is None or not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("receipt log line must contain a JSON object")
                records.append(value)
        return records

    def _build_receipt(
        self,
        records: list[dict[str, Any]],
        *,
        task_id: str,
        step_id: str,
        capability: str,
        capability_digest: str,
        effect: str,
        status: str,
        arguments: Mapping[str, Any],
        output: Mapping[str, Any],
    ) -> dict[str, Any]:
        previous_hash = records[-1]["hash"] if records else self.GENESIS
        body = {
            "task_id": task_id,
            "step_id": step_id,
            "capability": capability,
            "capability_digest": capability_digest,
            "effect": effect,
            "status": status,
            "arguments": deepcopy(dict(arguments)),
            "output": deepcopy(dict(output)),
            "timestamp_ms": int(self._clock() * 1000),
            "previous_hash": previous_hash,
        }
        receipt = dict(body)
        receipt["hash"] = hashlib.sha256(_canonical(body).encode()).hexdigest()
        return receipt

    @classmethod
    def _verify_records(cls, records: list[dict[str, Any]]) -> bool:
        previous_hash = cls.GENESIS
        for receipt in records:
            if receipt.get("previous_hash") != previous_hash:
                return False
            body = {key: value for key, value in receipt.items() if key != "hash"}
            expected = hashlib.sha256(_canonical(body).encode()).hexdigest()
            actual_hash = receipt.get("hash")
            if not isinstance(actual_hash, str) or not hmac_safe_equal(
                expected,
                actual_hash,
            ):
                return False
            previous_hash = actual_hash
        return True


def hmac_safe_equal(left: str, right: str) -> bool:
    # Constant-time comparison without coupling receipt hashing to grant signing.
    import hmac

    return hmac.compare_digest(left, right)

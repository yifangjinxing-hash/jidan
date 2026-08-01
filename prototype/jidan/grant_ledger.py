from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
import os
import re
import sqlite3
import threading


_NONCE = re.compile(r"^[0-9a-f]{16,128}$")
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SCHEMA_VERSION = 1


class GrantLedgerError(RuntimeError):
    """A durable grant claim could not be established safely."""


@dataclass(frozen=True)
class GrantConsumption:
    nonce: str
    task_id: str
    plan_hash: str
    signature_sha256: str
    consumed_at_ms: int

    def __post_init__(self) -> None:
        if _NONCE.fullmatch(self.nonce) is None:
            raise ValueError("nonce must be 16..128 lowercase hexadecimal characters")
        if not self.task_id:
            raise ValueError("task_id is required")
        if _HEX_SHA256.fullmatch(self.plan_hash) is None:
            raise ValueError("plan_hash must be a lowercase SHA-256 digest")
        if _HEX_SHA256.fullmatch(self.signature_sha256) is None:
            raise ValueError("signature_sha256 must be a lowercase SHA-256 digest")
        if self.consumed_at_ms < 0:
            raise ValueError("consumed_at_ms must not be negative")


class GrantLedger(Protocol):
    persistent: bool

    def consume(self, record: GrantConsumption) -> bool:
        """Atomically claim a nonce, returning false when it was already claimed."""


class InMemoryGrantLedger:
    """Process-local ledger retained for deterministic demos and unit tests."""

    persistent = False

    def __init__(self) -> None:
        self._nonces: set[str] = set()
        self._lock = threading.Lock()

    def consume(self, record: GrantConsumption) -> bool:
        with self._lock:
            if record.nonce in self._nonces:
                return False
            self._nonces.add(record.nonce)
            return True

    def count(self) -> int:
        with self._lock:
            return len(self._nonces)


class SqliteGrantLedger:
    """Cross-process, crash-durable, at-most-once grant consumption ledger."""

    persistent = True

    def __init__(
        self,
        path: str | Path,
        *,
        timeout_seconds: float = 10.0,
        _create_new: bool = False,
    ) -> None:
        self.path = Path(path).resolve()
        self.timeout_seconds = float(timeout_seconds)
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if _create_new:
            self._reserve_new_file()
        elif not self.path.is_file():
            raise GrantLedgerError(f"existing grant ledger is missing: {self.path}")
        self._initialize(create_new=_create_new)

    @classmethod
    def create_new(
        cls,
        path: str | Path,
        *,
        timeout_seconds: float = 10.0,
    ) -> "SqliteGrantLedger":
        """Provision a brand-new ledger; existing main/sidecar files are rejected."""

        return cls(path, timeout_seconds=timeout_seconds, _create_new=True)

    @classmethod
    def open_existing(
        cls,
        path: str | Path,
        *,
        timeout_seconds: float = 10.0,
    ) -> "SqliteGrantLedger":
        """Open a provisioned ledger without ever creating a missing database."""

        return cls(path, timeout_seconds=timeout_seconds, _create_new=False)

    def _reserve_new_file(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise GrantLedgerError(f"cannot create grant ledger directory: {exc}") from exc
        reserved = {
            self.path,
            *(Path(str(self.path) + suffix) for suffix in ("-wal", "-shm", "-journal")),
        }
        if any(path.exists() for path in reserved):
            raise GrantLedgerError(f"new grant ledger path is already reserved: {self.path}")
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
        except OSError as exc:
            raise GrantLedgerError(f"cannot reserve new grant ledger: {exc}") from exc

    def _connect(self) -> sqlite3.Connection:
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                self.path.as_uri() + "?mode=rw",
                uri=True,
                timeout=self.timeout_seconds,
                isolation_level=None,
            )
            connection.execute(f"PRAGMA busy_timeout={int(self.timeout_seconds * 1000)}")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA synchronous=FULL")
            return connection
        except (OSError, sqlite3.Error) as exc:
            if connection is not None:
                connection.close()
            raise GrantLedgerError(f"cannot open durable grant ledger: {exc}") from exc

    def _initialize(self, *, create_new: bool) -> None:
        connection = self._connect()
        try:
            journal_mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()
            if journal_mode is None or str(journal_mode[0]).lower() != "wal":
                raise GrantLedgerError("grant ledger could not enable WAL journal mode")
            current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if create_new and current_version != 0:
                raise GrantLedgerError(
                    f"new grant ledger was not empty: schema version {current_version}"
                )
            if not create_new and current_version != _SCHEMA_VERSION:
                raise GrantLedgerError(
                    f"unsupported grant ledger schema version: {current_version}"
                )
            if create_new:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    CREATE TABLE grant_consumptions (
                        nonce TEXT PRIMARY KEY NOT NULL,
                        task_id TEXT NOT NULL,
                        plan_hash TEXT NOT NULL,
                        signature_sha256 TEXT NOT NULL,
                        consumed_at_ms INTEGER NOT NULL
                    ) WITHOUT ROWID
                    """
                )
                connection.execute(f"PRAGMA user_version={_SCHEMA_VERSION}")
                connection.execute("COMMIT")
            if not self.verify():
                raise GrantLedgerError("grant ledger integrity check failed")
        except GrantLedgerError:
            self._rollback_quietly(connection)
            raise
        except (OSError, sqlite3.Error) as exc:
            self._rollback_quietly(connection)
            raise GrantLedgerError(f"cannot initialize durable grant ledger: {exc}") from exc
        finally:
            connection.close()

    def consume(self, record: GrantConsumption) -> bool:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT 1 FROM grant_consumptions WHERE nonce = ?",
                (record.nonce,),
            ).fetchone()
            if existing is not None:
                connection.execute("ROLLBACK")
                return False
            connection.execute(
                """
                INSERT INTO grant_consumptions (
                    nonce, task_id, plan_hash, signature_sha256, consumed_at_ms
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    record.nonce,
                    record.task_id,
                    record.plan_hash,
                    record.signature_sha256,
                    record.consumed_at_ms,
                ),
            )
            connection.execute("COMMIT")
            return True
        except (OSError, sqlite3.Error) as exc:
            self._rollback_quietly(connection)
            raise GrantLedgerError(f"cannot atomically consume grant nonce: {exc}") from exc
        finally:
            connection.close()

    def count(self) -> int:
        connection = self._connect()
        try:
            return int(connection.execute("SELECT COUNT(*) FROM grant_consumptions").fetchone()[0])
        except (OSError, sqlite3.Error) as exc:
            raise GrantLedgerError(f"cannot read grant ledger: {exc}") from exc
        finally:
            connection.close()

    def verify(self) -> bool:
        connection = self._connect()
        try:
            result = connection.execute("PRAGMA quick_check").fetchone()
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            columns = connection.execute("PRAGMA table_info(grant_consumptions)").fetchall()
            expected_columns = [
                ("nonce", "TEXT", 1, 1),
                ("task_id", "TEXT", 1, 0),
                ("plan_hash", "TEXT", 1, 0),
                ("signature_sha256", "TEXT", 1, 0),
                ("consumed_at_ms", "INTEGER", 1, 0),
            ]
            actual_columns = [
                (str(row[1]), str(row[2]).upper(), int(row[3]), int(row[5]))
                for row in columns
            ]
            return (
                result is not None
                and result[0] == "ok"
                and version == _SCHEMA_VERSION
                and actual_columns == expected_columns
            )
        except (OSError, sqlite3.Error) as exc:
            raise GrantLedgerError(f"cannot verify grant ledger: {exc}") from exc
        finally:
            connection.close()

    def checkpoint(self) -> None:
        connection = self._connect()
        try:
            result = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if result is None or int(result[0]) != 0:
                raise GrantLedgerError(f"grant ledger WAL checkpoint was busy: {result!r}")
        except GrantLedgerError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise GrantLedgerError(f"cannot checkpoint grant ledger: {exc}") from exc
        finally:
            connection.close()

    @staticmethod
    def _rollback_quietly(connection: sqlite3.Connection) -> None:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass

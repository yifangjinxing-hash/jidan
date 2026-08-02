from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import gc
import json
import os
import sqlite3
import subprocess
import sys
import unittest
import weakref


PROTOTYPE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROTOTYPE_ROOT))

from demo import build_demo_runtime, build_plan  # noqa: E402
from jidan.registry import capability_digest  # noqa: E402
from jidan import (  # noqa: E402
    Capability,
    Effect,
    GrantConsumption,
    GrantLedgerError,
    JidanRuntime,
    PolicyEngine,
    SqliteGrantLedger,
    Step,
    TaskPlan,
    issue_grant,
)


class GrantLedgerTests(unittest.TestCase):
    def test_consumed_grant_stays_rejected_after_policy_and_runtime_restart(self) -> None:
        with TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "grants.sqlite3"
            runtime, secret, shopping_list = build_demo_runtime()
            runtime.policy = PolicyEngine(
                secret,
                grant_ledger=SqliteGrantLedger.create_new(ledger_path),
            )
            plan = build_plan()
            grant = issue_grant(
                secret,
                plan,
                [step.capability for step in plan.steps],
                {"mail.content.read", "local.inference", "shopping.list.write"},
                Effect.WRITE,
                approved_steps={"add_to_list"},
                capability_digests=runtime.registry.definition_digests(
                    step.capability for step in plan.steps
                ),
            )

            first = runtime.execute(plan, grant)
            snapshot = list(shopping_list)
            registry = runtime.registry
            old_runtime_reference = weakref.ref(runtime)
            old_policy_reference = weakref.ref(runtime.policy)
            old_ledger_reference = weakref.ref(runtime.policy.grant_ledger)
            del runtime
            gc.collect()
            self.assertIsNone(old_runtime_reference())
            self.assertIsNone(old_policy_reference())
            self.assertIsNone(old_ledger_reference())
            restarted = JidanRuntime(
                registry,
                PolicyEngine(secret, grant_ledger=SqliteGrantLedger.open_existing(ledger_path)),
            )
            replay = restarted.execute(plan, grant)

            self.assertEqual("completed", first.status)
            self.assertEqual("rejected", replay.status)
            self.assertTrue(
                all("already been consumed" in item.reason for item in replay.decisions)
            )
            self.assertEqual(snapshot, shopping_list)
            persisted = SqliteGrantLedger.open_existing(ledger_path)
            self.assertEqual(1, persisted.count())
            self.assertTrue(persisted.verify())

    def test_two_independent_processes_cannot_claim_the_same_nonce(self) -> None:
        with TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "race.sqlite3"
            start_path = Path(directory) / "start"
            SqliteGrantLedger.create_new(ledger_path)
            record = GrantConsumption(
                nonce="ab" * 16,
                task_id="cross-process-race",
                plan_hash="cd" * 32,
                signature_sha256="ef" * 32,
                consumed_at_ms=1,
            )
            environment = os.environ.copy()
            existing_pythonpath = environment.get("PYTHONPATH")
            environment["PYTHONPATH"] = (
                str(PROTOTYPE_ROOT)
                if not existing_pythonpath
                else str(PROTOTYPE_ROOT) + os.pathsep + existing_pythonpath
            )
            processes = []
            ready_paths = []
            for index in range(8):
                ready_path = Path(directory) / f"ready-{index}"
                ready_paths.append(ready_path)
                code = (
                    "from pathlib import Path;import time;"
                    "from jidan import GrantConsumption,SqliteGrantLedger;"
                    f"ledger=SqliteGrantLedger.open_existing({str(ledger_path)!r});"
                    f"record=GrantConsumption({record.nonce!r},{record.task_id!r},"
                    f"{record.plan_hash!r},{record.signature_sha256!r},{record.consumed_at_ms});"
                    f"ready=Path({str(ready_path)!r});start=Path({str(start_path)!r});"
                    "ready.write_text('ready',encoding='utf-8');"
                    "deadline=time.monotonic()+10;"
                    "exec(\"while not start.exists():\\n"
                    "    assert time.monotonic() < deadline, 'barrier timeout'\\n"
                    "    time.sleep(0.005)\");"
                    "print(int(ledger.consume(record)),flush=True)"
                )
                processes.append(
                    subprocess.Popen(
                    [sys.executable, "-c", code],
                    cwd=PROTOTYPE_ROOT,
                    env=environment,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                )
                )
            deadline = __import__("time").monotonic() + 10
            while not all(path.exists() for path in ready_paths):
                self.assertLess(__import__("time").monotonic(), deadline)
                __import__("time").sleep(0.005)
            start_path.touch()
            results = [process.communicate(timeout=15) for process in processes]

            self.assertEqual([0] * 8, [process.returncode for process in processes])
            claims = [stdout.strip() for stdout, _ in results]
            self.assertEqual(1, claims.count("1"))
            self.assertEqual(7, claims.count("0"))
            self.assertEqual([""] * 8, [stderr.strip() for _, stderr in results])
            persisted = SqliteGrantLedger.open_existing(ledger_path)
            self.assertEqual(1, persisted.count())
            self.assertTrue(persisted.verify())

    def test_full_runtime_replay_is_rejected_in_second_interpreter(self) -> None:
        with TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "runtime.sqlite3"
            grant_path = Path(directory) / "grant.json"
            side_effect_path = Path(directory) / "side-effect.txt"
            secret = bytes.fromhex("42" * 32)
            SqliteGrantLedger.create_new(ledger_path)
            capability = Capability(
                id="test.process_write",
                app="test",
                description="Append exactly one durable cross-process test marker",
                effect=Effect.WRITE,
                scopes=frozenset({"test.process.write"}),
                requires_confirmation=True,
                reversible=False,
                input_schema={"type": "object", "additionalProperties": False},
                output_schema={
                    "type": "object",
                    "required": ["ok"],
                    "properties": {"ok": {"type": "boolean"}},
                    "additionalProperties": False,
                },
            )
            definition_digests = {
                capability.id: capability_digest(capability)
            }
            plan = TaskPlan(
                id="cross.process.runtime",
                goal="Prove persistent replay rejection",
                steps=(Step("write", capability.id, {}),),
            )
            grant = issue_grant(
                secret,
                plan,
                {capability.id},
                capability.scopes,
                Effect.WRITE,
                approved_steps={"write"},
                capability_digests=definition_digests,
            )
            grant_path.write_text(
                json.dumps(
                    {
                        "task_id": grant.task_id,
                        "plan_hash": grant.plan_hash,
                        "capabilities": sorted(grant.capabilities),
                        "scopes": sorted(grant.scopes),
                        "approved_steps": sorted(grant.approved_steps),
                        "max_effect": int(grant.max_effect),
                        "expires_at": grant.expires_at,
                        "nonce": grant.nonce,
                        "signature": grant.signature,
                        "capability_digests": list(grant.capability_digests),
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            command = [
                sys.executable,
                str(PROTOTYPE_ROOT / "tests" / "grant_runtime_worker.py"),
                "--ledger",
                str(ledger_path),
                "--grant",
                str(grant_path),
                "--secret-hex",
                secret.hex(),
                "--side-effect",
                str(side_effect_path),
            ]
            first = subprocess.run(
                command,
                cwd=PROTOTYPE_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
                timeout=15,
            )
            second = subprocess.run(
                command,
                cwd=PROTOTYPE_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
                timeout=15,
            )

            self.assertEqual(0, first.returncode, first.stderr)
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual("completed", json.loads(first.stdout)["status"])
            second_result = json.loads(second.stdout)
            self.assertEqual("rejected", second_result["status"])
            self.assertEqual(0, second_result["receipts"])
            self.assertTrue(
                all("already been consumed" in reason for reason in second_result["reasons"])
            )
            self.assertEqual(["invoked"], side_effect_path.read_text(encoding="utf-8").splitlines())
            self.assertEqual(1, SqliteGrantLedger.open_existing(ledger_path).count())

    def test_wal_recovers_pre_and_post_commit_process_death(self) -> None:
        with TemporaryDirectory() as directory:
            pre_path = Path(directory) / "pre.sqlite3"
            post_path = Path(directory) / "post.sqlite3"
            pre_ledger = SqliteGrantLedger.create_new(pre_path)
            post_ledger = SqliteGrantLedger.create_new(post_path)
            record = GrantConsumption("aa" * 16, "crash", "bb" * 32, "cc" * 32, 1)
            insert_sql = (
                "INSERT INTO grant_consumptions "
                "(nonce,task_id,plan_hash,signature_sha256,consumed_at_ms) "
                "VALUES (?,?,?,?,?)"
            )
            pre_code = (
                "import os,sqlite3;"
                f"c=sqlite3.connect({str(pre_path)!r},isolation_level=None);"
                "c.execute('PRAGMA synchronous=FULL');c.execute('BEGIN IMMEDIATE');"
                f"c.execute({insert_sql!r},{(record.nonce, record.task_id, record.plan_hash, record.signature_sha256, record.consumed_at_ms)!r});"
                "os._exit(91)"
            )
            post_code = (
                "import os;from jidan import GrantConsumption,SqliteGrantLedger;"
                f"ledger=SqliteGrantLedger.open_existing({str(post_path)!r});"
                f"record=GrantConsumption({record.nonce!r},{record.task_id!r},"
                f"{record.plan_hash!r},{record.signature_sha256!r},{record.consumed_at_ms});"
                "assert ledger.consume(record);os._exit(92)"
            )
            pre = subprocess.run([sys.executable, "-c", pre_code], cwd=PROTOTYPE_ROOT)
            post = subprocess.run([sys.executable, "-c", post_code], cwd=PROTOTYPE_ROOT)

            self.assertEqual(91, pre.returncode)
            self.assertEqual(92, post.returncode)
            self.assertEqual(0, pre_ledger.count())
            self.assertTrue(pre_ledger.consume(record))
            self.assertEqual(1, post_ledger.count())
            self.assertFalse(post_ledger.consume(record))
            self.assertTrue(pre_ledger.verify())
            self.assertTrue(post_ledger.verify())

    def test_real_sqlite_busy_fails_runtime_closed(self) -> None:
        with TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "busy.sqlite3"
            ledger = SqliteGrantLedger.create_new(ledger_path, timeout_seconds=0.05)
            runtime, secret, shopping_list = build_demo_runtime()
            runtime.policy = PolicyEngine(secret, grant_ledger=ledger)
            plan = build_plan()
            grant = issue_grant(
                secret,
                plan,
                [step.capability for step in plan.steps],
                {"mail.content.read", "local.inference", "shopping.list.write"},
                Effect.WRITE,
                approved_steps={"add_to_list"},
                capability_digests=runtime.registry.definition_digests(
                    step.capability for step in plan.steps
                ),
            )
            blocker = sqlite3.connect(ledger_path, isolation_level=None)
            blocker.execute("BEGIN IMMEDIATE")
            try:
                result = runtime.execute(plan, grant)
            finally:
                blocker.execute("ROLLBACK")
                blocker.close()

            self.assertEqual("rejected", result.status)
            self.assertTrue(all("ledger rejected" in item.reason for item in result.decisions))
            self.assertEqual([], shopping_list)
            self.assertEqual(0, len(result.receipts))
            self.assertEqual(0, ledger.count())
            self.assertTrue(ledger.verify())

    def test_schema_version_and_shape_mismatches_are_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            version_path = Path(directory) / "version.sqlite3"
            SqliteGrantLedger.create_new(version_path)
            connection = sqlite3.connect(version_path)
            connection.execute("PRAGMA user_version=2")
            connection.close()
            with self.assertRaises(GrantLedgerError):
                SqliteGrantLedger.open_existing(version_path)

            shape_path = Path(directory) / "shape.sqlite3"
            connection = sqlite3.connect(shape_path)
            connection.execute("CREATE TABLE grant_consumptions (nonce TEXT PRIMARY KEY)")
            connection.execute("PRAGMA user_version=1")
            connection.commit()
            connection.close()
            with self.assertRaises(GrantLedgerError):
                SqliteGrantLedger.open_existing(shape_path)

    def test_corrupt_database_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "corrupt.sqlite3"
            ledger_path.write_bytes(b"not a sqlite database")

            with self.assertRaises(GrantLedgerError):
                SqliteGrantLedger.open_existing(ledger_path)

    def test_missing_ledger_never_silently_recreates(self) -> None:
        with TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "must-exist.sqlite3"

            with self.assertRaises(GrantLedgerError):
                SqliteGrantLedger.open_existing(ledger_path)
            self.assertFalse(ledger_path.exists())

            SqliteGrantLedger.create_new(ledger_path)
            ledger_path.unlink()
            with self.assertRaises(GrantLedgerError):
                SqliteGrantLedger.open_existing(ledger_path)
            self.assertFalse(ledger_path.exists())

    def test_create_new_rejects_existing_main_or_sidecar(self) -> None:
        with TemporaryDirectory() as directory:
            existing_path = Path(directory) / "existing.sqlite3"
            SqliteGrantLedger.create_new(existing_path)
            with self.assertRaises(GrantLedgerError):
                SqliteGrantLedger.create_new(existing_path)

            sidecar_path = Path(directory) / "sidecar.sqlite3"
            Path(str(sidecar_path) + "-wal").write_bytes(b"stale")
            with self.assertRaises(GrantLedgerError):
                SqliteGrantLedger.create_new(sidecar_path)
            self.assertFalse(sidecar_path.exists())

    def test_unavailable_ledger_fails_closed_before_side_effects(self) -> None:
        class BrokenLedger:
            persistent = True

            def consume(self, record: GrantConsumption) -> bool:
                del record
                raise GrantLedgerError("simulated durable storage failure")

        runtime, secret, shopping_list = build_demo_runtime()
        runtime.policy = PolicyEngine(secret, grant_ledger=BrokenLedger())
        plan = build_plan()
        grant = issue_grant(
            secret,
            plan,
            [step.capability for step in plan.steps],
            {"mail.content.read", "local.inference", "shopping.list.write"},
            Effect.WRITE,
            approved_steps={"add_to_list"},
            capability_digests=runtime.registry.definition_digests(
                step.capability for step in plan.steps
            ),
        )

        result = runtime.execute(plan, grant)

        self.assertEqual("rejected", result.status)
        self.assertTrue(all("ledger rejected" in item.reason for item in result.decisions))
        self.assertEqual([], shopping_list)
        self.assertEqual(0, len(result.receipts))


if __name__ == "__main__":
    unittest.main()

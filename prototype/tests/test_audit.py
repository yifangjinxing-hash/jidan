from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import sys
import time
import unittest


PROTOTYPE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROTOTYPE_ROOT))

from jidan.audit import ReceiptLog  # noqa: E402


WORKER = Path(__file__).with_name("receipt_log_worker.py")


class ReceiptLogConcurrencyTests(unittest.TestCase):
    def test_independent_processes_append_one_disk_verified_chain(self) -> None:
        with TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            receipt_path = directory / "receipts.jsonl"
            start_path = directory / "start"
            processes: list[subprocess.Popen[bytes]] = []
            ready_paths: list[Path] = []
            for index in range(8):
                ready_path = directory / f"ready-{index}"
                ready_paths.append(ready_path)
                processes.append(
                    subprocess.Popen(
                        [
                            sys.executable,
                            str(WORKER),
                            str(receipt_path),
                            str(ready_path),
                            str(start_path),
                            str(index),
                        ],
                        shell=False,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                )

            deadline = time.monotonic() + 15.0
            while not all(path.exists() for path in ready_paths):
                if time.monotonic() >= deadline:
                    for process in processes:
                        process.kill()
                    self.fail("receipt workers did not become ready")
                time.sleep(0.01)
            start_path.touch()

            failures = []
            for process in processes:
                stdout, stderr = process.communicate(timeout=20)
                if process.returncode != 0:
                    failures.append((process.returncode, stdout, stderr))
            self.assertEqual([], failures)

            reloaded = ReceiptLog(receipt_path)
            self.assertTrue(reloaded.verify())
            records = reloaded.all()
            self.assertEqual(8, len(records))
            self.assertEqual(
                {str(index) for index in range(8)},
                {record["output"]["worker"] for record in records},
            )


if __name__ == "__main__":
    unittest.main()

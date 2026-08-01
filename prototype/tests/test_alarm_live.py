from __future__ import annotations

from pathlib import Path
import base64
import contextlib
import io
import json
import subprocess
import sys
import unittest


PROTOTYPE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROTOTYPE_ROOT))

from alarm_live import _decode_message, _parser  # noqa: E402


class AlarmMessageTransportTests(unittest.TestCase):
    def test_decodes_ascii_safe_utf8_base64_without_loss(self) -> None:
        expected = "Jidan 实战闹钟"
        encoded = base64.b64encode(expected.encode("utf-8")).decode("ascii")

        self.assertEqual(expected, _decode_message(None, encoded))

    def test_plain_message_remains_the_default(self) -> None:
        self.assertEqual("普通标签", _decode_message("普通标签", None))

    def test_rejects_invalid_base64(self) -> None:
        with self.assertRaisesRegex(ValueError, "valid base64"):
            _decode_message(None, "not-base64!")

    def test_rejects_base64_that_is_not_utf8(self) -> None:
        encoded = base64.b64encode(b"\xff").decode("ascii")

        with self.assertRaisesRegex(ValueError, "valid base64-encoded UTF-8"):
            _decode_message(None, encoded)

    def test_rejects_noncanonical_base64(self) -> None:
        with self.assertRaisesRegex(ValueError, "canonical"):
            _decode_message(None, "QR==")

    def test_parser_rejects_both_message_transports(self) -> None:
        argv = [
            "--adb-path",
            "adb.exe",
            "--hour",
            "8",
            "--minutes",
            "0",
            "--message",
            "plain",
            "--message-utf8-base64",
            "cGxhaW4=",
            "--receipt-log",
            "receipts.jsonl",
            "--grant-ledger",
            "grants.sqlite3",
        ]

        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                _parser().parse_args(argv)

        self.assertEqual(2, raised.exception.code)

    def test_ascii_base64_survives_a_shell_free_process_boundary(self) -> None:
        expected = "Jidan 中文 ' & 🚀"
        encoded = base64.b64encode(expected.encode("utf-8")).decode("ascii")
        program = (
            "import base64,json,sys;"
            "print(json.dumps(base64.b64decode(sys.argv[1]).decode('utf-8')))"
        )

        completed = subprocess.run(
            [sys.executable, "-c", program, encoded],
            check=True,
            capture_output=True,
            shell=False,
        )

        self.assertEqual(expected, json.loads(completed.stdout.decode("utf-8")))

from __future__ import annotations

from pathlib import Path
import sys
import unittest


PROTOTYPE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROTOTYPE_ROOT))

from jidan.console import configure_utf8_stdio  # noqa: E402


class RecordingStream:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def reconfigure(self, **kwargs) -> None:
        self.calls.append(dict(kwargs))


class Utf8ConsoleTests(unittest.TestCase):
    def test_reconfigures_both_output_streams_as_utf8(self) -> None:
        stdout = RecordingStream()
        stderr = RecordingStream()

        configure_utf8_stdio(stdout=stdout, stderr=stderr)

        expected = [{"encoding": "utf-8", "errors": "backslashreplace"}]
        self.assertEqual(expected, stdout.calls)
        self.assertEqual(expected, stderr.calls)

    def test_ignores_streams_without_reconfigure(self) -> None:
        configure_utf8_stdio(stdout=object(), stderr=object())

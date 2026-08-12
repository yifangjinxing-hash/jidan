from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import json
import sys
import unittest


PROTOTYPE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROTOTYPE_ROOT))

from ninelights_gui import bundled_asset, run_self_test  # noqa: E402


class NineLightsGuiTests(unittest.TestCase):
    def test_checked_in_windows_icon_is_available(self) -> None:
        icon = bundled_asset("ninelights-icon.ico")

        self.assertTrue(icon.is_file())
        self.assertEqual(b"\x00\x00\x01\x00", icon.read_bytes()[:4])

    def test_headless_self_test_covers_all_levels_and_receipt_chain(self) -> None:
        output = StringIO()

        with redirect_stdout(output):
            exit_code = run_self_test()

        payload = json.loads(output.getvalue())
        self.assertEqual(0, exit_code)
        self.assertTrue(payload["ok"])
        self.assertEqual(
            ["cross", "corners", "full"],
            [level["levelId"] for level in payload["levels"]],
        )
        self.assertTrue(all(level["status"] == "won" for level in payload["levels"]))
        self.assertEqual(11, payload["receiptCount"])
        self.assertTrue(payload["receiptChainVerified"])


if __name__ == "__main__":
    unittest.main()
